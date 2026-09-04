# futures_system.py
# Sistema de análisis de FUTUROS - Extiende TradingExpertSystem del sistema principal
# Versión 1.0 - FASE 4
#
# CARACTERÍSTICAS:
# - 5 criptomonedas: BTC, ETH, SOL, XRP, ADA (contra USDT)
# - 6 temporalidades: 5m, 15m, 30m, 1h, 2h, 4h
# - Solo acciones LONG y SHORT (nunca COMPRA_SPOT/VENTA_SPOT)
# - Apalancamiento dinámico sin mínimo forzado y limitado por riesgo/ATR
# - Hereda TODA la lógica del sistema principal (traders, indicadores, patrones)
# - Correlación adaptada: BTC dominancia + BTC vs alts (no PAXG)
# - Usa el mismo Moderador con los 9 traders + ReviewTrader (cuando esté integrado)
# - Registra señales en Supabase con system_type='futures'

import logging
import math
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

# Importamos la clase base del sistema principal
from app import TradingExpertSystem, KUCOIN_INTERVALS, SYMBOLS as SPOT_SYMBOLS

logger = logging.getLogger('FUTURES')
logger.setLevel(logging.INFO)

# ============================================================================
# CONFIGURACIÓN DE FUTUROS
# ============================================================================

# Símbolos disponibles para futuros
FUTURES_SYMBOLS = {
    'BTC-USDT': {'name': 'BTC/USDT', 'type': 'crypto_major', 'decimals': 2},
    'ETH-USDT': {'name': 'ETH/USDT', 'type': 'crypto_major', 'decimals': 2},
    'SOL-USDT': {'name': 'SOL/USDT', 'type': 'crypto_alt', 'decimals': 2},
    'XRP-USDT': {'name': 'XRP/USDT', 'type': 'crypto_alt', 'decimals': 4},
    'ADA-USDT': {'name': 'ADA/USDT', 'type': 'crypto_alt', 'decimals': 4}
}

# Temporalidades para futuros (TF cortas)
FUTURES_TIMEFRAMES = {
    '5m':  {'name': '5 Minutos',  'type': 'scalping',   'kucoin': '5min'},
    '15m': {'name': '15 Minutos', 'type': 'scalping',   'kucoin': '15min'},
    '30m': {'name': '30 Minutos', 'type': 'intraday',   'kucoin': '30min'},
    '1h':  {'name': '1 Hora',     'type': 'intraday',   'kucoin': '1hour'},
    '2h':  {'name': '2 Horas',    'type': 'intraday',   'kucoin': '2hour'},
    '4h':  {'name': '4 Horas',    'type': 'intraday',   'kucoin': '4hour'}
}

# Contratos perpetuos USDT-M reales de KuCoin Futures.
# BTC se llama XBT dentro de la API de derivados de KuCoin.
FUTURES_CONTRACT_SYMBOLS = {
    'BTC-USDT': 'XBTUSDTM',
    'ETH-USDT': 'ETHUSDTM',
    'SOL-USDT': 'SOLUSDTM',
    'XRP-USDT': 'XRPUSDTM',
    'ADA-USDT': 'ADAUSDTM',
}

# Duración real de cada temporalidad. Se usa únicamente para comprobar
# si la última fila OHLCV ya cerró; no modifica indicadores ni niveles.
FUTURES_TIMEFRAME_SECONDS = {
    '5m': 5 * 60,
    '15m': 15 * 60,
    '30m': 30 * 60,
    '1h': 60 * 60,
    '2h': 2 * 60 * 60,
    '4h': 4 * 60 * 60,
}

# La API de Futures recibe la granularidad como minutos, no con los textos
# ("5min", "1hour", etc.) utilizados por la API Spot.
FUTURES_GRANULARITY_MINUTES = {
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '2h': 120,
    '4h': 240,
}

KUCOIN_FUTURES_KLINES_URL = (
    'https://api-futures.kucoin.com/api/v1/kline/query'
)
KUCOIN_FUTURES_DATA_SOURCE = 'KUCOIN_FUTURES_PERPETUAL_REST'
FUTURES_MIN_REAL_CANDLES = 100

# Caché corto e independiente del caché Spot. Evita repetir descargas durante
# un mismo refresco sin permitir que una respuesta vieja se convierta en una
# señal nueva.
FUTURES_DATA_TTL_SECONDS = {
    '5m': 15,
    '15m': 30,
    '30m': 60,
    '1h': 120,
    '2h': 240,
    '4h': 300,
}
_futures_data_cache = {}
_futures_data_cache_lock = threading.Lock()
_futures_fetch_inflight = {}
_futures_fetch_inflight_lock = threading.Lock()
_futures_http_session = None
_futures_http_session_lock = threading.Lock()


def _get_futures_http_session() -> requests.Session:
    """Crea una sesión HTTP reutilizable exclusivamente para Futures."""
    global _futures_http_session

    if _futures_http_session is not None:
        return _futures_http_session

    with _futures_http_session_lock:
        if _futures_http_session is None:
            session = requests.Session()
            adapter = HTTPAdapter(
                pool_connections=12,
                pool_maxsize=12,
                max_retries=0,
                pool_block=False,
            )
            session.mount('https://', adapter)
            session.headers.update({
                'Accept': 'application/json',
                'User-Agent': 'SmartTradingReview/1.0',
            })
            _futures_http_session = session

    return _futures_http_session


def _get_cached_futures_data(symbol: str, interval: str):
    """Devuelve una copia sólo cuando el caché Futures sigue fresco."""
    cache_key = (symbol, interval)
    ttl = FUTURES_DATA_TTL_SECONDS.get(interval, 30)

    with _futures_data_cache_lock:
        cached = _futures_data_cache.get(cache_key)
        if not cached:
            return None
        if time.monotonic() - cached['stored_at'] >= ttl:
            _futures_data_cache.pop(cache_key, None)
            return None
        return cached['df'].copy(deep=True)


def _store_futures_data(symbol: str, interval: str, df) -> None:
    """Guarda únicamente velas reales ya validadas."""
    cache_key = (symbol, interval)
    with _futures_data_cache_lock:
        _futures_data_cache[cache_key] = {
            'df': df.copy(deep=True),
            'stored_at': time.monotonic(),
        }

# Extender el mapeo de intervalos KuCoin
FUTURES_KUCOIN_INTERVALS = {
    '5m': '5min',
    '15m': '15min',
    '30m': '30min',
    '1h': '1hour',
    '2h': '2hour',
    '4h': '4hour'
}

# ============================================================================
# RANGOS DE LEVERAGE POR TEMPORALIDAD
# ============================================================================
#
# IMPORTANTE:
# Estos valores son TECHOS, NO mínimos obligatorios.
#
# El leverage final se determinará posteriormente usando:
#
#   1. Execution Safety
#   2. Distancia del SL
#   3. Calidad del TP
#   4. RR
#   5. Costes
#   6. Temporalidad
#   7. Viabilidad económica con el margen
#
# El mínimo operativo siempre puede ser 1x.
#
LEVERAGE_RANGES = {
    '5m':  (1, 50),
    '15m': (1, 40),
    '30m': (1, 30),
    '1h':  (1, 20),
    '2h':  (1, 15),
    '4h':  (1, 10),
}

# Banda preferida para operaciones con margen pequeño. No es un mínimo ciego:
# una señal por debajo de la banda puede publicarse si un TP amplio produce
# suficiente ROI y beneficio neto sin romper los límites de riesgo.
PREFERRED_LEVERAGE_RANGES = {
    '5m':  (25, 50),
    '15m': (20, 40),
    '30m': (15, 30),
    '1h':  (10, 20),
    '2h':  (8, 15),
    '4h':  (5, 10),
}
# ============================================================================
# ECONOMÍA DE FUTUROS — CONFIGURACIÓN
# ============================================================================
# El usuario trabaja normalmente con márgenes pequeños (~10 USDT).
#
# IMPORTANTE:
# El leverage no se determina únicamente por confianza.
# Debe ser viable después de costes y estar limitado por el riesgo del SL.
# ============================================================================

FUTURES_RISK_CONFIG = {

    # Margen habitual utilizado por el usuario.
    'default_margin_usdt': 10.0,

    # Beneficio neto mínimo deseado por operación.
    # No significa que todas las operaciones deban alcanzar esto:
    # sólo define el mínimo económico para considerar una entrada.
    'target_net_profit_usdt': 0.75,

    # Coste ida + vuelta estimado.
    #
    # DEBES reemplazar este valor por el coste REAL de tu exchange
    # incluyendo comisión y un margen prudente para slippage.
    #
    # Ejemplo ilustrativo: 0.12% = 0.0012
    'round_trip_cost_pct': 0.0012,

    # Máxima pérdida prevista sobre el margen si el SL se ejecuta
    # aproximadamente en el nivel calculado.
    #
    # No es una garantía de pérdida máxima real.
    # Slippage, gaps y liquidación pueden producir diferencias.
    'max_loss_pct_margin': 10.0,

    # Un movimiento adverso equivalente a 1.5 ATR no debería consumir más
    # de este porcentaje del margen. Es una prueba de estrés adicional para
    # evitar que un SL muy estrecho justifique leverage excesivo.
    'atr_stress_multiplier': 1.5,
    'max_atr_stress_loss_pct_margin': 30.0,

    # ROI bruto mínimo que debe poder producir el TP. Se incorpora desde el
    # cálculo del leverage para elegir el MENOR entero que cumpla el objetivo.
    'minimum_roi_tp_pct': 12.0,

    # Leverage máximo absoluto que el sistema permitirá.
    # Después también se aplicará el máximo específico del TF.
    'absolute_max_leverage': 50,

    # Porcentaje mínimo del score de seguridad necesario para
    # poder abrir futuros.
    'minimum_execution_safety': 65.0,

    # Con seguridad muy elevada se permite acercarse más al máximo.
    'high_safety_threshold': 90.0,

    # Filtro PREMIUM para Activas / Vela anterior. Una decisión direccional
    # que no lo supere sigue visible como análisis, pero no como oportunidad.
    'minimum_publication_execution_safety': 75.0,
    'minimum_publication_tp_quality': 55.0,
    'minimum_publication_sl_avoidance_quality': 60.0,
    'minimum_publication_rr': 1.8,
    'maximum_publication_rr': 3.5,
    'maximum_publication_loss_pct_margin': 8.0,
    'maximum_publication_atr_stress_loss_pct_margin': 25.0,
}

# ============================================================================
# CAPA CUANTITATIVA FUTURES — CONFIGURACIÓN POR TEMPORALIDAD
# ============================================================================
#
# Esta capa usa únicamente las velas OHLCV cerradas del contrato perpetuo que
# el sistema ya descargó. No consulta servicios de pago ni crea datos que no
# existen (footprint, bid/ask real, opciones o griegas).
#
# En este primer paso trabaja en SHADOW/OBSERVACIÓN: describe el régimen y la
# calidad del setup, pero NO puede aprobar, rechazar, aumentar leverage ni
# modificar Entry/SL/TP. Primero necesitamos guardar una cohorte limpia y
# comparar estas métricas con resultados reales.
FUTURES_QUANT_MODEL_VERSION = 'closed_returns_regime_v1'

FUTURES_QUANT_CONFIG = {
    # Los TF cortos exigen mayor eficiencia direccional porque contienen más
    # ruido. Los lookbacks se expresan en velas y siempre caben dentro de las
    # 100 velas reales mínimas exigidas al proveedor.
    '5m': {
        'trend_window': 36,
        'volatility_fast_window': 12,
        'volatility_slow_window': 72,
        'trend_efficiency_min': 0.30,
        'balance_efficiency_max': 0.16,
        'drift_strength_min': 1.10,
        'return_shock_z': 3.75,
        'volatility_shock_ratio': 2.25,
        'max_pullback_atr': 1.50,
    },
    '15m': {
        'trend_window': 32,
        'volatility_fast_window': 12,
        'volatility_slow_window': 64,
        'trend_efficiency_min': 0.28,
        'balance_efficiency_max': 0.17,
        'drift_strength_min': 1.05,
        'return_shock_z': 3.75,
        'volatility_shock_ratio': 2.20,
        'max_pullback_atr': 1.55,
    },
    '30m': {
        'trend_window': 28,
        'volatility_fast_window': 10,
        'volatility_slow_window': 56,
        'trend_efficiency_min': 0.26,
        'balance_efficiency_max': 0.18,
        'drift_strength_min': 1.00,
        'return_shock_z': 3.60,
        'volatility_shock_ratio': 2.15,
        'max_pullback_atr': 1.60,
    },
    '1h': {
        'trend_window': 24,
        'volatility_fast_window': 8,
        'volatility_slow_window': 48,
        'trend_efficiency_min': 0.24,
        'balance_efficiency_max': 0.19,
        'drift_strength_min': 0.95,
        'return_shock_z': 3.50,
        'volatility_shock_ratio': 2.10,
        'max_pullback_atr': 1.70,
    },
    '2h': {
        'trend_window': 20,
        'volatility_fast_window': 8,
        'volatility_slow_window': 40,
        'trend_efficiency_min': 0.22,
        'balance_efficiency_max': 0.20,
        'drift_strength_min': 0.90,
        'return_shock_z': 3.40,
        'volatility_shock_ratio': 2.05,
        'max_pullback_atr': 1.80,
    },
    '4h': {
        'trend_window': 18,
        'volatility_fast_window': 6,
        'volatility_slow_window': 36,
        'trend_efficiency_min': 0.20,
        'balance_efficiency_max': 0.20,
        'drift_strength_min': 0.85,
        'return_shock_z': 3.25,
        'volatility_shock_ratio': 2.00,
        'max_pullback_atr': 2.00,
    },
}

def _leverage_in_valid_range(
    leverage: int,
    timeframe: str
) -> bool:
    """
    Valida que el leverage no supere el techo del timeframe.

    Importante:
    - 1x siempre es válido si la operación supera las demás condiciones.
    - El máximo sí es una restricción dura.
    - Rentabilidad, SL, ATR y Execution Safety se validan por separado.

    Ejemplo:

        4h → techo 10x
        leverage calculado = 4x → válido
        leverage calculado = 11x → inválido
    """

    try:
        lev = int(leverage)
    except (
        TypeError,
        ValueError
    ):
        return False

    min_leverage, max_leverage = LEVERAGE_RANGES.get(
        timeframe,
        (1, 10)
    )

    return (
        min_leverage
        <= lev
        <= max_leverage
    )


# ============================================================================
# CLASE PRINCIPAL: FUTURES ANALYSIS
# ============================================================================

class FuturesAnalysis(TradingExpertSystem):
    """
    Sistema de análisis de futuros. Hereda TODA la lógica del sistema principal
    (indicadores, traders, moderador, votación) y sobreescribe solo lo específico
    de futuros:
    - Símbolos permitidos (5 cripto sin PAXG)
    - Temporalidades permitidas (5m-4h)
    - Cálculo de apalancamiento óptimo
    - Traducción de acciones (COMPRA_SPOT → LONG, VENTA_SPOT → SHORT)
    - Correlación (BTC dominancia + BTC vs alts)
    """
    
    def __init__(self):
        super().__init__()
        self._futures_data_errors = {}
        print("=" * 60)
        print("🚀 FUTURES ANALYSIS - INICIALIZANDO")
        print("=" * 60)
        print(f"✅ Símbolos: {list(FUTURES_SYMBOLS.keys())}")
        print(f"✅ Temporalidades: {list(FUTURES_TIMEFRAMES.keys())}")
        print(f"✅ Apalancamiento por TF:")
        for tf, (lo, hi) in LEVERAGE_RANGES.items():
            print(f"   {tf}: x{lo} - x{hi}")
        print("=" * 60)
    
    # ========================================================================
    # OVERRIDE: OBTENER DATOS DE KUCOIN (mapea TF cortas)
    # ========================================================================
    
    def get_kucoin_data(self, symbol: str, interval: str):
        """
        Obtiene velas REALES del contrato perpetuo KuCoin Futures.

        Reglas de seguridad:
        - nunca consulta el endpoint Spot;
        - nunca inventa velas cuando KuCoin falla;
        - valida esquema, timestamps y coherencia OHLC;
        - devuelve None ante cualquier duda para que NO se publique una señal.
        """
        error_key = (symbol, interval)
        contract_symbol = FUTURES_CONTRACT_SYMBOLS.get(symbol)
        granularity = FUTURES_GRANULARITY_MINUTES.get(interval)

        if not contract_symbol:
            error = f'Símbolo Futures no soportado: {symbol}'
            self._futures_data_errors[error_key] = error
            logger.warning(error)
            return None

        if not granularity:
            error = f'Temporalidad Futures no soportada: {interval}'
            self._futures_data_errors[error_key] = error
            logger.warning(error)
            return None

        cached = _get_cached_futures_data(symbol, interval)
        if cached is not None:
            self._futures_data_errors.pop(error_key, None)
            return cached

        # Single-flight: si otro hilo ya descarga exactamente el mismo
        # contrato+TF, esperamos su resultado en vez de duplicar la petición.
        with _futures_fetch_inflight_lock:
            inflight_event = _futures_fetch_inflight.get(error_key)
            if inflight_event is None:
                inflight_event = threading.Event()
                _futures_fetch_inflight[error_key] = inflight_event
                fetch_owner = True
            else:
                fetch_owner = False

        if not fetch_owner:
            if inflight_event.wait(timeout=20):
                cached_after_wait = _get_cached_futures_data(
                    symbol,
                    interval,
                )
                if cached_after_wait is not None:
                    self._futures_data_errors.pop(error_key, None)
                    return cached_after_wait

            self._futures_data_errors[error_key] = (
                'No se recibieron velas reales del contrato perpetuo'
            )
            return None

        try:
            session = _get_futures_http_session()
            response = session.get(
                KUCOIN_FUTURES_KLINES_URL,
                params={
                    'symbol': contract_symbol,
                    'granularity': granularity,
                },
                timeout=15,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f'KuCoin Futures respondió HTTP {response.status_code}'
                )

            payload = response.json()
            if payload.get('code') != '200000':
                raise RuntimeError(
                    'KuCoin Futures rechazó la consulta '
                    f"(code={payload.get('code', 'desconocido')})"
                )

            candles = payload.get('data')
            if not isinstance(candles, list):
                raise ValueError('Respuesta Futures sin lista de velas')

            # Esquema oficial Futures:
            # time, open, high, low, close, volume, turnover
            valid_rows = [
                row for row in candles
                if isinstance(row, (list, tuple)) and len(row) >= 7
            ]
            if len(valid_rows) < FUTURES_MIN_REAL_CANDLES:
                raise ValueError(
                    f'Sólo llegaron {len(valid_rows)} velas Futures válidas; '
                    f'se requieren al menos {FUTURES_MIN_REAL_CANDLES}'
                )

            df = pd.DataFrame(
                [row[:7] for row in valid_rows],
                columns=[
                    'time',
                    'open',
                    'high',
                    'low',
                    'close',
                    'volume',
                    'turnover',
                ],
            )

            df['time'] = pd.to_datetime(
                pd.to_numeric(df['time'], errors='coerce'),
                unit='ms',
                utc=True,
                errors='coerce',
            ).dt.tz_convert(None)

            numeric_columns = [
                'open', 'high', 'low', 'close', 'volume', 'turnover'
            ]
            for column in numeric_columns:
                df[column] = pd.to_numeric(df[column], errors='coerce')

            df = (
                df.dropna(subset=['time'] + numeric_columns)
                .drop_duplicates(subset=['time'], keep='last')
                .sort_values('time')
                .reset_index(drop=True)
            )

            coherent_ohlc = (
                (df['open'] > 0)
                & (df['high'] > 0)
                & (df['low'] > 0)
                & (df['close'] > 0)
                & (df['volume'] >= 0)
                & (df['high'] >= df[['open', 'close']].max(axis=1))
                & (df['low'] <= df[['open', 'close']].min(axis=1))
                & (df['high'] >= df['low'])
            )
            df = df.loc[coherent_ohlc].reset_index(drop=True)

            if len(df) < FUTURES_MIN_REAL_CANDLES:
                raise ValueError(
                    'Las velas Futures no superaron la validación OHLC '
                    f'({len(df)} válidas)'
                )

            fetched_at = datetime.utcnow().isoformat() + 'Z'
            df.attrs.update({
                'market_data_source': KUCOIN_FUTURES_DATA_SOURCE,
                'market_data_is_synthetic': False,
                'contract_symbol': contract_symbol,
                'fetched_at': fetched_at,
                'candles_count': int(len(df)),
            })

            _store_futures_data(symbol, interval, df)
            self._futures_data_errors.pop(error_key, None)
            logger.info(
                'Velas reales Futures cargadas: '
                f'{symbol}->{contract_symbol} {interval} ({len(df)})'
            )
            return df.copy(deep=True)

        except requests.exceptions.Timeout:
            error = 'Timeout consultando velas reales de KuCoin Futures'
        except requests.exceptions.ConnectionError:
            error = 'Sin conexión con KuCoin Futures'
        except Exception as exc:
            error = str(exc)
        finally:
            with _futures_fetch_inflight_lock:
                finished_event = _futures_fetch_inflight.pop(
                    error_key,
                    inflight_event,
                )
                finished_event.set()

        # Fail closed: sin velas reales no hay análisis ni señal.
        self._futures_data_errors[error_key] = error
        logger.warning(f'{symbol} {interval}: {error}')
        return None

    def _analyze_quantitative_futures_context(
        self,
        df: pd.DataFrame,
        action: str,
        timeframe: str,
        entry_price: Optional[float] = None,
    ) -> Dict:
        """
        Mide el contexto cuantitativo con velas perpetuas ya cerradas.

        Es una capa de investigación, no un oráculo ni una probabilidad de
        ganar. En ``SHADOW_OBSERVATION`` sus métricas se guardan para poder
        contrastarlas posteriormente con TP/SL reales; no cambia la decisión,
        los niveles, el leverage ni el filtro de publicación.
        """
        base = {
            'available': False,
            'model_version': FUTURES_QUANT_MODEL_VERSION,
            'mode': 'SHADOW_OBSERVATION',
            'calibrated': False,
            'affects_publication': False,
            'data_scope': 'CLOSED_PERPETUAL_OHLCV_ONLY',
            'quality_score_status': (
                'UNVALIDATED_PROXY_NOT_WIN_PROBABILITY'
            ),
            'limitations': [
                'NO_REAL_BID_ASK_OR_FOOTPRINT',
                'NO_OPTIONS_GREEKS_OR_GEX',
            ],
        }

        config = FUTURES_QUANT_CONFIG.get(timeframe)
        if not config:
            return {
                **base,
                'status': 'UNSUPPORTED_TIMEFRAME',
                'reason': f'Sin configuración cuantitativa para {timeframe}',
            }

        try:
            if not isinstance(df, pd.DataFrame):
                raise ValueError('Los datos cuantitativos no son un DataFrame')

            required_columns = ('high', 'low', 'close')
            missing = [column for column in required_columns if column not in df]
            if missing:
                raise ValueError(
                    'Faltan columnas OHLC: ' + ', '.join(missing)
                )

            prices = df.loc[:, required_columns].copy()
            for column in required_columns:
                prices[column] = pd.to_numeric(
                    prices[column],
                    errors='coerce',
                )

            valid_rows = pd.Series(True, index=prices.index)
            for column in required_columns:
                valid_rows &= prices[column].map(
                    lambda value: (
                        pd.notna(value)
                        and math.isfinite(float(value))
                        and float(value) > 0
                    )
                )

            prices = prices.loc[valid_rows].reset_index(drop=True)
            minimum_samples = max(
                int(config['volatility_slow_window']) + 2,
                int(config['trend_window']) + 2,
                30,
            )

            if len(prices) < minimum_samples:
                return {
                    **base,
                    'status': 'INSUFFICIENT_DATA',
                    'reason': (
                        f'{len(prices)} velas válidas; '
                        f'se requieren {minimum_samples}'
                    ),
                    'sample_size': int(len(prices)),
                    'minimum_sample_size': int(minimum_samples),
                    'shadow_verdict': 'INSUFFICIENT_DATA',
                }

            close = prices['close'].astype(float)
            high = prices['high'].astype(float)
            low = prices['low'].astype(float)
            returns = close.pct_change().dropna()

            trend_window = int(config['trend_window'])
            fast_window = int(config['volatility_fast_window'])
            slow_window = int(config['volatility_slow_window'])

            path = close.tail(trend_window + 1)
            path_changes = path.diff().dropna()
            path_distance = float(path_changes.abs().sum())
            net_move = float(path.iloc[-1] - path.iloc[0])
            efficiency_ratio = (
                abs(net_move) / path_distance
                if path_distance > 0
                else 0.0
            )
            trend_move_pct = (
                (float(path.iloc[-1]) / float(path.iloc[0]) - 1.0)
                * 100.0
            )

            trend_returns = returns.tail(trend_window)
            mean_return = float(trend_returns.mean())
            return_std = float(trend_returns.std(ddof=1) or 0.0)
            drift_strength = (
                mean_return
                / return_std
                * math.sqrt(len(trend_returns))
                if return_std > 1e-12
                else 0.0
            )

            short_volatility = float(
                returns.tail(fast_window).std(ddof=1) or 0.0
            )
            long_volatility = float(
                returns.tail(slow_window).std(ddof=1) or 0.0
            )
            if long_volatility > 1e-12:
                volatility_ratio = short_volatility / long_volatility
            elif short_volatility <= 1e-12:
                volatility_ratio = 1.0
            else:
                volatility_ratio = 99.0

            latest_return = float(returns.iloc[-1])
            return_history = returns.tail(slow_window + 1).iloc[:-1]
            return_median = float(return_history.median())
            median_deviation = float(
                (return_history - return_median).abs().median()
            )
            robust_sigma = median_deviation * 1.4826
            if robust_sigma <= 1e-12:
                robust_sigma = float(return_history.std(ddof=1) or 0.0)
            if robust_sigma > 1e-12:
                return_anomaly_z = (
                    latest_return - return_median
                ) / robust_sigma
            elif abs(latest_return - return_median) <= 1e-12:
                return_anomaly_z = 0.0
            else:
                return_anomaly_z = math.copysign(99.0, latest_return)
            return_anomaly_z = max(-99.0, min(99.0, return_anomaly_z))

            rolling_volatility = (
                returns
                .rolling(fast_window, min_periods=fast_window)
                .std(ddof=1)
                .dropna()
                .tail(slow_window)
            )
            if not rolling_volatility.empty:
                current_rolling_volatility = float(
                    rolling_volatility.iloc[-1]
                )
                volatility_percentile = float(
                    (rolling_volatility <= current_rolling_volatility).mean()
                    * 100.0
                )
            else:
                volatility_percentile = 50.0

            previous_close = close.shift(1)
            true_range = pd.concat(
                [
                    (high - low).abs(),
                    (high - previous_close).abs(),
                    (low - previous_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr = float(true_range.tail(14).mean() or 0.0)
            source_price = float(close.iloc[-1])
            atr_pct = (
                atr / source_price * 100.0
                if source_price > 0
                else 0.0
            )

            try:
                autocorrelation = float(
                    trend_returns.autocorr(lag=1) or 0.0
                )
                if not math.isfinite(autocorrelation):
                    autocorrelation = 0.0
            except Exception:
                autocorrelation = 0.0

            shock_detected = (
                abs(return_anomaly_z) >= float(config['return_shock_z'])
                or volatility_ratio
                >= float(config['volatility_shock_ratio'])
            )
            trend_detected = (
                efficiency_ratio >= float(config['trend_efficiency_min'])
                and abs(drift_strength)
                >= float(config['drift_strength_min'])
            )
            balance_detected = (
                efficiency_ratio <= float(config['balance_efficiency_max'])
                and abs(drift_strength)
                < float(config['drift_strength_min'])
            )

            if shock_detected:
                regime = 'VOLATILITY_SHOCK'
            elif trend_detected and trend_move_pct > 0:
                regime = 'TREND_UP'
            elif trend_detected and trend_move_pct < 0:
                regime = 'TREND_DOWN'
            elif balance_detected:
                regime = 'BALANCE'
            else:
                regime = 'TRANSITION'

            if trend_move_pct > 0 and drift_strength > 0:
                quantitative_direction = 'BULLISH'
            elif trend_move_pct < 0 and drift_strength < 0:
                quantitative_direction = 'BEARISH'
            else:
                quantitative_direction = 'NEUTRAL'

            normalized_action = str(action or 'NO_OPERAR').upper()
            if normalized_action == 'COMPRA_SPOT':
                normalized_action = 'LONG'
            elif normalized_action == 'VENTA_SPOT':
                normalized_action = 'SHORT'

            directional_setup = normalized_action in ('LONG', 'SHORT')
            direction_aligned = (
                (normalized_action == 'LONG'
                 and quantitative_direction == 'BULLISH')
                or
                (normalized_action == 'SHORT'
                 and quantitative_direction == 'BEARISH')
            )
            direction_conflict = (
                (normalized_action == 'LONG'
                 and quantitative_direction == 'BEARISH')
                or
                (normalized_action == 'SHORT'
                 and quantitative_direction == 'BULLISH')
            )

            if not directional_setup:
                direction_alignment = 'NOT_APPLICABLE'
            elif direction_aligned:
                direction_alignment = 'ALIGNED'
            elif direction_conflict:
                direction_alignment = 'CONFLICT'
            else:
                direction_alignment = 'NEUTRAL'

            entry_location = 'UNAVAILABLE'
            entry_distance_atr = None
            entry_pullback_signed_atr = None
            try:
                normalized_entry = float(entry_price or 0.0)
            except (TypeError, ValueError):
                normalized_entry = 0.0

            if directional_setup and normalized_entry > 0 and atr > 1e-12:
                if normalized_action == 'LONG':
                    entry_pullback_signed_atr = (
                        source_price - normalized_entry
                    ) / atr
                else:
                    entry_pullback_signed_atr = (
                        normalized_entry - source_price
                    ) / atr

                entry_distance_atr = abs(entry_pullback_signed_atr)
                if entry_pullback_signed_atr < -0.10:
                    entry_location = 'NOT_PULLBACK'
                elif entry_pullback_signed_atr <= 0.10:
                    entry_location = 'AT_SOURCE_PRICE'
                elif entry_pullback_signed_atr <= float(
                    config['max_pullback_atr']
                ):
                    entry_location = 'PULLBACK'
                else:
                    entry_location = 'DEEP_PULLBACK'

            reasons = []
            quality_score = 50.0

            if directional_setup:
                if direction_aligned:
                    quality_score += 20.0
                    reasons.append('Dirección cuantitativa alineada')
                elif direction_conflict:
                    quality_score -= 30.0
                    reasons.append('Dirección cuantitativa opuesta al setup')
                else:
                    quality_score -= 5.0
                    reasons.append('Dirección cuantitativa todavía neutral')

                if regime in ('TREND_UP', 'TREND_DOWN'):
                    quality_score += 15.0 if direction_aligned else 0.0
                    reasons.append(f'Régimen direccional {regime}')
                elif regime == 'VOLATILITY_SHOCK':
                    quality_score -= 25.0
                    reasons.append('Choque de volatilidad detectado')
                elif regime == 'BALANCE':
                    quality_score -= 15.0
                    reasons.append('Mercado en balance: menor ventaja direccional')
                else:
                    reasons.append('Mercado en transición')

                if entry_location == 'PULLBACK':
                    quality_score += 10.0
                    reasons.append('Entry ubicado en retroceso medido por ATR')
                elif entry_location == 'AT_SOURCE_PRICE':
                    quality_score += 3.0
                    reasons.append('Entry próximo al cierre fuente')
                elif entry_location == 'NOT_PULLBACK':
                    quality_score -= 20.0
                    reasons.append('Entry no está en retroceso')
                elif entry_location == 'DEEP_PULLBACK':
                    quality_score -= 10.0
                    reasons.append('Entry profundo: menor probabilidad de toque')
                else:
                    quality_score -= 5.0
                    reasons.append('No se pudo evaluar la ubicación del Entry')

                if abs(return_anomaly_z) < 2.0:
                    quality_score += 5.0
                elif shock_detected:
                    quality_score -= 15.0

                if 0.60 <= volatility_ratio <= 1.50:
                    quality_score += 5.0
                elif volatility_ratio >= float(
                    config['volatility_shock_ratio']
                ):
                    quality_score -= 10.0

            quality_score = round(max(0.0, min(100.0, quality_score)), 2)

            if not directional_setup:
                shadow_verdict = 'NO_DIRECTIONAL_SETUP'
            elif (
                shock_detected
                or direction_conflict
                or entry_location == 'NOT_PULLBACK'
            ):
                shadow_verdict = 'REJECT_CANDIDATE'
            elif (
                quality_score >= 70.0
                and direction_aligned
                and regime in ('TREND_UP', 'TREND_DOWN')
            ):
                shadow_verdict = 'FAVORABLE_CANDIDATE'
            elif quality_score >= 55.0:
                shadow_verdict = 'CAUTION_CANDIDATE'
            else:
                shadow_verdict = 'REJECT_CANDIDATE'

            return {
                **base,
                'available': True,
                'status': 'OBSERVED_NOT_ENFORCED',
                'sample_size': int(len(prices)),
                'minimum_sample_size': int(minimum_samples),
                'timeframe': timeframe,
                'action_evaluated': normalized_action,
                'regime': regime,
                'direction': quantitative_direction,
                'direction_alignment': direction_alignment,
                'entry_location': entry_location,
                'shadow_verdict': shadow_verdict,
                'quality_score': quality_score,
                'reasons': reasons,
                'metrics': {
                    'source_price': round(source_price, 10),
                    'latest_return_pct': round(latest_return * 100.0, 6),
                    'return_anomaly_robust_z': round(return_anomaly_z, 4),
                    'directional_efficiency_ratio': round(
                        efficiency_ratio,
                        4,
                    ),
                    'trend_move_pct': round(trend_move_pct, 6),
                    'drift_strength': round(drift_strength, 4),
                    'return_autocorrelation_lag1': round(
                        autocorrelation,
                        4,
                    ),
                    'realized_volatility_fast_pct': round(
                        short_volatility * 100.0,
                        6,
                    ),
                    'realized_volatility_slow_pct': round(
                        long_volatility * 100.0,
                        6,
                    ),
                    'fast_slow_volatility_ratio': round(
                        volatility_ratio,
                        4,
                    ),
                    'volatility_percentile': round(
                        volatility_percentile,
                        2,
                    ),
                    'atr_pct': round(atr_pct, 6),
                    'entry_distance_atr': (
                        round(entry_distance_atr, 4)
                        if entry_distance_atr is not None
                        else None
                    ),
                    'entry_pullback_signed_atr': (
                        round(entry_pullback_signed_atr, 4)
                        if entry_pullback_signed_atr is not None
                        else None
                    ),
                },
                'thresholds': {
                    key: (
                        int(value)
                        if isinstance(value, int)
                        else float(value)
                    )
                    for key, value in config.items()
                },
            }

        except Exception as exc:
            logger.warning(
                'Capa cuantitativa Futures no disponible para %s: %s',
                timeframe,
                exc,
            )
            return {
                **base,
                'status': 'CALCULATION_ERROR',
                'reason': str(exc),
                'shadow_verdict': 'UNAVAILABLE',
            }
            
    def _calculate_execution_safety(
        self,
        levels: Dict,
        trend: Dict,
        momentum: Dict,
        structure: Dict,
        timeframe: str
    ) -> Dict:
        """
        Calcula la SEGURIDAD DE EJECUCIÓN de una señal de futuros.
    
        IMPORTANTE:
        Este score NO es una probabilidad matemática.
    
        Representa calidad de ejecución:
    
            ENTRY
            SL
            TP
            RR
            SMC
            estructura
            temporalidad
    
        La confianza del comité NO participa directamente.
    
        El score será recalibrado estadísticamente por ReviewTrader
        en una fase posterior.
        """
    
        try:
    
            # ==============================================================
            # SCORES BASE
            # ==============================================================
    
            entry_score = float(
                levels.get(
                    'entry_score',
                    0
                )
                or 0
            )
    
            tp_quality = float(
                levels.get(
                    'tp_quality_score',
                    0
                )
                or 0
            )
    
            sl_reliability_raw = float(
                levels.get(
                    'sl_reliability',
                    0
                )
                or 0
            )
    
            # app.py entrega actualmente sl_reliability
            # normalizado 0-1.
            if sl_reliability_raw <= 1:
                sl_quality = (
                    sl_reliability_raw * 100
                )
            else:
                sl_quality = sl_reliability_raw
    
            rr = float(
                levels.get(
                    'risk_reward',
                    0
                )
                or 0
            )
    
            # ==============================================================
            # 1. ENTRY SMC
            # ==============================================================
            entry_component = max(
                0,
                min(
                    100,
                    entry_score
                )
            )
    
            # ==============================================================
            # 2. SL
            # ==============================================================
            sl_component = max(
                0,
                min(
                    100,
                    sl_quality
                )
            )
    
            # ==============================================================
            # 3. TP
            # ==============================================================
            tp_component = max(
                0,
                min(
                    100,
                    tp_quality
                )
            )
    
            # ==============================================================
            # 4. RR
            # ==============================================================
            if rr < 1.8:
                rr_component = 0
    
            elif rr < 2.0:
                rr_component = 45
    
            elif rr < 2.5:
                rr_component = 65
    
            elif rr < 3.0:
                rr_component = 80
    
            elif rr < 3.5:
                rr_component = 90
    
            elif rr <= 4.5:
                rr_component = 100
    
            else:
                # Un RR demasiado grande suele implicar
                # un TP excesivamente lejano.
                rr_component = 65
    
            # ==============================================================
            # 5. CONDICIONES ESTRUCTURALES
            # ==============================================================
            structure_component = 50
    
            if isinstance(
                structure,
                dict
            ):
    
                order_blocks = structure.get(
                    'order_blocks',
                    []
                ) or []
    
                fvgs = structure.get(
                    'fair_value_gaps',
                    []
                ) or []
    
                sweeps = structure.get(
                    'liquidity_sweeps',
                    []
                ) or []
    
                if order_blocks:
                    structure_component += 10
    
                if fvgs:
                    structure_component += 10
    
                if sweeps:
                    structure_component += 15
    
            structure_component = min(
                100,
                structure_component
            )
    
            # ==============================================================
            # 6. MOMENTUM / TREND
            # ==============================================================
            trend_component = 50
    
            if isinstance(
                trend,
                dict
            ):
    
                adx = float(
                    trend.get(
                        'adx',
                        0
                    )
                    or 0
                )
    
                if adx >= 30:
                    trend_component += 20
    
                elif adx >= 25:
                    trend_component += 10
    
                elif adx < 15:
                    trend_component -= 20
    
            if isinstance(
                momentum,
                dict
            ):
    
                momentum_direction = str(
                    momentum.get(
                        'direction',
                        ''
                    )
                ).lower()
    
                if momentum_direction in (
                    'bullish',
                    'bearish'
                ):
                    trend_component += 10
    
            trend_component = max(
                0,
                min(
                    100,
                    trend_component
                )
            )
    
            # ==============================================================
            # 7. FACTOR TEMPORAL
            # ==============================================================
            #
            # La cohorte histórica anterior mezcló señales Spot con Futuros y
            # no puede decidir qué temporalidad es "mejor". Hasta que el
            # ReviewTrader reúna una muestra limpia de perpetuos reales, todos
            # los TF reciben el mismo valor NEUTRAL.
            #
            # 0.50 significa "sin evidencia estadística", NO 50% de acierto.
            # Además es deliberadamente prudente: no aumenta el score de
            # ninguna temporalidad ni autoriza más leverage.
            timeframe_factor = 0.50
            timeframe_factor_source = (
                'NEUTRAL_PENDING_CLEAN_FUTURES_COHORT'
            )
    
            timeframe_component = (
                timeframe_factor
                * 100
            )
    
            # ==============================================================
            # SCORE FINAL
            # ==============================================================
            #
            # Pesos:
            #
            # ENTRY SMC       25%
            # SL              20%
            # TP              15%
            # RR              15%
            # estructura      10%
            # tendencia       5%
            # temporalidad    10%
            #
            score = (
                entry_component * 0.25
                + sl_component * 0.20
                + tp_component * 0.15
                + rr_component * 0.15
                + structure_component * 0.10
                + trend_component * 0.05
                + timeframe_component * 0.10
            )
    
            score = max(
                0,
                min(
                    100,
                    score
                )
            )
    
            # ==============================================================
            # CLASIFICACIÓN
            # ==============================================================
            if score >= 85:
                label = 'PREMIUM'
    
            elif score >= 75:
                label = 'ALTA'
    
            elif score >= 65:
                label = 'VALIDA'
    
            elif score >= 55:
                label = 'BAJA'
    
            else:
                label = 'RECHAZAR'
    
            return {
                'score': round(
                    score,
                    1
                ),
                'label': label,
    
                'components': {
                    'entry_smc': round(
                        entry_component,
                        1
                    ),
                    'sl': round(
                        sl_component,
                        1
                    ),
                    'tp': round(
                        tp_component,
                        1
                    ),
                    'rr': round(
                        rr_component,
                        1
                    ),
                    'structure': round(
                        structure_component,
                        1
                    ),
                    'trend': round(
                        trend_component,
                        1
                    ),
                    'timeframe': round(
                        timeframe_component,
                        1
                    )
                },
    
                'timeframe_factor': round(
                    timeframe_factor,
                    3
                ),

                'timeframe_factor_source': (
                    timeframe_factor_source
                ),

                'timeframe_factor_statistically_calibrated': False
            }
    
        except Exception as e:
    
            logger.warning(
                f"Error calculando execution safety: {e}"
            )
    
            return {
                'score': 0,
                'label': 'RECHAZAR',
                'components': {},
                'timeframe_factor': 0,
                'timeframe_factor_source': 'ERROR',
                'timeframe_factor_statistically_calibrated': False
            }    
    # ========================================================================
    # CÁLCULO DE APALANCAMIENTO ÓPTIMO
    # ========================================================================
    def _calculate_economic_leverage(
        self,
        margin_usdt,
        tp_distance_pct,
        sl_distance_pct,
        atr_pct,
        execution_safety,
        timeframe
    ):
        """
        Elige el MENOR leverage entero que hace viable la operación.

        Debe caber simultáneamente bajo cuatro techos independientes:
        riesgo del SL, estrés de volatilidad ATR, Execution Safety y TF.
        Si el mínimo rentable no cabe bajo todos los techos, devuelve None.
        """
        try:
            margin = float(
                margin_usdt
                or FUTURES_RISK_CONFIG['default_margin_usdt']
            )

            tp_pct = abs(float(tp_distance_pct or 0))
            sl_pct = abs(float(sl_distance_pct or 0))
            normalized_atr_pct = abs(float(atr_pct or 0))
            safety = max(
                0.0,
                min(100.0, float(execution_safety or 0))
            )

            if (
                margin <= 0
                or tp_pct <= 0
                or sl_pct <= 0
                or normalized_atr_pct <= 0
            ):
                return None

            # El TP debe dejar ventaja después del coste de entrada y salida.
            round_trip_cost = float(
                FUTURES_RISK_CONFIG['round_trip_cost_pct']
            )
            edge_after_cost = (
                tp_pct / 100.0
                - round_trip_cost
            )

            if edge_after_cost <= 0:
                return None

            target_profit = float(
                FUTURES_RISK_CONFIG[
                    'target_net_profit_usdt'
                ]
            )
            min_leverage_economic = (
                target_profit
                / (margin * edge_after_cost)
            )

            minimum_roi_tp = float(
                FUTURES_RISK_CONFIG['minimum_roi_tp_pct']
            )
            min_leverage_by_roi = minimum_roi_tp / tp_pct

            # Techo 1: pérdida prevista si se ejecuta el SL.
            max_loss_pct = float(
                FUTURES_RISK_CONFIG[
                    'max_loss_pct_margin'
                ]
            )
            max_leverage_by_risk = (
                max_loss_pct
                / sl_pct
            )

            # Techo 2: prueba de estrés. Aunque el SL sea estrecho, un salto
            # adverso de 1.5 ATR no debe acercar el margen a liquidación.
            atr_stress_multiplier = float(
                FUTURES_RISK_CONFIG['atr_stress_multiplier']
            )
            atr_stress_move_pct = max(
                sl_pct,
                normalized_atr_pct * atr_stress_multiplier,
            )
            max_atr_stress_loss = float(
                FUTURES_RISK_CONFIG[
                    'max_atr_stress_loss_pct_margin'
                ]
            )
            max_leverage_by_atr_stress = (
                max_atr_stress_loss / atr_stress_move_pct
            )

            # Techo 3: temporalidad y techo absoluto del sistema.
            min_leverage_tf, tf_max = LEVERAGE_RANGES.get(
                timeframe,
                (1, 10)
            )
            absolute_max = float(
                FUTURES_RISK_CONFIG[
                    'absolute_max_leverage'
                ]
            )
            max_leverage_by_policy = min(
                float(tf_max),
                absolute_max
            )

            # Techo 4: una mejor puntuación permite utilizar una parte mayor
            # del techo, pero nunca convierte directamente 90 puntos en 90x.
            security_factor = (
                0.25
                + 0.75 * (safety / 100.0)
            )
            if safety >= FUTURES_RISK_CONFIG[
                'high_safety_threshold'
            ]:
                security_factor = min(
                    1.0,
                    security_factor + 0.05
                )
            max_leverage_by_security = (
                max_leverage_by_policy
                * security_factor
            )

            final_max_leverage = min(
                max_leverage_by_risk,
                max_leverage_by_atr_stress,
                max_leverage_by_security,
                max_leverage_by_policy,
            )

            minimum_required = max(
                float(min_leverage_tf),
                min_leverage_economic,
                min_leverage_by_roi,
            )
            minimum_required_integer = int(math.ceil(minimum_required))
            maximum_safe_integer = int(math.floor(final_max_leverage))

            if (
                maximum_safe_integer < 1
                or minimum_required_integer > maximum_safe_integer
            ):
                logger.info(
                    f'FUTURES {timeframe} sin leverage viable: '
                    f'mínimo rentable {minimum_required:.2f}x > '
                    f'máximo seguro {final_max_leverage:.2f}x'
                )
                return None

            # No premiamos una señal con más riesgo. Se recomienda el menor
            # entero que supera rentabilidad y ROI sin romper ningún techo.
            leverage = minimum_required_integer

            return {
                'leverage': leverage,
                'min_economic': round(
                    min_leverage_economic,
                    2
                ),
                'min_by_roi': round(
                    min_leverage_by_roi,
                    2
                ),
                'max_by_risk': round(
                    max_leverage_by_risk,
                    2
                ),
                'max_by_atr_stress': round(
                    max_leverage_by_atr_stress,
                    2
                ),
                'max_by_security': round(
                    max_leverage_by_security,
                    2
                ),
                'max_safe': round(
                    final_max_leverage,
                    2
                ),
                'min_by_timeframe': int(
                    min_leverage_tf
                ),
                'max_by_timeframe': int(
                    tf_max
                ),
                'atr_pct': round(
                    normalized_atr_pct,
                    4
                ),
                'atr_stress_move_pct': round(
                    atr_stress_move_pct,
                    4
                ),
                'estimated_atr_stress_loss_pct_margin': round(
                    atr_stress_move_pct * leverage,
                    2
                ),
                'security_factor': round(
                    security_factor,
                    3
                ),
                'selection_policy': 'MINIMUM_SAFE_VIABLE',
                'economically_viable': True
            }

        except Exception as e:
            logger.warning(
                f"Error en cálculo económico de leverage: {e}"
            )
            return None    
   
    def calculate_optimal_leverage(
        self,
        timeframe: str,
        atr_pct: float,
        confidence: float,
        review_multiplier: float = 1.0,
        sl_distance_pct: float = None,
        max_loss_pct_of_margin: float = 10.0,
        execution_safety: float = 0.0,
        tp_distance_pct: float = None,
        margin_usdt: float = None
    ) -> int:

        """
        Calcula el leverage dinámico de futuros.
        
        El leverage final NO depende directamente de confidence.
        
        Se determina mediante:
        
            - Execution Safety
            - distancia del SL
            - distancia del TP
            - coste operativo
            - temporalidad
            - techo de leverage
        
        La seguridad del SL limita el leverage máximo.
        
        La rentabilidad mínima determina el leverage mínimo
        económicamente necesario.
        
        Si el leverage mínimo económico supera el máximo seguro:
            → NO OPERAR.
        
        El objetivo es que una operación con margen pequeño
        (~10 USDT) siga siendo económicamente útil sin aumentar
        artificialmente el riesgo.
        """
    
        economic = self._calculate_economic_leverage(
            margin_usdt=(
                margin_usdt
                or FUTURES_RISK_CONFIG[
                    'default_margin_usdt'
                ]
            ),
            tp_distance_pct=(
                tp_distance_pct
                or 0
            ),
            sl_distance_pct=(
                sl_distance_pct
                or 0
            ),
            atr_pct=(
                atr_pct
                or 0
            ),
            execution_safety=execution_safety,
            timeframe=timeframe
        )
    
        if not economic:
    
            return 0
    
        return int(
            economic.get(
                'leverage',
                0
            )
        )
    @staticmethod
    def _stamp_futures_filter_trace(
        levels: Dict,
        stage: str,
        reason_codes=None,
        reason: str = '',
        reached_publication_gate: bool = False,
        outcome: str = 'ANALYSIS_ONLY'
    ) -> Dict:
        """
        Commit 36E — instrumentación del funnel Futures en el ORIGEN.

        Sólo agrega metadata diagnóstica. No cambia:
        Entry, SL, TP, RR, leverage, Safety ni elegibilidad.
        """
        result = dict(levels or {})

        raw_codes = reason_codes or []
        if not isinstance(raw_codes, (list, tuple, set)):
            raw_codes = [raw_codes]

        codes = []
        for raw_code in raw_codes:
            code = str(raw_code or '').strip().upper()
            if code and code not in codes:
                codes.append(code)

        normalized_stage = str(
            stage or 'UNKNOWN'
        ).strip().upper()

        normalized_outcome = str(
            outcome or 'ANALYSIS_ONLY'
        ).strip().upper()

        trace = {
            'instrumentation_version':
                'futures_filter_trace_v1',

            'stage':
                normalized_stage,

            'reached_publication_gate':
                bool(reached_publication_gate),

            'outcome':
                normalized_outcome,

            'rejected':
                bool(codes),

            'reason_codes':
                codes,

            'reason':
                str(reason or '')[:240],

            'diagnostic_only':
                True,

            'affects_publication':
                False,

            'affects_weights':
                False
        }

        result[
            'futures_filter_trace'
        ] = trace

        result[
            'futures_filter_stage'
        ] = normalized_stage

        result[
            'futures_filter_reason_codes'
        ] = list(codes)

        result[
            'futures_filter_reason_code'
        ] = (
            codes[0]
            if len(codes) == 1
            else None
        )

        result[
            'futures_rejection_stage'
        ] = (
            normalized_stage
            if codes
            else None
        )

        result[
            'futures_rejection_code'
        ] = (
            codes[0]
            if len(codes) == 1
            else None
        )

        return result
        
    def _apply_futures_publication_gate(
        self,
        levels: Dict,
        timeframe: str
    ) -> Dict:
        """
        Decide si un análisis merece aparecer como oportunidad de Futuros.

        Los niveles técnicos siempre se conservan. Si falla este filtro, el
        resultado continúa visible como ANALYSIS_ONLY, pero no entra en las
        listas Activas ni Vela anterior.

        `tp_quality_score` y `sl_reliability` son proxies de calidad; todavía
        NO son probabilidades estadísticas calibradas de toque/no toque.
        """
        result = dict(levels or {})
        risk_control = dict(result.get('risk_control') or {})

        def safe_float(value, default=0.0):
            try:
                return float(value if value is not None else default)
            except (TypeError, ValueError):
                return float(default)

        leverage = int(safe_float(result.get('leverage'), 0))
        safety = safe_float(result.get('execution_safety'))
        tp_quality = safe_float(result.get('tp_quality_score'))
        sl_quality_raw = safe_float(result.get('sl_reliability'))
        sl_avoidance_quality = (
            sl_quality_raw * 100.0
            if sl_quality_raw <= 1.0
            else sl_quality_raw
        )
        rr = safe_float(result.get('risk_reward'))
        roi_tp = safe_float(result.get('roi_tp'))
        roi_sl_abs = abs(safe_float(result.get('roi_sl')))
        net_profit = safe_float(result.get('net_profit_tp_usdt'))
        atr_stress_loss = safe_float(
            risk_control.get('estimated_atr_stress_loss_pct_margin')
        )

        preferred_min, preferred_max = PREFERRED_LEVERAGE_RANGES.get(
            timeframe,
            (1, LEVERAGE_RANGES.get(timeframe, (1, 10))[1])
        )
        in_preferred_band = preferred_min <= leverage <= preferred_max

        thresholds = {
            'execution_safety_min': float(
                FUTURES_RISK_CONFIG[
                    'minimum_publication_execution_safety'
                ]
            ),
            'tp_quality_min': float(
                FUTURES_RISK_CONFIG['minimum_publication_tp_quality']
            ),
            'sl_avoidance_quality_min': float(
                FUTURES_RISK_CONFIG[
                    'minimum_publication_sl_avoidance_quality'
                ]
            ),
            'risk_reward_min': float(
                FUTURES_RISK_CONFIG['minimum_publication_rr']
            ),
            'risk_reward_max': float(
                FUTURES_RISK_CONFIG['maximum_publication_rr']
            ),
            'roi_tp_min': float(
                FUTURES_RISK_CONFIG['minimum_roi_tp_pct']
            ),
            'net_profit_min_usdt': float(
                FUTURES_RISK_CONFIG['target_net_profit_usdt']
            ),
            'loss_at_sl_max_pct_margin': float(
                FUTURES_RISK_CONFIG[
                    'maximum_publication_loss_pct_margin'
                ]
            ),
            'atr_stress_loss_max_pct_margin': float(
                FUTURES_RISK_CONFIG[
                    'maximum_publication_atr_stress_loss_pct_margin'
                ]
            ),
        }

        rejection_reasons = []
        rejection_reason_codes = []

        def require(condition, code, reason):
            if not condition:
                rejection_reasons.append(reason)

                normalized_code = str(
                    code or 'OTHER'
                ).strip().upper()

                if (
                    normalized_code
                    and normalized_code
                    not in rejection_reason_codes
                ):
                    rejection_reason_codes.append(
                        normalized_code
                    )

        require(
            safety
            >= thresholds[
                'execution_safety_min'
            ],
            'SAFETY',
            (
                f"Safety {safety:.1f} < "
                f"{thresholds['execution_safety_min']:.1f}"
            )
        )

        require(
            tp_quality
            >= thresholds[
                'tp_quality_min'
            ],
            'TP_QUALITY',
            (
                f"calidad TP {tp_quality:.1f} < "
                f"{thresholds['tp_quality_min']:.1f}"
            )
        )

        require(
            sl_avoidance_quality
            >= thresholds[
                'sl_avoidance_quality_min'
            ],
            'SL_QUALITY',
            (
                'protección SL '
                f"{sl_avoidance_quality:.1f} < "
                f"{thresholds['sl_avoidance_quality_min']:.1f}"
            )
        )

        require(
            thresholds[
                'risk_reward_min'
            ]
            <= rr
            <= thresholds[
                'risk_reward_max'
            ],
            'RR',
            (
                'R/R fuera de banda premium '
                f"{thresholds['risk_reward_min']:.1f}-"
                f"{thresholds['risk_reward_max']:.1f}"
            )
        )

        require(
            roi_tp
            >= thresholds[
                'roi_tp_min'
            ],
            'ROI_TP',
            (
                f"ROI TP {roi_tp:.1f}% < "
                f"{thresholds['roi_tp_min']:.1f}%"
            )
        )

        require(
            net_profit
            >= thresholds[
                'net_profit_min_usdt'
            ],
            'NET_PROFIT',
            (
                'beneficio neto '
                f"${net_profit:.2f} < "
                f"${thresholds['net_profit_min_usdt']:.2f}"
            )
        )

        require(
            roi_sl_abs
            <= thresholds[
                'loss_at_sl_max_pct_margin'
            ],
            'LOSS_AT_SL',
            (
                'pérdida estimada en SL '
                f"{roi_sl_abs:.1f}% > "
                f"{thresholds['loss_at_sl_max_pct_margin']:.1f}% "
                'del margen'
            )
        )

        require(
            0 < atr_stress_loss
            <= thresholds[
                'atr_stress_loss_max_pct_margin'
            ],
            'ATR_STRESS',
            (
                'estrés ATR '
                f"{atr_stress_loss:.1f}% > "
                f"{thresholds['atr_stress_loss_max_pct_margin']:.1f}% "
                'del margen'
            )
        )

        gate = {
            'eligible': not rejection_reasons,
            'tier': 'PREMIUM' if not rejection_reasons else 'ANALYSIS_ONLY',
            'reasons': rejection_reasons,
            'reason_codes':
                list(
                    rejection_reason_codes
                ),

            'stage':
                'PUBLICATION_GATE',

            'instrumentation_version':
                'futures_filter_trace_v1',
            'preferred_leverage_min': int(preferred_min),
            'preferred_leverage_max': int(preferred_max),
            'leverage_in_preferred_band': bool(in_preferred_band),
            'tp_touch_quality_score': round(tp_quality, 2),
            'sl_avoidance_quality_score': round(sl_avoidance_quality, 2),
            'probability_status': 'QUALITY_PROXY_NOT_CALIBRATED',
            'thresholds': thresholds,
        }

        result['futures_publication_gate'] = gate
        result['futures_signal_tier'] = gate['tier']
        result['publication_eligible'] = gate['eligible']
        result['leverage_preferred_min'] = int(preferred_min)
        result['leverage_preferred_max'] = int(preferred_max)
        result['leverage_in_preferred_band'] = bool(in_preferred_band)
        result['tp_touch_quality_score'] = round(tp_quality, 2)
        result['sl_avoidance_quality_score'] = round(
            sl_avoidance_quality,
            2
        )
        result[
            'probability_status'
        ] = 'QUALITY_PROXY_NOT_CALIBRATED'

        publication_reason = (
            'No cumple publicación premium: '
            + '; '.join(
                rejection_reasons
            )
            if rejection_reasons
            else ''
        )

        result = (
            self
            ._stamp_futures_filter_trace(
                result,
                stage='PUBLICATION_GATE',
                reason_codes=(
                    rejection_reason_codes
                ),
                reason=publication_reason,
                reached_publication_gate=True,
                outcome=(
                    'ANALYSIS_ONLY'
                    if rejection_reasons
                    else 'PREMIUM'
                )
            )
        )

        if rejection_reasons:
            return self._mark_levels_non_executable(
                result,
                publication_reason,
                recommended_leverage=leverage
            )

        result['is_rejected'] = False
        result['is_executable'] = True
        result['publication_status'] = 'EXECUTABLE_SIGNAL'
        return result
    
    def calculate_roi_futures(
        self,
        entry: float,
        tp: float,
        sl: float,
        leverage: int,
        direction: str
    ) -> Dict:
        """
        Calcula el ROI potencial de una operación de futuros.
    
        ROI positivo = ganancia potencial si toca TP.
        ROI negativo = pérdida potencial si toca SL.
    
        Además calcula una estimación monetaria basada en el
        margen de referencia configurado para Futuros.
    
        IMPORTANTE:
        - El ROI es sobre el margen.
        - Los importes USDT son estimaciones brutas.
        - Las comisiones/slippage se descuentan posteriormente
          en calculate_entry_levels().
        """
    
        # ==============================================================
        # VALIDACIÓN BÁSICA
        # ==============================================================
    
        if entry <= 0 or leverage <= 0:
            return {
                'roi_tp': 0,
                'roi_sl': 0,
                'move_tp_pct': 0,
                'move_sl_pct': 0,
                'profit_tp_usdt': 0,
                'loss_sl_usdt': 0
            }
    
        if tp <= 0 or sl <= 0:
            return {
                'roi_tp': 0,
                'roi_sl': 0,
                'move_tp_pct': 0,
                'move_sl_pct': 0,
                'profit_tp_usdt': 0,
                'loss_sl_usdt': 0
            }
    
        # ==============================================================
        # MOVIMIENTO DEL PRECIO
        # ==============================================================
    
        if direction == 'long':
    
            move_tp = (
                (tp - entry)
                / entry
                * 100
            )
    
            move_sl = (
                (entry - sl)
                / entry
                * 100
            )
    
        else:
    
            move_tp = (
                (entry - tp)
                / entry
                * 100
            )
    
            move_sl = (
                (sl - entry)
                / entry
                * 100
            )
    
        # ==============================================================
        # VALIDAR QUE TP Y SL ESTÉN DEL LADO CORRECTO
        # ==============================================================
    
        if move_tp < 0:
            move_tp = 0
    
        if move_sl < 0:
            move_sl = 0
    
        # ==============================================================
        # ROI SOBRE EL MARGEN
        # ==============================================================
    
        # ROI TP = movimiento × leverage
        roi_tp = (
            move_tp
            * leverage
        )
    
        # ROI SL siempre se muestra negativo
        roi_sl = (
            -move_sl
            * leverage
        )
    
        # ==============================================================
        # MARGEN DE REFERENCIA
        # ==============================================================
    
        # El sistema actualmente trabaja con una configuración
        # de margen por defecto para poder estimar el resultado
        # monetario.
        #
        # Más adelante Fase 5B:
        # utilizaremos el margen REAL de cada señal.
        try:
    
            margin_usdt = float(
                FUTURES_RISK_CONFIG.get(
                    'default_margin_usdt',
                    10.0
                )
            )
    
        except (
            TypeError,
            ValueError,
            AttributeError
        ):
    
            margin_usdt = 10.0
    
        if margin_usdt <= 0:
            margin_usdt = 10.0
    
        # ==============================================================
        # NOTIONAL
        # ==============================================================
    
        # Ejemplo:
        #
        # margen = 10 USDT
        # leverage = 8x
        #
        # notional = 80 USDT
        #
        notional_usdt = (
            margin_usdt
            * leverage
        )
    
        # ==============================================================
        # GANANCIA BRUTA EN TP
        # ==============================================================
    
        profit_tp_usdt = (
            notional_usdt
            * (move_tp / 100.0)
        )
    
        # ==============================================================
        # PÉRDIDA BRUTA EN SL
        # ==============================================================
    
        loss_sl_usdt = (
            notional_usdt
            * (move_sl / 100.0)
        )
    
        # ==============================================================
        # RESULTADO
        # ==============================================================
    
        return {
            'roi_tp': round(
                roi_tp,
                2
            ),
    
            'roi_sl': round(
                roi_sl,
                2
            ),
    
            'move_tp_pct': round(
                move_tp,
                2
            ),
    
            'move_sl_pct': round(
                move_sl,
                2
            ),
    
            # Ganancia bruta estimada si toca TP
            'profit_tp_usdt': round(
                profit_tp_usdt,
                4
            ),
    
            # Pérdida bruta estimada si toca SL
            'loss_sl_usdt': round(
                loss_sl_usdt,
                4
            ),
    
            # Información adicional útil para debug/UI
            'margin_usdt': round(
                margin_usdt,
                4
            ),
    
            'notional_usdt': round(
                notional_usdt,
                4
            )
        }
    
    # ========================================================================
    # OVERRIDE: CALCULATE_ENTRY_LEVELS (para futuros)
    # ========================================================================
    
    def calculate_entry_levels(self, decision, trend, momentum, volatility, structure, 
                                symbol, timeframe, liquidation=None):
        """
        Override específico para futuros.
        
        1. Traduce COMPRA_SPOT/VENTA_SPOT a LONG/SHORT (nunca operaciones spot en futuros).
        2. Llama al calculate_entry_levels padre para obtener niveles Smart Money.
        3. Recalcula el apalancamiento con la fórmula optimizada para futuros.
        4. Añade cálculos de ROI potencial.
        """
        # Traducción de acción (defensiva)
        original_action = decision
        if decision == 'COMPRA_SPOT':
            decision = 'LONG'
        elif decision == 'VENTA_SPOT':
            decision = 'SHORT'
        
        # Solo procesar acciones de futuros
        if decision not in ('LONG', 'SHORT'):
            return self._get_default_levels(structure.get('current_price', 0), symbol)
        
        # Llamar al método padre para obtener niveles base
        levels = super().calculate_entry_levels(
            decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation
        )
        
        # Si la señal fue rechazada por el padre, propagar
        # y conservar en qué etapa ocurrió.
        if levels.get('rejected_reason'):

            return (
                self
                ._stamp_futures_filter_trace(
                    levels,
                    stage='PRE_GATE',
                    reason_codes=[
                        'BASE_LEVELS_REJECTION'
                    ],
                    reason=levels.get(
                        'rejected_reason',
                        ''
                    ),
                    reached_publication_gate=False,
                    outcome='ANALYSIS_ONLY'
                )
            )

        
        # ==============================================================
        # FASE 5 — EXECUTION SAFETY
        # ==============================================================
        
        atr_pct = float(
            volatility.get(
                'atr_pct',
                1.0
            )
            or 1.0
        )
        
        review_multiplier = getattr(
            self,
            '_current_review_multiplier',
            1.0
        )
        
        entry_price = float(
            levels.get(
                'entry',
                0
            )
            or 0
        )
        
        sl_price = float(
            levels.get(
                'stop_loss',
                0
            )
            or 0
        )
        
        tp_price = float(
            levels.get(
                'take_profit',
                0
            )
            or 0
        )
        
        sl_distance_pct = None
        tp_distance_pct = None
        
        if (
            entry_price > 0
            and sl_price > 0
        ):
            sl_distance_pct = (
                abs(
                    entry_price
                    - sl_price
                )
                / entry_price
                * 100
            )
        
        if (
            entry_price > 0
            and tp_price > 0
        ):
            tp_distance_pct = (
                abs(
                    tp_price
                    - entry_price
                )
                / entry_price
                * 100
            )
        
        # ==============================================================
        # SEGURIDAD REAL DE EJECUCIÓN
        # ==============================================================
        execution_safety = (
            self._calculate_execution_safety(
                levels=levels,
                trend=trend or {},
                momentum=momentum or {},
                structure=structure or {},
                timeframe=timeframe
            )
        )
        
        safety_score = float(
            execution_safety.get(
                'score',
                0
            )
        )
        
        safety_label = execution_safety.get(
            'label',
            'RECHAZAR'
        )
        
        print(
            f"   🛡️ Execution Safety: "
            f"{safety_score:.1f}/100 "
            f"({safety_label})"
        )
        
        # ==============================================================
        # FASE 7E.3 — EXECUTION SAFETY OPERATIVO PROTEGIDO
        # ==============================================================
        #
        # La configuración estática sigue siendo la FUENTE BASE.
        #
        # ReviewTrader puede:
        #
        #     ✅ endurecer el filtro
        #     ✅ reducir Safety usado para leverage
        #
        # Nunca:
        #
        #     ❌ bajar el mínimo base
        #     ❌ aumentar Safety
        #     ❌ aumentar leverage
        #
        # Si ReviewTrader falla:
        #
        #     comportamiento original.
        # ==============================================================

        base_minimum_safety = float(
            FUTURES_RISK_CONFIG[
                'minimum_execution_safety'
            ]
        )

        minimum_safety = (
            base_minimum_safety
        )

        leverage_safety_score = (
            safety_score
        )

        execution_calibration = {
            'active':
                False,

            'mode':
                'STATIC_FALLBACK',

            'minimum_safety':
                base_minimum_safety,

            'raw_safety':
                safety_score,

            'leverage_safety_score':
                safety_score,

            'leverage_factor':
                1.0,

            'reason':
                'REVIEWTRADER_NO_DISPONIBLE'
        }

        try:

            # Import diferido para evitar dependencia circular.
            from review_trader import (
                review_trader
            )

            execution_calibration = (
                review_trader
                .get_execution_safety_operational_policy(
                    timeframe=timeframe,
                    safety_score=safety_score,
                    default_min_safety=(
                        base_minimum_safety
                    )
                )
            )

            if isinstance(
                execution_calibration,
                dict
            ):

                learned_minimum = float(
                    execution_calibration.get(
                        'minimum_safety',
                        base_minimum_safety
                    )
                    or base_minimum_safety
                )

                # ======================================================
                # GUARDRAIL FINAL EN FUTURES
                # ======================================================
                #
                # Aunque ReviewTrader tuviese un bug:
                #
                #     JAMÁS permitir bajar de la configuración base.
                # ======================================================

                minimum_safety = max(
                    base_minimum_safety,
                    learned_minimum
                )

                learned_leverage_safety = float(
                    execution_calibration.get(
                        'leverage_safety_score',
                        safety_score
                    )
                    or safety_score
                )

                # Nunca permitir una bonificación.
                leverage_safety_score = min(
                    safety_score,
                    learned_leverage_safety
                )

        except Exception as e:

            logger.debug(
                "7E.3 Execution Safety fallback: "
                f"{e}"
            )

            minimum_safety = (
                base_minimum_safety
            )

            leverage_safety_score = (
                safety_score
            )

        # ==============================================================
        # GUARDAR CONTEXTO DE CALIBRACIÓN
        # ==============================================================
        #
        # execution_safety sigue siendo el RAW original.
        #
        # Esto es MUY importante porque ReviewTrader debe seguir
        # aprendiendo sobre el score original y no sobre un score
        # ya modificado por sí mismo.
        # ==============================================================

        levels[
            'execution_safety'
        ] = round(
            safety_score,
            1
        )

        levels[
            'execution_safety_label'
        ] = (
            safety_label
        )

        levels[
            'execution_safety_operational_min'
        ] = round(
            minimum_safety,
            2
        )

        levels[
            'execution_safety_leverage_score'
        ] = round(
            leverage_safety_score,
            2
        )

        levels[
            'execution_safety_calibration_active'
        ] = bool(
            execution_calibration.get(
                'active',
                False
            )
        )

        levels[
            'execution_safety_calibration_mode'
        ] = str(
            execution_calibration.get(
                'mode',
                'STATIC_FALLBACK'
            )
        )

        if execution_calibration.get(
            'active',
            False
        ):

            print(
                "   🧠 7E.3 Safety protegido: "
                f"mínimo={minimum_safety:.1f} "
                f"| raw={safety_score:.1f} "
                f"| leverage_score="
                f"{leverage_safety_score:.1f} "
                f"| factor="
                f"{execution_calibration.get('leverage_factor', 1.0):.3f}"
            )

        if safety_score < minimum_safety:

            print(
                f"   ⚠️ FUTUROS ANALYSIS_ONLY: "
                f"Execution Safety "
                f"{safety_score:.1f} < "
                f"{minimum_safety:.1f}"
            )

            # ==========================================================
            # CONSERVAR NIVELES TÉCNICOS
            # ==========================================================
            # Entry / SL / TP / RR siguen siendo información válida
            # del análisis aunque la operación NO sea ejecutable.
            # ==========================================================

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            rejection_reason = (
                f"Execution Safety insuficiente "
                f"({safety_score:.1f}/100)"
            )

            traced_levels = (
                self
                ._stamp_futures_filter_trace(
                    levels,
                    stage='PRE_GATE',
                    reason_codes=[
                        'HARD_SAFETY'
                    ],
                    reason=rejection_reason,
                    reached_publication_gate=False,
                    outcome='ANALYSIS_ONLY'
                )
            )

            return self._mark_levels_non_executable(
                traced_levels,
                rejection_reason
            )
        
        # ==============================================================
        # LEVERAGE ECONÓMICO
        # ==============================================================
        leverage_evaluation = self._calculate_economic_leverage(
            margin_usdt=float(
                FUTURES_RISK_CONFIG['default_margin_usdt']
            ),
            tp_distance_pct=tp_distance_pct,
            sl_distance_pct=sl_distance_pct,
            atr_pct=atr_pct,
            execution_safety=leverage_safety_score,
            timeframe=timeframe,
        )

        optimal_leverage = int(
            leverage_evaluation.get('leverage', 0)
            if leverage_evaluation
            else 0
        )
        
        if optimal_leverage <= 0:

            print(
                "   ⚠️ FUTUROS ANALYSIS_ONLY: "
                "No existe leverage simultáneamente "
                "seguro y económicamente viable."
            )

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            rejection_reason = (
                "No existe leverage que cumpla "
                "seguridad + riesgo + rentabilidad"
            )

            traced_levels = (
                self
                ._stamp_futures_filter_trace(
                    levels,
                    stage='PRE_GATE',
                    reason_codes=[
                        'LEVERAGE_VIABILITY'
                    ],
                    reason=rejection_reason,
                    reached_publication_gate=False,
                    outcome='ANALYSIS_ONLY'
                )
            )

            return self._mark_levels_non_executable(
                traced_levels,
                rejection_reason
            )   
        # ============ CALCULAR ROI POTENCIAL ============
        direction = 'long' if decision == 'LONG' else 'short'
        
        roi = self.calculate_roi_futures(
            levels['entry'],
            levels['take_profit'],
            levels['stop_loss'],
            optimal_leverage,
            direction
        )
        
        levels.update(roi)
        levels['is_futures'] = True
        
        
        # ==============================================================
        # FASE 5 — VALIDACIÓN ECONÓMICA REAL
        # ==============================================================
        #
        # Ya no basta con:
        #
        #     ROI TP > 5%
        #
        # porque una operación puede mostrar ROI atractivo y,
        # después de comisiones, seguir siendo poco rentable.
        #
        # Ahora comprobamos:
        #
        #     1. ROI bruto suficiente
        #     2. coste estimado
        #     3. beneficio neto estimado
        #     4. pérdida estimada en USDT
        # ==============================================================
        
        min_roi_tp = float(
            FUTURES_RISK_CONFIG.get(
                'minimum_roi_tp_pct',
                8.0
            )
        )
        
        if roi['roi_tp'] < min_roi_tp:

            print(
                f"   ⚠️ FUTUROS ANALYSIS_ONLY: "
                f"ROI potencial "
                f"{roi['roi_tp']:.1f}% "
                f"< mínimo {min_roi_tp:.1f}%"
            )

            levels['leverage'] = int(
                optimal_leverage
            )

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            rejection_reason = (
                f"ROI potencial "
                f"{roi['roi_tp']:.1f}% "
                f"< {min_roi_tp:.1f}% mínimo"
            )

            traced_levels = (
                self
                ._stamp_futures_filter_trace(
                    levels,
                    stage='PRE_GATE',
                    reason_codes=[
                        'ROI_TP'
                    ],
                    reason=rejection_reason,
                    reached_publication_gate=False,
                    outcome='ANALYSIS_ONLY'
                )
            )

            return self._mark_levels_non_executable(
                traced_levels,
                rejection_reason,
                recommended_leverage=(
                    optimal_leverage
                )
            )
        
        
        # ==============================================================
        # COSTE ESTIMADO DE LA OPERACIÓN
        # ==============================================================
        round_trip_cost = float(
            FUTURES_RISK_CONFIG.get(
                'round_trip_cost_pct',
                0.0012
            )
        )
        
        margin_usdt = float(
            FUTURES_RISK_CONFIG.get(
                'default_margin_usdt',
                10.0
            )
        )
        
        notional = (
            margin_usdt
            * optimal_leverage
        )
        
        estimated_cost_usdt = (
            notional
            * round_trip_cost
        )
        
        
        # ==============================================================
        # BENEFICIO NETO ESTIMADO EN TP
        # ==============================================================
        profit_tp_usdt = float(
            roi.get(
                'profit_tp_usdt',
                0
            )
            or 0
        )
        
        net_profit_tp_usdt = (
            profit_tp_usdt
            - estimated_cost_usdt
        )
        
        levels['estimated_cost_usdt'] = round(
            estimated_cost_usdt,
            4
        )
        
        levels['net_profit_tp_usdt'] = round(
            net_profit_tp_usdt,
            4
        )
        
        
        # ==============================================================
        # PÉRDIDA ESTIMADA EN SL
        # ==============================================================
        loss_sl_usdt = abs(
            float(
                roi.get(
                    'loss_sl_usdt',
                    0
                )
                or 0
            )
        )
        
        levels['estimated_loss_sl_usdt'] = round(
            loss_sl_usdt,
            4
        )
        
        
        # ==============================================================
        # BENEFICIO NETO MÍNIMO
        # ==============================================================
        target_net_profit = float(
            FUTURES_RISK_CONFIG.get(
                'target_net_profit_usdt',
                0.50
            )
        )
        
        if (
            net_profit_tp_usdt
            < target_net_profit
        ):
            print(
                f"   ⚠️ FUTUROS ANALYSIS_ONLY: "
                f"beneficio neto estimado "
                f"${net_profit_tp_usdt:.4f} "
                f"< objetivo "
                f"${target_net_profit:.4f}"
            )

            levels['leverage'] = int(
                optimal_leverage
            )

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            rejection_reason = (
                f"Beneficio neto estimado "
                f"${net_profit_tp_usdt:.4f} "
                f"< objetivo "
                f"${target_net_profit:.4f}"
            )

            traced_levels = (
                self
                ._stamp_futures_filter_trace(
                    levels,
                    stage='PRE_GATE',
                    reason_codes=[
                        'NET_PROFIT'
                    ],
                    reason=rejection_reason,
                    reached_publication_gate=False,
                    outcome='ANALYSIS_ONLY'
                )
            )

            return self._mark_levels_non_executable(
                traced_levels,
                rejection_reason,
                recommended_leverage=(
                    optimal_leverage
                )
            )
        # ==============================================================
        # OPERACIÓN APROBADA
        # ==============================================================
        # Si llegamos hasta aquí:
        #
        #   ✅ ENTRY válido
        #   ✅ SL válido
        #   ✅ TP válido
        #   ✅ Execution Safety suficiente
        #   ✅ leverage económicamente viable
        #   ✅ ROI suficiente
        #   ✅ beneficio neto suficiente
        #
        # Debemos devolver los niveles calculados.
        # ==============================================================

        levels['leverage'] = int(
            optimal_leverage
        )

        levels['execution_safety'] = round(
            safety_score,
            1
        )

        levels['execution_safety_label'] = (
            safety_label
        )

        levels['risk_control'] = {
            'max_loss_pct_margin': float(
                FUTURES_RISK_CONFIG[
                    'max_loss_pct_margin'
                ]
            ),
            'leverage': int(
                optimal_leverage
            ),
            
            'leverage_min_tf': int(
                LEVERAGE_RANGES[
                    timeframe
                ][0]
            ),
            
            'leverage_max_tf': int(
                LEVERAGE_RANGES[
                    timeframe
                ][1]
            ),
            'leverage_preferred_min': int(
                PREFERRED_LEVERAGE_RANGES[timeframe][0]
            ),
            'leverage_preferred_max': int(
                PREFERRED_LEVERAGE_RANGES[timeframe][1]
            ),
            
            'leverage_policy': (
                'MINIMUM_SAFE_VIABLE '
                f"(1x-{LEVERAGE_RANGES[timeframe][1]}x)"
            ),
            'minimum_economic_leverage': leverage_evaluation.get(
                'min_economic'
            ),
            'minimum_roi_leverage': leverage_evaluation.get(
                'min_by_roi'
            ),
            'maximum_leverage_by_sl_risk': leverage_evaluation.get(
                'max_by_risk'
            ),
            'maximum_leverage_by_atr_stress': leverage_evaluation.get(
                'max_by_atr_stress'
            ),
            'maximum_leverage_by_execution_safety': (
                leverage_evaluation.get('max_by_security')
            ),
            'maximum_safe_leverage': leverage_evaluation.get(
                'max_safe'
            ),
            'atr_pct': leverage_evaluation.get('atr_pct'),
            'atr_stress_move_pct': leverage_evaluation.get(
                'atr_stress_move_pct'
            ),
            'estimated_atr_stress_loss_pct_margin': (
                leverage_evaluation.get(
                    'estimated_atr_stress_loss_pct_margin'
                )
            ),
            'margin_usdt': float(
                FUTURES_RISK_CONFIG[
                    'default_margin_usdt'
                ]
            ),
            'estimated_loss_sl_usdt': round(
                loss_sl_usdt,
                4
            ),
            'estimated_cost_usdt': round(
                estimated_cost_usdt,
                4
            ),
            'net_profit_tp_usdt': round(
                net_profit_tp_usdt,
                4
            )
        }
        # ==============================================================
        # VALIDACIÓN FINAL DEL LEVERAGE
        # ==============================================================
        if not _leverage_in_valid_range(
            int(optimal_leverage),
            timeframe
        ):
        
            min_tf, max_tf = LEVERAGE_RANGES.get(
                timeframe,
                (1, 10)
            )
        
            rejection_reason = (
                f"Leverage recomendado "
                f"{optimal_leverage}x "
                f"fuera del rango operativo "
                f"{min_tf}x-{max_tf}x "
                f"para {timeframe}"
            )

            traced_levels = (
                self
                ._stamp_futures_filter_trace(
                    levels,
                    stage='PRE_GATE',
                    reason_codes=[
                        'LEVERAGE_VIABILITY'
                    ],
                    reason=rejection_reason,
                    reached_publication_gate=False,
                    outcome='ANALYSIS_ONLY'
                )
            )

            return self._mark_levels_non_executable(
                traced_levels,
                rejection_reason,
                recommended_leverage=(
                    optimal_leverage
                )
            )

        # Sólo las oportunidades premium alimentan Activas/Vela anterior.
        # Las demás conservan decisión y niveles como análisis consultable.
        return self._apply_futures_publication_gate(
            levels,
            timeframe
        )
    # ========================================================================
    # ANÁLISIS COMPLETO DE FUTUROS
    # ========================================================================

    def _prepare_closed_candle_analysis_data(
        self,
        symbol: str,
        timeframe: str
    ) -> Dict:
        """
        Separa la información en dos mundos:

        - closed_df: velas completamente cerradas para generar el setup.
        - live_price: último precio OHLCV disponible para seguimiento.

        No asume ciegamente que KuCoin siempre incluye una vela abierta.
        Comprueba el tiempo de apertura de la última fila y la duración del TF.
        """
        try:
            full_df = self.get_kucoin_data(
                symbol,
                timeframe
            )

            if full_df is None or len(full_df) < 3:
                data_error = self._futures_data_errors.get(
                    (symbol, timeframe),
                    'No se recibieron velas reales del contrato perpetuo'
                )
                return {
                    'success': False,
                    'error': (
                        'Futuros detenido por seguridad: '
                        f'{data_error}'
                    ),
                    'market_data_source': KUCOIN_FUTURES_DATA_SOURCE,
                    'market_data_is_synthetic': False,
                }

            tf_seconds = FUTURES_TIMEFRAME_SECONDS.get(
                timeframe
            )

            if not tf_seconds:
                return {
                    'success': False,
                    'error': f'Temporalidad sin duración definida: {timeframe}'
                }

            parsed_times = pd.to_datetime(
                full_df['time'],
                utc=True,
                errors='coerce'
            )

            last_open = parsed_times.iloc[-1]

            if pd.isna(last_open):
                return {
                    'success': False,
                    'error': 'Timestamp inválido en la última vela'
                }

            now_utc = pd.Timestamp.now(tz='UTC')
            candle_duration = pd.Timedelta(seconds=tf_seconds)

            last_row_is_closed = (
                last_open + candle_duration
                <= now_utc
            )

            if last_row_is_closed:
                closed_df = full_df.copy()
                open_candle_present = False
            else:
                closed_df = full_df.iloc[:-1].copy()
                open_candle_present = True

            closed_df = closed_df.reset_index(drop=True)

            if len(closed_df) < 2:
                return {
                    'success': False,
                    'error': 'No existen suficientes velas cerradas'
                }

            source_open = pd.to_datetime(
                closed_df['time'].iloc[-1],
                utc=True,
                errors='coerce'
            )

            if pd.isna(source_open):
                return {
                    'success': False,
                    'error': 'Timestamp inválido en la vela fuente'
                }

            source_close = source_open + candle_duration

            return {
                'success': True,
                'closed_df': closed_df,
                'source_candle_timestamp': source_open.isoformat(),
                'source_candle_close_timestamp': source_close.isoformat(),
                'live_price': float(full_df['close'].iloc[-1]),
                'live_candle_timestamp': last_open.isoformat(),
                'open_candle_present': bool(open_candle_present),
                'market_data_source': full_df.attrs.get(
                    'market_data_source',
                    KUCOIN_FUTURES_DATA_SOURCE,
                ),
                'market_data_is_synthetic': False,
                'contract_symbol': full_df.attrs.get(
                    'contract_symbol',
                    FUTURES_CONTRACT_SYMBOLS.get(symbol),
                ),
                'market_data_fetched_at': full_df.attrs.get('fetched_at'),
                'market_data_candles': int(len(full_df)),
            }

        except Exception as e:
            logger.error(
                f'Error preparando vela cerrada {symbol} {timeframe}: {e}'
            )

            return {
                'success': False,
                'error': str(e)
            }
    
    def analyze_futures_market(self, symbol: str, timeframe: str, 
                                btc_analysis: Optional[Dict] = None,
                                closed_candle_only: bool = True) -> Dict:
        """
        Análisis completo para futuros.
        
        Wrapper de analyze_full_market del padre pero:
        - Valida símbolo y TF de futuros
        - Fuerza system_type='futures' al registrar en Supabase
        - Adapta la correlación (no usa PAXG)
        - Traduce COMPRA/VENTA a LONG/SHORT en la decisión final

        closed_candle_only=False conserva el comportamiento anterior.
        closed_candle_only=True excluye la vela abierta de todos los
        indicadores, traders, votación y niveles.
        """
        # Validar
        if symbol not in FUTURES_SYMBOLS:
            return {
                'success': False,
                'error': f'Símbolo {symbol} no permitido en futuros. Válidos: {list(FUTURES_SYMBOLS.keys())}',
                'symbol': symbol,
                'timeframe': timeframe
            }
        
        if timeframe not in FUTURES_TIMEFRAMES:
            return {
                'success': False,
                'error': f'Timeframe {timeframe} no permitido en futuros. Válidos: {list(FUTURES_TIMEFRAMES.keys())}',
                'symbol': symbol,
                'timeframe': timeframe
            }
        
        print(f"\n{'='*60}")
        print(f"🚀 FUTUROS: Analizando {symbol} {timeframe}")
        print(f"{'='*60}")

        # Preparación opcional y retrocompatible. app.py activará este modo
        # en un commit posterior; mientras tanto el comportamiento no cambia.
        df_override = None
        closed_context = None

        if closed_candle_only:
            closed_context = self._prepare_closed_candle_analysis_data(
                symbol,
                timeframe
            )

            if not closed_context.get('success'):
                return {
                    'success': False,
                    'error': closed_context.get(
                        'error',
                        'No se pudo preparar la vela cerrada'
                    ),
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'market_data_source': closed_context.get(
                        'market_data_source',
                        KUCOIN_FUTURES_DATA_SOURCE,
                    ),
                    'market_data_is_synthetic': False,
                }

            df_override = closed_context['closed_df']
        
        # Llamar al análisis del padre
        # NOTA: paxg_analysis y paxg_btc_analysis se pasan como None
        # (no aplica en futuros)
        # FLAG: evitar doble registro en Supabase (el padre registraría con
        # system_type='spot'. Aquí lo registramos después con 'futures').
        self._skip_supabase_register = True
        try:
            result = self.analyze_full_market(
                symbol=symbol,
                timeframe=timeframe,
                btc_analysis=btc_analysis,
                paxg_analysis=None,
                paxg_btc_analysis=None,
                df_override=df_override
            )
        finally:
            self._skip_supabase_register = False
        
        if not result or not result.get('success'):
            return result
        
        # ============ TRADUCIR ACCIÓN ============
        decision = result.get('decision', {})
        original_action = decision.get('action', 'NO_OPERAR')
        
        translated_action = original_action
        if original_action == 'COMPRA_SPOT':
            translated_action = 'LONG'
        elif original_action == 'VENTA_SPOT':
            translated_action = 'SHORT'
        
        decision['action'] = translated_action
        decision['original_action'] = original_action  # Guardar por si acaso
        result['decision'] = decision
        
        # ============ MARCAR COMO FUTUROS ============
        result['system_type'] = 'futures'
        result['is_futures'] = True
        result['market_data_source'] = KUCOIN_FUTURES_DATA_SOURCE
        result['market_data_is_synthetic'] = False
        result['contract_symbol'] = FUTURES_CONTRACT_SYMBOLS.get(symbol)

        # ============ IDENTIDAD DE LA VELA FUENTE ============
        # Solo se publica cuando el caller pidió explícitamente analizar
        # velas cerradas. ReviewTrader ya entiende este campo y mantiene
        # fallback para resultados antiguos.
        if closed_context:
            import hashlib

            source_ts = closed_context['source_candle_timestamp']
            signal_seed = (
                f"{symbol}|{timeframe}|{translated_action}|"
                f"{source_ts}|closed_v1"
            )

            result['signal_id'] = hashlib.sha256(
                signal_seed.encode('utf-8')
            ).hexdigest()[:24]
            result['analysis_mode'] = 'CLOSED_CANDLE'
            result['analysis_version'] = 'closed_v1'
            result['source_candle_timestamp'] = source_ts
            result['source_candle_close_timestamp'] = closed_context[
                'source_candle_close_timestamp'
            ]
            result['source_candle_closed'] = True
            result['analysis_price'] = float(
                result.get('current_price', 0) or 0
            )
            result['live_price'] = closed_context['live_price']
            result['live_candle_timestamp'] = closed_context[
                'live_candle_timestamp'
            ]
            result['open_candle_present'] = closed_context[
                'open_candle_present'
            ]
            result['market_data_source'] = closed_context[
                'market_data_source'
            ]
            result['market_data_fetched_at'] = closed_context[
                'market_data_fetched_at'
            ]
            result['market_data_candles'] = closed_context[
                'market_data_candles'
            ]

        # ============ CAPA CUANTITATIVA FUTURES (SHADOW) ============
        #
        # Se calcula DESPUÉS de la decisión para poder medir alineación y la
        # ubicación del Entry, pero no retroalimenta al comité ni reabre el
        # filtro de publicación. Sus resultados quedan listos para formar una
        # cohorte estadística separada en ReviewTrader.
        levels_for_quant = dict(result.get('levels') or {})
        if closed_context:
            quantitative_context = (
                self._analyze_quantitative_futures_context(
                    df=closed_context['closed_df'],
                    action=translated_action,
                    timeframe=timeframe,
                    entry_price=levels_for_quant.get('entry'),
                )
            )
        else:
            quantitative_context = {
                'available': False,
                'model_version': FUTURES_QUANT_MODEL_VERSION,
                'mode': 'SHADOW_OBSERVATION',
                'calibrated': False,
                'affects_publication': False,
                'data_scope': 'CLOSED_PERPETUAL_OHLCV_ONLY',
                'quality_score_status': (
                    'UNVALIDATED_PROXY_NOT_WIN_PROBABILITY'
                ),
                'status': 'REQUIRES_CLOSED_CANDLE_MODE',
                'shadow_verdict': 'UNAVAILABLE',
            }

        result['futures_quantitative_context'] = quantitative_context
        levels_for_quant['quantitative_model_version'] = (
            quantitative_context.get('model_version')
        )
        levels_for_quant['quantitative_regime'] = (
            quantitative_context.get('regime', 'UNAVAILABLE')
        )
        levels_for_quant['quantitative_direction_alignment'] = (
            quantitative_context.get(
                'direction_alignment',
                'NOT_APPLICABLE',
            )
        )
        levels_for_quant['quantitative_shadow_verdict'] = (
            quantitative_context.get('shadow_verdict', 'UNAVAILABLE')
        )
        levels_for_quant['quantitative_quality_score'] = float(
            quantitative_context.get('quality_score', 0.0) or 0.0
        )
        levels_for_quant['quantitative_affects_publication'] = False
        result['levels'] = levels_for_quant

        decision['quantitative_observation'] = {
            'regime': quantitative_context.get('regime', 'UNAVAILABLE'),
            'direction': quantitative_context.get('direction', 'NEUTRAL'),
            'alignment': quantitative_context.get(
                'direction_alignment',
                'NOT_APPLICABLE',
            ),
            'entry_location': quantitative_context.get(
                'entry_location',
                'UNAVAILABLE',
            ),
            'shadow_verdict': quantitative_context.get(
                'shadow_verdict',
                'UNAVAILABLE',
            ),
            'quality_score': float(
                quantitative_context.get('quality_score', 0.0) or 0.0
            ),
            'affects_publication': False,
        }
        result['decision'] = decision
        
        # ============ ADAPTAR JUSTIFICACIÓN AL CONTEXTO DE FUTUROS ============
        # El mensaje se generó con la acción original (COMPRA_SPOT / VENTA_SPOT)
        # usando las plantillas spot. Para futuros necesitamos:
        #   1. Reemplazar títulos: "COMPRA SPOT DE X" → "LONG FUTURES DE X"
        #   2. Reemplazar recomendaciones incorrectas de par-ratio (SOL/XRP/ADA/ETH
        #      caían en la rama "ratio PAXG/BTC" del selector spot)
        try:
            msg = result.get('message', '') or ''
            if msg:
                symbol_name_map = {
                    'BTC-USDT': 'BTC/USDT', 'ETH-USDT': 'ETH/USDT',
                    'SOL-USDT': 'SOL/USDT', 'XRP-USDT': 'XRP/USDT',
                    'ADA-USDT': 'ADA/USDT',
                }
                pretty_name = symbol_name_map.get(symbol, symbol.replace('-', '/'))
                
                if original_action == 'COMPRA_SPOT':
                    # Título
                    msg = msg.replace(
                        f'🟢 COMPRA SPOT DE {pretty_name}',
                        f'📈 LONG FUTURES DE {pretty_name}'
                    )
                    # Fallback si el símbolo no tenía nombre mapeado
                    msg = msg.replace(
                        '🟢 COMPRA SPOT DE',
                        '📈 LONG FUTURES DE'
                    )

                    # También normalizar mensajes fallback.
                    msg = msg.replace(
                        'Recomendación: COMPRA_SPOT',
                        'Recomendación: LONG'
                    )

                    msg = msg.replace(
                        'Recomendación: COMPRA SPOT',
                        'Recomendación: LONG'
                    )

                    # Recomendaciones incorrectas: eliminar todas las variantes spot
                    # y reemplazar por una recomendación futures apropiada
                    for wrong in (
                        'Se recomienda COMPRA del ratio PAXG/BTC.',
                        'Se recomienda COMPRA SPOT de BTC/USDT.',
                        'Se recomienda COMPRA SPOT de Bitcoin.',
                        'Se recomienda COMPRA SPOT de Bitcoin',
                        'Se aconseja COMPRA SPOT de PAXG.',
                    ):
                        msg = msg.replace(
                            wrong,
                            f'Se recomienda LONG en futuros de {pretty_name}.'
                        )
                elif original_action == 'VENTA_SPOT':
                    msg = msg.replace(
                        f'🔴 VENTA SPOT DE {pretty_name}',
                        f'📉 SHORT FUTURES DE {pretty_name}'
                    )
                    msg = msg.replace(
                        '🔴 VENTA SPOT DE',
                        '📉 SHORT FUTURES DE'
                    )

                    msg = msg.replace(
                        'Recomendación: VENTA_SPOT',
                        'Recomendación: SHORT'
                    )

                    msg = msg.replace(
                        'Recomendación: VENTA SPOT',
                        'Recomendación: SHORT'
                    )

                    for wrong in (
                        'Se aconseja VENTA del ratio PAXG/BTC.',
                        'Se recomienda VENTA SPOT de BTC/USDT.',
                        'Se recomienda VENTA SPOT de Bitcoin.',
                        'Se recomienda VENTA SPOT de Bitcoin',
                        'Se sugiere VENTA SPOT de PAXG.',
                    ):
                        msg = msg.replace(
                            wrong,
                            f'Se recomienda SHORT en futuros de {pretty_name}.'
                        )
                
                result['message'] = msg
        except Exception as _msg_err:
            logger.debug(f"No se pudo adaptar mensaje a futures: {_msg_err}")
        
        # ============ RECALCULAR NIVELES CON LÓGICA DE FUTUROS ============
        # (Ya se hizo dentro de analyze_full_market → calculate_entry_levels overrideado)
        # Pero verificamos que la traducción sea consistente
        levels = result.get('levels', {})
        
        # ============ REGISTRAR EN REVIEWTRADER (si está disponible) ============
        # IMPORTANTE: solo registrar si el análisis fue FRESCO (no vino del caché).
        # Antes se registraba SIEMPRE, causando 5-10 duplicados idénticos por
        # cada TF cada vez que el warm-up paralelo tocaba el mismo par.
        if result.get('_from_cache'):
            # Análisis servido desde caché → la señal ya fue registrada antes.
            pass
        else:
            try:
                from review_trader import review_trader
                if review_trader.db.enabled:
                    review_trader.register_signal(result, system_type='futures')
                    print(f"   📝 Señal registrada en ReviewTrader (futures)")
            except Exception as e:
                logger.debug(f"ReviewTrader no disponible: {e}")
        
        return result
    
    # ========================================================================
    # ANÁLISIS DE CORRELACIÓN PARA FUTUROS (BTC + alts, sin PAXG)
    # ========================================================================
    
    def analyze_futures_correlation(self, results: Dict) -> Dict:
        """
        Calcula la correlación entre BTC y las alts para futuros.
        Reemplaza la correlación BTC/PAXG del sistema principal.
        
        results: dict con las análisis por símbolo, ej:
            {'BTC-USDT': {...}, 'ETH-USDT': {...}, 'SOL-USDT': {...}, ...}
        """
        try:
            btc = results.get('BTC-USDT', {})
            btc_trend = btc.get('trend', {})
            btc_direction = btc_trend.get('direction', 'neutral')
            btc_adx = btc_trend.get('adx', 0)
            
            # Alts
            alts = ['ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT']
            alt_directions = {}
            for alt in alts:
                alt_data = results.get(alt, {})
                alt_trend = alt_data.get('trend', {})
                alt_directions[alt] = {
                    'direction': alt_trend.get('direction', 'neutral'),
                    'adx': alt_trend.get('adx', 0)
                }
            
            # Contar cuántas alts van en la misma dirección que BTC
            aligned_with_btc = 0
            opposed_to_btc = 0
            
            for alt, data in alt_directions.items():
                if data['direction'] == btc_direction and data['direction'] != 'neutral':
                    aligned_with_btc += 1
                elif data['direction'] != 'neutral' and data['direction'] != btc_direction:
                    opposed_to_btc += 1
            
            # Interpretación
            if btc_direction == 'bullish' and aligned_with_btc >= 3:
                rotation = 'BULLISH_MARKET'
                description = 'BTC alcista arrastra alts al alza'
            elif btc_direction == 'bearish' and aligned_with_btc >= 3:
                rotation = 'BEARISH_MARKET'
                description = 'BTC bajista arrastra alts a la baja'
            elif btc_direction == 'bullish' and opposed_to_btc >= 2:
                rotation = 'ALTS_DIVERGE'
                description = 'BTC alcista pero alts muestran debilidad'
            elif btc_direction == 'bearish' and opposed_to_btc >= 2:
                rotation = 'ALTS_STRONG'
                description = 'BTC bajista pero alts se mantienen fuertes'
            else:
                rotation = 'MIXED'
                description = 'Mercado sin dirección clara entre BTC y alts'
            
            return {
                'rotation_signal': rotation,
                'description': description,
                'btc_direction': btc_direction,
                'btc_adx': btc_adx,
                'aligned_with_btc': aligned_with_btc,
                'opposed_to_btc': opposed_to_btc,
                'alt_directions': alt_directions
            }
            
        except Exception as e:
            logger.error(f"Error en analyze_futures_correlation: {e}")
            return {
                'rotation_signal': 'NEUTRAL',
                'description': 'Error en cálculo',
                'btc_direction': 'neutral'
            }
    
    # ========================================================================
    # ANÁLISIS DE TODOS LOS PARES DE FUTUROS
    # ========================================================================
    
    def analyze_all_futures_pairs(self, timeframe: str) -> Dict:
        """
        Analiza los 5 pares de futuros en la temporalidad dada.
        Retorna todos los análisis + correlación.
        """
        results = {}
        
        # 1. Analizar BTC primero (base para correlación)
        print(f"\n🚀 FUTUROS: Analizando 5 pares en {timeframe}")
        btc_result = self.analyze_futures_market('BTC-USDT', timeframe)
        results['BTC-USDT'] = btc_result
        
        # 2. Analizar los demás pares con contexto de BTC
        for symbol in ['ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT']:
            try:
                results[symbol] = self.analyze_futures_market(
                    symbol, timeframe, 
                    btc_analysis=btc_result if btc_result.get('success') else None
                )
            except Exception as e:
                logger.error(f"Error analizando {symbol}: {e}")
                results[symbol] = {
                    'success': False,
                    'error': str(e),
                    'symbol': symbol,
                    'timeframe': timeframe
                }
        
        # 3. Calcular correlación intra-cripto
        correlation = self.analyze_futures_correlation(results)
        results['_correlation'] = correlation
        
        return results


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================

# Otras partes del sistema importan esta instancia:
# from futures_system import futures_system
futures_system = FuturesAnalysis()
print("✅ FUTURES SYSTEM inicializado y listo")
