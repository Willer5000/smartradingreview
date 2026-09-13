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
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from supabase_client import supabase_db
from execution_learning import (
    build_execution_forensics,
    build_strategy_attribution_v2,
)
from execution_economics import build_provisional_economics
from execution_challenger_lab import evaluate_execution_challengers

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

# Duración real de cada vela. Se usa para comenzar la evaluación DESPUÉS del
# cierre que originó la señal y evitar que ReviewTrader vea precios anteriores
# a una decisión que todavía no existía.
TIMEFRAME_MINUTES = {
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '2h': 120,
    '4h': 240,
    '12h': 720,
    '1D': 1440,
    '1W': 10080
}

# Contrato de aprendizaje de Futuros.
#
# Antes de esta versión existieron señales rotuladas como ``futures`` que podían
# haber sido creadas o evaluadas con velas Spot. No se borran: permanecen como
# historial, pero no pueden autorizar ajustes del ReviewTrader.
LEARNING_CONTRACT_VERSION = 'market_separated_v1'
FUTURES_REAL_DATA_SOURCE = 'KUCOIN_FUTURES_PERPETUAL_REST'
FUTURES_REAL_ANALYSIS_VERSION = 'closed_v1'
FUTURES_REAL_COHORT = 'FUTURES_PERPETUAL_REAL_CLOSED_V1'
FUTURES_LEGACY_COHORT = 'FUTURES_LEGACY_UNVERIFIED'
from q6_integrity import SPOT_COHORT, SPOT_LEGACY, clean_spot_learning, verified_spot
SPOT_LEARNING_COHORT = SPOT_COHORT
CAUTIOUS_SHADOW_MODEL_VERSION = 'cautious_shadow_v1'
CAUTIOUS_SHADOW_NEAR_MISS_RATIO = 0.80
CAUTIOUS_SHADOW_RISK_MULTIPLIER = 0.50
# ============================================================================
# COMMIT 37 — POLÍTICA CAUTIOUS GATE-LOCKED
# ============================================================================
#
# Commit 37 NO baja umbrales operativos y NO publica señales nuevas.
# Formaliza qué evidencia puede usarse para revisar una futura capa CAUTIOUS.
#
# Regla crítica post-36W:
# nunca mezclar scores LEGACY con los scores matemáticamente normalizados V2
# al decidir si existe edge suficiente para una revisión humana.
# ============================================================================
COMMIT37_POLICY_VERSION = 'commit37_gate_locked_v1'
COMMIT37_REQUIRED_QUALITY_SCORE_VERSION = '36W_V2_NORMALIZED'
COMMIT37_OBSERVATIONAL_REGIME = 'TRANSITION'
# ============================================================================
# QUALITY ENGINE Q3B — LEARNING BRIDGE
# ============================================================================
#
# Q3A observa microestructura pública gratuita de KuCoin Futures.
#
# Q3B NO consulta nuevamente ninguna API.
# Sólo persiste una fotografía compacta de:
#
# - Q1 Entry Quality / Reachability
# - Q2 Futures Execution Specialist
# - Q3 Microstructure Shadow
#
# para poder relacionarla posteriormente con:
#
# Entry tocado / TP / SL / Expired / Expectancy / PnL.
#
# Ninguno de estos datos adquiere autoridad operativa por ser persistido.
# ============================================================================

Q3B_LEARNING_SNAPSHOT_VERSION = (
    'Q3B_MICROSTRUCTURE_LEARNING_V1'
)
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
    # CONTRATO DE APRENDIZAJE — SEPARACIÓN SPOT / FUTUROS
    # ========================================================================

    @staticmethod
    def _as_bool(value) -> bool:
        """Convierte valores JSON comunes a booleano sin confundir 'false'."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'si', 'sí')
        return bool(value)

    @staticmethod
    def _normalize_system_type(system_type: str) -> str:
        value = str(system_type or '').strip().lower()
        return 'futures' if value == 'futures' else 'spot'

    def _build_learning_provenance(
        self,
        analysis: Dict,
        system_type: str
    ) -> Dict:
        """
        Guarda la procedencia necesaria para que una observación pueda auditarse.

        Una señal Futures sólo entra a estadísticas de rentabilidad cuando:
        - nació de velas reales del perpetuo;
        - la vela fuente estaba cerrada;
        - pasó el filtro de publicación EXECUTABLE_SIGNAL.

        Los análisis descartados se conservan como shadow para estudiar el filtro,
        pero no se presentan como si hubieran sido operaciones publicadas.
        """
        market = self._normalize_system_type(system_type)
        levels = analysis.get('levels', {}) or {}

        data_source = str(
            analysis.get('market_data_source')
            or levels.get('market_data_source')
            or ''
        ).strip().upper()
        is_synthetic = self._as_bool(
            analysis.get(
                'market_data_is_synthetic',
                levels.get('market_data_is_synthetic', False)
            )
        )
        analysis_version = str(
            analysis.get('analysis_version')
            or levels.get('analysis_version')
            or ''
        ).strip()
        source_closed = self._as_bool(
            analysis.get(
                'source_candle_closed',
                levels.get('source_candle_closed', False)
            )
        )
        source_timestamp = (
            analysis.get('source_candle_timestamp')
            or levels.get('source_candle_timestamp')
        )
        publication_status = str(
            analysis.get('publication_status')
            or levels.get('publication_status')
            or 'ANALYSIS_ONLY'
        ).strip().upper()
        publication_eligible = self._as_bool(
            analysis.get(
                'publication_eligible',
                levels.get('publication_eligible', False)
            )
        )

        clean_futures = bool(
            market == 'futures'
            and data_source == FUTURES_REAL_DATA_SOURCE
            and not is_synthetic
            and analysis_version == FUTURES_REAL_ANALYSIS_VERSION
            and source_closed
            and source_timestamp
        )

        if market == 'futures':
            cohort = (
                FUTURES_REAL_COHORT
                if clean_futures
                else FUTURES_LEGACY_COHORT
            )
            evaluation_role = (
                'EXECUTABLE_SIGNAL'
                if publication_status == 'EXECUTABLE_SIGNAL'
                and publication_eligible
                else 'SHADOW_ANALYSIS'
            )
            statistically_eligible = bool(
                clean_futures
                and evaluation_role == 'EXECUTABLE_SIGNAL'
            )
        else:
            spot_provenance = {
                'cohort': SPOT_LEARNING_COHORT, 'market_data_source': data_source,
                'market_data_is_synthetic': is_synthetic, 'analysis_version': analysis_version,
                'source_candle_closed': source_closed,
                'source_candle_timestamp': source_timestamp,
                'source_candle_close_timestamp': analysis.get('source_candle_close_timestamp'),
            }
            clean_spot = clean_spot_learning(spot_provenance)
            cohort = SPOT_LEARNING_COHORT if clean_spot else SPOT_LEGACY
            replay = analysis.get('analysis_mode') == 'PREVIOUS_CLOSED_CANDLE'
            evaluation_role = 'SPOT_PREVIOUS_REPLAY' if replay else 'SPOT_ACCUMULATION'
            statistically_eligible = bool(clean_spot and not replay)

        return {
            'contract_version': LEARNING_CONTRACT_VERSION,
            'system_type': market,
            'cohort': cohort,
            'evaluation_role': evaluation_role,
            'statistically_eligible': statistically_eligible,
            'market_data_source': data_source,
            'market_data_is_synthetic': is_synthetic,
            'analysis_version': analysis_version,
            'analysis_mode': str(
                analysis.get('analysis_mode')
                or levels.get('analysis_mode')
                or ''
            ),
            'source_candle_closed': source_closed,
            'source_candle_timestamp': (
                str(source_timestamp) if source_timestamp else None
            ),
            'source_candle_close_timestamp': analysis.get(
                'source_candle_close_timestamp'
            ),
            'signal_id': analysis.get('signal_id'),
            'publication_status': publication_status,
            'publication_eligible': publication_eligible,
            'futures_signal_tier': (
                analysis.get('futures_signal_tier')
                or levels.get('futures_signal_tier')
            ),
            'probability_status': (
                analysis.get('probability_status')
                or levels.get('probability_status')
            )
        }
# ============================================================================
# BLOQUE B — MÉTODOS DE ReviewTrader
# Pegar dentro de class ReviewTrader, justo después de _build_learning_provenance()
# y antes de _get_signal_learning().
# ============================================================================

    @staticmethod
    def _publication_reason_code(reason: str) -> str:
        text = str(reason or '').strip().lower()

        if 'safety' in text:
            return 'SAFETY'

        if (
            'calidad tp' in text
            or 'tp quality' in text
        ):
            return 'TP_QUALITY'

        if (
            'protección sl' in text
            or 'proteccion sl' in text
            or 'sl quality' in text
        ):
            return 'SL_QUALITY'

        if (
            'r/r' in text
            or 'risk/reward' in text
            or 'risk_reward' in text
        ):
            return 'RR'

        if 'roi tp' in text:
            return 'ROI_TP'

        if (
            'beneficio neto' in text
            or 'net profit' in text
        ):
            return 'NET_PROFIT'

        if (
            'pérdida estimada en sl' in text
            or 'perdida estimada en sl' in text
            or 'loss at sl' in text
        ):
            return 'LOSS_AT_SL'

        if (
            'estrés atr' in text
            or 'estres atr' in text
            or 'atr stress' in text
        ):
            return 'ATR_STRESS'

        return 'OTHER'


    @staticmethod
    def _pre_gate_rejection_code(reason: str) -> str:
        """Clasifica rechazos exactos ocurridos ANTES del gate Premium."""
        text = str(reason or '').strip().lower()

        if 'safety' in text:
            return 'HARD_SAFETY'

        if (
            'no existe leverage' in text
            or 'leverage recomendado' in text
            or 'leverage' in text
        ):
            return 'LEVERAGE_VIABILITY'

        if (
            'roi potencial' in text
            or 'roi tp' in text
        ):
            return 'ROI_TP'

        if (
            'beneficio neto' in text
            or 'net profit' in text
        ):
            return 'NET_PROFIT'

        if (
            'pérdida' in text
            or 'perdida' in text
        ) and 'sl' in text:
            return 'LOSS_AT_SL'

        if (
            'atr' in text
            and (
                'estrés' in text
                or 'estres' in text
                or 'stress' in text
            )
        ):
            return 'ATR_STRESS'

        return 'PRE_GATE_OTHER'


    def _build_futures_pre_gate_rejection_snapshot(
        self,
        analysis: Dict
    ) -> Dict:
        """
        Conserva el motivo EXACTO por el que Futures salió ANALYSIS_ONLY
        antes de llegar a _apply_futures_publication_gate().

        Este snapshot NO es un publication gate y NO cambia decisiones.
        Sirve para distinguir:

            PRE_GATE_REJECTION
                vs
            PUBLICATION_GATE_REJECTION

        sin inventar backfill histórico.
        """
        levels = (
            analysis.get(
                'levels',
                {}
            )
            or {}
        )

        reason = (
            analysis.get('rejected_reason')
            or analysis.get('non_executable_reason')
            or levels.get('rejected_reason')
            or levels.get('non_executable_reason')
            or ''
        )

        reason = str(reason or '').strip()

        if not reason:
            return {}

        # Si existe gate Premium, este rechazo pertenece al gate y no al pre-gate.
        if (
            analysis.get('futures_publication_gate')
            or levels.get('futures_publication_gate')
        ):
            return {}

        return {
            'stage': 'PRE_PUBLICATION',
            'exact': True,
            'reason': reason[:220],
            'reason_code': self._pre_gate_rejection_code(reason),
            'publication_status': str(
                analysis.get('publication_status')
                or levels.get('publication_status')
                or 'ANALYSIS_ONLY'
            ).strip().upper(),
            'is_executable': self._as_bool(
                analysis.get(
                    'is_executable',
                    levels.get('is_executable', False)
                )
            ),
            'affects_publication': False,
            'affects_weights': False,
            'diagnostic_only': True
        }


    def _build_futures_publication_snapshot(
        self,
        analysis: Dict
    ) -> Dict:
        """
        Copia el publication gate EXACTO calculado por Futures.

        No recalcula la decisión y no modifica analysis.
        """

        levels = (
            analysis.get(
                'levels',
                {}
            )
            or {}
        )

        raw_gate = (
            analysis.get(
                'futures_publication_gate'
            )
            or levels.get(
                'futures_publication_gate'
            )
            or {}
        )

        if not isinstance(
            raw_gate,
            dict
        ) or not raw_gate:

            return {}

        raw_reasons = (
            raw_gate.get(
                'reasons'
            )
            or []
        )

        if not isinstance(
            raw_reasons,
            (list, tuple)
        ):

            raw_reasons = [
                raw_reasons
            ]

        reasons = [
            str(reason)[:180]
            for reason
            in raw_reasons[:8]
            if str(reason or '').strip()
        ]

        reason_codes = []

        for reason in reasons:

            code = (
                self._publication_reason_code(
                    reason
                )
            )

            if code not in reason_codes:

                reason_codes.append(
                    code
                )

        raw_thresholds = (
            raw_gate.get(
                'thresholds'
            )
            or {}
        )

        if not isinstance(
            raw_thresholds,
            dict
        ):

            raw_thresholds = {}

        thresholds = {}

        for key, value in raw_thresholds.items():

            try:

                number = float(
                    value
                )

                if math.isfinite(
                    number
                ):

                    thresholds[
                        str(key)
                    ] = number

            except (
                TypeError,
                ValueError
            ):
                continue

        def optional_float(
            value
        ):

            try:

                number = float(
                    value
                )

                if math.isfinite(
                    number
                ):

                    return number

            except (
                TypeError,
                ValueError
            ):
                pass

            return None

        eligible = (
            self._as_bool(
                raw_gate.get(
                    'eligible',
                    False
                )
            )
        )

        return {
            'eligible':
                eligible,

            'tier':
                str(
                    raw_gate.get(
                        'tier'
                    )
                    or (
                        'PREMIUM'
                        if eligible
                        else 'ANALYSIS_ONLY'
                    )
                ),

            'rejection_count':
                len(
                    reasons
                ),

            'reason_codes':
                reason_codes,

            'reasons':
                reasons,

            'tp_touch_quality_score':
                optional_float(
                    raw_gate.get(
                        'tp_touch_quality_score'
                    )
                ),

            'sl_avoidance_quality_score':
                optional_float(
                    raw_gate.get(
                        'sl_avoidance_quality_score'
                    )
                ),

            'preferred_leverage_min':
                optional_float(
                    raw_gate.get(
                        'preferred_leverage_min'
                    )
                ),

            'preferred_leverage_max':
                optional_float(
                    raw_gate.get(
                        'preferred_leverage_max'
                    )
                ),

            'leverage_in_preferred_band':
                self._as_bool(
                    raw_gate.get(
                        'leverage_in_preferred_band',
                        False
                    )
                ),

            'probability_status':
                str(
                    raw_gate.get(
                        'probability_status'
                    )
                    or ''
                ),

            'thresholds':
                thresholds
        }


    def _build_cautious_shadow_profile(
        self,
        analysis: Dict,
        learning: Dict,
        publication: Dict
    ) -> Dict:
        """
        Commit 35 — experimento CAUTIOUS_SHADOW.

        REGLA ABSOLUTA:
        este resultado sólo sirve para aprendizaje SHADOW.
        Nunca puede publicar una señal ni modificar Entry/SL/TP/leverage/pesos.

        Candidato v1:
        - Futures real + vela cerrada;
        - ya fue rechazado por el gate PREMIUM;
        - LONG/SHORT con geometría válida;
        - TODOS los filtros duros de riesgo/economía pasan;
        - los únicos bloqueos exactos son SAFETY y/o TP_QUALITY;
        - Safety y TP Quality están al menos al 80% del umbral premium.

        Riesgo simulado:
        - 0.50x del riesgo monetario/margen;
        - NO cambia el leverage técnico ni los niveles originales.
        """

        base = {
            'model_version':
                CAUTIOUS_SHADOW_MODEL_VERSION,

            'mode':
                'SHADOW_ONLY',

            'candidate':
                False,

            'status':
                'NOT_APPLICABLE',

            'simulated_risk_multiplier':
                CAUTIOUS_SHADOW_RISK_MULTIPLIER,

            'simulated_margin_multiplier':
                CAUTIOUS_SHADOW_RISK_MULTIPLIER,

            'near_miss_ratio':
                CAUTIOUS_SHADOW_NEAR_MISS_RATIO,

            'affects_publication':
                False,

            'affects_weights':
                False,

            'affects_entry':
                False,

            'affects_stop_loss':
                False,

            'affects_take_profit':
                False,

            'affects_leverage':
                False,

            'reason_codes':
                [],

            'failed_guardrails':
                [],

            'metrics':
                {}
        }

        if str(
            learning.get(
                'system_type',
                ''
            )
        ).lower() != 'futures':

            return base

        if (
            learning.get(
                'cohort'
            )
            != FUTURES_REAL_COHORT
        ):

            return {
                **base,
                'status':
                    'UNVERIFIED_FUTURES'
            }

        if (
            learning.get(
                'evaluation_role'
            )
            != 'SHADOW_ANALYSIS'
        ):

            return {
                **base,
                'status':
                    'NOT_SHADOW'
            }

        decision = (
            analysis.get(
                'decision',
                {}
            )
            or {}
        )

        action = str(
            decision.get(
                'action',
                ''
            )
            or ''
        ).upper()

        if action not in (
            'LONG',
            'SHORT'
        ):

            return {
                **base,
                'status':
                    'NOT_DIRECTIONAL'
            }

        levels = (
            analysis.get(
                'levels',
                {}
            )
            or {}
        )

        def safe_float(
            value,
            default=None
        ):

            try:

                number = float(
                    value
                )

                if math.isfinite(
                    number
                ):

                    return number

            except (
                TypeError,
                ValueError
            ):
                pass

            return default

        entry = safe_float(
            levels.get(
                'entry'
            )
        )

        sl = safe_float(
            levels.get(
                'stop_loss'
            )
        )

        tp = safe_float(
            levels.get(
                'take_profit'
            )
        )

        if not all(
            value is not None
            and value > 0
            for value
            in (
                entry,
                sl,
                tp
            )
        ):

            return {
                **base,
                'status':
                    'INVALID_GEOMETRY'
            }

        if (
            action == 'LONG'
            and not (
                sl < entry < tp
            )
        ):

            return {
                **base,
                'status':
                    'INVALID_GEOMETRY'
            }

        if (
            action == 'SHORT'
            and not (
                tp < entry < sl
            )
        ):

            return {
                **base,
                'status':
                    'INVALID_GEOMETRY'
            }

        if not isinstance(
            publication,
            dict
        ) or not publication:

            pre_gate = (
                learning.get(
                    'pre_gate_rejection'
                )
                or {}
            )

            if isinstance(
                pre_gate,
                dict
            ) and pre_gate:

                reason_code = str(
                    pre_gate.get(
                        'reason_code'
                    )
                    or 'PRE_GATE_OTHER'
                ).strip().upper()

                return {
                    **base,
                    'status':
                        'PRE_GATE_REJECTION',
                    'reason_codes': [
                        reason_code
                    ],
                    'failed_guardrails': [
                        reason_code
                    ]
                }

            return {
                **base,
                'status':
                    'MISSING_PUBLICATION_GATE'
            }

        if self._as_bool(
            publication.get(
                'eligible',
                False
            )
        ):

            return {
                **base,
                'status':
                    'PREMIUM_NOT_CAUTIOUS'
            }

        thresholds = (
            publication.get(
                'thresholds'
            )
            or {}
        )

        required_thresholds = (
            'execution_safety_min',
            'tp_quality_min',
            'sl_avoidance_quality_min',
            'risk_reward_min',
            'risk_reward_max',
            'roi_tp_min',
            'net_profit_min_usdt',
            'loss_at_sl_max_pct_margin',
            'atr_stress_loss_max_pct_margin'
        )

        if not all(
            key in thresholds
            for key
            in required_thresholds
        ):

            return {
                **base,
                'status':
                    'MISSING_THRESHOLDS'
            }

        safety = safe_float(
            levels.get(
                'execution_safety',
                levels.get(
                    'execution_safety_score'
                )
            ),
            0.0
        )

        tp_quality = safe_float(
            publication.get(
                'tp_touch_quality_score'
            ),
            safe_float(
                levels.get(
                    'tp_quality_score'
                ),
                0.0
            )
        )

        sl_quality = safe_float(
            publication.get(
                'sl_avoidance_quality_score'
            )
        )

        if sl_quality is None:

            sl_quality = safe_float(
                levels.get(
                    'sl_reliability'
                ),
                0.0
            )

            if (
                sl_quality is not None
                and sl_quality <= 1.0
            ):

                sl_quality *= 100.0

        rr = safe_float(
            levels.get(
                'risk_reward'
            ),
            0.0
        )

        roi_tp = safe_float(
            levels.get(
                'roi_tp'
            ),
            0.0
        )

        roi_sl_abs = abs(
            safe_float(
                levels.get(
                    'roi_sl'
                ),
                0.0
            )
        )

        net_profit = safe_float(
            levels.get(
                'net_profit_tp_usdt'
            ),
            0.0
        )

        risk_control = (
            levels.get(
                'risk_control',
                {}
            )
            or {}
        )

        atr_stress = safe_float(
            risk_control.get(
                'estimated_atr_stress_loss_pct_margin'
            ),
            0.0
        )

        hard_checks = {
            'SL_QUALITY':
                (
                    sl_quality
                    >= float(
                        thresholds[
                            'sl_avoidance_quality_min'
                        ]
                    )
                ),

            'RR':
                (
                    float(
                        thresholds[
                            'risk_reward_min'
                        ]
                    )
                    <= rr
                    <= float(
                        thresholds[
                            'risk_reward_max'
                        ]
                    )
                ),

            'ROI_TP':
                (
                    roi_tp
                    >= float(
                        thresholds[
                            'roi_tp_min'
                        ]
                    )
                ),

            'NET_PROFIT':
                (
                    net_profit
                    >= float(
                        thresholds[
                            'net_profit_min_usdt'
                        ]
                    )
                ),

            'LOSS_AT_SL':
                (
                    roi_sl_abs
                    <= float(
                        thresholds[
                            'loss_at_sl_max_pct_margin'
                        ]
                    )
                ),

            'ATR_STRESS':
                (
                    atr_stress > 0
                    and atr_stress
                    <= float(
                        thresholds[
                            'atr_stress_loss_max_pct_margin'
                        ]
                    )
                )
        }

        failed_guardrails = [
            name
            for name, passed
            in hard_checks.items()
            if not passed
        ]

        reason_codes = [
            str(code).upper()
            for code
            in (
                publication.get(
                    'reason_codes'
                )
                or []
            )
            if str(
                code
                or ''
            ).strip()
        ]

        reason_set = set(
            reason_codes
        )

        soft_only = bool(
            reason_set
        ) and reason_set.issubset({
            'SAFETY',
            'TP_QUALITY'
        })

        safety_threshold = float(
            thresholds[
                'execution_safety_min'
            ]
        )

        tp_threshold = float(
            thresholds[
                'tp_quality_min'
            ]
        )

        minimum_cautious_safety = (
            safety_threshold
            * CAUTIOUS_SHADOW_NEAR_MISS_RATIO
        )

        minimum_cautious_tp = (
            tp_threshold
            * CAUTIOUS_SHADOW_NEAR_MISS_RATIO
        )

        near_miss = (
            safety
            >= minimum_cautious_safety
            and tp_quality
            >= minimum_cautious_tp
        )

        candidate = bool(
            not failed_guardrails
            and soft_only
            and near_miss
        )

        status = (
            'CAUTIOUS_SHADOW'
            if candidate
            else 'REJECTED_SHADOW'
        )

        return {
            **base,

            'candidate':
                candidate,

            'status':
                status,

            'reason_codes':
                reason_codes,

            'failed_guardrails':
                failed_guardrails,

            'metrics': {
                'execution_safety':
                    round(
                        safety,
                        3
                    ),

                'minimum_cautious_safety':
                    round(
                        minimum_cautious_safety,
                        3
                    ),

                'premium_safety_threshold':
                    round(
                        safety_threshold,
                        3
                    ),

                'tp_quality':
                    round(
                        tp_quality,
                        3
                    ),

                'minimum_cautious_tp_quality':
                    round(
                        minimum_cautious_tp,
                        3
                    ),

                'premium_tp_quality_threshold':
                    round(
                        tp_threshold,
                        3
                    ),

                'sl_quality':
                    round(
                        sl_quality,
                        3
                    ),

                'risk_reward':
                    round(
                        rr,
                        4
                    ),

                'roi_tp':
                    round(
                        roi_tp,
                        4
                    ),

                'roi_sl_abs':
                    round(
                        roi_sl_abs,
                        4
                    ),

                'net_profit_tp_usdt':
                    round(
                        net_profit,
                        4
                    ),

                'atr_stress_loss_pct_margin':
                    round(
                        atr_stress,
                        4
                    ),

                'original_leverage':
                    safe_float(
                        levels.get(
                            'leverage'
                        ),
                        0.0
                    )
            }
        }

    @staticmethod
    def _get_signal_context(signal: Dict) -> Dict:
        """
        COMMIT 36W

        Devuelve context como dict aunque Supabase lo entregue
        como JSON serializado.

        No modifica ninguna señal.
        """
        context = (
            signal.get(
                'context',
                {}
            )
            or {}
        )

        if isinstance(
            context,
            str
        ):
            try:
                context = json.loads(
                    context
                )

            except Exception:
                return {}

        return (
            context
            if isinstance(
                context,
                dict
            )
            else {}
        )


    @staticmethod
    def _get_signal_learning(signal: Dict) -> Dict:
        context = (
            ReviewTrader
            ._get_signal_context(
                signal
            )
        )

        learning = (
            context.get(
                'learning',
                {}
            )
            or {}
        )

        return (
            learning
            if isinstance(
                learning,
                dict
            )
            else {}
        )

    def _is_clean_futures_signal(self, signal: Dict) -> bool:
        if self._normalize_system_type(
            signal.get('system_type')
        ) != 'futures':
            return False

        learning = self._get_signal_learning(signal)
        return bool(
            learning.get('contract_version') == LEARNING_CONTRACT_VERSION
            and learning.get('cohort') == FUTURES_REAL_COHORT
            and str(learning.get('market_data_source', '')).upper()
            == FUTURES_REAL_DATA_SOURCE
            and not self._as_bool(
                learning.get('market_data_is_synthetic', True)
            )
            and self._as_bool(
                learning.get('source_candle_closed', False)
            )
        )

    def _is_signal_eligible_for_profit_stats(self, signal: Dict) -> bool:
        market = self._normalize_system_type(signal.get('system_type'))
        if market == 'spot':
            return verified_spot(signal)

        if not self._is_clean_futures_signal(signal):
            return False

        learning = self._get_signal_learning(signal)
        return bool(
            self._as_bool(learning.get('statistically_eligible', False))
            and learning.get('evaluation_role') == 'EXECUTABLE_SIGNAL'
        )

    @staticmethod
    def _scoped_action(action: str, system_type: str) -> str:
        """Usa la columna action existente para evitar mezclar ambos mercados."""
        normalized = str(action or '').strip().upper()
        if str(system_type or '').strip().lower() == 'futures':
            return f'FUTURES_{normalized}'
        return normalized

    @staticmethod
    def _scope_from_action(action: str) -> str:
        return (
            'futures'
            if str(action or '').upper().startswith('FUTURES_')
            else 'spot'
        )

    @staticmethod
    def _general_strategy_key(strategy: str, system_type: str) -> str:
        strategy = str(strategy or '').strip().upper()
        if str(system_type or '').strip().lower() == 'futures':
            return f'FUTURES::{strategy}'
        return strategy

    def _fetch_market_data_for_signal(
        self,
        signal: Dict,
        price_fetcher
    ):
        """
        Spot usa el proveedor recibido por app.py. Futuros ignora ese proveedor
        porque históricamente apunta al endpoint Spot y consulta su motor real.
        """
        symbol = signal.get('symbol')
        timeframe = signal.get('timeframe')
        market = self._normalize_system_type(signal.get('system_type'))

        if market == 'spot':
            if not verified_spot(signal):
                return None, 'SPOT_LEGACY_QUARANTINED'
            try:
                from q6_integrity import prepare_spot_frame, SPOT_SOURCE
                df = prepare_spot_frame(price_fetcher(symbol, timeframe),
                                        timeframe, check_fresh=False)
                return df, SPOT_SOURCE
            except Exception:
                return None, 'SPOT_SOURCE_REJECTED'

        if not self._is_clean_futures_signal(signal):
            return None, 'FUTURES_LEGACY_QUARANTINED'

        try:
            # Importación diferida para no crear un ciclo durante el arranque.
            from futures_system import futures_system as futures_engine

            df = futures_engine.get_kucoin_data(symbol, timeframe)
            if df is None or len(df) == 0:
                return None, 'FUTURES_PROVIDER_EMPTY'

            attrs = getattr(df, 'attrs', {}) or {}
            source = str(
                attrs.get('market_data_source', '')
            ).strip().upper()
            synthetic = self._as_bool(
                attrs.get('market_data_is_synthetic', True)
            )
            if source != FUTURES_REAL_DATA_SOURCE or synthetic:
                logger.error(
                    'Velas Futures rechazadas por procedencia: '
                    f'{symbol} {timeframe} source={source or "UNKNOWN"} '
                    f'synthetic={synthetic}'
                )
                return None, 'FUTURES_SOURCE_REJECTED'

            return df, FUTURES_REAL_DATA_SOURCE

        except Exception as exc:
            logger.error(
                f'No se pudieron obtener velas perpetuas reales para '
                f'{symbol} {timeframe}: {exc}'
            )
            return None, 'FUTURES_PROVIDER_ERROR'
    
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
            # Extraer el timestamp de la vela que realmente originó
            # la señal. Las versiones nuevas lo enviarán explícitamente;
            # las versiones antiguas siguen usando el fallback histórico.
            candle_ts = self._get_previous_candle_timestamp(analysis_result)
            
            # Extraer estrategias detectadas por los traders
            strategies = self._extract_strategies(analysis_result)
            
            # Extraer snapshot de indicadores
            indicators = self._extract_indicators_snapshot(analysis_result)
            
            # Extraer contexto (sesión, día, sentimiento, etc.)
# ============================================================================
# BLOQUE C — register_signal()
#
# Buscar:
#
# context = self._extract_context(analysis_result)
# context['learning'] = self._build_learning_provenance(
#     analysis_result,
#     system_type
# )
#
# Reemplazar SOLO ese bloque por:
# ============================================================================

            context = self._extract_context(
                analysis_result
            )

            existing_learning = (
                context.get(
                    'learning',
                    {}
                )
                or {}
            )

            if not isinstance(
                existing_learning,
                dict
            ):

                existing_learning = {}

            learning = dict(
                existing_learning
            )

            learning.update(
                self._build_learning_provenance(
                    analysis_result,
                    system_type
                )
            )

            context[
                'learning'
            ] = learning

            # ==========================================================
            # COMMIT 2 — STRATEGY ATTRIBUTION V2
            # ==========================================================
            # Preserva qué trader emitió cada estrategia, en qué
            # dirección votó y si apoyó o contradijo la decisión final.
            # Es diagnóstico puro: no modifica votos ni confianza.
            # ==========================================================
            try:
                strategy_attribution = build_strategy_attribution_v2(
                    analysis_result,
                    system_type
                )
                context['learning']['strategy_attribution_v2'] = (
                    strategy_attribution
                )
            except Exception as attribution_error:
                logger.warning(
                    'Strategy Attribution V2 no disponible: %s',
                    attribution_error
                )

            # ==========================================================
            # COMMIT 11 — PERSISTIR TESIS DE ESPECIALISTAS
            # ==========================================================
            # La tesis fue construida DESPUÉS del consenso. Guardarla permite
            # medir abstención, especialización y calibración sin recalcular
            # ni cambiar una señal histórica.
            runtime_intelligence = analysis_result.get('trader_intelligence_v2')
            if isinstance(runtime_intelligence, dict):
                context['learning']['trader_intelligence_v2'] = runtime_intelligence

            dynamic_shadow = (
                ((analysis_result.get('decision') or {}).get('registro_votacion') or {})
                .get('dynamic_expert_committee_shadow')
                if isinstance((analysis_result.get('decision') or {}).get('registro_votacion'), dict)
                else None
            )
            if isinstance(dynamic_shadow, dict):
                context['learning']['dynamic_expert_committee_shadow'] = dynamic_shadow

            challenger_lab = analysis_result.get('execution_challenger_lab')
            if isinstance(challenger_lab, dict):
                context['learning']['execution_challenger_lab'] = challenger_lab

            # Commit 15E — lightweight uncertainty/conformal foundation.
            # Persist only scalars/labels already computed by Futures; no new
            # market query and no production authority.
            uncertainty_shadow = analysis_result.get('uncertainty_shadow_gate')
            if isinstance(uncertainty_shadow, dict) and uncertainty_shadow:
                context['learning']['uncertainty_shadow'] = {
                    'version': str(uncertainty_shadow.get('version') or '')[:100],
                    'authority': 'SHADOW_ONLY',
                    'method': str(uncertainty_shadow.get('method') or '')[:80],
                    'conformal_status': str(uncertainty_shadow.get('conformal_status') or '')[:80],
                    'calibrated': self._as_bool(uncertainty_shadow.get('calibrated', False)),
                    'uncertainty_score': uncertainty_shadow.get('uncertainty_score'),
                    'uncertainty_bucket': str(uncertainty_shadow.get('uncertainty_bucket') or 'UNAVAILABLE')[:20],
                    'shadow_gate': str(uncertainty_shadow.get('shadow_gate') or 'UNAVAILABLE')[:40],
                    'components': dict(uncertainty_shadow.get('components') or {}),
                    'affects_entry': False,
                    'affects_safety': False,
                    'affects_publication': False,
                    'affects_leverage': False,
                }

            if self._as_bool(analysis_result.get('research_only', False)):
                context['learning']['research_only_universe'] = {
                    'version': 'C15_RESEARCH_UNIVERSE_V1',
                    'research_only': True,
                    'universe': str(analysis_result.get('research_universe') or 'C15_LINK_BNB_SHADOW')[:80],
                    'affects_official_kpis': False,
                    'affects_publication': False,
                }

            if (
                self._normalize_system_type(
                    system_type
                )
                == 'futures'
            ):

                publication = (
                    self._build_futures_publication_snapshot(
                        analysis_result
                    )
                )

                if publication:

                    context[
                        'futures_publication'
                    ] = publication

                else:

                    pre_gate_rejection = (
                        self._build_futures_pre_gate_rejection_snapshot(
                            analysis_result
                        )
                    )

                    if pre_gate_rejection:

                        context[
                            'learning'
                        ][
                            'pre_gate_rejection'
                        ] = pre_gate_rejection

                context[
                    'learning'
                ][
                    'cautious_shadow'
                ] = (
                    self._build_cautious_shadow_profile(
                        analysis_result,
                        context[
                            'learning'
                        ],
                        publication
                    )
                )

            # ==============================================================
            # FUTURES QUANTITATIVE SHADOW — SNAPSHOT PARA APRENDIZAJE
            # ==============================================================
            #
            # Sólo guarda una copia compacta del contexto cuantitativo que ya
            # calculó futures_system.py.
            #
            # IMPORTANTE:
            # - NO recalcula mercado.
            # - NO modifica votos.
            # - NO modifica la decisión.
            # - NO modifica Entry, SL o TP.
            # - NO modifica leverage.
            # - NO modifica Execution Safety.
            # - NO modifica publication_status.
            #
            # Su única función es permitir relacionar posteriormente el
            # contexto cuantitativo original con el resultado real de la señal.
            # ==============================================================

            if self._normalize_system_type(system_type) == 'futures':

                raw_quant = analysis_result.get(
                    'futures_quantitative_context'
                ) or {}

                if isinstance(raw_quant, dict) and raw_quant:

                    raw_metrics = raw_quant.get(
                        'metrics'
                    ) or {}

                    if not isinstance(
                        raw_metrics,
                        dict
                    ):
                        raw_metrics = {}

                    raw_reasons = raw_quant.get(
                        'reasons'
                    ) or []

                    if not isinstance(
                        raw_reasons,
                        (list, tuple)
                    ):
                        raw_reasons = [
                            raw_reasons
                        ]

                    def _optional_float(value):
                        try:
                            number = float(
                                value
                            )

                            return (
                                number
                                if math.isfinite(
                                    number
                                )
                                else None
                            )

                        except (
                            TypeError,
                            ValueError
                        ):
                            return None

                    context[
                        'learning'
                    ][
                        'quantitative_shadow'
                    ] = {

                        'available':
                            self._as_bool(
                                raw_quant.get(
                                    'available',
                                    False
                                )
                            ),

                        'model_version':
                            str(
                                raw_quant.get(
                                    'model_version'
                                ) or ''
                            ),

                        'mode':
                            str(
                                raw_quant.get(
                                    'mode'
                                ) or ''
                            ),

                        'status':
                            str(
                                raw_quant.get(
                                    'status'
                                ) or ''
                            ),

                        'data_scope':
                            str(
                                raw_quant.get(
                                    'data_scope'
                                ) or ''
                            ),

                        'calibrated':
                            self._as_bool(
                                raw_quant.get(
                                    'calibrated',
                                    False
                                )
                            ),

                        'affects_publication':
                            self._as_bool(
                                raw_quant.get(
                                    'affects_publication',
                                    False
                                )
                            ),

                        'quality_score_status':
                            str(
                                raw_quant.get(
                                    'quality_score_status'
                                ) or ''
                            ),

                        'regime':
                            str(
                                raw_quant.get(
                                    'regime'
                                ) or 'UNAVAILABLE'
                            ),

                        'direction':
                            str(
                                raw_quant.get(
                                    'direction'
                                ) or 'NEUTRAL'
                            ),

                        'direction_alignment':
                            str(
                                raw_quant.get(
                                    'direction_alignment'
                                )
                                or 'NOT_APPLICABLE'
                            ),

                        'entry_location':
                            str(
                                raw_quant.get(
                                    'entry_location'
                                )
                                or 'UNAVAILABLE'
                            ),

                        'shadow_verdict':
                            str(
                                raw_quant.get(
                                    'shadow_verdict'
                                )
                                or 'UNAVAILABLE'
                            ),

                        'quality_score':
                            _optional_float(
                                raw_quant.get(
                                    'quality_score'
                                )
                            ),

                        'reasons': [
                            str(
                                item
                            )[:180]
                            for item
                            in raw_reasons[:6]
                        ],

                        'metrics': {

                            key:
                                _optional_float(
                                    raw_metrics.get(
                                        key
                                    )
                                )

                            for key in (

                                'source_price',

                                'latest_return_pct',

                                'return_anomaly_robust_z',

                                'directional_efficiency_ratio',

                                'trend_move_pct',

                                'drift_strength',

                                'return_autocorrelation_lag1',

                                'realized_volatility_fast_pct',

                                'realized_volatility_slow_pct',

                                'fast_slow_volatility_ratio',

                                'volatility_percentile',

                                'atr_pct',

                                'entry_distance_atr',

                                'entry_pullback_signed_atr',
                            )
                        }
                    }            
            # ==============================================================
            # QUALITY ENGINE Q3B
            # MICROESTRUCTURA FUTURES → APRENDIZAJE PROSPECTIVO
            # ==============================================================
            #
            # Q3A ya consultó los endpoints públicos de KuCoin.
            #
            # Q3B:
            #
            # - NO hace otra llamada HTTP;
            # - NO recalcula order book;
            # - NO modifica la decisión;
            # - NO modifica Entry;
            # - NO modifica SL;
            # - NO modifica TP;
            # - NO modifica leverage;
            # - NO modifica Safety;
            # - NO modifica publication_status;
            # - NO modifica pesos del comité.
            #
            # Sólo guarda una fotografía compacta para que, cuando esta
            # misma señal termine en TP / SL / Expired, podamos medir si
            # ALIGNED / NEUTRAL / CONFLICT tenía realmente valor predictivo.
            # ==============================================================

            if (
                self._normalize_system_type(
                    system_type
                )
                == 'futures'
            ):

                raw_micro = (
                    analysis_result.get(
                        'futures_microstructure_context'
                    )
                    or {}
                )

                if isinstance(
                    raw_micro,
                    dict
                ) and raw_micro:

                    raw_micro_metrics = (
                        raw_micro.get(
                            'metrics'
                        )
                        or {}
                    )

                    if not isinstance(
                        raw_micro_metrics,
                        dict
                    ):

                        raw_micro_metrics = {}

                    raw_micro_reasons = (
                        raw_micro.get(
                            'reasons'
                        )
                        or []
                    )

                    if not isinstance(
                        raw_micro_reasons,
                        (list, tuple)
                    ):

                        raw_micro_reasons = [
                            raw_micro_reasons
                        ]

                    raw_source_status = (
                        raw_micro.get(
                            'source_status'
                        )
                        or {}
                    )

                    if not isinstance(
                        raw_source_status,
                        dict
                    ):

                        raw_source_status = {}

                    raw_sources = (
                        raw_source_status.get(
                            'sources_available'
                        )
                        or []
                    )

                    if not isinstance(
                        raw_sources,
                        (list, tuple)
                    ):

                        raw_sources = [
                            raw_sources
                        ]

                    raw_source_errors = (
                        raw_source_status.get(
                            'source_errors'
                        )
                        or []
                    )

                    if not isinstance(
                        raw_source_errors,
                        (list, tuple)
                    ):

                        raw_source_errors = [
                            raw_source_errors
                        ]

                    def _micro_optional_float(
                        value
                    ):
                        try:
                            number = float(
                                value
                            )

                            return (
                                number
                                if math.isfinite(
                                    number
                                )
                                else None
                            )

                        except (
                            TypeError,
                            ValueError
                        ):
                            return None

                    context[
                        'learning'
                    ][
                        'microstructure_shadow'
                    ] = {
                        # ==============================================
                        # VERSIONADO
                        # ==============================================

                        'snapshot_version':
                            Q3B_LEARNING_SNAPSHOT_VERSION,

                        'model_version':
                            str(
                                raw_micro.get(
                                    'model_version',
                                    ''
                                )
                                or ''
                            ),

                        # ==============================================
                        # ESTADO
                        # ==============================================

                        'available':
                            self._as_bool(
                                raw_micro.get(
                                    'available',
                                    False
                                )
                            ),

                        'status':
                            str(
                                raw_micro.get(
                                    'status',
                                    'UNAVAILABLE'
                                )
                                or 'UNAVAILABLE'
                            ),

                        'mode':
                            str(
                                raw_micro.get(
                                    'mode',
                                    'SHADOW_OBSERVATION'
                                )
                                or 'SHADOW_OBSERVATION'
                            ),

                        'calibrated':
                            self._as_bool(
                                raw_micro.get(
                                    'calibrated',
                                    False
                                )
                            ),

                        'quality_score_status':
                            str(
                                raw_micro.get(
                                    'quality_score_status',
                                    'UNVALIDATED'
                                )
                                or 'UNVALIDATED'
                            ),

                        # ==============================================
                        # ACCIÓN + VEREDICTO
                        # ==============================================

                        'action_evaluated':
                            str(
                                raw_micro.get(
                                    'action_evaluated',
                                    ''
                                )
                                or ''
                            ).upper(),

                        'alignment':
                            str(
                                raw_micro.get(
                                    'alignment',
                                    'NOT_APPLICABLE'
                                )
                                or 'NOT_APPLICABLE'
                            ).upper(),

                        'alignment_score':
                            _micro_optional_float(
                                raw_micro.get(
                                    'alignment_score'
                                )
                            ),

                        'shadow_verdict':
                            str(
                                raw_micro.get(
                                    'shadow_verdict',
                                    'UNAVAILABLE'
                                )
                                or 'UNAVAILABLE'
                            ).upper(),

                        # ==============================================
                        # GUARDRAILS
                        # ==============================================
                        #
                        # Estos False son IMPORTANTES.
                        #
                        # Incluso aunque la microestructura diga ALIGNED,
                        # Q3B no adquiere autoridad operativa.
                        # ==============================================

                        'affects_entry':
                            False,

                        'affects_safety':
                            False,

                        'affects_publication':
                            False,

                        'affects_leverage':
                            False,

                        # ==============================================
                        # RAZONES COMPACTAS
                        # ==============================================

                        'reasons': [
                            str(
                                reason
                            )[:140]

                            for reason
                            in raw_micro_reasons[:6]

                            if str(
                                reason
                                or ''
                            ).strip()
                        ],

                        # ==============================================
                        # MÉTRICAS Q3
                        # ==============================================

                        'metrics': {
                            'orderbook_imbalance':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'orderbook_imbalance'
                                    )
                                ),

                            'spread_pct':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'spread_pct'
                                    )
                                ),

                            'recent_buy_share':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'recent_buy_share'
                                    )
                                ),

                            'recent_buy_sell_ratio':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'recent_buy_sell_ratio'
                                    )
                                ),

                            'oi_change_pct':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'oi_change_pct'
                                    )
                                ),

                            'funding_rate':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'funding_rate'
                                    )
                                ),

                            'basis_pct':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'basis_pct'
                                    )
                                ),

                            'liquidity_band':
                                str(
                                    raw_micro_metrics.get(
                                        'liquidity_band'
                                    )
                                    or 'NO_DATA'
                                )[:20],

                            'liquidity_score':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'liquidity_score'
                                    )
                                ),

                            'source_count':
                                _micro_optional_float(
                                    raw_micro_metrics.get(
                                        'source_count'
                                    )
                                )
                        },

                        # ==============================================
                        # AUDITORÍA DE FUENTE
                        # ==============================================

                        'source_status': {
                            'sources_available': [
                                str(
                                    source
                                )[:80]

                                for source
                                in raw_sources[:6]

                                if str(
                                    source
                                    or ''
                                ).strip()
                            ],

                            'source_errors': [
                                str(
                                    error
                                )[:160]

                                for error
                                in raw_source_errors[:4]

                                if str(
                                    error
                                    or ''
                                ).strip()
                            ],

                            'cache_hit':
                                self._as_bool(
                                    raw_source_status.get(
                                        'cache_hit',
                                        False
                                    )
                                ),

                            'fetched_at':
                                str(
                                    raw_source_status.get(
                                        'fetched_at',
                                        ''
                                    )
                                    or ''
                                )
                        }
                    }
            # ==============================================================
            # Q7B — STRATEGY LAB SHADOW → APRENDIZAJE PROSPECTIVO
            # ==============================================================
            #
            # Persiste únicamente el snapshot compacto que app.py ya calculó.
            # Q7B NO recalcula mercado y NO modifica ninguna regla operativa.
            # ==============================================================

            if (
                self._normalize_system_type(
                    system_type
                )
                == 'futures'
            ):

                raw_q7 = (
                    analysis_result.get(
                        'strategy_lab'
                    )
                    or {}
                )

                if (
                    isinstance(
                        raw_q7,
                        dict
                    )
                    and raw_q7.get(
                        'shadow_only',
                        False
                    )
                ):

                    raw_q7_strategies = (
                        raw_q7.get(
                            'strategies',
                            {}
                        )
                        or {}
                    )

                    if not isinstance(
                        raw_q7_strategies,
                        dict
                    ):
                        raw_q7_strategies = {}

                    q7_rsi = (
                        raw_q7_strategies.get(
                            'rsi_profile',
                            {}
                        )
                        or {}
                    )

                    q7_vwap = (
                        raw_q7_strategies.get(
                            'vwap_reversion',
                            {}
                        )
                        or {}
                    )

                    q7_retest = (
                        raw_q7_strategies.get(
                            'breakout_retest',
                            {}
                        )
                        or {}
                    )

                    context[
                        'learning'
                    ][
                        'q7_strategy_lab_shadow'
                    ] = {
                        'snapshot_version':
                            'Q7_STRATEGY_LAB_LEARNING_V1',

                        'lab_version':
                            str(
                                raw_q7.get(
                                    'version',
                                    ''
                                )
                                or ''
                            )[:80],

                        'shadow_only':
                            True,

                        'eligible':
                            bool(
                                raw_q7.get(
                                    'eligible',
                                    False
                                )
                            ),

                        'system_type':
                            'futures',

                        'active_profile':
                            str(
                                raw_q7.get(
                                    'active_profile',
                                    ''
                                )
                                or ''
                            )[:40],

                        'final_action_observed':
                            str(
                                raw_q7.get(
                                    'final_action_observed',
                                    ''
                                )
                                or ''
                            ).upper()[:40],

                        'final_action_normalized':
                            str(
                                raw_q7.get(
                                    'final_action_normalized',
                                    ''
                                )
                                or ''
                            ).upper()[:40],

                        'reason':
                            str(
                                raw_q7.get(
                                    'reason',
                                    ''
                                )
                                or ''
                            )[:120],

                        # ----------------------------------------------
                        # Guardrails forzados: Q7 sigue sin autoridad.
                        # ----------------------------------------------
                        'affects_vote':
                            False,

                        'affects_safety':
                            False,

                        'affects_entry':
                            False,

                        'affects_levels':
                            False,

                        'affects_publication':
                            False,

                        'affects_leverage':
                            False,

                        'rsi_profile':
                            dict(q7_rsi)
                            if isinstance(
                                q7_rsi,
                                dict
                            )
                            else {},

                        'vwap_reversion':
                            dict(q7_vwap)
                            if isinstance(
                                q7_vwap,
                                dict
                            )
                            else {},

                        'breakout_retest':
                            dict(q7_retest)
                            if isinstance(
                                q7_retest,
                                dict
                            )
                            else {}
                    }
            # ==============================================================
            # COMMIT 7 — TRENDLINE SHADOW → APRENDIZAJE PROSPECTIVO
            # ==============================================================
            # Persistimos el snapshot compacto ya calculado en app.py.
            # No modifica votos, Safety, Entry, SL, TP, leverage ni publicación.
            try:
                raw_strategy_lab = analysis_result.get('strategy_lab') or {}
                raw_trendline = (
                    raw_strategy_lab.get('trendlines', {})
                    if isinstance(raw_strategy_lab, dict)
                    else {}
                ) or {}
                if isinstance(raw_trendline, dict) and raw_trendline.get('shadow_only', False):
                    compact_strategies = {}

                    def _trendline_optional_float(value):
                        try:
                            number = float(value)
                            return number if math.isfinite(number) else None
                        except (TypeError, ValueError):
                            return None

                    for key, item in (raw_trendline.get('strategies', {}) or {}).items():
                        if not isinstance(item, dict):
                            continue
                        compact_strategies[str(key)[:60]] = {
                            'name': str(item.get('name') or key)[:100],
                            'direction': str(item.get('direction') or 'NEUTRAL').upper()[:20],
                            'state': str(item.get('state') or 'NO_EDGE').upper()[:80],
                            'alignment_with_system': str(item.get('alignment_with_system') or 'NEUTRAL').upper()[:30],
                            'quality': _trendline_optional_float(item.get('quality')),
                            'shadow_only': True,
                        }
                    context['learning']['trendline_strategy_lab_shadow'] = {
                        'snapshot_version': 'C7_TRENDLINE_LEARNING_V1',
                        'lab_version': str(raw_trendline.get('version') or '')[:80],
                        'shadow_only': True,
                        'eligible': self._as_bool(raw_trendline.get('eligible', False)),
                        'reason': str(raw_trendline.get('reason') or '')[:120],
                        'strategies': compact_strategies,
                    }
            except Exception as trendline_learning_error:
                logger.warning('Trendline learning snapshot no disponible: %s', trendline_learning_error)

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

                print(
                    f"📝 [REVIEW] Señal registrada: "
                    f"{signal_data['symbol']} "
                    f"{signal_data['timeframe']} "
                    f"→ {signal_data['action']} "
                    f"(conf {signal_data['confidence']:.0f}%) "
                    f"- ID {signal_id[:8]}..."
                )

                micro_learning = (
                    context.get(
                        'learning',
                        {}
                    )
                    or {}
                ).get(
                    'microstructure_shadow',
                    {}
                ) or {}

                if micro_learning:

                    print(
                        "   🧠 [Q3B] Microestructura guardada "
                        f"| {signal_data['symbol']} "
                        f"{signal_data['timeframe']} "
                        f"| "
                        f"{micro_learning.get('alignment', 'N/A')} "
                        f"{micro_learning.get('alignment_score', 'N/A')} "
                        f"| fuentes="
                        f"{micro_learning.get('metrics', {}).get('source_count', 0)}"
                    )
                q7_learning = (
                    context.get(
                        'learning',
                        {}
                    )
                    or {}
                ).get(
                    'q7_strategy_lab_shadow',
                    {}
                ) or {}

                if q7_learning:

                    q7_rsi_learning = (
                        q7_learning.get(
                            'rsi_profile',
                            {}
                        )
                        or {}
                    )

                    print(
                        "   🧪 [Q7B] Strategy Lab guardado "
                        f"| {signal_data['symbol']} "
                        f"{signal_data['timeframe']} "
                        f"| perfil="
                        f"{q7_learning.get('active_profile', 'N/A')} "
                        f"| RSI="
                        f"{q7_rsi_learning.get('direction', 'NEUTRAL')} "
                        f"{q7_rsi_learning.get('alignment_with_system', 'NEUTRAL')}"
                    )
            # COMMIT 16 — Shadow central real, fail-open. Sólo registra coincidencias
            # con candidatos externos ya promovidos a SHADOW_READY/FAST.
            if signal_id:
                try:
                    from research_shadow_bridge import track_research_shadow_signal
                    track_research_shadow_signal(signal_id, analysis_result, system_type)
                except Exception as _research_shadow_error:
                    logger.warning('Research Shadow tracker no disponible: %s', _research_shadow_error)
            return signal_id
            
        except Exception as e:
            logger.error(f"Error registrando señal: {e}")
            return None
    
    def _get_previous_candle_timestamp(self, analysis: Dict) -> Optional[str]:
        """
        Obtiene el timestamp de la vela que realmente originó la señal.

        Compatibilidad:
        - Contrato nuevo: usa source_candle_timestamp.
        - Contrato antiguo: conserva times[-2] para no romper Spot ni los
          callers que todavía no envían el campo explícito.
        """
        try:
            explicit_source = analysis.get('source_candle_timestamp')

            if explicit_source:
                return str(explicit_source)

            df = analysis.get('df', {})
            times = df.get('time', [])

            if len(times) >= 2:
                # Fallback legado: el DataFrame incluía una vela abierta.
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
            ),

            # ==========================================================
            # COMMIT 36W
            # ==========================================================
            # Permite separar scores históricos de los scores
            # matemáticamente normalizados después de 36W.
            # ==========================================================

            'quality_score_version': str(
                levels.get(
                    'quality_score_version',
                    'LEGACY'
                )
                or 'LEGACY'
            ),

            # ==========================================================
            # QUALITY ENGINE Q1
            # ENTRY QUALITY / REACHABILITY
            # ==========================================================
            #
            # Importante para SPOT y FUTURES.
            #
            # Estos campos permiten comprobar posteriormente si:
            #
            # Entry más alcanzable
            #     ↓
            # más Entries realmente tocados
            #     ↓
            # mejor WR / Expectancy / PnL.
            # ==========================================================

            'entry_quality_version': str(
                levels.get(
                    'entry_quality_version',
                    'LEGACY_ENTRY'
                )
                or 'LEGACY_ENTRY'
            ),

            'entry_smc_raw_score': _safe_float(
                levels.get(
                    'entry_smc_raw_score',
                    levels.get(
                        'entry_score',
                        0
                    )
                ),
                0.0
            ),

            'entry_reachability_score': _safe_float(
                levels.get(
                    'entry_reachability_score',
                    0
                ),
                0.0
            ),

            # COMMIT 7 — separar alcanzabilidad de defendibilidad.
            # Persistimos el score ya calculado por Futures; no lo recalculamos.
            'entry_defensibility_score': _safe_float(
                levels.get(
                    'entry_defensibility_score'
                ),
                None
            ),

            'entry_defensibility_version': str(
                levels.get(
                    'entry_defensibility_version',
                    ''
                )
                or ''
            ),

            'entry_distance_atr': _safe_float(
                levels.get(
                    'entry_distance_atr'
                ),
                None
            ),

            'entry_distance_pct': _safe_float(
                levels.get(
                    'entry_distance_pct'
                ),
                None
            ),

            'entry_reachability_label': str(
                levels.get(
                    'entry_reachability_label',
                    'N/A'
                )
                or 'N/A'
            ),

            # ==========================================================
            # QUALITY ENGINE Q2
            # FUTURES EXECUTION SPECIALIST
            # ==========================================================
            #
            # Para Spot normalmente quedará vacío/False.
            # Para Futures permite saber qué señales realmente fueron
            # refinadas por Q2.
            # ==========================================================

            'futures_execution_specialist_version': str(
                levels.get(
                    'futures_execution_specialist_version',
                    ''
                )
                or ''
            ),

            'futures_execution_refined': self._as_bool(
                levels.get(
                    'futures_execution_refined',
                    False
                )
            )
        }


        # ==============================================================
        # COMMIT 36F — PERSISTIR BREAKDOWN DE EXECUTION SAFETY
        # ==============================================================

        raw_safety_breakdown = (
            levels.get(
                'execution_safety_breakdown',
                {}
            )
            or {}
        )

        if isinstance(
            raw_safety_breakdown,
            dict
        ) and raw_safety_breakdown:

            allowed_components = (
                'entry_smc',
                'sl',
                'tp',
                'rr',
                'structure',
                'trend',
                'timeframe'
            )

            def _compact_numeric_map(
                raw_map
            ):
                if not isinstance(
                    raw_map,
                    dict
                ):
                    return {}

                compact = {}

                for key in allowed_components:

                    if key not in raw_map:
                        continue

                    try:
                        number = float(
                            raw_map.get(
                                key
                            )
                        )
                    except (
                        TypeError,
                        ValueError
                    ):
                        continue

                    if math.isfinite(
                        number
                    ):
                        compact[
                            key
                        ] = round(
                            number,
                            4
                        )

                return compact

            compact_penalties = []

            raw_dominant = (
                raw_safety_breakdown.get(
                    'dominant_penalties'
                )
                or []
            )

            if isinstance(
                raw_dominant,
                list
            ):

                for item in raw_dominant[:3]:

                    if not isinstance(
                        item,
                        dict
                    ):
                        continue

                    component = str(
                        item.get(
                            'component',
                            ''
                        )
                        or ''
                    ).strip()

                    if component not in (
                        allowed_components
                    ):
                        continue

                    compact_item = {
                        'component':
                            component
                    }

                    for field in (
                        'score',
                        'weight',
                        'penalty_points'
                    ):

                        try:
                            number = float(
                                item.get(
                                    field
                                )
                            )
                        except (
                            TypeError,
                            ValueError
                        ):
                            continue

                        if math.isfinite(
                            number
                        ):
                            compact_item[
                                field
                            ] = round(
                                number,
                                4
                            )

                    compact_penalties.append(
                        compact_item
                    )

            context[
                'execution'
            ][
                'safety_breakdown'
            ] = {
                'model_version':
                    str(
                        raw_safety_breakdown.get(
                            'model_version',
                            ''
                        )
                        or ''
                    ),

                'available':
                    bool(
                        raw_safety_breakdown.get(
                            'available',
                            False
                        )
                    ),

                'raw_score':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'raw_score',
                            0
                        )
                    ),

                'label':
                    str(
                        raw_safety_breakdown.get(
                            'label',
                            ''
                        )
                        or ''
                    ),

                'base_minimum':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'base_minimum',
                            0
                        )
                    ),

                'operational_minimum':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'operational_minimum',
                            0
                        )
                    ),

                'distance_to_operational_min':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'distance_to_operational_min',
                            0
                        )
                    ),

                'shortfall_to_operational_min':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'shortfall_to_operational_min',
                            0
                        )
                    ),

                'leverage_safety_score':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'leverage_safety_score',
                            0
                        )
                    ),

                'components':
                    _compact_numeric_map(
                        raw_safety_breakdown.get(
                            'components'
                        )
                    ),

                'weights':
                    _compact_numeric_map(
                        raw_safety_breakdown.get(
                            'weights'
                        )
                    ),

                'weighted_contributions':
                    _compact_numeric_map(
                        raw_safety_breakdown.get(
                            'weighted_contributions'
                        )
                    ),

                'penalties_to_perfect':
                    _compact_numeric_map(
                        raw_safety_breakdown.get(
                            'penalties_to_perfect'
                        )
                    ),

                'dominant_penalties':
                    compact_penalties,

                'reconstructed_score':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'reconstructed_score',
                            0
                        )
                    ),

                'score_reconstruction_delta':
                    _safe_float(
                        raw_safety_breakdown.get(
                            'score_reconstruction_delta',
                            0
                        )
                    ),

                'timeframe_factor_source':
                    str(
                        raw_safety_breakdown.get(
                            'timeframe_factor_source',
                            ''
                        )
                        or ''
                    ),

                'calibration_active':
                    bool(
                        raw_safety_breakdown.get(
                            'calibration_active',
                            False
                        )
                    ),

                'calibration_mode':
                    str(
                        raw_safety_breakdown.get(
                            'calibration_mode',
                            ''
                        )
                        or ''
                    ),

                'diagnostic_only':
                    True
            }

        # ==============================================================
        # COMMIT 32 — PUBLICATION GATE FUTURES PARA APRENDIZAJE
        # ==============================================================
        #
        # El motor Futures ya conoce exactamente por qué una oportunidad
        # fue publicada o rechazada.
        #
        # Hasta ahora ReviewTrader guardaba las métricas individuales,
        # pero NO la decisión completa del publication gate.
        #
        # Este snapshot permite estudiar posteriormente:
        #
        #   Safety
        #   TP Quality
        #   SL Quality
        #   RR
        #   ROI TP
        #   beneficio neto
        #   pérdida en SL
        #   estrés ATR
        #
        # IMPORTANTE:
        # - NO cambia ninguna decisión.
        # - NO cambia Safety.
        # - NO cambia Entry / SL / TP.
        # - NO cambia leverage.
        # - NO cambia pesos.
        # - Sólo persiste el diagnóstico que YA calculó Futures.
        # ==============================================================

        raw_gate = (
            levels.get(
                'futures_publication_gate'
            )
            or {}
        )

        if isinstance(
            raw_gate,
            dict
        ) and raw_gate:

            raw_reasons = (
                raw_gate.get(
                    'reasons'
                )
                or []
            )

            if not isinstance(
                raw_reasons,
                (list, tuple)
            ):

                raw_reasons = [
                    raw_reasons
                ]

            raw_thresholds = (
                raw_gate.get(
                    'thresholds'
                )
                or {}
            )

            if not isinstance(
                raw_thresholds,
                dict
            ):

                raw_thresholds = {}

            def _publication_optional_float(
                value
            ):

                try:

                    number = float(
                        value
                    )

                    return (
                        number
                        if math.isfinite(
                            number
                        )
                        else None
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    return None

            # ==========================================================
            # NORMALIZAR MOTIVOS
            # ==========================================================
            #
            # La descripción humana original se conserva.
            #
            # Además creamos códigos estables para estadísticas:
            #
            # SAFETY
            # TP_QUALITY
            # SL_QUALITY
            # RR
            # ROI_TP
            # NET_PROFIT
            # LOSS_AT_SL
            # ATR_STRESS
            # OTHER
            # ==========================================================

            reason_codes = []

            for reason in raw_reasons:

                reason_text = str(
                    reason
                    or ''
                ).strip()

                reason_lower = (
                    reason_text.lower()
                )

                if (
                    'safety'
                    in reason_lower
                ):

                    code = (
                        'SAFETY'
                    )

                elif (
                    'calidad tp'
                    in reason_lower
                    or 'tp quality'
                    in reason_lower
                ):

                    code = (
                        'TP_QUALITY'
                    )

                elif (
                    'protección sl'
                    in reason_lower
                    or 'proteccion sl'
                    in reason_lower
                    or 'sl quality'
                    in reason_lower
                ):

                    code = (
                        'SL_QUALITY'
                    )

                elif (
                    'r/r'
                    in reason_lower
                    or 'risk_reward'
                    in reason_lower
                ):

                    code = (
                        'RR'
                    )

                elif (
                    'roi tp'
                    in reason_lower
                ):

                    code = (
                        'ROI_TP'
                    )

                elif (
                    'beneficio neto'
                    in reason_lower
                ):

                    code = (
                        'NET_PROFIT'
                    )

                elif (
                    'pérdida estimada en sl'
                    in reason_lower
                    or 'perdida estimada en sl'
                    in reason_lower
                ):

                    code = (
                        'LOSS_AT_SL'
                    )

                elif (
                    'estrés atr'
                    in reason_lower
                    or 'estres atr'
                    in reason_lower
                ):

                    code = (
                        'ATR_STRESS'
                    )

                else:

                    code = (
                        'OTHER'
                    )

                if code not in reason_codes:

                    reason_codes.append(
                        code
                    )

            context[
                'futures_publication'
            ] = {

                'eligible':
                    self._as_bool(
                        raw_gate.get(
                            'eligible',
                            False
                        )
                    ),

                'tier':
                    str(
                        raw_gate.get(
                            'tier'
                        )
                        or (
                            'PREMIUM'
                            if self._as_bool(
                                raw_gate.get(
                                    'eligible',
                                    False
                                )
                            )
                            else 'ANALYSIS_ONLY'
                        )
                    ),

                'rejection_count':
                    len(
                        raw_reasons
                    ),

                'reason_codes':
                    reason_codes,

                # Guardamos también el texto para auditoría humana.
                # Máximo 8 motivos y longitud limitada para no inflar JSON.
                'reasons': [

                    str(
                        reason
                    )[:180]

                    for reason
                    in raw_reasons[:8]

                ],

                'tp_touch_quality_score':
                    _publication_optional_float(
                        raw_gate.get(
                            'tp_touch_quality_score'
                        )
                    ),

                'sl_avoidance_quality_score':
                    _publication_optional_float(
                        raw_gate.get(
                            'sl_avoidance_quality_score'
                        )
                    ),

                'preferred_leverage_min':
                    _publication_optional_float(
                        raw_gate.get(
                            'preferred_leverage_min'
                        )
                    ),

                'preferred_leverage_max':
                    _publication_optional_float(
                        raw_gate.get(
                            'preferred_leverage_max'
                        )
                    ),

                'leverage_in_preferred_band':
                    self._as_bool(
                        raw_gate.get(
                            'leverage_in_preferred_band',
                            False
                        )
                    ),

                'probability_status':
                    str(
                        raw_gate.get(
                            'probability_status'
                        )
                        or ''
                    ),

                'thresholds': {

                    str(
                        key
                    ):
                        _publication_optional_float(
                            value
                        )

                    for key, value
                    in raw_thresholds.items()

                    if _publication_optional_float(
                        value
                    ) is not None
                }
            }
            # ==============================================================
            # COMMIT 34 — PUBLICATION GATE FUTURES EXACTO PARA APRENDIZAJE
            # ==============================================================
            #
            # El motor Futures ya calculó el publication gate antes de que
            # ReviewTrader registre la observación. Aquí sólo copiamos ese
            # diagnóstico al context persistido en Supabase.
            #
            # IMPORTANTE:
            # - NO cambia publicación.
            # - NO cambia Safety.
            # - NO cambia Entry / SL / TP.
            # - NO cambia leverage.
            # - NO cambia traders, pesos ni votos.
            # - NO reconstruye un gate inexistente.
            #
            # Compatibilidad:
            # hoy futures_system guarda el gate dentro de levels, pero también
            # aceptamos una futura versión top-level sin romper el contrato.
            # ==============================================================
    
            raw_gate = (
                analysis.get('futures_publication_gate')
                or levels.get('futures_publication_gate')
                or {}
            )
    
            if isinstance(raw_gate, dict) and raw_gate:
    
                raw_reasons = raw_gate.get('reasons') or []
    
                if not isinstance(raw_reasons, (list, tuple)):
                    raw_reasons = [raw_reasons]
    
                raw_thresholds = raw_gate.get('thresholds') or {}
    
                if not isinstance(raw_thresholds, dict):
                    raw_thresholds = {}
    
                def _publication_optional_float(value):
                    try:
                        number = float(value)
                        return number if math.isfinite(number) else None
                    except (TypeError, ValueError):
                        return None
    
                # ==========================================================
                # NORMALIZAR MOTIVOS A CÓDIGOS ESTABLES
                # ==========================================================
                # El texto humano se conserva, pero el PDF necesita códigos
                # estables para agrupar estadísticamente los rechazos.
                # ==========================================================
    
                reason_codes = []
    
                for reason in raw_reasons:
    
                    reason_text = str(reason or '').strip()
                    reason_lower = reason_text.lower()
    
                    if 'safety' in reason_lower:
                        code = 'SAFETY'
    
                    elif (
                        'calidad tp' in reason_lower
                        or 'tp quality' in reason_lower
                    ):
                        code = 'TP_QUALITY'
    
                    elif (
                        'protección sl' in reason_lower
                        or 'proteccion sl' in reason_lower
                        or 'sl quality' in reason_lower
                    ):
                        code = 'SL_QUALITY'
    
                    elif (
                        'r/r' in reason_lower
                        or 'risk/reward' in reason_lower
                        or 'risk_reward' in reason_lower
                    ):
                        code = 'RR'
    
                    elif 'roi tp' in reason_lower:
                        code = 'ROI_TP'
    
                    elif 'beneficio neto' in reason_lower:
                        code = 'NET_PROFIT'
    
                    elif (
                        'pérdida estimada en sl' in reason_lower
                        or 'perdida estimada en sl' in reason_lower
                    ):
                        code = 'LOSS_AT_SL'
    
                    elif (
                        'estrés atr' in reason_lower
                        or 'estres atr' in reason_lower
                    ):
                        code = 'ATR_STRESS'
    
                    else:
                        code = 'OTHER'
    
                    if code not in reason_codes:
                        reason_codes.append(code)
    
                threshold_snapshot = {}
    
                for key, value in raw_thresholds.items():
                    parsed_value = _publication_optional_float(value)
    
                    if parsed_value is not None:
                        threshold_snapshot[str(key)] = parsed_value
    
                context['futures_publication'] = {
                    'eligible': self._as_bool(
                        raw_gate.get('eligible', False)
                    ),
    
                    'tier': str(
                        raw_gate.get('tier')
                        or (
                            'PREMIUM'
                            if self._as_bool(raw_gate.get('eligible', False))
                            else 'ANALYSIS_ONLY'
                        )
                    ),
    
                    'publication_status': str(
                        analysis.get('publication_status')
                        or levels.get('publication_status')
                        or ''
                    ),
    
                    'is_executable': self._as_bool(
                        analysis.get(
                            'is_executable',
                            levels.get('is_executable', False)
                        )
                    ),
    
                    'gate_source': (
                        'TOP_LEVEL'
                        if analysis.get('futures_publication_gate')
                        else 'LEVELS'
                    ),
    
                    'rejection_count': len(raw_reasons),
                    'reason_codes': reason_codes,
    
                    # Mantener una copia humana compacta para auditoría.
                    'reasons': [
                        str(reason)[:180]
                        for reason in raw_reasons[:8]
                    ],
    
                    'tp_touch_quality_score': _publication_optional_float(
                        raw_gate.get('tp_touch_quality_score')
                    ),
    
                    'sl_avoidance_quality_score': _publication_optional_float(
                        raw_gate.get('sl_avoidance_quality_score')
                    ),
    
                    'preferred_leverage_min': _publication_optional_float(
                        raw_gate.get('preferred_leverage_min')
                    ),
    
                    'preferred_leverage_max': _publication_optional_float(
                        raw_gate.get('preferred_leverage_max')
                    ),
    
                    'leverage_in_preferred_band': self._as_bool(
                        raw_gate.get('leverage_in_preferred_band', False)
                    ),
    
                    'probability_status': str(
                        raw_gate.get('probability_status') or ''
                    ),
    
                    'thresholds': threshold_snapshot
                }

        return context
    
    # ========================================================================
    # 2. EVALUAR RESULTADOS DE SEÑALES PENDIENTES
    # ========================================================================

    def _get_signal_evaluation_window(
        self,
        signal: Dict
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Devuelve (inicio_operable, vencimiento) sin mirar precios futuros.

        El timestamp principal de una señal representa la APERTURA de la vela
        fuente. Esa vela tuvo que cerrar antes de que la decisión fuese válida.
        Las señales nuevas de Futuros guardan ese cierre explícitamente; para
        Spot y registros compatibles se calcula con su temporalidad.
        """
        timeframe = str(signal.get('timeframe') or '')
        learning = self._get_signal_learning(signal)

        source_open = self._parse_ts(
            learning.get('source_candle_timestamp')
            or signal.get('candle_timestamp')
        )
        source_close = self._parse_ts(
            learning.get('source_candle_close_timestamp')
        )

        if source_close is None and source_open is not None:
            minutes = TIMEFRAME_MINUTES.get(timeframe)
            if minutes:
                source_close = source_open + timedelta(minutes=minutes)

        # Si un registro legado no permite reconstruir la vela, created_at es
        # el primer instante seguro: jamás evaluamos antes de que se guardara.
        evaluation_start = source_close or self._parse_ts(
            signal.get('created_at')
        )
        if evaluation_start is None:
            return None, None

        max_hours = SIGNAL_EXPIRATION.get(timeframe, 24)
        evaluation_end = evaluation_start + timedelta(hours=max_hours)
        return evaluation_start, evaluation_end

    def _has_complete_expiration_coverage(
        self,
        signal: Dict,
        observation: Dict,
        evaluation_start: datetime,
        evaluation_end: datetime
    ) -> bool:
        """Impide expirar usando un historial recortado o con huecos."""
        timeframe = str(signal.get('timeframe') or '')
        minutes = TIMEFRAME_MINUTES.get(timeframe)
        if not minutes:
            return False

        expected_candles = int(
            (evaluation_end - evaluation_start).total_seconds()
            / (minutes * 60)
        )
        observed_candles = int(
            observation.get('candles_observed', 0) or 0
        )
        first_timestamp = self._parse_ts(
            observation.get('first_timestamp')
        )
        last_timestamp = self._parse_ts(
            observation.get('last_timestamp')
        )
        if not first_timestamp or not last_timestamp:
            return False

        last_required_open = evaluation_end - timedelta(minutes=minutes)
        return bool(
            observed_candles >= expected_candles
            and first_timestamp <= evaluation_start
            and last_timestamp >= last_required_open
        )

    # ====================================================================
    # COMMIT 2 — EXECUTION FORENSICS V2
    # ====================================================================

    def _build_execution_forensics_payload(
        self,
        signal: Dict,
        result: Dict,
        df,
        evaluation_start: Optional[datetime],
        evaluation_end: Optional[datetime]
    ) -> Dict:
        """
        Diagnóstico retrospectivo usando las MISMAS velas ya descargadas.

        No realiza nuevas llamadas HTTP y no cambia el outcome.
        Permite distinguir:
        - Entry no alcanzado;
        - SL casi inmediato;
        - progreso favorable antes del SL;
        - recuperación posterior al SL dentro de la vigencia original.
        """
        try:
            import pandas as pd

            action = str(
                signal.get('action_normalized', '') or ''
            ).upper()
            if action in ('COMPRA_SPOT', 'BUY'):
                action = 'LONG'
            elif action in ('VENTA_SPOT', 'SELL'):
                action = 'SHORT'

            entry = float(signal.get('entry_price', 0) or 0)
            sl = float(signal.get('stop_loss', 0) or 0)
            tp = float(signal.get('take_profit', 0) or 0)
            risk_abs = abs(entry - sl)

            if (
                action not in ('LONG', 'SHORT')
                or entry <= 0
                or sl <= 0
                or tp <= 0
                or risk_abs <= 0
            ):
                return build_execution_forensics(signal, result)

            if 'time' in df.columns:
                df_time = pd.to_datetime(df['time'], utc=True)

                start_timestamp = pd.Timestamp(evaluation_start)
                if start_timestamp.tzinfo is None:
                    start_timestamp = start_timestamp.tz_localize('UTC')
                else:
                    start_timestamp = start_timestamp.tz_convert('UTC')

                valid_mask = df_time >= start_timestamp

                if evaluation_end is not None:
                    end_timestamp = pd.Timestamp(evaluation_end)
                    if end_timestamp.tzinfo is None:
                        end_timestamp = end_timestamp.tz_localize('UTC')
                    else:
                        end_timestamp = end_timestamp.tz_convert('UTC')
                    valid_mask = valid_mask & (df_time < end_timestamp)

                df_after = df[valid_mask]
            else:
                df_after = df

            entry_touched = False
            entry_timestamp = None
            candles_to_entry = 0

            for candle_number, (_, row) in enumerate(
                df_after.iterrows(), start=1
            ):
                high = float(row['high'])
                low = float(row['low'])
                touched_now = (
                    low <= entry
                    if action == 'LONG'
                    else high >= entry
                )
                if touched_now:
                    entry_touched = True
                    candles_to_entry = candle_number
                    entry_timestamp = str(
                        row.get('time', '') or ''
                    ) or None
                    break

            post_stop_recovery = {}
            if str(result.get('status', '')).lower() == 'sl_hit':
                sl_candle = int(
                    result.get('candles_to_result', 0) or 0
                )
                remaining = (
                    df_after.iloc[sl_candle:]
                    if sl_candle >= 0
                    else df_after.iloc[0:0]
                )

                reclaimed_entry = False
                tp_reached_after_stop = False
                candles_to_reclaim = 0
                candles_to_tp = 0
                best_favorable_r = 0.0
                worst_adverse_r = 1.0

                for offset, (_, row) in enumerate(
                    remaining.iterrows(), start=1
                ):
                    high = float(row['high'])
                    low = float(row['low'])

                    if action == 'LONG':
                        favorable_r = max(0.0, (high - entry) / risk_abs)
                        adverse_r = max(0.0, (entry - low) / risk_abs)
                        reclaimed_now = high >= entry
                        target_now = high >= tp
                    else:
                        favorable_r = max(0.0, (entry - low) / risk_abs)
                        adverse_r = max(0.0, (high - entry) / risk_abs)
                        reclaimed_now = low <= entry
                        target_now = low <= tp

                    best_favorable_r = max(
                        best_favorable_r, favorable_r
                    )
                    worst_adverse_r = max(
                        worst_adverse_r, adverse_r
                    )

                    if reclaimed_now and not reclaimed_entry:
                        reclaimed_entry = True
                        candles_to_reclaim = offset

                    if target_now:
                        tp_reached_after_stop = True
                        candles_to_tp = offset
                        break

                post_stop_recovery = {
                    'observed': True,
                    'reclaimed_entry': reclaimed_entry,
                    'tp_reached_after_stop': tp_reached_after_stop,
                    'candles_to_reclaim_entry': int(candles_to_reclaim),
                    'candles_to_tp_after_stop': int(candles_to_tp),
                    'best_favorable_r_after_stop': round(
                        best_favorable_r, 4
                    ),
                    'worst_adverse_r_after_stop': round(
                        worst_adverse_r, 4
                    )
                }

            return build_execution_forensics(
                signal,
                result,
                entry_touched=entry_touched,
                entry_timestamp=entry_timestamp,
                candles_to_entry=candles_to_entry,
                post_stop_recovery=post_stop_recovery
            )

        except Exception as forensic_error:
            logger.warning(
                'Execution Forensics V2 no disponible para %s: %s',
                signal.get('id'),
                forensic_error
            )
            return build_execution_forensics(signal, result)
    
    def evaluate_pending_signals(
        self,
        price_fetcher,
        max_rows: int = 4000,
        budget_seconds: int = 60,
        should_yield=None
    ) -> Dict:
        """
        Recorre señales pendientes y verifica si alcanzaron TP, SL o expiraron.

        Hotfix 15.2 añade ejecución cooperativa: el worker puede procesar
        micro-lotes acotados y ceder inmediatamente cuando una vista Futures
        interactiva necesita el único slot pesado del Render gratuito. El
        comportamiento estadístico no cambia; sólo cambia cuánto trabajo se
        procesa por turno.

        price_fetcher: proveedor Spot que recibe (symbol, timeframe). Las señales
                       Futures NO usan este proveedor: se consultan mediante el
                       motor de contratos perpetuos y se valida su procedencia.
        
        Retorna: estadísticas del batch procesado.
        """
        if not self.db.enabled:
            return {'processed': 0, 'tp_hit': 0, 'sl_hit': 0, 'expired': 0}
        
        # Margen adicional para que una indisponibilidad temporal del proveedor
        # no haga desaparecer una señal justo al vencer la ventana más larga.
        oldest_pending_hours = max(SIGNAL_EXPIRATION.values()) + (14 * 24)
        max_rows = max(1, int(max_rows or 1))
        budget_seconds = max(1, int(budget_seconds or 1))
        pending = self.db.iter_pending_signals(
            hours_old_max=oldest_pending_hours,
            directional=True,
            page_size=min(50, max_rows),
            max_rows=max_rows,
            budget_seconds=budget_seconds,
        )
        # Q6-E: local to this run. Never retains full candle sets across workers.
        from collections import OrderedDict
        market_frames = OrderedDict()
        def cached_market_data(signal):
            key = (signal.get('system_type'), signal.get('symbol'), signal.get('timeframe'))
            if key in market_frames:
                market_frames.move_to_end(key)
                return market_frames[key]
            value = self._fetch_market_data_for_signal(signal, price_fetcher)
            market_frames[key] = value
            # Un micro-lote no necesita retener doce DataFrames de 200 velas.
            # Cuatro combinaciones bastan para reutilización local y reducen el
            # working set mientras el usuario navega Futures.
            if len(market_frames) > 4:
                market_frames.popitem(last=False)
            return value
        
        stats = {
            'processed': 0,
            'tp_hit': 0,
            'sl_hit': 0,
            'expired': 0,
            'expired_no_entry': 0,
            'expired_after_entry': 0,
            'ambiguous': 0,
            'invalid_setup': 0,
            'incomplete_history': 0,
            'still_pending': 0,
            'spot_evaluated': 0,
            'futures_real_evaluated': 0,
            'legacy_futures_quarantined': 0,
            'market_data_rejected': 0,
            'scanned': 0,
            'yielded_for_ui': False,
        }
        
        print(f"\n{'='*60}")
        print(
            "🔍 [REVIEW] Evaluando señales pendientes "
            f"(micro-lote max={max_rows}, presupuesto={budget_seconds}s)"
        )
        print(f"{'='*60}")

        pending_iter = iter(pending)
        while True:
            if callable(should_yield):
                try:
                    if should_yield():
                        stats['yielded_for_ui'] = True
                        print("⏸️ [REVIEW] Cediendo turno a la vista Futures.")
                        break
                except Exception:
                    pass

            try:
                signal = next(pending_iter)
            except StopIteration:
                break

            stats['scanned'] += 1
            try:
                symbol = signal.get('symbol')
                timeframe = signal.get('timeframe')
                
                # Solo evaluar señales de trading (no NO_OPERAR, esas se evalúan en otro método)
                action_norm = signal.get('action_normalized')
                if action_norm == 'NO_OPERAR':
                    stats['still_pending'] += 1
                    continue

                system_type = self._normalize_system_type(
                    signal.get('system_type')
                )

                # Las filas antiguas de Futuros no tienen una cadena de
                # procedencia demostrable. No se borran ni se reinterpretan:
                # se dejan en cuarentena para no fabricar un win rate.
                if (
                    system_type == 'futures'
                    and not self._is_clean_futures_signal(signal)
                ):
                    stats['legacy_futures_quarantined'] += 1
                    continue
                
                if system_type == 'spot' and not verified_spot(signal):
                    stats.setdefault('legacy_spot_quarantined', 0)
                    stats['legacy_spot_quarantined'] += 1
                    continue
                # Obtain once per market/pair/timeframe, with bounded local cache.
                df, data_source = cached_market_data(signal)
                if df is None or len(df) == 0:
                    if data_source in (
                        'FUTURES_SOURCE_REJECTED',
                        'FUTURES_PROVIDER_ERROR'
                    ):
                        stats['market_data_rejected'] += 1
                    stats['still_pending'] += 1
                    continue

                if system_type == 'futures':
                    stats['futures_real_evaluated'] += 1
                else:
                    stats['spot_evaluated'] += 1
                
                evaluation_start, evaluation_end = (
                    self._get_signal_evaluation_window(signal)
                )
                if evaluation_start is None or evaluation_end is None:
                    stats['invalid_setup'] += 1
                    stats['still_pending'] += 1
                    continue

                is_expired = datetime.utcnow() >= evaluation_end

                # Primero se reconstruye TODA la vida válida de la señal. Sólo
                # después, si no hubo salida, se la marca como expirada.
                result = self._check_tp_sl_hit(
                    signal,
                    df,
                    evaluation_start=evaluation_start,
                    evaluation_end=evaluation_end,
                    include_pending_snapshot=True
                )

                if result and result.get('status') in (
                    'tp_hit',
                    'sl_hit',
                    'ambiguous',
                    'invalid_setup'
                ):
                    result['execution_forensics'] = (
                        self._build_execution_forensics_payload(
                            signal,
                            result,
                            df,
                            evaluation_start,
                            evaluation_end
                        )
                    )
                    # COMMIT 13 — evaluate every SHADOW geometry on exactly the
                    # same closed candles. Official outcome remains immutable.
                    try:
                        challenger_results = evaluate_execution_challengers(
                            signal, df, evaluation_start, evaluation_end
                        )
                        if challenger_results:
                            result['execution_challenger_results'] = challenger_results
                            # Commit 14: persist C13 evidence inside the existing
                            # execution_forensics JSON column.  No schema change
                            # and no extra row/table is required.
                            if isinstance(result.get('execution_forensics'), dict):
                                result['execution_forensics']['execution_challenger_results'] = challenger_results
                    except Exception as challenger_error:
                        logger.warning(
                            'Execution Challenger Lab no disponible: %s',
                            challenger_error
                        )
                    # COMMIT 9 — persist conservative provisional economics at
                    # the same time as the immutable TP/SL outcome. Funding is
                    # enriched later in a bounded background pass.
                    if result.get('status') in ('tp_hit', 'sl_hit'):
                        economics = build_provisional_economics(signal, result)
                        if economics:
                            result.update(economics)
                    if not self.db.update_signal_result(signal['id'], result):
                        stats.setdefault('write_errors', 0)
                        stats['write_errors'] += 1
                        continue
                    stats['processed'] += 1
                    if result['status'] == 'tp_hit':
                        stats['tp_hit'] += 1
                    elif result['status'] == 'sl_hit':
                        stats['sl_hit'] += 1
                    elif result['status'] == 'ambiguous':
                        stats['ambiguous'] += 1
                    elif result['status'] == 'invalid_setup':
                        stats['invalid_setup'] += 1
                    marker = {
                        'tp_hit': '✅',
                        'sl_hit': '❌',
                        'ambiguous': '⚖️',
                        'invalid_setup': '⚠️'
                    }.get(result['status'], 'ℹ️')
                    print(f"   {marker} "
                          f"{symbol} {timeframe} {action_norm}: {result['status']} "
                          f"({result['pnl_pct']:+.2f}%)")
                elif result and is_expired:
                    result['execution_forensics'] = (
                        self._build_execution_forensics_payload(
                            signal,
                            result,
                            df,
                            evaluation_start,
                            evaluation_end
                        )
                    )
                    try:
                        challenger_results = evaluate_execution_challengers(
                            signal, df, evaluation_start, evaluation_end
                        )
                        if challenger_results:
                            result['execution_challenger_results'] = challenger_results
                            # Commit 14: persist C13 evidence inside the existing
                            # execution_forensics JSON column.  No schema change
                            # and no extra row/table is required.
                            if isinstance(result.get('execution_forensics'), dict):
                                result['execution_forensics']['execution_challenger_results'] = challenger_results
                    except Exception as challenger_error:
                        logger.warning(
                            'Execution Challenger Lab no disponible en expiración: %s',
                            challenger_error
                        )
                    if not self._has_complete_expiration_coverage(
                        signal,
                        result,
                        evaluation_start,
                        evaluation_end
                    ):
                        stats['incomplete_history'] += 1
                        stats['still_pending'] += 1
                        continue
                    expiry_result = self._mark_signal_expired(
                        signal,
                        result,
                        evaluation_end
                    )
                    if not expiry_result.get('persisted'):
                        stats.setdefault('write_errors', 0)
                        stats['write_errors'] += 1
                        continue
                    stats['expired'] += 1
                    stats['processed'] += 1
                    if expiry_result.get('entry_touched'):
                        stats['expired_after_entry'] += 1
                    else:
                        stats['expired_no_entry'] += 1
                else:
                    stats['still_pending'] += 1
                    
            except Exception as e:
                logger.error(f"Error evaluando señal {signal.get('id')}: {e}")
        
        print(f"\n📊 [REVIEW] Batch completado:")
        print(
            f"   Revisadas: {stats['scanned']} | "
            f"cedió a UI: {'sí' if stats['yielded_for_ui'] else 'no'}"
        )
        print(f"   TP alcanzado: {stats['tp_hit']}")
        print(f"   SL alcanzado: {stats['sl_hit']}")
        print(
            f"   Expiradas: {stats['expired']} "
            f"(sin Entry={stats['expired_no_entry']} | "
            f"tras Entry={stats['expired_after_entry']})"
        )
        print(
            "   Resultado OHLC no demostrable (TP+SL misma vela): "
            f"{stats['ambiguous']}"
        )
        print(f"   Setups inválidos: {stats['invalid_setup']}")
        print(
            "   Historial incompleto (sin fabricar resultado): "
            f"{stats['incomplete_history']}"
        )
        print(f"   Aún pendientes: {stats['still_pending']}")
        print(
            "   Mercados evaluados: "
            f"Spot={stats['spot_evaluated']} | "
            f"Futures reales={stats['futures_real_evaluated']}"
        )
        print(
            "   Futures antiguos en cuarentena: "
            f"{stats['legacy_futures_quarantined']}"
        )
        print(f"{'='*60}\n")
        
        return stats
    
    def _check_tp_sl_hit(
        self,
        signal: Dict,
        df,
        evaluation_start: Optional[datetime] = None,
        evaluation_end: Optional[datetime] = None,
        include_pending_snapshot: bool = False
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

            if action not in ('LONG', 'SHORT'):
                return None

            invalid_reason = None
            if entry <= 0 or sl <= 0 or tp <= 0:
                invalid_reason = 'LEVEL_NON_POSITIVE'
            elif action == 'LONG' and not (sl < entry < tp):
                invalid_reason = 'INVALID_LONG_GEOMETRY'
            elif action == 'SHORT' and not (tp < entry < sl):
                invalid_reason = 'INVALID_SHORT_GEOMETRY'

            if invalid_reason:
                return {
                    'status': 'invalid_setup',
                    'exit_price': 0,
                    'exit_timestamp': datetime.utcnow().isoformat(),
                    'pnl_pct': 0,
                    'candles_to_result': 0,
                    'notes': (
                        'outcome_reason=invalid_setup; '
                        f'validation={invalid_reason}; '
                        'statistically_resolved=false'
                    )
                }

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

            if evaluation_start is None or evaluation_end is None:
                calculated_start, calculated_end = (
                    self._get_signal_evaluation_window(signal)
                )
                evaluation_start = evaluation_start or calculated_start
                evaluation_end = evaluation_end or calculated_end

            if not evaluation_start:
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

                start_timestamp = pd.Timestamp(
                    evaluation_start,
                    tz='UTC'
                )

                valid_mask = df_time >= start_timestamp

                if evaluation_end is not None:
                    end_timestamp = pd.Timestamp(
                        evaluation_end,
                        tz='UTC'
                    )
                    valid_mask = valid_mask & (df_time < end_timestamp)

                df_after = df[valid_mask]

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
            # ENTRY REAL
            # ==========================================================
            #
            # Una señal direccional no es una operación hasta que el
            # mercado alcanza su Entry. Antes de ese momento:
            #
            # - TP no cuenta;
            # - SL no cuenta;
            # - MFE / MAE no empiezan;
            # - ReviewTrader no debe aprender un resultado.
            #
            # El sistema construye LONG como entrada de retroceso
            # (entry <= cierre fuente) y SHORT como entrada de rebote
            # (entry >= cierre fuente). Por eso un salto que abra más allá
            # del Entry también se considera ejecutado.
            # ==========================================================

            entry_touched = False
            entry_timestamp = None
            last_close = entry
            first_candle_ts = None
            last_candle_ts = evaluation_start
            observed_candles = 0

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
                    ),

                    # COMMIT 9 — exact observed first Entry touch.
                    # Never substitute signal creation time for a fill.
                    'entry_timestamp': (
                        str(entry_timestamp)
                        if entry_timestamp is not None
                        else None
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

                candle_close = float(
                    row.get('close', entry)
                    or entry
                )
                last_close = candle_close
                if first_candle_ts is None:
                    first_candle_ts = candle_ts
                last_candle_ts = candle_ts
                observed_candles = candle_number

                # ======================================================
                # NO EVALUAR TP / SL ANTES DE ENTRY
                # ======================================================

                if not entry_touched:

                    if action == 'LONG':
                        touched_now = low <= entry
                    else:
                        touched_now = high >= entry

                    if not touched_now:
                        continue

                    entry_touched = True
                    entry_timestamp = candle_ts
                    # Q6-B: TP can have occurred BEFORE the first limit fill.
                    # OHLC cannot prove the sequence when opening outside Entry.
                    opening = float(row.get('open', float('nan')))
                    filled_at_open = (opening <= entry if action == 'LONG' else opening >= entry)
                    target_touched = (high >= tp if action == 'LONG' else low <= tp)
                    if target_touched and not filled_at_open:
                        return {
                            'status': 'ambiguous', 'exit_price': 0,
                            'exit_timestamp': str(candle_ts), 'pnl_pct': 0,
                            'candles_to_result': candle_number,
                            'notes': ('outcome_reason=entry_tp_same_candle_order_unknown; '
                                      'entry_touched=true; statistically_resolved=false; '
                                      'requires_lower_timeframe=true'),
                            **_excursion_payload()
                        }

                # ======================================================
                # LONG
                # ======================================================

                if action == 'LONG':

                    # Una vela OHLC informa que ambos niveles ocurrieron, pero
                    # no en qué orden. Etiquetarla siempre como SL fabricaba
                    # pérdidas; etiquetarla TP fabricaría ganancias. Se aparta
                    # de win rate hasta poder resolverla con menor timeframe.
                    if low <= sl and high >= tp:
                        mfe_price = max(mfe_price, tp)
                        mae_price = min(mae_price, sl)
                        candles_to_mfe = candle_number
                        candles_to_mae = candle_number
                        metrics = _excursion_payload()
                        return {
                            'status': 'ambiguous',
                            'exit_price': 0,
                            'exit_timestamp': str(candle_ts),
                            'pnl_pct': 0,
                            'candles_to_result': candle_number,
                            'notes': (
                                'outcome_reason=tp_and_sl_same_candle; '
                                'entry_touched=true; '
                                'statistically_resolved=false; '
                                'requires_lower_timeframe=true'
                            ),
                            **metrics
                        }

                    # --------------------------------------------------
                    # SL
                    # --------------------------------------------------
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

                            'notes': (
                                'outcome_reason=sl_hit; '
                                'entry_touched=true; '
                                'resolution_quality=unambiguous_ohlc; '
                                'statistically_resolved=true'
                            ),

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

                            'notes': (
                                'outcome_reason=tp_hit; '
                                'entry_touched=true; '
                                'resolution_quality=unambiguous_ohlc; '
                                'statistically_resolved=true'
                            ),

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

                    if high >= sl and low <= tp:
                        mfe_price = min(mfe_price, tp)
                        mae_price = max(mae_price, sl)
                        candles_to_mfe = candle_number
                        candles_to_mae = candle_number
                        metrics = _excursion_payload()
                        return {
                            'status': 'ambiguous',
                            'exit_price': 0,
                            'exit_timestamp': str(candle_ts),
                            'pnl_pct': 0,
                            'candles_to_result': candle_number,
                            'notes': (
                                'outcome_reason=tp_and_sl_same_candle; '
                                'entry_touched=true; '
                                'statistically_resolved=false; '
                                'requires_lower_timeframe=true'
                            ),
                            **metrics
                        }

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

                            'notes': (
                                'outcome_reason=sl_hit; '
                                'entry_touched=true; '
                                'resolution_quality=unambiguous_ohlc; '
                                'statistically_resolved=true'
                            ),

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

                            'notes': (
                                'outcome_reason=tp_hit; '
                                'entry_touched=true; '
                                'resolution_quality=unambiguous_ohlc; '
                                'statistically_resolved=true'
                            ),

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

            if not include_pending_snapshot:
                return None

            metrics = _excursion_payload()
            return {
                'status': (
                    'pending_after_entry'
                    if entry_touched
                    else 'pending_no_entry'
                ),
                'entry_touched': entry_touched,
                'last_price': float(last_close),
                'first_timestamp': str(first_candle_ts),
                'last_timestamp': str(last_candle_ts),
                'candles_observed': int(observed_candles),
                **metrics
            }

        except Exception as e:

            logger.error(
                f"Error en _check_tp_sl_hit: {e}"
            )

            return None
    
    def _mark_signal_expired(
        self,
        signal: Dict,
        observation: Optional[Dict] = None,
        evaluation_end: Optional[datetime] = None
    ) -> Dict:
        """
        Cierra por tiempo distinguiendo una orden nunca ejecutada de una
        operación que sí alcanzó Entry pero no tocó TP/SL.
        """
        observation = observation or {}
        entry_touched = bool(observation.get('entry_touched', False))
        entry = float(signal.get('entry_price', 0) or 0)
        last_price = float(observation.get('last_price', 0) or 0)
        action = str(signal.get('action_normalized', '') or '').upper()

        pnl_pct = 0.0
        if entry_touched and entry > 0 and last_price > 0:
            if action == 'LONG':
                pnl_pct = (last_price - entry) / entry * 100
            elif action == 'SHORT':
                pnl_pct = (entry - last_price) / entry * 100

        outcome_reason = (
            'expired_after_entry'
            if entry_touched
            else 'expired_no_entry'
        )
        expiry_ts = (
            evaluation_end.isoformat()
            if evaluation_end is not None
            else datetime.utcnow().isoformat()
        )
        result = {
            'status': 'expired',
            'exit_price': last_price if entry_touched else 0,
            'exit_timestamp': expiry_ts,
            'pnl_pct': pnl_pct,
            'candles_to_result': int(
                observation.get('candles_observed', 0) or 0
            ),
            'entry_touched': entry_touched,
            'notes': (
                f'outcome_reason={outcome_reason}; '
                f'entry_touched={str(entry_touched).lower()}; '
                'exit_rule=time_expiration; '
                'statistically_resolved=false'
            ),
            'mfe_price': observation.get('mfe_price', 0),
            'mae_price': observation.get('mae_price', 0),
            'mfe_pct': observation.get('mfe_pct', 0),
            'mae_pct': observation.get('mae_pct', 0),
            'mfe_r': observation.get('mfe_r', 0),
            'mae_r': observation.get('mae_r', 0),
            'candles_to_mfe': observation.get('candles_to_mfe', 0),
            'candles_to_mae': observation.get('candles_to_mae', 0),
            'execution_forensics': observation.get(
                'execution_forensics',
                {}
            ),
            'execution_challenger_results': observation.get(
                'execution_challenger_results',
                {}
            )
        }
        result['persisted'] = self.db.update_signal_result(signal['id'], result)
        return result
    
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
    # COMMIT 36U
    # FUTURES QUALITY LAB — SHADOW ONLY
    # ========================================================================

    def get_futures_quality_lab(
        self,
        days_back: int = 90,
        max_rows: int = 1000
    ) -> Dict:
        """
        COMMIT 36U

        Estudia cómo la calidad de:

        - Entry SMC
        - Stop Loss
        - Take Profit
        - RR
        - Estructura
        - Tendencia
        - Temporalidad

        se relaciona con outcomes reales de los Futures Shadow.

        REGLAS ABSOLUTAS:

        - READ-ONLY;
        - no modifica Safety;
        - no modifica Entry;
        - no modifica SL;
        - no modifica TP;
        - no modifica leverage;
        - no modifica publication gate;
        - no crea un segundo evaluador;
        - no publica señales.

        Su único producto son hipótesis SHADOW para mejorar
        la calidad de las señales.
        """

        result = {
            'mode':
                'FUTURES_QUALITY_LAB_SHADOW',

            'days_back':
                int(
                    days_back
                ),

            'authority_changed':
                False,

            'production_changed':
                False,

            'ready_for_production_change':
                False,

            'policy':
                'IMPROVE_QUALITY_DO_NOT_LOWER_SAFETY',

            # ============================================================
            # COMMIT 37 — CONTRATO DE CALIBRACIÓN
            # ============================================================
            #
            # La evidencia LEGACY sigue visible como inventario histórico,
            # pero sólo 36W_V2_NORMALIZED puede alimentar la calibración
            # que eventualmente habilite una REVISIÓN HUMANA del Commit 37.
            # Nunca existe promoción automática.
            # ============================================================

            'commit37_policy': {
                'version':
                    COMMIT37_POLICY_VERSION,

                'mode':
                    'GATE_LOCKED_SHADOW',

                'required_quality_score_version':
                    COMMIT37_REQUIRED_QUALITY_SCORE_VERSION,

                'premium_unchanged':
                    True,

                'production_changed':
                    False,

                'automatic_promotion':
                    False,

                'human_review_required':
                    True,

                'operational_authority':
                    'NONE',

                'observational_focus': {
                    'safety_65_69':
                        'PROMISING_SHADOW_ONLY',

                    'safety_70_74':
                        'COLLECT_MORE_EVIDENCE',

                    'below_65':
                        'DO_NOT_RELAX_HARD_SAFETY',

                    'regime':
                        COMMIT37_OBSERVATIONAL_REGIME,

                    'allowed_near_miss_blocks': [
                        'SAFETY',
                        'TP_QUALITY'
                    ]
                }
            },

            'inventory': {
                'futures_rows_scanned':
                    0,

                'clean_directional_shadow':
                    0,

                'invalid_geometry':
                    0,

                'pending':
                    0,

                'tp_hit':
                    0,

                'sl_hit':
                    0,

                'expired_no_entry':
                    0,

                'expired_after_entry':
                    0,

                'ambiguous':
                    0,

                'invalid_setup':
                    0,

                'other_outcome':
                    0,

                'resolved_tp_sl':
                    0,

                'commit37_v2_directional_shadow':
                    0,

                'excluded_non_v2_from_commit37':
                    0
            },

            'component_inventory':
                {},

            'quality_score_versions':
                {},

            'quality_by_component':
                {},

            'validation_30':
                {},

            'quality_proposals':
                {},

            'gate': {
                'resolved_sample_ok':
                    False,

                'validation_sample_ok':
                    False,

                'has_promising_component':
                    False,

                'net_outcomes_verified':
                    False,

                'oos_positive':
                    False
            },

            'status':
                'COLLECTING_EVIDENCE',

            'reason':
                None
        }

        if not self.db.enabled:
            result[
                'status'
            ] = 'SUPABASE_UNAVAILABLE'

            result[
                'reason'
            ] = (
                'ReviewTrader no tiene Supabase activo.'
            )

            return result

        try:
            safe_days = max(
                7,
                min(
                    int(
                        days_back
                        or 90
                    ),
                    180
                )
            )

            safe_max_rows = max(
                100,
                min(
                    int(
                        max_rows
                        or 1000
                    ),
                    1500
                )
            )

            cutoff = (
                datetime.utcnow()
                - timedelta(
                    days=safe_days
                )
            ).isoformat()

            # ============================================================
            # HELPERS
            # ============================================================

            def _float_or_none(
                value
            ):
                try:
                    number = float(
                        value
                    )

                    if math.isfinite(
                        number
                    ):
                        return number

                except (
                    TypeError,
                    ValueError
                ):
                    pass

                return None


            def _quality_score(
                value
            ):
                number = _float_or_none(
                    value
                )

                if number is None:
                    return None

                return max(
                    0.0,
                    min(
                        100.0,
                        number
                    )
                )


            def _extract_quality(
                signal
            ):
                """
                Devuelve únicamente scores ya persistidos.
                No recalcula Safety.
                """

                context = (
                    self._get_signal_context(
                        signal
                    )
                    or {}
                )

                execution = (
                    context.get(
                        'execution'
                    )
                    or {}
                )

                if not isinstance(
                    execution,
                    dict
                ):
                    execution = {}

                breakdown = (
                    execution.get(
                        'safety_breakdown'
                    )
                    or {}
                )

                if not isinstance(
                    breakdown,
                    dict
                ):
                    breakdown = {}

                components = (
                    breakdown.get(
                        'components'
                    )
                    or {}
                )

                if not isinstance(
                    components,
                    dict
                ):
                    components = {}

                def _component(
                    name,
                    fallback=None
                ):
                    if name in components:
                        return _quality_score(
                            components.get(
                                name
                            )
                        )

                    value = _float_or_none(
                        fallback
                    )

                    if (
                        value is None
                        or value <= 0
                    ):
                        return None

                    return _quality_score(
                        value
                    )


                # sl_reliability histórico puede ser 0..1.
                sl_fallback = _float_or_none(
                    execution.get(
                        'sl_reliability'
                    )
                )

                if (
                    sl_fallback is not None
                    and 0 < sl_fallback <= 1
                ):
                    sl_fallback *= 100.0

                scores = {
                    'entry_smc':
                        _component(
                            'entry_smc',
                            execution.get(
                                'entry_score'
                            )
                        ),

                    'sl':
                        _component(
                            'sl',
                            sl_fallback
                        ),

                    'tp':
                        _component(
                            'tp',
                            execution.get(
                                'tp_quality_score'
                            )
                        ),

                    'rr':
                        _component(
                            'rr'
                        ),

                    'structure':
                        _component(
                            'structure'
                        ),

                    'trend':
                        _component(
                            'trend'
                        ),

                    'timeframe':
                        _component(
                            'timeframe'
                        )
                }

                learning = (
                    self._get_signal_learning(
                        signal
                    )
                    or {}
                )

                quant = (
                    learning.get(
                        'quantitative_shadow'
                    )
                    or {}
                )

                if not isinstance(
                    quant,
                    dict
                ):
                    quant = {}

                return {
                    'scores':
                        scores,

                    'quality_score_version':
                        str(
                            execution.get(
                                'quality_score_version'
                            )
                            or 'LEGACY'
                        ),

                    'execution_safety':
                        _float_or_none(
                            execution.get(
                                'execution_safety'
                            )
                        ),

                    'regime':
                        str(
                            quant.get(
                                'regime'
                            )
                            or 'UNAVAILABLE'
                        )
                }


            def _valid_geometry(
                action,
                entry,
                sl,
                tp
            ):
                if not all(
                    value is not None
                    and value > 0
                    for value in (
                        entry,
                        sl,
                        tp
                    )
                ):
                    return False

                if action == 'LONG':
                    return (
                        sl
                        < entry
                        < tp
                    )

                if action == 'SHORT':
                    return (
                        tp
                        < entry
                        < sl
                    )

                return False


            # ============================================================
            # 1. LEER FUTURES EN PÁGINAS PEQUEÑAS
            # ============================================================
            #
            # Compactamos inmediatamente cada fila.
            # No mantenemos 1000 context JSON pesados en memoria.
            # ============================================================

            candidates = []

            offset = 0
            page_size = 200

            while (
                offset < safe_max_rows
            ):
                current_size = min(
                    page_size,
                    safe_max_rows
                    - offset
                )

                response = (
                    self.db.client
                    .table(
                        'signals'
                    )
                    .select(
                        (
                            'id,'
                            'symbol,'
                            'timeframe,'
                            'system_type,'
                            'action_original,'
                            'action_normalized,'
                            'status,'
                            'entry_price,'
                            'stop_loss,'
                            'take_profit,'
                            'leverage,'
                            'context,'
                            'created_at'
                        )
                    )
                    .eq(
                        'system_type',
                        'futures'
                    )
                    .gte(
                        'created_at',
                        cutoff
                    )
                    .order(
                        'created_at',
                        desc=False
                    )
                    .range(
                        offset,
                        offset
                        + current_size
                        - 1
                    )
                    .execute()
                )

                batch = (
                    response.data
                    or []
                )

                if not batch:
                    break

                result[
                    'inventory'
                ][
                    'futures_rows_scanned'
                ] += len(
                    batch
                )

                for signal in batch:
                    if not isinstance(
                        signal,
                        dict
                    ):
                        continue

                    learning = (
                        self._get_signal_learning(
                            signal
                        )
                        or {}
                    )

                    if (
                        learning.get(
                            'cohort'
                        )
                        != FUTURES_REAL_COHORT
                    ):
                        continue

                    if (
                        learning.get(
                            'evaluation_role'
                        )
                        != 'SHADOW_ANALYSIS'
                    ):
                        continue

                    action = str(
                        signal.get(
                            'action_normalized'
                        )
                        or signal.get(
                            'action_original'
                        )
                        or ''
                    ).upper()

                    if action not in (
                        'LONG',
                        'SHORT'
                    ):
                        continue

                    entry = _float_or_none(
                        signal.get(
                            'entry_price'
                        )
                    )

                    sl = _float_or_none(
                        signal.get(
                            'stop_loss'
                        )
                    )

                    tp = _float_or_none(
                        signal.get(
                            'take_profit'
                        )
                    )

                    if not _valid_geometry(
                        action,
                        entry,
                        sl,
                        tp
                    ):
                        result[
                            'inventory'
                        ][
                            'invalid_geometry'
                        ] += 1

                        continue

                    quality = (
                        _extract_quality(
                            signal
                        )
                    )

                    candidates.append({
                        'id':
                            str(
                                signal.get(
                                    'id'
                                )
                                or ''
                            ),

                        'symbol':
                            signal.get(
                                'symbol'
                            ),

                        'timeframe':
                            signal.get(
                                'timeframe'
                            ),

                        'action':
                            action,

                        'entry':
                            entry,

                        'sl':
                            sl,

                        'tp':
                            tp,

                        'leverage':
                            _float_or_none(
                                signal.get(
                                    'leverage'
                                )
                            ),

                        'created_at':
                            str(
                                signal.get(
                                    'created_at'
                                )
                                or ''
                            ),

                        'scores':
                            quality[
                                'scores'
                            ],

                        'quality_score_version':
                            quality[
                                'quality_score_version'
                            ],

                        'execution_safety':
                            quality[
                                'execution_safety'
                            ],

                        'regime':
                            quality[
                                'regime'
                            ]
                    })

                if len(
                    batch
                ) < current_size:
                    break

                offset += len(
                    batch
                )

            result[
                'inventory'
            ][
                'clean_directional_shadow'
            ] = len(
                candidates
            )

            # ==========================================================
            # COMMIT 36W
            # DIFERENCIAR HISTÓRICO LEGACY DE SCORE REPARADO
            # ==========================================================

            for candidate in candidates:

                version = str(
                    candidate.get(
                        'quality_score_version'
                    )
                    or 'LEGACY'
                )

                result[
                    'quality_score_versions'
                ][
                    version
                ] = (
                    result[
                        'quality_score_versions'
                    ].get(
                        version,
                        0
                    )
                    + 1
                )

            if not candidates:
                result[
                    'reason'
                ] = (
                    'NO_CLEAN_DIRECTIONAL_FUTURES_SHADOW'
                )

                return result

            # ============================================================
            # COMMIT 37
            # COHORTE DE CALIBRACIÓN EXCLUSIVAMENTE 36W V2
            # ============================================================
            #
            # El inventario histórico completo continúa disponible arriba,
            # pero las métricas que podrían alimentar readiness de Commit 37
            # NO pueden mezclar LEGACY con 36W_V2_NORMALIZED.
            # ============================================================

            commit37_candidates = [
                candidate
                for candidate
                in candidates
                if str(
                    candidate.get(
                        'quality_score_version'
                    )
                    or 'LEGACY'
                )
                == COMMIT37_REQUIRED_QUALITY_SCORE_VERSION
            ]

            result[
                'inventory'
            ][
                'commit37_v2_directional_shadow'
            ] = len(
                commit37_candidates
            )

            result[
                'inventory'
            ][
                'excluded_non_v2_from_commit37'
            ] = max(
                0,
                len(
                    candidates
                )
                - len(
                    commit37_candidates
                )
            )

            if not commit37_candidates:
                result[
                    'status'
                ] = 'COLLECTING_36W_V2_EVIDENCE'

                result[
                    'reason'
                ] = (
                    'Hay Futures Shadow limpios, pero todavía no existen '
                    'candidatos 36W_V2_NORMALIZED suficientes para calibrar '
                    'Commit 37 sin mezclar scores LEGACY.'
                )

                return result

            # ============================================================
            # 2. RESULTADOS
            # ============================================================

            signal_ids = [
                row[
                    'id'
                ]
                for row
                in commit37_candidates
                if row.get(
                    'id'
                )
            ]

            results_by_signal = {}

            for start in range(
                0,
                len(
                    signal_ids
                ),
                100
            ):
                id_batch = signal_ids[
                    start:
                    start + 100
                ]

                response = (
                    self.db.client
                    .table(
                        'signal_results'
                    )
                    .select(
                        (
                            'signal_id,'
                            'status,'
                            'pnl_pct,'
                            'notes,'
                            'created_at'
                        )
                    )
                    .in_(
                        'signal_id',
                        id_batch
                    )
                    .order(
                        'created_at',
                        desc=False
                    )
                    .execute()
                )

                for row in (
                    response.data
                    or []
                ):
                    if not isinstance(
                        row,
                        dict
                    ):
                        continue

                    signal_id = str(
                        row.get(
                            'signal_id'
                        )
                        or ''
                    )

                    if signal_id:
                        # Si existiese más de un resultado legado,
                        # conservar el último cronológicamente.
                        results_by_signal[
                            signal_id
                        ] = row

            # ============================================================
            # 3. INVENTARIO DE CALIDAD
            # ============================================================

            components = (
                'entry_smc',
                'sl',
                'tp',
                'rr',
                'structure',
                'trend',
                'timeframe'
            )

            component_values = {
                name:
                    []
                for name
                in components
            }

            for candidate in commit37_candidates:
                for name in components:
                    score = (
                        candidate[
                            'scores'
                        ].get(
                            name
                        )
                    )

                    if score is not None:
                        component_values[
                            name
                        ].append(
                            score
                        )

            for name in components:
                values = (
                    component_values[
                        name
                    ]
                )

                result[
                    'component_inventory'
                ][
                    name
                ] = {
                    'n':
                        len(
                            values
                        ),

                    'mean':
                        (
                            round(
                                sum(
                                    values
                                )
                                / len(
                                    values
                                ),
                                2
                            )
                            if values
                            else None
                        )
                }

            # ============================================================
            # 4. OUTCOMES
            # ============================================================

            resolved_rows = []

            for candidate in commit37_candidates:
                outcome = (
                    results_by_signal.get(
                        candidate[
                            'id'
                        ]
                    )
                )

                if not outcome:
                    result[
                        'inventory'
                    ][
                        'pending'
                    ] += 1

                    continue

                status = str(
                    outcome.get(
                        'status'
                    )
                    or ''
                ).lower()

                if status == 'tp_hit':
                    result[
                        'inventory'
                    ][
                        'tp_hit'
                    ] += 1

                elif status == 'sl_hit':
                    result[
                        'inventory'
                    ][
                        'sl_hit'
                    ] += 1

                elif status == 'expired':
                    notes = str(
                        outcome.get(
                            'notes'
                        )
                        or ''
                    ).lower()

                    if (
                        'expired_after_entry'
                        in notes
                        or 'entry_touched=true'
                        in notes
                    ):
                        result[
                            'inventory'
                        ][
                            'expired_after_entry'
                        ] += 1

                    else:
                        result[
                            'inventory'
                        ][
                            'expired_no_entry'
                        ] += 1

                    continue

                elif status == 'ambiguous':
                    result[
                        'inventory'
                    ][
                        'ambiguous'
                    ] += 1

                    continue

                elif status == 'invalid_setup':
                    result[
                        'inventory'
                    ][
                        'invalid_setup'
                    ] += 1

                    continue

                else:
                    result[
                        'inventory'
                    ][
                        'other_outcome'
                    ] += 1

                    continue

                # Sólo TP y SL son resultados R estadísticamente
                # resueltos para este Quality Lab.

                risk = abs(
                    candidate[
                        'entry'
                    ]
                    - candidate[
                        'sl'
                    ]
                )

                reward = abs(
                    candidate[
                        'tp'
                    ]
                    - candidate[
                        'entry'
                    ]
                )

                if risk <= 0:
                    continue

                planned_rr = (
                    reward
                    / risk
                )

                realized_r = (
                    planned_rr
                    if status
                    == 'tp_hit'
                    else -1.0
                )

                resolved_rows.append({
                    **candidate,

                    'outcome':
                        status,

                    'realized_r':
                        realized_r
                })

            result[
                'inventory'
            ][
                'resolved_tp_sl'
            ] = len(
                resolved_rows
            )

            resolved_rows.sort(
                key=lambda row:
                    row[
                        'created_at'
                    ]
            )

            # ============================================================
            # 5. BANDAS DE CALIDAD
            # ============================================================

            def _score_band(
                score
            ):
                if score < 40:
                    return '<40'

                if score < 55:
                    return '40-54'

                if score < 65:
                    return '55-64'

                if score < 75:
                    return '65-74'

                return '75+'


            def _summarize_component(
                rows,
                component
            ):
                buckets = {}

                for row in rows:
                    score = (
                        row[
                            'scores'
                        ].get(
                            component
                        )
                    )

                    if score is None:
                        continue

                    band = (
                        _score_band(
                            score
                        )
                    )

                    bucket = (
                        buckets.setdefault(
                            band,
                            {
                                'n':
                                    0,

                                'tp':
                                    0,

                                'sl':
                                    0,

                                'sum_r':
                                    0.0
                            }
                        )
                    )

                    bucket[
                        'n'
                    ] += 1

                    bucket[
                        'sum_r'
                    ] += float(
                        row[
                            'realized_r'
                        ]
                    )

                    if (
                        row[
                            'outcome'
                        ]
                        == 'tp_hit'
                    ):
                        bucket[
                            'tp'
                        ] += 1

                    else:
                        bucket[
                            'sl'
                        ] += 1

                output = {}

                for (
                    band,
                    bucket
                ) in buckets.items():
                    n = (
                        bucket[
                            'n'
                        ]
                    )

                    output[
                        band
                    ] = {
                        'n':
                            n,

                        'tp':
                            bucket[
                                'tp'
                            ],

                        'sl':
                            bucket[
                                'sl'
                            ],

                        'win_rate_pct':
                            round(
                                (
                                    bucket[
                                        'tp'
                                    ]
                                    / n
                                    * 100.0
                                ),
                                2
                            )
                            if n
                            else None,

                        'expectancy_r':
                            round(
                                (
                                    bucket[
                                        'sum_r'
                                    ]
                                    / n
                                ),
                                4
                            )
                            if n
                            else None
                    }

                return output


            for component in components:
                result[
                    'quality_by_component'
                ][
                    component
                ] = (
                    _summarize_component(
                        resolved_rows,
                        component
                    )
                )

            # ============================================================
            # 6. WALK-FORWARD 70 / 30
            # ============================================================

            split_index = int(
                len(
                    resolved_rows
                )
                * 0.70
            )

            validation_rows = (
                resolved_rows[
                    split_index:
                ]
            )

            for component in components:
                result[
                    'validation_30'
                ][
                    component
                ] = (
                    _summarize_component(
                        validation_rows,
                        component
                    )
                )

            # ============================================================
            # 7. BUSCAR UMBRALES DE MAYOR CALIDAD — SHADOW
            # ============================================================
            #
            # Esto NO propone bajar Safety.
            #
            # Pregunta exactamente lo contrario:
            #
            # "¿Existe evidencia de que exigir MAYOR calidad en un
            # componente produce mejor expectancy?"
            # ============================================================

            def _average_r(
                rows
            ):
                if not rows:
                    return None

                return (
                    sum(
                        float(
                            row[
                                'realized_r'
                            ]
                        )
                        for row
                        in rows
                    )
                    / len(
                        rows
                    )
                )


            promising_count = 0

            for component in components:
                proposal = {
                    'status':
                        'COLLECTING_EVIDENCE',

                    'candidate_min_score_shadow':
                        None,

                    'sample':
                        0,

                    'validation_sample':
                        0,

                    'reason':
                        (
                            'Muestra insuficiente o '
                            'sin edge OOS demostrado.'
                        ),

                    'affects_production':
                        False
                }

                component_rows = [
                    row
                    for row
                    in resolved_rows
                    if (
                        row[
                            'scores'
                        ].get(
                            component
                        )
                        is not None
                    )
                ]

                component_validation = [
                    row
                    for row
                    in validation_rows
                    if (
                        row[
                            'scores'
                        ].get(
                            component
                        )
                        is not None
                    )
                ]

                proposal[
                    'sample'
                ] = len(
                    component_rows
                )

                proposal[
                    'validation_sample'
                ] = len(
                    component_validation
                )

                # Sólo examinamos umbrales que EXIGEN calidad.
                for threshold in (
                    55.0,
                    65.0,
                    75.0
                ):
                    above = [
                        row
                        for row
                        in component_rows
                        if (
                            row[
                                'scores'
                            ][
                                component
                            ]
                            >= threshold
                        )
                    ]

                    below = [
                        row
                        for row
                        in component_rows
                        if (
                            row[
                                'scores'
                            ][
                                component
                            ]
                            < threshold
                        )
                    ]

                    validation_above = [
                        row
                        for row
                        in component_validation
                        if (
                            row[
                                'scores'
                            ][
                                component
                            ]
                            >= threshold
                        )
                    ]

                    if (
                        len(
                            above
                        ) < 5
                        or len(
                            below
                        ) < 5
                        or len(
                            validation_above
                        ) < 3
                    ):
                        continue

                    above_r = (
                        _average_r(
                            above
                        )
                    )

                    below_r = (
                        _average_r(
                            below
                        )
                    )

                    validation_r = (
                        _average_r(
                            validation_above
                        )
                    )

                    if (
                        above_r is not None
                        and below_r is not None
                        and validation_r is not None
                        and above_r > 0
                        and validation_r > 0
                        and above_r
                        >= below_r
                        + 0.10
                    ):
                        proposal.update({
                            'status':
                                'PROMISING_SHADOW',

                            'candidate_min_score_shadow':
                                threshold,

                            'above_sample':
                                len(
                                    above
                                ),

                            'below_sample':
                                len(
                                    below
                                ),

                            'validation_above_sample':
                                len(
                                    validation_above
                                ),

                            'above_expectancy_r':
                                round(
                                    above_r,
                                    4
                                ),

                            'below_expectancy_r':
                                round(
                                    below_r,
                                    4
                                ),

                            'validation_expectancy_r':
                                round(
                                    validation_r,
                                    4
                                ),

                            'reason':
                                (
                                    'Mayor calidad mostró '
                                    'mejor expectancy y '
                                    'continuó positiva OOS.'
                                )
                        })

                        promising_count += 1

                        # Elegir el primer umbral prudente que
                        # demuestra edge; no buscar uno más agresivo.
                        break

                result[
                    'quality_proposals'
                ][
                    component
                ] = proposal

            # ============================================================
            # 8. GATE 36U
            # ============================================================

            result[
                'gate'
            ][
                'resolved_sample_ok'
            ] = bool(
                len(
                    resolved_rows
                )
                >= 25
            )

            result[
                'gate'
            ][
                'validation_sample_ok'
            ] = bool(
                len(
                    validation_rows
                )
                >= 10
            )

            result[
                'gate'
            ][
                'has_promising_component'
            ] = bool(
                promising_count > 0
            )

            # No inventamos costes realizados.
            result[
                'gate'
            ][
                'net_outcomes_verified'
            ] = False

            # En esta fase OOS sólo se considera una señal
            # diagnóstica, nunca permiso de producción.
            result[
                'gate'
            ][
                'oos_positive'
            ] = bool(
                promising_count > 0
            )

            if (
                result[
                    'gate'
                ][
                    'resolved_sample_ok'
                ]
                and result[
                    'gate'
                ][
                    'validation_sample_ok'
                ]
                and result[
                    'gate'
                ][
                    'has_promising_component'
                ]
            ):
                result[
                    'status'
                ] = (
                    'DIAGNOSTIC_READY_'
                    'WAITING_NET_VALIDATION'
                )

                result[
                    'reason'
                ] = (
                    'Existe una hipótesis de mayor calidad '
                    'con evidencia OOS, pero no puede '
                    'modificar producción sin outcomes netos.'
                )

            else:
                result[
                    'status'
                ] = (
                    'COLLECTING_EVIDENCE'
                )

                result[
                    'reason'
                ] = (
                    'Aún faltan outcomes Futures resueltos '
                    'para relacionar calidad con expectancy.'
                )

            # Regla absoluta de 36U.
            result[
                'ready_for_production_change'
            ] = False

            return result

        except Exception as error:
            # ============================================================
            # FAIL-OPEN
            # ============================================================
            #
            # Un fallo del laboratorio jamás toca Futures.
            # ============================================================

            logger.warning(
                "36U Futures Quality Lab: %s",
                error
            )

            result[
                'status'
            ] = 'QUALITY_LAB_ERROR'

            result[
                'reason'
            ] = str(
                error
            )[:180]

            return result    

    # ========================================================================
    # COMMIT 36V
    # GATE COMBINADO PARA REVISIÓN DE COMMIT 37
    # ========================================================================

    def get_commit37_readiness(
        self,
        days_back: int = 90
    ) -> Dict:
        """
        COMMIT 36V

        Une:

        A) 36U:
           calidad técnica Shadow + OOS.

        B) 36V:
           economía neta MODELADA de Futures trazables.

        La salida máxima es:

            READY_FOR_COMMIT37_REVIEW

        Nunca:

        - cambia producción;
        - baja Safety;
        - cambia Entry;
        - cambia SL;
        - cambia TP;
        - cambia leverage;
        - promociona una regla automáticamente.
        """

        result = {
            'mode':
                'COMMIT37_READINESS_36V',

            'days_back':
                int(
                    days_back
                ),

            'production_changed':
                False,

            'ready_for_commit37_review':
                False,

            'ready_for_automatic_promotion':
                False,

            'realized_profit_claim_allowed':
                False,

            # ============================================================
            # COMMIT 37 — ESTADO DE AUTORIDAD
            # ============================================================
            #
            # Incluso si 36V llega a READY_FOR_COMMIT37_REVIEW, este método
            # sólo habilita REVISIÓN HUMANA. No existe activación automática
            # ni una ruta que cambie Futures desde este gate.
            # ============================================================

            'commit37_policy': {
                'version':
                    COMMIT37_POLICY_VERSION,

                'mode':
                    'GATE_LOCKED_SHADOW',

                'required_quality_score_version':
                    COMMIT37_REQUIRED_QUALITY_SCORE_VERSION,

                'premium_unchanged':
                    True,

                'production_changed':
                    False,

                'automatic_promotion':
                    False,

                'human_review_required':
                    True,

                'authority':
                    'SHADOW_ONLY',

                'activation_status':
                    'LOCKED_NOT_READY'
            },

            'quality':
                {},

            'economics':
                {},

            'gate': {
                'quality_available':
                    False,

                'quality_sample_ok':
                    False,

                'quality_validation_ok':
                    False,

                'quality_candidate_found':
                    False,

                'quality_oos_positive':
                    False,

                'economics_available':
                    False,

                'economic_review_ready':
                    False,

                'realized_costs_verified':
                    False
            },

            'status':
                'NOT_READY',

            'reasons':
                []
        }

        # ============================================================
        # 1. 36U — QUALITY LAB
        # ============================================================

        quality_fn = getattr(
            self,
            'get_futures_quality_lab',
            None
        )

        if not callable(
            quality_fn
        ):
            result[
                'reasons'
            ].append(
                (
                    '36U Futures Quality Lab '
                    'no está disponible.'
                )
            )

            return result

        try:
            quality = (
                quality_fn(
                    days_back=days_back,
                    max_rows=1000
                )
                or {}
            )

        except Exception as quality_error:
            result[
                'reasons'
            ].append(
                (
                    '36U no pudo generar evidencia: '
                    f'{str(quality_error)[:160]}'
                )
            )

            return result

        # No devolvemos todo el JSON pesado.
        result[
            'quality'
        ] = {
            'mode':
                quality.get(
                    'mode'
                ),

            'status':
                quality.get(
                    'status'
                ),

            'inventory':
                quality.get(
                    'inventory',
                    {}
                ),

            'quality_score_versions':
                quality.get(
                    'quality_score_versions',
                    {}
                ),

            'commit37_policy':
                quality.get(
                    'commit37_policy',
                    {}
                ),

            'quality_proposals':
                quality.get(
                    'quality_proposals',
                    {}
                ),

            'validation_30':
                quality.get(
                    'validation_30',
                    {}
                ),

            'gate':
                quality.get(
                    'gate',
                    {}
                )
        }

        quality_policy = (
            quality.get(
                'commit37_policy'
            )
            or {}
        )

        if quality_policy:
            result[
                'commit37_policy'
            ][
                'required_quality_score_version'
            ] = str(
                quality_policy.get(
                    'required_quality_score_version'
                )
                or COMMIT37_REQUIRED_QUALITY_SCORE_VERSION
            )

        quality_gate = (
            quality.get(
                'gate'
            )
            or {}
        )

        result[
            'gate'
        ][
            'quality_available'
        ] = bool(
            quality
            and quality.get(
                'status'
            )
            not in (
                'QUALITY_LAB_ERROR',
                'SUPABASE_UNAVAILABLE'
            )
        )

        result[
            'gate'
        ][
            'quality_sample_ok'
        ] = bool(
            quality_gate.get(
                'resolved_sample_ok'
            )
        )

        result[
            'gate'
        ][
            'quality_validation_ok'
        ] = bool(
            quality_gate.get(
                'validation_sample_ok'
            )
        )

        result[
            'gate'
        ][
            'quality_candidate_found'
        ] = bool(
            quality_gate.get(
                'has_promising_component'
            )
        )

        result[
            'gate'
        ][
            'quality_oos_positive'
        ] = bool(
            quality_gate.get(
                'oos_positive'
            )
        )

        # ============================================================
        # 2. 36V — ECONOMÍA
        # ============================================================

        try:
            from saved_signals import (
                get_commit37_economic_validation
            )

            economics = (
                get_commit37_economic_validation(
                    days_back=days_back,
                    max_rows=2000
                )
                or {}
            )

        except Exception as economics_error:
            result[
                'reasons'
            ].append(
                (
                    '36V economía no disponible: '
                    f'{str(economics_error)[:160]}'
                )
            )

            return result

        result[
            'economics'
        ] = economics

        result[
            'gate'
        ][
            'economics_available'
        ] = bool(
            economics

            and economics.get(
                'status'
            )
            != 'ECONOMIC_VALIDATION_ERROR'
        )

        result[
            'gate'
        ][
            'economic_review_ready'
        ] = bool(
            economics.get(
                'ready_for_commit37_economic_review'
            )
        )

        result[
            'gate'
        ][
            'realized_costs_verified'
        ] = bool(
            economics.get(
                'ready_for_realized_profit_claim'
            )
        )

        # ============================================================
        # 3. GATE COMBINADO
        # ============================================================

        required = (
            'quality_available',
            'quality_sample_ok',
            'quality_validation_ok',
            'quality_candidate_found',
            'quality_oos_positive',
            'economics_available',
            'economic_review_ready'
        )

        combined_ready = all(
            result[
                'gate'
            ].get(
                key
            )
            is True
            for key
            in required
        )

        result[
            'ready_for_commit37_review'
        ] = bool(
            combined_ready
        )

        # ============================================================
        # NUNCA PROMOCIÓN AUTOMÁTICA
        # ============================================================

        result[
            'ready_for_automatic_promotion'
        ] = False

        result[
            'realized_profit_claim_allowed'
        ] = bool(
            result[
                'gate'
            ][
                'realized_costs_verified'
            ]
        )

        # ============================================================
        # RESULTADO
        # ============================================================

        if combined_ready:
            result[
                'status'
            ] = (
                'READY_FOR_COMMIT37_REVIEW'
            )

            result[
                'commit37_policy'
            ][
                'authority'
            ] = 'REVIEW_ONLY'

            result[
                'commit37_policy'
            ][
                'activation_status'
            ] = 'READY_FOR_HUMAN_REVIEW'

            result[
                'reasons'
            ].append(
                (
                    '36U encontró una hipótesis '
                    'de mayor calidad con validación OOS.'
                )
            )

            result[
                'reasons'
            ].append(
                (
                    '36V encontró expectancy neta '
                    'MODELADA positiva total y OOS '
                    'en Futures trazables.'
                )
            )

            if not result[
                'realized_profit_claim_allowed'
            ]:
                result[
                    'reasons'
                ].append(
                    (
                        'Fee+slippage aún son modelados: '
                        'se permite revisar Commit 37, '
                        'no afirmar beneficio neto realizado.'
                    )
                )

        else:
            result[
                'status'
            ] = 'NOT_READY'

            checks = (
                (
                    'quality_sample_ok',
                    (
                        'Faltan >=25 outcomes '
                        'técnicos resueltos.'
                    )
                ),

                (
                    'quality_validation_ok',
                    (
                        'Faltan >=10 outcomes '
                        'técnicos OOS.'
                    )
                ),

                (
                    'quality_candidate_found',
                    (
                        'Todavía no existe un componente '
                        'de mayor calidad con edge demostrado.'
                    )
                ),

                (
                    'quality_oos_positive',
                    (
                        'La mejora técnica todavía no '
                        'mantiene expectancy positiva OOS.'
                    )
                ),

                (
                    'economic_review_ready',
                    (
                        'La economía neta modelada aún no '
                        'supera muestra, cobertura y '
                        'expectancy OOS.'
                    )
                )
            )

            for (
                key,
                message
            ) in checks:

                if not result[
                    'gate'
                ].get(
                    key
                ):
                    result[
                        'reasons'
                    ].append(
                        message
                    )

        return result
    
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
            no_op_signals = self.db.iter_pending_signals(hours_old_max=168, directional=False)
            print("\n🔍 [REVIEW] Buscando oportunidades perdidas por lotes")
            
            missed = 0
            
            for signal in no_op_signals:
                try:
                    symbol = signal.get('symbol')
                    timeframe = signal.get('timeframe')
                    system_type = self._normalize_system_type(
                        signal.get('system_type')
                    )

                    # No reinterpretar como oportunidades perdidas las antiguas
                    # filas Futures cuya procedencia no puede demostrarse.
                    if (
                        system_type == 'futures'
                        and not self._is_clean_futures_signal(signal)
                    ):
                        continue

                    price_at_signal = float(signal.get('current_price', 0))
                    
                    if price_at_signal == 0:
                        continue
                    
                    df, _ = self._fetch_market_data_for_signal(
                        signal,
                        price_fetcher
                    )
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
                            'action_should': self._scoped_action(
                                'LONG',
                                system_type
                            ),
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
                            'action_should': self._scoped_action(
                                'SHORT',
                                system_type
                            ),
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

        all_signals_data = (
            self.db.get_signals_for_stats(
                days_back=90
            )
        )

        if not all_signals_data:

            print(
                "   ⚠️ No hay señales suficientes"
            )

            return {
                'specific': 0,
                'general': 0
            }

        cohort_counts = {
            'input_records': len(all_signals_data),
            'eligible_records': 0,
            'spot_records': 0,
            'futures_real_executable_records': 0,
            'legacy_futures_quarantined': 0,
            'futures_shadow_excluded': 0
        }
        signals_data = []

        for candidate in all_signals_data:
            market = self._normalize_system_type(
                candidate.get('system_type')
            )
            if market == 'spot':
                cohort_counts['spot_records'] += 1
            elif not self._is_clean_futures_signal(candidate):
                cohort_counts['legacy_futures_quarantined'] += 1
            elif not self._is_signal_eligible_for_profit_stats(candidate):
                cohort_counts['futures_shadow_excluded'] += 1

            if self._is_signal_eligible_for_profit_stats(candidate):
                signals_data.append(candidate)
                if market == 'futures':
                    cohort_counts[
                        'futures_real_executable_records'
                    ] += 1

        cohort_counts['eligible_records'] = len(signals_data)

        print(
            f"   📈 Registros recibidos: {len(all_signals_data)} | "
            f"aptos para rentabilidad: {len(signals_data)}"
        )
        print(
            "   🧪 Cohorte Futures: "
            f"reales+publicables="
            f"{cohort_counts['futures_real_executable_records']} | "
            f"shadow excluidos={cohort_counts['futures_shadow_excluded']} | "
            f"antiguos en cuarentena="
            f"{cohort_counts['legacy_futures_quarantined']}"
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

                        action = self._scoped_action(
                            signal.get('action_normalized'),
                            signal.get('system_type')
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

                system_type = self._normalize_system_type(
                    signal.get('system_type')
                )

                action = self._scoped_action(
                    signal.get('action_normalized'),
                    system_type
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
                    general_strategy = self._general_strategy_key(
                        strategy,
                        system_type
                    )

                    g = general_stats[
                        general_strategy
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

            'learning_cohort':
                cohort_counts,

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

                market_scope = self._scope_from_action(action)
                cohort_label = (
                    FUTURES_REAL_COHORT
                    if market_scope == 'futures'
                    else SPOT_LEARNING_COHORT
                )
                notes += (
                    f" | MARKET={market_scope.upper()}"
                    f" | COHORT={cohort_label}"
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

    def _get_market_recommendation(
        self,
        symbol: str,
        timeframe: str,
        direction: str,
        system_type: str
    ) -> Optional[Dict]:
        """Obtiene sólo recomendaciones identificadas con su mercado/cohorte."""
        market = str(system_type or '').strip().lower()
        if market not in ('spot', 'futures'):
            return None

        scoped_action = self._scoped_action(direction, market)
        recommendation = self.db.get_recommendations(
            symbol,
            timeframe,
            scoped_action
        )
        if not recommendation:
            return None

        notes = str(recommendation.get('notes', '') or '').upper()
        expected_market = f'MARKET={market.upper()}'
        expected_cohort = (
            FUTURES_REAL_COHORT
            if market == 'futures'
            else SPOT_LEARNING_COHORT
        )

        # Las recomendaciones antiguas no indican de qué mercado proceden.
        # Fallamos de forma neutral en vez de reutilizarlas a ciegas.
        if (
            expected_market not in notes
            or f'COHORT={expected_cohort}' not in notes
        ):
            return None

        return recommendation
    
    # ========================================================================
    # 5. CONSULTAS PARA EL FRONTEND
    # ========================================================================
    
    def get_confidence_adjustment(self, symbol: str, timeframe: str, action: str,
                                  min_sample_size: int = 10,
                                  system_type: Optional[str] = None) -> float:
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

            market = str(system_type or '').strip().lower()
            if market not in ('spot', 'futures'):
                return 1.0  # mercado no identificado = autoridad neutral

            direction = (
                'LONG'
                if action in ('LONG', 'COMPRA_SPOT')
                else 'SHORT'
            )
            rec = self._get_market_recommendation(
                symbol,
                timeframe,
                direction,
                market
            )
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
    
    def get_recommendations_for(
        self,
        symbol: str,
        timeframe: str,
        action: str,
        system_type: str = 'spot'
    ) -> Dict:
        """
        Retorna recomendaciones cacheadas para un contexto específico.
        Uso desde endpoint /api/review/recommendations/<symbol>/<tf>/<action>
        """
        if not self.db.enabled:
            return {'available': False, 'message': 'Supabase no configurado'}
        
        direction = (
            'LONG'
            if action in ('LONG', 'COMPRA_SPOT')
            else 'SHORT'
        )
        rec = self._get_market_recommendation(
            symbol,
            timeframe,
            direction,
            system_type
        )
        if not rec:
            return {
                'available': False,
                'message': 'Aún no hay suficientes datos históricos para esta combinación',
                'symbol': symbol,
                'timeframe': timeframe,
                'action': self._scoped_action(direction, system_type),
                'system_type': self._normalize_system_type(system_type)
            }
        
        return {
            'available': True,
            'system_type': self._normalize_system_type(system_type),
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

        result = []
        for stat in stats:
            stored_strategy = str(stat.get('strategy', '') or '')
            is_futures = stored_strategy.upper().startswith('FUTURES::')
            display_strategy = (
                stored_strategy.split('::', 1)[1]
                if is_futures
                else stored_strategy
            )
            result.append({
                'system_type': 'futures' if is_futures else 'spot',
                'strategy': display_strategy,
                'win_rate': stat.get('win_rate', 0),
                'expectancy': stat.get('expectancy', 0),
                'sample': stat.get('total_signals', 0),
                'best_symbols': stat.get('best_symbols', []),
                'worst_symbols': stat.get('worst_symbols', []),
                'best_timeframes': stat.get('best_timeframes', []),
                'worst_timeframes': stat.get('worst_timeframes', []),
                'is_degrading': stat.get('is_degrading', False)
            })

        return result
    
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

            explicit_market = str(
                capas.get('system_type')
                or capas.get('_system_type')
                or ''
            ).strip().lower()
            if explicit_market not in ('spot', 'futures'):
                return (
                    'NEUTRAL',
                    0,
                    [],
                    ['Mercado Spot/Futures no identificado; ReviewTrader neutral']
                )
            
            # Recolectar estrategias detectadas por otros traders desde las capas
            active_strategies = self._collect_strategies_from_layers(capas)
            
            if not active_strategies:
                print(f"   ⚠️ No hay estrategias activas para evaluar")
                return 'NEUTRAL', 30, [], ['Sin estrategias activas para evaluar']
            
            print(f"   📋 Estrategias activas: {active_strategies}")
            
            # Consultar exclusivamente el historial del mercado actual.
            rec_long = self._get_market_recommendation(
                symbol,
                timeframe,
                'LONG',
                explicit_market
            )
            rec_short = self._get_market_recommendation(
                symbol,
                timeframe,
                'SHORT',
                explicit_market
            )
            
            # Evaluar coincidencia con ganadoras live/históricas del sistema.
            long_score = self._evaluate_match(active_strategies, rec_long)
            short_score = self._evaluate_match(active_strategies, rec_short)

            # COMMIT J — Backtest causal/OOS como PRIOR, no como muestra live.
            # Puede reforzar/atenuar un voto que ya tiene estrategias activas,
            # pero jamás inventa LONG/SHORT por sí solo ni toca Entry/SL/TP.
            research_long = {'state': 'UNAVAILABLE', 'support_score': 0.0, 'penalty_score': 0.0}
            research_short = {'state': 'UNAVAILABLE', 'support_score': 0.0, 'penalty_score': 0.0}
            try:
                from research_evidence_fusion import edge_prior
                regime = str(
                    (capas.get('futures_quantitative_context') or {}).get('regime')
                    or (capas.get('market_regime') or {}).get('regime')
                    or ''
                ).upper() or None
                strategy_blob = ' | '.join(str(x).upper() for x in active_strategies)
                runtime_features = {
                    'has_pullback': 'YES' if ('PULLBACK' in strategy_blob or 'RETEST' in strategy_blob) else 'NO',
                    'has_sweep': 'YES' if ('SWEEP' in strategy_blob or 'LIQUIDITY' in strategy_blob) else 'NO',
                    'has_order_block': 'YES' if ('ORDER_BLOCK' in strategy_blob or 'ORDER BLOCK' in strategy_blob) else 'NO',
                }
                research_long = edge_prior(symbol, timeframe, 'LONG', explicit_market, regime=regime, runtime_features=runtime_features)
                research_short = edge_prior(symbol, timeframe, 'SHORT', explicit_market, regime=regime, runtime_features=runtime_features)

                def _fuse(existing, prior):
                    support=float(prior.get('support_score') or 0.0)
                    penalty=float(prior.get('penalty_score') or 0.0)
                    # With no local score, causal evidence alone tops out below
                    # the 60-point voting gate: evidence supports, never creates.
                    fused=(0.65*float(existing) + 0.35*support) if existing > 0 else (0.35*support)
                    return max(0.0, min(100.0, fused-penalty))

                long_score = _fuse(long_score, research_long)
                short_score = _fuse(short_score, research_short)
            except Exception as research_error:
                logger.debug('Research evidence prior no disponible: %s', research_error)

            print(f"   📈 Score LONG fusionado: {long_score:.1f} | Research={research_long.get('state')}")
            print(f"   📉 Score SHORT fusionado: {short_score:.1f} | Research={research_short.get('state')}")
            
            # Decisión
            if long_score > 60 and long_score > short_score + 15:
                accion = (
                    'LONG'
                    if explicit_market == 'futures'
                    else 'COMPRA_SPOT'
                )
                confianza = min(95, long_score)
                estrategias_detectadas.append('REVIEW_HISTORICO_GANADOR_LONG')
                razones.append(f"Coincidencia con estrategias ganadoras históricas (score {long_score:.0f})")
                if rec_long:
                    razones.append(f"Basado en {rec_long.get('sample_size', 0)} señales live/históricas")
                if research_long.get('state') in ('OOS_VALIDATED','OOS_PLUS_SHADOW'):
                    bp=research_long.get('best_positive') or {}
                    razones.append(
                        f"Research causal OOS apoya LONG: {bp.get('oos_exp_r')}R, "
                        f"PF {bp.get('oos_pf')}, N={bp.get('oos_n')}"
                    )
                    estrategias_detectadas.append('RESEARCH_CAUSAL_OOS_LONG')
                    
            elif short_score > 60 and short_score > long_score + 15:
                accion = (
                    'SHORT'
                    if explicit_market == 'futures'
                    else 'VENTA_SPOT'
                )
                confianza = min(95, short_score)
                estrategias_detectadas.append('REVIEW_HISTORICO_GANADOR_SHORT')
                razones.append(f"Coincidencia con estrategias ganadoras históricas (score {short_score:.0f})")
                if rec_short:
                    razones.append(f"Basado en {rec_short.get('sample_size', 0)} señales live/históricas")
                if research_short.get('state') in ('OOS_VALIDATED','OOS_PLUS_SHADOW'):
                    bp=research_short.get('best_positive') or {}
                    razones.append(
                        f"Research causal OOS apoya SHORT: {bp.get('oos_exp_r')}R, "
                        f"PF {bp.get('oos_pf')}, N={bp.get('oos_n')}"
                    )
                    estrategias_detectadas.append('RESEARCH_CAUSAL_OOS_SHORT')
                    
            elif (
                research_long.get('state') == 'NEGATIVE_OOS'
                and research_short.get('state') == 'NEGATIVE_OOS'
            ) or self._detect_loser_pattern(active_strategies, rec_long, rec_short):
                accion = 'NO_OPERAR'
                confianza = 75
                estrategias_detectadas.append('REVIEW_PATRON_PERDEDOR')
                razones.append("Estrategias activas coinciden con evidencia perdedora live y/o OOS causal")
                
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
    # COMMIT 4 — REVIEWTRADER ADAPTIVE AUTOPILOT
    # ========================================================================

    def run_adaptive_autopilot(self, price_fetcher=None) -> Dict:
        """
        Convierte evidencia acumulada en perfiles versionados y reversibles.

        Importante:
        - con muestra insuficiente retorna OBSERVE y no cambia producción;
        - evidencia negativa robusta sólo puede PROTEGER/reducir riesgo;
        - crecimiento de leverage exige evidencia positiva mucho más fuerte;
        - Gemini/Groq no tienen autoridad para promover configuraciones;
        - toda transición queda auditada en Supabase.
        """
        try:
            from adaptive_autopilot import run_autopilot_cycle
            result = run_autopilot_cycle(
                self.db,
                price_fetcher=price_fetcher
            )
            if result.get('success'):
                logger.info(
                    'C4 Autopilot: %s profiles, %s transitions',
                    result.get('profiles_updated', 0),
                    len(result.get('strategy_transitions', []) or [])
                )
            return result
        except Exception as exc:
            logger.error('C4 Autopilot fallback: %s', exc)
            return {
                'version': 'C4_REVIEWTRADER_AUTOPILOT_V1',
                'success': False,
                'reason': f'FAIL_OPEN:{type(exc).__name__}',
                'error': str(exc)[:180],
            }

    # ========================================================================
    # COMMIT 7 — EDGE DISCOVERY ENGINE
    # ========================================================================

    def run_edge_discovery(self) -> Dict:
        """
        Busca subconjuntos con mejor/peor expectancy usando sólo evidencia
        persistida. Es investigación: nunca cambia producción.
        """
        try:
            from edge_discovery import run_edge_discovery
            result = run_edge_discovery(self.db, days_back=90)
            logger.info(
                'C7 Edge Discovery: rows=%s priority=%s',
                result.get('rows_scanned', 0),
                len((result.get('futures_shadow') or {}).get('priority') or [])
            )
            return result
        except Exception as exc:
            logger.error('C7 Edge Discovery fallback: %s', exc)
            return {
                'version': 'C7_EDGE_DISCOVERY_V1',
                'authority': 'RESEARCH_ONLY',
                'production_change': False,
                'success': False,
                'reason': f'FAIL_OPEN:{type(exc).__name__}',
                'error': str(exc)[:180],
            }

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
            'edge_discovery': {},
            'adaptive_autopilot': {},
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
        
        # 4. Descubrimiento de edge — sólo investigación, sin autoridad.
        try:
            results['edge_discovery'] = self.run_edge_discovery()
        except Exception as e:
            err_msg = f"run_edge_discovery: {str(e)[:200]}"
            logger.error(err_msg)
            warnings.append(err_msg)

        # 5. Autopilot gobernado — consume evidencia sólo bajo sus guardrails.
        try:
            results['adaptive_autopilot'] = self.run_adaptive_autopilot(
                price_fetcher=price_fetcher
            )
        except Exception as e:
            err_msg = f"run_adaptive_autopilot: {str(e)[:200]}"
            logger.error(err_msg)
            warnings.append(err_msg)

        # 6. Optimizaciones de almacenamiento
        try:
            results['optimization'] = self.apply_optimization_cleanup()
        except Exception as e:
            err_msg = f"apply_optimization_cleanup: {str(e)[:200]}"
            logger.error(err_msg)
            errors.append(err_msg)
        
        run_finished = datetime.utcnow()
        duration = (run_finished - run_started).total_seconds()
        
        # 6. Registrar log completo en Supabase
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
