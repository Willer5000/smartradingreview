# analytics_service.py
# Servicio de análisis estadístico del sistema
# Consume Supabase y devuelve datos listos para gráficos Plotly
# Fase B - Backend de la pestaña /analytics

import json
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from supabase_client import supabase_db
from edge_discovery import build_edge_discovery_summary
from promotion_governance import get_promotion_governance_status
from learning_integrity import build_integrity_manifest
from trader_intelligence import (
    build_trader_scorecard,
    build_trader_intelligence_v2_summary,
)
from dynamic_expert_committee import build_shadow_profile, install_shadow_profile
from execution_challenger_lab import summarize_execution_challenger_evidence

logger = logging.getLogger('ANALYTICS')
# ============================================================================
# QUALITY ENGINE Q5 — ANALYTICS V2
# ============================================================================
#
# Q5 mide exclusivamente la cohorte matemática actual.
#
# LEGACY:
#     se conserva como histórico, pero NO contamina estos KPIs.
#
# FUTURES SHADOW:
#     se muestra por separado, pero NO entra en WR/PnL oficial.
#
# ============================================================================
Q5_CURRENT_QUALITY_SCORE_VERSION = (
    '36W_V2_NORMALIZED'
)

Q5_ANALYTICS_VERSION = (
    'Q5_ANALYTICS_V2_V1'
)

def _cap_confidence(v):
    """
    Cap defensivo para lectura de confianza desde BD.
    Rows históricos pre-fix pueden contener valores >100 que corrompen la UI.
    """
    try:
        return max(0.0, min(100.0, float(v or 0)))
    except (TypeError, ValueError):
        return 0.0


class AnalyticsService:
    """
    Servicio que agrega estadísticas para el frontend de análisis.
    Todos los métodos aceptan filtros opcionales: symbol, timeframe, system_type, action, days_back.
    """
    
    def __init__(self):
        self.db = supabase_db
    
    # ========================================================================
    # HELPER: construir query de signals con filtros
    # ========================================================================
    
    def _fetch_signals_with_results(self, symbol: str = None, timeframe: str = None,
                                     system_type: str = None, action: str = None,
                                     days_back: int = 90) -> List[Dict]:
        """
        Retorna las señales resueltas (tp_hit, sl_hit, expired) 
        con sus estrategias y resultados agregados.
        """
        if not self.db.enabled:
            return []
        
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            
            query = (self.db.client.table('signals')
                     .select('*, signal_indicators(strategy_name), signal_results(status, pnl_pct, exit_price, exit_timestamp)')
                     .gte('created_at', cutoff)
                     .neq('status', 'pending'))
            
            if symbol:
                query = query.eq('symbol', symbol)
            if timeframe:
                query = query.eq('timeframe', timeframe)
            if system_type and system_type != 'both':
                query = query.eq('system_type', system_type)
            if action and action != 'ALL':
                query = query.eq('action_normalized', action)
            
            response = query.order('created_at', desc=True).limit(2000).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching signals: {e}")
            return []
    # ========================================================================
    # QUALITY ENGINE Q5 — HELPERS V2
    # ========================================================================

    @staticmethod
    def _q5_float(
        value,
        default=None
    ):
        try:

            if value is None:
                return default

            number = float(
                value
            )

            return (
                number
                if math.isfinite(
                    number
                )
                else default
            )

        except (
            TypeError,
            ValueError
        ):
            return default


    @staticmethod
    def _q5_bool(
        value
    ):
        if isinstance(
            value,
            bool
        ):
            return value

        if isinstance(
            value,
            str
        ):
            return (
                value
                .strip()
                .lower()
                in (
                    '1',
                    'true',
                    'yes',
                    'si',
                    'sí'
                )
            )

        return bool(
            value
        )


    @staticmethod
    def _q5_context(
        signal
    ):
        raw = (
            (
                signal
                or {}
            ).get(
                'context',
                {}
            )
            or {}
        )

        if isinstance(
            raw,
            str
        ):

            try:
                raw = json.loads(
                    raw
                )

            except Exception:
                return {}

        return (
            raw
            if isinstance(
                raw,
                dict
            )
            else {}
        )


    @classmethod
    def _q5_execution(
        cls,
        signal
    ):
        context = (
            cls._q5_context(
                signal
            )
        )

        execution = (
            context.get(
                'execution',
                {}
            )
            or {}
        )

        return (
            execution
            if isinstance(
                execution,
                dict
            )
            else {}
        )


    @classmethod
    def _q5_learning(
        cls,
        signal
    ):
        context = (
            cls._q5_context(
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


    @staticmethod
    def _q5_result(
        signal
    ):
        results = (
            (
                signal
                or {}
            ).get(
                'signal_results',
                []
            )
            or []
        )

        if isinstance(
            results,
            list
        ):

            if (
                results
                and isinstance(
                    results[0],
                    dict
                )
            ):
                return results[0]

            return {}

        return (
            results
            if isinstance(
                results,
                dict
            )
            else {}
        )


    @classmethod
    def _q5_status(
        cls,
        signal
    ):
        status = str(
            (
                signal
                or {}
            ).get(
                'status',
                ''
            )
            or ''
        ).strip().lower()

        if status:
            return status

        result = (
            cls._q5_result(
                signal
            )
        )

        return str(
            result.get(
                'status',
                ''
            )
            or ''
        ).strip().lower()


    @classmethod
    def _q5_is_v2(
        cls,
        signal
    ):
        execution = (
            cls._q5_execution(
                signal
            )
        )

        return (
            str(
                execution.get(
                    'quality_score_version',
                    ''
                )
                or ''
            )
            .strip()
            .upper()
            ==
            Q5_CURRENT_QUALITY_SCORE_VERSION
        )


    @staticmethod
    def _q5_is_directional(
        signal
    ):
        action = str(
            (
                signal
                or {}
            ).get(
                'action_normalized'
            )
            or (
                signal
                or {}
            ).get(
                'action'
            )
            or ''
        ).strip().upper()

        return action in (
            'LONG',
            'SHORT',
            'COMPRA_SPOT',
            'VENTA_SPOT'
        )


    @staticmethod
    def _q5_safety_band(
        safety
    ):
        if safety is None:
            return 'SIN_DATO'

        if safety < 65:
            return '<65'

        if safety < 70:
            return '65-69'

        if safety < 75:
            return '70-74'

        return '>=75'


    # ========================================================================
    # Q5 — AGREGADOR ECONÓMICO
    # ========================================================================

    @classmethod
    def _q5_aggregate(
        cls,
        signals,
        include_bands=True
    ):
        signals = list(
            signals
            or []
        )

        tp_count = 0
        sl_count = 0
        expired_count = 0
        pending_count = 0
        ambiguous_count = 0

        pnl_values = []
        realized_r_values = []

        safety_values = []
        entry_values = []
        sl_quality_values = []
        tp_quality_values = []

        q2_refined = 0

        q3_counts = {
            'ALIGNED':
                0,

            'NEUTRAL':
                0,

            'CONFLICT':
                0,

            'OTHER':
                0
        }

        band_rows = defaultdict(
            list
        )

        for signal in signals:

            status = (
                cls._q5_status(
                    signal
                )
            )

            if status == 'tp_hit':
                tp_count += 1

            elif status == 'sl_hit':
                sl_count += 1

            elif status == 'expired':
                expired_count += 1

            elif status in (
                'ambiguous',
                'ambiguous_result'
            ):
                ambiguous_count += 1

            elif status == 'pending':
                pending_count += 1

            execution = (
                cls._q5_execution(
                    signal
                )
            )

            learning = (
                cls._q5_learning(
                    signal
                )
            )

            # ==============================================================
            # SAFETY
            # ==============================================================

            system_type = str(
                signal.get(
                    'system_type',
                    ''
                )
                or ''
            ).strip().lower()

            # PRE38-B:
            # Execution Safety es una métrica operativa de Futures.
            # Spot no dispone actualmente de un Execution Safety comparable.
            #
            # Por eso, en Spot:
            # - NO convertir ausencia de Safety en 0;
            # - NO clasificarla falsamente dentro de <65;
            # - mostrarla como dato no disponible;
            # - enviarla a la banda SIN_DATO.
            if system_type == 'spot':
                safety = None

            else:
                safety = (
                    cls._q5_float(
                        execution.get(
                            'execution_safety'
                        )
                    )
                )

            if safety is not None:

                safety_values.append(
                    safety
                )

            band_rows[
                cls._q5_safety_band(
                    safety
                )
            ].append(
                signal
            )

            # ==============================================================
            # ENTRY QUALITY
            # ==============================================================

            entry_quality = (
                cls._q5_float(
                    execution.get(
                        'entry_score'
                    )
                )
            )

            if entry_quality is not None:

                entry_values.append(
                    entry_quality
                )

            # ==============================================================
            # SL QUALITY
            # ==============================================================

            sl_quality = (
                cls._q5_float(
                    execution.get(
                        'sl_reliability'
                    )
                )
            )

            if sl_quality is not None:

                # Históricamente sl_reliability puede venir 0–1.
                if (
                    0
                    <= sl_quality
                    <= 1
                ):

                    sl_quality *= 100.0

                sl_quality_values.append(
                    sl_quality
                )

            # ==============================================================
            # TP QUALITY
            # ==============================================================

            tp_quality = (
                cls._q5_float(
                    execution.get(
                        'tp_quality_score'
                    )
                )
            )

            if tp_quality is not None:

                tp_quality_values.append(
                    tp_quality
                )

            # ==============================================================
            # Q2
            # ==============================================================

            if cls._q5_bool(
                execution.get(
                    'futures_execution_refined',
                    False
                )
            ):

                q2_refined += 1

            # ==============================================================
            # Q3
            # ==============================================================

            micro = (
                learning.get(
                    'microstructure_shadow',
                    {}
                )
                or {}
            )

            if (
                isinstance(
                    micro,
                    dict
                )
                and micro
            ):

                alignment = str(
                    micro.get(
                        'alignment',
                        ''
                    )
                    or ''
                ).strip().upper()

                if alignment in q3_counts:

                    q3_counts[
                        alignment
                    ] += 1

                else:

                    q3_counts[
                        'OTHER'
                    ] += 1

            # ==============================================================
            # PnL Y EXPECTANCY R
            # ==============================================================

            if status not in (
                'tp_hit',
                'sl_hit'
            ):
                continue

            result = (
                cls._q5_result(
                    signal
                )
            )

            pnl = (
                cls._q5_float(
                    result.get(
                        'pnl_pct'
                    )
                )
            )

            if pnl is None:
                continue

            pnl_values.append(
                pnl
            )

            entry = (
                cls._q5_float(
                    signal.get(
                        'entry_price'
                    )
                )
            )

            stop_loss = (
                cls._q5_float(
                    signal.get(
                        'stop_loss'
                    )
                )
            )

            if (
                entry is not None
                and stop_loss is not None
                and entry > 0
            ):

                risk_pct = (
                    abs(
                        entry
                        - stop_loss
                    )
                    / entry
                    * 100.0
                )

                if risk_pct > 0:

                    realized_r_values.append(
                        pnl
                        / risk_pct
                    )

        resolved = (
            tp_count
            + sl_count
        )

        win_rate = (
            tp_count
            / resolved
            * 100.0
            if resolved
            else 0.0
        )

        wins = [
            pnl
            for pnl
            in pnl_values
            if pnl > 0
        ]

        losses = [
            pnl
            for pnl
            in pnl_values
            if pnl < 0
        ]

        total_wins = sum(
            wins
        )

        total_losses = abs(
            sum(
                losses
            )
        )

        profit_factor = (
            total_wins
            / total_losses
            if total_losses > 0
            else (
                total_wins
                if total_wins > 0
                else 0.0
            )
        )

        data = {
            'total_directional':
                len(
                    signals
                ),

            'pending':
                pending_count,

            'resolved':
                resolved,

            'tp_hit':
                tp_count,

            'sl_hit':
                sl_count,

            'expired':
                expired_count,

            'ambiguous':
                ambiguous_count,

            'win_rate':
                round(
                    win_rate,
                    2
                ),

            'pnl_total_pct':
                round(
                    sum(
                        pnl_values
                    ),
                    3
                ),

            'avg_pnl_pct':
                round(
                    (
                        sum(
                            pnl_values
                        )
                        / len(
                            pnl_values
                        )
                    )
                    if pnl_values
                    else 0.0,
                    4
                ),

            'profit_factor':
                round(
                    profit_factor,
                    3
                ),

            # ==========================================================
            # EXPECTANCY R REAL
            # ==========================================================
            #
            # No presupone que cada TP vale +2R.
            #
            # Cada operación utiliza:
            #
            # PnL realizado
            # ----------------
            # riesgo Entry-SL
            #
            # ==========================================================

            'expectancy_r':
                round(
                    (
                        sum(
                            realized_r_values
                        )
                        / len(
                            realized_r_values
                        )
                    )
                    if realized_r_values
                    else 0.0,
                    4
                ),

            'expectancy_r_samples':
                len(
                    realized_r_values
                ),

            'avg_safety':
                (
                    round(
                        sum(
                            safety_values
                        )
                        / len(
                            safety_values
                        ),
                        2
                    )
                    if safety_values
                    else None
                ),

            'avg_entry_quality':
                (
                    round(
                        sum(
                            entry_values
                        )
                        / len(
                            entry_values
                        ),
                        2
                    )
                    if entry_values
                    else None
                ),

            'avg_sl_quality':
                (
                    round(
                        sum(
                            sl_quality_values
                        )
                        / len(
                            sl_quality_values
                        ),
                        2
                    )
                    if sl_quality_values
                    else None
                ),

            'avg_tp_quality':
                (
                    round(
                        sum(
                            tp_quality_values
                        )
                        / len(
                            tp_quality_values
                        ),
                        2
                    )
                    if tp_quality_values
                    else None
                ),

            'q2_refined':
                q2_refined,

            'q3_alignment':
                q3_counts
        }

        # Q6-F: absence of observations is not zero performance.
        data['pnl_basis'] = 'OBSERVED_GROSS_BEFORE_COSTS'
        data['resolved_pnl_samples'] = len(pnl_values)
        if not resolved:
            data['win_rate'] = None
        if not pnl_values:
            data['pnl_total_pct'] = None
            data['avg_pnl_pct'] = None
        if not realized_r_values:
            data['expectancy_r'] = None
        if total_losses == 0:
            data['profit_factor'] = None
            data['profit_factor_status'] = 'NO_LOSSES' if total_wins else 'NO_RESULTS'
        if include_bands:

            data[
                'safety_bands'
            ] = {
                label:
                    cls._q5_aggregate(
                        band_rows.get(
                            label,
                            []
                        ),
                        include_bands=False
                    )

                for label
                in (
                    '<65',
                    '65-69',
                    '70-74',
                    '>=75',
                    'SIN_DATO'
                )
            }

        return data

    # ========================================================================
    # Q7C — ADAPTIVE INTRADAY STRATEGY LAB / ANALYTICS SHADOW
    # ========================================================================

    @classmethod
    def _q7_entry_activated(
        cls,
        signal
    ):
        """
        Detecta si el Entry llegó a activarse.

        No inventa Entry Hit cuando el resultado no permite demostrarlo.
        """
        status = cls._q5_status(
            signal
        )

        if status in (
            'tp_hit',
            'sl_hit'
        ):
            return True

        result = cls._q5_result(
            signal
        )

        notes = str(
            result.get(
                'notes',
                ''
            )
            or ''
        ).lower()

        if 'entry_touched=true' in notes:
            return True

        if 'entry_touched=false' in notes:
            return False

        return None


    @classmethod
    def _q7_group_metrics(
        cls,
        rows
    ):
        """
        Métricas económicas de un grupo Q7.

        Reutiliza el agregador económico Q5 para mantener exactamente
        la misma definición de WR, PnL, Expectancy y Profit Factor.
        """
        rows = list(
            rows
            or []
        )

        base = cls._q5_aggregate(
            rows,
            include_bands=False
        )

        activated = 0
        known_activation = 0

        for row in rows:

            value = cls._q7_entry_activated(
                row
            )

            if value is None:
                continue

            known_activation += 1

            if value:
                activated += 1

        base[
            'entry_activated'
        ] = activated

        base[
            'entry_activation_known'
        ] = known_activation

        base[
            'entry_activation_rate'
        ] = (
            round(
                activated
                / known_activation
                * 100.0,
                2
            )
            if known_activation
            else None
        )

        resolved = int(
            base.get(
                'resolved',
                0
            )
            or 0
        )

        # ==============================================================
        # POLÍTICA DE EVIDENCIA
        # ==============================================================
        #
        # <10 resueltas:
        #     insuficiente.
        #
        # 10–24:
        #     evidencia preliminar.
        #
        # >=25:
        #     puede ser revisada por humano,
        #     pero NUNCA promocionada automáticamente.
        # ==============================================================

        if resolved < 10:

            evidence_status = (
                'INSUFFICIENT_EVIDENCE'
            )

        elif resolved < 25:

            evidence_status = (
                'PRELIMINARY'
            )

        else:

            evidence_status = (
                'ELIGIBLE_FOR_HUMAN_REVIEW'
            )

        base[
            'evidence_status'
        ] = evidence_status

        base[
            'ready_for_automatic_promotion'
        ] = False

        base[
            'authority'
        ] = 'SHADOW_ONLY'

        return base


    @classmethod
    def _q7_build_cohort_summary(
        cls,
        rows
    ):
        """
        Construye las comparaciones internas de una cohorte Q7.

        IMPORTANTE:
        esta función recibe Oficial o Shadow por separado.
        Nunca mezcla ambas cohortes.
        """
        rows = list(
            rows
            or []
        )

        groups = {
            'profiles':
                defaultdict(
                    list
                ),

            'rsi_alignment':
                defaultdict(
                    list
                ),

            'profile_alignment':
                defaultdict(
                    list
                ),

            'vwap_states':
                defaultdict(
                    list
                ),

            'vwap_alignment':
                defaultdict(
                    list
                ),

            'breakout_retest_states':
                defaultdict(
                    list
                ),

            'breakout_retest_alignment':
                defaultdict(
                    list
                )
        }

        valid_rows = []

        for signal, q7 in rows:

            valid_rows.append(
                signal
            )

            profile = str(
                q7.get(
                    'active_profile',
                    'UNKNOWN'
                )
                or 'UNKNOWN'
            ).upper()

            groups[
                'profiles'
            ][
                profile
            ].append(
                signal
            )

            # ==========================================================
            # RSI ADAPTATIVO
            # ==========================================================

            rsi = (
                q7.get(
                    'rsi_profile',
                    {}
                )
                or {}
            )

            if isinstance(
                rsi,
                dict
            ):

                rsi_alignment = str(
                    rsi.get(
                        'alignment_with_system',
                        'NEUTRAL'
                    )
                    or 'NEUTRAL'
                ).upper()

                groups[
                    'rsi_alignment'
                ][
                    rsi_alignment
                ].append(
                    signal
                )

                groups[
                    'profile_alignment'
                ][
                    f'{profile}|{rsi_alignment}'
                ].append(
                    signal
                )

            # ==========================================================
            # VWAP
            # ==========================================================

            vwap = (
                q7.get(
                    'vwap_reversion',
                    {}
                )
                or {}
            )

            if isinstance(
                vwap,
                dict
            ):

                vwap_state = str(
                    vwap.get(
                        'state',
                        'UNKNOWN'
                    )
                    or 'UNKNOWN'
                ).upper()

                vwap_alignment = str(
                    vwap.get(
                        'alignment_with_system',
                        'NEUTRAL'
                    )
                    or 'NEUTRAL'
                ).upper()

                groups[
                    'vwap_states'
                ][
                    vwap_state
                ].append(
                    signal
                )

                groups[
                    'vwap_alignment'
                ][
                    vwap_alignment
                ].append(
                    signal
                )

            # ==========================================================
            # BREAKOUT + RETEST
            # ==========================================================

            retest = (
                q7.get(
                    'breakout_retest',
                    {}
                )
                or {}
            )

            if isinstance(
                retest,
                dict
            ):

                retest_state = str(
                    retest.get(
                        'state',
                        'UNKNOWN'
                    )
                    or 'UNKNOWN'
                ).upper()

                retest_alignment = str(
                    retest.get(
                        'alignment_with_system',
                        'NEUTRAL'
                    )
                    or 'NEUTRAL'
                ).upper()

                groups[
                    'breakout_retest_states'
                ][
                    retest_state
                ].append(
                    signal
                )

                groups[
                    'breakout_retest_alignment'
                ][
                    retest_alignment
                ].append(
                    signal
                )

        return {
            'observations':
                len(
                    valid_rows
                ),

            # ==========================================================
            # CONTROL
            # ==========================================================
            #
            # Ésta será nuestra referencia.
            #
            # No basta con que una estrategia gane.
            # Debe mejorar respecto al conjunto comparable.
            # ==========================================================

            'control':
                cls._q7_group_metrics(
                    valid_rows
                ),

            'profiles': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'profiles'
                    ].items()
                )
            },

            'rsi_alignment': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'rsi_alignment'
                    ].items()
                )
            },

            'profile_alignment': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'profile_alignment'
                    ].items()
                )
            },

            'vwap_states': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'vwap_states'
                    ].items()
                )
            },

            'vwap_alignment': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'vwap_alignment'
                    ].items()
                )
            },

            'breakout_retest_states': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'breakout_retest_states'
                    ].items()
                )
            },

            'breakout_retest_alignment': {
                key:
                    cls._q7_group_metrics(
                        value
                    )

                for key, value
                in sorted(
                    groups[
                        'breakout_retest_alignment'
                    ].items()
                )
            }
        }


    @classmethod
    def _q7_strategy_summary(
        cls,
        signals
    ):
        """
        Separa Q7 oficial y Q7 Shadow.

        La separación es obligatoria para impedir que resultados
        hipotéticos mejoren artificialmente los KPIs oficiales.
        """
        official_rows = []
        shadow_rows = []
        excluded = 0

        for signal in list(
            signals
            or []
        ):

            if str(
                signal.get(
                    'system_type',
                    ''
                )
                or ''
            ).strip().lower() != 'futures':

                continue

            learning = (
                cls._q5_learning(
                    signal
                )
            )

            q7 = (
                learning.get(
                    'q7_strategy_lab_shadow',
                    {}
                )
                or {}
            )

            if not isinstance(
                q7,
                dict
            ):
                continue

            if not q7.get(
                'shadow_only',
                False
            ):

                excluded += 1
                continue

            if str(
                q7.get(
                    'lab_version',
                    ''
                )
                or ''
            ) != 'Q7_STRATEGY_LAB_SHADOW_V1':

                excluded += 1
                continue

            if not cls._q5_bool(
                q7.get(
                    'eligible',
                    False
                )
            ):

                continue

            # ==========================================================
            # MISMO CONTRATO DE PROCEDENCIA FUTURES QUE Q5
            # ==========================================================

            clean_futures = (
                learning.get(
                    'cohort'
                )
                == 'FUTURES_PERPETUAL_REAL_CLOSED_V1'

                and learning.get(
                    'market_data_source'
                )
                == 'KUCOIN_FUTURES_PERPETUAL_REST'

                and not cls._q5_bool(
                    learning.get(
                        'market_data_is_synthetic',
                        True
                    )
                )

                and cls._q5_bool(
                    learning.get(
                        'source_candle_closed',
                        False
                    )
                )
            )

            if not clean_futures:

                excluded += 1
                continue

            evaluation_role = str(
                learning.get(
                    'evaluation_role',
                    ''
                )
                or ''
            ).strip().upper()

            statistically_eligible = (
                cls._q5_bool(
                    learning.get(
                        'statistically_eligible',
                        False
                    )
                )
            )

            pair = (
                signal,
                q7
            )

            # ==========================================================
            # OFICIAL
            # ==========================================================

            if (
                statistically_eligible
                and evaluation_role
                == 'EXECUTABLE_SIGNAL'
            ):

                official_rows.append(
                    pair
                )

            # ==========================================================
            # SHADOW
            # ==========================================================

            elif (
                evaluation_role
                == 'SHADOW_ANALYSIS'
            ):

                shadow_rows.append(
                    pair
                )

            else:

                excluded += 1

        return {
            'version':
                'Q7_STRATEGY_LAB_ANALYTICS_V1',

            'lab_version':
                'Q7_STRATEGY_LAB_SHADOW_V1',

            'mode':
                'SHADOW_ONLY',

            'authority_changed':
                False,

            'ready_for_automatic_promotion':
                False,

            'policy':
                'IMPROVE_QUALITY_DO_NOT_LOWER_SAFETY',

            # ==========================================================
            # NUNCA MEZCLAR RENTABILIDAD OFICIAL CON SHADOW
            # ==========================================================

            'official':
                cls._q7_build_cohort_summary(
                    official_rows
                ),

            'shadow':
                cls._q7_build_cohort_summary(
                    shadow_rows
                ),

            'excluded':
                excluded
        }


    # ========================================================================
    # Q5 — LEER COHORTE V2
    # ========================================================================

    def _fetch_q5_v2_signals(self, symbol=None, timeframe=None, system_type=None,
                             action=None, days_back=90):
        from q6_integrity import ReadRows, read_pages
        if not self.db.enabled:
            return ReadRows(coverage={'complete': False, 'errors': ['DB_UNAVAILABLE']})
        end = datetime.utcnow()
        cutoff = (end - timedelta(days=max(1, min(int(days_back), 365)))).isoformat()
        def query():
            q = (self.db.client.table('signals')
                 .select('id,symbol,timeframe,system_type,action_normalized,status,created_at,'
                         'entry_price,stop_loss,take_profit,risk_reward,'
                         'q6_learning:context->learning,q6_execution:context->execution,'
                         'signal_results(status,pnl_pct,exit_price,exit_timestamp,notes,created_at,'
                         'mfe_r,mae_r,mfe_pct,mae_pct,candles_to_result,execution_forensics)')
                 .gte('created_at', cutoff).lt('created_at', end.isoformat())
                 .eq('context->execution->>quality_score_version', Q5_CURRENT_QUALITY_SCORE_VERSION)
                 .in_('action_normalized', ['LONG', 'SHORT', 'COMPRA_SPOT', 'VENTA_SPOT'])
                 .order('created_at', desc=True).order('id', desc=True))
            if symbol:
                q = q.eq('symbol', symbol)
            if timeframe:
                q = q.eq('timeframe', timeframe)
            if system_type and system_type != 'both':
                q = q.eq('system_type', system_type)
            if action and action != 'ALL':
                q = q.eq('action_normalized', action)
            return q
        rows = read_pages(query)
        for row in rows:
            row['context'] = {'learning': row.pop('q6_learning', {}) or {},
                              'execution': row.pop('q6_execution', {}) or {}}
        return rows


    # ========================================================================
    # COMMIT 2 — EXECUTION LEARNING V2
    # ========================================================================

    @classmethod
    def _execution_forensics_summary(cls, rows):
        """
        Agrega diagnóstico de ejecución sin cambiar producción.

        Commit 6 añade métricas orientadas a la pregunta que hoy importa:
        no sólo si el Entry fue alcanzado, sino si fue defendible después de
        ser tocado. Todo sigue siendo observacional.
        """
        diagnoses = defaultdict(int)
        mfe_values = []
        mae_values = []
        entry_reached = 0
        stop_tight_suspects = 0
        post_stop_tp = 0
        post_stop_reclaims = 0
        resolved = 0
        sl_resolved = 0
        with_forensics = 0

        for signal in rows or []:
            results = signal.get('signal_results') or []
            if not isinstance(results, list) or not results:
                continue
            result = results[0] if isinstance(results[0], dict) else {}
            forensics = result.get('execution_forensics') or {}
            if not isinstance(forensics, dict) or not forensics:
                continue

            with_forensics += 1
            diagnosis = str(forensics.get('diagnosis') or 'UNKNOWN').upper()
            diagnoses[diagnosis] += 1

            if cls._q5_bool(forensics.get('entry_reached', False)):
                entry_reached += 1

            status = str(result.get('status') or signal.get('status') or '').lower()
            if status in ('tp_hit', 'sl_hit'):
                resolved += 1
            if status == 'sl_hit':
                sl_resolved += 1

            mfe = cls._q5_float(forensics.get('mfe_r'), None)
            mae = cls._q5_float(forensics.get('mae_r'), None)
            if mfe is None:
                mfe = cls._q5_float(result.get('mfe_r'), None)
            if mae is None:
                mae = cls._q5_float(result.get('mae_r'), None)
            if mfe is not None:
                mfe_values.append(mfe)
            if mae is not None:
                mae_values.append(mae)

            if cls._q5_bool(forensics.get('stop_was_possibly_tight', False)):
                stop_tight_suspects += 1

            recovery = forensics.get('post_stop_recovery') or {}
            if isinstance(recovery, dict):
                if cls._q5_bool(recovery.get('tp_reached_after_stop', False)):
                    post_stop_tp += 1
                if cls._q5_bool(recovery.get('reclaimed_entry', False)):
                    post_stop_reclaims += 1

        def _median(values):
            if not values:
                return None
            ordered = sorted(float(value) for value in values)
            midpoint = len(ordered) // 2
            if len(ordered) % 2:
                return ordered[midpoint]
            return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0

        direct_stops = int(diagnoses.get('STOPPED_WITHOUT_PROGRESS', 0))
        weak_progress = int(diagnoses.get('STOPPED_AFTER_WEAK_PROGRESS', 0))
        meaningful_progress = int(diagnoses.get('STOPPED_AFTER_MEANINGFUL_PROGRESS', 0))
        avg_mfe = (sum(mfe_values) / len(mfe_values)) if mfe_values else None
        avg_mae = (sum(mae_values) / len(mae_values)) if mae_values else None
        efficiency = None
        if avg_mfe is not None and avg_mae is not None and avg_mae > 0:
            efficiency = avg_mfe / avg_mae

        # Proxy descriptivo, NO probabilidad: entre Entries alcanzados, cuántos
        # no terminaron clasificados como stop prácticamente inmediato.
        defended_proxy = max(0, entry_reached - direct_stops)

        return {
            'version': 'COMMIT6_EXECUTION_OBSERVATORY_V1',
            'diagnostic_only': True,
            'n_with_forensics': with_forensics,
            'resolved': resolved,
            'sl_resolved': sl_resolved,
            'entry_reached': entry_reached,
            'entry_reach_rate_pct': (
                round(entry_reached / with_forensics * 100.0, 2)
                if with_forensics
                else None
            ),
            'entry_defensibility_proxy_pct': (
                round(defended_proxy / entry_reached * 100.0, 2)
                if entry_reached
                else None
            ),
            'direct_stop_rate_pct': (
                round(direct_stops / sl_resolved * 100.0, 2)
                if sl_resolved
                else None
            ),
            'weak_progress_stop_rate_pct': (
                round(weak_progress / sl_resolved * 100.0, 2)
                if sl_resolved
                else None
            ),
            'meaningful_progress_stop_rate_pct': (
                round(meaningful_progress / sl_resolved * 100.0, 2)
                if sl_resolved
                else None
            ),
            'avg_mfe_r': round(avg_mfe, 4) if avg_mfe is not None else None,
            'avg_mae_r': round(avg_mae, 4) if avg_mae is not None else None,
            'median_mfe_r': (
                round(_median(mfe_values), 4) if mfe_values else None
            ),
            'median_mae_r': (
                round(_median(mae_values), 4) if mae_values else None
            ),
            'mfe_mae_efficiency': (
                round(efficiency, 4) if efficiency is not None else None
            ),
            'stop_tight_suspects': stop_tight_suspects,
            'stop_tight_suspect_rate_pct': (
                round(stop_tight_suspects / sl_resolved * 100.0, 2)
                if sl_resolved
                else None
            ),
            'post_stop_tp_reached': post_stop_tp,
            'post_stop_tp_rate_pct': (
                round(post_stop_tp / sl_resolved * 100.0, 2)
                if sl_resolved
                else None
            ),
            'post_stop_entry_reclaimed': post_stop_reclaims,
            'post_stop_reclaim_rate_pct': (
                round(post_stop_reclaims / sl_resolved * 100.0, 2)
                if sl_resolved
                else None
            ),
            'diagnoses': dict(
                sorted(
                    diagnoses.items(),
                    key=lambda item: (-item[1], item[0])
                )
            )
        }

    @classmethod
    def _strategy_attribution_summary(cls, rows, top_n=20):
        """
        Atribuye outcomes sólo a la dirección que cada trader realmente votó.
        Evita acreditar un TP LONG a una estrategia que había votado SHORT.
        """
        groups = defaultdict(lambda: {
            'n': 0,
            'tp': 0,
            'sl': 0,
            'expired': 0,
            'entry_reached': 0,
            'r_sum': 0.0,
            'r_n': 0
        })
        signals_with_snapshot = 0

        for signal in rows or []:
            learning = cls._q5_learning(signal)
            attribution = learning.get('strategy_attribution_v2') or {}
            if not isinstance(attribution, dict):
                continue
            items = attribution.get('items') or []
            if not isinstance(items, list) or not items:
                continue
            signals_with_snapshot += 1

            status = str(signal.get('status') or '').lower()
            entry = cls._q5_float(signal.get('entry_price'), 0.0) or 0.0
            sl = cls._q5_float(signal.get('stop_loss'), 0.0) or 0.0
            tp = cls._q5_float(signal.get('take_profit'), 0.0) or 0.0
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            realized_r = None
            if risk > 0 and status == 'tp_hit':
                realized_r = reward / risk
            elif status == 'sl_hit':
                realized_r = -1.0

            results = signal.get('signal_results') or []
            forensics = {}
            if isinstance(results, list) and results and isinstance(results[0], dict):
                forensics = results[0].get('execution_forensics') or {}
            entry_was_reached = bool(
                isinstance(forensics, dict)
                and cls._q5_bool(forensics.get('entry_reached', False))
            ) or status in ('tp_hit', 'sl_hit')

            for item in items:
                if not isinstance(item, dict):
                    continue
                trader = str(item.get('trader') or 'UNKNOWN')
                strategy = str(item.get('strategy') or '').upper().strip()
                relation = str(item.get('relation_to_final') or 'UNKNOWN').upper()
                if not strategy:
                    continue
                key = (trader, strategy, relation)
                data = groups[key]
                data['n'] += 1
                if status == 'tp_hit':
                    data['tp'] += 1
                elif status == 'sl_hit':
                    data['sl'] += 1
                elif status == 'expired':
                    data['expired'] += 1
                if entry_was_reached:
                    data['entry_reached'] += 1
                if realized_r is not None:
                    data['r_sum'] += realized_r
                    data['r_n'] += 1

        result = []
        for (trader, strategy, relation), data in groups.items():
            resolved = data['tp'] + data['sl']
            result.append({
                'trader': trader,
                'strategy': strategy,
                'relation_to_final': relation,
                'n': data['n'],
                'resolved': resolved,
                'tp': data['tp'],
                'sl': data['sl'],
                'expired': data['expired'],
                'entry_reached': data['entry_reached'],
                'entry_activation_pct': (
                    round(data['entry_reached'] / data['n'] * 100.0, 2)
                    if data['n']
                    else None
                ),
                'win_rate_pct': (
                    round(data['tp'] / resolved * 100.0, 2)
                    if resolved
                    else None
                ),
                'expectancy_r': (
                    round(data['r_sum'] / data['r_n'], 4)
                    if data['r_n']
                    else None
                )
            })

        result.sort(
            key=lambda row: (
                -(row['resolved'] or 0),
                -(row['n'] or 0),
                row['trader'],
                row['strategy']
            )
        )
        return {
            'version': 'COMMIT2_STRATEGY_ATTRIBUTION_V2',
            'diagnostic_only': True,
            'signals_with_snapshot': signals_with_snapshot,
            'rows': result[:max(1, int(top_n))]
        }

    # ========================================================================
    # Q5 — RESUMEN V2 POR MERCADO
    # ========================================================================

    def get_quality_v2_summary(
        self,
        symbol=None,
        timeframe=None,
        system_type=None,
        action=None,
        days_back=90
    ):
        """
        Cohorte actual post-36W.

        LEGACY queda fuera.

        SPOT:
            señales direccionales V2.

        FUTURES OFICIAL:
            V2 + statistically_eligible +
            EXECUTABLE_SIGNAL.

        FUTURES SHADOW:
            diagnóstico separado.
            Nunca contamina WR/PnL oficial.
        """

        signals = (
            self._fetch_q5_v2_signals(
                symbol=symbol,
                timeframe=timeframe,
                system_type=system_type,
                action=action,
                days_back=days_back
            )
        )

        spot = []

        futures_official = []

        futures_shadow = []

        futures_other = []

        for signal in signals:

            market = str(
                signal.get(
                    'system_type',
                    ''
                )
                or ''
            ).strip().lower()

            if market == 'spot':
                from q6_integrity import verified_spot
                if verified_spot(signal):
                    spot.append(signal)
                continue

            if market != 'futures':
                continue

            learning = (
                self._q5_learning(
                    signal
                )
            )

            evaluation_role = str(
                learning.get(
                    'evaluation_role',
                    ''
                )
                or ''
            ).strip().upper()

            statistically_eligible = (
                self._q5_bool(
                    learning.get(
                        'statistically_eligible',
                        False
                    )
                )
            )

            clean_futures = (
                learning.get('cohort') == 'FUTURES_PERPETUAL_REAL_CLOSED_V1'
                and learning.get('market_data_source') == 'KUCOIN_FUTURES_PERPETUAL_REST'
                and not self._q5_bool(learning.get('market_data_is_synthetic', True))
                and self._q5_bool(learning.get('source_candle_closed', False))
            )
            if (
                clean_futures and statistically_eligible
                and evaluation_role == 'EXECUTABLE_SIGNAL'
            ):

                futures_official.append(
                    signal
                )

            elif (
                clean_futures and evaluation_role == 'SHADOW_ANALYSIS'
            ):

                futures_shadow.append(
                    signal
                )

            else:

                futures_other.append(
                    signal
                )

        official_combined = (
            spot
            + futures_official
        )

        # Commit 6 — calcular una sola vez las capas de observabilidad.
        forensics_spot = self._execution_forensics_summary(spot)
        forensics_futures = self._execution_forensics_summary(futures_official)
        forensics_shadow = self._execution_forensics_summary(futures_shadow)
        attribution_spot = self._strategy_attribution_summary(spot)
        attribution_futures = self._strategy_attribution_summary(futures_official)
        attribution_shadow = self._strategy_attribution_summary(futures_shadow)

        # COMMIT 7 — Edge Discovery utiliza exactamente las cohortes ya
        # separadas arriba. No hace otra consulta ni puede cambiar producción.
        try:
            edge_discovery = build_edge_discovery_summary(
                spot,
                futures_shadow,
                futures_official
            )
        except Exception as edge_error:
            edge_discovery = {
                'version': 'C7_EDGE_DISCOVERY_V1',
                'authority': 'RESEARCH_ONLY',
                'production_change': False,
                'status': f'UNAVAILABLE:{type(edge_error).__name__}',
                'error': str(edge_error)[:160],
                'futures_shadow': {'priority': [], 'watch': [], 'low_priority': []},
                'spot': {'priority': [], 'watch': [], 'low_priority': []},
                'early_failure_watch': {}
            }

        coverage = getattr(signals, 'coverage', {'complete': False}) or {'complete': False}

        resolved_futures = sum(
            1 for signal in futures_official
            if str(signal.get('status') or '').lower() in ('tp_hit', 'sl_hit')
        )
        resolved_spot = sum(
            1 for signal in spot
            if str(signal.get('status') or '').lower() in ('tp_hit', 'sl_hit')
        )

        # Commit 8: use the persisted lightweight full-window governance probe
        # rather than reinterpreting this heavier Analytics read as authority.
        try:
            promotion_governance = get_promotion_governance_status(self.db)
        except Exception as governance_error:
            promotion_governance = {
                'quality_optimization_allowed': False,
                'strategy_veto_authority_allowed': False,
                'risk_growth_allowed': False,
                'block_reasons': [f'GOVERNANCE_UNAVAILABLE:{type(governance_error).__name__}'],
                'coverage': {'complete': False},
                'evidence': {},
            }

        observatory_reasons = list(promotion_governance.get('block_reasons') or [])
        if resolved_spot < 25:
            observatory_reasons.append(f'SPOT_{resolved_spot}_DE_25_RESUELTAS')

        # COMMIT 10 — diagnostic-only scope manifest and trader scorecard.
        # IMPORTANT: the cohort selection above is intentionally unchanged.
        # Commit 10 measures the existing system before Commit 11 can adapt it.
        integrity_governance = promotion_governance if (
            not symbol
            and not timeframe
            and (not action or action == 'ALL')
            and (not system_type or system_type in ('both', 'futures'))
        ) else {}
        learning_integrity = build_integrity_manifest(
            spot_rows=spot,
            futures_official_rows=futures_official,
            futures_shadow_rows=futures_shadow,
            quality_score_version=Q5_CURRENT_QUALITY_SCORE_VERSION,
            coverage=getattr(signals, 'coverage', {}) or {},
            governance=integrity_governance,
        )
        scoped_trader_rows = {
            'SPOT_CURRENT_OFFICIAL': spot,
            'FUTURES_CURRENT_OFFICIAL': futures_official,
            'FUTURES_CURRENT_SHADOW': futures_shadow,
        }
        trader_scorecard = build_trader_scorecard(scoped_trader_rows)
        trader_intelligence_v2 = build_trader_intelligence_v2_summary(
            scoped_trader_rows
        )
        dynamic_expert_committee = build_shadow_profile(
            trader_intelligence_v2,
            promotion_governance,
        )
        # Lightweight in-process snapshot. Runtime voting only READS candidate
        # multipliers for shadow diagnostics; production weights remain intact.
        install_shadow_profile(dynamic_expert_committee)
        execution_challenger_lab = summarize_execution_challenger_evidence(
            scoped_trader_rows
        )

        return {
            'version':
                Q5_ANALYTICS_VERSION,

            'quality_score_version':
                Q5_CURRENT_QUALITY_SCORE_VERSION,

            'cohort_mode':
                'CURRENT_V2_ONLY',

            'legacy_included':
                False,

            'official_combined':
                self._q5_aggregate(
                    official_combined
                ),

            'spot':
                self._q5_aggregate(
                    spot
                ),

            'futures':
                self._q5_aggregate(
                    futures_official
                ),

            'futures_shadow':
                self._q5_aggregate(
                    futures_shadow
                ),

            # ==========================================================
            # COMMIT 2 — EXECUTION LEARNING / ATTRIBUTION
            # ==========================================================
            # Datos diagnósticos adicionales. El frontend actual puede
            # ignorarlos sin romper compatibilidad. Gemini/ReviewTrader
            # pueden utilizarlos como evidencia SHADOW/observacional.
            # ==========================================================
            'execution_forensics_v2': {
                'spot': forensics_spot,
                'futures_official': forensics_futures,
                'futures_shadow': forensics_shadow
            },

            'strategy_attribution_v2': {
                'spot': attribution_spot,
                'futures_official': attribution_futures,
                'futures_shadow': attribution_shadow
            },

            # COMMIT 7 — hipótesis falsables, research-only.
            'edge_discovery_v1': edge_discovery,

            # COMMIT 10 — observability only; no committee authority.
            'learning_integrity_v1': learning_integrity,
            'trader_intelligence_v1': trader_scorecard,
            'trader_intelligence_v2': trader_intelligence_v2,
            'dynamic_expert_committee_v1': dynamic_expert_committee,
            'execution_challenger_lab_v1': execution_challenger_lab,

            # ==========================================================
            # COMMIT 6 — LEARNING OBSERVATORY
            # ==========================================================
            # Sólo resume evidencia ya persistida. No recalibra ni modifica
            # ninguna decisión. La promoción permanece bloqueada mientras
            # la cohorte/costes no sean verificables.
            'learning_observatory_v1': {
                'version': 'COMMIT9_NET_EDGE_GOVERNANCE_V1',
                'diagnostic_only': False,
                # Positive authority here means quality selection only. It never
                # lowers Safety and Commit 8 never grows leverage.
                'calibration_allowed': bool(promotion_governance.get('quality_optimization_allowed', False)),
                'promotion_allowed': bool(promotion_governance.get('strategy_veto_authority_allowed', False)),
                'leverage_growth_allowed': bool(promotion_governance.get('risk_growth_allowed', False)),
                'block_reasons': observatory_reasons,
                'coverage_complete': bool((promotion_governance.get('coverage') or {}).get('complete', False)),
                'coverage': dict(promotion_governance.get('coverage') or {}),
                'promotion_governance': promotion_governance,
                'resolved': {
                    'spot': resolved_spot,
                    'futures_official': resolved_futures
                },
                'execution_forensics': {
                    'spot': forensics_spot,
                    'futures_official': forensics_futures,
                    'futures_shadow': forensics_shadow
                },
                'strategy_attribution': {
                    'spot': attribution_spot,
                    'futures_official': attribution_futures,
                    'futures_shadow': attribution_shadow
                },
                'learning_integrity': learning_integrity,
                'trader_intelligence': trader_scorecard
            },

            # ==========================================================
            # Q7C — ADAPTIVE INTRADAY STRATEGY LAB
            # ==========================================================
            #
            # Oficial y Shadow permanecen completamente separados.
            # Q7 continúa sin autoridad operativa.
            # ==========================================================

            'q7_strategy_lab':
                self._q7_strategy_summary(
                    signals
                ),

            'coverage': {
                **getattr(signals, 'coverage', {'complete': False}),
                'spot_unverified_excluded': sum(
                    1 for s in signals if s.get('system_type') == 'spot'
                    and s not in spot),
                'v2_directional_total':
                    len(
                        signals
                    ),

                'spot_v2':
                    len(
                        spot
                    ),

                'futures_official_v2':
                    len(
                        futures_official
                    ),

                'futures_shadow_v2':
                    len(
                        futures_shadow
                    ),

                'futures_other_v2':
                    len(
                        futures_other
                    ),

                'max_rows_guard':
                    4000
            },

            'days_back':
                days_back,

            'filters': {
                'symbol':
                    symbol,

                'timeframe':
                    timeframe,

                'system_type':
                    system_type,

                'action':
                    action
            }
        }    
    # ========================================================================
    # 1. RESUMEN (KPIs globales)
    # ========================================================================
    
    def get_summary(self, symbol: str = None, timeframe: str = None,
                    system_type: str = None, action: str = None,
                    days_back: int = 90) -> Dict:
        """
        Retorna KPIs globales: total señales, win_rate, expectancy, PnL total, etc.
        
        AMPLIADO v13: ahora incluye rendimiento económico completo:
          - pnl_total_pct: suma de todos los PnL % de operaciones resueltas
          - profit_factor: ganancia total / pérdida total (>1 rentable)
          - avg_pnl_per_trade: PnL medio por operación
          - best_trade / worst_trade: extremos
          - consecutive_wins / consecutive_losses: rachas
          - roi_estimated_1000_usd: ROI simulado con capital de 1000 USD
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        total = len(signals)
        tp_count = sum(1 for s in signals if s.get('status') == 'tp_hit')
        sl_count = sum(1 for s in signals if s.get('status') == 'sl_hit')
        expired_count = sum(1 for s in signals if s.get('status') == 'expired')
        missed_count = sum(1 for s in signals if s.get('status') == 'missed_opportunity')
        resolved = tp_count + sl_count
        
        win_rate = (tp_count / resolved * 100) if resolved > 0 else 0
        
        # ============ PnL de operaciones REALES (solo tp_hit / sl_hit) ============
        # Excluir missed_opportunity porque son NO_OPERAR con "PnL teórico" que no
        # es dinero real: contaminan el rendimiento económico del sistema.
        pnl_real_trades = []  # lista de PnL de operaciones que realmente se hicieron
        pnl_by_status_order = []  # para calcular rachas (por fecha)
        
        for s in signals:
            status = s.get('status')
            if status not in ('tp_hit', 'sl_hit'):
                continue
            results_data = s.get('signal_results', [])
            if isinstance(results_data, list) and results_data:
                pnl = results_data[0].get('pnl_pct')
                if pnl is not None:
                    pnl_val = float(pnl)
                    pnl_real_trades.append(pnl_val)
                    pnl_by_status_order.append((
                        s.get('created_at', ''),
                        status,
                        pnl_val
                    ))
        
        wins_pnl = [p for p in pnl_real_trades if p > 0]
        losses_pnl = [p for p in pnl_real_trades if p < 0]
        
        avg_win = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0
        avg_loss = abs(sum(losses_pnl) / len(losses_pnl)) if losses_pnl else 0
        
        # ============ EXPECTANCY (real, no asumida) ============
        expectancy = 0
        if resolved > 0:
            expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
        
        # ============ MÉTRICAS ECONÓMICAS ============
        # PnL total acumulado (suma de todos los PnL individuales)
        pnl_total_pct = sum(pnl_real_trades)
        
        # Profit factor: ganancia total / pérdida total
        total_wins = sum(wins_pnl) if wins_pnl else 0
        total_losses = abs(sum(losses_pnl)) if losses_pnl else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else (total_wins if total_wins > 0 else 0)
        
        # PnL promedio por trade
        avg_pnl_per_trade = (pnl_total_pct / len(pnl_real_trades)) if pnl_real_trades else 0
        
        # Mejor y peor trade
        best_trade_pct = max(pnl_real_trades) if pnl_real_trades else 0
        worst_trade_pct = min(pnl_real_trades) if pnl_real_trades else 0
        
        # Rachas (ordenadas cronológicamente)
        pnl_by_status_order.sort(key=lambda x: x[0])
        max_consec_wins = 0
        max_consec_losses = 0
        cur_wins = 0
        cur_losses = 0
        for _, status, _ in pnl_by_status_order:
            if status == 'tp_hit':
                cur_wins += 1
                cur_losses = 0
                max_consec_wins = max(max_consec_wins, cur_wins)
            elif status == 'sl_hit':
                cur_losses += 1
                cur_wins = 0
                max_consec_losses = max(max_consec_losses, cur_losses)
        
        # ROI estimado con capital fijo de 1000 USD y sizing 100% (simulación simple)
        # Cada operación multiplica el capital por (1 + pnl/100)
        # Nota: esto asume que se sale exactamente en el toque, sin slippage
        capital = 1000.0
        for _, _, pnl in pnl_by_status_order:
            capital *= (1 + pnl / 100)
        roi_1000 = ((capital - 1000.0) / 1000.0) * 100
        
        # Estrategias únicas activas
        strategies_seen = set()
        for s in signals:
            si = s.get('signal_indicators', [])
            if isinstance(si, list):
                for entry in si:
                    if isinstance(entry, dict) and entry.get('strategy_name'):
                        strategies_seen.add(entry['strategy_name'])
        
        return {
            'total_signals': total,
            'tp_hit': tp_count,
            'sl_hit': sl_count,
            'expired': expired_count,
            'missed_opportunity': missed_count,
            'resolved': resolved,
            'win_rate': round(win_rate, 2),
            'avg_win_pct': round(avg_win, 3),
            'avg_loss_pct': round(avg_loss, 3),
            'expectancy': round(expectancy, 3),
            'unique_strategies': len(strategies_seen),
            # ============ NUEVAS MÉTRICAS ECONÓMICAS ============
            'pnl_total_pct': round(pnl_total_pct, 2),
            'avg_pnl_per_trade': round(avg_pnl_per_trade, 3),
            'profit_factor': round(profit_factor, 2),
            'best_trade_pct': round(best_trade_pct, 2),
            'worst_trade_pct': round(worst_trade_pct, 2),
            'total_gains_pct': round(total_wins, 2),
            'total_losses_pct': round(-total_losses, 2),
            'max_consecutive_wins': max_consec_wins,
            'max_consecutive_losses': max_consec_losses,
            'roi_1000usd_estimated': round(roi_1000, 2),
            'is_profitable': profit_factor >= 1.0,
            # ============ FIN NUEVAS MÉTRICAS ============
            'days_back': days_back,
            'filters': {
                'symbol': symbol, 'timeframe': timeframe,
                'system_type': system_type, 'action': action
            }
        }
    
    # ========================================================================
    # 2. RANKING DE ESTRATEGIAS
    # ========================================================================
    
    def get_strategies_ranking(self, symbol: str = None, timeframe: str = None,
                                system_type: str = None, action: str = None,
                                days_back: int = 90, top_n: int = 30) -> List[Dict]:
        """
        Ranking de estrategias por win rate. Retorna lista ordenada.
        Formato para gráfico de barras.
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        # Agrupar por estrategia
        strategy_data = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0, 'pnl_sum': 0.0, 'pnl_count': 0})
        
        for s in signals:
            status = s.get('status')
            si = s.get('signal_indicators', [])
            results_data = s.get('signal_results', [])
            pnl = 0
            if isinstance(results_data, list) and results_data:
                pnl = float(results_data[0].get('pnl_pct', 0) or 0)
            
            if not isinstance(si, list):
                continue
            
            for entry in si:
                if not isinstance(entry, dict):
                    continue
                strategy = entry.get('strategy_name')
                if not strategy:
                    continue
                
                d = strategy_data[strategy]
                if status == 'tp_hit':
                    d['wins'] += 1
                elif status == 'sl_hit':
                    d['losses'] += 1
                elif status == 'expired':
                    d['expired'] += 1
                
                if pnl:
                    d['pnl_sum'] += pnl
                    d['pnl_count'] += 1
        
        # Calcular métricas
        results = []
        for strategy, d in strategy_data.items():
            resolved = d['wins'] + d['losses']
            if resolved == 0:
                continue
            
            win_rate = (d['wins'] / resolved) * 100
            avg_pnl = (d['pnl_sum'] / d['pnl_count']) if d['pnl_count'] > 0 else 0
            
            results.append({
                'strategy': strategy,
                'total': resolved + d['expired'],
                'wins': d['wins'],
                'losses': d['losses'],
                'expired': d['expired'],
                'win_rate': round(win_rate, 2),
                'avg_pnl_pct': round(avg_pnl, 3)
            })
        
        # Ordenar por win_rate DESC, con criterio de desempate (más muestras)
        results.sort(key=lambda x: (-x['win_rate'], -x['total']))
        
        return results[:top_n]
    
    # ========================================================================
    # 3. HEATMAP símbolo × timeframe
    # ========================================================================
    
    def get_heatmap_data(self, system_type: str = None, action: str = None,
                          days_back: int = 90) -> Dict:
        """
        Retorna matriz de win_rates por (symbol, timeframe).
        Formato para gráfico de heatmap.
        """
        signals = self._fetch_signals_with_results(
            symbol=None, timeframe=None, system_type=system_type,
            action=action, days_back=days_back
        )
        
        matrix = defaultdict(lambda: defaultdict(lambda: {'wins': 0, 'losses': 0}))
        
        for s in signals:
            symbol = s.get('symbol')
            tf = s.get('timeframe')
            status = s.get('status')
            if not symbol or not tf:
                continue
            
            if status == 'tp_hit':
                matrix[symbol][tf]['wins'] += 1
            elif status == 'sl_hit':
                matrix[symbol][tf]['losses'] += 1
        
        # Recolectar todas las TF y símbolos únicos
        symbols_set = set()
        tfs_set = set()
        for symbol, tf_data in matrix.items():
            symbols_set.add(symbol)
            for tf in tf_data.keys():
                tfs_set.add(tf)
        
        # Ordenar TF por duración
        tf_order = ['5m', '15m', '30m', '1h', '2h', '4h', '12h', '1D', '1W']
        symbols_list = sorted(symbols_set)
        tfs_list = [tf for tf in tf_order if tf in tfs_set]
        
        # Construir matriz z (rows = symbols, cols = timeframes)
        z_win_rate = []
        z_sample_size = []
        for symbol in symbols_list:
            row_wr = []
            row_ss = []
            for tf in tfs_list:
                cell = matrix[symbol].get(tf, {'wins': 0, 'losses': 0})
                resolved = cell['wins'] + cell['losses']
                if resolved > 0:
                    row_wr.append(round((cell['wins'] / resolved) * 100, 1))
                else:
                    row_wr.append(None)
                row_ss.append(resolved)
            z_win_rate.append(row_wr)
            z_sample_size.append(row_ss)
        
        return {
            'symbols': symbols_list,
            'timeframes': tfs_list,
            'win_rates': z_win_rate,
            'sample_sizes': z_sample_size
        }
    
    # ========================================================================
    # 4. EVOLUCIÓN TEMPORAL (serie de tiempo)
    # ========================================================================
    
    def get_timeline(self, symbol: str = None, timeframe: str = None,
                     system_type: str = None, action: str = None,
                     days_back: int = 90, bucket: str = 'week') -> Dict:
        """
        Retorna evolución del win_rate agrupado por semana (o día).
        Formato para gráfico de líneas.
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        # Agrupar por bucket
        buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
        
        for s in signals:
            status = s.get('status')
            ts_str = s.get('created_at')
            if not ts_str or status not in ('tp_hit', 'sl_hit'):
                continue
            
            try:
                # Parsear timestamp
                if 'Z' in ts_str:
                    ts_str = ts_str.replace('Z', '+00:00')
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=None)
                
                if bucket == 'week':
                    # Inicio de semana (lunes)
                    week_start = ts - timedelta(days=ts.weekday())
                    key = week_start.strftime('%Y-%m-%d')
                else:
                    key = ts.strftime('%Y-%m-%d')
                
                if status == 'tp_hit':
                    buckets[key]['wins'] += 1
                elif status == 'sl_hit':
                    buckets[key]['losses'] += 1
                buckets[key]['total'] += 1
            except Exception:
                continue
        
        # Ordenar por fecha
        sorted_keys = sorted(buckets.keys())
        
        return {
            'dates': sorted_keys,
            'win_rates': [
                round((buckets[k]['wins'] / (buckets[k]['wins'] + buckets[k]['losses'])) * 100, 2)
                if (buckets[k]['wins'] + buckets[k]['losses']) > 0 else 0
                for k in sorted_keys
            ],
            'sample_sizes': [buckets[k]['total'] for k in sorted_keys],
            'wins': [buckets[k]['wins'] for k in sorted_keys],
            'losses': [buckets[k]['losses'] for k in sorted_keys]
        }
    
    # ========================================================================
    # 5. DISTRIBUCIÓN DE PnL
    # ========================================================================
    
    def get_pnl_distribution(self, symbol: str = None, timeframe: str = None,
                              system_type: str = None, action: str = None,
                              days_back: int = 90) -> Dict:
        """
        Distribución de PnL: cuántas señales cayeron en cada rango.
        Formato para histograma.
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        pnl_values = []
        for s in signals:
            results_data = s.get('signal_results', [])
            if isinstance(results_data, list) and results_data:
                pnl = results_data[0].get('pnl_pct', 0)
                if pnl:
                    pnl_values.append(float(pnl))
        
        # Bins predefinidos
        bins = [
            (-float('inf'), -5, '<-5%'),
            (-5, -3, '-5 a -3%'),
            (-3, -2, '-3 a -2%'),
            (-2, -1, '-2 a -1%'),
            (-1, 0, '-1 a 0%'),
            (0, 1, '0 a 1%'),
            (1, 2, '1 a 2%'),
            (2, 3, '2 a 3%'),
            (3, 5, '3 a 5%'),
            (5, float('inf'), '>5%')
        ]
        
        counts = []
        labels = []
        colors = []
        for lo, hi, label in bins:
            count = sum(1 for v in pnl_values if lo <= v < hi)
            counts.append(count)
            labels.append(label)
            # Verde para ganancias, rojo para pérdidas
            if lo >= 0:
                colors.append('#00C076')
            else:
                colors.append('#FF5B5B')
        
        return {
            'labels': labels,
            'counts': counts,
            'colors': colors,
            'total': len(pnl_values),
            'mean': round(sum(pnl_values) / len(pnl_values), 3) if pnl_values else 0,
            'positive': sum(1 for v in pnl_values if v > 0),
            'negative': sum(1 for v in pnl_values if v < 0)
        }
    
    # ========================================================================
    # 6. TOP MEJORES Y PEORES OPERACIONES
    # ========================================================================
    
    def get_top_operations(self, top_n: int = 10, mode: str = 'best',
                            symbol: str = None, timeframe: str = None,
                            system_type: str = None, action: str = None,
                            days_back: int = 90) -> List[Dict]:
        """
        Top N mejores o peores operaciones por PnL.
        mode: 'best' | 'worst'
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        # Filtrar solo OPERACIONES REALES resueltas (tp_hit / sl_hit)
        # Antes se incluían missed_opportunity (NO_OPERAR con PnL positivo por
        # movimientos no aprovechados), que aparecían como "TOP mejores" siendo
        # oportunidades no tomadas, no ganancias reales. Ahora solo cuentan
        # operaciones que el sistema recomendó ejecutar y que tocaron TP o SL.
        signals_with_pnl = []
        for s in signals:
            # Excluir missed_opportunity y NO_OPERAR — no son operaciones reales
            status = s.get('status', '')
            if status not in ('tp_hit', 'sl_hit'):
                continue
            action_norm = s.get('action_normalized', '')
            if action_norm not in ('LONG', 'SHORT'):
                continue
            
            results_data = s.get('signal_results', [])
            if isinstance(results_data, list) and results_data:
                pnl = results_data[0].get('pnl_pct')
                if pnl is not None:
                    s['_pnl'] = float(pnl)
                    s['_exit_price'] = results_data[0].get('exit_price')
                    s['_exit_ts'] = results_data[0].get('exit_timestamp')
                    signals_with_pnl.append(s)
        
        # Ordenar
        signals_with_pnl.sort(key=lambda s: s['_pnl'], reverse=(mode == 'best'))
        
        top = signals_with_pnl[:top_n]
        
        result = []
        for s in top:
            # Extraer estrategias
            si = s.get('signal_indicators', [])
            strategies = []
            if isinstance(si, list):
                strategies = [e.get('strategy_name') for e in si if isinstance(e, dict) and e.get('strategy_name')]
            
            result.append({
                'id': s.get('id'),
                'symbol': s.get('symbol'),
                'timeframe': s.get('timeframe'),
                'action': s.get('action_normalized'),
                'confidence': _cap_confidence(s.get('confidence')),
                'entry_price': s.get('entry_price'),
                'stop_loss': s.get('stop_loss'),
                'take_profit': s.get('take_profit'),
                'exit_price': s.get('_exit_price'),
                'pnl_pct': s.get('_pnl'),
                'status': s.get('status'),
                'created_at': s.get('created_at'),
                'exit_at': s.get('_exit_ts'),
                'strategies': strategies,
                'system_type': s.get('system_type')
            })
        
        return result
    
    # ========================================================================
    # 7. DETALLE DE UNA OPERACIÓN
    # ========================================================================
    
    def get_operation_detail(self, signal_id: str) -> Optional[Dict]:
        """Retorna el detalle completo de una señal (para modal de gráfico)"""
        if not self.db.enabled:
            return None
        
        try:
            response = (self.db.client.table('signals')
                        .select('*, signal_indicators(strategy_name, indicator_values), signal_results(*)')
                        .eq('id', signal_id)
                        .limit(1)
                        .execute())
            if not response.data:
                return None
            
            signal = response.data[0]
            si = signal.get('signal_indicators', [])
            strategies = []
            if isinstance(si, list):
                strategies = [e.get('strategy_name') for e in si if isinstance(e, dict)]
            
            results_data = signal.get('signal_results', [])
            result = results_data[0] if isinstance(results_data, list) and results_data else None
            
            return {
                'id': signal.get('id'),
                'symbol': signal.get('symbol'),
                'timeframe': signal.get('timeframe'),
                'system_type': signal.get('system_type'),
                'action': signal.get('action_normalized'),
                'confidence': _cap_confidence(signal.get('confidence')),
                'entry_price': signal.get('entry_price'),
                'stop_loss': signal.get('stop_loss'),
                'take_profit': signal.get('take_profit'),
                'leverage': signal.get('leverage'),
                'risk_reward': signal.get('risk_reward'),
                'current_price_at_signal': signal.get('current_price'),
                'candle_timestamp': signal.get('candle_timestamp'),
                'created_at': signal.get('created_at'),
                'closed_at': signal.get('closed_at'),
                'status': signal.get('status'),
                'strategies': strategies,
                'indicators_snapshot': signal.get('indicators_snapshot', {}),
                'context': signal.get('context', {}),
                'result': result
            }
        except Exception as e:
            logger.error(f"Error obteniendo detalle: {e}")
            return None


# Instancia global
analytics_service = AnalyticsService()
