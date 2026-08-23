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
    'bg': '#1a1a2e',
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


def _prepare_df(analysis: dict, min_candles: int = 60) -> Optional[pd.DataFrame]:
    """
    Extrae el DataFrame del análisis. Devuelve None si no hay datos suficientes.
    Puede venir en analysis['df'] o análisis['structure']['df'].
    """
    df_dict = analysis.get('df') or (analysis.get('structure') or {}).get('df') or {}
    if not df_dict or not isinstance(df_dict, dict):
        return None
    
    times = df_dict.get('time', [])
    opens = df_dict.get('open', [])
    highs = df_dict.get('high', [])
    lows = df_dict.get('low', [])
    closes = df_dict.get('close', [])
    volumes = df_dict.get('volume', [])
    
    if len(times) < min_candles:
        return None
    
    try:
        df = pd.DataFrame({
            'time': pd.to_datetime(times),
            'open': [float(x) for x in opens],
            'high': [float(x) for x in highs],
            'low':  [float(x) for x in lows],
            'close': [float(x) for x in closes],
            'volume': [float(x) if x else 0 for x in volumes],
        })
        # Tomar solo las últimas N velas para el gráfico
        df = df.tail(100).reset_index(drop=True)
        return df
    except Exception as e:
        logger.warning(f'Error construyendo df: {e}')
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
    df = _prepare_df(analysis, min_candles=30)
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


def render_supporting_indicators_bundle(symbol: str, timeframe: str,
                                          analysis: dict,
                                          indicators: List[str],
                                          max_indicators: int = 4) -> List[dict]:
    """
    Genera imágenes individuales de los indicadores que respaldan la señal.
    Retorna lista de {'name': str, 'image': bytes}.
    """
    df = _prepare_df(analysis, min_candles=30)
    if df is None:
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
