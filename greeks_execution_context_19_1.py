"""Commit 19.1 FINAL — observed Greeks/options reaction-map execution lens.

Purpose
-------
Use directly observed option-chain reaction levels as a *small confluence/tie-breaker*
inside Entry / SL / TP ranking without turning Greeks into a direction engine.

Anti-overfit / safety contract
------------------------------
* theoretical Black-Scholes surfaces have ZERO live execution authority;
* option levels never create LONG/SHORT;
* option levels never create a standalone Entry/SL/TP price;
* only an already-existing technical candidate may receive a bounded ranking lens;
* Safety, R/R, leverage and publication gates remain downstream and unchanged;
* public OI does not reveal dealer inventory, so CALL+/PUT- GEX stays heuristic.

The helper is pure/local: no network, DB, threads or caches.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

VERSION = "COMMIT19_1_GREEKS_REACTION_MAP_V1"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if isfinite(out) else default
    except Exception:
        return default


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def compact_execution_market_maker_context(mm: Any) -> Dict[str, Any]:
    """Keep only the tiny fields execution committees need.

    UI curves are intentionally removed from the hot analysis path.  The chart
    obtains those curves on demand, so this reduces transient heap pressure on
    the 512 MB Render service and avoids duplicating payloads in runtime objects.
    """
    src = _d(mm)
    if not src:
        return {}
    keep = (
        "version", "available", "authority", "observed_option_chain",
        "dealer_position_sign", "delta_exposure_semantics", "confidence",
        "contracts_used", "spot", "gamma_regime", "zero_dte_gamma_share",
        "nearest_expiry_hours", "gamma_wall", "call_wall", "put_wall",
        "zero_gamma_level", "delta_neutral_level",
        "execution_reaction_map_authority", "can_refine_entry",
        "can_refine_sl", "can_refine_tp", "can_create_direction",
        "can_raise_leverage", "can_bypass_safety",
        "can_create_standalone_execution_level",
        "context_quality_score", "source", "fetched_at",
    )
    out = {k: src.get(k) for k in keep if k in src}
    shadow = _d(src.get("specialist_shadow_context"))
    if shadow:
        out["context_quality_score"] = _f(
            src.get("context_quality_score"),
            _f(shadow.get("context_quality_score"), 0.0),
        )
        if shadow.get("flags"):
            out["flags"] = list(shadow.get("flags") or [])[:8]
    return out


def _observed_eligible(mm: Mapping[str, Any]) -> Tuple[bool, str]:
    if not isinstance(mm, Mapping):
        return False, "NO_CONTEXT"
    if mm.get("observed_option_chain") is not True:
        return False, "THEORETICAL_OR_UNOBSERVED"
    if str(mm.get("execution_reaction_map_authority") or "").upper() != "OBSERVED_CONFLUENCE_RANKER_ONLY":
        return False, "NO_EXECUTION_REACTION_AUTHORITY"
    confidence = str(mm.get("confidence") or "").upper()
    contracts = int(_f(mm.get("contracts_used"), 0.0))
    if confidence not in {"MEDIUM", "HIGH"} or contracts < 8:
        return False, "OBSERVED_CHAIN_TOO_THIN"
    return True, "OBSERVED_CHAIN_OK"


def observed_reaction_map(mm: Any, *, spot: float, atr: float) -> Dict[str, Any]:
    """Return de-duplicated observed reaction levels and a conservative radius."""
    src = _d(mm)
    eligible, reason = _observed_eligible(src)
    s = max(_f(spot), _f(src.get("spot"), 0.0))
    a = max(_f(atr), 0.0)
    if not eligible or s <= 0 or a <= 0:
        return {
            "version": VERSION, "eligible": False, "reason": reason,
            "levels": [], "radius": 0.0,
        }

    # Broad confluence window rather than an optimized strike-specific rule.
    # It is deliberately small enough to act only as a tie-breaker around an
    # already-existing technical zone.
    radius = min(s * 0.006, max(a * 0.22, s * 0.0012))
    dedupe = max(a * 0.06, s * 0.00035)

    raw: List[Tuple[str, float, float]] = [
        ("Zero-Gamma", _f(src.get("zero_gamma_level")), 1.00),
        ("Delta-Neutral", _f(src.get("delta_neutral_level")), 0.95),
        ("Gamma Wall", _f(src.get("gamma_wall")), 1.00),
        ("Call Wall", _f(src.get("call_wall")), 0.85),
        ("Put Wall", _f(src.get("put_wall")), 0.85),
    ]
    levels: List[Dict[str, Any]] = []
    for label, price, strength in raw:
        if price <= 0:
            continue
        merged = None
        for row in levels:
            if abs(_f(row.get("price")) - price) <= dedupe:
                merged = row
                break
        if merged is None:
            levels.append({
                "price": price,
                "labels": [label],
                "strength": strength,
            })
        else:
            merged["strength"] = max(_f(merged.get("strength"), 0.0), strength)
            if label not in merged["labels"]:
                merged["labels"].append(label)

    return {
        "version": VERSION,
        "eligible": bool(levels),
        "reason": "OBSERVED_LEVELS_READY" if levels else "NO_OBSERVED_LEVELS",
        "levels": levels,
        "radius": radius,
        "confidence": str(src.get("confidence") or ""),
        "contracts_used": int(_f(src.get("contracts_used"), 0.0)),
        "dealer_sign_is_heuristic": True,
    }


def _nearest(levels: Iterable[Mapping[str, Any]], price: float) -> Optional[Tuple[Mapping[str, Any], float]]:
    best = None
    for row in levels or []:
        p = _f(row.get("price"), 0.0)
        if p <= 0:
            continue
        d = abs(price - p)
        if best is None or d < best[1]:
            best = (row, d)
    return best


def score_entry_confluence(*, candidate: Mapping[str, Any], context: Mapping[str, Any],
                            current_price: float, atr: float) -> Dict[str, Any]:
    """Bounded tie-breaker for an existing technical Entry candidate only."""
    family = str(candidate.get("family") or "")
    # Baseline-by-itself is not independent technical evidence.
    if family in {"", "baseline"}:
        return {"score": None, "reason": "NO_STANDALONE_OPTIONS_ENTRY"}
    price = _f(candidate.get("price"), 0.0)
    if price <= 0:
        return {"score": None, "reason": "INVALID_PRICE"}
    mm = _d(_d(context).get("market_maker_context"))
    reaction = observed_reaction_map(mm, spot=current_price, atr=atr)
    if not reaction.get("eligible"):
        return {"score": None, "reason": reaction.get("reason")}
    nearest = _nearest(reaction.get("levels") or [], price)
    if nearest is None or nearest[1] > _f(reaction.get("radius"), 0.0):
        return {"score": None, "reason": "NO_OPTIONS_CONFLUENCE_NEAR_TECHNICAL_ENTRY"}
    row, distance = nearest
    radius = max(_f(reaction.get("radius"), 0.0), 1e-12)
    closeness = 1.0 - min(1.0, distance / radius)
    multi = max(1, len(list(row.get("labels") or [])))
    score = _clip(58.0 + 24.0 * closeness + 4.0 * min(2, multi - 1) + 5.0 * _f(row.get("strength"), 0.0))
    return {
        "score": round(score, 2),
        "reason": "OBSERVED_OPTIONS_CONFLUENCE",
        "nearest_level": round(_f(row.get("price")), 10),
        "labels": list(row.get("labels") or [])[:4],
        "distance": round(distance, 10),
        "radius": round(radius, 10),
    }


def score_sl_collision(*, candidate: Mapping[str, Any], context: Mapping[str, Any],
                       entry: float, direction: str, atr: float) -> Dict[str, Any]:
    """Penalize a stop placed *inside* an observed options reaction zone.

    It never proposes a new stop. Existing structural candidates compete as usual.
    """
    price = _f(candidate.get("price"), 0.0)
    if price <= 0:
        return {"score": None, "reason": "INVALID_PRICE"}
    mm = _d(_d(context).get("market_maker_context"))
    reaction = observed_reaction_map(mm, spot=entry, atr=atr)
    if not reaction.get("eligible"):
        return {"score": None, "reason": reaction.get("reason")}
    nearest = _nearest(reaction.get("levels") or [], price)
    if nearest is None:
        return {"score": None, "reason": "NO_OPTIONS_LEVELS"}
    row, distance = nearest
    radius = max(_f(reaction.get("radius"), 0.0), 1e-12)
    if distance > radius:
        # No relation => abstain instead of adding a constant score to all SLs.
        return {"score": None, "reason": "NO_OPTIONS_COLLISION"}
    closeness = 1.0 - min(1.0, distance / radius)
    score = _clip(58.0 - 38.0 * closeness)
    return {
        "score": round(score, 2),
        "reason": "SL_NEAR_OBSERVED_OPTIONS_REACTION",
        "nearest_level": round(_f(row.get("price")), 10),
        "labels": list(row.get("labels") or [])[:4],
        "distance": round(distance, 10),
        "radius": round(radius, 10),
        "direction": str(direction or "").lower(),
    }


def score_tp_barrier(*, candidate: Mapping[str, Any], context: Mapping[str, Any],
                     entry: float, direction: str, atr: float) -> Dict[str, Any]:
    """Rank existing structural TPs relative to the first observed options barrier."""
    target = _f(candidate.get("price"), 0.0)
    entry = _f(entry, 0.0)
    if target <= 0 or entry <= 0:
        return {"score": None, "reason": "INVALID_PRICE"}
    mm = _d(_d(context).get("market_maker_context"))
    reaction = observed_reaction_map(mm, spot=entry, atr=atr)
    if not reaction.get("eligible"):
        return {"score": None, "reason": reaction.get("reason")}
    direction = str(direction or "").lower()
    if direction == "long":
        ahead = sorted([r for r in reaction["levels"] if _f(r.get("price")) > entry], key=lambda r: _f(r.get("price")))
    elif direction == "short":
        ahead = sorted([r for r in reaction["levels"] if _f(r.get("price")) < entry], key=lambda r: _f(r.get("price")), reverse=True)
    else:
        return {"score": None, "reason": "INVALID_DIRECTION"}
    if not ahead:
        return {"score": None, "reason": "NO_OPTIONS_BARRIER_AHEAD"}
    barrier = ahead[0]
    bp = _f(barrier.get("price"), 0.0)
    radius = max(_f(reaction.get("radius"), 0.0), 1e-12)
    if direction == "long":
        safe_side = target <= bp
        gap = bp - target
        beyond = target > bp
    else:
        safe_side = target >= bp
        gap = target - bp
        beyond = target < bp

    if safe_side and 0 <= gap <= radius:
        score = 92.0 - 12.0 * min(1.0, gap / radius)
        reason = "TP_FRONTRUNS_OBSERVED_OPTIONS_BARRIER"
    elif beyond:
        overshoot = abs(target - bp)
        score = _clip(48.0 - 22.0 * min(1.0, overshoot / max(radius * 2.0, 1e-12)))
        reason = "TP_BEYOND_OBSERVED_OPTIONS_BARRIER"
    else:
        # The target is safely before the barrier but not close enough for the
        # barrier to be relevant. Abstain to keep the lens a true tie-breaker.
        return {"score": None, "reason": "OPTIONS_BARRIER_NOT_MATERIAL"}
    return {
        "score": round(score, 2),
        "reason": reason,
        "barrier": round(bp, 10),
        "labels": list(barrier.get("labels") or [])[:4],
        "radius": round(radius, 10),
    }
