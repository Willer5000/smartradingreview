"""
chart_renderer.py
==================
Genera imágenes PNG de análisis técnico usando matplotlib (10× más ligero
que kaleido/Chrome, ~30MB vs ~250MB). Reemplazo del sistema anterior con
plotly + kaleido que causaba OOM en Render Free.

Uso:
    from chart_renderer import render_main_chart, render_indicator_chart
    
    png_bytes = render_main_chart(symbol, timeframe, analysis)
    png_bytes = render_indicator_chart(df, indicator_name, analysis)

Genera:
- Gráfico principal: velas + EMAs + soportes/resistencias
- Gráficos individuales de indicadores: RSI, MACD, DMI, Bollinger, Volume,
  Stochastic, Williams, CCI, MFI, OBV, ATR
"""

import io
import logging
from typing import Optional, List
import numpy as np
import pandas as pd

logger = logging.getLogger('CHART_RENDERER')

# Configurar matplotlib para modo headless (sin display) - CRÍTICO en servidor
import matplotlib
matplotlib.use('Agg')  # Backend no interactivo
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

# Estilo dark para todos los gráficos
plt.style.use('dark_background')


# ============================================================================
# CONFIGURACIÓN DE COLORES (consistente con el resto del sistema)
# ============================================================================
COLORS = {
    # v22: alineados con el frontend (script.js paper_bgcolor='#0A0C10')
    'bg': '#0A0C10',
    'grid': 'rgba(255,255,255,0.1)',
    'green': '#00C076',
    'red': '#FF5B5B',
    'yellow': '#FFD700',
    'blue': '#3A8BFF',
    'purple': '#8A63D2',
    'orange': '#FF8C00',
    'pink': '#FF69B4',
    'white': '#FFFFFF',
    'gray': '#666666',
}


def _prepare_df(analysis: dict, min_candles: int = 30,
                 symbol: str = None, timeframe: str = None) -> Optional[pd.DataFrame]:
    """
    Extrae el DataFrame del análisis. Devuelve None si no hay datos suficientes.
    
    Prioridad:
      1. analysis['df'] (top-level, disponible en spot y análisis fresco)
      2. analysis['structure']['df'] (fallback)
      3. Fetch directo de KuCoin usando kucoin_cache (si symbol y timeframe se pasan)
         → Este fallback es CRÍTICO porque el caché de futures elimina 'df'
         para ahorrar memoria, entonces las funciones downstream (PDF anexo B,
         imagen Telegram) necesitan re-obtenerlo desde KuCoin.
    """
    df_dict = analysis.get('df') or (analysis.get('structure') or {}).get('df') or {}
    
    # Camino 1 y 2: df en el análisis
    if df_dict and isinstance(df_dict, dict):
        times = df_dict.get('time', [])
        if len(times) >= min_candles:
            try:
                df = pd.DataFrame({
                    'time': pd.to_datetime(times),
                    'open': [float(x) for x in df_dict.get('open', [])],
                    'high': [float(x) for x in df_dict.get('high', [])],
                    'low':  [float(x) for x in df_dict.get('low', [])],
                    'close': [float(x) for x in df_dict.get('close', [])],
                    'volume': [float(x) if x else 0 for x in df_dict.get('volume', [])],
                })
                # Tomar solo las últimas N velas para el gráfico
                df = df.tail(100).reset_index(drop=True)
                return df
            except Exception as e:
                logger.warning(f'Error construyendo df desde analysis: {e}')
    
    # Camino 3: fallback — fetch directo de KuCoin (soluciona anexo B vacío)
    if symbol and timeframe:
        try:
            from kucoin_cache import fetch_kucoin_candles
            df = fetch_kucoin_candles(symbol, timeframe, timeout=8)
            if df is not None and len(df) >= min_candles:
                df = df.tail(100).reset_index(drop=True)
                logger.info(f'_prepare_df: usó fallback KuCoin para {symbol} {timeframe}')
                return df
        except Exception as e:
            logger.warning(f'_prepare_df: fallback KuCoin falló: {e}')
    
    return None


def _fig_to_png_bytes(fig: Figure, dpi: int = 100) -> Optional[bytes]:
    """
    Convierte una figura matplotlib a bytes PNG.
    Libera la figura después para evitar leaks de memoria.
    """
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        data = buf.getvalue()
        buf.close()
        return data
    except Exception as e:
        logger.error(f'Error convirtiendo figura a PNG: {e}')
        return None
    finally:
        plt.close(fig)  # Liberar memoria SIEMPRE


# ============================================================================
# GRÁFICO PRINCIPAL: velas + EMAs + niveles clave
# ============================================================================
def render_main_chart(symbol: str, timeframe: str, analysis: dict,
                      width: int = 12, height: int = 8) -> Optional[bytes]:
    """
    Genera el gráfico principal del análisis:
    - Panel superior (70%): velas + EMA9/21/50/200 + soportes/resistencias
    - Panel inferior (30%): volumen
    """
    df = _prepare_df(analysis, min_candles=30, symbol=symbol, timeframe=timeframe)
    if df is None:
        logger.warning(f'render_main_chart: sin df para {symbol} {timeframe}')
        return None
    
    try:
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=(width, height),
            gridspec_kw={'height_ratios': [3, 1], 'hspace': 0.05},
            facecolor=COLORS['bg']
        )
        
        # ============ PANEL SUPERIOR: VELAS ============
        _draw_candles(ax1, df)
        
        # EMAs
        closes = df['close'].values
        for period, color in [(9, COLORS['blue']), (21, COLORS['yellow']),
                              (50, COLORS['orange']), (200, COLORS['pink'])]:
            if len(closes) >= period:
                ema = _calc_ema(closes, period)
                ax1.plot(df.index, ema, color=color, linewidth=1,
                         label=f'EMA {period}', alpha=0.9)
        
        # Soportes y resistencias
        structure = analysis.get('structure', {}) or {}
        for s in (structure.get('supports') or [])[:3]:
            if s and s > 0:
                ax1.axhline(y=s, color=COLORS['green'], linestyle='--',
                            linewidth=0.8, alpha=0.6)
                ax1.text(len(df) - 1, s, f' S {s:.2f}',
                         color=COLORS['green'], fontsize=8, va='center')
        for r in (structure.get('resistances') or [])[:3]:
            if r and r > 0:
                ax1.axhline(y=r, color=COLORS['red'], linestyle='--',
                            linewidth=0.8, alpha=0.6)
                ax1.text(len(df) - 1, r, f' R {r:.2f}',
                         color=COLORS['red'], fontsize=8, va='center')
        
        # Niveles de entry/SL/TP si están disponibles
        levels = analysis.get('levels', {}) or {}
        entry = levels.get('entry')
        sl = levels.get('stop_loss')
        tp = levels.get('take_profit')
        if entry and entry > 0:
            ax1.axhline(y=entry, color=COLORS['blue'], linestyle='-',
                        linewidth=1.5, alpha=0.8, label=f'Entry ${entry:.2f}')
        if sl and sl > 0:
            ax1.axhline(y=sl, color=COLORS['red'], linestyle='-',
                        linewidth=1.5, alpha=0.8, label=f'SL ${sl:.2f}')
        if tp and tp > 0:
            ax1.axhline(y=tp, color=COLORS['green'], linestyle='-',
                        linewidth=1.5, alpha=0.8, label=f'TP ${tp:.2f}')
        
        # Título
        decision = analysis.get('decision', {}) or {}
        action = decision.get('action', 'NO_OPERAR')
        conf = decision.get('confidence', 0)
        try:
            conf = max(0, min(100, float(conf)))
        except Exception:
            conf = 0
        
        title_color = COLORS['green'] if action in ('LONG', 'COMPRA_SPOT') else \
                      COLORS['red'] if action in ('SHORT', 'VENTA_SPOT') else \
                      COLORS['yellow']
        
        ax1.set_title(f'{symbol} · {timeframe} · {action} ({conf:.0f}%)',
                      color=title_color, fontsize=13, fontweight='bold', pad=10)
        ax1.set_ylabel('Precio (USD)', color='white', fontsize=10)
        ax1.legend(loc='upper left', fontsize=8, framealpha=0.7)
        ax1.grid(True, alpha=0.2, linestyle=':')
        ax1.tick_params(colors='white', labelsize=8)
        ax1.set_facecolor(COLORS['bg'])
        
        # ============ PANEL INFERIOR: VOLUMEN ============
        colors_vol = [COLORS['green'] if c >= o else COLORS['red']
                      for c, o in zip(df['close'], df['open'])]
        ax2.bar(df.index, df['volume'], color=colors_vol, alpha=0.7, width=0.8)
        ax2.set_ylabel('Volumen', color='white', fontsize=9)
        ax2.tick_params(colors='white', labelsize=8)
        ax2.grid(True, alpha=0.2, linestyle=':')
        ax2.set_facecolor(COLORS['bg'])
        # X-axis: mostrar solo cada N ticks
        n = len(df)
        step = max(1, n // 8)
        ax2.set_xticks(range(0, n, step))
        ax2.set_xticklabels([df['time'].iloc[i].strftime('%m-%d %H:%M')
                              for i in range(0, n, step)], rotation=30, ha='right')
        
        plt.tight_layout()
        return _fig_to_png_bytes(fig, dpi=90)
    except Exception as e:
        logger.error(f'render_main_chart error: {e}')
        try:
            plt.close('all')
        except Exception:
            pass
        return None


def _draw_candles(ax, df: pd.DataFrame):
    """Dibuja velas japonesas simplificadas."""
    for i, (idx, row) in enumerate(df.iterrows()):
        color = COLORS['green'] if row['close'] >= row['open'] else COLORS['red']
        # Mecha (línea vertical high-low)
        ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=0.6)
        # Cuerpo (rectángulo open-close)
        body_bottom = min(row['open'], row['close'])
        body_height = abs(row['close'] - row['open'])
        if body_height < 1e-9:
            body_height = row['high'] * 0.0001  # doji mínimo visible
        rect = Rectangle((i - 0.35, body_bottom), 0.7, body_height,
                          facecolor=color, edgecolor=color, alpha=0.9)
        ax.add_patch(rect)


# ============================================================================
# CÁLCULOS DE INDICADORES (vectorizados numpy — más rápidos que Python puro)
# ============================================================================
def _calc_ema(values, period):
    """EMA vectorizada con numpy."""
    values = np.asarray(values, dtype=float)
    alpha = 2.0 / (period + 1)
    ema = np.empty_like(values)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return ema


def _calc_rsi(values, period=14):
    """RSI vectorizado."""
    values = np.asarray(values, dtype=float)
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.zeros_like(values)
    avg_loss = np.zeros_like(values)
    if len(values) > period:
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])
        for i in range(period + 1, len(values)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period
    rs = np.divide(avg_gain, avg_loss, out=np.ones_like(avg_gain) * 50, where=avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    rsi[:period] = 50  # valores previos al warmup
    return rsi


def _calc_macd(values, fast=12, slow=26, signal=9):
    """MACD histograma."""
    ema_fast = _calc_ema(values, fast)
    ema_slow = _calc_ema(values, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _calc_bollinger(values, period=20, std_dev=2):
    """Bandas de Bollinger."""
    values = np.asarray(values, dtype=float)
    sma = np.array([np.mean(values[max(0, i - period + 1):i + 1])
                    for i in range(len(values))])
    std = np.array([np.std(values[max(0, i - period + 1):i + 1])
                    for i in range(len(values))])
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


# ============================================================================
# GRÁFICOS INDIVIDUALES DE INDICADORES
# ============================================================================
def render_indicator_chart(df: pd.DataFrame, indicator: str,
                            analysis: dict = None,
                            width: int = 10, height: int = 3) -> Optional[bytes]:
    """
    Genera un gráfico PNG de un indicador específico.
    
    Indicadores soportados:
      rsi, macd, bollinger, volume, dmi, ema, stochastic, williams
    """
    if df is None or len(df) < 20:
        return None
    
    try:
        fig, ax = plt.subplots(figsize=(width, height), facecolor=COLORS['bg'])
        ax.set_facecolor(COLORS['bg'])
        
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        times = df['time'].values
        n = len(df)
        
        indicator = (indicator or '').lower()
        title_map = {
            'rsi': 'RSI (14)', 'rsi_maverick': 'RSI Maverick',
            'macd': 'MACD (12/26/9)', 'bollinger': 'Bollinger Bands',
            'volume': 'Volumen', 'dmi': 'DMI / ADX', 'adx': 'ADX (14)',
            'ema': 'Precio + EMAs', 'stochastic': 'Estocástico',
            'williams': 'Williams %R', 'cci': 'CCI (20)',
            'mfi': 'Money Flow Index', 'obv': 'On Balance Volume',
            'atr': 'ATR (14)', 'supertrend': 'SuperTrend',
            'psar': 'Parabolic SAR', 'squeeze': 'Squeeze Momentum',
            'ftm': 'Fuerza Tendencia (FTM)', 'whale': 'Detección Ballenas',
            'ichimoku': 'Ichimoku Cloud', 'fvg': 'Fair Value Gaps',
        }
        title = title_map.get(indicator, indicator.upper())
        
        # ============ Renderizar según indicador ============
        if indicator == 'rsi':
            rsi = _calc_rsi(closes, 14)
            ax.plot(range(n), rsi, color=COLORS['purple'], linewidth=1.5)
            ax.axhline(y=70, color=COLORS['red'], linestyle='--', linewidth=0.8, alpha=0.6)
            ax.axhline(y=30, color=COLORS['green'], linestyle='--', linewidth=0.8, alpha=0.6)
            ax.axhline(y=50, color=COLORS['gray'], linestyle=':', linewidth=0.5, alpha=0.4)
            ax.fill_between(range(n), 70, rsi, where=(rsi > 70),
                             color=COLORS['red'], alpha=0.2)
            ax.fill_between(range(n), 30, rsi, where=(rsi < 30),
                             color=COLORS['green'], alpha=0.2)
            ax.set_ylim([0, 100])
        
        elif indicator == 'macd':
            macd_line, signal_line, histogram = _calc_macd(closes)
            colors_hist = [COLORS['green'] if h >= 0 else COLORS['red'] for h in histogram]
            ax.bar(range(n), histogram, color=colors_hist, alpha=0.5, width=0.8, label='Histograma')
            ax.plot(range(n), macd_line, color=COLORS['blue'], linewidth=1.2, label='MACD')
            ax.plot(range(n), signal_line, color=COLORS['yellow'], linewidth=1.2, label='Señal')
            ax.axhline(y=0, color=COLORS['white'], linewidth=0.5, alpha=0.5)
            ax.legend(loc='upper left', fontsize=8)
        
        elif indicator == 'bollinger':
            upper, sma, lower = _calc_bollinger(closes, 20, 2)
            ax.plot(range(n), closes, color=COLORS['white'], linewidth=1.2, label='Precio')
            ax.plot(range(n), upper, color=COLORS['red'], linewidth=0.8, linestyle='--', label='Upper')
            ax.plot(range(n), sma, color=COLORS['yellow'], linewidth=0.8, label='SMA 20')
            ax.plot(range(n), lower, color=COLORS['green'], linewidth=0.8, linestyle='--', label='Lower')
            ax.fill_between(range(n), lower, upper, color=COLORS['blue'], alpha=0.1)
            ax.legend(loc='upper left', fontsize=8)
        
        elif indicator == 'volume':
            volumes = df['volume'].values
            colors_vol = [COLORS['green'] if c >= o else COLORS['red']
                          for c, o in zip(closes, df['open'].values)]
            ax.bar(range(n), volumes, color=colors_vol, alpha=0.7, width=0.8)
            avg_vol = np.mean(volumes) if len(volumes) > 0 else 0
            ax.axhline(y=avg_vol, color=COLORS['yellow'], linestyle='--',
                       linewidth=0.8, alpha=0.6, label=f'Promedio {avg_vol:.0f}')
            ax.legend(loc='upper left', fontsize=8)
        
        elif indicator in ('dmi', 'adx'):
            # ADX / DMI (cálculo simplificado)
            high_diff = np.diff(highs, prepend=highs[0])
            low_diff = -np.diff(lows, prepend=lows[0])
            plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
            minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
            tr = np.maximum(highs - lows,
                             np.maximum(np.abs(highs - np.roll(closes, 1)),
                                        np.abs(lows - np.roll(closes, 1))))
            tr[0] = highs[0] - lows[0]
            atr = _calc_ema(tr, 14)
            plus_di = np.divide(_calc_ema(plus_dm, 14) * 100, atr,
                                 out=np.zeros_like(atr), where=atr != 0)
            minus_di = np.divide(_calc_ema(minus_dm, 14) * 100, atr,
                                  out=np.zeros_like(atr), where=atr != 0)
            dx = np.divide(np.abs(plus_di - minus_di) * 100, plus_di + minus_di,
                            out=np.zeros_like(plus_di), where=(plus_di + minus_di) != 0)
            adx = _calc_ema(dx, 14)
            ax.plot(range(n), plus_di, color=COLORS['green'], linewidth=1.2, label='+DI')
            ax.plot(range(n), minus_di, color=COLORS['red'], linewidth=1.2, label='-DI')
            ax.plot(range(n), adx, color=COLORS['yellow'], linewidth=1.5, label='ADX', linestyle='-.')
            ax.axhline(y=25, color=COLORS['gray'], linestyle=':', alpha=0.5)
            ax.legend(loc='upper left', fontsize=8)
        
        elif indicator == 'atr':
            # ATR
            tr = np.maximum(highs - lows,
                             np.maximum(np.abs(highs - np.roll(closes, 1)),
                                        np.abs(lows - np.roll(closes, 1))))
            tr[0] = highs[0] - lows[0]
            atr = _calc_ema(tr, 14)
            atr_pct = np.divide(atr * 100, closes, out=np.zeros_like(atr), where=closes != 0)
            ax.plot(range(n), atr_pct, color=COLORS['yellow'], linewidth=1.2, label='ATR %')
            ax.fill_between(range(n), 0, atr_pct, color=COLORS['yellow'], alpha=0.2)
            ax.legend(loc='upper left', fontsize=8)
        
        elif indicator in ('stochastic', 'williams'):
            # Estocástico / Williams
            period = 14
            k_line = np.zeros(n)
            for i in range(period, n):
                highest = np.max(highs[i - period + 1:i + 1])
                lowest = np.min(lows[i - period + 1:i + 1])
                if highest != lowest:
                    if indicator == 'stochastic':
                        k_line[i] = 100 * (closes[i] - lowest) / (highest - lowest)
                    else:  # williams
                        k_line[i] = -100 * (highest - closes[i]) / (highest - lowest)
                else:
                    k_line[i] = 50 if indicator == 'stochastic' else -50
            
            if indicator == 'stochastic':
                d_line = np.convolve(k_line, np.ones(3) / 3, mode='same')
                ax.plot(range(n), k_line, color=COLORS['blue'], linewidth=1.2, label='%K')
                ax.plot(range(n), d_line, color=COLORS['red'], linewidth=1.2, label='%D', linestyle='--')
                ax.axhline(y=80, color=COLORS['red'], linestyle=':', alpha=0.5)
                ax.axhline(y=20, color=COLORS['green'], linestyle=':', alpha=0.5)
                ax.set_ylim([0, 100])
            else:  # williams
                ax.plot(range(n), k_line, color=COLORS['purple'], linewidth=1.5, label='Williams %R')
                ax.axhline(y=-20, color=COLORS['red'], linestyle=':', alpha=0.5)
                ax.axhline(y=-80, color=COLORS['green'], linestyle=':', alpha=0.5)
                ax.set_ylim([-100, 0])
            ax.legend(loc='upper left', fontsize=8)
        
        elif indicator == 'obv':
            # On Balance Volume
            volumes = df['volume'].values
            obv = np.zeros(n)
            obv[0] = volumes[0]
            for i in range(1, n):
                if closes[i] > closes[i - 1]:
                    obv[i] = obv[i - 1] + volumes[i]
                elif closes[i] < closes[i - 1]:
                    obv[i] = obv[i - 1] - volumes[i]
                else:
                    obv[i] = obv[i - 1]
            ax.plot(range(n), obv, color=COLORS['blue'], linewidth=1.5)
            ax.fill_between(range(n), np.min(obv), obv, color=COLORS['blue'], alpha=0.15)
        
        else:
            # Fallback: precio + EMA 21 (para indicadores no soportados o desconocidos)
            ax.plot(range(n), closes, color=COLORS['white'], linewidth=1.2, label='Precio')
            if n >= 21:
                ema21 = _calc_ema(closes, 21)
                ax.plot(range(n), ema21, color=COLORS['yellow'], linewidth=1, label='EMA 21')
            ax.legend(loc='upper left', fontsize=8)
        
        # Formato común
        ax.set_title(title, color='white', fontsize=11, fontweight='bold', pad=8)
        ax.tick_params(colors='white', labelsize=8)
        ax.grid(True, alpha=0.15, linestyle=':')
        # X ticks: solo cada N para no saturar
        step = max(1, n // 6)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([pd.Timestamp(times[i]).strftime('%m-%d %H:%M')
                              for i in range(0, n, step)], rotation=25, ha='right', fontsize=7)
        
        plt.tight_layout()
        return _fig_to_png_bytes(fig, dpi=90)
    except Exception as e:
        logger.error(f'render_indicator_chart error ({indicator}): {e}')
        try:
            plt.close('all')
        except Exception:
            pass
        return None


def _safe_chart_number(value):
    """Convierte un valor de análisis a float finito para uso gráfico."""
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _format_chart_price(value):
    """Formato de precio adaptativo para BTC, altcoins y ratios como PAXG-BTC."""
    value = _safe_chart_number(value)
    if value is None:
        return '--'
    absolute = abs(value)
    if absolute >= 1000:
        return f'{value:,.2f}'
    if absolute >= 1:
        return f'{value:.4f}'
    if absolute >= 0.01:
        return f'{value:.5f}'
    return f'{value:.8f}'


def _calc_visual_atr(highs, lows, closes, period=14):
    """ATR sólo para visualización; no participa en decisiones del sistema."""
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum(
        highs - lows,
        np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close))
    )
    return _calc_ema(tr, period)


def _calc_visual_supertrend(highs, lows, closes, period=10, multiplier=3.0):
    """SuperTrend reproducible para el panel visual de Telegram."""
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    atr = _calc_visual_atr(highs, lows, closes, period)
    hl2 = (highs + lows) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr
    upper = upper_basic.copy()
    lower = lower_basic.copy()
    trend = np.ones(n, dtype=int)
    supertrend = np.zeros(n, dtype=float)

    for i in range(1, n):
        if upper_basic[i] < upper[i - 1] or closes[i - 1] > upper[i - 1]:
            upper[i] = upper_basic[i]
        else:
            upper[i] = upper[i - 1]

        if lower_basic[i] > lower[i - 1] or closes[i - 1] < lower[i - 1]:
            lower[i] = lower_basic[i]
        else:
            lower[i] = lower[i - 1]

        if trend[i - 1] > 0:
            trend[i] = -1 if closes[i] < lower[i] else 1
        else:
            trend[i] = 1 if closes[i] > upper[i] else -1

        supertrend[i] = lower[i] if trend[i] > 0 else upper[i]

    supertrend[0] = lower[0]
    return supertrend, trend


def _calc_visual_psar(highs, lows, step=0.02, max_step=0.2):
    """Parabolic SAR ligero para visualización."""
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    n = len(highs)
    psar = np.zeros(n, dtype=float)
    if n == 0:
        return psar

    bull = True
    af = step
    ep = highs[0]
    psar[0] = lows[0]

    for i in range(1, n):
        prev = psar[i - 1]
        current = prev + af * (ep - prev)

        if bull:
            if i >= 2:
                current = min(current, lows[i - 1], lows[i - 2])
            else:
                current = min(current, lows[i - 1])

            if lows[i] < current:
                bull = False
                current = ep
                ep = lows[i]
                af = step
            elif highs[i] > ep:
                ep = highs[i]
                af = min(max_step, af + step)
        else:
            if i >= 2:
                current = max(current, highs[i - 1], highs[i - 2])
            else:
                current = max(current, highs[i - 1])

            if highs[i] > current:
                bull = True
                current = ep
                ep = highs[i]
                af = step
            elif lows[i] < ep:
                ep = lows[i]
                af = min(max_step, af + step)

        psar[i] = current

    return psar


def render_telegram_signal_chart(symbol: str, timeframe: str,
                                   analysis: dict,
                                   indicators: List[str] = None,
                                   width: int = 14, height: int = 14) -> Optional[bytes]:
    """
    Genera UNA imagen operativa para Telegram:
      - Panel principal grande con velas, niveles y zonas de riesgo/objetivo.
      - Hasta 4 paneles con las evidencias técnicas seleccionadas para ESA señal.

    Este renderer sólo visualiza. No modifica decisiones, niveles ni aprendizaje.
    """
    df = _prepare_df(analysis, min_candles=30, symbol=symbol, timeframe=timeframe)
    if df is None:
        logger.warning(f'render_telegram_signal_chart: sin df para {symbol} {timeframe}')
        return None

    # Evitar duplicados conservando el orden de importancia recibido desde app.py.
    indicators = list(dict.fromkeys((indicators or [])))[:4]
    n_indicators = len(indicators)

    try:
        n_rows = 1 + n_indicators
        height_ratios = [3.6] + [1.05] * n_indicators
        fig = plt.figure(figsize=(width, height), facecolor=COLORS['bg'])
        gs = fig.add_gridspec(
            n_rows, 1,
            height_ratios=height_ratios,
            hspace=0.32
        )

        # ================================================================
        # PANEL PRINCIPAL
        # ================================================================
        ax_main = fig.add_subplot(gs[0])
        ax_main.set_facecolor(COLORS['bg'])
        _draw_candles(ax_main, df)

        closes = df['close'].values
        for period, color in [
            (9, COLORS['blue']),
            (21, COLORS['yellow']),
            (50, COLORS['orange']),
            (200, COLORS['pink'])
        ]:
            if len(closes) >= period:
                ema = _calc_ema(closes, period)
                ax_main.plot(
                    df.index, ema,
                    color=color,
                    linewidth=0.9,
                    label=f'EMA {period}',
                    alpha=0.78
                )

        # Soportes/resistencias discretos para contexto, sin competir con Entry/SL/TP.
        structure = analysis.get('structure', {}) or {}
        for support in (structure.get('supports') or [])[:2]:
            support = _safe_chart_number(support)
            if support and support > 0:
                ax_main.axhline(
                    support,
                    color=COLORS['green'],
                    linestyle=':',
                    linewidth=0.7,
                    alpha=0.35
                )
        for resistance in (structure.get('resistances') or [])[:2]:
            resistance = _safe_chart_number(resistance)
            if resistance and resistance > 0:
                ax_main.axhline(
                    resistance,
                    color=COLORS['red'],
                    linestyle=':',
                    linewidth=0.7,
                    alpha=0.35
                )

        # ================================================================
        # ENTRY / SL / TP — prominentes y legibles en móvil
        # ================================================================
        levels = analysis.get('levels', {}) or {}
        entry = _safe_chart_number(levels.get('entry'))
        sl = _safe_chart_number(levels.get('stop_loss'))
        tp = _safe_chart_number(levels.get('take_profit'))

        if entry and tp:
            ax_main.axhspan(
                min(entry, tp), max(entry, tp),
                color=COLORS['green'], alpha=0.045, zorder=0
            )
        if entry and sl:
            ax_main.axhspan(
                min(entry, sl), max(entry, sl),
                color=COLORS['red'], alpha=0.045, zorder=0
            )

        def draw_trade_level(value, label, color, linewidth=2.2):
            if not value or value <= 0:
                return
            ax_main.axhline(
                y=value,
                color=color,
                linestyle='-',
                linewidth=linewidth,
                alpha=0.96,
                zorder=6
            )
            ax_main.text(
                0.995,
                value,
                f' {label}  {_format_chart_price(value)} ',
                transform=ax_main.get_yaxis_transform(),
                ha='right',
                va='center',
                fontsize=9,
                fontweight='bold',
                color='white',
                bbox={
                    'boxstyle': 'round,pad=0.25',
                    'facecolor': color,
                    'edgecolor': color,
                    'alpha': 0.88,
                },
                zorder=8
            )

        draw_trade_level(tp, 'TP', COLORS['green'])
        draw_trade_level(entry, 'ENTRY', COLORS['blue'], linewidth=2.6)
        draw_trade_level(sl, 'SL', COLORS['red'])

        # ================================================================
        # TÍTULO Y RESUMEN OPERATIVO
        # ================================================================
        decision = analysis.get('decision', {}) or {}
        action = str(decision.get('action', '?')).upper()
        try:
            conf = max(0, min(100, float(decision.get('confidence', 0))))
        except Exception:
            conf = 0

        color_action = (
            COLORS['green'] if action in ('LONG', 'COMPRA_SPOT')
            else COLORS['red'] if action in ('SHORT', 'VENTA_SPOT')
            else COLORS['yellow']
        )

        title = f'{symbol} · {timeframe} · {action} · confianza {conf:.0f}%'
        ax_main.set_title(
            title,
            color=color_action,
            fontsize=14,
            fontweight='bold',
            pad=10
        )
        ax_main.set_ylabel('Precio', color='white', fontsize=9)
        ax_main.grid(True, alpha=0.13, linestyle=':')
        ax_main.tick_params(colors='white', labelsize=8)
        ax_main.set_xticks([])

        # Leyenda sólo para EMAs; Entry/SL/TP ya tienen etiquetas propias.
        handles, labels = ax_main.get_legend_handles_labels()
        if handles:
            ax_main.legend(
                handles, labels,
                loc='upper left',
                fontsize=7,
                framealpha=0.55,
                ncol=4
            )

        # ================================================================
        # PANELES DE LAS EVIDENCIAS REALES
        # ================================================================
        for idx, indicator in enumerate(indicators):
            ax = fig.add_subplot(gs[idx + 1])
            ax.set_facecolor(COLORS['bg'])
            _render_indicator_into_ax(
                ax,
                df,
                indicator,
                idx == n_indicators - 1,
                analysis=analysis,
                evidence_number=idx + 1,
                evidence_total=n_indicators
            )

        fig.suptitle(
            'Evidencia técnica de la señal',
            color=COLORS['gray'],
            fontsize=9,
            y=0.995
        )
        fig.subplots_adjust(top=0.965, bottom=0.055, left=0.07, right=0.985)
        return _fig_to_png_bytes(fig, dpi=100)

    except Exception as e:
        logger.error(f'render_telegram_signal_chart error: {e}')
        try:
            plt.close('all')
        except Exception:
            pass
        return None


def _render_indicator_into_ax(
    ax,
    df: pd.DataFrame,
    indicator: str,
    is_last: bool,
    analysis: dict = None,
    evidence_number: int = None,
    evidence_total: int = None
):
    """
    Dibuja una evidencia técnica dentro de la imagen combinada de Telegram.

    Para evidencias estructurales que no son una serie clásica (FVG, OB, sweeps,
    ballenas, volume profile), se dibuja una representación OHLCV explícitamente
    etiquetada como visual/proxy cuando corresponde. Nunca se presentan datos
    estimados como order flow observado.
    """
    analysis = analysis or {}
    indicator = (indicator or '').lower().strip()
    closes = df['close'].values.astype(float)
    highs = df['high'].values.astype(float)
    lows = df['low'].values.astype(float)
    opens = df['open'].values.astype(float)
    volumes = df['volume'].values.astype(float)
    n = len(df)
    x = np.arange(n)
    uses_time_axis = True

    title_map = {
        'rsi': 'RSI (14)',
        'rsi_maverick': 'RSI Maverick',
        'macd': 'MACD',
        'bollinger': 'Bollinger',
        'volume': 'Volumen',
        'dmi': 'DMI / ADX',
        'adx': 'ADX',
        'stochastic': 'Estocástico',
        'williams': 'Williams %R',
        'atr': 'ATR %',
        'obv': 'OBV',
        'cci': 'CCI',
        'mfi': 'MFI',
        'force': 'Force Index',
        'supertrend': 'SuperTrend',
        'psar': 'Parabolic SAR',
        'ichimoku': 'Ichimoku',
        'squeeze': 'Squeeze',
        'ftm': 'Fuerza de Tendencia',
        'whale': 'Ballenas · proxy volumen',
        'fvg': 'Fair Value Gap',
        'order_blocks': 'Order Blocks · vista estructural',
        'sweeps': 'Liquidity Sweep',
        'stop_hunts': 'Stop Hunt / barrido',
        'volume_profile': 'Volume Profile · aprox. OHLCV',
    }

    prefix = ''
    if evidence_number and evidence_total:
        prefix = f'{evidence_number}/{evidence_total} · '

    ax.set_title(
        prefix + title_map.get(indicator, indicator.upper()),
        color='white',
        fontsize=9,
        fontweight='bold',
        pad=5,
        loc='left'
    )
    ax.tick_params(colors='white', labelsize=7)
    ax.grid(True, alpha=0.13, linestyle=':')

    try:
        if indicator == 'rsi':
            rsi = _calc_rsi(closes, 14)
            ax.plot(x, rsi, color=COLORS['purple'], linewidth=1.1)
            ax.axhline(70, color=COLORS['red'], linestyle='--', linewidth=0.6, alpha=0.5)
            ax.axhline(30, color=COLORS['green'], linestyle='--', linewidth=0.6, alpha=0.5)
            ax.axhline(50, color=COLORS['gray'], linestyle=':', linewidth=0.5, alpha=0.4)
            ax.set_ylim(0, 100)

        elif indicator == 'rsi_maverick':
            rsi3 = _calc_rsi(closes, 3)
            fast = _calc_ema(rsi3, 5)
            slow = _calc_ema(rsi3, 14)
            ax.plot(x, rsi3, color=COLORS['white'], linewidth=0.8, alpha=0.75, label='RSI 3')
            ax.plot(x, fast, color=COLORS['blue'], linewidth=1.1, label='EMA 5')
            ax.plot(x, slow, color=COLORS['yellow'], linewidth=1.1, label='EMA 14')
            ax.axhline(80, color=COLORS['red'], linestyle='--', linewidth=0.6, alpha=0.45)
            ax.axhline(20, color=COLORS['green'], linestyle='--', linewidth=0.6, alpha=0.45)
            ax.axhline(50, color=COLORS['gray'], linestyle=':', linewidth=0.5, alpha=0.4)
            ax.set_ylim(0, 100)
            ax.legend(loc='upper left', fontsize=6, ncol=3, framealpha=0.35)

        elif indicator == 'macd':
            macd_line, signal_line, hist = _calc_macd(closes)
            colors_hist = [COLORS['green'] if h >= 0 else COLORS['red'] for h in hist]
            ax.bar(x, hist, color=colors_hist, alpha=0.5, width=0.8)
            ax.plot(x, macd_line, color=COLORS['blue'], linewidth=0.9, label='MACD')
            ax.plot(x, signal_line, color=COLORS['yellow'], linewidth=0.9, label='Señal')
            ax.axhline(0, color=COLORS['white'], linewidth=0.4, alpha=0.5)
            ax.legend(loc='upper left', fontsize=6, framealpha=0.35)

        elif indicator == 'bollinger':
            upper, sma, lower = _calc_bollinger(closes, 20, 2)
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.8)
            ax.plot(x, upper, color=COLORS['red'], linewidth=0.7, linestyle='--')
            ax.plot(x, sma, color=COLORS['yellow'], linewidth=0.7)
            ax.plot(x, lower, color=COLORS['green'], linewidth=0.7, linestyle='--')
            ax.fill_between(x, lower, upper, color=COLORS['blue'], alpha=0.07)

        elif indicator == 'volume':
            colors_vol = [COLORS['green'] if c >= o else COLORS['red'] for c, o in zip(closes, opens)]
            ax.bar(x, volumes, color=colors_vol, alpha=0.7, width=0.8)
            if len(volumes) >= 20:
                avg = pd.Series(volumes).rolling(20, min_periods=1).median().values
                ax.plot(x, avg, color=COLORS['yellow'], linewidth=0.8, label='Mediana 20')
                ax.legend(loc='upper left', fontsize=6, framealpha=0.35)

        elif indicator in ('dmi', 'adx'):
            high_diff = np.diff(highs, prepend=highs[0])
            low_diff = -np.diff(lows, prepend=lows[0])
            plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
            minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
            atr = _calc_visual_atr(highs, lows, closes, 14)
            plus_di = np.divide(_calc_ema(plus_dm, 14) * 100, atr, out=np.zeros_like(atr), where=atr != 0)
            minus_di = np.divide(_calc_ema(minus_dm, 14) * 100, atr, out=np.zeros_like(atr), where=atr != 0)
            dx = np.divide(
                np.abs(plus_di - minus_di) * 100,
                plus_di + minus_di,
                out=np.zeros_like(plus_di),
                where=(plus_di + minus_di) != 0
            )
            adx = _calc_ema(dx, 14)
            if indicator == 'dmi':
                ax.plot(x, plus_di, color=COLORS['green'], linewidth=0.9, label='+DI')
                ax.plot(x, minus_di, color=COLORS['red'], linewidth=0.9, label='-DI')
            ax.plot(x, adx, color=COLORS['yellow'], linewidth=1.1, label='ADX')
            ax.axhline(25, color=COLORS['gray'], linestyle=':', alpha=0.4)
            ax.legend(loc='upper left', fontsize=6, ncol=3, framealpha=0.35)

        elif indicator == 'atr':
            atr = _calc_visual_atr(highs, lows, closes, 14)
            atr_pct = np.divide(atr * 100, closes, out=np.zeros_like(atr), where=closes != 0)
            ax.plot(x, atr_pct, color=COLORS['yellow'], linewidth=1.0)
            ax.fill_between(x, 0, atr_pct, color=COLORS['yellow'], alpha=0.12)

        elif indicator in ('stochastic', 'williams'):
            period = 14
            values = np.full(n, np.nan)
            for i in range(period - 1, n):
                highest = np.max(highs[i - period + 1:i + 1])
                lowest = np.min(lows[i - period + 1:i + 1])
                if highest != lowest:
                    if indicator == 'stochastic':
                        values[i] = 100 * (closes[i] - lowest) / (highest - lowest)
                    else:
                        values[i] = -100 * (highest - closes[i]) / (highest - lowest)
            if indicator == 'stochastic':
                filled = pd.Series(values).interpolate(limit_direction='both').fillna(50).values
                d_line = pd.Series(filled).rolling(3, min_periods=1).mean().values
                ax.plot(x, values, color=COLORS['blue'], linewidth=1.0, label='%K')
                ax.plot(x, d_line, color=COLORS['yellow'], linewidth=0.9, label='%D')
                ax.axhline(80, color=COLORS['red'], linestyle=':', alpha=0.45)
                ax.axhline(20, color=COLORS['green'], linestyle=':', alpha=0.45)
                ax.set_ylim(0, 100)
                ax.legend(loc='upper left', fontsize=6, framealpha=0.35)
            else:
                ax.plot(x, values, color=COLORS['purple'], linewidth=1.0)
                ax.axhline(-20, color=COLORS['red'], linestyle=':', alpha=0.45)
                ax.axhline(-80, color=COLORS['green'], linestyle=':', alpha=0.45)
                ax.set_ylim(-100, 0)

        elif indicator == 'obv':
            obv = np.zeros(n)
            if n:
                obv[0] = volumes[0]
            for i in range(1, n):
                direction = 1 if closes[i] > closes[i - 1] else -1 if closes[i] < closes[i - 1] else 0
                obv[i] = obv[i - 1] + direction * volumes[i]
            ax.plot(x, obv, color=COLORS['blue'], linewidth=1.0)
            ax.fill_between(x, np.nanmin(obv), obv, color=COLORS['blue'], alpha=0.1)

        elif indicator == 'cci':
            typical = (highs + lows + closes) / 3.0
            tp_series = pd.Series(typical)
            sma = tp_series.rolling(20, min_periods=20).mean()
            mad = tp_series.rolling(20, min_periods=20).apply(
                lambda values: np.mean(np.abs(values - np.mean(values))), raw=True
            )
            cci = ((tp_series - sma) / (0.015 * mad.replace(0, np.nan))).values
            ax.plot(x, cci, color=COLORS['purple'], linewidth=1.0)
            ax.axhline(100, color=COLORS['red'], linestyle=':', alpha=0.45)
            ax.axhline(-100, color=COLORS['green'], linestyle=':', alpha=0.45)
            ax.axhline(0, color=COLORS['gray'], linewidth=0.5, alpha=0.4)

        elif indicator == 'mfi':
            typical = (highs + lows + closes) / 3.0
            raw_flow = typical * volumes
            positive = np.where(np.diff(typical, prepend=typical[0]) > 0, raw_flow, 0.0)
            negative = np.where(np.diff(typical, prepend=typical[0]) < 0, raw_flow, 0.0)
            pos_sum = pd.Series(positive).rolling(14, min_periods=1).sum().values
            neg_sum = pd.Series(negative).rolling(14, min_periods=1).sum().values
            ratio = np.divide(pos_sum, neg_sum, out=np.full(n, 1.0), where=neg_sum != 0)
            mfi = 100 - (100 / (1 + ratio))
            ax.plot(x, mfi, color=COLORS['blue'], linewidth=1.0)
            ax.axhline(80, color=COLORS['red'], linestyle=':', alpha=0.45)
            ax.axhline(20, color=COLORS['green'], linestyle=':', alpha=0.45)
            ax.set_ylim(0, 100)

        elif indicator == 'force':
            force = np.diff(closes, prepend=closes[0]) * volumes
            smooth = _calc_ema(force, 13)
            ax.bar(x, force, color=[COLORS['green'] if v >= 0 else COLORS['red'] for v in force], alpha=0.3, width=0.8)
            ax.plot(x, smooth, color=COLORS['yellow'], linewidth=1.0)
            ax.axhline(0, color=COLORS['gray'], linewidth=0.5, alpha=0.5)

        elif indicator == 'supertrend':
            st, trend = _calc_visual_supertrend(highs, lows, closes)
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.75, alpha=0.8)
            bull = np.where(trend > 0, st, np.nan)
            bear = np.where(trend < 0, st, np.nan)
            ax.plot(x, bull, color=COLORS['green'], linewidth=1.1, label='ST alcista')
            ax.plot(x, bear, color=COLORS['red'], linewidth=1.1, label='ST bajista')
            ax.legend(loc='upper left', fontsize=6, framealpha=0.35)

        elif indicator == 'psar':
            psar = _calc_visual_psar(highs, lows)
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.7, alpha=0.75)
            colors = [COLORS['green'] if psar[i] <= closes[i] else COLORS['red'] for i in range(n)]
            ax.scatter(x, psar, c=colors, s=7, alpha=0.8)

        elif indicator == 'ichimoku':
            high_s = pd.Series(highs)
            low_s = pd.Series(lows)
            tenkan = ((high_s.rolling(9).max() + low_s.rolling(9).min()) / 2).values
            kijun = ((high_s.rolling(26).max() + low_s.rolling(26).min()) / 2).values
            span_a = pd.Series((tenkan + kijun) / 2).shift(26).values
            span_b = pd.Series((high_s.rolling(52).max() + low_s.rolling(52).min()) / 2).shift(26).values
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.7, alpha=0.75)
            ax.plot(x, tenkan, color=COLORS['blue'], linewidth=0.8, label='Tenkan')
            ax.plot(x, kijun, color=COLORS['red'], linewidth=0.8, label='Kijun')
            valid = np.isfinite(span_a) & np.isfinite(span_b)
            if valid.any():
                ax.fill_between(x, span_a, span_b, where=valid, color=COLORS['purple'], alpha=0.12)
            ax.legend(loc='upper left', fontsize=6, framealpha=0.35)

        elif indicator == 'squeeze':
            upper, sma, lower = _calc_bollinger(closes, 20, 2)
            bb_width = np.divide(upper - lower, sma, out=np.zeros_like(sma), where=sma != 0) * 100
            width_series = pd.Series(bb_width)
            threshold = width_series.rolling(50, min_periods=20).quantile(0.25).values
            squeeze_on = bb_width <= threshold
            ax.plot(x, bb_width, color=COLORS['yellow'], linewidth=1.0, label='BB width %')
            ax.fill_between(x, 0, bb_width, where=squeeze_on, color=COLORS['purple'], alpha=0.28, label='Squeeze')
            ax.legend(loc='upper left', fontsize=6, framealpha=0.35)

        elif indicator == 'ftm':
            # Proxy VISUAL de fuerza: spread EMA9/EMA21 normalizado por ATR.
            # No se usa para recalcular ni alterar el FTM del sistema.
            ema9 = _calc_ema(closes, 9)
            ema21 = _calc_ema(closes, 21)
            atr = _calc_visual_atr(highs, lows, closes, 14)
            force = np.divide(ema9 - ema21, atr, out=np.zeros_like(atr), where=atr != 0)
            ax.plot(x, force, color=COLORS['blue'], linewidth=1.0)
            ax.axhline(0, color=COLORS['gray'], linewidth=0.5, alpha=0.5)
            ax.fill_between(x, 0, force, where=(force >= 0), color=COLORS['green'], alpha=0.12)
            ax.fill_between(x, 0, force, where=(force < 0), color=COLORS['red'], alpha=0.12)
            ax.text(0.995, 0.86, 'proxy visual', transform=ax.transAxes, ha='right', va='top', fontsize=6, color=COLORS['gray'])

        elif indicator == 'whale':
            # Proxy explícito: anomalía de volumen + reacción del precio.
            vol_series = pd.Series(volumes)
            median = vol_series.rolling(20, min_periods=5).median().replace(0, np.nan)
            ratio = (vol_series / median).replace([np.inf, -np.inf], np.nan).fillna(0).values
            spike = ratio >= 2.0
            colors = [COLORS['orange'] if spike[i] else COLORS['gray'] for i in range(n)]
            ax.bar(x, ratio, color=colors, alpha=0.72, width=0.8)
            ax.axhline(2.0, color=COLORS['yellow'], linestyle='--', linewidth=0.7, alpha=0.7)
            ax.text(0.995, 0.86, 'proxy OHLCV, no órdenes observadas', transform=ax.transAxes, ha='right', va='top', fontsize=6, color=COLORS['gray'])

        elif indicator == 'fvg':
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.8)
            found = 0
            for i in range(2, n):
                # Gap alcista: high de i-2 por debajo del low actual.
                if highs[i - 2] < lows[i]:
                    ax.axhspan(highs[i - 2], lows[i], color=COLORS['green'], alpha=0.11)
                    found += 1
                # Gap bajista: low de i-2 por encima del high actual.
                elif lows[i - 2] > highs[i]:
                    ax.axhspan(highs[i], lows[i - 2], color=COLORS['red'], alpha=0.11)
                    found += 1
                if found >= 4:
                    break

        elif indicator == 'order_blocks':
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.8)
            atr = _calc_visual_atr(highs, lows, closes, 14)
            candidates = []
            for i in range(2, n - 1):
                displacement = closes[i + 1] - closes[i]
                if atr[i] <= 0:
                    continue
                if closes[i] < opens[i] and displacement > 1.2 * atr[i]:
                    candidates.append((i, lows[i], highs[i], COLORS['green']))
                elif closes[i] > opens[i] and displacement < -1.2 * atr[i]:
                    candidates.append((i, lows[i], highs[i], COLORS['red']))
            for i, low_zone, high_zone, color in candidates[-3:]:
                ax.axhspan(low_zone, high_zone, color=color, alpha=0.12)
                ax.axvline(i, color=color, linewidth=0.5, alpha=0.4)
            ax.text(0.995, 0.86, 'vista OHLCV del contexto OB', transform=ax.transAxes, ha='right', va='top', fontsize=6, color=COLORS['gray'])

        elif indicator in ('sweeps', 'stop_hunts'):
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.75)
            lookback = 5
            for i in range(lookback, n):
                prior_high = np.max(highs[i - lookback:i])
                prior_low = np.min(lows[i - lookback:i])
                if highs[i] > prior_high and closes[i] < prior_high:
                    ax.scatter(i, highs[i], marker='v', s=28, color=COLORS['red'], zorder=4)
                    ax.axhline(prior_high, color=COLORS['red'], linestyle=':', linewidth=0.5, alpha=0.35)
                if lows[i] < prior_low and closes[i] > prior_low:
                    ax.scatter(i, lows[i], marker='^', s=28, color=COLORS['green'], zorder=4)
                    ax.axhline(prior_low, color=COLORS['green'], linestyle=':', linewidth=0.5, alpha=0.35)

        elif indicator == 'volume_profile':
            uses_time_axis = False
            typical = (highs + lows + closes) / 3.0
            price_min = np.nanmin(lows)
            price_max = np.nanmax(highs)
            if price_max > price_min:
                bins = np.linspace(price_min, price_max, 25)
                idxs = np.clip(np.digitize(typical, bins) - 1, 0, len(bins) - 2)
                profile = np.zeros(len(bins) - 1)
                for i, bin_idx in enumerate(idxs):
                    profile[bin_idx] += volumes[i]
                centers = (bins[:-1] + bins[1:]) / 2
                height_bar = (bins[1] - bins[0]) * 0.78
                ax.barh(centers, profile, height=height_bar, color=COLORS['blue'], alpha=0.55)
                poc_idx = int(np.argmax(profile)) if len(profile) else 0
                if len(centers):
                    ax.axhline(centers[poc_idx], color=COLORS['yellow'], linewidth=1.0, label='POC aprox.')
                    ax.legend(loc='upper right', fontsize=6, framealpha=0.35)
            ax.set_xlabel('Volumen agregado por precio', fontsize=6, color=COLORS['gray'])
            ax.text(0.995, 0.86, 'aprox. con volumen de vela', transform=ax.transAxes, ha='right', va='top', fontsize=6, color=COLORS['gray'])

        else:
            # Fallback HONESTO: no fingir que otro gráfico representa el indicador.
            ax.plot(x, closes, color=COLORS['white'], linewidth=0.8)
            ax.text(
                0.5, 0.5,
                'Evidencia seleccionada por el sistema\nvisualización específica no disponible',
                transform=ax.transAxes,
                ha='center', va='center',
                fontsize=7,
                color=COLORS['gray'],
                bbox={
                    'boxstyle': 'round,pad=0.35',
                    'facecolor': COLORS['bg'],
                    'edgecolor': COLORS['gray'],
                    'alpha': 0.8,
                }
            )

    except Exception as e:
        logger.debug(f'_render_indicator_into_ax {indicator}: {e}')
        ax.clear()
        ax.set_facecolor(COLORS['bg'])
        ax.plot(x, closes, color=COLORS['white'], linewidth=0.75)
        ax.set_title(
            prefix + title_map.get(indicator, indicator.upper()),
            color='white', fontsize=9, fontweight='bold', pad=5, loc='left'
        )
        ax.text(
            0.5, 0.5,
            'Panel no disponible; la señal no fue modificada',
            transform=ax.transAxes,
            ha='center', va='center',
            fontsize=7, color=COLORS['gray']
        )

    # X ticks sólo en el último panel cuando el eje representa tiempo.
    if uses_time_axis:
        if is_last:
            times = df['time'].values
            step = max(1, n // 6)
            tick_idx = list(range(0, n, step))
            ax.set_xticks(tick_idx)
            ax.set_xticklabels(
                [pd.Timestamp(times[i]).strftime('%m-%d %H:%M') for i in tick_idx],
                rotation=25,
                ha='right',
                fontsize=6
            )
        else:
            ax.set_xticks([])

def render_supporting_indicators_bundle(symbol: str, timeframe: str,
                                          analysis: dict,
                                          indicators: List[str],
                                          max_indicators: int = 4) -> List[dict]:
    """
    Genera imágenes individuales de los indicadores que respaldan la señal.
    Retorna lista de {'name': str, 'image': bytes}.
    """
    df = _prepare_df(analysis, min_candles=30, symbol=symbol, timeframe=timeframe)
    if df is None:
        logger.warning(f'render_supporting_indicators_bundle: sin df para {symbol} {timeframe}')
        return []
    
    indicators = (indicators or [])[:max_indicators]
    title_names = {
        'rsi': 'RSI', 'rsi_maverick': 'RSI Maverick',
        'macd': 'MACD', 'bollinger': 'Bollinger Bands',
        'volume': 'Volumen', 'dmi': 'DMI/ADX', 'ema': 'Precio + EMAs',
        'stochastic': 'Estocástico', 'williams': 'Williams %R',
        'atr': 'ATR', 'obv': 'OBV', 'supertrend': 'SuperTrend',
        'squeeze': 'Squeeze', 'ftm': 'Fuerza Tendencia',
        'whale': 'Detección Ballenas', 'ichimoku': 'Ichimoku',
    }
    
    results = []
    for ind in indicators:
        png = render_indicator_chart(df, ind, analysis)
        if png:
            results.append({
                'name': title_names.get(ind, ind.upper()),
                'image': png,
            })
    return results
