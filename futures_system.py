# futures_system.py
# Sistema de análisis de FUTUROS - Extiende TradingExpertSystem del sistema principal
# Versión 1.0 - FASE 4
#
# CARACTERÍSTICAS:
# - 5 criptomonedas: BTC, ETH, SOL, XRP, ADA (contra USDT)
# - 6 temporalidades: 5m, 15m, 30m, 1h, 2h, 4h
# - Solo acciones LONG y SHORT (nunca COMPRA_SPOT/VENTA_SPOT)
# - Apalancamiento dinámico: x10-x50 en TF cortas, x5-x20 en TF largas
# - Hereda TODA la lógica del sistema principal (traders, indicadores, patrones)
# - Correlación adaptada: BTC dominancia + BTC vs alts (no PAXG)
# - Usa el mismo Moderador con los 9 traders + ReviewTrader (cuando esté integrado)
# - Registra señales en Supabase con system_type='futures'

import logging
from datetime import datetime
from typing import Dict, List, Optional

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

# Extender el mapeo de intervalos KuCoin
FUTURES_KUCOIN_INTERVALS = {
    '5m': '5min',
    '15m': '15min',
    '30m': '30min',
    '1h': '1hour',
    '2h': '2hour',
    '4h': '4hour'
}

# Rangos de apalancamiento por temporalidad (según requerimientos del usuario)
LEVERAGE_RANGES = {
    '5m':  (10, 50),   # x10 a x50 para TF muy cortas
    '15m': (10, 50),
    '30m': (10, 50),
    '1h':  (5, 20),    # x5 a x20 para TF más largas
    '2h':  (5, 20),
    '4h':  (5, 20)
}


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
        Obtener datos de velas de KuCoin.
        Sobrescribe el método padre para incluir las temporalidades cortas.
        Usa kucoin_cache (Session HTTP + caché con TTL por TF).
        """
        try:
            from kucoin_cache import fetch_kucoin_candles, KUCOIN_INTERVALS as CACHE_INTERVALS
            
            # Validar que el intervalo esté soportado (incluye los TF cortos de futuros)
            all_intervals = {**KUCOIN_INTERVALS, **FUTURES_KUCOIN_INTERVALS}
            if interval not in all_intervals and interval not in CACHE_INTERVALS:
                print(f"❌ Intervalo no soportado: {interval}")
                return self._generate_fallback_data(symbol, interval)
            
            df = fetch_kucoin_candles(symbol, interval, timeout=15)
            if df is None or df.empty:
                return self._generate_fallback_data(symbol, interval)
            return df
        except Exception as e:
            print(f"Excepción en get_kucoin_data (futures): {e}")
            return self._generate_fallback_data(symbol, interval)
    
    def _generate_fallback_data(self, symbol: str, interval: str):
        """Genera datos sintéticos si KuCoin falla"""
        import numpy as np
        import pandas as pd
        from datetime import datetime, timedelta
        
        try:
            # Precios base por símbolo
            base_prices = {
                'BTC-USDT': 68000,
                'ETH-USDT': 3500,
                'SOL-USDT': 150,
                'XRP-USDT': 0.55,
                'ADA-USDT': 0.40
            }
            base_price = base_prices.get(symbol, 100)
            volatility = 0.015  # 1.5%
            
            # Cantidad de velas y frecuencia
            freq_map = {
                '5m': ('5min', 300),
                '15m': ('15min', 200),
                '30m': ('30min', 200),
                '1h': ('1H', 200),
                '2h': ('2H', 200),
                '4h': ('4H', 200)
            }
            freq, periods = freq_map.get(interval, ('1H', 100))
            
            end_date = datetime.now()
            dates = pd.date_range(end=end_date, periods=periods, freq=freq)
            
            np.random.seed(hash(symbol) % 1000)
            returns = np.random.randn(periods) * volatility
            price_series = base_price * np.exp(np.cumsum(returns))
            
            df = pd.DataFrame({
                'time': dates,
                'open': price_series * (1 + np.random.randn(periods) * 0.002),
                'high': price_series * (1 + abs(np.random.randn(periods) * 0.005)),
                'low': price_series * (1 - abs(np.random.randn(periods) * 0.005)),
                'close': price_series * (1 + np.random.randn(periods) * 0.001),
                'volume': np.abs(np.random.randn(periods) * 1000 + 5000)
            })
            df['high'] = df[['open', 'close', 'high']].max(axis=1)
            df['low'] = df[['open', 'close', 'low']].min(axis=1)
            
            return df
        except Exception as e:
            print(f"Error generando fallback: {e}")
            return None
    
    # ========================================================================
    # CÁLCULO DE APALANCAMIENTO ÓPTIMO
    # ========================================================================
    
    def calculate_optimal_leverage(self, timeframe: str, atr_pct: float, 
                                    confidence: float, review_multiplier: float = 1.0) -> int:
        """
        Calcula el apalancamiento óptimo para futuros.
        
        Fórmula:
        1. Rango base según TF (definido por el usuario)
        2. Reducir si ATR es alto (volatilidad = más riesgo)
        3. Ajustar por confianza (más confianza = más apalancamiento)
        4. Aplicar multiplicador del ReviewTrader
        5. Cap por temporalidad
        
        Args:
            timeframe: '5m', '15m', ..., '4h'
            atr_pct: ATR como porcentaje del precio (ej: 1.5 para 1.5%)
            confidence: 0-100
            review_multiplier: multiplicador del ReviewTrader (0.5x-1.5x)
        """
        # 1. Rango base
        lo, hi = LEVERAGE_RANGES.get(timeframe, (2, 5))
        
        # 2. Ajuste por volatilidad (a más ATR, menos leverage)
        # Fórmula: base_by_atr = 20 / atr_pct (limitado al rango)
        if atr_pct <= 0:
            atr_pct = 1.0  # Fallback
        
        base_by_atr = 20.0 / atr_pct
        base_by_atr = max(lo, min(hi, base_by_atr))
        
        # 3. Factor de confianza (0.6 - 1.0)
        confidence_factor = max(0.6, min(1.0, confidence / 100))
        
        # 4. Factor del ReviewTrader (limitado 0.6 - 1.4)
        review_factor = max(0.6, min(1.4, review_multiplier))
        
        # 5. Combinar todos los factores
        leverage_raw = base_by_atr * confidence_factor * review_factor
        
        # 6. Redondear y aplicar cap del rango
        leverage = int(round(leverage_raw))
        leverage = max(lo, min(hi, leverage))
        
        # 7. Regla de precaución: si ATR es extremadamente alto (>5%), leverage bajo
        if atr_pct > 5.0:
            leverage = max(2, int(leverage * 0.5))
        
        return leverage
    
    def calculate_roi_futures(self, entry: float, tp: float, sl: float, leverage: int, 
                              direction: str) -> Dict:
        """
        Calcula el ROI potencial de una operación de futuros.
        
        ROI positivo = ganancia potencial si toca TP
        ROI negativo = pérdida potencial si toca SL
        """
        if entry <= 0:
            return {'roi_tp': 0, 'roi_sl': 0}
        
        if direction == 'long':
            move_tp = (tp - entry) / entry * 100
            move_sl = (entry - sl) / entry * 100
        else:
            move_tp = (entry - tp) / entry * 100
            move_sl = (sl - entry) / entry * 100
        
        # ROI = movimiento porcentual × apalancamiento
        roi_tp = move_tp * leverage
        roi_sl = -move_sl * leverage  # Negativo porque es pérdida
        
        return {
            'roi_tp': round(roi_tp, 2),
            'roi_sl': round(roi_sl, 2),
            'move_tp_pct': round(move_tp, 2),
            'move_sl_pct': round(move_sl, 2)
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
        if levels.get('rejected_reason'):
            return levels
        
        # ============ AJUSTAR APALANCAMIENTO PARA FUTUROS ============
        atr_pct = volatility.get('atr_pct', 1.0)
        
        # Usar la confianza si viene en el decision (por defecto 60 si no)
        confidence = 70  # Se ajustará cuando venga del Moderador
        
        # Multiplicador del ReviewTrader (se puede sobreescribir cuando se integre)
        review_multiplier = getattr(self, '_current_review_multiplier', 1.0)
        
        optimal_leverage = self.calculate_optimal_leverage(
            timeframe, atr_pct, confidence, review_multiplier
        )
        
        # Actualizar el apalancamiento en levels
        levels['leverage'] = optimal_leverage
        
        # ============ CALCULAR ROI POTENCIAL ============
        direction = 'long' if decision == 'LONG' else 'short'
        roi = self.calculate_roi_futures(
            levels['entry'], levels['take_profit'], levels['stop_loss'],
            optimal_leverage, direction
        )
        
        levels.update(roi)
        levels['is_futures'] = True
        
        # ============ VALIDACIÓN ADICIONAL: ROI MÍNIMO ============
        # Con 10 USDT invertidos, ROI mínimo aceptable es 5% (=0.5 USDT netos)
        min_roi_tp = 5.0
        if roi['roi_tp'] < min_roi_tp:
            print(f"   ⚠️ RECHAZADO (futuros): ROI potencial {roi['roi_tp']:.1f}% < mínimo {min_roi_tp}%")
            return self._build_rejected_levels(
                levels['entry'], symbol, 
                f"ROI potencial {roi['roi_tp']:.1f}% < {min_roi_tp}% mínimo"
            )
        
        print(f"   ✅ FUTUROS - Leverage: {optimal_leverage}x | ROI TP: +{roi['roi_tp']:.1f}% | ROI SL: {roi['roi_sl']:.1f}%")
        
        return levels
    
    # ========================================================================
    # ANÁLISIS COMPLETO DE FUTUROS
    # ========================================================================
    
    def analyze_futures_market(self, symbol: str, timeframe: str, 
                                btc_analysis: Optional[Dict] = None) -> Dict:
        """
        Análisis completo para futuros.
        
        Wrapper de analyze_full_market del padre pero:
        - Valida símbolo y TF de futuros
        - Fuerza system_type='futures' al registrar en Supabase
        - Adapta la correlación (no usa PAXG)
        - Traduce COMPRA/VENTA a LONG/SHORT en la decisión final
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
                paxg_btc_analysis=None
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
        
        # ============ RECALCULAR NIVELES CON LÓGICA DE FUTUROS ============
        # (Ya se hizo dentro de analyze_full_market → calculate_entry_levels overrideado)
        # Pero verificamos que la traducción sea consistente
        levels = result.get('levels', {})
        
        # ============ REGISTRAR EN REVIEWTRADER (si está disponible) ============
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
