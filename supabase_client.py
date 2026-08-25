# supabase_client.py
# Cliente para la base de datos Supabase del ReviewTrader y sistema de Futuros
# Versión 1.0 - FASE 1
# 
# INSTRUCCIONES DE INSTALACIÓN:
# 1. Ejecutar en terminal: pip install supabase
# 2. Agregar 'supabase>=2.0.0' al archivo requirements.txt
# 3. Colocar las credenciales en las variables SUPABASE_URL y SUPABASE_KEY más abajo
# 4. Ejecutar el archivo schema_supabase.sql en el editor SQL de Supabase (una sola vez)
#
# CARACTERÍSTICAS:
# - Persistencia de señales spot y futuros
# - Estadísticas por par/temporalidad/acción (individual)
# - Estadísticas por estrategia agregada (general)
# - Detección de oportunidades perdidas
# - Rotación FIFO automática para no colapsar la BD gratuita (500MB)
# - Compatibilidad COMPRA_SPOT ≡ LONG y VENTA_SPOT ≡ SHORT (ver normalize_action)

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# ============================================================================
# CREDENCIALES DE SUPABASE
# ============================================================================
# Las credenciales se leen desde un archivo .env (que NO se sube a GitHub).
# Ver archivo .env.example para saber qué variables definir.
#
# Instrucciones:
# 1. Crear un archivo .env en la raíz del proyecto (al lado de app.py)
# 2. Escribir en él:
#      SUPABASE_URL=https://tu-proyecto.supabase.co
#      SUPABASE_KEY=sb_secret_...
# 3. Guardar. El archivo .env está en .gitignore, no se subirá a GitHub.

# Cargar .env si está disponible
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv no está instalado, se usarán solo os.environ

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# ============================================================================
# LOGGING
# ============================================================================
logger = logging.getLogger('SUPABASE')
logger.setLevel(logging.INFO)

# Silenciar logs verbosos de httpcore/httpx/hpack en producción.
# Estos módulos imprimen DEBUG con cada reconexión SSL/HTTP2, ensuciando los logs.
for _noisy in ('httpcore', 'httpcore.connection', 'httpcore.http2', 'httpcore.http11',
               'httpx', 'hpack', 'h2', 'urllib3'):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

print("=" * 60)
print("🗄️ SUPABASE CLIENT - INICIALIZANDO")
print("=" * 60)

# ============================================================================
# LÍMITES DE ROTACIÓN FIFO (para no colapsar Supabase gratuito - 500MB)
# ============================================================================
LIMITS = {
    'signals': 20000,                    # Máximo de señales históricas
    'signal_indicators': 100000,         # Indicadores por señal (relación N:M)
    'signal_results': 20000,             # Resultados TP/SL
    'strategy_stats_specific': 5000,     # Estadísticas específicas
    'strategy_stats_general': 500,       # Estadísticas generales
    'missed_opportunities': 5000,        # Oportunidades perdidas
    'review_recommendations': 2000       # Recomendaciones cacheadas
}


# ============================================================================
# CLASE PRINCIPAL: SUPABASE CLIENT
# ============================================================================

class SupabaseClient:
    """
    Cliente Supabase para el ReviewTrader.
    
    Todas las operaciones son idempotentes y tolerantes a fallos.
    Si Supabase no está configurado, las operaciones no fallan: retornan None
    para que el sistema principal siga funcionando sin ReviewTrader.
    """
    
    def __init__(self, url: str = None, key: str = None):
        self.url = url or SUPABASE_URL
        self.key = key or SUPABASE_KEY
        self.client = None
        self.enabled = False
        self._reconnect_lock = None  # Se inicializa perezosamente
        
        if not self.url or not self.key:
            print("⚠️ SUPABASE no configurado (URL o KEY vacíos)")
            print("   El sistema funcionará SIN ReviewTrader hasta que se configuren las credenciales")
            return
        
        try:
            self._create_client()
            self.enabled = True
            print(f"✅ SUPABASE conectado a: {self.url[:40]}...")
        except ImportError:
            print("❌ Librería 'supabase' no instalada. Ejecutar: pip install supabase")
        except Exception as e:
            print(f"❌ Error conectando a SUPABASE: {e}")
    
    def _create_client(self):
        """Crea (o recrea) el cliente Supabase. Se usa en __init__ y en reconexiones."""
        from supabase import create_client
        self.client = create_client(self.url, self.key)
    
    def _reconnect(self):
        """
        Reconecta el cliente Supabase después de un ConnectionTerminated.
        Thread-safe: solo un thread reconecta a la vez.
        """
        import threading
        if self._reconnect_lock is None:
            self._reconnect_lock = threading.Lock()
        with self._reconnect_lock:
            try:
                self._create_client()
                logger.info("Cliente Supabase reconectado tras ConnectionTerminated")
                return True
            except Exception as e:
                logger.error(f"Fallo al reconectar cliente Supabase: {e}")
                return False
    
    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        """
        Detecta si una excepción es un error de conexión transitorio
        (ConnectionTerminated HTTP/2, RemoteProtocolError, ReadError, etc.)
        que se puede resolver reconectando y reintentando.
        """
        msg = str(exc)
        markers = (
            'ConnectionTerminated',
            'RemoteProtocolError',
            'ReadError',
            'WriteError',
            'ConnectError',
            'ConnectTimeout',
            'PoolTimeout',
            'GOAWAY',
            'error_code:9',
            'Server disconnected',
            'Connection aborted',
            'Resource temporarily unavailable',  # EAGAIN cuando el sistema está saturado
            'Errno 11',                          # código EAGAIN en Linux
            'BrokenPipeError',
            'OSError',
        )
        return any(m in msg for m in markers)
    
    def _with_retry(self, operation, *args, **kwargs):
        """
        Ejecuta una operación de Supabase con reintento automático ante
        errores de conexión (ConnectionTerminated, EAGAIN, etc).
        
        operation: callable que ejecuta la query Supabase.
        Si falla con error de conexión, reconecta y reintenta 1 vez.
        Si falla por otro motivo, propaga la excepción.
        
        v22.6: cambio de log level: si el retry TIENE ÉXITO, se registra a
        nivel DEBUG (no polluye los logs de Render). Solo si el retry FALLA
        se registra a WARNING para alertar al operador. Los EAGAIN transitorios
        (que se resuelven al 2° intento) son normales cuando el pool HTTP/2
        está saturado y no ameritan preocupar.
        """
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            if not self._is_connection_error(e):
                raise
            logger.debug(f"Error de conexión Supabase transitorio: {e}. Reconectando...")
            if not self._reconnect():
                logger.warning(f"Error de conexión Supabase y no se pudo reconectar: {e}")
                raise
            # Reintento (una sola vez)
            try:
                return operation(*args, **kwargs)
            except Exception as e2:
                logger.warning(f"Error de conexión Supabase persistió tras retry: {e2}")
                raise
    
    # ========================================================================
    # NORMALIZACIÓN DE ACCIONES
    # ========================================================================
    
    @staticmethod
    def normalize_action(action: str) -> str:
        """
        Normaliza las acciones para el ReviewTrader.
        COMPRA_SPOT ≡ LONG (ambas se guardan como 'LONG')
        VENTA_SPOT ≡ SHORT (ambas se guardan como 'SHORT')
        """
        if action in ('COMPRA_SPOT', 'LONG'):
            return 'LONG'
        elif action in ('VENTA_SPOT', 'SHORT'):
            return 'SHORT'
        elif action in ('NO_OPERAR', 'ESPERAR', 'CAUTION', 'NEUTRAL'):
            return 'NO_OPERAR'
        else:
            return action
    
    @staticmethod
    def get_system_type(symbol: str) -> str:
        """Determina si el símbolo es spot o futures según el par"""
        # PAXG es solo spot; el resto son ambos pero se distinguen por contexto
        spot_only = ['PAXG-USDT', 'PAXG-BTC']
        futures_symbols = ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT']
        
        if symbol in spot_only:
            return 'spot'
        elif symbol in futures_symbols:
            return 'both'  # Puede operarse como spot o futures
        return 'spot'
    
    # ========================================================================
    # INSERCIÓN DE SEÑALES (Fase 1: guardar; Fase 2: evaluar resultado)
    # ========================================================================
    
    def insert_signal(self, signal_data: Dict) -> Optional[str]:
        """
        Guarda una señal en la base de datos.
        
        Estructura esperada de signal_data:
        {
            'symbol': 'BTC-USDT',
            'timeframe': '1h',
            'system_type': 'spot' | 'futures',
            'action': 'COMPRA_SPOT' | 'LONG' | 'VENTA_SPOT' | 'SHORT' | 'NO_OPERAR',
            'confidence': 78.5,
            'entry': 68250.0,
            'stop_loss': 67320.0,
            'take_profit': 70180.0,
            'leverage': 12,
            'risk_reward': 2.5,
            'current_price': 68300.0,
            'candle_timestamp': '2026-08-21T14:00:00',  # Timestamp de la vela ANTERIOR (cerrada)
            'strategies': ['ORDER_BLOCK_ALCISTA', 'FVG_ALCISTA'],  # Lista de estrategias
            'indicators_snapshot': { ... },  # JSON con valores de todos los indicadores
            'context': { ... }  # sesión, día, fear&greed, correlación, etc.
        }
        
        Retorna: ID de la señal insertada o None si falla.
        """
        if not self.enabled:
            return None
        
        try:
            normalized_action = self.normalize_action(signal_data.get('action', ''))
            
            # Cap defensivo: la confianza NUNCA debe superar 100% estadísticamente.
            # Aunque el Moderador ahora capa correctamente, blindamos también aquí.
            _raw_conf = float(signal_data.get('confidence', 0))
            _capped_conf = max(0.0, min(100.0, _raw_conf))
            
            payload = {
                'symbol': signal_data.get('symbol'),
                'timeframe': signal_data.get('timeframe'),
                'system_type': signal_data.get('system_type', 'spot'),
                'action_original': signal_data.get('action'),
                'action_normalized': normalized_action,
                'confidence': _capped_conf,
                'entry_price': float(signal_data.get('entry', 0)),
                'stop_loss': float(signal_data.get('stop_loss', 0)),
                'take_profit': float(signal_data.get('take_profit', 0)),
                'leverage': int(signal_data.get('leverage', 1)),
                'risk_reward': float(signal_data.get('risk_reward', 0)),
                'current_price': float(signal_data.get('current_price', 0)),
                'candle_timestamp': signal_data.get('candle_timestamp'),
                'indicators_snapshot': signal_data.get('indicators_snapshot', {}),
                'context': signal_data.get('context', {}),
                'was_executed': normalized_action != 'NO_OPERAR',
                'status': 'pending',  # pending | tp_hit | sl_hit | expired | missed_opportunity
                'created_at': datetime.utcnow().isoformat()
            }
            
            # ============ DEDUP CHECK ============
            # Verifica si ya existe una señal para el mismo (symbol, timeframe,
            # candle_timestamp, action_normalized, system_type). Si existe, no
            # inserta. Evita duplicados sin depender de UNIQUE constraint en BD.
            # 
            # Corrige el problema de "8 señales ADA/USDT 2h LONG idénticas en 35
            # min" causado por el warm-up paralelo de futuros que ejecutaba
            # register_signal múltiples veces por vela.
            try:
                if payload.get('candle_timestamp'):
                    existing = self._with_retry(
                        lambda: self.client.table('signals')
                                .select('id')
                                .eq('symbol', payload['symbol'])
                                .eq('timeframe', payload['timeframe'])
                                .eq('action_normalized', payload['action_normalized'])
                                .eq('system_type', payload['system_type'])
                                .eq('candle_timestamp', payload['candle_timestamp'])
                                .limit(1)
                                .execute()
                    )
                    if existing.data and len(existing.data) > 0:
                        # Ya existe → devolver el ID existente (comportamiento idempotente)
                        return existing.data[0].get('id')
            except Exception as _dedup_err:
                # Si la verificación de dedup falla por conectividad, seguimos
                # con el INSERT (se guardará; peor caso duplicado ocasional).
                logger.debug(f"dedup check falló, continuando con INSERT: {_dedup_err}")
            
            response = self._with_retry(
                lambda: self.client.table('signals').insert(payload).execute()
            )
            
            if response.data and len(response.data) > 0:
                signal_id = response.data[0].get('id')
                
                # Insertar estrategias asociadas
                strategies = signal_data.get('strategies', [])
                if strategies and signal_id:
                    self._insert_signal_indicators(signal_id, strategies, signal_data.get('indicators_snapshot', {}))
                
                # Rotación FIFO si es necesario
                self._check_rotation('signals')
                
                return signal_id
            return None
            
        except Exception as e:
            if self._is_connection_error(e):
                logger.warning(f"Supabase temporalmente inaccesible al insertar señal: {type(e).__name__}")
            else:
                logger.error(f"Error insertando señal: {e}")
            return None
    
    def _insert_signal_indicators(self, signal_id: str, strategies: List[str], indicators_snapshot: Dict):
        """Guarda las estrategias detectadas asociadas a la señal"""
        if not self.enabled:
            return
        
        try:
            rows = []
            for strategy in strategies:
                rows.append({
                    'signal_id': signal_id,
                    'strategy_name': strategy,
                    'indicator_values': indicators_snapshot,
                    'created_at': datetime.utcnow().isoformat()
                })
            
            if rows:
                self.client.table('signal_indicators').insert(rows).execute()
                self._check_rotation('signal_indicators')
        except Exception as e:
            logger.error(f"Error insertando indicadores de señal: {e}")
    
    # ========================================================================
    # ACTUALIZACIÓN DE RESULTADOS (TP/SL/EXPIRED)
    # ========================================================================
    
    def update_signal_result(self, signal_id: str, result: Dict) -> bool:
        """
        Actualiza el resultado de una señal cuando alcanza TP, SL o expira.
        
        result = {
            'status': 'tp_hit' | 'sl_hit' | 'expired' | 'missed_opportunity',
            'exit_price': 70180.0,
            'exit_timestamp': '2026-08-21T18:00:00',
            'pnl_pct': 2.3,
            'candles_to_result': 4,  # Cuántas velas tardó en resolverse
            'notes': ''
        }
        """
        if not self.enabled:
            return False
        
        try:
            # Update en la tabla signals
            update_signal = {
                'status': result.get('status'),
                'closed_at': datetime.utcnow().isoformat()
            }
            self.client.table('signals').update(update_signal).eq('id', signal_id).execute()
            
            # Insert en signal_results
            payload = {
                'signal_id': signal_id,
                'status': result.get('status'),
                'exit_price': float(result.get('exit_price', 0)),
                'exit_timestamp': result.get('exit_timestamp'),
                'pnl_pct': float(result.get('pnl_pct', 0)),
                'candles_to_result': int(result.get('candles_to_result', 0)),
                'notes': result.get('notes', ''),
                'created_at': datetime.utcnow().isoformat()
            }
            
            self.client.table('signal_results').insert(payload).execute()
            self._check_rotation('signal_results')
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando resultado de señal {signal_id}: {e}")
            return False
    
    # ========================================================================
    # OPORTUNIDADES PERDIDAS
    # ========================================================================
    
    def insert_missed_opportunity(self, data: Dict) -> Optional[str]:
        """
        Guarda una oportunidad perdida: señal NO_OPERAR/ESPERAR cuyo precio 
        se movió a favor >2% en las siguientes N velas.
        """
        if not self.enabled:
            return None
        
        try:
            payload = {
                'symbol': data.get('symbol'),
                'timeframe': data.get('timeframe'),
                'action_that_should_have_been': self.normalize_action(data.get('action_should', '')),
                'confidence_at_moment': float(data.get('confidence', 0)),
                'strategies_detected': data.get('strategies', []),
                'indicators_snapshot': data.get('indicators_snapshot', {}),
                'price_at_signal': float(data.get('price_at_signal', 0)),
                'max_favorable_price': float(data.get('max_favorable_price', 0)),
                'max_favorable_pct': float(data.get('max_favorable_pct', 0)),
                'candles_to_max': int(data.get('candles_to_max', 0)),
                'candle_timestamp': data.get('candle_timestamp'),
                'created_at': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('missed_opportunities').insert(payload).execute()
            self._check_rotation('missed_opportunities')
            
            if response.data:
                return response.data[0].get('id')
            return None
        except Exception as e:
            logger.error(f"Error insertando oportunidad perdida: {e}")
            return None
    
    # ========================================================================
    # CONSULTAS ESTADÍSTICAS
    # ========================================================================
    
    def get_pending_signals(self, hours_old_max: int = 168) -> List[Dict]:
        """
        Retorna las señales pendientes de evaluar (status='pending') 
        que no sean más antiguas de N horas (default 7 días).
        """
        if not self.enabled:
            return []
        
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=hours_old_max)).isoformat()
            response = (self.client.table('signals')
                        .select('*')
                        .eq('status', 'pending')
                        .gte('created_at', cutoff)
                        .execute())
            return response.data or []
        except Exception as e:
            logger.error(f"Error obteniendo señales pendientes: {e}")
            return []
    
    def get_strategy_stats(self, symbol: str = None, timeframe: str = None, 
                          action: str = None, strategy: str = None) -> List[Dict]:
        """
        Consulta las estadísticas específicas de estrategias.
        Cualquier filtro es opcional; si se omite, retorna agregado.
        """
        if not self.enabled:
            return []
        
        try:
            query = self.client.table('strategy_stats_specific').select('*')
            
            if symbol:
                query = query.eq('symbol', symbol)
            if timeframe:
                query = query.eq('timeframe', timeframe)
            if action:
                query = query.eq('action', self.normalize_action(action))
            if strategy:
                query = query.eq('strategy', strategy)
            
            response = query.order('win_rate', desc=True).limit(50).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error obteniendo stats: {e}")
            return []
    
    def get_general_stats(self, strategy: str = None) -> List[Dict]:
        """Consulta estadísticas generales de estrategias (agregado global)."""
        if not self.enabled:
            return []
        
        try:
            query = self.client.table('strategy_stats_general').select('*')
            if strategy:
                query = query.eq('strategy', strategy)
            response = query.order('expectancy', desc=True).limit(100).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error obteniendo stats generales: {e}")
            return []
    
    def get_recommendations(self, symbol: str, timeframe: str, action: str) -> Optional[Dict]:
        """
        Obtiene las recomendaciones cacheadas del ReviewTrader para 
        (par, temporalidad, acción).
        """
        if not self.enabled:
            return None
        
        normalized = self.normalize_action(action)
        
        def _op():
            response = (self.client.table('review_recommendations')
                        .select('*')
                        .eq('symbol', symbol)
                        .eq('timeframe', timeframe)
                        .eq('action', normalized)
                        .order('created_at', desc=True)
                        .limit(1)
                        .execute())
            if response.data:
                return response.data[0]
            return None
        
        try:
            return self._with_retry(_op)
        except Exception as e:
            # Si es error de conexión persistente, lo degradamos a warning
            # (no rompe la app, solo devolvemos None y la próxima llamada intentará de nuevo)
            if self._is_connection_error(e):
                logger.warning(f"Supabase temporalmente inaccesible: {type(e).__name__}")
            else:
                logger.error(f"Error obteniendo recomendaciones: {e}")
            return None
    
    def upsert_recommendation(self, data: Dict) -> bool:
        """Guarda o actualiza una recomendación pre-calculada del ReviewTrader"""
        if not self.enabled:
            return False
        
        try:
            payload = {
                'symbol': data.get('symbol'),
                'timeframe': data.get('timeframe'),
                'action': self.normalize_action(data.get('action', '')),
                'winning_strategies': data.get('winning_strategies', []),
                'losing_strategies': data.get('losing_strategies', []),
                'best_combinations': data.get('best_combinations', []),
                'win_rate': float(data.get('win_rate', 0)),
                'expectancy': float(data.get('expectancy', 0)),
                'sample_size': int(data.get('sample_size', 0)),
                'recommended_confidence_multiplier': float(data.get('multiplier', 1.0)),
                'recommended_leverage': int(data.get('leverage', 1)),
                'notes': data.get('notes', ''),
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Elimina la recomendación anterior (mismo par/TF/acción) e inserta la nueva
            self.client.table('review_recommendations').delete().eq(
                'symbol', payload['symbol']
            ).eq('timeframe', payload['timeframe']).eq('action', payload['action']).execute()
            
            self.client.table('review_recommendations').insert(payload).execute()
            self._check_rotation('review_recommendations')
            return True
        except Exception as e:
            logger.error(f"Error guardando recomendación: {e}")
            return False
    
    def upsert_strategy_stats(self, stats_list: List[Dict], general: bool = False) -> bool:
        """
        Actualiza estadísticas de estrategias en batch.
        general=True usa la tabla general; False usa la específica.
        """
        if not self.enabled or not stats_list:
            return False
        
        try:
            table = 'strategy_stats_general' if general else 'strategy_stats_specific'
            
            # Delete previos + insert nuevos (idempotente)
            self.client.table(table).delete().neq('id', 0).execute()  # Limpia todo
            
            batch_size = 100
            for i in range(0, len(stats_list), batch_size):
                batch = stats_list[i:i+batch_size]
                self.client.table(table).insert(batch).execute()
            
            self._check_rotation(table)
            return True
        except Exception as e:
            logger.error(f"Error actualizando stats {table}: {e}")
            return False
    
    def get_signals_for_stats(self, days_back: int = 90) -> List[Dict]:
        """
        Obtiene todas las señales con resultado (no pending) de los últimos N días
        para recalcular estadísticas.
        
        FIX: PostgREST limita a 1000 rows por request. Antes solo se leían las
        primeras 1000, dejando afuera señales resueltas → stats vacías. Ahora
        paginamos manualmente con .range() hasta traer todas.
        """
        if not self.enabled:
            return []
        
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            all_data = []
            offset = 0
            page_size = 1000
            max_pages = 50  # safety cap (50k signals máx)
            
            for _ in range(max_pages):
                response = (self.client.table('signals')
                            .select('*, signal_indicators(strategy_name)')
                            .neq('status', 'pending')
                            .gte('created_at', cutoff)
                            .order('created_at', desc=True)
                            .range(offset, offset + page_size - 1)
                            .execute())
                batch = response.data or []
                if not batch:
                    break
                all_data.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            
            return all_data
        except Exception as e:
            logger.error(f"Error obteniendo señales para stats: {e}")
            return []
    
    def get_missed_opportunities_by_context(self, symbol: str = None, 
                                            timeframe: str = None) -> List[Dict]:
        """Retorna oportunidades perdidas filtradas por contexto"""
        if not self.enabled:
            return []
        
        try:
            query = self.client.table('missed_opportunities').select('*')
            if symbol:
                query = query.eq('symbol', symbol)
            if timeframe:
                query = query.eq('timeframe', timeframe)
            response = query.order('created_at', desc=True).limit(200).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error obteniendo missed opportunities: {e}")
            return []
    
    # ========================================================================
    # OPTIMIZACIONES DE VOLUMEN (FASE 2.5)
    # ========================================================================
    
    def delete_old_signals_by_tf(self, timeframe: str, days_retention: int) -> int:
        """
        Borra señales de un timeframe específico que sean más antiguas que N días.
        Se usa para el TTL diferenciado por temporalidad.
        
        IMPORTANTE: NO borra las señales con status='tp_hit' (son valiosas).
        
        Retorna: número de señales borradas.
        """
        if not self.enabled:
            return 0
        
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
            
            # Obtener IDs de señales antiguas que NO sean tp_hit
            response = (self.client.table('signals')
                        .select('id')
                        .eq('timeframe', timeframe)
                        .neq('status', 'tp_hit')
                        .lt('created_at', cutoff)
                        .execute())
            
            if not response.data:
                return 0
            
            ids_to_delete = [s['id'] for s in response.data]
            
            # Borrar en batches de 100
            deleted = 0
            for i in range(0, len(ids_to_delete), 100):
                batch = ids_to_delete[i:i+100]
                self.client.table('signals').delete().in_('id', batch).execute()
                deleted += len(batch)
            
            logger.info(f"TTL {timeframe}: eliminadas {deleted} señales con más de {days_retention} días")
            return deleted
            
        except Exception as e:
            logger.error(f"Error en delete_old_signals_by_tf({timeframe}): {e}")
            return 0
    
    def apply_ttl_cleanup(self) -> Dict:
        """
        Aplica el TTL (time-to-live) diferenciado por temporalidad.
        Cada TF tiene su propio tiempo de retención.
        """
        ttl_config = {
            '5m': 7,      # 7 días
            '15m': 14,    # 14 días
            '30m': 21,    # 21 días
            '1h': 30,     # 30 días
            '2h': 45,
            '4h': 60,
            '12h': 90,
            '1D': 180,
            '1W': 365
        }
        
        results = {}
        for tf, days in ttl_config.items():
            deleted = self.delete_old_signals_by_tf(tf, days)
            results[tf] = deleted
        
        total = sum(results.values())
        if total > 0:
            logger.info(f"TTL cleanup total: {total} señales eliminadas")
        
        return results
    
    def delete_low_sample_stats(self, min_sample: int = 5) -> int:
        """
        Borra filas de strategy_stats_specific con menos de N muestras.
        Estas filas son ruido estadístico y ocupan espacio innecesario.
        La info se agrega igual en strategy_stats_general.
        
        Retorna: número de filas borradas.
        """
        if not self.enabled:
            return 0
        
        try:
            response = (self.client.table('strategy_stats_specific')
                        .select('id')
                        .lt('total_signals', min_sample)
                        .execute())
            
            if not response.data:
                return 0
            
            ids_to_delete = [r['id'] for r in response.data]
            
            deleted = 0
            for i in range(0, len(ids_to_delete), 100):
                batch = ids_to_delete[i:i+100]
                self.client.table('strategy_stats_specific').delete().in_('id', batch).execute()
                deleted += len(batch)
            
            logger.info(f"Compresión de stats: {deleted} filas con <{min_sample} muestras eliminadas")
            return deleted
        except Exception as e:
            logger.error(f"Error en delete_low_sample_stats: {e}")
            return 0
    
    # ========================================================================
    # LOGS DEL REVIEWTRADER (Fase A)
    # ========================================================================
    
    def insert_review_log(self, log_data: Dict) -> Optional[str]:
        """
        Inserta una entrada de log del ReviewTrader.
        Se llama cada vez que se ejecuta run_full_review().
        
        log_data esperado:
        {
            'run_started_at': str ISO,
            'run_finished_at': str ISO,
            'duration_seconds': float,
            'trigger_source': 'scheduler' | 'manual',
            'signals_evaluated': int,
            'tp_hits': int, 'sl_hits': int, 'expired': int, 'still_pending': int,
            'missed_opportunities_found': int,
            'stats_specific_updated': int, 'stats_general_updated': int,
            'recommendations_updated': int,
            'ttl_deleted': int, 'low_sample_deleted': int,
            'storage_stats': dict,
            'errors': list, 'warnings': list, 'notes': str,
            'status': 'success' | 'partial' | 'failed'
        }
        """
        if not self.enabled:
            return None
        
        try:
            payload = {
                'run_started_at': log_data.get('run_started_at'),
                'run_finished_at': log_data.get('run_finished_at'),
                'duration_seconds': float(log_data.get('duration_seconds', 0)),
                'trigger_source': log_data.get('trigger_source', 'scheduler'),
                'signals_evaluated': int(log_data.get('signals_evaluated', 0)),
                'tp_hits': int(log_data.get('tp_hits', 0)),
                'sl_hits': int(log_data.get('sl_hits', 0)),
                'expired': int(log_data.get('expired', 0)),
                'still_pending': int(log_data.get('still_pending', 0)),
                'missed_opportunities_found': int(log_data.get('missed_opportunities_found', 0)),
                'stats_specific_updated': int(log_data.get('stats_specific_updated', 0)),
                'stats_general_updated': int(log_data.get('stats_general_updated', 0)),
                'recommendations_updated': int(log_data.get('recommendations_updated', 0)),
                'ttl_deleted': int(log_data.get('ttl_deleted', 0)),
                'low_sample_deleted': int(log_data.get('low_sample_deleted', 0)),
                'storage_stats': log_data.get('storage_stats', {}),
                'errors': log_data.get('errors', []),
                'warnings': log_data.get('warnings', []),
                'notes': log_data.get('notes', ''),
                'status': log_data.get('status', 'success'),
                'created_at': datetime.utcnow().isoformat()
            }
            
            response = self.client.table('review_logs').insert(payload).execute()
            if response.data:
                return response.data[0].get('id')
            return None
        except Exception as e:
            logger.error(f"Error insertando review_log: {e}")
            return None
    
    def get_recent_review_logs(self, limit: int = 50) -> List[Dict]:
        """Retorna los últimos N logs del ReviewTrader (ordenados por fecha DESC)"""
        if not self.enabled:
            return []
        
        # v22.6: envolver con _with_retry para tolerar EAGAIN transitorios
        # que aparecían cuando el frontend disparaba 8 requests en paralelo a
        # Supabase y saturaba el pool HTTP/2.
        try:
            def _op():
                return (self.client.table('review_logs')
                        .select('*')
                        .order('run_started_at', desc=True)
                        .limit(limit)
                        .execute())
            response = self._with_retry(_op)
            return response.data or []
        except Exception as e:
            logger.error(f"Error obteniendo review_logs: {e}")
            return []
    
    def get_last_review_log(self) -> Optional[Dict]:
        """Retorna el último log del ReviewTrader (el más reciente)"""
        logs = self.get_recent_review_logs(limit=1)
        return logs[0] if logs else None
    
    # ========================================================================
    
    def get_storage_stats(self) -> Dict:
        """
        Retorna conteo de filas por cada tabla.
        Útil para monitorear el uso de almacenamiento.
        """
        if not self.enabled:
            return {}
        
        tables = ['signals', 'signal_indicators', 'signal_results',
                  'strategy_stats_specific', 'strategy_stats_general',
                  'missed_opportunities', 'review_recommendations',
                  'review_logs']
        
        stats = {}
        for table in tables:
            try:
                response = self.client.table(table).select('id', count='exact').limit(1).execute()
                stats[table] = response.count or 0
            except Exception as e:
                stats[table] = -1  # Error
        
        return stats
    
    # ========================================================================
    # ROTACIÓN FIFO
    # ========================================================================
    
    def _check_rotation(self, table_name: str):
        """
        Verifica si la tabla superó el límite y borra las filas más antiguas.
        
        OPTIMIZACIÓN v15: probabilístico (10% de las llamadas) para reducir carga.
        Antes se ejecutaba en CADA insert (15+ requests por warm-up). Ahora se
        ejecuta en promedio 1 de cada 10 inserts, lo que es suficiente porque
        el límite tiene margen (LIMITS son valores grandes ~20000).
        """
        if not self.enabled:
            return
        
        # Chequeo probabilístico: solo 10% de las veces
        import random
        if random.random() > 0.1:
            return
        
        try:
            limit = LIMITS.get(table_name, 10000)
            
            # Contar filas actuales
            count_response = self.client.table(table_name).select('id', count='exact').limit(1).execute()
            current_count = count_response.count or 0
            
            if current_count > limit:
                # Excede el límite: borrar el 5% más antiguo
                to_delete = int(limit * 0.05)
                
                if table_name == 'signals':
                    # Preservar señales con TP exitoso (son valiosas)
                    old_signals = (self.client.table('signals')
                                   .select('id')
                                   .neq('status', 'tp_hit')
                                   .order('created_at')
                                   .limit(to_delete)
                                   .execute())
                    if old_signals.data:
                        ids_to_delete = [s['id'] for s in old_signals.data]
                        self.client.table('signals').delete().in_('id', ids_to_delete).execute()
                        logger.info(f"Rotación FIFO en {table_name}: eliminadas {len(ids_to_delete)} filas")
                else:
                    # Para otras tablas: borrar simplemente las más antiguas
                    old_rows = (self.client.table(table_name)
                                .select('id')
                                .order('created_at')
                                .limit(to_delete)
                                .execute())
                    if old_rows.data:
                        ids_to_delete = [r['id'] for r in old_rows.data]
                        self.client.table(table_name).delete().in_('id', ids_to_delete).execute()
                        logger.info(f"Rotación FIFO en {table_name}: eliminadas {len(ids_to_delete)} filas")
        except Exception as e:
            if self._is_connection_error(e):
                # Sistema saturado — no ensucies logs, la rotación FIFO no es crítica
                logger.debug(f"Rotación FIFO {table_name}: sistema temporalmente saturado")
            else:
                logger.error(f"Error en rotación FIFO de {table_name}: {e}")
    
    # ========================================================================
    # HEALTH CHECK
    # ========================================================================
    
    def health_check(self) -> Dict:
        """Diagnóstico del cliente Supabase"""
        result = {
            'enabled': self.enabled,
            'url_configured': bool(self.url),
            'key_configured': bool(self.key),
            'connection_ok': False,
            'tables_ok': {}
        }
        
        if not self.enabled:
            return result
        
        # Verificar cada tabla
        tables = ['signals', 'signal_indicators', 'signal_results', 
                  'strategy_stats_specific', 'strategy_stats_general',
                  'missed_opportunities', 'review_recommendations']
        
        try:
            for table in tables:
                try:
                    self.client.table(table).select('id').limit(1).execute()
                    result['tables_ok'][table] = True
                except Exception as e:
                    result['tables_ok'][table] = False
            
            result['connection_ok'] = all(result['tables_ok'].values())
        except Exception as e:
            logger.error(f"Health check falló: {e}")
        
        return result


# ============================================================================
# INSTANCIA GLOBAL (SINGLETON)
# ============================================================================

# El resto del sistema importa esta instancia:
# from supabase_client import supabase_db
supabase_db = SupabaseClient()

if supabase_db.enabled:
    health = supabase_db.health_check()
    print(f"✅ Tablas verificadas: {sum(1 for v in health['tables_ok'].values() if v)}/{len(health['tables_ok'])}")
    for table, ok in health['tables_ok'].items():
        status = "✅" if ok else "❌"
        print(f"   {status} {table}")



# ============================================================================
# INSTRUCCIONES PARA AGREGAR A supabase_client.py
# ============================================================================
#
# Paso 1: Nuevas funciones dentro de la clase SupabaseClient
# (o como funciones sueltas si tu supabase_client no usa clase)
#
# Busca el final de supabase_client.py (después de todas las funciones
# existentes) y AGREGA estas funciones:

    # ========================================================================
    # USER PORTFOLIO
    # ========================================================================

    def get_user_portfolio(self, user_name):
        """Obtiene el portafolio de un usuario desde Supabase."""
        try:
            result = self.supabase.table('user_portfolios')\
                .select('*')\
                .eq('user_name', user_name)\
                .execute()
            if result.data and len(result.data) > 0:
                row = result.data[0]
                return {
                    'BTC': float(row.get('btc_amount', 0)),
                    'PAXG': float(row.get('paxg_amount', 0)),
                    'USDT': float(row.get('usdt_amount', 0)),
                    'btc_price_at_update': float(row.get('btc_price_at_update', 0)),
                    'paxg_price_at_update': float(row.get('paxg_price_at_update', 0)),
                    'updated_at': row.get('updated_at', '')
                }
            return {'BTC': 0, 'PAXG': 0, 'USDT': 0}
        except Exception as e:
            print(f"❌ Error get_user_portfolio: {e}")
            return {'BTC': 0, 'PAXG': 0, 'USDT': 0}

    def upsert_user_portfolio(self, portfolio_data):
        """Guarda o actualiza el portafolio de un usuario."""
        try:
            # Verificar si existe
            existing = self.supabase.table('user_portfolios')\
                .select('id')\
                .eq('user_name', portfolio_data['user_name'])\
                .execute()

            if existing.data and len(existing.data) > 0:
                # Update
                self.supabase.table('user_portfolios')\
                    .update(portfolio_data)\
                    .eq('user_name', portfolio_data['user_name'])\
                    .execute()
            else:
                # Insert
                self.supabase.table('user_portfolios')\
                    .insert(portfolio_data)\
                    .execute()
            return True
        except Exception as e:
            print(f"❌ Error upsert_user_portfolio: {e}")
            return False

    # ========================================================================
    # USER TRADES (operaciones spot personales)
    # ========================================================================

    def insert_user_trade(self, trade_data):
        """Guarda una operación spot del usuario."""
        try:
            result = self.supabase.table('user_trades')\
                .insert(trade_data)\
                .execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            print(f"❌ Error insert_user_trade: {e}")
            return {}

    def get_user_trades(self, user_name, status=None, limit=100):
        """Obtiene operaciones del usuario."""
        try:
            query = self.supabase.table('user_trades')\
                .select('*')\
                .eq('user_name', user_name)\
                .order('created_at', desc=True)\
                .limit(limit)
            if status:
                query = query.eq('status', status)
            result = query.execute()
            return result.data or []
        except Exception as e:
            print(f"❌ Error get_user_trades: {e}")
            return []

    def update_user_trade(self, trade_id, updates):
        """Actualiza una operación (ej: cerrarla con PnL)."""
        try:
            self.supabase.table('user_trades')\
                .update(updates)\
                .eq('id', trade_id)\
                .execute()
            return True
        except Exception as e:
            print(f"❌ Error update_user_trade: {e}")
            return False

    def get_user_trade_stats(self, user_name):
        """Calcula estadísticas personales del usuario."""
        try:
            trades = self.get_user_trades(user_name, limit=1000)

            if not trades:
                return {
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl_usd': 0,
                    'total_pnl_pct': 0,
                    'avg_trade_usd': 0,
                    'best_trade': None,
                    'worst_trade': None,
                    'open_trades': 0,
                    'closed_trades': 0
                }

            closed = [t for t in trades if t.get('status') in ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_TIME', 'CLOSED_MANUAL')]
            wins = [t for t in closed if float(t.get('pnl_usd', 0)) > 0]
            losses = [t for t in closed if float(t.get('pnl_usd', 0)) <= 0]

            total_pnl = sum(float(t.get('pnl_usd', 0)) for t in closed)

            best = max(closed, key=lambda x: float(x.get('pnl_usd', 0))) if closed else None
            worst = min(closed, key=lambda x: float(x.get('pnl_usd', 0))) if closed else None

            return {
                'total_trades': len(trades),
                'win_rate': round(len(wins) / len(closed) * 100, 2) if closed else 0,
                'total_pnl_usd': round(total_pnl, 2),
                'total_pnl_pct': round(sum(float(t.get('pnl_pct', 0)) for t in closed), 2),
                'avg_trade_usd': round(sum(float(t.get('amount_usd', 0)) for t in trades) / len(trades), 2) if trades else 0,
                'best_trade': {
                    'action': best.get('action'),
                    'pnl_usd': round(float(best.get('pnl_usd', 0)), 2),
                    'date': best.get('closed_at')
                } if best else None,
                'worst_trade': {
                    'action': worst.get('action'),
                    'pnl_usd': round(float(worst.get('pnl_usd', 0)), 2),
                    'date': worst.get('closed_at')
                } if worst else None,
                'open_trades': len([t for t in trades if t.get('status') == 'OPEN']),
                'closed_trades': len(closed)
            }
        except Exception as e:
            print(f"❌ Error get_user_trade_stats: {e}")
            return {}


# ============================================================================
# Paso 2: SQL para crear las tablas en Supabase
# ============================================================================
# Ejecuta esto en el SQL Editor de Supabase:

-- Tabla de portafolios por usuario
CREATE TABLE IF NOT EXISTS user_portfolios (
    id SERIAL PRIMARY KEY,
    user_name TEXT NOT NULL UNIQUE,
    btc_amount DECIMAL(20,8) DEFAULT 0,
    paxg_amount DECIMAL(20,8) DEFAULT 0,
    usdt_amount DECIMAL(20,2) DEFAULT 0,
    btc_price_at_update DECIMAL(20,2) DEFAULT 0,
    paxg_price_at_update DECIMAL(20,2) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Tabla de operaciones spot personales
CREATE TABLE IF NOT EXISTS user_trades (
    id SERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    symbol TEXT,
    action TEXT,  -- BUY_BTC, BUY_PAXG, SELL_BTC, SELL_PAXG, SWAP_PAXG_TO_BTC, SWAP_BTC_TO_PAXG, HOLD
    entry_price DECIMAL(20,8) DEFAULT 0,
    exit_price DECIMAL(20,8) DEFAULT 0,
    amount_crypto DECIMAL(20,8) DEFAULT 0,
    amount_usd DECIMAL(20,2) DEFAULT 0,
    source_asset TEXT,
    target_asset TEXT,
    pnl_usd DECIMAL(20,2) DEFAULT 0,
    pnl_pct DECIMAL(10,4) DEFAULT 0,
    status TEXT DEFAULT 'OPEN',  -- OPEN, CLOSED_WIN, CLOSED_LOSS, CLOSED_TIME, CLOSED_MANUAL
    system_signal_action TEXT,
    tgp_recommendation TEXT,
    timeframe TEXT,
    opened_at TIMESTAMP,
    closed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_user_trades_user ON user_trades(user_name);
CREATE INDEX IF NOT EXISTS idx_user_trades_status ON user_trades(status);
CREATE INDEX IF NOT EXISTS idx_user_portfolios_user ON user_portfolios(user_name);
else:
    print("⚠️ SupabaseClient deshabilitado - el sistema principal seguirá funcionando sin ReviewTrader")

print("=" * 60)
