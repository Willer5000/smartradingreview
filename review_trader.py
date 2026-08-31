# review_trader.py
# El Trader de Revisión: 10º trader del sistema, aprende del historial
# Versión 1.0 - FASE 2
#
# CARACTERÍSTICAS:
# - Evalúa TODAS las señales generadas por el sistema (incluidas las rechazadas por consenso)
# - Solo usa señales de la vela ANTERIOR (cerrada/estática), NUNCA la vela actual (dinámica)
# - Trata como equivalentes: COMPRA_SPOT ≡ LONG y VENTA_SPOT ≡ SHORT
# - Detecta oportunidades perdidas (NO_OPERAR que resultaron rentables)
# - Recalcula estadísticas individuales (par+TF+acción+estrategia) y generales (agregado)
# - Genera recomendaciones cacheadas para consumo del frontend
# - Vota en el Moderador con multiplicador de confianza (0.5x - 1.5x)
# - Tolerante a fallos: si Supabase no está disponible, retorna neutralidad

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from supabase_client import supabase_db

logger = logging.getLogger('REVIEW_TRADER')
logger.setLevel(logging.INFO)


# ============================================================================
# CONSTANTES
# ============================================================================

# Umbrales para clasificar estrategias
# NOTA: reducidos de 20/50 → 10/25 para tener aprendizaje visible antes.
# El sistema es joven y con umbrales altos el PDF muestra 0 durante semanas.
# A medida que se acumulen muestras se pueden ir subiendo (>= 20 estadísticamente
# más robusto, pero requiere que N combinaciones tengan >=20 muestras cada una).
MIN_SAMPLE_SIZE = 10              # Mínimo de muestras para considerar estadísticamente válido
MIN_SAMPLE_SIZE_GENERAL = 25      # Para stats generales necesitamos más muestras
WIN_RATE_WINNER = 60.0            # % para considerar estrategia "ganadora"
WIN_RATE_LOSER = 40.0             # % para considerar estrategia "perdedora"
DEGRADATION_THRESHOLD = 15.0      # Caída de win rate en últimas 20 vs histórico
# ============================================================================
# APRENDIZAJE CUANTITATIVO — FASE 6
# ============================================================================

# Priorizamos RENTABILIDAD REAL sobre Win Rate aislado.
MIN_EXPECTANCY_ACTIONABLE = 0.05

# Expectancy >= este valor se considera claramente positiva.
MIN_EXPECTANCY_STRONG = 0.20

# RR mínimo aceptable para una estrategia de trading.
MIN_REALIZED_RR = 1.20

# Muestra mínima para que el ReviewTrader pueda ejercer autoridad.
MIN_SAMPLE_ACTIONABLE = 10

# Muestra robusta.
MIN_SAMPLE_STRONG = 25

# Prior estadístico para evitar que 3/3 = 100% se considere una certeza.
BAYESIAN_PRIOR_WEIGHT = 8

# Para combinaciones evitamos combinaciones gigantes.
MAX_COMBINATION_STRATEGIES = 4

# Sólo las estrategias de estructura/liquidez más relevantes participan
# del setup SMC aprendido.
SMC_STRATEGY_KEYWORDS = (
    'LIQUIDITY',
    'SWEEP',
    'STOP_HUNT',
    'ORDER_BLOCK',
    'FVG',
    'FAIR_VALUE',
    'POC',
    'HVN',
    'VALUE_AREA',
    'PULLBACK',
    'CONFLUENCIA'
)
# Umbrales para oportunidades perdidas
MISSED_OPP_THRESHOLD_PCT = 2.0    # Movimiento a favor >2% para considerar oportunidad perdida
MISSED_OPP_MIN_CANDLES = 3        # Debe mantenerse al menos 3 velas para no ser un spike

# Multiplicador de confianza aplicable a los votos
MULTIPLIER_MIN = 0.5              # Cuando la estrategia falla históricamente
MULTIPLIER_MAX = 1.5              # Cuando la estrategia es muy ganadora
MULTIPLIER_NEUTRAL = 1.0          # Sin evidencia suficiente

# Tiempos de expiración de señales por temporalidad (horas)
# Después de este tiempo, si no hay TP/SL, se marca como 'expired'
SIGNAL_EXPIRATION = {
    '5m': 2,      # 2 horas = 24 velas
    '15m': 6,     # 6 horas = 24 velas
    '30m': 12,    # 12 horas = 24 velas
    '1h': 24,     # 24 horas
    '2h': 48,
    '4h': 96,     # 4 días
    '12h': 168,   # 7 días
    '1D': 336,    # 14 días
    '1W': 1680    # 10 semanas
}


# ============================================================================
# CLASE PRINCIPAL: REVIEW TRADER
# ============================================================================

class ReviewTrader:
    """
    El 10º trader del sistema. Aprende del historial almacenado en Supabase.
    
    Responsabilidades:
    1. Guardar todas las señales generadas (para aprendizaje futuro).
    2. Evaluar el resultado de señales anteriores (TP hit / SL hit / expired).
    3. Detectar oportunidades perdidas.
    4. Recalcular estadísticas de win rate por estrategia.
    5. Generar recomendaciones para el frontend.
    6. Votar en el Moderador basado en historial.
    """
    
    # Peso del trader en la votación del Moderador (compatible con TraderBase)
    def __init__(self):
        self.nombre = "Trader de Revisión"
        self.especialidad = "aprendizaje_historico"
        self.peso_base = 1.0
        self.db = supabase_db

        # ==============================================================
        # FASE 7E.3 — EXECUTION SAFETY
        # ==============================================================
        #
        # Al arrancar el servidor NO existe todavía una calibración
        # estadística cargada.
        #
        # Por seguridad:
        #
        #     None
        #
        # significa:
        #
        #     usar configuración estática original de futuros.
        #
        # Nunca se bloquea Futures porque ReviewTrader todavía no
        # haya recalculado sus estadísticas.
        # ==============================================================

        self._execution_safety_shadow_policy = None

        self._execution_safety_policy_updated_at = None
    
    # ========================================================================
    # 1. REGISTRO DE SEÑALES (llamado desde app.py o futures_system.py)
    # ========================================================================
    
    def register_signal(self, analysis_result: Dict, system_type: str = 'spot') -> Optional[str]:
        """
        Registra una señal generada por el sistema en Supabase.
        Se llama AUTOMÁTICAMENTE después de cada análisis, sin importar si la acción es
        de trading o NO_OPERAR. TODAS las señales se guardan para aprender.
        
        IMPORTANTE: Se usa el timestamp de la VELA ANTERIOR (cerrada), no la actual.
        
        analysis_result: el diccionario que retorna analyze_full_market()
        system_type: 'spot' o 'futures'
        
        OPTIMIZACIÓN (Fase 2.5): Aplica muestreo estratificado.
        En TF cortas (5m/15m), NO guarda señales NO_OPERAR con confianza baja
        para evitar sobrecargar la base de datos con ruido.
        """
        if not self.db.enabled:
            return None
        
        # ============ MUESTREO ESTRATIFICADO ============
        if not self.should_save_signal(analysis_result):
            return None  # Se descarta silenciosamente
        
        try:
            # Extraer timestamp de la vela ANTERIOR (penúltima en el df)
            candle_ts = self._get_previous_candle_timestamp(analysis_result)
            
            # Extraer estrategias detectadas por los traders
            strategies = self._extract_strategies(analysis_result)
            
            # Extraer snapshot de indicadores
            indicators = self._extract_indicators_snapshot(analysis_result)
            
            # Extraer contexto (sesión, día, sentimiento, etc.)
            context = self._extract_context(analysis_result)
            
            # Datos de la señal
            decision = analysis_result.get('decision', {})
            levels = analysis_result.get('levels', {})
            
            signal_data = {
                'symbol': analysis_result.get('symbol', ''),
                'timeframe': analysis_result.get('timeframe', ''),
                'system_type': system_type,
                'action': decision.get('action', 'NO_OPERAR'),
                'confidence': decision.get('confidence', 0),
                'entry': levels.get('entry', 0),
                'stop_loss': levels.get('stop_loss', 0),
                'take_profit': levels.get('take_profit', 0),
                'leverage': levels.get('leverage', 1),
                'risk_reward': levels.get('risk_reward', 0),
                'current_price': analysis_result.get('current_price', 0),
                'candle_timestamp': candle_ts,
                'strategies': strategies,
                'indicators_snapshot': indicators,
                'context': context
            }
            
            signal_id = self.db.insert_signal(signal_data)
            
            if signal_id:
                print(f"📝 [REVIEW] Señal registrada: {signal_data['symbol']} {signal_data['timeframe']} "
                      f"→ {signal_data['action']} (conf {signal_data['confidence']:.0f}%) - ID {signal_id[:8]}...")
            
            return signal_id
            
        except Exception as e:
            logger.error(f"Error registrando señal: {e}")
            return None
    
    def _get_previous_candle_timestamp(self, analysis: Dict) -> Optional[str]:
        """Extrae el timestamp de la vela ANTERIOR (penúltima en el df, no la actual)"""
        try:
            df = analysis.get('df', {})
            times = df.get('time', [])
            if len(times) >= 2:
                # Vela anterior = penúltima
                return times[-2]
            elif len(times) == 1:
                return times[-1]
            return datetime.utcnow().isoformat()
        except Exception:
            return datetime.utcnow().isoformat()
    
    def _extract_strategies(self, analysis: Dict) -> List[str]:
        """Extrae las estrategias detectadas por los 9 traders del sistema"""
        strategies = set()
        
        # Estrategias explícitas del consenso
        decision = analysis.get('decision', {})
        for est in decision.get('estrategias', []):
            if isinstance(est, str) and est:
                strategies.add(est.upper())
        
        # Estrategias del registro de votación (por trader)
        registro = decision.get('registro_votacion', {})
        if isinstance(registro, dict):
            todos = registro.get('todos_los_votos', [])
            for voto in todos:
                if isinstance(voto, dict):
                    for est in voto.get('estrategias', []):
                        if isinstance(est, str) and est:
                            strategies.add(est.upper())
        
        return sorted(list(strategies))
    
    def _extract_indicators_snapshot(self, analysis: Dict) -> Dict:
        """Extrae un snapshot compacto de los principales indicadores"""
        snapshot = {}
        
        trend = analysis.get('trend', {})
        momentum = analysis.get('momentum', {})
        volatility = analysis.get('volatility', {})
        volume = analysis.get('volume', {})
        
        # Tendencia
        snapshot['adx'] = float(trend.get('adx', 0) or 0)
        snapshot['plus_di'] = float(trend.get('plus_di', 0) or 0)
        snapshot['minus_di'] = float(trend.get('minus_di', 0) or 0)
        snapshot['trend_direction'] = trend.get('direction', 'neutral')
        
        # Momentum
        indicators = momentum.get('indicators', {}) or {}
        snapshot['rsi'] = float(indicators.get('rsi', 50) or 50)
        snapshot['rsi_maverick'] = float(indicators.get('rsi_maverick', 0.5) or 0.5)
        snapshot['macd_hist'] = float(indicators.get('macd_histogram', 0) or 0)
        snapshot['stoch_k'] = float(indicators.get('stoch_k', 50) or 50)
        snapshot['williams'] = float(indicators.get('williams', -50) or -50)
        snapshot['cci'] = float(indicators.get('cci', 0) or 0)
        
        # Volatilidad
        snapshot['atr_pct'] = float(volatility.get('atr_pct', 0) or 0)
        snapshot['ftm_state'] = volatility.get('ftm_state', 'NEUTRAL')
        snapshot['squeeze_on'] = bool(volatility.get('squeeze_on', False))
        
        # Volumen
        snapshot['volume_ratio'] = float(volume.get('volume_ratio', 1) or 1)
        snapshot['mfi'] = float(volume.get('mfi', 50) or 50)
        snapshot['whale_buy'] = bool(volume.get('whale_buy', False))
        snapshot['whale_sell'] = bool(volume.get('whale_sell', False))
        snapshot['obv_trend'] = volume.get('obv_trend', 'neutral')
        
        return snapshot
    
    def _extract_context(self, analysis: Dict) -> Dict:
        """Extrae contexto de mercado (sesión, día, sentimiento, correlación)"""
        context = {}
        
        market_hours = analysis.get('market_hours', {}) or {}
        sentiment = analysis.get('sentiment', {}) or {}
        correlation = analysis.get('correlation', {}) or {}
        
        context['session'] = market_hours.get('session', 'UNKNOWN')
        context['day_type'] = market_hours.get('day_type', 'UNKNOWN')
        context['liquidity'] = market_hours.get('liquidity', 'unknown')
        
        if sentiment.get('available'):
            context['fear_greed'] = int(sentiment.get('current_value', 50))
            context['sentiment_bias'] = sentiment.get('sentiment_bias', 'neutral')
        
        context['rotation_signal'] = correlation.get('rotation_signal', 'NEUTRAL')
        # ==============================================================
        # FASE 6 — CONTEXTO DE EJECUCIÓN
        # ==============================================================
        #
        # Estos datos NO cambian ninguna decisión.
        # Se guardan para que ReviewTrader pueda aprender
        # posteriormente qué calidad de entrada/SL/TP produce
        # mejores resultados reales.
        # ==============================================================

        levels = analysis.get(
            'levels',
            {}
        ) or {}

        def _safe_float(value, default=0.0):
            try:
                return float(
                    value
                    if value is not None
                    else default
                )
            except (
                TypeError,
                ValueError
            ):
                return default

        context['execution'] = {
            'entry_score': _safe_float(
                levels.get(
                    'entry_score',
                    0
                )
            ),

            'execution_safety': _safe_float(
                levels.get(
                    'execution_safety',
                    levels.get(
                        'execution_safety_score',
                        0
                    )
                )
            ),

            'sl_reliability': _safe_float(
                levels.get(
                    'sl_reliability',
                    0
                )
            ),

            'tp_quality_score': _safe_float(
                levels.get(
                    'tp_quality_score',
                    0
                )
            ),

            'risk_reward': _safe_float(
                levels.get(
                    'risk_reward',
                    0
                )
            ),

            'sl_distance_pct': _safe_float(
                levels.get(
                    'sl_distance_pct',
                    0
                )
            ),

            'tp_distance_pct': _safe_float(
                levels.get(
                    'tp_distance_pct',
                    0
                )
            ),

            'entry_source': str(
                levels.get(
                    'entry_source',
                    ''
                ) or ''
            ),

            'sl_source': str(
                levels.get(
                    'sl_source',
                    ''
                ) or ''
            ),

            'tp_source': str(
                levels.get(
                    'tp_source',
                    ''
                ) or ''
            )
        }        
        return context
    
    # ========================================================================
    # 2. EVALUAR RESULTADOS DE SEÑALES PENDIENTES
    # ========================================================================
    
    def evaluate_pending_signals(self, price_fetcher) -> Dict:
        """
        Recorre todas las señales pendientes y verifica si alcanzaron TP, SL o expiraron.
        
        price_fetcher: función que recibe (symbol, timeframe) y retorna un DataFrame
                       con las velas más recientes. Se usa la función get_kucoin_data
                       del sistema principal.
        
        Retorna: estadísticas del batch procesado.
        """
        if not self.db.enabled:
            return {'processed': 0, 'tp_hit': 0, 'sl_hit': 0, 'expired': 0}
        
        pending = self.db.get_pending_signals(hours_old_max=1680)  # Hasta 70 días atrás
        
        stats = {'processed': 0, 'tp_hit': 0, 'sl_hit': 0, 'expired': 0, 'still_pending': 0}
        
        print(f"\n{'='*60}")
        print(f"🔍 [REVIEW] Evaluando {len(pending)} señales pendientes")
        print(f"{'='*60}")
        
        for signal in pending:
            try:
                symbol = signal.get('symbol')
                timeframe = signal.get('timeframe')
                
                # Solo evaluar señales de trading (no NO_OPERAR, esas se evalúan en otro método)
                action_norm = signal.get('action_normalized')
                if action_norm == 'NO_OPERAR':
                    stats['still_pending'] += 1
                    continue
                
                # Verificar expiración
                created = self._parse_ts(signal.get('created_at'))
                if created:
                    hours_old = (datetime.utcnow() - created).total_seconds() / 3600
                    max_hours = SIGNAL_EXPIRATION.get(timeframe, 24)
                    
                    if hours_old > max_hours:
                        # Expiró sin tocar TP ni SL
                        self._mark_signal_expired(signal)
                        stats['expired'] += 1
                        stats['processed'] += 1
                        continue
                
                # Obtener velas desde el timestamp de la señal
                df = price_fetcher(symbol, timeframe)
                if df is None or len(df) == 0:
                    stats['still_pending'] += 1
                    continue
                
                # Evaluar si tocó TP o SL
                result = self._check_tp_sl_hit(signal, df)
                if result:
                    self.db.update_signal_result(signal['id'], result)
                    stats['processed'] += 1
                    if result['status'] == 'tp_hit':
                        stats['tp_hit'] += 1
                    elif result['status'] == 'sl_hit':
                        stats['sl_hit'] += 1
                    print(f"   {'✅' if result['status']=='tp_hit' else '❌'} "
                          f"{symbol} {timeframe} {action_norm}: {result['status']} "
                          f"({result['pnl_pct']:+.2f}%)")
                else:
                    stats['still_pending'] += 1
                    
            except Exception as e:
                logger.error(f"Error evaluando señal {signal.get('id')}: {e}")
        
        print(f"\n📊 [REVIEW] Batch completado:")
        print(f"   TP alcanzado: {stats['tp_hit']}")
        print(f"   SL alcanzado: {stats['sl_hit']}")
        print(f"   Expiradas: {stats['expired']}")
        print(f"   Aún pendientes: {stats['still_pending']}")
        print(f"{'='*60}\n")
        
        return stats
    
    def _check_tp_sl_hit(
        self,
        signal: Dict,
        df
    ) -> Optional[Dict]:
        """
        Verifica TP / SL y calcula MFE / MAE histórico.

        FASE 7D.1

        IMPORTANTE:
        - NO modifica la decisión original.
        - NO modifica Entry / SL / TP.
        - NO modifica leverage.
        - NO agrega llamadas de mercado.
        - Utiliza exactamente las mismas velas que ya se
          recorrían para detectar TP / SL.

        MFE = Maximum Favorable Excursion.
        MAE = Maximum Adverse Excursion.

        Las métricas se calculan tanto en porcentaje como
        en unidades R respecto al riesgo original:

            risk = abs(entry - SL)

        LONG:
            favorable = precio por encima del entry
            adverse   = precio por debajo del entry

        SHORT:
            favorable = precio por debajo del entry
            adverse   = precio por encima del entry
        """

        try:
            action = str(
                signal.get(
                    'action_normalized',
                    ''
                )
                or ''
            ).upper()

            entry = float(
                signal.get(
                    'entry_price',
                    0
                )
                or 0
            )

            sl = float(
                signal.get(
                    'stop_loss',
                    0
                )
                or 0
            )

            tp = float(
                signal.get(
                    'take_profit',
                    0
                )
                or 0
            )

            if (
                action not in (
                    'LONG',
                    'SHORT'
                )
                or entry <= 0
                or sl <= 0
                or tp <= 0
            ):
                return None

            # ==========================================================
            # RIESGO ORIGINAL
            # ==========================================================

            risk_abs = abs(
                entry - sl
            )

            if risk_abs <= 0:
                return None

            # ==========================================================
            # TIMESTAMP ORIGINAL
            # ==========================================================

            signal_ts = self._parse_ts(
                signal.get(
                    'candle_timestamp'
                )
                or signal.get(
                    'created_at'
                )
            )

            if not signal_ts:
                return None

            # ==========================================================
            # UTILIZAR SÓLO VELAS POSTERIORES
            # ==========================================================

            import pandas as pd

            if 'time' in df.columns:

                df_time = pd.to_datetime(
                    df['time'],
                    utc=True
                )

                signal_timestamp = pd.Timestamp(
                    signal_ts,
                    tz='UTC'
                )

                df_after = df[
                    df_time
                    > signal_timestamp
                ]

            else:

                df_after = df

            if len(df_after) == 0:
                return None

            # ==========================================================
            # ESTADO INICIAL DE MFE / MAE
            # ==========================================================

            mfe_price = entry
            mae_price = entry

            mfe_pct = 0.0
            mae_pct = 0.0

            mfe_r = 0.0
            mae_r = 0.0

            candles_to_mfe = 0
            candles_to_mae = 0

            # ==========================================================
            # ACTUALIZAR MÉTRICAS
            # ==========================================================

            def _recalculate_excursions():

                nonlocal mfe_pct
                nonlocal mae_pct
                nonlocal mfe_r
                nonlocal mae_r

                if action == 'LONG':

                    favorable_abs = max(
                        0.0,
                        mfe_price - entry
                    )

                    adverse_abs = max(
                        0.0,
                        entry - mae_price
                    )

                else:

                    favorable_abs = max(
                        0.0,
                        entry - mfe_price
                    )

                    adverse_abs = max(
                        0.0,
                        mae_price - entry
                    )

                mfe_pct = (
                    favorable_abs
                    / entry
                    * 100
                )

                mae_pct = (
                    adverse_abs
                    / entry
                    * 100
                )

                mfe_r = (
                    favorable_abs
                    / risk_abs
                )

                mae_r = (
                    adverse_abs
                    / risk_abs
                )

            def _excursion_payload():

                _recalculate_excursions()

                return {
                    'mfe_price': round(
                        float(mfe_price),
                        8
                    ),

                    'mae_price': round(
                        float(mae_price),
                        8
                    ),

                    'mfe_pct': round(
                        float(mfe_pct),
                        4
                    ),

                    'mae_pct': round(
                        float(mae_pct),
                        4
                    ),

                    'mfe_r': round(
                        float(mfe_r),
                        4
                    ),

                    'mae_r': round(
                        float(mae_r),
                        4
                    ),

                    'candles_to_mfe': int(
                        candles_to_mfe
                    ),

                    'candles_to_mae': int(
                        candles_to_mae
                    )
                }

            # ==========================================================
            # RECORRER LAS MISMAS VELAS QUE YA USABA REVIEWTRADER
            # ==========================================================

            for candle_number, (
                idx,
                row
            ) in enumerate(
                df_after.iterrows(),
                start=1
            ):

                high = float(
                    row['high']
                )

                low = float(
                    row['low']
                )

                candle_ts = row.get(
                    'time',
                    datetime.utcnow()
                )

                # ======================================================
                # LONG
                # ======================================================

                if action == 'LONG':

                    # --------------------------------------------------
                    # SL
                    # --------------------------------------------------
                    # Se mantiene la regla conservadora existente:
                    # si SL y TP ocurren en la misma vela, se asume SL.
                    #
                    # La MAE termina exactamente en SL porque la
                    # operación deja de existir allí.
                    # --------------------------------------------------

                    if low <= sl:

                        if sl < mae_price:
                            mae_price = sl
                            candles_to_mae = (
                                candle_number
                            )

                        metrics = (
                            _excursion_payload()
                        )

                        pnl_pct = (
                            (sl - entry)
                            / entry
                            * 100
                        )

                        return {
                            'status':
                                'sl_hit',

                            'exit_price':
                                sl,

                            'exit_timestamp':
                                str(candle_ts),

                            'pnl_pct':
                                pnl_pct,

                            'candles_to_result':
                                candle_number,

                            **metrics
                        }

                    # --------------------------------------------------
                    # TP
                    # --------------------------------------------------

                    if high >= tp:

                        # Antes de alcanzar TP pudo existir una
                        # excursión adversa dentro de esta vela,
                        # siempre que no haya tocado SL.
                        if low < mae_price:
                            mae_price = low
                            candles_to_mae = (
                                candle_number
                            )

                        # Al cerrar en TP no contamos precios
                        # posteriores al TP dentro de la misma vela.
                        if tp > mfe_price:
                            mfe_price = tp
                            candles_to_mfe = (
                                candle_number
                            )

                        metrics = (
                            _excursion_payload()
                        )

                        pnl_pct = (
                            (tp - entry)
                            / entry
                            * 100
                        )

                        return {
                            'status':
                                'tp_hit',

                            'exit_price':
                                tp,

                            'exit_timestamp':
                                str(candle_ts),

                            'pnl_pct':
                                pnl_pct,

                            'candles_to_result':
                                candle_number,

                            **metrics
                        }

                    # --------------------------------------------------
                    # OPERACIÓN SIGUE ABIERTA
                    # --------------------------------------------------

                    if high > mfe_price:

                        mfe_price = high

                        candles_to_mfe = (
                            candle_number
                        )

                    if low < mae_price:

                        mae_price = low

                        candles_to_mae = (
                            candle_number
                        )

                # ======================================================
                # SHORT
                # ======================================================

                elif action == 'SHORT':

                    # --------------------------------------------------
                    # SL
                    # --------------------------------------------------

                    if high >= sl:

                        if sl > mae_price:

                            mae_price = sl

                            candles_to_mae = (
                                candle_number
                            )

                        metrics = (
                            _excursion_payload()
                        )

                        pnl_pct = (
                            (entry - sl)
                            / entry
                            * 100
                        )

                        return {
                            'status':
                                'sl_hit',

                            'exit_price':
                                sl,

                            'exit_timestamp':
                                str(candle_ts),

                            'pnl_pct':
                                pnl_pct,

                            'candles_to_result':
                                candle_number,

                            **metrics
                        }

                    # --------------------------------------------------
                    # TP
                    # --------------------------------------------------

                    if low <= tp:

                        if high > mae_price:

                            mae_price = high

                            candles_to_mae = (
                                candle_number
                            )

                        # La operación cierra en TP.
                        if tp < mfe_price:

                            mfe_price = tp

                            candles_to_mfe = (
                                candle_number
                            )

                        metrics = (
                            _excursion_payload()
                        )

                        pnl_pct = (
                            (entry - tp)
                            / entry
                            * 100
                        )

                        return {
                            'status':
                                'tp_hit',

                            'exit_price':
                                tp,

                            'exit_timestamp':
                                str(candle_ts),

                            'pnl_pct':
                                pnl_pct,

                            'candles_to_result':
                                candle_number,

                            **metrics
                        }

                    # --------------------------------------------------
                    # OPERACIÓN SIGUE ABIERTA
                    # --------------------------------------------------

                    if low < mfe_price:

                        mfe_price = low

                        candles_to_mfe = (
                            candle_number
                        )

                    if high > mae_price:

                        mae_price = high

                        candles_to_mae = (
                            candle_number
                        )

            # ==========================================================
            # AÚN PENDIENTE
            # ==========================================================
            #
            # En 7D.1 no escribimos MFE/MAE de operaciones abiertas.
            # Esto evita agregar escrituras Supabase cada 15 minutos.
            #
            # 7D.2 se encargará de las posiciones realmente abiertas.
            # ==========================================================

            return None

        except Exception as e:

            logger.error(
                f"Error en _check_tp_sl_hit: {e}"
            )

            return None
    
    def _mark_signal_expired(self, signal: Dict):
        """Marca una señal como expirada"""
        result = {
            'status': 'expired',
            'exit_price': 0,
            'exit_timestamp': datetime.utcnow().isoformat(),
            'pnl_pct': 0,
            'candles_to_result': 0,
            'notes': 'Señal expiró sin tocar TP ni SL'
        }
        self.db.update_signal_result(signal['id'], result)
    
    def _parse_ts(self, ts_str) -> Optional[datetime]:
        """Parsea un timestamp ISO a datetime"""
        if not ts_str:
            return None
        try:
            if isinstance(ts_str, datetime):
                return ts_str
            # Manejo de timezone
            ts_str = str(ts_str)
            if 'Z' in ts_str:
                ts_str = ts_str.replace('Z', '+00:00')
            return datetime.fromisoformat(ts_str).replace(tzinfo=None)
        except Exception:
            return None
    
    # ========================================================================
    # 3. DETECTAR OPORTUNIDADES PERDIDAS
    # ========================================================================
    
    def detect_missed_opportunities(self, price_fetcher) -> int:
        """
        Recorre señales NO_OPERAR/ESPERAR/CAUTION recientes y verifica si el precio
        se movió a favor >MISSED_OPP_THRESHOLD_PCT en las siguientes velas.
        
        Si sí, se registra como oportunidad perdida y se aprende de esa combinación.
        
        Retorna: número de oportunidades perdidas detectadas.
        """
        if not self.db.enabled:
            return 0
        
        try:
            # Obtener señales NO_OPERAR recientes (últimos 7 días, aún pendientes de análisis)
            pending = self.db.get_pending_signals(hours_old_max=168)
            no_op_signals = [s for s in pending if s.get('action_normalized') == 'NO_OPERAR']
            
            print(f"\n🔍 [REVIEW] Buscando oportunidades perdidas en {len(no_op_signals)} señales NO_OPERAR")
            
            missed = 0
            
            for signal in no_op_signals:
                try:
                    symbol = signal.get('symbol')
                    timeframe = signal.get('timeframe')
                    price_at_signal = float(signal.get('current_price', 0))
                    
                    if price_at_signal == 0:
                        continue
                    
                    df = price_fetcher(symbol, timeframe)
                    if df is None or len(df) == 0:
                        continue
                    
                    # Filtrar velas POSTERIORES a la señal
                    signal_ts = self._parse_ts(signal.get('candle_timestamp'))
                    if not signal_ts:
                        continue
                    
                    import pandas as pd
                    df_after = df[pd.to_datetime(df['time'], utc=True) > pd.Timestamp(signal_ts, tz='UTC')]
                    
                    if len(df_after) < MISSED_OPP_MIN_CANDLES:
                        continue
                    
                    # Buscar el máximo movimiento a favor (positivo Y negativo)
                    max_high = df_after['high'].max()
                    min_low = df_after['low'].min()
                    
                    pct_up = ((max_high - price_at_signal) / price_at_signal) * 100
                    pct_down = ((price_at_signal - min_low) / price_at_signal) * 100
                    
                    if pct_up > MISSED_OPP_THRESHOLD_PCT:
                        # Se debió haber comprado (LONG)
                        idx_of_max = df_after['high'].idxmax()
                        candles_to = int(idx_of_max) if isinstance(idx_of_max, (int, float)) else 0
                        
                        strategies = self._get_signal_strategies(signal['id'])
                        
                        opp_data = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'action_should': 'LONG',
                            'confidence': signal.get('confidence', 0),
                            'strategies': strategies,
                            'indicators_snapshot': signal.get('indicators_snapshot', {}),
                            'price_at_signal': price_at_signal,
                            'max_favorable_price': max_high,
                            'max_favorable_pct': pct_up,
                            'candles_to_max': candles_to,
                            'candle_timestamp': signal.get('candle_timestamp')
                        }
                        self.db.insert_missed_opportunity(opp_data)
                        missed += 1
                        print(f"   ⚠️ Oportunidad LONG perdida: {symbol} {timeframe} → +{pct_up:.2f}%")
                    
                    if pct_down > MISSED_OPP_THRESHOLD_PCT:
                        # Se debió haber vendido (SHORT)
                        idx_of_min = df_after['low'].idxmin()
                        candles_to = int(idx_of_min) if isinstance(idx_of_min, (int, float)) else 0
                        
                        strategies = self._get_signal_strategies(signal['id'])
                        
                        opp_data = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'action_should': 'SHORT',
                            'confidence': signal.get('confidence', 0),
                            'strategies': strategies,
                            'indicators_snapshot': signal.get('indicators_snapshot', {}),
                            'price_at_signal': price_at_signal,
                            'max_favorable_price': min_low,
                            'max_favorable_pct': pct_down,
                            'candles_to_max': candles_to,
                            'candle_timestamp': signal.get('candle_timestamp')
                        }
                        self.db.insert_missed_opportunity(opp_data)
                        missed += 1
                        print(f"   ⚠️ Oportunidad SHORT perdida: {symbol} {timeframe} → -{pct_down:.2f}%")
                    
                    # Marcar la señal como procesada (aunque haya sido NO_OPERAR)
                    if pct_up > MISSED_OPP_THRESHOLD_PCT or pct_down > MISSED_OPP_THRESHOLD_PCT:
                        self.db.update_signal_result(signal['id'], {
                            'status': 'missed_opportunity',
                            'exit_price': max_high if pct_up > pct_down else min_low,
                            'exit_timestamp': datetime.utcnow().isoformat(),
                            'pnl_pct': max(pct_up, pct_down),
                            'candles_to_result': candles_to,
                            'notes': 'Oportunidad perdida detectada'
                        })
                    
                except Exception as e:
                    logger.error(f"Error detectando oportunidad en {signal.get('id')}: {e}")
            
            print(f"\n📊 [REVIEW] Oportunidades perdidas detectadas: {missed}")
            return missed
            
        except Exception as e:
            logger.error(f"Error en detect_missed_opportunities: {e}")
            return 0
    
    def _get_signal_strategies(self, signal_id: str) -> List[str]:
        """Obtiene las estrategias asociadas a una señal"""
        if not self.db.enabled:
            return []
        try:
            response = (self.db.client.table('signal_indicators')
                        .select('strategy_name')
                        .eq('signal_id', signal_id)
                        .execute())
            return [r['strategy_name'] for r in (response.data or [])]
        except Exception:
            return []
    # ========================================================================
    # MÉTRICAS CUANTITATIVAS — FASE 6
    # ========================================================================

    def _calculate_real_trade_metrics(
        self,
        signal: Dict
    ) -> Optional[Dict]:
        """
        Calcula las métricas reales de una señal resuelta.

        NO asume RR=2.

        Para una señal:
            LONG/SHORT + TP → R positivo igual al RR planificado.
            LONG/SHORT + SL → R = -1.

        Esto permite calcular expectancy real del setup.
        """

        try:

            status = str(
                signal.get(
                    'status',
                    ''
                )
            ).lower()

            if status not in (
                'tp_hit',
                'sl_hit'
            ):
                return None

            entry = float(
                signal.get(
                    'entry_price',
                    0
                )
                or 0
            )

            sl = float(
                signal.get(
                    'stop_loss',
                    0
                )
                or 0
            )

            tp = float(
                signal.get(
                    'take_profit',
                    0
                )
                or 0
            )

            if (
                entry <= 0
                or sl <= 0
                or tp <= 0
            ):
                return None

            risk_pct = (
                abs(
                    entry - sl
                )
                / entry
                * 100
            )

            reward_pct = (
                abs(
                    tp - entry
                )
                / entry
                * 100
            )

            if risk_pct <= 0:
                return None

            planned_rr = (
                reward_pct
                / risk_pct
            )

            if status == 'tp_hit':

                realized_r = planned_rr

                realized_pct = reward_pct

            else:

                realized_r = -1.0

                realized_pct = -risk_pct

            leverage = float(
                signal.get(
                    'leverage',
                    1
                )
                or 1
            )

            context = signal.get(
                'context',
                {}
            )

            if not isinstance(
                context,
                dict
            ):
                context = {}

            execution = context.get(
                'execution',
                {}
            )

            if not isinstance(
                execution,
                dict
            ):
                execution = {}

            def safe_float(
                value,
                default=0.0
            ):

                try:

                    return float(
                        value
                        if value is not None
                        else default
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    return default

            execution_safety = safe_float(
                execution.get(
                    'execution_safety',
                    0
                )
            )

            entry_score = safe_float(
                execution.get(
                    'entry_score',
                    0
                )
            )

            sl_quality = safe_float(
                execution.get(
                    'sl_reliability',
                    0
                )
            )

            tp_quality = safe_float(
                execution.get(
                    'tp_quality_score',
                    0
                )
            )

            # Normalizamos SL reliability 0-1 → 0-100.
            if (
                0
                < sl_quality
                <= 1
            ):
                sl_quality *= 100

            # ROI aproximado sobre margen para Futuros.
            margin_roi_pct = (
                realized_pct
                * leverage
                if (
                    signal.get(
                        'system_type'
                    ) == 'futures'
                    and leverage > 0
                )
                else realized_pct
            )

            return {
                'planned_rr': planned_rr,
                'realized_r': realized_r,
                'realized_pct': realized_pct,
                'risk_pct': risk_pct,
                'reward_pct': reward_pct,
                'margin_roi_pct': margin_roi_pct,
                'execution_safety': execution_safety,
                'entry_score': entry_score,
                'sl_quality': sl_quality,
                'tp_quality': tp_quality
            }

        except Exception as e:

            logger.debug(
                f"No se pudieron calcular métricas reales: {e}"
            )

            return None    

    # ========================================================================
    # FASE 7E.1 — CALIBRACIÓN ESTADÍSTICA DE EXECUTION SAFETY
    # ========================================================================

    def _build_execution_safety_calibration(
        self,
        signals_data: List[Dict]
    ) -> Dict:
        """
        FASE 7E.1

        Evalúa si Execution Safety realmente está relacionado con
        mejores resultados reales.

        IMPORTANTE:

        Execution Safety NO se interpreta como probabilidad.

        Ejemplo:

            Safety 85

        NO significa:

            85% de probabilidad de ganar.

        Lo que estudiamos es:

            Safety mayor
                ↓
            ¿mejor expectancy R?
            ¿mejor win rate?
            ¿mejor comportamiento histórico?

        Esta función es completamente PASIVA.

        NO modifica:
        - señales
        - leverage
        - filtros
        - minimum_execution_safety
        - TP
        - SL
        - decisiones
        """

        # ==============================================================
        # RESULTADO VACÍO SEGURO
        # ==============================================================

        empty_result = {
            'sample': 0,
            'wins': 0,
            'losses': 0,

            'win_rate': 0.0,
            'expectancy_r': 0.0,

            'bands': [],
            'by_timeframe': {},

            'monotonicity_score': 0.0,
            'monotonicity_pairs': 0,

            'suggested_min_safety_observational':
                None,

            'actionable':
                False
        }

        try:

            if not isinstance(
                signals_data,
                list
            ):

                return empty_result

            # ==========================================================
            # BUCKET VACÍO
            # ==========================================================

            def _new_bucket():

                return {
                    'sample': 0,
                    'wins': 0,
                    'losses': 0,

                    'sum_r': 0.0,
                    'sum_safety': 0.0
                }

            # ==========================================================
            # BANDAS ACTUALES DEL SISTEMA
            # ==========================================================
            #
            # Coinciden con la clasificación conceptual de
            # futures_system.py:
            #
            # <55      RECHAZAR
            # 55-64    BAJA
            # 65-74    VALIDA
            # 75-84    ALTA
            # >=85     PREMIUM
            #
            # NO estamos cambiando esos límites.
            # Sólo los usamos para medir resultados.
            # ==========================================================

            band_order = [
                'RECHAZAR',
                'BAJA',
                'VALIDA',
                'ALTA',
                'PREMIUM'
            ]

            band_lower_bound = {
                'RECHAZAR': 0,
                'BAJA': 55,
                'VALIDA': 65,
                'ALTA': 75,
                'PREMIUM': 85
            }

            band_stats = defaultdict(
                _new_bucket
            )

            timeframe_stats = defaultdict(
                _new_bucket
            )

            total_sample = 0
            total_wins = 0
            total_losses = 0
            total_r = 0.0

            # ==========================================================
            # CLASIFICAR SAFETY
            # ==========================================================

            def _safety_band(
                safety: float
            ) -> str:

                if safety >= 85:
                    return 'PREMIUM'

                if safety >= 75:
                    return 'ALTA'

                if safety >= 65:
                    return 'VALIDA'

                if safety >= 55:
                    return 'BAJA'

                return 'RECHAZAR'

            # ==========================================================
            # PROCESAR SEÑALES REALES
            # ==========================================================

            for signal in signals_data:

                try:

                    if not isinstance(
                        signal,
                        dict
                    ):
                        continue

                    # ==================================================
                    # SÓLO FUTUROS
                    # ==================================================

                    if str(
                        signal.get(
                            'system_type',
                            ''
                        )
                    ).lower() != 'futures':

                        continue

                    status = str(
                        signal.get(
                            'status',
                            ''
                        )
                    ).lower()

                    # Sólo operaciones realmente resueltas.
                    if status not in (
                        'tp_hit',
                        'sl_hit'
                    ):
                        continue

                    metrics = (
                        self
                        ._calculate_real_trade_metrics(
                            signal
                        )
                    )

                    if not metrics:
                        continue

                    safety = float(
                        metrics.get(
                            'execution_safety',
                            0
                        )
                        or 0
                    )

                    # ==================================================
                    # SAFETY 0 = SIN INFORMACIÓN
                    # ==================================================
                    #
                    # No mezclamos "0 porque realmente fue cero"
                    # con "0 porque antiguamente no se guardaba".
                    # ==================================================

                    if safety <= 0:
                        continue

                    safety = max(
                        0.0,
                        min(
                            100.0,
                            safety
                        )
                    )

                    realized_r = float(
                        metrics.get(
                            'realized_r',
                            0
                        )
                        or 0
                    )

                    is_win = (
                        status == 'tp_hit'
                    )

                    band = _safety_band(
                        safety
                    )

                    timeframe = str(
                        signal.get(
                            'timeframe',
                            'UNKNOWN'
                        )
                        or 'UNKNOWN'
                    )

                    # ==================================================
                    # GLOBAL
                    # ==================================================

                    total_sample += 1
                    total_r += realized_r

                    if is_win:
                        total_wins += 1
                    else:
                        total_losses += 1

                    # ==================================================
                    # POR BANDA
                    # ==================================================

                    bucket = (
                        band_stats[
                            band
                        ]
                    )

                    bucket[
                        'sample'
                    ] += 1

                    bucket[
                        'sum_r'
                    ] += realized_r

                    bucket[
                        'sum_safety'
                    ] += safety

                    if is_win:

                        bucket[
                            'wins'
                        ] += 1

                    else:

                        bucket[
                            'losses'
                        ] += 1

                    # ==================================================
                    # POR TIMEFRAME + BANDA
                    # ==================================================

                    tf_key = (
                        timeframe,
                        band
                    )

                    tf_bucket = (
                        timeframe_stats[
                            tf_key
                        ]
                    )

                    tf_bucket[
                        'sample'
                    ] += 1

                    tf_bucket[
                        'sum_r'
                    ] += realized_r

                    tf_bucket[
                        'sum_safety'
                    ] += safety

                    if is_win:

                        tf_bucket[
                            'wins'
                        ] += 1

                    else:

                        tf_bucket[
                            'losses'
                        ] += 1

                except Exception as e:

                    logger.debug(
                        f"7E calibration skip: {e}"
                    )

                    continue

            # ==========================================================
            # SIN DATOS
            # ==========================================================

            if total_sample <= 0:

                return empty_result

            # ==========================================================
            # FINALIZAR UN BUCKET
            # ==========================================================

            def _finalize_bucket(
                label: str,
                data: Dict
            ) -> Dict:

                sample = int(
                    data.get(
                        'sample',
                        0
                    )
                    or 0
                )

                wins = int(
                    data.get(
                        'wins',
                        0
                    )
                    or 0
                )

                losses = int(
                    data.get(
                        'losses',
                        0
                    )
                    or 0
                )

                if sample <= 0:

                    return {
                        'band': label,
                        'sample': 0,
                        'wins': 0,
                        'losses': 0,
                        'win_rate': 0.0,
                        'expectancy_r': 0.0,
                        'avg_safety': 0.0,
                        'sample_quality':
                            'SIN_MUESTRA'
                    }

                win_rate = (
                    wins
                    / sample
                    * 100.0
                )

                expectancy_r = (
                    float(
                        data.get(
                            'sum_r',
                            0
                        )
                        or 0
                    )
                    / sample
                )

                avg_safety = (
                    float(
                        data.get(
                            'sum_safety',
                            0
                        )
                        or 0
                    )
                    / sample
                )

                # ==============================================
                # CALIDAD DE MUESTRA
                # ==============================================

                if sample >= 25:

                    sample_quality = (
                        'ROBUSTA'
                    )

                elif sample >= 10:

                    sample_quality = (
                        'UTIL'
                    )

                elif sample >= 5:

                    sample_quality = (
                        'PRELIMINAR'
                    )

                else:

                    sample_quality = (
                        'INSUFICIENTE'
                    )

                return {
                    'band':
                        label,

                    'sample':
                        sample,

                    'wins':
                        wins,

                    'losses':
                        losses,

                    'win_rate':
                        round(
                            win_rate,
                            2
                        ),

                    'expectancy_r':
                        round(
                            expectancy_r,
                            4
                        ),

                    'avg_safety':
                        round(
                            avg_safety,
                            2
                        ),

                    'sample_quality':
                        sample_quality
                }

            # ==========================================================
            # BANDAS GLOBALES
            # ==========================================================

            bands = []

            for band in band_order:

                bands.append(
                    _finalize_bucket(
                        band,
                        band_stats[
                            band
                        ]
                    )
                )

            # ==========================================================
            # POR TIMEFRAME
            # ==========================================================

            by_timeframe = {}

            futures_timeframes = (
                '5m',
                '15m',
                '30m',
                '1h',
                '2h',
                '4h'
            )

            for timeframe in (
                futures_timeframes
            ):

                tf_rows = []

                for band in band_order:

                    data = (
                        timeframe_stats[
                            (
                                timeframe,
                                band
                            )
                        ]
                    )

                    finalized = (
                        _finalize_bucket(
                            band,
                            data
                        )
                    )

                    # Evitar inflar el resultado con
                    # combinaciones completamente vacías.
                    if (
                        finalized[
                            'sample'
                        ] > 0
                    ):

                        tf_rows.append(
                            finalized
                        )

                if tf_rows:

                    by_timeframe[
                        timeframe
                    ] = tf_rows

            # ==========================================================
            # MONOTONICIDAD
            # ==========================================================
            #
            # Si Execution Safety está bien ordenado,
            # idealmente una banda superior debería tener
            # expectancy igual o mejor que la anterior.
            #
            # Sólo comparamos bandas con >= 5 muestras.
            #
            # Permitimos una tolerancia de -0.05R para evitar
            # interpretar pequeñas diferencias como fallas.
            # ==========================================================

            comparable = [
                row
                for row in bands
                if row[
                    'sample'
                ] >= 5
            ]

            ordered_pairs = 0
            good_pairs = 0

            for i in range(
                1,
                len(
                    comparable
                )
            ):

                previous = (
                    comparable[
                        i - 1
                    ]
                )

                current = (
                    comparable[
                        i
                    ]
                )

                ordered_pairs += 1

                if (
                    current[
                        'expectancy_r'
                    ]
                    >=
                    previous[
                        'expectancy_r'
                    ]
                    - 0.05
                ):

                    good_pairs += 1

            monotonicity_score = (
                good_pairs
                / ordered_pairs
                * 100.0
                if ordered_pairs > 0
                else 0.0
            )

            # ==========================================================
            # UMBRAL OBSERVACIONAL
            # ==========================================================
            #
            # NO se aplica al sistema.
            #
            # Sólo informa cuál es la primera banda con:
            #
            # - al menos 10 muestras
            # - expectancy > mínimo accionable
            #
            # ==========================================================

            suggested_min_safety = None

            for row in bands:

                if (
                    row[
                        'sample'
                    ] >= MIN_SAMPLE_ACTIONABLE
                    and
                    row[
                        'expectancy_r'
                    ]
                    >= MIN_EXPECTANCY_ACTIONABLE
                ):

                    suggested_min_safety = (
                        band_lower_bound[
                            row[
                                'band'
                            ]
                        ]
                    )

                    break

            # ==========================================================
            # GLOBAL
            # ==========================================================

            global_win_rate = (
                total_wins
                / total_sample
                * 100.0
            )

            global_expectancy = (
                total_r
                / total_sample
            )

            actionable = (
                total_sample
                >= MIN_SAMPLE_STRONG
                and
                len(
                    comparable
                ) >= 2
            )

            return {
                'sample':
                    total_sample,

                'wins':
                    total_wins,

                'losses':
                    total_losses,

                'win_rate':
                    round(
                        global_win_rate,
                        2
                    ),

                'expectancy_r':
                    round(
                        global_expectancy,
                        4
                    ),

                'bands':
                    bands,

                'by_timeframe':
                    by_timeframe,

                'monotonicity_score':
                    round(
                        monotonicity_score,
                        2
                    ),

                'monotonicity_pairs':
                    ordered_pairs,

                'suggested_min_safety_observational':
                    suggested_min_safety,

                # Sólo significa que existe suficiente
                # información para estudiar la calibración.
                #
                # NO autoriza cambios automáticos.
                'actionable':
                    actionable
            }

        except Exception as e:

            logger.error(
                f"Error calibrando Execution Safety: {e}"
            )

            return empty_result    

    # ========================================================================
    # FASE 7E.2 — EXECUTION SAFETY SHADOW POLICY
    # ========================================================================

    def _build_execution_safety_shadow_policy(
        self,
        calibration: Dict
    ) -> Dict:
        """
        FASE 7E.2

        Convierte la evidencia estadística de 7E.1 en una
        política RECOMENDADA de Execution Safety.

        IMPORTANTE:
        esta política está en SHADOW MODE.

        NO modifica:
        - FUTURES_RISK_CONFIG
        - minimum_execution_safety
        - high_safety_threshold
        - leverage
        - señales
        - Entry
        - SL
        - TP

        Sólo responde:

            1. ¿Qué umbral mínimo parece razonable?
            2. ¿Qué bandas históricamente aportan o destruyen expectancy?
            3. ¿Hay suficiente muestra?
            4. ¿La relación Safety → Expectancy es coherente?
            5. ¿Existe evidencia específica por timeframe?
        """

        empty_result = {
            'mode':
                'SHADOW_ONLY',

            'sample':
                0,

            'eligible_for_operational_review':
                False,

            'candidate_min_safety':
                None,

            'recommended_min_safety_shadow':
                None,

            'reason':
                'SIN_MUESTRA',

            'band_factors':
                {},

            'by_timeframe':
                {},

            'guardrails': {
                'minimum_shadow_threshold':
                    55,

                'maximum_shadow_threshold':
                    85,

                'min_sample_band':
                    5,

                'min_sample_actionable':
                    MIN_SAMPLE_ACTIONABLE,

                'min_sample_operational_review':
                    MIN_SAMPLE_STRONG,

                'minimum_monotonicity_pct':
                    60.0,

                'factor_floor':
                    0.90,

                'factor_ceiling':
                    1.10
            }
        }

        try:

            if not isinstance(
                calibration,
                dict
            ):
                return empty_result

            sample = int(
                calibration.get(
                    'sample',
                    0
                )
                or 0
            )

            if sample <= 0:
                return empty_result

            bands = (
                calibration.get(
                    'bands',
                    []
                )
                or []
            )

            by_timeframe_source = (
                calibration.get(
                    'by_timeframe',
                    {}
                )
                or {}
            )

            monotonicity = float(
                calibration.get(
                    'monotonicity_score',
                    0
                )
                or 0
            )

            monotonicity_pairs = int(
                calibration.get(
                    'monotonicity_pairs',
                    0
                )
                or 0
            )

            calibration_actionable = bool(
                calibration.get(
                    'actionable',
                    False
                )
            )

            raw_suggested_threshold = (
                calibration.get(
                    'suggested_min_safety_observational'
                )
            )

            # ==========================================================
            # MAPA DE BANDAS
            # ==========================================================

            band_order = [
                'RECHAZAR',
                'BAJA',
                'VALIDA',
                'ALTA',
                'PREMIUM'
            ]

            band_lower_bound = {
                'RECHAZAR': 0,
                'BAJA': 55,
                'VALIDA': 65,
                'ALTA': 75,
                'PREMIUM': 85
            }

            # ==========================================================
            # FACTOR EMPÍRICO
            # ==========================================================
            #
            # NO es probabilidad.
            #
            # Es un factor conservador que podrá utilizar 7E.3
            # si la evidencia futura demuestra que es robusta.
            #
            # Expectancy claramente negativa:
            #       penalización.
            #
            # Expectancy claramente positiva:
            #       bonificación pequeña.
            #
            # Máximo permitido:
            #       ±10%.
            #
            # Además aplicamos SHRINKAGE según muestra:
            #
            # pocas muestras → factor vuelve hacia 1.0
            # muchas muestras → puede acercarse al factor empírico.
            # ==========================================================

            def _raw_factor_from_expectancy(
                expectancy_r: float
            ) -> float:

                if expectancy_r <= -0.25:
                    return 0.90

                if expectancy_r < 0:
                    return 0.95

                if expectancy_r < 0.20:
                    return 1.00

                if expectancy_r < 0.50:
                    return 1.05

                return 1.10

            def _shrunk_factor(
                expectancy_r: float,
                bucket_sample: int
            ) -> float:

                if bucket_sample < 5:
                    return 1.0

                raw_factor = (
                    _raw_factor_from_expectancy(
                        expectancy_r
                    )
                )

                reliability = min(
                    1.0,
                    bucket_sample
                    / float(
                        MIN_SAMPLE_STRONG
                    )
                )

                factor = (
                    1.0
                    +
                    (
                        raw_factor
                        - 1.0
                    )
                    * reliability
                )

                factor = max(
                    0.90,
                    min(
                        1.10,
                        factor
                    )
                )

                return round(
                    factor,
                    4
                )

            # ==========================================================
            # FACTORES POR BANDA
            # ==========================================================

            band_factors = {}

            rows_by_band = {}

            for row in bands:

                if not isinstance(
                    row,
                    dict
                ):
                    continue

                band = str(
                    row.get(
                        'band',
                        ''
                    )
                    or ''
                ).upper()

                if band not in band_order:
                    continue

                rows_by_band[
                    band
                ] = row

                bucket_sample = int(
                    row.get(
                        'sample',
                        0
                    )
                    or 0
                )

                expectancy_r = float(
                    row.get(
                        'expectancy_r',
                        0
                    )
                    or 0
                )

                factor = (
                    _shrunk_factor(
                        expectancy_r,
                        bucket_sample
                    )
                )

                if bucket_sample >= MIN_SAMPLE_STRONG:

                    evidence = (
                        'ROBUSTA'
                    )

                elif bucket_sample >= MIN_SAMPLE_ACTIONABLE:

                    evidence = (
                        'UTIL'
                    )

                elif bucket_sample >= 5:

                    evidence = (
                        'PRELIMINAR'
                    )

                else:

                    evidence = (
                        'INSUFICIENTE'
                    )

                band_factors[
                    band
                ] = {
                    'sample':
                        bucket_sample,

                    'expectancy_r':
                        round(
                            expectancy_r,
                            4
                        ),

                    'win_rate':
                        round(
                            float(
                                row.get(
                                    'win_rate',
                                    0
                                )
                                or 0
                            ),
                            2
                        ),

                    'shadow_factor':
                        factor,

                    'evidence':
                        evidence
                }

            # ==========================================================
            # UMBRAL GLOBAL CANDIDATO
            # ==========================================================

            candidate_threshold = None

            if raw_suggested_threshold is not None:

                try:
                    candidate_threshold = int(
                        raw_suggested_threshold
                    )

                except (
                    TypeError,
                    ValueError
                ):
                    candidate_threshold = None

            # ==========================================================
            # GUARDRAIL
            # ==========================================================
            #
            # Aunque la banda RECHAZAR tuviera resultados positivos
            # en una muestra histórica sesgada, Shadow Policy nunca
            # recomendará bajar de 55.
            #
            # Tampoco recomendará un mínimo superior a 85 en esta fase.
            # ==========================================================

            if candidate_threshold is not None:

                candidate_threshold = max(
                    55,
                    min(
                        85,
                        candidate_threshold
                    )
                )

            # ==========================================================
            # ¿LA EVIDENCIA GLOBAL ES SUFICIENTE?
            # ==========================================================

            global_ready = (
                calibration_actionable
                and
                sample >= MIN_SAMPLE_STRONG
                and
                monotonicity_pairs >= 1
                and
                monotonicity >= 60.0
                and
                candidate_threshold is not None
            )

            if candidate_threshold is None:

                global_reason = (
                    'NINGUNA_BANDA_CON_EXPECTANCY_Y_MUESTRA_SUFICIENTE'
                )

            elif sample < MIN_SAMPLE_STRONG:

                global_reason = (
                    'MUESTRA_GLOBAL_INSUFICIENTE'
                )

            elif monotonicity_pairs < 1:

                global_reason = (
                    'NO_HAY_BANDAS_COMPARABLES'
                )

            elif monotonicity < 60.0:

                global_reason = (
                    'SAFETY_NO_ORDENA_EXPECTANCY_DE_FORMA_CONSISTENTE'
                )

            elif not calibration_actionable:

                global_reason = (
                    'CALIBRACION_AUN_NO_ACCIONABLE'
                )

            else:

                global_reason = (
                    'EVIDENCIA_SUFICIENTE_PARA_REVISION'
                )

            recommended_shadow = (
                candidate_threshold
                if global_ready
                else None
            )

            # ==========================================================
            # CALIBRACIÓN POR TIMEFRAME
            # ==========================================================

            timeframe_policy = {}

            for (
                timeframe,
                tf_rows
            ) in by_timeframe_source.items():

                if not isinstance(
                    tf_rows,
                    list
                ):
                    continue

                tf_total_sample = sum(
                    int(
                        row.get(
                            'sample',
                            0
                        )
                        or 0
                    )
                    for row in tf_rows
                    if isinstance(
                        row,
                        dict
                    )
                )

                tf_rows_map = {
                    str(
                        row.get(
                            'band',
                            ''
                        )
                        or ''
                    ).upper():
                        row
                    for row in tf_rows
                    if isinstance(
                        row,
                        dict
                    )
                }

                # ------------------------------------------------------
                # Candidato por timeframe
                # ------------------------------------------------------

                tf_candidate = None

                for band in band_order:

                    row = tf_rows_map.get(
                        band
                    )

                    if not row:
                        continue

                    row_sample = int(
                        row.get(
                            'sample',
                            0
                        )
                        or 0
                    )

                    row_expectancy = float(
                        row.get(
                            'expectancy_r',
                            0
                        )
                        or 0
                    )

                    if (
                        row_sample
                        >= MIN_SAMPLE_ACTIONABLE
                        and
                        row_expectancy
                        >= MIN_EXPECTANCY_ACTIONABLE
                    ):

                        tf_candidate = (
                            band_lower_bound[
                                band
                            ]
                        )

                        break

                if tf_candidate is not None:

                    tf_candidate = max(
                        55,
                        min(
                            85,
                            int(
                                tf_candidate
                            )
                        )
                    )

                # ------------------------------------------------------
                # MONOTONICIDAD POR TIMEFRAME
                # ------------------------------------------------------

                tf_comparable = []

                for band in band_order:

                    row = tf_rows_map.get(
                        band
                    )

                    if not row:
                        continue

                    if int(
                        row.get(
                            'sample',
                            0
                        )
                        or 0
                    ) < 5:

                        continue

                    tf_comparable.append(
                        row
                    )

                tf_pairs = 0
                tf_good_pairs = 0

                for idx in range(
                    1,
                    len(
                        tf_comparable
                    )
                ):

                    previous = (
                        tf_comparable[
                            idx - 1
                        ]
                    )

                    current = (
                        tf_comparable[
                            idx
                        ]
                    )

                    tf_pairs += 1

                    previous_exp = float(
                        previous.get(
                            'expectancy_r',
                            0
                        )
                        or 0
                    )

                    current_exp = float(
                        current.get(
                            'expectancy_r',
                            0
                        )
                        or 0
                    )

                    if (
                        current_exp
                        >= previous_exp - 0.05
                    ):
                        tf_good_pairs += 1

                tf_monotonicity = (
                    tf_good_pairs
                    / tf_pairs
                    * 100.0
                    if tf_pairs > 0
                    else 0.0
                )

                tf_ready = (
                    tf_total_sample
                    >= MIN_SAMPLE_STRONG
                    and
                    tf_candidate is not None
                    and
                    tf_pairs >= 1
                    and
                    tf_monotonicity >= 60.0
                )

                timeframe_policy[
                    timeframe
                ] = {
                    'sample':
                        tf_total_sample,

                    'candidate_min_safety':
                        tf_candidate,

                    'recommended_min_safety_shadow':
                        (
                            tf_candidate
                            if tf_ready
                            else None
                        ),

                    'monotonicity_score':
                        round(
                            tf_monotonicity,
                            2
                        ),

                    'monotonicity_pairs':
                        tf_pairs,

                    'eligible_for_operational_review':
                        bool(
                            tf_ready
                        )
                }

            return {
                'mode':
                    'SHADOW_ONLY',

                'sample':
                    sample,

                'eligible_for_operational_review':
                    bool(
                        global_ready
                    ),

                'candidate_min_safety':
                    candidate_threshold,

                'recommended_min_safety_shadow':
                    recommended_shadow,

                'reason':
                    global_reason,

                'monotonicity_score':
                    round(
                        monotonicity,
                        2
                    ),

                'monotonicity_pairs':
                    monotonicity_pairs,

                'band_factors':
                    band_factors,

                'by_timeframe':
                    timeframe_policy,

                'guardrails':
                    empty_result[
                        'guardrails'
                    ]
            }

        except Exception as e:

            logger.error(
                f"Error creando Shadow Policy "
                f"de Execution Safety: {e}"
            )

            return empty_result

    # ========================================================================
    # FASE 7E.3 — POLÍTICA OPERATIVA PROTEGIDA
    # ========================================================================

    def get_execution_safety_operational_policy(
        self,
        timeframe: str,
        safety_score: float,
        default_min_safety: float = 65.0
    ) -> Dict:
        """
        FASE 7E.3

        Convierte la Shadow Policy de 7E.2 en una protección
        operacional extremadamente conservadora.

        REGLA CENTRAL:

            EL APRENDIZAJE SÓLO PUEDE REDUCIR RIESGO.

        Puede:

            - subir minimum_execution_safety;
            - reducir el score utilizado para calcular leverage.

        Nunca puede:

            - bajar minimum_execution_safety;
            - aumentar Execution Safety;
            - aumentar leverage;
            - forzar una señal;
            - saltarse SL / TP / RR / costes.

        Si cualquier dato es insuficiente o inválido:

            FALLBACK = configuración estática original.
        """

        try:

            raw_safety = float(
                safety_score
                or 0
            )

        except (
            TypeError,
            ValueError
        ):

            raw_safety = 0.0

        raw_safety = max(
            0.0,
            min(
                100.0,
                raw_safety
            )
        )

        try:

            default_min = float(
                default_min_safety
                or 65.0
            )

        except (
            TypeError,
            ValueError
        ):

            default_min = 65.0

        default_min = max(
            0.0,
            min(
                100.0,
                default_min
            )
        )

        # ==============================================================
        # FALLBACK ABSOLUTAMENTE SEGURO
        # ==============================================================

        fallback = {
            'active':
                False,

            'mode':
                'STATIC_FALLBACK',

            'minimum_safety':
                round(
                    default_min,
                    2
                ),

            'raw_safety':
                round(
                    raw_safety,
                    2
                ),

            'leverage_safety_score':
                round(
                    raw_safety,
                    2
                ),

            'leverage_factor':
                1.0,

            'band':
                None,

            'sample':
                0,

            'monotonicity_score':
                0.0,

            'reason':
                'CALIBRACION_NO_DISPONIBLE',

            'updated_at':
                self._execution_safety_policy_updated_at
        }

        try:

            shadow = getattr(
                self,
                '_execution_safety_shadow_policy',
                None
            )

            if not isinstance(
                shadow,
                dict
            ):

                return fallback

            # ==========================================================
            # GUARDRAILS MÁS ESTRICTOS QUE 7E.2
            # ==========================================================
            #
            # 7E.2:
            #   permite revisión con muestra mínima robusta.
            #
            # 7E.3:
            #   exige el DOBLE antes de tocar comportamiento real.
            # ==============================================================

            sample = int(
                shadow.get(
                    'sample',
                    0
                )
                or 0
            )

            monotonicity = float(
                shadow.get(
                    'monotonicity_score',
                    0
                )
                or 0
            )

            eligible = bool(
                shadow.get(
                    'eligible_for_operational_review',
                    False
                )
            )

            shadow_min = (
                shadow.get(
                    'recommended_min_safety_shadow'
                )
            )

            required_global_sample = max(
                50,
                MIN_SAMPLE_STRONG * 2
            )

            # ==========================================================
            # TODAVÍA NO HAY SUFICIENTE EVIDENCIA
            # ==============================================================

            if not eligible:

                fallback[
                    'reason'
                ] = (
                    'SHADOW_POLICY_NO_ELEGIBLE'
                )

                fallback[
                    'sample'
                ] = sample

                fallback[
                    'monotonicity_score'
                ] = round(
                    monotonicity,
                    2
                )

                return fallback

            if sample < required_global_sample:

                fallback[
                    'reason'
                ] = (
                    'MUESTRA_OPERATIVA_INSUFICIENTE'
                )

                fallback[
                    'sample'
                ] = sample

                fallback[
                    'monotonicity_score'
                ] = round(
                    monotonicity,
                    2
                )

                return fallback

            # Para actuar realmente exigimos más
            # monotonicidad que en Shadow Mode.
            if monotonicity < 75.0:

                fallback[
                    'reason'
                ] = (
                    'MONOTONICIDAD_OPERATIVA_INSUFICIENTE'
                )

                fallback[
                    'sample'
                ] = sample

                fallback[
                    'monotonicity_score'
                ] = round(
                    monotonicity,
                    2
                )

                return fallback

            if shadow_min is None:

                fallback[
                    'reason'
                ] = (
                    'SIN_UMBRAL_SHADOW_VALIDO'
                )

                return fallback

            try:

                shadow_min = float(
                    shadow_min
                )

            except (
                TypeError,
                ValueError
            ):

                return fallback

            # ==========================================================
            # PROTECTION ONLY
            # ==========================================================
            #
            # Nunca bajar de:
            #
            #     FUTURES_RISK_CONFIG.minimum_execution_safety
            #
            # Si Shadow recomienda 55:
            #
            #     REAL sigue siendo 65.
            #
            # Si Shadow recomienda 75:
            #
            #     REAL puede subir a 75.
            # ==============================================================

            operational_min = max(
                default_min,
                shadow_min
            )

            operational_min = min(
                85.0,
                operational_min
            )

            # ==========================================================
            # TIMEFRAME
            # ==========================================================
            #
            # Un TF puede endurecer el filtro.
            #
            # Nunca puede relajarlo.
            # ==============================================================

            timeframe_policy = (
                shadow.get(
                    'by_timeframe',
                    {}
                )
                or {}
            )

            tf_policy = (
                timeframe_policy.get(
                    timeframe,
                    {}
                )
                or {}
            )

            if isinstance(
                tf_policy,
                dict
            ):

                tf_ready = bool(
                    tf_policy.get(
                        'eligible_for_operational_review',
                        False
                    )
                )

                tf_sample = int(
                    tf_policy.get(
                        'sample',
                        0
                    )
                    or 0
                )

                tf_monotonicity = float(
                    tf_policy.get(
                        'monotonicity_score',
                        0
                    )
                    or 0
                )

                tf_min = (
                    tf_policy.get(
                        'recommended_min_safety_shadow'
                    )
                )

                if (
                    tf_ready
                    and
                    tf_sample >= MIN_SAMPLE_STRONG
                    and
                    tf_monotonicity >= 75.0
                    and
                    tf_min is not None
                ):

                    try:

                        tf_min = float(
                            tf_min
                        )

                        # Sólo endurecer.
                        operational_min = max(
                            operational_min,
                            tf_min
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        pass

            operational_min = min(
                85.0,
                operational_min
            )

            # ==========================================================
            # DETERMINAR BANDA DEL SAFETY ACTUAL
            # ==============================================================

            if raw_safety >= 85:

                band = 'PREMIUM'

            elif raw_safety >= 75:

                band = 'ALTA'

            elif raw_safety >= 65:

                band = 'VALIDA'

            elif raw_safety >= 55:

                band = 'BAJA'

            else:

                band = 'RECHAZAR'

            band_factors = (
                shadow.get(
                    'band_factors',
                    {}
                )
                or {}
            )

            band_data = (
                band_factors.get(
                    band,
                    {}
                )
                or {}
            )

            # ==========================================================
            # FACTOR DE LEVERAGE
            # ==========================================================
            #
            # También PROTECTION ONLY.
            #
            # Aunque Shadow diga:
            #
            #     factor 1.08
            #
            # Operational utiliza:
            #
            #     1.00
            #
            # Nunca aumenta leverage.
            #
            # Sólo una banda ROBUSTA puede reducir Safety para leverage.
            # ==============================================================

            leverage_factor = 1.0

            evidence = str(
                band_data.get(
                    'evidence',
                    ''
                )
                or ''
            ).upper()

            try:

                shadow_factor = float(
                    band_data.get(
                        'shadow_factor',
                        1.0
                    )
                    or 1.0
                )

            except (
                TypeError,
                ValueError
            ):

                shadow_factor = 1.0

            if (
                evidence == 'ROBUSTA'
                and
                shadow_factor < 1.0
            ):

                # Penalización máxima operativa:
                # -5%.
                leverage_factor = max(
                    0.95,
                    shadow_factor
                )

            # Nunca bonificar.
            leverage_factor = min(
                1.0,
                leverage_factor
            )

            leverage_safety_score = (
                raw_safety
                * leverage_factor
            )

            # Protección extra:
            # jamás devolver un Safety de leverage
            # superior al score original.
            leverage_safety_score = min(
                raw_safety,
                leverage_safety_score
            )

            return {
                'active':
                    True,

                'mode':
                    'PROTECTION_ONLY',

                'minimum_safety':
                    round(
                        operational_min,
                        2
                    ),

                'raw_safety':
                    round(
                        raw_safety,
                        2
                    ),

                'leverage_safety_score':
                    round(
                        leverage_safety_score,
                        2
                    ),

                'leverage_factor':
                    round(
                        leverage_factor,
                        4
                    ),

                'band':
                    band,

                'band_evidence':
                    evidence,

                'sample':
                    sample,

                'monotonicity_score':
                    round(
                        monotonicity,
                        2
                    ),

                'reason':
                    'PROTECCION_ESTADISTICA_ACTIVA',

                'updated_at':
                    self._execution_safety_policy_updated_at
            }

        except Exception as e:

            logger.warning(
                "Execution Safety operational policy "
                f"fallback: {e}"
            )

            return fallback
   
    # ========================================================================
    # 4. RECALCULAR ESTADÍSTICAS
    # ========================================================================
    
    def recalculate_stats(self) -> Dict:
        """
        Recalcula estadísticas reales.

        FASE 6:

        - Win Rate real
        - Avg Win %
        - Avg Loss %
        - Avg R
        - Avg RR
        - Expectancy real
        - Degradación
        - Calidad de ENTRY
        - Calidad de SL
        - Calidad de TP
        - Temporalidad
        - Símbolo
        - Acción
        - Estrategias
        - Combinaciones SMC

        NO asume RR fijo.
        """

        if not self.db.enabled:
            return {
                'specific': 0,
                'general': 0
            }

        print(
            f"\n{'=' * 60}"
        )

        print(
            "📊 [REVIEW] Recalculando estadísticas CUANTITATIVAS..."
        )

        print(
            f"{'=' * 60}"
        )

        signals_data = (
            self.db.get_signals_for_stats(
                days_back=90
            )
        )

        if not signals_data:

            print(
                "   ⚠️ No hay señales suficientes"
            )

            return {
                'specific': 0,
                'general': 0
            }

        print(
            f"   📈 Procesando "
            f"{len(signals_data)} señales..."
        )

        # ==============================================================
        # FASE 7E.1 — CALIBRACIÓN PASIVA DE EXECUTION SAFETY
        # ==============================================================
        #
        # IMPORTANTE:
        # reutilizamos signals_data.
        #
        # NO hacemos:
        # - nueva consulta Supabase
        # - llamada KuCoin
        # - DataFrame
        # - thread
        #
        # ==============================================================

        execution_safety_calibration = (
            self
            ._build_execution_safety_calibration(
                signals_data
            )
        )

        calibration_sample = int(
            execution_safety_calibration.get(
                'sample',
                0
            )
            or 0
        )

        if calibration_sample > 0:

            print(
                "   🛡️ Execution Safety calibration: "
                f"{calibration_sample} operaciones "
                f"| Exp "
                f"{execution_safety_calibration.get('expectancy_r', 0):+.3f}R "
                f"| monotonicidad "
                f"{execution_safety_calibration.get('monotonicity_score', 0):.1f}%"
            )

            suggested = (
                execution_safety_calibration
                .get(
                    'suggested_min_safety_observational'
                )
            )

            if suggested is not None:

                print(
                    "   👁️ Umbral Safety observado "
                    f"(NO aplicado): {suggested}"
                )

        else:
            print(
                "   ℹ️ Execution Safety calibration: "
                "sin muestra Futures suficiente todavía."
            )

        # ==============================================================
        # FASE 7E.2 — SHADOW POLICY
        # ==============================================================
        #
        # Convierte la evidencia 7E.1 en recomendaciones,
        # pero NO modifica futures_system.py.
        # ==============================================================
        execution_safety_shadow_policy = (
            self
            ._build_execution_safety_shadow_policy(
                execution_safety_calibration
            )
        )

        # ==============================================================
        # FASE 7E.3
        # ==============================================================
        #
        # Guardar solamente en memoria.
        #
        # NO Supabase.
        # NO archivo.
        # NO nueva consulta.
        #
        # Si Render reinicia:
        #
        #     vuelve temporalmente al Safety estático de 65
        #
        # hasta que ReviewTrader recalcule nuevamente estadísticas.
        # ==============================================================

        self._execution_safety_shadow_policy = (
            execution_safety_shadow_policy
        )

        self._execution_safety_policy_updated_at = (
            datetime.utcnow()
            .isoformat()
        )

        shadow_candidate = (
            execution_safety_shadow_policy
            .get(
                'candidate_min_safety'
            )
        )

        shadow_recommended = (
            execution_safety_shadow_policy
            .get(
                'recommended_min_safety_shadow'
            )
        )

        shadow_ready = bool(
            execution_safety_shadow_policy
            .get(
                'eligible_for_operational_review',
                False
            )
        )

        if shadow_candidate is not None:

            print(
                "   👁️ 7E.2 Shadow Safety: "
                f"candidato={shadow_candidate} "
                f"| listo={shadow_ready} "
                f"| razón="
                f"{execution_safety_shadow_policy.get('reason')}"
            )

        else:

            print(
                "   👁️ 7E.2 Shadow Safety: "
                "sin umbral candidato todavía."
            )

        if shadow_recommended is not None:

            print(
                "   🧪 Umbral recomendado SHADOW: "
                f"{shadow_recommended} "
                "(NO APLICADO)"
            )

        # ==============================================================
        # ESTADÍSTICAS ESPECÍFICAS
        # ==============================================================
        specific_stats = defaultdict(
            lambda: {
                'wins': 0,
                'losses': 0,
                'expired': 0,

                'sum_win_pct': 0.0,
                'sum_loss_pct': 0.0,

                'sum_win_r': 0.0,
                'sum_loss_r': 0.0,

                'sum_rr': 0.0,

                'sum_execution_safety': 0.0,
                'count_execution_safety': 0,

                'sum_entry_score': 0.0,
                'count_entry_score': 0,

                'sum_sl_quality': 0.0,
                'count_sl_quality': 0,

                'sum_tp_quality': 0.0,
                'count_tp_quality': 0,

                'recent_20': [],

                'combination_results': defaultdict(
                    lambda: {
                        'wins': 0,
                        'losses': 0,
                        'sum_r': 0.0
                    }
                )
            }
        )

        # ==============================================================
        # ESTADÍSTICAS GENERALES POR ESTRATEGIA
        # ==============================================================
        general_stats = defaultdict(
            lambda: {
                'wins': 0,
                'losses': 0,

                'sum_win_pct': 0.0,
                'sum_loss_pct': 0.0,

                'sum_win_r': 0.0,
                'sum_loss_r': 0.0,

                'sum_rr': 0.0,

                'by_symbol': defaultdict(
                    lambda: {
                        'wins': 0,
                        'losses': 0,
                        'sum_r': 0.0
                    }
                ),

                'by_timeframe': defaultdict(
                    lambda: {
                        'wins': 0,
                        'losses': 0,
                        'sum_r': 0.0
                    }
                ),

                'recent_20': []
            }
        )

        # ==============================================================
        # PROCESAR SEÑALES
        # ==============================================================
        for signal in signals_data:

            try:

                status = str(
                    signal.get(
                        'status',
                        ''
                    )
                ).lower()

                # ------------------------------------------------------
                # Expired no es WIN ni LOSS.
                # Missed Opportunity tampoco.
                # ------------------------------------------------------
                if status == 'expired':

                    # Lo contabilizamos solamente para
                    # información de cobertura.
                    signal_indicators = (
                        signal.get(
                            'signal_indicators',
                            []
                        )
                        or []
                    )

                    strategies = [
                        si.get(
                            'strategy_name'
                        )

                        for si
                        in signal_indicators

                        if isinstance(si, dict)
                        and si.get(
                            'strategy_name'
                        )
                    ]

                    for strategy in set(
                        strategies
                    ):

                        symbol = signal.get(
                            'symbol'
                        )

                        timeframe = signal.get(
                            'timeframe'
                        )

                        action = signal.get(
                            'action_normalized'
                        )

                        key = (
                            symbol,
                            timeframe,
                            action,
                            strategy
                        )

                        specific_stats[key][
                            'expired'
                        ] += 1

                    continue

                # ------------------------------------------------------
                # Sólo resultados reales.
                # ------------------------------------------------------
                metrics = (
                    self._calculate_real_trade_metrics(
                        signal
                    )
                )

                if not metrics:
                    continue

                if status not in (
                    'tp_hit',
                    'sl_hit'
                ):
                    continue

                symbol = signal.get(
                    'symbol'
                )

                timeframe = signal.get(
                    'timeframe'
                )

                action = signal.get(
                    'action_normalized'
                )

                is_win = (
                    status == 'tp_hit'
                )

                signal_indicators = (
                    signal.get(
                        'signal_indicators',
                        []
                    )
                    or []
                )

                strategies = sorted(
                    {
                        si.get(
                            'strategy_name'
                        )
                        for si
                        in signal_indicators

                        if isinstance(si, dict)
                        and si.get(
                            'strategy_name'
                        )
                    }
                )

                if not strategies:
                    continue

                # ======================================================
                # PERFIL SMC DE LA SEÑAL
                # ======================================================

                smc_strategies = [
                    s.upper()
                    for s in strategies

                    if any(
                        key in s.upper()
                        for key
                        in SMC_STRATEGY_KEYWORDS
                    )
                ]

                # Evitar combinaciones gigantes.
                smc_strategies = sorted(
                    set(
                        smc_strategies
                    )
                )[
                    :MAX_COMBINATION_STRATEGIES
                ]

                context = signal.get(
                    'context',
                    {}
                )

                if not isinstance(
                    context,
                    dict
                ):
                    context = {}

                execution = context.get(
                    'execution',
                    {}
                )

                if not isinstance(
                    execution,
                    dict
                ):
                    execution = {}

                safety = float(
                    execution.get(
                        'execution_safety',
                        0
                    )
                    or 0
                )

                entry_score = float(
                    execution.get(
                        'entry_score',
                        0
                    )
                    or 0
                )

                sl_quality = float(
                    execution.get(
                        'sl_reliability',
                        0
                    )
                    or 0
                )

                tp_quality = float(
                    execution.get(
                        'tp_quality_score',
                        0
                    )
                    or 0
                )

                if (
                    0
                    < sl_quality
                    <= 1
                ):
                    sl_quality *= 100

                # ------------------------------------------------------
                # BUCKETS
                # ------------------------------------------------------
                safety_bucket = (
                    f"SAFETY_"
                    f"{int(safety // 10) * 10}"
                    if safety > 0
                    else "SAFETY_UNKNOWN"
                )

                entry_bucket = (
                    f"ENTRY_"
                    f"{int(entry_score // 10) * 10}"
                    if entry_score > 0
                    else "ENTRY_UNKNOWN"
                )

                sl_bucket = (
                    f"SL_"
                    f"{int(sl_quality // 10) * 10}"
                    if sl_quality > 0
                    else "SL_UNKNOWN"
                )

                tp_bucket = (
                    f"TP_"
                    f"{int(tp_quality // 10) * 10}"
                    if tp_quality > 0
                    else "TP_UNKNOWN"
                )

                # ======================================================
                # PROCESAR CADA ESTRATEGIA
                # ======================================================

                for strategy in strategies:

                    key = (
                        symbol,
                        timeframe,
                        action,
                        strategy
                    )

                    data = specific_stats[key]

                    if is_win:

                        data['wins'] += 1

                        data['sum_win_pct'] += (
                            metrics[
                                'realized_pct'
                            ]
                        )

                        data['sum_win_r'] += (
                            metrics[
                                'realized_r'
                            ]
                        )

                    else:

                        data['losses'] += 1

                        data['sum_loss_pct'] += (
                            abs(
                                metrics[
                                    'realized_pct'
                                ]
                            )
                        )

                        data['sum_loss_r'] += (
                            abs(
                                metrics[
                                    'realized_r'
                                ]
                            )
                        )

                    data['sum_rr'] += (
                        metrics[
                            'planned_rr'
                        ]
                    )

                    if safety > 0:

                        data[
                            'sum_execution_safety'
                        ] += safety

                        data[
                            'count_execution_safety'
                        ] += 1

                    if entry_score > 0:

                        data[
                            'sum_entry_score'
                        ] += entry_score

                        data[
                            'count_entry_score'
                        ] += 1

                    if sl_quality > 0:

                        data[
                            'sum_sl_quality'
                        ] += sl_quality

                        data[
                            'count_sl_quality'
                        ] += 1

                    if tp_quality > 0:

                        data[
                            'sum_tp_quality'
                        ] += tp_quality

                        data[
                            'count_tp_quality'
                        ] += 1

                    data[
                        'recent_20'
                    ].append(
                        (
                            is_win,
                            signal.get(
                                'created_at'
                            )
                        )
                    )

                    # ==================================================
                    # COMBINACIÓN SMC
                    # ==================================================
                    if smc_strategies:

                        signature = (
                            '|'.join(
                                smc_strategies
                            )
                            + f"|{safety_bucket}"
                            + f"|{entry_bucket}"
                            + f"|{sl_bucket}"
                            + f"|{tp_bucket}"
                        )

                        combo = data[
                            'combination_results'
                        ][signature]

                        if is_win:
                            combo['wins'] += 1

                        else:
                            combo['losses'] += 1

                        combo['sum_r'] += (
                            metrics[
                                'realized_r'
                            ]
                        )

                    # ==================================================
                    # GENERAL
                    # ==================================================
                    g = general_stats[
                        strategy
                    ]

                    if is_win:

                        g['wins'] += 1

                        g[
                            'sum_win_pct'
                        ] += metrics[
                            'realized_pct'
                        ]

                        g[
                            'sum_win_r'
                        ] += metrics[
                            'realized_r'
                        ]

                        g[
                            'by_symbol'
                        ][symbol]['wins'] += 1

                        g[
                            'by_symbol'
                        ][symbol]['sum_r'] += (
                            metrics[
                                'realized_r'
                            ]
                        )

                        g[
                            'by_timeframe'
                        ][timeframe]['wins'] += 1

                        g[
                            'by_timeframe'
                        ][timeframe]['sum_r'] += (
                            metrics[
                                'realized_r'
                            ]
                        )

                    else:

                        g['losses'] += 1

                        g[
                            'sum_loss_pct'
                        ] += abs(
                            metrics[
                                'realized_pct'
                            ]
                        )

                        g[
                            'sum_loss_r'
                        ] += abs(
                            metrics[
                                'realized_r'
                            ]
                        )

                        g[
                            'by_symbol'
                        ][symbol]['losses'] += 1

                        g[
                            'by_symbol'
                        ][symbol]['sum_r'] += (
                            metrics[
                                'realized_r'
                            ]
                        )

                        g[
                            'by_timeframe'
                        ][timeframe]['losses'] += 1

                        g[
                            'by_timeframe'
                        ][timeframe]['sum_r'] += (
                            metrics[
                                'realized_r'
                            ]
                        )

                    g[
                        'sum_rr'
                    ] += metrics[
                        'planned_rr'
                    ]

                    g[
                        'recent_20'
                    ].append(
                        (
                            is_win,
                            signal.get(
                                'created_at'
                            )
                        )
                    )

            except Exception as e:

                logger.error(
                    f"Error procesando señal: {e}"
                )

        # ==============================================================
        # TRANSFORMAR ESPECÍFICAS
        # ==============================================================
        specific_rows = []

        for (
            symbol,
            tf,
            action,
            strategy
        ), data in specific_stats.items():

            wins = data[
                'wins'
            ]

            losses = data[
                'losses'
            ]

            resolved = (
                wins
                + losses
            )

            if resolved <= 0:
                continue

            win_rate = (
                wins
                / resolved
                * 100
            )

            avg_win_pct = (
                data[
                    'sum_win_pct'
                ]
                / wins
                if wins > 0
                else 0
            )

            avg_loss_pct = (
                data[
                    'sum_loss_pct'
                ]
                / losses
                if losses > 0
                else 0
            )

            avg_win_r = (
                data[
                    'sum_win_r'
                ]
                / wins
                if wins > 0
                else 0
            )

            avg_loss_r = (
                data[
                    'sum_loss_r'
                ]
                / losses
                if losses > 0
                else 0
            )

            avg_rr = (
                data[
                    'sum_rr'
                ]
                / resolved
            )

            expectancy = (
                (
                    wins
                    / resolved
                )
                * avg_win_r
                -
                (
                    losses
                    / resolved
                )
                * avg_loss_r
            )

            # ==========================================================
            # ÚLTIMAS 20 RESUELTAS
            # ==========================================================
            recent = sorted(
                data[
                    'recent_20'
                ],
                key=lambda x:
                    x[1] or '',
                reverse=True
            )[:20]

            recent_total = len(
                recent
            )

            recent_wins = sum(
                1
                for r in recent
                if r[0]
            )

            last_20_wr = (
                recent_wins
                / recent_total
                * 100
                if recent_total
                else win_rate
            )

            is_degrading = (
                win_rate
                - last_20_wr
                > DEGRADATION_THRESHOLD
            )

            # ==========================================================
            # CALIDAD DE MUESTRA
            # ==========================================================
            sample_strength = min(
                1.0,
                resolved / 30.0
            )

            adjusted_wr = (
                (
                    win_rate * resolved
                )
                +
                (
                    50.0
                    * BAYESIAN_PRIOR_WEIGHT
                )
            ) / (
                resolved
                + BAYESIAN_PRIOR_WEIGHT
            )

            execution_safety = (
                data[
                    'sum_execution_safety'
                ]
                / data[
                    'count_execution_safety'
                ]
                if data[
                    'count_execution_safety'
                ] > 0
                else 0
            )

            entry_score = (
                data[
                    'sum_entry_score'
                ]
                / data[
                    'count_entry_score'
                ]
                if data[
                    'count_entry_score'
                ] > 0
                else 0
            )

            sl_quality = (
                data[
                    'sum_sl_quality'
                ]
                / data[
                    'count_sl_quality'
                ]
                if data[
                    'count_sl_quality'
                ] > 0
                else 0
            )

            tp_quality = (
                data[
                    'sum_tp_quality'
                ]
                / data[
                    'count_tp_quality'
                ]
                if data[
                    'count_tp_quality'
                ] > 0
                else 0
            )

            # ==========================================================
            # COMBINACIONES
            # ==========================================================
            best_combinations = []

            for (
                signature,
                combo
            ) in data[
                'combination_results'
            ].items():

                combo_n = (
                    combo['wins']
                    + combo['losses']
                )

                if combo_n < 3:
                    continue

                combo_wr = (
                    combo['wins']
                    / combo_n
                    * 100
                )

                combo_exp = (
                    combo[
                        'sum_r'
                    ]
                    / combo_n
                )

                best_combinations.append({
                    'setup': signature,
                    'sample': combo_n,
                    'win_rate': round(
                        combo_wr,
                        2
                    ),
                    'expectancy_r': round(
                        combo_exp,
                        3
                    )
                })

            best_combinations.sort(
                key=lambda x: (
                    -x[
                        'expectancy_r'
                    ],
                    -x[
                        'sample'
                    ]
                )
            )

            best_combinations = (
                best_combinations[:5]
            )

            specific_rows.append({
                'symbol': symbol,
                'timeframe': tf,
                'action': action,
                'strategy': strategy,

                'total_signals':
                    resolved
                    + data[
                        'expired'
                    ],

                'wins': wins,
                'losses': losses,
                'expired':
                    data[
                        'expired'
                    ],

                'win_rate':
                    round(
                        win_rate,
                        2
                    ),

                'avg_win_pct':
                    round(
                        avg_win_pct,
                        4
                    ),

                'avg_loss_pct':
                    round(
                        avg_loss_pct,
                        4
                    ),

                'avg_rr':
                    round(
                        avg_rr,
                        3
                    ),

                'expectancy':
                    round(
                        expectancy,
                        4
                    ),

                'last_20_win_rate':
                    round(
                        last_20_wr,
                        2
                    ),

                'is_degrading':
                    is_degrading,

                # Campos JSONB existentes no se pueden usar aquí,
                # por eso estas métricas se incorporarán a
                # review_recommendations.
                '_adjusted_wr':
                    round(
                        adjusted_wr,
                        2
                    ),

                '_sample_strength':
                    round(
                        sample_strength,
                        3
                    ),

                '_execution_safety':
                    round(
                        execution_safety,
                        2
                    ),

                '_entry_score':
                    round(
                        entry_score,
                        2
                    ),

                '_sl_quality':
                    round(
                        sl_quality,
                        2
                    ),

                '_tp_quality':
                    round(
                        tp_quality,
                        2
                    ),

                '_best_combinations':
                    best_combinations,

                '_avg_win_r':
                    round(
                        avg_win_r,
                        3
                    ),

                '_avg_loss_r':
                    round(
                        avg_loss_r,
                        3
                    ),

                'last_updated':
                    datetime.utcnow().isoformat()
            })

        # ==============================================================
        # GENERALES
        # ==============================================================
        general_rows = []

        for strategy, data in general_stats.items():

            wins = data[
                'wins'
            ]

            losses = data[
                'losses'
            ]

            total = (
                wins
                + losses
            )

            if total <= 0:
                continue

            win_rate = (
                wins
                / total
                * 100
            )

            avg_win_r = (
                data[
                    'sum_win_r'
                ]
                / wins
                if wins
                else 0
            )

            avg_loss_r = (
                data[
                    'sum_loss_r'
                ]
                / losses
                if losses
                else 0
            )

            avg_rr = (
                data[
                    'sum_rr'
                ]
                / total
            )

            expectancy = (
                (
                    wins
                    / total
                )
                * avg_win_r
                -
                (
                    losses
                    / total
                )
                * avg_loss_r
            )

            # ----------------------------------------------------------
            # SÍMBOLOS
            # ----------------------------------------------------------
            symbol_scores = {}

            for sym, stats in data[
                'by_symbol'
            ].items():

                n = (
                    stats['wins']
                    + stats['losses']
                )

                if n < 3:
                    continue

                wr = (
                    stats['wins']
                    / n
                    * 100
                )

                exp = (
                    stats['sum_r']
                    / n
                )

                symbol_scores[
                    sym
                ] = {
                    'win_rate': wr,
                    'expectancy': exp,
                    'sample': n
                }

            best_symbols = sorted(
                symbol_scores.items(),
                key=lambda x: (
                    -x[1]['expectancy'],
                    -x[1]['sample']
                )
            )[:3]

            worst_symbols = sorted(
                symbol_scores.items(),
                key=lambda x: (
                    x[1]['expectancy'],
                    -x[1]['sample']
                )
            )[:3]

            # ----------------------------------------------------------
            # TEMPORALIDADES
            # ----------------------------------------------------------
            tf_scores = {}

            for tf, stats in data[
                'by_timeframe'
            ].items():

                n = (
                    stats['wins']
                    + stats['losses']
                )

                if n < 3:
                    continue

                wr = (
                    stats['wins']
                    / n
                    * 100
                )

                exp = (
                    stats['sum_r']
                    / n
                )

                # Score ajustado por tamaño de muestra.
                strength = min(
                    1.0,
                    n / 20.0
                )

                score = (
                    exp
                    * (
                        0.50
                        + 0.50
                        * strength
                    )
                )

                tf_scores[
                    tf
                ] = {
                    'win_rate': wr,
                    'expectancy': exp,
                    'sample': n,
                    'score': score
                }

            best_tfs = sorted(
                tf_scores.items(),
                key=lambda x: (
                    -x[1]['score'],
                    -x[1]['sample']
                )
            )[:3]

            worst_tfs = sorted(
                tf_scores.items(),
                key=lambda x: (
                    x[1]['score'],
                    -x[1]['sample']
                )
            )[:3]

            # ----------------------------------------------------------
            # DEGRADACIÓN
            # ----------------------------------------------------------
            recent = sorted(
                data[
                    'recent_20'
                ],
                key=lambda x:
                    x[1] or '',
                reverse=True
            )[:20]

            recent_total = len(
                recent
            )

            recent_wins = sum(
                1
                for r in recent
                if r[0]
            )

            last_20_wr = (
                recent_wins
                / recent_total
                * 100
                if recent_total
                else win_rate
            )

            is_degrading = (
                win_rate
                - last_20_wr
                > DEGRADATION_THRESHOLD
            )

            general_rows.append({
                'strategy': strategy,
                'total_signals': total,
                'wins': wins,
                'losses': losses,
                'win_rate': round(
                    win_rate,
                    2
                ),

                'avg_rr': round(
                    avg_rr,
                    3
                ),

                'expectancy': round(
                    expectancy,
                    4
                ),

                'best_symbols': [
                    {
                        'symbol': item[0],
                        'win_rate': round(
                            item[1]['win_rate'],
                            2
                        ),
                        'expectancy': round(
                            item[1]['expectancy'],
                            4
                        ),
                        'sample': item[1]['sample']
                    }

                    for item
                    in best_symbols
                ],

                'worst_symbols': [
                    {
                        'symbol': item[0],
                        'win_rate': round(
                            item[1]['win_rate'],
                            2
                        ),
                        'expectancy': round(
                            item[1]['expectancy'],
                            4
                        ),
                        'sample': item[1]['sample']
                    }

                    for item
                    in worst_symbols
                ],

                'best_timeframes': [
                    {
                        'timeframe': item[0],
                        'win_rate': round(
                            item[1]['win_rate'],
                            2
                        ),
                        'expectancy': round(
                            item[1]['expectancy'],
                            4
                        ),
                        'sample': item[1]['sample']
                    }

                    for item
                    in best_tfs
                ],

                'worst_timeframes': [
                    {
                        'timeframe': item[0],
                        'win_rate': round(
                            item[1]['win_rate'],
                            2
                        ),
                        'expectancy': round(
                            item[1]['expectancy'],
                            4
                        ),
                        'sample': item[1]['sample']
                    }

                    for item
                    in worst_tfs
                ],

                'is_degrading':
                    is_degrading,

                'last_updated':
                    datetime.utcnow().isoformat()
            })

        # ==============================================================
        # GUARDAR
        # ==============================================================
        if specific_rows:

            # Quitamos campos internos antes de enviarlos a Supabase.
            db_specific_rows = []

            for row in specific_rows:

                clean = {
                    k: v
                    for k, v in row.items()
                    if not k.startswith('_')
                }

                db_specific_rows.append(
                    clean
                )

            self.db.upsert_strategy_stats(
                db_specific_rows,
                general=False
            )

        if general_rows:

            self.db.upsert_strategy_stats(
                general_rows,
                general=True
            )

        print(
            f"   ✅ Stats específicas: "
            f"{len(specific_rows)}"
        )

        print(
            f"   ✅ Stats generales: "
            f"{len(general_rows)}"
        )

        print(
            f"{'=' * 60}\n"
        )

        # ==============================================================
        # RECOMENDACIONES
        # ==============================================================
        self._generate_recommendations(
            specific_rows,
            general_rows
        )

        return {
            'specific':
                len(
                    specific_rows
                ),

            'general':
                len(
                    general_rows
                ),

            # ==========================================================
            # FASE 7E.1
            # ==========================================================

            'execution_safety_calibration':
                execution_safety_calibration,

            # ==========================================================
            # FASE 7E.2
            # ==========================================================
            #
            # Shadow mode.
            #
            # No existe todavía ningún consumidor operativo
            # de este objeto.
            # ==========================================================

            'execution_safety_shadow_policy':
                execution_safety_shadow_policy
        }
    
    def _generate_recommendations(
        self,
        specific_rows: List[Dict],
        general_rows: List[Dict]
    ):
        """
        Genera recomendaciones utilizando:

        - Expectancy REAL
        - Win Rate
        - Tamaño de muestra
        - Degradación
        - Calidad ENTRY
        - Calidad SL
        - Calidad TP
        - Combinaciones SMC

        No utiliza RR fijo.
        """

        if not self.db.enabled:
            return

        try:

            grouped = defaultdict(
                list
            )

            for row in specific_rows:

                grouped[
                    (
                        row['symbol'],
                        row['timeframe'],
                        row['action']
                    )
                ].append(
                    row
                )

            recs_generated = 0

            for (
                symbol,
                timeframe,
                action
            ), rows in grouped.items():

                if action == 'NO_OPERAR':
                    continue

                # ======================================================
                # ELEGIBILIDAD
                # ======================================================
                actionable = []

                for row in rows:

                    sample = (
                        row['wins']
                        + row['losses']
                    )

                    expectancy = float(
                        row.get(
                            'expectancy',
                            0
                        )
                        or 0
                    )

                    wr = float(
                        row.get(
                            'win_rate',
                            0
                        )
                        or 0
                    )

                    degrading = bool(
                        row.get(
                            'is_degrading',
                            False
                        )
                    )

                    if sample < MIN_SAMPLE_ACTIONABLE:
                        continue

                    # Una estrategia no entra como ganadora sólo
                    # por tener WR alto.
                    #
                    # Debe tener expectancy positiva.
                    if expectancy <= (
                        MIN_EXPECTANCY_ACTIONABLE
                    ):
                        continue

                    if degrading:
                        continue

                    row['_quality_score'] = (
                        expectancy * 60
                        +
                        min(
                            25,
                            max(
                                0,
                                wr - 50
                            )
                        )
                        +
                        min(
                            15,
                            sample
                            / 2
                        )
                    )

                    actionable.append(
                        row
                    )

                # ======================================================
                # ORDENAR POR CALIDAD REAL
                # ======================================================
                actionable.sort(
                    key=lambda r: (
                        -r.get(
                            '_quality_score',
                            0
                        ),
                        -r['expectancy'],
                        -r['win_rate'],
                        -(
                            r['wins']
                            + r['losses']
                        )
                    )
                )

                winners = actionable[:5]

                # ======================================================
                # PERDEDORAS
                # ======================================================
                losers = []

                for row in rows:

                    sample = (
                        row['wins']
                        + row['losses']
                    )

                    expectancy = float(
                        row.get(
                            'expectancy',
                            0
                        )
                        or 0
                    )

                    degrading = bool(
                        row.get(
                            'is_degrading',
                            False
                        )
                    )

                    if sample < MIN_SAMPLE_ACTIONABLE:
                        continue

                    if (
                        expectancy
                        <= -0.10
                        or degrading
                    ):
                        losers.append(
                            row
                        )

                losers.sort(
                    key=lambda r: (
                        r['expectancy'],
                        r['win_rate']
                    )
                )

                losers = losers[:5]

                # ======================================================
                # RESULTADO DE LA RECOMENDACIÓN
                # ======================================================
                if winners:

                    best = winners[0]

                    best_wr = float(
                        best['win_rate']
                    )

                    multiplier = (
                        self._calculate_multiplier(
                            best_wr
                        )
                    )

                    avg_wr = (
                        sum(
                            r['win_rate']
                            for r in winners
                        )
                        /
                        len(winners)
                    )

                    avg_exp = (
                        sum(
                            r['expectancy']
                            for r in winners
                        )
                        /
                        len(winners)
                    )

                    avg_rr = (
                        sum(
                            r['avg_rr']
                            for r in winners
                        )
                        /
                        len(winners)
                    )

                    sample_total = sum(
                        r['wins']
                        + r['losses']
                        for r in winners
                    )

                    # Combinaciones aprendidas.
                    combinations = []

                    for row in winners:

                        for combo in row.get(
                            '_best_combinations',
                            []
                        ):

                            if (
                                combo[
                                    'expectancy_r'
                                ]
                                <= 0
                            ):
                                continue

                            combinations.append({
                                'strategy':
                                    row[
                                        'strategy'
                                    ],

                                'setup':
                                    combo[
                                        'setup'
                                    ],

                                'sample':
                                    combo[
                                        'sample'
                                    ],

                                'win_rate':
                                    combo[
                                        'win_rate'
                                    ],

                                'expectancy_r':
                                    combo[
                                        'expectancy_r'
                                    ],

                                'entry_score':
                                    row.get(
                                        '_entry_score',
                                        0
                                    ),

                                'sl_quality':
                                    row.get(
                                        '_sl_quality',
                                        0
                                    ),

                                'tp_quality':
                                    row.get(
                                        '_tp_quality',
                                        0
                                    )
                            })

                    combinations.sort(
                        key=lambda x: (
                            -x[
                                'expectancy_r'
                            ],
                            -x[
                                'sample'
                            ]
                        )
                    )

                    combinations = (
                        combinations[:10]
                    )

                else:

                    multiplier = (
                        MULTIPLIER_NEUTRAL
                    )

                    avg_wr = 0
                    avg_exp = 0
                    avg_rr = 0
                    sample_total = 0
                    combinations = []

                # ======================================================
                # TEMPORALIDAD — ESTE TF
                # ======================================================
                #
                # Una temporalidad no será considerada "buena"
                # solamente porque tenga 100% con 3 muestras.
                #
                # Para su recomendación usamos:
                #   expectancy +
                #   muestra +
                #   estabilidad
                # ======================================================

                timeframe_status = (
                    'INSUFICIENTE'
                )

                if sample_total >= MIN_SAMPLE_ACTIONABLE:

                    if avg_exp >= (
                        MIN_EXPECTANCY_STRONG
                    ):

                        timeframe_status = (
                            'FAVORABLE'
                        )

                    elif avg_exp > 0:

                        timeframe_status = (
                            'VIGILAR'
                        )

                    else:

                        timeframe_status = (
                            'EVITAR'
                        )

                # ======================================================
                # CONSTRUIR NOTES
                # ======================================================
                notes = (
                    self._build_notes(
                        winners,
                        losers
                    )
                )

                notes += (
                    f" | TF={timeframe_status}"
                )

                notes += (
                    f" | AvgRR={avg_rr:.2f}"
                )

                notes += (
                    f" | Exp={avg_exp:+.3f}R"
                )

                rec_data = {
                    'symbol':
                        symbol,

                    'timeframe':
                        timeframe,

                    'action':
                        action,

                    'winning_strategies': [
                        {
                            'strategy':
                                r['strategy'],

                            'win_rate':
                                r['win_rate'],

                            'sample':
                                r[
                                    'wins'
                                ]
                                + r[
                                    'losses'
                                ],

                            'rr':
                                r['avg_rr'],

                            'expectancy':
                                r['expectancy'],

                            'entry_score':
                                r.get(
                                    '_entry_score',
                                    0
                                ),

                            'sl_quality':
                                r.get(
                                    '_sl_quality',
                                    0
                                ),

                            'tp_quality':
                                r.get(
                                    '_tp_quality',
                                    0
                                )
                        }

                        for r
                        in winners
                    ],

                    'losing_strategies': [
                        {
                            'strategy':
                                r['strategy'],

                            'win_rate':
                                r['win_rate'],

                            'sample':
                                r[
                                    'wins'
                                ]
                                + r[
                                    'losses'
                                ],

                            'expectancy':
                                r['expectancy'],

                            'degrading':
                                r[
                                    'is_degrading'
                                ]
                        }

                        for r
                        in losers
                    ],

                    'best_combinations':
                        combinations,

                    'win_rate':
                        round(
                            avg_wr,
                            2
                        ),

                    'expectancy':
                        round(
                            avg_exp,
                            4
                        ),

                    'sample_size':
                        sample_total,

                    'multiplier':
                        multiplier,

                    # Se conserva por compatibilidad.
                    # NO debe utilizarse como leverage real.
                    'leverage':
                        1,

                    'notes':
                        notes
                }

                self.db.upsert_recommendation(
                    rec_data
                )

                recs_generated += 1

            print(
                f"   ✅ Recomendaciones cuantitativas: "
                f"{recs_generated}"
            )

        except Exception as e:

            logger.error(
                f"Error generando recomendaciones cuantitativas: {e}"
            )
    
    def _calculate_multiplier(self, win_rate: float) -> float:
        """
        Convierte un win rate en un multiplicador de confianza (0.5x - 1.5x).
        - 50% win rate = 1.0x (neutral)
        - 75% win rate = 1.25x
        - 90% win rate = 1.5x (máximo)
        - 25% win rate = 0.5x (mínimo)
        """
        if win_rate >= 90:
            return MULTIPLIER_MAX
        elif win_rate <= 25:
            return MULTIPLIER_MIN
        else:
            # Lineal entre 25% y 90%
            multiplier = 0.5 + (win_rate - 25) / (90 - 25) * (1.5 - 0.5)
            return round(multiplier, 2)
    
    def _suggest_leverage(self, timeframe: str, win_rate: float) -> int:
        """Sugiere apalancamiento basado en TF y win rate histórico"""
        # Rangos base por TF (según requerimientos del usuario)
        if timeframe in ('5m', '15m', '30m'):
            base_range = (10, 50)
        elif timeframe in ('1h', '2h', '4h'):
            base_range = (5, 20)
        else:  # 12h, 1D, 1W
            base_range = (1, 5)
        
        # Factor por win rate: >70% permite el máximo del rango; <50% el mínimo
        if win_rate >= 70:
            return base_range[1]
        elif win_rate >= 60:
            return int((base_range[0] + base_range[1]) / 2)
        elif win_rate >= 50:
            return base_range[0] + 2
        else:
            return base_range[0]
    
    def _build_notes(self, winners: List[Dict], losers: List[Dict]) -> str:
        """Construye notas descriptivas de la recomendación"""
        notes = []
        if winners:
            notes.append(f"Top ganadora: {winners[0]['strategy']} ({winners[0]['win_rate']}% en {winners[0]['total_signals']} señales)")
        if losers:
            notes.append(f"Evitar: {losers[0]['strategy']} ({losers[0]['win_rate']}%)")
        return " | ".join(notes)
    
    # ========================================================================
    # 5. CONSULTAS PARA EL FRONTEND
    # ========================================================================
    
    def get_confidence_adjustment(self, symbol: str, timeframe: str, action: str,
                                     min_sample_size: int = 10) -> float:
        """
        Devuelve el multiplicador de confianza que el ReviewTrader recomienda
        para un trader que vote (action) en (symbol, timeframe).
        
        Ejemplo: si históricamente COMPRA_SPOT en BTC-USDT 4h tiene win_rate 70%
        con 50 muestras, el multiplicador será 1.3 (amplificar convicción).
        Si tiene win_rate 25% con 30 muestras, será 0.7 (atenuar).
        
        Retorna:
          1.0 si no hay datos suficientes (min_sample_size no alcanzado) o
              Supabase no está conectado (comportamiento neutral).
          0.5 a 1.5 según el historial (con clip).
        
        Uso desde el Moderador: aplicar este multiplicador ANTES del peso del
        régimen, para que el ReviewTrader ejerza su rol de juez del comité.
        """
        try:
            if not self.db.enabled:
                return 1.0
            if action not in ('LONG', 'SHORT', 'COMPRA_SPOT', 'VENTA_SPOT'):
                return 1.0  # solo ajustamos direccionales
            
            rec = self.db.get_recommendations(symbol, timeframe, action)
            if not rec:
                return 1.0  # sin recomendación cacheada = neutral
            
            sample = int(rec.get('sample_size', 0) or 0)
            if sample < min_sample_size:
                return 1.0  # muestra insuficiente para ejercer autoridad
            
            mult = float(rec.get('recommended_confidence_multiplier', 1.0) or 1.0)
            # Clip defensivo
            return max(0.5, min(1.5, mult))
        except Exception:
            return 1.0
    
    def get_recommendations_for(self, symbol: str, timeframe: str, action: str) -> Dict:
        """
        Retorna recomendaciones cacheadas para un contexto específico.
        Uso desde endpoint /api/review/recommendations/<symbol>/<tf>/<action>
        """
        if not self.db.enabled:
            return {'available': False, 'message': 'Supabase no configurado'}
        
        rec = self.db.get_recommendations(symbol, timeframe, action)
        if not rec:
            return {
                'available': False,
                'message': 'Aún no hay suficientes datos históricos para esta combinación',
                'symbol': symbol,
                'timeframe': timeframe,
                'action': self.db.normalize_action(action)
            }
        
        return {
            'available': True,
            'symbol': rec['symbol'],
            'timeframe': rec['timeframe'],
            'action': rec['action'],
            'winning_strategies': rec.get('winning_strategies', []),
            'losing_strategies': rec.get('losing_strategies', []),
            'best_combinations': rec.get('best_combinations', []),
            'win_rate': rec.get('win_rate', 0),
            'expectancy': rec.get('expectancy', 0),
            'sample_size': rec.get('sample_size', 0),
            'multiplier': rec.get('recommended_confidence_multiplier', 1.0),
            'leverage': rec.get('recommended_leverage', 1),
            'notes': rec.get('notes', ''),
            'created_at': rec.get('created_at')
        }
    
    def get_general_recommendations(self) -> List[Dict]:
        """Retorna las recomendaciones generales (top estrategias globalmente)"""
        if not self.db.enabled:
            return []
        
        stats = self.db.get_general_stats()
        
        return [
            {
                'strategy': s['strategy'],
                'win_rate': s.get('win_rate', 0),
                'expectancy': s.get('expectancy', 0),
                'sample': s.get('total_signals', 0),
                'best_symbols': s.get('best_symbols', []),
                'worst_symbols': s.get('worst_symbols', []),
                'best_timeframes': s.get('best_timeframes', []),
                'worst_timeframes': s.get('worst_timeframes', []),
                'is_degrading': s.get('is_degrading', False)
            }
            for s in stats
        ]
    
    # ========================================================================
    # 6. VOTO EN EL MODERADOR (compatible con TraderBase)
    # ========================================================================
    
    def votar(self, capas: Dict, symbol: str, timeframe: str) -> Tuple[str, float, List[str], List[str]]:
        """
        Vota en el sistema de moderación como los otros 9 traders.
        
        Retorna: (accion, confianza, estrategias_detectadas, razones)
        
        Lógica:
        1. Obtiene las estrategias detectadas por los otros traders (via capas).
        2. Consulta el historial para (symbol, timeframe, LONG) y (symbol, timeframe, SHORT).
        3. Si las estrategias actuales coinciden con combinaciones históricamente ganadoras,
           vota a favor con confianza igual al win rate.
        4. Si coinciden con perdedoras degradadas, vota NO_OPERAR o CAUTION.
        5. Si no hay historial suficiente, vota NEUTRAL con confianza baja.
        """
        accion = 'NEUTRAL'
        confianza = 0
        estrategias_detectadas = []
        razones = []
        
        if not self.db.enabled:
            return 'NEUTRAL', 0, [], ['ReviewTrader deshabilitado (Supabase no configurado)']
        
        try:
            print(f"\n📊 REVIEW TRADER - {symbol} {timeframe}")
            
            # Recolectar estrategias detectadas por otros traders desde las capas
            active_strategies = self._collect_strategies_from_layers(capas)
            
            if not active_strategies:
                print(f"   ⚠️ No hay estrategias activas para evaluar")
                return 'NEUTRAL', 30, [], ['Sin estrategias activas para evaluar']
            
            print(f"   📋 Estrategias activas: {active_strategies}")
            
            # Consultar historial para LONG y SHORT
            rec_long = self.db.get_recommendations(symbol, timeframe, 'LONG')
            rec_short = self.db.get_recommendations(symbol, timeframe, 'SHORT')
            
            # Evaluar coincidencia con ganadoras
            long_score = self._evaluate_match(active_strategies, rec_long)
            short_score = self._evaluate_match(active_strategies, rec_short)
            
            print(f"   📈 Score LONG: {long_score:.1f}")
            print(f"   📉 Score SHORT: {short_score:.1f}")
            
            # Decisión
            if long_score > 60 and long_score > short_score + 15:
                accion = 'COMPRA_SPOT'  # Se normalizará a LONG en el guardado
                confianza = min(95, long_score)
                estrategias_detectadas.append('REVIEW_HISTORICO_GANADOR_LONG')
                razones.append(f"Coincidencia con estrategias ganadoras históricas (score {long_score:.0f})")
                if rec_long:
                    razones.append(f"Basado en {rec_long.get('sample_size', 0)} señales")
                    
            elif short_score > 60 and short_score > long_score + 15:
                accion = 'VENTA_SPOT'  # Se normalizará a SHORT
                confianza = min(95, short_score)
                estrategias_detectadas.append('REVIEW_HISTORICO_GANADOR_SHORT')
                razones.append(f"Coincidencia con estrategias ganadoras históricas (score {short_score:.0f})")
                if rec_short:
                    razones.append(f"Basado en {rec_short.get('sample_size', 0)} señales")
                    
            elif self._detect_loser_pattern(active_strategies, rec_long, rec_short):
                accion = 'NO_OPERAR'
                confianza = 75
                estrategias_detectadas.append('REVIEW_PATRON_PERDEDOR')
                razones.append("Estrategias activas coinciden con patrones históricamente perdedores")
                
            else:
                accion = 'NEUTRAL'
                confianza = 40
                razones.append("Sin evidencia estadística clara")
            
            print(f"   ✅ Decisión: {accion} (confianza {confianza})")
            
        except Exception as e:
            logger.error(f"Error en ReviewTrader.votar: {e}")
            import traceback
            traceback.print_exc()
        
        return accion, confianza, estrategias_detectadas, razones
    
    def _collect_strategies_from_layers(self, capas: Dict) -> List[str]:
        """Recolecta estrategias detectadas por los otros traders desde las capas de análisis"""
        strategies = set()
        
        # Del trend layer
        trend = capas.get('trend', {})
        for vote in trend.get('votes', []):
            src = vote.get('source', '')
            if 'psar_reversal_bull' in src:
                strategies.add('PSAR_REVERSAL_ALCISTA')
            elif 'psar_reversal_bear' in src:
                strategies.add('PSAR_REVERSAL_BAJISTA')
            elif 'dmi_cross_bull' in src:
                strategies.add('DMI_CROSS_ALCISTA')
            elif 'dmi_cross_bear' in src:
                strategies.add('DMI_CROSS_BAJISTA')
        
        # Del momentum layer
        momentum = capas.get('momentum', {})
        divs = momentum.get('divergences', [])
        for d in divs:
            if 'bull' in d.lower():
                strategies.add(f'DIVERGENCIA_{d.upper()}_ALCISTA')
            elif 'bear' in d.lower():
                strategies.add(f'DIVERGENCIA_{d.upper()}_BAJISTA')
        
        # Del volume layer
        volume = capas.get('volume', {})
        if volume.get('whale_buy_confirmed'):
            strategies.add('MAVERICK')
        if volume.get('whale_sell_confirmed'):
            strategies.add('MAVERICK_BAJISTA')
        if volume.get('iceberg_buy'):
            strategies.add('ACUMULACION_ICEBERG')
        if volume.get('iceberg_sell'):
            strategies.add('DISTRIBUCION_ICEBERG')
        
        # Del structure layer
        structure = capas.get('structure', {})
        for ob in structure.get('order_blocks', [])[-3:]:
            if isinstance(ob, dict):
                if ob.get('type') == 'bullish':
                    strategies.add('ORDER_BLOCK_ALCISTA')
                elif ob.get('type') == 'bearish':
                    strategies.add('ORDER_BLOCK_BAJISTA')
        
        for fvg in structure.get('fair_value_gaps', [])[-3:]:
            if isinstance(fvg, dict) and not fvg.get('filled', True):
                if fvg.get('type') == 'bullish':
                    strategies.add('FVG_ALCISTA')
                elif fvg.get('type') == 'bearish':
                    strategies.add('FVG_BAJISTA')
        
        for sweep in structure.get('liquidity_sweeps', [])[-2:]:
            if isinstance(sweep, dict):
                if sweep.get('type') == 'bullish':
                    strategies.add('LIQUIDITY_SWEEP_ALCISTA')
                elif sweep.get('type') == 'bearish':
                    strategies.add('LIQUIDITY_SWEEP_BAJISTA')
        
        # Patrones
        patterns = structure.get('patterns', {})
        for p in patterns.get('recent_patterns', []):
            if isinstance(p, dict) and p.get('reliability', 0) >= 70:
                nombre = p.get('name', '').upper().replace(' ', '_')
                direction = p.get('direction', 'neutral')
                if direction == 'bullish':
                    strategies.add(f'PATRON_{nombre}_ALCISTA')
                elif direction == 'bearish':
                    strategies.add(f'PATRON_{nombre}_BAJISTA')
        
        return sorted(list(strategies))
    
    def _evaluate_match(
        self,
        active: List[str],
        recommendation: Optional[Dict]
    ) -> float:
        """
        Evalúa coincidencia histórica usando:

        - Win Rate
        - Expectancy REAL
        - Tamaño de muestra
        - Calidad del setup

        No confunde WR alto con rentabilidad.
        """

        if not recommendation:
            return 0

        winning = recommendation.get(
            'winning_strategies',
            []
        )

        if not winning:
            return 0

        active_set = {
            s.upper()
            for s in active
        }

        total_score = 0.0
        matches = 0

        for winner in winning:

            if not isinstance(
                winner,
                dict
            ):
                continue

            strategy = str(
                winner.get(
                    'strategy',
                    ''
                )
            ).upper()

            if strategy not in active_set:
                continue

            wr = float(
                winner.get(
                    'win_rate',
                    0
                )
                or 0
            )

            expectancy = float(
                winner.get(
                    'expectancy',
                    0
                )
                or 0
            )

            sample = int(
                winner.get(
                    'sample',
                    0
                )
                or 0
            )

            # ----------------------------------------------------------
            # SCORE WR
            # ----------------------------------------------------------
            wr_score = min(
                100,
                max(
                    0,
                    wr
                )
            )

            # ----------------------------------------------------------
            # SCORE EXPECTANCY
            # ----------------------------------------------------------
            #
            # 0R      = 50
            # +0.5R   = 75
            # +1.0R   = 100
            # negativo = penalización
            # ----------------------------------------------------------
            expectancy_score = (
                50
                + expectancy * 50
            )

            expectancy_score = max(
                0,
                min(
                    100,
                    expectancy_score
                )
            )

            # ----------------------------------------------------------
            # CONFIANZA POR MUESTRA
            # ----------------------------------------------------------
            sample_factor = min(
                1.0,
                sample / 30.0
            )

            # ----------------------------------------------------------
            # SCORE DEL SETUP
            # ----------------------------------------------------------
            strategy_score = (
                wr_score * 0.35
                +
                expectancy_score * 0.45
                +
                (
                    sample_factor
                    * 100
                    * 0.20
                )
            )

            total_score += strategy_score
            matches += 1

        if matches <= 0:
            return 0

        # Bonus pequeño por múltiples coincidencias.
        bonus = min(
            15,
            (matches - 1) * 5
        )

        return min(
            95,
            (
                total_score
                / matches
            )
            + bonus
        )
    
    def _detect_loser_pattern(
        self,
        active: List[str],
        rec_long: Optional[Dict],
        rec_short: Optional[Dict]
    ) -> bool:
        """
        Detecta patrones históricamente perdedores.

        Un patrón sólo cuenta como perdedor si además de
        tener suficiente muestra presenta expectancy negativa
        o degradación importante.
        """

        all_losers = {}

        for rec in (
            rec_long,
            rec_short
        ):

            if not rec:
                continue

            for losing in rec.get(
                'losing_strategies',
                []
            ):

                if not isinstance(
                    losing,
                    dict
                ):
                    continue

                name = str(
                    losing.get(
                        'strategy',
                        ''
                    )
                ).upper()

                if not name:
                    continue

                sample = int(
                    losing.get(
                        'sample',
                        0
                    )
                    or 0
                )

                expectancy = float(
                    losing.get(
                        'expectancy',
                        0
                    )
                    or 0
                )

                degrading = bool(
                    losing.get(
                        'degrading',
                        False
                    )
                )

                all_losers[
                    name
                ] = (
                    sample,
                    expectancy,
                    degrading
                )

        active_set = {
            s.upper()
            for s in active
        }

        strong_loser_matches = 0

        for strategy in (
            active_set
            & set(
                all_losers.keys()
            )
        ):

            sample, expectancy, degrading = (
                all_losers[
                    strategy
                ]
            )

            if sample < MIN_SAMPLE_ACTIONABLE:
                continue

            if (
                expectancy <= -0.10
                or degrading
            ):
                strong_loser_matches += 1

        return (
            strong_loser_matches
            >= 2
        )
    
    # ========================================================================
    # OPTIMIZACIONES DE VOLUMEN (Fase 2.5)
    # ========================================================================
    
    def should_save_signal(self, analysis_result: Dict) -> bool:
        """
        Decide si guardar una señal en la BD.
        Aplica muestreo estratificado para evitar sobrecarga en TF cortas.
        
        Reglas:
        - TODAS las señales de trading (LONG/SHORT/COMPRA_SPOT/VENTA_SPOT) SIEMPRE se guardan.
        - Señales NO_OPERAR con confianza >= 55% se guardan (posibles oportunidades perdidas).
        - Señales NO_OPERAR con confianza < 55% en TF cortas (5m, 15m) → DESCARTAR.
        - En TF largas (>= 30m), todas las señales NO_OPERAR se guardan.
        
        Retorna: True si debe guardarse, False si debe descartarse.
        """
        try:
            decision = analysis_result.get('decision', {})
            action = decision.get('action', 'NO_OPERAR')
            confidence = decision.get('confidence', 0)
            timeframe = analysis_result.get('timeframe', '')
            
            # Regla 1: Señales de trading SIEMPRE se guardan
            if action in ('COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT'):
                return True
            
            # Regla 2: Señales de espera se guardan si confianza >= 55%
            if action in ('NO_OPERAR', 'ESPERAR', 'CAUTION', 'NEUTRAL'):
                # En TF cortas: solo si confianza suficiente
                if timeframe in ('5m', '15m'):
                    if confidence < 55:
                        return False  # Descartar ruido
                # En TF medianas: filtro más laxo
                elif timeframe in ('30m', '1h'):
                    if confidence < 40:
                        return False
                # En TF largas: guardar todas (son pocas)
                # timeframe en ('2h', '4h', '12h', '1D', '1W'): siempre guardar
                
                return True
            
            # Otro tipo de acción: guardar por defecto
            return True
            
        except Exception as e:
            logger.error(f"Error en should_save_signal: {e}")
            return True  # En caso de error, guardar (mejor tener demás que perder datos)
    
    def apply_optimization_cleanup(self) -> Dict:
        """
        Aplica todas las optimizaciones de almacenamiento:
        1. TTL diferenciado por temporalidad (borra señales antiguas)
        2. Compresión de stats con pocas muestras
        3. Reporte de uso de almacenamiento
        
        Se ejecuta idealmente 1 vez al día junto con run_full_review().
        """
        if not self.db.enabled:
            return {'ttl': {}, 'compression': 0, 'storage': {}}
        
        print(f"\n{'='*60}")
        print(f"🧹 [REVIEW] Aplicando optimizaciones de almacenamiento")
        print(f"{'='*60}")
        
        results = {}
        
        # 1. TTL cleanup
        try:
            results['ttl'] = self.db.apply_ttl_cleanup()
            total_ttl = sum(results['ttl'].values())
            print(f"   ✅ TTL cleanup: {total_ttl} señales antiguas eliminadas")
            for tf, count in results['ttl'].items():
                if count > 0:
                    print(f"      • {tf}: {count} señales")
        except Exception as e:
            logger.error(f"Error en TTL cleanup: {e}")
            results['ttl'] = {}
        
        # 2. Compresión de stats con muestra baja
        # DESACTIVADO: en sistemas jóvenes, borrar stats con <5 muestras impide
        # que se acumule aprendizaje visible. Preferimos guardar todas las stats
        # aunque tengan pocas muestras (el PDF ya las etiqueta como "insuficientes"
        # si están por debajo de MIN_SAMPLE_SIZE).
        results['compression'] = 0
        print(f"   ℹ️  Compresión de stats: DESACTIVADA (se mantienen todas las stats aunque tengan <5 muestras)")
        
        # 3. Reporte de uso
        try:
            results['storage'] = self.db.get_storage_stats()
            total_rows = sum(v for v in results['storage'].values() if v > 0)
            print(f"\n   📊 USO ACTUAL DE ALMACENAMIENTO:")
            for table, count in results['storage'].items():
                print(f"      • {table:35s} {count:6d} filas")
            print(f"      • TOTAL: {total_rows} filas")
        except Exception as e:
            logger.error(f"Error obteniendo storage stats: {e}")
            results['storage'] = {}
        
        print(f"{'='*60}\n")
        return results
    
    # ========================================================================
    # 7. MÉTODO PRINCIPAL (para ser llamado por el scheduler)
    # ========================================================================
    
    def run_full_review(self, price_fetcher, trigger_source: str = 'scheduler') -> Dict:
        """
        Ejecuta el ciclo completo del ReviewTrader:
        1. Evaluar señales pendientes (TP/SL/expired)
        2. Detectar oportunidades perdidas
        3. Recalcular estadísticas
        4. Aplicar optimizaciones
        5. Registrar log en Supabase (Fase A)
        
        Se ejecuta ideal 1 vez al día por un scheduler.
        
        Args:
            price_fetcher: función (symbol, timeframe) → DataFrame de velas
            trigger_source: 'scheduler' (automático) o 'manual' (desde endpoint)
        """
        run_started = datetime.utcnow()
        
        print(f"\n{'#'*60}")
        print(f"# 🎓 REVIEW TRADER - CICLO COMPLETO")
        print(f"# Trigger: {trigger_source}")
        print(f"# {run_started.isoformat()}")
        print(f"{'#'*60}")
        
        results = {
            'evaluated': {},
            'missed': 0,
            'stats': {},
            'optimization': {}
        }
        errors = []
        warnings = []
        
        # 1. Evaluar señales pendientes
        try:
            results['evaluated'] = self.evaluate_pending_signals(price_fetcher)
        except Exception as e:
            err_msg = f"evaluate_pending_signals: {str(e)[:200]}"
            logger.error(err_msg)
            errors.append(err_msg)
        
        # 2. Detectar oportunidades perdidas
        try:
            results['missed'] = self.detect_missed_opportunities(price_fetcher)
        except Exception as e:
            err_msg = f"detect_missed_opportunities: {str(e)[:200]}"
            logger.error(err_msg)
            errors.append(err_msg)
        
        # 3. Recalcular stats
        try:
            results['stats'] = self.recalculate_stats()
        except Exception as e:
            err_msg = f"recalculate_stats: {str(e)[:200]}"
            logger.error(err_msg)
            errors.append(err_msg)
        
        # 4. Optimizaciones de almacenamiento
        try:
            results['optimization'] = self.apply_optimization_cleanup()
        except Exception as e:
            err_msg = f"apply_optimization_cleanup: {str(e)[:200]}"
            logger.error(err_msg)
            errors.append(err_msg)
        
        run_finished = datetime.utcnow()
        duration = (run_finished - run_started).total_seconds()
        
        # 5. Registrar log completo en Supabase
        try:
            evaluated = results.get('evaluated', {})
            stats = results.get('stats', {})
            optimization = results.get('optimization', {})
            ttl = optimization.get('ttl', {})
            storage = optimization.get('storage', {})
            
            # Estado del ciclo
            if errors:
                status = 'failed' if len(errors) >= 3 else 'partial'
            else:
                status = 'success'
            
            # Notas descriptivas
            notes_parts = []
            if evaluated:
                notes_parts.append(
                    f"Evaluadas: {evaluated.get('processed', 0)} "
                    f"(TP: {evaluated.get('tp_hit', 0)}, "
                    f"SL: {evaluated.get('sl_hit', 0)}, "
                    f"Exp: {evaluated.get('expired', 0)})"
                )
            if results.get('missed', 0) > 0:
                notes_parts.append(f"Oportunidades perdidas: {results['missed']}")
            if stats:
                notes_parts.append(
                    f"Stats actualizadas: {stats.get('specific', 0)} específicas + "
                    f"{stats.get('general', 0)} generales"
                )
            notes = ' | '.join(notes_parts) if notes_parts else 'Ciclo sin cambios'
            
            log_data = {
                'run_started_at': run_started.isoformat(),
                'run_finished_at': run_finished.isoformat(),
                'duration_seconds': round(duration, 2),
                'trigger_source': trigger_source,
                'signals_evaluated': evaluated.get('processed', 0),
                'tp_hits': evaluated.get('tp_hit', 0),
                'sl_hits': evaluated.get('sl_hit', 0),
                'expired': evaluated.get('expired', 0),
                'still_pending': evaluated.get('still_pending', 0),
                'missed_opportunities_found': results.get('missed', 0),
                'stats_specific_updated': stats.get('specific', 0),
                'stats_general_updated': stats.get('general', 0),
                'recommendations_updated': 0,  # se calcula dentro de recalculate_stats
                'ttl_deleted': sum(ttl.values()) if isinstance(ttl, dict) else 0,
                'low_sample_deleted': optimization.get('compression', 0),
                'storage_stats': storage,
                'errors': errors,
                'warnings': warnings,
                'notes': notes,
                'status': status
            }
            
            log_id = self.db.insert_review_log(log_data)
            if log_id:
                print(f"📝 [REVIEW] Log guardado: {log_id[:8]}... ({status}, {duration:.1f}s)")
            
            results['log_id'] = log_id
            results['duration_seconds'] = duration
            results['status'] = status
        except Exception as e:
            logger.error(f"Error insertando review_log: {e}")
        
        print(f"\n{'#'*60}")
        print(f"# ✅ REVIEW TRADER - CICLO COMPLETADO ({duration:.1f}s)")
        print(f"{'#'*60}\n")
        
        return results


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================

# Otras partes del sistema importan esta instancia:
# from review_trader import review_trader
review_trader = ReviewTrader()

if review_trader.db.enabled:
    print("✅ REVIEW TRADER inicializado y conectado a Supabase")
else:
    print("⚠️ REVIEW TRADER en modo degradado (Supabase no disponible)")
    print("   Las señales NO se guardarán hasta configurar credenciales")
