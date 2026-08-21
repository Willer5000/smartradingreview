# app.py - Sistema Experto de Trading Profesional
# Versión 1.0 - Implementación completa sin atajos

import os
import json
import time
import math
import random
import base64
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO, StringIO
import pytz
from flask import Flask, render_template, jsonify, request, send_file
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import kaleido
import threading
warnings.filterwarnings('ignore')
# ============================================================================
# CONFIGURACIÓN DE LOGGING PARA DEPURACIÓN
# ============================================================================

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("=" * 60)
print("🚀 CRYPTO TRADER ANALYST PRO - INICIANDO SISTEMA")
print("=" * 60)
print(f"✅ Logging activado - Nivel: DEBUG")

# ============================================================================
# CONFIGURACIÓN INICIAL DEL SISTEMA
# ============================================================================

app = Flask(__name__)

# Configuración de zona horaria Bolivia
bolivia_tz = pytz.timezone('America/La_Paz')

# Credenciales Telegram
TELEGRAM_BOT_TOKEN = "7248129884:AAE2vctRH82wosRTrqs-PxdTgQLLG_nYYjU"
TELEGRAM_CHAT_ID = "-5079948404"

# Configuración de pares
SYMBOLS = {
    'BTC-USDT': {'name': 'BTC/USDT', 'type': 'crypto', 'decimals': 2},
    'PAXG-USDT': {'name': 'PAXG/USDT', 'type': 'gold', 'decimals': 2},
    'PAXG-BTC': {'name': 'PAXG/BTC', 'type': 'ratio', 'decimals': 8}
}

# Mapeo de intervalos KuCoin
KUCOIN_INTERVALS = {
    '4h': '4hour',
    '12h': '12hour',
    '1D': '1day',
    '1W': '1week'
}

# Temporalidades operativas con horarios de ejecución (Bolivia)
TIMEFRAMES = {
    '4h': {'execution': ['23:57', '03:57', '07:57', '11:57', '15:57', '19:57'], 'name': '4 Horas', 'type': 'intraday'},
    '12h': {'execution': ['07:55', '19:55'], 'name': '12 Horas', 'type': 'swing'},
    '1D': {'execution': ['19:53'], 'name': '1 Día', 'type': 'investment'},
    '1W': {'execution': ['Sunday 19:50'], 'name': '1 Semana', 'type': 'strategic'}
}

# ============================================================================
# CONFIGURACIÓN PARA FEAR & GREED INDEX
# ============================================================================
FEAR_GREED_API_URL = "https://api.alternative.me/fng/"
FEAR_GREED_CACHE = {
    'data': None,
    'last_update': None,
    'cache_duration': 3600  # 1 hora en segundos (el índice cambia 1 vez al día)
}

# ============================================================================
# CLASE PRINCIPAL: SISTEMA EXPERTO DE TRADING
# ============================================================================

class TradingExpertSystem:
    """Sistema Experto de Trading con 10+ años de experiencia simulada"""
    
    def __init__(self):
        self.bolivia_tz = pytz.timezone('America/La_Paz')
        self.last_analysis = {}
        self.voting_history = {}
        self.pattern_database = self._initialize_pattern_database()
        self.justification_bank = self._initialize_justification_bank()
        
        # ============ INSTANCIA DEL MAPA DE CALOR DE LIQUIDACIONES ============
        # Soporta TF de spot Y futuros
        self.liquidation_heatmaps = {
            '5m': {}, '15m': {}, '30m': {}, '1h': {}, '2h': {},
            '4h': {}, '12h': {}, '1D': {}, '1W': {}
        }
        
        # ============ NUEVO: SISTEMA DE ZONAS DINÁMICAS ============
        self.dynamic_zones = {'4h': {}, '12h': {}, '1D': {}, '1W': {}}
        # ===========================================================
        
    # ========================================================================
    # FUNCIONES AUXILIARES DE CÁLCULO (IMPLEMENTACIÓN MANUAL SIN TALIB)
    # ========================================================================
    
    def calculate_sma(self, prices, period):
        """Calcular Media Móvil Simple manualmente"""
        if len(prices) == 0 or period <= 0:
            return np.zeros_like(prices) if isinstance(prices, np.ndarray) else [0] * len(prices)
        
        prices_array = np.array(prices) if not isinstance(prices, np.ndarray) else prices
        sma = np.zeros_like(prices_array)
        
        for i in range(len(prices_array)):
            if i < period - 1:
                window = prices_array[0:i+1]
                sma[i] = np.mean(window) if len(window) > 0 else prices_array[i]
            else:
                window = prices_array[i-period+1:i+1]
                sma[i] = np.mean(window)
        
        return sma
    
    def calculate_ema(self, prices, period):
        """Calcular Media Móvil Exponencial manualmente"""
        if len(prices) == 0 or period <= 0:
            return np.zeros_like(prices) if isinstance(prices, np.ndarray) else [0] * len(prices)
        
        prices_array = np.array(prices) if not isinstance(prices, np.ndarray) else prices
        ema = np.zeros_like(prices_array)
        alpha = 2 / (period + 1)
        
        ema[0] = prices_array[0]
        
        for i in range(1, len(prices_array)):
            ema[i] = (prices_array[i] * alpha) + (ema[i-1] * (1 - alpha))
        
        return ema
    
    def calculate_rsi(self, prices, period=14):
        """Calcular RSI Tradicional manualmente"""
        if len(prices) < period + 1:
            return np.array([50] * len(prices))
        
        prices_array = np.array(prices)
        deltas = np.diff(prices_array)
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 100
        rsi = np.zeros_like(prices_array)
        rsi[period] = 100 - (100 / (1 + rs))
        
        for i in range(period + 1, len(prices_array)):
            delta = deltas[i-1]
            if delta > 0:
                upval = delta
                downval = 0
            else:
                upval = 0
                downval = -delta
            
            up = ((up * (period - 1)) + upval) / period
            down = ((down * (period - 1)) + downval) / period
            rs = up / down if down != 0 else 100
            rsi[i] = 100 - (100 / (1 + rs))
        
        rsi[:period] = rsi[period]
        return rsi
    
    def calculate_stochastic(self, high, low, close, k_period=14, d_period=3):
        """Calcular Estocástico manualmente"""
        n = len(close)
        k_line = np.zeros(n)
        
        for i in range(n):
            if i < k_period - 1:
                k_line[i] = 50
            else:
                high_max = np.max(high[i-k_period+1:i+1])
                low_min = np.min(low[i-k_period+1:i+1])
                if high_max - low_min != 0:
                    k_line[i] = 100 * (close[i] - low_min) / (high_max - low_min)
                else:
                    k_line[i] = 50
        
        d_line = self.calculate_sma(k_line, d_period)
        
        return {'%K': k_line, '%D': d_line}
    
    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calcular MACD manualmente"""
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self.calculate_ema(macd_line, signal)
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def calculate_bollinger_bands(self, prices, period=20, std_dev=2):
        """Calcular Bandas de Bollinger manualmente"""
        sma = self.calculate_sma(prices, period)
        n = len(prices)
        upper_band = np.zeros(n)
        lower_band = np.zeros(n)
        
        for i in range(n):
            if i < period - 1:
                window = prices[0:i+1]
            else:
                window = prices[i-period+1:i+1]
            std = np.std(window) if len(window) > 1 else 0
            upper_band[i] = sma[i] + (std * std_dev)
            lower_band[i] = sma[i] - (std * std_dev)
        
        return {
            'middle': sma,
            'upper': upper_band,
            'lower': lower_band
        }
    
    def calculate_atr(self, high, low, close, period=14):
        """Calcular ATR manualmente"""
        n = len(high)
        tr = np.zeros(n)
        
        for i in range(n):
            if i == 0:
                tr[i] = high[i] - low[i]
            else:
                hl = high[i] - low[i]
                hc = abs(high[i] - close[i-1])
                lc = abs(low[i] - close[i-1])
                tr[i] = max(hl, hc, lc)
        
        atr = self.calculate_ema(tr, period)
        return atr
    
    def calculate_adx(self, high, low, close, period=14):
        """Calcular ADX con DMI manualmente - SIN LÍMITE ARTIFICIAL"""
        n = len(high)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        tr = np.zeros(n)
        
        for i in range(1, n):
            up_move = high[i] - high[i-1]
            down_move = low[i-1] - low[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            else:
                plus_dm[i] = 0
                
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            else:
                minus_dm[i] = 0
            
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i-1])
            lc = abs(low[i] - close[i-1])
            tr[i] = max(hl, hc, lc)
        
        atr = self.calculate_ema(tr, period)
        plus_di_ema = self.calculate_ema(plus_dm, period)
        minus_di_ema = self.calculate_ema(minus_dm, period)
        
        plus_di = np.zeros(n)
        minus_di = np.zeros(n)
        dx = np.zeros(n)
        
        for i in range(n):
            if atr[i] != 0:
                plus_di[i] = 100 * plus_di_ema[i] / atr[i]
                minus_di[i] = 100 * minus_di_ema[i] / atr[i]
                di_sum = plus_di[i] + minus_di[i]
                if di_sum != 0:
                    dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum
        
        adx = self.calculate_ema(dx, period)
        
        # EL ADX AHORA PUEDE SUPERAR 60, REFLEJANDO TENDENCIAS EXTREMADAMENTE FUERTES
        
        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di,
            'dx': dx
        }
    
    def calculate_supertrend(self, high, low, close, period=10, multiplier=3):
        """Calcular SuperTrend manualmente"""
        atr = self.calculate_atr(high, low, close, period)
        n = len(close)
        
        basic_ub = (high + low) / 2 + multiplier * atr
        basic_lb = (high + low) / 2 - multiplier * atr
        
        final_ub = np.zeros(n)
        final_lb = np.zeros(n)
        supertrend = np.zeros(n)
        trend = np.zeros(n)
        
        for i in range(n):
            if i == 0:
                final_ub[i] = basic_ub[i]
                final_lb[i] = basic_lb[i]
                supertrend[i] = final_ub[i]
                trend[i] = -1
            else:
                final_ub[i] = basic_ub[i] if (basic_ub[i] < final_ub[i-1] or close[i-1] > final_ub[i-1]) else final_ub[i-1]
                final_lb[i] = basic_lb[i] if (basic_lb[i] > final_lb[i-1] or close[i-1] < final_lb[i-1]) else final_lb[i-1]
                
                if close[i] <= final_ub[i] and trend[i-1] == 1:
                    trend[i] = -1
                    supertrend[i] = final_ub[i]
                elif close[i] >= final_lb[i] and trend[i-1] == -1:
                    trend[i] = 1
                    supertrend[i] = final_lb[i]
                else:
                    trend[i] = trend[i-1]
                    supertrend[i] = supertrend[i-1]
        
        return {
            'supertrend': supertrend,
            'trend': trend,
            'upper': final_ub,
            'lower': final_lb
        }
    
    def calculate_parabolic_sar(self, high, low, acceleration=0.02, maximum=0.2):
        """Calcular Parabolic SAR manualmente"""
        n = len(high)
        sar = np.zeros(n)
        ep = np.zeros(n)
        af = np.zeros(n)
        trend = np.zeros(n)
        
        if n == 0:
            return {'sar': sar, 'trend': trend, 'ep': ep, 'af': af}
        
        sar[0] = low[0]
        ep[0] = high[0]
        af[0] = acceleration
        trend[0] = 1
        
        for i in range(1, n):
            if trend[i-1] == 1:
                sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
                if high[i] > ep[i-1]:
                    ep[i] = high[i]
                    af[i] = min(af[i-1] + acceleration, maximum)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
                
                if low[i] < sar[i]:
                    trend[i] = -1
                    sar[i] = ep[i-1]
                    ep[i] = low[i]
                    af[i] = acceleration
                else:
                    trend[i] = 1
            else:
                sar[i] = sar[i-1] - af[i-1] * (sar[i-1] - ep[i-1])
                if low[i] < ep[i-1]:
                    ep[i] = low[i]
                    af[i] = min(af[i-1] + acceleration, maximum)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
                
                if high[i] > sar[i]:
                    trend[i] = 1
                    sar[i] = ep[i-1]
                    ep[i] = high[i]
                    af[i] = acceleration
                else:
                    trend[i] = -1
        
        return {'sar': sar, 'trend': trend, 'ep': ep, 'af': af}
    
    def calculate_obv(self, close, volume):
        """Calcular On-Balance Volume manualmente"""
        n = len(close)
        obv = np.zeros(n)
        
        for i in range(1, n):
            if close[i] > close[i-1]:
                obv[i] = obv[i-1] + volume[i]
            elif close[i] < close[i-1]:
                obv[i] = obv[i-1] - volume[i]
            else:
                obv[i] = obv[i-1]
        
        return obv
    
    def calculate_mfi(self, high, low, close, volume, period=14):
        """Calcular Money Flow Index manualmente"""
        n = len(close)
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        mfi = np.zeros(n)
        
        for i in range(period, n):
            positive_flow = 0
            negative_flow = 0
            
            for j in range(i - period + 1, i + 1):
                if j > i - period + 1:
                    if typical_price[j] > typical_price[j-1]:
                        positive_flow += money_flow[j]
                    else:
                        negative_flow += money_flow[j]
            
            if negative_flow != 0:
                money_ratio = positive_flow / negative_flow
                mfi[i] = 100 - (100 / (1 + money_ratio))
            else:
                mfi[i] = 100
        
        mfi[:period] = mfi[period]
        return mfi
    
    def calculate_cci(self, high, low, close, period=20):
        """Calcular Commodity Channel Index manualmente"""
        typical_price = (high + low + close) / 3
        sma_tp = self.calculate_sma(typical_price, period)
        n = len(close)
        cci = np.zeros(n)
        
        for i in range(period - 1, n):
            mean_dev = 0
            for j in range(i - period + 1, i + 1):
                mean_dev += abs(typical_price[j] - sma_tp[i])
            mean_dev = mean_dev / period
            if mean_dev != 0:
                cci[i] = (typical_price[i] - sma_tp[i]) / (0.015 * mean_dev)
        
        cci[:period-1] = cci[period-1]
        return cci
    
    def calculate_williams_r(self, high, low, close, period=14):
        """Calcular Williams %R manualmente"""
        n = len(close)
        williams_r = np.zeros(n)
        
        for i in range(period - 1, n):
            highest_high = np.max(high[i-period+1:i+1])
            lowest_low = np.min(low[i-period+1:i+1])
            if highest_high - lowest_low != 0:
                williams_r[i] = -100 * (highest_high - close[i]) / (highest_high - lowest_low)
            else:
                williams_r[i] = -50
        
        williams_r[:period-1] = williams_r[period-1]
        return williams_r
    
    def calculate_force_index(self, close, volume, period=13):
        """Calcular Force Index manualmente"""
        n = len(close)
        force = np.zeros(n)
        
        for i in range(1, n):
            force[i] = (close[i] - close[i-1]) * volume[i]
        
        force_smooth = self.calculate_ema(force, period)
        return force_smooth
    
    # === FUNCIÓN COMPLETA: calculate_ichimoku ===
    # Ubicación: Reemplazar entre línea ~410 y línea ~450 aproximadamente
    
    def calculate_ichimoku(self, high, low, close, tenkan=9, kijun=26, senkou=52):
        """Calcular Ichimoku Cloud completo con desplazamientos y señales"""
        try:
            n = len(high)
            
            tenkan_sen = np.zeros(n)
            kijun_sen = np.zeros(n)
            senkou_span_a = np.zeros(n)
            senkou_span_b = np.zeros(n)
            chikou_span = np.zeros(n)
            
            # Cálculo de líneas base
            for i in range(n):
                if i >= tenkan - 1:
                    tenkan_sen[i] = (np.max(high[i-tenkan+1:i+1]) + np.min(low[i-tenkan+1:i+1])) / 2
                
                if i >= kijun - 1:
                    kijun_sen[i] = (np.max(high[i-kijun+1:i+1]) + np.min(low[i-kijun+1:i+1])) / 2
                
                if i >= kijun - 1 and tenkan_sen[i] != 0 and kijun_sen[i] != 0:
                    senkou_span_a[i] = (tenkan_sen[i] + kijun_sen[i]) / 2
                
                if i >= senkou - 1:
                    senkou_span_b[i] = (np.max(high[i-senkou+1:i+1]) + np.min(low[i-senkou+1:i+1])) / 2
                
                if i < n - kijun:
                    chikou_span[i] = close[i]
            
            # Desplazar Senkou Span A/B 26 períodos hacia adelante
            senkou_a_shifted = np.zeros(n)
            senkou_b_shifted = np.zeros(n)
            
            for i in range(n):
                if i >= kijun:
                    senkou_a_shifted[i] = senkou_span_a[i - kijun] if (i - kijun) < n else 0
                    senkou_b_shifted[i] = senkou_span_b[i - kijun] if (i - kijun) < n else 0
            
            # Desplazar Chikou Span 26 períodos hacia atrás
            chikou_shifted = np.zeros(n)
            for i in range(n - kijun):
                chikou_shifted[i + kijun] = chikou_span[i]
            
            # Detección de señales
            signals = []
            
            # TK Cross (Tenkan/Kijun cruce)
            if n > 1:
                if tenkan_sen[-1] > kijun_sen[-1] and tenkan_sen[-2] <= kijun_sen[-2]:
                    signals.append({'type': 'tk_cross_bull', 'strength': 80})
                elif tenkan_sen[-1] < kijun_sen[-1] and tenkan_sen[-2] >= kijun_sen[-2]:
                    signals.append({'type': 'tk_cross_bear', 'strength': 80})
            
            # Precio sobre/bajo nube
            if n > 0:
                if close[-1] > max(senkou_a_shifted[-1], senkou_b_shifted[-1]):
                    signals.append({'type': 'price_above_cloud', 'strength': 70})
                    cloud_position = 'above'
                elif close[-1] < min(senkou_a_shifted[-1], senkou_b_shifted[-1]):
                    signals.append({'type': 'price_below_cloud', 'strength': 70})
                    cloud_position = 'below'
                else:
                    signals.append({'type': 'price_inside_cloud', 'strength': 50})
                    cloud_position = 'inside'
            
            # Cambio de color de nube
            if n > 1 and senkou_a_shifted[-1] > senkou_b_shifted[-1] and senkou_a_shifted[-2] <= senkou_b_shifted[-2]:
                signals.append({'type': 'cloud_turn_bull', 'strength': 85})
            elif n > 1 and senkou_a_shifted[-1] < senkou_b_shifted[-1] and senkou_a_shifted[-2] >= senkou_b_shifted[-2]:
                signals.append({'type': 'cloud_turn_bear', 'strength': 85})
            
            # Espesor de nube
            cloud_thickness = abs(senkou_a_shifted[-1] - senkou_b_shifted[-1]) if n > 0 else 0
            price = close[-1] if n > 0 else 1
            cloud_thickness_pct = (cloud_thickness / price * 100) if price != 0 else 0
            
            if cloud_thickness_pct > 2:
                cloud_thickness_signal = 'thick'
            elif cloud_thickness_pct < 0.5:
                cloud_thickness_signal = 'thin'
            else:
                cloud_thickness_signal = 'normal'
            
            # Chikou Span posición
            if n > kijun:
                chikou_position = 'above' if chikou_shifted[-1] > close[-(kijun+1)] else 'below' if chikou_shifted[-1] < close[-(kijun+1)] else 'equal'
            else:
                chikou_position = 'unknown'
            
            # Interpretación completa
            if cloud_position == 'above' and 'tk_cross_bull' in [s['type'] for s in signals]:
                interpretation = 'bullish_strong'
                score = 90
            elif cloud_position == 'below' and 'tk_cross_bear' in [s['type'] for s in signals]:
                interpretation = 'bearish_strong'
                score = 90
            elif cloud_position == 'above':
                interpretation = 'bullish'
                score = 70
            elif cloud_position == 'below':
                interpretation = 'bearish'
                score = 70
            else:
                interpretation = 'neutral'
                score = 50
            
            return {
                'tenkan': tenkan_sen,
                'kijun': kijun_sen,
                'senkou_a': senkou_span_a,
                'senkou_b': senkou_span_b,
                'chikou': chikou_span,
                'senkou_a_shifted': senkou_a_shifted,
                'senkou_b_shifted': senkou_b_shifted,
                'chikou_shifted': chikou_shifted,
                'signals': signals,
                'cloud_position': cloud_position,
                'cloud_thickness': float(cloud_thickness),
                'cloud_thickness_pct': float(cloud_thickness_pct),
                'cloud_thickness_signal': cloud_thickness_signal,
                'chikou_position': chikou_position,
                'interpretation': interpretation,
                'score': score
            }
        except Exception as e:
            print(f"Error en Ichimoku: {e}")
            n = len(high) if isinstance(high, np.ndarray) else 0
            return {
                'tenkan': np.zeros(n),
                'kijun': np.zeros(n),
                'senkou_a': np.zeros(n),
                'senkou_b': np.zeros(n),
                'chikou': np.zeros(n),
                'senkou_a_shifted': np.zeros(n),
                'senkou_b_shifted': np.zeros(n),
                'chikou_shifted': np.zeros(n),
                'signals': [],
                'cloud_position': 'unknown',
                'cloud_thickness': 0,
                'cloud_thickness_pct': 0,
                'cloud_thickness_signal': 'unknown',
                'chikou_position': 'unknown',
                'interpretation': 'neutral',
                'score': 50
            }
    # === FIN calculate_ichimoku ===
    
    # ========================================================================
    # INDICADORES ESPECIALES MAVERICK
    # ========================================================================
    
    def calculate_trend_strength_maverick(self, close, length=20, mult=2.0):
        """Calcular Fuerza de Tendencia Maverick - SEGÚN PINESCRIPT ORIGINAL"""
        try:
            n = len(close)
            close_array = np.array(close)
            
            basis = self.calculate_sma(close_array, length)
            dev = np.zeros(n)
            
            for i in range(length-1, n):
                window = close_array[i-length+1:i+1]
                dev[i] = np.std(window) if len(window) > 1 else 0
            
            upper = basis + (dev * mult)
            lower = basis - (dev * mult)
            
            bb_width = np.zeros(n)
            for i in range(n):
                if basis[i] > 0:
                    bb_width[i] = ((upper[i] - lower[i]) / basis[i]) * 100
            
            # ============ LÓGICA ORIGINAL DE PINESCRIPT ============
            # trend_strength = bb_width CON SIGNO:
            # POSITIVO = bb_width AUMENTÓ respecto a vela anterior
            # NEGATIVO = bb_width DISMINUYÓ respecto a vela anterior
            # El VALOR es el ancho de banda, no la diferencia
            trend_strength = np.zeros(n)
            for i in range(1, n):
                if bb_width[i] > bb_width[i-1]:
                    trend_strength[i] = bb_width[i]      # Verde: ancho creciente
                else:
                    trend_strength[i] = -bb_width[i]     # Rojo: ancho decreciente
            
            # Umbral para zonas de no-operación (percentil 70 del ancho de banda histórico)
            if n >= 50:
                historical_bb_width = bb_width[max(0, n-100):n]
                high_zone_threshold = np.percentile(historical_bb_width, 70)
            else:
                high_zone_threshold = np.percentile(bb_width, 70) if len(bb_width) > 0 else 5
            
            no_trade_zones = np.zeros(n, dtype=bool)
            strength_signals = ['NEUTRAL'] * n
            
            # Detección de zonas de no-operación: 
            # Ancho de banda ALTO (> percentil 70) pero DECRECIENTE (rojo)
            for i in range(10, n):
                if (bb_width[i] > high_zone_threshold and 
                    trend_strength[i] < 0 and  # Rojo (decreciente)
                    bb_width[i] < np.max(bb_width[max(0, i-10):i])):  # No es el máximo absoluto
                    no_trade_zones[i] = True
                
                # Clasificación de fuerza
                if trend_strength[i] > 0:
                    if bb_width[i] > high_zone_threshold:
                        strength_signals[i] = 'STRONG_UP'      # Verde alto
                    else:
                        strength_signals[i] = 'WEAK_UP'        # Verde bajo
                elif trend_strength[i] < 0:
                    if bb_width[i] > high_zone_threshold:
                        strength_signals[i] = 'STRONG_DOWN'    # Rojo alto (¡NO OPERAR!)
                    else:
                        strength_signals[i] = 'WEAK_DOWN'      # Rojo bajo
                else:
                    strength_signals[i] = 'NEUTRAL'
            
            return {
                'bb_width': bb_width.tolist(),
                'trend_strength': trend_strength.tolist(),
                'basis': basis.tolist(),
                'upper_band': upper.tolist(),
                'lower_band': lower.tolist(),
                'high_zone_threshold': float(high_zone_threshold),
                'no_trade_zones': no_trade_zones.tolist(),
                'strength_signals': strength_signals,
                'colors': ['green' if x > 0 else 'red' for x in trend_strength]
            }
        except Exception as e:
            print(f"Error en FTMaverick: {e}")
            n = len(close)
            return {
                'bb_width': [0] * n,
                'trend_strength': [0] * n,
                'basis': [0] * n,
                'upper_band': [0] * n,
                'lower_band': [0] * n,
                'high_zone_threshold': 5.0,
                'no_trade_zones': [False] * n,
                'strength_signals': ['NEUTRAL'] * n,
                'colors': ['gray'] * n
            }
    
    def calculate_rsi_maverick(self, close, length=20, bb_multiplier=2.0):
        """Calcular RSI Maverick - Posición dentro de bandas de volatilidad"""
        try:
            n = len(close)
            close_array = np.array(close)
            
            basis = np.array([np.mean(close_array[max(0, i-length+1):i+1]) for i in range(n)])
            dev = np.array([np.std(close_array[max(0, i-length+1):i+1]) for i in range(n)])
            
            upper = basis + (dev * bb_multiplier)
            lower = basis - (dev * bb_multiplier)
            
            b_percent = np.zeros(n)
            for i in range(n):
                if (upper[i] - lower[i]) > 0:
                    b_percent[i] = (close_array[i] - lower[i]) / (upper[i] - lower[i])
                else:
                    b_percent[i] = 0.5
            
            return b_percent.tolist()
        except Exception as e:
            print(f"Error en RSI Maverick: {e}")
            return [0.5] * len(close)
    
    # === FUNCIÓN COMPLETA: calculate_whale_signals_improved ===
    # Ubicación: Reemplazar entre línea ~460 y línea ~530 aproximadamente
    
    def calculate_whale_signals_improved(self, df, sensitivity=1.7, min_volume_multiplier=1.5, 
                                       support_resistance_lookback=50, signal_threshold=25):
        """Detector de Ballenas Mejorado - RETORNA VALORES BOOLEANOS, NO LISTAS"""
        try:
            close = df['close'].values
            low = df['low'].values
            high = df['high'].values
            volume = df['volume'].values
            open_price = df['open'].values
            
            n = len(close)
            
            # Inicializar acumuladores
            whale_pump = 0
            whale_dump = 0
            confirmed_buy = False
            confirmed_sell = False
            extended_buy = False
            extended_sell = False
            iceberg_buy = False
            iceberg_sell = False
            spoofing_buy = False
            spoofing_sell = False
            aggressive_whale = False
            passive_whale = False
            
            # Usar SOLO la última vela para análisis en tiempo real
            i = n - 1
            
            if i < 10:
                return {
                    'whale_pump': 0, 'whale_dump': 0,
                    'confirmed_buy': False, 'confirmed_sell': False,
                    'extended_buy': False, 'extended_sell': False,
                    'iceberg_buy': False, 'iceberg_sell': False,
                    'spoofing_buy': False, 'spoofing_sell': False,
                    'aggressive_whale': False, 'passive_whale': False,
                    'support': float(low[i]), 'resistance': float(high[i]),
                    'volume_anomaly': False
                }
            
            # Volumen promedio
            avg_volume = np.mean(volume[max(0, i-20):i+1])
            volume_ratio = volume[i] / avg_volume if avg_volume > 0 else 1
            
            # Cambio de precio
            price_change = (close[i] - close[i-1]) / close[i-1] * 100 if close[i-1] != 0 else 0
            
            # ============ DETECCIÓN DE ICEBERG ============
            consecutive_buy = 0
            consecutive_sell = 0
            for j in range(max(5, i-5), i+1):
                if j > 0:
                    if close[j] > open_price[j] and volume[j] > avg_volume * 0.8:
                        consecutive_buy += 1
                    if close[j] < open_price[j] and volume[j] > avg_volume * 0.8:
                        consecutive_sell += 1
            
            if consecutive_buy >= 3 and volume[i] > avg_volume * 1.2 and abs(price_change) < 0.5:
                iceberg_buy = True
                whale_pump = 60
            
            if consecutive_sell >= 3 and volume[i] > avg_volume * 1.2 and abs(price_change) < 0.5:
                iceberg_sell = True
                whale_dump = 60
            
            # ============ DETECCIÓN DE SPOOFING ============
            if volume[i] > avg_volume * 1.8:
                if high[i] > high[i-1] * 1.01 and close[i] < (high[i] + low[i]) / 2:
                    spoofing_sell = True
                    whale_dump = max(whale_dump, 50)
                
                if low[i] < low[i-1] * 0.99 and close[i] > (high[i] + low[i]) / 2:
                    spoofing_buy = True
                    whale_pump = max(whale_pump, 50)
            
            # ============ TIPO DE BALLENA ============
            volume_strength = min(3.0, volume_ratio / min_volume_multiplier)
            
            if volume_ratio > 2.0 and abs(price_change) > 1.0:
                aggressive_whale = True
            elif volume_ratio > 1.5 and abs(price_change) < 0.5:
                passive_whale = True
            
            # ============ SEÑAL DE COMPRA ============
            if (volume_ratio > min_volume_multiplier and 
                (close[i] < close[i-1] or price_change < -0.5) and
                low[i] <= np.min(low[max(0, i-5):i+1]) * 1.01):
                
                whale_pump = max(whale_pump, min(100, volume_ratio * 20 * sensitivity * volume_strength))
                extended_buy = True
            
            # ============ SEÑAL DE VENTA ============
            if (volume_ratio > min_volume_multiplier and 
                (close[i] > close[i-1] or price_change > 0.5) and
                high[i] >= np.max(high[max(0, i-5):i+1]) * 0.99):
                
                whale_dump = max(whale_dump, min(100, volume_ratio * 20 * sensitivity * volume_strength))
                extended_sell = True
            
            # ============ CONFIRMACIÓN ============
            current_support = np.min(low[max(0, i-support_resistance_lookback+1):i+1])
            current_resistance = np.max(high[max(0, i-support_resistance_lookback+1):i+1])
            
            if (whale_pump > signal_threshold and 
                close[i] <= current_support * 1.02 and
                volume[i] > np.mean(volume[max(0, i-10):i+1])):
                confirmed_buy = True
            
            if (whale_dump > signal_threshold and 
                close[i] >= current_resistance * 0.98 and
                volume[i] > np.mean(volume[max(0, i-10):i+1])):
                confirmed_sell = True
            
            return {
                'whale_pump': float(whale_pump),
                'whale_dump': float(whale_dump),
                'confirmed_buy': confirmed_buy,
                'confirmed_sell': confirmed_sell,
                'extended_buy': extended_buy,
                'extended_sell': extended_sell,
                'iceberg_buy': iceberg_buy,
                'iceberg_sell': iceberg_sell,
                'spoofing_buy': spoofing_buy,
                'spoofing_sell': spoofing_sell,
                'aggressive_whale': aggressive_whale,
                'passive_whale': passive_whale,
                'support': float(current_support),
                'resistance': float(current_resistance),
                'volume_anomaly': volume[i] > avg_volume * min_volume_multiplier
            }
            
        except Exception as e:
            print(f"Error en Detector de Ballenas Mejorado: {e}")
            import traceback
            traceback.print_exc()
            return {
                'whale_pump': 0, 'whale_dump': 0,
                'confirmed_buy': False, 'confirmed_sell': False,
                'extended_buy': False, 'extended_sell': False,
                'iceberg_buy': False, 'iceberg_sell': False,
                'spoofing_buy': False, 'spoofing_sell': False,
                'aggressive_whale': False, 'passive_whale': False,
                'support': 0, 'resistance': 0,
                'volume_anomaly': False
            }
    # === FIN calculate_whale_signals_improved ===
    
    def calculate_squeeze_momentum(self, high, low, close, period=20, bb_mult=2.0, kc_mult=1.5):
        """Calcular Squeeze Momentum Indicator"""
        try:
            n = len(close)
            
            bb_basis = self.calculate_sma(close, period)
            bb_dev = np.zeros(n)
            for i in range(period-1, n):
                window = close[i-period+1:i+1]
                bb_dev[i] = np.std(window) if len(window) > 1 else 0
            
            bb_upper = bb_basis + (bb_dev * bb_mult)
            bb_lower = bb_basis - (bb_dev * bb_mult)
            
            tr = np.zeros(n)
            for i in range(1, n):
                hl = high[i] - low[i]
                hc = abs(high[i] - close[i-1])
                lc = abs(low[i] - close[i-1])
                tr[i] = max(hl, hc, lc)
            
            kc_ma = self.calculate_ema(close, period)
            kc_atr = self.calculate_ema(tr, period)
            kc_upper = kc_ma + (kc_atr * kc_mult)
            kc_lower = kc_ma - (kc_atr * kc_mult)
            
            squeeze_on = np.zeros(n, dtype=bool)
            for i in range(n):
                squeeze_on[i] = (bb_lower[i] > kc_lower[i] and bb_upper[i] < kc_upper[i])
            
            highest = np.zeros(n)
            lowest = np.zeros(n)
            for i in range(n):
                highest[i] = max(high[max(0, i-period+1):i+1]) if i >= period-1 else high[i]
                lowest[i] = min(low[max(0, i-period+1):i+1]) if i >= period-1 else low[i]
            
            avg_highest = self.calculate_sma(highest, period)
            avg_lowest = self.calculate_sma(lowest, period)
            
            avg_highest = np.array(avg_highest)
            avg_lowest = np.array(avg_lowest)
            close_array = np.array(close)
            
            momentum_value = (close_array - (avg_highest + avg_lowest) / 2)
            
            momentum_line = np.zeros(n)
            for i in range(period, n):
                momentum_line[i] = momentum_value[i] - momentum_value[i-1]
            
            momentum_histogram = self.calculate_sma(momentum_line, 2)
            
            return {
                'squeeze_on': squeeze_on.tolist(),
                'momentum': momentum_line.tolist(),
                'histogram': momentum_histogram.tolist(),
                'bb_upper': bb_upper.tolist(),
                'bb_lower': bb_lower.tolist(),
                'kc_upper': kc_upper.tolist(),
                'kc_lower': kc_lower.tolist()
            }
        except Exception as e:
            print(f"Error en Squeeze Momentum: {e}")
            n = len(close)
            return {
                'squeeze_on': [False] * n,
                'momentum': [0] * n,
                'histogram': [0] * n,
                'bb_upper': [0] * n,
                'bb_lower': [0] * n,
                'kc_upper': [0] * n,
                'kc_lower': [0] * n
            }
    
    def calculate_support_resistance_channels(self, high, low, close, pivot_period=10, channel_width_pct=2, min_strength=1):
        """Calcular canales de soporte/resistencia con ancho 2%"""
        try:
            n = len(high)
            
            pivot_highs = np.zeros(n)
            pivot_lows = np.zeros(n)
            
            for i in range(pivot_period, n - pivot_period):
                window_high = high[i-pivot_period:i+pivot_period+1]
                window_low = low[i-pivot_period:i+pivot_period+1]
                
                if high[i] == np.max(window_high):
                    pivot_highs[i] = high[i]
                
                if low[i] == np.min(window_low):
                    pivot_lows[i] = low[i]
            
            pivot_points = []
            pivot_indices = []
            
            for i in range(n):
                if pivot_highs[i] > 0:
                    pivot_points.append(pivot_highs[i])
                    pivot_indices.append(i)
                if pivot_lows[i] > 0:
                    pivot_points.append(pivot_lows[i])
                    pivot_indices.append(i)
            
            if len(pivot_points) < 2:
                return [], []
            
            pivot_points = np.array(pivot_points)
            
            prd_highest = np.max(high[-300:]) if len(high) >= 300 else np.max(high)
            prd_lowest = np.min(low[-300:]) if len(low) >= 300 else np.min(low)
            cwidth = (prd_highest - prd_lowest) * channel_width_pct / 100
            
            channels = []
            
            for i in range(len(pivot_points)):
                level = pivot_points[i]
                hi = level
                lo = level
                strength = 0
                
                for j in range(len(pivot_points)):
                    other_level = pivot_points[j]
                    width = abs(other_level - level)
                    
                    if width <= cwidth:
                        hi = max(hi, other_level)
                        lo = min(lo, other_level)
                        strength += 1
                
                if strength >= min_strength:
                    channels.append({
                        'high': hi,
                        'low': lo,
                        'strength': strength,
                        'mid': (hi + lo) / 2
                    })
            
            channels = sorted(channels, key=lambda x: x['strength'], reverse=True)
            
            supports = []
            resistances = []
            current_price = close[-1] if len(close) > 0 else 0
            
            for channel in channels[:6]:
                if current_price > channel['mid']:
                    supports.append(channel['low'])
                else:
                    resistances.append(channel['high'])
            
            supports = [round(float(s), 2) for s in supports if s > 0]
            resistances = [round(float(r), 2) for r in resistances if r > 0]
            
            return supports, resistances
        except Exception as e:
            print(f"Error en Soportes/Resistencias: {e}")
            return [], []
    
    # ========================================================================
    # DETECTOR DE PATRONES DE VELA (AMPLIABLE - 32 PATRONES IMPLEMENTADOS)
    # ========================================================================
    
    # === FUNCIÓN COMPLETA: _initialize_pattern_database ===
    # Ubicación: Reemplazar entre línea ~160 y línea ~260 aproximadamente
    
    def _initialize_pattern_database(self):
        """Inicializar base de datos de patrones de vela - 130+ patrones con validación estricta"""
        return {
            # ============ PATRONES DE 1 VELA (28 COMPLETO) ============
            '1_hammer': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Martillo',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and  # Vela alcista
                    (o - l) >= (c - o) * 2.0 and  # Sombra inferior >= 2x cuerpo
                    (h - c) <= (c - o) * 0.3 and  # Sombra superior <= 30% del cuerpo
                    (c - o) > (h - l) * 0.1  # Cuerpo no mínimo
                )
            },
            '1_hanging_man': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Colgado',
                'detect': lambda o, h, l, c, p, i: (
                    i > 3 and
                    c[i] < o[i] and  # Vela bajista
                    (c[i] - l[i]) >= (o[i] - c[i]) * 2.0 and  # Sombra inferior >= 2x cuerpo
                    (h[i] - o[i]) <= (o[i] - c[i]) * 0.3 and  # Sombra superior pequeña
                    # Tendencia previa alcista (últimas 3 velas)
                    c[i-1] > o[i-1] and
                    c[i-2] > o[i-2] and
                    c[i-3] > o[i-3] and
                    np.mean(c[i-3:i]) > np.mean(c[i-6:i-3]) if i > 6 else True
                )
            },
            '1_inverted_hammer': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Martillo Invertido',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] > o[i] and  # Vela alcista
                    (h[i] - c[i]) >= (c[i] - o[i]) * 2.0 and  # Sombra superior >= 2x cuerpo
                    (o[i] - l[i]) <= (c[i] - o[i]) * 0.3 and  # Sombra inferior pequeña
                    # Tendencia previa bajista
                    c[i-1] < o[i-1] and
                    c[i-2] < o[i-2]
                )
            },
            '1_shooting_star': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Estrella Fugaz',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] < o[i] and  # Vela bajista
                    (h[i] - o[i]) >= (o[i] - c[i]) * 2.0 and  # Sombra superior >= 2x cuerpo
                    (c[i] - l[i]) <= (o[i] - c[i]) * 0.3 and  # Sombra inferior pequeña
                    # Tendencia previa alcista
                    c[i-1] > o[i-1] and
                    c[i-2] > o[i-2]
                )
            },
            '1_doji': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 50,
                'name': 'Doji',
                'detect': lambda o, h, l, c, p, i: abs(c - o) <= (h - l) * 0.1
            },
            '1_long_legged_doji': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 60,
                'name': 'Doji de Larga Sombra',
                'detect': lambda o, h, l, c, p, i: (
                    abs(c - o) <= (h - l) * 0.1 and
                    (h - max(o, c)) >= (h - l) * 0.4 and
                    (min(o, c) - l) >= (h - l) * 0.4
                )
            },
            '1_dragonfly_doji': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Doji Libélula',
                'detect': lambda o, h, l, c, p, i: (
                    abs(c - o) <= (h - l) * 0.1 and
                    h - max(o, c) <= (h - l) * 0.1 and
                    min(o, c) - l >= (h - l) * 0.5
                )
            },
            '1_gravestone_doji': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Doji Lápida',
                'detect': lambda o, h, l, c, p, i: (
                    abs(c - o) <= (h - l) * 0.1 and
                    min(o, c) - l <= (h - l) * 0.1 and
                    h - max(o, c) >= (h - l) * 0.5
                )
            },
            '1_four_price_doji': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 80,
                'name': 'Doji de Cuatro Precios',
                'detect': lambda o, h, l, c, p, i: o == h == l == c
            },
            '1_marubozu_bull': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Marubozu Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and
                    (o == l or abs(o - l) <= (c - o) * 0.05) and
                    (c == h or abs(h - c) <= (c - o) * 0.05) and
                    (c - o) > (h - l) * 0.9
                )
            },
            '1_marubozu_bear': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Marubozu Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    o > c and
                    (o == h or abs(h - o) <= (o - c) * 0.05) and
                    (c == l or abs(c - l) <= (o - c) * 0.05) and
                    (o - c) > (h - l) * 0.9
                )
            },
            '1_open_marubozu_bull': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Marubozu Abierto Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and
                    o == l and
                    c < h and
                    (c - o) > (h - l) * 0.8
                )
            },
            '1_close_marubozu_bull': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Marubozu Cerrado Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and
                    c == h and
                    o > l and
                    (c - o) > (h - l) * 0.8
                )
            },
            '1_spinning_top': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 40,
                'name': 'Peonza',
                'detect': lambda o, h, l, c, p, i: (
                    abs(c - o) <= (h - l) * 0.3 and
                    (h - max(o, c)) >= abs(c - o) * 0.5 and
                    (min(o, c) - l) >= abs(c - o) * 0.5 and
                    abs(c - o) > (h - l) * 0.05
                )
            },
            '1_long_white_candle': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 65,
                'name': 'Vela Larga Blanca',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and
                    (c - o) > (h - l) * 0.7 and
                    (c - o) > np.mean([abs(p[j] - p[j-1]) for j in range(max(1, i-10), i+1)]) * 1.5 if i > 10 else True
                )
            },
            '1_long_black_candle': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 65,
                'name': 'Vela Larga Negra',
                'detect': lambda o, h, l, c, p, i: (
                    o > c and
                    (o - c) > (h - l) * 0.7 and
                    (o - c) > np.mean([abs(p[j] - p[j-1]) for j in range(max(1, i-10), i+1)]) * 1.5 if i > 10 else True
                )
            },
            '1_short_white_candle': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 40,
                'name': 'Vela Corta Blanca',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and
                    (c - o) < (h - l) * 0.3 and
                    (c - o) < np.mean([abs(p[j] - p[j-1]) for j in range(max(1, i-10), i+1)]) * 0.7 if i > 10 else True
                )
            },
            '1_short_black_candle': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 40,
                'name': 'Vela Corta Negra',
                'detect': lambda o, h, l, c, p, i: (
                    o > c and
                    (o - c) < (h - l) * 0.3 and
                    (o - c) < np.mean([abs(p[j] - p[j-1]) for j in range(max(1, i-10), i+1)]) * 0.7 if i > 10 else True
                )
            },
            '1_high_wave': {
                'type': '1',
                'direction': 'neutral',
                'reliability': 55,
                'name': 'Onda Alta',
                'detect': lambda o, h, l, c, p, i: (
                    (h - l) > (abs(c - o)) * 3 and
                    (h - max(o, c)) > (abs(c - o)) * 1 and
                    (min(o, c) - l) > (abs(c - o)) * 1
                )
            },
            '1_umbrella': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 65,
                'name': 'Paraguas',
                'detect': lambda o, h, l, c, p, i: (
                    min(o, c) - l >= (max(o, c) - min(o, c)) * 2 and
                    h - max(o, c) <= (max(o, c) - min(o, c)) * 0.3
                )
            },
            '1_tombstone': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Lápida',
                'detect': lambda o, h, l, c, p, i: (
                    h - max(o, c) >= (max(o, c) - min(o, c)) * 2 and
                    min(o, c) - l <= (max(o, c) - min(o, c)) * 0.3
                )
            },
            '1_belt_hold_bull': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Cinturón Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    c > o and
                    (o == l or abs(o - l) <= (c - o) * 0.05) and
                    (c - o) > (h - l) * 0.7 and
                    h > c * 1.01
                )
            },
            '1_belt_hold_bear': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Cinturón Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    o > c and
                    (o == h or abs(h - o) <= (o - c) * 0.05) and
                    (o - c) > (h - l) * 0.7 and
                    l < c * 0.99
                )
            },
            '1_thrusting_bull': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 60,
                'name': 'Empuje Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    c[i] > c[i-1] and o[i] < o[i-1] and
                    c[i] < o[i-1]
                )
            },
            '1_thrusting_bear': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 60,
                'name': 'Empuje Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    c[i] < c[i-1] and o[i] > o[i-1] and
                    c[i] > o[i-1]
                )
            },
            '1_gap_up': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 55,
                'name': 'Gap Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and l[i] > h[i-1]
                )
            },
            '1_gap_down': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 55,
                'name': 'Gap Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and h[i] < l[i-1]
                )
            },
            '1_closing_marubozu_bull': {
                'type': '1',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Marubozu de Cierre Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    c == h and o > l and (c - o) > (h - l) * 0.7 and
                    (h - l) > 0
                )
            },
            '1_opening_marubozu_bear': {
                'type': '1',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Marubozu de Apertura Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    o == h and c < o and (o - c) > (h - l) * 0.7 and
                    c > l
                )
            },
            
            # ============ PATRONES DE 2 VELAS (33 COMPLETO) ============
            '2_bullish_engulfing': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Envolvente Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and
                    c[i] > o[i] and c[i-1] < o[i-1] and
                    o[i] < c[i-1] and
                    c[i] > o[i-1] and
                    h[i] > h[i-1] and
                    l[i] < l[i-1] and
                    (c[i] - o[i]) > (o[i-1] - c[i-1]) * 1.2
                )
            },
            '2_bearish_engulfing': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Envolvente Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and
                    c[i] < o[i] and c[i-1] > o[i-1] and
                    o[i] > c[i-1] and
                    c[i] < o[i-1] and
                    h[i] > h[i-1] and
                    l[i] < l[i-1] and
                    (o[i] - c[i]) > (c[i-1] - o[i-1]) * 1.2
                )
            },
            '2_bullish_engulfing_small': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Envolvente Alcista Pequeño',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    o[i] < c[i-1] and c[i] > o[i-1] and
                    (c[i] - o[i]) <= (o[i-1] - c[i-1]) * 1.5
                )
            },
            '2_bearish_engulfing_small': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Envolvente Bajista Pequeño',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    o[i] > c[i-1] and c[i] < o[i-1] and
                    (o[i] - c[i]) <= (c[i-1] - o[i-1]) * 1.5
                )
            },
            '2_bullish_harami': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Harami Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and
                    c[i] > o[i] and c[i-1] < o[i-1] and
                    o[i] > c[i-1] and
                    c[i] < o[i-1] and
                    h[i] < h[i-1] and
                    l[i] > l[i-1] and
                    (c[i] - o[i]) < (o[i-1] - c[i-1]) * 0.5
                )
            },
            '2_bearish_harami': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Harami Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and
                    c[i] < o[i] and c[i-1] > o[i-1] and
                    o[i] < c[i-1] and
                    c[i] > o[i-1] and
                    h[i] < h[i-1] and
                    l[i] > l[i-1] and
                    (o[i] - c[i]) < (c[i-1] - o[i-1]) * 0.5
                )
            },
            '2_harami_cross_bull': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Harami Cruz Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i-1] < o[i-1] and
                    abs(c[i] - o[i]) <= (h[i] - l[i]) * 0.1 and
                    o[i] > c[i-1] and c[i] < o[i-1]
                )
            },
            '2_harami_cross_bear': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Harami Cruz Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i-1] > o[i-1] and
                    abs(c[i] - o[i]) <= (h[i] - l[i]) * 0.1 and
                    o[i] < c[i-1] and c[i] > o[i-1]
                )
            },
            '2_piercing': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Línea Perforante',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    o[i] < c[i-1] and c[i] > (o[i-1] + c[i-1]) / 2 and
                    c[i] < o[i-1]
                )
            },
            '2_dark_cloud': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Nube Oscura',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    o[i] > c[i-1] and c[i] < (o[i-1] + c[i-1]) / 2 and
                    c[i] > o[i-1]
                )
            },
            '2_tweezer_top': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Pinzas en Techo',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and abs(h[i] - h[i-1]) <= (h[i] - l[i]) * 0.05 and
                    c[i] < o[i] and c[i-1] > o[i-1]
                )
            },
            '2_tweezer_bottom': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Pinzas en Suelo',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and abs(l[i] - l[i-1]) <= (h[i] - l[i]) * 0.05 and
                    c[i] > o[i] and c[i-1] < o[i-1]
                )
            },
            '2_tweezer_doji_top': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Pinzas Doji en Techo',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and abs(h[i] - h[i-1]) <= (h[i] - l[i]) * 0.05 and
                    abs(c[i] - o[i]) <= (h[i] - l[i]) * 0.1 and
                    c[i-1] > o[i-1]
                )
            },
            '2_tweezer_doji_bottom': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Pinzas Doji en Suelo',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and abs(l[i] - l[i-1]) <= (h[i] - l[i]) * 0.05 and
                    abs(c[i] - o[i]) <= (h[i] - l[i]) * 0.1 and
                    c[i-1] < o[i-1]
                )
            },
            '2_meeting_lines_bull': {
                'type': '2',
                'direction': 'neutral',
                'reliability': 60,
                'name': 'Líneas Encuentro Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    abs(c[i] - c[i-1]) <= (h[i] - l[i]) * 0.05
                )
            },
            '2_meeting_lines_bear': {
                'type': '2',
                'direction': 'neutral',
                'reliability': 60,
                'name': 'Líneas Encuentro Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    abs(c[i] - c[i-1]) <= (h[i] - l[i]) * 0.05
                )
            },
            '2_thrusting_bull': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 65,
                'name': 'Empuje Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    c[i] > c[i-1] and c[i] < (o[i-1] + c[i-1]) / 2
                )
            },
            '2_thrusting_bear': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 65,
                'name': 'Empuje Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    c[i] < c[i-1] and c[i] > (o[i-1] + c[i-1]) / 2
                )
            },
            '2_separating_lines_bull': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Líneas Separadas Alcistas',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    abs(o[i] - o[i-1]) <= (o[i] - l[i]) * 0.05
                )
            },
            '2_separating_lines_bear': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Líneas Separadas Bajistas',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    abs(o[i] - o[i-1]) <= (h[i] - o[i]) * 0.05
                )
            },
            '2_upside_gap_tasuki': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Gap Tasuki Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    l[i] > h[i-1] and o[i] < h[i-1] and c[i] > h[i-1]
                )
            },
            '2_downside_gap_tasuki': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Gap Tasuki Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    h[i] < l[i-1] and o[i] > l[i-1] and c[i] < l[i-1]
                )
            },
            '2_kissing_death': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Beso de la Muerte',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    abs(h[i] - l[i-1]) <= (h[i] - l[i]) * 0.05 and
                    c[i] < c[i-1] * 0.98
                )
            },
            '2_bullish_hug': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Abrazo Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] < o[i-1] and
                    abs(l[i] - l[i-1]) <= (h[i] - l[i]) * 0.03 and
                    o[i] > o[i-1]
                )
            },
            '2_bearish_hug': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Abrazo Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] > o[i-1] and
                    abs(h[i] - h[i-1]) <= (h[i] - l[i]) * 0.03 and
                    o[i] < o[i-1]
                )
            },
            '2_stick_sandwich_bull': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Sandwich Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and c[i] > o[i] and c[i-1] < o[i-1] and c[i-2] > o[i-2] and
                    abs(c[i] - c[i-2]) <= (h[i] - l[i]) * 0.05
                )
            },
            '2_stick_sandwich_bear': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Sandwich Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and c[i] < o[i] and c[i-1] > o[i-1] and c[i-2] < o[i-2] and
                    abs(c[i] - c[i-2]) <= (h[i] - l[i]) * 0.05
                )
            },
            '2_matching_low': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 60,
                'name': 'Mínimos Coincidentes',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] < o[i-1] and
                    abs(l[i] - l[i-1]) <= (h[i] - l[i]) * 0.03
                )
            },
            '2_matching_high': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 60,
                'name': 'Máximos Coincidentes',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] > o[i-1] and
                    abs(h[i] - h[i-1]) <= (h[i] - l[i]) * 0.03
                )
            },
            '2_side_by_side_gap_bull': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Gap Lateral Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] > o[i-1] and
                    l[i] > h[i-1] and abs(o[i] - o[i-1]) <= (o[i] - l[i]) * 0.1
                )
            },
            '2_side_by_side_gap_bear': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Gap Lateral Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] < o[i-1] and
                    h[i] < l[i-1] and abs(o[i] - o[i-1]) <= (h[i] - o[i]) * 0.1
                )
            },
            '2_on_neck': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 65,
                'name': 'En el Cuello',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] < o[i-1] and
                    abs(c[i] - l[i-1]) <= (h[i] - l[i]) * 0.05
                )
            },
            '2_on_neck_bull': {
                'type': '2',
                'direction': 'bullish',
                'reliability': 65,
                'name': 'En el Cuello Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] > o[i] and c[i-1] > o[i-1] and
                    abs(c[i] - h[i-1]) <= (h[i] - l[i]) * 0.05
                )
            },
            '2_in_neck': {
                'type': '2',
                'direction': 'bearish',
                'reliability': 60,
                'name': 'En el Cuello Interior',
                'detect': lambda o, h, l, c, p, i: (
                    i > 0 and c[i] < o[i] and c[i-1] < o[i-1] and
                    c[i] > l[i-1] and c[i] < (l[i-1] + h[i-1]) / 2
                )
            },
            
            # ============ PATRONES DE 3 VELAS (38 COMPLETO) - CON VALIDACIÓN ESTRICTA ============
            '3_morning_star': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 90,
                'name': 'Estrella Matutina',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    # Vela1: Bajista grande
                    c[i-2] < o[i-2] and
                    (o[i-2] - c[i-2]) > (h[i-2] - l[i-2]) * 0.6 and
                    # Vela2: Cuerpo pequeño (estrella)
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.3 and
                    # Vela3: Alcista grande
                    c[i] > o[i] and
                    (c[i] - o[i]) > (h[i] - l[i]) * 0.6 and
                    # GAPs
                    c[i-1] < l[i-2] and
                    c[i] > o[i-1] and
                    c[i] > (o[i-2] + c[i-2]) / 2
                )
            },
            '3_evening_star': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 90,
                'name': 'Estrella Vespertina',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    # Vela1: Alcista grande
                    c[i-2] > o[i-2] and
                    (c[i-2] - o[i-2]) > (h[i-2] - l[i-2]) * 0.6 and
                    # Vela2: Cuerpo pequeño (estrella)
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.3 and
                    # Vela3: Bajista grande
                    c[i] < o[i] and
                    (o[i] - c[i]) > (h[i] - l[i]) * 0.6 and
                    # GAPs
                    c[i-1] > h[i-2] and
                    c[i] < o[i-1] and
                    c[i] < (o[i-2] + c[i-2]) / 2
                )
            },
            '3_morning_star_doji': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 95,
                'name': 'Estrella Matutina Doji',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and
                    (c[i] - o[i]) > (h[i] - l[i]) * 0.6 and
                    c[i-2] < o[i-2] and
                    (o[i-2] - c[i-2]) > (h[i-2] - l[i-2]) * 0.6 and
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.1 and
                    c[i] > (o[i-2] + c[i-2]) / 2
                )
            },
            '3_evening_star_doji': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 95,
                'name': 'Estrella Vespertina Doji',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and
                    (o[i] - c[i]) > (h[i] - l[i]) * 0.6 and
                    c[i-2] > o[i-2] and
                    (c[i-2] - o[i-2]) > (h[i-2] - l[i-2]) * 0.6 and
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.1 and
                    c[i] < (o[i-2] + c[i-2]) / 2
                )
            },
            '3_three_white_soldiers': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Tres Soldados Blancos',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    # Las 3 velas deben ser ALCISTAS
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    # Cada vela cierra más alta que la anterior
                    c[i] > c[i-1] and c[i-1] > c[i-2] and
                    # Las aperturas están dentro del rango de la vela anterior
                    o[i] > o[i-1] and o[i] < c[i-1] and
                    o[i-1] > o[i-2] and o[i-1] < c[i-2] and
                    # Los cuerpos son grandes (>70% del rango)
                    (c[i-2] - o[i-2]) > (h[i-2] - l[i-2]) * 0.7 and
                    (c[i-1] - o[i-1]) > (h[i-1] - l[i-1]) * 0.7 and
                    (c[i] - o[i]) > (h[i] - l[i]) * 0.7 and
                    # Las mechas superiores son pequeñas
                    (h[i-2] - c[i-2]) <= (c[i-2] - o[i-2]) * 0.2 and
                    (h[i-1] - c[i-1]) <= (c[i-1] - o[i-1]) * 0.2 and
                    (h[i] - c[i]) <= (c[i] - o[i]) * 0.2 and
                    # Las mechas inferiores son pequeñas
                    (o[i-2] - l[i-2]) <= (c[i-2] - o[i-2]) * 0.2 and
                    (o[i-1] - l[i-1]) <= (c[i-1] - o[i-1]) * 0.2 and
                    (o[i] - l[i]) <= (c[i] - o[i]) * 0.2
                )
            },
            '3_three_black_crows': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 90,
                'name': 'Tres Cuervos Negros',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    # Las 3 velas deben ser BAJISTAS
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    # Cada vela cierra más baja que la anterior
                    c[i] < c[i-1] and c[i-1] < c[i-2] and
                    # Las aperturas son progresivamente más bajas
                    o[i] < o[i-1] and o[i-1] < o[i-2] and
                    # Los cuerpos son grandes (>70% del rango)
                    (o[i-2] - c[i-2]) > (h[i-2] - l[i-2]) * 0.7 and
                    (o[i-1] - c[i-1]) > (h[i-1] - l[i-1]) * 0.7 and
                    (o[i] - c[i]) > (h[i] - l[i]) * 0.7 and
                    # Las mechas superiores son pequeñas
                    (h[i-2] - o[i-2]) <= (o[i-2] - c[i-2]) * 0.2 and
                    (h[i-1] - o[i-1]) <= (o[i-1] - c[i-1]) * 0.2 and
                    (h[i] - o[i]) <= (o[i] - c[i]) * 0.2 and
                    # Las mechas inferiores son pequeñas
                    (c[i-2] - l[i-2]) <= (o[i-2] - c[i-2]) * 0.2 and
                    (c[i-1] - l[i-1]) <= (o[i-1] - c[i-1]) * 0.2 and
                    (c[i] - l[i]) <= (o[i] - c[i]) * 0.2
                )
            },
            '3_abandoned_baby_bull': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 95,
                'name': 'Bebé Abandonado Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    # Vela1: Bajista grande
                    c[i-2] < o[i-2] and
                    (o[i-2] - c[i-2]) > (h[i-2] - l[i-2]) * 0.6 and
                    # Vela2: Doji
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.05 and
                    # Vela3: Alcista grande
                    c[i] > o[i] and
                    (c[i] - o[i]) > (h[i] - l[i]) * 0.6 and
                    # GAPs en AMBOS LADOS (isla)
                    l[i-1] > h[i-2] and
                    l[i] > h[i-1] and
                    c[i] > h[i-1]
                )
            },
            '3_abandoned_baby_bear': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 95,
                'name': 'Bebé Abandonado Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    # Vela1: Alcista grande
                    c[i-2] > o[i-2] and
                    (c[i-2] - o[i-2]) > (h[i-2] - l[i-2]) * 0.6 and
                    # Vela2: Doji
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.05 and
                    # Vela3: Bajista grande
                    c[i] < o[i] and
                    (o[i] - c[i]) > (h[i] - l[i]) * 0.6 and
                    # GAPs en AMBOS LADOS (isla)
                    h[i-1] < l[i-2] and
                    h[i] < l[i-1] and
                    c[i] < l[i-1]
                )
            },
            '3_deliberation_bull': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Deliberación Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    c[i] > c[i-1] and c[i-1] > c[i-2] and
                    abs(c[i] - o[i]) < abs(c[i-1] - o[i-1]) and
                    (h[i] - c[i]) > (c[i] - o[i]) * 0.5
                )
            },
            '3_deliberation_bear': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Deliberación Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    c[i] < c[i-1] and c[i-1] < c[i-2] and
                    abs(o[i] - c[i]) < abs(o[i-1] - c[i-1]) and
                    (c[i] - l[i]) > (o[i] - c[i]) * 0.5
                )
            },
            '3_advance_block': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Bloque de Avance',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    c[i] > c[i-1] and c[i-1] > c[i-2] and
                    (h[i] - c[i]) > (c[i] - o[i]) * 0.7 and
                    (h[i-1] - c[i-1]) > (c[i-1] - o[i-1]) * 0.5
                )
            },
            '3_stalled_pattern': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Patrón Estancado',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    c[i] > c[i-1] and c[i-1] > c[i-2] and
                    abs(c[i] - o[i]) < abs(c[i-1] - o[i-1]) * 0.7 and
                    o[i] > c[i-1]
                )
            },
            '3_three_inside_up': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Tres Interiores Arriba',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] < o[i-2] and
                    o[i-1] > c[i-2] and c[i-1] < o[i-2] and
                    c[i] > o[i-2]
                )
            },
            '3_three_inside_down': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Tres Interiores Abajo',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] > o[i-2] and
                    o[i-1] < c[i-2] and c[i-1] > o[i-2] and
                    c[i] < o[i-2]
                )
            },
            '3_three_outside_up': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Tres Exteriores Arriba',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] < o[i-2] and
                    o[i-1] < c[i-2] and c[i-1] > o[i-2] and
                    c[i] > c[i-1]
                )
            },
            '3_three_outside_down': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Tres Exteriores Abajo',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] > o[i-2] and
                    o[i-1] > c[i-2] and c[i-1] < o[i-2] and
                    c[i] < c[i-1]
                )
            },
            '3_three_stars_south': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Tres Estrellas en el Sur',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    c[i] > c[i-1] and c[i-1] > c[i-2] and
                    l[i] > l[i-1] and l[i-1] > l[i-2] and
                    abs(c[i-1] - o[i-1]) <= (h[i-1] - l[i-1]) * 0.2
                )
            },
            '3_three_mountains': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Tres Montañas',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and 
                    abs(h[i] - h[i-2]) <= (h[i] - l[i]) * 0.03 and
                    h[i] <= h[i-1] and h[i-2] <= h[i-1] and
                    c[i] < o[i] and c[i-2] < o[i-2]
                )
            },
            '3_three_rivers': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Tres Ríos',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    l[i] < l[i-1] and l[i-1] < l[i-2] and
                    c[i] > (o[i-1] + c[i-1]) / 2
                )
            },
            '3_counterattack_bull': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Contraataque Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    c[i] > c[i-2] and abs(c[i] - c[i-2]) <= (h[i] - l[i]) * 0.05 and
                    c[i-1] < c[i-2]
                )
            },
            '3_counterattack_bear': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Contraataque Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    c[i] < c[i-2] and abs(c[i] - c[i-2]) <= (h[i] - l[i]) * 0.05 and
                    c[i-1] > c[i-2]
                )
            },
            '3_three_method_advance': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Avance de Tres Métodos',
                'detect': lambda o, h, l, c, p, i: (
                    i > 3 and
                    c[i] > o[i] and
                    c[i-1] < o[i-1] and c[i-2] < o[i-2] and c[i-3] < o[i-3] and
                    c[i-3] > o[i-3] and
                    c[i] > h[i-3] and
                    c[i-1] > l[i-3] and c[i-2] > l[i-3] and
                    c[i-1] < o[i-3] and c[i-2] < o[i-3]
                )
            },
            '3_three_method_decline': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Retroceso de Tres Métodos',
                'detect': lambda o, h, l, c, p, i: (
                    i > 3 and
                    c[i] < o[i] and
                    c[i-1] > o[i-1] and c[i-2] > o[i-2] and c[i-3] > o[i-3] and
                    c[i-3] < o[i-3] and
                    c[i] < l[i-3] and
                    c[i-1] < h[i-3] and c[i-2] < h[i-3] and
                    c[i-1] > o[i-3] and c[i-2] > o[i-3]
                )
            },
            '3_upside_tasuki_gap': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Gap Tasuki Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    l[i-1] > h[i-2] and l[i] > h[i-1] and
                    o[i] < c[i-1] and c[i] > o[i-1]
                )
            },
            '3_downside_tasuki_gap': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Gap Tasuki Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    h[i-1] < l[i-2] and h[i] < l[i-1] and
                    o[i] > c[i-1] and c[i] < o[i-1]
                )
            },
            '3_concealing_baby_swallow': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Bebé Golondrina Oculto',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    c[i-1] < l[i-2] and o[i-1] < l[i-2] and
                    c[i] > l[i-2] and o[i] < l[i-1] and
                    (o[i-1] - c[i-1]) > (h[i-1] - l[i-1]) * 0.8
                )
            },
            '3_identical_three_crows': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Tres Cuervos Idénticos',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    abs(o[i] - o[i-1]) <= (o[i] - c[i]) * 0.1 and
                    abs(o[i-1] - o[i-2]) <= (o[i-1] - c[i-1]) * 0.1 and
                    abs(c[i] - c[i-1]) <= (o[i] - c[i]) * 0.1
                )
            },
            '3_three_line_strike_bull': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Golpe de Tres Líneas Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    c[i-3] < o[i-3] and c[i] < l[i-3] and
                    o[i] > h[i-3]
                )
            },
            '3_three_line_strike_bear': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Golpe de Tres Líneas Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    c[i-3] > o[i-3] and c[i] > h[i-3] and
                    o[i] < l[i-3]
                )
            },
            '3_breakaway_bull': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Escape Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 3 and
                    c[i] > o[i] and c[i-1] < o[i-1] and
                    h[i-1] < l[i-3] and c[i] > h[i-3] and
                    c[i-2] < o[i-2] and c[i-3] < o[i-3]
                )
            },
            '3_breakaway_bear': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Escape Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 3 and
                    c[i] < o[i] and c[i-1] > o[i-1] and
                    l[i-1] > h[i-3] and c[i] < l[i-3] and
                    c[i-2] > o[i-2] and c[i-3] > o[i-3]
                )
            },
            '3_ladder_bottom': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Fondo de Escalera',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] > o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    c[i-3] < o[i-3] and c[i-1] < c[i-2] and c[i-2] < c[i-3] and
                    c[i] > c[i-1] and (h[i] - l[i]) > (h[i-1] - l[i-1]) * 1.5
                )
            },
            '3_ladder_top': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Techo de Escalera',
                'detect': lambda o, h, l, c, p, i: (
                    i > 2 and
                    c[i] < o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    c[i-3] > o[i-3] and c[i-1] > c[i-2] and c[i-2] > c[i-3] and
                    c[i] < c[i-1] and (h[i] - l[i]) > (h[i-1] - l[i-1]) * 1.5
                )
            },
            '3_tasuki_bridge_bull': {
                'type': '3',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Puente Tasuki Alcista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2] and
                    l[i-1] > h[i-2] and c[i] < o[i-1] and c[i] > l[i-1]
                )
            },
            '3_tasuki_bridge_bear': {
                'type': '3',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Puente Tasuki Bajista',
                'detect': lambda o, h, l, c, p, i: (
                    i > 1 and
                    c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2] and
                    h[i-1] < l[i-2] and c[i] > o[i-1] and c[i] < h[i-1]
                )
            },
            
            # ============ PATRONES DE 4+ VELAS (48 COMPLETO) ============
            '4_bull_flag': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Bandera Alcista',
                'detect': self._detect_bull_flag
            },
            '4_bear_flag': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Bandera Bajista',
                'detect': self._detect_bear_flag
            },
            '4_bull_pennant': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Banderín Alcista',
                'detect': self._detect_bull_pennant
            },
            '4_bear_pennant': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Banderín Bajista',
                'detect': self._detect_bear_pennant
            },
            '4_ascending_triangle': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Triángulo Ascendente',
                'detect': self._detect_ascending_triangle
            },
            '4_descending_triangle': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Triángulo Descendente',
                'detect': self._detect_descending_triangle
            },
            '4_symmetrical_triangle': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 70,
                'name': 'Triángulo Simétrico',
                'detect': self._detect_symmetrical_triangle
            },
            '4_ascending_triangle_breakout': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 90,
                'name': 'Triángulo Ascendente Rotura',
                'detect': self._detect_ascending_triangle_breakout
            },
            '4_descending_triangle_breakdown': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 90,
                'name': 'Triángulo Descendente Ruptura',
                'detect': self._detect_descending_triangle_breakdown
            },
            '4_symmetrical_triangle_breakout': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Triángulo Simétrico Rotura Alcista',
                'detect': self._detect_symmetrical_triangle_breakout
            },
            '4_symmetrical_triangle_breakdown': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Triángulo Simétrico Ruptura Bajista',
                'detect': self._detect_symmetrical_triangle_breakdown
            },
            '4_wedge_bull': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 80,
                'name': 'Cuña Alcista',
                'detect': self._detect_bullish_wedge
            },
            '4_wedge_bear': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 80,
                'name': 'Cuña Bajista',
                'detect': self._detect_bearish_wedge
            },
            '4_falling_wedge': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Cuña Descendente',
                'detect': self._detect_falling_wedge
            },
            '4_rising_wedge': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Cuña Ascendente',
                'detect': self._detect_rising_wedge
            },
            '4_double_bottom': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 90,
                'name': 'Doble Suelo',
                'detect': self._detect_double_bottom
            },
            '4_double_top': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 90,
                'name': 'Doble Techo',
                'detect': self._detect_double_top
            },
            '4_double_bottom_breakout': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 95,
                'name': 'Doble Suelo Confirmado',
                'detect': self._detect_double_bottom_breakout
            },
            '4_double_top_breakdown': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 95,
                'name': 'Doble Techo Confirmado',
                'detect': self._detect_double_top_breakdown
            },
            '4_triple_bottom': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 95,
                'name': 'Triple Suelo',
                'detect': self._detect_triple_bottom
            },
            '4_triple_top': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 95,
                'name': 'Triple Techo',
                'detect': self._detect_triple_top
            },
            '4_head_shoulders': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 95,
                'name': 'Hombro Cabeza Hombro',
                'detect': self._detect_head_shoulders
            },
            '4_inverse_head_shoulders': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 95,
                'name': 'HCH Invertido',
                'detect': self._detect_inverse_head_shoulders
            },
            '4_head_shoulders_breakdown': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 98,
                'name': 'HCH Confirmado',
                'detect': self._detect_head_shoulders_breakdown
            },
            '4_inverse_head_shoulders_breakout': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 98,
                'name': 'HCH Invertido Confirmado',
                'detect': self._detect_inverse_head_shoulders_breakout
            },
            '4_rounded_bottom': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Fondo Redondeado',
                'detect': self._detect_rounded_bottom
            },
            '4_rounded_top': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Techo Redondeado',
                'detect': self._detect_rounded_top
            },
            '4_cup_handle': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 90,
                'name': 'Taza con Asa',
                'detect': self._detect_cup_handle
            },
            '4_cup_handle_breakout': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 95,
                'name': 'Taza con Asa Rotura',
                'detect': self._detect_cup_handle_breakout
            },
            '4_reversal_island_bull': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 85,
                'name': 'Isla de Reversión Alcista',
                'detect': self._detect_reversal_island_bull
            },
            '4_reversal_island_bear': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 85,
                'name': 'Isla de Reversión Bajista',
                'detect': self._detect_reversal_island_bear
            },
            '4_exhaustion_gap': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 70,
                'name': 'Gap de Agotamiento',
                'detect': self._detect_exhaustion_gap
            },
            '4_runaway_gap': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 75,
                'name': 'Gap de Continuación',
                'detect': self._detect_runaway_gap
            },
            '4_breakaway_gap': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 80,
                'name': 'Gap de Ruptura',
                'detect': self._detect_breakaway_gap
            },
            '4_window_opening': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 60,
                'name': 'Ventana Abierta',
                'detect': self._detect_window_opening
            },
            '4_three_gaps': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 70,
                'name': 'Tres Gaps',
                'detect': self._detect_three_gaps
            },
            '4_measuring_gap': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 65,
                'name': 'Gap de Medición',
                'detect': self._detect_measuring_gap
            },
            '4_continuation_gap': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 70,
                'name': 'Gap de Continuación',
                'detect': self._detect_continuation_gap  # <-- DEBE COINCIDIR
            },
            '4_key_reversal_day_bull': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 75,
                'name': 'Día Clave de Reversión Alcista',
                'detect': self._detect_key_reversal_day_bull
            },
            '4_key_reversal_day_bear': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 75,
                'name': 'Día Clave de Reversión Bajista',
                'detect': self._detect_key_reversal_day_bear
            },
            '4_wide_ranging_day': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 60,
                'name': 'Día de Amplio Rango',
                'detect': self._detect_wide_ranging_day
            },
            '4_narrow_ranging_day': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 55,
                'name': 'Día de Estrecho Rango',
                'detect': self._detect_narrow_ranging_day
            },
            '4_inside_day': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 50,
                'name': 'Día Interior',
                'detect': self._detect_inside_day
            },
            '4_outside_day': {
                'type': '4+',
                'direction': 'neutral',
                'reliability': 55,
                'name': 'Día Exterior',
                'detect': self._detect_outside_day
            },
            '4_high_price_gapping_day': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 65,
                'name': 'Día de Gap Alcista',
                'detect': self._detect_high_price_gapping_day
            },
            '4_low_price_gapping_day': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 65,
                'name': 'Día de Gap Bajista',
                'detect': self._detect_low_price_gapping_day
            },
            '4_closing_price_reversal_bull': {
                'type': '4+',
                'direction': 'bullish',
                'reliability': 70,
                'name': 'Reversión de Cierre Alcista',
                'detect': self._detect_closing_price_reversal_bull
            },
            '4_closing_price_reversal_bear': {
                'type': '4+',
                'direction': 'bearish',
                'reliability': 70,
                'name': 'Reversión de Cierre Bajista',
                'detect': self._detect_closing_price_reversal_bear
            }
        }
    # === FIN _initialize_pattern_database ===
    
    # ========================================================================
    # FUNCIONES DE DETECCIÓN PARA PATRONES COMPLEJOS (CHARTISTAS)
    # ========================================================================
    
    def _detect_bull_flag(self, o, h, l, c, p, i):
        """Detectar bandera alcista"""
        try:
            if i < 15:
                return False
            # Asta de la bandera (movimiento fuerte)
            pole_high = max(h[i-10:i-4]) if i-4 > i-10 else 0
            pole_low = min(l[i-10:i-4]) if i-4 > i-10 else 0
            pole_height = pole_high - pole_low
            
            # Banderín (consolidación)
            flag_high = max(h[i-5:i])
            flag_low = min(l[i-5:i])
            flag_height = flag_high - flag_low
            
            # Verificar que el asta sea al menos 2 veces más grande que el banderín
            # y que el banderín sea pequeño (menos del 30% del asta)
            return (pole_height > flag_height * 2 and 
                    flag_height < pole_height * 0.3 and
                    c[i] > flag_high * 0.98)  # Precio cerca de la parte superior
        except:
            return False
    
    def _detect_bear_flag(self, o, h, l, c, p, i):
        """Detectar bandera bajista"""
        try:
            if i < 15:
                return False
            # Asta de la bandera (movimiento fuerte)
            pole_high = max(h[i-10:i-4])
            pole_low = min(l[i-10:i-4])
            pole_height = pole_high - pole_low
            
            # Banderín (consolidación)
            flag_high = max(h[i-5:i])
            flag_low = min(l[i-5:i])
            flag_height = flag_high - flag_low
            
            # Verificar el asta y banderín
            return (pole_height > flag_height * 2 and 
                    flag_height < pole_height * 0.3 and 
                    c[i] < flag_low * 1.02 and  # Precio cerca de la parte inferior
                    c[i] < c[i-5])  # Tendencia bajista general
        except:
            return False
    
    def _detect_bull_pennant(self, o, h, l, c, p, i):
        """Detectar banderín alcista"""
        try:
            if i < 20:
                return False
            
            # Asta: movimiento alcista fuerte
            pole_start = max(10, i - 15)
            pole_high = max(h[pole_start:i-5])
            pole_low = min(l[pole_start:i-5])
            pole_height = pole_high - pole_low
            
            # Banderín: consolidación triangular (convergencia)
            pennant_highs = h[i-8:i]
            pennant_lows = l[i-8:i]
            
            if len(pennant_highs) < 5 or len(pennant_lows) < 5:
                return False
            
            # Verificar que los máximos sean decrecientes y mínimos crecientes
            highs_decreasing = all(pennant_highs[j] <= pennant_highs[j-1] for j in range(1, len(pennant_highs)))
            lows_increasing = all(pennant_lows[j] >= pennant_lows[j-1] for j in range(1, len(pennant_lows)))
            
            pennant_height = max(pennant_highs) - min(pennant_lows)
            
            return (pole_height > pennant_height * 2 and 
                    highs_decreasing and lows_increasing and
                    c[i] > pennant_highs[-2] and  # Ruptura
                    pole_high > c[i] * 1.05)  # El asta fue más alto
        except:
            return False
    
    def _detect_bear_pennant(self, o, h, l, c, p, i):
        """Detectar banderín bajista"""
        try:
            if i < 20:
                return False
            
            pole_start = max(10, i - 15)
            pole_high = max(h[pole_start:i-5])
            pole_low = min(l[pole_start:i-5])
            pole_height = pole_high - pole_low
            
            pennant_highs = h[i-8:i]
            pennant_lows = l[i-8:i]
            
            if len(pennant_highs) < 5 or len(pennant_lows) < 5:
                return False
            
            highs_decreasing = all(pennant_highs[j] <= pennant_highs[j-1] for j in range(1, len(pennant_highs)))
            lows_increasing = all(pennant_lows[j] >= pennant_lows[j-1] for j in range(1, len(pennant_lows)))
            
            pennant_height = max(pennant_highs) - min(pennant_lows)
            
            return (pole_height > pennant_height * 2 and 
                    highs_decreasing and lows_increasing and
                    c[i] < pennant_lows[-2] and  # Ruptura a la baja
                    pole_low < c[i] * 0.95)  # El asta fue más bajo
        except:
            return False
    
    def _detect_ascending_triangle(self, o, h, l, c, p, i):
        """Detectar triángulo ascendente (alcista)"""
        try:
            if i < 10:
                return False
            
            # Resistencia horizontal (techo plano)
            resistance = max(h[i-10:i])
            
            # Soportes ascendentes
            support_line = [l[j] for j in range(i-10, i)]
            if len(support_line) < 5:
                return False
            
            # Verificar que los soportes sean ascendentes
            support_rising = True
            for j in range(1, len(support_line)):
                if support_line[j] < support_line[j-1] * 0.99:
                    support_rising = False
                    break
            
            # Contar toques de resistencia
            touches = 0
            for j in range(i-10, i):
                if abs(h[j] - resistance) / resistance < 0.01:
                    touches += 1
            
            return (touches >= 2 and support_rising)
        except:
            return False
    
    def _detect_descending_triangle(self, o, h, l, c, p, i):
        """Detectar triángulo descendente (bajista)"""
        try:
            if i < 10:
                return False
            
            # Soporte horizontal
            support = min(l[i-10:i])
            
            # Resistencias descendentes
            resistance_line = [h[j] for j in range(i-10, i)]
            if len(resistance_line) < 5:
                return False
            
            # Verificar que las resistencias sean descendentes
            resistance_falling = True
            for j in range(1, len(resistance_line)):
                if resistance_line[j] > resistance_line[j-1] * 1.01:
                    resistance_falling = False
                    break
            
            # Contar toques de soporte
            touches = 0
            for j in range(i-10, i):
                if abs(l[j] - support) / support < 0.01:
                    touches += 1
            
            return (touches >= 2 and resistance_falling)
        except:
            return False

    def _detect_ascending_triangle_breakout(self, o, h, l, c, p, i):
        """Detectar triángulo ascendente con ruptura alcista"""
        try:
            if i < 15:
                return False
            
            resistance = max(h[i-15:i-2])
            touches = 0
            for j in range(i-15, i-2):
                if abs(h[j] - resistance) / resistance < 0.01:
                    touches += 1
            
            support_line = [l[j] for j in range(i-15, i-2)]
            support_rising = all(support_line[j] >= support_line[j-1] * 0.99 for j in range(1, len(support_line)))
            
            return (touches >= 2 and support_rising and 
                    c[i] > resistance * 1.01 and 
                    h[i] > resistance * 1.02)
        except:
            return False
    
    def _detect_descending_triangle_breakdown(self, o, h, l, c, p, i):
        """Detectar triángulo descendente con ruptura bajista"""
        try:
            if i < 15:
                return False
            
            support = min(l[i-15:i-2])
            touches = 0
            for j in range(i-15, i-2):
                if abs(l[j] - support) / support < 0.01:
                    touches += 1
            
            resistance_line = [h[j] for j in range(i-15, i-2)]
            resistance_falling = all(resistance_line[j] <= resistance_line[j-1] * 1.01 for j in range(1, len(resistance_line)))
            
            return (touches >= 2 and resistance_falling and 
                    c[i] < support * 0.99 and 
                    l[i] < support * 0.98)
        except:
            return False
    
    def _detect_symmetrical_triangle(self, o, h, l, c, p, i):
        """Detectar triángulo simétrico"""
        try:
            if i < 12:
                return False
            
            highs = [h[j] for j in range(i-12, i)]
            lows = [l[j] for j in range(i-12, i)]
            
            # Calcular pendientes
            high_slope = (highs[-1] - highs[0]) / len(highs) if len(highs) > 0 else 0
            low_slope = (lows[-1] - lows[0]) / len(lows) if len(lows) > 0 else 0
            
            # Máximos descendentes, mínimos ascendentes
            return (high_slope < 0 and low_slope > 0 and abs(high_slope) > abs(low_slope) * 0.5)
        except:
            return False

    def _detect_symmetrical_triangle_breakout(self, o, h, l, c, p, i):
        """Detectar triángulo simétrico con ruptura alcista"""
        try:
            if i < 20:
                return False
            
            window = 20
            highs = h[i-window:i-3]
            lows = l[i-window:i-3]
            
            high_slope = (highs[-1] - highs[0]) / len(highs) if len(highs) > 0 else 0
            low_slope = (lows[-1] - lows[0]) / len(lows) if len(lows) > 0 else 0
            
            triangle = (high_slope < 0 and low_slope > 0)
            apex = (highs[-1] + lows[-1]) / 2
            
            return (triangle and c[i] > apex * 1.03 and h[i] > max(highs) * 1.01)
        except:
            return False
    
    def _detect_symmetrical_triangle_breakdown(self, o, h, l, c, p, i):
        """Detectar triángulo simétrico con ruptura bajista"""
        try:
            if i < 20:
                return False
            
            window = 20
            highs = h[i-window:i-3]
            lows = l[i-window:i-3]
            
            high_slope = (highs[-1] - highs[0]) / len(highs) if len(highs) > 0 else 0
            low_slope = (lows[-1] - lows[0]) / len(lows) if len(lows) > 0 else 0
            
            triangle = (high_slope < 0 and low_slope > 0)
            apex = (highs[-1] + lows[-1]) / 2
            
            return (triangle and c[i] < apex * 0.97 and l[i] < min(lows) * 0.99)
        except:
            return False
    
    def _detect_bullish_wedge(self, o, h, l, c, p, i):
        """Detectar cuña alcista (fallida - realmente bajista)"""
        try:
            if i < 12:
                return False
            
            highs = [h[j] for j in range(i-12, i)]
            lows = [l[j] for j in range(i-12, i)]
            
            high_slope = (highs[-1] - highs[0]) / len(highs)
            low_slope = (lows[-1] - lows[0]) / len(lows)
            
            # Cuña ascendente: ambos techos y suelos suben, pero los techos suben más
            return (high_slope > 0 and low_slope > 0 and high_slope > low_slope)
        except:
            return False
    
    def _detect_bearish_wedge(self, o, h, l, c, p, i):
        """Detectar cuña bajista (fallida - realmente alcista)"""
        try:
            if i < 12:
                return False
            
            highs = [h[j] for j in range(i-12, i)]
            lows = [l[j] for j in range(i-12, i)]
            
            high_slope = (highs[-1] - highs[0]) / len(highs)
            low_slope = (lows[-1] - lows[0]) / len(lows)
            
            # Cuña descendente: ambos techos y suelos bajan, pero los suelos bajan más
            return (high_slope < 0 and low_slope < 0 and abs(low_slope) > abs(high_slope))
        except:
            return False
    
    def _detect_falling_wedge(self, o, h, l, c, p, i):
        """Detectar cuña descendente (alcista - reversión)"""
        try:
            if i < 15:
                return False
            
            window = 15
            highs = h[i-window:i]
            lows = l[i-window:i]
            
            if len(highs) < 10 or len(lows) < 10:
                return False
            
            high_slope = (highs[-1] - highs[0]) / len(highs)
            low_slope = (lows[-1] - lows[0]) / len(lows)
            
            # Ambos techos y suelos bajan, pero los techos bajan más rápido
            return (high_slope < 0 and low_slope < 0 and 
                    abs(high_slope) > abs(low_slope) and
                    c[i] > highs[-1] * 0.98)  # Precio cerca del techo de la cuña
        except:
            return False
    
    def _detect_rising_wedge(self, o, h, l, c, p, i):
        """Detectar cuña ascendente (bajista - reversión)"""
        try:
            if i < 15:
                return False
            
            window = 15
            highs = h[i-window:i]
            lows = l[i-window:i]
            
            if len(highs) < 10 or len(lows) < 10:
                return False
            
            high_slope = (highs[-1] - highs[0]) / len(highs)
            low_slope = (lows[-1] - lows[0]) / len(lows)
            
            # Ambos techos y suelos suben, pero los suelos suben más rápido
            return (high_slope > 0 and low_slope > 0 and 
                    abs(low_slope) > abs(high_slope) and
                    c[i] < lows[-1] * 1.02)  # Precio cerca del suelo de la cuña
        except:
            return False
    
    def _detect_double_bottom(self, o, h, l, c, p, i):
        """Detectar doble suelo"""
        try:
            if i < 20:
                return False
            
            lows_20 = l[i-20:i]
            
            # Encontrar los dos mínimos más bajos
            first_bottom_idx = np.argmin(lows_20[:10]) if len(lows_20[:10]) > 0 else -1
            second_bottom_idx = 10 + np.argmin(lows_20[10:]) if len(lows_20[10:]) > 0 else -1
            
            if first_bottom_idx == -1 or second_bottom_idx == -1:
                return False
            
            first_bottom = lows_20[first_bottom_idx]
            second_bottom = lows_20[second_bottom_idx]
            
            # Punto medio (resistencia)
            middle_high = max(h[i-15:i-5]) if i-5 > i-15 else 0
            
            # Los dos suelos deben estar cerca (menos de 3% de diferencia)
            # y el precio debe estar rompiendo la resistencia media
            return (abs(first_bottom - second_bottom) / first_bottom < 0.03 and 
                    middle_high > first_bottom * 1.05 and 
                    c[i] > middle_high * 0.95)
        except:
            return False

    def _detect_double_bottom_breakout(self, o, h, l, c, p, i):
        """Detectar doble suelo con ruptura confirmada"""
        try:
            if i < 25:
                return False
            
            lows_25 = l[i-25:i]
            
            bottom1_idx = np.argmin(lows_25[:12]) if len(lows_25[:12]) > 0 else -1
            bottom2_idx = 12 + np.argmin(lows_25[12:]) if len(lows_25[12:]) > 0 else -1
            
            if bottom1_idx == -1 or bottom2_idx == -1:
                return False
            
            bottom1 = lows_25[bottom1_idx]
            bottom2 = lows_25[bottom2_idx]
            
            # Neckline (máximo entre los dos suelos)
            neckline = max(h[i-20:i-5])
            
            return (abs(bottom1 - bottom2) / bottom1 < 0.03 and
                    neckline > bottom1 * 1.05 and
                    c[i] > neckline * 1.02)  # Ruptura confirmada
        except:
            return False
    
    def _detect_double_top(self, o, h, l, c, p, i):
        """Detectar doble techo"""
        try:
            if i < 20:
                return False
            
            highs_20 = h[i-20:i]
            
            first_top_idx = np.argmax(highs_20[:10]) if len(highs_20[:10]) > 0 else -1
            second_top_idx = 10 + np.argmax(highs_20[10:]) if len(highs_20[10:]) > 0 else -1
            
            if first_top_idx == -1 or second_top_idx == -1:
                return False
            
            first_top = highs_20[first_top_idx]
            second_top = highs_20[second_top_idx]
            
            # Punto medio (soporte)
            middle_low = min(l[i-15:i-5]) if i-5 > i-15 else 0
            
            return (abs(first_top - second_top) / first_top < 0.03 and 
                    middle_low < first_top * 0.95 and 
                    c[i] < middle_low * 1.05)
        except:
            return False

    def _detect_double_top_breakdown(self, o, h, l, c, p, i):
        """Detectar doble techo con ruptura confirmada"""
        try:
            if i < 25:
                return False
            
            highs_25 = h[i-25:i]
            
            top1_idx = np.argmax(highs_25[:12]) if len(highs_25[:12]) > 0 else -1
            top2_idx = 12 + np.argmax(highs_25[12:]) if len(highs_25[12:]) > 0 else -1
            
            if top1_idx == -1 or top2_idx == -1:
                return False
            
            top1 = highs_25[top1_idx]
            top2 = highs_25[top2_idx]
            
            # Neckline (mínimo entre los dos techos)
            neckline = min(l[i-20:i-5])
            
            return (abs(top1 - top2) / top1 < 0.03 and
                    neckline < top1 * 0.95 and
                    c[i] < neckline * 0.98)  # Ruptura confirmada
        except:
            return False

    def _detect_triple_bottom(self, o, h, l, c, p, i):
        """Detectar triple suelo"""
        try:
            if i < 35:
                return False
            
            lows_35 = l[i-35:i]
            
            # Encontrar mínimos locales
            bottoms = []
            for j in range(5, len(lows_35)-5):
                if lows_35[j] == min(lows_35[j-5:j+6]):
                    bottoms.append(lows_35[j])
            
            if len(bottoms) < 3:
                return False
            
            # Tomar los 3 mínimos más significativos
            bottoms = sorted(bottoms)[-3:]
            spread = (max(bottoms) - min(bottoms)) / min(bottoms)
            
            # Neckline
            neckline = max(h[i-25:i-5])
            
            return (spread < 0.05 and
                    len(bottoms) >= 3 and
                    c[i] > neckline * 0.98 and
                    c[i-1] < neckline)
        except:
            return False
    
    def _detect_triple_top(self, o, h, l, c, p, i):
        """Detectar triple techo"""
        try:
            if i < 35:
                return False
            
            highs_35 = h[i-35:i]
            
            # Encontrar máximos locales
            tops = []
            for j in range(5, len(highs_35)-5):
                if highs_35[j] == max(highs_35[j-5:j+6]):
                    tops.append(highs_35[j])
            
            if len(tops) < 3:
                return False
            
            tops = sorted(tops)[-3:]
            spread = (max(tops) - min(tops)) / min(tops)
            
            neckline = min(l[i-25:i-5])
            
            return (spread < 0.05 and
                    len(tops) >= 3 and
                    c[i] < neckline * 1.02 and
                    c[i-1] > neckline)
        except:
            return False

    def _detect_head_shoulders(self, o, h, l, c, p, i):
        """Detectar hombro cabeza hombro (HCH)"""
        try:
            if i < 50:
                return False
            
            window = 50
            highs = h[i-window:i]
            
            # Buscar máximos locales
            peaks = []
            for j in range(10, len(highs)-10):
                if highs[j] == max(highs[j-5:j+6]):
                    peaks.append((j, highs[j]))
            
            if len(peaks) < 3:
                return False
            
            # Últimos 3 picos
            peaks = peaks[-3:]
            left_shoulder, head, right_shoulder = peaks[0][1], peaks[1][1], peaks[2][1]
            
            # Verificar que la cabeza sea más alta
            if head <= left_shoulder or head <= right_shoulder:
                return False
            
            # Verificar simetría (hombros similares)
            shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder
            if shoulder_diff > 0.05:
                return False
            
            # Verificar que el derecho no sea más alto que el izquierdo
            if right_shoulder > left_shoulder * 1.01:
                return False
            
            # Encontrar neckline (mínimos entre picos)
            left_neck = min(l[peaks[0][0]:peaks[1][0]])
            right_neck = min(l[peaks[1][0]:peaks[2][0]])
            neckline = (left_neck + right_neck) / 2
            
            # Verificar ruptura
            return (c[i] < neckline * 0.99 and
                    l[i] < neckline * 0.98)
        except:
            return False
    
    def _detect_inverse_head_shoulders(self, o, h, l, c, p, i):
        """Detectar hombro cabeza hombro invertido"""
        try:
            if i < 50:
                return False
            
            window = 50
            lows = l[i-window:i]
            
            # Buscar mínimos locales
            troughs = []
            for j in range(10, len(lows)-10):
                if lows[j] == min(lows[j-5:j+6]):
                    troughs.append((j, lows[j]))
            
            if len(troughs) < 3:
                return False
            
            # Últimos 3 mínimos
            troughs = troughs[-3:]
            left_shoulder, head, right_shoulder = troughs[0][1], troughs[1][1], troughs[2][1]
            
            # Verificar que la cabeza sea más baja
            if head >= left_shoulder or head >= right_shoulder:
                return False
            
            # Verificar simetría
            shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder
            if shoulder_diff > 0.05:
                return False
            
            # Verificar que el derecho no sea más bajo que el izquierdo
            if right_shoulder < left_shoulder * 0.99:
                return False
            
            # Encontrar neckline (máximos entre mínimos)
            left_neck = max(h[troughs[0][0]:troughs[1][0]])
            right_neck = max(h[troughs[1][0]:troughs[2][0]])
            neckline = (left_neck + right_neck) / 2
            
            # Verificar ruptura
            return (c[i] > neckline * 1.01 and
                    h[i] > neckline * 1.02)
        except:
            return False

    def _detect_head_shoulders_breakdown(self, o, h, l, c, p, i):
        """Detectar HCH con ruptura confirmada"""
        try:
            if i < 45:
                return False
            
            window = 45
            highs = h[i-window:i-5]
            lows = l[i-window:i-5]
            
            left_shoulder_idx = np.argmax(highs[:15]) if len(highs[:15]) > 0 else -1
            head_idx = 15 + np.argmax(highs[15:25]) if len(highs[15:25]) > 0 else -1
            right_shoulder_idx = 25 + np.argmax(highs[25:35]) if len(highs[25:35]) > 0 else -1
            
            if left_shoulder_idx == -1 or head_idx == -1 or right_shoulder_idx == -1:
                return False
            
            neckline_left = min(l[left_shoulder_idx:head_idx])
            neckline_right = min(l[head_idx:right_shoulder_idx])
            neckline = (neckline_left + neckline_right) / 2
            
            return (c[i] < neckline * 0.97 and
                    l[i] < neckline * 0.96)
        except:
            return False
    
    def _detect_inverse_head_shoulders_breakout(self, o, h, l, c, p, i):
        """Detectar HCH invertido con ruptura confirmada"""
        try:
            if i < 45:
                return False
            
            window = 45
            highs = h[i-window:i-5]
            lows = l[i-window:i-5]
            
            left_shoulder_idx = np.argmin(lows[:15]) if len(lows[:15]) > 0 else -1
            head_idx = 15 + np.argmin(lows[15:25]) if len(lows[15:25]) > 0 else -1
            right_shoulder_idx = 25 + np.argmin(lows[25:35]) if len(lows[25:35]) > 0 else -1
            
            if left_shoulder_idx == -1 or head_idx == -1 or right_shoulder_idx == -1:
                return False
            
            neckline_left = max(h[left_shoulder_idx:head_idx])
            neckline_right = max(h[head_idx:right_shoulder_idx])
            neckline = (neckline_left + neckline_right) / 2
            
            return (c[i] > neckline * 1.03 and
                    h[i] > neckline * 1.04)
        except:
            return False

    def _detect_rounded_bottom(self, o, h, l, c, p, i):
        """Detectar fondo redondeado"""
        try:
            if i < 30:
                return False
            
            window = 30
            closes = c[i-window:i]
            
            left_avg = np.mean(closes[:10]) if len(closes[:10]) > 0 else 0
            mid_avg = np.mean(closes[10:20]) if len(closes[10:20]) > 0 else 0
            right_avg = np.mean(closes[20:30]) if len(closes[20:30]) > 0 else 0
            
            # Forma de U: izquierda y derecha más altas que el medio
            return (left_avg > mid_avg and
                    right_avg > mid_avg and
                    abs(left_avg - right_avg) / left_avg < 0.1 and
                    c[i] > right_avg * 1.01)
        except:
            return False
    
    def _detect_rounded_top(self, o, h, l, c, p, i):
        """Detectar techo redondeado"""
        try:
            if i < 30:
                return False
            
            window = 30
            closes = c[i-window:i]
            
            left_avg = np.mean(closes[:10]) if len(closes[:10]) > 0 else 0
            mid_avg = np.mean(closes[10:20]) if len(closes[10:20]) > 0 else 0
            right_avg = np.mean(closes[20:30]) if len(closes[20:30]) > 0 else 0
            
            # Forma de ∩: izquierda y derecha más bajas que el medio
            return (left_avg < mid_avg and
                    right_avg < mid_avg and
                    abs(left_avg - right_avg) / left_avg < 0.1 and
                    c[i] < right_avg * 0.99)
        except:
            return False

    def _detect_cup_handle(self, o, h, l, c, p, i):
        """Detectar taza con asa"""
        try:
            if i < 40:
                return False
            
            window = 40
            
            # Taza (parte redondeada)
            cup_high = max(h[i-window:i-15]) if len(h[i-window:i-15]) > 0 else 0
            cup_low = min(l[i-window:i-15]) if len(l[i-window:i-15]) > 0 else 0
            cup_depth = (cup_high - cup_low) / cup_high if cup_high > 0 else 0
            
            # Asa (consolidación bajista)
            handle_highs = h[i-15:i]
            handle_lows = l[i-15:i]
            
            # El asa debe tener tendencia bajista
            handle_trend = all(handle_highs[j] <= handle_highs[j-1] * 1.01 for j in range(1, len(handle_highs)))
            
            return (0.1 < cup_depth < 0.5 and
                    handle_trend and
                    c[i] > handle_lows[-1] * 1.02 and  # Precio saliendo del asa
                    c[i] < cup_high * 0.95)  # Aún no rompió el máximo de la taza
        except:
            return False
    
    def _detect_cup_handle_breakout(self, o, h, l, c, p, i):
        """Detectar taza con asa - ruptura"""
        try:
            if i < 45:
                return False
            
            window = 45
            cup_high = max(h[i-window:i-20]) if len(h[i-window:i-20]) > 0 else 0
            
            return (c[i] > cup_high * 1.02 and
                    h[i] > cup_high * 1.03)
        except:
            return False

    def _detect_reversal_island_bull(self, o, h, l, c, p, i):
        """Detectar isla de reversión alcista"""
        try:
            if i < 3:
                return False
            
            # Gap a la baja, luego gap al alza (dejando una vela aislada)
            return (i > 2 and
                    l[i] > h[i-1] and  # Gap al alza hoy
                    h[i-1] < l[i-2] and  # Gap a la baja ayer
                    c[i] > o[i] and  # Vela alcista
                    c[i] > h[i-1])  # Cierra por encima del gap
        except:
            return False
    
    def _detect_reversal_island_bear(self, o, h, l, c, p, i):
        """Detectar isla de reversión bajista"""
        try:
            if i < 3:
                return False
            
            return (i > 2 and
                    h[i] < l[i-1] and  # Gap a la baja hoy
                    l[i-1] > h[i-2] and  # Gap al alza ayer
                    c[i] < o[i] and  # Vela bajista
                    c[i] < l[i-1])  # Cierra por debajo del gap
        except:
            return False

    def _detect_exhaustion_gap(self, o, h, l, c, p, i):
        """Detectar gap de agotamiento"""
        try:
            if i < 10:
                return False
            
            gap_up = l[i] > h[i-1]
            gap_down = h[i] < l[i-1]
            
            if gap_up:
                # Tendencia previa alcista
                prev_trend = np.mean(c[i-10:i-1]) > np.mean(c[i-20:i-10]) if i > 20 else False
                # Reversión intradía
                reversal = c[i] < o[i] and c[i] < (h[i] + l[i]) / 2
                return (prev_trend and reversal and gap_up)
            
            if gap_down:
                # Tendencia previa bajista
                prev_trend = np.mean(c[i-10:i-1]) < np.mean(c[i-20:i-10]) if i > 20 else False
                # Reversión intradía
                reversal = c[i] > o[i] and c[i] > (h[i] + l[i]) / 2
                return (prev_trend and reversal and gap_down)
            
            return False
        except:
            return False
    
    def _detect_runaway_gap(self, o, h, l, c, p, i):
        """Detectar gap de continuación"""
        try:
            if i < 15:
                return False
            
            gap_up = l[i] > h[i-1]
            gap_down = h[i] < l[i-1]
            
            if gap_up:
                # Tendencia alcista y vela alcista
                return (c[i] > o[i] and
                        c[i] > c[i-1] and
                        c[i-1] > c[i-2])
            
            if gap_down:
                # Tendencia bajista y vela bajista
                return (c[i] < o[i] and
                        c[i] < c[i-1] and
                        c[i-1] < c[i-2])
            
            return False
        except:
            return False
    
    def _detect_breakaway_gap(self, o, h, l, c, p, i):
        """Detectar gap de ruptura"""
        try:
            if i < 20:
                return False
            
            gap_up = l[i] > h[i-1]
            gap_down = h[i] < l[i-1]
            
            if gap_up:
                # Ruptura de resistencia
                resistance_break = h[i] > max(h[i-20:i-1]) * 1.02
                return (resistance_break and c[i] > o[i] and gap_up)
            
            if gap_down:
                # Ruptura de soporte
                support_break = l[i] < min(l[i-20:i-1]) * 0.98
                return (support_break and c[i] < o[i] and gap_down)
            
            return False
        except:
            return False

    def _detect_continuation_gap(self, o, h, l, c, p, i):
        """Detectar gap de continuación"""
        try:
            if i < 15:
                return False
            
            # Gap alcista
            if l[i] > h[i-1]:
                return (c[i] > o[i] and  # Vela alcista
                        c[i] > c[i-1] and  # Cierre superior
                        c[i-1] > c[i-2])   # Tendencia previa alcista
            
            # Gap bajista
            if h[i] < l[i-1]:
                return (c[i] < o[i] and  # Vela bajista
                        c[i] < c[i-1] and  # Cierre inferior
                        c[i-1] < c[i-2])   # Tendencia previa bajista
            
            return False
        except:
            return False
            
    def _detect_window_opening(self, o, h, l, c, p, i):
        """Detectar ventana abierta (gap sin cerrar)"""
        try:
            if i < 1:
                return False
            
            gap_up = l[i] > h[i-1]
            gap_down = h[i] < l[i-1]
            
            if gap_up or gap_down:
                # El gap es significativo
                gap_size = abs(l[i] - h[i-1]) if gap_up else abs(h[i] - l[i-1])
                avg_range = (h[i] - l[i] + h[i-1] - l[i-1]) / 2
                return gap_size > avg_range * 0.3
            
            return False
        except:
            return False
    
    def _detect_three_gaps(self, o, h, l, c, p, i):
        """Detectar tres gaps consecutivos"""
        try:
            if i < 3:
                return False
            
            gaps = 0
            for j in range(i-2, i+1):
                if j > 0:
                    if l[j] > h[j-1] or h[j] < l[j-1]:
                        gaps += 1
            
            return gaps >= 3
        except:
            return False
    
    def _detect_measuring_gap(self, o, h, l, c, p, i):
        """Detectar gap de medición"""
        try:
            if i < 25:
                return False
            
            gap_up = l[i] > h[i-1]
            gap_down = h[i] < l[i-1]
            
            if gap_up:
                # Gap en medio de un movimiento alcista
                move_start = min(l[i-25:i-10]) if i > 25 else l[i-10]
                return (c[i] > move_start * 1.2 and gap_up)
            
            if gap_down:
                move_start = max(h[i-25:i-10]) if i > 25 else h[i-10]
                return (c[i] < move_start * 0.8 and gap_down)
            
            return False
        except:
            return False

    def _detect_key_reversal_day_bull(self, o, h, l, c, p, i):
        """Detectar día clave de reversión alcista"""
        try:
            if i < 1:
                return False
            
            return (c[i] > o[i] and
                    c[i-1] < o[i-1] and
                    l[i] < l[i-1] and
                    c[i] > c[i-1] and
                    c[i] > (h[i] + l[i]) / 2)
        except:
            return False
    
    def _detect_key_reversal_day_bear(self, o, h, l, c, p, i):
        """Detectar día clave de reversión bajista"""
        try:
            if i < 1:
                return False
            
            return (c[i] < o[i] and
                    c[i-1] > o[i-1] and
                    h[i] > h[i-1] and
                    c[i] < c[i-1] and
                    c[i] < (h[i] + l[i]) / 2)
        except:
            return False

    def _detect_wide_ranging_day(self, o, h, l, c, p, i):
        """Detectar día de amplio rango"""
        try:
            if i < 20:
                return False
            
            avg_range = np.mean([h[j] - l[j] for j in range(max(0, i-20), i)])
            current_range = h[i] - l[i]
            
            return current_range > avg_range * 1.8
        except:
            return False
    
    def _detect_narrow_ranging_day(self, o, h, l, c, p, i):
        """Detectar día de estrecho rango"""
        try:
            if i < 20:
                return False
            
            avg_range = np.mean([h[j] - l[j] for j in range(max(0, i-20), i)])
            current_range = h[i] - l[i]
            
            return current_range < avg_range * 0.5
        except:
            return False

    def _detect_inside_day(self, o, h, l, c, p, i):
        """Detectar día interior"""
        try:
            if i < 1:
                return False
            
            return (h[i] <= h[i-1] and
                    l[i] >= l[i-1] and
                    (h[i] < h[i-1] or l[i] > l[i-1]))
        except:
            return False
    
    def _detect_outside_day(self, o, h, l, c, p, i):
        """Detectar día exterior"""
        try:
            if i < 1:
                return False
            
            return (h[i] > h[i-1] and
                    l[i] < l[i-1])
        except:
            return False

    def _detect_high_price_gapping_day(self, o, h, l, c, p, i):
        """Detectar día de gap alcista"""
        try:
            if i < 1:
                return False
            
            return (l[i] > h[i-1] and
                    c[i] > o[i] and
                    c[i] > (h[i] + l[i]) / 2)
        except:
            return False
    
    def _detect_low_price_gapping_day(self, o, h, l, c, p, i):
        """Detectar día de gap bajista"""
        try:
            if i < 1:
                return False
            
            return (h[i] < l[i-1] and
                    c[i] < o[i] and
                    c[i] < (h[i] + l[i]) / 2)
        except:
            return False

    def _detect_closing_price_reversal_bull(self, o, h, l, c, p, i):
        """Detectar reversión de cierre alcista"""
        try:
            if i < 1:
                return False
            
            return (c[i] > o[i] and
                    c[i-1] < o[i-1] and
                    c[i] > c[i-1] and
                    l[i] < l[i-1] and
                    c[i] > (h[i] + l[i]) / 2)
        except:
            return False
    
    def _detect_closing_price_reversal_bear(self, o, h, l, c, p, i):
        """Detectar reversión de cierre bajista"""
        try:
            if i < 1:
                return False
            
            return (c[i] < o[i] and
                    c[i-1] > o[i-1] and
                    c[i] < c[i-1] and
                    h[i] > h[i-1] and
                    c[i] < (h[i] + l[i]) / 2)
        except:
            return False
    
    # === FIN _detect_bull_pennant, _detect_bear_pennant, _detect_falling_wedge, _detect_rising_wedge ===
                 
    
    # === FUNCIÓN COMPLETA: detect_candle_patterns ===
    # Ubicación: Reemplazar entre línea ~700 y línea ~750 aproximadamente
    
    def detect_candle_patterns(self, df, max_lookback=30):
        """Detector de patrones de vela - VERSIÓN CORREGIDA CON VALIDACIÓN ESTRICTA"""
        try:
            o = df['open'].values
            h = df['high'].values
            l = df['low'].values
            c = df['close'].values
            v = df['volume'].values if 'volume' in df else np.zeros(len(df))
            
            n = len(df)
            detected_patterns = []
            pattern_score = 0
            
            if n < 10:
                return {
                    'all_patterns': [],
                    'recent_patterns': [],
                    'bullish_patterns': [],
                    'bearish_patterns': [],
                    'neutral_patterns': [],
                    'count': 0,
                    'bullish_count': 0,
                    'bearish_count': 0,
                    'neutral_count': 0,
                    'pattern_score': 0,
                    'highest_reliability': 0,
                    'avg_reliability': 0,
                    'high_quality_patterns': []
                }
            
            # Calcular métricas de contexto
            avg_volume = np.mean(v) if len(v) > 0 else 0
            current_price = c[-1] if n > 0 else 0
            
            # Calcular soportes y resistencias cercanos
            supports = []
            resistances = []
            for i in range(max(10, n-50), n):
                if i > 5 and i < n-5:
                    if l[i] == min(l[i-5:i+6]):
                        supports.append(l[i])
                    if h[i] == max(h[i-5:i+6]):
                        resistances.append(h[i])
            
            # CORREGIDO: Verificar listas vacías antes de min/max
            support_candidates = [s for s in supports if s < current_price]
            nearest_support = max(support_candidates) if support_candidates else None
            
            resistance_candidates = [r for r in resistances if r > current_price]
            nearest_resistance = min(resistance_candidates) if resistance_candidates else None
            
            # Calcular fuerza de tendencia previa
            prev_trend = None
            if n > 10:
                cambios = [(c[i] - c[i-1]) / c[i-1] * 100 for i in range(max(0, n-10), n)]
                if sum(cambios) > 2:
                    prev_trend = 'bullish'
                elif sum(cambios) < -2:
                    prev_trend = 'bearish'
                else:
                    prev_trend = 'neutral'
            
            # Agrupar patrones por tipo
            patterns_by_type = {
                '1': [],
                '2': [],
                '3': [],
                '4+': []
            }
            
            for pattern_id, pattern in self.pattern_database.items():
                patterns_by_type[pattern['type']].append((pattern_id, pattern))
            
            # ============ DETECTAR PATRONES DE 1 VELA ============
            for i in range(0, n):
                for pattern_id, pattern in patterns_by_type['1']:
                    try:
                        # Verificar que la vela sea del color correcto según el patrón
                        if pattern['direction'] == 'bullish' and c[i] <= o[i]:
                            continue
                        if pattern['direction'] == 'bearish' and c[i] >= o[i]:
                            continue
                        
                        if pattern['detect'](o[i], h[i], l[i], c[i], c, i):
                            contexto_score = 0
                            razones_contexto = []
                            
                            # 1. Volumen
                            if v[i] > avg_volume * 1.5:
                                contexto_score += 20
                                razones_contexto.append('volumen_alto')
                            elif v[i] > avg_volume * 1.2:
                                contexto_score += 10
                                razones_contexto.append('volumen_moderado')
                            elif v[i] < avg_volume * 0.7:
                                contexto_score -= 15
                                razones_contexto.append('volumen_bajo')
                            
                            # 2. Cerca de soporte (para patrones alcistas)
                            if nearest_support and pattern['direction'] == 'bullish':
                                distancia = abs(current_price - nearest_support) / current_price * 100
                                if distancia < 1.0:
                                    contexto_score += 30
                                    razones_contexto.append('sobre_soporte')
                                elif distancia < 2.0:
                                    contexto_score += 15
                                    razones_contexto.append('cerca_soporte')
                            
                            # 3. Cerca de resistencia (para patrones bajistas)
                            if nearest_resistance and pattern['direction'] == 'bearish':
                                distancia = abs(nearest_resistance - current_price) / current_price * 100
                                if distancia < 1.0:
                                    contexto_score += 30
                                    razones_contexto.append('bajo_resistencia')
                                elif distancia < 2.0:
                                    contexto_score += 15
                                    razones_contexto.append('cerca_resistencia')
                            
                            # 4. Tendencia previa
                            if prev_trend == pattern['direction']:
                                contexto_score += 20
                                razones_contexto.append('tendencia_favorable')
                            elif prev_trend and prev_trend != pattern['direction']:
                                contexto_score -= 10
                                razones_contexto.append('contra_tendencia')
                            
                            # 5. Tamaño de la vela (calidad)
                            rango_vela = h[i] - l[i]
                            cuerpo = abs(c[i] - o[i])
                            if rango_vela > 0:
                                calidad_cuerpo = (cuerpo / rango_vela) * 100
                                if calidad_cuerpo > 70:
                                    contexto_score += 15
                                    razones_contexto.append('vela_fuerte')
                                elif calidad_cuerpo < 30:
                                    contexto_score -= 10
                                    razones_contexto.append('vela_debil')
                            
                            confiabilidad_final = min(100, pattern['reliability'] + contexto_score)
                            
                            if confiabilidad_final >= 60:
                                detected_patterns.append({
                                    'name': pattern['name'],
                                    'direction': pattern['direction'],
                                    'reliability': confiabilidad_final,
                                    'raw_reliability': pattern['reliability'],
                                    'contexto_score': contexto_score,
                                    'razones_contexto': razones_contexto,
                                    'index': i,
                                    'type': pattern['type']
                                })
                                
                                if pattern['direction'] == 'bullish':
                                    pattern_score += confiabilidad_final / 100
                                elif pattern['direction'] == 'bearish':
                                    pattern_score -= confiabilidad_final / 100
                    except Exception as e:
                        continue
            
            # ============ PATRONES DE 2 VELAS ============
            for i in range(1, n):
                for pattern_id, pattern in patterns_by_type['2']:
                    try:
                        if pattern['direction'] == 'bullish' and c[i] <= o[i]:
                            continue
                        if pattern['direction'] == 'bearish' and c[i] >= o[i]:
                            continue
                        
                        if pattern['detect'](o, h, l, c, None, i):
                            contexto_score = 0
                            razones_contexto = []
                            
                            if v[i] > avg_volume * 1.5:
                                contexto_score += 25
                                razones_contexto.append('volumen_alto')
                            elif v[i] > avg_volume * 1.2:
                                contexto_score += 15
                                razones_contexto.append('volumen_moderado')
                            
                            if nearest_support and pattern['direction'] == 'bullish':
                                distancia = abs(current_price - nearest_support) / current_price * 100
                                if distancia < 2.0:
                                    contexto_score += 25
                                    razones_contexto.append('sobre_soporte')
                            
                            if nearest_resistance and pattern['direction'] == 'bearish':
                                distancia = abs(nearest_resistance - current_price) / current_price * 100
                                if distancia < 2.0:
                                    contexto_score += 25
                                    razones_contexto.append('bajo_resistencia')
                            
                            confiabilidad_final = min(100, pattern['reliability'] + contexto_score)
                            
                            if confiabilidad_final >= 65:
                                detected_patterns.append({
                                    'name': pattern['name'],
                                    'direction': pattern['direction'],
                                    'reliability': confiabilidad_final,
                                    'raw_reliability': pattern['reliability'],
                                    'contexto_score': contexto_score,
                                    'razones_contexto': razones_contexto,
                                    'index': i,
                                    'type': pattern['type']
                                })
                                
                                if pattern['direction'] == 'bullish':
                                    pattern_score += confiabilidad_final / 100 * 1.5
                                elif pattern['direction'] == 'bearish':
                                    pattern_score -= confiabilidad_final / 100 * 1.5
                    except Exception as e:
                        continue
            
            # ============ PATRONES DE 3 VELAS - VERSIÓN CORREGIDA ============
            for i in range(2, n):
                for pattern_id, pattern in patterns_by_type['3']:
                    try:
                        # ============ VALIDACIÓN ESTRICTA PARA TRES CUERVOS NEGROS ============
                        if pattern['name'] == 'Tres Cuervos Negros':
                            # Verificar que las 3 velas sean BAJISTAS
                            if not (c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2]):
                                continue
                            
                            # Verificar que los cuerpos sean grandes (> 60% del rango)
                            cuerpo1 = o[i-2] - c[i-2]
                            rango1 = h[i-2] - l[i-2]
                            cuerpo2 = o[i-1] - c[i-1]
                            rango2 = h[i-1] - l[i-1]
                            cuerpo3 = o[i] - c[i]
                            rango3 = h[i] - l[i]
                            
                            if (cuerpo1 / rango1 < 0.6 or cuerpo2 / rango2 < 0.6 or cuerpo3 / rango3 < 0.6):
                                continue
                            
                            # Verificar que cada vela cierra más baja que la anterior
                            if not (c[i] < c[i-1] < c[i-2]):
                                continue
                            
                            # Verificar que las mechas sean pequeñas (< 30% del cuerpo)
                            mecha_sup1 = h[i-2] - o[i-2]
                            mecha_inf1 = c[i-2] - l[i-2]
                            mecha_sup2 = h[i-1] - o[i-1]
                            mecha_inf2 = c[i-1] - l[i-1]
                            mecha_sup3 = h[i] - o[i]
                            mecha_inf3 = c[i] - l[i]
                            
                            if (mecha_sup1 > cuerpo1 * 0.3 or mecha_inf1 > cuerpo1 * 0.3 or
                                mecha_sup2 > cuerpo2 * 0.3 or mecha_inf2 > cuerpo2 * 0.3 or
                                mecha_sup3 > cuerpo3 * 0.3 or mecha_inf3 > cuerpo3 * 0.3):
                                continue
                            
                            # Si pasa todas las validaciones, es un patrón válido
                            contexto_score = 30  # Base alta por ser patrón fuerte
                            
                        # ============ VALIDACIÓN PARA TRES SOLDADOS BLANCOS ============
                        elif pattern['name'] == 'Tres Soldados Blancos':
                            if not (c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2]):
                                continue
                            
                            cuerpo1 = c[i-2] - o[i-2]
                            rango1 = h[i-2] - l[i-2]
                            cuerpo2 = c[i-1] - o[i-1]
                            rango2 = h[i-1] - l[i-1]
                            cuerpo3 = c[i] - o[i]
                            rango3 = h[i] - l[i]
                            
                            if (cuerpo1 / rango1 < 0.6 or cuerpo2 / rango2 < 0.6 or cuerpo3 / rango3 < 0.6):
                                continue
                            
                            if not (c[i] > c[i-1] > c[i-2]):
                                continue
                            
                            contexto_score = 30
                        
                        # ============ VALIDACIÓN PARA ESTRELLA MATUTINA ============
                        elif pattern['name'] == 'Estrella Matutina':
                            # Vela1: Bajista grande
                            if not (c[i-2] < o[i-2]):
                                continue
                            cuerpo1 = o[i-2] - c[i-2]
                            rango1 = h[i-2] - l[i-2]
                            if cuerpo1 / rango1 < 0.6:
                                continue
                            
                            # Vela2: Cuerpo pequeño (estrella)
                            if abs(c[i-1] - o[i-1]) > (h[i-1] - l[i-1]) * 0.3:
                                continue
                            
                            # Vela3: Alcista grande
                            if not (c[i] > o[i]):
                                continue
                            cuerpo3 = c[i] - o[i]
                            rango3 = h[i] - l[i]
                            if cuerpo3 / rango3 < 0.6:
                                continue
                            
                            # Gap
                            if not (c[i-1] < l[i-2] and c[i] > o[i-1]):
                                continue
                            
                            contexto_score = 30
                        
                        # ============ VALIDACIÓN PARA ESTRELLA VESPERTINA ============
                        elif pattern['name'] == 'Estrella Vespertina':
                            # Vela1: Alcista grande
                            if not (c[i-2] > o[i-2]):
                                continue
                            cuerpo1 = c[i-2] - o[i-2]
                            rango1 = h[i-2] - l[i-2]
                            if cuerpo1 / rango1 < 0.6:
                                continue
                            
                            # Vela2: Cuerpo pequeño (estrella)
                            if abs(c[i-1] - o[i-1]) > (h[i-1] - l[i-1]) * 0.3:
                                continue
                            
                            # Vela3: Bajista grande
                            if not (c[i] < o[i]):
                                continue
                            cuerpo3 = o[i] - c[i]
                            rango3 = h[i] - l[i]
                            if cuerpo3 / rango3 < 0.6:
                                continue
                            
                            # Gap
                            if not (c[i-1] > h[i-2] and c[i] < o[i-1]):
                                continue
                            
                            contexto_score = 30
                        
                        else:
                            # Para otros patrones, usar la detección normal
                            if pattern['detect'](o, h, l, c, None, i):
                                contexto_score = 0
                            else:
                                continue
                        
                        # Calcular confiabilidad final
                        confiabilidad_final = min(100, pattern['reliability'] + contexto_score)
                        
                        if confiabilidad_final >= 70:
                            detected_patterns.append({
                                'name': pattern['name'],
                                'direction': pattern['direction'],
                                'reliability': confiabilidad_final,
                                'raw_reliability': pattern['reliability'],
                                'contexto_score': contexto_score,
                                'razones_contexto': [],
                                'index': i,
                                'type': pattern['type']
                            })
                            
                            if pattern['direction'] == 'bullish':
                                pattern_score += confiabilidad_final / 100 * 2
                            elif pattern['direction'] == 'bearish':
                                pattern_score -= confiabilidad_final / 100 * 2
                                
                    except Exception as e:
                        continue
            
            # ============ PATRONES DE 4+ VELAS ============
            for i in range(15, n):
                for pattern_id, pattern in patterns_by_type['4+']:
                    try:
                        if pattern['detect'](o, h, l, c, None, i):
                            contexto_score = 0
                            razones_contexto = []
                            
                            if v[i] > avg_volume * 2.0:
                                contexto_score += 40
                                razones_contexto.append('volumen_institucional')
                            elif v[i] > avg_volume * 1.5:
                                contexto_score += 25
                                razones_contexto.append('volumen_confirmacion')
                            
                            if pattern['direction'] == 'bullish' and nearest_resistance:
                                if current_price > nearest_resistance:
                                    contexto_score += 50
                                    razones_contexto.append('ruptura_resistencia')
                            
                            if pattern['direction'] == 'bearish' and nearest_support:
                                if current_price < nearest_support:
                                    contexto_score += 50
                                    razones_contexto.append('ruptura_soporte')
                            
                            confiabilidad_final = min(100, pattern['reliability'] + contexto_score)
                            
                            if confiabilidad_final >= 75:
                                detected_patterns.append({
                                    'name': pattern['name'],
                                    'direction': pattern['direction'],
                                    'reliability': confiabilidad_final,
                                    'raw_reliability': pattern['reliability'],
                                    'contexto_score': contexto_score,
                                    'razones_contexto': razones_contexto,
                                    'index': i,
                                    'type': pattern['type']
                                })
                                
                                if pattern['direction'] == 'bullish':
                                    pattern_score += confiabilidad_final / 100 * 2.5
                                elif pattern['direction'] == 'bearish':
                                    pattern_score -= confiabilidad_final / 100 * 2.5
                    except Exception as e:
                        continue
            
            # Filtrar patrones recientes
            recent_patterns = [p for p in detected_patterns if p['index'] >= n - max_lookback]
            
            # Eliminar duplicados
            unique_patterns = {}
            for p in recent_patterns:
                key = f"{p['index']}_{p['name']}"
                if key not in unique_patterns or p['reliability'] > unique_patterns[key]['reliability']:
                    unique_patterns[key] = p
            
            recent_patterns = list(unique_patterns.values())
            recent_patterns.sort(key=lambda x: x['index'], reverse=True)
            
            # Normalizar score
            if len(recent_patterns) > 0:
                pattern_score = np.clip(pattern_score / max(1, len(recent_patterns) * 0.5), -10, 10)
            else:
                pattern_score = 0
            
            return {
                'all_patterns': detected_patterns,
                'recent_patterns': recent_patterns,
                'bullish_patterns': [p for p in recent_patterns if p['direction'] == 'bullish'],
                'bearish_patterns': [p for p in recent_patterns if p['direction'] == 'bearish'],
                'neutral_patterns': [p for p in recent_patterns if p['direction'] == 'neutral'],
                'count': len(recent_patterns),
                'bullish_count': len([p for p in recent_patterns if p['direction'] == 'bullish']),
                'bearish_count': len([p for p in recent_patterns if p['direction'] == 'bearish']),
                'neutral_count': len([p for p in recent_patterns if p['direction'] == 'neutral']),
                'pattern_score': float(pattern_score),
                'highest_reliability': max([p['reliability'] for p in recent_patterns]) if recent_patterns else 0,
                'avg_reliability': np.mean([p['reliability'] for p in recent_patterns]) if recent_patterns else 0,
                'high_quality_patterns': [p for p in recent_patterns if p['reliability'] >= 80]
            }
        except Exception as e:
            print(f"Error en detect_candle_patterns: {e}")
            import traceback
            traceback.print_exc()
            return {
                'all_patterns': [],
                'recent_patterns': [],
                'bullish_patterns': [],
                'bearish_patterns': [],
                'neutral_patterns': [],
                'count': 0,
                'bullish_count': 0,
                'bearish_count': 0,
                'neutral_count': 0,
                'pattern_score': 0,
                'highest_reliability': 0,
                'avg_reliability': 0,
                'high_quality_patterns': []
            }
    # === FIN detect_candle_patterns ===
    
    # ========================================================================
    # BANCO DE JUSTIFICACIONES COMPLETO (20+ POR CATEGORÍA)
    # ========================================================================
    
    # === FUNCIÓN COMPLETA:  ===
    # Ubicación: Reemplazar entre línea ~270 y línea ~500 aproximadamente
    
    def _initialize_justification_bank(self):
        """Inicializar banco de justificaciones - VERSIÓN COMPLETA CON TODAS LAS CATEGORÍAS"""
        return {
            # ============ CATEGORÍA 1: ACCIÓN (TÍTULO) ============
            'accion_compra_spot': {
                'template': '🟢 COMPRA SPOT DE {par} en {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            'accion_venta_spot': {
                'template': '🔴 VENTA SPOT DE {par} en {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            'accion_long': {
                'template': '📈 LONG FUTURES DE {par} en {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            'accion_short': {
                'template': '📉 SHORT FUTURES DE {par} en {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            'accion_no_operar': {
                'template': '⏸️ NO OPERAR EN {par} {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            'accion_esperar': {
                'template': '⏳ ESPERAR - {par} en {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            'accion_caution': {
                'template': '⚠️ PRECAUCIÓN - {par} en {temporalidad}\n\n',
                'type': 'accion',
                'order': 1
            },
            
            # ============ CATEGORÍA 2: FUERZA DE TENDENCIA ============
            'fuerza_tendencia_adx_fuerte': {
                'template': 'El ADX registra {adx_valor} puntos, confirmando una tendencia FUERTE en desarrollo. ',
                'type': 'fuerza_tendencia',
                'order': 2,
                'condition': 'adx_fuerte'
            },
            'fuerza_tendencia_adx_creciente': {
                'template': 'El ADX presenta una pendiente positiva ({adx_valor}), indicando que la fuerza de la tendencia se está incrementando. ',
                'type': 'fuerza_tendencia',
                'order': 2,
                'condition': 'adx_25_plus'
            },
            'fuerza_tendencia_adx_decreciente': {
                'template': 'La disminución en las lecturas de ADX ({adx_valor}) sugiere que la tendencia actual está perdiendo fuerza. ',
                'type': 'fuerza_tendencia',
                'order': 2,
                'condition': 'adx_bajo'
            },
            'fuerza_tendencia_ftm_expansion': {
                'template': 'FTMaverick muestra expansión CRECIENTE del ancho de banda ({ftm_fuerza}%), confirmando aumento de volatilidad direccional. ',
                'type': 'fuerza_tendencia',
                'order': 2,
                'condition': 'ftm_fuerte_alcista'
            },
            'fuerza_tendencia_ftm_contraccion': {
                'template': 'La contracción en FTMaverick ({ftm_fuerza}%) indica pérdida de momentum y posible consolidación. ',
                'type': 'fuerza_tendencia',
                'order': 2,
                'condition': 'ftm_debil_bajista'
            },
            
            # ============ CATEGORÍA 3: DIRECCIÓN DE TENDENCIA (DMI) ============
            'direccion_dmi_alcista': {
                'template': 'DMI muestra dominio alcista: +DI ({plus_di}) supera a -DI ({minus_di}), indicando presión compradora. ',
                'type': 'direccion_tendencia',
                'order': 3,
                'condition': 'dmi_alcista'
            },
            'direccion_dmi_bajista': {
                'template': 'DMI muestra dominio bajista: -DI ({minus_di}) supera a +DI ({plus_di}), confirmando presión vendedora. ',
                'type': 'direccion_tendencia',
                'order': 3,
                'condition': 'dmi_bajista'
            },
            'direccion_dmi_fuerte_alcista': {
                'template': 'DMI con fuerte dominio alcista: +DI ({plus_di}) supera ampliamente a -DI ({minus_di}) por {dmi_diff} puntos. ',
                'type': 'direccion_tendencia',
                'order': 3,
                'condition': 'dmi_fuerte_alcista'
            },
            'direccion_dmi_fuerte_bajista': {
                'template': 'DMI con fuerte dominio bajista: -DI ({minus_di}) supera ampliamente a +DI ({plus_di}) por {dmi_diff} puntos. ',
                'type': 'direccion_tendencia',
                'order': 3,
                'condition': 'dmi_fuerte_bajista'
            },
            
            # ============ CATEGORÍA 4: TENDENCIA CON EMAS ============
            'tendencia_emas_alcista': {
                'template': 'Las medias móviles EMA 9 ({ema9}), EMA 21 ({ema21}) y EMA 50 ({ema50}) se encuentran alineadas en orden ascendente, actuando como soporte dinámico. ',
                'type': 'direccion_tendencia',
                'order': 4,
                'condition': 'emas_alineadas_alcista'
            },
            'tendencia_emas_bajista': {
                'template': 'Las medias móviles muestran alineación bajista: EMA 9 ({ema9}) bajo EMA 21 ({ema21}) y EMA 50 ({ema50}), confirmando presión vendedora. ',
                'type': 'direccion_tendencia',
                'order': 4,
                'condition': 'emas_alineadas_bajista'
            },
            'tendencia_ema_cruce_alcista': {
                'template': 'Cruce alcista de EMAs: EMA 9 ({ema9}) cruza sobre EMA 21 ({ema21}), señal temprana de cambio de tendencia. ',
                'type': 'direccion_tendencia',
                'order': 4,
                'condition': 'ema_cross_bull'
            },
            'tendencia_ema_cruce_bajista': {
                'template': 'Cruce bajista de EMAs: EMA 9 ({ema9}) cruza bajo EMA 21 ({ema21}), confirmando pérdida de momentum alcista. ',
                'type': 'direccion_tendencia',
                'order': 4,
                'condition': 'ema_cross_bear'
            },
            
            # ============ CATEGORÍA 5: SUPERTREND ============
            'supertrend_alcista': {
                'template': 'SuperTrend se mantiene en posición alcista en {supertrend}, actuando como soporte dinámico. ',
                'type': 'direccion_tendencia',
                'order': 5,
                'condition': 'supertrend_alcista'
            },
            'supertrend_bajista': {
                'template': 'SuperTrend bajista en {supertrend}, con el precio cotizando por debajo de la línea que actúa como resistencia dinámica. ',
                'type': 'direccion_tendencia',
                'order': 5,
                'condition': 'supertrend_bajista'
            },
            
            # ============ CATEGORÍA 6: ICHIMOKU ============
            'ichimoku_alcista': {
                'template': 'Ichimoku muestra configuración alcista: precio sobre nube con Tenkan ({ichimoku_tk}) sobre Kijun, confirmando tendencia positiva. ',
                'type': 'direccion_tendencia',
                'order': 6,
                'condition': 'ichimoku_alcista'
            },
            'ichimoku_bajista': {
                'template': 'Ichimoku bajista: precio bajo nube con Tenkan ({ichimoku_tk}) bajo Kijun, confirmando tendencia negativa. ',
                'type': 'direccion_tendencia',
                'order': 6,
                'condition': 'ichimoku_bajista'
            },
            'ichimoku_tk_cruce_alcista': {
                'template': 'Ichimoku muestra cruce de Tenkan sobre Kijun, señal temprana de posible cambio de tendencia alcista. ',
                'type': 'direccion_tendencia',
                'order': 6,
                'condition': 'ichimoku_tk_cross_bull'
            },
            
            # ============ CATEGORÍA 7: PARABOLIC SAR ============
            'parabolic_sar_alcista': {
                'template': 'Parabolic SAR bajo el precio ({parabolic_sar_trend}) actuando como trailing stop dinámico en la tendencia alcista. ',
                'type': 'direccion_tendencia',
                'order': 7,
                'condition': 'psar_alcista'
            },
            'parabolic_sar_bajista': {
                'template': 'Parabolic SAR sobre el precio ({parabolic_sar_trend}) confirma presión vendedora y sirve como resistencia móvil. ',
                'type': 'direccion_tendencia',
                'order': 7,
                'condition': 'psar_bajista'
            },
            'parabolic_sar_cambio_alcista': {
                'template': 'Parabolic SAR señala un posible CAMBIO DE TENDENCIA a alcista, con puntos bajo el precio después de una fase bajista. ',
                'type': 'cambio_tendencia',
                'order': 7,
                'condition': 'psar_alcista_contra_tendencia'
            },
            'parabolic_sar_cambio_bajista': {
                'template': 'Parabolic SAR anticipa un CAMBIO DE TENDENCIA a bajista, con puntos sobre el precio tras una fase alcista. ',
                'type': 'cambio_tendencia',
                'order': 7,
                'condition': 'psar_bajista_contra_tendencia'
            },
            
            # ============ CATEGORÍA 8: MOMENTUM - RSI ============
            'rsi_alcista': {
                'template': 'RSI en {rsi_valor} puntos, manteniéndose en territorio positivo sin alcanzar sobrecompra. ',
                'type': 'momentum_clasico',
                'order': 8,
                'condition': 'rsi_alcista'
            },
            'rsi_bajista': {
                'template': 'RSI en {rsi_valor} puntos, reflejando debilidad en el impulso comprador. ',
                'type': 'momentum_clasico',
                'order': 8,
                'condition': 'rsi_bajista'
            },
            'rsi_sobrecompra': {
                'template': 'RSI alcanza nivel de sobrecompra ({rsi_valor}), lo que podría anticipar una pausa o corrección. ',
                'type': 'momentum_clasico',
                'order': 8,
                'condition': 'rsi_sobrecompra'
            },
            'rsi_sobreventa': {
                'template': 'RSI en zona de sobreventa ({rsi_valor}), sugiriendo que la presión vendedora podría estar agotándose. ',
                'type': 'momentum_clasico',
                'order': 8,
                'condition': 'rsi_sobreventa'
            },
            
            # ============ CATEGORÍA 9: RSI MAVERICK ============
            'rsi_maverick_alcista': {
                'template': 'RSI Maverick en {rsi_maverick_valor} puntos, indicando posición favorable dentro de las bandas de volatilidad. ',
                'type': 'momentum_avanzado',
                'order': 9,
                'condition': 'rsi_maverick_alcista'
            },
            'rsi_maverick_bajista': {
                'template': 'RSI Maverick en {rsi_maverick_valor} puntos, reflejando debilidad en el contexto de volatilidad actual. ',
                'type': 'momentum_avanzado',
                'order': 9,
                'condition': 'rsi_maverick_bajista'
            },
            'rsi_maverick_sobrecompra': {
                'template': 'RSI Maverick en zona de sobrecompra ({rsi_maverick_valor}), sugiriendo posible agotamiento. ',
                'type': 'momentum_avanzado',
                'order': 9,
                'condition': 'rsi_maverick_sobrecompra'
            },
            'rsi_maverick_sobreventa': {
                'template': 'RSI Maverick en zona de sobreventa ({rsi_maverick_valor}), anticipando posible rebote. ',
                'type': 'momentum_avanzado',
                'order': 9,
                'condition': 'rsi_maverick_sobreventa'
            },
            
            # ============ CATEGORÍA 10: MACD ============
            'macd_alcista': {
                'template': 'MACD muestra histograma positivo ({macd_histograma}) con señal alcista, confirmando momentum favorable. ',
                'type': 'momentum_avanzado',
                'order': 10,
                'condition': 'macd_alcista'
            },
            'macd_bajista': {
                'template': 'MACD con histograma negativo ({macd_histograma}) refleja pérdida de impulso y presión vendedora. ',
                'type': 'momentum_avanzado',
                'order': 10,
                'condition': 'macd_bajista'
            },
            'macd_histograma_creciente': {
                'template': 'MACD histograma creciente ({macd_histograma}) confirma fortalecimiento del momentum actual. ',
                'type': 'momentum_avanzado',
                'order': 10,
                'condition': 'macd_hist_creciente'
            },
            
            # ============ CATEGORÍA 11: ESTOCÁSTICO ============
            'estocastico_alcista': {
                'template': 'Estocástico (%K {stoch_k}) muestra posición alcista, con cruce favorable desde zona de sobreventa. ',
                'type': 'momentum_clasico',
                'order': 11,
                'condition': 'estocastico_alcista'
            },
            'estocastico_bajista': {
                'template': 'Estocástico (%K {stoch_k}) refleja debilidad, con cruce bajista desde zona de sobrecompra. ',
                'type': 'momentum_clasico',
                'order': 11,
                'condition': 'estocastico_bajista'
            },
            'estocastico_cruce_alcista': {
                'template': 'Estocástico presenta cruce alcista (%K {stoch_k} > %D {stoch_d}) desde zona de sobreventa, anticipando recuperación. ',
                'type': 'momentum_clasico',
                'order': 11,
                'condition': 'estocastico_cruce_alcista'
            },
            'estocastico_cruce_bajista': {
                'template': 'Estocástico presenta cruce bajista (%K {stoch_k} < %D {stoch_d}) desde zona de sobrecompra, advirtiendo corrección. ',
                'type': 'momentum_clasico',
                'order': 11,
                'condition': 'estocastico_cruce_bajista'
            },
            
            # ============ CATEGORÍA 12: WILLIAMS %R ============
            'williams_alcista': {
                'template': 'Williams %R en {williams} puntos, reflejando condiciones favorables sin extremos. ',
                'type': 'momentum_avanzado',
                'order': 12,
                'condition': 'williams_alcista'
            },
            'williams_bajista': {
                'template': 'Williams %R en {williams} puntos, indicando debilidad en el impulso actual. ',
                'type': 'momentum_avanzado',
                'order': 12,
                'condition': 'williams_bajista'
            },
            'williams_sobrecompra': {
                'template': 'Williams %R en territorio de sobrecompra ({williams}), advirtiendo sobre posible agotamiento. ',
                'type': 'momentum_avanzado',
                'order': 12,
                'condition': 'williams_sobrecompra'
            },
            'williams_sobreventa': {
                'template': 'Williams %R en zona de sobreventa ({williams}), sugiriendo posible rebote. ',
                'type': 'momentum_avanzado',
                'order': 12,
                'condition': 'williams_sobreventa'
            },
            
            # ============ CATEGORÍA 13: CCI ============
            'cci_alcista': {
                'template': 'CCI en {cci} puntos, confirmando momentum alcista sin llegar a niveles extremos. ',
                'type': 'momentum_avanzado',
                'order': 13,
                'condition': 'cci_alcista'
            },
            'cci_bajista': {
                'template': 'CCI en {cci} puntos, reflejando presión vendedora y debilidad en el impulso. ',
                'type': 'momentum_avanzado',
                'order': 13,
                'condition': 'cci_bajista'
            },
            'cci_extremo_alto': {
                'template': 'CCI supera +200 ({cci}), indicando fuerza excepcional pero también condición de extensión que podría preceder a una pausa. ',
                'type': 'momentum_avanzado',
                'order': 13,
                'condition': 'cci_extremo_alto'
            },
            'cci_extremo_bajo': {
                'template': 'CCI bajo -200 ({cci}) refleja condición de sobreventa extrema, posible rebote inminente. ',
                'type': 'momentum_avanzado',
                'order': 13,
                'condition': 'cci_extremo_bajo'
            },
            
            # ============ CATEGORÍA 14: SQUEEZE MOMENTUM ============
            'squeeze_alcista': {
                'template': 'Squeeze Momentum positivo ({squeeze_momentum}) confirma liberación de presión alcista. ',
                'type': 'momentum_avanzado',
                'order': 14,
                'condition': 'squeeze_alcista'
            },
            'squeeze_bajista': {
                'template': 'Squeeze Momentum negativo ({squeeze_momentum}) indica liberación de presión bajista. ',
                'type': 'momentum_avanzado',
                'order': 14,
                'condition': 'squeeze_bajista'
            },
            'squeeze_prolongado': {
                'template': 'Squeeze prolongado por {squeeze_length} velas, anticipando expansión inminente de volatilidad. ',
                'type': 'volatilidad',
                'order': 14,
                'condition': 'squeeze_prolongado'
            },
            
            # ============ CATEGORÍA 15: DIVERGENCIAS ============
            'divergencia_rsi_alcista': {
                'template': 'Divergencia alcista en RSI: mientras el precio marca mínimos decrecientes, RSI ({rsi_valor}) muestra mínimos crecientes. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_rsi_alcista'
            },
            'divergencia_rsi_bajista': {
                'template': 'Divergencia bajista en RSI: precio en máximos crecientes mientras RSI ({rsi_valor}) forma máximos decrecientes. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_rsi_bajista'
            },
            'divergencia_macd_alcista': {
                'template': 'Divergencia alcista en MACD: histograma ({macd_histograma}) muestra mínimos crecientes mientras el precio cae. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_macd_alcista'
            },
            'divergencia_macd_bajista': {
                'template': 'Divergencia bajista en MACD: histograma ({macd_histograma}) decrece mientras el precio sube. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_macd_bajista'
            },
            'divergencia_estocastico_alcista': {
                'template': 'Divergencia alcista en Estocástico: %K ({stoch_k}) forma mínimos crecientes frente a precio. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_estocastico_alcista'
            },
            'divergencia_estocastico_bajista': {
                'template': 'Divergencia bajista en Estocástico: %K ({stoch_k}) forma máximos decrecientes mientras precio sube. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_estocastico_bajista'
            },
            'divergencia_williams_alcista': {
                'template': 'Divergencia alcista en Williams %R ({williams}) anticipa posible giro al alza. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_williams_alcista'
            },
            'divergencia_williams_bajista': {
                'template': 'Divergencia bajista en Williams %R ({williams}) advierte sobre posible agotamiento. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_williams_bajista'
            },
            'divergencia_cci_alcista': {
                'template': 'Divergencia alcista en CCI ({cci}) sugiere acumulación en zonas de sobreventa. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_cci_alcista'
            },
            'divergencia_cci_bajista': {
                'template': 'Divergencia bajista en CCI ({cci}) indica posible distribución en sobrecompra. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_cci_bajista'
            },
            'divergencia_rsi_maverick_alcista': {
                'template': 'Divergencia alcista en RSI Maverick ({rsi_maverick_valor}) confirma acumulación institucional. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_rsi_maverick_alcista'
            },
            'divergencia_rsi_maverick_bajista': {
                'template': 'Divergencia bajista en RSI Maverick ({rsi_maverick_valor}) indica distribución. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_rsi_maverick_bajista'
            },
            'divergencia_oculta_alcista': {
                'template': 'Divergencia oculta alcista detectada, indicando fortaleza subyacente en la tendencia actual. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_oculta_alcista'
            },
            'divergencia_oculta_bajista': {
                'template': 'Divergencia oculta bajista detectada, señal de debilidad subyacente en la tendencia. ',
                'type': 'divergencias',
                'order': 15,
                'condition': 'divergencia_oculta_bajista'
            },
            
            # ============ CATEGORÍA 16: FLUJO DE DINERO (MFI) ============
            'mfi_compra': {
                'template': 'MFI supera 60 ({mfi}) con volumen creciente, confirmando entrada de capital institucional. ',
                'type': 'flujo_dinero',
                'order': 16,
                'condition': 'mfi_compra'
            },
            'mfi_venta': {
                'template': 'MFI desciende por debajo de 40 ({mfi}), indicando salida de flujo y distribución. ',
                'type': 'flujo_dinero',
                'order': 16,
                'condition': 'mfi_venta'
            },
            'mfi_positivo': {
                'template': 'MFI en {mfi} puntos refleja flujo de capital positivo, respaldando el movimiento. ',
                'type': 'flujo_dinero',
                'order': 16,
                'condition': 'mfi_positivo'
            },
            'mfi_negativo': {
                'template': 'MFI en {mfi} puntos indica salida de capital, consistente con presión vendedora. ',
                'type': 'flujo_dinero',
                'order': 16,
                'condition': 'mfi_negativo'
            },
            
            # ============ CATEGORÍA 17: FORCE INDEX ============
            'force_index_positivo': {
                'template': 'Force Index en territorio positivo ({force_index}) confirma fuerza compradora genuina. ',
                'type': 'flujo_dinero',
                'order': 17,
                'condition': 'force_positivo'
            },
            'force_index_negativo': {
                'template': 'Force Index negativo ({force_index}) refleja presión vendedora sostenida. ',
                'type': 'flujo_dinero',
                'order': 17,
                'condition': 'force_negativo'
            },
            
            # ============ CATEGORÍA 18: OBV ============
            'obv_alcista': {
                'template': 'OBV marca máximos crecientes, anticipando el movimiento del precio y confirmando acumulación. ',
                'type': 'flujo_dinero',
                'order': 18,
                'condition': 'obv_alcista'
            },
            'obv_bajista': {
                'template': 'OBV en tendencia decreciente adelanta la distribución institucional antes de que se refleje en precio. ',
                'type': 'flujo_dinero',
                'order': 18,
                'condition': 'obv_bajista'
            },
            
            # ============ CATEGORÍA 19: VOLUMEN Y BALLENAS ============
            'volumen_alto': {
                'template': 'Volumen {volumen_relativo}x superior al promedio confirma participación institucional significativa. ',
                'type': 'volumen_ballenas',
                'order': 19,
                'condition': 'volumen_alto'
            },
            'volumen_muy_alto': {
                'template': 'Volumen {volumen_relativo}x superior al promedio, con patrones de absorción típicos de acumulación institucional. ',
                'type': 'volumen_ballenas',
                'order': 19,
                'condition': 'volumen_muy_alto'
            },
            'volumen_insuficiente': {
                'template': 'Volumen insuficiente ({volumen_relativo}x) no respalda la validez del movimiento actual. ',
                'type': 'riesgo',
                'order': 19,
                'condition': 'volumen_bajo'
            },
            'ballenas_compra': {
                'template': '🐋 BALLENAS COMPRANDO: Señal {tipo_ballena} con fuerza {fuerza_ballena} en las últimas {velas_ballena} velas. ',
                'type': 'volumen_ballenas',
                'order': 19,
                'condition': 'ballenas_compra'
            },
            'ballenas_venta': {
                'template': '🐋 BALLENAS VENDIENDO: Señal de distribución detectada con fuerza {fuerza_ballena}. ',
                'type': 'volumen_ballenas',
                'order': 19,
                'condition': 'ballenas_venta'
            },
            'iceberg_acumulacion': {
                'template': 'Operativa iceberg de acumulación: {velas_consecutivas} velas con volumen alto y precio estable. ',
                'type': 'volumen_ballenas',
                'order': 19,
                'condition': 'iceberg_acumulacion'
            },
            'iceberg_distribucion': {
                'template': 'Operativa iceberg de distribución detectada, sugiriendo ventas institucionales sin alterar bruscamente el precio. ',
                'type': 'volumen_ballenas',
                'order': 19,
                'condition': 'iceberg_distribucion'
            },
            
            # ============ CATEGORÍA 20: ESTRUCTURA DE PRECIO ============
            'soporte_historico': {
                'template': 'El precio respeta soporte histórico en {nivel_soporte}, probado en múltiples ocasiones. ',
                'type': 'estructura',
                'order': 20,
                'condition': 'soporte_cercano'
            },
            'resistencia_historica': {
                'template': 'Resistencia clave en {nivel_resistencia} ha sido probada repetidamente sin ser superada. ',
                'type': 'estructura',
                'order': 20,
                'condition': 'resistencia_cercana'
            },
            'soporte_multiple': {
                'template': 'Confluencia de soportes: {nivel_soporte} coincide con EMA 200 ({ema200}) y Fibonacci 0.618 ({fib_618}). ',
                'type': 'estructura',
                'order': 20,
                'condition': 'soporte_cercano'
            },
            'resistencia_multiple': {
                'template': 'Múltiples resistencias confluyen en {nivel_resistencia}: EMA 50 ({ema50}) y Fibonacci 0.618 ({fib_618}). ',
                'type': 'estructura',
                'order': 20,
                'condition': 'resistencia_cercana'
            },
            
            # ============ CATEGORÍA 21: PATRONES DE VELAS (COMPLETA) ============
            'patron_martillo': {
                'template': 'Martillo en zona de soporte: vela con mecha inferior larga, señal de rechazo a caídas. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_martillo'
            },
            'patron_martillo_invertido': {
                'template': 'Martillo invertido sugiere posible agotamiento vendedor y giro alcista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_martillo_invertido'
            },
            'patron_estrella_fugaz': {
                'template': 'Estrella fugaz en resistencia: vela con mecha superior larga, indicando rechazo a subidas. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_estrella_fugaz'
            },
            'patron_colgado': {
                'template': 'Hombre colgado en zona de resistencia sugiere posible agotamiento comprador. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_colgado'
            },
            'patron_doji': {
                'template': 'Doji de indecisión refleja equilibrio entre compradores y vendedores. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_doji'
            },
            'patron_marubozu_alcista': {
                'template': 'Marubozu alcista de {tipo_patron} velas con {confianza_patron}% de confiabilidad, confirmando fortaleza compradora. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_marubozu_alcista'
            },
            'patron_marubozu_bajista': {
                'template': 'Marubozu bajista detectado con {confianza_patron}% de confiabilidad, indicando fuerte presión vendedora. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_marubozu_bajista'
            },
            'patron_vela_larga_blanca': {
                'template': 'Vela larga blanca indica fuerte presión compradora. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_vela_larga_blanca'
            },
            'patron_vela_larga_negra': {
                'template': 'Vela larga negra indica fuerte presión vendedora. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_vela_larga_negra'
            },
            'patron_envolvente_alcista': {
                'template': 'Patrón envolvente alcista completado, con vela alcista que engloba la vela bajista previa. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_envolvente_alcista'
            },
            'patron_envolvente_bajista': {
                'template': 'Patrón envolvente bajista detectado: vela bajista engloba la vela alcista anterior. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_envolvente_bajista'
            },
            'patron_harami_alcista': {
                'template': 'Harami alcista de {tipo_patron} velas con {confianza_patron}% de confiabilidad, anticipando giro alcista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_harami_alcista'
            },
            'patron_harami_bajista': {
                'template': 'Harami bajista de reversión con {confianza_patron}% de confiabilidad. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_harami_bajista'
            },
            'patron_tweezer_fondo': {
                'template': 'Tweezer bottom en soporte sugiere posible reversión alcista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tweezer_fondo'
            },
            'patron_tweezer_techo': {
                'template': 'Tweezer top en resistencia anticipa posible giro bajista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tweezer_techo'
            },
            'patron_estrella_matutina': {
                'template': 'Estrella matutina completada: señal de reversión alcista con {confianza_patron}% confiabilidad. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_estrella_matutina'
            },
            'patron_estrella_vespertina': {
                'template': 'Estrella vespertina en techo de mercado, señal de reversión bajista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_estrella_vespertina'
            },
            'patron_tres_soldados': {
                'template': 'Tres soldados blancos consecutivos confirman fortaleza alcista sostenida. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tres_soldados'
            },
            'patron_tres_cuervos': {
                'template': 'Tres cuervos negros consecutivos confirman presión vendedora sostenida. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tres_cuervos'
            },
            'patron_tres_dentro_arriba': {
                'template': 'Tres dentro arriba: patrón de continuación alcista de alta confiabilidad. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tres_dentro_arriba'
            },
            'patron_tres_dentro_abajo': {
                'template': 'Tres dentro abajo: señal de continuación bajista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tres_dentro_abajo'
            },
            'patron_tres_fuera_arriba': {
                'template': 'Tres fuera arriba confirma fortaleza alcista con volumen creciente. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tres_fuera_arriba'
            },
            'patron_tres_fuera_abajo': {
                'template': 'Tres fuera abajo indica aceleración de la presión vendedora. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_tres_fuera_abajo'
            },
            'patron_hch': {
                'template': 'Hombro cabeza hombro completado, señal de reversión bajista con proyección de {proyeccion}%. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_hch'
            },
            'patron_hch_invertido': {
                'template': 'HCH invertido completado, anticipando giro alcista con proyección de {proyeccion}%. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_hch_invertido'
            },
            'patron_doble_suelo': {
                'template': 'Doble suelo confirmado en {nivel_soporte} con proyección de {proyeccion}%. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_doble_suelo'
            },
            'patron_doble_techo': {
                'template': 'Doble techo en {nivel_resistencia} anticipa caída con proyección de {proyeccion}%. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_doble_techo'
            },
            'patron_triple_suelo': {
                'template': 'Triple suelo en soporte, señal de acumulación con alta confiabilidad. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_triple_suelo'
            },
            'patron_triple_techo': {
                'template': 'Triple techo en resistencia, indicando agotamiento comprador. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_triple_techo'
            },
            'patron_bandera_alcista': {
                'template': 'Bandera alcista en formación, típica de continuación tras fuerte movimiento. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_bandera_alcista'
            },
            'patron_bandera_bajista': {
                'template': 'Bandera bajista sugiere continuación de la presión vendedora. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_bandera_bajista'
            },
            'patron_banderin_alcista': {
                'template': 'Banderín alcista con volatilidad decreciente, anticipando explosión al alza. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_banderin_alcista'
            },
            'patron_banderin_bajista': {
                'template': 'Banderín bajista precedido de fuerte caída, señal de continuación. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_banderin_bajista'
            },
            'patron_cuna_ascendente': {
                'template': 'Cuña ascendente en resistencia, patrón de reversión bajista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_cuna_ascendente'
            },
            'patron_cuna_descendente': {
                'template': 'Cuña descendente en soporte, anticipando posible giro alcista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_cuna_descendente'
            },
            'patron_triangulo_ascendente': {
                'template': 'Triángulo ascendente con resistencia plana y soportes crecientes, señal alcista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_triangulo_ascendente'
            },
            'patron_triangulo_descendente': {
                'template': 'Triángulo descendente con soporte plano y resistencias decrecientes, señal bajista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_triangulo_descendente'
            },
            'patron_triangulo_simetrico': {
                'template': 'Triángulo simétrico en compresión, esperando ruptura direccional. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_triangulo_simetrico'
            },
            'patron_taza_mango': {
                'template': 'Taza con asa completada, patrón de continuación alcista de alta fiabilidad. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_taza_mango'
            },
            'patron_generico_alcista': {
                'template': 'Se ha completado un patrón {nombre_patron} de {tipo_patron} velas con {confianza_patron}% de confiabilidad, anticipando un giro alcista. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_alcista'
            },
            'patron_generico_bajista': {
                'template': 'La configuración de velas reciente muestra un patrón {nombre_patron} de reversión bajista con {confianza_patron}% de confiabilidad. ',
                'type': 'patrones',
                'order': 21,
                'condition': 'patron_bajista'
            },
            
            # ============ CATEGORÍA 22: SMART MONEY ============
            'order_block_alcista': {
                'template': 'Order Block alcista institucional en {nivel_order_block}, zona donde previamente se absorbió oferta con volumen {volumen_ob}% superior al promedio. ',
                'type': 'smart_money',
                'order': 22,
                'condition': 'order_block_alcista'
            },
            'order_block_bajista': {
                'template': 'Order Block bajista actuando como resistencia en {nivel_order_block}, área de distribución institucional previa. ',
                'type': 'smart_money',
                'order': 22,
                'condition': 'order_block_bajista'
            },
            'fvg_alcista': {
                'template': 'Fair Value Gap alcista sin rellenar entre {fvg_inferior} y {fvg_superior}, actuando como soporte dinámico. ',
                'type': 'smart_money',
                'order': 22,
                'condition': 'fvg_alcista'
            },
            'fvg_bajista': {
                'template': 'FVG bajista sin rellenar entre {fvg_inferior} y {fvg_superior}, zona que probablemente será revisitada. ',
                'type': 'smart_money',
                'order': 22,
                'condition': 'fvg_bajista'
            },
            'liquidity_sweep_alcista': {
                'template': 'Liquidity sweep en mínimos previos ({nivel_sweep}) seguido de reversión alcista, típico de acumulación institucional. ',
                'type': 'smart_money',
                'order': 22,
                'condition': 'liquidity_sweep_alcista'
            },
            'liquidity_sweep_bajista': {
                'template': 'Liquidity sweep en máximos ({nivel_sweep}) con posterior caída, patrón de distribución institucional. ',
                'type': 'smart_money',
                'order': 22,
                'condition': 'liquidity_sweep_bajista'
            },
            
            # ============ CATEGORÍA 23: PERFIL DE VOLUMEN ============
            'poc_soporte': {
                'template': 'POC en {poc_price} actuando como soporte, con Value Area entre {val_price} y {vah_price}. ',
                'type': 'perfil_volumen',
                'order': 23,
                'condition': 'cerca_poc'
            },
            'poc_resistencia': {
                'template': 'POC en {poc_price} actuando como resistencia, zona de máximo volumen. ',
                'type': 'perfil_volumen',
                'order': 23,
                'condition': 'cerca_poc'
            },
            'value_area_aceptacion': {
                'template': 'Precio dentro de Value Area ({val_price} - {vah_price}), indicando aceptación de precios y equilibrio. ',
                'type': 'perfil_volumen',
                'order': 23,
                'condition': 'perfil_dentro_valor'
            },
            'value_area_ruptura': {
                'template': 'Precio fuera de Value Area ({price_position}) con volumen creciente, confirmando dirección. ',
                'type': 'perfil_volumen',
                'order': 23,
                'condition': 'fuera_de_valor'
            },
            
            # ============ CATEGORÍA 24: FIBONACCI ============
            'fibonacci_618': {
                'template': 'Nivel Fibonacci 0.618 ({fib_618}) actuando como soporte/resistencia, zona de alta probabilidad. ',
                'type': 'fibonacci',
                'order': 24,
                'condition': 'fib_0_618'
            },
            'fibonacci_382': {
                'template': 'Fibonacci 0.382 ({fib_382}) coincide con zona de retroceso superficial. ',
                'type': 'fibonacci',
                'order': 24,
                'condition': 'fib_0_382'
            },
            'fibonacci_extension': {
                'template': 'Extensión Fibonacci 1.618 ({fib_1618}) como objetivo principal del movimiento. ',
                'type': 'fibonacci',
                'order': 24,
                'condition': ''
            },
            
            # ============ CATEGORÍA 25: VOLATILIDAD ============
            'atr_alto': {
                'template': 'ATR en {atr_pct}% refleja alta volatilidad, con rangos de movimiento superiores al promedio. ',
                'type': 'volatilidad',
                'order': 25,
                'condition': 'atr_alto'
            },
            'atr_bajo': {
                'template': 'ATR en {atr_pct}% indica baja volatilidad, típica de fases de consolidación. ',
                'type': 'volatilidad',
                'order': 25,
                'condition': 'atr_bajo'
            },
            'atr_extremo': {
                'template': 'VOLATILIDAD EXTREMA: ATR en {atr_pct}% supera niveles habituales, aumentando riesgo de stops cazados. ',
                'type': 'riesgo',
                'order': 25,
                'condition': 'atr_extremo'
            },
            'bb_squeeze': {
                'template': 'Bandas de Bollinger en máxima contracción (squeeze), anticipando expansión inminente. ',
                'type': 'volatilidad',
                'order': 25,
                'condition': 'squeeze_on'
            },
            'bb_touch_superior': {
                'template': 'Precio tocando banda superior de Bollinger, indicando fuerza pero también posible extensión. ',
                'type': 'volatilidad',
                'order': 25,
                'condition': 'bb_touch_superior'
            },
            'bb_touch_inferior': {
                'template': 'Precio en banda inferior de Bollinger, sugiriendo sobreventa y posible rebote. ',
                'type': 'volatilidad',
                'order': 25,
                'condition': 'bb_touch_inferior'
            },
            
          
            # ============ CATEGORÍA 27: SESIONES ============
            'sesion_americana': {
                'template': 'Sesión americana con máxima liquidez y participación institucional, momento de mayor fiabilidad. ',
                'type': 'sesiones',
                'order': 27,
                'condition': 'sesion_americana'
            },
            'sesion_europea': {
                'template': 'Sesión europea con buena liquidez, comenzando a definir la dirección del día. ',
                'type': 'sesiones',
                'order': 27,
                'condition': 'sesion_europea'
            },
            'sesion_asiatica': {
                'template': 'SESIÓN ASIÁTICA: Liquidez reducida y movimientos erráticos. Señales con menor fiabilidad. ',
                'type': 'precaucion',
                'order': 27,
                'condition': 'sesion_asiatica'
            },
            'cierre_semanal': {
                'template': 'CIERRE SEMANAL: Alta probabilidad de toma de ganancias y distorsión de señales técnicas. ',
                'type': 'precaucion',
                'order': 27,
                'condition': 'viernes'
            },
                        'precaucion_liquidez_baja': {
                'template': 'LIQUIDEZ BAJA: Volumen reducido puede magnificar movimientos y generar señales falsas. ',
                'type': 'precaucion',
                'order': 27,
                'condition': 'liquidez_baja'
            },
            
            # ============ CATEGORÍA 28: CONFIRMACIÓN (AGREGAR) ============
            'confirmacion_pendiente': {
                'template': 'CONFIRMACIÓN PENDIENTE: La señal requiere validación con volumen y cierre fuera de rango. ',
                'type': 'confirmacion',
                'order': 28,
                'condition': 'confirmacion_pendiente'
            },
            'confirmacion_esperar_velas': {
                'template': 'SE REQUIEREN {wait_bars} VELA(S) DE CONFIRMACIÓN: Esperar cierre fuera del rango para validar. ',
                'type': 'confirmacion',
                'order': 28,
                'condition': 'requiere_espera'
            },
            'confirmacion_falso_breakout_alcista': {
                'template': 'FALSO BREAKOUT ALCISTA: Precio superó {breakout_level} pero cerró dentro del rango. Posible trampa para toros. ',
                'type': 'confirmacion',
                'order': 28,
                'condition': 'falso_breakout_alcista'
            },
            'confirmacion_falso_breakdown_bajista': {
                'template': 'FALSO BREAKDOWN BAJISTA: Precio perforó {breakout_level} pero cerró por encima. Posible trampa para osos. ',
                'type': 'confirmacion',
                'order': 28,
                'condition': 'falso_breakdown_bajista'
            },
            
            # ============ CATEGORÍA 29: RIESGO ESPECÍFICO ============
            'riesgo_adx_bajo': {
                'template': 'MERCADO SIN DIRECCIÓN: ADX en {adx_valor} por debajo de 20, fase lateral con señales falsas. ',
                'type': 'riesgo',
                'order': 29,
                'condition': 'adx_bajo'
            },
            'riesgo_ftm_no_trade': {
                'template': 'FTMaverick en ZONA DE NO OPERACIÓN: ancho de banda alto pero decreciente, entorno propenso a whipsaws. ',
                'type': 'riesgo',
                'order': 29,
                'condition': 'ftm_no_trade'
            },
            'riesgo_indecision': {
                'template': 'PATRONES DE INDECISIÓN: Múltiples velas de indecisión reflejan equilibrio compra/venta. ',
                'type': 'riesgo',
                'order': 29,
                'condition': 'indecision'
            },
            'riesgo_sobrecompra': {
                'template': 'Múltiples osciladores en sobrecompra ({rsi_valor} RSI, {stoch_k} Estocástico), posible corrección. ',
                'type': 'riesgo',
                'order': 29,
                'condition': 'rsi_sobrecompra'
            },
            'riesgo_sobreventa': {
                'template': 'Osciladores en sobreventa sugieren posible rebote, pero requieren confirmación. ',
                'type': 'riesgo',
                'order': 29,
                'condition': 'rsi_sobreventa'
            },
            
            # ============ CATEGORÍA 30: ACTIVO (ANÁLISIS POR PAR) ============
            'activo_btc_dominante': {
                'template': 'Bitcoin lidera el movimiento del mercado, con ADX {adx_valor} arrastrando al resto de criptoactivos. ',
                'type': 'activo',
                'order': 30,
                'condition': 'trend_bullish'
            },
            'activo_btc_debil': {
                'template': 'Bitcoin muestra debilidad (ADX {adx_valor} con -DI {minus_di} dominante), arrastrando mercado a la baja. ',
                'type': 'activo',
                'order': 30,
                'condition': 'trend_bearish'
            },
            'activo_paxg_refugio': {
                'template': 'PAXG mantiene condición de refugio, con menor volatilidad (ATR {atr_pct}%) y correlación inversa. ',
                'type': 'activo',
                'order': 30,
                'condition': 'trend_bullish'
            },
            'activo_paxg_debil': {
                'template': 'PAXG pierde condición de refugio, correlacionándose con mercados de riesgo. ',
                'type': 'activo',
                'order': 30,
                'condition': 'trend_bearish'
            },
            
            # ============ CATEGORÍA 31: REFLEXIÓN DE ACCIÓN ============
            'reflexion_compra_oportunidad': {
                'template': 'Confluencia de factores presenta oportunidad de acumulación con relación riesgo/beneficio 1:{risk_reward}. ',
                'type': 'reflexion',
                'order': 31,
                'condition': 'COMPRA_SPOT OR LONG'
            },
            'reflexion_venta_oportunidad': {
                'template': 'Niveles de resistencia y agotamiento comprador ofrecen oportunidad de toma de ganancias. ',
                'type': 'reflexion',
                'order': 31,
                'condition': 'VENTA_SPOT OR SHORT'
            },
            'reflexion_esperar_pullback': {
                'template': 'Se recomienda esperar retroceso a {nivel_soporte} para mejorar relación riesgo/beneficio. ',
                'type': 'reflexion',
                'order': 31,
                'condition': 'ESPERAR'
            },
            'reflexion_': {
                'template': 'Falta de señales claras y condiciones actuales recomiendan mantenerse al margen. ',
                'type': 'reflexion',
                'order': 31,
                'condition': ''
            },
            'reflexion_caution': {
                'template': 'Elevada volatilidad (ATR {atr_pct}%) aconseja reducir tamaño y ajustar stops. ',
                'type': 'reflexion',
                'order': 31,
                'condition': 'CAUTION'
            },
            
            # ============ CATEGORÍA 32: RECOMENDACIONES ============
            'recomendacion_compra_spot_btc_usdt': {
                'template': 'Por tanto, se recomienda COMPRA SPOT de Bitcoin. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_venta_spot_btc_usdt': {
                'template': 'Se recomienda VENTA SPOT de Bitcoin. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_long_btc_usdt': {
                'template': 'Se propone LONG FUTURES de Bitcoin. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_short_btc_usdt': {
                'template': 'Se plantea SHORT FUTURES de Bitcoin. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_compra_spot_paxg_usdt': {
                'template': 'Se aconseja COMPRA SPOT de PAXG. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_venta_spot_paxg_usdt': {
                'template': 'Se sugiere VENTA SPOT de PAXG. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_compra_spot_paxg_btc': {
                'template': 'Se recomienda COMPRA del ratio PAXG/BTC. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_venta_spot_paxg_btc': {
                'template': 'Se aconseja VENTA del ratio PAXG/BTC. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_': {
                'template': 'La prudencia aconseja NO OPERAR en estos niveles. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_esperar': {
                'template': 'Se recomienda ESPERAR, manteniendo liquidez. ',
                'type': 'recomendacion',
                'order': 32
            },
            'recomendacion_caution': {
                'template': 'Se sugiere PRUDENCIA, reduciendo exposición. ',
                'type': 'recomendacion',
                'order': 32
            },
            
            # ============ CATEGORÍA 33: CIERRE ============
            'cierre_timestamp': {
                'template': '\n\n{timestamp} Hora Bolivia',
                'type': 'cierre',
                'order': 33
            },
            # ============ NUEVAS PLANTILLAS PARA SENTIMIENTO (CATEGORÍA 34) ============
            'sentimiento_oportunidad_panico': {
                'template': 'El Fear & Greed Index muestra {fear_greed_value} puntos ({fear_greed_classification}), pero con tendencia alcista de {fear_greed_trend_7d}% en los últimos 7 días, indicando que el pánico está cediendo. ',
                'type': 'sentimiento',
                'order': 34,
                'condition': 'sentiment_bullish_opportunity'
            },
            'sentimiento_oportunidad_euforia': {
                'template': 'El Fear & Greed Index muestra {fear_greed_value} puntos ({fear_greed_classification}) con tendencia bajista de {fear_greed_trend_7d}% en la última semana, señal de agotamiento comprador. ',
                'type': 'sentimiento',
                'order': 34,
                'condition': 'sentiment_bearish_opportunity'
            },
            'sentimiento_acumulacion_miedo': {
                'template': 'Fear & Greed en zona de miedo ({fear_greed_value}) con tendencia mejorando ({fear_greed_trend_7d}% ), oportunidad de acumulación gradual. ',
                'type': 'sentimiento',
                'order': 34,
                'condition': 'sentiment_bullish_moderate'
            },
            'sentimiento_toma_ganancias': {
                'template': 'Avaricia moderada ({fear_greed_value}) con tendencia a la baja ({fear_greed_trend_7d}%), momento de tomar ganancias parciales. ',
                'type': 'sentimiento',
                'order': 34,
                'condition': 'sentiment_bearish_moderate'
            },
            'sentimiento_cautela_extrema': {
                'template': '{fear_greed_classification} ({fear_greed_value}) persistente con tendencia {fear_greed_trend_7d}%, recomienda máxima cautela. ',
                'type': 'sentimiento',
                'order': 34,
                'condition': 'sentiment_bullish_caution OR sentiment_bearish_caution'
            },
            'sentimiento_contexto': {
                'template': 'El sentimiento de mercado se encuentra en {fear_greed_classification} ({fear_greed_value}) con volatilidad de {fear_greed_volatility} puntos en 30 días. ',
                'type': 'sentimiento',
                'order': 34,
                'condition': 'sentiment_bullish_opportunity OR sentiment_bearish_opportunity OR sentiment_bullish_moderate OR sentiment_bearish_moderate'
            },
            
            # ============ NUEVAS PLANTILLAS PARA MULTIFRAME (CATEGORÍA 35) ============
            'multiframe_alineacion_alcista_completa': {
                'template': 'Todas las temporalidades ({tfs}) muestran alineación alcista, aumentando probabilidad de éxito. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'alineacion_bullish_completa'
            },
            'multiframe_alineacion_bajista_completa': {
                'template': 'Todas las temporalidades ({tfs}) muestran alineación bajista, confirmando presión vendedora. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'alineacion_bearish_completa'
            },
            'multiframe_pullback_oportunidad': {
                'template': 'Tendencia superior ({tf_superior}) {direccion_superior} con corrección en {tf_actual}, oportunidad de entrada en retroceso. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'pullback_oportunidad'
            },
            'multiframe_conflicto_menor_muestra_debilidad': {
                'template': 'Tendencia superior ({tf_superior}) {direccion_superior} pero {tf_inferior} muestra debilidad, reducir tamaño de operación. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'conflicto_menor_muestra_debilidad'
            },
            'multiframe_conflicto_mayor_advierta_cambio': {
                'template': 'Tendencia superior ({tf_superior}) {direccion_superior} pero temporalidades inferiores ya giraron, posible cambio inminente. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'conflicto_mayor_advierta_cambio'
            },
            'multiframe_acumulacion_en_zona_bajista': {
                'template': 'Tendencia superior bajista pero en soporte histórico (EMA200), acumulación estratégica para spot. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'acumulacion_en_zona_bajista'
            },
            'multiframe_distribucion_en_zona_alcista': {
                'template': 'Tendencia superior alcista pero en zona de resistencia, tomar ganancias parciales. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'distribucion_en_zona_alcista'
            },
            'multiframe_ruptura_confirmada': {
                'template': 'Temporalidades superiores laterales pero {tf_actual} rompiendo, posible inicio de tendencia. ',
                'type': 'multiframe',
                'order': 35,
                'condition': 'ruptura_confirmada'
            },
            
            # ============ NUEVAS PLANTILLAS PARA BOLLINGER (CATEGORÍA 36) ============
            'bollinger_squeeze_alcista': {
                'template': 'Bandas de Bollinger en máxima contracción (squeeze) de {squeeze_length} velas con ruptura alcista, anticipando expansión de volatilidad. ',
                'type': 'bollinger',
                'order': 36,
                'condition': 'squeeze_alcista'
            },
            'bollinger_squeeze_bajista': {
                'template': 'Bandas de Bollinger en squeeze de {squeeze_length} velas con ruptura bajista, anticipando expansión a la baja. ',
                'type': 'bollinger',
                'order': 36,
                'condition': 'squeeze_bajista'
            },
            'bollinger_band_walk_alcista': {
                'template': 'Precio caminando sobre banda superior de Bollinger con volumen, tendencia fuerte confirmada. ',
                'type': 'bollinger',
                'order': 36,
                'condition': 'band_walk_alcista'
            },
            'bollinger_band_walk_bajista': {
                'template': 'Precio caminando bajo banda inferior de Bollinger, tendencia bajista sostenida. ',
                'type': 'bollinger',
                'order': 36,
                'condition': 'band_walk_bajista'
            },
            'bollinger_expansion': {
                'template': 'Expansión brusca de volatilidad (ancho de banda {bb_width:.1f}%), confirmando dirección del movimiento. ',
                'type': 'bollinger',
                'order': 36,
                'condition': 'expansion_volatilidad'
            },
            
            # ============ NUEVAS PLANTILLAS PARA PERFIL VOLUMEN (CATEGORÍA 37) ============
            'perfil_hvn_soporte': {
                'template': 'High Volume Node en ${hvn_level:.2f} actuando como soporte, con volumen {hvn_volume}% superior al promedio. ',
                'type': 'perfil_volumen',
                'order': 37,
                'condition': 'hvn_soporte'
            },
            'perfil_hvn_resistencia': {
                'template': 'High Volume Node en ${hvn_level:.2f} actuando como resistencia, zona de distribución institucional. ',
                'type': 'perfil_volumen',
                'order': 37,
                'condition': 'hvn_resistencia'
            },
            'perfil_lvn_rotura': {
                'template': 'Low Volume Node roto con volumen {volume_ratio:.1f}x, movimiento rápido esperado. ',
                'type': 'perfil_volumen',
                'order': 37,
                'condition': 'lvn_rotura'
            },
            'perfil_poc_confluencia': {
                'template': 'Confluencia de POC (${poc_price:.2f}) con EMA50, zona de alta probabilidad. ',
                'type': 'perfil_volumen',
                'order': 37,
                'condition': 'poc_vwap_confluencia'
            },
            
            # ============ NUEVAS PLANTILLAS PARA STOP HUNTS (CATEGORÍA 38) ============
            'stop_hunt_long': {
                'template': 'Stop hunt alcista detectado en ${stop_hunt_level:.2f}: precio perforó soporte y revertió con volumen, caza de stops completada. ',
                'type': 'stop_hunt',
                'order': 38,
                'condition': 'stop_hunt_long'
            },
            'stop_hunt_short': {
                'template': 'Stop hunt bajista detectado en ${stop_hunt_level:.2f}: precio rompió resistencia y cayó con volumen, distribución institucional. ',
                'type': 'stop_hunt',
                'order': 38,
                'condition': 'stop_hunt_short'
            },
            'stop_hunt_ob': {
                'template': 'Stop hunt en zona de Order Block, entrada de alta probabilidad con volumen de absorción. ',
                'type': 'stop_hunt',
                'order': 38,
                'condition': 'stop_hunt_ob'
            },
             # ============ NUEVAS PLANTILLAS PARA CORRELACIÓN (CATEGORÍA 39) ============
            'correlacion_btc_mas_fuerte': {
                'template': 'Bitcoin muestra mayor fortaleza relativa que el oro, con ADX {btc_adx:.1f} frente a {paxg_adx:.1f} de PAXG. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'BTC_STRONGER'
            },
            'correlacion_paxg_mas_fuerte': {
                'template': 'El oro muestra mayor fortaleza relativa que Bitcoin, con ADX {paxg_adx:.1f} frente a {btc_adx:.1f} de BTC. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'PAXG_STRONGER'
            },
            'correlacion_btc_alcista_unilateral': {
                'template': 'Bitcoin presenta tendencia alcista independiente (ADX {btc_adx:.1f}) sin correlación clara con el oro. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'BTC_BULLISH'
            },
            'correlacion_btc_bajista_unilateral': {
                'template': 'Bitcoin presenta tendencia bajista independiente (ADX {btc_adx:.1f}) sin correlación clara con el oro. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'BTC_BEARISH'
            },
            'correlacion_ratio_alcista': {
                'template': 'El ratio PAXG/BTC muestra tendencia alcista (ADX {ratio_adx:.1f}), indicando fortalecimiento del oro frente a Bitcoin. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'RATIO_BULLISH'
            },
            'correlacion_ratio_bajista': {
                'template': 'El ratio PAXG/BTC muestra tendencia bajista (ADX {ratio_adx:.1f}), indicando debilidad del oro frente a Bitcoin. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'RATIO_BEARISH'
            },
            # ============ PLANTILLAS PARA NO ROTACIÓN (CATEGORÍA 39) ============
            'correlacion_neutral_por_conflicto': {
                'template': 'No hay rotación clara: BTC y el ratio muestran tendencias opuestas sin dominancia definida. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'rotation_signal == "NEUTRAL" AND btc_trend != ratio_trend'
            },
            'correlacion_neutral_por_debilidad': {
                'template': 'No hay rotación clara: ambos activos muestran tendencias débiles (ADX < 20). ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'rotation_signal == "NEUTRAL" AND btc_adx < 20 AND ratio_adx < 20'
            },
            'correlacion_neutral_por_decisiones': {
                'template': 'Sin rotación definida: las decisiones de los traders en BTC y el ratio no muestran consenso direccional. ',
                'type': 'correlacion',
                'order': 39,
                'condition': 'rotation_signal == "NEUTRAL"'
            },
            # ============ NUEVAS PLANTILLAS PARA LIQUIDACIONES (CATEGORÍA 40) ============
            'liquidation_bullish_opportunity': {
                'template': 'LIQUIDACIONES: {total_short_below:.1f}M en SHORT por debajo de ${price:.2f}, posible squeeze alcista. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'liquidation_bullish_opportunity'
            },
            'liquidation_bearish_opportunity': {
                'template': 'LIQUIDACIONES: {total_long_above:.1f}M en LONG por encima de ${price:.2f}, probable atracción bajista. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'liquidation_bearish_opportunity'
            },
            'liquidity_grab_long_confirmed': {
                'template': 'CAZA DE LIQUIDEZ ALCISTA: Precio barrió {volume_liquidated:.1f}M en LONG en ${price:.2f} y revertió con volumen. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'liquidity_grab_long'
            },
            'liquidity_grab_short_confirmed': {
                'template': 'CAZA DE LIQUIDEZ BAJISTA: Precio barrió {volume_liquidated:.1f}M en SHORT en ${price:.2f} y cayó con volumen. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'liquidity_grab_short'
            },
            'high_density_support': {
                'template': 'SOPORTE DE ALTA PROBABILIDAD: Zona de alta densidad de liquidaciones en ${support:.2f} no tocada. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'high_density_support'
            },
            'high_density_resistance': {
                'template': 'RESISTENCIA DE ALTA PROBABILIDAD: Gran cluster de liquidaciones en ${resistance:.2f}. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'high_density_resistance'
            },
            'liquidity_sweep_bounce': {
                'template': 'REBOTE TRAS BARRIDO: Precio limpió {bins_cleared} zonas de liquidez, posible reversión. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'liquidity_sweep_bounce'
            },
            'spike_accumulation': {
                'template': 'ACUMULACIÓN DE SPIKES: {spike_count} eventos de alta actividad en {hours}h, acumulando {total_weight:.1f}M. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'spike_accumulation'
            },
            'liquidity_warning': {
                'template': 'ALERTA DE LIQUIDEZ: Precio en zona de baja densidad entre clusters, posible movimiento rápido. ',
                'type': 'liquidaciones',
                'order': 40,
                'condition': 'liquidity_warning'
            }
        }
    # === FIN _initialize_justification_bank ===
    # ========================================================================
    # SISTEMA DE SELECCIÓN INTELIGENTE DE PLANTILLAS
    # ========================================================================
    
    def seleccionar_plantillas_por_condiciones(self, decision, symbol, timeframe, 
                                              trend, momentum, volatility, volume, 
                                              structure, correlation, market_hours, 
                                              confirmation, estrategias_consenso, sentiment,
                                              liquidation):  # <--- NUEVO PARÁMETRO
        """
        Selecciona MÚLTIPLES plantillas por categoría FILTRADAS POR COHERENCIA con la decisión.
        VERSIÓN COMPLETA CON TODAS LAS CATEGORÍAS DE NO OPERAR
        """
        try:
            # ============ 1. MAPA DE CONDICIONES ACTIVAS ============
            condiciones_activas = self._mapear_condiciones_activas(
                decision, symbol, timeframe, trend, momentum, volatility, volume,
                structure, correlation, market_hours, confirmation, estrategias_consenso, sentiment,
                liquidation  # <--- DEBE ESTAR
            )
            
            print(f"\n{'='*60}")
            print(f"📊 SELECCIÓN DE PLANTILLAS para {decision} {symbol} {timeframe}")
            print(f"{'='*60}")
            print(f"📊 Condiciones activas totales: {len(condiciones_activas)}")
            if len(condiciones_activas) > 0:
                print(f"   Primeras 10: {condiciones_activas[:10]}")
            
            # ============ 2. OBTENER DIRECCIÓN REAL DEL DMI ============
            direccion_real = 'neutral'
            plus_di = 0
            minus_di = 0
            adx_valor = 0
            dmi_diff = 0
            
            if trend and isinstance(trend, dict):
                plus_di = trend.get('plus_di', 0)
                minus_di = trend.get('minus_di', 0)
                adx_valor = trend.get('adx', 0) #S e cambio adx_value
                dmi_diff = abs(plus_di - minus_di)
                
                if plus_di > minus_di and dmi_diff > 5:
                    direccion_real = 'bullish'
                    print(f"   📈 DMI: +DI={plus_di:.1f} > -DI={minus_di:.1f} → ALCISTA")
                elif minus_di > plus_di and dmi_diff > 5:
                    direccion_real = 'bearish'
                    print(f"   📉 DMI: -DI={minus_di:.1f} > +DI={plus_di:.1f} → BAJISTA")
                else:
                    direccion_real = trend.get('direction', 'neutral')
                    print(f"   ⚖️ DMI: +DI={plus_di:.1f}, -DI={minus_di:.1f} → {direccion_real.upper()}")
            
            # ============ 3. DETECTAR SEÑALES DE CAMBIO DE TENDENCIA ============
            hay_cambio_tendencia = False
            razon_cambio = ""
            
            if 'psar_alcista_contra_tendencia' in condiciones_activas:
                hay_cambio_tendencia = True
                razon_cambio = "Parabolic SAR alcista contra tendencia"
                print(f"🔄 DETECTADO: {razon_cambio}")
            elif 'psar_bajista_contra_tendencia' in condiciones_activas:
                hay_cambio_tendencia = True
                razon_cambio = "Parabolic SAR bajista contra tendencia"
                print(f"🔄 DETECTADO: {razon_cambio}")
            elif 'ema_cross_bull' in condiciones_activas and direccion_real == 'bearish':
                hay_cambio_tendencia = True
                razon_cambio = "Cruce alcista de EMAs contra tendencia"
                print(f"🔄 DETECTADO: {razon_cambio}")
            elif 'divergencia_alcista' in condiciones_activas and direccion_real == 'bearish':
                hay_cambio_tendencia = True
                razon_cambio = "Divergencia alcista en mercado bajista"
                print(f"🔄 DETECTADO: {razon_cambio}")
            
            # ============ 4. FILTRAR CONDICIONES POR DECISIÓN ============
            condiciones_filtradas = []
            
            # Definir palabras clave según la decisión
            if decision in ['COMPRA_SPOT', 'LONG']:
                # Para compras, SOLO condiciones alcistas o neutrales
                palabras_prohibidas = ['bajista', 'venta', 'bear', 'negativo', 'resistencia', 'sobrecompra', 'distribution', 'sobrecomprado', 'no_trade']
                for cond in condiciones_activas:
                    if not any(p in cond.lower() for p in palabras_prohibidas):
                        condiciones_filtradas.append(cond)
                    else:
                        print(f"   🚫 Excluida condición contradictoria: {cond}")
            
            elif decision in ['VENTA_SPOT', 'SHORT']:
                # Para ventas, SOLO condiciones bajistas o neutrales
                palabras_prohibidas = ['alcista', 'compra', 'bull', 'positivo', 'soporte', 'sobreventa', 'accumulation', 'sobrevendido', 'no_trade']
                for cond in condiciones_activas:
                    if not any(p in cond.lower() for p in palabras_prohibidas):
                        condiciones_filtradas.append(cond)
                    else:
                        print(f"   🚫 Excluida condición contradictoria: {cond}")
            
            elif decision in ['', 'ESPERAR', 'CAUTION']:
                # Para NO OPERAR, SOLO condiciones de riesgo, confirmación o precaución
                # INCLUIR EXPLÍCITAMENTE ftm_no_trade y otras condiciones de no operabilidad
                palabras_permitidas = [
                    'riesgo', 'confirmacion', 'precaucion', 'falso', 'adx_bajo', 
                    'ftm_no_trade', 'atr_extremo', 'volumen_bajo', 'indecision',
                    'esperar', 'conflicto', 'pendiente', 'insuficiente', 'no_trade',
                    'zona_no_operacion', 'compresion_prolongada', 'squeeze_prolongado',
                    'volumen_insuficiente', 'trampa', 'falso_breakout', 'requiere_espera',
                    'necesita_confirmacion', 'liquidez_baja', 'cierre_semanal'
                ]
                palabras_prohibidas_extra = ['activo', 'reflexion', 'compra', 'venta', 'alcista', 'bajista',
                                            'bull', 'bear', 'positivo', 'negativo']
                
                for cond in condiciones_activas:
                    permitida = any(p in cond.lower() for p in palabras_permitidas)
                    prohibida = any(p in cond.lower() for p in palabras_prohibidas_extra)
                    
                    if permitida and not prohibida:
                        condiciones_filtradas.append(cond)
                    else:
                        print(f"   🚫 Excluida condición no relevante para NO OPERAR: {cond}")
            else:
                condiciones_filtradas = condiciones_activas
            
            print(f"   📊 Condiciones después de filtro: {len(condiciones_filtradas)}")
            
            # ============ 5. PLANTILLA DE ACCIÓN (siempre) ============
            plantillas_seleccionadas = []
            textos_usados = set()  # Para evitar frases duplicadas
            ids_usados = set()     # Para evitar plantillas duplicadas
            
            accion_key = f"accion_{decision.lower()}"
            if decision == '':
                accion_key = 'accion_'
            elif decision == 'ESPERAR':
                accion_key = 'accion_esperar'
            elif decision == 'CAUTION':
                accion_key = 'accion_caution'
            
            if accion_key in self.justification_bank:
                plantilla = self.justification_bank[accion_key]
                plantillas_seleccionadas.append({
                    'plantilla': plantilla,
                    'order': 1,
                    'categoria': 'accion',
                    'id': accion_key
                })
                ids_usados.add(accion_key)
                textos_usados.add(plantilla['template'][:50])
                print(f"   ✅ Plantilla de acción: {accion_key}")
            else:
                print(f"   ⚠️ No se encontró plantilla de acción")
            
            # ============ 6. DEFINIR PRIORIDAD DE CATEGORÍAS ============
            
            # Para NO OPERAR, ESPERAR, CAUTION - CON FILTRO ESTRICTO
            if decision in ['NO_OPERAR', 'ESPERAR', 'CAUTION']:
                print(f"\n📋 PRIORIDAD PARA {decision}:")
                
                # Definir todas las categorías que pueden justificar NO OPERAR
                prioridad_no_operar = [
                    ('confirmacion', 'Confirmación'),
                    ('riesgo', 'Riesgo'),
                    ('precaucion', 'Precaución'),
                    ('volumen_ballenas', 'Volumen'),
                    ('volatilidad', 'Volatilidad'),
                    ('liquidaciones', 'Liquidaciones'),
                    ('multiframe', 'Multiframe'),
                    ('sentimiento', 'Sentimiento'),
                    ('estructura', 'Estructura'),
                    ('smart_money', 'Smart Money'),
                    ('perfil_volumen', 'Perfil Volumen'),
                    ('patrones', 'Patrones'),
                    ('momentum_clasico', 'Momentum Clásico'),
                    ('correlacion', 'Correlación'),
                    ('sesiones', 'Sesiones')
                ]
                
                orden_base = 2
                justificaciones_encontradas = 0
                
                for categoria, nombre in prioridad_no_operar:
                    if len(plantillas_seleccionadas) >= 6:
                        print(f"   🛑 Límite de frases alcanzado (6)")
                        break
                    
                    claves = self._filtrar_por_condiciones(categoria, condiciones_filtradas)
                    
                    if claves:
                        print(f"   📍 {nombre}: {len(claves)} opciones")
                        
                        for clave in claves:
                            if clave in ids_usados:
                                continue
                            
                            plantilla = self.justification_bank[clave]
                            
                            # ============ FILTRO MEJORADO PARA NO OPERAR ============
                            texto_template = plantilla['template'].lower()
                            
                            # Palabras que hacen que una frase sea DIRECCIONAL (prohibidas)
                            palabras_direccionales = [
                                'alcista', 'bajista', 'compra', 'venta', 'long', 'short',
                                'presión compradora', 'presión vendedora', 'dominio',
                                'fortaleza', 'debilidad', 'sobrecompra', 'sobreventa',
                                'oportunidad de compra', 'oportunidad de venta', 'acumulación',
                                'distribución', 'rebote', 'rechazo'
                            ]
                            
                            # PERMITIR frases que tengan palabras como 'soporte', 'resistencia',
                            # 'volumen', 'ATR', 'value area', 'sesión', etc. siempre que NO tengan
                            # palabras direccionales
                            tiene_direccional = any(p in texto_template for p in palabras_direccionales)
                            
                            # PERMITIR la frase si NO tiene palabras direccionales
                            if not tiene_direccional:
                                fingerprint = plantilla['template'][:50]
                                
                                if fingerprint not in textos_usados:
                                    plantillas_seleccionadas.append({
                                        'plantilla': plantilla,
                                        'order': orden_base,
                                        'categoria': categoria,
                                        'id': clave
                                    })
                                    ids_usados.add(clave)
                                    textos_usados.add(fingerprint)
                                    orden_base += 1
                                    justificaciones_encontradas += 1
                                    print(f"      ✅ Seleccionada: {clave}")
                                    break
                            else:
                                print(f"      🚫 Excluida por direccional: {clave}")
                
                # SI NO HAY NINGUNA JUSTIFICACIÓN, USAR UNA GENÉRICA PERO CON DATOS
                if justificaciones_encontradas == 0:
                    print(f"   ⚠️ NO HAY JUSTIFICACIONES ESPECÍFICAS - USANDO GENÉRICA CON DATOS")
                    
                    # Extraer valores para la justificación genérica
                    from datetime import datetime
                    
                    # Obtener valores de las capas
                    adx_valor_local = 0
                    volumen_relativo_local = 1.0
                    atr_pct_local = 0
                    ftm_estado_local = "desconocido"
                    
                    if trend and isinstance(trend, dict):
                        adx_valor_local = trend.get('adx', 0) #adx_value
                    if volume and isinstance(volume, dict):
                        volumen_relativo_local = volume.get('volume_ratio', 1.0)
                    if volatility and isinstance(volatility, dict):
                        atr_pct_local = volatility.get('atr_pct', 0)
                        ftm_estado_local = volatility.get('ftm_state', 'NEUTRAL')
                    
                    # Construir justificación basada en datos reales
                    razones = []
                    
                    # Verificar FTM no trade primero (es el más importante)
                    if 'ftm_no_trade' in condiciones_activas or 'zona_no_operacion' in condiciones_activas:
                        razones.append(f"FTMaverick en zona de no operación")
                    
                    if adx_valor_local < 20:
                        razones.append(f"ADX bajo ({adx_valor_local:.1f})")
                    if volumen_relativo_local < 0.7:
                        razones.append(f"volumen insuficiente ({volumen_relativo_local:.1f}x)")
                    if atr_pct_local > 5:
                        razones.append(f"volatilidad extrema ({atr_pct_local:.1f}%)")
                    if 'falso_breakout' in condiciones_activas:
                        razones.append("falso breakout detectado")
                    if 'indecision' in condiciones_activas:
                        razones.append("múltiples velas de indecisión")
                    
                    if razones:
                        razon_texto = ", ".join(razones[:3])
                        plantilla_generica = {'template': f'Mercado sin condiciones claras: {razon_texto}. Se recomienda NO OPERAR. '}
                    else:
                        plantilla_generica = {'template': 'Condiciones actuales no favorables para operar. Se recomienda NO OPERAR. '}
                    
                    plantillas_seleccionadas.append({
                        'plantilla': plantilla_generica,
                        'order': orden_base,
                        'categoria': 'riesgo',
                        'id': 'generica_no_operar'
                    })
            
            # Para acciones de TRADING (COMPRA, VENTA, LONG, SHORT)
            else:
                print(f"\n📋 PRIORIDAD PARA {decision}:")
                
                # Categorías base para trading - ordenadas por importancia
                categorias_trading = [
                    ('cambio_tendencia', 'Cambio Tendencia'),
                    ('divergencias', 'Divergencias'),
                    ('estructura', 'Estructura'),
                    ('patrones', 'Patrones'),
                    ('volumen_ballenas', 'Volumen/Ballenas'),
                    ('sentimiento', 'Sentimiento'),
                    ('multiframe', 'Multiframe'),
                    ('bollinger', 'Bollinger'),
                    ('perfil_volumen', 'Perfil Volumen'),
                    ('stop_hunt', 'Stop Hunts'),
                    ('liquidaciones', 'Liquidaciones'),
                    ('momentum_clasico', 'Momentum Clásico'),
                    ('momentum_avanzado', 'Momentum Avanzado'),
                    ('flujo_dinero', 'Flujo Dinero'),
                    ('smart_money', 'Smart Money'),
                    ('fibonacci', 'Fibonacci'),
                    ('dmi', 'DMI'),
                    ('volatilidad', 'Volatilidad')
                ]
                
                # ============ AÑADIR ESTA LÓGICA ============
                # Para PAXG-BTC, dar más peso a correlación
                if symbol == 'PAXG-BTC':
                    # Insertar correlación al principio (después de estructura)
                    categorias_trading.insert(3, ('correlacion', 'Correlación/Rotación'))
                else:
                    # Para otros pares, poner correlación al final
                    categorias_trading.append(('correlacion', 'Correlación'))
                # ============================================
                
                # Añadir tendencia SOLO si es coherente con la decisión
                if not hay_cambio_tendencia:
                    if direccion_real == 'bullish' and decision in ['COMPRA_SPOT', 'LONG']:
                        categorias_trading.insert(0, ('direccion_tendencia', 'Dirección Tendencia'))
                        categorias_trading.insert(1, ('fuerza_tendencia', 'Fuerza Tendencia'))
                        print(f"   ✅ Incluyendo tendencia alcista (coherente)")
                    elif direccion_real == 'bearish' and decision in ['VENTA_SPOT', 'SHORT']:
                        categorias_trading.insert(0, ('direccion_tendencia', 'Dirección Tendencia'))
                        categorias_trading.insert(1, ('fuerza_tendencia', 'Fuerza Tendencia'))
                        print(f"   ✅ Incluyendo tendencia bajista (coherente)")
                    else:
                        print(f"   ⚠️ Tendencia {direccion_real} no coincide con {decision} - OMITIDA")
                else:
                    print(f"   🔄 Hay cambio de tendencia - priorizando cambio_tendencia")
                
                # Añadir multiframe SOLO si es coherente
                if 'multiframe_alineacion_alcista' in condiciones_filtradas and decision in ['COMPRA_SPOT', 'LONG']:
                    categorias_trading.append(('multiframe', 'Multiframe'))
                    print(f"   ✅ Multiframe alcista incluido")
                elif 'multiframe_alineacion_bajista' in condiciones_filtradas and decision in ['VENTA_SPOT', 'SHORT']:
                    categorias_trading.append(('multiframe', 'Multiframe'))
                    print(f"   ✅ Multiframe bajista incluido")
                
                # Añadir sesiones y activo al final
                categorias_trading.append(('sesiones', 'Sesiones'))
                categorias_trading.append(('activo', 'Activo'))
                categorias_trading.append(('reflexion', 'Reflexión'))
                
                orden_base = 2
                
                for categoria, nombre in categorias_trading:
                    if len(plantillas_seleccionadas) >= 7:
                        print(f"   🛑 Límite de frases alcanzado (7)")
                        break
                    
                    claves = self._filtrar_por_condiciones(categoria, condiciones_filtradas)
                    
                    if claves:
                        print(f"   📍 {nombre}: {len(claves)} opciones")
                        
                        # ============ FILTROS ESPECIALES POR CATEGORÍA PARA EVITAR CONTRADICCIONES ============
                        
                        # FILTRO PARA DMI
                        if categoria == 'dmi':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if 'alcista' in k]
                                claves_filtradas = [k for k in claves_filtradas if 'bajista' not in k]
                            else:
                                claves_filtradas = [k for k in claves if 'bajista' in k]
                                claves_filtradas = [k for k in claves_filtradas if 'alcista' not in k]
                        
                        # FILTRO PARA DIRECCIÓN DE TENDENCIA
                        elif categoria == 'direccion_tendencia':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if 'alcista' in k]
                            else:
                                claves_filtradas = [k for k in claves if 'bajista' in k]
                        
                        # FILTRO PARA FUERZA DE TENDENCIA
                        elif categoria == 'fuerza_tendencia':
                            claves_filtradas = claves
                        
                        # FILTRO PARA MOMENTUM CLÁSICO
                        elif categoria == 'momentum_clasico':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['alcista', 'favorable', 'sobreventa'])]
                                claves_filtradas = [k for k in claves_filtradas if 'sobrecompra' not in k]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['bajista', 'sobrecompra'])]
                                claves_filtradas = [k for k in claves_filtradas if 'sobreventa' not in k]
                        
                        # FILTRO PARA MOMENTUM AVANZADO
                        elif categoria == 'momentum_avanzado':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['alcista', 'bull', 'positivo'])]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['bajista', 'bear', 'negativo'])]
                        
                        # FILTRO PARA FLUJO DE DINERO
                        elif categoria == 'flujo_dinero':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['compra', 'positivo', 'alcista'])]
                                claves_filtradas = [k for k in claves_filtradas if 'venta' not in k and 'negativo' not in k]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['venta', 'negativo', 'bajista'])]
                                claves_filtradas = [k for k in claves_filtradas if 'compra' not in k and 'positivo' not in k]
                        
                        # FILTRO PARA VOLUMEN Y BALLENAS
                        elif categoria == 'volumen_ballenas':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['compra', 'acumulacion', 'alto'])]
                                claves_filtradas = [k for k in claves_filtradas if 'venta' not in k and 'distribucion' not in k]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['venta', 'distribucion'])]
                                claves_filtradas = [k for k in claves_filtradas if 'compra' not in k and 'acumulacion' not in k]
                        
                        # FILTRO PARA PATRONES
                        elif categoria == 'patrones':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['alcista', 'martillo', 'soldados', 'envolvente_alcista', 'harami_alcista', 'estrella_matutina', 'hch_invertido', 'doble_suelo'])]
                                claves_filtradas = [k for k in claves_filtradas if not any(x in k for x in ['bajista', 'cuervos', 'fugaz', 'colgado', 'envolvente_bajista', 'harami_bajista', 'estrella_vespertina', 'hch', 'doble_techo'])]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['bajista', 'cuervos', 'fugaz', 'colgado', 'envolvente_bajista', 'harami_bajista', 'estrella_vespertina', 'hch', 'doble_techo'])]
                                claves_filtradas = [k for k in claves_filtradas if not any(x in k for x in ['alcista', 'martillo', 'soldados', 'envolvente_alcista', 'harami_alcista', 'estrella_matutina', 'hch_invertido', 'doble_suelo'])]
                        
                        # FILTRO PARA DIVERGENCIAS
                        elif categoria == 'divergencias':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if 'alcista' in k]
                                claves_filtradas = [k for k in claves_filtradas if 'bajista' not in k]
                            else:
                                claves_filtradas = [k for k in claves if 'bajista' in k]
                                claves_filtradas = [k for k in claves_filtradas if 'alcista' not in k]
                        
                        # FILTRO PARA SMART MONEY
                        elif categoria == 'smart_money':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['alcista', 'compra', 'soporte'])]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['bajista', 'venta', 'resistencia'])]
                        
                        # FILTRO PARA PERFIL DE VOLUMEN
                        elif categoria == 'perfil_volumen':
                            claves_filtradas = claves
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = sorted(claves_filtradas, key=lambda x: 0 if 'soporte' in x else 1)
                            else:
                                claves_filtradas = sorted(claves_filtradas, key=lambda x: 0 if 'resistencia' in x else 1)
                        
                        # FILTRO PARA VOLATILIDAD
                        elif categoria == 'volatilidad':
                            claves_filtradas = claves
                        
                        # FILTRO PARA ACTIVO
                        elif categoria == 'activo':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if 'dominante' in k or 'fuerte' in k or 'acumulacion' in k]
                            else:
                                claves_filtradas = [k for k in claves if 'debil' in k]
                        
                        # FILTRO PARA REFLEXIÓN
                        elif categoria == 'reflexion':
                            claves_filtradas = claves
                        
                        # ============ NUEVOS FILTROS ============
                        
                        # FILTRO PARA SENTIMIENTO
                        elif categoria == 'sentimiento':
                            # El sentimiento puede ser oportunidad o cautela, pero debe coincidir con la dirección
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['oportunidad', 'bullish', 'acumulacion'])]
                                claves_filtradas = [k for k in claves_filtradas if 'cautela' not in k or 'bearish' not in k]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['oportunidad', 'bearish', 'toma_ganancias'])]
                                claves_filtradas = [k for k in claves_filtradas if 'cautela' not in k or 'bullish' not in k]
                            
                            # Si no hay filtradas, incluir todas las de sentimiento (son neutrales en dirección)
                            if not claves_filtradas:
                                claves_filtradas = claves
                        
                        # FILTRO PARA MULTIFRAME
                        elif categoria == 'multiframe':
                            # Multiframe puede ser neutral o direccional según alineación
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['alcista', 'pullback', 'acumulacion', 'ruptura'])]
                                claves_filtradas = [k for k in claves_filtradas if 'bajista' not in k]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['bajista', 'distribucion'])]
                                claves_filtradas = [k for k in claves_filtradas if 'alcista' not in k]
                            
                            # Incluir siempre las de conflicto (son neutrales)
                            for k in claves:
                                if 'conflicto' in k and k not in claves_filtradas:
                                    claves_filtradas.append(k)
                        
                        # FILTRO PARA BOLLINGER
                        elif categoria == 'bollinger':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['alcista', 'walk_alcista', 'squeeze_alcista'])]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['bajista', 'walk_bajista', 'squeeze_bajista'])]
                            
                            # La expansión puede ser neutral
                            if not claves_filtradas and 'expansion' in str(claves):
                                claves_filtradas = [k for k in claves if 'expansion' in k]
                        
                        # FILTRO PARA STOP HUNT
                        elif categoria == 'stop_hunt':
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['long', 'ob'])]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in ['short'])]
                            
                            # Si hay stop_hunt_ob, puede ser para ambas direcciones
                            if 'stop_hunt_ob' in claves and 'stop_hunt_ob' not in claves_filtradas:
                                claves_filtradas.append('stop_hunt_ob')
                        
                        else:
                            # Filtro genérico para otras categorías
                            if decision in ['COMPRA_SPOT', 'LONG']:
                                claves_filtradas = [k for k in claves if any(x in k for x in 
                                                       ['alcista', 'compra', 'bull', 'positivo', 'soporte', 'favorable'])]
                            else:
                                claves_filtradas = [k for k in claves if any(x in k for x in 
                                                       ['bajista', 'venta', 'bear', 'negativo', 'resistencia'])]
                        
                        if not claves_filtradas:
                            claves_filtradas = claves
                        
                        # ============ SELECCIONAR LA MEJOR OPCIÓN ============
                        for clave in claves_filtradas:
                            if clave in ids_usados:
                                continue
                            
                            plantilla = self.justification_bank[clave]
                            fingerprint = plantilla['template'][:50]
                            
                            if fingerprint not in textos_usados:
                                plantillas_seleccionadas.append({
                                    'plantilla': plantilla,
                                    'order': orden_base,
                                    'categoria': categoria,
                                    'id': clave
                                })
                                ids_usados.add(clave)
                                textos_usados.add(fingerprint)
                                orden_base += 1
                                print(f"      ✅ Seleccionada: {clave}")
                                break  # Solo una por categoría
                
                # ============ AÑADIR REFLEXIÓN SI NO SE INCLUYÓ (CON FILTRO DIRECCIONAL) ============
                if 'reflexion' not in [p['categoria'] for p in plantillas_seleccionadas] and len(plantillas_seleccionadas) < 7:
                    reflexion_claves = self._filtrar_por_condiciones('reflexion', condiciones_filtradas)
                    if reflexion_claves:
                        # Filtrar según la decisión
                        if decision in ['COMPRA_SPOT', 'LONG']:
                            # Solo reflexiones que NO hablen de esperar o no operar
                            reflexion_claves = [k for k in reflexion_claves 
                                               if 'esperar' not in k.lower() 
                                               and 'no_operar' not in k.lower()
                                               and 'cautela' not in k.lower()]
                        elif decision in ['VENTA_SPOT', 'SHORT']:
                            # Solo reflexiones que NO hablen de esperar o no operar
                            reflexion_claves = [k for k in reflexion_claves 
                                               if 'esperar' not in k.lower() 
                                               and 'no_operar' not in k.lower()
                                               and 'cautela' not in k.lower()]
                        else:
                            # Para NO_OPERAR/ESPERAR, permitir reflexiones de precaución
                            reflexion_claves = [k for k in reflexion_claves 
                                               if any(x in k.lower() for x in ['esperar', 'cautela', 'precaucion'])]
                        
                        # Si después del filtro aún hay claves, seleccionar una
                        if reflexion_claves:
                            for clave in reflexion_claves:
                                if clave not in ids_usados:
                                    plantilla = self.justification_bank[clave]
                                    fingerprint = plantilla['template'][:50]
                                    if fingerprint not in textos_usados:
                                        plantillas_seleccionadas.append({
                                            'plantilla': plantilla,
                                            'order': orden_base,
                                            'categoria': 'reflexion',
                                            'id': clave
                                        })
                                        orden_base += 1
                                        print(f"      ✅ Reflexión seleccionada: {clave}")
                                        break
            
            # ============ 7. RECOMENDACIÓN ============
            # Determinar clave de recomendación según decisión y símbolo
            if decision in ['COMPRA_SPOT', 'LONG']:
                if 'BTC' in symbol and 'PAXG' not in symbol:
                    rec_key = 'recomendacion_compra_spot_btc_usdt'
                elif 'PAXG' in symbol and 'BTC' not in symbol:
                    rec_key = 'recomendacion_compra_spot_paxg_usdt'
                else:
                    rec_key = 'recomendacion_compra_spot_paxg_btc'
                    
            elif decision in ['VENTA_SPOT', 'SHORT']:
                if 'BTC' in symbol and 'PAXG' not in symbol:
                    rec_key = 'recomendacion_venta_spot_btc_usdt'
                elif 'PAXG' in symbol and 'BTC' not in symbol:
                    rec_key = 'recomendacion_venta_spot_paxg_usdt'
                else:
                    rec_key = 'recomendacion_venta_spot_paxg_btc'
                    
            elif decision == 'NO_OPERAR':
                rec_key = 'recomendacion_no_operar'
                
            elif decision == 'ESPERAR':
                rec_key = 'recomendacion_esperar'
                
            elif decision == 'CAUTION':
                rec_key = 'recomendacion_caution'
                
            else:
                rec_key = f'recomendacion_{decision.lower()}'
            
            # Verificar que la plantilla existe
            if rec_key in self.justification_bank:
                if rec_key not in ids_usados:
                    plantilla = self.justification_bank[rec_key]
                    fingerprint = plantilla['template'][:50]
                    if fingerprint not in textos_usados:
                        plantillas_seleccionadas.append({
                            'plantilla': plantilla,
                            'order': 98,
                            'categoria': 'recomendacion',
                            'id': rec_key
                        })
            else:
                # Fallback genérico
                if decision == 'NO_OPERAR':
                    plantillas_seleccionadas.append({
                        'plantilla': {'template': 'Se recomienda NO OPERAR en estos niveles. '},
                        'order': 98,
                        'categoria': 'recomendacion'
                    })
                elif decision == 'ESPERAR':
                    plantillas_seleccionadas.append({
                        'plantilla': {'template': 'Se recomienda ESPERAR por confirmación. '},
                        'order': 98,
                        'categoria': 'recomendacion'
                    })            
            # ============ 8. CIERRE ============
            plantillas_seleccionadas.append({
                'plantilla': {'template': '\n\n{timestamp} Hora Bolivia'},
                'order': 99,
                'categoria': 'cierre'
            })
            
            # ============ 9. ORDENAR Y RETORNAR ============
            plantillas_seleccionadas.sort(key=lambda x: x['order'])
            
            print(f"\n📋 PLANTILLAS FINALES ({len(plantillas_seleccionadas)}):")
            for p in plantillas_seleccionadas:
                print(f"   {p['order']}: {p.get('categoria', 'unknown')} - {p.get('id', '')[:30]}")
            
            return [p['plantilla'] for p in plantillas_seleccionadas]
            
        except Exception as e:
            print(f"❌ Error en seleccionar_plantillas_por_condiciones: {e}")
            import traceback
            traceback.print_exc()
            return [{'template': '{accion} DE {par} en {temporalidad}\n\n{timestamp} Hora Bolivia'}]
            
    
    def _mapear_condiciones_activas(self, decision, symbol, timeframe, trend, momentum, volatility, 
                                    volume, structure, correlation, market_hours, confirmation, 
                                    estrategias_consenso, sentiment, liquidation):
        """
        Mapea todas las condiciones activas del mercado - VERSIÓN CON DEBUG
        """
        import traceback
        
        # DEBUG: Mostrar quién llamó a esta función
        stack = traceback.extract_stack()
        caller = stack[-2]  # El que llamó a esta función
        print(f"\n🔍 DEBUG: _mapear_condiciones_activas llamada desde:")
        print(f"   Archivo: {caller.filename}")
        print(f"   Línea: {caller.lineno}")
        print(f"   Función: {caller.name}")
        print(f"   ¿liquidation recibido? {'SÍ' if liquidation is not None else 'NO'}")
        try:
            condiciones = []
            
            # Obtener índices para antigüedad de patrones
            last_candle_index = 0
            if structure and isinstance(structure, dict):
                if 'df' in structure and isinstance(structure.get('df'), dict):
                    df_dict = structure.get('df', {})
                    last_candle_index = len(df_dict.get('time', [])) - 1
            
            # ============ TENDENCIA (CAPA 1) ============
            if trend and isinstance(trend, dict):
                # Dirección general
                if trend.get('direction') == 'bullish':
                    condiciones.append('trend_bullish')
                elif trend.get('direction') == 'bearish':
                    condiciones.append('trend_bearish')
                
                # ADX
                adx = trend.get('adx', 0) # adx_value
                if adx < 20:
                    condiciones.append('adx_bajo')
                    condiciones.append('adx_low')
                    condiciones.append('tendencia_debil')
                elif adx > 25:
                    condiciones.append('adx_25_plus')
                    if adx > 40:
                        condiciones.append('adx_fuerte')
                        condiciones.append('adx_strong')
                        condiciones.append('tendencia_fuerte')
                
                # DMI específico (+DI / -DI)
                plus_di = trend.get('plus_di', 0)
                minus_di = trend.get('minus_di', 0)
                if plus_di > minus_di:
                    condiciones.append('dmi_alcista')
                    if plus_di - minus_di > 10:
                        condiciones.append('dmi_fuerte_alcista')
                elif minus_di > plus_di:
                    condiciones.append('dmi_bajista')
                    if minus_di - plus_di > 10:
                        condiciones.append('dmi_fuerte_bajista')
                
                indicators = trend.get('indicators', {}) or {}
                
                # EMAs
                ema9 = indicators.get('ema9', 0)
                ema21 = indicators.get('ema21', 0)
                ema50 = indicators.get('ema50', 0)
                ema200 = indicators.get('ema200', 0)
                
                if ema9 and ema21:
                    if ema9 > ema21:
                        condiciones.append('ema9_sobre_ema21')
                        condiciones.append('ema_alcista_9_21')
                    else:
                        condiciones.append('ema9_bajo_ema21')
                        condiciones.append('ema_bajista_9_21')
                
                if ema21 and ema50:
                    if ema21 > ema50:
                        condiciones.append('ema21_sobre_ema50')
                        condiciones.append('ema_alcista_21_50')
                    else:
                        condiciones.append('ema21_bajo_ema50')
                        condiciones.append('ema_bajista_21_50')
                
                if ema50 and ema200:
                    if ema50 > ema200:
                        condiciones.append('ema50_sobre_ema200')
                        condiciones.append('ema_alcista_50_200')
                    else:
                        condiciones.append('ema50_bajo_ema200')
                        condiciones.append('ema_bajista_50_200')
                
                # Cruce de EMAs
                ema9_prev = indicators.get('ema9_prev', 0)
                ema21_prev = indicators.get('ema21_prev', 0)
                if ema9 and ema21 and ema9_prev and ema21_prev:
                    if ema9 > ema21 and ema9_prev <= ema21_prev:
                        condiciones.append('ema_cross_bull')
                        condiciones.append('cruce_ema_alcista')
                    elif ema9 < ema21 and ema9_prev >= ema21_prev:
                        condiciones.append('ema_cross_bear')
                        condiciones.append('cruce_ema_bajista')
                
                # Alineación completa de EMAs
                if ema9 and ema21 and ema50 and ema200:
                    if ema9 > ema21 > ema50 > ema200:
                        condiciones.append('emas_alineadas_alcista')
                        condiciones.append('alineacion_emas_alcista')
                    elif ema9 < ema21 < ema50 < ema200:
                        condiciones.append('emas_alineadas_bajista')
                        condiciones.append('alineacion_emas_bajista')
                
                # SuperTrend
                supertrend_trend = indicators.get('supertrend_trend', 'neutral')
                if supertrend_trend == 'bullish':
                    condiciones.append('supertrend_alcista')
                    condiciones.append('st_alcista')
                elif supertrend_trend == 'bearish':
                    condiciones.append('supertrend_bajista')
                    condiciones.append('st_bajista')
                
                # Ichimoku
                ichimoku_tk = indicators.get('ichimoku_tk', 'neutral')
                if ichimoku_tk == 'bullish':
                    condiciones.append('ichimoku_alcista')
                    condiciones.append('tk_alcista')
                elif ichimoku_tk == 'bearish':
                    condiciones.append('ichimoku_bajista')
                    condiciones.append('tk_bajista')
                
                ichimoku_cloud = indicators.get('ichimoku_cloud', 'neutral')
                if ichimoku_cloud == 'bullish':
                    condiciones.append('ichimoku_cloud_alcista')
                elif ichimoku_cloud == 'bearish':
                    condiciones.append('ichimoku_cloud_bajista')
                
                # Cruce de Ichimoku TK
                if ichimoku_tk == 'bullish' and trend.get('direction') == 'bearish':
                    condiciones.append('ichimoku_tk_cross_bull')
                elif ichimoku_tk == 'bearish' and trend.get('direction') == 'bullish':
                    condiciones.append('ichimoku_tk_cross_bear')
                
                # Parabolic SAR
                psar_trend = indicators.get('parabolic_sar_trend', 'neutral')
                if psar_trend == 'bullish':
                    condiciones.append('psar_alcista')
                    if trend.get('direction') == 'bearish':
                        condiciones.append('psar_alcista_contra_tendencia')
                        condiciones.append('cambio_tendencia_alcista')
                elif psar_trend == 'bearish':
                    condiciones.append('psar_bajista')
                    if trend.get('direction') == 'bullish':
                        condiciones.append('psar_bajista_contra_tendencia')
                        condiciones.append('cambio_tendencia_bajista')
            
            # ============ MOMENTUM (CAPA 2) ============
            if momentum and isinstance(momentum, dict):
                indicators = momentum.get('indicators', {}) or {}
                
                # RSI
                rsi = indicators.get('rsi', 50)
                if rsi < 30:
                    condiciones.append('rsi_sobreventa')
                    condiciones.append('rsi_oversold')
                    condiciones.append('rsi_extremo_bajo')
                elif rsi > 70:
                    condiciones.append('rsi_sobrecompra')
                    condiciones.append('rsi_overbought')
                    condiciones.append('rsi_extremo_alto')
                elif rsi > 50:
                    condiciones.append('rsi_alcista')
                    condiciones.append('rsi_positivo')
                elif rsi < 50:
                    condiciones.append('rsi_bajista')
                    condiciones.append('rsi_negativo')
                
                # RSI Maverick
                rsi_maverick = indicators.get('rsi_maverick', 0.5)
                if rsi_maverick < 0.2:
                    condiciones.append('rsi_maverick_sobreventa')
                    condiciones.append('rsi_maverick_extremo_bajo')
                elif rsi_maverick > 0.8:
                    condiciones.append('rsi_maverick_sobrecompra')
                    condiciones.append('rsi_maverick_extremo_alto')
                elif rsi_maverick > 0.5:
                    condiciones.append('rsi_maverick_alcista')
                else:
                    condiciones.append('rsi_maverick_bajista')
                
                # MACD
                macd_hist = indicators.get('macd_histogram', 0)
                macd_hist_pre = indicators.get('macd_hist_pre', 0)
                if macd_hist > 0:
                    condiciones.append('macd_alcista')
                    condiciones.append('macd_bull')
                    if macd_hist > macd_hist_pre:
                        condiciones.append('macd_hist_creciente')
                        condiciones.append('macd_momentum_alcista')
                elif macd_hist < 0:
                    condiciones.append('macd_bajista')
                    condiciones.append('macd_bear')
                    if macd_hist < macd_hist_pre:
                        condiciones.append('macd_hist_decreciente')
                        condiciones.append('macd_momentum_bajista')
                
                # Estocástico
                stoch_k = indicators.get('stoch_k', 50)
                stoch_d = indicators.get('stoch_d', 50)
                if stoch_k > 80 and stoch_d > 80:
                    condiciones.append('estocastico_sobrecompra')
                    condiciones.append('stoch_sobrecompra')
                elif stoch_k < 20 and stoch_d < 20:
                    condiciones.append('estocastico_sobreventa')
                    condiciones.append('stoch_sobreventa')
                
                if stoch_k > stoch_d:
                    condiciones.append('estocastico_alcista')
                    condiciones.append('stoch_alcista')
                    if stoch_k < 30:
                        condiciones.append('estocastico_cruce_alcista')
                        condiciones.append('stoch_cruce_alcista')
                elif stoch_k < stoch_d:
                    condiciones.append('estocastico_bajista')
                    condiciones.append('stoch_bajista')
                    if stoch_k > 70:
                        condiciones.append('estocastico_cruce_bajista')
                        condiciones.append('stoch_cruce_bajista')
                
                # Williams %R
                williams = indicators.get('williams', -50)
                if williams > -20:
                    condiciones.append('williams_sobrecompra')
                    condiciones.append('williams_sobrecomprado')
                elif williams < -80:
                    condiciones.append('williams_sobreventa')
                    condiciones.append('williams_sobrevendido')
                elif williams > -50:
                    condiciones.append('williams_alcista')
                else:
                    condiciones.append('williams_bajista')
                
                # CCI
                cci = indicators.get('cci', 0)
                if cci > 200:
                    condiciones.append('cci_extremo_alto')
                    condiciones.append('cci_muy_alcista')
                elif cci < -200:
                    condiciones.append('cci_extremo_bajo')
                    condiciones.append('cci_muy_bajista')
                elif cci > 100:
                    condiciones.append('cci_alcista')
                elif cci < -100:
                    condiciones.append('cci_bajista')
                
                # Squeeze Momentum
                squeeze = indicators.get('squeeze_momentum', 0)
                if squeeze > 0:
                    condiciones.append('squeeze_alcista')
                    if squeeze > 0.5:
                        condiciones.append('squeeze_fuerte_alcista')
                elif squeeze < 0:
                    condiciones.append('squeeze_bajista')
                    if squeeze < -0.5:
                        condiciones.append('squeeze_fuerte_bajista')
                
                # ============ DIVERGENCIAS ============
                # Divergencias regulares
                for div in momentum.get('divergences', []):
                    div_lower = div.lower()
                    if 'rsi' in div_lower:
                        condiciones.append('divergencia_rsi')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_rsi_alcista')
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_rsi_bajista')
                            condiciones.append('divergencia_bajista')
                    elif 'macd' in div_lower:
                        condiciones.append('divergencia_macd')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_macd_alcista')
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_macd_bajista')
                            condiciones.append('divergencia_bajista')
                    elif 'estocastico' in div_lower or 'stoch' in div_lower:
                        condiciones.append('divergencia_estocastico')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_estocastico_alcista')
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_estocastico_bajista')
                            condiciones.append('divergencia_bajista')
                    elif 'williams' in div_lower:
                        condiciones.append('divergencia_williams')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_williams_alcista')
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_williams_bajista')
                            condiciones.append('divergencia_bajista')
                    elif 'cci' in div_lower:
                        condiciones.append('divergencia_cci')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_cci_alcista')
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_cci_bajista')
                            condiciones.append('divergencia_bajista')
                    elif 'rsi_maverick' in div_lower:
                        condiciones.append('divergencia_rsi_maverick')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_rsi_maverick_alcista')
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_rsi_maverick_bajista')
                            condiciones.append('divergencia_bajista')
                    else:
                        condiciones.append('divergencia_detectada')
                        if 'bull' in div_lower:
                            condiciones.append('divergencia_alcista')
                        elif 'bear' in div_lower:
                            condiciones.append('divergencia_bajista')
                
                # Divergencias ocultas
                for div in momentum.get('hidden_divergences', []):
                    div_lower = div.lower()
                    condiciones.append('divergencia_oculta')
                    if 'bull' in div_lower:
                        condiciones.append('divergencia_oculta_alcista')
                        condiciones.append('fortaleza_subyacente')
                    elif 'bear' in div_lower:
                        condiciones.append('divergencia_oculta_bajista')
                        condiciones.append('debilidad_subyacente')
            
            # ============ VOLATILIDAD (CAPA 3) ============
            if volatility and isinstance(volatility, dict):
                # ATR
                atr = volatility.get('atr_pct', 0)
                if atr > 5:
                    condiciones.append('atr_extremo')
                    condiciones.append('atr_muy_alto')
                    condiciones.append('volatilidad_extrema')
                elif atr > 3:
                    condiciones.append('atr_alto')
                    condiciones.append('volatilidad_alta')
                elif atr < 1:
                    condiciones.append('atr_bajo')
                    condiciones.append('volatilidad_baja')
                
                # FTMaverick
                ftm = volatility.get('ftm_state', 'NEUTRAL')
                if ftm == 'STRONG_UP':
                    condiciones.append('ftm_fuerte_alcista')
                    condiciones.append('ftm_alcista_fuerte')
                elif ftm == 'WEAK_UP':
                    condiciones.append('ftm_debil_alcista')
                elif ftm == 'STRONG_DOWN':
                    condiciones.append('ftm_fuerte_bajista')
                    condiciones.append('ftm_no_trade')
                    condiciones.append('zona_no_operacion')
                elif ftm == 'WEAK_DOWN':
                    condiciones.append('ftm_debil_bajista')
                
                ftm_fuerza = abs(volatility.get('ftm_strength', 0))
                if ftm_fuerza > 50:
                    condiciones.append('ftm_fuerza_alta')
                
                # Squeeze
                if volatility.get('squeeze_on'):
                    condiciones.append('squeeze_on')
                    squeeze_len = volatility.get('squeeze_length', 0)
                    if squeeze_len > 5:
                        condiciones.append('squeeze_prolongado')
                        condiciones.append('squeeze_prolonged')
                        condiciones.append('compresion_prolongada')
                
                # Bandas de Bollinger
                bb_pos = volatility.get('bb_position', 0.5)
                if bb_pos > 0.8:
                    condiciones.append('bb_touch_superior')
                elif bb_pos < 0.2:
                    condiciones.append('bb_touch_inferior')
            
            # ============ VOLUMEN (CAPA 4) ============
            if volume and isinstance(volume, dict):
                vol_ratio = volume.get('volume_ratio', 1)
                if vol_ratio > 2:
                    condiciones.append('volumen_muy_alto')
                    condiciones.append('volumen_explosivo')
                elif vol_ratio > 1.5:
                    condiciones.append('volumen_alto')
                    condiciones.append('volumen_significativo')
                elif vol_ratio < 0.5:
                    condiciones.append('volumen_muy_bajo')
                    condiciones.append('volumen_insuficiente')
                    condiciones.append('volumen_critico')
                elif vol_ratio < 0.7:
                    condiciones.append('volumen_bajo')
                    condiciones.append('volumen_insuficiente')
                
                # MFI
                mfi = volume.get('mfi', 50)
                if mfi > 60:
                    condiciones.append('mfi_compra')
                    condiciones.append('mfi_alcista')
                elif mfi < 40:
                    condiciones.append('mfi_venta')
                    condiciones.append('mfi_bajista')
                elif mfi > 50:
                    condiciones.append('mfi_positivo')
                else:
                    condiciones.append('mfi_negativo')
                
                # Force Index
                force = volume.get('force_index', 0)
                if force > 0:
                    condiciones.append('force_positivo')
                    condiciones.append('force_alcista')
                elif force < 0:
                    condiciones.append('force_negativo')
                    condiciones.append('force_bajista')
                
                # OBV
                obv = volume.get('obv_trend', 'neutral')
                if obv == 'bullish':
                    condiciones.append('obv_alcista')
                    condiciones.append('obv_positivo')
                elif obv == 'bearish':
                    condiciones.append('obv_bajista')
                    condiciones.append('obv_negativo')
                
                # Ballenas
                if volume.get('whale_buy', False):
                    condiciones.append('ballenas_compra')
                    if volume.get('whale_buy_confirmed', False):
                        condiciones.append('ballenas_compra_confirmada')
                if volume.get('whale_sell', False):
                    condiciones.append('ballenas_venta')
                    if volume.get('whale_sell_confirmed', False):
                        condiciones.append('ballenas_venta_confirmada')
                
                # Iceberg
                if volume.get('iceberg_buy', False):
                    condiciones.append('iceberg_acumulacion')
                if volume.get('iceberg_sell', False):
                    condiciones.append('iceberg_distribucion')
            
            # ============ ESTRUCTURA (CAPA 5) ============
            if structure and isinstance(structure, dict):
                # Soportes y resistencias
                current_price = structure.get('current_price', 0)
                if structure.get('nearest_support'):
                    condiciones.append('soporte_cercano')
                    distancia_soporte = abs(current_price - structure['nearest_support']) / current_price * 100 if current_price else 999
                    if distancia_soporte < 1:
                        condiciones.append('muy_cerca_soporte')
                
                if structure.get('nearest_resistance'):
                    condiciones.append('resistencia_cercana')
                    distancia_resistencia = abs(structure['nearest_resistance'] - current_price) / current_price * 100 if current_price else 999
                    if distancia_resistencia < 1:
                        condiciones.append('muy_cerca_resistencia')
                
                # Order Blocks
                for ob in structure.get('order_blocks', [])[:2]:
                    if ob.get('type') == 'bullish':
                        condiciones.append('order_block_alcista')
                    else:
                        condiciones.append('order_block_bajista')
                
                # Fair Value Gaps
                for fvg in structure.get('fair_value_gaps', [])[:2]:
                    if fvg.get('type') == 'bullish' and not fvg.get('filled', True):
                        condiciones.append('fvg_alcista')
                    elif fvg.get('type') == 'bearish' and not fvg.get('filled', True):
                        condiciones.append('fvg_bajista')
                
                # Liquidity Sweeps
                for sweep in structure.get('liquidity_sweeps', [])[:2]:
                    if sweep.get('type') == 'bullish':
                        condiciones.append('liquidity_sweep_alcista')
                    else:
                        condiciones.append('liquidity_sweep_bajista')
                
                # Stop Hunts (NUEVO)
                stop_hunts = structure.get('stop_hunts', [])
                if stop_hunts:
                    for hunt in stop_hunts[-2:]:  # Últimos 2
                        if hunt.get('type') == 'bullish':
                            condiciones.append('stop_hunt_alcista')
                        elif hunt.get('type') == 'bearish':
                            condiciones.append('stop_hunt_bajista')
                    condiciones.append('stop_hunts_detectados')
                
                # Perfil de Volumen
                vp = structure.get('volume_profile', {})
                if vp:
                    pos = vp.get('price_position', '')
                    if pos == 'inside_value_area':
                        condiciones.append('perfil_dentro_valor')
                        condiciones.append('zona_equilibrio')
                    elif pos == 'above_value_area':
                        condiciones.append('perfil_sobre_valor')
                        condiciones.append('fuera_de_valor')
                    elif pos == 'below_value_area':
                        condiciones.append('perfil_bajo_valor')
                        condiciones.append('fuera_de_valor')
                    
                    if vp.get('distance_to_poc', 999) < 2:
                        condiciones.append('cerca_poc')
                    
                    # ============ NUEVAS CONDICIONES HVN/LVN ============
                    closest_hvn = vp.get('closest_hvn')
                    closest_lvn = vp.get('closest_lvn')
                    
                    if closest_hvn:
                        distancia_hvn = abs(current_price - closest_hvn['price']) / current_price * 100
                        if distancia_hvn < 1.0:
                            condiciones.append('hvn_cercano')
                            if closest_hvn['price'] < current_price:
                                condiciones.append('hvn_soporte_potencial')
                            else:
                                condiciones.append('hvn_resistencia_potencial')
                    
                    if closest_lvn:
                        distancia_lvn = abs(current_price - closest_lvn['price']) / current_price * 100
                        if distancia_lvn < 1.0:
                            condiciones.append('lvn_cercano')
                
                # Fibonacci
                precio = structure.get('current_price', 0)
                fibs = structure.get('fib_levels', {})
                for nivel, valor in fibs.items():
                    if valor and precio and abs(precio - valor) / precio < 0.01:
                        nivel_key = nivel.replace('.', '_')
                        condiciones.append(f'fib_{nivel_key}')
            
            # ============ PATRONES DE VELAS - VERSIÓN CORREGIDA CON VERIFICACIÓN DE CONFIABILIDAD ============
            if structure and isinstance(structure, dict):
                patterns = structure.get('patterns', {})
                
                # Listas separadas por dirección y calidad
                patrones_alcistas = []
                patrones_bajistas = []
                patrones_muy_confiables = []  # >85% confianza
                patrones_detectados = set()
                
                # Obtener la fecha actual para filtrar patrones muy antiguos
                ahora = datetime.now()
                
                for pattern in patterns.get('recent_patterns', []):
                    if isinstance(pattern, dict):
                        pattern_index = pattern.get('index', 0)
                        antiguedad = last_candle_index - pattern_index if last_candle_index > 0 else 0
                        reliability = pattern.get('reliability', 0)
                        
                        # SOLO considerar patrones RECIENTES (menos de 10 velas) y CONFIABLES (>60%)
                        if antiguedad <= 10 and reliability >= 60:
                            nombre = pattern.get('name', '').lower()
                            direccion = pattern.get('direction', '')
                            tipo = pattern.get('type', '')
                            
                            # Clasificar por confiabilidad
                            if reliability >= 85:
                                patrones_muy_confiables.append({
                                    'nombre': nombre,
                                    'reliability': reliability,
                                    'direccion': direccion
                                })
                            
                            # Registrar tipo de patrón
                            if tipo == '1':
                                condiciones.append('patron_1v')
                            elif tipo == '2':
                                condiciones.append('patron_2v')
                            elif tipo == '3':
                                condiciones.append('patron_3v')
                            elif tipo == '4+':
                                condiciones.append('patron_chartista')
                            
                            # Clasificar por dirección EXPLÍCITA
                            if direccion == 'bullish':
                                patrones_alcistas.append({
                                    'nombre': nombre,
                                    'reliability': reliability,
                                    'tipo': tipo
                                })
                            elif direccion == 'bearish':
                                patrones_bajistas.append({
                                    'nombre': nombre,
                                    'reliability': reliability,
                                    'tipo': tipo
                                })
                            
                            # ============ PATRONES DE 1 VELA ============
                            # Alcistas
                            if direccion == 'bullish':
                                if 'martillo' in nombre and 'martillo' not in patrones_detectados:
                                    condiciones.append('patron_martillo')
                                    patrones_detectados.add('martillo')
                                elif 'martillo invertido' in nombre and 'martillo_invertido' not in patrones_detectados:
                                    condiciones.append('patron_martillo_invertido')
                                    patrones_detectados.add('martillo_invertido')
                                elif 'marubozu' in nombre and 'alcista' in nombre and 'marubozu_alcista' not in patrones_detectados:
                                    condiciones.append('patron_marubozu_alcista')
                                    patrones_detectados.add('marubozu_alcista')
                                elif 'vela larga blanca' in nombre and 'vela_larga_blanca' not in patrones_detectados:
                                    condiciones.append('patron_vela_larga_blanca')
                                    patrones_detectados.add('vela_larga_blanca')
                            
                            # Bajistas
                            elif direccion == 'bearish':
                                if 'colgado' in nombre and 'colgado' not in patrones_detectados:
                                    condiciones.append('patron_colgado')
                                    patrones_detectados.add('colgado')
                                elif 'estrella fugaz' in nombre and 'estrella_fugaz' not in patrones_detectados:
                                    condiciones.append('patron_estrella_fugaz')
                                    patrones_detectados.add('estrella_fugaz')
                                elif 'marubozu' in nombre and 'bajista' in nombre and 'marubozu_bajista' not in patrones_detectados:
                                    condiciones.append('patron_marubozu_bajista')
                                    patrones_detectados.add('marubozu_bajista')
                                elif 'vela larga negra' in nombre and 'vela_larga_negra' not in patrones_detectados:
                                    condiciones.append('patron_vela_larga_negra')
                                    patrones_detectados.add('vela_larga_negra')
                            
                            # Neutrales
                            if 'doji' in nombre and 'doji' not in patrones_detectados:
                                condiciones.append('patron_doji')
                                patrones_detectados.add('doji')
                            
                            # ============ PATRONES DE 2 VELAS ============
                            # Alcistas
                            if direccion == 'bullish':
                                if 'envolvente' in nombre and 'alcista' in nombre and 'envolvente_alcista' not in patrones_detectados:
                                    condiciones.append('patron_envolvente_alcista')
                                    patrones_detectados.add('envolvente_alcista')
                                elif 'harami' in nombre and 'alcista' in nombre and 'harami_alcista' not in patrones_detectados:
                                    condiciones.append('patron_harami_alcista')
                                    patrones_detectados.add('harami_alcista')
                                elif 'tweezer' in nombre and 'fondo' in nombre and 'tweezer_fondo' not in patrones_detectados:
                                    condiciones.append('patron_tweezer_fondo')
                                    patrones_detectados.add('tweezer_fondo')
                            
                            # Bajistas
                            elif direccion == 'bearish':
                                if 'envolvente' in nombre and 'bajista' in nombre and 'envolvente_bajista' not in patrones_detectados:
                                    condiciones.append('patron_envolvente_bajista')
                                    patrones_detectados.add('envolvente_bajista')
                                elif 'harami' in nombre and 'bajista' in nombre and 'harami_bajista' not in patrones_detectados:
                                    condiciones.append('patron_harami_bajista')
                                    patrones_detectados.add('harami_bajista')
                                elif 'tweezer' in nombre and 'techo' in nombre and 'tweezer_techo' not in patrones_detectados:
                                    condiciones.append('patron_tweezer_techo')
                                    patrones_detectados.add('tweezer_techo')
                            
                            # ============ PATRONES DE 3 VELAS ============
                            # Alcistas
                            if direccion == 'bullish':
                                if 'estrella matutina' in nombre and 'estrella_matutina' not in patrones_detectados:
                                    condiciones.append('patron_estrella_matutina')
                                    patrones_detectados.add('estrella_matutina')
                                elif 'tres soldados' in nombre and 'tres_soldados' not in patrones_detectados:
                                    condiciones.append('patron_tres_soldados')
                                    patrones_detectados.add('tres_soldados')
                                elif 'tres dentro' in nombre and 'arriba' in nombre and 'tres_dentro_arriba' not in patrones_detectados:
                                    condiciones.append('patron_tres_dentro_arriba')
                                    patrones_detectados.add('tres_dentro_arriba')
                                elif 'tres fuera' in nombre and 'arriba' in nombre and 'tres_fuera_arriba' not in patrones_detectados:
                                    condiciones.append('patron_tres_fuera_arriba')
                                    patrones_detectados.add('tres_fuera_arriba')
                            
                            # Bajistas
                            elif direccion == 'bearish':
                                if 'estrella vespertina' in nombre and 'estrella_vespertina' not in patrones_detectados:
                                    condiciones.append('patron_estrella_vespertina')
                                    patrones_detectados.add('estrella_vespertina')
                                elif 'tres cuervos' in nombre and 'tres_cuervos' not in patrones_detectados:
                                    condiciones.append('patron_tres_cuervos')
                                    patrones_detectados.add('tres_cuervos')
                                elif 'tres dentro' in nombre and 'abajo' in nombre and 'tres_dentro_abajo' not in patrones_detectados:
                                    condiciones.append('patron_tres_dentro_abajo')
                                    patrones_detectados.add('tres_dentro_abajo')
                                elif 'tres fuera' in nombre and 'abajo' in nombre and 'tres_fuera_abajo' not in patrones_detectados:
                                    condiciones.append('patron_tres_fuera_abajo')
                                    patrones_detectados.add('tres_fuera_abajo')
                            
                            # ============ PATRONES CHARTISTAS (4+ VELAS) ============
                            # Alcistas
                            if direccion == 'bullish':
                                if 'hch invertido' in nombre and 'hch_invertido' not in patrones_detectados:
                                    condiciones.append('patron_hch_invertido')
                                    patrones_detectados.add('hch_invertido')
                                elif 'doble suelo' in nombre and 'doble_suelo' not in patrones_detectados:
                                    condiciones.append('patron_doble_suelo')
                                    patrones_detectados.add('doble_suelo')
                                elif 'triple suelo' in nombre and 'triple_suelo' not in patrones_detectados:
                                    condiciones.append('patron_triple_suelo')
                                    patrones_detectados.add('triple_suelo')
                                elif 'bandera' in nombre and 'alcista' in nombre and 'bandera_alcista' not in patrones_detectados:
                                    condiciones.append('patron_bandera_alcista')
                                    patrones_detectados.add('bandera_alcista')
                                elif 'banderín' in nombre and 'alcista' in nombre and 'banderin_alcista' not in patrones_detectados:
                                    condiciones.append('patron_banderin_alcista')
                                    patrones_detectados.add('banderin_alcista')
                                elif 'cuña descendente' in nombre and 'cuna_descendente' not in patrones_detectados:
                                    condiciones.append('patron_cuna_descendente')
                                    patrones_detectados.add('cuna_descendente')
                                elif 'triángulo ascendente' in nombre and 'triangulo_ascendente' not in patrones_detectados:
                                    condiciones.append('patron_triangulo_ascendente')
                                    patrones_detectados.add('triangulo_ascendente')
                                elif 'taza' in nombre and 'taza_mango' not in patrones_detectados:
                                    condiciones.append('patron_taza_mango')
                                    patrones_detectados.add('taza_mango')
                            
                            # Bajistas
                            elif direccion == 'bearish':
                                if 'hch' in nombre and 'invertido' not in nombre and 'hch' not in patrones_detectados:
                                    condiciones.append('patron_hch')
                                    patrones_detectados.add('hch')
                                elif 'doble techo' in nombre and 'doble_techo' not in patrones_detectados:
                                    condiciones.append('patron_doble_techo')
                                    patrones_detectados.add('doble_techo')
                                elif 'triple techo' in nombre and 'triple_techo' not in patrones_detectados:
                                    condiciones.append('patron_triple_techo')
                                    patrones_detectados.add('triple_techo')
                                elif 'bandera' in nombre and 'bajista' in nombre and 'bandera_bajista' not in patrones_detectados:
                                    condiciones.append('patron_bandera_bajista')
                                    patrones_detectados.add('bandera_bajista')
                                elif 'banderín' in nombre and 'bajista' in nombre and 'banderin_bajista' not in patrones_detectados:
                                    condiciones.append('patron_banderin_bajista')
                                    patrones_detectados.add('banderin_bajista')
                                elif 'cuña ascendente' in nombre and 'cuna_ascendente' not in patrones_detectados:
                                    condiciones.append('patron_cuna_ascendente')
                                    patrones_detectados.add('cuna_ascendente')
                                elif 'triángulo descendente' in nombre and 'triangulo_descendente' not in patrones_detectados:
                                    condiciones.append('patron_triangulo_descendente')
                                    patrones_detectados.add('triangulo_descendente')
                
                # Añadir condiciones de dirección general SOLO si hay patrones de alta calidad
                if patrones_muy_confiables:
                    for p in patrones_muy_confiables:
                        if p['direccion'] == 'bullish':
                            condiciones.append('patron_alcista_muy_confiable')
                        else:
                            condiciones.append('patron_bajista_muy_confiable')
                
                # Añadir dirección general si hay suficientes patrones
                if len(patrones_alcistas) > 0:
                    condiciones.append('patron_alcista')
                if len(patrones_bajistas) > 0:
                    condiciones.append('patron_bajista')
                
                # Conteo de patrones para contexto
                if len(patrones_alcistas) > 2:
                    condiciones.append('multiples_patrones_alcistas')
                if len(patrones_bajistas) > 2:
                    condiciones.append('multiples_patrones_bajistas')
                if len(patrones_alcistas) == 0 and len(patrones_bajistas) == 0 and patterns.get('count', 0) > 2:
                    condiciones.append('patrones_indecision')
                    condiciones.append('indecision')
            
            # ============ CORRELACIÓN (CAPA 6) - VERSIÓN COMPLETA ============
            if correlation and isinstance(correlation, dict):
                rot = correlation.get('rotation_signal')
                
                # Extraer tendencias y ADX para condiciones de NO rotación
                btc_trend = None
                ratio_trend = None
                btc_adx = 0
                ratio_adx = 0
                
                if correlation.get('btc_analysis'):
                    btc_trend = correlation['btc_analysis'].get('trend', {}).get('direction')
                    btc_adx = correlation['btc_analysis'].get('trend', {}).get('adx', 0)
                
                if correlation.get('paxg_btc_analysis'):
                    ratio_trend = correlation['paxg_btc_analysis'].get('trend', {}).get('direction')
                    ratio_adx = correlation['paxg_btc_analysis'].get('trend', {}).get('adx', 0)
                
                # ============ SEÑALES DE ROTACIÓN ACTIVA ============
                if rot == 'RISK_ON':
                    condiciones.append('rotacion_riesgo_on')
                    condiciones.append('rotation_risk_on')
                    condiciones.append('apetito_riesgo')
                elif rot == 'RISK_OFF':
                    condiciones.append('rotacion_riesgo_off')
                    condiciones.append('rotation_risk_off')
                    condiciones.append('aversion_riesgo')
                elif rot == 'BTC_STRONGER':
                    condiciones.append('btc_mas_fuerte')
                elif rot == 'PAXG_STRONGER':
                    condiciones.append('paxg_mas_fuerte')
                elif rot == 'BTC_BULLISH':
                    condiciones.append('btc_alcista_unilateral')
                elif rot == 'BTC_BEARISH':
                    condiciones.append('btc_bajista_unilateral')
                elif rot == 'RATIO_BULLISH':
                    condiciones.append('ratio_alcista')
                elif rot == 'RATIO_BEARISH':
                    condiciones.append('ratio_bajista')
                
                # ============ FORTALEZA RELATIVA (COMPATIBILIDAD) ============
                rel = correlation.get('relative_strength')
                if rel == 'BTC_STRONGER':
                    condiciones.append('btc_mas_fuerte')
                elif rel == 'PAXG_STRONGER':
                    condiciones.append('paxg_mas_fuerte')
                
                # ============ CONDICIONES PARA NO ROTACIÓN ============
                if rot == 'NEUTRAL':
                    condiciones.append('rotacion_neutral')
                    
                    # Conflicto de tendencias
                    if btc_trend and ratio_trend and btc_trend != ratio_trend:
                        condiciones.append('conflicto_tendencias')
                        if btc_trend == 'bullish' and ratio_trend == 'bearish':
                            condiciones.append('conflicto_alcista_riesgo')
                        elif btc_trend == 'bearish' and ratio_trend == 'bullish':
                            condiciones.append('conflicto_bajista_refugio')
                    
                    # Tendencias débiles
                    if btc_adx < 20 and ratio_adx < 20:
                        condiciones.append('tendencias_debiles')
                        condiciones.append('sin_direccion_ambos')
                    elif btc_adx < 20:
                        condiciones.append('btc_sin_direccion')
                    elif ratio_adx < 20:
                        condiciones.append('ratio_sin_direccion')
                    
                    # Indecisión por datos insuficientes
                    if not btc_trend or not ratio_trend:
                        condiciones.append('datos_insuficientes_correlacion')
            
            # ============ HORARIOS (CAPA 7) ============
            if market_hours and isinstance(market_hours, dict):
                session = market_hours.get('session', '')
                if session == 'ASIAN':
                    condiciones.append('sesion_asiatica')
                    condiciones.append('liquidez_baja')
                elif session == 'EUROPEAN':
                    condiciones.append('sesion_europea')
                    condiciones.append('liquidez_media')
                elif session == 'AMERICAN':
                    condiciones.append('sesion_americana')
                    condiciones.append('liquidez_alta')
                
                if market_hours.get('overlap') != 'NONE':
                    condiciones.append('solapamiento_sesiones')
                    condiciones.append('liquidez_maxima')
                
                day = market_hours.get('day_type', '')
                if day == 'FRIDAY':
                    condiciones.append('viernes')
                    condiciones.append('cierre_semanal')
                elif day == 'WEEKEND':
                    condiciones.append('finde_semana')
                    condiciones.append('liquidez_minima')
                elif day == 'OPTIMAL':
                    condiciones.append('dia_optimo')
            
            # ============ CONFIRMACIÓN (CAPA 8) ============
            if confirmation and isinstance(confirmation, dict):
                status = confirmation.get('confirmation_status')
                if status == 'CONFIRMED':
                    condiciones.append('confirmacion_valida')
                    condiciones.append('ruptura_confirmada')
                elif status == 'REJECTED':
                    condiciones.append('confirmacion_rechazada')
                    condiciones.append('falso_breakout')
                    condiciones.append('trampa')
                    razon = confirmation.get('reason', [''])[0] if confirmation.get('reason') else ''
                    if 'falso_breakout_alcista' in str(razon):
                        condiciones.append('falso_breakout_alcista')
                        condiciones.append('trampa_alcista')
                    elif 'falso_breakdown_bajista' in str(razon):
                        condiciones.append('falso_breakdown_bajista')
                        condiciones.append('trampa_bajista')
                elif status == 'PENDING':
                    condiciones.append('confirmacion_pendiente')
                    condiciones.append('esperar_confirmacion')
                
                if confirmation.get('requires_wait'):
                    condiciones.append('requiere_espera')
                    wait = confirmation.get('wait_bars', 0)
                    if wait > 0:
                        condiciones.append(f'esperar_{wait}_velas')
                        condiciones.append('necesita_confirmacion')
            
            # ============ SENTIMIENTO (CAPA 9) - VERSIÓN COMPLETA ============
            if sentiment and isinstance(sentiment, dict):
                if sentiment.get('available', False):
                    current_value = sentiment.get('current_value', 50)
                    classification = sentiment.get('classification', 'Neutral')
                    trend_7d_pct = sentiment.get('trend_7d_pct', 0)
                    sentiment_bias = sentiment.get('sentiment_bias', 'neutral')
                    
                    # Añadir condición genérica de sentimiento disponible
                    condiciones.append('sentiment_available')
                    
                    # Clasificación por valor
                    if current_value < 20:
                        condiciones.append('sentiment_extreme_fear')
                    elif current_value < 40:
                        condiciones.append('sentiment_fear')
                    elif current_value < 60:
                        condiciones.append('sentiment_neutral')
                    elif current_value < 80:
                        condiciones.append('sentiment_greed')
                    else:
                        condiciones.append('sentiment_extreme_greed')
                    
                    # Clasificación por sesgo (del análisis)
                    if sentiment_bias == 'bullish_opportunity':
                        condiciones.append('sentiment_bullish_opportunity')
                        condiciones.append('oportunidad_panico')
                    elif sentiment_bias == 'bearish_opportunity':
                        condiciones.append('sentiment_bearish_opportunity')
                        condiciones.append('euforia_agotada')
                    elif sentiment_bias == 'bullish_moderate':
                        condiciones.append('sentiment_bullish_moderate')
                        condiciones.append('miedo_moderado')
                    elif sentiment_bias == 'bearish_moderate':
                        condiciones.append('sentiment_bearish_moderate')
                        condiciones.append('avaricia_moderada')
                    elif sentiment_bias == 'bullish_caution':
                        condiciones.append('sentiment_bullish_caution')
                        condiciones.append('euforia_sostenida')
                    elif sentiment_bias == 'bearish_caution':
                        condiciones.append('sentiment_bearish_caution')
                        condiciones.append('panico_estructural')
                    
                    # Tendencia del sentimiento
                    if trend_7d_pct > 5:
                        condiciones.append('sentiment_trending_up')
                    elif trend_7d_pct < -5:
                        condiciones.append('sentiment_trending_down')
                    
                    print(f"   📊 Sentimiento mapeado: {current_value} ({classification}) - {sentiment_bias}")
            
            # ============ NUEVA SECCIÓN: CONDICIONES DE LIQUIDACIONES ============
            if liquidation and isinstance(liquidation, dict):
                active_bins = liquidation.get('active_bins', [])
                total_long_bins = liquidation.get('total_long_bins', 0)
                total_short_bins = liquidation.get('total_short_bins', 0)
                total_long_weight = liquidation.get('total_long_weight', 0)
                total_short_weight = liquidation.get('total_short_weight', 0)
                total_spikes = liquidation.get('total_spikes', 0)
                
                # Convertir a millones para facilitar lectura
                long_weight_m = total_long_weight / 1_000_000
                short_weight_m = total_short_weight / 1_000_000
                
                # Condición 1: Oportunidad alcista por acumulación de SHORTS (resistencia)
                if total_short_weight > 100_000_000 and total_short_bins > 20:  # Más de 100M en shorts
                    condiciones.append('liquidation_bearish_opportunity')  # Shorts arriba = resistencia bajista
                    print(f"   🔴 Condición: liquidation_bearish_opportunity ({short_weight_m:.1f}M shorts en {total_short_bins} bins)")
                
                # Condición 2: Oportunidad bajista por acumulación de LONGS (soporte)
                if total_long_weight > 100_000_000 and total_long_bins > 20:  # Más de 100M en longs
                    condiciones.append('liquidation_bullish_opportunity')  # Longs abajo = soporte alcista
                    print(f"   🟢 Condición: liquidation_bullish_opportunity ({long_weight_m:.1f}M longs en {total_long_bins} bins)")
                
                # Condición 3: Alta concentración (pocos bins pero muy pesados)
                if total_long_bins < 10 and total_long_weight > 100_000_000:
                    condiciones.append('heavy_long_concentration')
                    print(f"   🟢 Condición: heavy_long_concentration ({long_weight_m:.1f}M en {total_long_bins} bins)")
                
                if total_short_bins < 10 and total_short_weight > 100_000_000:
                    condiciones.append('heavy_short_concentration')
                    print(f"   🔴 Condición: heavy_short_concentration ({short_weight_m:.1f}M en {total_short_bins} bins)")
                
                # Condición 4: Actividad reciente (spikes)
                if total_spikes > 5:
                    condiciones.append('recent_spike_activity')
                    print(f"   ⚡ Condición: recent_spike_activity ({total_spikes} spikes)")
                
                # Condición 5: Equilibrio de liquidaciones
                if abs(total_long_bins - total_short_bins) < 10 and total_long_bins > 30:
                    condiciones.append('liquidity_balance')
                    print(f"   ⚖️ Condición: liquidity_balance ({total_long_bins}L vs {total_short_bins}S)")
                
                # Condición 6: Sobreacumulación (posible reversión)
                if total_long_bins > 100 and total_long_weight > 200_000_000:
                    condiciones.append('long_extreme')
                    print(f"   ⚠️ Condición: long_extreme ({total_long_bins} bins, {long_weight_m:.1f}M)")
                
                if total_short_bins > 100 and total_short_weight > 200_000_000:
                    condiciones.append('short_extreme')
                    print(f"   ⚠️ Condición: short_extreme ({total_short_bins} bins, {short_weight_m:.1f}M)")
            # =====================================================================
           
            
            
            
            
            # ============ ESTRATEGIAS DE TRADERS ============
            for est in estrategias_consenso:
                est_lower = est.lower()
                condiciones.append(est_lower)
                
                if 'esperar' in est_lower or 'pullback' in est_lower:
                    condiciones.append('esperar_estrategia')
                if 'riesgo' in est_lower or 'caution' in est_lower:
                    condiciones.append('precaucion_estrategia')
                
                # ============ NUEVAS CONDICIONES DESDE ESTRATEGIAS ============
                # Sentimiento
                if 'oportunidad_panico' in est_lower:
                    condiciones.append('sentiment_bullish_opportunity')
                if 'panico_estructural' in est_lower:
                    condiciones.append('sentiment_bearish_caution')
                if 'euforia_agotada' in est_lower:
                    condiciones.append('sentiment_bearish_opportunity')
                if 'euforia_sostenida' in est_lower:
                    condiciones.append('sentiment_bullish_caution')
                if 'miedo_moderado' in est_lower:
                    condiciones.append('sentiment_bullish_moderate')
                if 'avaricia_moderada' in est_lower:
                    condiciones.append('sentiment_bearish_moderate')
                
                # Multiframe
                if 'alineacion_bullish_completa' in est_lower:
                    condiciones.append('alineacion_bullish_completa')
                if 'alineacion_bearish_completa' in est_lower:
                    condiciones.append('alineacion_bearish_completa')
                if 'pullback_oportunidad' in est_lower:
                    condiciones.append('pullback_oportunidad')
                if 'conflicto_menor' in est_lower:
                    condiciones.append('conflicto_menor_muestra_debilidad')
                if 'conflicto_mayor' in est_lower:
                    condiciones.append('conflicto_mayor_advierta_cambio')
                if 'acumulacion_en_zona_bajista' in est_lower:
                    condiciones.append('acumulacion_en_zona_bajista')
                if 'distribucion_en_zona_alcista' in est_lower:
                    condiciones.append('distribucion_en_zona_alcista')
                if 'ruptura_confirmada' in est_lower:
                    condiciones.append('ruptura_confirmada')
                
                # Bollinger
                if 'squeeze_alcista' in est_lower:
                    condiciones.append('squeeze_alcista')
                if 'squeeze_bajista' in est_lower:
                    condiciones.append('squeeze_bajista')
                if 'band_walk_alcista' in est_lower:
                    condiciones.append('band_walk_alcista')
                if 'band_walk_bajista' in est_lower:
                    condiciones.append('band_walk_bajista')
                if 'expansion_volatilidad' in est_lower:
                    condiciones.append('expansion_volatilidad')
                
                # Perfil Volumen
                if 'hvn_soporte' in est_lower:
                    condiciones.append('hvn_soporte')
                if 'hvn_resistencia' in est_lower:
                    condiciones.append('hvn_resistencia')
                if 'lvn_rotura' in est_lower:
                    condiciones.append('lvn_rotura')
                if 'poc_vwap_confluencia' in est_lower:
                    condiciones.append('poc_vwap_confluencia')
                
                # Stop Hunts
                if 'stop_hunt_long' in est_lower:
                    condiciones.append('stop_hunt_long')
                if 'stop_hunt_short' in est_lower:
                    condiciones.append('stop_hunt_short')
                if 'stop_hunt_ob' in est_lower:
                    condiciones.append('stop_hunt_ob')
            
            # ============ MULTIFRAME ============
            condiciones.append(f'timeframe_{timeframe}')
            
            if timeframe == '4h':
                condiciones.append('timeframe_intraday')
            elif timeframe == '12h':
                condiciones.append('timeframe_swing')
            elif timeframe == '1D':
                condiciones.append('timeframe_diario')
            elif timeframe == '1W':
                condiciones.append('timeframe_semanal')
            
            # Eliminar duplicados
            condiciones_unicas = list(set(condiciones))
            
            print(f"   📊 Total condiciones mapeadas: {len(condiciones_unicas)}")
            
            return condiciones_unicas
            
        except Exception as e:
            print(f"❌ Error en _mapear_condiciones_activas: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _filtrar_por_condiciones(self, tipo, condiciones_activas):
        """
        Filtra plantillas por tipo y condiciones activas.
        VERSIÓN COMPLETA Y ROBUSTA PARA EVITAR CONTRADICCIONES
        """
        seleccionadas = []
        
        for pid, plantilla in self.justification_bank.items():
            if plantilla.get('type') != tipo:
                continue
            
            condition = plantilla.get('condition', '')
            if not condition:
                # Si no tiene condición, siempre es elegible
                seleccionadas.append(pid)
                continue
            
            # Evaluar condición con operadores lógicos
            try:
                # Limpiar la condición
                condition = condition.strip()
                
                # Manejar múltiples condiciones separadas por OR
                if ' OR ' in condition:
                    condiciones_or = [c.strip() for c in condition.split(' OR ')]
                    
                    for cond_or in condiciones_or:
                        # Cada condición OR puede tener ANDs internos
                        if ' AND ' in cond_or:
                            condiciones_and = [c.strip() for c in cond_or.split(' AND ')]
                            # Verificar que TODAS las condiciones AND se cumplan
                            cumple_and = True
                            for cond in condiciones_and:
                                if cond and cond not in condiciones_activas:
                                    cumple_and = False
                                    break
                            if cumple_and:
                                seleccionadas.append(pid)
                                break
                        else:
                            # Condición OR simple
                            if cond_or in condiciones_activas:
                                seleccionadas.append(pid)
                                break
                
                # Manejar condiciones con AND solamente
                elif ' AND ' in condition:
                    condiciones_and = [c.strip() for c in condition.split(' AND ')]
                    cumple_and = True
                    for cond in condiciones_and:
                        if cond and cond not in condiciones_activas:
                            cumple_and = False
                            break
                    if cumple_and:
                        seleccionadas.append(pid)
                
                # Manejar condición simple
                else:
                    if condition in condiciones_activas:
                        seleccionadas.append(pid)
                        
            except Exception as e:
                print(f"⚠️ Error evaluando condición '{condition}' en plantilla {pid}: {e}")
                continue
        
        return seleccionadas
       
    
    # ========================================================================
    # OBTENCIÓN DE DATOS DE KUCOIN
    # ========================================================================
    
    # === CORRECCIÓN: TradingExpertSystem.get_kucoin_data - Manejo de errores ===
    # Ubicación: Reemplazar función completa
    
    def get_kucoin_data(self, symbol, interval):
        """Obtener datos de velas de KuCoin con manejo robusto de errores"""
        try:
            kucoin_interval = KUCOIN_INTERVALS.get(interval, '1day')
            url = f"https://api.kucoin.com/api/v1/market/candles?symbol={symbol}&type={kucoin_interval}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"Error HTTP {response.status_code} en KuCoin: {response.text[:200]}")
                return self._generate_fallback_data(symbol, interval)
            
            data = response.json()
            
            if data.get('code') != '200000' or 'data' not in data:
                print(f"Respuesta KuCoin inválida: {data.get('code', 'unknown')}")
                return self._generate_fallback_data(symbol, interval)
            
            candles = data['data']
            if not candles or len(candles) < 30:
                print(f"Datos insuficientes de KuCoin: {len(candles) if candles else 0} velas")
                return self._generate_fallback_data(symbol, interval)
            
            df = pd.DataFrame(candles, columns=['time', 'open', 'close', 'high', 'low', 'volume', 'turnover'])
            
            # Convertir tipos
            df['time'] = pd.to_datetime(df['time'].astype(int), unit='s')
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            df = df.sort_values('time')
            df = df.reset_index(drop=True)
            
            return df
            
        except requests.exceptions.Timeout:
            print(f"Timeout al obtener datos de KuCoin para {symbol} {interval}")
            return self._generate_fallback_data(symbol, interval)
        except requests.exceptions.ConnectionError:
            print(f"Error de conexión con KuCoin para {symbol} {interval}")
            return self._generate_fallback_data(symbol, interval)
        except Exception as e:
            print(f"Excepción inesperada en KuCoin: {e}")
            return self._generate_fallback_data(symbol, interval)
    
    def _generate_fallback_data(self, symbol, interval):
        """Generar datos sintéticos cuando falla KuCoin"""
        import numpy as np
        import pandas as pd
        from datetime import datetime, timedelta
        
        try:
            print(f"Generando datos sintéticos para {symbol} {interval}")
            
            # Determinar precio base según símbolo
            if symbol == 'BTC-USDT':
                base_price = 50000
                volatility = 0.02
            elif symbol == 'PAXG-USDT':
                base_price = 2000
                volatility = 0.01
            else:  # PAXG-BTC
                base_price = 0.04
                volatility = 0.015
            
            # Determinar cantidad de velas según intervalo
            if interval == '4h':
                periods = 100
                freq = '4H'
            elif interval == '12h':
                periods = 100
                freq = '12H'
            elif interval == '1D':
                periods = 100
                freq = 'D'
            else:  # 1W
                periods = 52
                freq = 'W'
            
            # Generar fechas
            end_date = datetime.now()
            dates = pd.date_range(end=end_date, periods=periods, freq=freq)
            
            # Generar precios con tendencia aleatoria
            np.random.seed(42)  # Para reproducibilidad
            returns = np.random.randn(periods) * volatility
            price_series = base_price * np.exp(np.cumsum(returns))
            
            # Generar OHLCV
            df = pd.DataFrame({
                'time': dates,
                'open': price_series * (1 + np.random.randn(periods) * 0.002),
                'high': price_series * (1 + abs(np.random.randn(periods) * 0.005)),
                'low': price_series * (1 - abs(np.random.randn(periods) * 0.005)),
                'close': price_series * (1 + np.random.randn(periods) * 0.001),
                'volume': np.abs(np.random.randn(periods) * 1000 + 5000)
            })
            
            # Ajustar para consistencia
            df['high'] = df[['open', 'close', 'high']].max(axis=1)
            df['low'] = df[['open', 'close', 'low']].min(axis=1)
            
            return df
            
        except Exception as e:
            print(f"Error generando datos sintéticos: {e}")
            return None
    # === FIN CORRECCIÓN get_kucoin_data ===
    
    # ========================================================================
    # NUEVA FUNCIÓN: OBTENER FEAR & GREED INDEX
    # ========================================================================
    def get_fear_greed_data(self, limit=30):
        """
        Obtener datos del Fear & Greed Index de Alternative.me
        Args:
            limit: número de días a obtener (0 = todos, 1 = solo hoy, 30 = último mes)
        Returns:
            Diccionario con datos del índice o None si hay error
        """
        try:
            # Verificar caché
            global FEAR_GREED_CACHE
            now = time.time()
            
            if (FEAR_GREED_CACHE['data'] is not None and 
                FEAR_GREED_CACHE['last_update'] is not None and
                now - FEAR_GREED_CACHE['last_update'] < FEAR_GREED_CACHE['cache_duration']):
                print(f"📊 Usando datos en caché de Fear & Greed (actualizado hace {int((now - FEAR_GREED_CACHE['last_update'])/60)} min)")
                return FEAR_GREED_CACHE['data']
            
            # Construir URL
            url = f"{FEAR_GREED_API_URL}?limit={limit}"
            print(f"📡 Obteniendo Fear & Greed Index de {url}")
            
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ Error HTTP {response.status_code} al obtener Fear & Greed")
                return None
            
            data = response.json()
            
            if 'data' not in data:
                print(f"❌ Respuesta de Fear & Greed no contiene datos: {data}")
                return None
            
            # Procesar datos
            result = {
                'current': None,
                'historical': [],
                'trend_7d': None,
                'trend_30d': None,
                'volatility': None,
                'classification': None
            }
            
            # Procesar cada entrada
            for item in data['data']:
                processed = {
                    'value': int(item['value']),
                    'classification': item['value_classification'],
                    'timestamp': int(item['timestamp']),
                    'date': datetime.fromtimestamp(int(item['timestamp'])).strftime('%Y-%m-%d')
                }
                result['historical'].append(processed)
                
                # El primero es el más reciente
                if result['current'] is None:
                    result['current'] = processed
                    result['classification'] = processed['classification']
            
            # Calcular tendencias si tenemos suficientes datos
            if len(result['historical']) >= 7:
                values_7d = [item['value'] for item in result['historical'][:7]]
                result['trend_7d'] = values_7d[0] - values_7d[-1]  # Positivo = mejora
                result['trend_7d_pct'] = ((values_7d[0] - values_7d[-1]) / values_7d[-1]) * 100 if values_7d[-1] > 0 else 0
            else:
                result['trend_7d'] = 0
                result['trend_7d_pct'] = 0
            
            if len(result['historical']) >= 30:
                values_30d = [item['value'] for item in result['historical'][:30]]
                result['trend_30d'] = values_30d[0] - values_30d[-1]
                result['trend_30d_pct'] = ((values_30d[0] - values_30d[-1]) / values_30d[-1]) * 100 if values_30d[-1] > 0 else 0
                
                # Calcular volatilidad (desviación estándar)
                import numpy as np
                result['volatility'] = float(np.std(values_30d))
            else:
                result['trend_30d'] = 0
                result['trend_30d_pct'] = 0
                result['volatility'] = 0
            
            # Guardar en caché
            FEAR_GREED_CACHE['data'] = result
            FEAR_GREED_CACHE['last_update'] = now
            
            print(f"✅ Fear & Greed obtenido: {result['current']['value']} ({result['current']['classification']})")
            print(f"   Tendencia 7d: {result['trend_7d']:+.1f} puntos ({result['trend_7d_pct']:+.1f}%)")
            
            return result
            
        except Exception as e:
            print(f"❌ Error obteniendo Fear & Greed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    

    # ========================================================================
    # SISTEMA DE VOTACIÓN PONDERADA POR CAPAS
    # ========================================================================
    
    # === FUNCIÓN COMPLETA: analyze_trend_layer ===
    # Ubicación: Reemplazar entre línea ~1000 y línea ~1080 aproximadamente
    # CORRECCIÓN DEL ERROR: missing 1 required positional argument: 'indicators'
    
    # === CORRECCIÓN: analyze_trend_layer - Eliminar parámetro indicators ===
    # Ubicación: Reemplazar función analyze_trend_layer completa
    
    def analyze_trend_layer(self, df):
        """Capa 1: Análisis de Tendencia - Establece marco principal con Parabolic SAR"""
        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            
            n = len(close)
            if n < 50:
                return {
                    'direction': 'neutral',
                    'confidence': 0,
                    'strength': 'unknown',
                    'strength_score': 0,
                    'adx': 0, # adx_value
                    'plus_di': 0,
                    'minus_di': 0,
                    'votes': [],
                    'score': 0,
                    'indicators': {}
                }
            
            # Calcular indicadores
            ema9 = self.calculate_ema(close, 9)
            ema21 = self.calculate_ema(close, 21)
            ema50 = self.calculate_ema(close, 50)
            ema200 = self.calculate_ema(close, 200)
            
            adx_data = self.calculate_adx(high, low, close, 14)
            supertrend = self.calculate_supertrend(high, low, close, 10, 3)
            ichimoku = self.calculate_ichimoku(high, low, close)
            
            # Calcular Parabolic SAR (usando la función existente)
            psar = self.calculate_parabolic_sar(high, low)
            psar_values = psar['sar']
            psar_trend = psar['trend']
            
            votes = []
            direction_score = 0
            
            # ============ DMI es el más importante para dirección ============
            plus_di = 0
            minus_di = 0
            if len(adx_data['plus_di']) > 0 and len(adx_data['minus_di']) > 0:
                plus_di = adx_data['plus_di'][-1]
                minus_di = adx_data['minus_di'][-1]
                
                # DMI define la dirección PRINCIPAL
                if plus_di > minus_di:
                    votes.append({'direction': 'bullish', 'weight': 5, 'source': 'dmi_dominant_bull'})
                    direction_score += 5
                elif minus_di > plus_di:
                    votes.append({'direction': 'bearish', 'weight': 5, 'source': 'dmi_dominant_bear'})
                    direction_score -= 5
                
                # Cruce DMI (peso extra)
                if len(adx_data['plus_di']) > 1 and len(adx_data['minus_di']) > 1:
                    if plus_di > minus_di and adx_data['plus_di'][-2] <= adx_data['minus_di'][-2]:
                        votes.append({'direction': 'bullish', 'weight': 3, 'source': 'dmi_cross_bull'})
                        direction_score += 3
                    elif plus_di < minus_di and adx_data['plus_di'][-2] >= adx_data['minus_di'][-2]:
                        votes.append({'direction': 'bearish', 'weight': 3, 'source': 'dmi_cross_bear'})
                        direction_score -= 3
            
            # ============ PARABOLIC SAR (señales de cambio) ============
            if len(psar_trend) > 1:
                # Detectar cambio de tendencia
                if psar_trend[-1] == 1 and psar_trend[-2] == -1:
                    votes.append({'direction': 'bullish', 'weight': 4, 'source': 'psar_reversal_bull'})
                    direction_score += 4
                    print(f"   🔄 Parabolic SAR: CAMBIO A ALCISTA detectado")
                elif psar_trend[-1] == -1 and psar_trend[-2] == 1:
                    votes.append({'direction': 'bearish', 'weight': 4, 'source': 'psar_reversal_bear'})
                    direction_score -= 4
                    print(f"   🔄 Parabolic SAR: CAMBIO A BAJISTA detectado")
                
                # Posición actual
                if psar_trend[-1] == 1:
                    votes.append({'direction': 'bullish', 'weight': 2, 'source': 'psar_bull'})
                    direction_score += 2
                elif psar_trend[-1] == -1:
                    votes.append({'direction': 'bearish', 'weight': 2, 'source': 'psar_bear'})
                    direction_score -= 2
            
            # EMA Alignment (peso 3) - SOLO si confirma DMI
            if len(ema9) > 0 and len(ema21) > 0 and len(ema50) > 0 and len(ema200) > 0:
                if close[-1] > ema9[-1] > ema21[-1] > ema50[-1] > ema200[-1]:
                    if direction_score > 0:
                        votes.append({'direction': 'bullish', 'weight': 3, 'source': 'ema_alignment_bull'})
                        direction_score += 3
                elif close[-1] < ema9[-1] < ema21[-1] < ema50[-1] < ema200[-1]:
                    if direction_score < 0:
                        votes.append({'direction': 'bearish', 'weight': 3, 'source': 'ema_alignment_bear'})
                        direction_score -= 3
            
            # EMA 9/21 Cross (peso 2)
            if len(ema9) > 1 and len(ema21) > 1:
                if ema9[-1] > ema21[-1] and ema9[-2] <= ema21[-2]:
                    if direction_score > -2:
                        votes.append({'direction': 'bullish', 'weight': 2, 'source': 'ema_cross_bull'})
                        direction_score += 2
                elif ema9[-1] < ema21[-1] and ema9[-2] >= ema21[-2]:
                    if direction_score < 2:
                        votes.append({'direction': 'bearish', 'weight': 2, 'source': 'ema_cross_bear'})
                        direction_score -= 2
            
            # SuperTrend (peso 3)
            if len(supertrend['trend']) > 0:
                if supertrend['trend'][-1] == 1:
                    if direction_score > -3:
                        votes.append({'direction': 'bullish', 'weight': 3, 'source': 'supertrend_bull'})
                        direction_score += 3
                elif supertrend['trend'][-1] == -1:
                    if direction_score < 3:
                        votes.append({'direction': 'bearish', 'weight': 3, 'source': 'supertrend_bear'})
                        direction_score -= 3
            
            # Ichimoku (peso 2)
            if len(ichimoku['senkou_a_shifted']) > 0 and len(ichimoku['senkou_b_shifted']) > 0:
                if close[-1] > ichimoku['senkou_a_shifted'][-1] and close[-1] > ichimoku['senkou_b_shifted'][-1]:
                    if len(ichimoku['tenkan']) > 0 and len(ichimoku['kijun']) > 0:
                        if ichimoku['tenkan'][-1] > ichimoku['kijun'][-1]:
                            if direction_score > -2:
                                votes.append({'direction': 'bullish', 'weight': 2, 'source': 'ichimoku_bull'})
                                direction_score += 2
                elif close[-1] < ichimoku['senkou_a_shifted'][-1] and close[-1] < ichimoku['senkou_b_shifted'][-1]:
                    if len(ichimoku['tenkan']) > 0 and len(ichimoku['kijun']) > 0:
                        if ichimoku['tenkan'][-1] < ichimoku['kijun'][-1]:
                            if direction_score < 2:
                                votes.append({'direction': 'bearish', 'weight': 2, 'source': 'ichimoku_bear'})
                                direction_score -= 2
            
            # ADX Strength (solo para fuerza, no dirección) se cambio adx_value a adx
            adx = 0
            if len(adx_data['adx']) > 0:
                adx = adx_data['adx'][-1]
            
            if adx < 20:
                strength = 'weak'
                strength_score = 0
            elif adx < 40:
                strength = 'normal'
                strength_score = 1
            else:
                strength = 'strong'
                strength_score = 2
            
            # Determinar dirección basada en DMI y Parabolic SAR
            if plus_di > minus_di and abs(plus_di - minus_di) > 5:
                direction = 'bullish'
                confidence = min(100, 50 + abs(plus_di - minus_di) * 2)
            elif minus_di > plus_di and abs(minus_di - plus_di) > 5:
                direction = 'bearish'
                confidence = min(100, 50 + abs(minus_di - plus_di) * 2)
            elif direction_score > 3:
                direction = 'bullish'
                confidence = 60
            elif direction_score < -3:
                direction = 'bearish'
                confidence = 60
            else:
                direction = 'neutral'
                confidence = 50
            
            # Obtener valores para indicadores
            ema9_val = float(ema9[-1]) if len(ema9) > 0 else 0
            ema21_val = float(ema21[-1]) if len(ema21) > 0 else 0
            ema50_val = float(ema50[-1]) if len(ema50) > 0 else 0
            ema200_val = float(ema200[-1]) if len(ema200) > 0 else 0
            supertrend_val = float(supertrend['supertrend'][-1]) if len(supertrend['supertrend']) > 0 else 0
            supertrend_trend = 'bullish' if len(supertrend['trend']) > 0 and supertrend['trend'][-1] == 1 else 'bearish' if len(supertrend['trend']) > 0 and supertrend['trend'][-1] == -1 else 'neutral'
            
            # Determinar tendencia de Parabolic SAR
            psar_trend_val = 'neutral'
            if len(psar_trend) > 0:
                if psar_trend[-1] == 1:
                    psar_trend_val = 'bullish'
                elif psar_trend[-1] == -1:
                    psar_trend_val = 'bearish'
            
            # Guardar valores previos de EMAs para detectar cruces
            ema9_prev = float(ema9[-2]) if len(ema9) > 1 else ema9_val
            ema21_prev = float(ema21[-2]) if len(ema21) > 1 else ema21_val
            
            print(f"📊 TREND LAYER - DMI: +DI={plus_di:.1f}, -DI={minus_di:.1f}, ADX={adx:.1f}") # adx_value
            print(f"   Parabolic SAR trend: {psar_trend_val}")
            print(f"   Dirección determinada: {direction} (score={direction_score})")
            
            return {
                'direction': direction,
                'confidence': confidence,
                'strength': strength,
                'strength_score': strength_score,
                'adx': float(adx), #adx_value
                'plus_di': float(plus_di),
                'minus_di': float(minus_di),
                'votes': votes,
                'score': direction_score,
                'indicators': {
                    'ema9': ema9_val,
                    'ema21': ema21_val,
                    'ema50': ema50_val,
                    'ema200': ema200_val,
                    'ema9_prev': ema9_prev,
                    'ema21_prev': ema21_prev,
                    'supertrend': supertrend_val,
                    'supertrend_trend': supertrend_trend,
                    'parabolic_sar_trend': psar_trend_val,
                    'ichimoku_cloud': ichimoku.get('cloud_position', 'neutral'),
                    'ichimoku_tk': 'bullish' if len(ichimoku.get('tenkan', [])) > 0 and len(ichimoku.get('kijun', [])) > 0 and ichimoku['tenkan'][-1] > ichimoku['kijun'][-1] else 'bearish' if len(ichimoku.get('tenkan', [])) > 0 and len(ichimoku.get('kijun', [])) > 0 and ichimoku['tenkan'][-1] < ichimoku['kijun'][-1] else 'neutral'
                }
            }
        except Exception as e:
            print(f"Error en analyze_trend_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'direction': direction,
                'confidence': confidence,
                'strength': strength,
                'strength_score': strength_score,
                'adx': float(adx),  # ← CAMBIADO de 'adx_value' a 'adx'
                'plus_di': float(plus_di),
                'minus_di': float(minus_di),
                'votes': votes,
                'score': direction_score,
                'indicators': {
                    'ema9': ema9_val,
                    'ema21': ema21_val,
                    'ema50': ema50_val,
                    'ema200': ema200_val,
                    'ema9_prev': ema9_prev,
                    'ema21_prev': ema21_prev,
                    'supertrend': supertrend_val,
                    'supertrend_trend': supertrend_trend,
                    'parabolic_sar_trend': psar_trend_val,
                    'ichimoku_cloud': ichimoku.get('cloud_position', 'neutral'),
                    'ichimoku_tk': 'bullish' if len(ichimoku.get('tenkan', [])) > 0 and len(ichimoku.get('kijun', [])) > 0 and ichimoku['tenkan'][-1] > ichimoku['kijun'][-1] else 'bearish' if len(ichimoku.get('tenkan', [])) > 0 and len(ichimoku.get('kijun', [])) > 0 and ichimoku['tenkan'][-1] < ichimoku['kijun'][-1] else 'neutral'
                }
            }
    # === FIN CORRECCIÓN analyze_trend_layer ===
    
    # === FUNCIÓN COMPLETA: analyze_momentum_layer ===
    # Ubicación: Reemplazar entre línea ~1080 y línea ~1200 aproximadamente
    
    def analyze_momentum_layer(self, df):
        """Capa 2: Análisis de Momentum - Fuerza, timing y divergencias ocultas"""
        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            
            n = len(close)
            if n < 30:
                return {
                    'direction': 'neutral',
                    'confidence': 0,
                    'score': 0,
                    'votes': [],
                    'divergences': [],
                    'hidden_divergences': [],
                    'divergence_details': [],
                    'indicators': {}
                }
            
            rsi = self.calculate_rsi(close, 14)
            macd = self.calculate_macd(close, 12, 26, 9)
            stoch = self.calculate_stochastic(high, low, close, 14, 3)
            rsi_maverick = self.calculate_rsi_maverick(close, 20, 2.0)
            squeeze = self.calculate_squeeze_momentum(high, low, close)
            williams = self.calculate_williams_r(high, low, close, 14)
            cci = self.calculate_cci(high, low, close, 20)
            
            votes = []
            divergence_signals = []
            hidden_divergence_signals = []
            divergence_details = []
            
            direction_score = 0
            
            # RSI (peso 2)
            if rsi[-1] < 30:
                votes.append({'direction': 'bullish', 'weight': 2, 'source': 'rsi_oversold'})
                direction_score += 2
            elif rsi[-1] > 70:
                votes.append({'direction': 'bearish', 'weight': 2, 'source': 'rsi_overbought'})
                direction_score -= 2
            elif rsi[-1] > 50 and rsi[-2] <= 50:
                votes.append({'direction': 'bullish', 'weight': 1, 'source': 'rsi_cross_50'})
                direction_score += 1
            elif rsi[-1] < 50 and rsi[-2] >= 50:
                votes.append({'direction': 'bearish', 'weight': 1, 'source': 'rsi_cross_50_bear'})
                direction_score -= 1
            
            # RSI Maverick (peso 3)
            if rsi_maverick[-1] < 0.2:
                votes.append({'direction': 'bullish', 'weight': 3, 'source': 'rsi_maverick_extreme_low'})
                direction_score += 3
            elif rsi_maverick[-1] > 0.8:
                votes.append({'direction': 'bearish', 'weight': 3, 'source': 'rsi_maverick_extreme_high'})
                direction_score -= 3
            elif rsi_maverick[-1] > rsi_maverick[-2] and rsi_maverick[-1] < 0.5:
                votes.append({'direction': 'bullish', 'weight': 2, 'source': 'rsi_maverick_rising'})
                direction_score += 2
            elif rsi_maverick[-1] < rsi_maverick[-2] and rsi_maverick[-1] > 0.5:
                votes.append({'direction': 'bearish', 'weight': 2, 'source': 'rsi_maverick_falling'})
                direction_score -= 2
            
            # MACD (peso 2)
            if macd['histogram'][-1] > 0 and macd['histogram'][-2] <= 0:
                votes.append({'direction': 'bullish', 'weight': 2, 'source': 'macd_histogram_cross_bull'})
                direction_score += 2
            elif macd['histogram'][-1] < 0 and macd['histogram'][-2] >= 0:
                votes.append({'direction': 'bearish', 'weight': 2, 'source': 'macd_histogram_cross_bear'})
                direction_score -= 2
            elif macd['macd'][-1] > macd['signal'][-1] and macd['macd'][-2] <= macd['signal'][-2]:
                votes.append({'direction': 'bullish', 'weight': 2, 'source': 'macd_cross_bull'})
                direction_score += 2
            elif macd['macd'][-1] < macd['signal'][-1] and macd['macd'][-2] >= macd['signal'][-2]:
                votes.append({'direction': 'bearish', 'weight': 2, 'source': 'macd_cross_bear'})
                direction_score -= 2
            
            # Estocástico (peso 1)
            if stoch['%K'][-1] < 20 and stoch['%K'][-1] > stoch['%D'][-1] and stoch['%K'][-2] <= stoch['%D'][-2]:
                votes.append({'direction': 'bullish', 'weight': 1, 'source': 'stoch_cross_bull'})
                direction_score += 1
            elif stoch['%K'][-1] > 80 and stoch['%K'][-1] < stoch['%D'][-1] and stoch['%K'][-2] >= stoch['%D'][-2]:
                votes.append({'direction': 'bearish', 'weight': 1, 'source': 'stoch_cross_bear'})
                direction_score -= 1
            
            # Williams %R (peso 1)
            if williams[-1] < -80:
                votes.append({'direction': 'bullish', 'weight': 1, 'source': 'williams_oversold'})
                direction_score += 1
            elif williams[-1] > -20:
                votes.append({'direction': 'bearish', 'weight': 1, 'source': 'williams_overbought'})
                direction_score -= 1
            
            # CCI (peso 1)
            if cci[-1] < -100:
                votes.append({'direction': 'bullish', 'weight': 1, 'source': 'cci_oversold'})
                direction_score += 1
            elif cci[-1] > 100:
                votes.append({'direction': 'bearish', 'weight': 1, 'source': 'cci_overbought'})
                direction_score -= 1
            
            # Squeeze Momentum (peso 2)
            if len(squeeze['momentum']) > 0:
                if squeeze['momentum'][-1] > 0 and squeeze['momentum'][-2] <= 0:
                    votes.append({'direction': 'bullish', 'weight': 2, 'source': 'squeeze_momentum_bull'})
                    direction_score += 2
                elif squeeze['momentum'][-1] < 0 and squeeze['momentum'][-2] >= 0:
                    votes.append({'direction': 'bearish', 'weight': 2, 'source': 'squeeze_momentum_bear'})
                    direction_score -= 2
            
            # ============ DIVERGENCIAS REGULARES ============
            if len(close) > 30 and len(rsi) > 30:
                # ---- RSI divergences ----
                price_low_5 = min(close[-5:])
                price_low_10 = min(close[-10:-5]) if len(close) > 10 else price_low_5
                rsi_low_5 = min(rsi[-5:])
                rsi_low_10 = min(rsi[-10:-5]) if len(rsi) > 10 else rsi_low_5
                
                if price_low_5 < price_low_10 and rsi_low_5 > rsi_low_10:
                    votes.append({'direction': 'bullish', 'weight': 3, 'source': 'rsi_divergence_bull'})
                    divergence_signals.append('rsi_bull_divergence')
                    divergence_details.append({
                        'type': 'bullish',
                        'oscillator': 'RSI',
                        'description': f'RSI en {rsi_low_5:.1f} vs {rsi_low_10:.1f}'
                    })
                    direction_score += 3
                
                price_high_5 = max(close[-5:])
                price_high_10 = max(close[-10:-5]) if len(close) > 10 else price_high_5
                rsi_high_5 = max(rsi[-5:])
                rsi_high_10 = max(rsi[-10:-5]) if len(rsi) > 10 else rsi_high_5
                
                if price_high_5 > price_high_10 and rsi_high_5 < rsi_high_10:
                    votes.append({'direction': 'bearish', 'weight': 3, 'source': 'rsi_divergence_bear'})
                    divergence_signals.append('rsi_bear_divergence')
                    divergence_details.append({
                        'type': 'bearish',
                        'oscillator': 'RSI',
                        'description': f'RSI en {rsi_high_5:.1f} vs {rsi_high_10:.1f}'
                    })
                    direction_score -= 3
                
                # ---- MACD divergences ----
                if len(macd['histogram']) > 15:
                    macd_low_5 = min(macd['histogram'][-5:])
                    macd_low_10 = min(macd['histogram'][-10:-5]) if len(macd['histogram']) > 10 else macd_low_5
                    
                    if price_low_5 < price_low_10 and macd_low_5 > macd_low_10:
                        votes.append({'direction': 'bullish', 'weight': 3, 'source': 'macd_divergence_bull'})
                        divergence_signals.append('macd_bull_divergence')
                        divergence_details.append({
                            'type': 'bullish',
                            'oscillator': 'MACD',
                            'description': f'MACD en {macd_low_5:.2f} vs {macd_low_10:.2f}'
                        })
                        direction_score += 3
                    
                    macd_high_5 = max(macd['histogram'][-5:])
                    macd_high_10 = max(macd['histogram'][-10:-5]) if len(macd['histogram']) > 10 else macd_high_5
                    
                    if price_high_5 > price_high_10 and macd_high_5 < macd_high_10:
                        votes.append({'direction': 'bearish', 'weight': 3, 'source': 'macd_divergence_bear'})
                        divergence_signals.append('macd_bear_divergence')
                        divergence_details.append({
                            'type': 'bearish',
                            'oscillator': 'MACD',
                            'description': f'MACD en {macd_high_5:.2f} vs {macd_high_10:.2f}'
                        })
                        direction_score -= 3
                
                # ---- Estocástico divergences ----
                if len(stoch['%K']) > 15:
                    stoch_low_5 = min(stoch['%K'][-5:])
                    stoch_low_10 = min(stoch['%K'][-10:-5]) if len(stoch['%K']) > 10 else stoch_low_5
                    
                    if price_low_5 < price_low_10 and stoch_low_5 > stoch_low_10:
                        votes.append({'direction': 'bullish', 'weight': 3, 'source': 'stoch_divergence_bull'})
                        divergence_signals.append('stoch_bull_divergence')
                        divergence_details.append({
                            'type': 'bullish',
                            'oscillator': 'Estocástico',
                            'description': f'%K en {stoch_low_5:.1f} vs {stoch_low_10:.1f}'
                        })
                        direction_score += 3
                    
                    stoch_high_5 = max(stoch['%K'][-5:])
                    stoch_high_10 = max(stoch['%K'][-10:-5]) if len(stoch['%K']) > 10 else stoch_high_5
                    
                    if price_high_5 > price_high_10 and stoch_high_5 < stoch_high_10:
                        votes.append({'direction': 'bearish', 'weight': 3, 'source': 'stoch_divergence_bear'})
                        divergence_signals.append('stoch_bear_divergence')
                        divergence_details.append({
                            'type': 'bearish',
                            'oscillator': 'Estocástico',
                            'description': f'%K en {stoch_high_5:.1f} vs {stoch_high_10:.1f}'
                        })
                        direction_score -= 3
                
                # ---- RSI Maverick divergences ----
                if len(rsi_maverick) > 15:
                    rsim_low_5 = min(rsi_maverick[-5:])
                    rsim_low_10 = min(rsi_maverick[-10:-5]) if len(rsi_maverick) > 10 else rsim_low_5
                    
                    if price_low_5 < price_low_10 and rsim_low_5 > rsim_low_10:
                        votes.append({'direction': 'bullish', 'weight': 3, 'source': 'rsi_maverick_divergence_bull'})
                        divergence_signals.append('rsi_maverick_bull_divergence')
                        divergence_details.append({
                            'type': 'bullish',
                            'oscillator': 'RSI Maverick',
                            'description': f'%B en {rsim_low_5:.2f} vs {rsim_low_10:.2f}'
                        })
                        direction_score += 3
                    
                    rsim_high_5 = max(rsi_maverick[-5:])
                    rsim_high_10 = max(rsi_maverick[-10:-5]) if len(rsi_maverick) > 10 else rsim_high_5
                    
                    if price_high_5 > price_high_10 and rsim_high_5 < rsim_high_10:
                        votes.append({'direction': 'bearish', 'weight': 3, 'source': 'rsi_maverick_divergence_bear'})
                        divergence_signals.append('rsi_maverick_bear_divergence')
                        divergence_details.append({
                            'type': 'bearish',
                            'oscillator': 'RSI Maverick',
                            'description': f'%B en {rsim_high_5:.2f} vs {rsim_high_10:.2f}'
                        })
                        direction_score -= 3
            
            # ============ DIVERGENCIAS OCULTAS ============
            if len(close) > 30 and len(rsi) > 30:
                # Divergencia oculta alcista
                price_low_5 = min(close[-5:])
                price_low_15 = min(close[-15:-5]) if len(close) > 15 else price_low_5
                rsi_low_5 = min(rsi[-5:])
                rsi_low_15 = min(rsi[-15:-5]) if len(rsi) > 15 else rsi_low_5
                
                if price_low_5 > price_low_15 and rsi_low_5 < rsi_low_15:
                    votes.append({'direction': 'bullish', 'weight': 4, 'source': 'hidden_divergence_bull'})
                    hidden_divergence_signals.append('hidden_bull')
                    divergence_details.append({
                        'type': 'hidden_bullish',
                        'oscillator': 'RSI',
                        'description': 'Divergencia oculta alcista'
                    })
                    direction_score += 4
                
                # Divergencia oculta bajista
                price_high_5 = max(close[-5:])
                price_high_15 = max(close[-15:-5]) if len(close) > 15 else price_high_5
                rsi_high_5 = max(rsi[-5:])
                rsi_high_15 = max(rsi[-15:-5]) if len(rsi) > 15 else rsi_high_5
                
                if price_high_5 < price_high_15 and rsi_high_5 > rsi_high_15:
                    votes.append({'direction': 'bearish', 'weight': 4, 'source': 'hidden_divergence_bear'})
                    hidden_divergence_signals.append('hidden_bear')
                    divergence_details.append({
                        'type': 'hidden_bearish',
                        'oscillator': 'RSI',
                        'description': 'Divergencia oculta bajista'
                    })
                    direction_score -= 4
            
            # Determinar dirección
            if direction_score > 6:
                direction = 'bullish'
                confidence = min(100, 50 + abs(direction_score) * 4)
            elif direction_score < -6:
                direction = 'bearish'
                confidence = min(100, 50 + abs(direction_score) * 4)
            else:
                direction = 'neutral'
                confidence = 50 - abs(direction_score) * 2
            
            return {
                'direction': direction,
                'confidence': confidence,
                'score': direction_score,
                'votes': votes,
                'divergences': divergence_signals,
                'hidden_divergences': hidden_divergence_signals,
                'divergence_details': divergence_details,
                'indicators': {
                    'rsi': float(rsi[-1]) if len(rsi) > 0 else 50,
                    'rsi_maverick': float(rsi_maverick[-1]) if len(rsi_maverick) > 0 else 0.5,
                    'macd_histogram': float(macd['histogram'][-1]) if len(macd['histogram']) > 0 else 0,
                    'macd_hist_pre': float(macd['histogram'][-2]) if len(macd['histogram']) > 1 else 0,
                    'stoch_k': float(stoch['%K'][-1]) if len(stoch['%K']) > 0 else 50,
                    'stoch_d': float(stoch['%D'][-1]) if len(stoch['%D']) > 0 else 50,
                    'williams': float(williams[-1]) if len(williams) > 0 else -50,
                    'cci': float(cci[-1]) if len(cci) > 0 else 0,
                    'squeeze_momentum': float(squeeze['momentum'][-1]) if len(squeeze['momentum']) > 0 else 0
                }
            }
        except Exception as e:
            print(f"Error en analyze_momentum_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'direction': 'neutral',
                'confidence': 0,
                'score': 0,
                'votes': [],
                'divergences': [],
                'hidden_divergences': [],
                'divergence_details': [],
                'indicators': {}
            }
    # === FIN analyze_momentum_layer ===
    
    # === FUNCIÓN COMPLETA: analyze_volatility_layer ===
    # Ubicación: Reemplazar entre línea ~1200 y línea ~1250 aproximadamente
    # Agregar squeeze_length para detectar compresión prolongada
    
    def analyze_volatility_layer(self, df):
        """Capa 3: Análisis de Volatilidad - Espacio, riesgo y apalancamiento"""
        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            
            atr = self.calculate_atr(high, low, close, 14)
            bb = self.calculate_bollinger_bands(close, 20, 2)
            ftm = self.calculate_trend_strength_maverick(close, 20, 2.0)
            squeeze = self.calculate_squeeze_momentum(high, low, close)
            
            current_price = close[-1] if len(close) > 0 else 0
            atr_pct = (atr[-1] / current_price * 100) if current_price != 0 else 0
            
            bb_width = ((bb['upper'][-1] - bb['lower'][-1]) / bb['middle'][-1] * 100) if bb['middle'][-1] != 0 else 0
            bb_position = (current_price - bb['lower'][-1]) / (bb['upper'][-1] - bb['lower'][-1]) if (bb['upper'][-1] - bb['lower'][-1]) != 0 else 0.5
            
            # Determinar nivel de volatilidad
            if atr_pct < 1:
                volatility_level = 'low'
            elif atr_pct < 3:
                volatility_level = 'medium'
            elif atr_pct < 5:
                volatility_level = 'high'
            else:
                volatility_level = 'extreme'
            
            operability = True
            no_trade_reason = []
            squeeze_length = 0
            
            # Calcular duración de la compresión
            if len(squeeze['squeeze_on']) > 0:
                for i in range(min(30, len(squeeze['squeeze_on']) - 1), 0, -1):
                    if squeeze['squeeze_on'][-i]:
                        squeeze_length += 1
                    else:
                        break
            
            # ============ ESTADOS DEL FTMaverick ============
            ftm_strength = ftm['trend_strength'][-1] if len(ftm['trend_strength']) > 0 else 0
            ftm_bb_width = abs(ftm_strength)  # El valor absoluto es el ancho de banda
            ftm_signal = ftm['strength_signals'][-1] if len(ftm['strength_signals']) > 0 else 'NEUTRAL'
            ftm_color = 'green' if ftm_strength > 0 else 'red' if ftm_strength < 0 else 'gray'
            
            # Determinar estado según clasificación original
            ftm_state = ftm_signal
            if ftm_signal == 'STRONG_UP':
                ftm_description = 'Expansión fuerte (alcista)'
            elif ftm_signal == 'WEAK_UP':
                ftm_description = 'Expansión débil'
            elif ftm_signal == 'STRONG_DOWN':
                ftm_description = 'Contracción fuerte - ZONA DE NO OPERACIÓN'
            elif ftm_signal == 'WEAK_DOWN':
                ftm_description = 'Contracción débil'
            else:
                ftm_description = 'Neutral'
            
            # Zona de no-operación: STRONG_DOWN = ancho alto pero decreciente
            ftm_no_trade = False
            if ftm_signal == 'STRONG_DOWN':
                ftm_no_trade = True
                no_trade_reason.append('ftm_strong_down')
                operability = False
            
            # Contracción prolongada (rojo sostenido)
            contraction_count = 0
            for val in ftm['trend_strength'][-10:]:
                if val < 0:  # Rojo = decreciente
                    contraction_count += 1
                else:
                    break
            
            if contraction_count >= 8:
                no_trade_reason.append('ftm_prolonged_contraction')
                if contraction_count >= 12:
                    operability = False
            
            # Otras condiciones de no operabilidad
            if atr_pct > 5:
                operability = False
                no_trade_reason.append('volatility_extreme')
            
            if len(squeeze['squeeze_on']) > 0 and squeeze['squeeze_on'][-1]:
                if squeeze_length >= 8:
                    operability = False
                    no_trade_reason.append('prolonged_squeeze')
            
            # ============ CÁLCULO DE APALANCAMIENTO POR VOLATILIDAD ============
            # Fórmula: apalancamiento base 15 / ATR% (inversamente proporcional)
            if atr_pct > 0:
                # A mayor ATR, menor apalancamiento
                suggested_leverage_raw = 15 / atr_pct
                # Limitar entre 2x y 10x
                suggested_leverage = max(2, min(10, int(suggested_leverage_raw)))
            else:
                suggested_leverage = 5  # Valor por defecto
            
            # Ajustar por nivel de volatilidad textual
            if volatility_level == 'extreme':
                suggested_leverage = 2
            elif volatility_level == 'high':
                suggested_leverage = min(suggested_leverage, 5)
            elif volatility_level == 'low':
                suggested_leverage = min(suggested_leverage, 8)
            
            # Stop multiplier: a mayor volatilidad, stop más amplio
            suggested_stop_multiplier = 1.5 + (atr_pct / 5)  # Entre 1.5 y 2.5
            suggested_stop_multiplier = min(3.0, max(1.2, suggested_stop_multiplier))
            
            return {
                'atr': float(atr[-1]) if len(atr) > 0 else 0,
                'atr_pct': float(atr_pct),
                'volatility_level': volatility_level,
                'bb_width': float(bb_width),
                'bb_position': float(bb_position),
                'bb_upper': float(bb['upper'][-1]) if len(bb['upper']) > 0 else 0,
                'bb_lower': float(bb['lower'][-1]) if len(bb['lower']) > 0 else 0,
                'ftm_width': float(ftm_bb_width),
                'ftm_strength': float(ftm_strength),
                'ftm_state': ftm_state,
                'ftm_description': ftm_description,
                'ftm_color': ftm_color,
                'ftm_no_trade': ftm_no_trade,
                'contraction_count': contraction_count,
                'squeeze_on': squeeze['squeeze_on'][-1] if len(squeeze['squeeze_on']) > 0 else False,
                'squeeze_length': squeeze_length,
                'operability': operability,
                'no_trade_reason': no_trade_reason,
                'suggested_stop_multiplier': float(suggested_stop_multiplier),
                'suggested_leverage': suggested_leverage
            }
        except Exception as e:
            print(f"Error en analyze_volatility_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'atr': 0,
                'atr_pct': 0,
                'volatility_level': 'unknown',
                'bb_width': 0,
                'bb_position': 0.5,
                'bb_upper': 0,
                'bb_lower': 0,
                'ftm_width': 0,
                'ftm_strength': 0,
                'ftm_state': 'NEUTRAL',
                'ftm_description': 'Desconocido',
                'ftm_color': 'gray',
                'ftm_no_trade': False,
                'contraction_count': 0,
                'squeeze_on': False,
                'squeeze_length': 0,
                'operability': False,
                'no_trade_reason': ['error'],
                'suggested_stop_multiplier': 2.0,
                'suggested_leverage': 5
            }
    # === FIN analyze_volatility_layer ===
    
    # === FUNCIÓN COMPLETA: analyze_volume_layer ===
    # Ubicación: Reemplazar entre línea ~1220 y línea ~1250 aproximadamente
    
    def analyze_volume_layer(self, df, timeframe):
        """Capa 4: Análisis de Volumen - Participación real, ballenas y órdenes institucionales"""
        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            volume = df['volume'].values
            open_price = df['open'].values
            
            # ============ INDICADORES DE VOLUMEN ============
            obv = self.calculate_obv(close, volume)
            mfi = self.calculate_mfi(high, low, close, volume, 14)
            force_index = self.calculate_force_index(close, volume, 13)
            
            volume_sma = self.calculate_sma(volume, 20)
            volume_ratio = volume[-1] / volume_sma[-1] if volume_sma[-1] != 0 else 1
            
            obv_sma = self.calculate_sma(obv, 20)
            obv_trend = 'bullish' if obv[-1] > obv[-5] else 'bearish' if obv[-1] < obv[-5] else 'neutral'
            
            # ============ DETECTOR DE BALLENAS MEJORADO ============
            whale_data = None
            if timeframe in ['12h', '1D']:
                whale_data = self.calculate_whale_signals_improved(df)
            else:
                whale_data = {
                    'whale_pump': 0, 'whale_dump': 0,
                    'confirmed_buy': False, 'confirmed_sell': False,
                    'extended_buy': False, 'extended_sell': False,
                    'iceberg_buy': False, 'iceberg_sell': False,
                    'spoofing_buy': False, 'spoofing_sell': False,
                    'aggressive_whale': False, 'passive_whale': False,
                    'support': float(df['low'].iloc[-1]) if len(df) > 0 else 0,
                    'resistance': float(df['high'].iloc[-1]) if len(df) > 0 else 0,
                    'volume_anomaly': False
                }
            
            # ============ PUNTUACIÓN DE ACUMULACIÓN/DISTRIBUCIÓN ============
            accumulation_score = 0
            accumulation_reasons = []
            
            # OBV vs Precio
            if obv[-1] > obv_sma[-1] and close[-1] > close[-5]:
                accumulation_score += 1
                accumulation_reasons.append('obv_bullish')
            elif obv[-1] < obv_sma[-1] and close[-1] < close[-5]:
                accumulation_score -= 1
                accumulation_reasons.append('obv_bearish')
            
            # MFI
            if mfi[-1] > 60:
                accumulation_score += 1
                accumulation_reasons.append('mfi_overbought')
            elif mfi[-1] < 40:
                accumulation_score -= 1
                accumulation_reasons.append('mfi_oversold')
            
            # Force Index
            if force_index[-1] > 0:
                accumulation_score += 0.5
                accumulation_reasons.append('force_positive')
            else:
                accumulation_score -= 0.5
                accumulation_reasons.append('force_negative')
            
            # ============ SEÑALES DE BALLENAS ============
            whale_buy_confirmed = False
            whale_sell_confirmed = False
            whale_signal_strength = 0
            
            if whale_data:
                # Ballenas confirmadas
                if whale_data.get('confirmed_buy', False):
                    accumulation_score += 3
                    whale_buy_confirmed = True
                    whale_signal_strength = whale_data.get('whale_pump', 0)
                    accumulation_reasons.append('whale_confirmed_buy')
                
                if whale_data.get('confirmed_sell', False):
                    accumulation_score -= 3
                    whale_sell_confirmed = True
                    whale_signal_strength = whale_data.get('whale_dump', 0)
                    accumulation_reasons.append('whale_confirmed_sell')
                
                # Señales extendidas
                if whale_data.get('extended_buy', False):
                    accumulation_score += 2
                    accumulation_reasons.append('whale_extended_buy')
                
                if whale_data.get('extended_sell', False):
                    accumulation_score -= 2
                    accumulation_reasons.append('whale_extended_sell')
                
                # Iceberg
                if whale_data.get('iceberg_buy', False):
                    accumulation_score += 1.5
                    accumulation_reasons.append('iceberg_accumulation')
                
                if whale_data.get('iceberg_sell', False):
                    accumulation_score -= 1.5
                    accumulation_reasons.append('iceberg_distribution')
            
            # Volumen anómalo
            volume_anomaly = volume[-1] > volume_sma[-1] * 1.5
            volume_spike = volume[-1] > volume_sma[-1] * 1.8
            
            # Participación
            if volume_ratio > 1.5:
                volume_participation = 'high'
            elif volume_ratio > 0.7:
                volume_participation = 'normal'
            else:
                volume_participation = 'low'
            
            # Normalizar score
            accumulation_score = max(-10, min(10, accumulation_score))
            
            return {
                'volume_ratio': float(volume_ratio),
                'volume_participation': volume_participation,
                'volume_anomaly': volume_anomaly,
                'volume_spike': volume_spike,
                'obv_trend': obv_trend,
                'mfi': float(mfi[-1]) if len(mfi) > 0 else 50,
                'force_index': float(force_index[-1]) if len(force_index) > 0 else 0,
                'accumulation_score': float(accumulation_score),
                'accumulation_reasons': accumulation_reasons[-3:],
                
                # Ballenas - VALORES BOOLEANOS SIMPLES
                'whale_buy': whale_data.get('extended_buy', False) if whale_data else False,
                'whale_sell': whale_data.get('extended_sell', False) if whale_data else False,
                'whale_buy_confirmed': whale_buy_confirmed,
                'whale_sell_confirmed': whale_sell_confirmed,
                'whale_signal_strength': float(whale_signal_strength),
                'whale_pump': float(whale_data.get('whale_pump', 0)) if whale_data else 0,
                'whale_dump': float(whale_data.get('whale_dump', 0)) if whale_data else 0,
                'iceberg_buy': whale_data.get('iceberg_buy', False) if whale_data else False,
                'iceberg_sell': whale_data.get('iceberg_sell', False) if whale_data else False,
                'spoofing_buy': whale_data.get('spoofing_buy', False) if whale_data else False,
                'spoofing_sell': whale_data.get('spoofing_sell', False) if whale_data else False,
                'aggressive_whale': whale_data.get('aggressive_whale', False) if whale_data else False,
                'passive_whale': whale_data.get('passive_whale', False) if whale_data else False
            }
            
        except Exception as e:
            print(f"Error en analyze_volume_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'volume_ratio': 1.0,
                'volume_participation': 'normal',
                'volume_anomaly': False,
                'volume_spike': False,
                'obv_trend': 'neutral',
                'mfi': 50,
                'force_index': 0,
                'accumulation_score': 0,
                'accumulation_reasons': [],
                'whale_buy': False,
                'whale_sell': False,
                'whale_buy_confirmed': False,
                'whale_sell_confirmed': False,
                'whale_signal_strength': 0,
                'whale_pump': 0,
                'whale_dump': 0,
                'iceberg_buy': False,
                'iceberg_sell': False,
                'spoofing_buy': False,
                'spoofing_sell': False,
                'aggressive_whale': False,
                'passive_whale': False
            }
    # === FIN FUNCIÓN COMPLETA ===
    
    # === FUNCIÓN COMPLETA:  ===
    # Ubicación: Reemplazar entre línea ~1250 y línea ~1320 aproximadamente
        
    def analyze_price_structure_layer(self, df, timeframe='1D', symbol=None):  # <--- CAMBIO: Añadir parámetro timeframe con valor por defecto
        """Capa 5: Análisis de Precio y Estructura - VERSIÓN COMPLETA con FVGs y OB"""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            open_price = df['open'].values
            volume = df['volume'].values if 'volume' in df else np.zeros(len(df))
            
            n = len(close)
            current_price = close[-1] if n > 0 else 0

            # Si symbol no viene, intentar inferirlo (fallback)
            if symbol is None:
                # Intentar obtener de algún lado, o usar valor por defecto
                symbol = 'BTC-USDT'  # Valor por defecto seguro
                print(f"⚠️ symbol no proporcionado, usando {symbol}")
            
            # ============ MÉTRICAS PARA DETECCIÓN ============
            avg_volume = np.mean(volume) if len(volume) > 0 else 1
            avg_range = np.mean(high - low) if n > 0 else 1
            
            print(f"\n📊 ANALIZANDO ESTRUCTURA - {n} velas, precio actual: {current_price:.2f}")
            print(f"   Volumen promedio: {avg_volume:.0f}, Rango promedio: {avg_range:.2f}")
            
            # Canales de soporte/resistencia
            supports, resistances = self.calculate_support_resistance_channels(high, low, close)
            
            # Patrones de vela
            patterns = self.detect_candle_patterns(df)
            
            # Pivotes
            pivot_highs = []
            pivot_lows = []
            for i in range(5, len(high)-5):
                if high[i] == max(high[i-5:i+6]):
                    pivot_highs.append({'price': float(high[i]), 'index': i, 'volume': float(volume[i])})
                if low[i] == min(low[i-5:i+6]):
                    pivot_lows.append({'price': float(low[i]), 'index': i, 'volume': float(volume[i])})
            
            # Soportes y resistencias cercanos
            nearest_support = None
            nearest_resistance = None
            
            for s in supports:
                if s < current_price:
                    if nearest_support is None or s > nearest_support:
                        nearest_support = s
            
            for r in resistances:
                if r > current_price:
                    if nearest_resistance is None or r < nearest_resistance:
                        nearest_resistance = r
            
            # ============ FIBONACCI COMPLETO ============
            fib_levels = {}
            fib_extensions = {}
            psychological_levels = []
            
            if len(pivot_lows) > 0 and len(pivot_highs) > 0:
                recent_high = max([p['price'] for p in pivot_highs[-3:]]) if pivot_highs else current_price * 1.1
                recent_low = min([p['price'] for p in pivot_lows[-3:]]) if pivot_lows else current_price * 0.9
                diff = recent_high - recent_low
                
                if diff > 0:
                    fib_levels = {
                        '0.236': float(recent_high - diff * 0.236),
                        '0.382': float(recent_high - diff * 0.382),
                        '0.5': float(recent_high - diff * 0.5),
                        '0.618': float(recent_high - diff * 0.618),
                        '0.786': float(recent_high - diff * 0.786)
                    }
                    
                    fib_extensions = {
                        '1.272': float(recent_high + diff * 0.272),
                        '1.414': float(recent_high + diff * 0.414),
                        '1.618': float(recent_high + diff * 0.618),
                        '2.000': float(recent_high + diff * 1.0),
                        '2.618': float(recent_high + diff * 1.618),
                        '3.618': float(recent_high + diff * 2.618)
                    }
                    
                    for level in [1000, 2000, 5000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000, 100000]:
                        if abs(current_price - level) / current_price < 0.1:
                            psychological_levels.append(level)
            
            # ============ ORDER BLOCKS MEJORADOS ============
            order_blocks = []
            
            for i in range(5, n-3):
                try:
                    # OB Alcista: vela alcista que absorbe presión vendedora
                    if close[i] > open_price[i]:  # Vela alcista
                        rango_vela = high[i] - low[i]
                        if rango_vela > avg_range * 1.2:  # Rango mayor al promedio
                            if volume[i] > avg_volume * 1.3:  # Volumen mayor al promedio
                                # Verificar que las siguientes velas respeten
                                if i < n-2 and close[i+1] > high[i] * 0.98:
                                    strength = 'strong' if volume[i] > avg_volume * 2.0 else 'moderate'
                                    order_blocks.append({
                                        'type': 'bullish',
                                        'price_range': [float(low[i]), float(high[i])],
                                        'index': i,
                                        'strength': strength,
                                        'volume_ratio': float(volume[i] / avg_volume) if avg_volume > 0 else 1.0
                                    })
                                    print(f"   ✅ OB ALCISTA detectado en índice {i}, precio {high[i]:.2f}")
                    
                    # OB Bajista: vela bajista que absorbe presión compradora
                    if close[i] < open_price[i]:  # Vela bajista
                        rango_vela = high[i] - low[i]
                        if rango_vela > avg_range * 1.2:
                            if volume[i] > avg_volume * 1.3:
                                if i < n-2 and close[i+1] < low[i] * 1.02:
                                    strength = 'strong' if volume[i] > avg_volume * 2.0 else 'moderate'
                                    order_blocks.append({
                                        'type': 'bearish',
                                        'price_range': [float(low[i]), float(high[i])],
                                        'index': i,
                                        'strength': strength,
                                        'volume_ratio': float(volume[i] / avg_volume) if avg_volume > 0 else 1.0
                                    })
                                    print(f"   ✅ OB BAJISTA detectado en índice {i}, precio {low[i]:.2f}")
                except:
                    continue
            

            # ============ IMBALANCE DETECTION (FAIR VALUE GAPS PARA CRIPTO 24/7) - VERSIÓN MÁS SENSIBLE ============
            # ============ IMBALANCE DETECTION (FAIR VALUE GAPS) - VERSIÓN CORREGIDA ============
            fair_value_gaps = []
            
            # Lookback dinámico según temporalidad y símbolo
            if symbol == 'BTC-USDT':
                if timeframe == '1W':
                    max_lookback = 200
                elif timeframe == '1D':
                    max_lookback = 400
                elif timeframe == '12h':
                    max_lookback = 400
                else:  # 4h
                    max_lookback = 500
            else:
                if timeframe == '1W':
                    max_lookback = 100
                elif timeframe == '1D':
                    max_lookback = 200
                elif timeframe == '12h':
                    max_lookback = 200
                else:  # 4h
                    max_lookback = 300
            
            start_idx = max(2, max(0, n - max_lookback))
            
            for i in range(start_idx, n-2):
                try:
                    # ============ TEORÍA CORRECTA DE IMBALANCE (3 VELAS) ============
                    # Vela1: i-2, Vela2: i-1, Vela3: i
                    # El imbalance existe si el rango de la vela2 NO está completamente cubierto
                    # por el rango combinado de vela1 y vela3
                    
                    rango_vela2 = high[i-1] - low[i-1]
                    if rango_vela2 <= 0:
                        continue
                        
                    # Rango cubierto por vela1 y vela3
                    cobertura_superior = max(high[i-2], high[i])
                    cobertura_inferior = min(low[i-2], low[i])
                    
                    # Solapamiento entre el rango de vela2 y la cobertura
                    overlap = max(0, min(high[i-1], cobertura_superior) - max(low[i-1], cobertura_inferior))
                    overlap_ratio = overlap / rango_vela2 if rango_vela2 > 0 else 1.0
                    
                    # Si el solapamiento es MENOR al 70%, hay imbalance (30% o más sin cubrir)
                    if overlap_ratio < 0.7:
                        # Determinar la zona del imbalance
                        gap_bottom = max(low[i-1], cobertura_inferior)
                        gap_top = min(high[i-1], cobertura_superior)
                        
                        # Asegurar que el gap tenga dirección
                        if gap_top > gap_bottom:
                            gap_size = (gap_top - gap_bottom) / close[i-1] * 100
                            
                            # Determinar dirección del imbalance
                            if close[i-1] > open_price[i-1]:  # Vela2 alcista
                                # Para vela alcista, el imbalance está en la parte superior
                                gap_bottom = max(high[i-2], high[i])  # CORREGIDO
                                gap_top = high[i-1]
                                direccion = 'bullish'
                            else:  # Vela2 bajista
                                # Para vela bajista, el imbalance está en la parte inferior
                                gap_bottom = low[i-1]
                                gap_top = min(low[i-2], low[i])  # CORREGIDO
                                direccion = 'bearish'
                            
                            if gap_top > gap_bottom:
                                gap_size = (gap_top - gap_bottom) / close[i-1] * 100
                                
                                # Umbrales dinámicos por símbolo
                                if symbol == 'BTC-USDT':
                                    min_gap_size = 0.02  # 0.02% para BTC
                                elif symbol == 'PAXG-USDT':
                                    min_gap_size = 0.03
                                else:
                                    min_gap_size = 0.04
                                
                                if gap_size > min_gap_size:
                                    filled = (current_price <= gap_top and current_price >= gap_bottom)
                                    
                                    # Determinar fuerza
                                    if gap_size > 0.5:
                                        strength = 'strong'
                                    elif gap_size > 0.2:
                                        strength = 'moderate'
                                    else:
                                        strength = 'weak'
                                    
                                    fair_value_gaps.append({
                                        'type': direccion,
                                        'gap_bottom': float(gap_bottom),
                                        'gap_top': float(gap_top),
                                        'gap_size': float(gap_size),
                                        'index': i-1,
                                        'filled': filled,
                                        'reaccion': False,  # Se calculará después
                                        'antiguedad': n - 1 - (i-1),
                                        'strength': strength,
                                        'volume_ratio': float(volume[i-1] / avg_volume) if avg_volume > 0 else 1.0
                                    })
                                    print(f"   ✅ IMBALANCE {direccion.upper()} en índice {i-1}: {gap_bottom:.2f}-{gap_top:.2f} (gap {gap_size:.2f}%)")
                    
                    # ============ IMBALANCE DE 2 VELAS (CASOS ESPECIALES) ============
                    # Para movimientos muy fuertes donde la vela2 cubre casi toda la vela1
                    if i > 1:
                        rango_vela1 = high[i-2] - low[i-2]
                        if rango_vela1 > 0:
                            overlap_2v = max(0, min(high[i-1], high[i-2]) - max(low[i-1], low[i-2]))
                            overlap_ratio_2v = overlap_2v / rango_vela1
                            
                            # Si el solapamiento es muy bajo (<30%) y la vela2 es grande
                            if overlap_ratio_2v < 0.3 and rango_vela1 > avg_range * 1.5:
                                if close[i-1] > open_price[i-1]:  # Vela2 alcista
                                    gap_bottom = high[i-2]
                                    gap_top = high[i-1]
                                    direccion = 'bullish'
                                else:  # Vela2 bajista
                                    gap_bottom = low[i-1]
                                    gap_top = low[i-2]
                                    direccion = 'bearish'
                                
                                if gap_top > gap_bottom:
                                    gap_size = (gap_top - gap_bottom) / close[i-2] * 100
                                    if gap_size > 0.1:  # Umbral más alto para 2 velas
                                        fair_value_gaps.append({
                                            'type': direccion,
                                            'gap_bottom': float(gap_bottom),
                                            'gap_top': float(gap_top),
                                            'gap_size': float(gap_size),
                                            'index': i-1,
                                            'filled': current_price <= gap_top and current_price >= gap_bottom,
                                            'reaccion': False,
                                            'antiguedad': n - 1 - (i-1),
                                            'strength': 'moderate' if gap_size > 0.3 else 'weak',
                                            'volume_ratio': float(volume[i-1] / avg_volume) if avg_volume > 0 else 1.0
                                        })
                    
                    # ============ ACTUALIZAR REACCIÓN PARA FVGs EXISTENTES ============
                    # Verificar si el precio actual reaccionó en algún FVG
                    for fvg in fair_value_gaps:
                        if not fvg['filled']:
                            if current_price <= fvg['gap_top'] and current_price >= fvg['gap_bottom']:
                                # El precio está dentro del gap
                                if abs(current_price - fvg['gap_bottom']) / current_price < 0.005:
                                    fvg['reaccion'] = True  # Rebote en soporte
                                elif abs(fvg['gap_top'] - current_price) / current_price < 0.005:
                                    fvg['reaccion'] = True  # Rechazo en resistencia
                                    
                except Exception as e:
                    continue
            
            # Eliminar duplicados (mismo índice y tipo)
            fvgs_unicos = {}
            for fvg in fair_value_gaps:
                key = f"{fvg['index']}_{fvg['type']}"
                if key not in fvgs_unicos or fvg['gap_size'] > fvgs_unicos[key]['gap_size']:
                    fvgs_unicos[key] = fvg
            
            fair_value_gaps = list(fvgs_unicos.values())
            
            # Ordenar por antigüedad (más recientes primero)
            fair_value_gaps.sort(key=lambda x: x['antiguedad'])
            
            # Limitar a los 40 más relevantes
            fair_value_gaps = fair_value_gaps[:40]
            
            print(f"   Fair Value Gaps detectados: {len(fair_value_gaps)}")
            
            # ============ LIQUIDITY SWEEPS ============
            liquidity_sweeps = []
            
            for i in range(20, n):
                try:
                    # Barrido de liquidez en máximos (rechazo)
                    if high[i] > max(high[i-20:i-5]) * 1.01:
                        if close[i] < open_price[i] and close[i] < (high[i] + low[i]) / 2:
                            strength = 'strong' if volume[i] > avg_volume * 1.5 else 'moderate'
                            liquidity_sweeps.append({
                                'type': 'bearish',
                                'sweep_level': float(high[i]),
                                'index': i,
                                'strength': strength
                            })
                    
                    # Barrido de liquidez en mínimos (rebote)
                    if low[i] < min(low[i-20:i-5]) * 0.99:
                        if close[i] > open_price[i] and close[i] > (high[i] + low[i]) / 2:
                            strength = 'strong' if volume[i] > avg_volume * 1.5 else 'moderate'
                            liquidity_sweeps.append({
                                'type': 'bullish',
                                'sweep_level': float(low[i]),
                                'index': i,
                                'strength': strength
                            })
                except:
                    continue
            
            # ============ STOP HUNTS ============
            stop_hunts = []
            
            for i in range(10, n):
                try:
                    # Caza de stops por encima de resistencia
                    if high[i] > max(high[i-10:i]) * 1.005 and close[i] < (high[i] + low[i]) / 2:
                        stop_hunts.append({
                            'type': 'bearish',
                            'level': float(high[i]),
                            'index': i
                        })
                    
                    # Caza de stops por debajo de soporte
                    if low[i] < min(low[i-10:i]) * 0.995 and close[i] > (high[i] + low[i]) / 2:
                        stop_hunts.append({
                            'type': 'bullish',
                            'level': float(low[i]),
                            'index': i
                        })
                except:
                    continue
            
            # ============ PERFIL DE VOLUMEN ============
            volume_profile = self.analyze_volume_profile(df)
            
            # Extraer HVN y LVN para uso en estrategias
            hvn_nodes = volume_profile.get('hvn_nodes', [])
            lvn_nodes = volume_profile.get('lvn_nodes', [])
            closest_hvn = volume_profile.get('closest_hvn')
            closest_lvn = volume_profile.get('closest_lvn')
            
            if closest_hvn:
                print(f"   📍 HVN más cercano: ${closest_hvn['price']:.2f} (ratio: {closest_hvn['volume_ratio']:.1f}x)")
            if closest_lvn:
                print(f"   📍 LVN más cercano: ${closest_lvn['price']:.2f}")
            
            # Añadir POC como nivel de soporte/resistencia si es significativo
            if volume_profile and volume_profile.get('poc'):
                poc_price = volume_profile['poc']
                if poc_price < current_price:
                    if nearest_support is None or poc_price > nearest_support:
                        nearest_support = poc_price
                        if poc_price not in supports:
                            supports.append(poc_price)
                else:
                    if nearest_resistance is None or poc_price < nearest_resistance:
                        nearest_resistance = poc_price
                        if poc_price not in resistances:
                            resistances.append(poc_price)
            
            # Añadir HVN más cercano como nivel si está cerca
            if closest_hvn:
                hvn_price = closest_hvn['price']
                if abs(hvn_price - current_price) / current_price < 0.02:
                    if hvn_price < current_price:
                        if nearest_support is None or hvn_price > nearest_support:
                            nearest_support = hvn_price
                            if hvn_price not in supports:
                                supports.append(hvn_price)
                    else:
                        if nearest_resistance is None or hvn_price < nearest_resistance:
                            nearest_resistance = hvn_price
                            if hvn_price not in resistances:
                                resistances.append(hvn_price)
            
            print(f"\n📊 RESUMEN ESTRUCTURA:")
            print(f"   Order Blocks detectados: {len(order_blocks)}")
            print(f"   Fair Value Gaps detectados: {len(fair_value_gaps)}")
            print(f"   Liquidity Sweeps detectados: {len(liquidity_sweeps)}")
            print(f"   HVN detectados: {len(hvn_nodes)}")
            print(f"   LVN detectados: {len(lvn_nodes)}")
            
            return {
                'supports': [float(s) for s in supports[:5]],
                'resistances': [float(r) for r in resistances[:5]],
                'nearest_support': float(nearest_support) if nearest_support else None,
                'nearest_resistance': float(nearest_resistance) if nearest_resistance else None,
                'patterns': patterns,
                'bullish_patterns_count': int(patterns.get('bullish_count', 0)),
                'bearish_patterns_count': int(patterns.get('bearish_count', 0)),
                'pivot_highs': pivot_highs[-3:] if pivot_highs else [],
                'pivot_lows': pivot_lows[-3:] if pivot_lows else [],
                'fib_levels': {str(k): float(v) for k, v in fib_levels.items()},
                'fib_extensions': {str(k): float(v) for k, v in fib_extensions.items()},
                'psychological_levels': [float(l) for l in psychological_levels],
                'order_blocks': order_blocks[-10:] if order_blocks else [],
                'fair_value_gaps': fair_value_gaps[-10:] if fair_value_gaps else [],
                'liquidity_sweeps': liquidity_sweeps[-5:] if liquidity_sweeps else [],
                'stop_hunts': stop_hunts[-5:] if stop_hunts else [],
                'volume_profile': volume_profile,
                'hvn_nodes': hvn_nodes[:5],
                'lvn_nodes': lvn_nodes[:5],
                'closest_hvn': closest_hvn,
                'closest_lvn': closest_lvn,
                'current_price': float(current_price),
                # ============ LÍNEA CRÍTICA QUE FALTA ============
                'df': {
                    'time': [str(t) for t in df['time'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()],
                    'open': [float(x) for x in df['open'].tolist()],
                    'high': [float(x) for x in df['high'].tolist()],
                    'low': [float(x) for x in df['low'].tolist()],
                    'close': [float(x) for x in df['close'].tolist()],
                    'volume': [float(x) for x in df['volume'].tolist()]
                }
                # =================================================
            }
            
        except Exception as e:
            print(f"❌ Error en analyze_price_structure_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': True,
                'symbol': symbol,
                'timeframe': timeframe,
                'decision': {
                    'action': accion_consenso,
                    'confidence': float(confianza_consenso),
                    'estrategias': [str(e) for e in estrategias_consenso],
                    'razones': [str(r) for r in razones_consenso],
                    'registro_votacion': registro_serializable,
                    'conviction': conviction
                },
                'levels': {k: float(v) if isinstance(v, (int, float)) else v for k, v in levels.items()},
                'message': str(message),
                'trend': self._make_serializable(trend),
                'momentum': self._make_serializable(momentum),
                'volatility': self._make_serializable(volatility),
                'volume': self._make_serializable(volume),
                'structure': self._make_serializable(structure),
                'correlation': self._make_serializable(correlation),
                'market_hours': self._make_serializable(market_hours),
                'confirmation': self._make_serializable(confirmation),
                'time_factor': self._make_serializable(time_factor),
                'sentiment': self._make_serializable(sentiment),
                'liquidation': self._make_serializable(liquidation_data),  # <--- AÑADIR ESTA LÍNEA
                'current_price': float(structure.get('current_price', 0)),
                'df': df_dict,
                'timestamp': datetime.now(self.bolivia_tz).isoformat()
            }
            
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ ERROR CRÍTICO en analyze_full_market: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol,
                'timeframe': timeframe
            }
            
        # === FIN analyze_price_structure_layer ===

    # ========================================================================
    # ANÁLISIS DE PERFIL DE VOLUMEN (MEJORADO CON HVN/LVN)
    # ========================================================================
    
    def analyze_volume_profile(self, df):
        """Analizar perfil de volumen de las últimas 50 velas para encontrar POC, VAH, VAL, HVN y LVN"""
        try:
            if df is None or len(df) < 30:
                return {
                    'poc': None,
                    'vah': None,
                    'val': None,
                    'value_area_width': 0,
                    'poc_volume': 0,
                    'total_volume': 0,
                    'poc_volume_pct': 0,
                    'price_position': 'unknown',
                    'distance_to_poc': 999,
                    'hvn_nodes': [],
                    'lvn_nodes': [],
                    'closest_hvn': None,
                    'closest_lvn': None
                }
            
            # Tomar últimas 50 velas
            df_profile = df.tail(50).copy()
            
            high = df_profile['high'].values
            low = df_profile['low'].values
            volume = df_profile['volume'].values
            close = df_profile['close'].values
            
            min_price = np.min(low)
            max_price = np.max(high)
            price_range = max_price - min_price
            
            # Crear 30 buckets de precio
            num_buckets = 30
            bucket_size = price_range / num_buckets
            buckets = np.zeros(num_buckets)
            bucket_centers = []
            
            for i in range(num_buckets):
                bucket_centers.append(min_price + (i + 0.5) * bucket_size)
            
            # Llenar buckets con volumen
            for i in range(len(df_profile)):
                candle_high = high[i]
                candle_low = low[i]
                candle_volume = volume[i]
                candle_range = candle_high - candle_low
                
                if candle_range <= 0:
                    continue
                
                for b in range(num_buckets):
                    bucket_low = min_price + b * bucket_size
                    bucket_high = bucket_low + bucket_size
                    
                    if candle_high > bucket_low and candle_low < bucket_high:
                        overlap = min(candle_high, bucket_high) - max(candle_low, bucket_low)
                        if overlap > 0:
                            buckets[b] += candle_volume * (overlap / candle_range)
            
            # Encontrar POC (Point of Control)
            poc_index = np.argmax(buckets)
            poc_price = min_price + (poc_index + 0.5) * bucket_size
            poc_volume = buckets[poc_index]
            total_volume = np.sum(buckets)
            
            # Calcular Value Area (70% del volumen)
            target_volume = total_volume * 0.7
            accumulated = buckets[poc_index]
            val_index = poc_index
            vah_index = poc_index
            
            # Expandir hacia abajo y arriba
            expand_down = True
            expand_up = True
            
            while accumulated < target_volume and (expand_down or expand_up):
                if expand_down and val_index > 0:
                    val_index -= 1
                    accumulated += buckets[val_index]
                else:
                    expand_down = False
                
                if accumulated >= target_volume:
                    break
                
                if expand_up and vah_index < num_buckets - 1:
                    vah_index += 1
                    accumulated += buckets[vah_index]
                else:
                    expand_up = False
            
            val_price = min_price + (val_index + 0.5) * bucket_size
            vah_price = min_price + (vah_index + 0.5) * bucket_size
            
            # Determinar posición del precio actual respecto al POC
            current_price = close[-1]
            if current_price > vah_price:
                price_position = 'above_value_area'
            elif current_price < val_price:
                price_position = 'below_value_area'
            else:
                price_position = 'inside_value_area'
            
            # Calcular distancia al POC
            distance_to_poc = abs(current_price - poc_price) / current_price * 100
            
            # ============ IDENTIFICAR HVN (High Volume Nodes) y LVN (Low Volume Nodes) ============
            avg_bucket_volume = np.mean(buckets) if len(buckets) > 0 else 0
            std_bucket_volume = np.std(buckets) if len(buckets) > 1 else 0
            
            hvn_nodes = []
            lvn_nodes = []
            
            for i, vol in enumerate(buckets):
                if vol > avg_bucket_volume * 1.5:  # HVN: volumen > 150% del promedio
                    hvn_nodes.append({
                        'price': float(bucket_centers[i]),
                        'volume': float(vol),
                        'volume_ratio': float(vol / avg_bucket_volume) if avg_bucket_volume > 0 else 1.0,
                        'index': i,
                        'type': 'HVN'
                    })
                elif vol < avg_bucket_volume * 0.5:  # LVN: volumen < 50% del promedio
                    lvn_nodes.append({
                        'price': float(bucket_centers[i]),
                        'volume': float(vol),
                        'volume_ratio': float(vol / avg_bucket_volume) if avg_bucket_volume > 0 else 0.5,
                        'index': i,
                        'type': 'LVN'
                    })
            
            # Ordenar HVN y LVN por cercanía al precio actual
            hvn_nodes_sorted = sorted(hvn_nodes, key=lambda x: abs(x['price'] - current_price))
            lvn_nodes_sorted = sorted(lvn_nodes, key=lambda x: abs(x['price'] - current_price))
            
            # Encontrar el HVN y LVN más cercanos
            closest_hvn = hvn_nodes_sorted[0] if hvn_nodes_sorted else None
            closest_lvn = lvn_nodes_sorted[0] if lvn_nodes_sorted else None
            
            # Identificar zonas de confluencia (múltiples HVN cercanos)
            hvn_clusters = []
            if len(hvn_nodes) >= 2:
                # Agrupar HVN que están cerca entre sí
                hvn_nodes_sorted_by_price = sorted(hvn_nodes, key=lambda x: x['price'])
                current_cluster = [hvn_nodes_sorted_by_price[0]]
                
                for i in range(1, len(hvn_nodes_sorted_by_price)):
                    if hvn_nodes_sorted_by_price[i]['price'] - current_cluster[-1]['price'] < bucket_size * 2:
                        current_cluster.append(hvn_nodes_sorted_by_price[i])
                    else:
                        if len(current_cluster) >= 2:
                            cluster_price = sum(n['price'] for n in current_cluster) / len(current_cluster)
                            cluster_volume = sum(n['volume'] for n in current_cluster)
                            hvn_clusters.append({
                                'price': float(cluster_price),
                                'volume': float(cluster_volume),
                                'nodes': len(current_cluster),
                                'price_min': min(n['price'] for n in current_cluster),
                                'price_max': max(n['price'] for n in current_cluster)
                            })
                        current_cluster = [hvn_nodes_sorted_by_price[i]]
                
                # Último cluster
                if len(current_cluster) >= 2:
                    cluster_price = sum(n['price'] for n in current_cluster) / len(current_cluster)
                    cluster_volume = sum(n['volume'] for n in current_cluster)
                    hvn_clusters.append({
                        'price': float(cluster_price),
                        'volume': float(cluster_volume),
                        'nodes': len(current_cluster),
                        'price_min': min(n['price'] for n in current_cluster),
                        'price_max': max(n['price'] for n in current_cluster)
                    })
            
            print(f"\n📊 PERFIL DE VOLUMEN:")
            print(f"   POC: ${poc_price:.2f} (volumen: {poc_volume:.0f}, {poc_volume/total_volume*100:.1f}%)")
            print(f"   Value Area: ${val_price:.2f} - ${vah_price:.2f}")
            print(f"   HVN detectados: {len(hvn_nodes)}")
            print(f"   LVN detectados: {len(lvn_nodes)}")
            if closest_hvn:
                print(f"   HVN más cercano: ${closest_hvn['price']:.2f} (ratio: {closest_hvn['volume_ratio']:.1f}x)")
            if closest_lvn:
                print(f"   LVN más cercano: ${closest_lvn['price']:.2f}")
            
            return {
                'poc': float(poc_price),
                'vah': float(vah_price),
                'val': float(val_price),
                'value_area_width': float((vah_price - val_price) / poc_price * 100),
                'poc_volume': float(poc_volume),
                'total_volume': float(total_volume),
                'poc_volume_pct': float(poc_volume / total_volume * 100),
                'price_position': price_position,
                'distance_to_poc': float(distance_to_poc),
                'hvn_nodes': hvn_nodes[:10],  # Limitar a 10 para no saturar
                'lvn_nodes': lvn_nodes[:10],
                'closest_hvn': closest_hvn,
                'closest_lvn': closest_lvn,
                'hvn_clusters': hvn_clusters,
                'bucket_size': float(bucket_size),
                'num_buckets': num_buckets,
                'min_price': float(min_price),
                'max_price': float(max_price)
            }
            
        except Exception as e:
            print(f"❌ Error en analyze_volume_profile: {e}")
            import traceback
            traceback.print_exc()
            return {
                'poc': None,
                'vah': None,
                'val': None,
                'value_area_width': 0,
                'poc_volume': 0,
                'total_volume': 0,
                'poc_volume_pct': 0,
                'price_position': 'unknown',
                'distance_to_poc': 999,
                'hvn_nodes': [],
                'lvn_nodes': [],
                'closest_hvn': None,
                'closest_lvn': None,
                'hvn_clusters': []
            }


    
    # ========================================================================
    # ANALISIS DE CORRELACION
    # ========================================================================

    def analyze_correlation_layer(self, btc_analysis, paxg_analysis, paxg_btc_analysis, current_symbol):
        """Capa 6: Análisis de Correlación y Rotación entre pares - VERSIÓN FORZADA"""
        try:
            correlation_score = 0
            rotation_signal = 'NEUTRAL'
            weight_modifier = 1.0
            
            print(f"\n{'='*60}")
            print(f"📊 [CORRELACIÓN] Procesando para {current_symbol}")
            print(f"{'='*60}")
            
            # ============ VALORES POR DEFECTO ============
            btc_action = 'NO_OPERAR'
            btc_confidence = 0
            btc_trend = 'neutral'
            btc_trend_confidence = 0
            btc_adx = 0
            btc_plus_di = 0
            btc_minus_di = 0
            
            ratio_action = 'NO_OPERAR'
            ratio_confidence = 0
            ratio_trend = 'neutral'
            ratio_trend_confidence = 0
            ratio_adx = 0
            
            paxg_trend = 'neutral'
            paxg_adx = 0
            
            # ============ EXTRAER DATOS DE BTC CON DEBUG ============
            print(f"\n🔍 DEBUG - btc_analysis recibido:")
            if btc_analysis and isinstance(btc_analysis, dict):
                print(f"   btc_analysis keys: {list(btc_analysis.keys())}")
                print(f"   btc_analysis success: {btc_analysis.get('success', False)}")
                
                if 'decision' in btc_analysis:
                    print(f"   decision keys: {list(btc_analysis['decision'].keys()) if isinstance(btc_analysis['decision'], dict) else 'no es dict'}")
                    btc_action = btc_analysis['decision'].get('action', 'NO_OPERAR')
                    btc_confidence = float(btc_analysis['decision'].get('confidence', 0))
                
                if 'trend' in btc_analysis:
                    print(f"   trend keys: {list(btc_analysis['trend'].keys()) if isinstance(btc_analysis['trend'], dict) else 'no es dict'}")
                    btc_trend = btc_analysis['trend'].get('direction', 'neutral')
                    btc_trend_confidence = float(btc_analysis['trend'].get('confidence', 50))
                    
                    # EXTRACCIÓN FORZADA DE ADX
                    if 'adx' in btc_analysis['trend']:
                        btc_adx = float(btc_analysis['trend']['adx'])
                        print(f"   → ADX encontrado en trend['adx']: {btc_adx}")
                    else:
                        print(f"   ⚠️ No hay campo 'adx' en trend")
                    
                    btc_plus_di = float(btc_analysis['trend'].get('plus_di', 0))
                    btc_minus_di = float(btc_analysis['trend'].get('minus_di', 0))
                else:
                    print(f"   ⚠️ No hay 'trend' en btc_analysis")
            else:
                print(f"   ⚠️ btc_analysis es None o no es dict")
            
            # ============ EXTRAER DATOS DEL RATIO CON DEBUG ============
            print(f"\n🔍 DEBUG - paxg_btc_analysis recibido:")
            if paxg_btc_analysis and isinstance(paxg_btc_analysis, dict):
                print(f"   paxg_btc_analysis keys: {list(paxg_btc_analysis.keys())}")
                print(f"   paxg_btc_analysis success: {paxg_btc_analysis.get('success', False)}")
                
                if 'decision' in paxg_btc_analysis:
                    print(f"   decision keys: {list(paxg_btc_analysis['decision'].keys()) if isinstance(paxg_btc_analysis['decision'], dict) else 'no es dict'}")
                    ratio_action = paxg_btc_analysis['decision'].get('action', 'NO_OPERAR')
                    ratio_confidence = float(paxg_btc_analysis['decision'].get('confidence', 0))
                
                if 'trend' in paxg_btc_analysis:
                    print(f"   trend keys: {list(paxg_btc_analysis['trend'].keys()) if isinstance(paxg_btc_analysis['trend'], dict) else 'no es dict'}")
                    ratio_trend = paxg_btc_analysis['trend'].get('direction', 'neutral')
                    ratio_trend_confidence = float(paxg_btc_analysis['trend'].get('confidence', 50))
                    
                    # EXTRACCIÓN FORZADA DE ADX
                    if 'adx' in paxg_btc_analysis['trend']:
                        ratio_adx = float(paxg_btc_analysis['trend']['adx'])
                        print(f"   → ADX encontrado en trend['adx']: {ratio_adx}")
                    else:
                        print(f"   ⚠️ No hay campo 'adx' en trend")
                else:
                    print(f"   ⚠️ No hay 'trend' en paxg_btc_analysis")
            else:
                print(f"   ⚠️ paxg_btc_analysis es None o no es dict")
            
            # ============ EXTRAER DATOS DE PAXG CON DEBUG ============
            print(f"\n🔍 DEBUG - paxg_analysis recibido:")
            if paxg_analysis and isinstance(paxg_analysis, dict):
                print(f"   paxg_analysis keys: {list(paxg_analysis.keys())}")
                print(f"   paxg_analysis success: {paxg_analysis.get('success', False)}")
                
                if 'trend' in paxg_analysis:
                    print(f"   trend keys: {list(paxg_analysis['trend'].keys()) if isinstance(paxg_analysis['trend'], dict) else 'no es dict'}")
                    paxg_trend = paxg_analysis['trend'].get('direction', 'neutral')
                    
                    # EXTRACCIÓN FORZADA DE ADX
                    if 'adx' in paxg_analysis['trend']:
                        paxg_adx = float(paxg_analysis['trend']['adx'])
                        print(f"   → ADX encontrado en trend['adx']: {paxg_adx}")
                    else:
                        print(f"   ⚠️ No hay campo 'adx' en trend")
                else:
                    print(f"   ⚠️ No hay 'trend' en paxg_analysis")
            else:
                print(f"   ⚠️ paxg_analysis es None o no es dict")
            
            print(f"\n📊 Datos extraídos finales:")
            print(f"   BTC: acción={btc_action} (conf {btc_confidence:.0f}%), tendencia={btc_trend}, ADX={btc_adx:.1f}")
            print(f"   RATIO: acción={ratio_action} (conf {ratio_confidence:.0f}%), tendencia={ratio_trend}, ADX={ratio_adx:.1f}")
            print(f"   PAXG: tendencia={paxg_trend}, ADX={paxg_adx:.1f}")
            
            # ============ CONDICIÓN 1: ROTACIÓN POR DECISIONES ============
            if btc_confidence >= 60 and ratio_confidence >= 55:
                if btc_action in ['COMPRA_SPOT', 'LONG'] and ratio_action in ['VENTA_SPOT', 'SHORT']:
                    rotation_signal = 'RISK_ON'
                    correlation_score = 50
                    weight_modifier = 1.3 if current_symbol == 'BTC-USDT' else 1.2
                    print(f"   ✅ ROTACIÓN POR DECISIONES: RISK_ON")
                
                elif btc_action in ['VENTA_SPOT', 'SHORT'] and ratio_action in ['COMPRA_SPOT', 'LONG']:
                    rotation_signal = 'RISK_OFF'
                    correlation_score = 50
                    weight_modifier = 1.3 if current_symbol == 'PAXG-USDT' else 1.2
                    print(f"   ✅ ROTACIÓN POR DECISIONES: RISK_OFF")
            
            # ============ CONDICIÓN 2: ROTACIÓN POR TENDENCIAS ============
            if rotation_signal == 'NEUTRAL' and btc_trend_confidence >= 50 and ratio_trend_confidence >= 50:
                if btc_trend == 'bullish' and ratio_trend == 'bearish':
                    rotation_signal = 'RISK_ON'
                    correlation_score = 40
                    weight_modifier = 1.2 if current_symbol == 'BTC-USDT' else 1.1
                    print(f"   ✅ ROTACIÓN POR TENDENCIAS: RISK_ON")
                
                elif btc_trend == 'bearish' and ratio_trend == 'bullish':
                    rotation_signal = 'RISK_OFF'
                    correlation_score = 40
                    weight_modifier = 1.2 if current_symbol == 'PAXG-USDT' else 1.1
                    print(f"   ✅ ROTACIÓN POR TENDENCIAS: RISK_OFF")
            
            # ============ CONDICIÓN 3: CORRELACIÓN ============
            if rotation_signal == 'NEUTRAL' and btc_trend_confidence >= 40 and ratio_trend_confidence >= 40:
                if btc_trend == 'bullish' and ratio_trend == 'bullish':
                    rotation_signal = 'POSITIVE_CORRELATION'
                    correlation_score = 30
                    weight_modifier = 1.1
                    print(f"   ✅ CORRELACIÓN POSITIVA")
                
                elif btc_trend == 'bearish' and ratio_trend == 'bearish':
                    rotation_signal = 'NEGATIVE_CORRELATION'
                    correlation_score = 30
                    weight_modifier = 0.9
                    print(f"   ✅ CORRELACIÓN NEGATIVA")
            
            # ============ CONDICIÓN 4: FORTALEZA RELATIVA ============
            if rotation_signal == 'NEUTRAL':
                if paxg_trend == 'bullish' and btc_trend == 'bearish':
                    rotation_signal = 'PAXG_STRONGER'
                    correlation_score = 25
                    if current_symbol == 'PAXG-USDT':
                        weight_modifier = 1.15
                    print(f"   ✅ PAXG MÁS FUERTE")
                
                elif btc_trend == 'bullish' and paxg_trend == 'bearish':
                    rotation_signal = 'BTC_STRONGER'
                    correlation_score = 25
                    if current_symbol == 'BTC-USDT':
                        weight_modifier = 1.15
                    print(f"   ✅ BTC MÁS FUERTE")
            
            # ============ CONDICIÓN 5: DECISIONES UNILATERALES ============
            if rotation_signal == 'NEUTRAL':
                if btc_action in ['COMPRA_SPOT', 'LONG'] and btc_confidence >= 70:
                    rotation_signal = 'BTC_BULLISH'
                    correlation_score = 20
                    weight_modifier = 1.1 if current_symbol == 'BTC-USDT' else 1.0
                    print(f"   ✅ BTC ALCISTA UNILATERAL")
                
                elif btc_action in ['VENTA_SPOT', 'SHORT'] and btc_confidence >= 70:
                    rotation_signal = 'BTC_BEARISH'
                    correlation_score = 20
                    weight_modifier = 0.9 if current_symbol == 'BTC-USDT' else 1.0
                    print(f"   ✅ BTC BAJISTA UNILATERAL")
                
                elif ratio_action in ['COMPRA_SPOT', 'LONG'] and ratio_confidence >= 70:
                    rotation_signal = 'RATIO_BULLISH'
                    correlation_score = 20
                    weight_modifier = 1.1 if current_symbol == 'PAXG-BTC' else 1.0
                    print(f"   ✅ RATIO ALCISTA UNILATERAL")
                
                elif ratio_action in ['VENTA_SPOT', 'SHORT'] and ratio_confidence >= 70:
                    rotation_signal = 'RATIO_BEARISH'
                    correlation_score = 20
                    weight_modifier = 0.9 if current_symbol == 'PAXG-BTC' else 1.0
                    print(f"   ✅ RATIO BAJISTA UNILATERAL")
            
            # ============ DECISIÓN POR SÍMBOLO ============
            symbol_recommendation = {'action': 'NEUTRAL', 'reason': 'sin rotación clara', 'weight': 1.0}
            symbol_score = 0
            
            signal_to_btc = {
                'RISK_ON': ('PREFER', 50),
                'BTC_STRONGER': ('PREFER', 40),
                'BTC_BULLISH': ('PREFER', 30),
                'RISK_OFF': ('CAUTION', -40),
                'PAXG_STRONGER': ('CAUTION', -30),
                'BTC_BEARISH': ('CAUTION', -30),
                'POSITIVE_CORRELATION': ('NEUTRAL_POSITIVE', 20),
                'NEGATIVE_CORRELATION': ('CAUTION', -20)
            }
            
            signal_to_paxg = {
                'RISK_OFF': ('PREFER', 50),
                'PAXG_STRONGER': ('PREFER', 40),
                'RATIO_BULLISH': ('PREFER', 30),
                'RISK_ON': ('CAUTION', -40),
                'BTC_STRONGER': ('CAUTION', -30),
                'BTC_BULLISH': ('CAUTION', -20),
                'POSITIVE_CORRELATION': ('NEUTRAL_POSITIVE', 20),
                'NEGATIVE_CORRELATION': ('CAUTION', -20)
            }
            
            signal_to_ratio = {
                'RISK_OFF': ('BULLISH', 60),
                'PAXG_STRONGER': ('BULLISH', 50),
                'RATIO_BULLISH': ('BULLISH', 40),
                'RISK_ON': ('BEARISH', -60),
                'BTC_STRONGER': ('BEARISH', -50),
                'RATIO_BEARISH': ('BEARISH', -40)
            }
            
            if current_symbol == 'BTC-USDT' and rotation_signal in signal_to_btc:
                action, score = signal_to_btc[rotation_signal]
                symbol_recommendation = {
                    'action': action,
                    'reason': rotation_signal.lower().replace('_', ' '),
                    'weight': 1.0 + (score / 100)
                }
                symbol_score = score
            
            elif current_symbol == 'PAXG-USDT' and rotation_signal in signal_to_paxg:
                action, score = signal_to_paxg[rotation_signal]
                symbol_recommendation = {
                    'action': action,
                    'reason': rotation_signal.lower().replace('_', ' '),
                    'weight': 1.0 + (score / 100)
                }
                symbol_score = score
            
            elif current_symbol == 'PAXG-BTC' and rotation_signal in signal_to_ratio:
                action, score = signal_to_ratio[rotation_signal]
                symbol_recommendation = {
                    'action': action,
                    'reason': rotation_signal.lower().replace('_', ' '),
                    'weight': 1.0 + (score / 100)
                }
                symbol_score = score
            
            # ============ CONSTRUIR RESULTADO ============
            resultado = {
                'correlation_score': correlation_score,
                'rotation_signal': rotation_signal,
                'weight_modifier': weight_modifier,
                'symbol_recommendation': symbol_recommendation,
                'symbol_score': symbol_score,
                'btc_analysis': {
                    'decision': {'action': btc_action, 'confidence': btc_confidence},
                    'trend': {
                        'direction': btc_trend,
                        'confidence': btc_trend_confidence,
                        'adx': btc_adx,
                        'plus_di': btc_plus_di,
                        'minus_di': btc_minus_di
                    }
                },
                'paxg_analysis': {
                    'trend': {
                        'direction': paxg_trend,
                        'adx': paxg_adx
                    }
                },
                'paxg_btc_analysis': {
                    'decision': {'action': ratio_action, 'confidence': ratio_confidence},
                    'trend': {
                        'direction': ratio_trend,
                        'confidence': ratio_trend_confidence,
                        'adx': ratio_adx
                    }
                }
            }
            
            print(f"\n📊 RESULTADO FINAL:")
            print(f"   Señal: {rotation_signal}")
            print(f"   Weight modifier: {weight_modifier}")
            print(f"   BTC ADX en resultado: {resultado['btc_analysis']['trend']['adx']}")
            print(f"   RATIO ADX en resultado: {resultado['paxg_btc_analysis']['trend']['adx']}")
            print(f"{'='*60}\n")
            
            return resultado
            
        except Exception as e:
            print(f"❌ Error en analyze_correlation_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'correlation_score': 0,
                'rotation_signal': 'NEUTRAL',
                'weight_modifier': 1.0,
                'symbol_recommendation': {'action': 'NEUTRAL', 'reason': 'error', 'weight': 1.0},
                'symbol_score': 0,
                'btc_analysis': {
                    'decision': {'action': 'N/A'},
                    'trend': {'direction': 'neutral', 'adx': 0}
                },
                'paxg_analysis': {
                    'trend': {'direction': 'neutral', 'adx': 0}
                },
                'paxg_btc_analysis': {
                    'decision': {'action': 'N/A'},
                    'trend': {'direction': 'neutral', 'adx': 0}
                }
            }

    # ========================================================================
    # CORRELACION FORZADA
    # ========================================================================

    
    def calculate_correlation_from_results(self, results, current_symbol):
        """Calcula la correlación directamente desde los resultados de analyze_all_pairs"""
        try:
            print(f"\n{'='*60}")
            print(f"📊 [CORRELACIÓN RADICAL] Procesando para {current_symbol}")
            print(f"{'='*60}")
            
            # Obtener análisis de los 3 pares
            btc_result = results.get('BTC-USDT', {})
            paxg_result = results.get('PAXG-USDT', {})
            ratio_result = results.get('PAXG-BTC', {})
            
            # Extraer datos de BTC
            btc_trend = btc_result.get('trend', {})
            btc_decision = btc_result.get('decision', {})
            
            btc_action = btc_decision.get('action', 'NO_OPERAR')
            btc_confidence = btc_decision.get('confidence', 0)
            btc_direction = btc_trend.get('direction', 'neutral')
            btc_adx = float(btc_trend.get('adx', 0))
            btc_plus_di = float(btc_trend.get('plus_di', 0))
            btc_minus_di = float(btc_trend.get('minus_di', 0))
            
            # Extraer datos de PAXG
            paxg_trend = paxg_result.get('trend', {})
            paxg_direction = paxg_trend.get('direction', 'neutral')
            paxg_adx = float(paxg_trend.get('adx', 0))
            
            # Extraer datos del RATIO
            ratio_trend = ratio_result.get('trend', {})
            ratio_decision = ratio_result.get('decision', {})
            
            ratio_action = ratio_decision.get('action', 'NO_OPERAR')
            ratio_confidence = ratio_decision.get('confidence', 0)
            ratio_direction = ratio_trend.get('direction', 'neutral')
            ratio_adx = float(ratio_trend.get('adx', 0))
            
            print(f"\n📊 Datos extraídos:")
            print(f"   BTC: acción={btc_action} (conf {btc_confidence:.0f}%), tendencia={btc_direction}, ADX={btc_adx:.1f}")
            print(f"   RATIO: acción={ratio_action} (conf {ratio_confidence:.0f}%), tendencia={ratio_direction}, ADX={ratio_adx:.1f}")
            print(f"   PAXG: tendencia={paxg_direction}, ADX={paxg_adx:.1f}")
            
            # ============ LÓGICA DE ROTACIÓN (IGUAL QUE ANTES) ============
            rotation_signal = 'NEUTRAL'
            weight_modifier = 1.0
            
            # RISK_ON: BTC compra/alcista + ratio venta/bajista
            if (btc_action in ['COMPRA_SPOT', 'LONG'] or btc_direction == 'bullish') and \
               (ratio_action in ['VENTA_SPOT', 'SHORT'] or ratio_direction == 'bearish'):
                rotation_signal = 'RISK_ON'
                weight_modifier = 1.3 if current_symbol == 'BTC-USDT' else 1.2
            
            # RISK_OFF: BTC venta/bajista + ratio compra/alcista
            elif (btc_action in ['VENTA_SPOT', 'SHORT'] or btc_direction == 'bearish') and \
                 (ratio_action in ['COMPRA_SPOT', 'LONG'] or ratio_direction == 'bullish'):
                rotation_signal = 'RISK_OFF'
                weight_modifier = 1.3 if current_symbol == 'PAXG-USDT' else 1.2
            
            # POSITIVE_CORRELATION
            elif btc_direction == 'bullish' and ratio_direction == 'bullish':
                rotation_signal = 'POSITIVE_CORRELATION'
                weight_modifier = 1.1
            
            # NEGATIVE_CORRELATION
            elif btc_direction == 'bearish' and ratio_direction == 'bearish':
                rotation_signal = 'NEGATIVE_CORRELATION'
                weight_modifier = 0.9
            
            # BTC_STRONGER
            elif btc_direction == 'bullish' and paxg_direction == 'bearish':
                rotation_signal = 'BTC_STRONGER'
                weight_modifier = 1.15 if current_symbol == 'BTC-USDT' else 1.0
            
            # PAXG_STRONGER
            elif paxg_direction == 'bullish' and btc_direction == 'bearish':
                rotation_signal = 'PAXG_STRONGER'
                weight_modifier = 1.15 if current_symbol == 'PAXG-USDT' else 1.0
            
            print(f"\n📊 RESULTADO RADICAL:")
            print(f"   Señal: {rotation_signal}")
            print(f"   Weight modifier: {weight_modifier}")
            print(f"{'='*60}\n")
            
            return {
                'rotation_signal': rotation_signal,
                'weight_modifier': weight_modifier,
                'btc_analysis': {
                    'decision': {'action': btc_action, 'confidence': btc_confidence},
                    'trend': {
                        'direction': btc_direction,
                        'adx': btc_adx,
                        'plus_di': btc_plus_di,
                        'minus_di': btc_minus_di
                    }
                },
                'paxg_analysis': {
                    'trend': {
                        'direction': paxg_direction,
                        'adx': paxg_adx
                    }
                },
                'paxg_btc_analysis': {
                    'decision': {'action': ratio_action, 'confidence': ratio_confidence},
                    'trend': {
                        'direction': ratio_direction,
                        'adx': ratio_adx
                    }
                }
            }
            
        except Exception as e:
            print(f"❌ Error en calculate_correlation_from_results: {e}")
            import traceback
            traceback.print_exc()
            return {
                'rotation_signal': 'NEUTRAL',
                'weight_modifier': 1.0,
                'btc_analysis': {
                    'decision': {'action': 'N/A'},
                    'trend': {'direction': 'neutral', 'adx': 0}
                },
                'paxg_analysis': {
                    'trend': {'direction': 'neutral', 'adx': 0}
                },
                'paxg_btc_analysis': {
                    'decision': {'action': 'N/A'},
                    'trend': {'direction': 'neutral', 'adx': 0}
                }
            }   
    
    
    
    
    
    # ========================================================================
    # ANALISIS DEL HORARIO DEL MERCADO
    # ========================================================================

    def analyze_market_hours_layer(self, current_time=None):
        """Capa 7: Análisis de Estacionalidad y Horarios de Mercado - VERSIÓN CORREGIDA"""
        try:
            if current_time is None:
                current_time = datetime.now(self.bolivia_tz)
            
            hour = current_time.hour
            minute = current_time.minute
            weekday = current_time.weekday()  # 0=Lunes, 6=Domingo
            
            # Valores por defecto
            session = 'UNKNOWN'
            session_name = 'Desconocido'
            session_icon = '⏰'
            liquidity = 'desconocida'
            volatility = 'desconocida'
            session_weight = 1.0
            session_description = ''
            
            overlap = 'NONE'
            overlap_name = 'Sin solapamiento'
            overlap_weight = 1.0
            
            day_type = 'UNKNOWN'
            day_name = 'Desconocido'
            day_icon = '📅'
            day_weight = 1.0
            day_description = ''
            
            special_event = None
            event_weight = 1.0
            event_description = None
            
            # ============ IDENTIFICAR SESIÓN DE MERCADO ============
            # Horario Bolivia (America/La_Paz) = UTC-4
            
            # Sesión Asiática: 19:00 - 03:00 (hora Bolivia)
            if (hour >= 19 and hour <= 23) or (hour >= 0 and hour < 3):
                session = 'ASIAN'
                session_name = 'Asiático'
                session_icon = '🌏'
                liquidity = 'baja'
                volatility = 'moderada'
                session_weight = 0.85  # -15% peso
                session_description = 'Menor liquidez, movimientos más erráticos'
                
            # Sesión Europea: 03:00 - 11:00 (hora Bolivia)
            elif hour >= 3 and hour < 11:
                session = 'EUROPEAN'
                session_name = 'Europeo'
                session_icon = '🇪🇺'
                liquidity = 'alta'
                volatility = 'moderada'
                session_weight = 1.0
                session_description = 'Buen volumen, tendencias más definidas'
                
            # Sesión Americana: 11:00 - 19:00 (hora Bolivia)
            elif hour >= 11 and hour < 19:
                session = 'AMERICAN'
                session_name = 'Americano'
                session_icon = '🇺🇸'
                liquidity = 'muy alta'
                volatility = 'alta'
                session_weight = 1.15  # +15% peso
                session_description = 'Máxima liquidez, mayor volatilidad'
            
            # Solapamiento Europa-América: 11:00 - 15:00
            if hour >= 11 and hour < 15:
                overlap = 'EUROPE_AMERICA'
                overlap_name = 'Solapamiento Europa-América'
                overlap_weight = 1.25  # +25% peso
                session_description = 'Máxima liquidez del día'
            
            # ============ ANÁLISIS POR DÍA DE LA SEMANA ============
            # Lunes: Apertura errática
            if weekday == 0:
                day_type = 'MONDAY'
                day_name = 'Lunes'
                day_icon = '📆'
                day_weight = 0.9  # -10% peso
                day_description = 'Apertura de semana, mayor probabilidad de gaps'
                
            # Martes - Jueves: Días óptimos
            elif weekday in [1, 2, 3]:
                day_names = ['Martes', 'Miércoles', 'Jueves']
                day_type = 'OPTIMAL'
                day_name = day_names[weekday-1]
                day_icon = '✅'
                day_weight = 1.1  # +10% peso
                day_description = 'Días óptimos para trading direccional'
                
            # Viernes: Cierre semanal
            elif weekday == 4:
                day_type = 'FRIDAY'
                day_name = 'Viernes'
                day_icon = '🏁'
                day_weight = 0.85  # -15% peso base
                if hour >= 15:
                    day_weight = 0.7  # -30% peso después de 15:00
                day_description = 'Cierre semanal, reducción de posiciones'
                
            # Fin de semana: Baja liquidez
            elif weekday in [5, 6]:
                day_type = 'WEEKEND'
                day_name = 'Sábado' if weekday == 5 else 'Domingo'
                day_icon = '🏖️'
                day_weight = 0.6  # -40% peso
                day_description = 'Muy baja liquidez, solo operaciones estratégicas'
            
            # ============ EVENTOS ESPECIALES ============
            # Viernes después de 15:00 (cierre de opciones semanales)
            if weekday == 4 and hour >= 15:
                special_event = 'WEEKLY_OPTIONS_EXPIRY'
                event_weight = 0.7
                event_description = 'Vencimiento de opciones semanales - alta volatilidad'
            
            # ============ CÁLCULO DE PESO TOTAL ============
            total_weight = session_weight * day_weight * overlap_weight * event_weight
            confidence_modifier = (total_weight - 1.0) * 100  # Convertir a puntos porcentuales
            
            # Descripción combinada
            full_description = f"{session_icon} {session_name} | {day_icon} {day_name}"
            if overlap != 'NONE':
                full_description += f" | {overlap_name}"
            
            return {
                'session': session,
                'session_name': session_name,
                'session_icon': session_icon,
                'liquidity': liquidity,
                'volatility': volatility,
                'session_weight': session_weight,
                'session_description': session_description,
                
                'overlap': overlap,
                'overlap_name': overlap_name,
                'overlap_weight': overlap_weight,
                
                'day_type': day_type,
                'day_name': day_name,
                'day_icon': day_icon,
                'day_weight': day_weight,
                'day_description': day_description,
                
                'special_event': special_event,
                'event_weight': event_weight,
                'event_description': event_description,
                
                'total_weight': total_weight,
                'confidence_modifier': confidence_modifier,
                'description': full_description
            }
            
        except Exception as e:
            print(f"Error en analyze_market_hours_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'session': 'UNKNOWN',
                'session_name': 'Desconocido',
                'session_icon': '⏰',
                'liquidity': 'desconocida',
                'volatility': 'desconocida',
                'session_weight': 1.0,
                'session_description': '',
                'overlap': 'NONE',
                'overlap_name': 'Sin solapamiento',
                'overlap_weight': 1.0,
                'day_type': 'UNKNOWN',
                'day_name': 'Desconocido',
                'day_icon': '📅',
                'day_weight': 1.0,
                'day_description': '',
                'special_event': None,
                'event_weight': 1.0,
                'event_description': None,
                'total_weight': 1.0,
                'confidence_modifier': 0,
                'description': 'Horario desconocido'
            }
    # ========================================================================
    # CAPAS DE CONFIRMACION
    # ========================================================================

    def analyze_confirmation_layer(self, df, structure, decision, trend, momentum, volatility):
        """Capa 8: Análisis de Confirmación de Rupturas - Filtro de Falsos Breakouts"""
        try:
            confirmation_status = 'CONFIRMED'
            confirmation_score = 0
            reason = []
            requires_wait = False
            wait_bars = 0
            alternative_signal = None
            
            if len(df) < 5:
                return {
                    'confirmation_status': 'UNKNOWN',
                    'confirmation_score': 0,
                    'reason': ['datos insuficientes'],
                    'requires_wait': False,
                    'wait_bars': 0,
                    'alternative_signal': None
                }
            
            # Obtener últimas 3 velas
            close = df['close'].values
            open_price = df['open'].values
            high = df['high'].values
            low = df['low'].values
            
            last_close = close[-1]
            last_open = open_price[-1]
            last_high = high[-1]
            last_low = low[-1]
            
            prev_close = close[-2] if len(close) > 1 else last_close
            prev_high = high[-2] if len(high) > 1 else last_high
            prev_low = low[-2] if len(low) > 1 else last_low
            
            # ============ DETECTAR POSIBLE RUPTURA ============
            is_breakout = False
            is_breakdown = False
            breakout_level = 0
            
            # Ruptura de resistencia
            if structure.get('nearest_resistance'):
                resistance = structure['nearest_resistance']
                if last_high > resistance:
                    is_breakout = True
                    breakout_level = resistance
            
            # Ruptura de soporte
            if structure.get('nearest_support'):
                support = structure['nearest_support']
                if last_low < support:
                    is_breakdown = True
                    breakout_level = support
            
            # ============ ANÁLISIS DE CONFIRMACIÓN ============
            if is_breakout or is_breakdown:
                
                # VERIFICAR 1: Cierre fuera del nivel
                if is_breakout and last_close > breakout_level:
                    confirmation_score += 30
                    reason.append('cierre_fuera_resistencia')
                elif is_breakdown and last_close < breakout_level:
                    confirmation_score += 30
                    reason.append('cierre_fuera_soporte')
                else:
                    # Rechazo - vela que abre fuera pero cierra dentro
                    confirmation_score -= 50
                    reason.append('rechazo_intrabarra')
                    confirmation_status = 'REJECTED'
                    
                    # Señal contraria
                    if is_breakout:
                        alternative_signal = 'SHORT'
                        reason.append('falso_breakout_alcista')
                    else:
                        alternative_signal = 'LONG'
                        reason.append('falso_breakdown_bajista')
                
                # VERIFICAR 2: Volumen de confirmación
                volume = df['volume'].values if 'volume' in df else []
                if len(volume) > 0:
                    avg_volume = np.mean(volume[-20:-1]) if len(volume) > 20 else np.mean(volume)
                    current_volume = volume[-1]
                    
                    if current_volume > avg_volume * 1.5:
                        confirmation_score += 20
                        reason.append('volumen_confirmacion')
                    elif current_volume < avg_volume * 0.7:
                        confirmation_score -= 20
                        reason.append('volumen_bajo')
                        requires_wait = True
                        wait_bars = 1
                
                # VERIFICAR 3: Tamaño de la vela
                candle_range = last_high - last_low
                body_size = abs(last_close - last_open)
                avg_range = np.mean(high[-20:] - low[-20:]) if len(high) > 20 else candle_range
                
                if candle_range > avg_range * 1.3:
                    confirmation_score += 15
                    reason.append('vela_fuerte')
                elif candle_range < avg_range * 0.7:
                    confirmation_score -= 15
                    reason.append('vela_debil')
                    requires_wait = True
                    wait_bars = max(wait_bars, 1)
                
                # VERIFICAR 4: Condiciones de sobrecompra/sobreventa
                if momentum.get('indicators', {}).get('rsi', 50) > 70 and is_breakout:
                    confirmation_score -= 25
                    reason.append('sobrecompra_ruptura')
                    requires_wait = True
                    wait_bars = max(wait_bars, 1)
                    
                if momentum.get('indicators', {}).get('rsi', 50) < 30 and is_breakdown:
                    confirmation_score -= 25
                    reason.append('sobreventa_ruptura')
                    requires_wait = True
                    wait_bars = max(wait_bars, 1)
                
                # VERIFICAR 5: Patrón de indecisión previo
                patterns = structure.get('patterns', {}).get('recent_patterns', [])
                indecision_count = sum(1 for p in patterns[-3:] if p.get('direction') == 'neutral')
                
                if indecision_count >= 2:
                    confirmation_score -= 20
                    reason.append('indecision_previa')
                    requires_wait = True
                    wait_bars = max(wait_bars, 2)
            
            # ============ DECISIÓN FINAL ============
            if confirmation_score >= 30:
                confirmation_status = 'CONFIRMED'
            elif confirmation_score >= 0:
                confirmation_status = 'PENDING'
            else:
                confirmation_status = 'REJECTED'
            
            return {
                'confirmation_status': confirmation_status,
                'confirmation_score': confirmation_score,
                'reason': reason,
                'requires_wait': requires_wait,
                'wait_bars': wait_bars,
                'alternative_signal': alternative_signal,
                'is_breakout': is_breakout,
                'is_breakdown': is_breakdown,
                'breakout_level': breakout_level
            }
            
        except Exception as e:
            print(f"Error en analyze_confirmation_layer: {e}")
            return {
                'confirmation_status': 'UNKNOWN',
                'confirmation_score': 0,
                'reason': ['error'],
                'requires_wait': False,
                'wait_bars': 0,
                'alternative_signal': None,
                'is_breakout': False,
                'is_breakdown': False,
                'breakout_level': 0
            }

    # ========================================================================
    # NUEVA CAPA 9: ANÁLISIS DE SENTIMIENTO (FEAR & GREED)
    # ========================================================================
    def analyze_sentiment_layer(self, symbol, timeframe):
        """
        Capa 9: Análisis de Sentimiento de Mercado basado en Fear & Greed Index
        Analiza el valor actual, tendencias 7d/30d y volatilidad del sentimiento
        """
        try:
            # Obtener datos de Fear & Greed (últimos 30 días)
            fng_data = self.get_fear_greed_data(limit=30)
            
            if fng_data is None or fng_data['current'] is None:
                return {
                    'available': False,
                    'current_value': 50,
                    'classification': 'Neutral',
                    'trend_7d': 0,
                    'trend_7d_pct': 0,
                    'trend_30d': 0,
                    'trend_30d_pct': 0,
                    'volatility': 0,
                    'sentiment_score': 0,
                    'sentiment_bias': 'neutral'
                }
            
            current_value = fng_data['current']['value']
            classification = fng_data['current']['classification']
            trend_7d = fng_data['trend_7d']
            trend_7d_pct = fng_data['trend_7d_pct']
            trend_30d = fng_data['trend_30d']
            trend_30d_pct = fng_data['trend_30d_pct']
            volatility = fng_data['volatility']
            
            # Calcular peso del sentimiento según el par
            if symbol == 'BTC-USDT':
                sentiment_weight = 1.0  # 100%
            elif symbol == 'PAXG-BTC':
                sentiment_weight = 0.7  # 70%
            elif symbol == 'PAXG-USDT':
                sentiment_weight = 0.3  # 30%
            else:
                sentiment_weight = 0.5
            
            # Ajustar según temporalidad
            if timeframe == '1W':
                # En semanal, importa más la tendencia 30d
                effective_trend = trend_30d_pct * 2
            elif timeframe == '1D':
                # En diario, balance entre valor actual y tendencia 7d
                effective_trend = (trend_7d_pct * 0.7) + (trend_30d_pct * 0.3)
            elif timeframe == '12h':
                # En 12h, más peso a tendencia 7d
                effective_trend = trend_7d_pct * 0.9
            else:  # 4h
                # En 4h, más peso al valor actual
                effective_trend = trend_7d_pct * 0.5
            
            # Determinar sesgo del sentimiento
            sentiment_bias = 'neutral'
            sentiment_score = 0
            
            # Extremos con tendencia favorable
            if current_value < 20 and trend_7d > 0:
                sentiment_bias = 'bullish_opportunity'
                sentiment_score = 40 * sentiment_weight
            elif current_value < 20 and trend_7d <= 0:
                sentiment_bias = 'bearish_caution'
                sentiment_score = -10 * sentiment_weight
            
            # Extremos con tendencia desfavorable
            elif current_value > 80 and trend_7d < 0:
                sentiment_bias = 'bearish_opportunity'
                sentiment_score = -40 * sentiment_weight
            elif current_value > 80 and trend_7d >= 0:
                sentiment_bias = 'bullish_caution'
                sentiment_score = 10 * sentiment_weight
            
            # Zonas moderadas
            elif 20 <= current_value < 40:
                if trend_7d > 0:
                    sentiment_bias = 'bullish_moderate'
                    sentiment_score = 15 * sentiment_weight
                else:
                    sentiment_bias = 'neutral_fear'
                    sentiment_score = 0
            
            elif 60 < current_value <= 80:
                if trend_7d < 0:
                    sentiment_bias = 'bearish_moderate'
                    sentiment_score = -15 * sentiment_weight
                else:
                    sentiment_bias = 'neutral_greed'
                    sentiment_score = 0
            
            else:  # 40-60
                sentiment_bias = 'neutral'
                sentiment_score = 0
            
            print(f"\n📊 CAPA DE SENTIMIENTO - {symbol} {timeframe}")
            print(f"   Fear & Greed: {current_value} ({classification})")
            print(f"   Tendencia 7d: {trend_7d:+.1f} puntos ({trend_7d_pct:+.1f}%)")
            print(f"   Tendencia 30d: {trend_30d:+.1f} puntos ({trend_30d_pct:+.1f}%)")
            print(f"   Volatilidad: {volatility:.1f}")
            print(f"   Peso según par: {sentiment_weight*100:.0f}%")
            print(f"   Sesgo: {sentiment_bias}")
            print(f"   Score: {sentiment_score:.1f}")
            
            return {
                'available': True,
                'current_value': current_value,
                'classification': classification,
                'trend_7d': float(trend_7d),
                'trend_7d_pct': float(trend_7d_pct),
                'trend_30d': float(trend_30d),
                'trend_30d_pct': float(trend_30d_pct),
                'volatility': float(volatility),
                'sentiment_score': float(sentiment_score),
                'sentiment_bias': sentiment_bias,
                'historical': fng_data['historical']  # Para gráficos
            }
            
        except Exception as e:
            print(f"❌ Error en analyze_sentiment_layer: {e}")
            import traceback
            traceback.print_exc()
            return {
                'available': False,
                'current_value': 50,
                'classification': 'Neutral',
                'trend_7d': 0,
                'trend_7d_pct': 0,
                'trend_30d': 0,
                'trend_30d_pct': 0,
                'volatility': 0,
                'sentiment_score': 0,
                'sentiment_bias': 'neutral',
                'historical': []
            }    
    
      
    # ========================================================================
    # Tiempo como variable de decision
    # ========================================================================

    def analyze_time_factor_layer(self, df, decision, levels):
        """Analizar factor tiempo - sin memoria, solo basado en velas recientes"""
        try:
            if len(df) < 10:
                return {
                    'time_quality': 'NEUTRAL',
                    'time_score': 0,
                    'expected_bars': 0,
                    'reason': 'datos_insuficientes'
                }
            
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            open_price = df['open'].values
            
            # 1. Velocidad del movimiento actual
            last_candle_range = high[-1] - low[-1]
            avg_range = np.mean(high[-10:] - low[-10:])
            
            if avg_range > 0:
                velocity_ratio = last_candle_range / avg_range
            else:
                velocity_ratio = 1
            
            # 2. Inactividad (velas estrechas consecutivas)
            narrow_candles = 0
            for i in range(min(5, len(df)-1)):
                idx = -1 - i
                rango = high[idx] - low[idx]
                if rango < avg_range * 0.5:
                    narrow_candles += 1
                else:
                    break
            
            # 3. Estancamiento en niveles (el precio no avanza)
            price_range_5 = max(close[-5:]) - min(close[-5:])
            price_range_20 = max(close[-20:]) - min(close[-20:]) if len(close) >= 20 else price_range_5 * 2
            
            stagnation_ratio = price_range_5 / price_range_20 if price_range_20 > 0 else 1
            
            # 4. Calcular score de tiempo
            time_score = 0
            reason = []
            
            # Alta velocidad es buena para entrada
            if velocity_ratio > 1.5:
                time_score += 20
                reason.append('movimiento_rápido')
            elif velocity_ratio < 0.5:
                time_score -= 15
                reason.append('movimiento_lento')
            
            # Muchas velas estrechas es malo (indecisión)
            if narrow_candles >= 3:
                time_score -= 25
                reason.append('indecisión_prolongada')
            elif narrow_candles == 0:
                time_score += 10
                reason.append('velas_activas')
            
            # Estancamiento es malo
            if stagnation_ratio < 0.2:
                time_score -= 30
                reason.append('estancamiento_en_rango')
            elif stagnation_ratio > 0.8:
                time_score += 15
                reason.append('movimiento_direccional')
            
            # Estimar velas esperadas para alcanzar TP
            if decision in ['LONG', 'COMPRA_SPOT'] and levels.get('take_profit', 0) > 0:
                distancia_tp = levels['take_profit'] - close[-1]
                movimiento_por_vela = avg_range * 0.7  # Asumimos que cada vela mueve 70% del rango
                if movimiento_por_vela > 0:
                    expected_bars = int(distancia_tp / movimiento_por_vela)
                else:
                    expected_bars = 10
            elif decision in ['SHORT', 'VENTA_SPOT'] and levels.get('take_profit', 0) > 0:
                distancia_tp = close[-1] - levels['take_profit']
                movimiento_por_vela = avg_range * 0.7
                if movimiento_por_vela > 0:
                    expected_bars = int(distancia_tp / movimiento_por_vela)
                else:
                    expected_bars = 10
            else:
                expected_bars = 0
            
            # Determinar calidad temporal
            if time_score >= 20:
                time_quality = 'ÓPTIMO'
            elif time_score >= 0:
                time_quality = 'ACEPTABLE'
            elif time_score >= -20:
                time_quality = 'DESFAVORABLE'
            else:
                time_quality = 'PÉSIMO'
            
            return {
                'time_quality': time_quality,
                'time_score': time_score,
                'expected_bars': expected_bars,
                'velocity_ratio': float(velocity_ratio),
                'narrow_candles': narrow_candles,
                'stagnation_ratio': float(stagnation_ratio),
                'reason': reason
            }
            
        except Exception as e:
            print(f"Error en analyze_time_factor_layer: {e}")
            return {
                'time_quality': 'NEUTRAL',
                'time_score': 0,
                'expected_bars': 0,
                'velocity_ratio': 1.0,
                'narrow_candles': 0,
                'stagnation_ratio': 0.5,
                'reason': ['error']
            }

    # ========================================================================
    # CONVICCION DINAMICA
    # ========================================================================

    def calculate_dynamic_conviction(self, base_confidence, trend_score, momentum_score, 
                                   volatility_score, volume_score, structure_score,
                                   correlation_modifier, hours_modifier, confirmation_score):
        """Calcular convicción SEPARANDO tendencia de entrada"""
        try:
            # ============ CONVICCIÓN DE TENDENCIA (macro) ============
            pesos_tendencia = {
                'trend': 0.40,
                'momentum': 0.25,
                'volume': 0.20,
                'structure': 0.15
            }
            
            tendencia_score = (
                trend_score * pesos_tendencia['trend'] +
                momentum_score * pesos_tendencia['momentum'] +
                volume_score * pesos_tendencia['volume'] +
                structure_score * pesos_tendencia['structure']
            )
            
            # Normalizar tendencia (0-100)
            tendencia_conviction = max(0, min(100, 50 + tendencia_score))
            
            # ============ CONVICCIÓN DE ENTRADA (micro) ============
            pesos_entrada = {
                'volatility': 0.35,
                'confirmation': 0.35,
                'momentum': 0.20,
                'volume': 0.10
            }
            
            entrada_score = (
                volatility_score * pesos_entrada['volatility'] +
                confirmation_score * pesos_entrada['confirmation'] +
                momentum_score * pesos_entrada['momentum'] +
                volume_score * pesos_entrada['volume']
            )
            
            # Aplicar modificadores de correlación y horarios SOLO a entrada
            entrada_score_corregida = entrada_score + correlation_modifier * 10 + (hours_modifier - 1.0) * 50
            entrada_conviction = max(0, min(100, 50 + entrada_score_corregida))
            
            # ============ CONVICCIÓN FINAL (combinada) ============
            # La convicción final es la menor de ambas (principio de precaución)
            raw_conviction = min(tendencia_conviction, entrada_conviction)
            
            # Ajustar por base_confidence
            raw_conviction = (raw_conviction * 0.7 + base_confidence * 0.3)
            raw_conviction = max(0, min(100, raw_conviction))
            
            # ============ NIVELES DE CONVICCIÓN ============
            if raw_conviction >= 85:
                level = 'ALTA'
                icon = '🟢'
                description = 'Tendencia fuerte y condiciones óptimas de entrada'
                suggested_size = 1.0
                suggested_leverage_modifier = 1.0
                entry_quality = 'EXCELENTE'
            elif raw_conviction >= 70:
                level = 'MEDIA-ALTA'
                icon = '🟡'
                description = 'Buena tendencia, entrada razonable'
                suggested_size = 0.8
                suggested_leverage_modifier = 0.8
                entry_quality = 'BUENA'
            elif raw_conviction >= 55:
                level = 'MEDIA'
                icon = '🟠'
                description = 'Tendencia presente pero entrada mejorable'
                suggested_size = 0.6
                suggested_leverage_modifier = 0.6
                entry_quality = 'REGULAR'
            elif raw_conviction >= 40:
                level = 'BAJA'
                icon = '🔴'
                description = 'Tendencia débil o entrada forzada'
                suggested_size = 0.3
                suggested_leverage_modifier = 0.3
                entry_quality = 'DEFICIENTE'
            else:
                level = 'MUY BAJA'
                icon = '⛔'
                description = 'Condiciones desfavorables - NO ENTRAR'
                suggested_size = 0.0
                suggested_leverage_modifier = 0.0
                entry_quality = 'PÉSIMA'
            
            # Factores de degradación/bonificación
            degradation_reasons = []
            bonus_reasons = []
            
            if tendencia_conviction < entrada_conviction - 20:
                degradation_reasons.append("tendencia más débil que señal de entrada")
            if entrada_conviction < tendencia_conviction - 20:
                bonus_reasons.append("buena entrada en tendencia estable")
            if correlation_modifier < 0.9:
                degradation_reasons.append("correlación desfavorable")
            if hours_modifier > 1.1:
                bonus_reasons.append("horario óptimo")
            
            return {
                'raw_conviction': raw_conviction,
                'tendencia_conviction': tendencia_conviction,
                'entrada_conviction': entrada_conviction,
                'level': level,
                'icon': icon,
                'description': description,
                'entry_quality': entry_quality,
                'suggested_size': suggested_size,
                'suggested_leverage_modifier': suggested_leverage_modifier,
                'degradation_reasons': degradation_reasons,
                'bonus_reasons': bonus_reasons,
                'components': {
                    'base_confidence': base_confidence,
                    'trend_score': trend_score,
                    'momentum_score': momentum_score,
                    'volatility_score': volatility_score,
                    'volume_score': volume_score,
                    'structure_score': structure_score,
                    'correlation_impact': correlation_modifier * 10,
                    'hours_impact': (hours_modifier - 1.0) * 50,
                    'confirmation_impact': confirmation_score
                }
            }
            
        except Exception as e:
            print(f"Error en calculate_dynamic_conviction: {e}")
            return {
                'raw_conviction': 0,
                'tendencia_conviction': 0,
                'entrada_conviction': 0,
                'level': 'ERROR',
                'icon': '❌',
                'description': 'Error en cálculo',
                'entry_quality': 'DESCONOCIDA',
                'suggested_size': 0.0,
                'suggested_leverage_modifier': 0.0,
                'degradation_reasons': [],
                'bonus_reasons': []
            }


    # ========================================================================
    # SISTEMA DE VOTACIÓN Y DECISIÓN FINAL
    # ========================================================================
    
    def vote_on_actions(self, trend, momentum, volatility, volume, structure, 
                       correlation, market_hours, confirmation, symbol, timeframe):
        """Sistema de votación ponderada - CON NUEVAS CAPAS DE CORRELACIÓN, HORARIOS Y CONFIRMACIÓN"""
        
        # Inicializar pesos
        action_weights = {
            'COMPRA_SPOT': 0,
            'VENTA_SPOT': 0,
            'LONG': 0,
            'SHORT': 0,
            'NO_OPERAR': 0
        }
        
        # Scores por capa (para convicción dinámica)
        trend_score = 0
        momentum_score = 0
        volatility_score = 0
        volume_score = 0
        structure_score = 0
        
        # Verificar que los parámetros no sean None
        trend = trend if trend else {}
        momentum = momentum if momentum else {}
        volatility = volatility if volatility else {}
        volume = volume if volume else {}
        structure = structure if structure else {}
        correlation = correlation if correlation else {}
        market_hours = market_hours if market_hours else {}
        confirmation = confirmation if confirmation else {}
        
        # ============ VERIFICACIONES DE NO OPERAR (VETO) ============
        no_trade_score = 0
        
        # ADX bajo - mercado sin dirección
        if trend.get('strength') == 'weak' and trend.get('adx', 0) < 20: #adx_value
            no_trade_score += 100
            action_weights['NO_OPERAR'] += 100
        
        # Volatilidad extrema o condiciones no operables
        if not volatility.get('operability', True):
            for reason in volatility.get('no_trade_reason', []):
                no_trade_score += 80
                action_weights['NO_OPERAR'] += 80
        
        # Volumen extremadamente bajo
        if volume.get('volume_participation') == 'low' and volume.get('volume_ratio', 1) < 0.5:
            no_trade_score += 70
            action_weights['NO_OPERAR'] += 70
        
        # Contradicción entre temporalidades (detectada en trend layer)
        if 'tf_severe_conflict' in [v.get('source', '') for v in trend.get('votes', [])]:
            no_trade_score += 100
            action_weights['NO_OPERAR'] += 100
        
        # Patrones de indecisión consecutivos (3+ dojis/peonzas)
        if structure.get('patterns', {}).get('neutral_count', 0) >= 3:
            no_trade_score += 70
            action_weights['NO_OPERAR'] += 70
        
        # ============ FTMaverick - ZONAS DE NO OPERACIÓN ============
        if volatility.get('ftm_state') == 'STRONG_DOWN':
            no_trade_score += 100
            action_weights['NO_OPERAR'] += 100
        elif volatility.get('ftm_state') == 'WEAK_DOWN' and volatility.get('bb_width', 100) < 3:
            no_trade_score += 70
            action_weights['NO_OPERAR'] += 70
        
        # Contracción prolongada
        if volatility.get('contraction_count', 0) >= 8:
            no_trade_score += 85
            action_weights['NO_OPERAR'] += 85
            if volatility.get('contraction_count', 0) >= 12:
                no_trade_score += 30
                action_weights['NO_OPERAR'] += 30
        
        # ============ CONFIRMACIÓN DE RUPTURAS ============
        if confirmation.get('confirmation_status') == 'REJECTED':
            no_trade_score += 100
            action_weights['NO_OPERAR'] += 100
            reason = f"rechazo_{confirmation.get('reason', [''])[0]}"
            
        if confirmation.get('requires_wait', False):
            # No es veto, pero reduce confianza
            action_weights['NO_OPERAR'] += 30 * confirmation.get('wait_bars', 1)
            no_trade_score += 30 * confirmation.get('wait_bars', 1)
        
        # ============ SI NO OPERAR DOMINA, BLOQUEAR TODO ============
        if no_trade_score >= 70:
            return {
                'action': 'NO_OPERAR',
                'confidence': min(100, no_trade_score),
                'weights': action_weights,
                'reason': 'condiciones_de_mercado_desfavorables',
                'no_trade_score': no_trade_score
            }
        
        # ============ VOTACIÓN PARA SPOT ============
        if symbol in ['BTC-USDT', 'PAXG-USDT']:
            # ---------- COMPRA SPOT ----------
            # Tendencia alcista
            if trend.get('direction') == 'bullish' and trend.get('confidence', 0) > 60:
                weight = trend['confidence'] * 0.3
                action_weights['COMPRA_SPOT'] += weight
                trend_score += weight / 3
            
            # Momentum alcista
            if momentum.get('direction') == 'bullish' and momentum.get('confidence', 0) > 60:
                weight = momentum['confidence'] * 0.25
                action_weights['COMPRA_SPOT'] += weight
                momentum_score += weight / 2.5
                
                if 'rsi_divergence_bull' in momentum.get('divergences', []):
                    action_weights['COMPRA_SPOT'] += 30
                    momentum_score += 12
                if 'hidden_bull' in momentum.get('hidden_divergences', []):
                    action_weights['COMPRA_SPOT'] += 60
                    momentum_score += 24
            
            # Acumulación institucional
            if volume.get('accumulation_score', 0) > 2:
                action_weights['COMPRA_SPOT'] += 40
                volume_score += 40
                if volume.get('whale_buy', False):
                    action_weights['COMPRA_SPOT'] += 50
                    volume_score += 50
                if volume.get('whale_buy_confirmed', False):
                    action_weights['COMPRA_SPOT'] += 30
                    volume_score += 30
            
            # Patrones alcistas
            if structure.get('bullish_patterns_count', 0) > structure.get('bearish_patterns_count', 0) + 1:
                action_weights['COMPRA_SPOT'] += 30
                structure_score += 30
                
                patterns = structure.get('patterns', {}).get('recent_patterns', [])
                if any('HCH Invertido' in p.get('name', '') for p in patterns):
                    action_weights['COMPRA_SPOT'] += 100
                    structure_score += 100
            
            # Cerca de soporte
            if structure.get('nearest_support'):
                distance = abs(structure.get('current_price', 0) - structure['nearest_support']) / max(structure['current_price'], 1)
                if distance < 0.03:
                    action_weights['COMPRA_SPOT'] += 40
                    structure_score += 40
            
            # Order block alcista
            for ob in structure.get('order_blocks', []):
                if ob.get('type') == 'bullish':
                    distance = abs(ob.get('price_range', [0,0])[0] - structure.get('current_price', 0)) / max(structure['current_price'], 1)
                    if distance < 0.02:
                        action_weights['COMPRA_SPOT'] += 40
                        structure_score += 40
            
            # RSI Maverick en sobreventa
            if momentum.get('indicators', {}).get('rsi_maverick', 0.5) < 0.15:
                action_weights['COMPRA_SPOT'] += 50
                momentum_score += 50
            
            # FTMaverick alcista
            if volatility.get('ftm_state') == 'STRONG_UP':
                action_weights['COMPRA_SPOT'] += 40
                volatility_score += 40
                if trend.get('direction') == 'bullish':
                    action_weights['COMPRA_SPOT'] += 30
                    volatility_score += 30
            elif volatility.get('ftm_state') == 'WEAK_UP':
                action_weights['COMPRA_SPOT'] += 20
                volatility_score += 20
            
            # ---------- VENTA SPOT ----------
            # Tendencia bajista
            if trend.get('direction') == 'bearish' and trend.get('confidence', 0) > 60:
                weight = trend['confidence'] * 0.3
                action_weights['VENTA_SPOT'] += weight
                trend_score -= weight / 3
            
            # Momentum bajista
            if momentum.get('direction') == 'bearish' and momentum.get('confidence', 0) > 60:
                weight = momentum['confidence'] * 0.25
                action_weights['VENTA_SPOT'] += weight
                momentum_score -= weight / 2.5
                
                if 'rsi_divergence_bear' in momentum.get('divergences', []):
                    action_weights['VENTA_SPOT'] += 30
                    momentum_score -= 12
                if 'hidden_bear' in momentum.get('hidden_divergences', []):
                    action_weights['VENTA_SPOT'] += 60
                    momentum_score -= 24
            
            # Distribución institucional
            if volume.get('accumulation_score', 0) < -2:
                action_weights['VENTA_SPOT'] += 40
                volume_score -= 40
                if volume.get('whale_sell', False):
                    action_weights['VENTA_SPOT'] += 50
                    volume_score -= 50
                if volume.get('whale_sell_confirmed', False):
                    action_weights['VENTA_SPOT'] += 30
                    volume_score -= 30
            
            # Patrones bajistas
            if structure.get('bearish_patterns_count', 0) > structure.get('bullish_patterns_count', 0) + 1:
                action_weights['VENTA_SPOT'] += 30
                structure_score -= 30
                
                patterns = structure.get('patterns', {}).get('recent_patterns', [])
                if any('Hombro Cabeza Hombro' in p.get('name', '') for p in patterns):
                    action_weights['VENTA_SPOT'] += 100
                    structure_score -= 100
            
            # Cerca de resistencia
            if structure.get('nearest_resistance'):
                distance = abs(structure['nearest_resistance'] - structure.get('current_price', 0)) / max(structure['current_price'], 1)
                if distance < 0.03:
                    action_weights['VENTA_SPOT'] += 40
                    structure_score -= 40
        
        # ============ VOTACIÓN PARA FUTURES (SOLO BTC) ============
        if symbol == 'BTC-USDT':
            # LONG FUTURES
            if trend.get('direction') == 'bullish' and trend.get('confidence', 0) > 70 and trend.get('strength_score', 0) >= 1:
                weight = trend['confidence'] * 0.4
                action_weights['LONG'] += weight
                trend_score += weight / 2.5
            
            if momentum.get('direction') == 'bullish' and momentum.get('confidence', 0) > 65:
                weight = momentum['confidence'] * 0.3
                action_weights['LONG'] += weight
                momentum_score += weight / 3
            
            if volatility.get('squeeze_on') == False and 'squeeze_momentum_bull' in [v.get('source', '') for v in momentum.get('votes', [])]:
                action_weights['LONG'] += 50
                volatility_score += 50
                if volatility.get('squeeze_length', 0) >= 8:
                    action_weights['LONG'] += 40
                    volatility_score += 40
            
            if 'dmi_cross_bull' in [v.get('source', '') for v in trend.get('votes', [])]:
                action_weights['LONG'] += 40
                trend_score += 40
                if trend.get('adx', 0) > 25: # adx_value
                    action_weights['LONG'] += 30
                    trend_score += 30
            
            # SHORT FUTURES
            if trend.get('direction') == 'bearish' and trend.get('confidence', 0) > 70 and trend.get('strength_score', 0) >= 1:
                weight = trend['confidence'] * 0.4
                action_weights['SHORT'] += weight
                trend_score -= weight / 2.5
            
            if momentum.get('direction') == 'bearish' and momentum.get('confidence', 0) > 65:
                weight = momentum['confidence'] * 0.3
                action_weights['SHORT'] += weight
                momentum_score -= weight / 3
            
            if volatility.get('squeeze_on') == False and 'squeeze_momentum_bear' in [v.get('source', '') for v in momentum.get('votes', [])]:
                action_weights['SHORT'] += 50
                volatility_score -= 50
                if volatility.get('squeeze_length', 0) >= 8:
                    action_weights['SHORT'] += 40
                    volatility_score -= 40
            
            if 'dmi_cross_bear' in [v.get('source', '') for v in trend.get('votes', [])]:
                action_weights['SHORT'] += 40
                trend_score -= 40
                if trend.get('adx', 0) > 25: #adx_value
                    action_weights['SHORT'] += 30
                    trend_score -= 30
        
        # ============ VOTACIÓN PARA PAXG/BTC ============
        if symbol == 'PAXG-BTC':
            if momentum.get('direction') == 'bullish' and momentum.get('confidence', 0) > 60:
                weight = momentum['confidence'] * 0.4
                action_weights['COMPRA_SPOT'] += weight
                momentum_score += weight / 2.5
            
            if structure.get('bullish_patterns_count', 0) > 2:
                action_weights['COMPRA_SPOT'] += 40
                structure_score += 40
            
            if volume.get('accumulation_score', 0) > 1:
                action_weights['COMPRA_SPOT'] += 30
                volume_score += 30
            
            if momentum.get('direction') == 'bearish' and momentum.get('confidence', 0) > 60:
                weight = momentum['confidence'] * 0.4
                action_weights['VENTA_SPOT'] += weight
                momentum_score -= weight / 2.5
            
            if structure.get('bearish_patterns_count', 0) > 2:
                action_weights['VENTA_SPOT'] += 40
                structure_score -= 40
        
            # ============ APLICAR MODIFICADORES DE CORRELACIÓN ============
            corr = correlation.get('symbol_recommendation', {})
            weight_modifier = corr.get('weight', 1.0)
            symbol_score = correlation.get('symbol_score', 0)
            
            if symbol in ['BTC-USDT', 'PAXG-USDT', 'PAXG-BTC']:
                action_weights['COMPRA_SPOT'] *= weight_modifier
                action_weights['VENTA_SPOT'] *= weight_modifier
                action_weights['LONG'] *= weight_modifier
                action_weights['SHORT'] *= weight_modifier
                
                # Añadir score de correlación a la capa correspondiente
                if symbol == 'BTC-USDT':
                    trend_score += symbol_score * 0.5
                elif symbol == 'PAXG-USDT':
                    trend_score += symbol_score * 0.5
            
            # ============ APLICAR MODIFICADORES DE HORARIOS ============
            hours_modifier = market_hours.get('total_modifier', 1.0)
            action_weights['COMPRA_SPOT'] *= hours_modifier
            action_weights['VENTA_SPOT'] *= hours_modifier
            action_weights['LONG'] *= hours_modifier
            action_weights['SHORT'] *= hours_modifier
            
            # ============ AJUSTES POR TEMPORALIDAD ============
            if timeframe in ['1W', '1D']:
                action_weights['COMPRA_SPOT'] *= 1.2
                action_weights['VENTA_SPOT'] *= 1.2
                action_weights['LONG'] *= 0.5
                action_weights['SHORT'] *= 0.5
            elif timeframe in ['4h']:
                action_weights['LONG'] *= 1.3
                action_weights['SHORT'] *= 1.3
                action_weights['COMPRA_SPOT'] *= 0.8
                action_weights['VENTA_SPOT'] *= 0.8
            
            # ============ APLICAR MODIFICADORES DE CORRELACIÓN ============
            corr = correlation.get('symbol_recommendation', {})
            weight_modifier = corr.get('weight', 1.0)
            symbol_score = correlation.get('symbol_score', 0)
            
            if symbol in ['BTC-USDT', 'PAXG-USDT', 'PAXG-BTC']:
                action_weights['COMPRA_SPOT'] *= weight_modifier
                action_weights['VENTA_SPOT'] *= weight_modifier
                action_weights['LONG'] *= weight_modifier
                action_weights['SHORT'] *= weight_modifier
                
                # Añadir score de correlación a la capa correspondiente
                if symbol == 'BTC-USDT':
                    trend_score += symbol_score * 0.5
                elif symbol == 'PAXG-USDT':
                    trend_score += symbol_score * 0.5
            
            # ============ APLICAR MODIFICADORES DE HORARIOS ============
            hours_modifier = market_hours.get('total_modifier', 1.0)
            action_weights['COMPRA_SPOT'] *= hours_modifier
            action_weights['VENTA_SPOT'] *= hours_modifier
            action_weights['LONG'] *= hours_modifier
            action_weights['SHORT'] *= hours_modifier
            
            # ============ AJUSTES POR TEMPORALIDAD ============
            if timeframe in ['1W', '1D']:
                action_weights['COMPRA_SPOT'] *= 1.2
                action_weights['VENTA_SPOT'] *= 1.2
                action_weights['LONG'] *= 0.3  # Reducir futures en temporalidades largas
                action_weights['SHORT'] *= 0.3
            elif timeframe in ['4h']:
                action_weights['LONG'] *= 1.5  # Aumentar futures en 4h
                action_weights['SHORT'] *= 1.5
                action_weights['COMPRA_SPOT'] *= 0.7
                action_weights['VENTA_SPOT'] *= 0.7
            
            # ============ IMPLEMENTAR COHERENCIA DE PORTAFOLIO ============
            # Regla 1: No se puede tener LONG y SHORT altos simultáneamente
            if action_weights['LONG'] > 30 and action_weights['SHORT'] > 30:
                # El que tenga menor peso se reduce drásticamente
                if action_weights['LONG'] > action_weights['SHORT']:
                    action_weights['SHORT'] *= 0.2
                else:
                    action_weights['LONG'] *= 0.2
            
            # Regla 2: Futures tiene prioridad sobre Spot (es más rentable)
            if action_weights['LONG'] > action_weights['COMPRA_SPOT'] * 1.2:
                action_weights['COMPRA_SPOT'] *= 0.5  # Reducir spot si futures es mejor
            if action_weights['SHORT'] > action_weights['VENTA_SPOT'] * 1.2:
                action_weights['VENTA_SPOT'] *= 0.5
            
            # Regla 3: No mezclar direcciones opuestas en el mismo par
            if action_weights['LONG'] > 20 and action_weights['VENTA_SPOT'] > 20:
                action_weights['VENTA_SPOT'] *= 0.3  # Incompatible
            if action_weights['SHORT'] > 20 and action_weights['COMPRA_SPOT'] > 20:
                action_weights['COMPRA_SPOT'] *= 0.3
            
            # ============ DIFERENCIAR ENTRE NO_OPERAR Y ESPERAR ============
            # "ESPERAR" = hay dirección pero mal momento de entrada
            # "NO_OPERAR" = condiciones peligrosas o sin dirección
            
            esperar_score = 0
            no_operar_score = no_trade_score
            
            # Si hay tendencia pero mala entrada -> ESPERAR
            if abs(trend_score) > 30 and abs(entrada_score_temp) < 15:
                esperar_score = 70
                no_operar_score = 30
            
            # Si hay entrada buena pero tendencia débil -> ESPERAR
            if abs(entrada_score_temp) > 25 and abs(trend_score) < 15:
                esperar_score = 65
                no_operar_score = 35
            
            # Si hay peligro claro -> NO_OPERAR
            if volatility.get('ftm_state') == 'STRONG_DOWN' or volatility.get('atr_pct', 0) > 5:
                no_operar_score = 100
                esperar_score = 0
            
            # Asignar pesos a las acciones de espera
            action_weights['ESPERAR'] = esperar_score
            action_weights['NO_OPERAR'] = no_operar_score
            
            # ============ SELECCIONAR ACCIÓN GANADORA ============
            # Filtrar acciones con peso significativo
            acciones_validas = {k: v for k, v in action_weights.items() if v > 20}
            
            if not acciones_validas:
                # Si nada supera 20, la mejor opción es ESPERAR o NO_OPERAR
                if esperar_score > no_operar_score:
                    max_action = ('ESPERAR', esperar_score)
                else:
                    max_action = ('NO_OPERAR', no_operar_score)
            else:
                max_action = max(acciones_validas.items(), key=lambda x: x[1])
            
            # Si la acción ganadora es de trading pero la convicción es muy baja, convertir a ESPERAR
            if max_action[0] in ['COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT']:
                if max_action[1] < 50:
                    return {
                        'action': 'ESPERAR',
                        'confidence': 70,
                        'weights': action_weights,
                        'reason': 'señal_débil_esperar_confirmación',
                        'no_trade_score': no_operar_score,
                        'esperar_score': esperar_score
                    }
            
            confidence = min(100, max_action[1])
            
            # ============ CALCULAR CONVICCIÓN DINÁMICA ============
            base_confidence = confidence
            correlation_modifier = correlation.get('weight_modifier', 1.0)
            hours_modifier = market_hours.get('total_modifier', 1.0)
            confirmation_score = confirmation.get('confirmation_score', 0)
            
            # Guardar entrada_score_temp para usarlo en la función (definir antes)
            entrada_score_temp = volatility_score * 0.4 + confirmation_score * 0.4 + momentum_score * 0.2
            
            conviction = self.calculate_dynamic_conviction(
                base_confidence,
                trend_score,
                momentum_score,
                volatility_score,
                volume_score,
                structure_score,
                correlation_modifier,
                hours_modifier,
                confirmation_score
            )
            
            return {
                'action': max_action[0],
                'confidence': confidence,
                'conviction': conviction,
                'weights': action_weights,
                'reason': 'consenso_de_indicadores',
                'no_trade_score': no_operar_score,
                'esperar_score': esperar_score,
                'correlation': correlation,
                'market_hours': market_hours,
                'confirmation': confirmation
            }
    # === FIN vote_on_actions ===
    
    # === FUNCIÓN COMPLETA: calculate_entry_levels (FASE 3) ===
    # NUEVA VERSIÓN con TP único rentable+realista y SL óptimo protector+poco probable
    # Devuelve UN SOLO take_profit (no take_profit2 ni take_profit3)
    
    def _calculate_min_tp_distance_pct(self, timeframe, leverage=1, is_futures=False):
        """
        Retorna la distancia MÍNIMA del TP en % para asegurar rentabilidad.
        
        Regla base (spot):
        - 4h: >= 1.5%
        - 12h: >= 2.0%
        - 1D: >= 2.5%
        - 1W: >= 4.0%
        
        En futuros con apalancamiento >5x, se REDUCE porque el ROI se multiplica:
        - Para un ROI mínimo de 5% sobre el margen, se necesita: 5% / leverage
        - Pero nunca menos del 0.5% para cubrir comisiones (0.1% x 2 = 0.2%) + slippage
        """
        base = {
            '5m': 0.7,    # 0.7%
            '15m': 0.9,   # 0.9%
            '30m': 1.1,   # 1.1%
            '1h': 1.3,    # 1.3%
            '2h': 1.5,    # 1.5%
            '4h': 1.5,    # 1.5%
            '12h': 2.0,   # 2.0%
            '1D': 2.5,    # 2.5%
            '1W': 4.0     # 4.0%
        }
        min_pct = base.get(timeframe, 1.5)
        
        if is_futures and leverage > 1:
            # Con apalancamiento, ROI se amplifica. Aseguramos ROI mínimo 5% sobre margen.
            leverage_adjusted = max(0.5, 5.0 / leverage)
            # Retornar el MENOR de los dos (más permisivo con leverage alto)
            return min(min_pct, leverage_adjusted)
        
        return min_pct
    
    def _calculate_max_sl_distance_pct(self, timeframe):
        """
        Distancia MÁXIMA del SL en % (protección contra pérdidas catastróficas).
        """
        return {
            '5m': 1.5,
            '15m': 2.0,
            '30m': 2.5,
            '1h': 3.0,
            '2h': 3.5,
            '4h': 4.0,
            '12h': 5.0,
            '1D': 6.0,
            '1W': 8.0
        }.get(timeframe, 4.0)
    
    def _collect_tp_candidates(self, direction, structure, current_price, volatility, timeframe):
        """
        Recolecta TODOS los niveles candidatos para TP desde Smart Money.
        
        direction: 'long' (buscar niveles ARRIBA del precio) o 'short' (ABAJO)
        Retorna: lista de {'price', 'source', 'strength', 'confluence_count'}
        """
        candidates = []
        atr = volatility.get('atr', current_price * 0.02) or (current_price * 0.02)
        
        if direction == 'long':
            # 1. Order Blocks BAJISTAS por encima (donde el precio revierte hacia abajo)
            for ob in structure.get('order_blocks', []):
                if not isinstance(ob, dict):
                    continue
                if ob.get('type') == 'bearish':
                    price_range = ob.get('price_range', [0, 0])
                    if len(price_range) >= 2 and price_range[0] > current_price:
                        # Entrada al OB bajista (parte inferior del rango) es donde puede rechazar
                        target_price = price_range[0]
                        strength = ob.get('strength', 'moderate')
                        candidates.append({
                            'price': target_price,
                            'source': f"Order Block bajista ${target_price:.2f}",
                            'strength': 3 if strength == 'strong' else 2,
                            'volume_ratio': ob.get('volume_ratio', 1.0),
                            'type': 'ob'
                        })
            
            # 2. FVGs bajistas por encima (sin rellenar)
            for fvg in structure.get('fair_value_gaps', []):
                if not isinstance(fvg, dict) or fvg.get('filled', True):
                    continue
                if fvg.get('type') == 'bearish':
                    gap_bottom = fvg.get('gap_bottom', 0)
                    if gap_bottom > current_price:
                        candidates.append({
                            'price': gap_bottom,
                            'source': f"FVG bajista ${gap_bottom:.2f}",
                            'strength': 2 if fvg.get('strength') == 'strong' else 1,
                            'volume_ratio': fvg.get('volume_ratio', 1.0),
                            'type': 'fvg'
                        })
            
            # 3. Resistencias del análisis estructural
            for r in structure.get('resistances', []):
                if r and r > current_price:
                    candidates.append({
                        'price': r,
                        'source': f"Resistencia ${r:.2f}",
                        'strength': 2,
                        'volume_ratio': 1.0,
                        'type': 'resistance'
                    })
            
            # 4. Extensiones Fibonacci
            fib_ext = structure.get('fib_extensions', {}) or {}
            for level_name, price in fib_ext.items():
                if price and price > current_price:
                    strength = 3 if level_name in ('1.618', '1.272') else 1
                    candidates.append({
                        'price': price,
                        'source': f"Fibonacci {level_name}",
                        'strength': strength,
                        'volume_ratio': 1.0,
                        'type': 'fib'
                    })
            
            # 5. HVN (High Volume Nodes) por encima - fuerte magnetismo
            vp = structure.get('volume_profile', {}) or {}
            for hvn in vp.get('hvn_nodes', [])[:5]:
                if isinstance(hvn, dict):
                    hvn_price = hvn.get('price', 0)
                    if hvn_price > current_price * 1.005:  # Al menos 0.5% arriba
                        candidates.append({
                            'price': hvn_price,
                            'source': f"HVN ${hvn_price:.2f}",
                            'strength': 3,
                            'volume_ratio': hvn.get('volume_ratio', 1.0),
                            'type': 'hvn'
                        })
            
            # 6. VAH (Value Area High) si está arriba
            vah = vp.get('vah', 0)
            if vah and vah > current_price:
                candidates.append({
                    'price': vah,
                    'source': f"VAH ${vah:.2f}",
                    'strength': 2,
                    'volume_ratio': 1.0,
                    'type': 'va'
                })
            
            # 7. Zonas de alta densidad de liquidaciones SHORT (arriba del precio)
            # Estas son barreras donde muchos SHORTS serán liquidados si el precio sube
            # → precio puede pararse ahí temporalmente
            # (Se puede añadir después si se pasa liquidation)
        
        else:  # direction == 'short'
            # Espejo: buscar niveles POR DEBAJO del precio
            
            # 1. Order Blocks ALCISTAS por debajo
            for ob in structure.get('order_blocks', []):
                if not isinstance(ob, dict):
                    continue
                if ob.get('type') == 'bullish':
                    price_range = ob.get('price_range', [0, 0])
                    if len(price_range) >= 2 and price_range[1] < current_price:
                        target_price = price_range[1]  # Parte superior del OB alcista
                        strength = ob.get('strength', 'moderate')
                        candidates.append({
                            'price': target_price,
                            'source': f"Order Block alcista ${target_price:.2f}",
                            'strength': 3 if strength == 'strong' else 2,
                            'volume_ratio': ob.get('volume_ratio', 1.0),
                            'type': 'ob'
                        })
            
            # 2. FVGs alcistas por debajo (sin rellenar)
            for fvg in structure.get('fair_value_gaps', []):
                if not isinstance(fvg, dict) or fvg.get('filled', True):
                    continue
                if fvg.get('type') == 'bullish':
                    gap_top = fvg.get('gap_top', 0)
                    if 0 < gap_top < current_price:
                        candidates.append({
                            'price': gap_top,
                            'source': f"FVG alcista ${gap_top:.2f}",
                            'strength': 2 if fvg.get('strength') == 'strong' else 1,
                            'volume_ratio': fvg.get('volume_ratio', 1.0),
                            'type': 'fvg'
                        })
            
            # 3. Soportes
            for s in structure.get('supports', []):
                if s and s < current_price:
                    candidates.append({
                        'price': s,
                        'source': f"Soporte ${s:.2f}",
                        'strength': 2,
                        'volume_ratio': 1.0,
                        'type': 'support'
                    })
            
            # 4. Fibonacci (retrocesos hacia abajo)
            fib = structure.get('fib_levels', {}) or {}
            for level_name, price in fib.items():
                if price and price < current_price:
                    strength = 3 if level_name in ('0.618', '0.786') else 1
                    candidates.append({
                        'price': price,
                        'source': f"Fibonacci {level_name}",
                        'strength': strength,
                        'volume_ratio': 1.0,
                        'type': 'fib'
                    })
            
            # 5. HVN por debajo
            vp = structure.get('volume_profile', {}) or {}
            for hvn in vp.get('hvn_nodes', [])[:5]:
                if isinstance(hvn, dict):
                    hvn_price = hvn.get('price', 0)
                    if 0 < hvn_price < current_price * 0.995:
                        candidates.append({
                            'price': hvn_price,
                            'source': f"HVN ${hvn_price:.2f}",
                            'strength': 3,
                            'volume_ratio': hvn.get('volume_ratio', 1.0),
                            'type': 'hvn'
                        })
            
            # 6. VAL (Value Area Low)
            val = vp.get('val', 0)
            if val and val < current_price:
                candidates.append({
                    'price': val,
                    'source': f"VAL ${val:.2f}",
                    'strength': 2,
                    'volume_ratio': 1.0,
                    'type': 'va'
                })
        
        return candidates
    
    def _collect_sl_candidates(self, direction, structure, current_price, volatility, timeframe):
        """
        Recolecta candidatos para SL. La lógica es INVERSA al TP:
        - Para LONG: SL debe estar POR DEBAJO del precio (donde se invalida la tesis)
        - Para SHORT: SL debe estar POR ENCIMA del precio
        
        Los mejores SL están DETRÁS de una zona validada donde el precio NO debería llegar
        si la tesis se cumple.
        """
        candidates = []
        atr = volatility.get('atr', current_price * 0.02) or (current_price * 0.02)
        
        if direction == 'long':
            # SL debajo del precio
            
            # 1. Debajo del último swing low (pivot low)
            pivot_lows = structure.get('pivot_lows', [])
            for p in pivot_lows[-3:]:  # Últimos 3 pivotes
                if isinstance(p, dict):
                    p_price = p.get('price', 0)
                    if 0 < p_price < current_price:
                        # SL un poco DEBAJO del pivote (para dar margen)
                        candidates.append({
                            'price': p_price - atr * 0.3,
                            'source': f"Debajo swing low ${p_price:.2f}",
                            'strength': 3,
                            'type': 'swing'
                        })
            
            # 2. Debajo de OB alcista
            for ob in structure.get('order_blocks', []):
                if not isinstance(ob, dict):
                    continue
                if ob.get('type') == 'bullish':
                    price_range = ob.get('price_range', [0, 0])
                    if len(price_range) >= 2 and price_range[0] < current_price:
                        sl_price = price_range[0] - atr * 0.2
                        strength = 3 if ob.get('strength') == 'strong' else 2
                        candidates.append({
                            'price': sl_price,
                            'source': f"Debajo OB alcista ${price_range[0]:.2f}",
                            'strength': strength,
                            'type': 'ob'
                        })
            
            # 3. Debajo de FVG alcista sin rellenar
            for fvg in structure.get('fair_value_gaps', []):
                if not isinstance(fvg, dict) or fvg.get('filled', True):
                    continue
                if fvg.get('type') == 'bullish':
                    gap_bottom = fvg.get('gap_bottom', 0)
                    if 0 < gap_bottom < current_price:
                        candidates.append({
                            'price': gap_bottom - atr * 0.2,
                            'source': f"Debajo FVG alcista ${gap_bottom:.2f}",
                            'strength': 2,
                            'type': 'fvg'
                        })
            
            # 4. Debajo del soporte más cercano
            nearest_support = structure.get('nearest_support')
            if nearest_support and nearest_support < current_price:
                candidates.append({
                    'price': nearest_support - atr * 0.3,
                    'source': f"Debajo soporte ${nearest_support:.2f}",
                    'strength': 3,
                    'type': 'support'
                })
            
            # 5. Debajo del VAL (Value Area Low)
            vp = structure.get('volume_profile', {}) or {}
            val = vp.get('val', 0)
            if val and val < current_price:
                candidates.append({
                    'price': val - atr * 0.2,
                    'source': f"Debajo VAL ${val:.2f}",
                    'strength': 2,
                    'type': 'va'
                })
            
            # 6. Fallback: entry - 2 * ATR
            candidates.append({
                'price': current_price - atr * 2.0,
                'source': f"ATR fallback (-2×ATR)",
                'strength': 1,
                'type': 'atr'
            })
        
        else:  # direction == 'short'
            # SL por encima del precio
            
            pivot_highs = structure.get('pivot_highs', [])
            for p in pivot_highs[-3:]:
                if isinstance(p, dict):
                    p_price = p.get('price', 0)
                    if p_price > current_price:
                        candidates.append({
                            'price': p_price + atr * 0.3,
                            'source': f"Encima swing high ${p_price:.2f}",
                            'strength': 3,
                            'type': 'swing'
                        })
            
            for ob in structure.get('order_blocks', []):
                if not isinstance(ob, dict):
                    continue
                if ob.get('type') == 'bearish':
                    price_range = ob.get('price_range', [0, 0])
                    if len(price_range) >= 2 and price_range[1] > current_price:
                        sl_price = price_range[1] + atr * 0.2
                        strength = 3 if ob.get('strength') == 'strong' else 2
                        candidates.append({
                            'price': sl_price,
                            'source': f"Encima OB bajista ${price_range[1]:.2f}",
                            'strength': strength,
                            'type': 'ob'
                        })
            
            for fvg in structure.get('fair_value_gaps', []):
                if not isinstance(fvg, dict) or fvg.get('filled', True):
                    continue
                if fvg.get('type') == 'bearish':
                    gap_top = fvg.get('gap_top', 0)
                    if gap_top > current_price:
                        candidates.append({
                            'price': gap_top + atr * 0.2,
                            'source': f"Encima FVG bajista ${gap_top:.2f}",
                            'strength': 2,
                            'type': 'fvg'
                        })
            
            nearest_resistance = structure.get('nearest_resistance')
            if nearest_resistance and nearest_resistance > current_price:
                candidates.append({
                    'price': nearest_resistance + atr * 0.3,
                    'source': f"Encima resistencia ${nearest_resistance:.2f}",
                    'strength': 3,
                    'type': 'resistance'
                })
            
            vp = structure.get('volume_profile', {}) or {}
            vah = vp.get('vah', 0)
            if vah and vah > current_price:
                candidates.append({
                    'price': vah + atr * 0.2,
                    'source': f"Encima VAH ${vah:.2f}",
                    'strength': 2,
                    'type': 'va'
                })
            
            candidates.append({
                'price': current_price + atr * 2.0,
                'source': f"ATR fallback (+2×ATR)",
                'strength': 1,
                'type': 'atr'
            })
        
        return candidates
    
    def _score_tp_candidate(self, candidate, entry, direction, all_candidates, min_distance_pct):
        """
        Puntúa un candidato de TP.
        Un TP ideal: DISTANCIA suficiente (rentable) + ALTA probabilidad de ser tocado.
        
        score = (distancia_score × 0.4) + (probabilidad_score × 0.6)
        """
        price = candidate['price']
        distance_pct = abs(price - entry) / entry * 100 if entry > 0 else 0
        
        # Descartar si NO cumple distancia mínima
        if distance_pct < min_distance_pct:
            return -1  # Descarta
        
        # Score de distancia (más lejos = más rentable) — normalizado 0-100
        # Cap en 10% para no favorecer TPs irreales
        distance_score = min(100, (distance_pct / 10) * 100)
        
        # Score de probabilidad de toque:
        # - Fuerza del nivel (strength 1-3): peso 30
        # - Volumen anómalo cerca del nivel (volume_ratio): peso 20
        # - Confluencia con otros niveles cercanos (±0.5%): peso 50
        strength = candidate.get('strength', 1)
        volume_ratio = candidate.get('volume_ratio', 1.0)
        
        # Confluencia: contar otros candidatos cercanos
        confluence = 0
        for other in all_candidates:
            if other is candidate:
                continue
            other_price = other['price']
            if abs(other_price - price) / price < 0.005:  # Dentro de 0.5%
                confluence += 1
        
        strength_score = (strength / 3) * 30  # 0-30
        volume_score = min(20, (volume_ratio - 1) * 10)  # 0-20 (0 si volume_ratio<=1)
        confluence_score = min(50, confluence * 15)  # 0-50
        
        probability_score = strength_score + max(0, volume_score) + confluence_score
        
        total_score = (distance_score * 0.4) + (probability_score * 0.6)
        return total_score
    
    def _score_sl_candidate(self, candidate, entry, direction, timeframe, max_distance_pct, atr):
        """
        Puntúa un SL: menos probable de ser tocado + protector.
        
        score = (proteccion_score × 0.4) + (baja_probabilidad_score × 0.6)
        """
        price = candidate['price']
        distance_pct = abs(price - entry) / entry * 100 if entry > 0 else 0
        
        # Descartar si SL está muy cerca (menos 0.3%) o muy lejos (más max_distance_pct)
        if distance_pct < 0.3 or distance_pct > max_distance_pct:
            return -1
        
        # Score de protección: sweet spot alrededor de 1×ATR a 2×ATR
        atr_pct = (atr / entry) * 100 if entry > 0 else 1
        distance_in_atr = distance_pct / atr_pct if atr_pct > 0 else 1
        
        if 1.0 <= distance_in_atr <= 2.5:
            proteccion_score = 100  # Ideal
        elif 0.7 <= distance_in_atr < 1.0:
            proteccion_score = 70   # Un poco pegado
        elif 2.5 < distance_in_atr <= 3.5:
            proteccion_score = 80   # Un poco amplio pero ok
        elif distance_in_atr < 0.7:
            proteccion_score = 30   # Muy pegado (fácil de tocar)
        else:  # > 3.5
            proteccion_score = 40   # Muy amplio (poca protección real)
        
        # Score de baja probabilidad de toque:
        # - Fuerza del nivel (más fuerte = precio menos probable de romperlo): peso 60
        # - Tipo del nivel (swing/OB/FVG son más confiables que ATR fallback): peso 40
        strength = candidate.get('strength', 1)
        strength_score = (strength / 3) * 60
        
        type_bonus = {
            'swing': 40,
            'ob': 35,
            'fvg': 25,
            'support': 30,
            'resistance': 30,
            'va': 20,
            'atr': 5   # ATR fallback: menos fiable
        }
        type_score = type_bonus.get(candidate.get('type', 'atr'), 10)
        
        baja_prob_score = strength_score + type_score
        
        total_score = (proteccion_score * 0.4) + (baja_prob_score * 0.6)
        return total_score
    
    def _select_optimal_tp(self, direction, structure, current_price, volatility, timeframe, leverage=1, is_futures=False):
        """
        Selecciona el TP óptimo: rentable + probable.
        
        Retorna: (tp_price, tp_source, tp_score) o (None, "No hay TP válido", 0)
        """
        min_distance = self._calculate_min_tp_distance_pct(timeframe, leverage, is_futures)
        candidates = self._collect_tp_candidates(direction, structure, current_price, volatility, timeframe)
        
        if not candidates:
            return None, "Sin candidatos de TP", 0
        
        # Scoring
        scored = []
        for c in candidates:
            score = self._score_tp_candidate(c, current_price, direction, candidates, min_distance)
            if score > 0:
                scored.append((c, score))
        
        if not scored:
            return None, f"Ningún TP cumple distancia mínima ({min_distance:.1f}%)", 0
        
        # Ordenar por score descendente
        scored.sort(key=lambda x: -x[1])
        best = scored[0]
        
        return best[0]['price'], best[0]['source'], best[1]
    
    def _select_optimal_sl(self, direction, structure, current_price, volatility, timeframe):
        """
        Selecciona el SL óptimo: protector + poco probable de toque.
        
        Retorna: (sl_price, sl_source, sl_score)
        """
        max_distance = self._calculate_max_sl_distance_pct(timeframe)
        atr = volatility.get('atr', current_price * 0.02) or (current_price * 0.02)
        candidates = self._collect_sl_candidates(direction, structure, current_price, volatility, timeframe)
        
        if not candidates:
            # SIEMPRE hay al menos el ATR fallback — nunca debería llegar aquí
            atr_price = (current_price - atr * 2) if direction == 'long' else (current_price + atr * 2)
            return atr_price, "ATR fallback", 30
        
        scored = []
        for c in candidates:
            score = self._score_sl_candidate(c, current_price, direction, timeframe, max_distance, atr)
            if score > 0:
                scored.append((c, score))
        
        if not scored:
            # Fallback: usar el ATR
            atr_price = (current_price - atr * 2) if direction == 'long' else (current_price + atr * 2)
            return atr_price, "ATR fallback (sin candidatos válidos)", 30
        
        scored.sort(key=lambda x: -x[1])
        best = scored[0]
        return best[0]['price'], best[0]['source'], best[1]
    
    def calculate_entry_levels(self, decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation=None):
        """
        Calcula niveles de entrada, SL y TP.
        
        FASE 3: UN SOLO TP (el más rentable Y realista) + SL óptimo (protector y poco probable de toque).
        
        Si no hay un TP/SL válido o el R/R es < 1:1.5 → devuelve rejected_reason.
        """
        try:
            current_price = structure.get('current_price', 0)
            if current_price == 0:
                print("❌ Error: current_price es 0 en calculate_entry_levels")
                return self._get_default_levels(current_price, symbol)
            
            atr = volatility.get('atr', 0)
            atr_pct = volatility.get('atr_pct', 1.0) / 100
            
            if atr == 0 or atr_pct == 0:
                atr = current_price * 0.02
                atr_pct = 0.02
                volatility['atr'] = atr  # Actualizar para métodos internos
            
            print(f"💰 [FASE 3] Calculando niveles para {decision} - Precio: {current_price:.2f}, ATR: {atr:.4f}")
            
            # Solo procesar decisiones de trading
            if decision not in ('COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT'):
                return self._get_default_levels(current_price, symbol)
            
            # Determinar dirección
            direction = 'long' if decision in ('COMPRA_SPOT', 'LONG') else 'short'
            is_futures = decision in ('LONG', 'SHORT')
            
            # Entry = precio actual (con pequeño offset)
            if direction == 'long':
                entry = current_price * 1.001  # +0.1%
            else:
                entry = current_price * 0.999  # -0.1%
            
            # Apalancamiento base
            base_leverage = volatility.get('suggested_leverage', 5)
            if is_futures:
                # Ajuste por temporalidad
                if timeframe in ('5m', '15m', '30m'):
                    leverage = max(5, min(50, base_leverage))
                elif timeframe in ('1h', '2h', '4h'):
                    leverage = max(3, min(20, base_leverage))
                else:
                    leverage = max(1, min(5, base_leverage))
            else:
                leverage = 1
            
            # ============ SELECCIONAR TP ÓPTIMO ============
            tp_price, tp_source, tp_score = self._select_optimal_tp(
                direction, structure, current_price, volatility, timeframe, leverage, is_futures
            )
            
            # ============ SELECCIONAR SL ÓPTIMO ============
            sl_price, sl_source, sl_score = self._select_optimal_sl(
                direction, structure, current_price, volatility, timeframe
            )
            
            # ============ VALIDACIÓN ============
            if tp_price is None:
                print(f"   ⚠️ RECHAZADO: {tp_source}")
                return self._build_rejected_levels(current_price, symbol, tp_source)
            
            if sl_price is None:
                print(f"   ⚠️ RECHAZADO: sin SL válido")
                return self._build_rejected_levels(current_price, symbol, "Sin SL válido")
            
            # ============ CALCULAR R/R ============
            reward = abs(tp_price - entry)
            risk = abs(entry - sl_price)
            rr = reward / risk if risk > 0 else 0
            
            # POLÍTICA: Rechazar si R/R < 1:1.5
            if rr < 1.5:
                print(f"   ⚠️ RECHAZADO: R/R muy bajo ({rr:.2f} < 1.5)")
                return self._build_rejected_levels(
                    current_price, symbol, f"R/R desfavorable {rr:.2f} < 1.5"
                )
            
            # ============ AJUSTAR APALANCAMIENTO POR VOLATILIDAD ============
            if atr_pct > 0.05:  # > 5%
                leverage = max(1, int(leverage * 0.6))
            elif atr_pct > 0.03:  # > 3%
                leverage = max(1, int(leverage * 0.8))
            
            # ============ TAMAÑO SUGERIDO ============
            if tp_score >= 80 and sl_score >= 70:
                suggested_size = 1.0
            elif tp_score >= 60 and sl_score >= 60:
                suggested_size = 0.75
            else:
                suggested_size = 0.5
            
            # ============ CONSTRUIR RESPUESTA ============
            levels = {
                'entry': self._round_price(entry, symbol),
                'stop_loss': self._round_price(sl_price, symbol),
                'take_profit': self._round_price(tp_price, symbol),
                'leverage': int(leverage),
                'risk_reward': round(rr, 2),
                'suggested_size': round(suggested_size, 2),
                'tp_source': tp_source,
                'sl_source': sl_source,
                'tp_probability': round(tp_score / 100, 2),
                'sl_reliability': round(sl_score / 100, 2),
                'min_tp_distance_pct': self._calculate_min_tp_distance_pct(timeframe, leverage, is_futures),
                'rejected_reason': None
            }
            
            print(f"   ✅ TP: ${levels['take_profit']:.4f} ({tp_source}, score {tp_score:.0f})")
            print(f"   ✅ SL: ${levels['stop_loss']:.4f} ({sl_source}, score {sl_score:.0f})")
            print(f"   ✅ R/R: 1:{rr:.2f} | Leverage: {leverage}x | Size: {suggested_size*100:.0f}%")
            
            return levels
            
        except Exception as e:
            print(f"❌ Error en calculate_entry_levels (FASE 3): {e}")
            import traceback
            traceback.print_exc()
            return self._get_default_levels(current_price if 'current_price' in locals() else 0, symbol)
    
    def _build_rejected_levels(self, current_price, symbol, reason):
        """Construye una respuesta de niveles rechazados. La acción se degradará a NO_OPERAR."""
        return {
            'entry': self._round_price(current_price, symbol),
            'stop_loss': self._round_price(current_price * 0.97, symbol),
            'take_profit': self._round_price(current_price * 1.03, symbol),
            'leverage': 1,
            'risk_reward': 0,
            'suggested_size': 0,
            'tp_source': 'Rechazado',
            'sl_source': 'Rechazado',
            'tp_probability': 0,
            'sl_reliability': 0,
            'min_tp_distance_pct': 0,
            'rejected_reason': reason
        }
    
    def _round_price(self, price, symbol):
        """Redondear precio según el símbolo"""
        if price <= 0:
            return 0
        if symbol == 'PAXG-BTC':
            return round(price, 8)
        else:
            return round(price, 2)
    
    def _get_default_levels(self, current_price, symbol):
        """Niveles por defecto cuando falla el cálculo o no aplica trading (NO_OPERAR)"""
        if current_price == 0:
            current_price = 50000 if symbol == 'BTC-USDT' else 2000 if symbol == 'PAXG-USDT' else 0.04
        
        levels = {
            'entry': self._round_price(current_price, symbol),
            'stop_loss': self._round_price(current_price * 0.97, symbol),
            'take_profit': self._round_price(current_price * 1.03, symbol),
            'leverage': 1,
            'risk_reward': 0,
            'suggested_size': 0,
            'tp_source': 'N/A',
            'sl_source': 'N/A',
            'tp_probability': 0,
            'sl_reliability': 0,
            'min_tp_distance_pct': 0,
            'rejected_reason': None
        }
        return levels
    # === FIN calculate_entry_levels (FASE 3) ===
    
    # ========================================================================
    # GENERADOR DE MENSAJES CONCATENADOS (TRADER EXPERTO)
    # ========================================================================
    
    # === FUNCIÓN COMPLETA: generate_professional_message ===
    # Ubicación: Reemplazar entre línea ~1600 y línea ~1850 aproximadamente
    

    # ========================================================================
    # Mensaje con concenso
    # ========================================================================
    
    def generate_professional_message_with_consenso(self, symbol, timeframe, decision, confidence, levels, 
                                         trend, momentum, volatility, volume, structure,
                                         correlation, market_hours, confirmation, conviction,
                                         estrategias_consenso, razones_consenso, sentiment=None,
                                         liquidation=None):  # <--- NUEVO PARÁMETRO OPCIONAL
        """
        Genera mensaje concatenando MÚLTIPLES plantillas seleccionadas por condiciones.
        VERSIÓN MEJORADA CON SENTIMIENTO, MULTIFRAME, BOLLINGER, PERFIL VOLUMEN Y STOP HUNTS
        """
        
        # Limitar confianza a máximo 100%
        confidence = min(100, max(0, confidence))
        
        symbol_name = SYMBOLS.get(symbol, {'name': symbol})['name']
        timeframe_name = TIMEFRAMES.get(timeframe, {'name': timeframe})['name']
        
        # ============ SELECCIONAR MÚLTIPLES PLANTILLAS ============
        plantillas = self.seleccionar_plantillas_por_condiciones(
            decision, symbol, timeframe,
            trend, momentum, volatility, volume, structure,
            correlation, market_hours, confirmation,
            estrategias_consenso, sentiment,
            liquidation  # <--- NUEVO PARÁMETRO
        )
        
        # ============ EXTRACCIÓN MASIVA DE TODOS LOS INDICADORES ============
        
        # ---------- TREND (CAPA 1) ----------
        adx_valor = 0
        adx_tendencia = ''
        direccion_trend = 'neutral'
        plus_di = 0
        minus_di = 0
        ema9_valor = 0
        ema21_valor = 0
        ema50_valor = 0
        ema200_valor = 0
        ema9_prev = 0
        ema21_prev = 0
        supertrend_valor = 0
        supertrend_direccion = 'neutral'
        ichimoku_cloud = 'neutral'
        ichimoku_tk = 'neutral'
        ichimoku_espesor = 0
        cantidad_medias = 0
        velas_tendencia = 0
        tf_cruce = ''
        
        # Parabolic SAR
        psar_trend_val = 'neutral'
        psar_reversal = False
        
        if trend and isinstance(trend, dict):
            adx_valor = trend.get('adx', 0) or 0 #adx_value
            direccion_trend = trend.get('direction', 'neutral') or 'neutral'
            
            if adx_valor > 25:
                adx_tendencia = 'fuerte'
            elif adx_valor > 20:
                adx_tendencia = 'en desarrollo'
            else:
                adx_tendencia = 'débil'
            
            indicators = trend.get('indicators', {}) or {}
            ema9_valor = indicators.get('ema9', 0) or 0
            ema21_valor = indicators.get('ema21', 0) or 0
            ema50_valor = indicators.get('ema50', 0) or 0
            ema200_valor = indicators.get('ema200', 0) or 0
            ema9_prev = indicators.get('ema9_prev', 0) or 0
            ema21_prev = indicators.get('ema21_prev', 0) or 0
            supertrend_valor = indicators.get('supertrend', 0) or 0
            supertrend_direccion = indicators.get('supertrend_trend', 'neutral') or 'neutral'
            ichimoku_cloud = indicators.get('ichimoku_cloud', 'neutral') or 'neutral'
            ichimoku_tk = indicators.get('ichimoku_tk', 'neutral') or 'neutral'
            
            # Parabolic SAR
            psar_trend_val = indicators.get('parabolic_sar_trend', 'neutral') or 'neutral'
            
            # Detectar reversión de Parabolic SAR
            votes = trend.get('votes', [])
            for vote in votes:
                if vote.get('source') == 'psar_reversal_bull':
                    psar_reversal = True
                    print(f"   🔄 Parabolic SAR: Reversión alcista detectada")
                elif vote.get('source') == 'psar_reversal_bear':
                    psar_reversal = True
                    print(f"   🔄 Parabolic SAR: Reversión bajista detectada")
            
            # DMI separado
            plus_di = trend.get('plus_di', 0) or 0
            minus_di = trend.get('minus_di', 0) or 0
            
            # Contar medias alineadas
            if ema9_valor and ema21_valor and ema9_valor > ema21_valor:
                cantidad_medias += 1
            if ema21_valor and ema50_valor and ema21_valor > ema50_valor:
                cantidad_medias += 1
            if ema50_valor and ema200_valor and ema50_valor > ema200_valor:
                cantidad_medias += 1
            
            # Determinar timeframe para cruces
            tf_cruce = 'diaria' if timeframe == '1D' else 'intradía'
        
        # ---------- MOMENTUM (CAPA 2) ----------
        rsi_valor = 50
        rsi_estado = 'neutral'
        rsi_maverick_valor = 0.5
        rsi_maverick_estado = 'neutral'
        macd_valor = 0
        macd_signal = 0
        macd_histograma = 0
        macd_hist_pre = 0
        stoch_k = 50
        stoch_d = 50
        stoch_estado = 'neutral'
        williams_valor = -50
        williams_estado = 'neutral'
        cci_valor = 0
        cci_estado = 'neutral'
        squeeze_momentum = 0
        divergencias = []
        divergencias_ocultas = []
        divergence_details = []
        cantidad_osciladores = 0
        direccion_divergencia = ''
        interpretacion_divergencia = ''
        cantidad_divergencias = 0
        nombre_divergencia = ''
        oscilador_divergencia = ''
        
        # NUEVAS VARIABLES PARA MEJORES OSCILADORES
        mejor_oscilador = "osciladores"
        valor_oscilador = "neutral"
        mejor_avanzado = "indicadores avanzados"
        valor_avanzado = "neutral"
        
        if momentum and isinstance(momentum, dict):
            indicators = momentum.get('indicators', {}) or {}
            rsi_valor = indicators.get('rsi', 50) or 50
            rsi_maverick_valor = indicators.get('rsi_maverick', 0.5) or 0.5
            macd_histograma = indicators.get('macd_histogram', 0) or 0
            macd_hist_pre = indicators.get('macd_hist_pre', 0) or 0
            stoch_k = indicators.get('stoch_k', 50) or 50
            stoch_d = indicators.get('stoch_d', 50) or 50
            williams_valor = indicators.get('williams', -50) or -50
            cci_valor = indicators.get('cci', 0) or 0
            squeeze_momentum = indicators.get('squeeze_momentum', 0) or 0
            
            divergencias = momentum.get('divergences', []) or []
            divergencias_ocultas = momentum.get('hidden_divergences', []) or []
            divergence_details = momentum.get('divergence_details', []) or []
            cantidad_divergencias = len(divergencias) + len(divergencias_ocultas)
            
            # ============ USAR NUEVAS FUNCIONES AUXILIARES ============
            mejor_oscilador, valor_oscilador = self._obtener_mejor_oscilador(momentum)
            mejor_avanzado, valor_avanzado = self._obtener_mejor_avanzado(momentum)
            
            # Determinar qué oscilador muestra divergencia usando los detalles
            if divergence_details and len(divergence_details) > 0:
                primera_div = divergence_details[0]
                oscilador_divergencia = primera_div.get('oscillator', 'osciladores')
                nombre_divergencia = oscilador_divergencia
                print(f"   🔍 Divergencia detectada en: {oscilador_divergencia}")
            elif divergencias:
                div_str = str(divergencias).lower()
                if 'rsi' in div_str:
                    nombre_divergencia = 'RSI'
                elif 'macd' in div_str:
                    nombre_divergencia = 'MACD'
                elif 'estocastico' in div_str or 'stoch' in div_str:
                    nombre_divergencia = 'Estocástico'
                elif 'williams' in div_str:
                    nombre_divergencia = 'Williams %R'
                elif 'cci' in div_str:
                    nombre_divergencia = 'CCI'
                else:
                    nombre_divergencia = 'osciladores'
            elif divergencias_ocultas:
                div_str = str(divergencias_ocultas).lower()
                if 'rsi' in div_str:
                    nombre_divergencia = 'RSI'
                else:
                    nombre_divergencia = 'osciladores'
            
            # Estados RSI
            if rsi_valor > 70:
                rsi_estado = 'sobrecompra'
            elif rsi_valor < 30:
                rsi_estado = 'sobreventa'
            elif rsi_valor > 50:
                rsi_estado = 'alcista'
            else:
                rsi_estado = 'bajista'
            
            # Estados RSI Maverick
            if rsi_maverick_valor > 0.8:
                rsi_maverick_estado = 'sobrecompra'
            elif rsi_maverick_valor < 0.2:
                rsi_maverick_estado = 'sobreventa'
            
            # Estados Estocástico
            if stoch_k > 80 and stoch_d > 80:
                stoch_estado = 'sobrecompra'
            elif stoch_k < 20 and stoch_d < 20:
                stoch_estado = 'sobreventa'
            
            # Estados Williams
            if williams_valor > -20:
                williams_estado = 'sobrecompra'
            elif williams_valor < -80:
                williams_estado = 'sobreventa'
            
            # Estados CCI
            if cci_valor > 200:
                cci_estado = 'extremo alcista'
            elif cci_valor < -200:
                cci_estado = 'extremo bajista'
            elif cci_valor > 100:
                cci_estado = 'alcista'
            elif cci_valor < -100:
                cci_estado = 'bajista'
            
            # Contar osciladores en zona favorable
            if rsi_valor > 50:
                cantidad_osciladores += 1
            if macd_histograma > 0:
                cantidad_osciladores += 1
            if stoch_k > 50:
                cantidad_osciladores += 1
            if cci_valor > 0:
                cantidad_osciladores += 1
            
            # Interpretar divergencias
            if divergencias_ocultas:
                if 'bull' in str(divergencias_ocultas).lower():
                    direccion_divergencia = 'ALCISTA'
                    interpretacion_divergencia = 'fortaleza subyacente en la tendencia'
                elif 'bear' in str(divergencias_ocultas).lower():
                    direccion_divergencia = 'BAJISTA'
                    interpretacion_divergencia = 'debilidad subyacente en la tendencia'
        
        # ---------- VOLATILIDAD (CAPA 3) ----------
        atr_valor = 0
        atr_pct = 0
        volatility_level = 'medium'
        bb_width = 0
        bb_position = 0.5
        bb_upper = 0
        bb_lower = 0
        ftm_estado = 'NEUTRAL'
        ftm_descripcion = 'desconocido'
        ftm_strength = 0
        contraction_count = 0
        squeeze_on = False
        squeeze_length = 0
        operability = True
        suggested_leverage = 10
        direccion_squeeze = ''
        
        if volatility and isinstance(volatility, dict):
            atr_valor = volatility.get('atr', 0) or 0
            atr_pct = volatility.get('atr_pct', 0) or 0
            volatility_level = volatility.get('volatility_level', 'medium') or 'medium'
            bb_width = volatility.get('bb_width', 0) or 0
            bb_position = volatility.get('bb_position', 0.5) or 0.5
            bb_upper = volatility.get('bb_upper', 0) or 0
            bb_lower = volatility.get('bb_lower', 0) or 0
            ftm_estado = volatility.get('ftm_state', 'NEUTRAL') or 'NEUTRAL'
            ftm_descripcion = volatility.get('ftm_description', 'desconocido') or 'desconocido'
            ftm_strength = volatility.get('ftm_strength', 0) or 0
            contraction_count = volatility.get('contraction_count', 0) or 0
            squeeze_on = volatility.get('squeeze_on', False) or False
            squeeze_length = volatility.get('squeeze_length', 0) or 0
            operability = volatility.get('operability', True) or True
            suggested_leverage = volatility.get('suggested_leverage', 10) or 10
            
            if squeeze_momentum > 0:
                direccion_squeeze = 'ALCISTA'
            elif squeeze_momentum < 0:
                direccion_squeeze = 'BAJISTA'
        
        # ---------- VOLUMEN (CAPA 4) ----------
        volumen_relativo = 1.0
        volumen_participacion = 'normal'
        acumulacion_score = 0
        whale_buy = False
        whale_sell = False
        whale_buy_confirmed = False
        whale_sell_confirmed = False
        iceberg_buy = False
        iceberg_sell = False
        obv_trend = 'neutral'
        mfi_valor = 50
        mfi_estado = 'neutral'
        force_index_valor = 0
        force_index_estado = 'neutral'
        tipo_ballena = ''
        fuerza_ballena = 0
        velas_ballena = 2
        velas_consecutivas = 0
        
        # Variables específicas para NO OPERAR
        volumen_insuficiente = False
        volumen_critico = False
        
        if volume and isinstance(volume, dict):
            volumen_relativo = volume.get('volume_ratio', 1.0) or 1.0
            volumen_participacion = volume.get('volume_participation', 'normal') or 'normal'
            acumulacion_score = volume.get('accumulation_score', 0) or 0
            whale_buy = volume.get('whale_buy', False) or False
            whale_sell = volume.get('whale_sell', False) or False
            whale_buy_confirmed = volume.get('whale_buy_confirmed', False) or False
            whale_sell_confirmed = volume.get('whale_sell_confirmed', False) or False
            iceberg_buy = volume.get('iceberg_buy', False) or False
            iceberg_sell = volume.get('iceberg_sell', False) or False
            obv_trend = volume.get('obv_trend', 'neutral') or 'neutral'
            mfi_valor = volume.get('mfi', 50) or 50
            force_index_valor = volume.get('force_index', 0) or 0
            
            # Detectar volumen insuficiente
            if volumen_relativo < 0.7:
                volumen_insuficiente = True
            if volumen_relativo < 0.5:
                volumen_critico = True
            
            # Estados MFI
            if mfi_valor > 60:
                mfi_estado = 'compra'
            elif mfi_valor < 40:
                mfi_estado = 'venta'
            
            # Estados Force Index
            if force_index_valor > 0:
                force_index_estado = 'positivo'
            else:
                force_index_estado = 'negativo'
            
            if whale_buy_confirmed:
                tipo_ballena = 'CONFIRMADA'
                fuerza_ballena = volume.get('whale_signal_strength', 80) or 80
            elif whale_buy:
                tipo_ballena = 'EXTENDIDA'
                fuerza_ballena = volume.get('whale_signal_strength', 60) or 60
            
            if iceberg_buy or iceberg_sell:
                velas_consecutivas = 4
        
        # ---------- ESTRUCTURA (CAPA 5) ----------
        precio_actual = 0
        nearest_support = None
        nearest_resistance = None
        soportes = []
        resistencias = []
        fib_236 = 0
        fib_382 = 0
        fib_50 = 0
        fib_618 = 0
        fib_786 = 0
        fib_1272 = 0
        fib_1618 = 0
        fib_2618 = 0
        patrones_bullish = 0
        patrones_bearish = 0
        patrones_neutral = 0
        mejor_patron = ''
        confianza_patron = 0
        tipo_patron = ''
        toques = 3
        calidad_ruptura = 'fuerte'
        proyeccion = 0
        nivel1 = ''
        nivel2 = ''
        nombre_patron = ''
        
        # Perfil de volumen
        poc_price = 0
        vah_price = 0
        val_price = 0
        poc_volume_pct = 0
        price_position = 'unknown'
        funcion_valor = ''
        direccion_breakout = ''
        
        # NUEVAS VARIABLES PARA PERFIL VOLUMEN
        hvn_nodes = []
        lvn_nodes = []
        hvn_level = 0
        hvn_volume = 0
        lvn_level = 0
        hvn_price = None
        hvn_volume_ratio = None
        lvn_price = None
        
        if structure and isinstance(structure, dict):
            precio_actual = structure.get('current_price', 0) or 0
            nearest_support = structure.get('nearest_support')
            nearest_resistance = structure.get('nearest_resistance')
            soportes = structure.get('supports', []) or []
            resistencias = structure.get('resistances', []) or []
            
            patrones_bullish = structure.get('bullish_patterns_count', 0) or 0
            patrones_bearish = structure.get('bearish_patterns_count', 0) or 0
            
            patterns_data = structure.get('patterns', {}) or {}
            if patterns_data:
                patrones_neutral = patterns_data.get('neutral_count', 0) or 0
                patrones_recientes = patterns_data.get('recent_patterns', []) or []
                if patrones_recientes and len(patrones_recientes) > 0:
                    mejor = patrones_recientes[0]
                    if isinstance(mejor, dict):
                        mejor_patron = mejor.get('name', '') or ''
                        nombre_patron = mejor.get('name', '') or ''
                        confianza_patron = mejor.get('reliability', 0) or 0
                        tipo_patron = mejor.get('type', '1') or '1'
                        proyeccion = confianza_patron * 0.1
            
            fib = structure.get('fib_levels', {}) or {}
            fib_236 = fib.get('0.236', 0) or 0
            fib_382 = fib.get('0.382', 0) or 0
            fib_50 = fib.get('0.5', 0) or 0
            fib_618 = fib.get('0.618', 0) or 0
            fib_786 = fib.get('0.786', 0) or 0
            
            fib_ext = structure.get('fib_extensions', {}) or {}
            fib_1272 = fib_ext.get('1.272', 0) or 0
            fib_1618 = fib_ext.get('1.618', 0) or 0
            fib_2618 = fib_ext.get('2.618', 0) or 0
            
            nivel1 = f"${fib_618:.2f}" if fib_618 else ''
            nivel2 = f"${fib_382:.2f}" if fib_382 else ''
            
            # Perfil de volumen
            vp = structure.get('volume_profile', {}) or {}
            poc_price = vp.get('poc', 0) or 0
            vah_price = vp.get('vah', 0) or 0
            val_price = vp.get('val', 0) or 0
            poc_volume_pct = vp.get('poc_volume_pct', 0) or 0
            price_position = vp.get('price_position', 'unknown') or 'unknown'
            
            # NUEVOS: HVN y LVN
            hvn_nodes = vp.get('hvn_nodes', []) or []
            lvn_nodes = vp.get('lvn_nodes', []) or []
            
            # HVN más cercano
            if hvn_nodes and precio_actual > 0:
                closest_hvn = min(hvn_nodes, key=lambda x: abs(x.get('price', 0) - precio_actual))
                hvn_price = closest_hvn.get('price', 0)
                hvn_volume_ratio = closest_hvn.get('volume_ratio', 1.0)
                hvn_level = hvn_price
                hvn_volume = hvn_volume_ratio * 100
            
            # LVN más cercano
            if lvn_nodes and precio_actual > 0:
                closest_lvn = min(lvn_nodes, key=lambda x: abs(x.get('price', 0) - precio_actual))
                lvn_price = closest_lvn.get('price', 0)
                lvn_level = lvn_price
            
            if price_position == 'above_value_area':
                funcion_valor = 'resistencia'
                direccion_breakout = 'ALCISTA'
            elif price_position == 'below_value_area':
                funcion_valor = 'soporte'
                direccion_breakout = 'BAJISTA'
            else:
                funcion_valor = 'soporte y resistencia'
        
        # ---------- SMART MONEY ----------
        tipo_ob = ''
        nivel_order_block = 0
        volumen_ob = 0
        tipo_fvg = ''
        fvg_inferior = 0
        fvg_superior = 0
        funcion_fvg = ''
        tipo_sweep = ''
        nivel_sweep = 0
        interpretacion_sweep = ''
        tipo_hunt = ''
        
        # NUEVAS VARIABLES PARA STOP HUNTS
        stop_hunt_level = 0
        latest_hunt_level = None
        
        if structure and isinstance(structure, dict):
            order_blocks = structure.get('order_blocks', []) or []
            if order_blocks:
                ob = order_blocks[0]
                tipo_ob = 'ALCISTA' if ob.get('type') == 'bullish' else 'BAJISTA'
                price_range = ob.get('price_range', [0, 0])
                nivel_order_block = (price_range[0] + price_range[1]) / 2 if price_range else 0
                volumen_ob = volumen_relativo * 100
            
            fvg_list = structure.get('fair_value_gaps', []) or []
            if fvg_list:
                fvg = fvg_list[0]
                tipo_fvg = 'ALCISTA' if fvg.get('type') == 'bullish' else 'BAJISTA'
                fvg_inferior = fvg.get('gap_bottom', 0)
                fvg_superior = fvg.get('gap_top', 0)
                funcion_fvg = 'soporte' if fvg.get('type') == 'bullish' else 'resistencia'
            
            sweeps = structure.get('liquidity_sweeps', []) or []
            if sweeps:
                sweep = sweeps[0]
                tipo_sweep = 'ALCISTA' if sweep.get('type') == 'bullish' else 'BAJISTA'
                nivel_sweep = sweep.get('sweep_level', 0)
                interpretacion_sweep = 'acumulación institucional' if sweep.get('type') == 'bullish' else 'distribución institucional'
            
            hunts = structure.get('stop_hunts', []) or []
            if hunts:
                hunt = hunts[0]
                tipo_hunt = 'ALCISTA' if hunt.get('type') == 'bullish' else 'BAJISTA'
                stop_hunt_level = hunt.get('level', 0)
                latest_hunt_level = stop_hunt_level
        
        # ---------- CORRELACIÓN (CAPA 6) ----------
        rotation_signal = 'NEUTRAL'
        relative_strength = 'NEUTRAL'
        btc_action = 'N/A'
        ratio_action = 'N/A'
        btc_confianza = 0
        weight_modifier = 1.0
        
        if correlation and isinstance(correlation, dict):
            rotation_signal = correlation.get('rotation_signal', 'NEUTRAL') or 'NEUTRAL'
            relative_strength = correlation.get('relative_strength', 'NEUTRAL') or 'NEUTRAL'
            weight_modifier = correlation.get('weight_modifier', 1.0) or 1.0
            
            btc_analysis = correlation.get('btc_analysis', {}) or {}
            if btc_analysis:
                btc_action = btc_analysis.get('decision', {}).get('action', 'N/A') or 'N/A'
                btc_confianza = btc_analysis.get('decision', {}).get('confidence', 0) or 0
            
            paxg_btc_analysis = correlation.get('paxg_btc_analysis', {}) or {}
            if paxg_btc_analysis:
                ratio_action = paxg_btc_analysis.get('decision', {}).get('action', 'N/A') or 'N/A'
        
        # ---------- HORARIOS (CAPA 7) ----------
        session_name = 'Desconocido'
        session_icon = '⏰'
        liquidity = 'desconocida'
        day_name = 'Desconocido'
        day_icon = '📅'
        session_weight = 1.0
        day_weight = 1.0
        total_weight = 1.0
        tfs = ''
        tf_rapida = ''
        tf_lenta = ''
        tf_principal = ''
        direccion_rapida = ''
        direccion_lenta = ''
        direccion_principal = ''
        
        if market_hours and isinstance(market_hours, dict):
            session_name = market_hours.get('session_name', 'Desconocido') or 'Desconocido'
            session_icon = market_hours.get('session_icon', '⏰') or '⏰'
            liquidity = market_hours.get('liquidity', 'desconocida') or 'desconocida'
            day_name = market_hours.get('day_name', 'Desconocido') or 'Desconocido'
            day_icon = market_hours.get('day_icon', '📅') or '📅'
            session_weight = market_hours.get('session_weight', 1.0) or 1.0
            day_weight = market_hours.get('day_weight', 1.0) or 1.0
            total_weight = market_hours.get('total_weight', 1.0) or 1.0
        
        # ---------- MULTIFRAME ----------
        # Determinar las temporalidades según el timeframe actual
        if timeframe == '1W':
            tfs = '1D, 12H, 4H'
            tf_superior = '1W'
            tf_actual = timeframe_name
            tf_inferior = '1D'
            direccion_superior = direccion_trend.upper()
            direccion_actual = direccion_trend.upper()
            direccion_inferior = 'NEUTRAL'  # Se actualizará si hay datos
            
            # Intentar obtener dirección de 1D de la estructura
            if structure and isinstance(structure, dict):
                # Aquí podrías obtener la dirección real de 1D si está disponible
                pass
                
        elif timeframe == '1D':
            tfs = '1W, 12H, 4H'
            tf_superior = '1W'
            tf_actual = timeframe_name
            tf_inferior = '12H'
            direccion_superior = 'NEUTRAL'
            direccion_actual = direccion_trend.upper()
            direccion_inferior = 'NEUTRAL'
            
        elif timeframe == '12h':
            tfs = '1D, 4H'
            tf_superior = '1D'
            tf_actual = timeframe_name
            tf_inferior = '4H'
            direccion_superior = 'NEUTRAL'
            direccion_actual = direccion_trend.upper()
            direccion_inferior = 'NEUTRAL'
            
        else:  # 4h
            tfs = '12H, 1D'
            tf_superior = '12H'
            tf_actual = timeframe_name
            tf_inferior = 'N/A'
            direccion_superior = 'NEUTRAL'
            direccion_actual = direccion_trend.upper()
            direccion_inferior = 'N/A'
        
        # ---------- CONFIRMACIÓN (CAPA 8) ----------
        confirmation_status = 'UNKNOWN'
        confirmation_reason = 'sin datos'
        wait_bars = 0
        breakout_level = 0
        alternative_signal = 'NINGUNA'
        
        if confirmation and isinstance(confirmation, dict):
            confirmation_status = confirmation.get('confirmation_status', 'UNKNOWN') or 'UNKNOWN'
            confirmation_reason = ', '.join(confirmation.get('reason', ['sin datos'])) or 'sin datos'
            wait_bars = confirmation.get('wait_bars', 0) or 0
            breakout_level = confirmation.get('breakout_level', 0) or 0
            alternative_signal = confirmation.get('alternative_signal', 'NINGUNA') or 'NINGUNA'
        
        # ---------- CONVICCIÓN ----------
        conviction_level = 'MEDIA'
        conviction_icon = '🟡'
        suggested_size = 1.0
        bonus_reasons = []
        degradation_reasons = []
        
        if conviction and isinstance(conviction, dict):
            conviction_level = conviction.get('level', 'MEDIA') or 'MEDIA'
            conviction_icon = conviction.get('icon', '🟡') or '🟡'
            suggested_size = conviction.get('suggested_size', 1.0) or 1.0
            bonus_reasons = conviction.get('bonus_reasons', []) or []
            degradation_reasons = conviction.get('degradation_reasons', []) or []
        
        # ---------- SENTIMIENTO (NUEVA CAPA 9) ----------
        fear_greed_value = 50
        fear_greed_classification = 'Neutral'
        fear_greed_trend_7d = '0.0'
        fear_greed_trend_30d = '0.0'
        fear_greed_volatility = '0.0'
        sentiment_bias = 'neutral'
        sentiment_description = 'Sin datos de sentimiento'
        
        if sentiment and isinstance(sentiment, dict):
            fear_greed_value = str(sentiment.get('current_value', 50))
            fear_greed_classification = str(sentiment.get('classification', 'Neutral'))
            fear_greed_trend_7d = f"{sentiment.get('trend_7d_pct', 0):+.1f}"
            fear_greed_trend_30d = f"{sentiment.get('trend_30d_pct', 0):+.1f}"
            fear_greed_volatility = f"{sentiment.get('volatility', 0):.1f}"
            sentiment_bias = str(sentiment.get('sentiment_bias', 'neutral'))
            
            # Texto descriptivo según el sesgo
            bias = sentiment.get('sentiment_bias', 'neutral')
            if bias == 'bullish_opportunity':
                sentiment_description = "Miedo extremo remontando, oportunidad de compra"
            elif bias == 'bearish_opportunity':
                sentiment_description = "Avaricia extrema cayendo, oportunidad de venta"
            elif bias == 'bullish_moderate':
                sentiment_description = "Miedo moderado mejorando, acumulación"
            elif bias == 'bearish_moderate':
                sentiment_description = "Avaricia moderada empeorando, tomar ganancias"
            elif bias == 'bullish_caution':
                sentiment_description = "Avaricia extrema continuando, cautela"
            elif bias == 'bearish_caution':
                sentiment_description = "Miedo extremo continuando, cautela"
            else:
                sentiment_description = "Sentimiento neutral"
        
        # Niveles de entrada
        entry_price = levels.get('entry', precio_actual)
        stop_loss = levels.get('stop_loss', precio_actual * 0.97 if precio_actual > 0 else 0)
        take_profit = levels.get('take_profit', precio_actual * 1.06 if precio_actual > 0 else 0)
        risk_reward = levels.get('risk_reward', 2.0)
        leverage = levels.get('leverage', 1)
        
        # Formatear precios según símbolo
        if symbol == 'PAXG-BTC':
            precio_actual_str = f"{precio_actual:.6f}"
            entry_price_str = f"{entry_price:.6f}"
            stop_loss_str = f"{stop_loss:.6f}"
            take_profit_str = f"{take_profit:.6f}"
        else:
            precio_actual_str = f"${precio_actual:.2f}"
            entry_price_str = f"${entry_price:.2f}"
            stop_loss_str = f"${stop_loss:.2f}"
            take_profit_str = f"${take_profit:.2f}"
        
        # Calcular valor_fuerza
        valor_fuerza = max(adx_valor, ftm_strength)
        
        # ============ FUNCIÓN AUXILIAR PARA INDICADOR DE FUERZA ============
        def _obtener_indicador_fuerza(adx, ftm, plus, minus, decision):
            # Verificar si ADX es coherente con la decisión
            direccion_dmi = 'neutral'
            if plus > minus:
                direccion_dmi = 'bullish'
            elif minus > plus:
                direccion_dmi = 'bearish'
            
            # Solo usar ADX si la dirección coincide con la decisión
            usar_adx = False
            if decision in ['COMPRA_SPOT', 'LONG'] and direccion_dmi == 'bullish':
                usar_adx = True
            elif decision in ['VENTA_SPOT', 'SHORT'] and direccion_dmi == 'bearish':
                usar_adx = True
            
            if usar_adx and adx > 25:
                return 'ADX'
            elif ftm > 20:
                return 'FTMaverick'
            elif adx > 20 and usar_adx:
                return 'ADX'
            else:
                return 'sistema de fuerza'
        
        indicador_fuerza = _obtener_indicador_fuerza(adx_valor, ftm_strength, plus_di, minus_di, decision)
        
        # Determinar si hay cambio de tendencia
        cambio_tendencia = 'sí' if psar_reversal else 'no'
        
        # ============ CONSTRUIR DICCIONARIO DE REEMPLAZOS COMPLETO ============
        replace_dict = {
            # ---------- ACCIÓN Y SÍMBOLO ----------
            '{accion}': decision.replace('_', ' '),
            '{par}': symbol_name,
            '{temporalidad}': timeframe_name,
            '{precio_entrada}': entry_price_str,
            '{stop_loss}': stop_loss_str,
            '{take_profit}': take_profit_str,
            '{apalancamiento}': str(leverage),
            '{risk_reward}': str(risk_reward),
            '{confianza}': str(int(confidence)),
            '{tamano_sugerido}': str(int(suggested_size * 100)) + '%',
            '{timestamp}': datetime.now(self.bolivia_tz).strftime('%Y-%m-%d %H:%M:%S'),
            '{decision}': decision.replace('_', ' '),
            
            # ---------- FUERZA DE TENDENCIA ----------
            '{adx_valor}': str(round(adx_valor, 1)),
            '{adx_tendencia}': adx_tendencia,
            '{ftm_fuerza}': str(round(ftm_strength, 1)),
            '{ftm_strength}': str(round(ftm_strength, 1)),
            '{valor_fuerza}': str(round(valor_fuerza, 1)) if valor_fuerza > 0 else 'considerable',
            '{indicador_fuerza}': indicador_fuerza,
            
            # ---------- DIRECCIÓN DE TENDENCIA ----------
            '{direccion_tendencia}': direccion_trend.upper(),
            '{plus_di}': str(round(plus_di, 1)),
            '{minus_di}': str(round(minus_di, 1)),
            '{ema9}': f"${ema9_valor:.2f}" if ema9_valor else 'N/A',
            '{ema21}': f"${ema21_valor:.2f}" if ema21_valor else 'N/A',
            '{ema50}': f"${ema50_valor:.2f}" if ema50_valor else 'N/A',
            '{ema200}': f"${ema200_valor:.2f}" if ema200_valor else 'N/A',
            '{supertrend}': supertrend_direccion.upper(),
            '{supertrend_direccion}': supertrend_direccion.upper(),
            '{ichimoku_cloud}': ichimoku_cloud.upper(),
            '{ichimoku_tk}': ichimoku_tk.upper(),
            '{cantidad_medias}': str(cantidad_medias),
            '{velas_tendencia}': str(velas_tendencia),
            '{tf_cruce}': tf_cruce,
            '{indicadores_tendencia}': f"EMA, SuperTrend, Ichimoku",
            
            # ---------- PARABOLIC SAR ----------
            '{parabolic_sar_trend}': psar_trend_val,
            '{cambio_tendencia}': cambio_tendencia,
            
            # ---------- MOMENTUM CLÁSICO ----------
            '{rsi_valor}': str(round(rsi_valor, 1)),
            '{rsi_estado}': rsi_estado,
            '{stoch_k}': str(round(stoch_k, 1)),
            '{stoch_d}': str(round(stoch_d, 1)),
            '{stoch_estado}': stoch_estado,
            
            # ---------- NUEVAS VARIABLES DE OSCILADORES ----------
            '{mejor_oscilador}': mejor_oscilador,
            '{valor_oscilador}': valor_oscilador,
            '{mejor_avanzado}': mejor_avanzado,
            '{valor_avanzado}': valor_avanzado,
            
            # ---------- MOMENTUM AVANZADO ----------
            '{rsi_maverick_valor}': str(round(rsi_maverick_valor, 2)),
            '{rsi_maverick_estado}': rsi_maverick_estado,
            '{macd_histograma}': str(round(macd_histograma, 2)),
            '{macd_hist_pre}': str(round(macd_hist_pre, 2)),
            '{williams}': str(round(williams_valor, 1)),
            '{williams_estado}': williams_estado,
            '{cci}': str(round(cci_valor, 1)),
            '{cci_estado}': cci_estado,
            '{squeeze_momentum}': str(round(squeeze_momentum, 2)),
            '{cantidad_osciladores}': str(cantidad_osciladores),
            '{direccion_squeeze}': direccion_squeeze,
            '{nombre_divergencia}': nombre_divergencia or 'osciladores',
            '{oscilador_divergencia}': oscilador_divergencia or nombre_divergencia or 'osciladores',
            
            # ---------- FLUJO DE DINERO ----------
            '{mfi}': str(round(mfi_valor, 1)),
            '{mfi_estado}': mfi_estado,
            '{force_index}': str(round(force_index_valor, 1)),
            '{force_index_estado}': force_index_estado,
            '{obv_trend}': obv_trend.upper(),
            
            # ---------- VOLUMEN Y BALLENAS ----------
            '{volumen_relativo}': str(round(volumen_relativo, 1)),
            '{volumen_participacion}': volumen_participacion.upper(),
            '{acumulacion_score}': str(round(acumulacion_score, 1)),
            '{tipo_ballena}': tipo_ballena,
            '{fuerza_ballena}': str(round(fuerza_ballena, 0)),
            '{velas_ballena}': str(velas_ballena),
            '{velas_consecutivas}': str(velas_consecutivas),
            
            # ---------- VARIABLES ESPECÍFICAS PARA NO OPERAR ----------
            '{volumen_insuficiente}': 'sí' if volumen_insuficiente else 'no',
            '{volumen_critico}': 'sí' if volumen_critico else 'no',
            
            # ---------- ESTRUCTURA DE PRECIO ----------
            '{precio_actual}': precio_actual_str,
            '{nivel_soporte}': f"${nearest_support:.2f}" if nearest_support else 'N/A',
            '{nivel_resistencia}': f"${nearest_resistance:.2f}" if nearest_resistance else 'N/A',
            '{soportes}': ', '.join([f"${s:.2f}" for s in soportes[:3]]) if soportes else 'N/A',
            '{resistencias}': ', '.join([f"${r:.2f}" for r in resistencias[:3]]) if resistencias else 'N/A',
            '{toques}': str(toques),
            '{calidad_ruptura}': calidad_ruptura,
            
            # ---------- PATRONES DE VELAS ----------
            '{mejor_patron}': mejor_patron,
            '{nombre_patron}': nombre_patron,
            '{confianza_patron}': str(round(confianza_patron, 0)),
            '{tipo_patron}': tipo_patron,
            '{proyeccion}': str(round(proyeccion, 1)),
            '{patrones_bullish}': str(patrones_bullish),
            '{patrones_bearish}': str(patrones_bearish),
            
            # ---------- SMART MONEY ----------
            '{tipo_ob}': tipo_ob,
            '{nivel_order_block}': f"${nivel_order_block:.2f}" if nivel_order_block else 'N/A',
            '{volumen_ob}': str(round(volumen_ob, 0)),
            '{tipo_fvg}': tipo_fvg,
            '{fvg_inferior}': f"${fvg_inferior:.2f}" if fvg_inferior else 'N/A',
            '{fvg_superior}': f"${fvg_superior:.2f}" if fvg_superior else 'N/A',
            '{funcion_fvg}': funcion_fvg,
            '{tipo_sweep}': tipo_sweep,
            '{nivel_sweep}': f"${nivel_sweep:.2f}" if nivel_sweep else 'N/A',
            '{interpretacion_sweep}': interpretacion_sweep,
            '{tipo_hunt}': tipo_hunt,
            
            # ---------- PERFIL DE VOLUMEN ----------
            '{poc_price}': f"${poc_price:.2f}" if poc_price else 'N/A',
            '{vah_price}': f"${vah_price:.2f}" if vah_price else 'N/A',
            '{val_price}': f"${val_price:.2f}" if val_price else 'N/A',
            '{poc_volume_pct}': str(round(poc_volume_pct, 0)),
            '{price_position}': price_position.replace('_', ' ').upper(),
            '{funcion_valor}': funcion_valor,
            '{direccion_breakout}': direccion_breakout,
            
            # ---------- NUEVAS VARIABLES HVN/LVN ----------
            '{hvn_level}': f"${hvn_price:.2f}" if hvn_price else 'N/A',
            '{hvn_volume}': str(int(hvn_volume_ratio * 100)) if hvn_volume_ratio else '0',
            '{lvn_level}': f"${lvn_price:.2f}" if lvn_price else 'N/A',
            
            # ---------- FIBONACCI ----------
            '{fib_236}': f"${fib_236:.2f}" if fib_236 else 'N/A',
            '{fib_382}': f"${fib_382:.2f}" if fib_382 else 'N/A',
            '{fib_50}': f"${fib_50:.2f}" if fib_50 else 'N/A',
            '{fib_618}': f"${fib_618:.2f}" if fib_618 else 'N/A',
            '{fib_786}': f"${fib_786:.2f}" if fib_786 else 'N/A',
            '{fib_1272}': f"${fib_1272:.2f}" if fib_1272 else 'N/A',
            '{fib_1618}': f"${fib_1618:.2f}" if fib_1618 else 'N/A',
            '{fib_2618}': f"${fib_2618:.2f}" if fib_2618 else 'N/A',
            '{nivel_fibonacci}': f"{fib_618:.2f}" if fib_618 else 'N/A',
            '{nivel1}': nivel1,
            '{nivel2}': nivel2,
            
            # ---------- DMI ----------
            '{dmi_alcista}': 'sí' if plus_di > minus_di else 'no',
            '{dmi_bajista}': 'sí' if minus_di > plus_di else 'no',
            
            # ---------- VOLATILIDAD ----------
            '{atr_pct}': str(round(atr_pct, 1)),
            '{volatility_level}': volatility_level.upper(),
            '{bb_width}': str(round(bb_width, 1)),
            '{bb_position}': str(round(bb_position, 2)),
            '{bb_upper}': f"${bb_upper:.2f}" if bb_upper else 'N/A',
            '{bb_lower}': f"${bb_lower:.2f}" if bb_lower else 'N/A',
            
            # ---------- NUEVAS VARIABLES DE BOLLINGER ----------
            '{squeeze_length}': str(volatility.get('squeeze_length', 0)),
            
            # ---------- DIVERGENCIAS ----------
            '{direccion_divergencia}': direccion_divergencia,
            '{interpretacion_divergencia}': interpretacion_divergencia,
            '{cantidad_divergencias}': str(cantidad_divergencias),
            
            # ---------- MULTIFRAME ----------

            '{tfs}': tfs,
            '{tf_superior}': tf_superior,
            '{tf_actual}': tf_actual,
            '{tf_inferior}': tf_inferior,
            '{direccion_superior}': direccion_superior,
            '{direccion_actual}': direccion_actual,
            '{direccion_inferior}': direccion_inferior,
            
            # ---------- SESIONES ----------
            '{session_name}': session_name,
            '{liquidity}': liquidity,
            '{day_name}': day_name,
            
            # ---------- CONFIRMACIÓN ----------
            '{confirmation_status}': confirmation_status,
            '{confirmation_reason}': confirmation_reason,
            '{wait_bars}': str(wait_bars),
            '{breakout_level}': f"${breakout_level:.2f}" if breakout_level > 0 else 'N/A',
            '{alternative_signal}': alternative_signal,
            
            # ---------- RIESGO ----------
            '{ftm_estado}': ftm_estado,
            '{ftm_descripcion}': ftm_descripcion,
            '{contraction_count}': str(contraction_count),
            '{squeeze_length}': str(squeeze_length),
            '{eventos}': 'datos macro, noticias',
            
            # ---------- PRECAUCIÓN ----------
            '{precaucion_motivo}': 'condiciones de mercado',
            
            # ---------- ACTIVO ----------
            '{comportamiento}': 'consistente' if direccion_trend != 'neutral' else 'lateral',
            
            # ---------- REFLEXIÓN ----------
            '{reflexion}': 'análisis integral',
            
            # ---------- NUEVAS VARIABLES DE SENTIMIENTO ----------
            '{fear_greed_value}': fear_greed_value,
            '{fear_greed_classification}': fear_greed_classification,
            '{fear_greed_trend_7d}': fear_greed_trend_7d,
            '{fear_greed_trend_30d}': fear_greed_trend_30d,
            '{fear_greed_volatility}': fear_greed_volatility,
            '{sentiment_bias}': sentiment_bias,
            '{sentiment_description}': sentiment_description,
            
            # ---------- NUEVAS VARIABLES PARA STOP HUNTS ----------
            '{stop_hunt_level}': f"${latest_hunt_level:.2f}" if latest_hunt_level else 'N/A',
            
            # ---------- OTROS ----------
            '{riesgo_recompensa}': f"1:{risk_reward}",
            '{num_indicadores}': '30+',
            '{velas_restantes}': '5',
            '{cantidad_tf}': '2',
            '': '',
        }
        
        # ============ AÑADIR VARIABLES DE SENTIMIENTO SI EXISTEN ============
        if sentiment and isinstance(sentiment, dict):
            bias = sentiment.get('sentiment_bias', 'neutral')
            if bias == 'bullish_opportunity':
                replace_dict['{sentiment_description}'] = "Miedo extremo remontando, oportunidad de compra"
            elif bias == 'bearish_opportunity':
                replace_dict['{sentiment_description}'] = "Avaricia extrema cayendo, oportunidad de venta"
            elif bias == 'bullish_moderate':
                replace_dict['{sentiment_description}'] = "Miedo moderado mejorando, acumulación"
            elif bias == 'bearish_moderate':
                replace_dict['{sentiment_description}'] = "Avaricia moderada empeorando, tomar ganancias"
            elif bias == 'bullish_caution':
                replace_dict['{sentiment_description}'] = "Avaricia extrema continuando, cautela"
            elif bias == 'bearish_caution':
                replace_dict['{sentiment_description}'] = "Miedo extremo continuando, cautela"
            else:
                replace_dict['{sentiment_description}'] = "Sentimiento neutral"
        
        # ============ AÑADIR VARIABLES DE STOP HUNTS ============
        stop_hunts = structure.get('stop_hunts', [])
        latest_hunt_level = None
        if stop_hunts:
            latest_hunt = stop_hunts[-1]
            latest_hunt_level = latest_hunt.get('level', 0)
            replace_dict['{stop_hunt_level}'] = f"${latest_hunt_level:.2f}"
        
        # ============ AÑADIR VARIABLES DE HVN/LVN ============
        vp = structure.get('volume_profile', {})
        closest_hvn = vp.get('closest_hvn')
        closest_lvn = vp.get('closest_lvn')
        
        if closest_hvn:
            hvn_price_val = closest_hvn.get('price', 0)
            hvn_volume_ratio_val = closest_hvn.get('volume_ratio', 1.0)
            replace_dict['{hvn_level}'] = f"${hvn_price_val:.2f}" if hvn_price_val else 'N/A'
            replace_dict['{hvn_volume}'] = str(int(hvn_volume_ratio_val * 100))
        
        if closest_lvn:
            lvn_price_val = closest_lvn.get('price', 0)
            replace_dict['{lvn_level}'] = f"${lvn_price_val:.2f}" if lvn_price_val else 'N/A'
        
        # ============ AÑADIR VARIABLES DE BOLLINGER ============
        replace_dict['{squeeze_length}'] = str(volatility.get('squeeze_length', 0))
        replace_dict['{bb_width}'] = f"{volatility.get('bb_width', 0):.1f}"
        
        # ============ CONCATENAR PLANTILLAS ============
        mensaje_completo = ""
        for plantilla in plantillas:
            template_text = plantilla['template']
            mensaje_parcial = template_text
            
            # Aplicar reemplazos
            for key, value in replace_dict.items():
                if key and isinstance(value, str):
                    mensaje_parcial = mensaje_parcial.replace(key, value)
            
            mensaje_completo += mensaje_parcial
        
        # ============ LIMPIEZA FINAL ============
        import re
        mensaje_completo = re.sub(r'\{[^}]+\}', '', mensaje_completo)
        mensaje_completo = re.sub(r'\s+', ' ', mensaje_completo)
        mensaje_completo = mensaje_completo.replace(' .', '.').replace(' ,', ',')
        mensaje_completo = mensaje_completo.replace('  ', ' ').strip()
        
        # Eliminar espacios antes de puntuación
        mensaje_completo = re.sub(r'\s+\.', '.', mensaje_completo)
        mensaje_completo = re.sub(r'\s+,', ',', mensaje_completo)
        
        return mensaje_completo
                                         
    def _get_sentiment_description(self, sentiment):
        """Obtener descripción textual del sentimiento"""
        if not sentiment or not isinstance(sentiment, dict):
            return "Sin datos de sentimiento"
        
        bias = sentiment.get('sentiment_bias', 'neutral')
        
        if bias == 'bullish_opportunity':
            return "Miedo extremo remontando, oportunidad de compra"
        elif bias == 'bearish_opportunity':
            return "Avaricia extrema cayendo, oportunidad de venta"
        elif bias == 'bullish_moderate':
            return "Miedo moderado mejorando, acumulación"
        elif bias == 'bearish_moderate':
            return "Avaricia moderada empeorando, tomar ganancias"
        elif bias == 'bullish_caution':
            return "Avaricia extrema continuando, cautela"
        elif bias == 'bearish_caution':
            return "Miedo extremo continuando, cautela"
        else:
            return "Sentimiento neutral"
    
    
    def _obtener_conflicto(self, trend, momentum, numero):
        """Obtener descripción de conflicto entre indicadores"""
        try:
            if not trend or not momentum:
                return "indicadores sin definir"
            
            adx = trend.get('adx', 0) # adx_value
            direccion = trend.get('direction', 'neutral')
            rsi = momentum.get('indicators', {}).get('rsi', 50)
            
            if numero == 1:
                if adx < 20:
                    return "ADX bajo (sin tendencia)"
                elif adx > 40:
                    return f"ADX muy alto ({adx:.1f})"
                elif direccion == 'bullish':
                    return "tendencia alcista"
                elif direccion == 'bearish':
                    return "tendencia bajista"
                else:
                    return "tendencia lateral"
            else:
                if rsi > 70:
                    return f"RSI sobrecomprado ({rsi:.1f})"
                elif rsi < 30:
                    return f"RSI sobrevendido ({rsi:.1f})"
                elif rsi > 50:
                    return "RSI alcista"
                elif rsi < 50:
                    return "RSI bajista"
                else:
                    return "RSI neutral"
        except Exception as e:
            print(f"Error en _obtener_conflicto: {e}")
            return "indicador técnico"
    
    def _obtener_indicador_fuerza(self, adx_valor, ftm_strength, plus_di, minus_di, decision):
        """
        Determina qué indicador de fuerza usar basado en los valores
        AHORA CONSIDERA LA DIRECCIÓN DEL DMI
        """
        try:
            # Verificar si ADX es relevante para la dirección
            direccion_dmi = 'neutral'
            if plus_di > minus_di:
                direccion_dmi = 'bullish'
            elif minus_di > plus_di:
                direccion_dmi = 'bearish'
            
            # Solo usar ADX si la dirección coincide con la decisión
            usar_adx = False
            if decision in ['COMPRA_SPOT', 'LONG'] and direccion_dmi == 'bullish':
                usar_adx = True
            elif decision in ['VENTA_SPOT', 'SHORT'] and direccion_dmi == 'bearish':
                usar_adx = True
            
            if usar_adx and adx_valor > 25:
                return 'ADX'
            elif ftm_strength > 20:
                # Verificar dirección de FTM (esto requeriría más datos)
                return 'FTMaverick'
            elif adx_valor > 20 and usar_adx:
                return 'ADX'
            else:
                return 'sistema de fuerza'
        except Exception as e:
            print(f"Error en _obtener_indicador_fuerza: {e}")
            return 'indicador de fuerza'

    def _obtener_mejor_oscilador(self, momentum, decision=None):
        """
        Determina el mejor oscilador para mencionar en el mensaje
        VERSIÓN MEJORADA - Incluye más osciladores y contexto
        """
        try:
            if not momentum:
                return "osciladores", "neutral"
            
            indicators = momentum.get('indicators', {})
            rsi = indicators.get('rsi', 50)
            stoch_k = indicators.get('stoch_k', 50)
            stoch_d = indicators.get('stoch_d', 50)
            williams = indicators.get('williams', -50)
            cci = indicators.get('cci', 0)
            rsi_maverick = indicators.get('rsi_maverick', 0.5)
            
            # Verificar divergencias primero (son las señales más fuertes)
            divergence_details = momentum.get('divergence_details', [])
            if divergence_details and len(divergence_details) > 0:
                primera_div = divergence_details[0]
                oscilador = primera_div.get('oscillator', '')
                if oscilador:
                    if oscilador == 'RSI':
                        return "RSI", str(round(rsi, 1))
                    elif oscilador == 'MACD':
                        return "MACD", str(round(indicators.get('macd_histogram', 0), 2))
                    elif 'Estocástico' in oscilador:
                        return "Estocástico", str(round(stoch_k, 1))
                    elif 'Williams' in oscilador:
                        return "Williams %R", str(round(williams, 1))
            
            # Priorizar condiciones extremas
            if rsi > 70:
                return "RSI", str(round(rsi, 1))
            elif rsi < 30:
                return "RSI", str(round(rsi, 1))
            elif stoch_k > 80:
                return "Estocástico", str(round(stoch_k, 1))
            elif stoch_k < 20:
                return "Estocástico", str(round(stoch_k, 1))
            elif williams > -20:
                return "Williams %R", str(round(williams, 1))
            elif williams < -80:
                return "Williams %R", str(round(williams, 1))
            elif cci > 200:
                return "CCI", str(round(cci, 1))
            elif cci < -200:
                return "CCI", str(round(cci, 1))
            elif rsi_maverick > 0.8:
                return "RSI Maverick", str(round(rsi_maverick, 2))
            elif rsi_maverick < 0.2:
                return "RSI Maverick", str(round(rsi_maverick, 2))
            
            # Si no hay extremos, priorizar según la tendencia
            if decision in ['COMPRA_SPOT', 'LONG']:
                if rsi > 50:
                    return "RSI", str(round(rsi, 1))
                elif stoch_k > 50:
                    return "Estocástico", str(round(stoch_k, 1))
            elif decision in ['VENTA_SPOT', 'SHORT']:
                if rsi < 50:
                    return "RSI", str(round(rsi, 1))
                elif stoch_k < 50:
                    return "Estocástico", str(round(stoch_k, 1))
            
            # Fallback a RSI
            return "RSI", str(round(rsi, 1))
            
        except Exception as e:
            print(f"Error en _obtener_mejor_oscilador: {e}")
            return "osciladores", "neutral"
    
    def _obtener_mejor_avanzado(self, momentum, decision=None):
        """
        Determina el mejor oscilador avanzado
        VERSIÓN MEJORADA - Incluye más indicadores y contexto
        """
        try:
            if not momentum:
                return "indicadores avanzados", "neutral"
            
            indicators = momentum.get('indicators', {})
            macd = indicators.get('macd_histogram', 0)
            cci = indicators.get('cci', 0)
            williams = indicators.get('williams', -50)
            squeeze = indicators.get('squeeze_momentum', 0)
            
            # Verificar divergencias primero
            divergence_details = momentum.get('divergence_details', [])
            for div in divergence_details:
                oscilador = div.get('oscillator', '')
                if oscilador == 'MACD':
                    return "MACD", str(round(macd, 2))
                elif oscilador == 'CCI':
                    return "CCI", str(round(cci, 1))
            
            # Priorizar señales fuertes
            if abs(macd) > 1.0:
                return "MACD", str(round(macd, 2))
            elif abs(cci) > 200:
                return "CCI", str(round(cci, 1))
            elif abs(squeeze) > 0.5:
                return "Squeeze Momentum", str(round(squeeze, 2))
            elif williams > -20 or williams < -80:
                return "Williams %R", str(round(williams, 1))
            elif abs(macd) > 0.3:
                return "MACD", str(round(macd, 2))
            elif abs(cci) > 100:
                return "CCI", str(round(cci, 1))
            
            # Según la decisión
            if decision in ['COMPRA_SPOT', 'LONG']:
                if macd > 0:
                    return "MACD", str(round(macd, 2))
                elif cci > 0:
                    return "CCI", str(round(cci, 1))
            elif decision in ['VENTA_SPOT', 'SHORT']:
                if macd < 0:
                    return "MACD", str(round(macd, 2))
                elif cci < 0:
                    return "CCI", str(round(cci, 1))
            
            return "osciladores avanzados", "neutral"
            
        except Exception as e:
            print(f"Error en _obtener_mejor_avanzado: {e}")
            return "indicadores avanzados", "neutral"
      




    
    # ========================================================================
    # ANÁLISIS COMPLETO DE MERCADO
    # ========================================================================
    
    # === FUNCIÓN COMPLETA: analyze_full_market ===
    # Ubicación: Reemplazar entre línea ~1850 y línea ~1900 aproximadamente
    # CORRECCIÓN: Pasar parámetro indicators a analyze_trend_layer
    
        # === CORRECCIÓN: analyze_trend_layer en analyze_full_market ===
        # Ubicación: Línea ~1870 en analyze_full_market
        # Cambiar: trend = self.analyze_trend_layer(df, {})
        # Por: trend = self.analyze_trend_layer(df)
        
    def analyze_full_market(self, symbol, timeframe, btc_analysis=None, paxg_analysis=None, 
                            paxg_btc_analysis=None, df_override=None):
        try:
            print(f"\n{'='*60}")
            print(f"🔍 INICIANDO ANÁLISIS para {symbol} {timeframe}")
            print(f"{'='*60}")
            
            # Mostrar qué análisis se están pasando
            print(f"   BTC analysis: {type(btc_analysis).__name__ if btc_analysis else 'None'}")
            print(f"   PAXG analysis: {type(paxg_analysis).__name__ if paxg_analysis else 'None'}")
            print(f"   RATIO analysis: {type(paxg_btc_analysis).__name__ if paxg_btc_analysis else 'None'}")
            
    
            # ============ OBTENER DATOS ============
            print(f"📡 Obteniendo datos de KuCoin...")
            
            if df_override is not None:
                df = df_override
                print(f"✅ Usando DataFrame externo con {len(df)} velas")
            else:
                df = self.get_kucoin_data(symbol, timeframe)
            
            if df is None:
                print(f"❌ ERROR: get_kucoin_data devolvió None")
                return {
                    'success': False,
                    'error': 'No se pudieron obtener datos de KuCoin',
                    'symbol': symbol,
                    'timeframe': timeframe
                }
    
            
            print(f"✅ Datos obtenidos: {len(df)} velas")
            
            # ============ CAPAS EXISTENTES ============
            print(f"📊 Calculando capa de tendencia...")
            trend = self.analyze_trend_layer(df)
            print(f"   → Dirección: {trend.get('direction', 'unknown')}")
            
            print(f"📊 Calculando capa de momentum...")
            momentum = self.analyze_momentum_layer(df)
            
            print(f"📊 Calculando capa de volatilidad...")
            volatility = self.analyze_volatility_layer(df)
            
            print(f"📊 Calculando capa de volumen...")
            volume = self.analyze_volume_layer(df, timeframe)
            
            print(f"📊 Calculando capa de estructura...")
            structure = self.analyze_price_structure_layer(df, timeframe, symbol)
            
            # ============ AÑADIR INFORMACIÓN ADICIONAL A STRUCTURE ============
            if structure and isinstance(structure, dict):
                df_dict = {
                    'time': [str(t) for t in df['time'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()],
                    'open': [float(x) for x in df['open'].tolist()],
                    'high': [float(x) for x in df['high'].tolist()],
                    'low': [float(x) for x in df['low'].tolist()],
                    'close': [float(x) for x in df['close'].tolist()],
                    'volume': [float(x) for x in df['volume'].tolist()]
                }
                structure['df'] = df_dict
                structure['last_candle_index'] = len(df) - 1
            
            # ============ MAPA DE CALOR DE LIQUIDACIONES ============
            print(f"📊 Calculando capa de liquidaciones para {timeframe}...")
            
            # Inicializar estructura si no existe (con soporte para TF de futuros y spot)
            if not hasattr(self, 'liquidation_heatmaps'):
                self.liquidation_heatmaps = {
                    '5m': {}, '15m': {}, '30m': {}, '1h': {}, '2h': {},
                    '4h': {}, '12h': {}, '1D': {}, '1W': {}
                }
                print("   ✅ Estructura liquidation_heatmaps inicializada")
            
            # Verificar que la temporalidad existe
            if timeframe not in self.liquidation_heatmaps:
                self.liquidation_heatmaps[timeframe] = {}
                print(f"   ✅ Añadida temporalidad {timeframe}")
            
            # Crear heatmap si no existe
            if symbol not in self.liquidation_heatmaps[timeframe]:
                self.liquidation_heatmaps[timeframe][symbol] = LiquidationHeatmap(timeframe=timeframe)
                print(f"   ✅ Nuevo heatmap {timeframe} creado para {symbol}")
                
                # ============ CARGAR HISTORIAL COMPLETO ============
                self.liquidation_heatmaps[timeframe][symbol].load_price_history(df)
                print(f"   ✅ Historial cargado: {len(df)} velas para {symbol} {timeframe}")
                
            else:
                print(f"   🔍 Heatmap {timeframe} existente para {symbol}")
            
            heatmap = self.liquidation_heatmaps[timeframe][symbol]
            
            # ============ OBTENER DATOS DE LA VELA ACTUAL ============
            current_idx = len(df) - 1
            high_val = df['high'].iloc[current_idx]
            low_val = df['low'].iloc[current_idx]
            close_val = df['close'].iloc[current_idx]
            volume_val = df['volume'].iloc[current_idx]
            
            # ============ ACTUALIZAR HEATMAP ============
            heatmap.update_heatmap(
                df, current_idx, high_val, low_val, close_val, volume_val
            )
            
            # Obtener datos para la respuesta
            liquidation_data = heatmap.get_heatmap_data(current_idx, close_val)
            
            # Verificar que hay datos
            if liquidation_data['total_bins_historical'] > 0:
                print(f"   ✅ Heatmap {timeframe} tiene {liquidation_data['total_bins_historical']} bins totales")
            else:
                print(f"   ⚠️ Heatmap {timeframe} aún sin datos (acumulando...)")
            
            # ============ CAPAS EXISTENTES ============
            print(f"📊 Calculando capa de horarios...")
            market_hours = self.analyze_market_hours_layer()
            
            print(f"📊 Calculando capa de confirmación...")
            confirmation = self.analyze_confirmation_layer(
                df, structure, None, trend, momentum, volatility
            )
            
            print(f"📊 Calculando capa de tiempo...")
            levels_temp = {
                'entry': float(structure.get('current_price', 0)),
                'stop_loss': float(structure.get('current_price', 0)),
                'take_profit': float(structure.get('current_price', 0))
            }
            time_factor = self.analyze_time_factor_layer(df, 'NO_OPERAR', levels_temp)
            
            # ============ NUEVA CAPA 9: SENTIMIENTO ============
            print(f"📊 Calculando capa de sentimiento...")
            sentiment = self.analyze_sentiment_layer(symbol, timeframe)
            
            # ============ VERIFICAR Y CORREGIR ANÁLISIS PARA TRADERS ============
            print(f"\n🔍 VERIFICANDO ANÁLISIS RECIBIDOS EN analyze_full_market:")
            
            # BTC ANALYSIS
            if btc_analysis and isinstance(btc_analysis, dict):
                print(f"   BTC analysis recibido - symbol: {btc_analysis.get('symbol', 'unknown')}")
                if 'trend' in btc_analysis:
                    btc_adx_val = btc_analysis['trend'].get('adx', 0)
                    print(f"      → ADX en trend: {btc_adx_val}")
                    if btc_adx_val == 0:
                        print(f"      ⚠️ ADX es 0, pero debería tener valor")
                else:
                    print(f"      ⚠️ No hay trend en btc_analysis")
                    btc_analysis['trend'] = {'direction': 'neutral', 'adx': 0}
            else:
                print(f"   ⚠️ btc_analysis no válido, creando por defecto")
                btc_analysis = {
                    'success': True,
                    'symbol': 'BTC-USDT',
                    'timeframe': timeframe,
                    'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                    'trend': {'direction': 'neutral', 'adx': 0, 'plus_di': 0, 'minus_di': 0, 'confidence': 50},
                    'current_price': 0
                }
            
            # PAXG ANALYSIS
            if paxg_analysis and isinstance(paxg_analysis, dict):
                print(f"   PAXG analysis recibido - symbol: {paxg_analysis.get('symbol', 'unknown')}")
                if 'trend' in paxg_analysis:
                    paxg_adx_val = paxg_analysis['trend'].get('adx', 0)
                    print(f"      → ADX en trend: {paxg_adx_val}")
                else:
                    print(f"      ⚠️ No hay trend en paxg_analysis")
                    paxg_analysis['trend'] = {'direction': 'neutral', 'adx': 0}
            else:
                print(f"   ⚠️ paxg_analysis no válido, creando por defecto")
                paxg_analysis = {
                    'success': True,
                    'symbol': 'PAXG-USDT',
                    'timeframe': timeframe,
                    'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                    'trend': {'direction': 'neutral', 'adx': 0},
                    'current_price': 0
                }
            
            # RATIO ANALYSIS (PAXG/BTC)
            if paxg_btc_analysis and isinstance(paxg_btc_analysis, dict):
                print(f"   RATIO analysis recibido - symbol: {paxg_btc_analysis.get('symbol', 'unknown')}")
                if 'trend' in paxg_btc_analysis:
                    ratio_adx_val = paxg_btc_analysis['trend'].get('adx', 0)
                    print(f"      → ADX en trend: {ratio_adx_val}")
                else:
                    print(f"      ⚠️ No hay trend en ratio_analysis")
                    paxg_btc_analysis['trend'] = {'direction': 'neutral', 'adx': 0}
            else:
                print(f"   ⚠️ ratio_analysis no válido, creando por defecto")
                paxg_btc_analysis = {
                    'success': True,
                    'symbol': 'PAXG-BTC',
                    'timeframe': timeframe,
                    'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                    'trend': {'direction': 'neutral', 'adx': 0},
                    'current_price': 0
                }
            
            # ============ CONSTRUIR CAPAS PARA TRADERS ============
            capas = {
                'trend': trend,
                'momentum': momentum,
                'volatility': volatility,
                'volume': volume,
                'structure': structure,
                'market_hours': market_hours,
                'confirmation': confirmation,
                'time_factor': time_factor,
                'sentiment': sentiment,
                'liquidation': liquidation_data,
                'symbol': symbol,
                'timeframe': timeframe,
                'btc_analysis': btc_analysis,
                'paxg_analysis': paxg_analysis,
                'ratio_analysis': paxg_btc_analysis
            }
            
            # ============ SISTEMA DE 9 TRADERS ============
            print(f"👥 Iniciando votación de 9 traders...")
            moderador = Moderador()
            try:
                accion_consenso, confianza_consenso, estrategias_consenso, razones_consenso, registro_votacion = moderador.procesar_votacion(capas, symbol, timeframe)
                
                confianza_consenso = min(100, max(0, confianza_consenso))
                
                print(f"✅ Votación completada: {accion_consenso} (confianza {confianza_consenso})")
            except Exception as e:
                print(f"❌ ERROR en votación: {e}")
                import traceback
                traceback.print_exc()
                accion_consenso = 'NO_OPERAR'
                confianza_consenso = 0
                estrategias_consenso = []
                razones_consenso = ['Error en sistema de traders']
                registro_votacion = {}
            
            # ============ NIVELES ============
            levels = {}
            if accion_consenso in ['COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT']:
                print(f"💰 Calculando niveles para {accion_consenso}...")
                try:
                    levels = self.calculate_entry_levels(
                        accion_consenso, trend, momentum, volatility, structure, symbol, timeframe
                    )
                    
                    # Ajustar tamaño por convicción
                    if confianza_consenso < 70:
                        levels['suggested_size'] = 0.5
                    elif confianza_consenso < 85:
                        levels['suggested_size'] = 0.75
                    else:
                        levels['suggested_size'] = 1.0
                    
                    # Ajustar por sentimiento
                    if sentiment.get('sentiment_bias') in ['bullish_opportunity', 'bearish_opportunity']:
                        levels['suggested_size'] = min(1.0, levels['suggested_size'] * 1.2)
                    
                    print(f"✅ Niveles calculados: Entry={levels['entry']}, SL={levels['stop_loss']}, TP={levels['take_profit']}")
                    
                except Exception as e:
                    print(f"❌ ERROR en calculate_entry_levels: {e}")
                    import traceback
                    traceback.print_exc()
                    levels = self._get_default_levels(structure.get('current_price', 0), symbol)
            else:
                levels = self._get_default_levels(structure.get('current_price', 0), symbol)
            
            # ============ CALCULAR CONVICCIÓN ============
            print(f"📈 Calculando convicción...")
            if accion_consenso in ['COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT']:
                if confianza_consenso >= 85:
                    nivel_conv = 'ALTA'
                    icono_conv = '🟢'
                elif confianza_consenso >= 70:
                    nivel_conv = 'MEDIA-ALTA'
                    icono_conv = '🟡'
                elif confianza_consenso >= 55:
                    nivel_conv = 'MEDIA'
                    icono_conv = '🟠'
                elif confianza_consenso >= 40:
                    nivel_conv = 'BAJA'
                    icono_conv = '🔴'
                else:
                    nivel_conv = 'MUY BAJA'
                    icono_conv = '⛔'
                
                conviction = {
                    'level': nivel_conv,
                    'icon': icono_conv,
                    'description': f'Convicción {nivel_conv} basada en consenso',
                    'suggested_size': float(levels.get('suggested_size', 0.5)),
                    'suggested_leverage_modifier': float(confianza_consenso) / 100,
                    'raw_conviction': float(confianza_consenso),
                    'bonus_reasons': [str(r) for r in razones_consenso if isinstance(r, str) and ('favorable' in r or 'óptimo' in r or 'oportunidad' in r)][:2],
                    'degradation_reasons': [str(r) for r in razones_consenso if isinstance(r, str) and ('desfavorable' in r or 'riesgo' in r or 'cautela' in r)][:2]
                }
            else:
                conviction = {
                    'level': 'N/A',
                    'icon': '⚪',
                    'description': 'Sin acción de trading',
                    'suggested_size': 0,
                    'suggested_leverage_modifier': 0,
                    'raw_conviction': 0,
                    'bonus_reasons': [],
                    'degradation_reasons': []
                }
            
            # ============ CALCULAR CORRELACIÓN ============
            print(f"📊 Calculando capa de correlación...")
            
            # Verificar si los análisis existen y tienen éxito
            btc_available = False
            paxg_available = False
            ratio_available = False
            
            if btc_analysis is not None and isinstance(btc_analysis, dict):
                btc_available = btc_analysis.get('success', False)
                if not btc_available and 'decision' in btc_analysis:
                    btc_available = True
                    
            if paxg_analysis is not None and isinstance(paxg_analysis, dict):
                paxg_available = paxg_analysis.get('success', False)
                if not paxg_available and 'decision' in paxg_analysis:
                    paxg_available = True
                    
            if paxg_btc_analysis is not None and isinstance(paxg_btc_analysis, dict):
                ratio_available = paxg_btc_analysis.get('success', False)
                if not ratio_available and 'decision' in paxg_btc_analysis:
                    ratio_available = True
            
            print(f"   BTC disponible: {btc_available}")
            print(f"   PAXG disponible: {paxg_available}")
            print(f"   RATIO disponible: {ratio_available}")
            
            # Siempre calcular correlación, incluso con datos por defecto
            try:
                # Preparar análisis por defecto si es necesario
                if not btc_available:
                    btc_analysis = {
                        'success': True,
                        'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                        'trend': {'direction': 'neutral', 'adx': 0}
                    }
                    btc_available = True
                    print(f"   ⚠️ Usando BTC por defecto")
                    
                if not paxg_available:
                    paxg_analysis = {
                        'success': True,
                        'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                        'trend': {'direction': 'neutral', 'adx': 0}
                    }
                    paxg_available = True
                    print(f"   ⚠️ Usando PAXG por defecto")
                    
                if not ratio_available:
                    paxg_btc_analysis = {
                        'success': True,
                        'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                        'trend': {'direction': 'neutral', 'adx': 0}
                    }
                    ratio_available = True
                    print(f"   ⚠️ Usando RATIO por defecto")
                
                # Calcular correlación
                correlation = self.analyze_correlation_layer(
                    btc_analysis, paxg_analysis, paxg_btc_analysis, symbol
                )
                
                # Actualizar correlación con datos actuales
                if symbol == 'BTC-USDT':
                    if 'btc_analysis' in correlation:
                        correlation['btc_analysis']['trend'] = {
                            'direction': trend.get('direction', 'neutral'),
                            'adx': float(trend.get('adx', 0)),
                            'plus_di': float(trend.get('plus_di', 0)),
                            'minus_di': float(trend.get('minus_di', 0)),
                            'confidence': float(trend.get('confidence', 50))
                        }
                        correlation['btc_analysis']['decision'] = {
                            'action': accion_consenso,
                            'confidence': float(confianza_consenso)
                        }
                elif symbol == 'PAXG-USDT':
                    if 'paxg_analysis' in correlation:
                        correlation['paxg_analysis']['trend'] = {
                            'direction': trend.get('direction', 'neutral'),
                            'adx': float(trend.get('adx', 0)),
                            'plus_di': float(trend.get('plus_di', 0)),
                            'minus_di': float(trend.get('minus_di', 0)),
                            'confidence': float(trend.get('confidence', 50))
                        }
                elif symbol == 'PAXG-BTC':
                    if 'paxg_btc_analysis' in correlation:
                        correlation['paxg_btc_analysis']['trend'] = {
                            'direction': trend.get('direction', 'neutral'),
                            'adx': float(trend.get('adx', 0)),
                            'plus_di': float(trend.get('plus_di', 0)),
                            'minus_di': float(trend.get('minus_di', 0)),
                            'confidence': float(trend.get('confidence', 50))
                        }
                        correlation['paxg_btc_analysis']['decision'] = {
                            'action': accion_consenso,
                            'confidence': float(confianza_consenso)
                        }
                
                print(f"   ✅ Correlación calculada: {correlation.get('rotation_signal', 'NEUTRAL')}")
                
            except Exception as e:
                print(f"   ❌ Error calculando correlación: {e}")
                correlation = {
                    'correlation_score': 0,
                    'rotation_signal': 'NEUTRAL',
                    'weight_modifier': 1.0,
                    'symbol_recommendation': {'action': 'NEUTRAL', 'reason': 'error', 'weight': 1.0},
                    'symbol_score': 0,
                    'btc_analysis': {
                        'decision': {'action': 'N/A'},
                        'trend': {'direction': 'neutral', 'adx': 0}
                    },
                    'paxg_analysis': {
                        'trend': {'direction': 'neutral', 'adx': 0}
                    },
                    'paxg_btc_analysis': {
                        'decision': {'action': 'N/A'},
                        'trend': {'direction': 'neutral', 'adx': 0}
                    }
                }
            
            # ============ NUEVO: ZONAS DINÁMICAS DE TRADING (DESPUÉS DE LA VOTACIÓN) ============

            print(f"📊 Calculando zonas dinámicas para {timeframe}...")
            
            # Inicializar zonas si no existen
            if not hasattr(self, 'dynamic_zones'):
                self.dynamic_zones = {'4h': {}, '12h': {}, '1D': {}, '1W': {}}
            
            if timeframe not in self.dynamic_zones:
                self.dynamic_zones[timeframe] = {}
            
            if symbol not in self.dynamic_zones[timeframe]:
                self.dynamic_zones[timeframe][symbol] = DynamicZones(symbol, timeframe)
                print(f"   ✅ Nuevo sistema de zonas creado para {symbol} {timeframe}")
            
            zones_system = self.dynamic_zones[timeframe][symbol]
            
            # ============ CORRECCIÓN: Obtener información de votación para zonas ============
            veto_info = None
            todos_los_votos = []
            
            # Caso 1: registro_votacion es un diccionario
            if isinstance(registro_votacion, dict):
                todos_los_votos = registro_votacion.get('todos_los_votos', [])
                conteo_acciones = registro_votacion.get('conteo_acciones', {})
                confianza_por_accion = registro_votacion.get('confianza_por_accion', {})
                traders_por_accion = registro_votacion.get('traders_por_accion', {})
                
            # Caso 2: registro_votacion es una lista (como en caso de veto)
            elif isinstance(registro_votacion, list):
                print(f"   ⚠️ registro_votacion es una lista con {len(registro_votacion)} elementos")
                todos_los_votos = registro_votacion
                
                # Construir diccionarios a partir de la lista
                conteo_acciones = {}
                confianza_por_accion = {}
                traders_por_accion = {}
                
                for voto in todos_los_votos:
                    if isinstance(voto, dict):
                        accion = voto.get('accion')
                        trader = voto.get('trader')
                        confianza = voto.get('confianza_original', 0)
                        
                        if accion:
                            conteo_acciones[accion] = conteo_acciones.get(accion, 0) + 1
                            if accion not in traders_por_accion:
                                traders_por_accion[accion] = []
                            if trader:
                                traders_por_accion[accion].append(trader)
                            confianza_por_accion[accion] = confianza_por_accion.get(accion, 0) + confianza
            
            # Caso 3: otro tipo (error)
            else:
                print(f"   ⚠️ registro_votacion es de tipo {type(registro_votacion)}, usando valores vacíos")
                todos_los_votos = []
                conteo_acciones = {}
                confianza_por_accion = {}
                traders_por_accion = {}
            
            # Buscar veto del Escéptico
            for voto in todos_los_votos:
                if isinstance(voto, dict):
                    if voto.get('trader') == 'Escéptico' and voto.get('accion') == 'NO_OPERAR' and voto.get('confianza_original', 0) >= 80:
                        veto_info = {'trader': 'Escéptico', 'accion': 'NO_OPERAR', 'confianza': voto.get('confianza_original', 0)}
                        print(f"   ⚠️ Veto detectado: {veto_info}")
                        break
            
            # Calcular zonas
            zonas_data = zones_system.calculate_zone_from_votes(
                accion_consenso,
                conteo_acciones,
                confianza_por_accion,
                traders_por_accion,
                veto_info,
                close_val,
                current_idx,
                volatility # <--- Nuevo: pasar volatility para ATR dinámico
            )
            
            # Obtener estado del precio
            price_status = zones_system.get_price_status(close_val)
            print(f"   📍 Estado: {price_status['estado']}")
            # ====================================================================================
            
            # ============ GENERAR MENSAJE ============
            print(f"📝 Generando mensaje profesional...")
            try:
                message = self.generate_professional_message_with_consenso(
                    symbol, timeframe, 
                    accion_consenso,
                    float(confianza_consenso),
                    levels, 
                    trend, momentum, volatility, volume, structure,
                    correlation, market_hours, confirmation, 
                    conviction,
                    [str(e) for e in estrategias_consenso],
                    [str(r) for r in razones_consenso],
                    sentiment,
                    liquidation_data
                )
                print(f"✅ Mensaje generado correctamente")
            except Exception as e:
                print(f"❌ ERROR generando mensaje: {e}")
                import traceback
                traceback.print_exc()
                message = f"Análisis de {symbol} {timeframe}. Recomendación: {accion_consenso}"
            
            # ============ DATAFRAME PARA GRÁFICOS ============
            print(f"📊 Preparando DataFrame para gráficos...")
            try:
                df_dict = {
                    'time': [str(t) for t in df['time'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()],
                    'open': [float(x) for x in df['open'].tolist()],
                    'high': [float(x) for x in df['high'].tolist()],
                    'low': [float(x) for x in df['low'].tolist()],
                    'close': [float(x) for x in df['close'].tolist()],
                    'volume': [float(x) for x in df['volume'].tolist()]
                }
            except Exception as e:
                print(f"❌ ERROR preparando DataFrame: {e}")
                df_dict = {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}
            
            # ============ PREPARAR REGISTRO DE VOTACIÓN ============
            registro_serializable = {}
            try:
                if registro_votacion:
                    if isinstance(registro_votacion, dict):
                        registro_serializable = {
                            'accion_ganadora': str(registro_votacion.get('accion_ganadora', '')),
                            'confianza_final': float(registro_votacion.get('confianza_final', 0)),
                            'traders_que_apoyan': [str(t) for t in registro_votacion.get('traders_que_apoyan', [])],
                            'conteo_acciones': {str(k): int(v) for k, v in registro_votacion.get('conteo_acciones', {}).items()},
                            'confianza_por_accion': {str(k): float(v) for k, v in registro_votacion.get('confianza_por_accion', {}).items()},
                            'estrategias_consenso': [str(e) for e in registro_votacion.get('estrategias_consenso', [])],
                        }
                    else:
                        registro_serializable = {
                            'accion_ganadora': accion_consenso,
                            'confianza_final': float(confianza_consenso),
                            'traders_que_apoyan': [],
                            'conteo_acciones': {},
                            'confianza_por_accion': {},
                            'estrategias_consenso': [str(e) for e in estrategias_consenso]
                        }
            except Exception as e:
                print(f"❌ ERROR preparando registro de votación: {e}")
                registro_serializable = {
                    'accion_ganadora': accion_consenso,
                    'confianza_final': float(confianza_consenso),
                    'traders_que_apoyan': [],
                    'conteo_acciones': {},
                    'confianza_por_accion': {},
                    'estrategias_consenso': [str(e) for e in estrategias_consenso]
                }
            
            print(f"✅ ANÁLISIS COMPLETADO para {symbol} {timeframe}")
            print(f"{'='*60}\n")
            
            # === CONSTRUIR RESULTADO ===
            resultado_final = {
                'success': True,
                'symbol': symbol,
                'timeframe': timeframe,
                'decision': {
                    'action': accion_consenso,
                    'confidence': float(confianza_consenso),
                    'estrategias': [str(e) for e in estrategias_consenso],
                    'razones': [str(r) for r in razones_consenso],
                    'registro_votacion': registro_serializable,
                    'conviction': conviction
                },
                'levels': {k: float(v) if isinstance(v, (int, float)) else v for k, v in levels.items()},
                'message': str(message),
                'trend': self._make_serializable(trend),
                'momentum': self._make_serializable(momentum),
                'volatility': self._make_serializable(volatility),
                'volume': self._make_serializable(volume),
                'structure': self._make_serializable(structure),
                'correlation': self._make_serializable(correlation),
                'market_hours': self._make_serializable(market_hours),
                'confirmation': self._make_serializable(confirmation),
                'time_factor': self._make_serializable(time_factor),
                'sentiment': self._make_serializable(sentiment),
                'liquidation': self._make_serializable(liquidation_data),
                'zones': self._make_serializable({
                    'active_zones': zonas_data,
                    'price_status': price_status,
                    'timestamp': datetime.now(self.bolivia_tz).isoformat()
                }),
                'current_price': float(structure.get('current_price', 0)),
                'df': df_dict,
                'timestamp': datetime.now(self.bolivia_tz).isoformat()
            }
            
            # === FASE 7: Registrar señal en Supabase (best-effort, no bloqueante) ===
            try:
                from review_trader import review_trader
                if review_trader.db.enabled:
                    review_trader.register_signal(resultado_final, system_type='spot')
            except Exception as _register_error:
                # Nunca bloquear el análisis por un error de registro
                print(f"⚠️ No se pudo registrar señal en ReviewTrader: {_register_error}")
            
            return resultado_final
            
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ ERROR CRÍTICO en analyze_full_market: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol,
                'timeframe': timeframe
            }
    
    # ========================================================================
    # FUNCIÓN _make_serializable (AHORA SÍ AL MISMO NIVEL)
    # ========================================================================
    
    def _make_serializable(self, obj):
        """Convierte cualquier objeto a tipos serializables JSON - VERSIÓN CORREGIDA"""
        if obj is None:
            return None
        
        # Si el objeto tiene método to_dict, usarlo (CRÍTICO para LiquidationBin)
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
            return self._make_serializable(obj.to_dict())
        
        # Tipos básicos ya serializables
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # NumPy types
        if isinstance(obj, (np.integer, np.floating, np.bool_)):
            return obj.item()
        
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        
        # Datetime
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        
        # Listas y tuplas - procesar cada elemento
        if isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]
        
        # Diccionarios - preservar estructura
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                str_key = str(k)
                result[str_key] = self._make_serializable(v)
            return result
        
        # Para cualquier otro tipo, convertir a string
        return str(obj)
    # ========================================================================
    # ANALIZE ALL PAIRS
    # ========================================================================

    def analyze_all_pairs(self, timeframe):
        """Analizar todos los pares para una temporalidad específica - VERSIÓN CON CORRELACIÓN RADICAL"""
        print(f"\n{'='*60}")
        print(f"📊 [analyze_all_pairs] INICIANDO para {timeframe}")
        print(f"{'='*60}")
        
        results = {}
        
        # ============ PASO 1: ANALIZAR BTC (BASE) ============
        print(f"\n🔍 PASO 1: Analizando BTC-USDT...")
        try:
            btc_result = self.analyze_full_market('BTC-USDT', timeframe)
            if btc_result and btc_result.get('success'):
                results['BTC-USDT'] = btc_result
                print(f"   ✅ BTC-USDT OK")
                print(f"   Decisión: {btc_result['decision']['action']}")
                print(f"   Confianza: {btc_result['decision']['confidence']}%")
                print(f"   BTC ADX: {btc_result['trend'].get('adx', 0)}")
            else:
                print(f"   ❌ BTC-USDT falló: {btc_result.get('error', 'Error desconocido') if btc_result else 'Sin resultado'}")
                results['BTC-USDT'] = {
                    'success': True,
                    'symbol': 'BTC-USDT',
                    'timeframe': timeframe,
                    'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                    'trend': {
                        'direction': 'neutral',
                        'adx': 0,
                        'plus_di': 0,
                        'minus_di': 0
                    },
                    'current_price': 0
                }
        except Exception as e:
            print(f"   ❌ Excepción en BTC-USDT: {e}")
            results['BTC-USDT'] = {
                'success': True,
                'symbol': 'BTC-USDT',
                'timeframe': timeframe,
                'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                'trend': {
                    'direction': 'neutral',
                    'adx': 0,
                    'plus_di': 0,
                    'minus_di': 0
                },
                'current_price': 0
            }
        
        time.sleep(1)
        
        # ============ PASO 2: ANALIZAR PAXG CON BTC ============
        print(f"\n🔍 PASO 2: Analizando PAXG-USDT...")
        try:
            paxg_result = self.analyze_full_market(
                'PAXG-USDT', 
                timeframe, 
                btc_analysis=results['BTC-USDT']
            )
            if paxg_result and paxg_result.get('success'):
                results['PAXG-USDT'] = paxg_result
                print(f"   ✅ PAXG-USDT OK")
                print(f"   Decisión: {paxg_result['decision']['action']}")
                print(f"   PAXG ADX: {paxg_result['trend'].get('adx', 0)}")
            else:
                print(f"   ❌ PAXG-USDT falló: {paxg_result.get('error', 'Error desconocido') if paxg_result else 'Sin resultado'}")
                results['PAXG-USDT'] = {
                    'success': True,
                    'symbol': 'PAXG-USDT',
                    'timeframe': timeframe,
                    'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                    'trend': {
                        'direction': 'neutral',
                        'adx': 0,
                        'plus_di': 0,
                        'minus_di': 0
                    },
                    'current_price': 0
                }
        except Exception as e:
            print(f"   ❌ Excepción en PAXG-USDT: {e}")
            results['PAXG-USDT'] = {
                'success': True,
                'symbol': 'PAXG-USDT',
                'timeframe': timeframe,
                'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                'trend': {
                    'direction': 'neutral',
                    'adx': 0,
                    'plus_di': 0,
                    'minus_di': 0
                },
                'current_price': 0
            }
        
        time.sleep(1)
        
        # ============ PASO 3: ANALIZAR RATIO CON BTC Y PAXG ============
        print(f"\n🔍 PASO 3: Analizando PAXG-BTC...")
        try:
            # PRIMER ANÁLISIS - SIN paxg_btc_analysis (AÚN NO EXISTE)
            ratio_result = self.analyze_full_market(
                'PAXG-BTC', 
                timeframe,
                btc_analysis=results['BTC-USDT'],
                paxg_analysis=results['PAXG-USDT']
                # NO PASAR paxg_btc_analysis AQUÍ
            )
            if ratio_result and ratio_result.get('success'):
                results['PAXG-BTC'] = ratio_result
                print(f"   ✅ PAXG-BTC OK")
                print(f"   Decisión: {ratio_result['decision']['action']}")
                print(f"   RATIO ADX: {ratio_result['trend'].get('adx', 0)}")
            else:
                print(f"   ❌ PAXG-BTC falló")
                results['PAXG-BTC'] = {
                    'success': True,
                    'symbol': 'PAXG-BTC',
                    'timeframe': timeframe,
                    'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                    'trend': {'direction': 'neutral', 'adx': 0, 'plus_di': 0, 'minus_di': 0},
                    'current_price': 0
                }
        except Exception as e:
            print(f"   ❌ Excepción en PAXG-BTC: {e}")
            results['PAXG-BTC'] = {
                'success': True,
                'symbol': 'PAXG-BTC',
                'timeframe': timeframe,
                'decision': {'action': 'NO_OPERAR', 'confidence': 0},
                'trend': {'direction': 'neutral', 'adx': 0, 'plus_di': 0, 'minus_di': 0},
                'current_price': 0
            }
        
        # ============ PASO 4: RE-ANALIZAR BTC CON CORRELACIÓN COMPLETA ============
        print(f"\n🔍 PASO 4: Re-analizando BTC-USDT con correlación...")
        try:
            btc_con_corr = self.analyze_full_market(
                'BTC-USDT', 
                timeframe,
                btc_analysis=results['BTC-USDT'],
                paxg_analysis=results['PAXG-USDT'],
                paxg_btc_analysis=results['PAXG-BTC']
            )
            if btc_con_corr and btc_con_corr.get('success'):
                results['BTC-USDT'] = btc_con_corr
                print(f"   ✅ BTC-USDT re-analizado OK")
                print(f"   BTC ADX final: {btc_con_corr['trend'].get('adx', 0)}")
            else:
                print(f"   ⚠️ Re-análisis BTC falló, manteniendo anterior")
        except Exception as e:
            print(f"   ⚠️ Error en re-análisis BTC: {e}")
        
        time.sleep(1)
        
        # ============ PASO 5: RE-ANALIZAR PAXG CON CORRELACIÓN ============
        print(f"\n🔍 PASO 5: Re-analizando PAXG-USDT con correlación...")
        try:
            paxg_con_corr = self.analyze_full_market(
                'PAXG-USDT', 
                timeframe,
                btc_analysis=results['BTC-USDT'],
                paxg_analysis=results['PAXG-USDT'],
                paxg_btc_analysis=results['PAXG-BTC']
            )
            if paxg_con_corr and paxg_con_corr.get('success'):
                results['PAXG-USDT'] = paxg_con_corr
                print(f"   ✅ PAXG-USDT re-analizado OK")
                print(f"   PAXG ADX final: {paxg_con_corr['trend'].get('adx', 0)}")
            else:
                print(f"   ⚠️ Re-análisis PAXG falló, manteniendo anterior")
        except Exception as e:
            print(f"   ⚠️ Error en re-análisis PAXG: {e}")
        
        time.sleep(1)
        
        # ============ PASO 6: RE-ANALIZAR RATIO CON CORRELACIÓN ============
        print(f"\n🔍 PASO 6: Re-analizando PAXG-BTC con correlación...")
        try:
            ratio_con_corr = self.analyze_full_market(
                'PAXG-BTC', 
                timeframe,
                btc_analysis=results['BTC-USDT'],
                paxg_analysis=results['PAXG-USDT'],
                paxg_btc_analysis=results['PAXG-BTC']
            )
            if ratio_con_corr and ratio_con_corr.get('success'):
                results['PAXG-BTC'] = ratio_con_corr
                print(f"   ✅ PAXG-BTC re-analizado OK")
                print(f"   RATIO ADX final: {ratio_con_corr['trend'].get('adx', 0)}")
            else:
                print(f"   ⚠️ Re-análisis PAXG-BTC falló, manteniendo anterior")
        except Exception as e:
            print(f"   ⚠️ Error en re-análisis PAXG-BTC: {e}")
        
        time.sleep(1)
        
        # ============ CALCULAR CORRELACIÓN RADICAL Y FORZAR GUARDADO ============
        print(f"\n🔍 [RADICAL] Calculando correlación directamente desde resultados...")
        for symbol in results.keys():
            try:
                corr_result = self.calculate_correlation_from_results(results, symbol)
                if symbol in results:
                    # FORZAR GUARDADO
                    results[symbol]['correlation'] = corr_result
                    
                    # VERIFICAR QUE SE GUARDÓ
                    btc_adx = results[symbol].get('correlation', {}).get('btc_analysis', {}).get('trend', {}).get('adx', 0)
                    ratio_adx = results[symbol].get('correlation', {}).get('paxg_btc_analysis', {}).get('trend', {}).get('adx', 0)
                    
                    print(f"   ✅ Correlación GUARDADA para {symbol}: {corr_result['rotation_signal']}")
                    print(f"      BTC ADX guardado: {btc_adx}")
                    print(f"      RATIO ADX guardado: {ratio_adx}")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print(f"\n{'='*60}")
        print(f"📊 [analyze_all_pairs] COMPLETADO CON CORRELACIÓN RADICAL:")
        for symbol, result in results.items():
            status = "✅" if result.get('success') else "❌"
            action = result.get('decision', {}).get('action', 'N/A')
            adx = result.get('trend', {}).get('adx', 0)
            corr = result.get('correlation', {}).get('rotation_signal', 'N/A')
            print(f"   {status} {symbol}: {action} (ADX: {adx}) - Corr: {corr}")
        print(f"{'='*60}\n")
        
        return results
    # ========================================================================
    # GENERADOR DE GRÁFICOS CON PLOTLY
    # ========================================================================
    
    # === FUNCIÓN COMPLETA: generate_chart_image ===
    # Ubicación: Reemplazar entre línea 1650 y línea 1800 aproximadamente
    # CORRECCIONES: 
    # 1. Añadir import de kaleido al inicio del archivo (línea ~20)
    # 2. Usar 'df' del análisis si existe para evitar llamada adicional
    # 3. Manejar índices correctamente con pandas
    # 4. Corregir errores de sintaxis y variables
    
    def generate_chart_image(self, symbol, timeframe, analysis=None, top_indicators=None):
        """
        Generar gráfico con TODOS los indicadores relevantes
        - 6 subplots: 1 principal (velas) + 4 indicadores top + 1 patrón de velas
        """
        try:
            # Obtener datos
            df = None
            if analysis and 'df' in analysis:
                df_dict = analysis['df']
                df = pd.DataFrame({
                    'time': pd.to_datetime(df_dict['time']),
                    'open': df_dict['open'],
                    'high': df_dict['high'],
                    'low': df_dict['low'],
                    'close': df_dict['close'],
                    'volume': df_dict['volume']
                })
            else:
                df = self.get_kucoin_data(symbol, timeframe)
            
            if df is None or len(df) < 50:
                print(f"Datos insuficientes para gráfico: {symbol} {timeframe}")
                return None
            
            df = df.tail(100).copy()
            df = df.reset_index(drop=True)
            
            # ============ DETERMINAR TOP 4 INDICADORES ============
            if top_indicators is None:
                top_indicators = self.get_top_indicators_for_chart(analysis)
            
            # Asegurar que tenemos exactamente 4 indicadores
            if len(top_indicators) < 4:
                # Completar con indicadores por defecto según la acción
                action = analysis.get('decision', {}).get('action', '') if analysis else ''
                default_map = {
                    'COMPRA_SPOT': ['rsi_maverick', 'squeeze', 'whale', 'macd'],
                    'LONG': ['rsi_maverick', 'squeeze', 'dmi', 'supertrend'],
                    'VENTA_SPOT': ['rsi', 'macd', 'dmi', 'volume'],
                    'SHORT': ['rsi', 'macd', 'ftm', 'bollinger']
                }
                defaults = default_map.get(action, ['ftm', 'squeeze', 'rsi', 'volume'])
                for i in range(4 - len(top_indicators)):
                    if i < len(defaults):
                        top_indicators.append(defaults[i])
            
            top_indicators = top_indicators[:4]
            print(f"📊 Top 4 indicadores para gráfico: {top_indicators}")
            
            # ============ CREAR FIGURA CON 6 SUBPLOTS ============
            # Filas: 6 (1 principal + 4 indicadores + 1 patrón)
            fig = make_subplots(
                rows=6, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.25, 0.15, 0.15, 0.15, 0.15, 0.15],
                subplot_titles=[
                    f'{SYMBOLS[symbol]["name"]} - {TIMEFRAMES[timeframe]["name"]}',
                    f'📊 {top_indicators[0].upper()}',
                    f'📊 {top_indicators[1].upper()}',
                    f'📊 {top_indicators[2].upper()}',
                    f'📊 {top_indicators[3].upper()}',
                    '🔍 Patrón de Velas Detectado'
                ]
            )
            
            # ============ SUBPLOT 1: VELAS JAPONESAS + SOPORTES/RESISTENCIAS + EMAS + FVGs + ORDER BLOCKS ============
            # Velas
            fig.add_trace(
                go.Candlestick(
                    x=df['time'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name='Precio',
                    showlegend=False,
                    increasing=dict(line=dict(color='#00C076', width=1), fillcolor='#00C076'),
                    decreasing=dict(line=dict(color='#FF5B5B', width=1), fillcolor='#FF5B5B')
                ),
                row=1, col=1
            )
            
            # EMAs
            close_array = df['close'].values
            ema9 = self.calculate_ema(close_array, 9)
            ema21 = self.calculate_ema(close_array, 21)
            ema50 = self.calculate_ema(close_array, 50)
            ema200 = self.calculate_ema(close_array, 200)
            
            fig.add_trace(go.Scatter(x=df['time'], y=ema9, name='EMA 9', line=dict(color='#3A8BFF', width=1), row=1, col=1))
            fig.add_trace(go.Scatter(x=df['time'], y=ema21, name='EMA 21', line=dict(color='#FFD700', width=1), row=1, col=1))
            fig.add_trace(go.Scatter(x=df['time'], y=ema50, name='EMA 50', line=dict(color='#FF8C00', width=1), row=1, col=1))
            fig.add_trace(go.Scatter(x=df['time'], y=ema200, name='EMA 200', line=dict(color='#FF69B4', width=1), row=1, col=1))
            
            # Soportes y resistencias
            if analysis and 'structure' in analysis:
                structure = analysis['structure']
                if structure.get('nearest_support'):
                    fig.add_hline(y=structure['nearest_support'], line_dash="dash", 
                                line_color="#00C076", line_width=1, opacity=0.7, row=1, col=1)
                if structure.get('nearest_resistance'):
                    fig.add_hline(y=structure['nearest_resistance'], line_dash="dash",
                                line_color="#FF5B5B", line_width=1, opacity=0.7, row=1, col=1)
            
            # ============ SUBPLOTS 2-5: INDICADORES TOP ============
            for idx, indicator in enumerate(top_indicators[:4]):
                row = idx + 2
                self._add_indicator_trace(fig, df, indicator, analysis, row)
            
            # ============ SUBPLOT 6: PATRÓN DE VELAS ============
            self._add_pattern_chart(fig, df, analysis, row=6)
            
            # ============ LAYOUT ============
            title_text = f'{SYMBOLS[symbol]["name"]} - {TIMEFRAMES[timeframe]["name"]}'
            if analysis and 'decision' in analysis:
                action = analysis['decision'].get('action', 'Análisis')
                confidence = analysis['decision'].get('confidence', 0)
                action_color = self._get_action_color(analysis)
                title_text += f'<br><span style="font-size:12px; color:{action_color}">{action} - Confianza: {confidence:.0f}%</span>'
            
            fig.update_layout(
                height=1200,
                template='plotly_dark',
                showlegend=False,
                margin=dict(l=40, r=40, t=80, b=40),
                paper_bgcolor='#0A0C10',
                plot_bgcolor='#0A0C10',
                font=dict(color='white', size=8),
                title=dict(text=title_text, font=dict(size=12, color='white'), x=0.5, xanchor='center')
            )
            
            # Ocultar rangeslider en todos los subplots
            for i in range(1, 7):
                fig.update_xaxes(rangeslider=dict(visible=False), row=i, col=1)
            
            # Convertir a imagen
            try:
                img_bytes = fig.to_image(format="png", width=1600, height=1200, scale=1.5)
                return img_bytes
            except Exception as e:
                print(f"Error convirtiendo gráfico a PNG: {e}")
                return None
                
        except Exception as e:
            print(f"Error generando gráfico: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _add_indicator_trace(self, fig, df, indicator, analysis, row):
        """Añade la traza de un indicador específico al gráfico"""
        try:
            if indicator == 'ftm':
                ftm = self.calculate_trend_strength_maverick(df['close'].values)
                strength_values = ftm['trend_strength']
                abs_values = [abs(x) for x in strength_values]
                colors = ['#00C076' if x > 0 else '#FF5B5B' for x in strength_values]
                fig.add_trace(
                    go.Bar(x=df['time'], y=abs_values, marker_color=colors,
                          marker_line=dict(width=0.5, color='rgba(255,255,255,0.3)'),
                          hovertemplate='Ancho: %{y:.1f}%<br>Cambio: %{text}<extra></extra>',
                          text=['↑' if x > 0 else '↓' for x in strength_values]),
                    row=row, col=1
                )
                fig.add_hline(y=ftm['high_zone_threshold'], line_dash="dot", line_color="#FFD700", line_width=1, row=row, col=1)
                fig.update_yaxes(title_text="Ancho %", row=row, col=1)
            
            elif indicator == 'squeeze':
                squeeze = self.calculate_squeeze_momentum(df['high'].values, df['low'].values, df['close'].values)
                colors = ['#00C076' if x > 0 else '#FF5B5B' for x in squeeze['momentum']]
                fig.add_trace(
                    go.Bar(x=df['time'], y=squeeze['momentum'], marker_color=colors,
                          marker_line=dict(width=0.5, color='rgba(255,255,255,0.3)'),
                          name='Squeeze', row=row, col=1)
                )
                fig.add_hline(y=0, line_dash="solid", line_color="white", line_width=0.5, row=row, col=1)
                fig.update_yaxes(title_text="Momentum", row=row, col=1)
            
            elif indicator == 'rsi_maverick':
                rsi_m = self.calculate_rsi_maverick(df['close'].values, 20, 2.0)
                fig.add_trace(
                    go.Scatter(x=df['time'], y=rsi_m, line=dict(color='#3A8BFF', width=1.5),
                              fill='tozeroy', fillcolor='rgba(58,139,255,0.1)'),
                    row=row, col=1
                )
                fig.add_hline(y=0.8, line_dash="dot", line_color="#FF5B5B", row=row, col=1)
                fig.add_hline(y=0.2, line_dash="dot", line_color="#00C076", row=row, col=1)
                fig.update_yaxes(title_text="%B", range=[0, 1], row=row, col=1)
            
            elif indicator == 'whale':
                if analysis and 'volume' in analysis:
                    whale_strength = analysis['volume'].get('whale_signal_strength', 0)
                    whale_data = [whale_strength] * len(df)
                    colors = ['#00C076' if whale_strength > 0 else '#FF5B5B' for _ in df]
                    fig.add_trace(
                        go.Bar(x=df['time'], y=whale_data, marker_color=colors,
                              marker_line=dict(width=0.5, color='rgba(255,255,255,0.3)'),
                              name='Ballenas', row=row, col=1)
                    )
                fig.update_yaxes(title_text="Fuerza", row=row, col=1)
            
            elif indicator == 'dmi' or indicator == 'adx':
                adx_data = self.calculate_adx(df['high'].values, df['low'].values, df['close'].values, 14)
                fig.add_trace(go.Scatter(x=df['time'], y=adx_data['plus_di'], name='+DI',
                                        line=dict(color='#00C076', width=1), row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=adx_data['minus_di'], name='-DI',
                                        line=dict(color='#FF5B5B', width=1), row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=adx_data['adx'], name='ADX',
                                        line=dict(color='#FFD700', width=1, dash='dot'), row=row, col=1))
                fig.update_yaxes(title_text="DMI/ADX", row=row, col=1)
            
            elif indicator == 'rsi':
                rsi = self.calculate_rsi(df['close'].values, 14)
                fig.add_trace(go.Scatter(x=df['time'], y=rsi, line=dict(color='#8A63D2', width=1.5),
                                        name='RSI', row=row, col=1))
                fig.add_hline(y=70, line_dash="dot", line_color="#FF5B5B", row=row, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="#00C076", row=row, col=1)
                fig.update_yaxes(title_text="RSI", range=[0, 100], row=row, col=1)
            
            elif indicator == 'macd':
                macd_data = self.calculate_macd(df['close'].values, 12, 26, 9)
                colors = ['#00C076' if x > 0 else '#FF5B5B' for x in macd_data['histogram']]
                fig.add_trace(go.Scatter(x=df['time'], y=macd_data['macd'], line=dict(color='#3A8BFF', width=1),
                                        name='MACD', row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=macd_data['signal'], line=dict(color='#FFD700', width=1),
                                        name='Señal', row=row, col=1))
                fig.add_trace(go.Bar(x=df['time'], y=macd_data['histogram'], marker_color=colors,
                                    name='Histograma', row=row, col=1))
                fig.update_yaxes(title_text="MACD", row=row, col=1)
            
            elif indicator == 'volume':
                colors = ['#3A8BFF' if df['close'].iloc[i] > df['close'].iloc[i-1] else '#FF5B5B' 
                         for i in range(1, len(df))]
                colors.insert(0, '#3A8BFF')
                fig.add_trace(
                    go.Bar(x=df['time'], y=df['volume'], marker_color=colors,
                          marker_line=dict(width=0.5, color='rgba(255,255,255,0.3)'),
                          name='Volumen', row=row, col=1)
                )
                fig.update_yaxes(title_text="Volumen", row=row, col=1)
            
            elif indicator == 'atr':
                atr = self.calculate_atr(df['high'].values, df['low'].values, df['close'].values, 14)
                atr_pct = (atr / df['close'].values) * 100
                fig.add_trace(
                    go.Scatter(x=df['time'], y=atr_pct, line=dict(color='#FFD700', width=1.5),
                              fill='tozeroy', fillcolor='rgba(255,215,0,0.1)', name='ATR %', row=row, col=1)
                )
                fig.update_yaxes(title_text="ATR %", row=row, col=1)
            
            elif indicator == 'bollinger':
                bb = self.calculate_bollinger_bands(df['close'].values, 20, 2)
                bb_width = ((bb['upper'] - bb['lower']) / bb['middle'] * 100)
                fig.add_trace(
                    go.Scatter(x=df['time'], y=bb_width, line=dict(color='#8A63D2', width=1.5),
                              fill='tozeroy', fillcolor='rgba(138,99,210,0.1)', name='BB Width', row=row, col=1)
                )
                fig.update_yaxes(title_text="Ancho %", row=row, col=1)
            
            elif indicator == 'supertrend':
                st = self.calculate_supertrend(df['high'].values, df['low'].values, df['close'].values, 10, 3)
                st_colors = ['#00C076' if t == 1 else '#FF5B5B' for t in st['trend']]
                fig.add_trace(go.Scatter(x=df['time'], y=df['close'], line=dict(color='white', width=0.5),
                                        opacity=0.3, name='Precio', row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=st['supertrend'], line=dict(color='#8A63D2', width=1.5),
                                        mode='lines+markers', marker=dict(color=st_colors, size=2),
                                        name='SuperTrend', row=row, col=1))
                fig.update_yaxes(title_text="SuperTrend", row=row, col=1)
            
            elif indicator == 'ichimoku':
                ichimoku = self.calculate_ichimoku(df['high'].values, df['low'].values, df['close'].values)
                fig.add_trace(go.Scatter(x=df['time'], y=ichimoku['tenkan'], line=dict(color='#FFD700', width=1),
                                        name='Tenkan', row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=ichimoku['kijun'], line=dict(color='#FF69B4', width=1),
                                        name='Kijun', row=row, col=1))
                fig.update_yaxes(title_text="Ichimoku", row=row, col=1)
            
            elif indicator == 'stochastic':
                stoch = self.calculate_stochastic(df['high'].values, df['low'].values, df['close'].values, 14, 3)
                fig.add_trace(go.Scatter(x=df['time'], y=stoch['%K'], line=dict(color='#3A8BFF', width=1),
                                        name='%K', row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=stoch['%D'], line=dict(color='#FFD700', width=1),
                                        name='%D', row=row, col=1))
                fig.add_hline(y=80, line_dash="dot", line_color="#FF5B5B", row=row, col=1)
                fig.add_hline(y=20, line_dash="dot", line_color="#00C076", row=row, col=1)
                fig.update_yaxes(title_text="Estocástico", range=[0, 100], row=row, col=1)
            
            elif indicator == 'williams':
                williams = self.calculate_williams_r(df['high'].values, df['low'].values, df['close'].values, 14)
                fig.add_trace(go.Scatter(x=df['time'], y=williams, line=dict(color='#00C076', width=1.5),
                                        name='Williams %R', row=row, col=1))
                fig.add_hline(y=-20, line_dash="dot", line_color="#FF5B5B", row=row, col=1)
                fig.add_hline(y=-80, line_dash="dot", line_color="#00C076", row=row, col=1)
                fig.update_yaxes(title_text="Williams %R", row=row, col=1)
            
            elif indicator == 'cci':
                cci = self.calculate_cci(df['high'].values, df['low'].values, df['close'].values, 20)
                fig.add_trace(go.Scatter(x=df['time'], y=cci, line=dict(color='#FFD700', width=1.5),
                                        name='CCI', row=row, col=1))
                fig.add_hline(y=100, line_dash="dot", line_color="#FF5B5B", row=row, col=1)
                fig.add_hline(y=-100, line_dash="dot", line_color="#00C076", row=row, col=1)
                fig.update_yaxes(title_text="CCI", row=row, col=1)
            
            elif indicator == 'mfi':
                mfi = self.calculate_mfi(df['high'].values, df['low'].values, df['close'].values, df['volume'].values, 14)
                fig.add_trace(go.Scatter(x=df['time'], y=mfi, line=dict(color='#8A63D2', width=1.5),
                                        name='MFI', row=row, col=1))
                fig.add_hline(y=80, line_dash="dot", line_color="#FF5B5B", row=row, col=1)
                fig.add_hline(y=20, line_dash="dot", line_color="#00C076", row=row, col=1)
                fig.update_yaxes(title_text="MFI", range=[0, 100], row=row, col=1)
            
            elif indicator == 'force':
                force = self.calculate_force_index(df['close'].values, df['volume'].values, 13)
                fig.add_trace(go.Scatter(x=df['time'], y=force, line=dict(color='#FFD700', width=1.5),
                                        name='Force Index', row=row, col=1))
                fig.add_hline(y=0, line_dash="solid", line_color="white", line_width=0.5, row=row, col=1)
                fig.update_yaxes(title_text="Force Index", row=row, col=1)
            
            elif indicator == 'obv':
                obv = self.calculate_obv(df['close'].values, df['volume'].values)
                fig.add_trace(go.Scatter(x=df['time'], y=obv, line=dict(color='#FFD700', width=1.5),
                                        name='OBV', row=row, col=1))
                fig.update_yaxes(title_text="OBV", row=row, col=1)
            
            elif indicator == 'psar':
                psar = self.calculate_parabolic_sar(df['high'].values, df['low'].values)
                colors = ['#00C076' if psar['trend'][i] == 1 else '#FF5B5B' for i in range(len(df))]
                fig.add_trace(go.Scatter(x=df['time'], y=df['close'], line=dict(color='white', width=0.5),
                                        opacity=0.3, name='Precio', row=row, col=1))
                fig.add_trace(go.Scatter(x=df['time'], y=psar['sar'], mode='markers',
                                        marker=dict(color=colors, size=2, symbol='diamond'),
                                        name='Parabolic SAR', row=row, col=1))
                fig.update_yaxes(title_text="Parabolic SAR", row=row, col=1)
            
            elif indicator == 'fvg':
                if analysis and 'structure' in analysis and 'fair_value_gaps' in analysis['structure']:
                    fvgs = analysis['structure']['fair_value_gaps']
                    for fvg in fvgs[-5:]:  # Últimos 5 FVGs
                        if fvg.get('gap_bottom') and fvg.get('gap_top'):
                            color = '#00C076' if 'bullish' in fvg.get('type', '') else '#FF5B5B'
                            fig.add_hrect(y0=fvg['gap_bottom'], y1=fvg['gap_top'],
                                         line_width=0, fillcolor=color, opacity=0.2,
                                         row=row, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['close'], line=dict(color='white', width=0.5),
                                        name='Precio', row=row, col=1))
                fig.update_yaxes(title_text="FVGs", row=row, col=1)
            
        except Exception as e:
            print(f"Error añadiendo indicador {indicator}: {e}")
            fig.add_trace(go.Scatter(x=df['time'], y=[0]*len(df), name=f'Error {indicator}'), row=row, col=1)
    
    def _add_pattern_chart(self, fig, df, analysis, row):
        """Añade el gráfico del patrón de velas detectado"""
        try:
            if not analysis or 'structure' not in analysis:
                fig.add_trace(go.Scatter(x=df['time'], y=[0]*len(df), name='Sin patrón'), row=row, col=1)
                return
            
            patterns = analysis['structure'].get('patterns', {})
            recent_patterns = patterns.get('recent_patterns', [])
            
            if not recent_patterns:
                fig.add_trace(go.Scatter(x=df['time'], y=[0]*len(df), name='Sin patrón'), row=row, col=1)
                return
            
            # Encontrar el mejor patrón
            best_pattern = max(recent_patterns, key=lambda x: x.get('reliability', 0))
            pattern_index = best_pattern.get('index', 0)
            pattern_name = best_pattern.get('name', 'Patrón')
            pattern_reliability = best_pattern.get('reliability', 0)
            
            # Determinar cuántas velas mostrar según el tipo de patrón
            pattern_type = best_pattern.get('type', '1')
            if pattern_type in ['1', '2', '3']:
                num_velas = 10  # Mostrar contexto
            else:
                num_velas = 30  # Patrones chartistas
            
            # Obtener las velas relevantes
            start_idx = max(0, pattern_index - 5)
            end_idx = min(len(df), pattern_index + 5)
            
            df_pattern = df.iloc[start_idx:end_idx].copy()
            
            # Resaltar la vela del patrón
            colors = ['#00C076' if i == pattern_index - start_idx else '#808080' 
                     for i in range(len(df_pattern))]
            
            fig.add_trace(
                go.Candlestick(
                    x=df_pattern['time'],
                    open=df_pattern['open'],
                    high=df_pattern['high'],
                    low=df_pattern['low'],
                    close=df_pattern['close'],
                    name=pattern_name,
                    increasing=dict(line=dict(color='#00C076', width=1), fillcolor='#00C076'),
                    decreasing=dict(line=dict(color='#FF5B5B', width=1), fillcolor='#FF5B5B'),
                    showlegend=False
                ),
                row=row, col=1
            )
            
            # Añadir anotación del patrón
            pattern_time = df_pattern['time'].iloc[pattern_index - start_idx] if pattern_index < len(df) else df_pattern['time'].iloc[-1]
            fig.add_annotation(
                x=pattern_time,
                y=df_pattern['high'].max(),
                text=f"🔍 {pattern_name} ({pattern_reliability}%)",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=1,
                arrowcolor="#FFD700",
                font=dict(size=8, color="white"),
                row=row, col=1
            )
            
            fig.update_yaxes(title_text="Patrón", row=row, col=1)
            
        except Exception as e:
            print(f"Error añadiendo patrón: {e}")
            fig.add_trace(go.Scatter(x=df['time'], y=[0]*len(df), name='Error patrón'), row=row, col=1)
        
    def generate_pattern_chart(self, symbol, timeframe, analysis=None):
        """Generar gráfico específico para el patrón detectado - 4 velas o 30 velas según el tipo"""
        try:
            if not analysis or not analysis.get('success'):
                return None
            
            # Obtener datos
            df = None
            if analysis and 'df' in analysis:
                df_dict = analysis['df']
                df = pd.DataFrame({
                    'time': pd.to_datetime(df_dict['time']),
                    'open': df_dict['open'],
                    'high': df_dict['high'],
                    'low': df_dict['low'],
                    'close': df_dict['close'],
                    'volume': df_dict['volume']
                })
            else:
                df = self.get_kucoin_data(symbol, timeframe)
            
            if df is None or len(df) < 30:
                return None
            
            # Obtener el mejor patrón
            structure = analysis.get('structure', {})
            patterns = structure.get('patterns', {})
            recent_patterns = patterns.get('recent_patterns', [])
            
            if not recent_patterns:
                return None
            
            # Filtrar patrones de calidad
            patrones_validos = [p for p in recent_patterns if p.get('reliability', 0) >= 70]
            if not patrones_validos:
                return None
            
            mejor_patron = max(patrones_validos, key=lambda x: x.get('reliability', 0))
            tipo_patron = mejor_patron.get('type', '1')
            nombre_patron = mejor_patron.get('name', 'Patrón')
            idx_patron = mejor_patron.get('index', 0)  # Índice en el DataFrame original
            
            # Determinar cantidad de velas a mostrar
            if tipo_patron in ['1', '2', '3']:
                # Patrones de 1-3 velas: mostrar 4 velas (la del patrón + contexto)
                num_velas = 4
                titulo = f"Patrón de {tipo_patron} vela: {nombre_patron}"
            else:
                # Patrones chartistas (4+): mostrar 30 velas
                num_velas = 30
                titulo = f"Formación chartista: {nombre_patron}"
            
            # Tomar las últimas N velas
            df_chart = df.tail(num_velas).copy()
            df_chart = df_chart.reset_index(drop=True)
            
            # Calcular rango para ajustar ejes
            max_precio = df_chart['high'].max()
            min_precio = df_chart['low'].min()
            padding = (max_precio - min_precio) * 0.05
            
            # Crear figura
            fig = go.Figure()
            
            # Añadir velas japonesas
            fig.add_trace(go.Candlestick(
                x=df_chart['time'],
                open=df_chart['open'],
                high=df_chart['high'],
                low=df_chart['low'],
                close=df_chart['close'],
                name='Precio',
                increasing=dict(line=dict(color='#00C076', width=1), fillcolor='#00C076'),
                decreasing=dict(line=dict(color='#FF5B5B', width=1), fillcolor='#FF5B5B'),
                showlegend=False
            ))
            
            # ============ CORRECCIÓN ERROR 5 Y 6: Calcular offset según timeframe ============
            # Calcular offset para resaltar la vela del patrón
            if timeframe == '4h':
                offset = pd.Timedelta(hours=6)
            elif timeframe == '12h':
                offset = pd.Timedelta(hours=12)
            elif timeframe == '1D':
                offset = pd.Timedelta(days=1)
            elif timeframe == '1W':
                offset = pd.Timedelta(days=3)
            else:
                offset = pd.Timedelta(hours=12)
            
            # ============ CORRECCIÓN ERROR 6: Usar el índice real del patrón ============
            # Calcular la posición relativa del patrón en df_chart
            # El índice en df_chart es relativo a las últimas num_velas velas
            # El índice original está en el DataFrame completo
            idx_relativo = idx_patron - (len(df) - len(df_chart))
            
            # Verificar que el índice esté dentro del rango de df_chart
            if 0 <= idx_relativo < len(df_chart):
                tiempo_patron = df_chart['time'].iloc[idx_relativo]
                
                # Resaltar la vela donde se detectó el patrón
                fig.add_shape(
                    type="rect",
                    x0=tiempo_patron - offset,
                    x1=tiempo_patron + offset,
                    y0=min_precio,
                    y1=max_precio,
                    line=dict(color="#FFD700", width=2),
                    fillcolor="rgba(255,215,0,0.1)",
                    layer="below"
                )
                
                # Añadir marcador de "Patrón"
                fig.add_annotation(
                    x=tiempo_patron,
                    y=max_precio,
                    text="🔍 PATRÓN",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=2,
                    arrowcolor="#FFD700",
                    font=dict(size=12, color="white", family="Arial Black"),
                    bgcolor="rgba(255,215,0,0.3)",
                    bordercolor="#FFD700",
                    borderwidth=1,
                    borderpad=4
                )
            else:
                # Si el patrón está fuera del rango mostrado, resaltar la última vela
                print(f"⚠️ Patrón en índice {idx_patron} fuera del rango mostrado ({len(df)-len(df_chart)} a {len(df)-1})")
                tiempo_patron = df_chart['time'].iloc[-1]
                fig.add_shape(
                    type="rect",
                    x0=tiempo_patron - offset,
                    x1=tiempo_patron + offset,
                    y0=min_precio,
                    y1=max_precio,
                    line=dict(color="#FFD700", width=2, dash="dash"),
                    fillcolor="rgba(255,215,0,0.05)",
                    layer="below"
                )
            
            # Configurar layout
            fig.update_layout(
                title=dict(
                    text=titulo,
                    font=dict(color='white', size=14),
                    x=0.5,
                    xanchor='center'
                ),
                xaxis=dict(
                    range=[df_chart['time'].iloc[0], df_chart['time'].iloc[-1]],
                    showgrid=False,
                    showline=False,
                    showticklabels=True,
                    tickfont=dict(color='white', size=10),
                    title=dict(text='', font=dict(color='white'))
                ),
                yaxis=dict(
                    range=[min_precio - padding, max_precio + padding],
                    showgrid=True,
                    gridcolor='rgba(128,128,128,0.2)',
                    showline=True,
                    linecolor='rgba(128,128,128,0.5)',
                    tickfont=dict(color='white', size=10),
                    title=dict(text='Precio', font=dict(color='white'))
                ),
                template='plotly_dark',
                height=400,
                width=800,
                margin=dict(l=50, r=50, t=60, b=40),
                paper_bgcolor='#0A0C10',
                plot_bgcolor='#0A0C10',
                showlegend=False
            )
            
            # Convertir a imagen
            try:
                img_bytes = fig.to_image(format="png", width=800, height=400, scale=1.5)
                return img_bytes
            except Exception as e:
                print(f"Error convirtiendo gráfico de patrón a PNG: {e}")
                try:
                    import kaleido
                    img_bytes = fig.to_image(format="png", width=800, height=400, scale=1.5, engine="kaleido")
                    return img_bytes
                except:
                    return None
                
        except Exception as e:
            print(f"Error en generate_pattern_chart: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    
    
    def generate_pattern_alert(self, analysis):
        """Generar mensaje con el patrón de vela de mayor confianza detectado - VERSIÓN MEJORADA"""
        try:
            if not analysis or not analysis.get('success'):
                print("⚠️ generate_pattern_alert: análisis no exitoso")
                return None
            
            structure = analysis.get('structure', {})
            patterns = structure.get('patterns', {})
            recent_patterns = patterns.get('recent_patterns', [])
            
            if not recent_patterns:
                print("⚠️ generate_pattern_alert: no hay patrones recientes")
                return None
            
            # Encontrar el patrón con mayor confiabilidad
            best_pattern = max(recent_patterns, key=lambda x: x.get('reliability', 0))
            
            pattern_name = best_pattern.get('name', 'Patrón')
            pattern_direction = best_pattern.get('direction', 'neutral')
            pattern_reliability = best_pattern.get('reliability', 0)
            pattern_type = best_pattern.get('type', '1')
            pattern_index = best_pattern.get('index', 0)
            
            print(f"✅ Patrón detectado: {pattern_name} ({pattern_direction}) - {pattern_reliability}%")
            
            # Emoji según dirección
            if pattern_direction == 'bullish':
                direction_emoji = '🟢'
                direction_text = 'ALCISTA'
            elif pattern_direction == 'bearish':
                direction_emoji = '🔴'
                direction_text = 'BAJISTA'
            else:
                direction_emoji = '⚪'
                direction_text = 'NEUTRAL'
            
            # Texto según tipo de patrón
            if pattern_type == '1':
                type_text = '1 vela'
                formation_text = 'Patrón de reversión de 1 vela'
            elif pattern_type == '2':
                type_text = '2 velas'
                formation_text = 'Patrón de reversión/continuación de 2 velas'
            elif pattern_type == '3':
                type_text = '3 velas'
                formation_text = 'Patrón de reversión de 3 velas'
            else:
                type_text = 'formación chartista'
                formation_text = 'Formación chartista completada'
            
            # Nivel de confiabilidad textual
            if pattern_reliability >= 90:
                reliability_text = 'MUY ALTA'
                reliability_icon = '🔥'
            elif pattern_reliability >= 80:
                reliability_text = 'ALTA'
                reliability_icon = '✅'
            elif pattern_reliability >= 70:
                reliability_text = 'MODERADA'
                reliability_icon = '📊'
            elif pattern_reliability >= 60:
                reliability_text = 'MEDIA'
                reliability_icon = '⚠️'
            else:
                reliability_text = 'BAJA'
                reliability_icon = 'ℹ️'
            
            # Construir mensaje
            message = f"━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"{direction_emoji} <b>PATRÓN {direction_text} DETECTADO</b> {direction_emoji}\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>{pattern_name}</b> de {type_text}\n"
            message += f"{formation_text}\n"
            message += f"Confiabilidad: {pattern_reliability:.0f}% ({reliability_text}) {reliability_icon}\n"
            
            # Información adicional según el patrón
            if 'HCH' in pattern_name or 'Cabeza Hombro' in pattern_name:
                message += f"Proyección: Ruptura de neckline\n"
            elif 'Doble' in pattern_name:
                message += f"Proyección: Altura del patrón\n"
            elif 'Bandera' in pattern_name or 'Banderín' in pattern_name:
                message += f"Proyección: Misma dirección que el mástil\n"
            
            return message
            
        except Exception as e:
            print(f"❌ Error generando alerta de patrón: {e}")
            import traceback
            traceback.print_exc()
            return None

    
    def _get_action_color(self, analysis):
        """Obtener color para título según acción"""
        if not analysis or 'decision' not in analysis:
            return 'white'
        
        action = analysis['decision'].get('action', '')
        if action in ['COMPRA_SPOT', 'LONG']:
            return '#00C076'
        elif action in ['VENTA_SPOT', 'SHORT']:
            return '#FF5B5B'
        elif action == 'NO_OPERAR':
            return '#FFD700'
        else:
            return 'white'
    # === FIN FUNCIÓN COMPLETA ===
    
    # ========================================================================
    # ENVÍO A TELEGRAM
    # ========================================================================
    
    # === FUNCIÓN COMPLETA: send_telegram_alert ===
    # Ubicación: Reemplazar entre línea 1780 y línea 1805 aproximadamente
    
    def send_telegram_alert(self, message, image_bytes=None):
        """Enviar alerta a Telegram con imagen adjunta (ahora con todos los gráficos)"""
        try:
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                print("❌ Error: Credenciales de Telegram no configuradas")
                return False
            
            print(f"      📤 Telegram: Enviando mensaje ({len(message)} chars)")
            
            # Enviar mensaje de texto
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            if len(message) > 4000:
                message = message[:4000] + "...\n\n[Mensaje truncado]"
            
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=15)
            
            if response.status_code != 200:
                print(f"      ❌ Error HTTP {response.status_code}")
                return False
            
            # Enviar imagen si existe
            if image_bytes:
                print(f"      📤 Enviando imagen ({len(image_bytes)} bytes)")
                url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                
                files = {'photo': ('chart.png', image_bytes, 'image/png')}
                data = {'chat_id': TELEGRAM_CHAT_ID}
                
                response_photo = requests.post(url_photo, files=files, data=data, timeout=30)
                
                if response_photo.status_code == 200:
                    print(f"      ✅ Imagen enviada")
                else:
                    print(f"      ⚠️ Error imagen: {response_photo.status_code}")
                    print(f"      {response_photo.text[:200]}")
            
            return True
            
        except Exception as e:
            print(f"      ❌ Error crítico: {e}")
            return False
    # === FIN FUNCIÓN COMPLETA ===
    
    # === CORRECCIÓN: TradingExpertSystem.generate_market_panorama ===
    # Ubicación: Reemplazar función completa
    
    # === FUNCIÓN COMPLETA: generate_market_panorama ===
    # Ubicación: Reemplazar entre línea 1820 y línea 1920 aproximadamente
    
    def generate_market_panorama(self):
        """Generar informe completo del panorama de mercado con gráficos adjuntos"""
        try:
            message = "🔍 <b>📊 PANORAMA COMPLETO DE MERCADO</b>\n"
            message += f"🕐 {datetime.now(self.bolivia_tz).strftime('%Y-%m-%d %H:%M:%S')} Hora Bolivia\n\n"
            
            all_images = []
            btc_1d_analysis = None
            paxg_btc_analysis = None
            
            # ============ ANÁLISIS BTC/USDT ============
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>💰 BTC/USDT - ANÁLISIS MULTITEMPORAL</b>\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
            for tf in ['1D', '12h', '4h']:
                try:
                    analysis = self.analyze_full_market('BTC-USDT', tf)
                    if analysis['success']:
                        if tf == '1D':
                            btc_1d_analysis = analysis
                        
                        action = analysis['decision']['action']
                        conf = analysis['decision']['confidence']
                        
                        emoji = {
                            'COMPRA_SPOT': '🟢', 'VENTA_SPOT': '🔴',
                            'LONG': '📈', 'SHORT': '📉', 'NO_OPERAR': '⏸️'
                        }.get(action, '⚡')
                        
                        message += f"{emoji} <b>{TIMEFRAMES[tf]['name']}:</b> {action} (confianza {conf:.0f}%)\n"
                        message += f"   Precio: ${analysis['current_price']:.2f} | "
                        
                        if action not in ['NO_OPERAR', None]:
                            levels = analysis.get('levels', {})
                            message += f"Entrada: ${levels.get('entry', 0):.2f} | "
                            message += f"SL: ${levels.get('stop_loss', 0):.2f} | "
                            message += f"TP: ${levels.get('take_profit', 0):.2f}\n"
                        else:
                            reason = analysis['decision'].get('reason', 'condiciones desfavorables')
                            message += f"Razón: {reason}\n"
                        
                        # Generar gráfico para BTC (máximo 2 gráficos de BTC)
                        if len(all_images) < 2:
                            img = self.generate_chart_image('BTC-USDT', tf, analysis)
                            if img:
                                all_images.append(img)
                                
                except Exception as e:
                    print(f"Error analizando BTC {tf}: {e}")
                    message += f"⚠️ {tf}: Error en análisis\n"
            
            # ============ ANÁLISIS PAXG/USDT ============
            message += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>🏅 PAXG/USDT - ORO TOKENIZADO</b>\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
            for tf in ['1D', '12h']:
                try:
                    analysis = self.analyze_full_market('PAXG-USDT', tf)
                    if analysis['success']:
                        action = analysis['decision']['action']
                        conf = analysis['decision']['confidence']
                        
                        emoji = '🟢' if action == 'COMPRA_SPOT' else '🔴' if action == 'VENTA_SPOT' else '⏸️'
                        
                        message += f"{emoji} <b>{TIMEFRAMES[tf]['name']}:</b> {action} (confianza {conf:.0f}%)\n"
                        message += f"   Precio: ${analysis['current_price']:.2f} | "
                        
                        if action not in ['NO_OPERAR', None]:
                            levels = analysis.get('levels', {})
                            message += f"Entrada: ${levels.get('entry', 0):.2f}\n"
                        else:
                            message += f"\n"
                        
                        # Gráfico para PAXG (1 máximo)
                        if len(all_images) < 3:
                            img = self.generate_chart_image('PAXG-USDT', tf, analysis)
                            if img:
                                all_images.append(img)
                                
                except Exception as e:
                    print(f"Error analizando PAXG {tf}: {e}")
            
            # ============ ANÁLISIS PAXG/BTC ============
            message += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>🔄 PAXG/BTC - RATIO ORO/BITCOIN</b>\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
            try:
                analysis = self.analyze_full_market('PAXG-BTC', '1D')
                if analysis['success']:
                    paxg_btc_analysis = analysis
                    action = analysis['decision']['action']
                    conf = analysis['decision']['confidence']
                    
                    emoji = '🟢' if action == 'COMPRA_SPOT' else '🔴' if action == 'VENTA_SPOT' else '⏸️'
                    
                    message += f"{emoji} <b>1 Día:</b> {action} (confianza {conf:.0f}%)\n"
                    message += f"   Ratio: {analysis['current_price']:.6f} BTC | "
                    
                    if action not in ['NO_OPERAR', None]:
                        levels = analysis.get('levels', {})
                        message += f"Entrada: {levels.get('entry', 0):.6f} BTC\n"
                    else:
                        message += f"\n"
                    
                    # Gráfico del ratio
                    if len(all_images) < 4:
                        img = self.generate_chart_image('PAXG-BTC', '1D', analysis)
                        if img:
                            all_images.append(img)
                            
            except Exception as e:
                print(f"Error analizando PAXG/BTC: {e}")
            
            # ============ ANÁLISIS DE CORRELACIÓN Y ROTACIÓN ============
            message += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>🔄 ANÁLISIS DE CORRELACIÓN Y ROTACIÓN</b>\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
            risk_on = False
            rotation_signal = "NEUTRAL"
            
            if btc_1d_analysis and paxg_btc_analysis:
                btc_action = btc_1d_analysis['decision']['action']
                btc_conf = btc_1d_analysis['decision']['confidence']
                ratio_action = paxg_btc_analysis['decision']['action']
                
                if btc_action in ['COMPRA_SPOT', 'LONG'] and btc_conf > 65:
                    if ratio_action == 'VENTA_SPOT':
                        risk_on = True
                        rotation_signal = "🟢 ROTACIÓN HACIA CRYPTO (riesgo-on)"
                    else:
                        rotation_signal = "🟡 CORRELACIÓN POSITIVA (riesgo moderado)"
                elif btc_action in ['VENTA_SPOT', 'SHORT'] and btc_conf > 65:
                    if ratio_action == 'COMPRA_SPOT':
                        risk_on = False
                        rotation_signal = "🟠 ROTACIÓN HACIA ORO (riesgo-off)"
                    else:
                        rotation_signal = "🔵 CORRELACIÓN NEGATIVA (refugio)"
            
            message += f"<b>Señal de rotación:</b> {rotation_signal}\n"
            
            # Fortaleza relativa
            message += f"\n<b>📊 FORTALEZA RELATIVA (vs USD):</b>\n"
            
            if btc_1d_analysis:
                btc_trend = btc_1d_analysis['trend']['direction']
                btc_strength = btc_1d_analysis['trend']['strength']
                message += f"   • BTC/USDT: {btc_trend.upper()} | Fuerza: {btc_strength}\n"
            
            try:
                paxg_1d = self.analyze_full_market('PAXG-USDT', '1D')
                if paxg_1d['success']:
                    paxg_trend = paxg_1d['trend']['direction']
                    paxg_strength = paxg_1d['trend']['strength']
                    message += f"   • PAXG/USDT: {paxg_trend.upper()} | Fuerza: {paxg_strength}\n"
            except:
                pass
            
            # ============ RECOMENDACIÓN DE ASIGNACIÓN ============
            message += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>💼 RECOMENDACIÓN DE ASIGNACIÓN</b>\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
            if risk_on:
                message += f"🟢 <b>MODO RIESGO-ON:</b> Favorecer crypto sobre oro\n"
                message += f"   • BTC/USDT: 70% (spot/futures según temporalidad)\n"
                message += f"   • PAXG/USDT: 20% (hedge estratégico)\n"
                message += f"   • USDT: 10% (liquidez para oportunidades)\n"
            else:
                message += f"🟡 <b>MODO RIESGO-OFF:</b> Favorecer refugio sobre crypto\n"
                message += f"   • PAXG/USDT: 60% (protección de capital)\n"
                message += f"   • BTC/USDT: 20% (exposición controlada)\n"
                message += f"   • USDT: 20% (esperando mejor entrada)\n"
            
            # ============ ALERTAS DE RIESGO ============
            message += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"<b>⚠️ ALERTAS DE RIESGO ACTIVAS</b>\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
            risk_count = 0
            
            # BTC Alertas
            try:
                btc_4h = self.analyze_full_market('BTC-USDT', '4h')
                if btc_4h['success']:
                    if not btc_4h['volatility']['operability']:
                        reason = btc_4h['volatility']['no_trade_reason']
                        msg = reason[0] if reason else 'Volatilidad extrema'
                        message += f"   • BTC 4H: {msg}\n"
                        risk_count += 1
                    if btc_4h['volatility'].get('ftm_no_trade', False):
                        message += f"   • BTC 4H: FTMaverick en zona de NO-OPERACIÓN\n"
                        risk_count += 1
            except:
                pass
            
            if btc_1d_analysis:
                if btc_1d_analysis['trend']['adx'] < 20: #adx_value
                    adx_val = btc_1d_analysis['trend']['adx'] #adx_value
                    message += f"   • BTC 1D: ADX bajo ({adx_val:.1f}) - mercado sin dirección\n"
                    risk_count += 1
            
            if risk_count == 0:
                message += f"   • No hay alertas de riesgo significativas\n"
            
            message += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"✅ <b>Análisis generado por Crypto Trader Analyst Pro</b>\n"
            message += f"📊 {len(all_images)} gráficos adjuntos con indicadores clave\n"
            
            # Limitar a 5 imágenes máximo (Telegram permite hasta 10 pero por estabilidad)
            return message, all_images[:5]
            
        except Exception as e:
            print(f"Error generando panorama: {e}")
            import traceback
            traceback.print_exc()
            error_msg = "❌ <b>ERROR GENERANDO ANÁLISIS</b>\n\n"
            error_msg += f"No se pudo completar el panorama de mercado.\n"
            error_msg += f"Error: {str(e)[:200]}\n\n"
            error_msg += f"🕐 {datetime.now(self.bolivia_tz).strftime('%Y-%m-%d %H:%M:%S')} Hora Bolivia"
            return error_msg, []
    # === FIN FUNCIÓN COMPLETA ===


    def should_send_telegram_alert(self, decision, timeframe):
        """Determina si debe enviarse alerta según temporalidad y ventana de tiempo"""
        try:
            # Solo enviar señales de trading
            if decision not in ['COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT']:
                return False
            
            ahora = datetime.now(self.bolivia_tz)
            minuto = ahora.minute
            hora = ahora.hour
            minuto_actual = hora * 60 + minuto
            
            # Para DEBUG - mostrar siempre True (solo para pruebas)
            # return True  # ← Descomentar SOLO para probar
            
            # Definir ventanas por temporalidad (minutos ANTES del cierre)
            ventanas = {
                '4h': {  # Cierres: 23:00, 03:00, 07:00, 11:00, 15:00, 19:00
                    23*60: [30, 15],  # 30 min y 15 min antes
                    3*60: [30, 15],
                    7*60: [30, 15],
                    11*60: [30, 15],
                    15*60: [30, 15],
                    19*60: [30, 15],
                },
                '12h': {  # Cierres: 07:00, 19:00
                    7*60: [60],   # 1 hora antes
                    19*60: [60],
                },
                '1D': {  # Cierre: 19:00
                    19*60: [120, 60],  # 2 horas y 1 hora antes
                },
                '1W': {  # Cierre: Domingo 19:00
                    19*60: [240],  # 4 horas antes
                }
            }
            
            ventanas_tf = ventanas.get(timeframe, {})
            if not ventanas_tf:
                return False
            
            # Verificar si estamos dentro de alguna ventana
            for cierre_minutos, ventanas_minutos in ventanas_tf.items():
                for ventana_minutos in ventanas_minutos:
                    inicio_ventana = cierre_minutos - ventana_minutos
                    fin_ventana = cierre_minutos - 1
                    
                    if inicio_ventana <= minuto_actual <= fin_ventana:
                        hora_inicio = inicio_ventana // 60
                        min_inicio = inicio_ventana % 60
                        print(f"   📤 Telegram: Enviando {decision} en {timeframe} "
                              f"(ventana {ventana_minutos} min - {hora_inicio:02d}:{min_inicio:02d} a {cierre_minutos//60:02d}:{(cierre_minutos%60)-1:02d})")
                        return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error en should_send_telegram_alert: {e}")
            return False
        
    def get_top_indicators_for_chart(self, analysis, max_indicators=4):
        """
        Selecciona los indicadores más relevantes para el gráfico
        AHORA INCLUYE TODOS LOS INDICADORES DEL SISTEMA
        """
        try:
            if not analysis or not analysis.get('success'):
                return ['ftm', 'squeeze', 'rsi', 'volume']
            
            decision = analysis.get('decision', {}).get('action', '')
            votes = []
            
            # Recopilar votos de todas las capas
            if 'trend' in analysis and 'votes' in analysis['trend']:
                votes.extend(analysis['trend']['votes'])
            
            if 'momentum' in analysis and 'votes' in analysis['momentum']:
                votes.extend(analysis['momentum']['votes'])
            
            if 'volume' in analysis:
                if analysis['volume'].get('whale_buy', False):
                    votes.append({'source': 'whale_buy', 'weight': 50})
                if analysis['volume'].get('whale_sell', False):
                    votes.append({'source': 'whale_sell', 'weight': 50})
            
            # Mapa completo de TODOS los indicadores
            indicator_map = {
                # Maverick
                'rsi_maverick': ['rsi_maverick', 'rsi_maverick_extreme', 'rsi_maverick_rising'],
                'ftm': ['ftm', 'ftm_strength', 'ftm_fuerte', 'ftm_debil'],
                
                # Momentum
                'squeeze': ['squeeze', 'squeeze_momentum', 'squeeze_alcista', 'squeeze_bajista'],
                'macd': ['macd', 'macd_cross', 'macd_histogram'],
                'rsi': ['rsi', 'rsi_divergence', 'rsi_oversold', 'rsi_overbought'],
                'stochastic': ['stoch', 'estocastico', 'stoch_cross'],
                'williams': ['williams', 'williams_r'],
                'cci': ['cci'],
                
                # Volumen
                'whale': ['whale', 'ballenas', 'whale_buy', 'whale_sell'],
                'volume': ['volume', 'volumen'],
                'obv': ['obv'],
                'mfi': ['mfi'],
                'force': ['force', 'force_index'],
                
                # Tendencia
                'dmi': ['dmi', 'adx', 'plus_di', 'minus_di'],
                'supertrend': ['supertrend', 'st'],
                'ichimoku': ['ichimoku', 'tenkan', 'kijun'],
                'psar': ['psar', 'parabolic', 'parabolic_sar'],
                
                # Estructura
                'bollinger': ['bollinger', 'bb', 'bb_width'],
                'atr': ['atr'],
                'fvg': ['fvg', 'imbalance', 'fair_value_gap'],
                'order_blocks': ['order_block', 'ob'],
                'sweeps': ['sweep', 'liquidity_sweep'],
                'stop_hunts': ['stop_hunt', 'hunt'],
                
                # Otros
                'fibonacci': ['fib', 'fibonacci'],
                'volume_profile': ['profile', 'poc', 'value_area']
            }
            
            # Ponderar indicadores por peso de votos
            indicator_scores = {}
            for vote in votes:
                source = vote.get('source', '').lower()
                weight = vote.get('weight', 1)
                
                for indicator, keywords in indicator_map.items():
                    if any(keyword in source for keyword in keywords):
                        indicator_scores[indicator] = indicator_scores.get(indicator, 0) + weight
                        break
            
            # Si no hay votos, usar defaults según la decisión
            if not indicator_scores:
                default_map = {
                    'COMPRA_SPOT': ['rsi_maverick', 'squeeze', 'whale', 'macd'],
                    'LONG': ['rsi_maverick', 'squeeze', 'dmi', 'supertrend'],
                    'VENTA_SPOT': ['rsi', 'macd', 'dmi', 'volume'],
                    'SHORT': ['rsi', 'macd', 'ftm', 'bollinger']
                }
                return default_map.get(decision, ['ftm', 'squeeze', 'rsi', 'volume'])
            
            # Ordenar y seleccionar top N
            top_indicators = sorted(indicator_scores.items(), key=lambda x: x[1], reverse=True)
            selected = [ind[0] for ind in top_indicators[:max_indicators]]
            
            print(f"📊 Top indicadores seleccionados: {selected}")
            return selected
            
        except Exception as e:
            print(f"❌ Error en get_top_indicators_for_chart: {e}")
            return ['ftm', 'squeeze', 'rsi', 'volume']



# ============================================================================
# INSTANCIA GLOBAL DEL SISTEMA EXPERTO
# ============================================================================

expert_system = TradingExpertSystem()


# ============================================================================
# CLASE: LIQUIDATION HEATMAP (NUEVO INDICADOR)
# ============================================================================
# Ubicación: Después de la clase TradingExpertSystem y antes de la clase TraderBase

class LiquidationBin:
    """Representa un bin de liquidación con timestamp en lugar de índice"""
    def __init__(self, price_top, price_bottom, weight, side, timestamp, leverage):
        self.price_top = float(price_top)
        self.price_bottom = float(price_bottom)
        self.weight = float(weight)
        self.side = side
        self.created_at = timestamp
        self.frozen = False
        self.frozen_at = None
        self.leverage = int(leverage)
        self.spike_count = 1
        self.max_weight = float(weight)
        
    def to_dict(self):
        return {
            'price_top': self.price_top,
            'price_bottom': self.price_bottom,
            'weight': self.weight,
            'side': self.side,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'frozen': self.frozen,
            'frozen_at': self.frozen_at.isoformat() if self.frozen_at else None,
            'leverage': self.leverage,
            'spike_count': self.spike_count,
            'max_weight': self.max_weight
        }


class TradingZone:
    """
    Representa una zona de trading (COMPRA, VENTA, LONG, SHORT)
    con persistencia y transparencia dinámica
    """
    def __init__(self, zone_type, price_min, price_max, start_idx, confidence, source_traders):
        self.zone_type = zone_type  # 'COMPRA', 'VENTA', 'LONG', 'SHORT'
        self.price_min = float(price_min)
        self.price_max = float(price_max)
        self.created_at = start_idx
        self.last_updated = start_idx
        self.expires_at = start_idx + 20  # 20 velas de vida máxima
        self.confidence = float(confidence)  # 0-100
        self.source_traders = source_traders  # Lista de traders que apoyan
        self.veto_active = False
        self.veto_source = None
        self.opacity = 0.3  # Valor base, se ajusta por confianza
        self.active = True
        self.consecutive_absence = 0  # Velas sin soporte
        
    def update(self, new_confidence, new_source_traders, current_idx, veto=False, veto_source=None):
        """Actualiza la zona con nuevos valores"""
        self.last_updated = current_idx
        self.confidence = new_confidence
        self.source_traders = new_source_traders
        self.expires_at = current_idx + 20
        
        if veto:
            self.veto_active = True
            self.veto_source = veto_source
        else:
            self.veto_active = False
            self.veto_source = None
        
        # Ajustar opacidad basada en confianza y veto
        if self.veto_active:
            self.opacity = 0.15  # Más transparente con veto
        else:
            self.opacity = 0.2 + (self.confidence / 100) * 0.4  # Rango 0.2-0.6
        
        self.consecutive_absence = 0
        
    def decay(self):
        """Reduce la confianza si no hay soporte"""
        self.consecutive_absence += 1
        if self.consecutive_absence >= 3:
            self.confidence *= 0.7
            self.opacity *= 0.7
        
        if self.consecutive_absence >= 5 or self.confidence < 20:
            self.active = False
    
    def to_dict(self):
        """Para serialización JSON"""
        return {
            'zone_type': self.zone_type,
            'price_min': self.price_min,
            'price_max': self.price_max,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'confidence': self.confidence,
            'opacity': self.opacity,
            'veto_active': self.veto_active,
            'veto_source': self.veto_source,
            'source_traders': self.source_traders,
            'active': self.active
        }
class DynamicZones:
    """
    Sistema de zonas dinámicas de trading basado en consenso de traders
    """
    
    def __init__(self, symbol, timeframe):
        self.symbol = symbol
        self.timeframe = timeframe
        self.zones = {
            'COMPRA': None,
            'VENTA': None,
            'LONG': None,
            'SHORT': None
        }
        self.zone_history = []
        self.current_idx = 0
        self.last_price = 0
        
        # Parámetros de persistencia
        self.zone_lifetime = 20  # Velas máximas de vida
        self.smooth_factor = 0.3  # Factor de suavizado para cambios
        
        print(f"✅ Zonas dinámicas inicializadas para {symbol} {timeframe}")
    

    def calculate_zone_from_votes(self, accion, votos_por_accion, confianza_por_accion, 
                                   traders_por_accion, veto_info, current_price, current_idx, volatility=None):
        """
        Calcula las zonas basado en la votación actual
        CON EXPANSIÓN DINÁMICA POR CONFIANZA
        """
        self.current_idx = current_idx
        self.last_price = current_price
        
        # Obtener ATR de volatility layer si está disponible
        atr_pct = 0.02  # 2% por defecto
        if volatility and isinstance(volatility, dict):
            atr_pct = volatility.get('atr_pct', 2.0) / 100
        
        # ============ ZONA DE COMPRA ============
        compra_traders = traders_por_accion.get('COMPRA_SPOT', []) + traders_por_accion.get('LONG', [])
        compra_confianza = max(
            confianza_por_accion.get('COMPRA_SPOT', 0),
            confianza_por_accion.get('LONG', 0)
        )
        
        # Verificar veto del Escéptico
        veto_activo = False
        veto_source = None
        if veto_info and veto_info.get('accion') == 'NO_OPERAR' and veto_info.get('confianza', 0) >= 80:
            veto_activo = True
            veto_source = veto_info.get('trader', 'Escéptico')
            print(f"   ⚠️ Veto activo para zonas: {veto_source}")
        
        # Calcular rango de precio para COMPRA con expansión dinámica
        if compra_traders and compra_confianza > 30:
            # Factor de expansión basado en confianza y número de traders
            trust_factor = min(2.0, (compra_confianza / 50) * (len(compra_traders) / 5))
            expansion = atr_pct * (1 + trust_factor)
            
            # Si hay veto, reducir expansión
            if veto_activo:
                expansion *= 0.5
            
            # Zona COMPRA: más abajo que arriba (soporte)
            price_min = current_price * (1 - expansion * 1.8)
            price_max = current_price * (1 + expansion * 0.6)
            
            # Si la acción consenso es COMPRA, asegurar que el precio esté DENTRO
            if accion in ['COMPRA_SPOT', 'LONG'] and compra_confianza > 60:
                if current_price < price_min or current_price > price_max:
                    # Expandir zona para incluir precio actual
                    price_min = min(price_min, current_price * 0.98)
                    price_max = max(price_max, current_price * 1.02)
                    print(f"   🔧 Ajustando zona COMPRA para incluir precio actual")
            
            self._update_zone('COMPRA', price_min, price_max, compra_confianza, 
                              compra_traders, veto_activo, veto_source, current_idx)
        else:
            self._decay_zone('COMPRA')
        
        # ============ ZONA DE VENTA ============
        venta_traders = traders_por_accion.get('VENTA_SPOT', []) + traders_por_accion.get('SHORT', [])
        venta_confianza = max(
            confianza_por_accion.get('VENTA_SPOT', 0),
            confianza_por_accion.get('SHORT', 0)
        )
        
        if venta_traders and venta_confianza > 30:
            trust_factor = min(2.0, (venta_confianza / 50) * (len(venta_traders) / 5))
            expansion = atr_pct * (1 + trust_factor)
            
            if veto_activo:
                expansion *= 0.5
            
            # Zona VENTA: más arriba que abajo (resistencia)
            price_min = current_price * (1 - expansion * 0.6)
            price_max = current_price * (1 + expansion * 1.8)
            
            # Si la acción consenso es VENTA, asegurar que el precio esté DENTRO
            if accion in ['VENTA_SPOT', 'SHORT'] and venta_confianza > 60:
                if current_price < price_min or current_price > price_max:
                    price_min = min(price_min, current_price * 0.98)
                    price_max = max(price_max, current_price * 1.02)
                    print(f"   🔧 Ajustando zona VENTA para incluir precio actual")
            
            self._update_zone('VENTA', price_min, price_max, venta_confianza, 
                              venta_traders, veto_activo, veto_source, current_idx)
        else:
            self._decay_zone('VENTA')
        
        # ============ ZONA LONG (PRECISIÓN) ============
        long_traders = traders_por_accion.get('LONG', [])
        long_confianza = confianza_por_accion.get('LONG', 0)
        
        if long_traders and long_confianza > 65 and not veto_activo:
            trust_factor = min(1.5, (long_confianza / 70) * (len(long_traders) / 3))
            expansion = atr_pct * trust_factor
            
            # Zona LONG: simétrica y estrecha
            price_min = current_price * (1 - expansion)
            price_max = current_price * (1 + expansion)
            
            self._update_zone('LONG', price_min, price_max, long_confianza, 
                              long_traders, veto_activo, veto_source, current_idx)
        else:
            self._decay_zone('LONG')
        
        # ============ ZONA SHORT (PRECISIÓN) ============
        short_traders = traders_por_accion.get('SHORT', [])
        short_confianza = confianza_por_accion.get('SHORT', 0)
        
        if short_traders and short_confianza > 65 and not veto_activo:
            trust_factor = min(1.5, (short_confianza / 70) * (len(short_traders) / 3))
            expansion = atr_pct * trust_factor
            
            price_min = current_price * (1 - expansion)
            price_max = current_price * (1 + expansion)
            
            self._update_zone('SHORT', price_min, price_max, short_confianza, 
                              short_traders, veto_activo, veto_source, current_idx)
        else:
            self._decay_zone('SHORT')
        
        return self.get_active_zones()
    
    def _update_zone(self, zone_type, price_min, price_max, confidence, traders, veto, veto_source, idx):
        """Actualiza o crea una zona con suavizado"""
        if self.zones[zone_type] is None:
            # Crear nueva zona
            self.zones[zone_type] = TradingZone(
                zone_type, price_min, price_max, idx, confidence, traders
            )
            print(f"   🟢 Zona {zone_type} CREADA: ${price_min:.2f}-${price_max:.2f} (confianza {confidence:.1f}%)")
        else:
            # Suavizar cambios (media ponderada)
            old_zone = self.zones[zone_type]
            smoothed_min = old_zone.price_min * (1 - self.smooth_factor) + price_min * self.smooth_factor
            smoothed_max = old_zone.price_max * (1 - self.smooth_factor) + price_max * self.smooth_factor
            smoothed_conf = old_zone.confidence * (1 - self.smooth_factor) + confidence * self.smooth_factor
            
            old_zone.update(smoothed_conf, traders, idx, veto, veto_source)
            old_zone.price_min = smoothed_min
            old_zone.price_max = smoothed_max
            
            cambio = ((smoothed_min - old_zone.price_min) / old_zone.price_min * 100) if old_zone.price_min > 0 else 0
            print(f"   🔄 Zona {zone_type} ACTUALIZADA: ${smoothed_min:.2f}-${smoothed_max:.2f} (cambio {cambio:.1f}%)")
    
    def _decay_zone(self, zone_type):
        """Aplica decaimiento a una zona sin soporte"""
        if self.zones[zone_type] is not None:
            self.zones[zone_type].decay()
            if not self.zones[zone_type].active:
                print(f"   ⚰️ Zona {zone_type} DESACTIVADA por falta de soporte")
                self.zone_history.append(self.zones[zone_type].to_dict())
                self.zones[zone_type] = None
    
    def get_active_zones(self):
        """Retorna las zonas activas para frontend"""
        result = {}
        for zone_type, zone in self.zones.items():
            if zone is not None and zone.active:
                result[zone_type] = zone.to_dict()
        return result
    
    def get_price_status(self, current_price):
        """
        Determina el estado del precio respecto a las zonas
        Retorna: (estado_texto, direccion, distancia_compra, distancia_venta)
        """
        estado = "sin dirección definida"
        direccion = "neutral"
        dist_compra = None
        dist_venta = None
        dist_long = None
        dist_short = None
        
        # Calcular distancias a zonas principales
        if self.zones['COMPRA'] and self.zones['COMPRA'].active:
            centro_compra = (self.zones['COMPRA'].price_min + self.zones['COMPRA'].price_max) / 2
            dist_compra = (centro_compra - current_price) / current_price * 100
        
        if self.zones['VENTA'] and self.zones['VENTA'].active:
            centro_venta = (self.zones['VENTA'].price_min + self.zones['VENTA'].price_max) / 2
            dist_venta = (centro_venta - current_price) / current_price * 100
        
        if self.zones['LONG'] and self.zones['LONG'].active:
            centro_long = (self.zones['LONG'].price_min + self.zones['LONG'].price_max) / 2
            dist_long = (centro_long - current_price) / current_price * 100
        
        if self.zones['SHORT'] and self.zones['SHORT'].active:
            centro_short = (self.zones['SHORT'].price_min + self.zones['SHORT'].price_max) / 2
            dist_short = (centro_short - current_price) / current_price * 100
        
        # Determinar posición relativa
        dentro_compra = False
        dentro_venta = False
        dentro_long = False
        dentro_short = False
        
        if self.zones['COMPRA'] and self.zones['COMPRA'].active:
            dentro_compra = (current_price >= self.zones['COMPRA'].price_min and 
                            current_price <= self.zones['COMPRA'].price_max)
        
        if self.zones['VENTA'] and self.zones['VENTA'].active:
            dentro_venta = (current_price >= self.zones['VENTA'].price_min and 
                           current_price <= self.zones['VENTA'].price_max)
        
        if self.zones['LONG'] and self.zones['LONG'].active:
            dentro_long = (current_price >= self.zones['LONG'].price_min and 
                          current_price <= self.zones['LONG'].price_max)
        
        if self.zones['SHORT'] and self.zones['SHORT'].active:
            dentro_short = (current_price >= self.zones['SHORT'].price_min and 
                           current_price <= self.zones['SHORT'].price_max)
        
        # Clasificar estado
        if dentro_long:
            estado = "Dentro de zona LONG"
            direccion = "alcista_fuerte"
        elif dentro_short:
            estado = "Dentro de zona SHORT"
            direccion = "bajista_fuerte"
        elif dentro_compra:
            estado = "Dentro de zona de COMPRA"
            direccion = "alcista"
        elif dentro_venta:
            estado = "Dentro de zona de VENTA"
            direccion = "bajista"
        else:
            # Está entre zonas
            if dist_compra is not None and dist_venta is not None:
                if abs(dist_compra) < abs(dist_venta):
                    if dist_compra < 0:
                        estado = "Cerca de zona COMPRA en dirección alcista"
                        direccion = "alcista"
                    else:
                        estado = "Cerca de zona COMPRA en dirección bajista"
                        direccion = "bajista"
                else:
                    if dist_venta < 0:
                        estado = "Cerca de zona VENTA en dirección alcista"
                        direccion = "alcista"
                    else:
                        estado = "Cerca de zona VENTA en dirección bajista"
                        direccion = "bajista"
            elif dist_compra is not None:
                estado = "En el medio en dirección a zona COMPRA"
                direccion = "alcista" if dist_compra < 0 else "bajista"
            elif dist_venta is not None:
                estado = "En el medio en dirección a zona VENTA"
                direccion = "bajista" if dist_venta > 0 else "alcista"
            else:
                estado = "En el medio sin dirección definida"
                direccion = "neutral"
        
        return {
            'estado': estado,
            'direccion': direccion,
            'distancia_compra': dist_compra,
            'distancia_venta': dist_venta,
            'distancia_long': dist_long,
            'distancia_short': dist_short,
            'dentro_compra': dentro_compra,
            'dentro_venta': dentro_venta,
            'dentro_long': dentro_long,
            'dentro_short': dentro_short
        }


class LiquidationHeatmap:
    """
    Mapa de calor de liquidaciones - VERSIÓN CORREGIDA CON 3 CRITERIOS DE TOQUE
    """
    
    def __init__(self, timeframe='4h', max_bins_per_side=500):
        self.timeframe = timeframe
        self.max_bins_per_side = max_bins_per_side
        
        # ============ APALANCAMIENTOS POR TEMPORALIDAD ============
        # Mapa completo con soporte para TF cortas (futuros) y largas (spot)
        tf_config = {
            # Temporalidades cortas (futuros) - más liquidaciones agresivas
            '5m':  {'leverages': [75, 50, 25, 20, 15], 'min_volume': 0.05, 'step_multiplier': 0.7, 'disp_pct': 0.10, 'tolerance_pct': 0.5},
            '15m': {'leverages': [50, 25, 20, 15, 10], 'min_volume': 0.08, 'step_multiplier': 0.8, 'disp_pct': 0.15, 'tolerance_pct': 0.7},
            '30m': {'leverages': [50, 25, 20, 15, 10], 'min_volume': 0.09, 'step_multiplier': 0.9, 'disp_pct': 0.18, 'tolerance_pct': 0.9},
            '1h':  {'leverages': [50, 25, 20, 15, 10], 'min_volume': 0.10, 'step_multiplier': 1.0, 'disp_pct': 0.20, 'tolerance_pct': 1.0},
            '2h':  {'leverages': [50, 25, 20, 15, 10], 'min_volume': 0.10, 'step_multiplier': 1.0, 'disp_pct': 0.20, 'tolerance_pct': 1.0},
            # Temporalidades largas (spot)
            '4h':  {'leverages': [50, 25, 20, 15, 10], 'min_volume': 0.1, 'step_multiplier': 1.0, 'disp_pct': 0.20, 'tolerance_pct': 1.0},
            '12h': {'leverages': [25, 20, 15, 10, 5],  'min_volume': 0.2, 'step_multiplier': 1.3, 'disp_pct': 0.25, 'tolerance_pct': 1.5},
            '1D':  {'leverages': [20, 15, 10, 7, 5],   'min_volume': 0.3, 'step_multiplier': 1.6, 'disp_pct': 0.30, 'tolerance_pct': 2.0},
            '1W':  {'leverages': [10, 7, 5, 3, 2],     'min_volume': 0.5, 'step_multiplier': 2.0, 'disp_pct': 0.35, 'tolerance_pct': 3.0}
        }
        
        # Configuración por defecto (fallback) para timeframes no reconocidos
        cfg = tf_config.get(timeframe, tf_config['4h'])
        
        self.leverages = cfg['leverages']
        self.min_volume = cfg['min_volume']
        self.step_multiplier = cfg['step_multiplier']
        self.disp_pct = cfg['disp_pct']
        self.tolerance_pct = cfg['tolerance_pct']
        
        # ============ CONFIGURACIÓN BASE ============
        self.use_wicks = True
        self.scale_ticks = 600
        self.extend_bars = 500
        
        # ============ ESTRUCTURAS DE DATOS ============
        self.all_bins = []
        self.frozen_bins = []
        self.price_history = []
        
        # Estadísticas
        self.total_events = 0
        self.last_event_timestamp = None
        self.current_timestamp = None
        self.history_loaded = False
        self.current_idx = 0
        
        print(f"✅ Heatmap {timeframe} - leverages={self.leverages}")
    
    def load_price_history(self, df):
        """Carga TODO el historial de precios disponible al inicio"""
        if self.history_loaded:
            return
        
        print(f"   📥 Cargando historial de {len(df)} velas para {self.timeframe}")
        
        for i in range(len(df)):
            timestamp = df['time'].iloc[i]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            
            self.price_history.append({
                'timestamp': timestamp,
                'high': df['high'].iloc[i],
                'low': df['low'].iloc[i]
            })
        
        self.history_loaded = True
        print(f"   ✅ Historial cargado: {len(self.price_history)} velas")
    
    def get_step_size(self, price):
        """Tamaño de bin con ajuste especial para PAXG/BTC"""
        if price > 10000:
            return 50.0 * self.step_multiplier
        elif price > 1000:
            return 5.0 * self.step_multiplier
        else:
            base = 0.0001
            return base * self.step_multiplier
    
    def get_bin_extremes(self, price):
        step = self.get_step_size(price)
        bottom = math.floor(price / step) * step
        top = bottom + step
        return top, bottom
    
    def calculate_liq_price(self, ref_price, leverage, is_long):
        if leverage <= 0:
            return None
        if is_long:
            return ref_price * (1.0 - 1.0 / leverage)
        else:
            return ref_price * (1.0 + 1.0 / leverage)
    
    def get_color_from_weight(self, weight, max_weight):
        if max_weight <= 0:
            return 'rgba(0, 100, 0, 0.2)'
        
        ratio = weight / max_weight
        ratio = min(1.0, max(0.0, ratio))
        
        if ratio > 0.8:
            return 'rgba(255, 0, 0, 0.7)'
        elif ratio > 0.6:
            return 'rgba(255, 165, 0, 0.6)'
        elif ratio > 0.4:
            return 'rgba(255, 255, 0, 0.5)'
        elif ratio > 0.2:
            return 'rgba(144, 238, 144, 0.4)'
        else:
            return 'rgba(0, 100, 0, 0.3)'
    
    def update_heatmap(self, df, current_idx, high, low, close, volume):
        """Genera bins en CADA vela usando TIMESTAMPS"""
        if not self.history_loaded:
            self.load_price_history(df)
        
        self.current_idx = current_idx
        self.current_timestamp = df['time'].iloc[current_idx]
        if isinstance(self.current_timestamp, str):
            self.current_timestamp = datetime.fromisoformat(self.current_timestamp.replace('Z', '+00:00'))
        
        # Volumen en millones
        volume_m = volume / 1000
        print(f"   📊 Volumen: {volume:.2f}K = {volume_m:.2f}M USD")
        
        if volume_m < self.min_volume:
            volume_m = self.min_volume
            print(f"   ⚠️ Usando volumen mínimo {self.min_volume}M para {self.timeframe}")
        
        is_up = close >= df['open'].iloc[current_idx]
        
        if is_up:
            long_flow = volume_m * 0.7
            short_flow = volume_m * 0.3
        else:
            long_flow = volume_m * 0.3
            short_flow = volume_m * 0.7
        
        lev_count = len(self.leverages)
        per_lev_long = long_flow / lev_count
        per_lev_short = short_flow / lev_count
        
        # Asegurar peso mínimo
        if per_lev_long < 0.01:
            per_lev_long = 0.01
        if per_lev_short < 0.01:
            per_lev_short = 0.01
        
        print(f"   💰 Flujo LONG: {long_flow:.2f}M, SHORT: {short_flow:.2f}M")
        print(f"   ⚖️ Por leverage: LONG={per_lev_long:.3f}M, SHORT={per_lev_short:.3f}M")
        
        ref_price = close
        bins_creados = 0
        
        for lev in self.leverages:
            if lev <= 0:
                continue
            
            liq_long = ref_price * (1.0 - 1.0 / lev)
            if liq_long > 0:
                step = self.get_step_size(ref_price)
                bottom = math.floor(liq_long / step) * step
                top = bottom + step
                self._add_bin('long', top, bottom, per_lev_long, self.current_timestamp, lev)
                bins_creados += 1
            
            liq_short = ref_price * (1.0 + 1.0 / lev)
            if liq_short > 0:
                step = self.get_step_size(ref_price)
                bottom = math.floor(liq_short / step) * step
                top = bottom + step
                self._add_bin('short', top, bottom, per_lev_short, self.current_timestamp, lev)
                bins_creados += 1
        
        if bins_creados > 0:
            self.total_events += 1
            self.last_event_timestamp = self.current_timestamp
        
        # ============ NUEVO: Verificar bins tocados en la vela ACTUAL ============
        bins_congelados_actual = self._check_touched_bins(high, low)
        if bins_congelados_actual > 0:
            print(f"   ❄️ Total congelados en vela actual: {bins_congelados_actual}")
        # =========================================================================
        
        print(f"   📦 Total bins creados en esta vela: {bins_creados}")
        return self._get_stats()
    
    def _add_bin(self, side, price_top, price_bottom, weight, timestamp, leverage):
        """Añade un nuevo bin con timestamp - CORREGIDO"""
        # ============ CORRECCIÓN: Asegurar peso > 0 ============
        if weight <= 0:
            weight = 0.01
            print(f"   ⚠️ Peso ajustado a 0.01M para {side} ${price_top:.2f}")
        
        new_bin = LiquidationBin(
            price_top, price_bottom, weight, side, timestamp, leverage
        )
        new_bin.max_weight = weight
        self.all_bins.append(new_bin)
        
        if len(self.all_bins) % 50 == 0:
            print(f"   ✅ [{self.timeframe}] +50 bins - total: {len(self.all_bins)} (último: ${price_top:.2f})")
        elif len(self.all_bins) <= 10:
            print(f"   ✅ [{self.timeframe}] Nuevo bin {side} ${price_top:.2f} (peso: {weight:.2f}M, lev:{leverage}x)")
    
    def _check_touched_bins(self, high, low):
        """Congela bins tocados por el precio en la vela ACTUAL - VERSIÓN QUE FUNCIONABA"""
        touched = 0
        # Usar copia para poder eliminar mientras se itera
        for bin_obj in self.all_bins[:]:
            if bin_obj.frozen:
                continue
            
            # Verificar si el precio toca el bin
            if self.use_wicks:
                touched_now = (high > bin_obj.price_bottom and low < bin_obj.price_top)
            else:
                avg = (high + low) / 2
                touched_now = (avg > bin_obj.price_bottom and avg < bin_obj.price_top)
            
            if touched_now:
                bin_obj.frozen = True
                bin_obj.frozen_at = self.current_timestamp
                self.all_bins.remove(bin_obj)
                self.frozen_bins.append(bin_obj)
                touched += 1
                print(f"   ❄️ [{self.timeframe}] Bin {bin_obj.side} CONGELADO (actual) ${bin_obj.price_top:.2f} (peso: {bin_obj.weight:.1f}M)")
        
        return touched    
    
    
    
    def _check_bin_touched(self, bin_obj, high, low, price_point_idx=None):
        """
        Verifica si un bin fue tocado por UNA VELA específica
        CON TOLERANCIA DINÁMICA (1% para 4h, 2% para 1D, etc.)
        """
        avg_price = (high + low) / 2
        tolerance = avg_price * (self.tolerance_pct / 100) if hasattr(self, 'tolerance_pct') else avg_price * 0.01
        
        # Expandir los bordes del bin con la tolerancia
        expanded_bottom = bin_obj.price_bottom - tolerance
        expanded_top = bin_obj.price_top + tolerance
        
        # Verificar si el precio toca el bin expandido
        if high >= expanded_bottom and low <= expanded_top:
            if price_point_idx is not None and price_point_idx % 10 == 0:
                print(f"      🔴 TOCADO (tol {self.tolerance_pct if hasattr(self, 'tolerance_pct') else 1.0}%): high={high:.2f} low={low:.2f}")
            return True
        
        return False
    
    def _check_bin_against_history(self, bin_obj):
        """
        Verifica si un bin fue tocado en ALGÚN momento del historial POSTERIOR
        CON TOLERANCIA Y LOGS DETALLADOS
        """
        toques_encontrados = 0
        
        for idx, price_point in enumerate(self.price_history):
            if price_point['timestamp'] <= bin_obj.created_at:
                continue
            
            if self._check_bin_touched(bin_obj, price_point['high'], price_point['low'], idx):
                toques_encontrados += 1
                ts_str = price_point['timestamp'].strftime('%Y-%m-%d %H:%M')
                print(f"      ✅ BIN TOCADO (histórico): {bin_obj.side} ${bin_obj.price_top:.2f} en vela {idx} ({ts_str})")
                
                # Si encontramos UN toque, ya es suficiente
                if toques_encontrados == 1:
                    return True, price_point['timestamp']
        
        return False, None
    
    def _get_stats(self):
        """Retorna estadísticas actuales del heatmap"""
        total_long_weight = sum(b.weight for b in self.all_bins if b.side == 'long')
        total_short_weight = sum(b.weight for b in self.all_bins if b.side == 'short')
        total_long_bins = len([b for b in self.all_bins if b.side == 'long'])
        total_short_bins = len([b for b in self.all_bins if b.side == 'short'])
        
        # Log cada 10 llamadas para no saturar
        if self.current_idx % 10 == 0:
            print(f"   📊 Stats - Long: {total_long_bins} bins, {total_long_weight:.1f}M | Short: {total_short_bins} bins, {total_short_weight:.1f}M")
        
        return {
            'total_active': len(self.all_bins),
            'total_frozen': len(self.frozen_bins),
            'total_long_weight': total_long_weight,
            'total_short_weight': total_short_weight,
            'total_long_bins': total_long_bins,
            'total_short_bins': total_short_bins
        }
    
    def get_heatmap_data(self, current_idx, current_price):
        """
        Reprocesa bins contra TODO el historial - VERSIÓN CORREGIDA
        """
        if current_idx is not None:
            self.current_idx = current_idx
        
        print(f"\n🔄 [{self.timeframe}] VERIFICANDO {len(self.all_bins)} bins contra {len(self.price_history)} velas históricas")
        print(f"   📊 Criterios: cruce directo + toque de mechas")
        
        if self.price_history:
            first_ts = self.price_history[0]['timestamp'].strftime('%Y-%m-%d')
            last_ts = self.price_history[-1]['timestamp'].strftime('%Y-%m-%d')
            print(f"   📅 Rango historial: {first_ts} a {last_ts}")
        
        # ============ REPROCESAR BINS CONTRA TODO EL HISTORIAL ============
        nuevos_congelados = 0
        frozen_antes = len(self.frozen_bins)
        bins_verificados = 0
        
        for bin_obj in self.all_bins[:]:
            if bin_obj.frozen:
                continue
            
            bins_verificados += 1
            tocado, ts_tocado = self._check_bin_against_history(bin_obj)
            
            if tocado:
                bin_obj.frozen = True
                bin_obj.frozen_at = ts_tocado
                self.all_bins.remove(bin_obj)
                self.frozen_bins.append(bin_obj)
                nuevos_congelados += 1
                
                if nuevos_congelados % 5 == 0:
                    ts_str = ts_tocado.strftime('%Y-%m-%d') if ts_tocado else 'desconocido'
                    print(f"   ✅ [{self.timeframe}] +5 bins congelados (total: {nuevos_congelados}) - último: ${bin_obj.price_top:.2f} en {ts_str}")
        
        if nuevos_congelados > 0:
            pct_congelados = nuevos_congelados / max(1, bins_verificados) * 100
            print(f"   📌 Total congelados en este reproceso: {nuevos_congelados} ({pct_congelados:.1f}% de verificados)")
            print(f"   📊 Total frozen_bins AHORA: {len(self.frozen_bins)} (antes: {frozen_antes})")
        else:
            print(f"   ⚠️ No se congelaron bins en este reproceso")
            
            if self.all_bins and self.price_history:
                ultimo_precio = self.price_history[-1]
                avg_price = (ultimo_precio['high'] + ultimo_precio['low']) / 2
                
                distancias = []
                for bin_obj in self.all_bins[:50]:
                    bin_center = (bin_obj.price_top + bin_obj.price_bottom) / 2
                    distancia = abs(avg_price - bin_center)
                    distancia_pct = distancia / avg_price * 100
                    distancias.append((distancia_pct, bin_obj))
                
                distancias.sort(key=lambda x: x[0])
                print(f"   📊 Top 10 bins más cercanos al precio actual (${avg_price:.2f}):")
                for i, (pct, bin_obj) in enumerate(distancias[:10]):
                    print(f"      {i+1}. {bin_obj.side} ${bin_obj.price_top:.2f} a {pct:.2f}%")
        
        # ============ PREPARAR DATOS PARA FRONTEND ============
        if not self.all_bins and not self.frozen_bins:
            print(f"\n📊 [{self.timeframe}] HEATMAP DATA: Sin datos")
            return self._empty_data()
        
        all_weights = [b.max_weight for b in self.all_bins + self.frozen_bins]
        max_weight = max(all_weights) if all_weights else 1
        
        active_bins = []
        for bin_obj in self.all_bins:
            bin_dict = bin_obj.to_dict()
            bin_dict['color'] = self.get_color_from_weight(bin_obj.max_weight, max_weight)
            bin_dict['border_style'] = 'solid'
            active_bins.append(bin_dict)
        
        frozen_bins = []
        for bin_obj in self.frozen_bins:
            bin_dict = bin_obj.to_dict()
            base_color = self.get_color_from_weight(bin_obj.max_weight, max_weight)
            bin_dict['color'] = base_color.replace('0.7', '0.2').replace('0.6', '0.15').replace('0.5', '0.1').replace('0.4', '0.08').replace('0.3', '0.05')
            bin_dict['border_style'] = 'dotted'
            frozen_bins.append(bin_dict)
        
        total_long_weight = sum(b.weight for b in self.all_bins if b.side == 'long')
        total_short_weight = sum(b.weight for b in self.all_bins if b.side == 'short')
        total_long_bins = len([b for b in self.all_bins if b.side == 'long'])
        total_short_bins = len([b for b in self.all_bins if b.side == 'short'])
        total_bins = len(active_bins) + len(frozen_bins)
        
        print(f"\n📊 [{self.timeframe}] HEATMAP DATA:")
        print(f"   Bins activos: {len(active_bins)} (L:{total_long_bins} S:{total_short_bins})")
        print(f"   Bins congelados: {len(frozen_bins)}")
        print(f"   Long weight: {total_long_weight:.1f}M, Short weight: {total_short_weight:.1f}M")
        print(f"   % congelados: {len(frozen_bins)/max(1,total_bins)*100:.1f}% ({len(frozen_bins)}/{total_bins})")
        
        return {
            'active_bins': active_bins,
            'frozen_bins': frozen_bins,
            'total_long_bins': total_long_bins,
            'total_short_bins': total_short_bins,
            'total_long_weight': total_long_weight,
            'total_short_weight': total_short_weight,
            'last_spike_bar': self.last_event_timestamp.isoformat() if self.last_event_timestamp else None,
            'total_spikes': self.total_events,
            'total_bins_historical': total_bins
        }
    
    def _empty_data(self):
        return {
            'active_bins': [],
            'frozen_bins': [],
            'total_long_bins': 0,
            'total_short_bins': 0,
            'total_long_weight': 0,
            'total_short_weight': 0,
            'last_spike_bar': None,
            'total_spikes': 0,
            'total_bins_historical': 0
        }


# ============================================================================
# CLASES DE LOS 9 TRADERS (SISTEMA DE RAZONAMIENTO AVANZADO)
# ============================================================================

class TraderBase:
    """Clase base para todos los traders"""
    
    def __init__(self, nombre, especialidad, peso_base=1.0):
        self.nombre = nombre
        self.especialidad = especialidad
        self.peso_base = peso_base  # Peso en votación (1.0 = normal)
        
    def votar(self, capas, symbol, timeframe):
        """
        Cada trader implementa su lógica de votación.
        Retorna: (accion, confianza, estrategias_detectadas, razones)
        - accion: COMPRA_SPOT, VENTA_SPOT, LONG, SHORT, ESPERAR, NO_OPERAR
        - confianza: 0-100
        - estrategias_detectadas: lista de nombres de estrategias que vio
        - razones: lista de strings con argumentos
        """
        raise NotImplementedError
        
    def ponderar_por_especialidad(self, voto_base):
        """Ajustar el peso del voto según la especialidad y el contexto"""
        return voto_base * self.peso_base


class TraderTecnico(TraderBase):
    """Trader 1: Técnico Puro - Basado en indicadores técnicos clásicos"""
    
    def __init__(self):
        super().__init__("Técnico Puro", "indicadores", peso_base=1.2)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            # ============ LOG DE INICIO ============
            print(f"\n📊 TRADER TÉCNICO - {symbol} {timeframe}")
            
            trend = capas.get('trend', {})
            momentum = capas.get('momentum', {})
            volatility = capas.get('volatility', {})
            
            if not isinstance(trend, dict) or not isinstance(momentum, dict):
                print(f"   ⚠️ Datos insuficientes")
                return accion, confianza, estrategias, razones
            
            # Extraer datos relevantes
            adx = trend.get('adx', 0)
            direccion_trend = trend.get('direction', 'neutral')
            rsi = momentum.get('indicators', {}).get('rsi', 50)
            rsi_maverick = momentum.get('indicators', {}).get('rsi_maverick', 0.5)
            bb_position = volatility.get('bb_position', 0.5)
            
            print(f"   📊 ADX: {adx:.1f}, Dirección: {direccion_trend}, RSI: {rsi:.1f}, RSI_M: {rsi_maverick:.2f}")
            
            # ============ ESTRATEGIA 1: PULLBACK TENDENCIA ============
            if (adx > 25 and 
                direccion_trend == 'bullish' and
                rsi > 40 and rsi < 70 and
                volatility.get('bb_position', 0.5) < 0.3):
                
                accion = 'COMPRA_SPOT' if timeframe in ['1D', '12h'] else 'LONG'
                confianza = min(85, 60 + (adx - 25) * 2)
                estrategias.append('PULLBACK_TENDENCIA')
                razones.append(f"ADX en {adx:.1f} confirma tendencia alcista")
                razones.append(f"RSI en {rsi:.1f} muestra espacio para subir")
                razones.append("Precio cerca de soporte dinámico (banda inferior)")
                print(f"   ✅ ESTRATEGIA: PULLBACK_TENDENCIA - {accion} ({confianza:.0f}%)")
                
            # ============ ESTRATEGIA 2: TENDENCIA FUERTE ============
            elif (adx > 30 and 
                  direccion_trend == 'bullish' and
                  momentum.get('score', 0) > 5):
                
                accion = 'LONG' if timeframe == '4h' else 'COMPRA_SPOT'
                confianza = min(90, 70 + (adx - 30) * 2)
                estrategias.append('TENDENCIA_FUERTE')
                razones.append(f"ADX en {adx:.1f} indica tendencia extremadamente fuerte")
                razones.append("Momentum positivo confirma fuerza")
                print(f"   ✅ ESTRATEGIA: TENDENCIA_FUERTE - {accion} ({confianza:.0f}%)")
                
            # ============ ESTRATEGIA 3: SOBREVENTA ============
            elif (rsi < 30 and 
                  rsi_maverick < 0.2 and
                  direccion_trend in ['neutral', 'bullish']):
                
                accion = 'COMPRA_SPOT'
                confianza = 70
                estrategias.append('SOBREVENTA')
                razones.append(f"RSI en {rsi:.1f} indica condición de sobreventa")
                razones.append("RSI Maverick en zona extrema de acumulación")
                print(f"   ✅ ESTRATEGIA: SOBREVENTA - {accion} ({confianza:.0f}%)")
                
            # ============ ESTRATEGIA 4: SOBRECOMPRA ============
            elif (rsi > 70 and 
                  rsi_maverick > 0.8 and
                  direccion_trend in ['neutral', 'bearish']):
                
                accion = 'VENTA_SPOT'
                confianza = 70
                estrategias.append('SOBRECOMPRA')
                razones.append(f"RSI en {rsi:.1f} indica condición de sobrecompra")
                razones.append("RSI Maverick en zona extrema de distribución")
                print(f"   ✅ ESTRATEGIA: SOBRECOMPRA - {accion} ({confianza:.0f}%)")
            
            # ============ ESTRATEGIAS DE BANDAS DE BOLLINGER ============
            bb_width = volatility.get('bb_width', 0)
            squeeze_on = volatility.get('squeeze_on', False)
            squeeze_length = volatility.get('squeeze_length', 0)
            
            # Guardar acción y confianza actuales
            accion_actual = accion
            confianza_actual = confianza
            
            # ESTRATEGIA 5: SQUEEZE_ALCISTA
            if squeeze_on and squeeze_length >= 2 and bb_width < 2.0:
                if momentum.get('direction') == 'bullish' and momentum.get('score', 0) > 3:
                    accion_temp = 'LONG' if timeframe == '4h' and symbol == 'BTC-USDT' else 'COMPRA_SPOT'
                    if confianza_actual < 75:
                        accion_actual = accion_temp
                        confianza_actual = 75
                        if 'SQUEEZE_ALCISTA' not in estrategias:
                            estrategias.append('SQUEEZE_ALCISTA')
                            razones.append(f"Squeeze de Bollinger de {squeeze_length} velas anticipando expansión alcista")
                            print(f"   ✅ ESTRATEGIA: SQUEEZE_ALCISTA - {accion_temp} (75%)")
            
            # ESTRATEGIA 6: SQUEEZE_BAJISTA
            if squeeze_on and squeeze_length >= 2 and bb_width < 2.0:
                if momentum.get('direction') == 'bearish' and momentum.get('score', 0) < -3:
                    accion_temp = 'SHORT' if timeframe == '4h' and symbol == 'BTC-USDT' else 'VENTA_SPOT'
                    if confianza_actual < 75:
                        accion_actual = accion_temp
                        confianza_actual = 75
                        if 'SQUEEZE_BAJISTA' not in estrategias:
                            estrategias.append('SQUEEZE_BAJISTA')
                            razones.append(f"Squeeze de Bollinger de {squeeze_length} velas anticipando expansión bajista")
                            print(f"   ✅ ESTRATEGIA: SQUEEZE_BAJISTA - {accion_temp} (75%)")
            
            # ESTRATEGIA 7: BAND_WALK_ALCISTA
            if bb_position > 0.9 and not squeeze_on:
                if adx > 25 and direccion_trend == 'bullish':
                    if confianza_actual < 80:
                        confianza_actual = 80
                        if 'BAND_WALK_ALCISTA' not in estrategias:
                            estrategias.append('BAND_WALK_ALCISTA')
                            razones.append("Precio caminando sobre banda superior de Bollinger, tendencia fuerte confirmada")
                            print(f"   ✅ ESTRATEGIA: BAND_WALK_ALCISTA - {accion_actual} (80%)")
            
            # ESTRATEGIA 8: BAND_WALK_BAJISTA
            if bb_position < 0.1 and not squeeze_on:
                if adx > 25 and direccion_trend == 'bearish':
                    if confianza_actual < 80:
                        confianza_actual = 80
                        if 'BAND_WALK_BAJISTA' not in estrategias:
                            estrategias.append('BAND_WALK_BAJISTA')
                            razones.append("Precio caminando bajo banda inferior de Bollinger, tendencia bajista fuerte")
                            print(f"   ✅ ESTRATEGIA: BAND_WALK_BAJISTA - {accion_actual} (80%)")
            
            # ESTRATEGIA 9: EXPANSION_VOLATILIDAD
            if bb_width > 5.0 and bb_width > volatility.get('bb_width_prev', 0) * 1.5:
                if direccion_trend == 'bullish':
                    if confianza_actual < 70:
                        confianza_actual = 70
                        if 'EXPANSION_VOLATILIDAD' not in estrategias:
                            estrategias.append('EXPANSION_VOLATILIDAD')
                            razones.append(f"Expansión brusca de volatilidad (ancho de banda {bb_width:.1f}%), confirmando movimiento")
                            print(f"   ✅ ESTRATEGIA: EXPANSION_VOLATILIDAD - {accion_actual} (70%)")
            
            # Actualizar acción y confianza
            if accion_actual != accion or confianza_actual > confianza:
                accion = accion_actual
                confianza = confianza_actual
            
            # ============ LOG DE RESULTADO ============
            if accion != 'NO_OPERAR':
                print(f"   ✅ Decisión: {accion} (confianza {confianza:.0f}%) - Estrategias: {estrategias}")
            else:
                print(f"   ⚪ No se detectó estrategia - Decisión: NO_OPERAR")
            
        except Exception as e:
            print(f"❌ Error en TraderTecnico.votar: {e}")
            import traceback
            traceback.print_exc()
        
        return accion, confianza, estrategias, razones

class TraderChartista(TraderBase):
    """Trader 2: Chartista - Basado en patrones de velas y figuras chartistas"""
    
    def __init__(self):
        super().__init__("Chartista", "patrones", peso_base=1.3)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            structure = capas.get('structure', {})
            patterns = structure.get('patterns', {})
            recent = patterns.get('recent_patterns', [])
            bullish_count = patterns.get('bullish_count', 0)
            bearish_count = patterns.get('bearish_count', 0)
            high_quality = patterns.get('high_quality_patterns', [])
            
            # ============ LOG INICIAL ============
            print(f"\n📊 TRADER CHARTISTA - {symbol} {timeframe}")
            print(f"   Patrones totales: {len(recent)}")
            print(f"   Alta calidad: {len(high_quality)}")
            print(f"   Alcistas: {bullish_count}, Bajistas: {bearish_count}")
            
            # Mostrar patrones de alta calidad detectados
            if high_quality:
                print(f"   Patrones de alta calidad:")
                for pattern in high_quality[:5]:  # Mostrar primeros 5
                    nombre = pattern.get('name', '')
                    direccion = pattern.get('direction', 'neutral')
                    reliability = pattern.get('reliability', 0)
                    print(f"      - {nombre} ({direccion}) con {reliability}%")
            
            # Buscar patrones de alta calidad (reliability >= 80)
            for pattern in high_quality:
                if not isinstance(pattern, dict):
                    continue
                    
                nombre = pattern.get('name', '')
                direccion = pattern.get('direction', 'neutral')
                reliability = pattern.get('reliability', 0)
                
                # ============ ESTRATEGIA 5: HCH INVERTIDO ============
                if 'HCH Invertido' in nombre and direccion == 'bullish':
                    accion = 'COMPRA_SPOT'
                    confianza = max(confianza, reliability)
                    estrategias.append('HCH_INVERTIDO')
                    razones.append(f"Patrón HCH Invertido completado con {reliability}% confianza")
                    print(f"   ✅ ESTRATEGIA: HCH_INVERTIDO detectado con {reliability}%")
                    
                # ============ ESTRATEGIA 6: DOBLE SUELO ============
                elif 'Doble Suelo' in nombre and direccion == 'bullish':
                    accion = 'COMPRA_SPOT'
                    confianza = max(confianza, reliability)
                    estrategias.append('DOBLE_SUELO')
                    razones.append(f"Patrón de Doble Suelo confirmado con {reliability}% confianza")
                    print(f"   ✅ ESTRATEGIA: DOBLE_SUELO detectado con {reliability}%")
                    
                # ============ ESTRATEGIA 7: DOBLE TECHO ============
                elif 'Doble Techo' in nombre and direccion == 'bearish':
                    accion = 'VENTA_SPOT'
                    confianza = max(confianza, reliability)
                    estrategias.append('DOBLE_TECHO')
                    razones.append(f"Patrón de Doble Techo confirmado con {reliability}% confianza")
                    print(f"   ✅ ESTRATEGIA: DOBLE_TECHO detectado con {reliability}%")
                    
                # ============ ESTRATEGIA 8: BANDERA/BANDERÍN ============
                elif ('Bandera' in nombre or 'Banderín' in nombre) and direccion == 'bullish':
                    accion = 'LONG' if timeframe == '4h' else 'COMPRA_SPOT'
                    confianza = max(confianza, reliability)
                    estrategias.append('BANDERA_ALCISTA')
                    razones.append(f"Patrón de {nombre} detectado, típico de continuación alcista")
                    print(f"   ✅ ESTRATEGIA: BANDERA_ALCISTA detectado con {reliability}%")
            
            # Si no hay patrones de alta calidad pero hay acumulación de patrones
            if accion == 'NO_OPERAR' and bullish_count > bearish_count + 2:
                accion = 'COMPRA_SPOT'
                confianza = 60 + min(20, bullish_count * 5)
                estrategias.append('ACUMULACION_PATRONES')
                razones.append(f"{bullish_count} patrones alcistas vs {bearish_count} bajistas")
                print(f"   📊 ACUMULACIÓN: {bullish_count} patrones alcistas, {bearish_count} bajistas → COMPRA")
                
            elif accion == 'NO_OPERAR' and bearish_count > bullish_count + 2:
                accion = 'VENTA_SPOT'
                confianza = 60 + min(20, bearish_count * 5)
                estrategias.append('ACUMULACION_PATRONES_BAJISTAS')
                razones.append(f"{bearish_count} patrones bajistas vs {bullish_count} alcistas")
                print(f"   📊 ACUMULACIÓN: {bearish_count} patrones bajistas, {bullish_count} alcistas → VENTA")
            
            # ============ LOG FINAL ============
            print(f"   ✅ Decisión final: {accion} (confianza {confianza}%)")
            if estrategias:
                print(f"   📋 Estrategias: {estrategias}")
            
        except Exception as e:
            print(f"❌ Error en TraderChartista.votar: {e}")
            import traceback
            traceback.print_exc()
            
        return accion, confianza, estrategias, razones

class TraderBallenas(TraderBase):
    """Trader 3: Cazador de Ballenas - Basado en flujo institucional"""
    
    def __init__(self):
        super().__init__("Cazador de Ballenas", "volumen", peso_base=1.5)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            volume = capas.get('volume', {})
            if not isinstance(volume, dict):
                return accion, confianza, estrategias, razones
            
            print(f"\n📊 TRADER BALLENAS - {symbol} {timeframe}")
            
            whale_buy = volume.get('whale_buy', False)
            whale_sell = volume.get('whale_sell', False)
            whale_buy_confirmed = volume.get('whale_buy_confirmed', False)
            whale_sell_confirmed = volume.get('whale_sell_confirmed', False)
            iceberg_buy = volume.get('iceberg_buy', False)
            iceberg_sell = volume.get('iceberg_sell', False)
            accumulation_score = volume.get('accumulation_score', 0)
            volume_ratio = volume.get('volume_ratio', 1)
            
            print(f"   🐋 Ballena compra: {whale_buy} (confirmada: {whale_buy_confirmed})")
            print(f"   🐋 Ballena venta: {whale_sell} (confirmada: {whale_sell_confirmed})")
            print(f"   🧊 Iceberg compra: {iceberg_buy}, venta: {iceberg_sell}")
            print(f"   📊 Score acumulación: {accumulation_score:.1f}")
            print(f"   📈 Ratio volumen: {volume_ratio:.1f}x")
            
            # Calcular velas desde última señal (simulado)
            velas_desde_senal = 2
            
            # ============ ESTRATEGIA MAVERICK ============
            if whale_buy_confirmed and velas_desde_senal <= 7:
                accion = 'COMPRA_SPOT'
                confianza = 95
                estrategias.append('MAVERICK')
                razones.append(f"Ballena compradora CONFIRMADA hace {velas_desde_senal} velas")
                print(f"   ✅ MAVERICK: Compra confirmada (confianza 95%)")
                
            elif whale_buy:
                accion = 'COMPRA_SPOT'
                confianza = 80
                estrategias.append('MAVERICK')
                razones.append("Ballena compradora detectada (pendiente confirmación)")
                print(f"   ✅ MAVERICK: Compra detectada (confianza 80%)")
                
            elif whale_sell_confirmed:
                accion = 'VENTA_SPOT'
                confianza = 95
                estrategias.append('MAVERICK_BAJISTA')
                razones.append("Ballena vendedora CONFIRMADA")
                print(f"   🔴 MAVERICK: Venta confirmada (confianza 95%)")
                
            elif whale_sell:
                accion = 'VENTA_SPOT'
                confianza = 80
                estrategias.append('MAVERICK_BAJISTA')
                razones.append("Ballena vendedora detectada")
                print(f"   🔴 MAVERICK: Venta detectada (confianza 80%)")
            
            # ============ ESTRATEGIA ICEBERG ============
            if iceberg_buy:
                if accion == 'NO_OPERAR':
                    accion = 'COMPRA_SPOT'
                    confianza = 70
                else:
                    confianza = min(100, confianza + 15)
                estrategias.append('ACUMULACION_ICEBERG')
                razones.append("Acumulación tipo ICEBERG detectada")
                print(f"   🧊 ICEBERG: Acumulación detectada (+15% confianza)")
                
            elif iceberg_sell:
                if accion == 'NO_OPERAR':
                    accion = 'VENTA_SPOT'
                    confianza = 70
                else:
                    confianza = min(100, confianza + 15)
                estrategias.append('DISTRIBUCION_ICEBERG')
                razones.append("Distribución tipo ICEBERG detectada")
                print(f"   🧊 ICEBERG: Distribución detectada (+15% confianza)")
            
            # ============ ESTRATEGIA VOLUMEN ANÓMALO ============
            if volume_ratio > 2.0 and accumulation_score > 3:
                if accion == 'NO_OPERAR':
                    accion = 'COMPRA_SPOT'
                    confianza = 75
                estrategias.append('VOLUMEN_ANOMALO_ALCISTA')
                razones.append(f"Volumen anómalo ({volume_ratio:.1f}x) con acumulación")
                print(f"   📊 VOLUMEN ANÓMALO: Alcista (confianza 75%)")
                
            elif volume_ratio > 2.0 and accumulation_score < -3:
                if accion == 'NO_OPERAR':
                    accion = 'VENTA_SPOT'
                    confianza = 75
                estrategias.append('VOLUMEN_ANOMALO_BAJISTA')
                razones.append(f"Volumen anómalo ({volume_ratio:.1f}x) con distribución")
                print(f"   📊 VOLUMEN ANÓMALO: Bajista (confianza 75%)")
            
            print(f"   ✅ Decisión final: {accion} (confianza {confianza}%)")
            
        except Exception as e:
            print(f"❌ Error en TraderBallenas.votar: {e}")
            
        return accion, confianza, estrategias, razones


class TraderMacro(TraderBase):
    """Trader 4: Macroeconomista - Basado en correlación, rotación y SENTIMIENTO (Fear & Greed)
       VERSIÓN MEJORADA PARA NUEVAS SEÑALES DE CORRELACIÓN
    """
    
    def __init__(self):
        super().__init__("Macroeconomista", "correlacion_sentimiento", peso_base=1.3)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            # ============ OBTENER ANÁLISIS DE BTC Y RATIO ============
            btc_analysis = capas.get('btc_analysis', {})
            ratio_analysis = capas.get('ratio_analysis', {})
            
            # OBTENER CAPA DE SENTIMIENTO
            sentiment = capas.get('sentiment', {})
            
            # OBTENER SEÑAL DE CORRELACIÓN
            correlation = capas.get('correlation', {})
            rotation_signal = correlation.get('rotation_signal', 'NEUTRAL')
            weight_modifier = correlation.get('weight_modifier', 1.0)
            symbol_recommendation = correlation.get('symbol_recommendation', {})
            
            # ============ EXTRACCIÓN DE SENTIMIENTO ============
            sentiment_score = sentiment.get('sentiment_score', 0)
            sentiment_bias = sentiment.get('sentiment_bias', 'neutral')
            current_value = sentiment.get('current_value', 50)
            classification = sentiment.get('classification', 'Neutral')
            trend_7d_pct = sentiment.get('trend_7d_pct', 0)
            
            # Ajustar peso del sentimiento según par
            if symbol == 'BTC-USDT':
                sentiment_weight = 1.0
            elif symbol == 'PAXG-BTC':
                sentiment_weight = 0.7
            elif symbol == 'PAXG-USDT':
                sentiment_weight = 0.3
            else:
                sentiment_weight = 0.5
            
            print(f"\n📊 TRADER MACRO - {symbol} {timeframe}")
            print(f"   Señal de rotación: {rotation_signal}")
            print(f"   Sentimiento: {current_value} ({classification}), tendencia: {trend_7d_pct:+.1f}%")
            print(f"   Sentiment score: {sentiment_score:.1f}, bias: {sentiment_bias}")
            
            # ============ MAPEO DE SEÑALES DE CORRELACIÓN A ACCIONES ============
            
            # Para BTC-USDT
            if symbol == 'BTC-USDT':
                # RISK_ON: rotación a riesgo (COMPRAR BTC)
                if rotation_signal == 'RISK_ON':
                    accion = 'COMPRA_SPOT'
                    confianza = 85
                    estrategias.append('ROTACION_RIESGO')
                    razones.append("Rotación a riesgo detectada: BTC preferido sobre oro")
                
                # BTC_STRONGER: BTC más fuerte que PAXG
                elif rotation_signal == 'BTC_STRONGER':
                    accion = 'COMPRA_SPOT'
                    confianza = 75
                    estrategias.append('BTC_MAS_FUERTE')
                    razones.append("Bitcoin muestra mayor fortaleza que el oro")
                
                # BTC_BULLISH: BTC alcista unilateral
                elif rotation_signal == 'BTC_BULLISH':
                    accion = 'COMPRA_SPOT'
                    confianza = 65
                    estrategias.append('BTC_ALCISTA_UNILATERAL')
                    razones.append("Bitcoin en tendencia alcista independiente")
                
                # RISK_OFF: rotación a refugio (EVITAR BTC)
                elif rotation_signal == 'RISK_OFF':
                    accion = 'CAUTION'
                    confianza = 70
                    estrategias.append('EVITAR_BTC_POR_ROTACION')
                    razones.append("Rotación a refugio: evitar exposición en BTC")
                
                # PAXG_STRONGER: PAXG más fuerte (EVITAR BTC)
                elif rotation_signal == 'PAXG_STRONGER':
                    accion = 'CAUTION'
                    confianza = 65
                    estrategias.append('PAXG_MAS_FUERTE')
                    razones.append("Oro muestra mayor fortaleza que Bitcoin")
                
                # BTC_BEARISH: BTC bajista unilateral
                elif rotation_signal == 'BTC_BEARISH':
                    accion = 'CAUTION'
                    confianza = 60
                    estrategias.append('BTC_BAJISTA_UNILATERAL')
                    razones.append("Bitcoin en tendencia bajista")
                
                # POSITIVE_CORRELATION: ambos alcistas
                elif rotation_signal == 'POSITIVE_CORRELATION':
                    accion = 'NEUTRAL'
                    confianza = 60
                    estrategias.append('CORRELACION_POSITIVA')
                    razones.append("Correlación positiva: ambos activos suben")
                
                # NEGATIVE_CORRELATION: ambos bajistas
                elif rotation_signal == 'NEGATIVE_CORRELATION':
                    accion = 'CAUTION'
                    confianza = 60
                    estrategias.append('CORRELACION_NEGATIVA')
                    razones.append("Correlación negativa: ambos activos débiles")
                
                else:
                    accion = 'NEUTRAL'
                    confianza = 50
            
            # ----- PAXG-USDT -----
            elif symbol == 'PAXG-USDT':
                # RISK_OFF: rotación a refugio (COMPRAR PAXG)
                if rotation_signal == 'RISK_OFF':
                    accion = 'COMPRA_SPOT'
                    confianza = 85
                    estrategias.append('ROTACION_REFUGIO')
                    razones.append("Rotación a refugio detectada: oro preferido sobre BTC")
                
                # PAXG_STRONGER: PAXG más fuerte que BTC
                elif rotation_signal == 'PAXG_STRONGER':
                    accion = 'COMPRA_SPOT'
                    confianza = 75
                    estrategias.append('PAXG_MAS_FUERTE')
                    razones.append("Oro muestra mayor fortaleza que Bitcoin")
                
                # RATIO_BULLISH: ratio alcista (implica PAXG fuerte)
                elif rotation_signal == 'RATIO_BULLISH':
                    accion = 'COMPRA_SPOT'
                    confianza = 70
                    estrategias.append('RATIO_ALCISTA')
                    razones.append("Ratio PAXG/BTC alcista indica fortaleza del oro")
                
                # RISK_ON: rotación a riesgo (EVITAR PAXG)
                elif rotation_signal == 'RISK_ON':
                    accion = 'CAUTION'
                    confianza = 70
                    estrategias.append('EVITAR_PAXG_POR_ROTACION')
                    razones.append("Rotación a riesgo: evitar exposición en refugio")
                
                # BTC_STRONGER: BTC más fuerte (EVITAR PAXG)
                elif rotation_signal == 'BTC_STRONGER':
                    accion = 'CAUTION'
                    confianza = 65
                    estrategias.append('BTC_MAS_FUERTE')
                    razones.append("Bitcoin más fuerte que oro, cautela en refugio")
                
                # BTC_BULLISH: BTC alcista unilateral
                elif rotation_signal == 'BTC_BULLISH':
                    accion = 'NEUTRAL'
                    confianza = 55
                    estrategias.append('BTC_ALCISTA_UNILATERAL')
                    razones.append("Bitcoin alcista pero sin impacto directo en oro")
                
                # POSITIVE_CORRELATION: ambos alcistas
                elif rotation_signal == 'POSITIVE_CORRELATION':
                    accion = 'NEUTRAL'
                    confianza = 60
                    estrategias.append('CORRELACION_POSITIVA')
                    razones.append("Correlación positiva: ambos activos suben")
                
                # NEGATIVE_CORRELATION: ambos bajistas
                elif rotation_signal == 'NEGATIVE_CORRELATION':
                    accion = 'CAUTION'
                    confianza = 60
                    estrategias.append('CORRELACION_NEGATIVA')
                    razones.append("Correlación negativa: ambos activos débiles")
                
                else:
                    accion = 'NEUTRAL'
                    confianza = 50
            
            # ----- PAXG-BTC (RATIO) -----
            elif symbol == 'PAXG-BTC':
                # RISK_OFF: rotación a refugio (COMPRAR RATIO)
                if rotation_signal == 'RISK_OFF':
                    accion = 'COMPRA_SPOT'
                    confianza = 90
                    estrategias.append('ROTACION_REFUGIO_RATIO')
                    razones.append("Rotación a refugio confirmada: COMPRAR PAXG/BTC")
                
                # PAXG_STRONGER: PAXG más fuerte (COMPRAR RATIO)
                elif rotation_signal == 'PAXG_STRONGER':
                    accion = 'COMPRA_SPOT'
                    confianza = 80
                    estrategias.append('PAXG_MAS_FUERTE_RATIO')
                    razones.append("Oro más fuerte que Bitcoin, COMPRAR PAXG/BTC")
                
                # RATIO_BULLISH: ratio alcista unilateral
                elif rotation_signal == 'RATIO_BULLISH':
                    accion = 'COMPRA_SPOT'
                    confianza = 75
                    estrategias.append('RATIO_ALCISTA')
                    razones.append("Ratio PAXG/BTC en tendencia alcista")
                
                # RISK_ON: rotación a riesgo (VENDER RATIO)
                elif rotation_signal == 'RISK_ON':
                    accion = 'VENTA_SPOT'
                    confianza = 90
                    estrategias.append('ROTACION_RIESGO_RATIO')
                    razones.append("Rotación a riesgo confirmada: VENDER PAXG/BTC")
                
                # BTC_STRONGER: BTC más fuerte (VENDER RATIO)
                elif rotation_signal == 'BTC_STRONGER':
                    accion = 'VENTA_SPOT'
                    confianza = 80
                    estrategias.append('BTC_MAS_FUERTE_RATIO')
                    razones.append("Bitcoin más fuerte que oro, VENDER PAXG/BTC")
                
                # RATIO_BEARISH: ratio bajista unilateral
                elif rotation_signal == 'RATIO_BEARISH':
                    accion = 'VENTA_SPOT'
                    confianza = 75
                    estrategias.append('RATIO_BAJISTA')
                    razones.append("Ratio PAXG/BTC en tendencia bajista")
                
                # POSITIVE_CORRELATION: ambos alcistas (ratio neutral)
                elif rotation_signal == 'POSITIVE_CORRELATION':
                    accion = 'NO_OPERAR'
                    confianza = 60
                    razones.append("Correlación positiva sin dirección clara en ratio")
                
                # NEGATIVE_CORRELATION: ambos bajistas (ratio neutral)
                elif rotation_signal == 'NEGATIVE_CORRELATION':
                    accion = 'NO_OPERAR'
                    confianza = 60
                    razones.append("Correlación negativa sin dirección clara en ratio")
                
                else:
                    accion = 'NO_OPERAR'
                    confianza = 60
                    razones.append("Sin rotación clara en el ratio")
            
            # ============ AJUSTE POR SENTIMIENTO ============
            # El sentimiento puede modificar la confianza
            
            if sentiment_bias == 'bullish_opportunity':
                # Extreme Fear remontando - bueno para compras
                if accion in ['COMPRA_SPOT', 'LONG']:
                    confianza = min(100, confianza + 15)
                    razones.append(f"Fear & Greed en {current_value} (Extreme Fear) remontando {trend_7d_pct:+.1f}%")
                elif accion in ['VENTA_SPOT', 'SHORT']:
                    confianza = max(0, confianza - 10)
            
            elif sentiment_bias == 'bearish_opportunity':
                # Extreme Greed cayendo - bueno para ventas
                if accion in ['VENTA_SPOT', 'SHORT']:
                    confianza = min(100, confianza + 15)
                    razones.append(f"Fear & Greed en {current_value} (Extreme Greed) cayendo {trend_7d_pct:+.1f}%")
                elif accion in ['COMPRA_SPOT', 'LONG']:
                    confianza = max(0, confianza - 10)
            
            elif sentiment_bias == 'bullish_moderate':
                # Fear moderado mejorando - refuerzo leve para compras
                if accion in ['COMPRA_SPOT', 'LONG']:
                    confianza = min(100, confianza + 10)
            
            elif sentiment_bias == 'bearish_moderate':
                # Greed moderado empeorando - refuerzo leve para ventas
                if accion in ['VENTA_SPOT', 'SHORT']:
                    confianza = min(100, confianza + 10)
            
            elif sentiment_bias in ['bullish_caution', 'bearish_caution']:
                # Extremos sin dirección - reducir confianza general
                confianza = max(0, confianza - 10)
                razones.append(f"Sentimiento extremo ({classification}) sin dirección clara")
            
            # Ajustar por peso de correlación
            confianza = int(confianza * weight_modifier)
            
            # Limitar confianza
            confianza = min(100, max(0, confianza))
            
            print(f"   ✅ Decisión final: {accion} (confianza {confianza}%)")
            
        except Exception as e:
            print(f"❌ Error en TraderMacro.votar: {e}")
            import traceback
            traceback.print_exc()
            
        return accion, confianza, estrategias, razones


        
class TraderPullback(TraderBase):
    """Trader 5: Especialista en Pullbacks - Espera retrocesos para mejor entrada"""
    
    def __init__(self):
        super().__init__("Pullback", "timing", peso_base=1.2)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            print(f"\n📊 TRADER PULLBACK - {symbol} {timeframe}")
            
            trend = capas.get('trend', {})
            volatility = capas.get('volatility', {})
            structure = capas.get('structure', {})
            time_factor = capas.get('time_factor', {})
            
            if not isinstance(trend, dict):
                print(f"   ⚠️ Trend no disponible")
                return accion, confianza, estrategias, razones
            
            adx = trend.get('adx', 0)
            direccion_trend = trend.get('direction', 'neutral')
            bb_position = volatility.get('bb_position', 0.5)
            nearest_support = structure.get('nearest_support')
            nearest_resistance = structure.get('nearest_resistance')
            current_price = structure.get('current_price', 0)
            time_score = time_factor.get('time_score', 0) if time_factor else 0
            
            print(f"   ADX: {adx:.1f}, Dirección: {direccion_trend}")
            print(f"   BB Position: {bb_position:.2f}")
            
            # ============ CORRECCIÓN: Validar None antes de formatear ============
            support_str = f"${nearest_support:.2f}" if nearest_support is not None else "N/A"
            resistance_str = f"${nearest_resistance:.2f}" if nearest_resistance is not None else "N/A"
            print(f"   Soporte: {support_str}, Resistencia: {resistance_str}")
            # ======================================================================
            
            print(f"   Time Score: {time_score}")
            
            # ============ ESTRATEGIA PULLBACK ALCISTA ============
            if (direccion_trend == 'bullish' and adx > 20 and
                bb_position > 0.7 and nearest_support is not None and
                current_price > 0 and
                (current_price - nearest_support) / current_price > 0.02):
                
                accion = 'ESPERAR'
                confianza = 75
                estrategias.append('PULLBACK_ALCISTA')
                razones.append("Tendencia alcista confirmada pero precio extendido")
                razones.append(f"Esperar retroceso a soporte en ${nearest_support:.2f}")
                print(f"   ✅ Estrategia: PULLBACK_ALCISTA - Esperar retroceso a ${nearest_support:.2f}")
                
            # ============ ESTRATEGIA PULLBACK BAJISTA ============
            elif (direccion_trend == 'bearish' and adx > 20 and
                  bb_position < 0.3 and nearest_resistance is not None and
                  current_price > 0 and
                  (nearest_resistance - current_price) / current_price > 0.02):
                
                accion = 'ESPERAR'
                confianza = 75
                estrategias.append('PULLBACK_BAJISTA')
                razones.append("Tendencia bajista confirmada pero precio extendido")
                razones.append(f"Esperar rebote a resistencia en ${nearest_resistance:.2f}")
                print(f"   ✅ Estrategia: PULLBACK_BAJISTA - Esperar rebote a ${nearest_resistance:.2f}")
                
            # ============ ESTRATEGIA ESPERAR CONFIRMACIÓN ============
            elif time_score < -20:
                accion = 'ESPERAR'
                confianza = 70
                estrategias.append('ESPERAR_CONFIRMACION')
                razones.append("Momento desfavorable, esperar mejor timing")
                print(f"   ✅ Estrategia: ESPERAR_CONFIRMACION - Time score bajo")
            
            else:
                print(f"   ⚠️ Ninguna condición de pullback cumplida")
            
            print(f"   Decisión: {accion} (confianza {confianza}%)")
            
        except Exception as e:
            print(f"❌ Error en TraderPullback.votar: {e}")
            import traceback
            traceback.print_exc()
            
        return accion, confianza, estrategias, razones


class TraderSmartMoney(TraderBase):
    """Trader 6: Smart Money - Basado en Order Blocks, FVGs, Liquidity Sweeps y Perfil de Volumen
       VERSIÓN MEJORADA CON ESTRATEGIAS DE HVN, LVN Y STOP HUNTS
    """
    
    def __init__(self):
        super().__init__("Smart Money", "estructura", peso_base=1.4)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            structure = capas.get('structure', {})
            volume = capas.get('volume', {})
            momentum = capas.get('momentum', {})
            trend = capas.get('trend', {})
            
            if not isinstance(structure, dict):
                return accion, confianza, estrategias, razones
            
            current_price = structure.get('current_price', 0)
            if current_price == 0:
                return accion, confianza, estrategias, razones
            
            # ============ EXTRACCIÓN DE DATOS ESTRUCTURALES ============
            order_blocks = structure.get('order_blocks', [])
            fair_value_gaps = structure.get('fair_value_gaps', [])
            liquidity_sweeps = structure.get('liquidity_sweeps', [])
            stop_hunts = structure.get('stop_hunts', [])
            volume_profile = structure.get('volume_profile', {})
            
            # ============ EXTRACCIÓN DE DATOS DE VOLUMEN ============
            volume_ratio = volume.get('volume_ratio', 1) if volume else 1
            whale_buy = volume.get('whale_buy', False) if volume else False
            whale_sell = volume.get('whale_sell', False) if volume else False
            accumulation_score = volume.get('accumulation_score', 0) if volume else 0
            
            # ============ EXTRACCIÓN DE MOMENTUM ============
            rsi = momentum.get('indicators', {}).get('rsi', 50) if momentum else 50
            
            # ============ EXTRACCIÓN DE TENDENCIA ============
            adx = trend.get('adx', 0) if trend else 0 #adx_value
            direccion_trend = trend.get('direction', 'neutral') if trend else 'neutral'
            
            # Obtener n para calcular antigüedad
            n = 0
            if structure and isinstance(structure, dict):
                if 'df' in structure and isinstance(structure.get('df'), dict):
                    df_dict = structure.get('df', {})
                    n = len(df_dict.get('time', []))
            
            print(f"\n📊 TRADER SMARTMONEY - {symbol} {timeframe}")
            print(f"   Order Blocks disponibles: {len(order_blocks)}")
            print(f"   Fair Value Gaps disponibles: {len(fair_value_gaps)}")
            print(f"   Stop Hunts disponibles: {len(stop_hunts)}")
            print(f"   Liquidity Sweeps disponibles: {len(liquidity_sweeps)}")
            
            # ============ ESTRATEGIA 1: ORDER BLOCK ALCISTA ============
            for ob in order_blocks:
                if not isinstance(ob, dict):
                    continue
                    
                if ob.get('type') == 'bullish':
                    price_range = ob.get('price_range', [0, 0])
                    if len(price_range) >= 2 and price_range[0] <= current_price <= price_range[1] * 1.01:
                        # Order block alcista activo
                        confianza_base = 85 if ob.get('strength') == 'strong' else 75
                        
                        # Bonus por volumen
                        if volume_ratio > 1.5:
                            confianza = confianza_base + 10
                            razones.append(f"Order Block alcista con volumen {volume_ratio:.1f}x")
                        else:
                            confianza = confianza_base
                            razones.append("Order Block alcista detectado")
                        
                        accion = 'COMPRA_SPOT'
                        estrategias.append('ORDER_BLOCK_ALCISTA')
                        
                        # Si hay acumulación de ballenas, aumentar confianza
                        if whale_buy or accumulation_score > 3:
                            confianza = min(100, confianza + 10)
                            razones.append("coincide con acumulación institucional")
                        
                        break
            
            # ============ ESTRATEGIA 2: ORDER BLOCK BAJISTA ============
            if accion == 'NO_OPERAR':
                for ob in order_blocks:
                    if not isinstance(ob, dict):
                        continue
                        
                    if ob.get('type') == 'bearish':
                        price_range = ob.get('price_range', [0, 0])
                        if len(price_range) >= 2 and price_range[1] >= current_price >= price_range[0] * 0.99:
                            confianza_base = 85 if ob.get('strength') == 'strong' else 75
                            
                            if volume_ratio > 1.5:
                                confianza = confianza_base + 10
                                razones.append(f"Order Block bajista con volumen {volume_ratio:.1f}x")
                            else:
                                confianza = confianza_base
                                razones.append("Order Block bajista detectado")
                            
                            accion = 'VENTA_SPOT'
                            estrategias.append('ORDER_BLOCK_BAJISTA')
                            
                            if whale_sell or accumulation_score < -3:
                                confianza = min(100, confianza + 10)
                                razones.append("coincide con distribución institucional")
                            
                            break
            
            # ============ ESTRATEGIA 3: FAIR VALUE GAP ALCISTA ============
            if accion == 'NO_OPERAR':
                for fvg in fair_value_gaps:
                    if not isinstance(fvg, dict):
                        continue
                        
                    if fvg.get('type') == 'bullish' and not fvg.get('filled', True):
                        gap_bottom = fvg.get('gap_bottom', 0)
                        gap_top = fvg.get('gap_top', 0)
                        
                        if gap_bottom <= current_price <= gap_top:
                            confianza = 80
                            accion = 'COMPRA_SPOT'
                            estrategias.append('FVG_ALCISTA')
                            razones.append(f"Fair Value Gap alcista entre ${gap_bottom:.2f} y ${gap_top:.2f}")
                            
                            # Si el precio está en la parte inferior del gap, mejor entrada
                            if current_price < (gap_bottom + gap_top) / 2:
                                confianza += 5
                                razones.append("precio en zona inferior del gap")
                            
                            break
            
            # ============ ESTRATEGIA 4: FAIR VALUE GAP BAJISTA ============
            if accion == 'NO_OPERAR':
                for fvg in fair_value_gaps:
                    if not isinstance(fvg, dict):
                        continue
                        
                    if fvg.get('type') == 'bearish' and not fvg.get('filled', True):
                        gap_bottom = fvg.get('gap_bottom', 0)
                        gap_top = fvg.get('gap_top', 0)
                        
                        if gap_bottom <= current_price <= gap_top:
                            confianza = 80
                            accion = 'VENTA_SPOT'
                            estrategias.append('FVG_BAJISTA')
                            razones.append(f"Fair Value Gap bajista entre ${gap_bottom:.2f} y ${gap_top:.2f}")
                            
                            if current_price > (gap_bottom + gap_top) / 2:
                                confianza += 5
                                razones.append("precio en zona superior del gap")
                            
                            break
            
            # ============ ESTRATEGIA 5: LIQUIDITY SWEEP ALCISTA ============
            if accion == 'NO_OPERAR':
                for sweep in liquidity_sweeps:
                    if not isinstance(sweep, dict):
                        continue
                        
                    if sweep.get('type') == 'bullish' and sweep.get('strength') == 'strong':
                        # Sweep alcista (barrido de stops por debajo)
                        sweep_level = sweep.get('sweep_level', 0)
                        days_ago = len(liquidity_sweeps) - liquidity_sweeps.index(sweep)
                        
                        if days_ago <= 3:  # Sweep reciente (últimas 3 velas)
                            confianza = 85
                            accion = 'COMPRA_SPOT'
                            estrategias.append('LIQUIDITY_SWEEP_ALCISTA')
                            razones.append(f"Liquidity sweep en ${sweep_level:.2f} seguido de reversión")
                            
                            # Bonus si el precio ya superó el nivel del sweep
                            if current_price > sweep_level * 1.01:
                                confianza += 10
                                razones.append("precio ya superó el nivel del sweep")
                            
                            break
            
            # ============ ESTRATEGIA 6: LIQUIDITY SWEEP BAJISTA ============
            if accion == 'NO_OPERAR':
                for sweep in liquidity_sweeps:
                    if not isinstance(sweep, dict):
                        continue
                        
                    if sweep.get('type') == 'bearish' and sweep.get('strength') == 'strong':
                        sweep_level = sweep.get('sweep_level', 0)
                        days_ago = len(liquidity_sweeps) - liquidity_sweeps.index(sweep)
                        
                        if days_ago <= 3:
                            confianza = 85
                            accion = 'VENTA_SPOT'
                            estrategias.append('LIQUIDITY_SWEEP_BAJISTA')
                            razones.append(f"Liquidity sweep en ${sweep_level:.2f} seguido de reversión bajista")
                            
                            if current_price < sweep_level * 0.99:
                                confianza += 10
                                razones.append("precio ya perforó el nivel del sweep")
                            
                            break
            
            # ============ ESTRATEGIA 7: STOP HUNT ALCISTA ============
            if accion == 'NO_OPERAR':
                for hunt in stop_hunts:
                    if not isinstance(hunt, dict):
                        continue
                        
                    if hunt.get('type') == 'bullish':
                        hunt_level = hunt.get('level', 0)
                        days_ago = len(stop_hunts) - stop_hunts.index(hunt)
                        
                        if days_ago <= 2:  # Muy reciente
                            confianza = 75
                            accion = 'COMPRA_SPOT'
                            estrategias.append('STOP_HUNT_ALCISTA')
                            razones.append(f"Caza de stops en ${hunt_level:.2f} con absorción")
                            break
            
            # ============ ESTRATEGIA 8: STOP HUNT BAJISTA ============
            if accion == 'NO_OPERAR':
                for hunt in stop_hunts:
                    if not isinstance(hunt, dict):
                        continue
                        
                    if hunt.get('type') == 'bearish':
                        hunt_level = hunt.get('level', 0)
                        days_ago = len(stop_hunts) - stop_hunts.index(hunt)
                        
                        if days_ago <= 2:
                            confianza = 75
                            accion = 'VENTA_SPOT'
                            estrategias.append('STOP_HUNT_BAJISTA')
                            razones.append(f"Caza de stops en ${hunt_level:.2f} con distribución")
                            break
            
            # ============ ESTRATEGIAS DE PERFIL DE VOLUMEN (EXISTENTES + NUEVAS) ============
            if volume_profile:
                price_position = volume_profile.get('price_position', 'unknown')
                distance_to_poc = volume_profile.get('distance_to_poc', 999)
                poc_price = volume_profile.get('poc', 0)
                vah_price = volume_profile.get('vah', 0)
                val_price = volume_profile.get('val', 0)
                poc_volume_pct = volume_profile.get('poc_volume_pct', 0)
                
                # ESTRATEGIA 9: HVN_SOPORTE (NUEVA)
                if price_position == 'inside_value_area' and distance_to_poc < 2.0:
                    if current_price < poc_price * 1.01:  # Precio cerca del POC por debajo
                        if accion == 'NO_OPERAR':
                            accion = 'COMPRA_SPOT'
                            confianza = 75
                            estrategias.append('HVN_SOPORTE')
                            razones.append(f"High Volume Node en ${poc_price:.2f} actuando como soporte")
                        else:
                            # Si ya tenía otra señal, reforzar
                            confianza = min(100, confianza + 15)
                            estrategias.append('HVN_SOPORTE')
                            razones.append(f"confluencia con HVN en ${poc_price:.2f}")
                
                # ESTRATEGIA 10: HVN_RESISTENCIA (NUEVA)
                elif price_position == 'inside_value_area' and distance_to_poc < 2.0:
                    if current_price > poc_price * 0.99:  # Precio cerca del POC por arriba
                        if accion == 'NO_OPERAR':
                            accion = 'VENTA_SPOT'
                            confianza = 75
                            estrategias.append('HVN_RESISTENCIA')
                            razones.append(f"High Volume Node en ${poc_price:.2f} actuando como resistencia")
                        else:
                            confianza = min(100, confianza + 15)
                            estrategias.append('HVN_RESISTENCIA')
                            razones.append(f"confluencia con HVN en ${poc_price:.2f}")
                
                # ESTRATEGIA 11: LVN_ROTURA (NUEVA)
                if price_position == 'above_value_area' and volume_ratio > 1.5:
                    if accion == 'NO_OPERAR':
                        accion = 'COMPRA_SPOT'
                        confianza = 80
                        estrategias.append('LVN_ROTURA')
                        razones.append(f"Low Volume Node roto al alza con volumen {volume_ratio:.1f}x, movimiento rápido esperado")
                    else:
                        confianza = min(100, confianza + 20)
                        estrategias.append('LVN_ROTURA')
                        
                elif price_position == 'below_value_area' and volume_ratio > 1.5:
                    if accion == 'NO_OPERAR':
                        accion = 'VENTA_SPOT'
                        confianza = 80
                        estrategias.append('LVN_ROTURA')
                        razones.append(f"Low Volume Node roto a la baja con volumen {volume_ratio:.1f}x, movimiento rápido esperado")
                    else:
                        confianza = min(100, confianza + 20)
                        estrategias.append('LVN_ROTURA')
                
                # ESTRATEGIA 12: STOP_HUNT_OB (NUEVA)
                for hunt in stop_hunts[-3:]:
                    if hunt.get('index', 0) > n - 10:  # Reciente
                        for ob in order_blocks[-3:]:
                            ob_range = ob.get('price_range', [0, 0])
                            hunt_level = hunt.get('level', 0)
                            if len(ob_range) == 2 and ob_range[0] <= hunt_level <= ob_range[1]:
                                if hunt.get('type') == 'bullish':
                                    if accion == 'NO_OPERAR':
                                        accion = 'COMPRA_SPOT'
                                        confianza = 85
                                        estrategias.append('STOP_HUNT_OB')
                                        razones.append(f"Stop hunt en zona de Order Block, entrada de alta probabilidad")
                                elif hunt.get('type') == 'bearish':
                                    if accion == 'NO_OPERAR':
                                        accion = 'VENTA_SPOT'
                                        confianza = 85
                                        estrategias.append('STOP_HUNT_OB')
                                        razones.append(f"Stop hunt en zona de Order Block, entrada de alta probabilidad")
                
                # ESTRATEGIA 13: POC_VWAP_CONFLUENCIA (NUEVA - usando EMA como proxy)
                ema50 = trend.get('indicators', {}).get('ema50', 0) if trend else 0
                if poc_price > 0 and ema50 > 0:
                    diff_poc_ema = abs(poc_price - ema50) / ema50 * 100
                    if diff_poc_ema < 0.5 and abs(current_price - poc_price) / current_price < 1.0:
                        if accion == 'NO_OPERAR':
                            accion = 'NEUTRAL'
                            confianza = 80
                            estrategias.append('POC_VWAP_CONFLUENCIA')
                            razones.append(f"Confluencia de POC (${poc_price:.2f}) con EMA50, zona de alta probabilidad")
                
                # ESTRATEGIA 14: Respeto del POC (rebote) - EXISTENTE
                if price_position == 'inside_value_area' and distance_to_poc < 2.0:
                    if current_price < poc_price * 1.01:  # Precio cerca del POC por debajo
                        if accion == 'NO_OPERAR':
                            accion = 'COMPRA_SPOT'
                            confianza = 75
                            estrategias.append('POC_REBOTE')
                            razones.append(f"POC en ${poc_price:.2f} actuando como soporte")
                        else:
                            # Si ya tenía otra señal, reforzar
                            confianza = min(100, confianza + 15)
                            estrategias.append('POC_CONFLUENCIA')
                            razones.append(f"confluencia con POC en ${poc_price:.2f}")
                            
                # ESTRATEGIA 15: Ruptura de Value Area al alza - EXISTENTE
                elif price_position == 'above_value_area' and volume_ratio > 1.5:
                    if accion == 'NO_OPERAR':
                        accion = 'COMPRA_SPOT'
                        confianza = 80
                        estrategias.append('VALUE_AREA_BREAKOUT')
                        razones.append(f"Precio sobre Value Area (VAH ${vah_price:.2f}) con volumen {volume_ratio:.1f}x")
                    else:
                        confianza = min(100, confianza + 20)
                        estrategias.append('VALUE_AREA_CONFIRMACION')
                        
                # ESTRATEGIA 16: Ruptura de Value Area a la baja - EXISTENTE
                elif price_position == 'below_value_area' and volume_ratio > 1.5:
                    if accion == 'NO_OPERAR':
                        accion = 'VENTA_SPOT'
                        confianza = 80
                        estrategias.append('VALUE_AREA_BREAKDOWN')
                        razones.append(f"Precio bajo Value Area (VAL ${val_price:.2f}) con volumen {volume_ratio:.1f}x")
                    else:
                        confianza = min(100, confianza + 20)
                        estrategias.append('VALUE_AREA_CONFIRMACION_BAJISTA')
                
                # ESTRATEGIA 17: POC como resistencia (rechazo) - EXISTENTE
                elif price_position == 'above_value_area' and distance_to_poc < 1.0 and current_price > poc_price:
                    # Precio ligeramente por encima del POC, posible resistencia
                    if rsi > 70 or whale_sell:
                        if accion == 'NO_OPERAR':
                            accion = 'VENTA_SPOT'
                            confianza = 75
                            estrategias.append('POC_RESISTENCIA')
                            razones.append(f"POC en ${poc_price:.2f} actuando como resistencia")
                
                # ESTRATEGIA 18: Reversión desde extremos de Value Area - EXISTENTE
                elif price_position == 'above_value_area' and current_price > vah_price * 1.02:
                    if rsi > 70:
                        if accion == 'NO_OPERAR':
                            accion = 'VENTA_SPOT'
                            confianza = 70
                            estrategias.append('VALUE_AREA_EXTREMO_ALTO')
                            razones.append(f"Precio sobre VAH (${vah_price:.2f}) con RSI {rsi:.1f}")
                            
                elif price_position == 'below_value_area' and current_price < val_price * 0.98:
                    if rsi < 30:
                        if accion == 'NO_OPERAR':
                            accion = 'COMPRA_SPOT'
                            confianza = 70
                            estrategias.append('VALUE_AREA_EXTREMO_BAJO')
                            razones.append(f"Precio bajo VAL (${val_price:.2f}) con RSI {rsi:.1f}")
            
            # ============ ESTRATEGIA 19: CONFLUENCIA MÚLTIPLE - EXISTENTE MEJORADA ============
            if accion != 'NO_OPERAR' and len(estrategias) >= 2:
                # Verificar cuántas confirmaciones adicionales tenemos
                confirmaciones = 0
                
                # Verificar Order Blocks adicionales
                for ob in order_blocks:
                    if ob.get('type') == ('bullish' if accion in ['COMPRA_SPOT', 'LONG'] else 'bearish'):
                        price_range = ob.get('price_range', [0, 0])
                        if len(price_range) >= 2 and abs(current_price - price_range[0]) / current_price < 0.02:
                            confirmaciones += 1
                            break
                
                # Verificar FVGs
                for fvg in fair_value_gaps:
                    if fvg.get('type') == ('bullish' if accion in ['COMPRA_SPOT', 'LONG'] else 'bearish'):
                        gap_bottom = fvg.get('gap_bottom', 0)
                        gap_top = fvg.get('gap_top', 0)
                        if gap_bottom <= current_price <= gap_top:
                            confirmaciones += 1
                            break
                
                # Verificar perfil de volumen
                if volume_profile:
                    poc = volume_profile.get('poc', 0)
                    if poc > 0 and abs(current_price - poc) / current_price < 0.01:
                        confirmaciones += 1
                
                # Verificar tendencia
                if (accion in ['COMPRA_SPOT', 'LONG'] and direccion_trend == 'bullish') or \
                   (accion in ['VENTA_SPOT', 'SHORT'] and direccion_trend == 'bearish'):
                    confirmaciones += 1
                
                # Aplicar bonus por confluencia
                if confirmaciones >= 2:
                    confianza = min(100, confianza + 15)
                    estrategias.append('CONFLUENCIA_MULTIPLE')
                    razones.append(f"{confirmaciones} confirmaciones adicionales")
            
            # ============ LIMITAR CONFIANZA ============
            confianza = min(100, max(0, confianza))
            
            # Si no hay acción pero hay volumen anómalo, al menos marcar ESPERAR
            if accion == 'NO_OPERAR' and volume_ratio > 2.0:
                accion = 'ESPERAR'
                confianza = 60
                estrategias.append('VOLUMEN_ANOMALO')
                razones.append(f"Volumen anómalo ({volume_ratio:.1f}x) sin estructura clara")
            
            print(f"   ✅ Estrategias aplicadas: {len(estrategias)}")
            print(f"   ✅ Decisión: {accion} (confianza {confianza:.0f}%)")
            
        except Exception as e:
            print(f"❌ Error en TraderSmartMoney.votar: {e}")
            import traceback
            traceback.print_exc()
            
        return accion, confianza, estrategias, razones

class TraderEspectico(TraderBase):
    """Trader 7: Escéptico - Siempre duda, busca confirmación y consenso"""
    
    def __init__(self):
        super().__init__("Escéptico", "confirmacion", peso_base=1.1)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            confirmation = capas.get('confirmation', {})
            
            print(f"\n📊 TRADER ESCÉPTICO - {symbol} {timeframe}")
            
            if not isinstance(confirmation, dict):
                print(f"   ⚠️ No hay datos de confirmación")
                return accion, confianza, estrategias, razones
            
            confirmation_status = confirmation.get('confirmation_status', 'UNKNOWN')
            requires_wait = confirmation.get('requires_wait', False)
            wait_bars = confirmation.get('wait_bars', 0)
            alternative_signal = confirmation.get('alternative_signal', None)
            
            print(f"   📊 Status confirmación: {confirmation_status}")
            print(f"   ⏱️ Requiere espera: {requires_wait} ({wait_bars} velas)")
            
            # ============ ESTRATEGIA CONFIRMACIÓN RECHAZADA ============
            if confirmation_status == 'REJECTED':
                accion = 'NO_OPERAR'
                confianza = 100
                estrategias.append('CONFIRMACION_RECHAZADA')
                razones.append("Ruptura rechazada: señal de falso breakout")
                if alternative_signal:
                    razones.append(f"Señal alternativa sugerida: {alternative_signal}")
                print(f"   ✅ Decisión: NO_OPERAR (confianza 100%) - Falso breakout")
                        
            # ============ ESTRATEGIA ESPERAR CONFIRMACIÓN ============
            elif requires_wait:
                accion = 'ESPERAR'
                confianza = 80 + wait_bars * 5
                estrategias.append('ESPERAR_CONFIRMACION')
                razones.append(f"Se requiere confirmación por {wait_bars} vela(s)")
                print(f"   ⏳ Decisión: ESPERAR (confianza {confianza}%) - Confirmación pendiente")
            
            else:
                print(f"   ⚪ Decisión: NO_OPERAR - Sin señales de confirmación")
            
            print(f"   Estrategias: {estrategias}")
            
        except Exception as e:
            print(f"❌ Error en TraderEspectico.votar: {e}")
            import traceback
            traceback.print_exc()
        
        return accion, confianza, estrategias, razones

# ============================================================================
# TRADER 8: MULTIFRAME ANALYST - VERSIÓN CORREGIDA CON ANÁLISIS REAL
# ============================================================================
class TraderMultiframe(TraderBase):
    """
    Trader 8: Especialista en Análisis Multitemporal
    Analiza timeframes SUPERIORES e INFERIORES al actual
    """
    
    def __init__(self):
        super().__init__("Multiframe", "contexto_temporal", peso_base=1.4)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            # ============ OBTENER ANÁLISIS DE DIFERENTES TEMPORALIDADES ============
            # Estos análisis deberían venir en capas desde analyze_full_market
            # Necesitamos: análisis de 1D, 12H, 4H para el mismo símbolo
            
            btc_analysis = capas.get('btc_analysis', {})
            paxg_analysis = capas.get('paxg_analysis', {})
            ratio_analysis = capas.get('ratio_analysis', {})
            
            # Determinar qué análisis usar según el símbolo
            if symbol == 'BTC-USDT':
                # Para BTC, podemos obtener sus propios análisis de diferentes timeframes
                # Por ahora, usaremos los que vienen en capas
                analisis_1d = btc_analysis if btc_analysis.get('timeframe') == '1D' else None
                analisis_12h = btc_analysis if btc_analysis.get('timeframe') == '12h' else None
                analisis_4h = btc_analysis if btc_analysis.get('timeframe') == '4h' else None
            elif symbol == 'PAXG-USDT':
                analisis_1d = paxg_analysis if paxg_analysis.get('timeframe') == '1D' else None
                analisis_12h = paxg_analysis if paxg_analysis.get('timeframe') == '12h' else None
                analisis_4h = paxg_analysis if paxg_analysis.get('timeframe') == '4h' else None
            else:  # PAXG-BTC
                analisis_1d = ratio_analysis if ratio_analysis.get('timeframe') == '1D' else None
                analisis_12h = ratio_analysis if ratio_analysis.get('timeframe') == '12h' else None
                analisis_4h = ratio_analysis if ratio_analysis.get('timeframe') == '4h' else None
            
            # Si no tenemos análisis de otros timeframes, usar el actual con EMAs (fallback)
            trend = capas.get('trend', {})
            indicators = trend.get('indicators', {})
            current_price = capas.get('structure', {}).get('current_price', 0)
            
            # Determinar tendencias reales según el timeframe
            tendencia_superior = 'neutral'  # Timeframe mayor (ej: 1D si actual es 12h)
            tendencia_actual = 'neutral'    # Timeframe actual
            tendencia_inferior = 'neutral'  # Timeframe menor (ej: 4h si actual es 12h)
            
            # Mapeo de timeframes
            if timeframe == '1W':
                # Para 1W, el superior no existe, el actual es 1W, inferiores son 1D, 12H, 4H
                tendencia_actual = trend.get('direction', 'neutral')
                
                # Intentar obtener tendencia de 1D
                if analisis_1d and analisis_1d.get('trend'):
                    tendencia_inferior = analisis_1d['trend'].get('direction', 'neutral')
                else:
                    # Fallback: usar EMA50 vs precio
                    ema50 = indicators.get('ema50', 0)
                    if current_price > ema50:
                        tendencia_inferior = 'bullish'
                    elif current_price < ema50:
                        tendencia_inferior = 'bearish'
                
            elif timeframe == '1D':
                # Para 1D, superior es 1W, actual es 1D, inferiores son 12H, 4H
                tendencia_actual = trend.get('direction', 'neutral')
                
                # Superior (1W) - usar EMA200 como proxy
                ema200 = indicators.get('ema200', 0)
                if current_price > ema200:
                    tendencia_superior = 'bullish'
                elif current_price < ema200:
                    tendencia_superior = 'bearish'
                
                # Inferior (12H/4H) - usar EMA21/EMA9
                ema21 = indicators.get('ema21', 0)
                if current_price > ema21:
                    tendencia_inferior = 'bullish'
                elif current_price < ema21:
                    tendencia_inferior = 'bearish'
                
            elif timeframe == '12h':
                # Para 12H, superior es 1D, actual es 12H, inferiores son 4H
                tendencia_actual = trend.get('direction', 'neutral')
                
                # Superior (1D) - usar EMA50
                ema50 = indicators.get('ema50', 0)
                if current_price > ema50:
                    tendencia_superior = 'bullish'
                elif current_price < ema50:
                    tendencia_superior = 'bearish'
                
                # Inferior (4H) - usar EMA9
                ema9 = indicators.get('ema9', 0)
                if current_price > ema9:
                    tendencia_inferior = 'bullish'
                elif current_price < ema9:
                    tendencia_inferior = 'bearish'
                
            elif timeframe == '4h':
                # Para 4H, superior es 12H/1D, actual es 4H, inferiores no hay (o 1H pero no tenemos)
                tendencia_actual = trend.get('direction', 'neutral')
                
                # Superior (12H) - usar EMA21
                ema21 = indicators.get('ema21', 0)
                if current_price > ema21:
                    tendencia_superior = 'bullish'
                elif current_price < ema21:
                    tendencia_superior = 'bearish'
                
                # Superior mayor (1D) - usar EMA50
                ema50 = indicators.get('ema50', 0)
                if current_price > ema50:
                    # Ya tenemos tendencia_superior, pero podemos combinarlas
                    pass
            
            print(f"\n📊 TRADER MULTIFRAME - {symbol} {timeframe}")
            print(f"   Tendencia SUPERIOR: {tendencia_superior}")
            print(f"   Tendencia ACTUAL: {tendencia_actual}")
            print(f"   Tendencia INFERIOR: {tendencia_inferior}")
            
            # ============ ESTRATEGIAS MULTIFRAME ============
            
            # ESTRATEGIA 1: ALINEACIÓN COMPLETA ALCISTA
            if (tendencia_superior == 'bullish' and 
                tendencia_actual == 'bullish' and 
                tendencia_inferior == 'bullish'):
                
                if timeframe == '1W':
                    accion = 'COMPRA_SPOT'
                    confianza = 85
                elif timeframe == '1D':
                    accion = 'COMPRA_SPOT'
                    confianza = 90
                elif timeframe == '12h':
                    accion = 'COMPRA_SPOT'
                    confianza = 85
                else:  # 4h
                    if symbol == 'BTC-USDT':
                        accion = 'LONG'
                        confianza = 90
                    else:
                        accion = 'COMPRA_SPOT'
                        confianza = 85
                
                estrategias.append('ALINEACION_BULLISH_COMPLETA')
                razones.append(f"Todas las temporalidades alineadas al alza")
            
            # ESTRATEGIA 2: ALINEACIÓN COMPLETA BAJISTA
            elif (tendencia_superior == 'bearish' and 
                  tendencia_actual == 'bearish' and 
                  tendencia_inferior == 'bearish'):
                
                if timeframe == '1W':
                    accion = 'VENTA_SPOT'
                    confianza = 85
                elif timeframe == '1D':
                    accion = 'VENTA_SPOT'
                    confianza = 90
                elif timeframe == '12h':
                    accion = 'VENTA_SPOT'
                    confianza = 85
                else:  # 4h
                    if symbol == 'BTC-USDT':
                        accion = 'SHORT'
                        confianza = 90
                    else:
                        accion = 'VENTA_SPOT'
                        confianza = 85
                
                estrategias.append('ALINEACION_BEARISH_COMPLETA')
                razones.append(f"Todas las temporalidades alineadas a la baja")
            
            # ESTRATEGIA 3: CONFLICTO - Tendencia superior alcista, inferiores bajistas
            elif (tendencia_superior == 'bullish' and 
                  tendencia_actual == 'bearish' and 
                  tendencia_inferior == 'bearish'):
                
                accion = 'CAUTION'
                confianza = 75
                estrategias.append('CONFLICTO_MAYOR_ADVIERTE_CAMBIO')
                
                if timeframe == '1W':
                    razones.append("Tendencia semanal alcista pero diario y menores ya giraron, posible cambio inminente")
                elif timeframe == '1D':
                    razones.append("Tendencia diaria alcista pero temporalidades menores ya giraron, posible cambio inminente")
                else:
                    razones.append("Tendencia superior alcista pero actual y menores bajistas, conflicto severo")
            
            # ESTRATEGIA 4: CONFLICTO - Tendencia superior bajista, inferiores alcistas
            elif (tendencia_superior == 'bearish' and 
                  tendencia_actual == 'bullish' and 
                  tendencia_inferior == 'bullish'):
                
                accion = 'CAUTION'
                confianza = 75
                estrategias.append('CONFLICTO_MAYOR_ADVIERTE_CAMBIO')
                
                if timeframe == '1W':
                    razones.append("Tendencia semanal bajista pero diario y menores alcistas, posible rebote")
                elif timeframe == '1D':
                    razones.append("Tendencia diaria bajista pero temporalidades menores alcistas, posible rebote")
                else:
                    razones.append("Tendencia superior bajista pero actual y menores alcistas, conflicto severo")
            
            # ESTRATEGIA 5: PULLBACK - Tendencia superior alcista, actual en corrección
            elif (tendencia_superior == 'bullish' and 
                  tendencia_actual == 'bearish' and 
                  tendencia_inferior == 'neutral'):
                
                accion = 'COMPRA_SPOT'
                confianza = 70
                estrategias.append('PULLBACK_OPORTUNIDAD')
                razones.append("Tendencia superior alcista con corrección en actual, oportunidad de compra")
            
            # ESTRATEGIA 6: PULLBACK - Tendencia superior bajista, actual en rebote
            elif (tendencia_superior == 'bearish' and 
                  tendencia_actual == 'bullish' and 
                  tendencia_inferior == 'neutral'):
                
                accion = 'VENTA_SPOT'
                confianza = 70
                estrategias.append('PULLBACK_OPORTUNIDAD')
                razones.append("Tendencia superior bajista con rebote en actual, oportunidad de venta")
            
            # ESTRATEGIA 7: RUPTURA - Superior neutral, actual rompiendo
            elif (tendencia_superior == 'neutral' and 
                  tendencia_actual == 'bullish' and 
                  tendencia_inferior == 'bullish'):
                
                accion = 'COMPRA_SPOT'
                confianza = 65
                estrategias.append('RUPTURA_CONFIRMADA')
                razones.append("Temporalidades superiores laterales pero actual rompiendo al alza")
            
            elif (tendencia_superior == 'neutral' and 
                  tendencia_actual == 'bearish' and 
                  tendencia_inferior == 'bearish'):
                
                accion = 'VENTA_SPOT'
                confianza = 65
                estrategias.append('RUPTURA_CONFIRMADA')
                razones.append("Temporalidades superiores laterales pero actual rompiendo a la baja")
            
            # ESTRATEGIA 8: ACUMULACIÓN EN ZONA BAJISTA
            elif (tendencia_superior == 'bearish' and 
                  tendencia_actual == 'bearish' and 
                  current_price < indicators.get('ema50', 0) * 0.95 and 
                  current_price > indicators.get('ema200', 0)):
                
                accion = 'COMPRA_SPOT'
                confianza = 60
                estrategias.append('ACUMULACION_EN_ZONA_BAJISTA')
                razones.append("Tendencia bajista pero en soporte histórico (EMA200), acumulación estratégica")
            
            # ESTRATEGIA 9: DISTRIBUCIÓN EN ZONA ALCISTA
            elif (tendencia_superior == 'bullish' and 
                  tendencia_actual == 'bullish' and 
                  current_price > indicators.get('ema50', 0) * 1.05 and 
                  current_price < indicators.get('ema200', 0) * 1.1):
                
                accion = 'VENTA_SPOT'
                confianza = 60
                estrategias.append('DISTRIBUCION_EN_ZONA_ALCISTA')
                razones.append("Tendencia alcista pero en zona de posible resistencia, tomar ganancias parciales")
            
            # Ajustar confianza según el par
            if symbol == 'PAXG-BTC':
                confianza = int(confianza * 0.8)
            
            confianza = min(100, max(0, confianza))
            
            print(f"   ✅ Decisión: {accion} (confianza {confianza}%)")
            
        except Exception as e:
            print(f"❌ Error en TraderMultiframe.votar: {e}")
            import traceback
            traceback.print_exc()
            
        return accion, confianza, estrategias, razones


# ============================================================================
# TRADER 9: LIQUIDATION ANALYST (EL LIQUIDADOR)
# ============================================================================
# Ubicación: Después de la clase TraderMultiframe y antes de la clase Moderador

class TraderLiquidation(TraderBase):
    """
    Trader 9: Especialista en Mapa de Calor de Liquidaciones
    Analiza pools de liquidez apalancada para anticipar movimientos de stop hunting
    """
    
    def __init__(self):
        super().__init__("El Liquidador", "liquidaciones", peso_base=1.3)
        
    def votar(self, capas, symbol, timeframe):
        # Valores por defecto
        accion = 'NO_OPERAR'
        confianza = 0
        estrategias = []
        razones = []
        
        try:
            # ============ OBTENER CAPAS NECESARIAS ============
            liquidation = capas.get('liquidation', {})
            if not liquidation or not isinstance(liquidation, dict):
                return accion, confianza, estrategias, razones
            
            structure = capas.get('structure', {})
            trend = capas.get('trend', {})
            volume = capas.get('volume', {})
            momentum = capas.get('momentum', {})
            
            current_price = structure.get('current_price', 0)
            if current_price == 0:
                return accion, confianza, estrategias, razones
            
            # ============ EXTRAER DATOS DEL HEATMAP ============
            active_bins = liquidation.get('active_bins', [])
            frozen_bins = liquidation.get('frozen_bins', [])
            total_long_bins = liquidation.get('total_long_bins', 0)
            total_short_bins = liquidation.get('total_short_bins', 0)
            total_long_weight = liquidation.get('total_long_weight', 0)
            total_short_weight = liquidation.get('total_short_weight', 0)
            last_spike_bar = liquidation.get('last_spike_bar')
            total_spikes = liquidation.get('total_spikes', 0)
            
            # Calcular pesos en millones
            long_weight_m = total_long_weight / 1_000_000
            short_weight_m = total_short_weight / 1_000_000
            
            print(f"\n📊 TRADER LIQUIDACIÓN - {symbol} {timeframe}")
            print(f"   Long bins: {total_long_bins}, Short bins: {total_short_bins}")
            print(f"   Long weight: {long_weight_m:.1f}M, Short weight: {short_weight_m:.1f}M")
            print(f"   Total spikes: {total_spikes}")
            print(f"   Bins congelados: {len(frozen_bins)}")
            
            # ============ ESTRATEGIA 1: DOMINANCIA DE LARGOS (SOPORTE) ============
            if total_long_bins > total_short_bins * 1.5 and total_long_weight > 50_000_000:
                # Precio por debajo de los principales soportes LONG
                if active_bins:
                    long_prices = [b.get('price_top', 0) for b in active_bins if b.get('side') == 'long']
                    if long_prices and current_price < sum(long_prices[:5]) / 5:
                        confianza_base = 70
                        
                        volume_ratio = volume.get('volume_ratio', 1) if volume else 1
                        if volume_ratio > 1.5:
                            confianza = confianza_base + 10
                            razones.append(f"volumen {volume_ratio:.1f}x confirma acumulación")
                        else:
                            confianza = confianza_base
                        
                        if timeframe in ['4h', '12h'] and symbol == 'BTC-USDT':
                            accion = 'LONG'
                        else:
                            accion = 'COMPRA_SPOT'
                        
                        estrategias.append('LONG_DOMINANCE_SUPPORT')
                        razones.append(f"{total_long_bins} bins LONG (${long_weight_m:.1f}M) actuando como soporte")
            
            # ============ ESTRATEGIA 2: DOMINANCIA DE CORTOS (RESISTENCIA) ============
            elif total_short_bins > total_long_bins * 1.5 and total_short_weight > 50_000_000:
                # Precio por encima de las principales resistencias SHORT
                if active_bins:
                    short_prices = [b.get('price_bottom', 0) for b in active_bins if b.get('side') == 'short']
                    if short_prices and current_price > sum(short_prices[:5]) / 5:
                        confianza_base = 70
                        
                        volume_ratio = volume.get('volume_ratio', 1) if volume else 1
                        if volume_ratio > 1.5:
                            confianza = confianza_base + 10
                            razones.append(f"volumen {volume_ratio:.1f}x confirma distribución")
                        else:
                            confianza = confianza_base
                        
                        if timeframe in ['4h', '12h'] and symbol == 'BTC-USDT':
                            accion = 'SHORT'
                        else:
                            accion = 'VENTA_SPOT'
                        
                        estrategias.append('SHORT_DOMINANCE_RESISTANCE')
                        razones.append(f"{total_short_bins} bins SHORT (${short_weight_m:.1f}M) actuando como resistencia")
            
            # ============ ESTRATEGIA 3: ACUMULACIÓN DE SPIKES (ACTIVIDAD RECIENTE) ============
            elif total_spikes > 5:
                # Determinar dirección basada en el flujo
                if total_long_weight > total_short_weight * 1.3:
                    confianza = 65
                    accion = 'COMPRA_SPOT'
                    estrategias.append('SPIKE_ACCUMULATION_LONG')
                    razones.append(f"{total_spikes} spikes recientes con acumulación LONG de ${long_weight_m:.1f}M")
                
                elif total_short_weight > total_long_weight * 1.3:
                    confianza = 65
                    accion = 'VENTA_SPOT'
                    estrategias.append('SPIKE_ACCUMULATION_SHORT')
                    razones.append(f"{total_spikes} spikes recientes con acumulación SHORT de ${short_weight_m:.1f}M")
            
            # ============ ESTRATEGIA 4: EQUILIBRIO DE BINS ============
            elif abs(total_long_bins - total_short_bins) < 10 and total_long_bins > 20:
                accion = 'ESPERAR'
                confianza = 60
                estrategias.append('LIQUIDITY_BALANCE')
                razones.append(f"equilibrio de bins ({total_long_bins}L vs {total_short_bins}S) - esperar dirección")
            
            # ============ ESTRATEGIA 5: POCOS BINS PERO MUY PESADOS ============
            elif total_long_bins < 10 and total_long_weight > 100_000_000:
                confianza = 75
                accion = 'COMPRA_SPOT'
                estrategias.append('HEAVY_LONG_CONCENTRATION')
                razones.append(f"concentración LONG de ${long_weight_m:.1f}M en solo {total_long_bins} bins")
            
            elif total_short_bins < 10 and total_short_weight > 100_000_000:
                confianza = 75
                accion = 'VENTA_SPOT'
                estrategias.append('HEAVY_SHORT_CONCENTRATION')
                razones.append(f"concentración SHORT de ${short_weight_m:.1f}M en solo {total_short_bins} bins")
            
            # ============ ESTRATEGIA 6: SEÑAL CONTRARIA (SOBREEXTENSIÓN) ============
            else:
                if total_long_bins > 100 and total_long_weight > 200_000_000:
                    rsi = momentum.get('indicators', {}).get('rsi', 50) if momentum else 50
                    if rsi > 70:
                        confianza = 70
                        accion = 'VENTA_SPOT'
                        estrategias.append('LONG_EXTREME_REVERSAL')
                        razones.append(f"sobreacumulación LONG ({total_long_bins} bins) con RSI {rsi:.1f}")
                
                elif total_short_bins > 100 and total_short_weight > 200_000_000:
                    rsi = momentum.get('indicators', {}).get('rsi', 50) if momentum else 50
                    if rsi < 30:
                        confianza = 70
                        accion = 'COMPRA_SPOT'
                        estrategias.append('SHORT_EXTREME_REVERSAL')
                        razones.append(f"sobreacumulación SHORT ({total_short_bins} bins) con RSI {rsi:.1f}")
            
            # ============ ESTRATEGIA 7: BINS CONGELADOS RECIENTES ============
            if not accion != 'NO_OPERAR' and frozen_bins:
                # Verificar si hay congelamientos recientes (últimos 5 bins)
                ultimos_congelados = frozen_bins[-5:]
                direccion_congelados = {}
                
                for bin_obj in ultimos_congelados:
                    side = bin_obj.get('side') if isinstance(bin_obj, dict) else getattr(bin_obj, 'side', None)
                    if side:
                        direccion_congelados[side] = direccion_congelados.get(side, 0) + 1
                
                if direccion_congelados.get('long', 0) >= 3:
                    confianza = 60
                    accion = 'VENTA_SPOT'
                    estrategias.append('RECENT_LONG_LIQUIDATIONS')
                    razones.append(f"{direccion_congelados['long']} liquidaciones LONG recientes - posible presión bajista")
                
                elif direccion_congelados.get('short', 0) >= 3:
                    confianza = 60
                    accion = 'COMPRA_SPOT'
                    estrategias.append('RECENT_SHORT_LIQUIDATIONS')
                    razones.append(f"{direccion_congelados['short']} liquidaciones SHORT recientes - posible presión alcista")
            
            # ============ AJUSTES POR PAR Y TEMPORALIDAD ============
            if symbol == 'PAXG-USDT':
                if accion in ['LONG', 'SHORT']:
                    accion = 'COMPRA_SPOT' if accion == 'LONG' else 'VENTA_SPOT'
                    confianza = int(confianza * 0.8)
            
            elif symbol == 'PAXG-BTC':
                confianza = int(confianza * 0.7)
            
            if timeframe == '1W':
                if total_long_weight < 200_000_000 and total_short_weight < 200_000_000:
                    accion = 'NO_OPERAR'
                    confianza = 0
            
            # ============ LIMITAR CONFIANZA ============
            confianza = min(100, max(0, confianza))
            
            # Si no hay acción pero hay actividad, sugerir ESPERAR
            if accion == 'NO_OPERAR' and (total_long_bins > 10 or total_short_bins > 10):
                accion = 'ESPERAR'
                confianza = 55
                estrategias.append('LIQUIDITY_PRESENT')
                razones.append(f"liquidez detectada ({total_long_bins}L/{total_short_bins}S bins)")
            
            print(f"   Estrategias: {estrategias}")
            print(f"   Decisión: {accion} (confianza {confianza}%)")
            
        except Exception as e:
            print(f"❌ Error en TraderLiquidation.votar: {e}")
            import traceback
            traceback.print_exc()
        
        return accion, confianza, estrategias, razones




# ============================================================================
# MODERADOR - SISTEMA DE VOTACIÓN Y CONSENSO
# ============================================================================

class Moderador:
    """El moderador recibe los votos de los 10 traders (9 originales + ReviewTrader) y genera una decisión"""
    
    def __init__(self):
        self.traders = [
            TraderTecnico(),
            TraderChartista(),
            TraderBallenas(),
            TraderMacro(),
            TraderPullback(),
            TraderSmartMoney(),
            TraderEspectico(),
            TraderMultiframe(),
            TraderLiquidation()  # Trader 9
        ]
        
        # === FASE 7: Agregar ReviewTrader como 10º trader (opcional, tolerante a fallos) ===
        try:
            from review_trader import review_trader
            self.traders.append(review_trader)
            print(f"✅ Moderador: ReviewTrader agregado como 10º trader")
        except Exception as e:
            print(f"⚠️ Moderador: ReviewTrader no disponible ({e}). Continuando con 9 traders.")
        
    def procesar_votacion(self, capas, symbol, timeframe):
        """
        Procesa los votos de todos los traders y genera una decisión consensuada
        VERSIÓN CON LOGS DETALLADOS
        """
        votos = []
        todas_estrategias = []
        
        print(f"\n{'='*60}")
        print(f"👥 INICIANDO VOTACIÓN - {symbol} {timeframe}")
        print(f"{'='*60}")
        print(f"📋 Traders participantes: {len(self.traders)}")
        print()
        
        # 1. RECOLECTAR VOTOS DE CADA TRADER
        for i, trader in enumerate(self.traders, 1):
            try:
                print(f"▶️ [{i}/{len(self.traders)}] {trader.nombre} (peso: {trader.peso_base})")
                
                accion, confianza, estrategias, razones = trader.votar(capas, symbol, timeframe)
                
                # Validar que los valores sean correctos
                if accion is None:
                    accion = 'NO_OPERAR'
                if confianza is None:
                    confianza = 0
                if estrategias is None:
                    estrategias = []
                if razones is None:
                    razones = []
                
                # Aplicar peso del trader
                confianza_ponderada = confianza * trader.peso_base
                
                # Mostrar voto del trader
                print(f"   📊 VOTO: {accion}")
                print(f"   📈 Confianza original: {confianza}% | Ponderada: {confianza_ponderada:.1f}%")
                
                if estrategias:
                    print(f"   🎯 Estrategias: {', '.join(estrategias)}")
                if razones:
                    print(f"   💡 Razones: {', '.join(razones[:2])}")
                
                votos.append({
                    'trader': trader.nombre,
                    'accion': accion,
                    'confianza': confianza_ponderada,
                    'confianza_original': confianza,
                    'estrategias': estrategias,
                    'razones': razones,
                    'peso': trader.peso_base
                })
                
                todas_estrategias.extend(estrategias)
                print()
                
            except Exception as e:
                print(f"❌ Error en trader {trader.nombre}: {e}")
                print(f"   ⚠️ Usando voto por defecto: NO_OPERAR")
                votos.append({
                    'trader': trader.nombre,
                    'accion': 'NO_OPERAR',
                    'confianza': 0,
                    'confianza_original': 0,
                    'estrategias': ['ERROR'],
                    'razones': [f'Error: {str(e)[:50]}'],
                    'peso': trader.peso_base
                })
                print()
        
        # 2. MOSTRAR RESUMEN DE VOTOS
        print(f"\n{'='*60}")
        print(f"📊 RESUMEN DE VOTACIÓN")
        print(f"{'='*60}")
        
        for voto in votos:
            print(f"   • {voto['trader']}: {voto['accion']} ({voto['confianza_original']}%)")
        
        # 3. CONTAR VOTOS POR ACCIÓN
        conteo_acciones = {}
        confianza_por_accion = {}
        traders_por_accion = {}
        estrategias_por_accion = {}
        razones_por_accion = {}
        
        for voto in votos:
            accion = voto['accion']
            
            # Saltar NEUTRAL para el conteo principal
            if accion == 'NEUTRAL':
                continue
                
            confianza = voto['confianza']
            trader = voto['trader']
            estrategias = voto['estrategias']
            razones = voto['razones']
            
            if accion not in conteo_acciones:
                conteo_acciones[accion] = 0
                confianza_por_accion[accion] = 0
                traders_por_accion[accion] = []
                estrategias_por_accion[accion] = []
                razones_por_accion[accion] = []
                
            conteo_acciones[accion] += 1
            confianza_por_accion[accion] += confianza
            traders_por_accion[accion].append(trader)
            estrategias_por_accion[accion].extend(estrategias)
            razones_por_accion[accion].extend(razones)
        
        # 4. MOSTRAR CONTEO DE ACCIONES
        print(f"\n📋 Conteo de votos por acción:")
        for accion, count in conteo_acciones.items():
            conf_prom = confianza_por_accion[accion] / count if count > 0 else 0
            print(f"   • {accion}: {count} votos (confianza promedio: {conf_prom:.1f}%)")
            if accion in traders_por_accion:
                print(f"     └─ Traders: {', '.join(traders_por_accion[accion])}")
        
        # 5. CALCULAR CONFIANZA PROMEDIO POR ACCIÓN
        for accion in confianza_por_accion:
            if conteo_acciones[accion] > 0:
                confianza_por_accion[accion] /= conteo_acciones[accion]
        
        # 6. DETECTAR ESTRATEGIAS CON CONSENSO
        frecuencia_estrategias = {}
        for estrategia in todas_estrategias:
            if estrategia and isinstance(estrategia, str):
                frecuencia_estrategias[estrategia] = frecuencia_estrategias.get(estrategia, 0) + 1
            
        estrategias_consenso = [e for e, f in frecuencia_estrategias.items() if f >= 2]
        
        if estrategias_consenso:
            print(f"\n🎯 Estrategias con consenso (mencionadas por ≥2 traders):")
            for e in estrategias_consenso:
                print(f"   • {e} ({frecuencia_estrategias[e]} veces)")
        
        # 7. VERIFICAR SI HAY VETO (NO_OPERAR con alta confianza)
        veto_activo = False
        for voto in votos:
            if voto['accion'] == 'NO_OPERAR' and voto['confianza_original'] >= 80:
                veto_activo = True
                print(f"\n⚠️ VETO DETECTADO: {voto['trader']} votó NO_OPERAR con {voto['confianza_original']}%")
                break
                
        if veto_activo:
            print(f"\n🚫 Decisión final: NO_OPERAR por veto (confianza 90%)")
            return 'NO_OPERAR', 90, ['VETO_DETECTADO'], ['Un trader detectó condiciones peligrosas'], votos
        
        # 8. SELECCIONAR ACCIÓN GANADORA
        # Priorizar acciones con al menos 2 votos
        acciones_con_votos = {a: c for a, c in conteo_acciones.items() if c >= 2 and a not in ['NO_OPERAR', 'NEUTRAL']}
        
        if acciones_con_votos:
            # Entre las acciones con al menos 2 votos, elegir la de mayor confianza
            accion_ganadora = max(acciones_con_votos.keys(), 
                                  key=lambda a: confianza_por_accion.get(a, 0))
            confianza_final = confianza_por_accion.get(accion_ganadora, 50)
            traders_que_apoyan = traders_por_accion.get(accion_ganadora, [])
            estrategias_detectadas = list(set(estrategias_por_accion.get(accion_ganadora, [])))
            razones_consolidadas = razones_por_accion.get(accion_ganadora, [])[:3]
            
            print(f"\n🏆 Acción ganadora: {accion_ganadora}")
            print(f"   Confianza: {confianza_final:.1f}%")
            print(f"   Apoyada por: {', '.join(traders_que_apoyan)}")
            
        else:
            # Sin acciones con 2+ votos, verificar si ESPERAR tiene apoyo
            if conteo_acciones.get('ESPERAR', 0) >= 2:
                accion_ganadora = 'ESPERAR'
                confianza_final = confianza_por_accion.get('ESPERAR', 60)
                traders_que_apoyan = traders_por_accion.get('ESPERAR', [])
                estrategias_detectadas = list(set(estrategias_por_accion.get('ESPERAR', [])))
                razones_consolidadas = razones_por_accion.get('ESPERAR', [])[:3]
                
                print(f"\n⏳ Acción ganadora: ESPERAR")
                print(f"   Confianza: {confianza_final:.1f}%")
                print(f"   Apoyada por: {', '.join(traders_que_apoyan)}")
                
            # Si hay una acción con 1 voto pero muy alta confianza (>85)
            elif len(conteo_acciones) == 1:
                accion_unica = list(conteo_acciones.keys())[0]
                if confianza_por_accion.get(accion_unica, 0) >= 85:
                    accion_ganadora = accion_unica
                    confianza_final = confianza_por_accion[accion_unica]
                    traders_que_apoyan = traders_por_accion.get(accion_unica, [])
                    estrategias_detectadas = list(set(estrategias_por_accion.get(accion_unica, [])))
                    razones_consolidadas = razones_por_accion.get(accion_unica, [])[:3]
                    
                    print(f"\n🎲 Acción ganadora (única con alta confianza): {accion_ganadora}")
                    print(f"   Confianza: {confianza_final:.1f}%")
                    print(f"   Apoyada por: {', '.join(traders_que_apoyan)}")
                else:
                    accion_ganadora = 'ESPERAR'
                    confianza_final = 60
                    traders_que_apoyan = []
                    estrategias_detectadas = []
                    razones_consolidadas = ["Poca convicción en la señal única"]
                    print(f"\n🤔 Sin consenso claro - Se recomienda ESPERAR")
            else:
                accion_ganadora = 'NO_OPERAR'
                confianza_final = 70
                traders_que_apoyan = []
                estrategias_detectadas = []
                razones_consolidadas = ["Sin consenso claro entre los traders"]
                print(f"\n🤷 Sin consenso - Decisión: NO_OPERAR")
        
        # 7. REGISTRO DE VOTACIÓN
        registro_votacion = {
            'accion_ganadora': accion_ganadora,
            'confianza_final': confianza_final,
            'traders_que_apoyan': traders_que_apoyan,
            'conteo_acciones': conteo_acciones,
            'confianza_por_accion': confianza_por_accion,
            'estrategias_consenso': estrategias_consenso,
            'todos_los_votos': [
                {
                    'trader': v['trader'],
                    'accion': v['accion'],
                    'confianza': v['confianza_original'],
                    'estrategias': v['estrategias']
                } for v in votos
            ]
        }
        
        print(f"\n{'='*60}")
        print(f"✅ VOTACIÓN COMPLETADA: {accion_ganadora} (confianza {confianza_final:.1f}%)")
        print(f"{'='*60}\n")
        
        return accion_ganadora, confianza_final, estrategias_consenso, razones_consolidadas, registro_votacion

    def _resultado_serializable(self, resultado):
        """Convierte el resultado de votación a tipos serializables"""
        if resultado is None:
            return None
        if isinstance(resultado, (str, int, float, bool)):
            return resultado
        if isinstance(resultado, dict):
            return {str(k): self._resultado_serializable(v) for k, v in resultado.items()}
        if isinstance(resultado, (list, tuple)):
            return [self._resultado_serializable(item) for item in resultado]
        if isinstance(resultado, np.integer):
            return int(resultado)
        if isinstance(resultado, np.floating):
            return float(resultado)
        if isinstance(resultado, np.ndarray):
            return self._resultado_serializable(resultado.tolist())
        # Para cualquier otro tipo
        return str(resultado)

# ============================================================================
# RUTAS DE LA APLICACIÓN FLASK
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html', is_futures=False)

@app.route('/futures')
def futures_page():
    """Página de Futuros - reutiliza index.html con flag is_futures=True"""
    return render_template('index.html', is_futures=True)

@app.route('/analytics')
def analytics_page():
    """Página de Análisis Estadístico (Fase C)"""
    return render_template('analytics.html')

@app.route('/manual')
def manual():
    return render_template('manual.html')

@app.route('/health')
def health():
    """Health check para Render"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now(bolivia_tz).isoformat(),
        'system': 'Crypto Trader Analyst Pro',
        'version': '2.0'
    })

# === CORRECCIÓN: app.py - Manejo de errores en rutas API ===
# Ubicación: Reemplazar rutas  y /api/telegram/test

@app.route('/api/analyze')
def api_analyze():
    """Endpoint de análisis con manejo robusto de errores"""
    try:
        symbol = request.args.get('symbol', 'BTC-USDT')
        interval = request.args.get('interval', '1D')
        
        print(f"\n{'='*60}")
        print(f"🔍 API ANALYZE solicitado: {symbol} {interval}")
        print(f"{'='*60}")
        
        # Validación de símbolo
        if symbol not in SYMBOLS:
            error_response = {
                'success': False, 
                'error': f'Símbolo no válido: {symbol}. Opciones: {list(SYMBOLS.keys())}'
            }
            print(f"❌ Error 400: {error_response['error']}")
            return jsonify(error_response), 400
        
        # Validación de intervalo
        if interval not in TIMEFRAMES:
            error_response = {
                'success': False, 
                'error': f'Intervalo no válido: {interval}. Opciones: {list(TIMEFRAMES.keys())}'
            }
            print(f"❌ Error 400: {error_response['error']}")
            return jsonify(error_response), 400
        
        # Ejecutar análisis
        print(f"🔍 Ejecutando analyze_full_market...")
        result = expert_system.analyze_full_market(symbol, interval)
        
        # Verificar resultado
        if result is None:
            error_response = {
                'success': False, 
                'error': 'El análisis devolvió None'
            }
            print(f"❌ Error 500: {error_response['error']}")
            return jsonify(error_response), 500
            
        if not isinstance(result, dict):
            error_response = {
                'success': False, 
                'error': f'El análisis devolvió un tipo inválido: {type(result)}'
            }
            print(f"❌ Error 500: {error_response['error']}")
            return jsonify(error_response), 500
        
        if not result.get('success'):
            error_msg = result.get('error', 'Error desconocido en el análisis')
            error_response = {
                'success': False, 
                'error': error_msg
            }
            print(f"❌ Error 400: {error_response['error']}")
            return jsonify(error_response), 400
        
        # ============ EXTRACCIÓN SEGURA DE DATOS ============
        decision = result.get('decision')
        if decision is None:
            decision = {'action': 'NO_OPERAR', 'confidence': 0}
        elif not isinstance(decision, dict):
            decision = {'action': 'NO_OPERAR', 'confidence': 0}
            
        levels = result.get('levels', {})
        if not isinstance(levels, dict):
            levels = {}
            
        structure = result.get('structure', {})
        if not isinstance(structure, dict):
            structure = {}
            
        trend = result.get('trend', {})
        if not isinstance(trend, dict):
            trend = {}
            
        momentum = result.get('momentum', {})
        if not isinstance(momentum, dict):
            momentum = {}
            
        volatility = result.get('volatility', {})
        if not isinstance(volatility, dict):
            volatility = {}
            
        volume = result.get('volume', {})
        if not isinstance(volume, dict):
            volume = {}
        
        # ============ OBTENER CORRELACIÓN ============
        correlation = result.get('correlation', {})
        print(f"✅ CORRELACIÓN encontrada: {correlation.get('rotation_signal', 'NEUTRAL')}")
        
        # ============ EXTRAER FVGs PARA DEBUG ============
        fvg_count = len(structure.get('fair_value_gaps', []))
        print(f"✅ FVGs encontrados en estructura: {fvg_count}")
        
        # ============ CONSTRUIR RESPUESTA ============
        response_data = {
            'success': True,
            'data': {
                'symbol': result.get('symbol', symbol),
                'timeframe': result.get('timeframe', interval),
                'decision': {
                    'action': decision.get('action', 'NO_OPERAR'),
                    'confidence': float(decision.get('confidence', 0)),
                    'weights': decision.get('weights', {}),
                    'reason': decision.get('reason', ''),
                    'estrategias': [str(e) for e in decision.get('estrategias', [])],
                    'razones': [str(r) for r in decision.get('razones', [])[:3]]
                },
                'levels': {
                    'entry': float(levels.get('entry', 0)),
                    'stop_loss': float(levels.get('stop_loss', 0)),
                    'take_profit': float(levels.get('take_profit', 0)),
                    'leverage': int(levels.get('leverage', 1)),
                    'risk_reward': float(levels.get('risk_reward', 0)),
                    'suggested_size': float(levels.get('suggested_size', 1.0)),
                    'tp_source': str(levels.get('tp_source', 'N/A')),
                    'sl_source': str(levels.get('sl_source', 'N/A')),
                    'tp_probability': float(levels.get('tp_probability', 0)),
                    'sl_reliability': float(levels.get('sl_reliability', 0)),
                    'min_tp_distance_pct': float(levels.get('min_tp_distance_pct', 0)),
                    'rejected_reason': levels.get('rejected_reason')
                },
                'message': str(result.get('message', 'Análisis completado')),
                'current_price': float(result.get('current_price', 0)),
                'trend': {
                    'direction': trend.get('direction', 'neutral'),
                    'confidence': float(trend.get('confidence', 0)),
                    'strength': trend.get('strength', 'unknown'),
                    'adx': float(trend.get('adx', 0)),
                    'score': float(trend.get('score', 0))
                },
                'momentum': {
                    'direction': momentum.get('direction', 'neutral'),
                    'confidence': float(momentum.get('confidence', 0)),
                    'score': float(momentum.get('score', 0)),
                    'divergences': [str(d) for d in momentum.get('divergences', [])],
                    'hidden_divergences': [str(h) for h in momentum.get('hidden_divergences', [])],
                    'indicators': {
                        'rsi': float(momentum.get('indicators', {}).get('rsi', 50)),
                        'rsi_maverick': float(momentum.get('indicators', {}).get('rsi_maverick', 0.5))
                    }
                },
                'volatility': {
                    'atr_pct': float(volatility.get('atr_pct', 0)),
                    'volatility_level': volatility.get('volatility_level', 'unknown'),
                    'ftm_zone': volatility.get('ftm_zone', 'NEUTRAL'),
                    'ftm_no_trade': bool(volatility.get('ftm_no_trade', False)),
                    'squeeze_on': bool(volatility.get('squeeze_on', False)),
                    'squeeze_length': int(volatility.get('squeeze_length', 0)),
                    'operability': bool(volatility.get('operability', True)),
                    'suggested_leverage': int(volatility.get('suggested_leverage', 10))
                },
                'volume': {
                    'volume_ratio': float(volume.get('volume_ratio', 1)),
                    'volume_participation': volume.get('volume_participation', 'normal'),
                    'accumulation_score': float(volume.get('accumulation_score', 0)),
                    'whale_buy': bool(volume.get('whale_buy', False)),
                    'whale_sell': bool(volume.get('whale_sell', False)),
                    'whale_buy_confirmed': bool(volume.get('whale_buy_confirmed', False)),
                    'whale_sell_confirmed': bool(volume.get('whale_sell_confirmed', False)),
                    'iceberg_buy': bool(volume.get('iceberg_buy', False)),
                    'iceberg_sell': bool(volume.get('iceberg_sell', False)),
                    'obv_trend': volume.get('obv_trend', 'neutral'),
                    'mfi': float(volume.get('mfi', 50))
                },
                'structure': {
                    'supports': [float(s) for s in structure.get('supports', []) if s is not None],
                    'resistances': [float(r) for r in structure.get('resistances', []) if r is not None],
                    'nearest_support': float(structure.get('nearest_support')) if structure.get('nearest_support') is not None else None,
                    'nearest_resistance': float(structure.get('nearest_resistance')) if structure.get('nearest_resistance') is not None else None,
                    'current_price': float(structure.get('current_price', 0)),
                    'patterns': {
                        'count': int(structure.get('patterns', {}).get('count', 0)),
                        'recent_patterns': [
                            {
                                'name': str(p.get('name', '')),
                                'direction': str(p.get('direction', 'neutral')),
                                'reliability': float(p.get('reliability', 0)),
                                'type': str(p.get('type', '1')),
                                'index': int(p.get('index', 0))
                            } for p in structure.get('patterns', {}).get('recent_patterns', [])[:5]
                        ]
                    },
                    'bullish_patterns_count': int(structure.get('bullish_patterns_count', 0)),
                    'bearish_patterns_count': int(structure.get('bearish_patterns_count', 0)),
                    'fib_levels': {str(k): float(v) for k, v in structure.get('fib_levels', {}).items() if v is not None},
                    'order_blocks': [
                        {
                            'type': str(ob.get('type', '')),
                            'price_range': [float(ob['price_range'][0]), float(ob['price_range'][1])] if ob.get('price_range') and len(ob['price_range']) >= 2 else [0, 0],
                            'index': int(ob.get('index', 0)),
                            'strength': str(ob.get('strength', 'moderate')),
                            'volume_ratio': float(ob.get('volume_ratio', 1.0))
                        } for ob in structure.get('order_blocks', [])[:10]
                    ],
                    'fair_value_gaps': [
                        {
                            'type': str(fvg.get('type', '')),
                            'gap_bottom': float(fvg.get('gap_bottom', 0)),
                            'gap_top': float(fvg.get('gap_top', 0)),
                            'gap_size': float(fvg.get('gap_size', 0)),
                            'index': int(fvg.get('index', 0)),
                            'filled': bool(fvg.get('filled', False)),
                            'reaccion': bool(fvg.get('reaccion', False)),
                            'antiguedad': int(fvg.get('antiguedad', 0)),
                            'strength': str(fvg.get('strength', 'moderate')),
                            'volume_ratio': float(fvg.get('volume_ratio', 1.0))
                        } for fvg in structure.get('fair_value_gaps', [])[:15]
                    ],
                    'liquidity_sweeps': [
                        {
                            'type': str(sw.get('type', '')),
                            'sweep_level': float(sw.get('sweep_level', 0)),
                            'index': int(sw.get('index', 0)),
                            'strength': str(sw.get('strength', 'moderate'))
                        } for sw in structure.get('liquidity_sweeps', [])[:5]
                    ],
                    'stop_hunts': [
                        {
                            'type': str(hunt.get('type', '')),
                            'level': float(hunt.get('level', 0)),
                            'index': int(hunt.get('index', 0))
                        } for hunt in structure.get('stop_hunts', [])[:5]
                    ],
                    'volume_profile': {
                        'poc': float(structure.get('volume_profile', {}).get('poc', 0)) if structure.get('volume_profile', {}).get('poc') else None,
                        'vah': float(structure.get('volume_profile', {}).get('vah', 0)) if structure.get('volume_profile', {}).get('vah') else None,
                        'val': float(structure.get('volume_profile', {}).get('val', 0)) if structure.get('volume_profile', {}).get('val') else None,
                        'value_area_width': float(structure.get('volume_profile', {}).get('value_area_width', 0)),
                        'poc_volume': float(structure.get('volume_profile', {}).get('poc_volume', 0)),
                        'total_volume': float(structure.get('volume_profile', {}).get('total_volume', 0)),
                        'poc_volume_pct': float(structure.get('volume_profile', {}).get('poc_volume_pct', 0)),
                        'price_position': str(structure.get('volume_profile', {}).get('price_position', 'unknown')),
                        'distance_to_poc': float(structure.get('volume_profile', {}).get('distance_to_poc', 999)),
                        'hvn_nodes': structure.get('volume_profile', {}).get('hvn_nodes', [])[:5],
                        'lvn_nodes': structure.get('volume_profile', {}).get('lvn_nodes', [])[:5]
                    }
                },
                'sentiment': result.get('sentiment'),
                'correlation': {
                    'rotation_signal': str(correlation.get('rotation_signal', 'NEUTRAL')),
                    'weight_modifier': float(correlation.get('weight_modifier', 1.0)),
                    'symbol_recommendation': {
                        'action': str(correlation.get('symbol_recommendation', {}).get('action', 'NEUTRAL')),
                        'reason': str(correlation.get('symbol_recommendation', {}).get('reason', '')),
                        'weight': float(correlation.get('symbol_recommendation', {}).get('weight', 1.0))
                    },
                    'symbol_score': float(correlation.get('symbol_score', 0)),
                    'btc_analysis': {
                        'decision': {
                            'action': str(correlation.get('btc_analysis', {}).get('decision', {}).get('action', 'N/A')),
                            'confidence': float(correlation.get('btc_analysis', {}).get('decision', {}).get('confidence', 0))
                        },
                        'trend': {
                            'direction': str(correlation.get('btc_analysis', {}).get('trend', {}).get('direction', 'neutral')),
                            'adx': float(correlation.get('btc_analysis', {}).get('trend', {}).get('adx', 0)),
                            'plus_di': float(correlation.get('btc_analysis', {}).get('trend', {}).get('plus_di', 0)),
                            'minus_di': float(correlation.get('btc_analysis', {}).get('trend', {}).get('minus_di', 0)),
                            'confidence': float(correlation.get('btc_analysis', {}).get('trend', {}).get('confidence', 50))
                        }
                    },
                    'paxg_analysis': {
                        'trend': {
                            'direction': str(correlation.get('paxg_analysis', {}).get('trend', {}).get('direction', 'neutral')),
                            'adx': float(correlation.get('paxg_analysis', {}).get('trend', {}).get('adx', 0)),
                            'plus_di': float(correlation.get('paxg_analysis', {}).get('trend', {}).get('plus_di', 0)),
                            'minus_di': float(correlation.get('paxg_analysis', {}).get('trend', {}).get('minus_di', 0)),
                            'confidence': float(correlation.get('paxg_analysis', {}).get('trend', {}).get('confidence', 50))
                        }
                    },
                    'paxg_btc_analysis': {
                        'decision': {
                            'action': str(correlation.get('paxg_btc_analysis', {}).get('decision', {}).get('action', 'N/A')),
                            'confidence': float(correlation.get('paxg_btc_analysis', {}).get('decision', {}).get('confidence', 0))
                        },
                        'trend': {
                            'direction': str(correlation.get('paxg_btc_analysis', {}).get('trend', {}).get('direction', 'neutral')),
                            'adx': float(correlation.get('paxg_btc_analysis', {}).get('trend', {}).get('adx', 0)),
                            'plus_di': float(correlation.get('paxg_btc_analysis', {}).get('trend', {}).get('plus_di', 0)),
                            'minus_di': float(correlation.get('paxg_btc_analysis', {}).get('trend', {}).get('minus_di', 0)),
                            'confidence': float(correlation.get('paxg_btc_analysis', {}).get('trend', {}).get('confidence', 50))
                        }
                    }
                },
                # ============ NUEVA LÍNEA AÑADIDA ============
                'liquidation': result.get('liquidation'),  # <--- ÚNICA LÍNEA AÑADIDA
                # ============================================
                'zones': result.get('zones'), # <--- NUEVO
                'df': result.get('df', {
                    'time': [], 'open': [], 'high': [], 
                    'low': [], 'close': [], 'volume': []
                }),
                'timestamp': str(result.get('timestamp', datetime.now(bolivia_tz).isoformat()))
            }
        }
        
        # DEBUG: Verificar serialización
        try:
            test_json = json.dumps(response_data)
            print(f"✅ Serialización correcta - {len(test_json)} bytes")
            print(f"📊 Decisión: {decision.get('action', 'NO_OPERAR')} - Confianza: {decision.get('confidence', 0)}")
            print(f"📊 FVGs en respuesta: {len(response_data['data']['structure']['fair_value_gaps'])}")
            print(f"📊 Correlación en respuesta: {response_data['data']['correlation']['rotation_signal']}")
        except Exception as e:
            print(f"❌ Error de serialización: {e}")
            import traceback
            traceback.print_exc()
            error_response = {
                'success': False,
                'error': f'Error interno de serialización: {str(e)}'
            }
            return jsonify(error_response), 500
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error en API analyze: {str(e)}")
        import traceback
        traceback.print_exc()
        error_response = {
            'success': False, 
            'error': f'Error interno del servidor: {str(e)}'
        }
        return jsonify(error_response), 500
        

@app.route('/api/previous_signals')
def api_previous_signals():
    """
    Endpoint que devuelve las señales de la vela anterior - VERSIÓN CORREGIDA
    """
    try:
        print(f"\n{'='*60}")
        print(f"🔍 API PREVIOUS SIGNALS solicitado")
        print(f"{'='*60}")
        
        # ============ CACHE DE 10 MINUTOS ============
        cache_key = "prev_signals_cache"
        cache_time_key = "prev_signals_cache_time"
        cache_duration = 600  # 10 minutos
        
        now = time.time()
        
        if hasattr(expert_system, cache_key) and hasattr(expert_system, cache_time_key):
            cache_time = getattr(expert_system, cache_time_key)
            if now - cache_time < cache_duration:
                print(f"📦 Usando caché (expira en {int(cache_duration - (now - cache_time))}s)")
                return jsonify({
                    'success': True,
                    'data': getattr(expert_system, cache_key),
                    'cached': True,
                    'timestamp': datetime.now(bolivia_tz).isoformat()
                })
        
        resultados = {}
        tiempo_actual = datetime.now(bolivia_tz)
        temporalidades = ['4h', '12h', '1D', '1W']
        pares = ['BTC-USDT', 'PAXG-USDT', 'PAXG-BTC']
        
        # ============ OBTENER ANÁLISIS DE CORRELACIÓN POR TEMPORALIDAD ============
        print("📊 Obteniendo análisis de correlación para todas las temporalidades...")
        analisis_correlacion = {}
        
        for timeframe in temporalidades:
            print(f"\n   📈 Procesando correlación para {timeframe}...")
            analisis_correlacion[timeframe] = {}
            
            # BTC
            try:
                btc_actual = expert_system.analyze_full_market('BTC-USDT', timeframe)
                if btc_actual and btc_actual.get('success'):
                    analisis_correlacion[timeframe]['BTC-USDT'] = btc_actual
                    print(f"      ✅ BTC-{timeframe} obtenido")
            except Exception as e:
                print(f"      ⚠️ Error en BTC-{timeframe}: {e}")
            
            # PAXG (depende de BTC)
            if 'BTC-USDT' in analisis_correlacion[timeframe]:
                try:
                    paxg_actual = expert_system.analyze_full_market(
                        'PAXG-USDT', 
                        timeframe,
                        btc_analysis=analisis_correlacion[timeframe]['BTC-USDT']
                    )
                    if paxg_actual and paxg_actual.get('success'):
                        analisis_correlacion[timeframe]['PAXG-USDT'] = paxg_actual
                        print(f"      ✅ PAXG-{timeframe} obtenido")
                except Exception as e:
                    print(f"      ⚠️ Error en PAXG-{timeframe}: {e}")
            
            # RATIO (depende de BTC y PAXG)
            if ('BTC-USDT' in analisis_correlacion[timeframe] and 
                'PAXG-USDT' in analisis_correlacion[timeframe]):
                try:
                    ratio_actual = expert_system.analyze_full_market(
                        'PAXG-BTC', 
                        timeframe,
                        btc_analysis=analisis_correlacion[timeframe]['BTC-USDT'],
                        paxg_analysis=analisis_correlacion[timeframe]['PAXG-USDT']
                    )
                    if ratio_actual and ratio_actual.get('success'):
                        analisis_correlacion[timeframe]['PAXG-BTC'] = ratio_actual
                        print(f"      ✅ RATIO-{timeframe} obtenido")
                except Exception as e:
                    print(f"      ⚠️ Error en RATIO-{timeframe}: {e}")
        
        # ============ PROCESAR SEÑALES DE VELA ANTERIOR ============
        for timeframe in temporalidades:
            print(f"\n📊 Procesando {timeframe}...")
            
            for symbol in pares:
                try:
                    # Obtener datos
                    df = expert_system.get_kucoin_data(symbol, timeframe)
                    
                    if df is None or len(df) < 50:
                        print(f"   ⚠️ {symbol} {timeframe}: datos insuficientes")
                        continue
                    
                    # Verificar que hay al menos 2 velas
                    if len(df) < 2:
                        print(f"   ⚠️ {symbol} {timeframe}: menos de 2 velas")
                        continue
                    
                    # Precios
                    precio_cierre_anterior = float(df['close'].iloc[-2])
                    precio_actual = float(df['close'].iloc[-1])
                    
                    # DataFrame para vela anterior (100 velas terminando en penúltima)
                    if len(df) >= 101:
                        df_anterior = df.iloc[-101:-1].copy()
                    else:
                        df_anterior = df.iloc[:-1].copy()
                    
                    df_anterior = df_anterior.reset_index(drop=True)
                    
                    # Obtener análisis de correlación para esta temporalidad
                    btc_analysis = analisis_correlacion[timeframe].get('BTC-USDT')
                    paxg_analysis = analisis_correlacion[timeframe].get('PAXG-USDT')
                    paxg_btc_analysis = analisis_correlacion[timeframe].get('PAXG-BTC')
                    
                    # Analizar vela anterior
                    analisis = expert_system.analyze_full_market(
                        symbol, 
                        timeframe, 
                        btc_analysis=btc_analysis,
                        paxg_analysis=paxg_analysis,
                        paxg_btc_analysis=paxg_btc_analysis,
                        df_override=df_anterior
                    )
                    
                    if not analisis or not analisis.get('success'):
                        print(f"   ⚠️ {symbol} {timeframe}: análisis falló")
                        continue
                    
                    decision = analisis['decision']['action']
                    confianza = float(analisis['decision']['confidence'])
                    
                    # SOLO señales de trading
                    if decision not in ['COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT']:
                        print(f"   ⏸️ {symbol} {timeframe}: {decision} - ignorada")
                        continue
                    
                    # Obtener niveles
                    levels = analisis.get('levels', {})
                    entry = float(levels.get('entry', precio_cierre_anterior)) if levels.get('entry') else None
                    stop_loss = float(levels.get('stop_loss', 0)) if levels.get('stop_loss') else None
                    take_profit = float(levels.get('take_profit', 0)) if levels.get('take_profit') else None
                    
                    # ============ VERIFICAR SI SIGUE ACTIVA (convertir a int para JSON) ============
                    activa = 0  # 0 = False, 1 = True
                    
                    if decision in ['COMPRA_SPOT', 'LONG'] and stop_loss and stop_loss > 0:
                        activa = 1 if precio_actual > stop_loss else 0
                    elif decision in ['VENTA_SPOT', 'SHORT'] and stop_loss and stop_loss > 0:
                        activa = 1 if precio_actual < stop_loss else 0
                    
                    # ============ TIEMPO RESTANTE ============
                    tiempo_restante = 0
                    try:
                        tiempo_vida = {'4h': 14400, '12h': 43200, '1D': 86400, '1W': 604800}.get(timeframe, 14400)
                        tiempo_cierre = pd.Timestamp(df['time'].iloc[-2]).to_pydatetime()
                        tiempo_transcurrido = (tiempo_actual - tiempo_cierre).total_seconds()
                        tiempo_restante = int(max(0, tiempo_vida - tiempo_transcurrido))
                    except Exception as e:
                        print(f"      ⚠️ Error calculando tiempo: {e}")
                    
                    # ============ CONSTRUIR MENSAJE CORTO ============
                    mensaje_corto = analisis.get('message', '')
                    if len(mensaje_corto) > 500:
                        mensaje_corto = mensaje_corto[:500] + '...'
                    
                    # ============ GUARDAR (TODOS LOS VALORES JSON SERIALIZABLES) ============
                    clave = f"{symbol}_{timeframe}"
                    resultados[clave] = {
                        'symbol': str(symbol),
                        'timeframe': str(timeframe),
                        'decision': str(decision),
                        'confidence': float(confianza),
                        'entry': entry,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'precio_actual': float(precio_actual),
                        'activa': int(activa),  # ← Convertido a int para JSON
                        'tiempo_restante': int(tiempo_restante),
                        'message': str(mensaje_corto),
                        'timestamp': str(tiempo_actual.isoformat())
                    }
                    
                    estado = "🟢 ACTIVA" if activa == 1 else "⚪ inactiva"
                    print(f"   ✅ {symbol} {timeframe}: {decision} ({confianza:.0f}%) - {estado}")
                    
                except Exception as e:
                    print(f"   ❌ Error en {symbol} {timeframe}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                
                time.sleep(0.2)
        
        # ============ GUARDAR EN CACHÉ ============
        setattr(expert_system, cache_key, resultados)
        setattr(expert_system, cache_time_key, now)
        
        activas = sum(1 for r in resultados.values() if r.get('activa', 0) == 1)
        print(f"\n✅ API COMPLETADA - {len(resultados)} señales totales, {activas} activas")
        
        return jsonify({
            'success': True,
            'data': resultados,
            'cached': False,
            'timestamp': tiempo_actual.isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error CRÍTICO en api_previous_signals: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': str(e),
            'data': {}
        })


@app.route('/api/telegram/test', methods=['POST'])
def api_telegram_test():
    """Endpoint de prueba Telegram con TODOS los indicadores en la imagen"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type debe ser application/json'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Cuerpo de solicitud vacío'}), 400
        
        symbol = data.get('symbol', 'BTC-USDT')
        interval = data.get('interval', '1D')
        include_chart = data.get('include_chart', True)
        
        if symbol not in SYMBOLS:
            return jsonify({'success': False, 'error': f'Símbolo no válido: {symbol}'}), 400
        
        if interval not in TIMEFRAMES:
            return jsonify({'success': False, 'error': f'Intervalo no válido: {interval}'}), 400
        
        result = expert_system.analyze_full_market(symbol, interval)
        
        if not result or not isinstance(result, dict):
            return jsonify({'success': False, 'error': 'El análisis no devolvió un resultado válido'}), 400
            
        if not result.get('success'):
            error_msg = result.get('error', 'Error desconocido en el análisis')
            return jsonify({'success': False, 'error': f'Error en análisis: {error_msg}'}), 400
        
        # Obtener top indicadores
        top_indicadores = expert_system.get_top_indicators_for_chart(result)
        
        message = result.get('message')
        if not message:
            message = f"🔍 Análisis de {SYMBOLS[symbol]['name']} en {TIMEFRAMES[interval]['name']}\n\n"
            message += f"Recomendación: {result.get('decision', {}).get('action', 'NO_OPERAR')}\n"
            message += f"Precio: ${result.get('current_price', 0):.2f}\n"
            message += f"Indicadores clave: {', '.join(top_indicadores[:4])}"
        
        images = []
        if include_chart:
            try:
                # Generar imagen con TODOS los indicadores
                img = expert_system.generate_chart_image(symbol, interval, result, top_indicadores)
                if img:
                    images = [img]
                    print(f"✅ Imagen generada con {len(top_indicadores)} indicadores top")
                else:
                    print("⚠️ No se pudo generar el gráfico")
            except Exception as e:
                print(f"❌ Error generando gráfico: {e}")
                import traceback
                traceback.print_exc()
        
        # Enviar a Telegram
        success = expert_system.send_telegram_alert(message, images[0] if images else None)
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'✅ Análisis de {SYMBOLS[symbol]["name"]} {TIMEFRAMES[interval]["name"]} enviado a Telegram',
                'symbol': symbol,
                'interval': interval,
                'has_chart': len(images) > 0,
                'top_indicators': top_indicadores[:4]
            })
        else:
            return jsonify({'success': False, 'error': 'Error al enviar mensaje a Telegram'}), 500
            
    except Exception as e:
        print(f"❌ Error en API telegram test: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500

@app.route('/api/generate_report')
def api_generate_report():
    symbol = request.args.get('symbol', 'BTC-USDT')
    interval = request.args.get('interval', '1D')
    
    result = expert_system.analyze_full_market(symbol, interval)
    
    if not result['success']:
        return jsonify({'success': False, 'error': 'No se pudo generar el análisis'}), 400
    
    report = f"""ANÁLISIS TÉCNICO PROFESIONAL
==============================
Par: {SYMBOLS[symbol]['name']}
Temporalidad: {TIMEFRAMES[interval]['name']}
Fecha: {datetime.now(bolivia_tz).strftime('%Y-%m-%d %H:%M:%S')} Hora Bolivia

RECOMENDACIÓN: {result['decision']['action']}
Confianza: {result['decision']['confidence']:.1f}%

NIVELES DE OPERACIÓN:
- Entrada: ${result['levels']['entry']:.2f}
- Stop Loss: ${result['levels']['stop_loss']:.2f}
- Take Profit: ${result['levels']['take_profit']:.2f}
- Riesgo/Recompensa: 1:{result['levels']['risk_reward']}
- Apalancamiento sugerido: {result['levels']['leverage']}x

ANÁLISIS DE TENDENCIA:
- Dirección: {result['trend']['direction'].upper()}
- Fuerza: {result['trend']['strength']}
- ADX: {result['trend']['adx']:.1f} 

ANÁLISIS DE MOMENTUM:
- Dirección: {result['momentum']['direction'].upper()}
- RSI: {result['momentum']['indicators'].get('rsi', 0):.1f}
- RSI Maverick: {result['momentum']['indicators'].get('rsi_maverick', 0):.2f}
- Divergencias: {', '.join(result['momentum']['divergences']) if result['momentum']['divergences'] else 'Ninguna'}

ANÁLISIS DE VOLATILIDAD:
- Nivel: {result['volatility']['volatility_level']}
- ATR %: {result['volatility']['atr_pct']:.2f}%
- FTMaverick: {result['volatility']['ftm_zone']}
- Operabilidad: {'SÍ' if result['volatility']['operability'] else 'NO'}

ANÁLISIS DE VOLUMEN:
- Participación: {result['volume']['volume_participation']}
- Ratio Volumen: {result['volume']['volume_ratio']:.2f}x
- Ballenas Compra: {'SÍ' if result['volume'].get('whale_buy', False) else 'NO'}
- Ballenas Venta: {'SÍ' if result['volume'].get('whale_sell', False) else 'NO'}

ESTRUCTURA DE PRECIO:
- Precio Actual: ${result['current_price']:.2f}
- Soportes Cercanos: {', '.join([f'${s:.2f}' for s in result['structure']['supports'][:3]]) if result['structure']['supports'] else 'N/A'}
- Resistencias Cercanas: {', '.join([f'${r:.2f}' for r in result['structure']['resistances'][:3]]) if result['structure']['resistances'] else 'N/A'}
- Patrones Detectados: {result['structure']['patterns']['count']}

JUSTIFICACIÓN COMPLETA:
{result['message']}

==============================
© Crypto Trader Analyst Pro - Sistema Experto de Trading
"""
    
    return report, 200, {
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': f'attachment; filename=analisis_{symbol}_{interval}_{datetime.now().strftime("%Y%m%d")}.txt'
    }

# === FUNCIÓN COMPLETA: api_run_scheduled ===
# Ubicación: Reemplazar entre línea 1950 y línea 1980 aproximadamente

@app.route('/api/run_scheduled', methods=['POST'])
def api_run_scheduled():
    """Ejecutar análisis programado para temporalidades específicas - CON GRÁFICOS Y PATRONES"""
    try:
        # Verificar autenticación simple (evitar ejecución no autorizada)
        auth_key = request.headers.get('X-Auth-Key')
        if auth_key != os.environ.get('SCHEDULED_AUTH_KEY', 'crypto_trader_analyst_2025'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos'}), 400
        
        timeframe = data.get('timeframe')
        if timeframe not in TIMEFRAMES:
            return jsonify({'success': False, 'error': f'Temporalidad no válida: {timeframe}'}), 400
        
        print(f"🚀 Ejecutando análisis programado para {timeframe}")
        results = expert_system.analyze_all_pairs(timeframe)
        
        messages_sent = 0
        for symbol, result in results.items():
            if result['success']:
                action = result['decision']['action']
                confidence = result['decision']['confidence']
                print(f"   📊 {symbol}: {action} (confianza {confidence:.0f}%)")
                
                # Generar mensaje de patrón de vela
                pattern_message = expert_system.generate_pattern_alert(result)
                
                # Mensaje completo
                full_message = result['message']
                if pattern_message:
                    full_message += f"\n\n{pattern_message}"
                
                # Generar gráfico con TOP indicadores que generaron la señal
                img = expert_system.generate_chart_image(symbol, timeframe, result)
                
                # Enviar mensaje con gráfico
                if expert_system.send_telegram_alert(full_message, img):
                    messages_sent += 1
                    print(f"      ✅ Enviado con gráfico y patrón")
                else:
                    # Reintentar solo texto
                    expert_system.send_telegram_alert(full_message, None)
                    print(f"      ⚠️ Enviado solo texto")
        
        return jsonify({
            'success': True,
            'timeframe': timeframe,
            'messages_sent': messages_sent,
            'total_pairs': len(results),
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
    except Exception as e:
        print(f"❌ Error en análisis programado: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
# === FIN FUNCIÓN COMPLETA ===


# ============================================================================
# ENDPOINTS NUEVOS - FASE 5 (FUTUROS Y REVIEWTRADER)
# ============================================================================
# Los siguientes endpoints son ADITIVOS - no modifican los endpoints existentes.
# Requieren: futures_system.py y review_trader.py (y opcionalmente supabase_client.py)


# --- HELPER: Instanciar sistemas de forma tolerante ---
def _get_futures_system():
    """Obtiene la instancia de FuturesAnalysis o None si no está disponible"""
    try:
        from futures_system import futures_system
        return futures_system
    except Exception as e:
        print(f"⚠️ FuturesSystem no disponible: {e}")
        return None


def _get_review_trader():
    """Obtiene la instancia de ReviewTrader o None si no está disponible"""
    try:
        from review_trader import review_trader
        return review_trader
    except Exception as e:
        print(f"⚠️ ReviewTrader no disponible: {e}")
        return None


# ============================================================================
# ENDPOINT 1: Analizar UN par de futuros
# ============================================================================
@app.route('/api/futures/analyze', methods=['POST'])
def api_futures_analyze():
    """
    Analiza un par específico de futuros.
    
    Body JSON: { "symbol": "BTC-USDT", "timeframe": "1h" }
    """
    try:
        futures = _get_futures_system()
        if futures is None:
            return jsonify({
                'success': False,
                'error': 'FuturesSystem no disponible'
            }), 503
        
        data = request.get_json() if request.is_json else {}
        symbol = data.get('symbol', 'BTC-USDT')
        timeframe = data.get('timeframe', '1h')
        
        result = futures.analyze_futures_market(symbol, timeframe)
        
        if not result:
            return jsonify({'success': False, 'error': 'Análisis vacío'}), 500
        
        # Envolver en formato consistente con /api/analyze
        return jsonify({
            'success': result.get('success', True),
            'data': result if result.get('success') else None,
            'error': result.get('error')
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500


# ============================================================================
# ENDPOINT 2: Analizar TODOS los pares de futuros en una temporalidad
# ============================================================================
@app.route('/api/futures/analyze_all/<timeframe>')
def api_futures_analyze_all(timeframe):
    """
    Analiza los 5 pares de futuros en la temporalidad dada.
    URL: /api/futures/analyze_all/1h
    """
    try:
        futures = _get_futures_system()
        if futures is None:
            return jsonify({'success': False, 'error': 'FuturesSystem no disponible'}), 503
        
        results = futures.analyze_all_futures_pairs(timeframe)
        
        return jsonify({
            'success': True,
            'timeframe': timeframe,
            'data': results,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500


# ============================================================================
# ENDPOINT 3: Señales LONG/SHORT activas (futuros)
# ============================================================================
@app.route('/api/futures/signals/active')
def api_futures_signals_active():
    """
    Retorna todas las señales LONG/SHORT activas en los 5 pares y 6 temporalidades.
    """
    try:
        futures = _get_futures_system()
        if futures is None:
            return jsonify({'success': False, 'error': 'FuturesSystem no disponible'}), 503
        
        from futures_system import FUTURES_SYMBOLS, FUTURES_TIMEFRAMES
        
        active_signals = []
        
        # Recorrer combinaciones (limitado a las TF más comunes para no saturar)
        for symbol in FUTURES_SYMBOLS.keys():
            for timeframe in FUTURES_TIMEFRAMES.keys():
                try:
                    result = futures.analyze_futures_market(symbol, timeframe)
                    if not result or not result.get('success'):
                        continue
                    
                    decision = result.get('decision', {})
                    action = decision.get('action', 'NO_OPERAR')
                    confidence = decision.get('confidence', 0)
                    
                    if action in ('LONG', 'SHORT') and confidence >= 60:
                        levels = result.get('levels', {})
                        active_signals.append({
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'action': action,
                            'confidence': confidence,
                            'entry': levels.get('entry'),
                            'stop_loss': levels.get('stop_loss'),
                            'take_profit': levels.get('take_profit'),
                            'leverage': levels.get('leverage'),
                            'risk_reward': levels.get('risk_reward'),
                            'roi_tp': levels.get('roi_tp', 0),
                            'roi_sl': levels.get('roi_sl', 0),
                            'tp_source': levels.get('tp_source'),
                            'sl_source': levels.get('sl_source')
                        })
                except Exception as e:
                    logger.warning(f"Error en {symbol} {timeframe}: {e}")
                    continue
        
        # Ordenar por confianza descendente
        active_signals.sort(key=lambda x: -x['confidence'])
        
        return jsonify({
            'success': True,
            'total': len(active_signals),
            'signals': active_signals,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500


# ============================================================================
# ENDPOINT 4: Recomendaciones del ReviewTrader
# ============================================================================
@app.route('/api/review/recommendations/<symbol>/<timeframe>/<action>')
def api_review_recommendations(symbol, timeframe, action):
    """
    Retorna las recomendaciones cacheadas del ReviewTrader para (symbol, TF, action).
    URL: /api/review/recommendations/BTC-USDT/1h/LONG
    """
    try:
        review = _get_review_trader()
        if review is None:
            return jsonify({'success': False, 'error': 'ReviewTrader no disponible'}), 503
        
        recommendations = review.get_recommendations_for(symbol, timeframe, action)
        
        return jsonify({
            'success': True,
            'data': recommendations,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500


# ============================================================================
# ENDPOINT 5: Estadísticas generales del ReviewTrader
# ============================================================================
@app.route('/api/review/general_stats')
def api_review_general_stats():
    """
    Retorna las estadísticas generales (agregadas por estrategia) del ReviewTrader.
    """
    try:
        review = _get_review_trader()
        if review is None:
            return jsonify({'success': False, 'error': 'ReviewTrader no disponible'}), 503
        
        stats = review.get_general_recommendations()
        
        return jsonify({
            'success': True,
            'total': len(stats),
            'stats': stats,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500


# ============================================================================
# ENDPOINT 6: Trigger manual del ciclo completo del ReviewTrader
# ============================================================================
@app.route('/api/review/run_now', methods=['POST'])
def api_review_run_now():
    """
    Ejecuta el ciclo completo del ReviewTrader manualmente:
    1. Evalúa señales pendientes (TP/SL)
    2. Detecta oportunidades perdidas
    3. Recalcula estadísticas
    4. Aplica optimizaciones de almacenamiento
    
    Protección: Requiere header X-Auth-Key con la misma key que /api/run_scheduled.
    """
    try:
        # Autenticación
        auth_key = request.headers.get('X-Auth-Key')
        expected_key = os.environ.get('SCHEDULED_AUTH_KEY', 'crypto_trader_analyst_2025')
        if auth_key != expected_key:
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        review = _get_review_trader()
        if review is None:
            return jsonify({'success': False, 'error': 'ReviewTrader no disponible'}), 503
        
        # Usar el fetcher del expert_system principal
        def price_fetcher(symbol, timeframe):
            return expert_system.get_kucoin_data(symbol, timeframe)
        
        results = review.run_full_review(price_fetcher, trigger_source='manual')
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500


# ============================================================================
# ENDPOINT AUXILIAR: Health check extendido con estado de Supabase/ReviewTrader
# ============================================================================
@app.route('/api/review/health')
def api_review_health():
    """Estado de salud del ReviewTrader y Supabase"""
    try:
        review = _get_review_trader()
        futures = _get_futures_system()
        
        review_status = {
            'available': review is not None,
            'supabase_connected': review.db.enabled if review else False,
            'health': review.db.health_check() if review and review.db.enabled else None,
            'storage': review.db.get_storage_stats() if review and review.db.enabled else None
        }
        
        futures_status = {
            'available': futures is not None,
        }
        
        return jsonify({
            'success': True,
            'review': review_status,
            'futures': futures_status,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ENDPOINTS FASE B: Analytics (estadísticas para gráficos)
# ============================================================================

def _get_analytics_service():
    """Obtiene la instancia de AnalyticsService o None"""
    try:
        from analytics_service import analytics_service
        return analytics_service
    except Exception as e:
        print(f"⚠️ AnalyticsService no disponible: {e}")
        return None


def _parse_analytics_filters():
    """Extrae filtros comunes de query params"""
    args = request.args
    return {
        'symbol':      args.get('symbol') or None,
        'timeframe':   args.get('timeframe') or None,
        'system_type': args.get('system_type') or None,
        'action':      args.get('action') or None,
        'days_back':   int(args.get('days_back', 90))
    }


@app.route('/api/analytics/summary')
def api_analytics_summary():
    """Retorna KPIs globales con filtros opcionales"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        filters = _parse_analytics_filters()
        data = svc.get_summary(**filters)
        return jsonify({'success': True, 'data': data, 'timestamp': datetime.now(bolivia_tz).isoformat()})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics/strategies')
def api_analytics_strategies():
    """Ranking de estrategias por win rate"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        filters = _parse_analytics_filters()
        top_n = int(request.args.get('top_n', 30))
        data = svc.get_strategies_ranking(top_n=top_n, **filters)
        return jsonify({'success': True, 'data': data, 'total': len(data)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics/heatmap')
def api_analytics_heatmap():
    """Heatmap símbolo × timeframe"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        args = request.args
        data = svc.get_heatmap_data(
            system_type=args.get('system_type') or None,
            action=args.get('action') or None,
            days_back=int(args.get('days_back', 90))
        )
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics/timeline')
def api_analytics_timeline():
    """Evolución temporal del win_rate"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        filters = _parse_analytics_filters()
        bucket = request.args.get('bucket', 'week')  # week | day
        data = svc.get_timeline(bucket=bucket, **filters)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics/pnl_distribution')
def api_analytics_pnl():
    """Distribución de PnL (histograma)"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        filters = _parse_analytics_filters()
        data = svc.get_pnl_distribution(**filters)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics/top_operations')
def api_analytics_top_operations():
    """Top N mejores o peores operaciones"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        filters = _parse_analytics_filters()
        mode = request.args.get('mode', 'best')  # best | worst
        top_n = int(request.args.get('top_n', 10))
        data = svc.get_top_operations(top_n=top_n, mode=mode, **filters)
        return jsonify({'success': True, 'data': data, 'mode': mode})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analytics/operation_detail/<signal_id>')
def api_analytics_operation_detail(signal_id):
    """Detalle completo de una señal específica"""
    try:
        svc = _get_analytics_service()
        if svc is None:
            return jsonify({'success': False, 'error': 'AnalyticsService no disponible'}), 503
        
        detail = svc.get_operation_detail(signal_id)
        if not detail:
            return jsonify({'success': False, 'error': 'Señal no encontrada'}), 404
        return jsonify({'success': True, 'data': detail})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ENDPOINT (Fase A): Logs del ReviewTrader
# ============================================================================
@app.route('/api/review/logs')
def api_review_logs():
    """Retorna los últimos N logs del ReviewTrader (default 50)"""
    try:
        review = _get_review_trader()
        if review is None:
            return jsonify({'success': False, 'error': 'ReviewTrader no disponible'}), 503
        
        limit = int(request.args.get('limit', 50))
        limit = max(1, min(200, limit))  # cap entre 1 y 200
        
        logs = review.db.get_recent_review_logs(limit=limit)
        last_log = logs[0] if logs else None
        
        return jsonify({
            'success': True,
            'total': len(logs),
            'last_log': last_log,
            'logs': logs,
            'timestamp': datetime.now(bolivia_tz).isoformat()
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# === FIN ENDPOINTS FASE 5 ===

# ============================================================================
# VERIFICACIÓN DE INICIALIZACIÓN
# ============================================================================

print("=" * 60)
print("🚀 CRYPTO TRADER ANALYST PRO - INICIANDO SISTEMA")
print("=" * 60)
print(f"✅ Zona horaria: Bolivia (America/La_Paz)")
print(f"✅ Pares configurados: {list(SYMBOLS.keys())}")
print(f"✅ Temporalidades: {list(TIMEFRAMES.keys())}")
print(f"✅ Horarios 4H: {TIMEFRAMES['4h']['execution']}")
print(f"✅ Horarios 12H: {TIMEFRAMES['12h']['execution']}")
print(f"✅ Horario 1D: {TIMEFRAMES['1D']['execution']}")
print(f"✅ Horario 1W: {TIMEFRAMES['1W']['execution']}")
print("=" * 60)

# ============================================================================
# SISTEMA DE ALERTAS TELEGRAM - VERSIÓN CON VENTANA ACTIVA
# ============================================================================

# Control de ejecuciones (evita duplicados)
ultima_ejecucion = {
    '4h': datetime.min,
    '12h': datetime.min,
    '1D': datetime.min,
    '1W': datetime.min,
    'REVIEW': datetime.min  # FASE 7: Ciclo diario del ReviewTrader
}

# Control de mensajes enviados por día (persistente)
mensajes_enviados_hoy = {}

def verificar_y_ejecutar():
    """
    Bucle principal que verifica horarios CADA MINUTO
    AHORA CON MÚLTIPLES OPORTUNIDADES DENTRO DE LA VENTANA
    """
    print("\n" + "="*60)
    print("🕐 SISTEMA DE ALERTAS INICIADO - Verificando cada 60 segundos")
    print("="*60)
    
    while True:
        try:
            ahora = datetime.now(bolivia_tz)
            hora = ahora.hour
            minuto = ahora.minute
            minuto_actual = hora * 60 + minuto
            dia_semana = ahora.strftime('%A')
            
            # ============ VERIFICAR 4H ============
            # Cierres: 23:00, 03:00, 07:00, 11:00, 15:00, 19:00
            horas_4h = [23, 3, 7, 11, 15, 19]
            
            for hora_cierre in horas_4h:
                cierre = hora_cierre * 60
                inicio_ventana = cierre - 30
                fin_ventana = cierre - 1
                
                # ✅ AHORA: Verifica CADA MINUTO dentro de la ventana
                if inicio_ventana <= minuto_actual <= fin_ventana:
                    # Evitar ejecutar más de una vez por minuto
                    if (ahora - ultima_ejecucion['4h']).total_seconds() > 50:
                        print(f"\n🚀 DENTRO DE VENTANA 4H - {hora:02d}:{minuto:02d}")
                        print(f"   Ventana activa: {inicio_ventana//60:02d}:{inicio_ventana%60:02d} - {fin_ventana//60:02d}:{fin_ventana%60:02d}")
                        ultima_ejecucion['4h'] = ahora
                        threading.Thread(target=ejecutar_analisis_completo, args=('4h',), daemon=True).start()
            
            # ============ VERIFICAR 12H ============
            horas_12h = [7, 19]
            
            for hora_cierre in horas_12h:
                cierre = hora_cierre * 60
                inicio_ventana = cierre - 60
                fin_ventana = cierre - 1
                
                if inicio_ventana <= minuto_actual <= fin_ventana:
                    if (ahora - ultima_ejecucion['12h']).total_seconds() > 50:
                        print(f"\n🚀 DENTRO DE VENTANA 12H - {hora:02d}:{minuto:02d}")
                        ultima_ejecucion['12h'] = ahora
                        threading.Thread(target=ejecutar_analisis_completo, args=('12h',), daemon=True).start()
            
            # ============ VERIFICAR 1D ============
            cierre_1d = 19 * 60
            inicio_1d = cierre_1d - 120
            fin_1d = cierre_1d - 1
            
            if inicio_1d <= minuto_actual <= fin_1d:
                if (ahora - ultima_ejecucion['1D']).total_seconds() > 50:
                    print(f"\n🚀 DENTRO DE VENTANA 1D - {hora:02d}:{minuto:02d}")
                    ultima_ejecucion['1D'] = ahora
                    threading.Thread(target=ejecutar_analisis_completo, args=('1D',), daemon=True).start()
            
            # ============ VERIFICAR 1W ============
            if dia_semana == 'Sunday':
                cierre_1w = 19 * 60
                inicio_1w = cierre_1w - 240
                fin_1w = cierre_1w - 1
                
                if inicio_1w <= minuto_actual <= fin_1w:
                    if (ahora - ultima_ejecucion['1W']).total_seconds() > 50:
                        print(f"\n🚀 DENTRO DE VENTANA 1W - {hora:02d}:{minuto:02d}")
                        ultima_ejecucion['1W'] = ahora
                        threading.Thread(target=ejecutar_analisis_completo, args=('1W',), daemon=True).start()
            
            # ============ FASE 7: EJECUTAR REVIEWTRADER DIARIAMENTE ============
            # Cierre a las 20:00 Bolivia (después de todos los análisis del día)
            # Ejecuta: evaluar pendientes + detectar oportunidades perdidas + recalcular stats
            if hora == 20 and minuto == 0:
                # Evitar ejecutar más de una vez por día
                if 'REVIEW' not in ultima_ejecucion or (ahora - ultima_ejecucion.get('REVIEW', datetime.min.replace(tzinfo=bolivia_tz))).total_seconds() > 3600:
                    print(f"\n🎓 EJECUTANDO CICLO DIARIO DEL REVIEWTRADER - {hora:02d}:{minuto:02d}")
                    ultima_ejecucion['REVIEW'] = ahora
                    threading.Thread(target=ejecutar_review_diario, daemon=True).start()
            
            # Heartbeat cada 5 minutos
            if minuto % 5 == 0 and ahora.second < 10:
                print(f"💓 Heartbeat - {hora:02d}:{minuto:02d}:{ahora.second:02d} - Sistema activo")
            
            # ⚠️ CLAVE: Siempre dormir 60 segundos
            time.sleep(60)
            
        except Exception as e:
            print(f"❌ Error en verificación: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)

def ejecutar_analisis_completo(timeframe):
    """
    Ejecuta análisis para los 3 pares y envía a Telegram
    AHORA CON TODOS LOS INDICADORES EN LA IMAGEN
    """
    try:
        print(f"\n{'='*60}")
        print(f"🚀 EJECUTANDO ANÁLISIS {timeframe}")
        print(f"{'='*60}")
        
        global mensajes_enviados_hoy
        ahora = datetime.now(bolivia_tz)
        fecha_str = ahora.strftime('%Y-%m-%d')
        
        resultados = {}
        señales_procesadas = 0
        
        # ============ DEFINIR LÍMITES POR TEMPORALIDAD ============
        limites = {
            '4h': {'max_por_par': 6, 'ventana_minutos': 30},
            '12h': {'max_por_par': 2, 'ventana_minutos': 60},
            '1D': {'max_por_par': 1, 'ventana_minutos': 120},
            '1W': {'max_por_par': 1, 'ventana_minutos': 240}
        }
        
        limite = limites.get(timeframe, {'max_por_par': 1, 'ventana_minutos': 30})
        max_por_par = limite['max_por_par']
        
        # Clave para saber qué señales ya se enviaron en ESTA ventana
        ventana_clave = f"señales_{timeframe}_{fecha_str}_{ahora.strftime('%H:%M')}"
        
        if not hasattr(expert_system, 'señales_ventana'):
            expert_system.señales_ventana = {}
        
        # ============ ANALIZAR LOS 3 PARES ============
        pares = ['BTC-USDT', 'PAXG-USDT', 'PAXG-BTC']
        
        for i, par in enumerate(pares):
            print(f"\n📊 [{i+1}/3] Analizando {par}...")
            try:
                if par == 'BTC-USDT':
                    resultado = expert_system.analyze_full_market(par, timeframe)
                elif par == 'PAXG-USDT':
                    resultado = expert_system.analyze_full_market(par, timeframe, 
                                                                 btc_analysis=resultados.get('BTC-USDT'))
                else:
                    resultado = expert_system.analyze_full_market(par, timeframe,
                                                                 btc_analysis=resultados.get('BTC-USDT'),
                                                                 paxg_analysis=resultados.get('PAXG-USDT'))
                
                if resultado and resultado.get('success'):
                    resultados[par] = resultado
                    decision = resultado['decision']['action']
                    confianza = resultado['decision']['confidence']
                    print(f"   ✅ {par}: {decision} ({confianza:.0f}%)")
                    
                    # ============ VERIFICAR SI DEBE ENVIARSE ============
                    # 1. ¿Es señal de trading?
                    if decision not in ['COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT']:
                        print(f"   ⏸️ No es señal de trading")
                        continue
                    
                    # 2. ¿Confianza suficiente?
                    if confianza < 60:
                        print(f"   ⏸️ Confianza baja ({confianza}%)")
                        continue
                    
                    # 3. ¿Ya enviamos esta señal en esta ventana?
                    señal_clave = f"{ventana_clave}_{par}"
                    if señal_clave in expert_system.señales_ventana:
                        print(f"   ⏸️ {par} ya enviado en esta ventana")
                        continue
                    
                    # 4. Control diario por par
                    contador_clave = f"{par}_{timeframe}_{fecha_str}"
                    if contador_clave not in mensajes_enviados_hoy:
                        mensajes_enviados_hoy[contador_clave] = 0
                    
                    if mensajes_enviados_hoy[contador_clave] >= max_por_par:
                        print(f"   ⏸️ {par} ya alcanzó límite diario ({max_por_par})")
                        continue
                    
                    # ============ OBTENER TOP 4 INDICADORES ============
                    top_indicadores = expert_system.get_top_indicators_for_chart(resultado)
                    
                    # ============ CONSTRUIR MENSAJE ============
                    symbol_name = SYMBOLS.get(par, {'name': par})['name']
                    emoji = '🟢' if 'COMPRA' in decision or 'LONG' in decision else '🔴'
                    
                    mensaje = f"{emoji} {decision} DE {symbol_name} en {timeframe}\n"
                    mensaje += f"Confianza: {confianza:.0f}%\n"
                    mensaje += f"📊 Indicadores clave: {', '.join(top_indicadores[:4])}\n\n"
                    mensaje += resultado.get('message', '')
                    
                    # ============ GENERAR IMAGEN CON TODOS LOS INDICADORES ============
                    print(f"   🖼️ Generando imagen con todos los indicadores...")
                    imagen = None
                    try:
                        # Pasar los top_indicadores para que se dibujen en los subplots 2-5
                        imagen = expert_system.generate_chart_image(par, timeframe, resultado, top_indicadores)
                        if imagen:
                            print(f"      ✅ Imagen generada ({len(imagen)} bytes)")
                    except Exception as e:
                        print(f"      ⚠️ Error imagen: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # ============ ENVIAR ============
                    if expert_system.send_telegram_alert(mensaje, imagen):
                        print(f"   ✅ {par} ENVIADO a Telegram")
                        expert_system.señales_ventana[señal_clave] = ahora
                        mensajes_enviados_hoy[contador_clave] += 1
                        señales_procesadas += 1
                    else:
                        print(f"   ❌ {par} no se pudo enviar")
                else:
                    print(f"   ❌ {par} falló")
            except Exception as e:
                print(f"   ❌ Error en {par}: {e}")
                import traceback
                traceback.print_exc()
        
        # Limpiar señales_ventana viejas (más de 2 horas)
        ahora_ts = time.time()
        for key in list(expert_system.señales_ventana.keys()):
            if (ahora_ts - expert_system.señales_ventana[key].timestamp()) > 7200:
                del expert_system.señales_ventana[key]
        
        print(f"\n✅ ANÁLISIS {timeframe} COMPLETADO - {ahora.strftime('%H:%M:%S')}")
        print(f"📤 Señales enviadas en esta ejecución: {señales_procesadas}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ Error CRÍTICO en ejecutar_analisis_completo: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# FASE 7: FUNCIÓN DEL CICLO DIARIO DEL REVIEWTRADER
# ============================================================================

def ejecutar_review_diario():
    """
    Ejecuta el ciclo completo del ReviewTrader una vez al día.
    - Evalúa señales pendientes (TP/SL/expired)
    - Detecta oportunidades perdidas
    - Recalcula estadísticas
    - Aplica optimizaciones de almacenamiento
    """
    try:
        print(f"\n{'#'*60}")
        print(f"# 🎓 EJECUTANDO REVIEWTRADER DIARIO - {datetime.now(bolivia_tz).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}\n")
        
        # Importar de forma diferida (por si review_trader no está disponible)
        try:
            from review_trader import review_trader
        except Exception as e:
            print(f"❌ ReviewTrader no disponible: {e}")
            return
        
        if not review_trader.db.enabled:
            print("⚠️ Supabase no configurado - saltando ciclo diario de review")
            return
        
        # Fetcher de precios reutilizando el sistema principal
        def price_fetcher(symbol, timeframe):
            return expert_system.get_kucoin_data(symbol, timeframe)
        
        results = review_trader.run_full_review(price_fetcher, trigger_source='scheduler')
        
        print(f"\n{'#'*60}")
        print(f"# ✅ REVIEWTRADER DIARIO COMPLETADO")
        print(f"{'#'*60}")
        print(f"Evaluated: {results.get('evaluated', {})}")
        print(f"Missed opportunities: {results.get('missed', 0)}")
        print(f"Stats: {results.get('stats', {})}")
        print(f"{'#'*60}\n")
        
    except Exception as e:
        print(f"❌ Error en ejecutar_review_diario: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# INICIALIZACIÓN (REEMPLAZA TODO LO QUE TENÍAS AL FINAL)
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 CRYPTO TRADER ANALYST PRO - INICIANDO")
    print("=" * 60)
    
    # Verificar Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("✅ Telegram OK")
        try:
            expert_system.send_telegram_alert("🚀 Sistema iniciado - Versión Estable", None)
            print("✅ Mensaje de prueba enviado")
        except Exception as e:
            print(f"⚠️ No se pudo enviar mensaje: {e}")
    else:
        print("❌ Telegram no configurado")
    
    # Iniciar verificador de horarios en hilo SEPARADO
    print("\n🕐 Iniciando verificador de horarios...")
    verificador_thread = threading.Thread(target=verificar_y_ejecutar, daemon=True)
    verificador_thread.start()
    print("✅ Verificador iniciado (revisa cada 30 segundos)")
    
    # Iniciar Flask
    print("\n🌐 Iniciando servidor Flask...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
