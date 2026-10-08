"""Commit 32.1 — graded setup recovery for Futures/Multi candidates.

This module widens *candidate generation only*. It never bypasses Strategy Bank,
official-cell, macro, geometry, specialised Safety, hard risk or validated OOS
publication authority. No symbol-specific parameter tuning is used.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, List

VERSION = "COMMIT32_1_GRADED_SETUP_RECOVERY_V1"


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _score_contract(ev: Mapping[str, Any], spec: Mapping[str, Any]) -> Dict[str, Any]:
    mandatory = list(spec.get("mandatory") or [])
    alternatives = [list(x) for x in (spec.get("alternatives") or [])]
    support = list(spec.get("support") or [])
    mandatory_hits = [k for k in mandatory if bool(ev.get(k))]
    alt_hits: List[str] = []
    alt_ok = True
    for group in alternatives:
        hits = [k for k in group if bool(ev.get(k))]
        if not hits:
            alt_ok = False
        alt_hits.extend(hits)
    support_hits = [k for k in support if bool(ev.get(k))]
    mandatory_ok = len(mandatory_hits) == len(mandatory)
    mtf_conflict = bool(ev.get("mtf_conflict"))
    mtf_opposite = bool(ev.get("mtf_opposite"))
    mtf_mode = str(spec.get("mtf_mode") or "STRICT").upper()
    min_support = int(spec.get("min_support") or 0)
    if mtf_mode == "STRICT":
        mtf_ok = not mtf_conflict and not mtf_opposite
    elif mtf_mode == "CONTEXT":
        # Early impulse/reversal may lead the higher timeframe. Conflict is
        # permitted only with one extra independent support role.
        mtf_ok = len(support_hits) >= min_support + (1 if (mtf_conflict or mtf_opposite) else 0)
    else:
        mtf_ok = True
    passed = mandatory_ok and alt_ok and len(support_hits) >= min_support and mtf_ok
    # Broad monotonic evidence score; no asset/TF calibration. This is a
    # pre-candidate score only, never a probability or final Safety score.
    quality = 70.0 + 4.0 * len(mandatory_hits) + 3.0 * len(set(alt_hits)) + 2.0 * len(support_hits)
    if bool(ev.get("mtf")):
        quality += 2.0
    if float(ev.get("volume_ratio") or 0.0) >= 1.2:
        quality += 2.0
    if mtf_conflict or mtf_opposite:
        quality -= 2.0
    quality = max(0.0, min(92.0, quality))
    return {
        "setup": spec["setup"],
        "preferred_family": spec["preferred_family"],
        "passed": bool(passed),
        "quality": round(quality, 2),
        "mandatory": mandatory,
        "mandatory_hits": mandatory_hits,
        "alternative_groups": alternatives,
        "alternative_hits": list(dict.fromkeys(alt_hits)),
        "support_pool": support,
        "support_hits": support_hits,
        "mtf_mode": mtf_mode,
        "mtf_conflict": mtf_conflict,
        "mtf_opposite": mtf_opposite,
        "anti_overfit": "ROLE_BASED_NO_SYMBOL_OR_TF_OPTIMIZATION",
    }


_SPECS = (
    {
        "setup": "DIRECTIONAL_IMPULSE_CONTINUATION",
        "preferred_family": "BREAKOUT_RETEST",
        "mandatory": ("dmi_impulse",),
        "alternatives": (("direction_anchor", "momentum"),),
        "support": ("structure", "volume", "displacement", "breakout", "mtf"),
        "min_support": 1,
        "mtf_mode": "CONTEXT",
    },
    {
        "setup": "SWEEP_REVERSAL",
        "preferred_family": "SWEEP_REVERSAL",
        "mandatory": ("sweep",),
        "alternatives": (("mss", "structure"),),
        "support": ("momentum", "poi", "volume", "displacement", "mtf"),
        "min_support": 2,
        "mtf_mode": "CONTEXT",
    },
    {
        "setup": "TREND_PULLBACK",
        "preferred_family": "TREND_PULLBACK",
        "mandatory": ("trend", "pullback", "mtf"),
        "alternatives": (),
        "support": ("momentum", "volume", "poi", "structure"),
        "min_support": 1,
        "mtf_mode": "STRICT",
    },
    {
        "setup": "BREAKOUT_RETEST",
        "preferred_family": "BREAKOUT_RETEST",
        "mandatory": ("breakout_retest",),
        "alternatives": (("structure", "direction_anchor"),),
        "support": ("displacement", "volume", "momentum", "mtf"),
        "min_support": 1,
        "mtf_mode": "STRICT",
    },
    {
        "setup": "COMPRESSION_EXPANSION",
        "preferred_family": "BOLLINGER_SQUEEZE",
        "mandatory": ("squeeze", "expansion"),
        "alternatives": (("direction_anchor", "momentum"),),
        "support": ("volume", "structure", "displacement", "mtf"),
        "min_support": 2,
        "mtf_mode": "CONTEXT",
    },
    {
        "setup": "RANGE_MEAN_REVERSION",
        "preferred_family": "MEAN_REVERSION",
        "mandatory": ("range", "extreme", "mean_reversion_location"),
        "alternatives": (("momentum", "structure"),),
        "support": ("volume", "poi", "mtf"),
        "min_support": 0,
        "mtf_mode": "CONTEXT",
    },
)


def evaluate_side(impl: Any, *, layers: Mapping[str, Any], operational: Mapping[str, Any], direction: str) -> Dict[str, Any]:
    ev = impl._live_evidence(layers, operational, direction)
    rows = [_score_contract(ev, s) for s in _SPECS]
    eligible = [r for r in rows if r["passed"]]
    eligible.sort(key=lambda r: (float(r["quality"]), len(r["support_hits"])), reverse=True)
    return {"direction": direction, "evidence": ev, "contracts": rows, "best": eligible[0] if eligible else None}


def recover_candidate(impl: Any, operational: Mapping[str, Any], *, layers: Mapping[str, Any], symbol: str, timeframe: str, system_type: str) -> Dict[str, Any]:
    op = deepcopy(dict(operational or {}))
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    if market != "FUTURES" or bool(op.get("candidate_ready")):
        return op
    is_multi = bool(impl._is_multiasset(symbol))
    long_side = evaluate_side(impl, layers=layers, operational=op, direction="BULLISH")
    short_side = evaluate_side(impl, layers=layers, operational=op, direction="BEARISH")
    candidates = []
    if long_side.get("best"):
        candidates.append(dict(long_side["best"], direction="BULLISH"))
    if short_side.get("best"):
        candidates.append(dict(short_side["best"], direction="BEARISH"))
    candidates.sort(key=lambda r: float(r.get("quality") or 0.0), reverse=True)
    diag = {"version": VERSION, "long": long_side, "short": short_side, "candidate_count": len(candidates)}
    op["commit32_1_graded_setup_diagnostic"] = diag
    if not candidates:
        op["commit32_1_recovery_rejected_reason"] = "NO_GRADED_SETUP"
        return op
    if len(candidates) > 1 and float(candidates[0]["quality"]) - float(candidates[1]["quality"]) < 5.0:
        op["commit32_1_recovery_rejected_reason"] = "DIRECTION_AMBIGUOUS"
        return op
    winner = candidates[0]
    quality = float(winner.get("quality") or 0.0)
    # Risk class controls execution tempo/size downstream, not whether a sound
    # technical hypothesis is allowed to reach Geometry. Multi keeps a slightly
    # higher pre-candidate evidence floor because cross-asset semantics vary.
    candidate_floor = 84.0 if is_multi else 82.0
    if quality < candidate_floor:
        op["commit32_1_recovery_rejected_reason"] = "GRADED_QUALITY_BELOW_CANDIDATE_FLOOR"
        return op
    direction = winner["direction"]
    action = impl._action(direction, market)
    official = bool(impl._official_cell(market, symbol, timeframe, action, fallback=bool(op.get("official_cell"))))
    if not official:
        op["commit32_1_recovery_rejected_reason"] = "UNOFFICIAL_CELL"
        return op
    base_thesis = dict(op.get("thesis") or {})
    macro = layers.get("macro_context") or {}
    macro_risk = _u(base_thesis.get("macro_risk") or macro.get("risk_level") or macro.get("risk"))
    if macro_risk == "CRITICAL":
        op["commit32_1_recovery_rejected_reason"] = "MACRO_CRITICAL"
        return op
    strategy = impl._select_default_strategy(
        op, layers=layers, symbol=symbol, timeframe=timeframe, market=market,
        action=action, preferred_family=str(winner.get("preferred_family") or ""), is_multi=is_multi,
    )
    strategy_quality = float(strategy.get("quality") or 0.0)
    if not (strategy_quality >= 78.0 and strategy.get("regime_match", True) and strategy.get("volatility_match", True)):
        op["commit32_1_recovery_strategy"] = strategy
        op["commit32_1_recovery_rejected_reason"] = "STRATEGY_BANK_QUALITY_NOT_READY"
        return op
    evidence = long_side["evidence"] if direction == "BULLISH" else short_side["evidence"]
    thesis = dict(base_thesis)
    thesis.update({
        "base_direction_before_commit32_1": base_thesis.get("direction"),
        "base_action_before_commit32_1": base_thesis.get("action"),
        "direction": direction,
        "action": action,
        "quality": round(quality, 2),
        "independent_support_families": list(dict.fromkeys(
            list(winner.get("mandatory_hits") or []) + list(winner.get("alternative_hits") or []) + list(winner.get("support_hits") or [])
        )),
        "commit32_1_graded_contract": {
            "setup": winner.get("setup"),
            "preferred_family": winner.get("preferred_family"),
            "quality": round(quality, 2),
            "candidate_floor": candidate_floor,
            "mtf_mode": winner.get("mtf_mode"),
            "mandatory_hits": list(winner.get("mandatory_hits") or []),
            "alternative_hits": list(winner.get("alternative_hits") or []),
            "support_hits": list(winner.get("support_hits") or []),
            "evidence_snapshot": {k: evidence.get(k) for k in ("adx", "rsi", "volume_ratio", "trend_direction", "structure_direction", "mtf_direction")},
            "anti_overfit": "ROLE_BASED_NO_SYMBOL_OR_TF_OPTIMIZATION",
        },
    })
    op["thesis"] = thesis
    op["default_strategy"] = strategy
    op["candidate_source"] = "COMMIT32_1_GRADED_SETUP+STRATEGY"
    op["candidate_action"] = action
    op["candidate_ready"] = True
    op["official_cell"] = True
    op["selected_specialist_source"] = "COMMIT32_1_GRADED_SETUP"
    op["commit32_1_candidate_recovered"] = True
    op["commit32_1_setup_family"] = winner.get("setup")
    op["commit32_1_candidate_quality"] = round(quality, 2)
    op["commit32_1_strategy_quality"] = round(strategy_quality, 2)
    op["never_bypass_safety"] = True
    op["requires_validated_live_route"] = True
    op["no_signal_quota"] = True
    return op
