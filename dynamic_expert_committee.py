"""Commit 12 — Dynamic Expert Committee, Shadow-first.

The module learns context-specific *candidate* multipliers from Commit 11
out-of-time diagnostics.  It deliberately does not change production votes.
Negative evidence may be surfaced earlier for protection, but activation still
requires governance and a later explicit Canary promotion.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple
import threading
import time

from learning_integrity import normalize_action, safe_float
from trader_intelligence import canonical_regime

DYNAMIC_COMMITTEE_VERSION = "C12_DYNAMIC_EXPERT_COMMITTEE_SHADOW_V1"
MIN_TOTAL_RESOLVED = 25
MIN_VALIDATION_RESOLVED = 10
MIN_POSITIVE_VALIDATION_R = 0.05
MIN_NEGATIVE_VALIDATION_R = -0.20
MIN_MULTIPLIER = 0.75
MAX_MULTIPLIER = 1.25

_PROFILE_LOCK = threading.Lock()
_PROFILE: Dict[str, Any] = {
    "version": DYNAMIC_COMMITTEE_VERSION,
    "authority": "SHADOW_ONLY",
    "production_change": False,
    "generated_at": None,
    "weights": [],
    "ready_for_canary": False,
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _key(row: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    return (
        str(row.get("trader") or "UNKNOWN"),
        str(row.get("market") or "UNKNOWN").upper(),
        str(row.get("timeframe") or "ALL").upper(),
        normalize_action(row.get("direction")),
        canonical_regime(row.get("regime")),
        str(row.get("relation") or "UNKNOWN").upper(),
    )


def _redundancy_penalties(scorecard: Dict[str, Any]) -> Dict[str, float]:
    penalties: Dict[str, float] = {}
    pairs = scorecard.get("pairwise_redundancy") or []
    for pair in pairs if isinstance(pairs, list) else []:
        if not isinstance(pair, dict):
            continue
        n = int(pair.get("co_signal_n") or 0)
        same = safe_float(pair.get("same_side_pct"), 0.0) or 0.0
        if n < 25 or same < 80.0:
            continue
        # Small shadow penalty only. It prevents four correlated opinions from
        # looking like four independent proofs in the research simulator.
        penalty = _clamp(1.0 - min(0.08, (same - 80.0) / 250.0), 0.92, 1.0)
        for name_field in ("trader_a", "trader_b"):
            name = str(pair.get(name_field) or "")
            if name:
                penalties[name] = min(penalties.get(name, 1.0), penalty)
    return penalties


def build_shadow_profile(
    trader_intelligence_v2: Dict[str, Any],
    governance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build bounded candidate weights from chronological validation only."""
    trader_intelligence_v2 = trader_intelligence_v2 or {}
    governance = governance or {}
    scorecard = trader_intelligence_v2.get("scorecard_v1") or {}
    redundancy = _redundancy_penalties(scorecard if isinstance(scorecard, dict) else {})
    validation_rows = trader_intelligence_v2.get("temporal_validation") or []

    weights: List[Dict[str, Any]] = []
    positive_ready = 0
    negative_ready = 0

    for row in validation_rows if isinstance(validation_rows, list) else []:
        if not isinstance(row, dict):
            continue
        n = int(row.get("n_resolved") or 0)
        validation_n = int(row.get("validation_n") or 0)
        val_r = safe_float(row.get("validation_expectancy_r"))
        disc_r = safe_float(row.get("discovery_expectancy_r"))
        if n < MIN_TOTAL_RESOLVED or validation_n < MIN_VALIDATION_RESOLVED or val_r is None:
            continue

        multiplier = 1.0
        evidence = "OBSERVE"
        if val_r >= MIN_POSITIVE_VALIDATION_R and disc_r is not None and disc_r > 0:
            multiplier = 1.0 + min(0.20, max(0.03, val_r * 0.08))
            evidence = "POSITIVE_OOS"
            positive_ready += 1
        elif val_r <= MIN_NEGATIVE_VALIDATION_R:
            multiplier = 1.0 - min(0.20, max(0.05, abs(val_r) * 0.08))
            evidence = "NEGATIVE_OOS"
            negative_ready += 1
        else:
            continue

        trader = str(row.get("trader") or "UNKNOWN")
        redundancy_mult = redundancy.get(trader, 1.0)
        multiplier = _clamp(multiplier * redundancy_mult, MIN_MULTIPLIER, MAX_MULTIPLIER)
        key = _key(row)
        weights.append({
            "trader": key[0], "market": key[1], "timeframe": key[2],
            "direction": key[3], "regime": key[4], "relation": key[5],
            "multiplier": round(multiplier, 4),
            "validation_expectancy_r": round(val_r, 4),
            "discovery_expectancy_r": round(disc_r, 4) if disc_r is not None else None,
            "n_resolved": n,
            "validation_n": validation_n,
            "evidence": evidence,
            "redundancy_multiplier": round(redundancy_mult, 4),
        })

    # Commit 12 never self-activates production. ready_for_canary merely says
    # the quantitative prerequisites exist for a future governed review.
    governance_quality = bool(governance.get("quality_optimization_allowed", False))
    coverage_complete = bool((governance.get("coverage") or {}).get("complete", False))
    ready_for_canary = bool(governance_quality and coverage_complete and positive_ready >= 2)

    weights.sort(key=lambda r: (r["market"], r["timeframe"], r["trader"], r["direction"], r["regime"]))
    return {
        "version": DYNAMIC_COMMITTEE_VERSION,
        "authority": "SHADOW_ONLY",
        "production_change": False,
        "generated_at": time.time(),
        "weights": weights,
        "positive_oos_specializations": positive_ready,
        "negative_oos_specializations": negative_ready,
        "ready_for_canary": ready_for_canary,
        "canary_active": False,
        "policy": {
            "min_multiplier": MIN_MULTIPLIER,
            "max_multiplier": MAX_MULTIPLIER,
            "min_total_resolved": MIN_TOTAL_RESOLVED,
            "min_validation_resolved": MIN_VALIDATION_RESOLVED,
            "redundancy_penalized": True,
            "oos_required": True,
            "cost_governance_required_for_positive_authority": True,
            "cannot_reopen_no_trade_in_production": True,
            "rollback_required_before_future_activation": True,
        },
    }


def install_shadow_profile(profile: Dict[str, Any]) -> None:
    global _PROFILE
    safe_profile = deepcopy(profile if isinstance(profile, dict) else {})
    safe_profile["authority"] = "SHADOW_ONLY"
    safe_profile["production_change"] = False
    safe_profile["canary_active"] = False
    with _PROFILE_LOCK:
        _PROFILE = safe_profile


def get_shadow_profile() -> Dict[str, Any]:
    with _PROFILE_LOCK:
        return deepcopy(_PROFILE)


def get_shadow_multiplier(
    trader: str,
    market: str,
    timeframe: str,
    direction: str,
    regime: str,
    relation: str = "SUPPORT",
) -> float:
    """Most-specific lookup with safe fallbacks; always research-only."""
    trader = str(trader or "UNKNOWN")
    market = str(market or "UNKNOWN").upper()
    timeframe = str(timeframe or "ALL").upper()
    direction = normalize_action(direction)
    regime = canonical_regime(regime)
    relation = str(relation or "SUPPORT").upper()
    profile = get_shadow_profile()
    rows = profile.get("weights") or []

    candidates = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("trader")) != trader:
            continue
        if str(row.get("market") or "").upper() != market:
            continue
        if normalize_action(row.get("direction")) != direction:
            continue
        if str(row.get("relation") or "").upper() != relation:
            continue
        tf = str(row.get("timeframe") or "ALL").upper()
        rg = canonical_regime(row.get("regime"))
        if tf not in {"ALL", timeframe}:
            continue
        if rg not in {"ALL", "UNKNOWN", regime}:
            continue
        specificity = int(tf == timeframe) + int(rg == regime)
        candidates.append((specificity, int(row.get("validation_n") or 0), row))
    if not candidates:
        return 1.0
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return _clamp(safe_float(candidates[0][2].get("multiplier"), 1.0) or 1.0, MIN_MULTIPLIER, MAX_MULTIPLIER)


def simulate_shadow_decision(votes: Iterable[Dict[str, Any]], baseline_action: str) -> Dict[str, Any]:
    """Simulate weighted confidence without touching the moderator result."""
    totals: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    details = []
    for vote in votes or []:
        if not isinstance(vote, dict):
            continue
        action = str(vote.get("accion") or vote.get("normalized_action") or "NEUTRAL").upper()
        if action in {"NEUTRAL", "NO_OPERAR", "ESPERAR"}:
            continue
        conf = safe_float(vote.get("confianza_contabilizada"), safe_float(vote.get("confianza_ponderada"), safe_float(vote.get("confianza"), 0.0))) or 0.0
        mult = safe_float(vote.get("multiplicador_experto_shadow"), 1.0) or 1.0
        simulated = max(0.0, min(100.0, conf * mult))
        totals[action] = totals.get(action, 0.0) + simulated
        counts[action] = counts.get(action, 0) + 1
        details.append({"trader": vote.get("trader"), "action": action, "base_confidence": round(conf, 2), "shadow_multiplier": round(mult, 4), "shadow_confidence": round(simulated, 2)})

    averages = {action: totals[action] / counts[action] for action in totals if counts.get(action)}
    shadow_action = max(averages, key=averages.get) if averages else "NO_OPERAR"
    baseline = str(baseline_action or "NO_OPERAR").upper()
    return {
        "version": DYNAMIC_COMMITTEE_VERSION,
        "authority": "SHADOW_ONLY",
        "production_change": False,
        "baseline_action": baseline,
        "shadow_action": shadow_action,
        "would_change_direction": shadow_action != baseline,
        "would_reopen_no_trade": baseline in {"NO_OPERAR", "ESPERAR", "NEUTRAL"} and shadow_action not in {"NO_OPERAR", "ESPERAR", "NEUTRAL"},
        "average_confidence_by_action": {k: round(v, 2) for k, v in averages.items()},
        "votes": details,
    }
