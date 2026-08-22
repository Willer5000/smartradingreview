"""
kucoin_cache.py
================
Caché de velas KuCoin con TTL dinámico + Session HTTP con connection pooling.

OBJETIVO: reducir latencia y número de requests a KuCoin sin alterar la lógica
de análisis. Los DataFrames devueltos son idénticos a los que produce
requests.get(...) directo, solo que:
  - Reutilizan conexión TCP+TLS (Session)
  - Se cachean por (symbol, interval) durante TTL corto

TTL por temporalidad (basado en la duración de la vela):
  5m   -> 15s
  15m  -> 30s
  30m  -> 60s
  1h   -> 120s
  2h   -> 240s
  4h   -> 300s
  12h  -> 600s
  1D   -> 900s
  1W   -> 1800s

Esto significa que si dos análisis piden BTC-USDT 1h dentro de 120s, el
segundo lee el DataFrame del caché en 0 ms en vez de esperar 500-2000 ms
por la API de KuCoin.

USO desde app.py:
    from kucoin_cache import fetch_kucoin_candles
    df = fetch_kucoin_candles(symbol, interval)   # DataFrame o None si falló
"""

import time
import threading
import logging
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger('KUCOIN_CACHE')
logger.setLevel(logging.INFO)

# ============================================================================
# TTL por temporalidad (segundos)
# ============================================================================
# Se calcula como ~1/20 de la ventana de la vela. Suficientemente fresco
# para que el usuario nunca vea datos "viejos" respecto a la vela actual.
TTL_BY_INTERVAL = {
    '1m':   5,
    '3m':   10,
    '5m':   15,
    '15m':  30,
    '30m':  60,
    '1h':   120,
    '2h':   240,
    '4h':   300,
    '6h':   400,
    '8h':   500,
    '12h':  600,
    '1D':   900,
    '1d':   900,
    '1W':   1800,
    '1w':   1800,
}
DEFAULT_TTL = 60  # fallback si el intervalo no está en la tabla

# ============================================================================
# Intervalos KuCoin (mapping)
# ============================================================================
# Mismos valores que la constante KUCOIN_INTERVALS en app.py.
# Se declaran aquí para que kucoin_cache sea autosuficiente.
KUCOIN_INTERVALS = {
    '1m':   '1min',
    '3m':   '3min',
    '5m':   '5min',
    '15m':  '15min',
    '30m':  '30min',
    '1h':   '1hour',
    '2h':   '2hour',
    '4h':   '4hour',
    '6h':   '6hour',
    '8h':   '8hour',
    '12h':  '12hour',
    '1D':   '1day',
    '1d':   '1day',
    '1W':   '1week',
    '1w':   '1week',
}

# ============================================================================
# Session HTTP compartida con connection pooling
# ============================================================================
# Reutiliza conexiones TCP+TLS entre requests. Ganancia típica:
# - Cold: ~1000-2000 ms (TCP + TLS handshake + HTTP)
# - Con Session: ~200-500 ms (solo HTTP, conexión reutilizada)
_session_lock = threading.Lock()
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Retorna la Session compartida (creada perezosamente y thread-safe)."""
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            adapter = HTTPAdapter(
                pool_connections=20,   # hosts distintos
                pool_maxsize=50,       # conexiones simultáneas por host
                max_retries=0,         # el retry lo maneja el caller
                pool_block=False
            )
            s.mount('https://', adapter)
            s.mount('http://', adapter)
            s.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            })
            _session = s
            logger.info("Session HTTP KuCoin creada (pool_maxsize=50, keep-alive)")
    return _session


# ============================================================================
# Caché en memoria
# ============================================================================
# Estructura: { (symbol, interval): {'df': DataFrame, 'ts': float} }
_cache: dict = {}
_cache_lock = threading.Lock()

# Estadísticas (útil para debug)
_stats = {'hits': 0, 'misses': 0, 'errors': 0, 'fetches': 0}


def _ttl_for(interval: str) -> int:
    return TTL_BY_INTERVAL.get(interval, DEFAULT_TTL)


def _cache_get(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    """Devuelve DataFrame del caché si está fresco, None si expiró o no existe."""
    key = (symbol, interval)
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        age = time.time() - entry['ts']
        if age >= _ttl_for(interval):
            return None
        # Devolver una COPIA para que el caller pueda mutarla sin invalidar el caché.
        return entry['df'].copy()


def _cache_put(symbol: str, interval: str, df: pd.DataFrame) -> None:
    """Guarda el DataFrame en caché (thread-safe)."""
    key = (symbol, interval)
    with _cache_lock:
        _cache[key] = {'df': df, 'ts': time.time()}


# ============================================================================
# FETCH principal
# ============================================================================
def fetch_kucoin_candles(symbol: str, interval: str, timeout: int = 15) -> Optional[pd.DataFrame]:
    """
    Obtiene velas de KuCoin con caché por (symbol, interval).
    
    Retorna DataFrame con columnas [time, open, close, high, low, volume, turnover]
    en orden ascendente por tiempo, o None si falla.
    
    El caller decide qué hacer si retorna None (típicamente: fallback data).
    """
    # 1. Intentar caché
    cached = _cache_get(symbol, interval)
    if cached is not None:
        with _cache_lock:
            _stats['hits'] += 1
        return cached
    
    with _cache_lock:
        _stats['misses'] += 1
    
    # 2. Fetch remoto
    kucoin_interval = KUCOIN_INTERVALS.get(interval)
    if not kucoin_interval:
        logger.warning(f"Intervalo no soportado: {interval}")
        return None
    
    url = f"https://api.kucoin.com/api/v1/market/candles?symbol={symbol}&type={kucoin_interval}"
    session = _get_session()
    
    try:
        with _cache_lock:
            _stats['fetches'] += 1
        response = session.get(url, timeout=timeout)
        
        if response.status_code != 200:
            logger.warning(f"HTTP {response.status_code} KuCoin {symbol} {interval}: {response.text[:120]}")
            with _cache_lock:
                _stats['errors'] += 1
            return None
        
        data = response.json()
        if data.get('code') != '200000' or 'data' not in data:
            logger.warning(f"Respuesta KuCoin inválida {symbol} {interval}: code={data.get('code')}")
            with _cache_lock:
                _stats['errors'] += 1
            return None
        
        candles = data['data']
        if not candles or len(candles) < 30:
            logger.warning(f"Datos insuficientes KuCoin {symbol} {interval}: {len(candles) if candles else 0} velas")
            with _cache_lock:
                _stats['errors'] += 1
            return None
        
        df = pd.DataFrame(candles, columns=['time', 'open', 'close', 'high', 'low', 'volume', 'turnover'])
        df['time'] = pd.to_datetime(df['time'].astype(int), unit='s')
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df = df.sort_values('time').reset_index(drop=True)
        
        # Guardar en caché
        _cache_put(symbol, interval, df)
        # Devolver copia (defensa contra mutación del caller)
        return df.copy()
    
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout KuCoin {symbol} {interval}")
        with _cache_lock:
            _stats['errors'] += 1
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"ConnectionError KuCoin {symbol} {interval}: {str(e)[:100]}")
        with _cache_lock:
            _stats['errors'] += 1
        return None
    except Exception as e:
        logger.error(f"Excepción KuCoin {symbol} {interval}: {e}")
        with _cache_lock:
            _stats['errors'] += 1
        return None


def get_cache_stats() -> dict:
    """Devuelve estadísticas del caché (útil para /api/review/health)."""
    with _cache_lock:
        entries = len(_cache)
        total = _stats['hits'] + _stats['misses']
        hit_rate = (_stats['hits'] / total * 100) if total > 0 else 0.0
        return {
            'entries': entries,
            'hits': _stats['hits'],
            'misses': _stats['misses'],
            'fetches': _stats['fetches'],
            'errors': _stats['errors'],
            'hit_rate_pct': round(hit_rate, 1),
        }


def clear_cache() -> int:
    """Limpia el caché. Retorna cuántas entradas se borraron."""
    with _cache_lock:
        n = len(_cache)
        _cache.clear()
        return n


# ============================================================================
# Session compartida para OTRAS APIs (Fear&Greed, etc.)
# ============================================================================
def get_shared_session() -> requests.Session:
    """
    Exporta la Session compartida para que otros módulos (Fear&Greed,
    Telegram, etc.) también puedan reutilizarla.
    """
    return _get_session()
