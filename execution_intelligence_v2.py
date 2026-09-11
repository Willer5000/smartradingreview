"""Commit 15 — Execution Intelligence V2 (research-only).

Lightweight helpers for the 512 MB Render deployment.  This module deliberately
avoids pandas/numpy and does not fetch market data.  It only transforms evidence
already produced by the Futures engine.

Guardrails:
- no production Entry/SL/TP changes;
- no Safety changes;
- no leverage changes;
- no publication changes;
- no new direction is invented;
- uncertainty is diagnostic until a later empirical conformal calibration has
  enough out-of-sample outcomes.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

EXECUTION_INTELLIGENCE_VERSION = "C15_EXECUTION_INTELLIGENCE_V2"
UNCERTAINTY_VERSION = "C15_UNCERTAINTY_CONFORMAL_FOUNDATION_V1"
MICRO_ENTRY_VERSION = "C15_MICROSTRUCTURE_CONFIRMED_ENTRY_V1"


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    return {
        "COMPRA_SPOT": "LONG",
        "VENTA_SPOT": "SHORT",
        "BUY": "LONG",
        "SELL": "SHORT",
        "ESPERAR": "NO_OPERAR",
        "CAUTION": "NO_OPERAR",
    }.get(text, text if text in {"LONG", "SHORT"} else "NO_OPERAR")


def _normalized_entropy(weights: Iterable[float]) -> float:
    clean = [max(0.0, float(v)) for v in weights if _safe_float(v) is not None]
    total = sum(clean)
    if total <= 0 or len(clean) <= 1:
        return 0.0
    probs = [v / total for v in clean if v > 0]
    if len(probs) <= 1:
        return 0.0
    entropy = -sum(p * math.log(p) for p in probs)
    return _clip(entropy / math.log(len(probs)) * 100.0)


def _vote_uncertainty(analysis: Dict[str, Any]) -> Dict[str, Any]:
    decision = analysis.get("decision") or {}
    registry = decision.get("registro_votacion") or {}
    votes = registry.get("todos_los_votos") if isinstance(registry, dict) else []
    if not isinstance(votes, list) or not votes:
        return {
            "available": False,
            "entropy_pct": None,
            "directional_margin_pct": None,
            "directional_votes": 0,
        }

    buckets = {"LONG": 0.0, "SHORT": 0.0, "NO_OPERAR": 0.0}
    directional_votes = 0
    for vote in votes:
        if not isinstance(vote, dict):
            continue
        action = _normalize_action(vote.get("accion", vote.get("action")))
        if action not in buckets:
            action = "NO_OPERAR"
        weight = _safe_float(vote.get("peso_efectivo"), None)
        confidence = _safe_float(
            vote.get("confianza_original", vote.get("confianza", 0)), 0.0
        ) or 0.0
        if weight is None:
            weight = _safe_float(vote.get("peso_base", vote.get("peso", 1.0)), 1.0) or 1.0
        contribution = max(0.05, weight) * max(0.0, confidence) / 100.0
        buckets[action] += contribution
        if action in {"LONG", "SHORT"}:
            directional_votes += 1

    entropy_pct = _normalized_entropy(buckets.values())
    long_w = buckets["LONG"]
    short_w = buckets["SHORT"]
    denom = long_w + short_w
    margin = abs(long_w - short_w) / denom * 100.0 if denom > 0 else 0.0
    return {
        "available": True,
        "entropy_pct": round(entropy_pct, 2),
        "directional_margin_pct": round(margin, 2),
        "directional_votes": directional_votes,
        "weighted_buckets": {k: round(v, 4) for k, v in buckets.items()},
    }


def build_uncertainty_shadow_gate(
    analysis: Dict[str, Any],
    microstructure_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a bounded, *research-only* uncertainty score.

    This is intentionally labelled a conformal *foundation*, not a calibrated
    conformal predictor.  A true split-conformal threshold requires a stable
    out-of-sample calibration cohort.  Commit 15 records the nonconformity-like
    score prospectively so ReviewTrader can later calibrate that threshold
    without hindsight.
    """
    analysis = analysis if isinstance(analysis, dict) else {}
    decision = analysis.get("decision") or {}
    action = _normalize_action(decision.get("action"))
    levels = analysis.get("levels") or {}
    regime = analysis.get("market_regime") or {}
    micro = microstructure_context if isinstance(microstructure_context, dict) else {}

    vote = _vote_uncertainty(analysis)
    vote_entropy = _safe_float(vote.get("entropy_pct"), 50.0) or 50.0

    confidence = _clip(_safe_float(decision.get("confidence"), 0.0) or 0.0)
    confidence_uncertainty = 100.0 - confidence

    regime_confidence = _clip(_safe_float(regime.get("confidence"), 50.0) or 50.0)
    regime_uncertainty = 100.0 - regime_confidence

    quality_values: List[float] = []
    for key in (
        "entry_defensibility_score",
        "entry_reachability_score",
        "tp_quality_score",
        "execution_safety",
    ):
        value = _safe_float(levels.get(key), None)
        if value is not None:
            quality_values.append(_clip(value))
    sl_rel = _safe_float(levels.get("sl_reliability"), None)
    if sl_rel is not None:
        quality_values.append(_clip(sl_rel * 100.0 if 0 <= sl_rel <= 1 else sl_rel))

    if len(quality_values) >= 2:
        mean_q = sum(quality_values) / len(quality_values)
        variance = sum((value - mean_q) ** 2 for value in quality_values) / len(quality_values)
        # 25 score-points std-dev is already very heterogeneous.
        component_dispersion = _clip(math.sqrt(variance) / 25.0 * 100.0)
    else:
        component_dispersion = 60.0

    micro_available = bool(micro.get("available"))
    micro_score = _safe_float(micro.get("alignment_score"), None)
    if action not in {"LONG", "SHORT"}:
        micro_uncertainty = 50.0
    elif not micro_available or micro_score is None:
        micro_uncertainty = 75.0
    else:
        # Alignment near 50 is maximally ambiguous; extremes are clearer.
        micro_uncertainty = _clip(100.0 - abs(micro_score - 50.0) * 2.0)

    source_count = _safe_float(((micro.get("metrics") or {}).get("source_count")), 0.0) or 0.0
    source_penalty = _clip((4.0 - min(4.0, source_count)) / 4.0 * 100.0)

    uncertainty = (
        0.30 * vote_entropy
        + 0.20 * confidence_uncertainty
        + 0.15 * regime_uncertainty
        + 0.15 * component_dispersion
        + 0.15 * micro_uncertainty
        + 0.05 * source_penalty
    )
    uncertainty = _clip(uncertainty)

    if uncertainty >= 70.0:
        bucket = "HIGH"
        candidate = "ABSTAIN_CANDIDATE"
    elif uncertainty >= 45.0:
        bucket = "MEDIUM"
        candidate = "WATCH_CANDIDATE"
    else:
        bucket = "LOW"
        candidate = "PASS_CANDIDATE"

    reasons = []
    if vote_entropy >= 60:
        reasons.append("Comité con alta dispersión")
    if confidence_uncertainty >= 45:
        reasons.append("Confianza direccional limitada")
    if regime_uncertainty >= 50:
        reasons.append("Régimen poco definido")
    if component_dispersion >= 55:
        reasons.append("Calidad de ejecución heterogénea")
    if micro_uncertainty >= 65:
        reasons.append("Microestructura ambigua/no disponible")
    if source_penalty >= 50:
        reasons.append("Cobertura de fuentes microestructurales incompleta")

    return {
        "version": UNCERTAINTY_VERSION,
        "execution_intelligence_version": EXECUTION_INTELLIGENCE_VERSION,
        "authority": "SHADOW_ONLY",
        "production_change": False,
        "method": "EMPIRICAL_NONCONFORMITY_FOUNDATION",
        "conformal_status": "NOT_CALIBRATED_WAITING_OOS",
        "calibrated": False,
        "action_evaluated": action,
        "uncertainty_score": round(uncertainty, 2),
        "uncertainty_bucket": bucket,
        "shadow_gate": candidate,
        "reasons": reasons[:6],
        "components": {
            "committee_entropy_pct": round(vote_entropy, 2),
            "decision_uncertainty_pct": round(confidence_uncertainty, 2),
            "regime_uncertainty_pct": round(regime_uncertainty, 2),
            "execution_dispersion_pct": round(component_dispersion, 2),
            "microstructure_uncertainty_pct": round(micro_uncertainty, 2),
            "micro_source_penalty_pct": round(source_penalty, 2),
            "directional_margin_pct": vote.get("directional_margin_pct"),
            "directional_votes": vote.get("directional_votes", 0),
        },
        "affects_entry": False,
        "affects_safety": False,
        "affects_publication": False,
        "affects_leverage": False,
        "promotion_requirement": "OOS_CALIBRATION_PLUS_COSTS_PLUS_GOVERNANCE",
    }


def attach_microstructure_entry_challenger(
    analysis: Dict[str, Any],
    microstructure_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a fixed, predeclared microstructure-confirmation challenger.

    It keeps the production geometry unchanged.  The experimental difference is
    the *confirmation condition*: only signals whose contemporaneous public
    order-flow snapshot is ALIGNED enter this challenger cohort.  This makes the
    candidate falsifiable without pretending we can reconstruct future order
    books from OHLC candles.
    """
    analysis = analysis if isinstance(analysis, dict) else {}
    lab = analysis.get("execution_challenger_lab") or {}
    if not isinstance(lab, dict):
        return analysis

    decision = analysis.get("decision") or {}
    action = _normalize_action(decision.get("action"))
    levels = analysis.get("levels") or {}
    micro = microstructure_context if isinstance(microstructure_context, dict) else {}
    if action not in {"LONG", "SHORT"} or not micro.get("available"):
        return analysis

    candidates = list(lab.get("candidates") or [])
    if any(isinstance(item, dict) and item.get("name") == "MICROSTRUCTURE_CONFIRMED_ENTRY" for item in candidates):
        return analysis

    aligned = str(micro.get("alignment") or "").upper() == "ALIGNED"
    entry = _safe_float(levels.get("entry"), None)
    sl = _safe_float(levels.get("stop_loss"), None)
    tp = _safe_float(levels.get("take_profit"), None)
    if not all(value is not None and value > 0 for value in (entry, sl, tp)):
        return analysis
    geometry_valid = (sl < entry < tp) if action == "LONG" else (tp < entry < sl)
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk if geometry_valid and risk > 0 else None

    candidate = {
        "name": "MICROSTRUCTURE_CONFIRMED_ENTRY",
        "version": MICRO_ENTRY_VERSION,
        "mode": "SHADOW_ONLY",
        "available": True,
        "geometry_valid": bool(geometry_valid),
        "action": action,
        "entry": round(entry, 10),
        "stop_loss": round(sl, 10),
        "take_profit": round(tp, 10),
        "risk_reward": round(rr, 4) if rr is not None else None,
        "source": "PUBLIC_ORDER_FLOW_CONFIRMATION",
        "reason": "Baseline geometry; cohort requires contemporaneous microstructure ALIGNED",
        "activation_condition": "MICROSTRUCTURE_ALIGNED_AT_SIGNAL",
        "condition_met_at_signal": bool(aligned),
        "microstructure_alignment": str(micro.get("alignment") or "UNAVAILABLE"),
        "microstructure_score": _safe_float(micro.get("alignment_score"), None),
        "affects_production": False,
    }
    candidates.append(candidate)
    # Fixed maximum: Baseline + original three structural challengers + one
    # genuinely new information source.  This cap limits multiple testing.
    lab = dict(lab)
    lab["candidates"] = candidates[:5]
    policy = dict(lab.get("policy") or {})
    policy["max_candidates_per_signal"] = 5
    policy["microstructure_candidate_predeclared"] = True
    lab["policy"] = policy
    lab["version"] = "C15_EXECUTION_CHALLENGER_LAB_V2"
    analysis["execution_challenger_lab"] = lab
    return analysis
