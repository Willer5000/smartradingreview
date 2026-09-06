"""
pdf_learning_report.py
=======================
Genera un PDF que explica QUÉ está aprendiendo el ReviewTrader.

Estructura del informe:
  1. Métricas coherentes por mercado y cohorte
  2. QUÉ HA APRENDIDO EL SISTEMA (resumen humano automático)
  3. Métricas separadas Spot/Futuros
  4. Futures Shadow: Safety, resultados y contexto cuantitativo
  5. Futures: anatomía diagnóstica de Execution Safety (Commit 36G)
  6. Mejores/peores estrategias operables y combinaciones por mercado
  7. ESTRATEGIAS POR TRADER (cobertura del comité) — v22
  8. Aprendizaje por PAR (win rate por símbolo)
  9. Aprendizaje por TIMEFRAME
  10. Oportunidades perdidas: indicadores que estaban activos
  11. Notas técnicas

CAMBIO IMPORTANTE: en lugar de leer solo las tablas strategy_stats_* (que
requieren ejecutar run_full_review y a veces fallan por timeout), este PDF
CALCULA las estadísticas EN EL MOMENTO desde `signals` + `signal_results`.
Así el aprendizaje siempre se ve, aunque las tablas cache estén vacías.

Requiere: reportlab, supabase-py.
"""

import io
import json
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger('LEARNING_REPORT')

# ============================================================================
# Umbrales de confianza estadística (informativos, no bloquean visualización)
# ============================================================================
SPECIFIC_SAMPLES_RIGOROUS = 10   # con >=10 muestras el resultado es "válido"
SPECIFIC_SAMPLES_MIN = 3         # con <3 no lo mostramos (ruido puro)
GENERAL_SAMPLES_RIGOROUS = 25    # con >=25 muestras el resultado es "válido"
GENERAL_SAMPLES_MIN = 5
REPORT_DAYS_BACK = 90

LEARNING_CONTRACT_VERSION = 'market_separated_v1'
FUTURES_REAL_DATA_SOURCE = 'KUCOIN_FUTURES_PERPETUAL_REST'
FUTURES_REAL_COHORT = 'FUTURES_PERPETUAL_REAL_CLOSED_V1'

# ============================================================================
# v26: BANDAS DE DIAGNÓSTICO SHADOW FUTURES
# ============================================================================
# Referencias exclusivas del informe: NO cambian el motor operativo.
SHADOW_EXECUTION_FLOOR = 65.0
SHADOW_PUBLICATION_SAFETY = 75.0
SHADOW_TP_QUALITY_REFERENCE = 55.0
SHADOW_SL_QUALITY_REFERENCE = 60.0
SHADOW_RR_MIN_REFERENCE = 1.8
SHADOW_RR_MAX_REFERENCE = 3.5

# Commit 36 — validación temporal CAUTIOUS_SHADOW.
# Son umbrales de INFORME/validación; no cambian el motor operativo.
CAUTIOUS_SHADOW_MODEL_VERSION = 'cautious_shadow_v1'
CAUTIOUS_WALK_FORWARD_VERSION = 'temporal_holdout_v1'
CAUTIOUS_WALK_FORWARD_CALIBRATION_RATIO = 0.70
CAUTIOUS_PROMOTION_MIN_TOTAL_RESOLVED = 25
CAUTIOUS_PROMOTION_MIN_VALIDATION_RESOLVED = 10


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'si', 'sí')
    return bool(value)


def _normalize_market(signal: Dict) -> str:
    value = str(signal.get('system_type') or '').strip().lower()
    if value == 'spot':
        return 'spot'
    if value == 'futures':
        return 'futures'
    return 'unscoped'


def _get_learning_context(signal: Dict) -> Dict:
    context = signal.get('context') or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            return {}
    if not isinstance(context, dict):
        return {}
    learning = context.get('learning') or {}
    return learning if isinstance(learning, dict) else {}


def _is_clean_futures_observation(signal: Dict) -> bool:
    if _normalize_market(signal) != 'futures':
        return False
    learning = _get_learning_context(signal)
    return bool(
        learning.get('contract_version') == LEARNING_CONTRACT_VERSION
        and learning.get('cohort') == FUTURES_REAL_COHORT
        and str(learning.get('market_data_source') or '').upper()
        == FUTURES_REAL_DATA_SOURCE
        and not _as_bool(learning.get('market_data_is_synthetic', True))
        and _as_bool(learning.get('source_candle_closed', False))
    )


def _is_verified_futures_trade(signal: Dict) -> bool:
    if not _is_clean_futures_observation(signal):
        return False
    learning = _get_learning_context(signal)
    return bool(
        _as_bool(learning.get('statistically_eligible', False))
        and learning.get('evaluation_role') == 'EXECUTABLE_SIGNAL'
    )


def _latest_signal_result(signal: Dict) -> Dict:
    results = signal.get('signal_results') or []
    if isinstance(results, dict):
        return results
    if not isinstance(results, list) or not results:
        return {}
    return max(
        (item for item in results if isinstance(item, dict)),
        key=lambda item: str(item.get('created_at') or ''),
        default={}
    )


def _outcome_values(signal: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Retorna (PnL bruto %, resultado R) usando los niveles de ESA señal."""
    status = str(signal.get('status') or '')
    if status not in ('tp_hit', 'sl_hit'):
        return None, None

    try:
        entry = float(signal.get('entry_price') or 0)
        sl = float(signal.get('stop_loss') or 0)
        tp = float(signal.get('take_profit') or 0)
    except (TypeError, ValueError):
        return None, None
    if entry <= 0 or sl <= 0 or tp <= 0:
        return None, None

    result = _latest_signal_result(signal)
    raw_pnl = result.get('pnl_pct')
    try:
        pnl_pct = float(raw_pnl) if raw_pnl is not None else None
    except (TypeError, ValueError):
        pnl_pct = None

    action = str(signal.get('action_normalized') or '').upper()
    if pnl_pct is None:
        exit_price = tp if status == 'tp_hit' else sl
        if action == 'LONG':
            pnl_pct = (exit_price - entry) / entry * 100
        elif action == 'SHORT':
            pnl_pct = (entry - exit_price) / entry * 100
        else:
            return None, None

    risk_pct = abs(entry - sl) / entry * 100
    r_multiple = pnl_pct / risk_pct if risk_pct > 0 else None
    return pnl_pct, r_multiple


def _signal_notes(signal: Dict) -> str:
    return str(_latest_signal_result(signal).get('notes') or '')


def _market_metrics(signals: List[Dict]) -> Dict:
    counts = defaultdict(int)
    pnl_values = []
    r_values = []
    for signal in signals:
        status = str(signal.get('status') or 'unknown')
        counts[status] += 1
        if status == 'expired':
            notes = _signal_notes(signal)
            if 'outcome_reason=expired_no_entry' in notes:
                counts['expired_no_entry'] += 1
            elif 'outcome_reason=expired_after_entry' in notes:
                counts['expired_after_entry'] += 1
        pnl_pct, r_multiple = _outcome_values(signal)
        if pnl_pct is not None:
            pnl_values.append(pnl_pct)
        if r_multiple is not None:
            r_values.append(r_multiple)

    resolved = counts['tp_hit'] + counts['sl_hit']
    return {
        'total': len(signals),
        'pending': counts['pending'],
        'tp_hit': counts['tp_hit'],
        'sl_hit': counts['sl_hit'],
        'resolved': resolved,
        'expired': counts['expired'],
        'expired_no_entry': counts['expired_no_entry'],
        'expired_after_entry': counts['expired_after_entry'],
        'ambiguous': counts['ambiguous'],
        'invalid_setup': counts['invalid_setup'],
        'win_rate': round(counts['tp_hit'] / resolved * 100, 1)
        if resolved else None,
        'avg_pnl_pct': round(sum(pnl_values) / len(pnl_values), 4)
        if pnl_values else None,
        'expectancy_r': round(sum(r_values) / len(r_values), 4)
        if r_values else None,
        'outcome_samples': len(pnl_values)
    }


def _split_learning_cohorts(signals: List[Dict]) -> Dict[str, List[Dict]]:
    cohorts = {
        'spot': [],
        'futures_verified': [],
        'futures_shadow': [],
        'futures_legacy': [],
        'unscoped': []
    }
    for signal in signals:
        market = _normalize_market(signal)
        if market == 'spot':
            cohorts['spot'].append(signal)
        elif market == 'futures':
            if _is_verified_futures_trade(signal):
                cohorts['futures_verified'].append(signal)
            elif _is_clean_futures_observation(signal):
                cohorts['futures_shadow'].append(signal)
            else:
                cohorts['futures_legacy'].append(signal)
        else:
            cohorts['unscoped'].append(signal)
    return cohorts


# ============================================================================
# v26: ANALÍTICA SHADOW FUTURES
# ============================================================================
# SHADOW nunca entra en métricas operativas ni modifica decisiones.
# Sólo permite estudiar si algún filtro podría ser demasiado estricto.
# ============================================================================

def _get_signal_context(signal: Dict) -> Dict:
    """Devuelve context como dict, tolerando JSON serializado."""
    context = signal.get('context') or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            return {}
    return context if isinstance(context, dict) else {}


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_execution_context(signal: Dict) -> Dict:
    context = _get_signal_context(signal)
    execution = context.get('execution') or {}
    return execution if isinstance(execution, dict) else {}


def _get_execution_safety_breakdown(signal: Dict) -> Dict:
    """Snapshot diagnóstico persistido por Commit 36F."""
    execution = _get_execution_context(signal)
    breakdown = execution.get('safety_breakdown') or {}
    return breakdown if isinstance(breakdown, dict) else {}


def _get_futures_publication_context(signal: Dict) -> Dict:
    """Snapshot exacto del publication gate persistido por Commit 32."""
    context = _get_signal_context(signal)
    publication = context.get('futures_publication') or {}
    return publication if isinstance(publication, dict) else {}


FUTURES_PUBLICATION_REASON_LABELS = {
    'SAFETY': 'Execution Safety',
    'TP_QUALITY': 'Calidad TP',
    'SL_QUALITY': 'Protección SL',
    'RR': 'Risk / Reward',
    'ROI_TP': 'ROI mínimo del TP',
    'NET_PROFIT': 'Beneficio neto mínimo',
    'LOSS_AT_SL': 'Pérdida máxima al SL',
    'ATR_STRESS': 'Estrés ATR',
    'OTHER': 'Otro bloqueo',
}

# Commit 36D — rechazos exactos ocurridos ANTES del publication gate Premium.
FUTURES_PRE_GATE_REASON_LABELS = {
    'HARD_SAFETY': 'Safety mínimo duro',
    'LEVERAGE_VIABILITY': 'Leverage no viable',
    'ROI_TP': 'ROI potencial insuficiente',
    'NET_PROFIT': 'Beneficio neto insuficiente',
    'LOSS_AT_SL': 'Pérdida máxima al SL',
    'ATR_STRESS': 'Estrés ATR',
    'PRE_GATE_OTHER': 'Otro rechazo pre-gate',
}


# Commit 36G — anatomía del Execution Safety.
# Orden y etiquetas exclusivamente diagnósticos; no cambian pesos del motor.
EXECUTION_SAFETY_COMPONENT_ORDER = (
    'entry_smc',
    'sl',
    'tp',
    'rr',
    'structure',
    'trend',
    'timeframe',
)

EXECUTION_SAFETY_COMPONENT_LABELS = {
    'entry_smc': 'Entry SMC',
    'sl': 'Stop Loss',
    'tp': 'Take Profit',
    'rr': 'Risk / Reward',
    'structure': 'Estructura',
    'trend': 'Tendencia',
    'timeframe': 'Temporalidad',
}

EXECUTION_SAFETY_BREAKDOWN_VERSION = 'execution_safety_breakdown_v1'


def _get_futures_pre_gate_context(signal: Dict) -> Dict:
    """Snapshot exacto de rechazo anterior al gate Premium (Commit 36C)."""
    learning = _get_learning_context(signal)
    pre_gate = learning.get('pre_gate_rejection') or {}
    return pre_gate if isinstance(pre_gate, dict) else {}


def _normalize_shadow_action(signal: Dict) -> str:
    raw = str(
        signal.get('action_normalized')
        or signal.get('action')
        or ''
    ).strip().upper()
    if raw.endswith('LONG'):
        return 'LONG'
    if raw.endswith('SHORT'):
        return 'SHORT'
    return raw


def _shadow_has_trade_geometry(signal: Dict) -> bool:
    """True sólo si hay LONG/SHORT con Entry, SL y TP numéricos válidos."""
    action = _normalize_shadow_action(signal)
    if action not in ('LONG', 'SHORT'):
        return False

    entry = _safe_float(signal.get('entry_price'), 0.0) or 0.0
    sl = _safe_float(signal.get('stop_loss'), 0.0) or 0.0
    tp = _safe_float(signal.get('take_profit'), 0.0) or 0.0

    if entry <= 0 or sl <= 0 or tp <= 0:
        return False
    if action == 'LONG':
        return sl < entry < tp
    return tp < entry < sl


def _shadow_entry_state(signal: Dict) -> str:
    """Infiere sólo estados de Entry demostrables por status/notas."""
    status = str(signal.get('status') or '').strip().lower()
    notes = _signal_notes(signal).lower()

    if status in (
        'entry_touched',
        'tp_hit',
        'sl_hit',
        'ambiguous',
        'expired_after_entry'
    ):
        return 'entry_touched'
    if status == 'expired_no_entry':
        return 'no_entry'
    if status == 'expired':
        if 'outcome_reason=expired_after_entry' in notes:
            return 'entry_touched'
        if 'outcome_reason=expired_no_entry' in notes:
            return 'no_entry'
    return 'unknown'


def _normalized_sl_quality(execution: Dict) -> Optional[float]:
    """Normaliza sl_reliability histórico 0-1 o 0-100 a escala 0-100."""
    raw = _safe_float(execution.get('sl_reliability'))
    if raw is None:
        return None
    if 0 <= raw <= 1:
        return raw * 100.0
    return raw


def _shadow_safety_bucket(safety: Optional[float]) -> str:
    if safety is None or safety <= 0:
        return 'Sin dato'
    if safety < SHADOW_EXECUTION_FLOOR:
        return '<65'
    if safety < 70:
        return '65-69'
    if safety < SHADOW_PUBLICATION_SAFETY:
        return '70-74'
    return '>=75'


def _shadow_bucket_metrics(signals: List[Dict]) -> Dict:
    counts = defaultdict(int)
    pnl_values = []
    r_values = []

    for signal in signals:
        status = str(signal.get('status') or 'unknown').strip().lower()
        counts[status] += 1
        counts[_shadow_entry_state(signal)] += 1

        pnl_pct, r_multiple = _outcome_values(signal)
        if pnl_pct is not None:
            pnl_values.append(pnl_pct)
        if r_multiple is not None:
            r_values.append(r_multiple)

    resolved = counts['tp_hit'] + counts['sl_hit']
    return {
        'total': len(signals),
        'pending': counts['pending'],
        'tp_hit': counts['tp_hit'],
        'sl_hit': counts['sl_hit'],
        'resolved': resolved,
        'expired': (
            counts['expired']
            + counts['expired_no_entry']
            + counts['expired_after_entry']
        ),
        'ambiguous': counts['ambiguous'],
        'invalid_setup': counts['invalid_setup'],
        'entry_touched': counts['entry_touched'],
        'no_entry': counts['no_entry'],
        'entry_unknown': counts['unknown'],
        'win_rate': round(counts['tp_hit'] / resolved * 100, 1)
        if resolved else None,
        'expectancy_r': round(sum(r_values) / len(r_values), 4)
        if r_values else None,
        'avg_pnl_pct': round(sum(pnl_values) / len(pnl_values), 4)
        if pnl_values else None,
        'outcome_samples': len(r_values),
    }



def _get_cautious_shadow_context(signal: Dict) -> Dict:
    """Snapshot CAUTIOUS_SHADOW persistido por Commit 35."""
    learning = _get_learning_context(signal)
    cautious = learning.get('cautious_shadow') or {}
    return cautious if isinstance(cautious, dict) else {}


def _is_cautious_shadow_candidate(signal: Dict) -> bool:
    cautious = _get_cautious_shadow_context(signal)
    return bool(
        cautious.get('model_version') == CAUTIOUS_SHADOW_MODEL_VERSION
        and str(cautious.get('mode') or '').upper() == 'SHADOW_ONLY'
        and _as_bool(cautious.get('candidate', False))
        and str(cautious.get('status') or '').upper() == 'CAUTIOUS_SHADOW'
        and not _as_bool(cautious.get('affects_publication', True))
        and not _as_bool(cautious.get('affects_weights', True))
    )


def _signal_created_at_key(signal: Dict) -> str:
    """
    Clave temporal para validación fuera de muestra.

    Sólo usa timestamps persistidos; no inventa una fecha si falta.
    Supabase entrega created_at en ISO-8601, por lo que el orden lexicográfico
    conserva el orden cronológico dentro de esta cohorte.
    """
    raw = str(
        signal.get('created_at')
        or signal.get('candle_timestamp')
        or ''
    ).strip()
    return raw


def _signal_risk_multiplier(signal: Dict, default: float = 1.0) -> float:
    cautious = _get_cautious_shadow_context(signal)
    value = _safe_float(
        cautious.get('simulated_risk_multiplier'),
        default
    )
    if value is None or value <= 0:
        return default
    return min(1.0, float(value))


def _net_outcome_r_if_persisted(signal: Dict) -> Optional[float]:
    """
    Devuelve R NETO sólo si el resultado real ya persiste net_pnl_pct.

    No resta una comisión teórica ni inventa funding/slippage. Mientras el
    lifecycle no persista costes realizados, la promoción Cautious permanece
    bloqueada por falta de atribución neta verificable.
    """
    status = str(signal.get('status') or '').strip().lower()
    if status not in ('tp_hit', 'sl_hit'):
        return None

    result = _latest_signal_result(signal)
    raw_net = result.get('net_pnl_pct')
    if raw_net is None:
        return None

    try:
        net_pnl_pct = float(raw_net)
        entry = float(signal.get('entry_price') or 0)
        sl = float(signal.get('stop_loss') or 0)
    except (TypeError, ValueError):
        return None

    if entry <= 0 or sl <= 0:
        return None

    risk_pct = abs(entry - sl) / entry * 100
    if risk_pct <= 0:
        return None

    return net_pnl_pct / risk_pct


def _walk_forward_metrics(
    signals: List[Dict],
    default_risk_multiplier: float
) -> Dict:
    """
    Métricas de una cohorte para Commit 36.

    - Expectancy R: R geométrico observado Entry→SL/TP.
    - Exp. presupuesto R: contribución equivalente si sólo se arriesgara el
      multiplicador indicado (0.50x para Cautious, 1.00x Premium).
    - DD presupuesto: drawdown máximo de la secuencia resuelta, expresado en R
      del presupuesto normal. No es dinero real ni incorpora funding.
    """
    ordered = sorted(
        list(signals or []),
        key=lambda signal: _signal_created_at_key(signal)
    )

    base = _shadow_bucket_metrics(ordered)
    r_values = []
    budget_r_values = []
    net_r_values = []
    net_budget_r_values = []
    multiplier_values = []

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for signal in ordered:
        _pnl_pct, r_multiple = _outcome_values(signal)
        if r_multiple is None:
            continue

        multiplier = _signal_risk_multiplier(
            signal,
            default=default_risk_multiplier
        )

        r_multiple = float(r_multiple)
        budget_r = r_multiple * multiplier

        r_values.append(r_multiple)
        budget_r_values.append(budget_r)
        multiplier_values.append(multiplier)

        cumulative += budget_r
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

        net_r = _net_outcome_r_if_persisted(signal)
        if net_r is not None:
            net_r_values.append(float(net_r))
            net_budget_r_values.append(float(net_r) * multiplier)

    total = len(ordered)
    entry_touched = int(base.get('entry_touched') or 0)

    return {
        **base,
        'entry_touch_rate': (
            round(entry_touched / total * 100, 1)
            if total else None
        ),
        'risk_multiplier_avg': (
            round(sum(multiplier_values) / len(multiplier_values), 3)
            if multiplier_values else default_risk_multiplier
        ),
        'budget_expectancy_r': (
            round(sum(budget_r_values) / len(budget_r_values), 4)
            if budget_r_values else None
        ),
        'max_drawdown_budget_r': (
            round(max_drawdown, 4)
            if budget_r_values else None
        ),
        'net_expectancy_r': (
            round(sum(net_r_values) / len(net_r_values), 4)
            if net_r_values else None
        ),
        'net_budget_expectancy_r': (
            round(sum(net_budget_r_values) / len(net_budget_r_values), 4)
            if net_budget_r_values else None
        ),
        'net_outcome_samples': len(net_r_values),
    }


def _calc_cautious_walk_forward_analysis(
    premium_signals: List[Dict],
    shadow_signals: List[Dict]
) -> Dict:
    """
    Commit 36 — comparación temporal Premium vs CAUTIOUS_SHADOW.

    No optimiza parámetros usando el bloque de validación. Las reglas Cautious
    quedaron fijadas en Commit 35. Aquí sólo se separa cronológicamente una
    primera zona de calibración (70%) y una zona posterior (30%) para observar
    comportamiento fuera de tiempo.

    La función nunca promueve ni publica señales.
    """
    premium = [
        signal for signal in (premium_signals or [])
        if _is_verified_futures_trade(signal)
        and _shadow_has_trade_geometry(signal)
    ]

    cautious_profiles = []
    cautious_candidates = []
    cautious_status_counts = defaultdict(int)
    pre_gate_reason_counts = defaultdict(int)
    publication_gate_reason_counts = defaultdict(int)
    publication_gate_exact_profiles = 0
    pre_gate_exact_profiles = 0

    for signal in shadow_signals or []:
        cautious = _get_cautious_shadow_context(signal)
        if not cautious:
            continue

        cautious_profiles.append(signal)
        cautious_status_counts[
            str(cautious.get('status') or 'UNKNOWN').upper()
        ] += 1

        pre_gate = _get_futures_pre_gate_context(signal)
        if pre_gate and _as_bool(pre_gate.get('exact', False)):
            pre_gate_exact_profiles += 1
            code = str(
                pre_gate.get('reason_code') or 'PRE_GATE_OTHER'
            ).strip().upper()
            if code not in FUTURES_PRE_GATE_REASON_LABELS:
                code = 'PRE_GATE_OTHER'
            pre_gate_reason_counts[code] += 1

        publication = _get_futures_publication_context(signal)
        if publication:
            publication_gate_exact_profiles += 1
            raw_codes = publication.get('reason_codes') or []
            if not isinstance(raw_codes, (list, tuple)):
                raw_codes = [raw_codes]
            seen_codes = set()
            for raw_code in raw_codes:
                code = str(raw_code or '').strip().upper()
                if not code:
                    continue
                if code not in FUTURES_PUBLICATION_REASON_LABELS:
                    code = 'OTHER'
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                publication_gate_reason_counts[code] += 1

        if _is_cautious_shadow_candidate(signal):
            cautious_candidates.append(signal)

    # Sólo timestamps demostrables entran al corte temporal.
    comparable = [
        ('PREMIUM', signal)
        for signal in premium
        if _signal_created_at_key(signal)
    ] + [
        ('CAUTIOUS_SHADOW', signal)
        for signal in cautious_candidates
        if _signal_created_at_key(signal)
    ]

    comparable.sort(
        key=lambda item: _signal_created_at_key(item[1])
    )

    cutoff = None
    if len(comparable) >= 2:
        cut_index = int(
            len(comparable)
            * CAUTIOUS_WALK_FORWARD_CALIBRATION_RATIO
        )
        cut_index = max(
            1,
            min(len(comparable) - 1, cut_index)
        )
        cutoff = _signal_created_at_key(
            comparable[cut_index][1]
        )

    def split(items):
        if not cutoff:
            return list(items), []
        calibration = [
            signal for signal in items
            if _signal_created_at_key(signal)
            and _signal_created_at_key(signal) < cutoff
        ]
        validation = [
            signal for signal in items
            if _signal_created_at_key(signal)
            and _signal_created_at_key(signal) >= cutoff
        ]
        return calibration, validation

    premium_cal, premium_val = split(premium)
    cautious_cal, cautious_val = split(cautious_candidates)

    premium_all_metrics = _walk_forward_metrics(
        premium,
        default_risk_multiplier=1.0
    )
    cautious_all_metrics = _walk_forward_metrics(
        cautious_candidates,
        default_risk_multiplier=0.50
    )

    premium_cal_metrics = _walk_forward_metrics(
        premium_cal,
        default_risk_multiplier=1.0
    )
    premium_val_metrics = _walk_forward_metrics(
        premium_val,
        default_risk_multiplier=1.0
    )
    cautious_cal_metrics = _walk_forward_metrics(
        cautious_cal,
        default_risk_multiplier=0.50
    )
    cautious_val_metrics = _walk_forward_metrics(
        cautious_val,
        default_risk_multiplier=0.50
    )

    promotion_reasons = []

    cautious_total_resolved = int(
        cautious_all_metrics.get('resolved') or 0
    )
    cautious_validation_resolved = int(
        cautious_val_metrics.get('resolved') or 0
    )

    if not cautious_candidates:
        promotion_reasons.append(
            'Sin candidatos CAUTIOUS_SHADOW todavía.'
        )

    if (
        cautious_total_resolved
        < CAUTIOUS_PROMOTION_MIN_TOTAL_RESOLVED
    ):
        promotion_reasons.append(
            'Muestra total resuelta insuficiente: '
            f'{cautious_total_resolved}/'
            f'{CAUTIOUS_PROMOTION_MIN_TOTAL_RESOLVED}.'
        )

    if (
        cautious_validation_resolved
        < CAUTIOUS_PROMOTION_MIN_VALIDATION_RESOLVED
    ):
        promotion_reasons.append(
            'Validación temporal insuficiente: '
            f'{cautious_validation_resolved}/'
            f'{CAUTIOUS_PROMOTION_MIN_VALIDATION_RESOLVED} resultados.'
        )

    total_expectancy = cautious_all_metrics.get('expectancy_r')
    if (
        total_expectancy is None
        or total_expectancy <= 0
    ):
        promotion_reasons.append(
            'Expectancy R total Cautious todavía no es positiva.'
        )

    validation_expectancy = cautious_val_metrics.get('expectancy_r')
    if (
        validation_expectancy is None
        or validation_expectancy <= 0
    ):
        promotion_reasons.append(
            'Expectancy R fuera de tiempo todavía no es positiva.'
        )

    # Costes: el candidato Cautious ya pasó el guardrail NET_PROFIT en el
    # momento de creación, pero para promotion exigimos resultados NETOS
    # realizados. Si el lifecycle no persiste net_pnl_pct, no inventamos fees,
    # slippage o funding en retrospectiva.
    if (
        int(cautious_val_metrics.get('net_outcome_samples') or 0)
        < cautious_validation_resolved
    ):
        promotion_reasons.append(
            'Falta atribución neta realizada de comisión/slippage/funding '
            'para toda la muestra de validación.'
        )

    promotion_ready = not promotion_reasons

    return {
        'model_version': CAUTIOUS_WALK_FORWARD_VERSION,
        'calibration_ratio': CAUTIOUS_WALK_FORWARD_CALIBRATION_RATIO,
        'cutoff_created_at': cutoff,
        'cautious_profile_available': len(cautious_profiles),
        'shadow_total_available': len(shadow_signals or []),
        'shadow_without_cautious_profile': max(
            0,
            len(shadow_signals or []) - len(cautious_profiles)
        ),
        'cautious_candidates': len(cautious_candidates),
        'cautious_status_counts': dict(cautious_status_counts),
        'pre_gate_exact_profiles': pre_gate_exact_profiles,
        'pre_gate_reason_counts': dict(pre_gate_reason_counts),
        'publication_gate_exact_profiles': publication_gate_exact_profiles,
        'publication_gate_reason_counts': dict(publication_gate_reason_counts),
        'premium_candidates': len(premium),
        'premium_all': premium_all_metrics,
        'cautious_all': cautious_all_metrics,
        'calibration': {
            'premium': premium_cal_metrics,
            'cautious': cautious_cal_metrics,
        },
        'validation': {
            'premium': premium_val_metrics,
            'cautious': cautious_val_metrics,
        },
        'promotion_ready': promotion_ready,
        'promotion_status': (
            'READY_FOR_COMMIT_37_REVIEW'
            if promotion_ready
            else 'NOT_READY'
        ),
        'promotion_reasons': promotion_reasons,
        'cost_policy': (
            'Cautious exige NET_PROFIT guardrail en creación; la promoción '
            'requiere además net_pnl_pct realizado. No se inventan costes.'
        ),
    }

def _calc_shadow_futures_analysis(signals: List[Dict]) -> Dict:
    """
    Resume la cohorte SHADOW sin concederle autoridad operativa.

    Commit 33:
    - usa el publication gate EXACTO cuando existe (Commit 32);
    - mantiene un fallback reconstruido sólo para registros anteriores;
    - mide outcome / expectancy por causa y por combinación de causas;
    - nunca cambia publicación, pesos, Safety, Entry, SL, TP o leverage.
    """
    signals = list(signals or [])
    directional = [
        s for s in signals
        if _normalize_shadow_action(s) in ('LONG', 'SHORT')
    ]
    geometry = [s for s in directional if _shadow_has_trade_geometry(s)]

    summary = _shadow_bucket_metrics(signals)
    summary['directional'] = len(directional)
    summary['valid_geometry'] = len(geometry)

    by_safety_raw = defaultdict(list)
    reference_flags = defaultdict(int)

    # Commit 33: causas exactas del publication gate.
    exact_reason_raw = defaultdict(list)
    exact_combo_raw = defaultdict(list)
    publication_exact_available = 0
    publication_exact_without_reasons = 0
    publication_exact_inconsistent = 0

    quant_regime_raw = defaultdict(list)
    quant_alignment_raw = defaultdict(list)
    quant_verdict_raw = defaultdict(list)
    quant_available = 0

    for signal in geometry:
        execution = _get_execution_context(signal)
        safety = _safe_float(execution.get('execution_safety'))
        tp_quality = _safe_float(execution.get('tp_quality_score'))
        sl_quality = _normalized_sl_quality(execution)
        rr = _safe_float(
            execution.get('risk_reward'),
            _safe_float(signal.get('risk_reward'))
        )

        by_safety_raw[_shadow_safety_bucket(safety)].append(signal)

        # =============================================================
        # COMMIT 33 — CAUSA EXACTA DEL RECHAZO
        # =============================================================
        publication = _get_futures_publication_context(signal)

        if publication:
            publication_exact_available += 1

            eligible = _as_bool(publication.get('eligible', False))
            raw_codes = publication.get('reason_codes') or []
            if not isinstance(raw_codes, (list, tuple)):
                raw_codes = [raw_codes]

            reason_codes = []
            for raw_code in raw_codes:
                code = str(raw_code or '').strip().upper()
                if not code:
                    continue
                if code not in FUTURES_PUBLICATION_REASON_LABELS:
                    code = 'OTHER'
                if code not in reason_codes:
                    reason_codes.append(code)

            # Una señal de la cohorte Shadow no debería aparecer como elegible.
            # No la corregimos: sólo la contamos para auditoría.
            if eligible:
                publication_exact_inconsistent += 1

            if not eligible and reason_codes:
                for code in reason_codes:
                    exact_reason_raw[code].append(signal)

                combo = ' + '.join(sorted(reason_codes))
                exact_combo_raw[combo].append(signal)

            elif not eligible:
                publication_exact_without_reasons += 1

        else:
            # =========================================================
            # FALLBACK HISTÓRICO
            # =========================================================
            # Sólo para señales anteriores al Commit 32.
            # Estas banderas son inferencias, NO causas históricas exactas.
            if (
                safety is not None
                and safety > 0
                and safety < SHADOW_PUBLICATION_SAFETY
            ):
                reference_flags['Safety < 75'] += 1

            if (
                tp_quality is not None
                and tp_quality > 0
                and tp_quality < SHADOW_TP_QUALITY_REFERENCE
            ):
                reference_flags['Calidad TP < 55'] += 1

            if (
                sl_quality is not None
                and sl_quality > 0
                and sl_quality < SHADOW_SL_QUALITY_REFERENCE
            ):
                reference_flags['Protección SL < 60'] += 1

            if rr is not None and rr > 0:
                if rr < SHADOW_RR_MIN_REFERENCE:
                    reference_flags['RR < 1.8'] += 1
                elif rr > SHADOW_RR_MAX_REFERENCE:
                    reference_flags['RR > 3.5'] += 1

        learning = _get_learning_context(signal)
        quant = learning.get('quantitative_shadow') or {}
        if isinstance(quant, dict) and quant:
            quant_available += 1
            regime = str(quant.get('regime') or 'UNAVAILABLE').strip().upper()
            alignment = str(
                quant.get('direction_alignment') or 'NOT_APPLICABLE'
            ).strip().upper()
            verdict = str(
                quant.get('shadow_verdict') or 'UNAVAILABLE'
            ).strip().upper()
            quant_regime_raw[regime].append(signal)
            quant_alignment_raw[alignment].append(signal)
            quant_verdict_raw[verdict].append(signal)

    by_safety = []
    for bucket in ['<65', '65-69', '70-74', '>=75', 'Sin dato']:
        items = by_safety_raw.get(bucket) or []
        if items:
            row = _shadow_bucket_metrics(items)
            row['bucket'] = bucket
            by_safety.append(row)

    def _group_rows(raw_groups, key_name):
        rows = []
        for key, items in raw_groups.items():
            row = _shadow_bucket_metrics(items)
            row[key_name] = key
            rows.append(row)
        return sorted(
            rows,
            key=lambda r: (-r.get('total', 0), str(r.get(key_name, '')))
        )

    exact_reason_rows = _group_rows(exact_reason_raw, 'reason_code')
    for row in exact_reason_rows:
        row['reason_label'] = FUTURES_PUBLICATION_REASON_LABELS.get(
            row.get('reason_code'),
            row.get('reason_code', 'OTHER')
        )

    exact_combo_rows = _group_rows(exact_combo_raw, 'reason_combo')

    coverage_pct = (
        round(publication_exact_available / len(geometry) * 100, 1)
        if geometry else None
    )

    return {
        'summary': summary,
        'by_safety': by_safety,

        # Exacto desde Commit 32.
        'publication_exact_available': publication_exact_available,
        'publication_exact_missing': max(0, len(geometry) - publication_exact_available),
        'publication_exact_coverage_pct': coverage_pct,
        'publication_exact_without_reasons': publication_exact_without_reasons,
        'publication_exact_inconsistent': publication_exact_inconsistent,
        'by_exact_rejection_reason': exact_reason_rows,
        'by_exact_rejection_combo': exact_combo_rows,

        # Sólo registros antiguos sin snapshot exacto.
        'reference_flags': sorted(
            reference_flags.items(),
            key=lambda item: (-item[1], item[0])
        ),

        'quant_available': quant_available,
        'by_quant_regime': _group_rows(quant_regime_raw, 'regime'),
        'by_quant_alignment': _group_rows(quant_alignment_raw, 'alignment'),
        'by_quant_verdict': _group_rows(quant_verdict_raw, 'verdict'),
    }


# ============================================================================
# COMMIT 36G — ANATOMÍA DIAGNÓSTICA DE EXECUTION SAFETY
# ============================================================================

def _calc_execution_safety_breakdown_analysis(signals: List[Dict]) -> Dict:
    """
    Resume los snapshots del Commit 36F sin modificar ninguna política.

    Separa especialmente los rechazos HARD_SAFETY exactos para responder:
    qué componentes están restando más puntos al score y cuánto falta, en
    promedio, para llegar al mínimo operativo vigente de cada observación.

    No recalcula Safety ni atribuye causas a registros históricos sin snapshot.
    """
    signals = list(signals or [])

    instrumented = []
    hard_safety = []

    component_values_all = defaultdict(list)
    component_values_hard = defaultdict(list)
    component_weights_hard = defaultdict(list)
    component_weighted_hard = defaultdict(list)
    component_penalties_hard = defaultdict(list)
    dominant_rank1 = defaultdict(int)
    dominant_top3 = defaultdict(int)

    raw_scores_all = []
    raw_scores_hard = []
    operational_minimum_hard = []
    shortfall_hard = []
    reconstruction_deltas = []
    calibration_active_count = 0
    timeframe_source_counts = defaultdict(int)

    for signal in signals:
        if not _is_clean_futures_observation(signal):
            continue
        if not _shadow_has_trade_geometry(signal):
            continue

        breakdown = _get_execution_safety_breakdown(signal)
        if not breakdown:
            continue

        model_version = str(
            breakdown.get('model_version') or ''
        ).strip()
        if (
            model_version
            and model_version != EXECUTION_SAFETY_BREAKDOWN_VERSION
        ):
            continue

        if not _as_bool(breakdown.get('available', False)):
            continue

        components = breakdown.get('components') or {}
        if not isinstance(components, dict) or not components:
            continue

        instrumented.append(signal)

        raw_score = _safe_float(breakdown.get('raw_score'))
        if raw_score is not None:
            raw_scores_all.append(raw_score)

        for component in EXECUTION_SAFETY_COMPONENT_ORDER:
            value = _safe_float(components.get(component))
            if value is not None:
                component_values_all[component].append(value)

        delta = _safe_float(breakdown.get('score_reconstruction_delta'))
        if delta is not None:
            reconstruction_deltas.append(delta)

        if _as_bool(breakdown.get('calibration_active', False)):
            calibration_active_count += 1

        tf_source = str(
            breakdown.get('timeframe_factor_source') or 'UNAVAILABLE'
        ).strip().upper()
        timeframe_source_counts[tf_source] += 1

        pre_gate = _get_futures_pre_gate_context(signal)
        is_hard_safety = bool(
            pre_gate
            and _as_bool(pre_gate.get('exact', False))
            and str(pre_gate.get('reason_code') or '').strip().upper()
            == 'HARD_SAFETY'
        )
        if not is_hard_safety:
            continue

        hard_safety.append(signal)

        if raw_score is not None:
            raw_scores_hard.append(raw_score)

        operational_min = _safe_float(
            breakdown.get('operational_minimum')
        )
        if operational_min is not None:
            operational_minimum_hard.append(operational_min)

        shortfall = _safe_float(
            breakdown.get('shortfall_to_operational_min')
        )
        if shortfall is not None:
            shortfall_hard.append(shortfall)

        weights = breakdown.get('weights') or {}
        weighted = breakdown.get('weighted_contributions') or {}
        penalties = breakdown.get('penalties_to_perfect') or {}
        if not isinstance(weights, dict):
            weights = {}
        if not isinstance(weighted, dict):
            weighted = {}
        if not isinstance(penalties, dict):
            penalties = {}

        for component in EXECUTION_SAFETY_COMPONENT_ORDER:
            value = _safe_float(components.get(component))
            weight = _safe_float(weights.get(component))
            weighted_value = _safe_float(weighted.get(component))
            penalty = _safe_float(penalties.get(component))

            if value is not None:
                component_values_hard[component].append(value)
            if weight is not None:
                component_weights_hard[component].append(weight)
            if weighted_value is not None:
                component_weighted_hard[component].append(weighted_value)
            if penalty is not None:
                component_penalties_hard[component].append(penalty)

        dominant = breakdown.get('dominant_penalties') or []
        if isinstance(dominant, list):
            seen = set()
            for index, item in enumerate(dominant[:3]):
                if not isinstance(item, dict):
                    continue
                component = str(
                    item.get('component') or ''
                ).strip()
                if component not in EXECUTION_SAFETY_COMPONENT_ORDER:
                    continue
                if component in seen:
                    continue
                seen.add(component)
                dominant_top3[component] += 1
                if index == 0:
                    dominant_rank1[component] += 1

    def _avg(values):
        values = [float(v) for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    component_rows = []
    for component in EXECUTION_SAFETY_COMPONENT_ORDER:
        row = {
            'component': component,
            'label': EXECUTION_SAFETY_COMPONENT_LABELS.get(
                component,
                component
            ),
            'all_n': len(component_values_all.get(component) or []),
            'avg_all_score': _avg(
                component_values_all.get(component) or []
            ),
            'hard_n': len(component_values_hard.get(component) or []),
            'avg_hard_score': _avg(
                component_values_hard.get(component) or []
            ),
            'avg_weight': _avg(
                component_weights_hard.get(component) or []
            ),
            'avg_weighted_contribution': _avg(
                component_weighted_hard.get(component) or []
            ),
            'avg_penalty_to_perfect': _avg(
                component_penalties_hard.get(component) or []
            ),
            'dominant_rank1_count': int(
                dominant_rank1.get(component, 0)
            ),
            'dominant_top3_count': int(
                dominant_top3.get(component, 0)
            ),
        }
        component_rows.append(row)

    ranked_culprits = sorted(
        [
            row for row in component_rows
            if row.get('avg_penalty_to_perfect') is not None
        ],
        key=lambda row: (
            -float(row.get('avg_penalty_to_perfect') or 0.0),
            -int(row.get('dominant_rank1_count') or 0),
            str(row.get('component') or '')
        )
    )

    abs_deltas = [abs(value) for value in reconstruction_deltas]
    reconstruction_warning_count = sum(
        1 for value in abs_deltas
        if value > 0.25
    )

    hard_n = len(hard_safety)
    if hard_n >= 25:
        sample_status = 'REVISABLE_DIAGNOSTICAMENTE'
    elif hard_n >= 10:
        sample_status = 'PRELIMINAR'
    elif hard_n > 0:
        sample_status = 'INSUFICIENTE'
    else:
        sample_status = 'SIN_MUESTRA'

    return {
        'model_version': 'execution_safety_diagnostic_v1',
        'breakdown_available': len(instrumented),
        'hard_safety_breakdown_available': hard_n,
        'sample_status': sample_status,
        'avg_raw_score_all': _avg(raw_scores_all),
        'avg_raw_score_hard': _avg(raw_scores_hard),
        'avg_operational_minimum_hard': _avg(
            operational_minimum_hard
        ),
        'avg_shortfall_hard': _avg(shortfall_hard),
        'max_shortfall_hard': (
            round(max(shortfall_hard), 4)
            if shortfall_hard else None
        ),
        'component_rows': component_rows,
        'ranked_culprits': ranked_culprits[:3],
        'hard_safety_outcomes': _shadow_bucket_metrics(hard_safety),
        'reconstruction_delta_avg_abs': _avg(abs_deltas),
        'reconstruction_delta_max_abs': (
            round(max(abs_deltas), 4)
            if abs_deltas else None
        ),
        'reconstruction_warning_count': reconstruction_warning_count,
        'calibration_active_count': calibration_active_count,
        'timeframe_factor_source_counts': dict(
            sorted(
                timeframe_source_counts.items(),
                key=lambda item: (-item[1], item[0])
            )
        ),
        'diagnostic_only': True,
        'policy_changed': False,
    }


# ============================================================================
# v22: MAPEO ESTRATEGIA → TRADER (para auditar cobertura del comité)
# ============================================================================
# Cada trader emite un conjunto conocido de estrategias. Este mapa permite
# saber a qué trader corresponde cada strategy_name guardada en Supabase, y
# generar la sección "estrategias por trader" del PDF de Aprendizaje.
STRATEGY_TO_TRADER = {
    # TraderTecnico (RSI, MACD, ADX, BB, Squeeze)
    'BAND_WALK_ALCISTA': 'TraderTecnico',
    'BAND_WALK_BAJISTA': 'TraderTecnico',
    'EXPANSION_VOLATILIDAD': 'TraderTecnico',
    'PULLBACK_TENDENCIA': 'TraderTecnico',
    'SOBRECOMPRA': 'TraderTecnico',
    'SOBREVENTA': 'TraderTecnico',
    'SQUEEZE_ALCISTA': 'TraderTecnico',
    'SQUEEZE_BAJISTA': 'TraderTecnico',
    'TENDENCIA_FUERTE': 'TraderTecnico',
    # TraderChartista (patrones gráficos)
    'ACUMULACION_PATRONES': 'TraderChartista',
    'ACUMULACION_PATRONES_BAJISTAS': 'TraderChartista',
    'BANDERA_ALCISTA': 'TraderChartista',
    'DOBLE_SUELO': 'TraderChartista',
    'DOBLE_TECHO': 'TraderChartista',
    'HCH_INVERTIDO': 'TraderChartista',
    # TraderBallenas (volumen anómalo, whale)
    'ACUMULACION_ICEBERG': 'TraderBallenas',
    'DISTRIBUCION_ICEBERG': 'TraderBallenas',
    'MAVERICK': 'TraderBallenas',
    'MAVERICK_BAJISTA': 'TraderBallenas',
    'VOLUMEN_ANOMALO_ALCISTA': 'TraderBallenas',
    'VOLUMEN_ANOMALO_BAJISTA': 'TraderBallenas',
    # TraderMacro (correlaciones BTC/PAXG, régimen macro)
    'BTC_ALCISTA_UNILATERAL': 'TraderMacro',
    'BTC_BAJISTA_UNILATERAL': 'TraderMacro',
    'BTC_MAS_FUERTE': 'TraderMacro',
    'BTC_MAS_FUERTE_RATIO': 'TraderMacro',
    'CORRELACION_NEGATIVA': 'TraderMacro',
    'CORRELACION_POSITIVA': 'TraderMacro',
    'EVITAR_BTC_POR_ROTACION': 'TraderMacro',
    'EVITAR_PAXG_POR_ROTACION': 'TraderMacro',
    'PAXG_MAS_FUERTE': 'TraderMacro',
    'PAXG_MAS_FUERTE_RATIO': 'TraderMacro',
    'RATIO_ALCISTA': 'TraderMacro',
    'RATIO_BAJISTA': 'TraderMacro',
    'ROTACION_REFUGIO': 'TraderMacro',
    'ROTACION_REFUGIO_RATIO': 'TraderMacro',
    'ROTACION_RIESGO': 'TraderMacro',
    'ROTACION_RIESGO_RATIO': 'TraderMacro',
    # TraderPullback
    'PULLBACK_ALCISTA': 'TraderPullback',
    'PULLBACK_BAJISTA': 'TraderPullback',
    # TraderSmartMoney (SMC: OB, FVG, VP, liquidity)
    'CONFLUENCIA_MULTIPLE': 'TraderSmartMoney',
    'FVG_ALCISTA': 'TraderSmartMoney',
    'FVG_BAJISTA': 'TraderSmartMoney',
    'HVN_RESISTENCIA': 'TraderSmartMoney',
    'HVN_SOPORTE': 'TraderSmartMoney',
    'LIQUIDITY_SWEEP_ALCISTA': 'TraderSmartMoney',
    'LIQUIDITY_SWEEP_BAJISTA': 'TraderSmartMoney',
    'LVN_ROTURA': 'TraderSmartMoney',
    'ORDER_BLOCK_ALCISTA': 'TraderSmartMoney',
    'ORDER_BLOCK_BAJISTA': 'TraderSmartMoney',
    'POC_CONFLUENCIA': 'TraderSmartMoney',
    'POC_REBOTE': 'TraderSmartMoney',
    'POC_RESISTENCIA': 'TraderSmartMoney',
    'POC_VWAP_CONFLUENCIA': 'TraderSmartMoney',
    'STOP_HUNT_ALCISTA': 'TraderSmartMoney',
    'STOP_HUNT_BAJISTA': 'TraderSmartMoney',
    'STOP_HUNT_OB': 'TraderSmartMoney',
    'VALUE_AREA_BREAKDOWN': 'TraderSmartMoney',
    'VALUE_AREA_BREAKOUT': 'TraderSmartMoney',
    'VALUE_AREA_CONFIRMACION': 'TraderSmartMoney',
    'VALUE_AREA_CONFIRMACION_BAJISTA': 'TraderSmartMoney',
    'VALUE_AREA_EXTREMO_ALTO': 'TraderSmartMoney',
    'VALUE_AREA_EXTREMO_BAJO': 'TraderSmartMoney',
    'VOLUMEN_ANOMALO': 'TraderSmartMoney',
    # TraderEspectico (cauteloso)
    'CONFIRMACION_RECHAZADA': 'TraderEspectico',
    # TraderMultiframe (multi-timeframe)
    'ACUMULACION_EN_ZONA_BAJISTA': 'TraderMultiframe',
    'ALINEACION_BEARISH_COMPLETA': 'TraderMultiframe',
    'ALINEACION_BULLISH_COMPLETA': 'TraderMultiframe',
    'CONFLICTO_MAYOR_ADVIERTE_CAMBIO': 'TraderMultiframe',
    'DISTRIBUCION_EN_ZONA_ALCISTA': 'TraderMultiframe',
    'PULLBACK_OPORTUNIDAD': 'TraderMultiframe',
    'RUPTURA_CONFIRMADA': 'TraderMultiframe',
    # TraderLiquidation (mapa de liquidaciones futuros)
    'HEAVY_LONG_CONCENTRATION': 'TraderLiquidation',
    'HEAVY_SHORT_CONCENTRATION': 'TraderLiquidation',
    'LIQUIDITY_BALANCE': 'TraderLiquidation',
    'LIQUIDITY_PRESENT': 'TraderLiquidation',
    'LONG_DOMINANCE_SUPPORT': 'TraderLiquidation',
    'LONG_EXTREME_REVERSAL': 'TraderLiquidation',
    'RECENT_LONG_LIQUIDATIONS': 'TraderLiquidation',
    'RECENT_SHORT_LIQUIDATIONS': 'TraderLiquidation',
    'SHORT_DOMINANCE_RESISTANCE': 'TraderLiquidation',
    'SHORT_EXTREME_REVERSAL': 'TraderLiquidation',
    'SPIKE_ACCUMULATION_LONG': 'TraderLiquidation',
    'SPIKE_ACCUMULATION_SHORT': 'TraderLiquidation',
    # ReviewTrader (juez del comité)
    'REVIEW_HISTORICO_GANADOR_LONG': 'ReviewTrader',
    'REVIEW_HISTORICO_GANADOR_SHORT': 'ReviewTrader',
    'REVIEW_PATRON_PERDEDOR': 'ReviewTrader',
    # Ambiguas / compartidas
    'ESPERAR_CONFIRMACION': 'TraderPullback+TraderEspectico',
}
# Lista canónica de traders para orden estable en el PDF
CANONICAL_TRADERS = [
    'TraderTecnico', 'TraderChartista', 'TraderBallenas',
    'TraderMacro', 'TraderPullback', 'TraderSmartMoney',
    'TraderEspectico', 'TraderMultiframe', 'TraderLiquidation',
    'ReviewTrader',
]


def _calc_stats_by_trader(signals: List[Dict]) -> List[Dict]:
    """
    v22: agrupa las señales resueltas por trader (usando STRATEGY_TO_TRADER)
    y calcula: nº estrategias distintas, señales totales, wins, losses, WR.
    
    Retorna lista ordenada por WR desc, con métricas por trader.
    """
    by_trader = defaultdict(lambda: {
        'strategies_seen': set(),
        'wins': 0, 'losses': 0, 'expired': 0,
    })
    
    for sig in signals:
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        status = sig.get('status')
        market = _normalize_market(sig)
        
        traders_de_esta_signal = set()
        for strat in strategies:
            trader = STRATEGY_TO_TRADER.get(strat)
            if not trader:
                continue
            # Estrategia ambigua: contarla para cada trader que la emite
            for t in trader.split('+'):
                traders_de_esta_signal.add(t)
                by_trader[(market, t)]['strategies_seen'].add(strat)
        
        # Cada trader que contribuyó recibe crédito/débito
        for t in traders_de_esta_signal:
            b = by_trader[(market, t)]
            if status == 'tp_hit':
                b['wins'] += 1
            elif status == 'sl_hit':
                b['losses'] += 1
            elif status == 'expired':
                b['expired'] += 1
    
    rows = []
    markets_present = [
        market for market in ('spot', 'futures')
        if any(key[0] == market for key in by_trader)
    ]
    for market in markets_present:
        for t in CANONICAL_TRADERS:
            b = by_trader.get((market, t))
            if not b:
                rows.append({
                    'market': market,
                    'trader': t, 'signals': 0, 'wins': 0, 'losses': 0,
                    'win_rate': 0.0, 'expired': 0,
                    'unique_strategies': 0, 'strategies': [],
                })
                continue
            resolved = b['wins'] + b['losses']
            wr = (b['wins'] / resolved * 100) if resolved > 0 else 0.0
            rows.append({
                'market': market,
                'trader': t,
                'signals': resolved + b['expired'],
                'wins': b['wins'],
                'losses': b['losses'],
                'expired': b['expired'],
                'win_rate': round(wr, 1),
                'unique_strategies': len(b['strategies_seen']),
                'strategies': sorted(b['strategies_seen']),
            })
    # Ordenar: primero por si aportó, luego por WR
    rows.sort(key=lambda x: (
        0 if x['market'] == 'spot' else 1,
        -x['signals'],
        -x['win_rate']
    ))
    return rows

def _compact_signal_for_learning_report(row: Dict) -> Dict:
    """
    Construye la representación mínima que necesita el Informe de Aprendizaje.

    No modifica la señal original ni Supabase.

    Soporta tres formatos:
    1. context completo, por compatibilidad;
    2. subcontextos proyectados de versiones anteriores del fetch;
    3. campos JSON mínimos proyectados por report_fetch_memory_v3.
    """
    if not isinstance(row, dict):
        return {}

    def _decode_json_value(value):
        if not isinstance(value, str):
            return value

        text = value.strip()

        if not text:
            return None

        try:
            return json.loads(text)
        except Exception:
            return value

    # ==============================================================
    # CAMPOS BASE
    # ==============================================================
    # En lugar de copiar toda la fila recibida desde PostgREST,
    # conservamos exclusivamente los campos utilizados por el PDF.
    compact = {
        'id': row.get('id'),
        'symbol': row.get('symbol'),
        'timeframe': row.get('timeframe'),
        'action_normalized': row.get('action_normalized'),
        'status': row.get('status'),
        'confidence': row.get('confidence'),
        'entry_price': row.get('entry_price'),
        'stop_loss': row.get('stop_loss'),
        'take_profit': row.get('take_profit'),
        'leverage': row.get('leverage'),
        'created_at': row.get('created_at'),
        'candle_timestamp': row.get('candle_timestamp'),
        'system_type': row.get('system_type'),
    }

    # ==============================================================
    # CONTEXT
    # ==============================================================
    compact_context = {}

    # --------------------------------------------------------------
    # A. Compatibilidad con context completo
    # --------------------------------------------------------------
    original_context = _decode_json_value(
        row.get('context')
    )

    if isinstance(original_context, dict):
        for key in (
            'learning',
            'execution',
            'futures_publication'
        ):
            value = original_context.get(key)

            if isinstance(value, dict) and value:
                compact_context[key] = dict(value)

    # --------------------------------------------------------------
    # B. Compatibilidad con proyección v2
    # --------------------------------------------------------------
    legacy_projected_contexts = (
        (
            'learning',
            'learning_context'
        ),
        (
            'execution',
            'execution_context'
        ),
        (
            'futures_publication',
            'futures_publication_context'
        ),
    )

    for target_key, source_key in legacy_projected_contexts:
        value = _decode_json_value(
            row.get(source_key)
        )

        if isinstance(value, dict) and value:
            compact_context[target_key] = dict(value)

    # --------------------------------------------------------------
    # C. LEARNING mínimo — v3
    # --------------------------------------------------------------
    learning = dict(
        compact_context.get('learning')
        or {}
    )

    learning_scalar_fields = (
        (
            'contract_version',
            'learning_contract_version'
        ),
        (
            'cohort',
            'learning_cohort'
        ),
        (
            'market_data_source',
            'learning_market_data_source'
        ),
        (
            'market_data_is_synthetic',
            'learning_market_data_is_synthetic'
        ),
        (
            'source_candle_closed',
            'learning_source_candle_closed'
        ),
        (
            'statistically_eligible',
            'learning_statistically_eligible'
        ),
        (
            'evaluation_role',
            'learning_evaluation_role'
        ),
    )

    for target_key, source_key in learning_scalar_fields:
        value = _decode_json_value(
            row.get(source_key)
        )

        if value is not None:
            learning[target_key] = value

    learning_object_fields = (
        (
            'pre_gate_rejection',
            'learning_pre_gate_rejection'
        ),
        (
            'cautious_shadow',
            'learning_cautious_shadow'
        ),
        (
            'quantitative_shadow',
            'learning_quantitative_shadow'
        ),
    )

    for target_key, source_key in learning_object_fields:
        value = _decode_json_value(
            row.get(source_key)
        )

        if isinstance(value, dict) and value:
            learning[target_key] = value

    if learning:
        compact_context['learning'] = learning

    # --------------------------------------------------------------
    # D. EXECUTION mínimo — v3
    # --------------------------------------------------------------
    execution = dict(
        compact_context.get('execution')
        or {}
    )

    execution_scalar_fields = (
        (
            'execution_safety',
            'execution_safety'
        ),
        (
            'tp_quality_score',
            'execution_tp_quality_score'
        ),
        (
            'sl_reliability',
            'execution_sl_reliability'
        ),
        (
            'risk_reward',
            'execution_risk_reward'
        ),
    )

    for target_key, source_key in execution_scalar_fields:
        value = _decode_json_value(
            row.get(source_key)
        )

        if value is not None:
            execution[target_key] = value

    safety_breakdown = _decode_json_value(
        row.get(
            'execution_safety_breakdown'
        )
    )

    if (
        isinstance(
            safety_breakdown,
            dict
        )
        and safety_breakdown
    ):
        execution[
            'safety_breakdown'
        ] = safety_breakdown

    if execution:
        compact_context[
            'execution'
        ] = execution

    # --------------------------------------------------------------
    # E. PUBLICATION mínimo — v3
    # --------------------------------------------------------------
    publication = dict(
        compact_context.get(
            'futures_publication'
        )
        or {}
    )

    publication_eligible = (
        _decode_json_value(
            row.get(
                'publication_eligible'
            )
        )
    )

    if publication_eligible is not None:
        publication[
            'eligible'
        ] = publication_eligible

    publication_reason_codes = (
        _decode_json_value(
            row.get(
                'publication_reason_codes'
            )
        )
    )

    if (
        publication_reason_codes
        is not None
    ):
        publication[
            'reason_codes'
        ] = publication_reason_codes

    if publication:
        compact_context[
            'futures_publication'
        ] = publication

    compact[
        'context'
    ] = compact_context

    # ==============================================================
    # INDICADORES / ESTRATEGIAS
    # ==============================================================
    indicators = (
        row.get(
            'signal_indicators'
        )
        or []
    )

    if isinstance(
        indicators,
        dict
    ):
        indicators = [
            indicators
        ]

    if isinstance(
        indicators,
        list
    ):
        compact[
            'signal_indicators'
        ] = [
            {
                'strategy_name':
                    item.get(
                        'strategy_name'
                    )
            }
            for item in indicators
            if (
                isinstance(
                    item,
                    dict
                )
                and item.get(
                    'strategy_name'
                )
            )
        ]
    else:
        compact[
            'signal_indicators'
        ] = []

    # ==============================================================
    # ÚLTIMO RESULTADO
    # ==============================================================
    results = (
        row.get(
            'signal_results'
        )
        or []
    )

    if isinstance(
        results,
        dict
    ):
        results = [
            results
        ]

    latest = {}

    if (
        isinstance(
            results,
            list
        )
        and results
    ):
        latest = max(
            (
                item
                for item
                in results
                if isinstance(
                    item,
                    dict
                )
            ),
            key=lambda item: str(
                item.get(
                    'created_at'
                )
                or ''
            ),
            default={}
        )

    if latest:
        latest_compact = {
            'status':
                latest.get(
                    'status'
                ),
            'pnl_pct':
                latest.get(
                    'pnl_pct'
                ),
            'notes':
                latest.get(
                    'notes'
                ),
            'created_at':
                latest.get(
                    'created_at'
                ),
        }

        if (
            'net_pnl_pct'
            in latest
        ):
            latest_compact[
                'net_pnl_pct'
            ] = latest.get(
                'net_pnl_pct'
            )

        compact[
            'signal_results'
        ] = [
            latest_compact
        ]

    else:
        compact[
            'signal_results'
        ] = []

    return compact

# ============================================================================
# HELPERS DE CÁLCULO DE STATS (funcionan directamente sobre signals de la BD)
# ============================================================================

def _fetch_all_signals_with_indicators(db, days_back: int = 90):
    """
    Trae una cohorte temporal coherente, incluyendo pendientes y resultados.

    COMMIT 36I
    -----------
    La versión anterior paginaba de 1000 en 1000 y cortaba ante el primer
    error. Si Supabase/PostgREST devolvía una segunda página vacía o fallaba
    transitoriamente, el PDF podía quedar exactamente con los 1000 registros
    más recientes aunque el count histórico demostrara que existían más.

    Esta versión:
    - congela una ventana temporal [cutoff, snapshot_end);
    - obtiene count exacto de esa MISMA ventana;
    - pagina en bloques de 1000 con proyección JSON mínima y reintentos;
    - NO asume que un batch parcial sea necesariamente el último;
    - deduplica por id;
    - si la paginación queda incompleta, conserva el diagnóstico y bloquea
      cualquier promoción en lugar de ejecutar una segunda descarga masiva;
    - devuelve diagnóstico de cobertura para que el PDF nunca presente una
      muestra truncada como si fuera completa.

    No modifica señales ni aprendizaje. Sólo mejora la lectura del informe.
    """
    from datetime import timedelta
    import time

    now = datetime.utcnow()
    cutoff_dt = now - timedelta(days=days_back)
    # Congela el límite superior para que el count y las páginas midan el
    # mismo snapshot lógico aunque entren nuevas señales mientras se genera.
    snapshot_end_dt = now + timedelta(seconds=2)

    cutoff = cutoff_dt.isoformat()
    snapshot_end = snapshot_end_dt.isoformat()

    select_fields = (
        'id, symbol, timeframe, action_normalized, status, '
        'confidence, entry_price, stop_loss, take_profit, leverage, '
        'created_at, candle_timestamp, system_type, '
        'learning_contract_version:context->learning->>contract_version, '
        'learning_cohort:context->learning->>cohort, '
        'learning_market_data_source:context->learning->>market_data_source, '
        'learning_market_data_is_synthetic:context->learning->>market_data_is_synthetic, '
        'learning_source_candle_closed:context->learning->>source_candle_closed, '
        'learning_statistically_eligible:context->learning->>statistically_eligible, '
        'learning_evaluation_role:context->learning->>evaluation_role, '
        'learning_pre_gate_rejection:context->learning->pre_gate_rejection, '
        'learning_cautious_shadow:context->learning->cautious_shadow, '
        'learning_quantitative_shadow:context->learning->quantitative_shadow, '
        'execution_safety:context->execution->>execution_safety, '
        'execution_tp_quality_score:context->execution->>tp_quality_score, '
        'execution_sl_reliability:context->execution->>sl_reliability, '
        'execution_risk_reward:context->execution->>risk_reward, '
        'execution_safety_breakdown:context->execution->safety_breakdown, '
        'publication_eligible:context->futures_publication->>eligible, '
        'publication_reason_codes:context->futures_publication->reason_codes'
    )

    diagnostics = {
        'window_days': int(days_back),
        'cutoff': cutoff,
        'snapshot_end': snapshot_end,
        'expected_rows': None,
        'fetched_rows': 0,
        'coverage_pct': None,
        'complete': False,
        'primary_pages': 0,
        'fallback_used': False,
        'fallback_slices': 0,
        'strategy_rows': 0,
        'strategy_batches': 0,
        'strategy_hydration_complete': True,
        'result_mode': 'LEVEL_RECONSTRUCTED_NO_RESULT_JOIN',
        'errors': [],
        'model_version': 'report_fetch_memory_v4'
    }

    # ------------------------------------------------------------------
    # Count exacto de la misma ventana del informe.
    # ------------------------------------------------------------------
    try:
        r_count = (
            db.client
            .table('signals')
            .select('id', count='exact')
            .gte('created_at', cutoff)
            .lt('created_at', snapshot_end)
            .limit(1)
            .execute()
        )
        diagnostics['expected_rows'] = int(
            getattr(r_count, 'count', 0) or 0
        )
    except Exception as e:
        diagnostics['errors'].append(
            f'count_window_failed: {str(e)[:180]}'
        )
        logger.warning(
            f'No se pudo contar la ventana de {days_back} días: {e}'
        )

    def _append_unique(target, seen_ids, batch):
        added = 0

        for row in batch or []:
            if not isinstance(row, dict):
                continue

            compacted = _compact_signal_for_learning_report(
                row
            )

            if not compacted:
                continue

            row_id = str(
                compacted.get('id') or ''
            ).strip()

            # Signals debería tener id. Si faltara por un problema
            # de select, usamos una clave compuesta para no perder
            # silenciosamente la fila.
            dedupe_key = row_id or '|'.join([
                str(
                    compacted.get('created_at') or ''
                ),
                str(
                    compacted.get('symbol') or ''
                ),
                str(
                    compacted.get('timeframe') or ''
                ),
                str(
                    compacted.get(
                        'action_normalized'
                    ) or ''
                )
            ])

            if dedupe_key in seen_ids:
                continue

            seen_ids.add(
                dedupe_key
            )

            target.append(
                compacted
            )

            added += 1

        return added

    def _execute_page(
        start_iso,
        end_iso,
        offset,
        page_size
    ):
        last_error = None

        for attempt in range(3):
            try:
                response = (
                    db.client
                    .table('signals')
                    .select(select_fields)
                    .gte('created_at', start_iso)
                    .lt('created_at', end_iso)
                    .order('created_at', desc=True)
                    .range(
                        offset,
                        offset + page_size - 1
                    )
                    .execute()
                )

                return (
                    response,
                    None
                )

            except Exception as exc:
                last_error = exc

                if attempt < 2:
                    time.sleep(
                        0.20 * (attempt + 1)
                    )

        return (
            None,
            last_error
        )
    # ------------------------------------------------------------------
    # PASO A: paginación normal de toda la ventana.
    # ------------------------------------------------------------------
    all_data = []
    seen_ids = set()

    # v3:
    # la consulta ya no transporta los contextos completos.
    #
    # Podemos recuperar más señales por request y reducir de forma
    # importante el número total de llamadas HTTP a Supabase.
    page_size = 1000
    offset = 0

    for _ in range(50):  # cap 50k filas
        response, error = _execute_page(
            cutoff,
            snapshot_end,
            offset,
            page_size
        )

        if error is not None:
            diagnostics['errors'].append(
                f'primary_offset_{offset}: {str(error)[:180]}'
            )
            logger.warning(
                f'Paginación principal falló offset={offset}: {error}'
            )
            break

        batch = response.data or []
        diagnostics['primary_pages'] += 1

        if not batch:
            break

        added = _append_unique(
            all_data,
            seen_ids,
            batch
        )

        # Avanzamos por filas REALMENTE devueltas, no por el tamaño pedido.
        # Esto evita asumir que el servidor respetó exactamente page_size.
        offset += len(batch)

        if added == 0:
            diagnostics['errors'].append(
                f'primary_no_progress_offset_{offset}'
            )
            logger.warning(
                'Paginación principal sin progreso; se detiene de forma segura.'
            )
            break

        expected = diagnostics.get('expected_rows')
        if expected is not None and len(all_data) >= expected:
            break

    expected = diagnostics.get('expected_rows')
    primary_incomplete = (
        expected is not None
        and len(all_data) < expected
    )

    # ------------------------------------------------------------------
    # PASO B — política fail-safe v3
    # ------------------------------------------------------------------
    #
    # La versión anterior volvía a descargar la ventana completa de
    # 90 días dividida en slices de 3 días si la primera lectura quedaba
    # incompleta.
    #
    # En Render esto podía duplicar:
    #
    #     all_data
    #     +
    #     fallback_data
    #
    # y además duplicaba gran parte del tiempo de consultas.
    #
    # Desde v3 NO hacemos una segunda descarga masiva dentro del mismo
    # request HTTP.
    #
    # Si la primera lectura queda incompleta:
    # - el PDF puede seguir generándose;
    # - la cobertura queda explícitamente marcada;
    # - Commit 37 queda bloqueado a NOT_READY más adelante.
    #
    # Nunca presentamos una muestra parcial como evidencia suficiente.
    # ------------------------------------------------------------------

    if primary_incomplete:
        diagnostics[
            'fallback_used'
        ] = False

        diagnostics[
            'errors'
        ].append(
            'primary_incomplete_no_heavy_fallback'
        )

        logger.warning(
            '⚠️ Fetch 90d incompleto: '
            f'{len(all_data)}/{expected}. '
            'Se omite el fallback pesado para proteger '
            'memoria/timeout; la promoción quedará bloqueada.'
        )

    # Orden determinista global para tablas y walk-forward.
    all_data.sort(
        key=lambda row: str(row.get('created_at') or ''),
        reverse=True
    )

    diagnostics['fetched_rows'] = len(all_data)

    expected = diagnostics.get('expected_rows')
    if expected is not None:
        diagnostics['complete'] = (
            len(all_data) == expected
        )
        diagnostics['coverage_pct'] = round(
            (len(all_data) / expected * 100.0)
            if expected > 0
            else 100.0,
            2
        )
    else:
        diagnostics['complete'] = not diagnostics['errors']
    # ------------------------------------------------------------------
    # v4: hidratar estrategias FUERA de la consulta principal.
    # ------------------------------------------------------------------
    # Sólo se necesitan para las tablas de estrategia/trader.
    # El gate Futures, Safety, Shadow y walk-forward no dependen de este join.
    signal_by_id = {
        str(row.get('id')): row
        for row in all_data
        if row.get('id')
    }

    strategy_ids = []

    for row in all_data:
        status = str(
            row.get('status') or ''
        ).strip().lower()

        if status not in (
            'tp_hit',
            'sl_hit',
            'expired',
            'missed_opportunity'
        ):
            continue

        market = _normalize_market(row)

        if (
            market != 'spot'
            and not _is_verified_futures_trade(row)
        ):
            continue

        row_id = str(
            row.get('id') or ''
        ).strip()

        if row_id:
            strategy_ids.append(row_id)

    relation_batch_size = 300

    for start in range(
        0,
        len(strategy_ids),
        relation_batch_size
    ):
        id_batch = strategy_ids[
            start:start + relation_batch_size
        ]

        try:
            relation_response = (
                db.client
                .table('signal_indicators')
                .select(
                    'signal_id, strategy_name'
                )
                .in_(
                    'signal_id',
                    id_batch
                )
                .execute()
            )

            diagnostics[
                'strategy_batches'
            ] += 1

            for item in (
                relation_response.data
                or []
            ):
                if not isinstance(
                    item,
                    dict
                ):
                    continue

                signal_id = str(
                    item.get(
                        'signal_id'
                    )
                    or ''
                ).strip()

                strategy_name = (
                    item.get(
                        'strategy_name'
                    )
                )

                target = signal_by_id.get(
                    signal_id
                )

                if (
                    target is None
                    or not strategy_name
                ):
                    continue

                target.setdefault(
                    'signal_indicators',
                    []
                ).append({
                    'strategy_name':
                        strategy_name
                })

                diagnostics[
                    'strategy_rows'
                ] += 1

        except Exception as exc:
            diagnostics[
                'strategy_hydration_complete'
            ] = False

            diagnostics[
                'errors'
            ].append(
                'strategy_hydration_'
                f'{start}: '
                f'{str(exc)[:180]}'
            )

            logger.warning(
                '⚠️ No se pudieron hidratar '
                'estrategias '
                f'[{start}:'
                f'{start + len(id_batch)}]: '
                f'{exc}'
            )

            # Fail-open:
            # el PDF principal y el gate continúan.
            continue
    if not diagnostics['complete']:
        logger.warning(
            '⚠️ Cohorte PDF incompleta: '
            f"{diagnostics['fetched_rows']}/"
            f"{diagnostics.get('expected_rows')} filas."
        )

    return all_data, diagnostics


def _calc_stats_general(signals: List[Dict]) -> List[Dict]:
    """
    Calcula stats por ESTRATEGIA (agregado global).
    Devuelve lista ordenada por expectancy desc.
    Solo cuenta wins/losses (tp_hit/sl_hit) para win_rate estadístico.
    """
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0, 'missed_opps': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0,
        'by_symbol': defaultdict(lambda: {'wins': 0, 'losses': 0}),
        'by_timeframe': defaultdict(lambda: {'wins': 0, 'losses': 0}),
        'by_action': defaultdict(lambda: {'wins': 0, 'losses': 0}),
    })
    
    for sig in signals:
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        status = sig.get('status')
        symbol = sig.get('symbol')
        tf = sig.get('timeframe')
        action = sig.get('action_normalized')
        market = _normalize_market(sig)
        pnl_pct, r_multiple = _outcome_values(sig)
        
        for strat in strategies:
            b = buckets[(market, strat)]
            if status == 'tp_hit':
                b['wins'] += 1
                b['by_symbol'][symbol]['wins'] += 1
                b['by_timeframe'][tf]['wins'] += 1
                if action:
                    b['by_action'][action]['wins'] += 1
            elif status == 'sl_hit':
                b['losses'] += 1
                b['by_symbol'][symbol]['losses'] += 1
                b['by_timeframe'][tf]['losses'] += 1
                if action:
                    b['by_action'][action]['losses'] += 1
            elif status == 'expired':
                b['expired'] += 1
            elif status == 'missed_opportunity':
                b['missed_opps'] += 1
            if pnl_pct is not None and r_multiple is not None:
                b['pnl_total'] += pnl_pct
                b['r_total'] += r_multiple
                b['outcome_samples'] += 1
    
    rows = []
    for (market, strat), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins'] / resolved * 100) if resolved > 0 else 0
        outcome_samples = b['outcome_samples']
        expectancy = (
            b['r_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        avg_pnl_pct = (
            b['pnl_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        
        # Best/worst pairs & timeframes (min 3 muestras)
        def _rank(subs: Dict, top: bool):
            scored = []
            for k, v in subs.items():
                s = v['wins'] + v['losses']
                if s >= 3:
                    scored.append((k, v['wins']/s*100, s))
            return sorted(scored, key=lambda x: -x[1] if top else x[1])[:3]
        
        rows.append({
            'market': market,
            'strategy': strat,
            'total': resolved + b['expired'],
            'wins': b['wins'],
            'losses': b['losses'],
            'expired': b['expired'],
            'missed': b['missed_opps'],
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 3),
            'avg_pnl_pct': round(avg_pnl_pct, 4),
            'sample_size': resolved,
            'best_symbols': _rank(b['by_symbol'], top=True),
            'worst_symbols': _rank(b['by_symbol'], top=False),
            'best_tfs': _rank(b['by_timeframe'], top=True),
            'worst_tfs': _rank(b['by_timeframe'], top=False),
        })
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        -r['expectancy'],
        -r['sample_size']
    ))


def _calc_stats_specific(signals: List[Dict]) -> List[Dict]:
    """
    Calcula stats por (symbol, timeframe, action, strategy).
    Ordenado por expectancy desc.
    """
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0
    })
    
    for sig in signals:
        symbol = sig.get('symbol')
        tf = sig.get('timeframe')
        action = sig.get('action_normalized')
        status = sig.get('status')
        market = _normalize_market(sig)
        pnl_pct, r_multiple = _outcome_values(sig)
        if not (symbol and tf and action):
            continue
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        
        for strat in strategies:
            key = (market, symbol, tf, action, strat)
            if status == 'tp_hit':
                buckets[key]['wins'] += 1
            elif status == 'sl_hit':
                buckets[key]['losses'] += 1
            elif status == 'expired':
                buckets[key]['expired'] += 1
            if pnl_pct is not None and r_multiple is not None:
                buckets[key]['pnl_total'] += pnl_pct
                buckets[key]['r_total'] += r_multiple
                buckets[key]['outcome_samples'] += 1
    
    rows = []
    for (market, sym, tf, action, strat), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0:
            continue
        win_rate = (b['wins'] / resolved) * 100
        outcome_samples = b['outcome_samples']
        expectancy = (
            b['r_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        avg_pnl_pct = (
            b['pnl_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        rows.append({
            'market': market,
            'symbol': sym, 'timeframe': tf, 'action': action, 'strategy': strat,
            'total': resolved + b['expired'], 'wins': b['wins'],
            'losses': b['losses'], 'expired': b['expired'],
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 3),
            'avg_pnl_pct': round(avg_pnl_pct, 4),
            'sample_size': resolved,
        })
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        -r['expectancy'],
        -r['sample_size']
    ))


def _calc_stats_by_symbol(signals: List[Dict]) -> List[Dict]:
    """Win rate agregado por par."""
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0, 'missed': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0
    })
    for sig in signals:
        sym = sig.get('symbol')
        if not sym:
            continue
        st = sig.get('status')
        market = _normalize_market(sig)
        b = buckets[(market, sym)]
        if st == 'tp_hit':
            b['wins'] += 1
        elif st == 'sl_hit':
            b['losses'] += 1
        elif st == 'expired':
            b['expired'] += 1
        elif st == 'missed_opportunity':
            b['missed'] += 1
        pnl_pct, r_multiple = _outcome_values(sig)
        if pnl_pct is not None and r_multiple is not None:
            b['pnl_total'] += pnl_pct
            b['r_total'] += r_multiple
            b['outcome_samples'] += 1
    rows = []
    for (market, sym), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins']/resolved*100) if resolved > 0 else 0
        outcome_samples = b['outcome_samples']
        rows.append({
            'market': market, 'symbol': sym,
            'wins': b['wins'], 'losses': b['losses'],
            'expired': b['expired'], 'missed': b['missed'],
            'sample_size': resolved,
            'win_rate': round(win_rate, 1),
            'expectancy': round(b['r_total']/outcome_samples, 3)
            if outcome_samples else 0.0,
            'avg_pnl_pct': round(b['pnl_total']/outcome_samples, 4)
            if outcome_samples else 0.0,
        })
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        -r['expectancy'],
        -r['sample_size']
    ))


def _calc_stats_by_timeframe(signals: List[Dict]) -> List[Dict]:
    """Win rate agregado por timeframe."""
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0
    })
    for sig in signals:
        tf = sig.get('timeframe')
        if not tf:
            continue
        st = sig.get('status')
        market = _normalize_market(sig)
        b = buckets[(market, tf)]
        if st == 'tp_hit':
            b['wins'] += 1
        elif st == 'sl_hit':
            b['losses'] += 1
        elif st == 'expired':
            b['expired'] += 1
        pnl_pct, r_multiple = _outcome_values(sig)
        if pnl_pct is not None and r_multiple is not None:
            b['pnl_total'] += pnl_pct
            b['r_total'] += r_multiple
            b['outcome_samples'] += 1
    rows = []
    for (market, tf), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins']/resolved*100) if resolved > 0 else 0
        outcome_samples = b['outcome_samples']
        rows.append({
            'market': market, 'timeframe': tf,
            'wins': b['wins'], 'losses': b['losses'],
            'expired': b['expired'], 'sample_size': resolved,
            'win_rate': round(win_rate, 1),
            'expectancy': round(b['r_total']/outcome_samples, 3)
            if outcome_samples else 0.0,
            'avg_pnl_pct': round(b['pnl_total']/outcome_samples, 4)
            if outcome_samples else 0.0,
        })
    # Ordenar por TF de menor a mayor (5m, 15m, 30m, 1h, 2h, 4h, 12h, 1D, 1W)
    tf_order = {'5m': 0, '15m': 1, '30m': 2, '1h': 3, '2h': 4, '4h': 5,
                '12h': 6, '1D': 7, '1W': 8}
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        tf_order.get(r['timeframe'], 99)
    ))


def _fetch_missed_opp_indicators(db, limit: int = 200) -> List[Dict]:
    """
    Trae oportunidades perdidas junto con los indicadores que estaban activos
    cuando el sistema NO tomó la operación. Ayuda a identificar patrones de
    'cuándo el sistema es demasiado conservador'.
    
    v22.8 FIX: los nombres de columnas eran INCORRECTOS. La tabla
    missed_opportunities usa 'max_favorable_pct' y 'strategies_detected'
    (ver schema_supabase.sql:137-151), no 'pct_missed' ni 'active_strategies'.
    Este bug hacía que el fetch fallara silenciosamente (try/except return [])
    y el PDF siempre mostraba 0 oportunidades perdidas, aunque en Supabase
    hubiera cientos (log del ReviewTrader reportaba 1061).
    """
    try:
        r = (db.client.table('missed_opportunities')
             .select('symbol, timeframe, action_that_should_have_been, '
                     'max_favorable_pct, strategies_detected, created_at')
             .order('created_at', desc=True)
             .limit(limit)
             .execute())
        return r.data or []
    except Exception as e:
        logger.warning(f"_fetch_missed_opp_indicators falló: {e}")
        return []


def _analyze_missed_opps(missed: List[Dict]) -> Dict:
    """
    De las oportunidades perdidas, agrupa por indicadores/estrategias activas
    para ver qué combinaciones aparecen con más frecuencia (candidatas a
    'próximas veces con este set, sí tomar la operación').
    
    v22.8: nombres de campos corregidos (strategies_detected, max_favorable_pct).
    """
    indicator_freq = defaultdict(lambda: {'count': 0, 'total_pct': 0.0})
    combination_freq = defaultdict(lambda: {'count': 0, 'total_pct': 0.0})
    by_pair = defaultdict(int)
    by_direction = defaultdict(int)
    
    for opp in missed:
        # v22.8: el schema usa 'strategies_detected', no 'active_strategies'
        strats = opp.get('strategies_detected') or []
        if not isinstance(strats, list):
            continue
        # v22.8: el schema usa 'max_favorable_pct', no 'pct_missed'
        pct = float(opp.get('max_favorable_pct', 0) or 0)
        
        # Frecuencia individual
        for s in strats:
            if not s:
                continue
            indicator_freq[s]['count'] += 1
            indicator_freq[s]['total_pct'] += pct
        
        # Combinaciones (pares de indicadores)
        if len(strats) >= 2:
            sorted_strats = sorted([s for s in strats if s])
            for i in range(len(sorted_strats)):
                for j in range(i+1, len(sorted_strats)):
                    combo = f"{sorted_strats[i]} + {sorted_strats[j]}"
                    combination_freq[combo]['count'] += 1
                    combination_freq[combo]['total_pct'] += pct
        
        pair = f"{opp.get('symbol','?')} {opp.get('timeframe','?')}"
        by_pair[pair] += 1
        by_direction[opp.get('action_that_should_have_been', '?')] += 1
    
    # Ordenar top
    top_indicators = sorted(
        [(k, v['count'], v['total_pct']/max(v['count'], 1)) for k, v in indicator_freq.items()],
        key=lambda x: -x[1]
    )[:15]
    top_combos = sorted(
        [(k, v['count'], v['total_pct']/max(v['count'], 1)) for k, v in combination_freq.items()],
        key=lambda x: -x[1]
    )[:10]
    top_pairs = sorted(by_pair.items(), key=lambda x: -x[1])[:8]
    
    return {
        'total': len(missed),
        'top_indicators': top_indicators,
        'top_combinations': top_combos,
        'top_pairs': top_pairs,
        'by_direction': dict(by_direction),
    }


def _build_human_summary(metrics: Dict, top_general: List[Dict],
                         worst_general: List[Dict],
                         by_symbol: List[Dict],
                         by_timeframe: List[Dict]) -> str:
    """Resumen por mercado, sin presentar win rate aislado como rentabilidad."""
    del worst_general, by_symbol, by_timeframe  # Las tablas contienen el detalle.
    lines = [
        f"Este informe usa una sola ventana coherente de <b>{REPORT_DAYS_BACK} días</b>. "
        "Spot y Futuros se evalúan por separado. Los Futuros sin procedencia "
        "verificable no pueden mejorar ni empeorar las estadísticas operables."
    ]
    metrics_by_market = metrics.get('metrics_by_market') or {}

    for market, label in (
        ('spot', 'SPOT — acumulación'),
        ('futures', 'FUTUROS — perpetuos verificados')
    ):
        values = metrics_by_market.get(market) or {}
        resolved = int(values.get('resolved') or 0)
        if resolved:
            wr = values.get('win_rate')
            expectancy_r = values.get('expectancy_r')
            avg_pnl = values.get('avg_pnl_pct')
            expectancy_text = (
                f'{expectancy_r:+.3f}R'
                if expectancy_r is not None else '—'
            )
            pnl_text = (
                f'{avg_pnl:+.3f}%'
                if avg_pnl is not None else '—'
            )
            lines.append(
                f"<br/><br/><b>{label}</b>: {resolved} salidas demostrables, "
                f"win rate {wr:.1f}%, expectancy observada "
                f"{expectancy_text} y movimiento bruto medio {pnl_text}."
            )
        else:
            lines.append(
                f"<br/><br/><b>{label}</b>: todavía no hay salidas "
                "demostrables suficientes para afirmar que existe rentabilidad."
            )
        lines.append(
            f" Pendientes: {int(values.get('pending') or 0)}; "
            f"expiradas: {int(values.get('expired') or 0)}; "
            f"ambiguas: {int(values.get('ambiguous') or 0)}; "
            f"setups inválidos: {int(values.get('invalid_setup') or 0)}."
        )

    quarantine = metrics.get('quarantine_counts') or {}
    lines.append(
        f"<br/><br/>Cuarentena informativa: "
        f"{int(quarantine.get('futures_legacy') or 0)} Futuros antiguos/no "
        f"verificables, {int(quarantine.get('futures_shadow') or 0)} análisis "
        f"shadow y {int(quarantine.get('unscoped') or 0)} registros sin mercado."
    )

    for market, label in (('spot', 'Spot'), ('futures', 'Futuros')):
        candidates = [
            item for item in top_general
            if item.get('market') == market
            and item.get('sample_size', 0) >= GENERAL_SAMPLES_RIGOROUS
        ]
        if candidates:
            best = max(candidates, key=lambda item: item['expectancy'])
            lines.append(
                f"<br/><br/><b>Mejor evidencia válida en {label}</b>: "
                f"{best['strategy']} con {best['expectancy']:+.3f}R por señal, "
                f"PnL bruto medio {best['avg_pnl_pct']:+.3f}% y "
                f"{best['sample_size']} resultados."
            )
        else:
            lines.append(
                f"<br/><br/>{label} aún no tiene una estrategia con "
                f"{GENERAL_SAMPLES_RIGOROUS} resultados demostrables."
            )

    lines.append(
        "<br/><br/><i>El PnL mostrado todavía es bruto: no descuenta comisión, "
        "slippage ni funding. Por eso este informe no lo llama beneficio neto.</i>"
    )
    return ''.join(lines)


# ============================================================================
# FETCH DE MÉTRICAS GLOBALES (usando .count real)
# ============================================================================

def _fetch_learning_data() -> Dict:
    """Recupera todo el conocimiento actual del ReviewTrader desde Supabase."""
    data = {
        'supabase_connected': False,
        'report_window_days': REPORT_DAYS_BACK,
        'all_time_signals': 0,
        'total_signals': 0,
        'evaluated_signals': 0,
        'pending_signals': 0,
        'tp_hit': 0,
        'sl_hit': 0,
        'expired': 0,
        'missed_opp_from_signals': 0,
        'missed_opportunities': 0,
        'signals_with_indicators': [],
        'fetch_diagnostics': {},
        'metrics_by_market': {},
        'quarantine_counts': {},
        'futures_shadow_analysis': {},
        'futures_walk_forward_analysis': {},
        'futures_safety_breakdown_analysis': {},
        'missed_details': [],
        'last_review_log': None,
        'error': None,
    }
    
    try:
        from review_trader import review_trader
        db = review_trader.db
    except Exception as e:
        data['error'] = f'ReviewTrader no disponible: {e}'
        return data
    
    if not db.enabled:
        data['error'] = 'Supabase no conectado'
        return data
    
    data['supabase_connected'] = True
    
    # El total histórico se muestra sólo como inventario; no se mezcla con la
    # ventana estadística del informe.
    try:
        r_total = (db.client.table('signals').select('id', count='exact').limit(1).execute())
        data['all_time_signals'] = int(getattr(r_total, 'count', 0) or 0)
    except Exception as e:
        logger.warning(f'Error contando signals: {e}')
    
    # Missed opportunities dedicated table
    try:
        r = db.client.table('missed_opportunities').select('id', count='exact').limit(1).execute()
        data['missed_opportunities'] = int(getattr(r, 'count', None) or 0)
    except Exception:
        pass
    
    # Traer una sola ventana y separar las cohortes antes de calcular cualquier
    # win rate. Así el encabezado y las tablas hablan del mismo conjunto.
    try:
        (
            report_signals,
            fetch_diagnostics
        ) = _fetch_all_signals_with_indicators(
            db,
            days_back=REPORT_DAYS_BACK
        )
        data['fetch_diagnostics'] = fetch_diagnostics

        if not fetch_diagnostics.get('complete', False):
            logger.warning(
                'El PDF continuará, pero marcará la cohorte 90d como INCOMPLETA.'
            )

        cohorts = _split_learning_cohorts(report_signals)
        eligible_signals = (
            cohorts['spot']
            + cohorts['futures_verified']
        )
        spot_metrics = _market_metrics(cohorts['spot'])
        futures_metrics = _market_metrics(cohorts['futures_verified'])
        data['signals_with_indicators'] = eligible_signals
        data['metrics_by_market'] = {
            'spot': spot_metrics,
            'futures': futures_metrics
        }
        data['quarantine_counts'] = {
            'futures_legacy': len(cohorts['futures_legacy']),
            'futures_shadow': len(cohorts['futures_shadow']),
            'unscoped': len(cohorts['unscoped'])
        }
        data['futures_shadow_analysis'] = _calc_shadow_futures_analysis(
            cohorts['futures_shadow']
        )
        walk_forward_analysis = (
            _calc_cautious_walk_forward_analysis(
                cohorts['futures_verified'],
                cohorts['futures_shadow']
            )
        )

        # ==========================================================
        # GATE DE INTEGRIDAD DE DATOS
        # ==========================================================
        #
        # Una lectura parcial nunca puede autorizar Commit 37,
        # aunque las métricas calculadas sobre ese subconjunto
        # parezcan positivas.
        #
        # Esto sólo afecta al gate del informe.
        # No modifica reglas operativas ni señales.
        if not fetch_diagnostics.get(
            'complete',
            False
        ):
            promotion_reasons = list(
                walk_forward_analysis.get(
                    'promotion_reasons'
                )
                or []
            )

            integrity_reason = (
                'Lectura Supabase de la cohorte '
                f'{REPORT_DAYS_BACK}d incompleta: '
                'no se permite promoción con una '
                'muestra potencialmente truncada.'
            )

            if (
                integrity_reason
                not in promotion_reasons
            ):
                promotion_reasons.append(
                    integrity_reason
                )

            walk_forward_analysis[
                'promotion_ready'
            ] = False

            walk_forward_analysis[
                'promotion_status'
            ] = 'NOT_READY'

            walk_forward_analysis[
                'promotion_reasons'
            ] = promotion_reasons

        data[
            'futures_walk_forward_analysis'
        ] = walk_forward_analysis
      
        data['futures_safety_breakdown_analysis'] = (
            _calc_execution_safety_breakdown_analysis(
                cohorts['futures_shadow']
            )
        )
        data['total_signals'] = len(eligible_signals)
        data['pending_signals'] = (
            spot_metrics['pending'] + futures_metrics['pending']
        )
        data['tp_hit'] = spot_metrics['tp_hit'] + futures_metrics['tp_hit']
        data['sl_hit'] = spot_metrics['sl_hit'] + futures_metrics['sl_hit']
        data['expired'] = spot_metrics['expired'] + futures_metrics['expired']
        data['evaluated_signals'] = (
            data['tp_hit'] + data['sl_hit'] + data['expired']
        )
        data['missed_opp_from_signals'] = sum(
            1 for signal in eligible_signals
            if signal.get('status') == 'missed_opportunity'
        )
    except Exception as e:
        logger.warning(f'Error trayendo signals con indicadores: {e}')
    
    # Missed opps detalladas para análisis
    try:
        data['missed_details'] = _fetch_missed_opp_indicators(db, limit=500)
    except Exception:
        pass
    
    # Último ciclo review_log
    try:
        r = (db.client.table('review_logs').select('*').order('created_at', desc=True)
             .limit(1).execute())
        if r.data:
            data['last_review_log'] = r.data[0]
    except Exception:
        pass
    
    return data


# ============================================================================
# GENERACIÓN DEL PDF
# ============================================================================

def _confidence_badge(sample_size: int, min_rigorous: int) -> str:
    """Devuelve texto y color según si la muestra es estadísticamente válida."""
    if sample_size >= min_rigorous:
        return '✅ Válida', '#0a8f4c'
    elif sample_size >= 5:
        return '⚠️ Preliminar', '#e8a500'
    else:
        return '❓ Insuficiente', '#c92a2a'


def generate_learning_pdf() -> bytes:
    """Genera el PDF completo de aprendizaje."""
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        KeepTogether
    )
    
    data = _fetch_learning_data()
    signals_with_ind = data.get(
        'signals_with_indicators',
        []
    )

    # ==============================================================
    # CALCULAR TODO LO QUE NECESITA LAS SEÑALES CRUDAS PRIMERO
    # ==============================================================
    # Después podremos liberar esa cohorte antes de construir
    # las tablas ReportLab, reduciendo significativamente el pico
    # de memoria del worker de Render.
    stats_general = (
        _calc_stats_general(
            signals_with_ind
        )
        if signals_with_ind
        else []
    )

    stats_specific = (
        _calc_stats_specific(
            signals_with_ind
        )
        if signals_with_ind
        else []
    )

    stats_by_symbol = (
        _calc_stats_by_symbol(
            signals_with_ind
        )
        if signals_with_ind
        else []
    )

    stats_by_tf = (
        _calc_stats_by_timeframe(
            signals_with_ind
        )
        if signals_with_ind
        else []
    )

    stats_by_trader = (
        _calc_stats_by_trader(
            signals_with_ind
        )
        if signals_with_ind
        else []
    )

    missed_analysis = _analyze_missed_opps(
        data.get(
            'missed_details',
            []
        )
    )

    # ==============================================================
    # LIBERACIÓN TEMPRANA DE MEMORIA
    # ==============================================================
    # Todos los cálculos que necesitaban estas señales ya terminaron.
    # Las métricas Futures Shadow / Walk-Forward / Safety también
    # fueron calculadas dentro de _fetch_learning_data().
    #
    # Vaciar estas listas NO modifica Supabase ni pierde aprendizaje:
    # solamente libera la copia temporal utilizada para generar
    # este PDF.
    if isinstance(
        signals_with_ind,
        list
    ):
        signals_with_ind.clear()

    data[
        'signals_with_indicators'
    ] = []

    data[
        'missed_details'
    ] = []

    # Ayuda a que Python libere objetos temporales antes de que
    # ReportLab empiece a construir todas las páginas.
    import gc
    gc.collect()
    
    # ============ SETUP DEL PDF ============
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=1.2*cm, leftMargin=1.2*cm,
        topMargin=1.2*cm, bottomMargin=1.2*cm,
        title='Aprendizaje del Sistema'
    )
    
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('LT', parent=styles['Title'],
        fontSize=20, textColor=HexColor('#1a1a2e'),
        alignment=TA_CENTER, spaceAfter=8)
    style_sub = ParagraphStyle('LS', parent=styles['Normal'],
        fontSize=11, textColor=HexColor('#555'),
        alignment=TA_CENTER, spaceAfter=14)
    style_h2 = ParagraphStyle('LH2', parent=styles['Heading2'],
        fontSize=14, textColor=HexColor('#0a3d62'),
        spaceBefore=12, spaceAfter=8)
    style_h3 = ParagraphStyle('LH3', parent=styles['Heading3'],
        fontSize=11, textColor=HexColor('#333'),
        spaceBefore=8, spaceAfter=6)
    style_body = ParagraphStyle('LB', parent=styles['Normal'],
        fontSize=10.5, leading=14.5,
        alignment=TA_JUSTIFY, spaceAfter=8,
        textColor=HexColor('#222'))
    style_meta = ParagraphStyle('LM', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#888'),
        alignment=TA_CENTER, spaceAfter=6)
    style_note = ParagraphStyle('LN', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#666'), leftIndent=10)
    
    story = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # ============ 1. CABECERA ============
    story.append(Paragraph("Aprendizaje del Sistema", style_title))
    story.append(Paragraph(
        f"Informe del ReviewTrader · generado {now_str}",
        style_sub
    ))
    
    if not data['supabase_connected']:
        story.append(Paragraph(
            f"<b>Supabase no está conectado.</b> Detalle: {data.get('error', 'desconocido')}",
            style_body
        ))
        doc.build(story)
        result = buf.getvalue()
        buf.close()
        return result
    
    # ============ 2. QUÉ HA APRENDIDO EL SISTEMA (resumen humano) ============
    story.append(Paragraph("¿Qué ha aprendido el sistema hasta ahora?", style_h2))
    human_summary = _build_human_summary(data, stats_general, stats_general,
                                          stats_by_symbol, stats_by_tf)
    story.append(Paragraph(human_summary, style_body))
    
    # ============ 3. MÉTRICAS COHERENTES POR MERCADO ============
    story.append(Paragraph("Métricas por mercado", style_h2))
    spot_metrics = data.get('metrics_by_market', {}).get('spot', {})
    futures_metrics = data.get('metrics_by_market', {}).get('futures', {})
    quarantine = data.get('quarantine_counts', {})

    def _metric_text(value, suffix=''):
        return '—' if value is None else f'{value}{suffix}'

    metrics_data = [
        ['Métrica', 'Valor'],
        ['Inventario histórico total (no usado como cohorte)', str(data['all_time_signals'])],
        [f'Cohorte estadística verificable ({REPORT_DAYS_BACK} días)', str(data['total_signals'])],
        [
            f'Cobertura lectura Supabase ({REPORT_DAYS_BACK} días)',
            (
                f"{int((data.get('fetch_diagnostics') or {}).get('fetched_rows') or 0)} / "
                f"{int((data.get('fetch_diagnostics') or {}).get('expected_rows') or 0)} "
                f"({float((data.get('fetch_diagnostics') or {}).get('coverage_pct') or 0):.1f}%)"
                if (data.get('fetch_diagnostics') or {}).get('expected_rows') is not None
                else 'COUNT NO DISPONIBLE'
            )
        ],
        [
            'Modo de lectura cohorte',
            (
                'FALLBACK TEMPORAL'
                if (data.get('fetch_diagnostics') or {}).get('fallback_used')
                else 'PAGINACIÓN NORMAL'
            )
        ],
        [
            'Estado lectura cohorte',
            (
                'COMPLETA'
                if (data.get('fetch_diagnostics') or {}).get('complete', False)
                else 'INCOMPLETA - NO CALIBRAR'
            )
        ],
        ['SPOT — señales en cohorte', str(spot_metrics.get('total', 0))],
        ['   — TP / SL / Expired', (
            f"{spot_metrics.get('tp_hit', 0)} / "
            f"{spot_metrics.get('sl_hit', 0)} / "
            f"{spot_metrics.get('expired', 0)}"
        )],
        ['   — Win rate / Expectancy observada', (
            f"{_metric_text(spot_metrics.get('win_rate'), '%')} / "
            f"{_metric_text(spot_metrics.get('expectancy_r'), 'R')}"
        )],
        ['FUTUROS — ejecutables y verificables', str(futures_metrics.get('total', 0))],
        ['   — TP / SL / Expired', (
            f"{futures_metrics.get('tp_hit', 0)} / "
            f"{futures_metrics.get('sl_hit', 0)} / "
            f"{futures_metrics.get('expired', 0)}"
        )],
        ['   — Win rate / Expectancy observada', (
            f"{_metric_text(futures_metrics.get('win_rate'), '%')} / "
            f"{_metric_text(futures_metrics.get('expectancy_r'), 'R')}"
        )],
        ['Resultados ambiguos (Spot / Futuros)', (
            f"{spot_metrics.get('ambiguous', 0)} / "
            f"{futures_metrics.get('ambiguous', 0)}"
        )],
        ['Futuros antiguos/no verificables en cuarentena', str(quarantine.get('futures_legacy', 0))],
        ['Análisis Futures shadow (no publicados)', str(quarantine.get('futures_shadow', 0))],
        ['Registros sin mercado en cuarentena', str(quarantine.get('unscoped', 0))],
        ['Oportunidades perdidas (diagnóstico no separado)', str(data['missed_opportunities'])],
    ]
    tmet = Table(metrics_data, colWidths=[11*cm, 5*cm])
    tmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#0a3d62')),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9.2),
        ('GRID', (0,0), (-1,-1), 0.4, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(tmet)

    story.append(PageBreak())
    
    # ============ 4. FUTURES SHADOW — DIAGNÓSTICO DE TIMIDEZ ============
    shadow = data.get('futures_shadow_analysis') or {}
    shadow_summary = shadow.get('summary') or {}

    story.append(Paragraph(
        "FUTURES — aprendizaje Shadow (diagnóstico de timidez)",
        style_h2
    ))
    story.append(Paragraph(
        "Esta sección estudia análisis de Futuros <b>reales, de perpetuos y vela "
        "cerrada</b> que NO superaron la publicación. Son observaciones hipotéticas: "
        "<b>no son operaciones autorizadas</b>, no entran al win rate oficial y no "
        "pueden modificar pesos, Safety, Entry, SL, TP ni leverage. Su función es "
        "descubrir si alguna puerta de publicación podría estar descartando edge.",
        style_body
    ))

    if shadow_summary.get('total'):
        def _shadow_metric_text(value, suffix=''):
            return '—' if value is None else f'{value}{suffix}'

        shadow_metrics_rows = [
            ['Métrica Shadow', 'Valor'],
            ['Observaciones limpias no publicadas',
             str(shadow_summary.get('total', 0))],
            ['Candidatos LONG/SHORT',
             str(shadow_summary.get('directional', 0))],
            ['Con Entry + SL + TP geométricamente válidos',
             str(shadow_summary.get('valid_geometry', 0))],
            ['Con causa EXACTA de publicación (Commit 32)', (
                f"{int(shadow.get('publication_exact_available') or 0)} / "
                f"{int(shadow_summary.get('valid_geometry') or 0)} "
                f"({_shadow_metric_text(shadow.get('publication_exact_coverage_pct'), '%')})"
            )],
            ['Entry demostrado / No Entry / Indeterminado', (
                f"{shadow_summary.get('entry_touched', 0)} / "
                f"{shadow_summary.get('no_entry', 0)} / "
                f"{shadow_summary.get('entry_unknown', 0)}"
            )],
            ['TP / SL / Expired / Ambiguous', (
                f"{shadow_summary.get('tp_hit', 0)} / "
                f"{shadow_summary.get('sl_hit', 0)} / "
                f"{shadow_summary.get('expired', 0)} / "
                f"{shadow_summary.get('ambiguous', 0)}"
            )],
            ['Win rate hipotético / Expectancy R', (
                f"{_shadow_metric_text(shadow_summary.get('win_rate'), '%')} / "
                f"{_shadow_metric_text(shadow_summary.get('expectancy_r'), 'R')}"
            )],
            ['PnL bruto medio de resultados TP/SL',
             _shadow_metric_text(shadow_summary.get('avg_pnl_pct'), '%')],
        ]

        tshadow = Table(shadow_metrics_rows, colWidths=[11*cm, 5*cm])
        tshadow.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#6c4ab6')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9.3),
            ('GRID', (0,0), (-1,-1), 0.35, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f6f2ff'), white]),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(tshadow)

        if shadow.get('by_safety'):
            story.append(Paragraph("Shadow por banda de Execution Safety", style_h3))
            story.append(Paragraph(
                "Las bandas 65-69 y 70-74 son diagnósticas. El motor operativo "
                "permanece sin cambios. Una banda sólo debería promoverse si acumula "
                "muestra suficiente, expectancy positiva neta y valida después en "
                "walk-forward.",
                style_note
            ))
            rows = [['Safety', 'N', 'Entry', 'TP', 'SL', 'WR %', 'Exp. R']]
            for row in shadow.get('by_safety') or []:
                rows.append([
                    row.get('bucket', '—'),
                    str(row.get('total', 0)),
                    str(row.get('entry_touched', 0)),
                    str(row.get('tp_hit', 0)),
                    str(row.get('sl_hit', 0)),
                    '—' if row.get('win_rate') is None else f"{row.get('win_rate'):.1f}",
                    '—' if row.get('expectancy_r') is None else f"{row.get('expectancy_r'):+.3f}",
                ])
            tsafety = Table(
                rows,
                colWidths=[2.2*cm, 1.5*cm, 1.7*cm, 1.4*cm, 1.4*cm, 1.7*cm, 2.0*cm]
            )
            tsafety.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), HexColor('#3f51b5')),
                ('TEXTCOLOR', (0,0), (-1,0), white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 8.5),
                ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f3f5ff'), white]),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ]))
            story.append(tsafety)

        # =============================================================
        # COMMIT 33 — CAUSAS EXACTAS DEL PUBLICATION GATE
        # =============================================================
        exact_available = int(
            shadow.get('publication_exact_available') or 0
        )
        exact_missing = int(
            shadow.get('publication_exact_missing') or 0
        )

        story.append(Paragraph(
            "Causas exactas del publication gate (Commit 32)",
            style_h3
        ))

        if exact_available:
            coverage = shadow.get('publication_exact_coverage_pct')
            coverage_text = '—' if coverage is None else f"{coverage:.1f}%"

            story.append(Paragraph(
                f"{exact_available} candidatos con geometría válida ya conservan la "
                f"decisión exacta del publication gate ({coverage_text} de cobertura "
                f"en esta cohorte). Otros {exact_missing} son anteriores al Commit 32 "
                "o todavía no contienen ese snapshot. <b>Las causas pueden solaparse</b>: "
                "una misma señal puede fallar Safety y TP Quality al mismo tiempo, por "
                "lo que los N por causa no deben sumarse entre sí.",
                style_note
            ))

            reason_rows = shadow.get('by_exact_rejection_reason') or []
            if reason_rows:
                rows = [['Bloqueo exacto', 'N', 'Entry', 'TP', 'SL', 'WR %', 'Exp. R']]
                for row in reason_rows[:10]:
                    rows.append([
                        str(row.get('reason_label') or row.get('reason_code') or 'OTHER')[:31],
                        str(row.get('total', 0)),
                        str(row.get('entry_touched', 0)),
                        str(row.get('tp_hit', 0)),
                        str(row.get('sl_hit', 0)),
                        '—' if row.get('win_rate') is None else f"{row.get('win_rate'):.1f}",
                        '—' if row.get('expectancy_r') is None else f"{row.get('expectancy_r'):+.3f}",
                    ])

                treasons = Table(
                    rows,
                    colWidths=[5.4*cm, 1.2*cm, 1.5*cm, 1.2*cm, 1.2*cm, 1.6*cm, 1.9*cm]
                )
                treasons.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), HexColor('#7b1fa2')),
                    ('TEXTCOLOR', (0,0), (-1,0), white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8.2),
                    ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f8f0fb'), white]),
                    ('ALIGN', (1,0), (-1,-1), 'CENTER'),
                ]))
                story.append(treasons)

            combo_rows = shadow.get('by_exact_rejection_combo') or []
            if combo_rows:
                story.append(Paragraph(
                    "Combinaciones exactas de bloqueos",
                    style_h3
                ))
                story.append(Paragraph(
                    "Esta tabla es especialmente útil para distinguir una puerta aislada "
                    "demasiado severa de candidatos que fallan varias condiciones a la vez.",
                    style_note
                ))
                rows = [['Combinación', 'N', 'Entry', 'TP', 'SL', 'Exp. R']]
                for row in combo_rows[:8]:
                    combo = str(row.get('reason_combo') or 'OTHER')
                    rows.append([
                        combo[:58],
                        str(row.get('total', 0)),
                        str(row.get('entry_touched', 0)),
                        str(row.get('tp_hit', 0)),
                        str(row.get('sl_hit', 0)),
                        '—' if row.get('expectancy_r') is None else f"{row.get('expectancy_r'):+.3f}",
                    ])
                tcombos = Table(
                    rows,
                    colWidths=[7.7*cm, 1.2*cm, 1.5*cm, 1.2*cm, 1.2*cm, 1.9*cm]
                )
                tcombos.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), HexColor('#512da8')),
                    ('TEXTCOLOR', (0,0), (-1,0), white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 7.8),
                    ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f1fb'), white]),
                    ('ALIGN', (1,0), (-1,-1), 'CENTER'),
                ]))
                story.append(tcombos)

            inconsistent = int(
                shadow.get('publication_exact_inconsistent') or 0
            )
            no_reasons = int(
                shadow.get('publication_exact_without_reasons') or 0
            )
            if inconsistent or no_reasons:
                story.append(Paragraph(
                    f"Auditoría de integridad: {inconsistent} Shadow aparecen como "
                    f"eligible y {no_reasons} rechazados no traen reason_codes. Estos "
                    "casos se señalan para depuración; no se reinterpretan ni se corrigen "
                    "automáticamente.",
                    style_note
                ))

        else:
            story.append(Paragraph(
                "La cohorte visible todavía no contiene snapshots exactos del Commit 32. "
                "Esto es esperable inmediatamente después del despliegue: no se hace "
                "backfill inventado de señales históricas. Las nuevas observaciones irán "
                "aumentando esta cobertura de forma natural.",
                style_note
            ))

        # =============================================================
        # FALLBACK HISTÓRICO — SÓLO SIN SNAPSHOT EXACTO
        # =============================================================
        if shadow.get('reference_flags'):
            story.append(Paragraph(
                "Fallback histórico: métricas reconstruidas",
                style_h3
            ))
            story.append(Paragraph(
                "Estas banderas se calculan <b>sólo para candidatos que todavía no "
                "tienen el publication gate exacto</b>. Son una aproximación útil para "
                "el legado reciente, pero no deben mezclarse ni sumarse con las causas "
                "exactas del Commit 32.",
                style_note
            ))
            rows = [['Banda reconstruida', 'Casos sin gate exacto']]
            for label, count in shadow.get('reference_flags') or []:
                rows.append([label, str(count)])
            tflags = Table(rows, colWidths=[10.5*cm, 3.5*cm])
            tflags.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), HexColor('#e8a500')),
                ('TEXTCOLOR', (0,0), (-1,0), white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#fff9e6'), white]),
            ]))
            story.append(tflags)

        if shadow.get('quant_available'):
            story.append(Paragraph("Contexto cuantitativo Shadow", style_h3))
            story.append(Paragraph(
                f"{int(shadow.get('quant_available') or 0)} candidatos ya contienen "
                "el snapshot cuantitativo del Commit 22. Sigue en modo observación: "
                "ninguna fila de esta tabla puede aprobar o rechazar una operación.",
                style_note
            ))
            quant_rows = shadow.get('by_quant_regime') or []
            if quant_rows:
                rows = [['Régimen', 'N', 'TP', 'SL', 'WR %', 'Exp. R']]
                for row in quant_rows[:10]:
                    rows.append([
                        str(row.get('regime') or 'UNAVAILABLE')[:24],
                        str(row.get('total', 0)),
                        str(row.get('tp_hit', 0)),
                        str(row.get('sl_hit', 0)),
                        '—' if row.get('win_rate') is None else f"{row.get('win_rate'):.1f}",
                        '—' if row.get('expectancy_r') is None else f"{row.get('expectancy_r'):+.3f}",
                    ])
                tq = Table(
                    rows,
                    colWidths=[5.2*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.7*cm, 2.0*cm]
                )
                tq.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), HexColor('#00838f')),
                    ('TEXTCOLOR', (0,0), (-1,0), white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8.5),
                    ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#edfafa'), white]),
                    ('ALIGN', (1,0), (-1,-1), 'CENTER'),
                ]))
                story.append(tq)
    else:
        story.append(Paragraph(
            "<i>Todavía no hay observaciones Shadow Futures limpias dentro de la "
            "ventana del informe. Esto no es un error del PDF: significa que la "
            "cohorte nueva aún no tiene registros disponibles.</i>",
            style_body
        ))

    # =============================================================
    # COMMIT 36 — PREMIUM VS CAUTIOUS_SHADOW / VALIDACIÓN TEMPORAL
    # =============================================================
    walk = data.get('futures_walk_forward_analysis') or {}

    story.append(PageBreak())
    story.append(Paragraph(
        "FUTURES — validación temporal Premium vs CAUTIOUS_SHADOW",
        style_h2
    ))
    story.append(Paragraph(
        "Commit 36 <b>no modifica ninguna decisión</b>. Las reglas de "
        "CAUTIOUS_SHADOW quedaron fijadas antes de observar esta validación. "
        "El informe separa cronológicamente una zona inicial de calibración "
        "(70%) y una zona posterior de validación (30%). Cautious conserva "
        "Entry/SL/TP/leverage originales y simula sólo <b>0.50x del presupuesto "
        "de riesgo</b>.",
        style_body
    ))

    profile_available = int(
        walk.get('cautious_profile_available') or 0
    )
    cautious_candidates = int(
        walk.get('cautious_candidates') or 0
    )
    premium_candidates = int(
        walk.get('premium_candidates') or 0
    )
    cutoff = str(
        walk.get('cutoff_created_at') or '—'
    )

    overview_rows = [
        ['Validación Commit 36', 'Valor'],
        ['Snapshots Cautious disponibles', str(profile_available)],
        ['Candidatos CAUTIOUS_SHADOW', str(cautious_candidates)],
        ['Futures Premium verificables', str(premium_candidates)],
        ['Corte temporal 70/30', cutoff[:32]],
        ['Estado promoción', str(walk.get('promotion_status') or 'NOT_READY')],
    ]
    twalk = Table(overview_rows, colWidths=[10.5*cm, 5.5*cm])
    twalk.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#1565c0')),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#edf5ff'), white]),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(twalk)

    def _wf_text(value, fmt='.3f', suffix=''):
        if value is None:
            return '—'
        try:
            return f"{float(value):{fmt}}{suffix}"
        except Exception:
            return str(value)

    def _append_wf_table(title, block):
        story.append(Paragraph(title, style_h3))
        rows = [[
            'Cohorte', 'N', 'Entry', 'TP', 'SL', 'WR %',
            'Exp.R', 'Exp.R riesgo', 'DD riesgo R', 'N neto'
        ]]

        for label, key in (
            ('PREMIUM', 'premium'),
            ('CAUTIOUS', 'cautious'),
        ):
            metrics = (block.get(key) or {}) if isinstance(block, dict) else {}
            rows.append([
                label,
                str(metrics.get('total', 0)),
                str(metrics.get('entry_touched', 0)),
                str(metrics.get('tp_hit', 0)),
                str(metrics.get('sl_hit', 0)),
                '—' if metrics.get('win_rate') is None else f"{metrics.get('win_rate'):.1f}",
                '—' if metrics.get('expectancy_r') is None else f"{metrics.get('expectancy_r'):+.3f}",
                '—' if metrics.get('budget_expectancy_r') is None else f"{metrics.get('budget_expectancy_r'):+.3f}",
                '—' if metrics.get('max_drawdown_budget_r') is None else f"{metrics.get('max_drawdown_budget_r'):.3f}",
                str(metrics.get('net_outcome_samples', 0)),
            ])

        table = Table(
            rows,
            colWidths=[2.2*cm, 0.8*cm, 1.0*cm, 0.8*cm, 0.8*cm,
                       1.2*cm, 1.3*cm, 1.7*cm, 1.7*cm, 1.1*cm]
        )
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#3949ab')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7.4),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f1f3ff'), white]),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ]))
        story.append(table)

    _append_wf_table(
        "Calibración temporal — primeros 70%",
        walk.get('calibration') or {}
    )
    _append_wf_table(
        "Validación fuera de tiempo — últimos 30%",
        walk.get('validation') or {}
    )

    story.append(Paragraph(
        "<b>Exp.R riesgo</b> expresa la contribución al presupuesto normal de "
        "riesgo: Premium usa 1.00x y Cautious 0.50x. El R geométrico de la "
        "operación no cambia. <b>DD riesgo R</b> es el drawdown secuencial de "
        "resultados resueltos expresado en ese mismo presupuesto; no es dinero "
        "real.",
        style_note
    ))

    status_counts = walk.get('cautious_status_counts') or {}
    if status_counts:
        story.append(Paragraph("Cobertura del experimento Cautious", style_h3))
        rows = [['Estado Cautious', 'N']]
        for key, value in sorted(
            status_counts.items(),
            key=lambda item: (-int(item[1]), str(item[0]))
        ):
            rows.append([str(key)[:45], str(value)])
        tcov = Table(rows, colWidths=[11*cm, 2.5*cm])
        tcov.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#00838f')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#edfafa'), white]),
        ]))
        story.append(tcov)

    story.append(Paragraph("Gate de promoción al Commit 37", style_h3))
    if walk.get('promotion_ready'):
        story.append(Paragraph(
            "<b>READY_FOR_COMMIT_37_REVIEW</b>: la cohorte supera los guardrails "
            "estadísticos de este informe. Esto NO la publica automáticamente; "
            "sólo habilita una revisión explícita antes de tocar producción.",
            style_note
        ))
    else:
        reasons = walk.get('promotion_reasons') or [
            'Todavía no existe evidencia suficiente.'
        ]
        reason_text = '<br/>'.join(
            f"• {str(reason)}"
            for reason in reasons[:8]
        )
        story.append(Paragraph(
            "<b>NO PROMOVER.</b><br/>" + reason_text,
            style_note
        ))

    story.append(Paragraph(
        "<b>Costes:</b> para ser CAUTIOUS_SHADOW el setup ya tuvo que pasar el "
        "guardrail económico NET_PROFIT calculado por Futures en el momento de "
        "la señal. Sin embargo, este informe no inventa comisión, slippage o "
        "funding realizados. La promoción queda bloqueada hasta que los resultados "
        "resueltos persistan atribución neta verificable (por ejemplo net_pnl_pct).",
        style_note
    ))

    story.append(Paragraph(
        "<b>MISSING_PUBLICATION_GATE:</b> desde Commit 36C un rechazo nuevo que "
        "ocurra antes del gate Premium se clasifica como PRE_GATE_REJECTION. Por "
        "tanto, los MISSING históricos no se reinterpretan ni se convierten "
        "retroactivamente en una causa que nunca fue persistida.",
        style_note
    ))

    # =============================================================
    # COMMIT 36D — FUNNEL EXACTO DE RECHAZOS FUTURES
    # =============================================================
    story.append(PageBreak())
    story.append(Paragraph(
        "FUTURES — funnel exacto de filtros y timidez",
        style_h2
    ))
    story.append(Paragraph(
        "Commit 36D separa por primera vez los rechazos que ocurren "
        "<b>antes</b> del publication gate Premium de los rechazos que sí llegan "
        "al gate. La tabla usa sólo snapshots instrumentados por los commits "
        "recientes; el Shadow histórico sin snapshot permanece fuera del funnel "
        "para evitar atribuirle una causa inventada. Ninguna fila de esta página "
        "modifica el motor operativo.",
        style_body
    ))

    shadow_total = int(walk.get('shadow_total_available') or 0)
    instrumented = int(walk.get('cautious_profile_available') or 0)
    historical_unclassified = int(
        walk.get('shadow_without_cautious_profile') or 0
    )
    pre_gate_exact = int(walk.get('pre_gate_exact_profiles') or 0)
    publication_exact = int(
        walk.get('publication_gate_exact_profiles') or 0
    )

    funnel_rows = [
        ['Etapa del funnel', 'N', 'Interpretación'],
        [
            'Shadow limpio (90 días)',
            str(shadow_total),
            'Inventario diagnóstico, no operaciones publicadas'
        ],
        [
            'Snapshots instrumentados',
            str(instrumented),
            'Tienen perfil Cautious y pueden ubicarse en el funnel'
        ],
        [
            'Histórico sin instrumentación',
            str(historical_unclassified),
            'No se hace backfill ni se inventa causa'
        ],
        [
            'Rechazo PRE-GATE exacto',
            str(pre_gate_exact),
            'Falló antes de _apply_futures_publication_gate()'
        ],
        [
            'Publication Gate exacto',
            str(publication_exact),
            'Llegó al gate Premium y conserva sus motivos exactos'
        ],
        [
            'CAUTIOUS_SHADOW',
            str(cautious_candidates),
            'Hipótesis 0.50x; no publicada'
        ],
        [
            'PREMIUM verificable',
            str(premium_candidates),
            'Única cohorte Futures potencialmente operable actual'
        ],
    ]
    tfunnel = Table(
        funnel_rows,
        colWidths=[5.0*cm, 1.4*cm, 9.0*cm]
    )
    tfunnel.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#6a1b9a')),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.0),
        ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f7effb'), white]),
        ('ALIGN', (1,0), (1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(tfunnel)

    pre_gate_counts = walk.get('pre_gate_reason_counts') or {}
    story.append(Paragraph(
        "Rechazos exactos ANTES del Publication Gate",
        style_h3
    ))
    if pre_gate_counts:
        rows = [['Código', 'Motivo', 'N']]
        for code, count in sorted(
            pre_gate_counts.items(),
            key=lambda item: (-int(item[1]), str(item[0]))
        ):
            code = str(code).upper()
            rows.append([
                code,
                FUTURES_PRE_GATE_REASON_LABELS.get(
                    code,
                    'Otro rechazo pre-gate'
                ),
                str(count),
            ])
        tpre = Table(rows, colWidths=[4.2*cm, 8.5*cm, 1.5*cm])
        tpre.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#ef6c00')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.2),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#fff4e8'), white]),
            ('ALIGN', (-1,0), (-1,-1), 'CENTER'),
        ]))
        story.append(tpre)
    else:
        story.append(Paragraph(
            "<i>Todavía no hay rechazos pre-gate exactos persistidos en la "
            "ventana instrumentada. Los registros históricos no se reclasifican "
            "retroactivamente.</i>",
            style_note
        ))

    publication_counts = walk.get('publication_gate_reason_counts') or {}
    story.append(Paragraph(
        "Rechazos exactos DENTRO del Publication Gate Premium",
        style_h3
    ))
    if publication_counts:
        rows = [['Código', 'Motivo', 'N']]
        for code, count in sorted(
            publication_counts.items(),
            key=lambda item: (-int(item[1]), str(item[0]))
        ):
            code = str(code).upper()
            rows.append([
                code,
                FUTURES_PUBLICATION_REASON_LABELS.get(
                    code,
                    'Otro bloqueo'
                ),
                str(count),
            ])
        tpub = Table(rows, colWidths=[4.2*cm, 8.5*cm, 1.5*cm])
        tpub.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#1565c0')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.2),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#edf5ff'), white]),
            ('ALIGN', (-1,0), (-1,-1), 'CENTER'),
        ]))
        story.append(tpub)
    else:
        story.append(Paragraph(
            "<i>Todavía no hay snapshots exactos del Publication Gate entre los "
            "perfiles instrumentados de esta ventana. No se usa el fallback "
            "histórico para atribuir una causa exacta.</i>",
            style_note
        ))

    story.append(Paragraph(
        "<b>Cómo leer el funnel:</b> si predominan HARD_SAFETY, LOSS_AT_SL o "
        "ATR_STRESS, el problema está en seguridad/riesgo y no debemos volver "
        "Futures más agresivo. Si, con muestra suficiente, predominan bloqueos "
        "cercanos a Premium como SAFETY o TP_QUALITY y esa subcohorte demuestra "
        "expectancy neta positiva fuera de tiempo, recién entonces existe una "
        "hipótesis seria para Cautious.",
        style_note
    ))

    story.append(Paragraph(
        "<b>Regla de interpretación:</b> un Shadow que habría tocado TP no prueba "
        "por sí solo que debió publicarse. Para relajar Futuros necesitaremos una "
        "cohorte suficiente, expectancy positiva después de costos y validación "
        "walk-forward. Hasta entonces la política operativa permanece intacta.",
        style_note
    ))

    # =============================================================
    # COMMIT 36G — ANATOMÍA DE EXECUTION SAFETY
    # =============================================================
    safety_diag = data.get('futures_safety_breakdown_analysis') or {}

    story.append(PageBreak())
    story.append(Paragraph(
        "FUTURES — anatomía de Execution Safety",
        style_h2
    ))
    story.append(Paragraph(
        "Commit 36G estudia los componentes que <b>ya calculó</b> el motor en "
        "Commit 36F. No recalcula Safety, no cambia pesos y no baja el mínimo "
        "operativo. El objetivo es explicar por qué una oportunidad termina en "
        "<b>HARD_SAFETY</b> antes de llegar al Publication Gate.",
        style_body
    ))

    hard_total_exact = int(
        (walk.get('pre_gate_reason_counts') or {}).get(
            'HARD_SAFETY',
            0
        )
        or 0
    )
    breakdown_available = int(
        safety_diag.get('breakdown_available') or 0
    )
    hard_breakdown = int(
        safety_diag.get('hard_safety_breakdown_available') or 0
    )
    hard_coverage = (
        hard_breakdown / hard_total_exact * 100.0
        if hard_total_exact > 0
        else None
    )

    def _diag_num(value, digits=2, signed=False):
        if value is None:
            return '—'
        try:
            number = float(value)
            if signed:
                return f"{number:+.{digits}f}"
            return f"{number:.{digits}f}"
        except Exception:
            return str(value)

    overview = [
        ['Diagnóstico Execution Safety', 'Valor'],
        ['Snapshots 36F con breakdown', str(breakdown_available)],
        ['HARD_SAFETY exactos en funnel', str(hard_total_exact)],
        ['HARD_SAFETY con breakdown 36F', str(hard_breakdown)],
        [
            'Cobertura breakdown de HARD_SAFETY',
            '—' if hard_coverage is None else f"{hard_coverage:.1f}%"
        ],
        [
            'Safety medio HARD_SAFETY',
            _diag_num(safety_diag.get('avg_raw_score_hard'))
        ],
        [
            'Mínimo operativo medio',
            _diag_num(safety_diag.get('avg_operational_minimum_hard'))
        ],
        [
            'Déficit medio hasta mínimo',
            _diag_num(safety_diag.get('avg_shortfall_hard'))
        ],
        [
            'Estado de muestra',
            str(safety_diag.get('sample_status') or 'SIN_MUESTRA')
        ],
    ]
    tdiag = Table(overview, colWidths=[10.2*cm, 5.8*cm])
    tdiag.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#455a64')),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.6),
        ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f3f6f7'), white]),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(tdiag)

    component_rows = safety_diag.get('component_rows') or []
    story.append(Paragraph(
        "Componentes del score en los rechazos HARD_SAFETY",
        style_h3
    ))

    if component_rows and hard_breakdown > 0:
        rows = [[
            'Componente', 'Peso', 'Media all', 'Media HARD',
            'Aporte HARD', 'Penaliz. vs 100', '#1', 'Top3'
        ]]
        for row in component_rows:
            weight = row.get('avg_weight')
            rows.append([
                str(row.get('label') or row.get('component') or '')[:24],
                '—' if weight is None else f"{float(weight)*100:.0f}%",
                _diag_num(row.get('avg_all_score'), 1),
                _diag_num(row.get('avg_hard_score'), 1),
                _diag_num(row.get('avg_weighted_contribution'), 2),
                _diag_num(row.get('avg_penalty_to_perfect'), 2),
                str(row.get('dominant_rank1_count', 0)),
                str(row.get('dominant_top3_count', 0)),
            ])

        tcomp = Table(
            rows,
            colWidths=[3.0*cm, 1.1*cm, 1.7*cm, 1.8*cm,
                       1.9*cm, 2.3*cm, 1.0*cm, 1.0*cm]
        )
        tcomp.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#6d4c41')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7.4),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#faf4f1'), white]),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(tcomp)

        story.append(Paragraph(
            "<b>Penaliz. vs 100</b> es la cantidad media de puntos ponderados "
            "que ese componente deja de aportar respecto de un componente "
            "perfecto de 100. No equivale a la distancia directa al umbral 65; "
            "sirve para ordenar qué partes del score están restando más.",
            style_note
        ))

        culprits = safety_diag.get('ranked_culprits') or []
        if culprits:
            culprit_text = []
            for index, row in enumerate(culprits[:3], 1):
                culprit_text.append(
                    f"{index}. <b>{str(row.get('label') or row.get('component'))}</b>: "
                    f"media { _diag_num(row.get('avg_hard_score'), 1) }, "
                    f"penalización { _diag_num(row.get('avg_penalty_to_perfect'), 2) } pts, "
                    f"#1 en {int(row.get('dominant_rank1_count') or 0)} casos."
                )
            story.append(Paragraph(
                "<b>Top 3 penalizaciones observadas:</b><br/>"
                + '<br/>'.join(culprit_text),
                style_note
            ))
    else:
        story.append(Paragraph(
            "<i>Todavía no hay rechazos HARD_SAFETY nuevos con el breakdown del "
            "Commit 36F. Es esperable justo después del despliegue: no se hace "
            "backfill de los 16 rechazos anteriores.</i>",
            style_note
        ))

    hard_outcomes = safety_diag.get('hard_safety_outcomes') or {}
    story.append(Paragraph(
        "Resultado posterior de la cohorte HARD_SAFETY instrumentada",
        style_h3
    ))
    outcome_rows = [
        ['N', 'Entry', 'TP', 'SL', 'Expired', 'WR %', 'Exp. R'],
        [
            str(hard_outcomes.get('total', 0)),
            str(hard_outcomes.get('entry_touched', 0)),
            str(hard_outcomes.get('tp_hit', 0)),
            str(hard_outcomes.get('sl_hit', 0)),
            str(hard_outcomes.get('expired', 0)),
            '—' if hard_outcomes.get('win_rate') is None
                else f"{hard_outcomes.get('win_rate'):.1f}",
            '—' if hard_outcomes.get('expectancy_r') is None
                else f"{hard_outcomes.get('expectancy_r'):+.3f}",
        ]
    ]
    tout = Table(
        outcome_rows,
        colWidths=[1.5*cm, 1.7*cm, 1.5*cm, 1.5*cm, 1.8*cm, 1.7*cm, 2.0*cm]
    )
    tout.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#0277bd')),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.0),
        ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#eef8fd'), white]),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(tout)

    delta_avg = safety_diag.get('reconstruction_delta_avg_abs')
    delta_max = safety_diag.get('reconstruction_delta_max_abs')
    delta_warnings = int(
        safety_diag.get('reconstruction_warning_count') or 0
    )
    story.append(Paragraph(
        "<b>Control de integridad:</b> delta absoluto medio entre el score "
        f"persistido y la reconstrucción ponderada = {_diag_num(delta_avg, 3)}; "
        f"máximo = {_diag_num(delta_max, 3)}; casos con |delta| &gt; 0.25 = "
        f"{delta_warnings}. Una diferencia material no autoriza recalibrar: "
        "primero indicaría que debemos revisar instrumentación/fórmula.",
        style_note
    ))

    tf_sources = safety_diag.get('timeframe_factor_source_counts') or {}
    if tf_sources:
        source_text = ', '.join(
            f"{key}: {value}"
            for key, value in list(tf_sources.items())[:5]
        )
        story.append(Paragraph(
            "<b>Fuente del componente temporalidad:</b> " + source_text + ". "
            "Si permanece neutral/no calibrado, se interpreta como limitación "
            "de evidencia y no como señal para bajar Safety.",
            style_note
        ))

    sample_status = str(
        safety_diag.get('sample_status') or 'SIN_MUESTRA'
    )
    if sample_status == 'REVISABLE_DIAGNOSTICAMENTE':
        policy_note = (
            "La muestra ya permite revisar técnicamente la calibración de los "
            "componentes, pero <b>no</b> autoriza modificar pesos o umbrales: "
            "todavía necesitamos relacionar los componentes con expectancy "
            "fuera de muestra y costes netos."
        )
    elif sample_status == 'PRELIMINAR':
        policy_note = (
            "La muestra es preliminar. Sirve para identificar una hipótesis "
            "dominante, no para cambiar pesos, mínimo 65 o Publication Gate."
        )
    else:
        policy_note = (
            "La muestra aún es insuficiente. Deben acumularse nuevos HARD_SAFETY "
            "instrumentados por Commit 36F antes de inferir qué componente está "
            "causando la timidez."
        )

    story.append(Paragraph(
        "<b>Decisión del Commit 36G:</b> " + policy_note,
        style_note
    ))

    story.append(PageBreak())

    # ============ 4. TOP 20 MEJORES ESTRATEGIAS GENERALES ============
    story.append(Paragraph("Mejores estrategias por mercado", style_h2))
    story.append(Paragraph(
        "Spot y Futuros permanecen separados. La <b>Expectancy R</b> es el "
        "promedio de los resultados R propios de cada señal; ya no supone que "
        "todas las ganadoras valen +2R. El PnL es bruto, antes de costos. "
        "La columna 'Confianza estadística' indica si la muestra es suficiente para "
        f"tomar la métrica como válida (≥{GENERAL_SAMPLES_RIGOROUS} muestras).",
        style_note
    ))
    
    top_general = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_general
            if s['market'] == market
            and s['sample_size'] >= GENERAL_SAMPLES_MIN
        ]
        top_general.extend(
            sorted(market_rows, key=lambda r: (-r['expectancy'], -r['sample_size']))[:10]
        )
    if top_general:
        rows = [['#', 'Mercado', 'Estrategia', 'N', 'TP', 'SL', 'Win %', 'Exp. R', 'PnL %', 'Confianza']]
        for i, s in enumerate(top_general, 1):
            badge_txt, _ = _confidence_badge(s['sample_size'], GENERAL_SAMPLES_RIGOROUS)
            rows.append([
                str(i), s['market'].upper(), s['strategy'][:27], str(s['sample_size']),
                str(s['wins']), str(s['losses']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%", badge_txt
            ])
        t = Table(rows, colWidths=[0.6*cm, 1.6*cm, 4.2*cm, 0.9*cm, 0.8*cm,
                                  0.8*cm, 1.2*cm, 1.2*cm, 1.4*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-2,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Aún no hay estrategias con al menos {GENERAL_SAMPLES_MIN} muestras evaluadas.</i>",
            style_body
        ))
    
    # ============ 5. TOP 20 PEORES ESTRATEGIAS GENERALES ============
    story.append(Paragraph("Estrategias con peor evidencia por mercado", style_h2))
    story.append(Paragraph(
        "Se muestran por separado y se ordenan por Expectancy R observada. Una "
        "muestra preliminar sirve para investigar, no para cambiar pesos automáticamente.",
        style_note
    ))
    
    worst_general = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_general
            if s['market'] == market
            and s['sample_size'] >= GENERAL_SAMPLES_MIN
        ]
        worst_general.extend(
            sorted(market_rows, key=lambda r: (r['expectancy'], -r['sample_size']))[:10]
        )
    if worst_general:
        rows = [['#', 'Mercado', 'Estrategia', 'N', 'TP', 'SL', 'Win %', 'Exp. R', 'PnL %', 'Confianza']]
        for i, s in enumerate(worst_general, 1):
            badge_txt, _ = _confidence_badge(s['sample_size'], GENERAL_SAMPLES_RIGOROUS)
            rows.append([
                str(i), s['market'].upper(), s['strategy'][:27], str(s['sample_size']),
                str(s['wins']), str(s['losses']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%", badge_txt
            ])
        t = Table(rows, colWidths=[0.6*cm, 1.6*cm, 4.2*cm, 0.9*cm, 0.8*cm,
                                  0.8*cm, 1.2*cm, 1.2*cm, 1.4*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#c92a2a')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-2,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Sin datos suficientes aún.</i>", style_body
        ))
    
    story.append(PageBreak())
    
    # ============ 6. APRENDIZAJE ESPECÍFICO ============
    story.append(Paragraph("Combinaciones específicas por mercado", style_h2))
    story.append(Paragraph(
        "Aprendizaje más granular: dónde exactamente rinde cada estrategia. "
        f"Requiere ≥{SPECIFIC_SAMPLES_MIN} muestras para aparecer, ≥{SPECIFIC_SAMPLES_RIGOROUS} para ser 'válida'.",
        style_note
    ))
    
    top_specific = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_specific
            if s['market'] == market
            and s['sample_size'] >= SPECIFIC_SAMPLES_MIN
        ]
        top_specific.extend(
            sorted(market_rows, key=lambda r: (-r['expectancy'], -r['sample_size']))[:8]
        )
    if top_specific:
        rows = [['Mercado', 'Par', 'TF', 'Acción', 'Estrategia', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in top_specific:
            rows.append([
                s['market'].upper(), s['symbol'], s['timeframe'], s['action'],
                s['strategy'][:20], str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.6*cm, 2.0*cm, 1.0*cm, 1.5*cm, 3.6*cm,
                                  0.8*cm, 1.2*cm, 1.3*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (4,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Aún no hay combinaciones específicas con ≥{SPECIFIC_SAMPLES_MIN} muestras.</i>",
            style_body
        ))
    
    # Peores específicas
    story.append(Paragraph("Peores combinaciones específicas por mercado", style_h2))
    worst_specific = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_specific
            if s['market'] == market
            and s['sample_size'] >= SPECIFIC_SAMPLES_MIN
        ]
        worst_specific.extend(
            sorted(market_rows, key=lambda r: (r['expectancy'], -r['sample_size']))[:8]
        )
    if worst_specific:
        rows = [['Mercado', 'Par', 'TF', 'Acción', 'Estrategia', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in worst_specific:
            rows.append([
                s['market'].upper(), s['symbol'], s['timeframe'], s['action'],
                s['strategy'][:20], str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.6*cm, 2.0*cm, 1.0*cm, 1.5*cm, 3.6*cm,
                                  0.8*cm, 1.2*cm, 1.3*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#c92a2a')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(f"<i>Sin datos suficientes.</i>", style_body))
    
    # ============ v22: 7. ESTRATEGIAS POR TRADER (auditoría del comité) ============
    # Permite al usuario verificar que cada uno de los 10 traders está
    # aportando estrategias distintas y qué performance tiene cada uno.
    story.append(Paragraph("Estrategias por trader (cobertura del comité)", style_h2))
    story.append(Paragraph(
        "Cada uno de los 10 traders del sistema emite un conjunto de estrategias distintas. "
        "La contribución se separa por mercado. Esta tabla muestra <b>qué está aportando cada trader</b>: cuántas estrategias diferentes "
        "ha emitido, cuántas señales resueltas tiene y su win rate. Si un trader tiene 0 señales, "
        "significa que no ha aportado en el período — puede indicar que no encuentra setups o que "
        "sus estrategias están silenciadas por el régimen de mercado actual.",
        style_body
    ))
    
    # stats_by_trader ya fue calculado al inicio para poder liberar
    # signals_with_ind antes de que ReportLab construya el PDF.
    if stats_by_trader:
        rows = [['Mercado', 'Trader', '# Estr.', 'Señales', 'TP', 'SL', 'Expired', 'Win %']]
        for s in stats_by_trader:
            active_mark = '' if s['signals'] > 0 else ' (inactivo)'
            rows.append([
                s['market'].upper(),
                s['trader'] + active_mark,
                str(s['unique_strategies']),
                str(s['signals']),
                str(s['wins']),
                str(s['losses']),
                str(s['expired']),
                f"{s['win_rate']}%" if s['signals'] > 0 else '—'
            ])
        t = Table(rows, colWidths=[1.7*cm, 3.8*cm, 1.4*cm, 1.5*cm, 1.0*cm,
                                  1.0*cm, 1.5*cm, 1.4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#1a5490')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
        
        # Detalle: estrategias emitidas por cada trader activo
        trader_details = [
            Paragraph("Estrategias emitidas por cada trader (detalle)", style_h3)
        ]
        for s in stats_by_trader:
            if s['unique_strategies'] == 0:
                continue
            strategies_str = ', '.join(s['strategies'])
            trader_details.append(Paragraph(
                f"<b>[{s['market'].upper()}] {s['trader']}</b> "
                f"({s['unique_strategies']} estrategias): "
                f"<font color='#555'>{strategies_str}</font>",
                style_note
            ))
        story.append(KeepTogether(trader_details))
    else:
        story.append(Paragraph("<i>Sin datos suficientes — el sistema aún no ha resuelto señales.</i>", style_body))
    
    # ============ 8. APRENDIZAJE POR PAR ============
    story.append(Paragraph("Aprendizaje por par y mercado", style_h2))
    if stats_by_symbol:
        rows = [['Mercado', 'Par', 'TP', 'SL', 'Expired', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in stats_by_symbol:
            rows.append([
                s['market'].upper(), s['symbol'], str(s['wins']), str(s['losses']),
                str(s['expired']), str(s['sample_size']), f"{s['win_rate']}%",
                f"{s['expectancy']:+.3f}", f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.8*cm, 2.3*cm, 1.0*cm, 1.0*cm, 1.4*cm,
                                  1.0*cm, 1.3*cm, 1.3*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#1a5490')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>Sin datos.</i>", style_body))
    
    # ============ 8. APRENDIZAJE POR TIMEFRAME ============
    story.append(Paragraph("Aprendizaje por timeframe y mercado", style_h2))
    if stats_by_tf:
        rows = [['Mercado', 'Timeframe', 'TP', 'SL', 'Expired', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in stats_by_tf:
            rows.append([
                s['market'].upper(), s['timeframe'], str(s['wins']),
                str(s['losses']), str(s['expired']), str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.8*cm, 2.0*cm, 1.0*cm, 1.0*cm, 1.4*cm,
                                  1.0*cm, 1.3*cm, 1.3*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#1a5490')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>Sin datos.</i>", style_body))
    
    story.append(PageBreak())
    
    # ============ 9. OPORTUNIDADES PERDIDAS - ANÁLISIS DE INDICADORES ============
    story.append(Paragraph("Análisis de oportunidades perdidas", style_h2))
    story.append(Paragraph(
        f"Se han detectado <b>{missed_analysis['total']}</b> oportunidades perdidas — "
        f"casos donde el sistema decidió NO_OPERAR pero el precio se movió >2% en una "
        f"dirección clara. La tabla histórica no identifica de forma fiable Spot/Futuros "
        f"ni demuestra que la entrada hubiese sido ejecutable. Por eso se usa sólo para "
        f"formular hipótesis y no para subir pesos automáticamente.",
        style_body
    ))
    
    if missed_analysis['top_indicators']:
        story.append(Paragraph("Top 15 indicadores/estrategias más frecuentes en oportunidades perdidas", style_h3))
        story.append(Paragraph(
            "Cuando estos indicadores estaban activos, el sistema no operó pero el mercado sí se movió. "
            "La frecuencia por sí sola <b>no prueba rentabilidad</b>: falta confirmar Entry, "
            "SL, TP, costos y mercado de procedencia.",
            style_note
        ))
        rows = [['#', 'Indicador / Estrategia', 'Veces aparece', 'Movimiento medio']]
        for i, (ind, count, avg_pct) in enumerate(missed_analysis['top_indicators'], 1):
            rows.append([str(i), ind[:35], str(count), f"{avg_pct:.2f}%"])
        t = Table(rows, colWidths=[0.8*cm, 8*cm, 3*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#e8a500')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ]))
        story.append(t)
    
    if missed_analysis['top_combinations']:
        story.append(Paragraph("Top 10 COMBINACIONES de indicadores en oportunidades perdidas", style_h3))
        story.append(Paragraph(
            "Estas combinaciones de 2 indicadores/estrategias aparecen juntas frecuentemente "
            "cuando el sistema no toma la operación pero el precio sí se mueve. Son candidatos "
            "para pruebas posteriores, <b>no señales autorizadas de trade</b>.",
            style_note
        ))
        rows = [['#', 'Combinación', 'Veces aparece', 'Movimiento medio']]
        for i, (combo, count, avg_pct) in enumerate(missed_analysis['top_combinations'], 1):
            rows.append([str(i), combo[:50], str(count), f"{avg_pct:.2f}%"])
        t = Table(rows, colWidths=[0.8*cm, 9*cm, 2.5*cm, 3.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#8a3ffc')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ]))
        story.append(t)
    
    if missed_analysis['top_pairs']:
        story.append(Paragraph("Pares con más oportunidades perdidas", style_h3))
        rows = [['Par + TF', 'Oportunidades perdidas']]
        for pair, count in missed_analysis['top_pairs']:
            rows.append([pair, str(count)])
        t = Table(rows, colWidths=[8*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#333')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
        ]))
        story.append(t)
    
    if not missed_analysis['top_indicators'] and not missed_analysis['top_combinations']:
        story.append(Paragraph(
            "<i>No hay oportunidades perdidas registradas con detalles de indicadores todavía.</i>",
            style_body
        ))
    
    # ============ 10. NOTAS TÉCNICAS ============
    story.append(PageBreak())
    story.append(Paragraph("Notas técnicas sobre el aprendizaje", style_h2))
    story.append(Paragraph(
        f"<b>Umbrales estadísticos:</b>"
        f"<br/>• Muestras mínimas para publicar estrategia como VÁLIDA (nivel específico): "
        f"<b>{SPECIFIC_SAMPLES_RIGOROUS}</b>"
        f"<br/>• Muestras mínimas para publicar estrategia como VÁLIDA (nivel general): "
        f"<b>{GENERAL_SAMPLES_RIGOROUS}</b>"
        f"<br/>• Muestras mínimas para mostrar en el PDF (preliminares): "
        f"<b>{SPECIFIC_SAMPLES_MIN}/{GENERAL_SAMPLES_MIN}</b>"
        f"<br/>• El win rate es descriptivo: no demuestra rentabilidad sin tamaño de "
        f"ganancias, pérdidas y costos."
        f"<br/>• Expectancy R = promedio de cada resultado dividido por el riesgo "
        f"Entry–SL de esa misma señal; no se supone RR fijo 2:1."
        f"<br/><br/>"
        f"<b>Cómo se aprende:</b>"
        f"<br/>• El learning worker corre cada 15 minutos: evalúa señales pendientes y "
        f"marca TP, SL, expiración, ambigüedad o setup inválido."
        f"<br/>• TP y SL en la misma vela no cuentan como win ni loss hasta resolver "
        f"su orden con datos más finos."
        f"<br/>• Las estadísticas OPERABLES de Futuros sólo usan contratos perpetuos "
        f"reales, vela fuente cerrada y señales que superaron el filtro de publicación. "
        f"El legado queda en cuarentena."
        f"<br/>• Los análisis Futures limpios que no superaron publicación se conservan "
        f"como SHADOW para estudiar timidez/filtros, pero no cambian pesos ni win rate oficial."
        f"<br/>• Cada 4 horas se recalculan las estadísticas cachedas y las recomendaciones."
        f"<br/>• A las 20:00 hora Bolivia corre el ciclo diario completo (evaluación + "
        f"detección de oportunidades perdidas + recalculo + optimización)."
        f"<br/><br/>"
        f"<b>Cómo se aplica el aprendizaje:</b>"
        f"<br/>• El ReviewTrader (10º trader del comité) consulta las estrategias "
        f"históricamente ganadoras para el (par, TF, acción) y emite voto con confianza "
        f"proporcional a cuántas coinciden con las estrategias activas actuales."
        f"<br/>• El voto se pondera con peso 1.0 en el consenso final junto a los otros 9 traders."
        f"<br/>• Las 'oportunidades perdidas' se registran para futura calibración pero "
        f"aún no ajustan automáticamente las decisiones — es información para el operador humano."
        f"<br/>• El PnL de este informe es bruto. Comisión, slippage y funding se "
        f"incorporarán en la siguiente fase económica.",
        style_body
    ))
    
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(
        "© Crypto Trader Analyst Pro — Sistema Experto de Trading. "
        "El aprendizaje se acumula con cada operación evaluada; a más muestras, más precisión.",
        style_meta
    ))
    
    doc.build(story)
    result = buf.getvalue()
    buf.close()
    return result
