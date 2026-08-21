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
MIN_SAMPLE_SIZE = 20              # Mínimo de muestras para considerar estadísticamente válido
MIN_SAMPLE_SIZE_GENERAL = 50      # Para stats generales necesitamos más muestras
WIN_RATE_WINNER = 60.0            # % para considerar estrategia "ganadora"
WIN_RATE_LOSER = 40.0             # % para considerar estrategia "perdedora"
DEGRADATION_THRESHOLD = 15.0      # Caída de win rate en últimas 20 vs histórico

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
    
    def _check_tp_sl_hit(self, signal: Dict, df) -> Optional[Dict]:
        """
        Verifica si la señal alcanzó su TP o SL usando el DataFrame de velas.
        Retorna dict con el resultado o None si aún no se resolvió.
        """
        try:
            action = signal.get('action_normalized')
            entry = float(signal.get('entry_price', 0))
            sl = float(signal.get('stop_loss', 0))
            tp = float(signal.get('take_profit', 0))
            
            if entry == 0 or sl == 0 or tp == 0:
                return None
            
            # Timestamp de la señal
            signal_ts = self._parse_ts(signal.get('candle_timestamp') or signal.get('created_at'))
            if not signal_ts:
                return None
            
            # Filtrar solo velas POSTERIORES a la señal
            import pandas as pd
            if 'time' in df.columns:
                df_after = df[pd.to_datetime(df['time'], utc=True) > pd.Timestamp(signal_ts, tz='UTC')]
            else:
                df_after = df
            
            if len(df_after) == 0:
                return None
            
            # Recorrer velas post-señal en orden
            for idx, row in df_after.iterrows():
                high = float(row['high'])
                low = float(row['low'])
                close = float(row['close'])
                candle_ts = row.get('time', datetime.utcnow())
                
                if action == 'LONG':
                    # SL primero (peor caso): si low <= SL
                    if low <= sl:
                        pnl_pct = ((sl - entry) / entry) * 100
                        return {
                            'status': 'sl_hit',
                            'exit_price': sl,
                            'exit_timestamp': str(candle_ts),
                            'pnl_pct': pnl_pct,
                            'candles_to_result': idx
                        }
                    # TP: si high >= TP
                    if high >= tp:
                        pnl_pct = ((tp - entry) / entry) * 100
                        return {
                            'status': 'tp_hit',
                            'exit_price': tp,
                            'exit_timestamp': str(candle_ts),
                            'pnl_pct': pnl_pct,
                            'candles_to_result': idx
                        }
                elif action == 'SHORT':
                    # SL primero: si high >= SL
                    if high >= sl:
                        pnl_pct = ((entry - sl) / entry) * 100
                        return {
                            'status': 'sl_hit',
                            'exit_price': sl,
                            'exit_timestamp': str(candle_ts),
                            'pnl_pct': pnl_pct,
                            'candles_to_result': idx
                        }
                    # TP: si low <= TP
                    if low <= tp:
                        pnl_pct = ((entry - tp) / entry) * 100
                        return {
                            'status': 'tp_hit',
                            'exit_price': tp,
                            'exit_timestamp': str(candle_ts),
                            'pnl_pct': pnl_pct,
                            'candles_to_result': idx
                        }
            
            return None  # Aún pendiente
            
        except Exception as e:
            logger.error(f"Error en _check_tp_sl_hit: {e}")
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
    # 4. RECALCULAR ESTADÍSTICAS
    # ========================================================================
    
    def recalculate_stats(self) -> Dict:
        """
        Recalcula todas las estadísticas específicas y generales a partir del historial.
        Se ejecuta idealmente 1 vez al día.
        """
        if not self.db.enabled:
            return {'specific': 0, 'general': 0}
        
        print(f"\n{'='*60}")
        print(f"📊 [REVIEW] Recalculando estadísticas...")
        print(f"{'='*60}")
        
        # Obtener todas las señales con resultado
        signals_data = self.db.get_signals_for_stats(days_back=90)
        
        if not signals_data:
            print("   ⚠️ No hay señales suficientes para calcular estadísticas")
            return {'specific': 0, 'general': 0}
        
        print(f"   📈 Procesando {len(signals_data)} señales con resultado...")
        
        # ============ ESTADÍSTICAS ESPECÍFICAS (par + TF + acción + estrategia) ============
        # Diccionario indexado por (symbol, timeframe, action, strategy)
        specific_stats = defaultdict(lambda: {
            'wins': 0, 'losses': 0, 'expired': 0,
            'win_pcts': [], 'loss_pcts': [], 'rrs': [],
            'recent_20': []  # (result_win_boolean, timestamp)
        })
        
        # ============ ESTADÍSTICAS GENERALES (agregado por estrategia) ============
        general_stats = defaultdict(lambda: {
            'wins': 0, 'losses': 0,
            'rrs': [],
            'by_symbol': defaultdict(lambda: {'wins': 0, 'losses': 0}),
            'by_timeframe': defaultdict(lambda: {'wins': 0, 'losses': 0}),
            'recent_20': []
        })
        
        for signal in signals_data:
            try:
                status = signal.get('status')
                if status not in ('tp_hit', 'sl_hit', 'expired', 'missed_opportunity'):
                    continue
                
                symbol = signal.get('symbol')
                timeframe = signal.get('timeframe')
                action = signal.get('action_normalized')
                
                # Extraer estrategias de la señal
                signal_indicators = signal.get('signal_indicators', [])
                if not isinstance(signal_indicators, list):
                    signal_indicators = []
                strategies = [si.get('strategy_name') for si in signal_indicators if si.get('strategy_name')]
                
                if not strategies:
                    continue
                
                # Extraer PnL del resultado
                pnl_pct = 0
                # Necesitamos consultar signal_results por separado si el join no lo trae
                # Por simplicidad, calculamos a partir de status
                is_win = status == 'tp_hit'
                is_loss = status == 'sl_hit'
                
                # Para cada estrategia detectada en esta señal
                for strategy in strategies:
                    # Stats específicas
                    key = (symbol, timeframe, action, strategy)
                    if is_win:
                        specific_stats[key]['wins'] += 1
                    elif is_loss:
                        specific_stats[key]['losses'] += 1
                    elif status == 'expired':
                        specific_stats[key]['expired'] += 1
                    
                    specific_stats[key]['recent_20'].append((is_win, signal.get('created_at')))
                    
                    # Stats generales
                    if is_win:
                        general_stats[strategy]['wins'] += 1
                        general_stats[strategy]['by_symbol'][symbol]['wins'] += 1
                        general_stats[strategy]['by_timeframe'][timeframe]['wins'] += 1
                    elif is_loss:
                        general_stats[strategy]['losses'] += 1
                        general_stats[strategy]['by_symbol'][symbol]['losses'] += 1
                        general_stats[strategy]['by_timeframe'][timeframe]['losses'] += 1
                    
                    general_stats[strategy]['recent_20'].append((is_win, signal.get('created_at')))
                    
            except Exception as e:
                logger.error(f"Error procesando señal: {e}")
        
        # ============ TRANSFORMAR A FORMATO DE TABLA ============
        specific_rows = []
        for (symbol, tf, action, strategy), data in specific_stats.items():
            total_resolved = data['wins'] + data['losses']
            if total_resolved == 0:
                continue
            
            win_rate = (data['wins'] / total_resolved) * 100
            
            # Win rate de las últimas 20 (para detectar degradación)
            recent = sorted(data['recent_20'], key=lambda x: x[1] or '', reverse=True)[:20]
            recent_wins = sum(1 for r in recent if r[0])
            recent_total = len(recent)
            last_20_win_rate = (recent_wins / recent_total * 100) if recent_total > 0 else win_rate
            
            is_degrading = (win_rate - last_20_win_rate) > DEGRADATION_THRESHOLD
            
            # Expectancy simplificada (asumimos R/R promedio 2:1 hasta tener datos exactos)
            avg_rr = 2.0
            expectancy = ((win_rate / 100) * avg_rr) - ((1 - win_rate / 100) * 1)
            
            specific_rows.append({
                'symbol': symbol,
                'timeframe': tf,
                'action': action,
                'strategy': strategy,
                'total_signals': total_resolved + data['expired'],
                'wins': data['wins'],
                'losses': data['losses'],
                'expired': data['expired'],
                'win_rate': round(win_rate, 2),
                'avg_win_pct': 0,  # Se puede calcular si hay datos de PnL
                'avg_loss_pct': 0,
                'avg_rr': avg_rr,
                'expectancy': round(expectancy, 4),
                'last_20_win_rate': round(last_20_win_rate, 2),
                'is_degrading': is_degrading,
                'last_updated': datetime.utcnow().isoformat()
            })
        
        general_rows = []
        for strategy, data in general_stats.items():
            total = data['wins'] + data['losses']
            if total == 0:
                continue
            
            win_rate = (data['wins'] / total) * 100
            avg_rr = 2.0
            expectancy = ((win_rate / 100) * avg_rr) - ((1 - win_rate / 100) * 1)
            
            # Best/worst symbols
            symbol_scores = {}
            for sym, ss in data['by_symbol'].items():
                if ss['wins'] + ss['losses'] > 0:
                    symbol_scores[sym] = (ss['wins'] / (ss['wins'] + ss['losses'])) * 100
            
            best_symbols = sorted(symbol_scores.items(), key=lambda x: -x[1])[:3]
            worst_symbols = sorted(symbol_scores.items(), key=lambda x: x[1])[:3]
            
            # Best/worst timeframes
            tf_scores = {}
            for tf, ts in data['by_timeframe'].items():
                if ts['wins'] + ts['losses'] > 0:
                    tf_scores[tf] = (ts['wins'] / (ts['wins'] + ts['losses'])) * 100
            
            best_tfs = sorted(tf_scores.items(), key=lambda x: -x[1])[:3]
            worst_tfs = sorted(tf_scores.items(), key=lambda x: x[1])[:3]
            
            # Degradación general
            recent = sorted(data['recent_20'], key=lambda x: x[1] or '', reverse=True)[:20]
            recent_wins = sum(1 for r in recent if r[0])
            recent_total = len(recent)
            last_20_wr = (recent_wins / recent_total * 100) if recent_total > 0 else win_rate
            is_degrading = (win_rate - last_20_wr) > DEGRADATION_THRESHOLD
            
            general_rows.append({
                'strategy': strategy,
                'total_signals': total,
                'wins': data['wins'],
                'losses': data['losses'],
                'win_rate': round(win_rate, 2),
                'avg_rr': avg_rr,
                'expectancy': round(expectancy, 4),
                'best_symbols': [s[0] for s in best_symbols],
                'worst_symbols': [s[0] for s in worst_symbols],
                'best_timeframes': [t[0] for t in best_tfs],
                'worst_timeframes': [t[0] for t in worst_tfs],
                'is_degrading': is_degrading,
                'last_updated': datetime.utcnow().isoformat()
            })
        
        # Guardar en base de datos
        if specific_rows:
            self.db.upsert_strategy_stats(specific_rows, general=False)
        if general_rows:
            self.db.upsert_strategy_stats(general_rows, general=True)
        
        print(f"   ✅ Stats específicas actualizadas: {len(specific_rows)} filas")
        print(f"   ✅ Stats generales actualizadas: {len(general_rows)} filas")
        print(f"{'='*60}\n")
        
        # Generar recomendaciones cacheadas
        self._generate_recommendations(specific_rows, general_rows)
        
        return {'specific': len(specific_rows), 'general': len(general_rows)}
    
    def _generate_recommendations(self, specific_rows: List[Dict], general_rows: List[Dict]):
        """Genera recomendaciones pre-calculadas para consumo rápido del frontend"""
        if not self.db.enabled:
            return
        
        try:
            # Agrupar stats específicas por (symbol, timeframe, action)
            grouped = defaultdict(list)
            for row in specific_rows:
                key = (row['symbol'], row['timeframe'], row['action'])
                grouped[key].append(row)
            
            recs_generated = 0
            
            for (symbol, timeframe, action), rows in grouped.items():
                if action == 'NO_OPERAR':
                    continue
                
                # Ordenar por expectancy
                rows_sorted = sorted(rows, key=lambda r: -r['expectancy'])
                
                # Ganadoras: expectancy > 0 y win_rate > 55 y sample >= MIN_SAMPLE_SIZE
                winners = [r for r in rows_sorted 
                          if r['win_rate'] >= WIN_RATE_WINNER 
                          and r['total_signals'] >= MIN_SAMPLE_SIZE
                          and not r['is_degrading']][:5]
                
                # Perdedoras
                losers = [r for r in rows_sorted 
                         if (r['win_rate'] < WIN_RATE_LOSER or r['is_degrading'])
                         and r['total_signals'] >= MIN_SAMPLE_SIZE][:5]
                
                # Multiplicador basado en el mejor win rate ganador
                if winners:
                    best_wr = winners[0]['win_rate']
                    multiplier = self._calculate_multiplier(best_wr)
                    avg_wr = sum(r['win_rate'] for r in winners) / len(winners)
                    avg_exp = sum(r['expectancy'] for r in winners) / len(winners)
                    sample_total = sum(r['total_signals'] for r in winners)
                else:
                    multiplier = MULTIPLIER_NEUTRAL
                    avg_wr = 0
                    avg_exp = 0
                    sample_total = 0
                
                rec_data = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'action': action,
                    'winning_strategies': [
                        {'strategy': r['strategy'], 'win_rate': r['win_rate'], 
                         'sample': r['total_signals'], 'rr': r['avg_rr']}
                        for r in winners
                    ],
                    'losing_strategies': [
                        {'strategy': r['strategy'], 'win_rate': r['win_rate'],
                         'sample': r['total_signals'], 'degrading': r['is_degrading']}
                        for r in losers
                    ],
                    'best_combinations': [],  # TODO en versión futura
                    'win_rate': round(avg_wr, 2),
                    'expectancy': round(avg_exp, 4),
                    'sample_size': sample_total,
                    'multiplier': multiplier,
                    'leverage': self._suggest_leverage(timeframe, avg_wr),
                    'notes': self._build_notes(winners, losers)
                }
                
                self.db.upsert_recommendation(rec_data)
                recs_generated += 1
            
            print(f"   ✅ Recomendaciones cacheadas: {recs_generated}")
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones: {e}")
    
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
    
    def _evaluate_match(self, active: List[str], recommendation: Optional[Dict]) -> float:
        """
        Evalúa qué tanto coinciden las estrategias activas con las ganadoras históricas.
        Retorna un score 0-100.
        """
        if not recommendation:
            return 0
        
        winning = recommendation.get('winning_strategies', [])
        if not winning:
            return 0
        
        winner_names = {w.get('strategy', '').upper() for w in winning if isinstance(w, dict)}
        active_set = {s.upper() for s in active}
        
        matches = active_set & winner_names
        
        if not matches:
            return 0
        
        # Score: promedio de win_rates de las estrategias que coinciden
        matching_wrs = []
        for w in winning:
            if isinstance(w, dict) and w.get('strategy', '').upper() in matches:
                matching_wrs.append(w.get('win_rate', 0))
        
        if matching_wrs:
            avg_wr = sum(matching_wrs) / len(matching_wrs)
            # Bonus por múltiples coincidencias
            bonus = min(15, (len(matches) - 1) * 5)
            return min(95, avg_wr + bonus)
        
        return 0
    
    def _detect_loser_pattern(self, active: List[str], rec_long: Optional[Dict], 
                              rec_short: Optional[Dict]) -> bool:
        """Detecta si las estrategias activas coinciden con patrones perdedores"""
        all_losers = set()
        
        for rec in [rec_long, rec_short]:
            if rec:
                for l in rec.get('losing_strategies', []):
                    if isinstance(l, dict):
                        all_losers.add(l.get('strategy', '').upper())
        
        active_set = {s.upper() for s in active}
        matches = active_set & all_losers
        
        # Si al menos 2 estrategias activas son perdedoras conocidas
        return len(matches) >= 2
    
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
        try:
            results['compression'] = self.db.delete_low_sample_stats(min_sample=5)
            print(f"   ✅ Compresión de stats: {results['compression']} filas con <5 muestras eliminadas")
        except Exception as e:
            logger.error(f"Error en compresión: {e}")
            results['compression'] = 0
        
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
    
    def run_full_review(self, price_fetcher) -> Dict:
        """
        Ejecuta el ciclo completo del ReviewTrader:
        1. Evaluar señales pendientes (TP/SL/expired)
        2. Detectar oportunidades perdidas
        3. Recalcular estadísticas
        4. Generar recomendaciones
        
        Se ejecuta ideal 1 vez al día por un scheduler.
        
        price_fetcher: función (symbol, timeframe) → DataFrame de velas
        """
        print(f"\n{'#'*60}")
        print(f"# 🎓 REVIEW TRADER - CICLO COMPLETO")
        print(f"# {datetime.utcnow().isoformat()}")
        print(f"{'#'*60}")
        
        results = {
            'evaluated': {},
            'missed': 0,
            'stats': {}
        }
        
        # 1. Evaluar señales pendientes
        try:
            results['evaluated'] = self.evaluate_pending_signals(price_fetcher)
        except Exception as e:
            logger.error(f"Error en evaluate_pending_signals: {e}")
        
        # 2. Detectar oportunidades perdidas
        try:
            results['missed'] = self.detect_missed_opportunities(price_fetcher)
        except Exception as e:
            logger.error(f"Error en detect_missed_opportunities: {e}")
        
        # 3. Recalcular stats
        try:
            results['stats'] = self.recalculate_stats()
        except Exception as e:
            logger.error(f"Error en recalculate_stats: {e}")
        
        # 4. Optimizaciones de almacenamiento (Fase 2.5)
        try:
            results['optimization'] = self.apply_optimization_cleanup()
        except Exception as e:
            logger.error(f"Error en apply_optimization_cleanup: {e}")
            results['optimization'] = {}
        
        print(f"\n{'#'*60}")
        print(f"# ✅ REVIEW TRADER - CICLO COMPLETADO")
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
