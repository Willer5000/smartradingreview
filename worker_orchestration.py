"""Commit 17.5.9 — worker orchestration, not trader voting.

This module converts the legacy trader payloads into work products and removes
majority/support-count semantics from the production moderator.  It deliberately
DOES NOT:
- create LONG/SHORT by itself;
- lower thesis, MTF, Safety, Entry/SL/TP, R/R or publication thresholds;
- let one worker veto/flip direction;
- change leverage;
- turn historical priors into calibrated probabilities.

Production ownership:
  Operational Intelligence -> thesis/candidate direction
  Strategy Bank             -> context-fit playbook
  Execution committees      -> Entry/SL/TP geometry
  Safety/Publication        -> final executable permission
  ReviewTrader/Research     -> evidence/governance

Legacy trader outputs remain useful as attribution/diagnostic work products, but
are no longer a second election after Operational Intelligence has already built
a governed candidate.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

VERSION = "COMMIT17_5_10_WORKER_ORCHESTRATION_MM_V1"

DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}

WORKER_ROLES: Dict[str, Dict[str, str]] = {
    "Técnico Puro": {
        "desk": "SETUP", "family": "MOMENTUM_TREND",
        "task": "medir tendencia, fuerza y momentum; describir el setup técnico",
        "deliverable": "technical_setup",
    },
    "Chartista": {
        "desk": "SETUP", "family": "PRICE_ACTION_PATTERN",
        "task": "mapear price action, swings, soportes/resistencias, ruptura y retest",
        "deliverable": "price_action_structure",
    },
    "Cazador de Ballenas": {
        "desk": "CONTEXT", "family": "WHALE_VOLUME",
        "task": "caracterizar flujo, volumen anómalo y actividad whale/iceberg",
        "deliverable": "flow_context",
    },
    "Macroeconomista": {
        "desk": "CONTEXT", "family": "MACRO",
        "task": "caracterizar riesgo/evento macro relevante sin fabricar dirección",
        "deliverable": "macro_risk_context",
    },
    "Pullback": {
        "desk": "EXECUTION", "family": "TIMING_PULLBACK",
        "task": "buscar timing, retroceso y reacción ejecutable sin perseguir precio",
        "deliverable": "timing_candidates",
    },
    "Smart Money": {
        "desk": "EXECUTION", "family": "STRUCTURE_LIQUIDITY",
        "task": "mapear sweep, MSS/BOS, displacement, OB/FVG, POI e invalidaciones",
        "deliverable": "structure_liquidity_map",
    },
    "Escéptico": {
        "desk": "CONTROL", "family": "RISK_CHALLENGE",
        "task": "red-team de la tesis: encontrar contradicciones, riesgos e invalidaciones",
        "deliverable": "counter_evidence",
    },
    "Multiframe": {
        "desk": "CONTEXT", "family": "MULTITIMEFRAME",
        "task": "organizar contexto HTF, TF operativo y conflictos multi-temporales",
        "deliverable": "mtf_context",
    },
    "El Liquidador": {
        "desk": "EXECUTION", "family": "LEVERAGED_LIQUIDITY",
        "task": "interpretar liquidez apalancada, clusters, riesgo squeeze/cascade y contexto Black-Scholes/Greeks/GEX cuando exista cadena de opciones",
        "deliverable": "leveraged_liquidity_context",
    },
    "Trader de Revisión": {
        "desk": "CONTROL", "family": "HISTORICAL_EDGE",
        "task": "aportar evidencia OOS/expectancy/PF/decay y falsos positivos/negativos",
        "deliverable": "statistical_evidence",
    },
}

MARKET_TF_EMPHASIS = {
    "FUTURES": {
        "30M": {"CONTEXT": 0.80, "SETUP": 1.00, "EXECUTION": 1.20, "CONTROL": 1.05},
        "1H":  {"CONTEXT": 0.85, "SETUP": 1.00, "EXECUTION": 1.18, "CONTROL": 1.06},
        "2H":  {"CONTEXT": 0.95, "SETUP": 1.06, "EXECUTION": 1.12, "CONTROL": 1.08},
        "4H":  {"CONTEXT": 1.05, "SETUP": 1.06, "EXECUTION": 1.06, "CONTROL": 1.08},
        "12H": {"CONTEXT": 1.16, "SETUP": 1.02, "EXECUTION": 0.92, "CONTROL": 1.10},
        "1D":  {"CONTEXT": 1.20, "SETUP": 1.00, "EXECUTION": 0.88, "CONTROL": 1.12},
    },
    "SPOT": {
        "4H":  {"CONTEXT": 0.92, "SETUP": 1.02, "EXECUTION": 1.00, "CONTROL": 1.04},
        "12H": {"CONTEXT": 1.02, "SETUP": 1.02, "EXECUTION": 0.96, "CONTROL": 1.06},
        "1D":  {"CONTEXT": 1.16, "SETUP": 1.00, "EXECUTION": 0.82, "CONTROL": 1.10},
        "1W":  {"CONTEXT": 1.22, "SETUP": 0.98, "EXECUTION": 0.76, "CONTROL": 1.12},
    },
    "MULTIASSET": {
        "1H": {"CONTEXT": 1.00, "SETUP": 1.00, "EXECUTION": 1.16, "CONTROL": 1.06},
        "4H": {"CONTEXT": 1.10, "SETUP": 1.04, "EXECUTION": 1.08, "CONTROL": 1.08},
        "1D": {"CONTEXT": 1.20, "SETUP": 1.00, "EXECUTION": 0.90, "CONTROL": 1.12},
    },
}


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _canon_market(market: Any, symbol: Any = "") -> str:
    raw = _u(market)
    if raw in {"MULTIASSET", "MULTI-ASSET", "MULTI_ASSET"}:
        return "MULTIASSET"
    # Multiasset is transported through Futures in the current engine.  Keep a
    # conservative name-based fallback only for the currently governed universe.
    sym = _u(symbol)
    if raw == "FUTURES" and sym in {
        "SPY-USDT", "QQQ-USDT", "CL-USDT", "NATGAS-USDT",
        "COPPER-USDT", "XAG-USDT", "KSTR-USDT",
    }:
        return "MULTIASSET"
    return "FUTURES" if raw == "FUTURES" else "SPOT"


def _canon_action(value: Any, market: str) -> str:
    raw = _u(value)
    if raw in {"BUY", "COMPRA"}:
        return "LONG" if market in {"FUTURES", "MULTIASSET"} else "COMPRA_SPOT"
    if raw in {"SELL", "VENTA"}:
        return "SHORT" if market in {"FUTURES", "MULTIASSET"} else "VENTA_SPOT"
    return raw


def _direction(value: Any) -> str:
    raw = _u(value)
    if raw in {"LONG", "COMPRA_SPOT", "BUY", "BULLISH", "ALCISTA"}:
        return "BULLISH"
    if raw in {"SHORT", "VENTA_SPOT", "SELL", "BEARISH", "BAJISTA"}:
        return "BEARISH"
    return "NEUTRAL"


def _tf(v: Any) -> str:
    raw = _u(v)
    return {"30MIN": "30M", "60M": "1H", "120M": "2H", "240M": "4H", "1DAY": "1D"}.get(raw, raw)


def _role_for(name: Any) -> Dict[str, str]:
    n = str(name or "UNKNOWN")
    return dict(WORKER_ROLES.get(n) or {
        "desk": "SETUP", "family": f"OTHER:{n}",
        "task": "aportar evidencia técnica especializada",
        "deliverable": "specialist_evidence",
    })


def build_worker_desk_snapshot(
    legacy_outputs: Iterable[Mapping[str, Any]] | None,
    operational: Mapping[str, Any] | None,
    *, market: Any, symbol: Any, timeframe: Any,
) -> Dict[str, Any]:
    """Translate legacy trader payloads into non-voting work products.

    The old payload still contains action/confidence fields for compatibility and
    historical attribution.  They are exposed here only as diagnostic hints.
    Production direction belongs to Operational Intelligence.
    """
    op = dict(operational or {})
    mk = _canon_market(market, symbol)
    tf = _tf(timeframe)
    thesis = dict(op.get("thesis") or {})
    thesis_dir = _direction(thesis.get("direction") or op.get("candidate_action"))
    emphasis = dict((MARKET_TF_EMPHASIS.get(mk) or {}).get(tf) or {
        "CONTEXT": 1.0, "SETUP": 1.0, "EXECUTION": 1.0, "CONTROL": 1.0,
    })

    workers: List[Dict[str, Any]] = []
    by_desk: Dict[str, List[str]] = {"CONTEXT": [], "SETUP": [], "EXECUTION": [], "CONTROL": []}
    contradiction_notes: List[str] = []

    for raw in legacy_outputs or []:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("trader") or "UNKNOWN")
        role = _role_for(name)
        observed_action = _canon_action(
            raw.get("accion_normalizada") or raw.get("accion") or raw.get("accion_original"), mk
        )
        observed_dir = _direction(observed_action)
        confidence = max(0.0, min(100.0, _f(
            raw.get("confianza_original") or raw.get("confianza") or raw.get("confianza_ponderada"), 0.0
        )))
        relation = "NOT_APPLICABLE" if observed_action in {"ABSTAIN", "NO_APLICA"} else "NEUTRAL"
        if thesis_dir in {"BULLISH", "BEARISH"} and observed_dir in {"BULLISH", "BEARISH"}:
            relation = "ALIGNED" if observed_dir == thesis_dir else "COUNTER_EVIDENCE"
        reasons = [str(x)[:260] for x in (raw.get("razones") or raw.get("reasons") or []) if str(x).strip()][:6]
        strategies = [str(x)[:120] for x in (raw.get("estrategias") or raw.get("strategies") or []) if str(x).strip()][:8]
        if relation == "COUNTER_EVIDENCE" and reasons:
            contradiction_notes.extend(reasons[:2])

        desk = role["desk"]
        by_desk.setdefault(desk, []).append(name)
        workers.append({
            "worker": name,
            "desk": desk,
            "evidence_family": role["family"],
            "task": role["task"],
            "deliverable": role["deliverable"],
            "timeframe_emphasis": round(float(emphasis.get(desk, 1.0)), 3),
            "legacy_direction_hint": observed_dir,
            "legacy_confidence": round(confidence, 2),
            "applicable": observed_action not in {"ABSTAIN", "NO_APLICA"},
            "relation_to_thesis": relation,
            "strategies_observed": strategies,
            "work_notes": reasons,
            "production_authority": "WORK_PRODUCT_ONLY",
            "can_veto": False,
            "can_flip_direction": False,
        })

    return {
        "version": VERSION,
        "market": mk,
        "symbol": _u(symbol),
        "timeframe": tf,
        "thesis_owner": "OPERATIONAL_INTELLIGENCE",
        "thesis_direction": thesis_dir,
        "workers": workers,
        "desks": by_desk,
        "counter_evidence_notes": contradiction_notes[:8],
        "policy": {
            "majority_vote_used": False,
            "worker_veto_used": False,
            "worker_direction_flip_allowed": False,
            "counter_evidence_is_input_not_authority": True,
            "safety_remains_final_gate": True,
            "market_maker_math_is_tool_not_vote": True,
            "options_gex_cannot_create_direction": True,
        },
    }


def build_strategy_reasoning(operational: Mapping[str, Any] | None, *, market: Any, symbol: Any, timeframe: Any) -> Dict[str, Any]:
    """Expose why the already-selected Strategy Bank playbook fits the context.

    No new strategy is invented here.  default_strategy_bank.select_strategy()
    already evaluates eligible playbooks and provides alternatives; this helper
    makes that reasoning explicit for workers/learning/QA.
    """
    op = dict(operational or {})
    ctx = dict(op.get("context") or {})
    strategy = dict(op.get("default_strategy") or {})
    prior = dict(op.get("selected_research_prior") or {})
    family = _u(strategy.get("family")) or "NONE"
    regime = _u(ctx.get("regime")) or "UNKNOWN"
    volatility = _u(ctx.get("volatility")) or "UNKNOWN"
    alternatives = []
    for row in strategy.get("alternatives") or []:
        if isinstance(row, Mapping):
            alternatives.append({
                "id": row.get("id"), "family": row.get("family"),
                "quality": row.get("quality"), "specialization_key": row.get("specialization_key"),
            })
    reasons: List[str] = []
    if strategy.get("regime_match") is True:
        reasons.append(f"familia compatible con régimen {regime}")
    elif strategy.get("regime_match") is False:
        reasons.append(f"familia no ideal para régimen {regime}")
    if strategy.get("volatility_match") is True:
        reasons.append(f"familia compatible con volatilidad {volatility}")
    elif strategy.get("volatility_match") is False:
        reasons.append(f"familia no ideal para volatilidad {volatility}")
    positives = int(strategy.get("positive_functional_families") or 0)
    negatives = int(strategy.get("negative_functional_families") or 0)
    if positives:
        reasons.append(f"{positives} familias funcionales a favor")
    if negatives:
        reasons.append(f"{negatives} familias funcionales en conflicto")
    if prior:
        reasons.append("evidencia Research usada sólo como prior gobernado")
    if op.get("operational_segment") == "MULTIASSET" or family == "MULTIASSET_DELEGATED":
        reasons.append("estrategia delegada al banco específico por clase de activo/sesión/evento")

    return {
        "version": VERSION,
        "market": _canon_market(market, symbol),
        "symbol": _u(symbol),
        "timeframe": _tf(timeframe),
        "regime": regime,
        "volatility": volatility,
        "candidate_source": op.get("candidate_source"),
        "primary": {
            "id": strategy.get("id"), "family": strategy.get("family"),
            "quality": strategy.get("quality"),
            "regime_match": strategy.get("regime_match"),
            "volatility_match": strategy.get("volatility_match"),
            "specialization_key": strategy.get("specialization_key"),
            "entry_policy": strategy.get("entry_policy"),
            "exit_policy": strategy.get("exit_policy"),
        },
        "alternatives": alternatives[:4],
        "reasoning": reasons,
        "research_prior_state": prior.get("state"),
        "authority": "CONTEXT_STRATEGY_ROUTING",
        "does_not_bypass_safety": True,
        "does_not_create_direction": True,
    }


def moderator_worker_candidate(
    operational: Mapping[str, Any] | None,
    *, market: Any, symbol: Any = "", timeframe: Any = "", worker_desk: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Production moderator without worker elections.

    If Operational Intelligence has already produced a governed candidate, this
    function forwards it to execution.  Worker work products are diagnostic and
    help explain/learn, but they do not add a second majority/veto gate.
    """
    op = dict(operational or {})
    mk = _canon_market(market, symbol)
    action = _canon_action(op.get("candidate_action"), mk)
    if action not in DIRECTIONAL or not bool(op.get("candidate_ready")):
        return {
            "use": False,
            "action": "NO_OPERAR",
            "reason": "OPERATIONAL_CANDIDATE_NOT_READY",
            "version": VERSION,
            "worker_vote_used": False,
        }

    thesis = dict(op.get("thesis") or {})
    strategy = dict(op.get("default_strategy") or {})
    thesis_quality = max(0.0, min(100.0, _f(thesis.get("quality"), 0.0)))
    strategy_quality = max(0.0, min(100.0, _f(strategy.get("quality"), 0.0)))
    source = str(op.get("candidate_source") or "")
    if source == "THESIS_AUTONOMOUS" or strategy_quality <= 0:
        confidence_base = thesis_quality
    else:
        confidence_base = 0.60 * thesis_quality + 0.40 * strategy_quality
    # This is display/ordering confidence only.  Existing downstream Safety and
    # publication gates remain unchanged.
    confidence = min(88.0, max(60.0, confidence_base))
    return {
        "use": True,
        "action": action,
        "confidence": round(confidence, 2),
        "reason": "GOVERNED_THESIS_TO_EXECUTION",
        "candidate_source": source,
        "version": VERSION,
        "worker_vote_used": False,
        "worker_veto_used": False,
        "workers_seen": len((worker_desk or {}).get("workers") or []),
        "safety_unchanged": True,
    }
