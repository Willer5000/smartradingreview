"""Commit 21 — Nine-Quality Engine + independent Q10 safety contract.

Q1..Q9 evaluate *quality of an already selected directional thesis and its
execution package*. They do not create direction, change Entry/SL/TP, add
market-data requests, or replace the production safety gate.

Q10 is the existing operational safety/publication contract: Safety 75, TP 55,
SL 60, R/R 1.8..3.5, loss-at-SL and ATR-stress rules. Q10 remains authoritative
and independent from the nine quality dimensions.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Iterable

VERSION = "COMMIT21_9Q_ENGINE_V1"
MODEL = "Q1-Q9_QUALITY_PLUS_Q10_SAFETY"

# These are inherited from the established CPQE research contract. They are not
# fitted on live outcomes in Commit 21.
MIN_COMPOSITE = 76.0
MIN_STRUCTURAL_FLOOR = 64.0
MIN_EXECUTION_Q6_Q7 = 70.0
MIN_Q9_EVIDENCE = 55.0

# Q10 = unchanged production safety/economic publication contract.
Q10_MIN_SAFETY = 75.0
Q10_MIN_TP = 55.0
Q10_MIN_SL = 60.0
Q10_MIN_RR = 1.8
Q10_MAX_RR = 3.5

Q_WEIGHTS = {
    "Q1": 0.13,  # thesis/directional coherence
    "Q2": 0.14,  # structure / smart money
    "Q3": 0.11,  # multi-timeframe
    "Q4": 0.14,  # strategy/family fit
    "Q5": 0.10,  # flow / derivatives / market context
    "Q6": 0.12,  # entry quality + reachability
    "Q7": 0.12,  # exit/economic geometry
    "Q8": 0.07,  # regime / timing / volatility / macro
    "Q9": 0.07,  # statistical / evidence authority
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _dir(value: Any) -> str:
    s = _u(value)
    if s in {"LONG", "BUY", "BULLISH", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if s in {"SHORT", "SELL", "BEARISH", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "none", "null", "off"}


def _blob(*items: Any) -> str:
    return " ".join(str(x or "") for x in items if x is not None).upper()


def _count_direction_support(levels: Mapping[str, Any], direction: str) -> int:
    """Read already-computed vote/worker summaries without creating votes."""
    candidates = (
        levels.get("directional_support"),
        levels.get("worker_consensus"),
        levels.get("trader_votes"),
        levels.get("vote_breakdown"),
        levels.get("committee_votes"),
        levels.get("supporting_traders"),
    )
    target = "LONG" if direction == "BULLISH" else "SHORT" if direction == "BEARISH" else ""
    for obj in candidates:
        if isinstance(obj, Mapping):
            for key in (target, direction, "support", "count", "votes"):
                val = obj.get(key)
                if isinstance(val, (int, float)):
                    return max(0, int(val))
    return 0


def _family_from_context(levels: Mapping[str, Any]) -> str:
    for key in (
        "strategy_family", "setup_family", "ppe_selected_route", "validated_strategy_route",
        "research_strategy_family", "execution_family", "premium_route", "selected_strategy",
    ):
        value = levels.get(key)
        if isinstance(value, Mapping):
            value = value.get("family") or value.get("setup_family") or value.get("name") or value.get("route")
        if value:
            return _u(value)
    for key in ("contingency_playbook", "operational_intelligence", "strategy", "selected_strategy"):
        block = levels.get(key)
        if isinstance(block, Mapping):
            value = block.get("family") or block.get("setup_family") or block.get("execution_family") or block.get("route")
            if value:
                return _u(value)
    return "UNKNOWN"


def _unique_tf_count(levels: Mapping[str, Any], timeframe: str) -> int:
    seen = set()
    blocks = (
        levels.get("mtf_alignment"), levels.get("multi_timeframe"), levels.get("multiframe_context"),
        levels.get("mtf_context"), levels.get("mtf"),
    )
    for block in blocks:
        if isinstance(block, Mapping):
            rows = block.get("timeframes") or block.get("snapshots") or block.get("roles")
            if isinstance(rows, Mapping):
                seen.update(str(k).upper() for k in rows.keys())
            elif isinstance(rows, Iterable) and not isinstance(rows, (str, bytes, Mapping)):
                for row in rows:
                    if isinstance(row, Mapping):
                        if row.get("timeframe"):
                            seen.add(_u(row.get("timeframe")))
                    elif row:
                        seen.add(_u(row))
    seen.add(_u(timeframe))
    return len({x for x in seen if x})


def _evidence_state(levels: Mapping[str, Any]) -> str:
    blocks = (
        levels.get("commit19_champion"), levels.get("validated_strategy_route"),
        levels.get("research_evidence"), levels.get("champion"), levels.get("strategy_evidence"),
        levels.get("research_prior"),
    )
    raw = _blob(*blocks)
    for state in ("RETIRED_ALPHA_DECAY", "RETIRED", "LIVE_CHAMPION", "CHAMPION", "OOS_VALIDATED", "SHADOW", "RESEARCH", "GAP"):
        if state in raw:
            return state
    return "GAP"


def evaluate(
    levels: Mapping[str, Any],
    trend: Mapping[str, Any] | None,
    momentum: Mapping[str, Any] | None,
    volatility: Mapping[str, Any] | None,
    structure: Mapping[str, Any] | None,
    timeframe: str,
    symbol: str,
    action: str,
) -> Dict[str, Any]:
    l = dict(levels or {})
    t = dict(trend or {})
    m = dict(momentum or {})
    v = dict(volatility or {})
    s = dict(structure or {})

    direction = _dir(action or l.get("action") or l.get("direction"))
    trend_dir = _dir(t.get("direction"))
    momentum_dir = _dir(m.get("direction"))
    structure_dir = _dir(s.get("direction") or s.get("structure_direction"))
    family = _family_from_context(l)

    # ----------------------------- Q1 ---------------------------------
    support = _count_direction_support(l, direction)
    agreements = sum(x == direction and direction != "NEUTRAL" for x in (trend_dir, momentum_dir, structure_dir))
    contradictions = sum(x not in {direction, "NEUTRAL"} and direction != "NEUTRAL" for x in (trend_dir, momentum_dir, structure_dir))
    q1 = 58.0 + agreements * 10.0 + min(18.0, support * 2.5) - contradictions * 12.0
    q1 += 8.0 if l.get("directional_thesis") or l.get("thesis") else 0.0

    # ----------------------------- Q2 ---------------------------------
    sweep = _truth(s.get("liquidity_sweep") or s.get("liquidity_sweeps") or s.get("sweep") or l.get("entry_sweep_confirmed"))
    mss = _truth(s.get("mss") or s.get("bos") or s.get("market_structure_shift") or l.get("entry_mss_bos_confirmed"))
    displacement = _truth(s.get("displacement") or s.get("displacement_confirmed") or l.get("entry_displacement_confirmed"))
    poi = _truth(s.get("order_blocks") or s.get("fair_value_gaps") or s.get("fvg") or l.get("entry_source") or l.get("entry_poi_confirmed"))
    invalidation = _truth(s.get("structural_invalidation") or l.get("sl_anchor") or l.get("invalidation_level"))
    q2 = 46.0 + (13 if sweep else 0) + (13 if mss else 0) + (10 if displacement else 0) + (10 if poi else 0) + (6 if invalidation else 0)
    if structure_dir == direction and direction != "NEUTRAL":
        q2 += 8
    elif structure_dir not in {direction, "NEUTRAL"} and direction != "NEUTRAL":
        q2 -= 12

    # ----------------------------- Q3 ---------------------------------
    mtf_block = l.get("multi_timeframe") or l.get("multiframe_context") or l.get("mtf_context") or l.get("mtf_alignment") or {}
    mtf_blob = _blob(mtf_block)
    unique_tf = _unique_tf_count(l, timeframe)
    aligned_hint = _truth(l.get("mtf_aligned") or l.get("mtf_alignment") in {"ALIGNED", "SUPPORTIVE"})
    conflict_hint = "CONFLICT" in mtf_blob or "OPPOSE" in mtf_blob or "CONTRADICT" in mtf_blob
    q3 = 56.0 + min(18.0, max(0, unique_tf - 1) * 5.0) + (18.0 if aligned_hint else 0.0) - (20.0 if conflict_hint else 0.0)
    if trend_dir == structure_dir == direction and direction != "NEUTRAL":
        q3 += 8.0

    # ----------------------------- Q4 ---------------------------------
    regime = _u(l.get("regime") or l.get("market_regime") or t.get("regime"))
    vol_state = _u(v.get("state") or v.get("volatility_state") or l.get("volatility_state"))
    primary_route = not bool(l.get("manual_geometry_fallback") or l.get("opportunity_recovery_applied") or l.get("manual_geometry_authority"))
    family_upper = family
    family_tf_ok = True
    family_regime_ok = True
    # Known family compatibility from the existing Strategy Bank / PPE universe.
    if "MEAN_REVERSION" in family_upper and regime not in {"RANGING", "BALANCE", "RANGE", "TRANSITION", "UNKNOWN"}:
        family_regime_ok = False
    if "TREND_PULLBACK" in family_upper and regime in {"RANGING", "RANGE", "BALANCE"}:
        family_regime_ok = False
    if "BREAKOUT" in family_upper and vol_state in {"LOW", "QUIET"} and not _truth(v.get("squeeze_on")):
        family_regime_ok = False
    if "30M" in family_upper and timeframe not in {"30m", "1h"}:
        family_tf_ok = False
    q4 = 58.0 + (15 if primary_route else -15) + (12 if family_regime_ok else -16) + (10 if family_tf_ok else -12)
    if l.get("validated_strategy_route") or l.get("strategy_route_id") or l.get("setup_family"):
        q4 += 7.0

    # ----------------------------- Q5 ---------------------------------
    flow_blob = _blob(
        l.get("volume"), l.get("open_interest"), l.get("funding"), l.get("order_book"),
        l.get("liquidation"), l.get("liquidation_map"), l.get("whale"), l.get("greeks"),
        l.get("sentiment"), l.get("correlation"), l.get("flow"), l.get("market_microstructure"),
    )
    flow_hits = sum(flow_blob.count(token) for token in ("VOLUME", "OPEN_INTEREST", "FUNDING", "LIQUID", "WHALE", "GREEK", "SENTIMENT", "CORRELATION", "ORDER BOOK"))
    q5 = 56.0 + min(30.0, flow_hits * 4.0)
    if "CONFLICT" in flow_blob or "OPPOSE" in flow_blob:
        q5 -= 10.0
    if not flow_blob:
        q5 = 56.0  # missing context is neutral, never an invented negative

    # ----------------------------- Q6 ---------------------------------
    entry = _f(l.get("entry_score") or l.get("entry_quality_score"), 0.0)
    reach = _f(l.get("entry_reachability") or l.get("entry_reachability_score") or l.get("reachability_score"), 0.0)
    if reach <= 1.0 and reach > 0:
        reach *= 100.0
    distance_atr = _f(l.get("entry_distance_atr") or l.get("distance_to_entry_atr"), 0.0)
    q6 = 0.40 * _clip(entry) + 0.35 * _clip(reach or entry) + 0.25 * 70.0
    if distance_atr > 0:
        q6 += 8.0 if distance_atr <= 1.0 else 3.0 if distance_atr <= 2.0 else -8.0
    if poi and sweep:
        q6 += 6.0

    # ----------------------------- Q7 ---------------------------------
    sl = _f(l.get("sl_reliability"), 0.0)
    if sl <= 1.0:
        sl *= 100.0
    tp = _f(l.get("tp_quality_score"), 0.0)
    rr = _f(l.get("risk_reward"), 0.0)
    rr_score = 35.0 if rr <= 0 else 58.0 if rr < 1.8 else 78.0 if rr < 2.0 else 90.0 if rr <= 3.0 else 78.0 if rr <= 3.5 else 42.0
    q7 = 0.38 * _clip(sl) + 0.38 * _clip(tp) + 0.24 * rr_score
    if _truth(l.get("tp_before_reaction_zone")):
        q7 += 6.0

    # ----------------------------- Q8 ---------------------------------
    atr = _f(v.get("atr_pct") or l.get("atr_pct"), 0.0)
    session = _u(l.get("market_session") or l.get("session") or v.get("session"))
    macro = _u(l.get("macro_bias") or l.get("macro_context") or l.get("macro"))
    q8 = 62.0
    if vol_state in {"NORMAL", "EXPANSION", "HIGH", "COMPRESSION"}:
        q8 += 10.0
    elif vol_state in {"SHOCK", "CRASH", "EXTREME"}:
        q8 -= 8.0
    if session and session not in {"UNKNOWN", "NONE"}:
        q8 += 8.0
    if macro:
        q8 += 5.0
    if 0.6 <= atr <= 6.0:
        q8 += 8.0
    elif atr > 10.0:
        q8 -= 10.0

    # ----------------------------- Q9 ---------------------------------
    state = _evidence_state(l)
    q9_map = {
        "LIVE_CHAMPION": 92.0,
        "CHAMPION": 88.0,
        "OOS_VALIDATED": 84.0,
        "SHADOW": 72.0,
        "RESEARCH": 62.0,
        "GAP": 55.0,
        "RETIRED": 25.0,
        "RETIRED_ALPHA_DECAY": 15.0,
    }
    q9 = q9_map.get(state, 55.0)
    # Exact strategy evidence can improve the score only when supplied by the
    # existing data contract; no cross-symbol inheritance is created here.
    evidence = l.get("validated_strategy_route") or l.get("research_evidence") or l.get("commit19_champion") or {}
    if isinstance(evidence, Mapping):
        exact = _truth(evidence.get("exact_cell") or evidence.get("cell_exact") or evidence.get("symbol_exact"))
        if exact:
            q9 += 5.0
        pf = _f((evidence.get("oos") or {}).get("pf") if isinstance(evidence.get("oos"), Mapping) else evidence.get("oos_pf"), 0.0)
        if pf >= 1.15:
            q9 += 4.0
    q9 = _clip(q9)

    q = {
        "Q1": round(_clip(q1), 2), "Q2": round(_clip(q2), 2), "Q3": round(_clip(q3), 2),
        "Q4": round(_clip(q4), 2), "Q5": round(_clip(q5), 2), "Q6": round(_clip(q6), 2),
        "Q7": round(_clip(q7), 2), "Q8": round(_clip(q8), 2), "Q9": round(_clip(q9), 2),
    }
    composite = sum(q[k] * Q_WEIGHTS[k] for k in Q_WEIGHTS)
    structural_floor = min(q[k] for k in ("Q1", "Q2", "Q3", "Q4"))
    execution_floor = min(q["Q6"], q["Q7"])
    q9_ok = q["Q9"] >= MIN_Q9_EVIDENCE and state not in {"RETIRED", "RETIRED_ALPHA_DECAY"}
    quality_ready = bool(
        direction in {"BULLISH", "BEARISH"}
        and composite >= MIN_COMPOSITE
        and structural_floor >= MIN_STRUCTURAL_FLOOR
        and execution_floor >= MIN_EXECUTION_Q6_Q7
        and q9_ok
    )
    return {
        "version": VERSION,
        "model": MODEL,
        "quality": q,
        "composite": round(composite, 2),
        "structural_floor": round(structural_floor, 2),
        "execution_floor": round(execution_floor, 2),
        "quality_ready": quality_ready,
        "route_family": family,
        "evidence_state": state,
        "direction": direction,
        "diagnostics": {
            "agreements": agreements,
            "contradictions": contradictions,
            "unique_timeframes": unique_tf,
            "support_count": support,
            "primary_geometry": primary_route,
            "family_regime_fit": family_regime_ok,
            "family_timeframe_fit": family_tf_ok,
        },
        "policy": {
            "creates_direction": False,
            "changes_entry": False,
            "changes_sl": False,
            "changes_tp": False,
            "uses_live_outcomes_for_fitting": False,
            "adds_network_calls": False,
            "changes_q10_safety": False,
        },
    }


def q10_safety_snapshot(result: Mapping[str, Any], levels: Mapping[str, Any]) -> Dict[str, Any]:
    gate = dict(result.get("futures_publication_gate") or {})
    safety = _f((result.get("levels") or {}).get("execution_safety"), _f(levels.get("execution_safety"), 0.0))
    rr = _f((result.get("levels") or {}).get("risk_reward"), _f(levels.get("risk_reward"), 0.0))
    tp = _f((result.get("levels") or {}).get("tp_quality_score"), _f(levels.get("tp_quality_score"), 0.0))
    sl = _f((result.get("levels") or {}).get("sl_reliability"), _f(levels.get("sl_reliability"), 0.0))
    if sl <= 1.0:
        sl *= 100.0
    reasons = [str(x).upper() for x in (gate.get("reason_codes") or [])]
    return {
        "execution_safety": round(safety, 2),
        "tp_quality": round(tp, 2),
        "sl_quality": round(sl, 2),
        "risk_reward": round(rr, 3),
        "hard_gate_eligible": bool(gate.get("eligible")),
        "hard_reason_codes": reasons,
        "thresholds": {
            "safety": Q10_MIN_SAFETY,
            "tp": Q10_MIN_TP,
            "sl": Q10_MIN_SL,
            "rr_min": Q10_MIN_RR,
            "rr_max": Q10_MAX_RR,
        },
    }


def route_score(quality: Mapping[str, Any], geometry_score: float) -> float:
    """Use 9Q to choose among already-valid route geometries."""
    composite = _f(quality.get("composite"), 0.0)
    q = quality.get("quality") or {}
    q7 = _f(q.get("Q7"), 0.0)
    # Keep geometry relevant, but let context/family quality break ties that the
    # old geometry-only comparator could not distinguish.
    score = 0.72 * composite + 0.18 * q7 + 0.10 * _clip(geometry_score)
    return round(score, 3)
