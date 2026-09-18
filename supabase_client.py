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
import time
import threading
import uuid
import requests
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

# HOTFIX 9.6.1 — credencial backend explícita para tablas protegidas por RLS.
# El servidor prefiere la secret/service-role; SUPABASE_KEY queda sólo como
# fallback de compatibilidad. Nunca se expone esta selección al navegador.
SUPABASE_URL_SOURCE = (
    'CENTRAL_SUPABASE_URL'
    if os.environ.get('CENTRAL_SUPABASE_URL')
    else 'SUPABASE_URL'
)
SUPABASE_URL = (
    os.environ.get('CENTRAL_SUPABASE_URL')
    or os.environ.get('SUPABASE_URL', '')
)

if os.environ.get('CENTRAL_SUPABASE_SERVICE_KEY'):
    SUPABASE_KEY_SOURCE = 'CENTRAL_SUPABASE_SERVICE_KEY'
    SUPABASE_KEY = os.environ.get('CENTRAL_SUPABASE_SERVICE_KEY', '')
elif os.environ.get('SUPABASE_SERVICE_ROLE_KEY'):
    SUPABASE_KEY_SOURCE = 'SUPABASE_SERVICE_ROLE_KEY'
    SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
else:
    SUPABASE_KEY_SOURCE = 'SUPABASE_KEY'
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# RC8.3 — FREE PLAN LOCKDOWN
# Supabase Free includes 5 GB/month uncached egress. The hard objective is to
# keep database traffic far below that ceiling. These guards are deliberately
# conservative and can be overridden in Render without another deploy.
FREE_PLAN_LOCKDOWN = str(os.environ.get('FREE_PLAN_LOCKDOWN', '1')).strip().lower() not in {'0','false','no','off'}
MAIN_SUPABASE_DAILY_BUDGET_MB = max(12.0, float(os.environ.get('MAIN_SUPABASE_DAILY_BUDGET_MB', '30') or 30))
# RC9.2: FREE_PLAN_LOCKDOWN is a hard cap as well as a default. This protects
# old Render env values (for example 60 MB/day) from silently restoring the
# previous egress envelope after this deploy. Research has its own much smaller
# cap; together they leave large headroom below Supabase Free monthly egress.
if FREE_PLAN_LOCKDOWN:
    MAIN_SUPABASE_DAILY_BUDGET_MB = min(MAIN_SUPABASE_DAILY_BUDGET_MB, 30.0)
MAIN_SUPABASE_DIAGNOSTIC_GUARD = max(0.10, min(0.95, float(os.environ.get('MAIN_SUPABASE_DIAGNOSTIC_GUARD', '0.70') or 0.70)))
MAIN_SUPABASE_OPTIONAL_GUARD = max(MAIN_SUPABASE_DIAGNOSTIC_GUARD, min(0.98, float(os.environ.get('MAIN_SUPABASE_OPTIONAL_GUARD', '0.85') or 0.85)))
MAIN_SUPABASE_IMPORTANT_GUARD = max(MAIN_SUPABASE_OPTIONAL_GUARD, min(0.995, float(os.environ.get('MAIN_SUPABASE_IMPORTANT_GUARD', '0.95') or 0.95)))

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
    'signal_indicators': 40000,          # RC8.2: sólo relación señal↔estrategia; sin snapshot JSON duplicado
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
        self._transient_lock = threading.Lock()
        self._transient_failures = 0
        self._read_circuit_until = 0.0
        self._preferences_cache = {}
        self._recommendations_cache = {}
        self._review_logs_cache = {}
        self._storage_stats_cache = {'ts': 0.0, 'value': {}}
        self._free_plan_lock = threading.Lock()
        self._free_plan_day = datetime.utcnow().date().isoformat()
        self._free_plan_response_bytes = 0
        self._free_plan_requests = 0
        self._rest_session = requests.Session()
        self._rotation_lock = threading.Lock()
        self._rotation_last_check = {}
        # FREE-PLAN: las estadísticas de 90 días se hidratan una vez por proceso
        # y después sólo incorporan nuevas señales cerradas. Evita descargar
        # repetidamente decenas de MB de JSON histórico cada cuatro horas.
        self._stats_signals_cache = []
        self._stats_closed_watermark = ''
        self._stats_cache_days = None
        
        if not self.url or not self.key:
            print("⚠️ SUPABASE no configurado (URL o KEY vacíos)")
            print("   El sistema funcionará SIN ReviewTrader hasta que se configuren las credenciales")
            return
        
        try:
            self._create_client()
            self.enabled = True
            print(f"✅ SUPABASE conectado a: {self.url[:40]}...")
            print(
                "🔐 SUPABASE backend: "
                f"url={SUPABASE_URL_SOURCE} · key={SUPABASE_KEY_SOURCE}"
            )
            if SUPABASE_KEY_SOURCE == 'SUPABASE_KEY':
                print(
                    "⚠️ SUPABASE backend usa SUPABASE_KEY de compatibilidad. "
                    "Si esa clave es anon/public, las tablas RLS internas "
                    "(por ejemplo q6_job_runs) pueden rechazar escrituras."
                )
            if FREE_PLAN_LOCKDOWN:
                print(
                    "🛡️ FREE PLAN LOCKDOWN activo · "
                    f"presupuesto local Main {MAIN_SUPABASE_DAILY_BUDGET_MB:.0f} MB/día · "
                    "diagnóstico y lecturas opcionales se degradan antes que trading crítico"
                )
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
            'JSON could not be generated',
            'Connection timed out',
            'Error code 521',
            'code 521',
            'HTTP 521',
            'Error code 522',
            'code 522',
            'HTTP 522',
            'PGRST002',
            'schema cache',
            'SSLV3_ALERT_BAD_RECORD_MAC',
            'bad record mac',
            '<!DOCTYPE html>',
            'Cloudflare',
            '57014',
            'statement timeout',
            'canceling statement',
        )
        return any(m in msg for m in markers)
    
    def _mark_transient_failure(self):
        with self._transient_lock:
            self._transient_failures += 1
            if self._transient_failures >= 2:
                self._read_circuit_until = time.monotonic() + 60.0

    def _mark_transport_success(self):
        with self._transient_lock:
            self._transient_failures = 0
            self._read_circuit_until = 0.0

    def read_circuit_open(self) -> bool:
        with self._transient_lock:
            return time.monotonic() < self._read_circuit_until

    @staticmethod
    def _is_origin_unavailable(exc: Exception) -> bool:
        msg = str(exc)
        markers = ('PGRST002','schema cache','JSON could not be generated','Error code 521','code 521','HTTP 521','Error code 522','code 522','HTTP 522','Cloudflare','<!DOCTYPE html>')
        return any(m in msg for m in markers)

    def _free_plan_roll_day(self):
        day = datetime.utcnow().date().isoformat()
        with self._free_plan_lock:
            if day != self._free_plan_day:
                self._free_plan_day = day
                self._free_plan_response_bytes = 0
                self._free_plan_requests = 0

    @staticmethod
    def _estimate_json_bytes(value) -> int:
        try:
            return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8'))
        except Exception:
            return 0

    def _track_response_egress(self, result) -> None:
        if not FREE_PLAN_LOCKDOWN:
            return
        try:
            data = getattr(result, 'data', None)
            size = self._estimate_json_bytes(data)
        except Exception:
            size = 0
        self._free_plan_roll_day()
        with self._free_plan_lock:
            self._free_plan_response_bytes += max(0, int(size or 0))
            self._free_plan_requests += 1

    def free_plan_status(self) -> Dict[str, Any]:
        self._free_plan_roll_day()
        with self._free_plan_lock:
            used = int(self._free_plan_response_bytes)
            calls = int(self._free_plan_requests)
            day = str(self._free_plan_day)
        budget = int(MAIN_SUPABASE_DAILY_BUDGET_MB * 1024 * 1024)
        ratio = (used / budget) if budget > 0 else 0.0
        return {
            'enabled': bool(FREE_PLAN_LOCKDOWN),
            'day': day,
            'estimated_response_mb': round(used / 1024 / 1024, 3),
            'daily_budget_mb': round(MAIN_SUPABASE_DAILY_BUDGET_MB, 1),
            'ratio': round(ratio, 4),
            'tracked_requests': calls,
            # This is application telemetry, not Supabase billing telemetry.
            'billing_authoritative': False,
        }

    def free_plan_allows(self, priority: str = 'optional') -> bool:
        if not FREE_PLAN_LOCKDOWN:
            return True
        ratio = float(self.free_plan_status().get('ratio') or 0.0)
        level = str(priority or 'optional').lower()
        if level == 'critical':
            return True
        if level == 'important':
            return ratio < MAIN_SUPABASE_IMPORTANT_GUARD
        if level == 'diagnostic':
            return ratio < MAIN_SUPABASE_DIAGNOSTIC_GUARD
        return ratio < MAIN_SUPABASE_OPTIONAL_GUARD

    def _with_retry(self, operation, *args, **kwargs):
        """Execute once + one bounded retry for transient transport failures.

        RC8 recognizes Cloudflare/Supabase 520/522 HTML errors as transport
        failures. Repeated failures open a short *read* circuit used by the
        high-frequency optional readers, preventing an outage from becoming a
        request storm. Writes are never silently skipped by this helper.
        """
        try:
            result = operation(*args, **kwargs)
            self._mark_transport_success()
            self._track_response_egress(result)
            return result
        except Exception as e:
            if not self._is_connection_error(e):
                raise
            self._mark_transient_failure()
            # 521/522/PGRST002 are provider/origin failures. Reconnecting the
            # local client and immediately retrying only doubles pressure.
            if self._is_origin_unavailable(e):
                raise
            logger.debug(f"Error de conexión Supabase transitorio: {e}. Reconectando...")
            if not self._reconnect():
                logger.warning(f"Error de conexión Supabase y no se pudo reconectar: {e}")
                raise
            time.sleep(0.35)
            try:
                result = operation(*args, **kwargs)
                self._mark_transport_success()
                self._track_response_egress(result)
                return result
            except Exception as e2:
                if self._is_connection_error(e2):
                    self._mark_transient_failure()
                logger.warning(f"Error de conexión Supabase persistió tras retry: {e2}")
                raise

    def _rest_headers(self, prefer: str = "return=minimal") -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": prefer,
        }
        if str(self.key or "").count(".") == 2:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def _rest_minimal(self, method: str, table: str, *, payload=None,
                      params=None, timeout=(1.5, 2.5), prefer="return=minimal"):
        """Write through PostgREST without echoing large JSON rows."""
        if not self.enabled:
            return None
        if self.read_circuit_open():
            raise RuntimeError("SUPABASE_CIRCUIT_OPEN")
        url=f"{self.url.rstrip('/')}/rest/v1/{table}"
        try:
            r=self._rest_session.request(
                method.upper(), url, params=params or {}, json=payload,
                headers=self._rest_headers(prefer), timeout=timeout,
            )
            if r.status_code >= 400:
                body=(r.text or "")[:500]
                err=requests.HTTPError(
                    f"Supabase HTTP {r.status_code}: {body}",
                    response=r,
                )
                if self._is_connection_error(err) or r.status_code in {500,502,503,504,520,521,522,523,524}:
                    self._mark_transient_failure()
                raise err
            self._mark_transport_success()
            return r
        except (requests.RequestException, RuntimeError) as exc:
            if self._is_connection_error(exc) or "SUPABASE_CIRCUIT_OPEN" in str(exc):
                self._mark_transient_failure()
            raise

    @staticmethod
    def _deterministic_signal_id(payload: Dict[str, Any]) -> str:
        parts=(
            str(payload.get("symbol") or ""),
            str(payload.get("timeframe") or ""),
            str(payload.get("system_type") or ""),
            str(payload.get("action_normalized") or ""),
            str(payload.get("candle_timestamp") or ""),
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "smartradingreview|" + "|".join(parts)))

    def _schedule_rotation(self, table_name: str) -> None:
        def worker():
            try:
                self._check_rotation(table_name)
            except Exception:
                pass
        threading.Thread(
            target=worker,
            daemon=True,
            name=f"supabase-rotation-{table_name}",
        ).start()

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
        futures_symbols = ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT', 'LINK-USDT', 'BNB-USDT']
        
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
            
            # RC8 FREE-PLAN — una sola escritura mínima.
            #
            # La BD ya tiene UNIQUE por mercado×TF×vela×acción. Hacer un SELECT
            # previo duplicaba requests y egress. Generamos un UUID determinista,
            # pedimos return=minimal y sólo consultamos el ID canónico si la BD
            # informa que la fila ya existía.
            signal_id = self._deterministic_signal_id(payload)
            payload['id'] = signal_id

            try:
                self._rest_minimal(
                    'POST',
                    'signals',
                    payload=payload,
                    timeout=(1.25, 2.25),
                    prefer='return=minimal',
                )
            except requests.HTTPError as write_error:
                status = int(getattr(getattr(write_error, 'response', None), 'status_code', 0) or 0)
                msg = str(write_error).lower()
                if status == 409 or 'duplicate key' in msg or '23505' in msg or 'unique constraint' in msg:
                    # Legacy rows may have a random UUID. Recover only the tiny ID.
                    try:
                        existing = (
                            self.client.table('signals')
                            .select('id')
                            .eq('symbol', payload['symbol'])
                            .eq('timeframe', payload['timeframe'])
                            .eq('action_normalized', payload['action_normalized'])
                            .eq('system_type', payload['system_type'])
                            .eq('candle_timestamp', payload['candle_timestamp'])
                            .limit(1)
                            .execute()
                        )
                        if existing.data:
                            signal_id = existing.data[0].get('id') or signal_id
                        else:
                            return None
                    except Exception:
                        return None
                else:
                    raise

            # La geometría/estrategias no deben retrasar la respuesta interactiva.
            strategies = signal_data.get('strategies', [])
            if strategies and signal_id:
                snapshot = signal_data.get('indicators_snapshot', {})
                threading.Thread(
                    target=self._insert_signal_indicators,
                    args=(signal_id, strategies, snapshot),
                    daemon=True,
                    name='signal-indicators-write',
                ).start()

            self._schedule_rotation('signals')
            return signal_id

        except Exception as e:
            # RC8: the database also enforces one signal per market×cell×closed
            # candle×direction. If two workers race, the loser receives a UNIQUE
            # violation; recover the canonical id instead of creating noise or
            # treating the idempotent race as an application error.
            msg = str(e).lower()
            if payload.get('candle_timestamp') and ('duplicate key' in msg or '23505' in msg or 'unique constraint' in msg):
                try:
                    existing = self.client.table('signals').select('id').eq(
                        'symbol', payload['symbol']
                    ).eq('timeframe', payload['timeframe']).eq(
                        'action_normalized', payload['action_normalized']
                    ).eq('system_type', payload['system_type']).eq(
                        'candle_timestamp', payload['candle_timestamp']
                    ).limit(1).execute()
                    if existing.data:
                        return existing.data[0].get('id')
                except Exception:
                    pass
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
                    # RC8.2: the compact indicator snapshot already lives once
                    # on signals.indicators_snapshot. Repeating the same JSON for
                    # every strategy multiplied storage/egress without adding
                    # learning information. This table is only the N:M link.
                    'indicator_values': None,
                    'created_at': datetime.utcnow().isoformat()
                })
            
            if rows:
                self._rest_minimal(
                    'POST',
                    'signal_indicators',
                    payload=rows,
                    timeout=(1.25, 2.5),
                    prefer='return=minimal',
                )
                self._schedule_rotation('signal_indicators')
        except Exception as e:
            if self._is_connection_error(e):
                logger.debug("Indicadores de señal diferidos: Supabase temporalmente no disponible")
            else:
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
            # Q6-B: persist the result FIRST. A failed result write must leave
            # the source pending so the next worker can retry safely.
            # Insert en signal_results
            payload = {
                'signal_id':
                    signal_id,

                'status':
                    result.get(
                        'status'
                    ),

                'exit_price':
                    float(
                        result.get(
                            'exit_price',
                            0
                        )
                        or 0
                    ),

                'exit_timestamp':
                    result.get(
                        'exit_timestamp'
                    ),

                'pnl_pct':
                    float(
                        result.get(
                            'pnl_pct',
                            0
                        )
                        or 0
                    ),

                'candles_to_result':
                    int(
                        result.get(
                            'candles_to_result',
                            0
                        )
                        or 0
                    ),

                # ======================================================
                # FASE 7D.1 — MFE / MAE
                # ======================================================

                'mfe_price':
                    float(
                        result.get(
                            'mfe_price',
                            0
                        )
                        or 0
                    ),

                'mae_price':
                    float(
                        result.get(
                            'mae_price',
                            0
                        )
                        or 0
                    ),

                'mfe_pct':
                    float(
                        result.get(
                            'mfe_pct',
                            0
                        )
                        or 0
                    ),

                'mae_pct':
                    float(
                        result.get(
                            'mae_pct',
                            0
                        )
                        or 0
                    ),

                'mfe_r':
                    float(
                        result.get(
                            'mfe_r',
                            0
                        )
                        or 0
                    ),

                'mae_r':
                    float(
                        result.get(
                            'mae_r',
                            0
                        )
                        or 0
                    ),

                'candles_to_mfe':
                    int(
                        result.get(
                            'candles_to_mfe',
                            0
                        )
                        or 0
                    ),

                'candles_to_mae':
                    int(
                        result.get(
                            'candles_to_mae',
                            0
                        )
                        or 0
                    ),

                # ======================================================
                # COMMIT 2 — EXECUTION FORENSICS V2
                # ======================================================
                'execution_forensics':
                    (
                        result.get(
                            'execution_forensics',
                            {}
                        )
                        if isinstance(
                            result.get(
                                'execution_forensics',
                                {}
                            ),
                            dict
                        )
                        else {}
                    ),

                'notes':
                    result.get(
                        'notes',
                        ''
                    ),

                'created_at':
                    datetime.utcnow().isoformat()
            }

            # ======================================================
            # COMMIT 9 — NET EDGE ECONOMICS
            # ======================================================
            # Only fields explicitly present in the result are written. Spot
            # and old callers therefore remain schema-compatible. None values
            # are intentional for not-yet-observed funding components.
            economics_text_fields = (
                'entry_timestamp',
                'economics_model_version',
                'economics_status',
                'economics_cost_model_source',
                'funding_data_source',
                'funding_calculation_status',
                'funding_contract_symbol',
                'funding_observed_at',
                'economics_quality',
                'economics_last_error',
                'economics_updated_at',
            )
            economics_float_fields = (
                'economics_round_trip_cost_rate',
                'gross_r',
                'gross_pnl_pct_margin',
                'modeled_fee_slippage_cost_r',
                'funding_rate_sum',
                'modeled_funding_cost_r',
                'modeled_total_cost_r',
                'modeled_net_r',
                'modeled_net_pnl_pct_margin',
            )
            economics_int_fields = (
                'funding_settlements_count',
                'funding_attempts',
            )
            for key in economics_text_fields:
                if key in result:
                    payload[key] = result.get(key)
            for key in economics_float_fields:
                if key in result:
                    value = result.get(key)
                    payload[key] = float(value) if value is not None else None
            for key in economics_int_fields:
                if key in result:
                    value = result.get(key)
                    payload[key] = int(value) if value is not None else None
            if 'economics_cost_components_complete' in result:
                payload['economics_cost_components_complete'] = bool(
                    result.get('economics_cost_components_complete')
                )
            
            from uuid import uuid5, NAMESPACE_URL
            payload['id'] = str(uuid5(NAMESPACE_URL,
                f"q6:{signal_id}:{payload['status']}:{payload['exit_timestamp']}"))
            self._rest_minimal(
                'POST',
                'signal_results',
                payload=payload,
                params={'on_conflict':'id'},
                timeout=(1.25, 2.5),
                prefer='resolution=merge-duplicates,return=minimal',
            )
            self._rest_minimal(
                'PATCH',
                'signals',
                payload=update_signal,
                params={'id':f'eq.{signal_id}'},
                timeout=(1.25, 2.5),
                prefer='return=minimal',
            )
            self._schedule_rotation('signal_results')
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
            
            # FREE-PLAN: no necesitamos que PostgREST nos devuelva el JSON
            # completo de la oportunidad. Un UUID determinista permite
            # idempotencia sin SELECT previo y `return=minimal` evita egress.
            missed_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                'missed|' + '|'.join((
                    str(payload.get('symbol') or ''),
                    str(payload.get('timeframe') or ''),
                    str(payload.get('action_that_should_have_been') or ''),
                    str(payload.get('candle_timestamp') or ''),
                )),
            ))
            payload['id'] = missed_id
            try:
                self._rest_minimal(
                    'POST',
                    'missed_opportunities',
                    payload=payload,
                    timeout=(1.25, 2.25),
                    prefer='return=minimal',
                )
            except requests.HTTPError as write_error:
                status = int(getattr(getattr(write_error, 'response', None), 'status_code', 0) or 0)
                if status != 409:
                    raise
            self._schedule_rotation('missed_opportunities')
            return missed_id
        except Exception as e:
            logger.error(f"Error insertando oportunidad perdida: {e}")
            return None
    
    # ========================================================================
    # CONSULTAS ESTADÍSTICAS
    # ========================================================================
    
    def iter_pending_signals(self, hours_old_max=168, directional=None,
                             page_size=200, max_rows=4000, budget_seconds=60):
        """Q6-E: keyset scan, stable while the evaluator changes pending status.

        The cursor rotates between runs so old unavailable/quarantined rows
        cannot permanently starve recent signals. No schema migration.
        """
        if not self.enabled:
            return
        import time
        start = time.monotonic()
        cutoff = (datetime.utcnow() - timedelta(hours=hours_old_max)).isoformat()
        snapshot_end = datetime.utcnow().isoformat()
        cursors = getattr(self, '_q6_pending_cursors', {})
        self._q6_pending_cursors = cursors
        cursor = cursors.get(directional)
        processed = 0
        while processed < max_rows and time.monotonic() - start < budget_seconds:
            try:
                query = (self.client.table('signals')
                         .select('id,symbol,timeframe,system_type,action_original,action_normalized,'
                                 'status,created_at,candle_timestamp,current_price,'
                                 'entry_price,stop_loss,take_profit,confidence,indicators_snapshot,'
                                 'leverage,q6_learning:context->learning,'
                                 'q6_execution:context->execution,'
                                 'q6_publication:context->futures_publication')
                         .eq('status', 'pending').gte('created_at', cutoff)
                         .lt('created_at', snapshot_end).order('id')
                         .limit(min(page_size, max_rows - processed)))
                if directional is True:
                    query = query.in_('action_normalized', ['LONG', 'SHORT'])
                elif directional is False:
                    query = query.eq('action_normalized', 'NO_OPERAR')
                if cursor:
                    query = query.gt('id', cursor)
                rows = query.execute().data or []
                if not rows:
                    cursors[directional] = None
                    return
                for row in rows:
                    row['context'] = {
                        'learning': row.pop('q6_learning', {}) or {},
                        'execution': row.pop('q6_execution', {}) or {},
                        'futures_publication': row.pop('q6_publication', {}) or {},
                    }
                    cursor = row['id']
                    cursors[directional] = cursor
                    processed += 1
                    yield row
            except Exception as exc:
                logger.error('Q6 pending batch failed: %s', type(exc).__name__)
                return

    def get_pending_signals(self, hours_old_max=168):
        """Compatibility API; evaluation workers consume the iterator directly."""
        return list(self.iter_pending_signals(hours_old_max=hours_old_max))

    
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
        cache_key = (str(symbol), str(timeframe), str(normalized))
        cached = self._recommendations_cache.get(cache_key) or {}
        if cached and (time.monotonic() - float(cached.get('ts') or 0.0)) < 1800:
            value = cached.get('value')
            return dict(value) if isinstance(value, dict) else None
        if not self.free_plan_allows('important'):
            value = cached.get('value')
            return dict(value) if isinstance(value, dict) else None
        
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
            value = self._with_retry(_op)
            self._recommendations_cache[cache_key] = {'ts': time.monotonic(), 'value': dict(value) if isinstance(value, dict) else None}
            return value
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
            
            # FREE-PLAN: estas recomendaciones son caché derivable. No descargar
            # la fila eliminada ni la recién insertada.
            filters = {
                'symbol': f"eq.{payload['symbol']}",
                'timeframe': f"eq.{payload['timeframe']}",
                'action': f"eq.{payload['action']}",
            }
            self._rest_minimal(
                'DELETE',
                'review_recommendations',
                params=filters,
                timeout=(1.25, 2.25),
                prefer='return=minimal',
            )
            self._rest_minimal(
                'POST',
                'review_recommendations',
                payload=payload,
                timeout=(1.25, 2.25),
                prefer='return=minimal',
            )
            self._schedule_rotation('review_recommendations')
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
            
            # Upsert fila por fila (más lento pero seguro)
            for stat in stats_list:
                # Construir filtro de unicidad
                if general:
                    # general: único por (strategy, action)
                    query = (self.client.table(table)
                             .select('id')
                             .eq('strategy', stat['strategy'])
                             .eq('action', stat['action']))
                else:
                    # specific: único por (symbol, timeframe, action, strategy)
                    query = (self.client.table(table)
                             .select('id')
                             .eq('symbol', stat['symbol'])
                             .eq('timeframe', stat['timeframe'])
                             .eq('action', stat['action'])
                             .eq('strategy', stat['strategy']))
                
                existing = query.limit(1).execute()
                
                if existing.data and len(existing.data) > 0:
                    # Update
                    stat_id = existing.data[0]['id']
                    self.client.table(table).update(stat).eq('id', stat_id).execute()
                else:
                    # Insert
                    self.client.table(table).insert(stat).execute()
            
            self._check_rotation(table)
            return True
        except Exception as e:
            logger.error(f"Error actualizando stats {table}: {e}")
            return False
    
    def get_signals_for_stats(self, days_back: int = 90) -> List[Dict]:
        """Señales cerradas de la cohorte operativa actual, con egress acotado.

        RC8.3 FINAL:
        - deja de descargar todo el histórico 90d + relación anidada;
        - filtra en PostgREST la generación 36W actual;
        - Futures: sólo EXECUTABLE_SIGNAL estadísticamente elegible;
        - Spot: sólo cohorte Q6 verificable/elegible;
        - hidrata nombres de estrategias en lotes sólo para las filas devueltas.

        5m/15m y Legacy siguen guardados, pero ReviewTrader no los usa para
        calibrar la producción actual.
        """
        if not self.enabled:
            return []

        try:
            days_back = max(7, min(int(days_back or 90), 180))
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            select_cols = (
                'id,symbol,timeframe,system_type,action_normalized,status,'
                'entry_price,stop_loss,take_profit,leverage,context,'
                'created_at,closed_at'
            )

            if self._stats_cache_days != days_back:
                self._stats_signals_cache = []
                self._stats_closed_watermark = ''
                self._stats_cache_days = days_back

            def _base_query(market):
                q = (
                    self.client.table('signals')
                    .select(select_cols)
                    .eq('system_type', market)
                    .neq('status', 'pending')
                    .gte('created_at', cutoff)
                    .eq('context->execution->>quality_score_version', '36W_V2_NORMALIZED')
                )
                if market == 'futures':
                    q = (
                        q.eq('context->learning->>cohort', 'FUTURES_PERPETUAL_REAL_CLOSED_V1')
                         .eq('context->learning->>market_data_source', 'KUCOIN_FUTURES_PERPETUAL_REST')
                         .eq('context->learning->>market_data_is_synthetic', 'false')
                         .eq('context->learning->>source_candle_closed', 'true')
                         .eq('context->learning->>evaluation_role', 'EXECUTABLE_SIGNAL')
                         .eq('context->learning->>statistically_eligible', 'true')
                    )
                else:
                    q = (
                        q.eq('context->learning->>cohort', 'SPOT_REAL_CLOSED_Q6')
                         .eq('context->learning->>market_data_source', 'KUCOIN_SPOT_REST')
                         .eq('context->learning->>market_data_is_synthetic', 'false')
                         .eq('context->learning->>source_candle_closed', 'true')
                         .eq('context->learning->>analysis_version', 'spot_closed_q6_v1')
                         .eq('context->learning->>statistically_eligible', 'true')
                    )
                return q

            def _fetch(after_closed=''):
                rows = []
                for market in ('spot', 'futures'):
                    q = _base_query(market)
                    if after_closed:
                        q = q.gt('closed_at', after_closed)
                    response = self._with_retry(
                        lambda q=q: q.order('closed_at', desc=False).limit(1000).execute()
                    )
                    rows.extend(response.data or [])
                return rows

            fresh_rows = _fetch('' if not self._stats_signals_cache else self._stats_closed_watermark)
            if not self._stats_signals_cache:
                merged = {str(row.get('id')): row for row in fresh_rows if row.get('id')}
            else:
                merged = {str(row.get('id')): row for row in self._stats_signals_cache if row.get('id')}
                for row in fresh_rows:
                    if row.get('id'):
                        merged[str(row.get('id'))] = row

            # Sólo la cohorte activa actual puede calibrar.
            try:
                from cohort_integrity import classify_quality_signal
                from q6_integrity import verified_spot_current
                filtered = []
                for row in merged.values():
                    market = str(row.get('system_type') or '').lower()
                    info = classify_quality_signal(
                        row,
                        spot_verified=bool(verified_spot_current(row)) if market == 'spot' else False
                    )
                    if info.get('cohort') in {'OFFICIAL_CURRENT_SPOT', 'OFFICIAL_CURRENT_FUTURES'}:
                        filtered.append(row)
                merged = {str(row.get('id')): row for row in filtered if row.get('id')}
            except Exception:
                pass

            # Hidratar únicamente nombres de estrategia para las pocas filas
            # oficiales. indicator_values ya vive una sola vez en signals y no
            # se descarga aquí.
            ids = list(merged.keys())
            strategies = {}
            for start_i in range(0, len(ids), 120):
                batch = ids[start_i:start_i + 120]
                if not batch:
                    continue
                response = self._with_retry(
                    lambda batch=batch: (
                        self.client.table('signal_indicators')
                        .select('signal_id,strategy_name')
                        .in_('signal_id', batch)
                        .execute()
                    )
                )
                for item in response.data or []:
                    sid = str(item.get('signal_id') or '')
                    name = item.get('strategy_name')
                    if sid and name:
                        strategies.setdefault(sid, []).append({'strategy_name': name})

            for sid, row in merged.items():
                row['signal_indicators'] = strategies.get(sid, [])

            self._stats_signals_cache = list(merged.values())
            closed_values = [
                str(row.get('closed_at') or '') for row in self._stats_signals_cache
                if row.get('closed_at')
            ]
            if closed_values:
                self._stats_closed_watermark = max(closed_values)
            return list(self._stats_signals_cache)
        except Exception as e:
            logger.error(f"Error obteniendo señales compactas para stats: {e}")
            return list(self._stats_signals_cache or [])

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
    
    def preview_old_signals_by_tf(self, timeframe: str, days_retention: int) -> int:
        """RC4.1: cuenta candidatos TTL sin borrar ninguna evidencia."""
        if not self.enabled:
            return 0
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
            response = (self.client.table('signals')
                        .select('id', count='exact')
                        .eq('timeframe', timeframe)
                        .lt('created_at', cutoff)
                        .limit(1)
                        .execute())
            return int(getattr(response, 'count', None) or len(response.data or []))
        except Exception as e:
            logger.error(f"Error en preview_old_signals_by_tf({timeframe}): {e}")
            return 0

    def delete_old_signals_by_tf(self, timeframe: str, days_retention: int, *, allow_destructive: bool = False) -> int:
        """Compatibilidad: RC4.1 bloquea borrado automático de señales.

        El antiguo TTL borraba pérdidas/expiraciones y podía sesgar la muestra.
        Para una limpieza física futura se requiere una migración/auditoría explícita;
        el runtime de producción nunca la ejecuta.
        """
        if not allow_destructive:
            logger.warning('RC4.1 DATA HYGIENE: borrado TTL bloqueado; sólo auditoría read-only')
            return 0
        # Incluso con flag explícito no borramos desde el runtime: fail-closed.
        logger.error('RC4.1 DATA HYGIENE: destructive cleanup requires an offline reviewed migration')
        return 0

    def apply_ttl_cleanup(self) -> Dict:
        """RC4.1: auditoría TTL no destructiva para evitar survivorship bias."""
        ttl_config = {
            '5m': 7, '15m': 14, '30m': 21, '1h': 30, '2h': 45,
            '4h': 60, '12h': 90, '1D': 180, '1W': 365
        }
        candidates = {tf: self.preview_old_signals_by_tf(tf, days) for tf, days in ttl_config.items()}
        return {
            'policy': 'NON_DESTRUCTIVE_AUDIT_ONLY',
            'deleted': 0,
            'candidates_by_tf': candidates,
            'candidate_total': sum(candidates.values()),
            'reason': 'Preserve TP/SL/expired/legacy evidence; physical cleanup only after reviewed backup and cohort audit.',
        }

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
        """Retorna los últimos N logs del ReviewTrader (ordenados por fecha DESC)."""
        if not self.enabled:
            return []
        limit = max(1, min(int(limit or 50), 100))
        cached = self._review_logs_cache.get(limit) or {}
        if cached and (time.monotonic() - float(cached.get('ts') or 0.0)) < 900:
            return list(cached.get('value') or [])
        if not self.free_plan_allows('diagnostic'):
            return list(cached.get('value') or [])
        
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
            value = response.data or []
            self._review_logs_cache[limit] = {'ts': time.monotonic(), 'value': list(value)}
            return value
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
        cached = self._storage_stats_cache or {}
        if cached.get('value') and (time.monotonic() - float(cached.get('ts') or 0.0)) < 3600:
            return dict(cached.get('value') or {})
        if not self.free_plan_allows('diagnostic'):
            return dict(cached.get('value') or {})
        
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
        
        self._storage_stats_cache = {'ts': time.monotonic(), 'value': dict(stats)}
        return stats
    
    # ========================================================================
    # ROTACIÓN FIFO
    # ========================================================================
    
    def _check_rotation(self, table_name: str):
        """
        Verifica si la tabla superó el límite y borra las filas más antiguas.

        PRE38-A:
        - conserva exactamente los límites FIFO existentes;
        - conserva el chequeo probabilístico del 10%;
        - conserva la protección de señales con TP exitoso;
        - evita enviar cientos o miles de UUIDs en una sola llamada .in_();
        - elimina en lotes pequeños para evitar 400 de Cloudflare/PostgREST.

        Esta función NO cambia señales de trading, Safety, aprendizaje ni
        criterios de ReviewTrader. Sólo hace más segura la limpieza FIFO.
        """
        if not self.enabled:
            return

        # FREE-PLAN: una rotación por tabla cada 6 horas como máximo.
        # Antes el chequeo probabilístico podía ejecutar COUNTs repetidamente
        # durante ráfagas de señales. La limpieza no necesita frecuencia por
        # inserción y el GC de Supabase ya cubre Research/runtime.
        now_mono = time.monotonic()
        with self._rotation_lock:
            last = float(self._rotation_last_check.get(table_name, 0.0) or 0.0)
            if last and (now_mono - last) < 6 * 3600:
                return
            self._rotation_last_check[table_name] = now_mono

        # Mantener cada filtro .in_() en un tamaño razonable.
        delete_batch_size = 100

        def _delete_ids_in_batches(ids):
            """
            Borra IDs de una tabla en lotes pequeños.

            Devuelve cuántos IDs fueron enviados correctamente a Supabase.
            Si un lote falla, la excepción sube al manejo general de
            _check_rotation para conservar el comportamiento tolerante a fallos.
            """
            deleted = 0

            for start in range(
                0,
                len(ids),
                delete_batch_size
            ):
                batch = ids[
                    start:start + delete_batch_size
                ]

                if not batch:
                    continue

                ids_csv = ','.join(str(x) for x in batch)
                self._rest_minimal(
                    'DELETE',
                    table_name,
                    params={'id': f'in.({ids_csv})'},
                    timeout=(1.25, 3.0),
                    prefer='return=minimal',
                )

                deleted += len(
                    batch
                )

            return deleted

        try:
            limit = LIMITS.get(
                table_name,
                10000
            )

            # Contar filas actuales.
            count_response = (
                self.client
                .table(table_name)
                .select(
                    'id',
                    count='exact'
                )
                .limit(1)
                .execute()
            )

            current_count = (
                count_response.count
                or 0
            )

            if current_count <= limit:
                return

            # Excede el límite: mantener la política actual de borrar
            # aproximadamente el 5% del límite configurado.
            to_delete = max(
                1,
                int(
                    limit
                    * 0.05
                )
            )

            if table_name == 'signals':
                # Preservar señales con TP exitoso.
                old_rows = (
                    self.client
                    .table('signals')
                    .select('id')
                    .neq(
                        'status',
                        'tp_hit'
                    )
                    .order('created_at')
                    .limit(to_delete)
                    .execute()
                )

            else:
                # Para otras tablas: borrar las filas más antiguas.
                old_rows = (
                    self.client
                    .table(table_name)
                    .select('id')
                    .order('created_at')
                    .limit(to_delete)
                    .execute()
                )

            ids_to_delete = [
                row.get('id')
                for row in (
                    old_rows.data
                    or []
                )
                if row.get('id')
            ]

            if not ids_to_delete:
                return

            deleted = (
                _delete_ids_in_batches(
                    ids_to_delete
                )
            )

            logger.info(
                f"Rotación FIFO en {table_name}: "
                f"eliminadas {deleted} filas "
                f"en lotes de máximo {delete_batch_size}"
            )

        except Exception as e:
            if self._is_connection_error(e):
                # La rotación FIFO no es crítica para la decisión de trading.
                logger.debug(
                    f"Rotación FIFO {table_name}: "
                    "sistema temporalmente saturado"
                )
            else:
                logger.error(
                    f"Error en rotación FIFO de {table_name}: {e}"
                )
    
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
    # ========================================================================
    # USER TELEGRAM PREFERENCES
    # ========================================================================

    def get_user_preferences(
        self,
        user_name: str
    ) -> Dict:
        defaults = {
            'spot_telegram_enabled': True,
            'spot_telegram_timeframes': ['4h', '12h', '1D', '1W'],
            'futures_scalping_telegram_enabled': False,
            'futures_scalping_timeframes': [],
            'futures_scalping_start_time': None,
            'futures_scalping_end_time': None,
            'futures_scalping_weekdays': [],
            'futures_scalping_timezone': 'UTC'
        }

        if not self.enabled:
            return dict(defaults)

        cache_key = str(user_name or '').strip()
        cached = self._preferences_cache.get(cache_key) or {}
        # Preferences almost never change; a 6h local cache eliminates thousands
        # of identical reads. Explicit preference writes invalidate this cache.
        if cached and (time.monotonic() - float(cached.get('ts') or 0.0)) < 21600:
            value = cached.get('value')
            return dict(value) if isinstance(value, dict) else dict(defaults)
        if not self.free_plan_allows('important'):
            value = cached.get('value')
            return dict(value) if isinstance(value, dict) else dict(defaults)
        if self.read_circuit_open():
            value = cached.get('value')
            return dict(value) if isinstance(value, dict) else dict(defaults)

        def _json_list(value):
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, list) else []
                except Exception:
                    return []
            return []

        def _clock_text(value):
            text = str(value or '').strip()
            if not text:
                return None
            try:
                parts = text.split(':')
                hour = int(parts[0])
                minute = int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    return None
                return f"{hour:02d}:{minute:02d}"
            except Exception:
                return None

        try:
            response = self._with_retry(
                lambda: (
                    self.client
                    .table('user_preferences')
                    .select('*')
                    .eq('user_name', user_name)
                    .limit(1)
                    .execute()
                )
            )

            rows = response.data or []
            if not rows:
                return dict(defaults)

            row = rows[0]

            spot_allowed = ('4h', '12h', '1D', '1W')
            raw_spot_tf = _json_list(
                row.get('spot_telegram_timeframes')
            )
            spot_timeframes = [
                tf for tf in spot_allowed if tf in raw_spot_tf
            ]

            scalping_allowed = ('5m', '15m')
            raw_scalping_tf = _json_list(
                row.get('futures_scalping_timeframes')
            )
            scalping_timeframes = [
                tf for tf in scalping_allowed if tf in raw_scalping_tf
            ]

            raw_weekdays = _json_list(
                row.get('futures_scalping_weekdays')
            )

            weekdays = []
            for day in raw_weekdays:
                try:
                    day_number = int(day)
                except (TypeError, ValueError):
                    continue
                if 1 <= day_number <= 7 and day_number not in weekdays:
                    weekdays.append(day_number)
            weekdays.sort()

            timezone_name = str(
                row.get('futures_scalping_timezone') or 'UTC'
            ).strip() or 'UTC'

            value = {
                'spot_telegram_enabled': bool(
                    row.get('spot_telegram_enabled', True)
                ),
                'spot_telegram_timeframes': spot_timeframes,
                'futures_scalping_telegram_enabled': bool(
                    row.get('futures_scalping_telegram_enabled', False)
                ),
                'futures_scalping_timeframes': scalping_timeframes,
                'futures_scalping_start_time': _clock_text(
                    row.get('futures_scalping_start_time')
                ),
                'futures_scalping_end_time': _clock_text(
                    row.get('futures_scalping_end_time')
                ),
                'futures_scalping_weekdays': weekdays,
                'futures_scalping_timezone': timezone_name
            }
            self._preferences_cache[cache_key] = {'ts': time.monotonic(), 'value': dict(value)}
            return value

        except Exception as e:
            logger.warning(
                "get_user_preferences "
                f"({user_name}): {e}"
            )
            stale = self._preferences_cache.get(cache_key) or {}
            value = stale.get('value')
            return dict(value) if isinstance(value, dict) else dict(defaults)

    def upsert_user_preferences(
        self,
        user_name: str,
        preferences: Dict
    ) -> bool:
        if not self.enabled:
            return False

        try:
            user_name = str(user_name or '').strip()
            if not user_name:
                return False
            self._preferences_cache.pop(user_name, None)

            if not isinstance(preferences, dict):
                return False

            current = self.get_user_preferences(user_name)
            merged = dict(current)

            allowed_keys = (
                'spot_telegram_enabled',
                'spot_telegram_timeframes',
                'futures_scalping_telegram_enabled',
                'futures_scalping_timeframes',
                'futures_scalping_start_time',
                'futures_scalping_end_time',
                'futures_scalping_weekdays',
                'futures_scalping_timezone'
            )

            for key in allowed_keys:
                if key in preferences:
                    merged[key] = preferences[key]

            spot_allowed = ('4h', '12h', '1D', '1W')
            requested_spot = (
                merged.get('spot_telegram_timeframes', []) or []
            )
            if not isinstance(requested_spot, list):
                requested_spot = []
            clean_spot = [
                tf for tf in spot_allowed if tf in requested_spot
            ]

            scalping_allowed = ('5m', '15m')
            requested_scalping = (
                merged.get('futures_scalping_timeframes', []) or []
            )
            if not isinstance(requested_scalping, list):
                requested_scalping = []
            clean_scalping = [
                tf for tf in scalping_allowed if tf in requested_scalping
            ]

            requested_weekdays = (
                merged.get('futures_scalping_weekdays', []) or []
            )
            if not isinstance(requested_weekdays, list):
                requested_weekdays = []

            clean_weekdays = []
            for day in requested_weekdays:
                try:
                    day_number = int(day)
                except (TypeError, ValueError):
                    continue
                if 1 <= day_number <= 7 and day_number not in clean_weekdays:
                    clean_weekdays.append(day_number)
            clean_weekdays.sort()

            def _normalize_clock(value):
                if value is None:
                    return None
                text = str(value or '').strip()
                if not text:
                    return None

                parts = text.split(':')
                if len(parts) < 2:
                    raise ValueError('Hora inválida; usar HH:MM.')

                hour = int(parts[0])
                minute = int(parts[1])

                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError('Hora fuera de rango.')

                return f"{hour:02d}:{minute:02d}"

            start_time = _normalize_clock(
                merged.get('futures_scalping_start_time')
            )
            end_time = _normalize_clock(
                merged.get('futures_scalping_end_time')
            )

            timezone_name = str(
                merged.get('futures_scalping_timezone') or 'UTC'
            ).strip() or 'UTC'

            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(timezone_name)
            except Exception as timezone_error:
                raise ValueError(
                    'Zona horaria IANA inválida: '
                    f'{timezone_name}'
                ) from timezone_error

            futures_enabled = bool(
                merged.get(
                    'futures_scalping_telegram_enabled',
                    False
                )
            )

            if futures_enabled:
                if not clean_scalping:
                    raise ValueError(
                        'Debes elegir al menos una temporalidad '
                        'de scalping Futures.'
                    )
                if start_time is None or end_time is None:
                    raise ValueError(
                        'Debes definir hora inicial y hora final.'
                    )
                if not clean_weekdays:
                    raise ValueError(
                        'Debes elegir al menos un día de la semana.'
                    )

            futures_keys = {
                'futures_scalping_telegram_enabled',
                'futures_scalping_timeframes',
                'futures_scalping_start_time',
                'futures_scalping_end_time',
                'futures_scalping_weekdays',
                'futures_scalping_timezone'
            }

            futures_changed = any(
                key in preferences for key in futures_keys
            )

            now_iso = datetime.utcnow().isoformat()

            payload = {
                'user_name': user_name,
                'spot_telegram_enabled': bool(
                    merged.get('spot_telegram_enabled', True)
                ),
                'spot_telegram_timeframes': clean_spot,
                'futures_scalping_telegram_enabled': futures_enabled,
                'futures_scalping_timeframes': clean_scalping,
                'futures_scalping_start_time': start_time,
                'futures_scalping_end_time': end_time,
                'futures_scalping_weekdays': clean_weekdays,
                'futures_scalping_timezone': timezone_name,
                'updated_at': now_iso
            }

            if futures_changed:
                payload['futures_scalping_updated_at'] = now_iso

            response = self._with_retry(
                lambda: (
                    self.client
                    .table('user_preferences')
                    .upsert(
                        payload,
                        on_conflict='user_name'
                    )
                    .execute()
                )
            )

            return response.data is not None

        except Exception as e:
            logger.error(
                "upsert_user_preferences "
                f"({user_name}): {e}"
            )
            return False

    # ========================================================================
    # COMMIT 36P — FUTURES RISK PROFILE
    # ========================================================================

    def get_user_futures_risk_profile(
        self,
        user_name: str
    ) -> Dict:
        """
        Perfil PERSONAL de sizing Futures.

        No modifica:
        - Safety
        - Entry
        - SL
        - TP
        - RR
        - Publication Gate
        """

        defaults = {
            'futures_risk_mode':
                'MANUAL',

            'futures_margin_policy':
                'FIXED_USDT',

            'futures_equity_usdt':
                None,

            'futures_max_allocation_pct':
                None,

            'futures_max_loss_pct_equity_per_trade':
                None,

            'futures_preferred_margin_usdt':
                None,

            'futures_personal_max_leverage':
                None,

            'futures_risk_updated_at':
                None,
        }

        if not self.enabled:
            return dict(
                defaults
            )

        def _number_or_none(
            value
        ):

            try:

                if value is None:
                    return None

                return float(
                    value
                )

            except (
                TypeError,
                ValueError
            ):

                return None

        try:

            response = self._with_retry(
                lambda: (
                    self.client
                    .table(
                        'user_preferences'
                    )
                    .select(
                        (
                            'futures_risk_mode,'
                            'futures_margin_policy,'
                            'futures_equity_usdt,'
                            'futures_max_allocation_pct,'
                            'futures_max_loss_pct_equity_per_trade,'
                            'futures_preferred_margin_usdt,'
                            'futures_personal_max_leverage,'
                            'futures_risk_updated_at'
                        )
                    )
                    .eq(
                        'user_name',
                        user_name
                    )
                    .limit(
                        1
                    )
                    .execute()
                )
            )

            rows = (
                response.data
                or []
            )

            if not rows:
                return dict(
                    defaults
                )

            row = rows[0]

            mode = str(
                row.get(
                    'futures_risk_mode'
                )
                or 'MANUAL'
            ).upper()

            if mode not in (
                'MANUAL',
                'PROFILE_ADVISORY'
            ):
                mode = 'MANUAL'

            margin_policy = str(
                row.get(
                    'futures_margin_policy'
                )
                or 'FIXED_USDT'
            ).upper()

            if margin_policy not in (
                'FIXED_USDT',
                'EQUITY_PCT'
            ):
                margin_policy = (
                    'FIXED_USDT'
                )

            raw_max_leverage = (
                row.get(
                    'futures_personal_max_leverage'
                )
            )

            try:

                personal_max_leverage = (
                    int(
                        raw_max_leverage
                    )
                    if raw_max_leverage
                    is not None
                    else None
                )

            except (
                TypeError,
                ValueError
            ):

                personal_max_leverage = (
                    None
                )

            return {
                'futures_risk_mode':
                    mode,

                'futures_margin_policy':
                    margin_policy,

                'futures_equity_usdt':
                    _number_or_none(
                        row.get(
                            'futures_equity_usdt'
                        )
                    ),

                'futures_max_allocation_pct':
                    _number_or_none(
                        row.get(
                            'futures_max_allocation_pct'
                        )
                    ),

                'futures_max_loss_pct_equity_per_trade':
                    _number_or_none(
                        row.get(
                            'futures_max_loss_pct_equity_per_trade'
                        )
                    ),

                'futures_preferred_margin_usdt':
                    _number_or_none(
                        row.get(
                            'futures_preferred_margin_usdt'
                        )
                    ),

                'futures_personal_max_leverage':
                    personal_max_leverage,

                'futures_risk_updated_at':
                    row.get(
                        'futures_risk_updated_at'
                    ),
            }

        except Exception as e:

            logger.warning(
                "get_user_futures_risk_profile "
                f"({user_name}): {e}"
            )

            return dict(
                defaults
            )


    def upsert_user_futures_risk_profile(
        self,
        user_name: str,
        profile: Dict
    ) -> bool:
        """
        Guarda exclusivamente preferencias PERSONALES
        de sizing Futures.
        """

        if not self.enabled:
            return False

        try:

            now_iso = (
                datetime.utcnow()
                .isoformat()
            )

            payload = {
                'user_name':
                    str(
                        user_name
                    ).strip(),

                'futures_risk_mode':
                    profile.get(
                        'futures_risk_mode',
                        'MANUAL'
                    ),

                'futures_margin_policy':
                    profile.get(
                        'futures_margin_policy',
                        'FIXED_USDT'
                    ),

                'futures_equity_usdt':
                    profile.get(
                        'futures_equity_usdt'
                    ),

                'futures_max_allocation_pct':
                    profile.get(
                        'futures_max_allocation_pct'
                    ),

                'futures_max_loss_pct_equity_per_trade':
                    profile.get(
                        'futures_max_loss_pct_equity_per_trade'
                    ),

                'futures_preferred_margin_usdt':
                    profile.get(
                        'futures_preferred_margin_usdt'
                    ),

                'futures_personal_max_leverage':
                    profile.get(
                        'futures_personal_max_leverage'
                    ),

                'futures_risk_updated_at':
                    now_iso,

                'updated_at':
                    now_iso,
            }

            response = self._with_retry(
                lambda: (
                    self.client
                    .table(
                        'user_preferences'
                    )
                    .upsert(
                        payload,
                        on_conflict='user_name'
                    )
                    .execute()
                )
            )

            return (
                response.data
                is not None
            )

        except Exception as e:

            logger.error(
                "upsert_user_futures_risk_profile "
                f"({user_name}): {e}"
            )

            return False    

    
    # ========================================================================
    # USER PORTFOLIO
    # ========================================================================

    def get_user_portfolio(self, user_name: str) -> Dict:
        """
        Obtiene el portfolio persistente del usuario.

        IMPORTANTE:
        - El usuario viene determinado por la sesión Flask.
        - Este método sólo realiza la consulta.
        - Si no existe registro devuelve valores cero.
        """

        if not self.enabled:
            return {
                'BTC': 0,
                'PAXG': 0,
                'USDT': 0
            }

        try:
            response = self._with_retry(
                lambda: (
                    self.client
                    .table('user_portfolios')
                    .select('*')
                    .eq('user_name', user_name)
                    .limit(1)
                    .execute()
                )
            )

            rows = response.data or []

            if not rows:
                return {
                    'BTC': 0,
                    'PAXG': 0,
                    'USDT': 0,
                    'btc_price_at_update': 0,
                    'paxg_price_at_update': 0,
                    'updated_at': None
                }

            row = rows[0]

            return {
                'BTC': float(
                    row.get('btc_amount', 0) or 0
                ),
                'PAXG': float(
                    row.get('paxg_amount', 0) or 0
                ),
                'USDT': float(
                    row.get('usdt_amount', 0) or 0
                ),
                'btc_price_at_update': float(
                    row.get(
                        'btc_price_at_update',
                        0
                    ) or 0
                ),
                'paxg_price_at_update': float(
                    row.get(
                        'paxg_price_at_update',
                        0
                    ) or 0
                ),
                'updated_at': row.get(
                    'updated_at'
                )
            }

        except Exception as e:
            logger.error(
                f"Error get_user_portfolio "
                f"({user_name}): {e}"
            )

            return {
                'BTC': 0,
                'PAXG': 0,
                'USDT': 0
            }


    def upsert_user_portfolio(
        self,
        portfolio_data: Dict
    ) -> bool:
        """
        Inserta o actualiza el portfolio del usuario.

        La identidad se toma de portfolio_data['user_name'],
        que debe haber sido determinada previamente por el backend.
        """

        if not self.enabled:
            return False

        try:
            user_name = str(
                portfolio_data.get(
                    'user_name',
                    ''
                )
            ).strip()

            if not user_name:
                logger.error(
                    'upsert_user_portfolio: '
                    'user_name vacío'
                )
                return False

            payload = {
                'user_name': user_name,
                'btc_amount': max(
                    0.0,
                    float(
                        portfolio_data.get(
                            'btc_amount',
                            0
                        ) or 0
                    )
                ),
                'paxg_amount': max(
                    0.0,
                    float(
                        portfolio_data.get(
                            'paxg_amount',
                            0
                        ) or 0
                    )
                ),
                'usdt_amount': max(
                    0.0,
                    float(
                        portfolio_data.get(
                            'usdt_amount',
                            0
                        ) or 0
                    )
                )
            }

            if 'btc_price_at_update' in portfolio_data:
                payload['btc_price_at_update'] = float(
                    portfolio_data.get(
                        'btc_price_at_update',
                        0
                    ) or 0
                )

            if 'paxg_price_at_update' in portfolio_data:
                payload['paxg_price_at_update'] = float(
                    portfolio_data.get(
                        'paxg_price_at_update',
                        0
                    ) or 0
                )

            response = self._with_retry(
                lambda: (
                    self.client
                    .table('user_portfolios')
                    .upsert(
                        payload,
                        on_conflict='user_name'
                    )
                    .execute()
                )
            )

            return bool(response.data is not None)

        except Exception as e:
            logger.error(
                f"Error upsert_user_portfolio "
                f"({portfolio_data.get('user_name')}): {e}"
            )
            return False
    # ========================================================================
    # FASE 7F.3 — MEMORIA PERSISTENTE DE ROTACIÓN TGP
    # ========================================================================

    def get_user_rotation_state(
        self,
        user_name: str
    ) -> Dict:
        """
        Recupera únicamente la memoria estratégica BTC/PAXG
        utilizada por el TGP.

        IMPORTANTE:
        - NO recupera precios.
        - NO recupera señales.
        - NO modifica portfolio.
        - Se utiliza únicamente una vez por usuario después
          de iniciar/reiniciar el proceso de Render.
        """

        if not self.enabled:
            return {}

        try:

            user_name = str(
                user_name
                or ''
            ).strip()

            if not user_name:
                return {}

            response = self._with_retry(
                lambda: (
                    self.client
                    .table(
                        'user_portfolios'
                    )
                    .select(
                        (
                            'tgp_rotation_direction,'
                            'tgp_rotation_started_at,'
                            'tgp_rotation_updated_at'
                        )
                    )
                    .eq(
                        'user_name',
                        user_name
                    )
                    .limit(
                        1
                    )
                    .execute()
                )
            )

            rows = (
                response.data
                or []
            )

            if not rows:
                return {}

            row = rows[0]

            direction = str(
                row.get(
                    'tgp_rotation_direction',
                    ''
                )
                or ''
            ).upper()

            if direction not in (
                'BTC',
                'PAXG'
            ):

                direction = ''

            return {
                'direction':
                    direction,

                'started_at':
                    row.get(
                        'tgp_rotation_started_at'
                    ),

                'updated_at':
                    row.get(
                        'tgp_rotation_updated_at'
                    )
            }

        except Exception as e:

            # ==========================================================
            # FAIL-SAFE
            # ==========================================================
            #
            # La persistencia 7F.3 NO puede tumbar el TGP.
            # Si Supabase falla, simplemente se empieza sin memoria.
            # ==========================================================

            logger.debug(
                "7F.3 get_user_rotation_state "
                f"({user_name}): {e}"
            )

            return {}


    def update_user_rotation_state(
        self,
        user_name: str,
        direction=None,
        started_at=None
    ) -> bool:
        """
        Guarda o limpia la memoria estratégica del TGP.

        direction:
            'BTC'
            'PAXG'

        direction=None:
            limpia la memoria persistida.

        IMPORTANTE:
        utiliza UPDATE, no UPSERT.

        Por tanto nunca crea un portfolio vacío accidentalmente.
        """

        if not self.enabled:
            return False

        try:

            user_name = str(
                user_name
                or ''
            ).strip()

            if not user_name:
                return False

            now_iso = (
                datetime.utcnow()
                .isoformat()
            )

            # ==========================================================
            # LIMPIAR MEMORIA
            # ==========================================================

            if direction is None:

                payload = {
                    'tgp_rotation_direction':
                        None,

                    'tgp_rotation_started_at':
                        None,

                    'tgp_rotation_updated_at':
                        now_iso
                }

            else:

                direction = str(
                    direction
                ).upper()

                if direction not in (
                    'BTC',
                    'PAXG'
                ):

                    return False

                if not started_at:

                    started_at = (
                        now_iso
                    )

                payload = {
                    'tgp_rotation_direction':
                        direction,

                    'tgp_rotation_started_at':
                        started_at,

                    'tgp_rotation_updated_at':
                        now_iso
                }

            response = self._with_retry(
                lambda: (
                    self.client
                    .table(
                        'user_portfolios'
                    )
                    .update(
                        payload
                    )
                    .eq(
                        'user_name',
                        user_name
                    )
                    .execute()
                )
            )

            return bool(
                response.data
                is not None
            )

        except Exception as e:

            # ==========================================================
            # FAIL-SAFE
            # ==========================================================
            #
            # Una falla guardando memoria NO puede afectar:
            #
            # BTC / PAXG / USDT
            # análisis
            # TGP
            # frontend
            # ==========================================================

            logger.debug(
                "7F.3 update_user_rotation_state "
                f"({user_name}): {e}"
            )

            return False

    # ========================================================================
    # USER TRADES
    # ========================================================================

    def insert_user_trade(
        self,
        trade_data: Dict
    ) -> Dict:
        """Guarda una operación personal del usuario."""

        if not self.enabled:
            return {}

        try:
            response = self._with_retry(
                lambda: (
                    self.client
                    .table('user_trades')
                    .insert(trade_data)
                    .execute()
                )
            )

            return (
                response.data[0]
                if response.data
                else {}
            )

        except Exception as e:
            logger.error(
                f"Error insert_user_trade: {e}"
            )
            return {}


    def get_user_trades(
        self,
        user_name: str,
        status: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Obtiene operaciones pertenecientes al usuario."""

        if not self.enabled:
            return []

        try:
            safe_limit = max(
                1,
                min(
                    int(limit),
                    1000
                )
            )

            query = (
                self.client
                .table('user_trades')
                .select('*')
                .eq('user_name', user_name)
                .order(
                    'created_at',
                    desc=True
                )
                .limit(safe_limit)
            )

            if status:
                query = query.eq(
                    'status',
                    status
                )

            response = self._with_retry(
                lambda: query.execute()
            )

            return response.data or []

        except Exception as e:
            logger.error(
                f"Error get_user_trades "
                f"({user_name}): {e}"
            )
            return []


    def update_user_trade(
        self,
        trade_id,
        updates: Dict
    ) -> bool:
        """Actualiza una operación personal."""

        if not self.enabled:
            return False

        try:
            response = self._with_retry(
                lambda: (
                    self.client
                    .table('user_trades')
                    .update(updates)
                    .eq('id', trade_id)
                    .execute()
                )
            )

            return response.data is not None

        except Exception as e:
            logger.error(
                f"Error update_user_trade "
                f"({trade_id}): {e}"
            )
            return False


    def get_user_trade_stats(
        self,
        user_name: str
    ) -> Dict:
        """
        Calcula estadísticas personales del usuario.
        """

        trades = self.get_user_trades(
            user_name,
            limit=1000
        )

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

        closed = [
            trade
            for trade in trades
            if trade.get('status')
            in (
                'CLOSED_WIN',
                'CLOSED_LOSS',
                'CLOSED_TIME',
                'CLOSED_MANUAL'
            )
        ]

        wins = [
            trade
            for trade in closed
            if float(
                trade.get('pnl_usd', 0) or 0
            ) > 0
        ]

        total_pnl = sum(
            float(
                trade.get('pnl_usd', 0) or 0
            )
            for trade in closed
        )

        best = (
            max(
                closed,
                key=lambda trade: float(
                    trade.get(
                        'pnl_usd',
                        0
                    ) or 0
                )
            )
            if closed
            else None
        )

        worst = (
            min(
                closed,
                key=lambda trade: float(
                    trade.get(
                        'pnl_usd',
                        0
                    ) or 0
                )
            )
            if closed
            else None
        )

        return {
            'total_trades': len(trades),

            'win_rate': (
                round(
                    len(wins)
                    / len(closed)
                    * 100,
                    2
                )
                if closed
                else 0
            ),

            'total_pnl_usd': round(
                total_pnl,
                2
            ),

            'total_pnl_pct': round(
                sum(
                    float(
                        trade.get(
                            'pnl_pct',
                            0
                        ) or 0
                    )
                    for trade in closed
                ),
                2
            ),

            'avg_trade_usd': round(
                sum(
                    float(
                        trade.get(
                            'amount_usd',
                            0
                        ) or 0
                    )
                    for trade in trades
                )
                / len(trades),
                2
            ),

            'best_trade': {
                'action': best.get('action'),
                'pnl_usd': round(
                    float(
                        best.get(
                            'pnl_usd',
                            0
                        ) or 0
                    ),
                    2
                ),
                'date': best.get(
                    'closed_at'
                )
            } if best else None,

            'worst_trade': {
                'action': worst.get('action'),
                'pnl_usd': round(
                    float(
                        worst.get(
                            'pnl_usd',
                            0
                        ) or 0
                    ),
                    2
                ),
                'date': worst.get(
                    'closed_at'
                )
            } if worst else None,

            'open_trades': len([
                trade
                for trade in trades
                if trade.get('status') == 'OPEN'
            ]),

            'closed_trades': len(closed)
        }
# ============================================================================
# INSTANCIA GLOBAL (SINGLETON)
# ============================================================================

# El resto del sistema importa esta instancia:
# from supabase_client import supabase_db

supabase_db = SupabaseClient()

# Alias de compatibilidad.
#
# app.py utiliza:
#
#     from supabase_client import supabase_client
#
# El alias apunta al mismo objeto.
supabase_client = supabase_db

# Hotfix 14.8: NO ejecutar health_check() automático al importar el módulo.
# El chequeo recorría varias tablas justo durante el bootstrap y retenía
# respuestas HTTP/Pydantic sin aportar funcionalidad al arranque. Las consultas
# reales ya son fail-open y validan sus tablas cuando se usan.
if supabase_db.enabled:
    print("✅ Supabase listo (health-check profundo diferido)")
