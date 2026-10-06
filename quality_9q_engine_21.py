"""Commit 23 — Parallel ten-filter quality authority + context groups.

Q1..Q9 evaluate *quality of an already selected directional thesis and its
execution package*. They do not create direction, change Entry/SL/TP, add
market-data requests, or replace the production safety gate.

Commit 25 keeps the ten parallel filters as diagnostics only. Publication
authority remains the native economic/safety contract. The parallel scores help
explain quality but cannot bypass Safety, Entry/SL/TP quality or R/R. No filter
creates direction or changes Entry/SL/TP.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Iterable

VERSION = "COMMIT23_10Q_ENGINE_V4_PARALLEL_AUTHORITY"
MODEL = "COMMIT27_CONTEXTUAL_Q1_Q9_WITH_PARALLEL_DIAGNOSTICS"

# These are inherited from the established CPQE research contract. They are not
# fitted on live outcomes in Commit 21.
MIN_COMPOSITE = 76.0
MIN_STRUCTURAL_FLOOR = 64.0
MIN_EXECUTION_Q6_Q7 = 70.0
MIN_Q9_EVIDENCE = 55.0
MIN_DEEP_QUALITY_SAFETY_UPGRADE = 76.0
MAX_GROUPS = 2
MAX_BONUS = 5.0
MAX_GROUP_BONUS = 5.0
CONTEXT_GROUPS_VERSION = "COMMIT22_CONTEXT_QUALITY_GROUPS_V1"
PARALLEL_FILTERS_VERSION = "COMMIT23_TEN_FILTER_PARALLEL_AUTHORITY_V1"
PARALLEL_FILTER_MIN_SCORE = 75.0
PARALLEL_OPERATIONAL_SAFETY_FLOOR = 65.0
PARALLEL_MAX_SL_LOSS_PCT = 8.0
PARALLEL_MAX_ATR_STRESS_PCT = 25.0

# Commit 22 — context groups never lower the global quality contract. They only
# provide a bounded quality contribution when an existing context is strong.
MIN_CONTEXT_GROUP_BASE_COMPOSITE = 70.0
MIN_CONTEXT_GROUP_ADJUSTED_COMPOSITE = 76.0
MAX_CONTEXT_GROUP_BONUS = 5.0

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


# ---------------------------------------------------------------------------
# COMMIT 22 — CONTEXT QUALITY GROUPS
# ---------------------------------------------------------------------------
# Each group is an evidence-conditioned quality lens over the existing Q1..Q9.
# It never creates direction and never touches Entry/SL/TP or Q10 thresholds.
_GROUP_PROFILES = {
    "FAST_STABLE_CONTINUATION": {"Q1": .14, "Q2": .08, "Q3": .12, "Q4": .10, "Q5": .07, "Q6": .17, "Q7": .17, "Q8": .10, "Q9": .05},
    "RANGE_REVERSION_SELECTIVE": {"Q1": .11, "Q2": .07, "Q3": .10, "Q4": .15, "Q5": .07, "Q6": .18, "Q7": .18, "Q8": .09, "Q9": .05},
    "SWEEP_MSS_RECLAIM": {"Q1": .13, "Q2": .18, "Q3": .12, "Q4": .11, "Q5": .07, "Q6": .15, "Q7": .14, "Q8": .05, "Q9": .05},
    "COMPRESSION_EXPANSION_RETEST": {"Q1": .12, "Q2": .10, "Q3": .10, "Q4": .12, "Q5": .12, "Q6": .14, "Q7": .14, "Q8": .11, "Q9": .05},
    "VOLATILITY_PULLBACK": {"Q1": .13, "Q2": .12, "Q3": .12, "Q4": .09, "Q5": .07, "Q6": .15, "Q7": .17, "Q8": .10, "Q9": .05},
    "MULTIASSET_SESSION_EXECUTION": {"Q1": .11, "Q2": .08, "Q3": .15, "Q4": .11, "Q5": .12, "Q6": .14, "Q7": .14, "Q8": .10, "Q9": .05},
}


def _profile(group: str) -> Dict[str, float]:
    return dict(_GROUP_PROFILES.get(group) or {})

def _group_direction(value: Any) -> str:
    s = _u(value)
    if s in {"LONG", "BUY", "BULLISH", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if s in {"SHORT", "SELL", "BEARISH", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _alignment(direction: str, trend: Mapping[str, Any], momentum: Mapping[str, Any], structure: Mapping[str, Any]) -> int:
    if direction == "NEUTRAL":
        return 0
    values = (
        _group_direction(trend.get("direction")),
        _group_direction(momentum.get("direction")),
        _group_direction(structure.get("direction") or structure.get("structure_direction")),
    )
    return sum(v == direction for v in values)


def _contradiction_count(direction: str, trend, momentum, structure) -> int:
    if direction == "NEUTRAL":
        return 0
    values = (
        _group_direction(trend.get("direction")),
        _group_direction(momentum.get("direction")),
        _group_direction(structure.get("direction") or structure.get("structure_direction")),
    )
    return sum(v not in {direction, "NEUTRAL"} for v in values)


def _regime(levels: Mapping[str, Any], trend: Mapping[str, Any]) -> str:
    return _u(levels.get("regime") or levels.get("market_regime") or trend.get("regime"))


def _vol_state(levels: Mapping[str, Any], volatility: Mapping[str, Any]) -> str:
    return _u(
        volatility.get("state")
        or volatility.get("volatility_state")
        or levels.get("volatility_state")
        or levels.get("volatility_regime")
    )


def _has_sweep_mss_poi(levels, structure) -> tuple[bool, bool, bool]:
    sweep = _truth(
        structure.get("liquidity_sweep")
        or structure.get("liquidity_sweeps")
        or structure.get("sweep")
        or levels.get("entry_sweep_confirmed")
    )
    mss = _truth(
        structure.get("mss")
        or structure.get("bos")
        or structure.get("market_structure_shift")
        or levels.get("entry_mss_bos_confirmed")
    )
    poi = _truth(
        structure.get("order_blocks")
        or structure.get("fair_value_gaps")
        or structure.get("fvg")
        or structure.get("entry_source")
        or structure.get("entry_poi_confirmed")
        or levels.get("entry_poi_confirmed")
    )
    return sweep, mss, poi


def evaluate_context_quality_groups(
    levels: Mapping[str, Any] | None,
    trend: Mapping[str, Any] | None,
    momentum: Mapping[str, Any] | None,
    volatility: Mapping[str, Any] | None,
    structure: Mapping[str, Any] | None,
    timeframe: str,
    symbol: str,
    action: str,
    market_type: str = "futures",
) -> Dict[str, Any]:
    """Score only context compatibility of an existing directional thesis.

    Each group is evidence-driven. A group must have a clean directional context
    and a minimum amount of explicit evidence before it can contribute any
    bonus. This is deliberately independent from the Q10 hard economic gate.
    """
    l = dict(levels or {})
    t = dict(trend or {})
    m = dict(momentum or {})
    v = dict(volatility or {})
    s = dict(structure or {})

    direction = _group_direction(action or l.get("action") or l.get("direction"))
    tf = str(timeframe or "").strip()
    adx = _f(t.get("adx") or l.get("adx"), 0.0)
    atr_pct = _f(v.get("atr_pct") or l.get("atr_pct"), 0.0)
    rsi = _f(m.get("rsi") or l.get("rsi"), 50.0)
    volume_ratio = _f(
        l.get("volume_ratio")
        or l.get("relative_volume")
        or v.get("volume_ratio")
        or v.get("relative_volume")
        or l.get("volume_multiple"),
        0.0,
    )
    distance_atr = _f(l.get("entry_distance_atr") or l.get("distance_to_entry_atr"), 0.0)
    reachability = _f(l.get("entry_reachability") or l.get("entry_reachability_score") or l.get("reachability_score"), 0.0)
    if 0 < reachability <= 1.0:
        reachability *= 100.0
    regime = _regime(l, t)
    vol_state = _vol_state(l, v)
    session = _u(l.get("market_session") or l.get("session") or v.get("session"))
    alignment = _alignment(direction, t, m, s)
    contradictions = _contradiction_count(direction, t, m, s)
    sweep, mss, poi = _has_sweep_mss_poi(l, s)
    structure_blob = _blob(s, l)
    vol_blob = _blob(v, l)
    family_blob = _blob(l.get("strategy_family"), l.get("setup_family"), l.get("execution_family"), l.get("ppe_selected_route"))

    groups = []

    # 1) FAST_STABLE_CONTINUATION
    evidence = []
    if tf in {"30m", "1h"}:
        evidence.append("FAST_TF")
    if adx >= 25:
        evidence.append("ADX_TREND")
    if alignment >= 2:
        evidence.append("DIRECTIONAL_ALIGNMENT")
    if vol_state in {"LOW", "NORMAL", "COMPRESSION", "QUIET"} or (0 < atr_pct < 2.5):
        evidence.append("STABLE_VOLATILITY")
    if (distance_atr and distance_atr <= 2.0) or reachability >= 70:
        evidence.append("REACHABLE_ENTRY")
    if contradictions == 0:
        evidence.append("NO_CONTRADICTION")
    ready = tf in {"30m", "1h"} and adx >= 25 and alignment >= 2 and contradictions == 0 and len(evidence) >= 4
    if ready:
        groups.append({"group": "FAST_STABLE_CONTINUATION", "weights": _profile("FAST_STABLE_CONTINUATION"), "score": 94.0, "bonus": 4.0, "evidence": evidence[:6]})

    # 2) RANGE_REVERSION_SELECTIVE
    evidence = []
    if tf in {"30m", "1h"}:
        evidence.append("FAST_TF")
    if adx and adx < 20:
        evidence.append("RANGE_ADX")
    if regime in {"RANGING", "RANGE", "BALANCE", "TRANSITION"}:
        evidence.append("RANGE_REGIME")
    if (direction == "BULLISH" and rsi <= 35) or (direction == "BEARISH" and rsi >= 65):
        evidence.append("MOMENTUM_EXTREME")
    if contradictions == 0:
        evidence.append("NO_CONTRADICTION")
    if "MEAN_REVERSION" in family_blob or "RANGE" in structure_blob:
        evidence.append("FAMILY_OR_STRUCTURE_FIT")
    ready = tf in {"30m", "1h"} and adx and adx < 20 and len(evidence) >= 4
    if ready:
        groups.append({"group": "RANGE_REVERSION_SELECTIVE", "weights": _profile("RANGE_REVERSION_SELECTIVE"), "score": 92.0, "bonus": 3.5, "evidence": evidence[:6]})

    # 3) SWEEP_MSS_RECLAIM
    evidence = []
    if sweep:
        evidence.append("LIQUIDITY_SWEEP")
    if mss:
        evidence.append("MSS_BOS")
    if poi:
        evidence.append("POI")
    if alignment >= 1:
        evidence.append("DIRECTIONAL_SUPPORT")
    if contradictions == 0:
        evidence.append("NO_CONTRADICTION")
    if tf in {"30m", "1h", "2h", "4h"}:
        evidence.append("EXECUTION_TF")
    ready = sweep and mss and poi and contradictions == 0 and len(evidence) >= 4
    if ready:
        groups.append({"group": "SWEEP_MSS_RECLAIM", "weights": _profile("SWEEP_MSS_RECLAIM"), "score": 96.0, "bonus": 4.0, "evidence": evidence[:6]})

    # 4) COMPRESSION_EXPANSION_RETEST
    evidence = []
    if any(token in vol_blob for token in ("SQUEEZE", "COMPRESSION", "EXPANSION")):
        evidence.append("COMPRESSION_SIGNAL")
    if _truth(v.get("squeeze_on") or l.get("squeeze_on") or s.get("compression")):
        evidence.append("SQUEEZE_STATE")
    if volume_ratio >= 0.9:
        evidence.append("VOLUME_CONFIRMED")
    if _truth(s.get("displacement") or s.get("displacement_confirmed") or l.get("entry_displacement_confirmed")):
        evidence.append("DISPLACEMENT")
    if tf in {"30m", "1h", "2h", "4h"}:
        evidence.append("EXECUTION_TF")
    if contradictions == 0:
        evidence.append("NO_CONTRADICTION")
    ready = any(e in evidence for e in ("COMPRESSION_SIGNAL", "SQUEEZE_STATE")) and len(evidence) >= 4 and contradictions == 0
    if ready:
        groups.append({"group": "COMPRESSION_EXPANSION_RETEST", "weights": _profile("COMPRESSION_EXPANSION_RETEST"), "score": 93.0, "bonus": 3.5, "evidence": evidence[:6]})

    # 5) VOLATILITY_PULLBACK
    evidence = []
    if vol_state in {"HIGH", "EXPANSION", "ELEVATED"} or atr_pct >= 2.5:
        evidence.append("ELEVATED_VOLATILITY")
    if alignment >= 2:
        evidence.append("DIRECTIONAL_ALIGNMENT")
    if _truth(s.get("displacement") or s.get("displacement_confirmed") or l.get("entry_displacement_confirmed")):
        evidence.append("DISPLACEMENT")
    if _truth(l.get("pullback") or l.get("retest") or s.get("retest") or s.get("pullback")):
        evidence.append("RETEST_PULLBACK")
    if contradictions == 0:
        evidence.append("NO_CONTRADICTION")
    if tf in {"30m", "1h", "2h", "4h"}:
        evidence.append("EXECUTION_TF")
    ready = (vol_state in {"HIGH", "EXPANSION", "ELEVATED"} or atr_pct >= 2.5) and alignment >= 2 and contradictions == 0 and len(evidence) >= 4
    if ready:
        groups.append({"group": "VOLATILITY_PULLBACK", "weights": _profile("VOLATILITY_PULLBACK"), "score": 91.0, "bonus": 3.0, "evidence": evidence[:6]})

    # 6) MULTIASSET_SESSION_EXECUTION
    market_upper = _u(market_type)
    evidence = []
    if "MULTI" in market_upper:
        evidence.append("MULTI_ASSET")
    if session not in {"", "UNKNOWN", "NONE", "OFFHOURS", "UNDERLYING_CLOSED_OR_OFFHOURS"}:
        evidence.append("ACTIVE_SESSION")
    if alignment >= 2:
        evidence.append("DIRECTIONAL_ALIGNMENT")
    if contradictions == 0:
        evidence.append("NO_CONTRADICTION")
    if tf in {"1h", "4h"}:
        evidence.append("EXECUTION_TF")
    if volume_ratio >= 0.8:
        evidence.append("VOLUME_OK")
    ready = "MULTI" in market_upper and session not in {"", "UNKNOWN", "OFFHOURS", "UNDERLYING_CLOSED_OR_OFFHOURS"} and alignment >= 2 and contradictions == 0 and len(evidence) >= 4
    if ready:
        groups.append({"group": "MULTIASSET_SESSION_EXECUTION", "weights": _profile("MULTIASSET_SESSION_EXECUTION"), "score": 90.0, "bonus": 3.0, "evidence": evidence[:6]})

    groups.sort(key=lambda x: (-float(x.get("score") or 0), -float(x.get("bonus") or 0), str(x.get("group") or "")))
    selected = groups[:MAX_GROUPS]
    bonus = min(MAX_BONUS, sum(_f(g.get("bonus"), 0.0) for g in selected))

    # A hard contradiction blocks contextual authority even if individual
    # evidence tokens exist. The groups can describe quality, but cannot
    # override a conflicting directional structure.
    authority_ready = bool(selected and contradictions == 0 and direction in {"BULLISH", "BEARISH"})

    return {
        "version": CONTEXT_GROUPS_VERSION,
        "primary_group": selected[0]["group"] if selected else "NONE",
        "matched_groups": [g["group"] for g in selected],
        "groups": selected,
        "group_bonus": round(bonus, 2),
        "group_score": round(float(selected[0]["score"]), 2) if selected else 0.0,
        "authority_ready": authority_ready,
        "evidence_count": sum(len(g.get("evidence") or []) for g in selected),
        "context": {
            "timeframe": tf,
            "symbol": str(symbol or ""),
            "direction": direction,
            "adx": round(adx, 3),
            "atr_pct": round(atr_pct, 4),
            "rsi": round(rsi, 3),
            "volume_ratio": round(volume_ratio, 3),
            "regime": regime,
            "volatility_state": vol_state,
            "session": session,
            "alignment": alignment,
            "contradictions": contradictions,
        },
        "policy": {
            "creates_direction": False,
            "changes_entry": False,
            "changes_sl": False,
            "changes_tp": False,
            "lowers_q10_thresholds": False,
            "adds_network_calls": False,
            "adds_threads": False,
            "uses_live_outcomes_for_fitting": False,
        },
    }



def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _dir(value: Any) -> str:
    s = _u(value)
    if s in {"LONG", "BUY", "BULLISH", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if s in {"SHORT", "SELL", "BEARISH", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"




# ---------------------------------------------------------------------------
# COMMIT 23 — TEN PARALLEL QUALITY FILTERS
# ---------------------------------------------------------------------------
# These are NOT ten sequential vetoes. They are ten independent quality lenses.
# One passing filter is sufficient for directional confirmation, provided the
# universal execution guards are valid. Q10 remains visible and auditable but is
# not a mandatory second gate.
_PARALLEL_FILTER_NAMES = {
    "Q1": "COHERENCIA DIRECCIONAL",
    "Q2": "ESTRUCTURA / SMC",
    "Q3": "ALINEACIÓN MULTITEMPORAL",
    "Q4": "ESTRATEGIA / CONTEXTO",
    "Q5": "FLUJO / VOLUMEN",
    "Q6": "ENTRADA / ALCANZABILIDAD",
    "Q7": "SALIDA / GEOMETRÍA",
    "Q8": "RÉGIMEN / VOLATILIDAD",
    "Q9": "EVIDENCIA / VALIDACIÓN",
    "Q10": "SAFETY DE EJECUCIÓN",
}


def _execution_committee_score(levels: Mapping[str, Any], *, fast: bool = False) -> float:
    entry = _f(levels.get("entry_score") or levels.get("entry_quality_score"), 0.0)
    reach = _f(levels.get("entry_reachability") or levels.get("entry_reachability_score") or levels.get("reachability_score"), 0.0)
    if 0 < reach <= 1.0:
        reach *= 100.0
    tp = _f(levels.get("tp_quality_score"), 0.0)
    sl = _f(levels.get("sl_reliability"), 0.0)
    if sl <= 1.0:
        sl *= 100.0
    entry_component = 0.55 * entry + 0.25 * reach + 0.20 * 70.0
    if fast:
        # Fast trades care more about reachable execution and SL protection than
        # a large R/R multiple.
        return _clip(0.34 * entry_component + 0.33 * sl + 0.33 * tp)
    return _clip(0.38 * entry_component + 0.31 * sl + 0.31 * tp)


def _fast_rr_quality(rr: float) -> float:
    """Soft R/R contribution for fast trades; it is never a standalone veto."""
    rr = _f(rr, 0.0)
    if rr >= 1.8:
        return 90.0
    if rr >= 1.5:
        return 84.0
    if rr >= 1.3:
        return 78.0
    if rr >= 1.15:
        return 74.0
    if rr >= 1.0:
        return 68.0
    return 52.0


def _standard_rr_quality(rr: float) -> float:
    rr = _f(rr, 0.0)
    if rr <= 0:
        return 35.0
    if rr < 1.3:
        return 55.0
    if rr < 1.6:
        return 68.0
    if rr < 1.8:
        return 74.0
    if rr <= 3.0:
        return 92.0
    if rr <= 3.5:
        return 82.0
    return 62.0


def _universal_parallel_guards(
    levels: Mapping[str, Any],
    *,
    direction: str,
    native_stage: str = "PUBLICATION_GATE",
) -> Dict[str, Any]:
    l = dict(levels or {})
    risk_control = dict(l.get("risk_control") or {})
    entry = _f(l.get("entry"), 0.0)
    sl = _f(l.get("stop_loss"), 0.0)
    tp = _f(l.get("take_profit"), 0.0)
    legacy_safety = _f(l.get("execution_safety"), 0.0)
    planned_sl_loss = _f(
        risk_control.get("estimated_sl_loss_pct_margin"),
        abs(_f(l.get("roi_sl"), 0.0)),
    )
    atr_stress = _f(risk_control.get("estimated_atr_stress_loss_pct_margin"), 0.0)
    market_synthetic = bool(l.get("market_data_is_synthetic"))
    rr = _f(l.get("risk_reward"), 0.0)
    if rr <= 0 and entry > 0 and sl > 0 and tp > 0:
        rr = abs(tp - entry) / max(abs(entry - sl), 1e-12)
    tp_quality = _f(l.get("tp_quality_score"), 0.0)
    sl_quality = _f(l.get("sl_reliability"), 0.0)
    sl_quality = sl_quality * 100.0 if 0.0 <= sl_quality <= 1.0 else sl_quality
    codes = []

    if direction not in {"BULLISH", "BEARISH"}:
        codes.append("DIRECTION_UNDEFINED")
    geometry_ok = bool(
        entry > 0 and sl > 0 and tp > 0
        and ((direction == "BULLISH" and sl < entry < tp) or
             (direction == "BEARISH" and tp < entry < sl))
    )
    if not geometry_ok:
        codes.append("INVALID_ENTRY_SL_TP")
    if legacy_safety < PARALLEL_OPERATIONAL_SAFETY_FLOOR:
        codes.append("OPERATIONAL_SAFETY_BELOW_65")
    # Commit 25: diagnostic filters are measured against the same Premium
    # economic package; no soft R/R or weak SL/TP can look publication-ready.
    if legacy_safety < Q10_MIN_SAFETY:
        codes.append("PREMIUM_SAFETY_BELOW_75")
    if tp_quality < Q10_MIN_TP:
        codes.append("TP_QUALITY_BELOW_55")
    if sl_quality < Q10_MIN_SL:
        codes.append("SL_QUALITY_BELOW_60")
    if not (Q10_MIN_RR <= rr <= Q10_MAX_RR):
        codes.append("RR_OUTSIDE_1_8_3_5")
    if planned_sl_loss > PARALLEL_MAX_SL_LOSS_PCT:
        codes.append("LOSS_AT_SL")
    if not (0 < atr_stress <= PARALLEL_MAX_ATR_STRESS_PCT):
        codes.append("ATR_STRESS")
    if market_synthetic:
        codes.append("SYNTHETIC_MARKET_DATA")
    if str(native_stage or "").upper() != "PUBLICATION_GATE":
        codes.append("PRE_GATE_REJECTION")

    return {
        "passed": not codes,
        "codes": codes,
        "geometry_valid": geometry_ok,
        "legacy_execution_safety": round(legacy_safety, 2),
        "loss_at_sl_pct": round(planned_sl_loss, 3),
        "atr_stress_pct": round(atr_stress, 3),
        "stage": str(native_stage or "").upper(),
    }


def evaluate_parallel_quality_filters(
    levels: Mapping[str, Any] | None,
    trend: Mapping[str, Any] | None,
    momentum: Mapping[str, Any] | None,
    volatility: Mapping[str, Any] | None,
    structure: Mapping[str, Any] | None,
    timeframe: str,
    symbol: str,
    action: str,
    q: Mapping[str, Any],
    context_groups: Mapping[str, Any] | None = None,
    market_type: str = "futures",
    native_stage: str = "PUBLICATION_GATE",
) -> Dict[str, Any]:
    """Evaluate Q1..Q10 in parallel and confirm when ONE filter is >=75.

    The existing q1..q9 dimensions are preserved. Each parallel filter is a
    contextual composition of those dimensions plus the existing Entry/SL/TP
    committee outputs. The R/R value contributes softly; it is not a universal
    veto. The universal guards remain hard: valid geometry, operational Safety
    floor, loss-at-SL, ATR stress, real data, and no pre-gate rejection.
    """
    l = dict(levels or {})
    t = dict(trend or {})
    m = dict(momentum or {})
    v = dict(volatility or {})
    s = dict(structure or {})
    qv = {f"Q{i}": _f((q.get("quality") or {}).get(f"Q{i}"), 0.0) for i in range(1, 10)}
    direction = _dir(action or l.get("action") or l.get("direction"))
    ctx = dict(context_groups or {})
    ctx_score = _f(ctx.get("group_score"), 55.0) or 55.0
    matched = [str(x) for x in (ctx.get("matched_groups") or [])]
    alignment = _alignment(direction, t, m, s)
    contradictions = _contradiction_count(direction, t, m, s)
    family = _family_from_context(l)
    regime = _regime(l, t)
    vol_state = _vol_state(l, v)
    tf = str(timeframe or "").strip()
    rr = _f(l.get("risk_reward"), 0.0)
    committee_fast = tf in {"30m", "1h"} or "FAST_STABLE_CONTINUATION" in matched or "VOLATILITY_PULLBACK" in matched
    committee = _execution_committee_score(l, fast=committee_fast)
    fast_exit = _clip(
        0.42 * _f(l.get("tp_quality_score"), 0.0)
        + 0.33 * _f(l.get("sl_reliability"), 0.0) * (100.0 if _f(l.get("sl_reliability"), 0.0) <= 1.0 else 1.0)
        + 0.20 * _f(l.get("entry_score") or l.get("entry_quality_score"), 0.0)
        + 0.05 * _fast_rr_quality(rr)
    )
    standard_exit = _clip(
        0.34 * _f(l.get("tp_quality_score"), 0.0)
        + 0.34 * _f(l.get("sl_reliability"), 0.0) * (100.0 if _f(l.get("sl_reliability"), 0.0) <= 1.0 else 1.0)
        + 0.17 * _f(l.get("entry_score") or l.get("entry_quality_score"), 0.0)
        + 0.15 * _standard_rr_quality(rr)
    )
    legacy_safety = _f(l.get("execution_safety"), 0.0)
    safety_component = _clip(
        0.45 * legacy_safety
        + 0.35 * committee
        + 0.20 * ctx_score
    )

    contextual = max(ctx_score, 55.0)
    profile_map = {
        "Q1": (0.60, 0.15, 0.10, 0.15),
        "Q2": (0.58, 0.12, 0.12, 0.18),
        "Q3": (0.62, 0.14, 0.08, 0.16),
        "Q4": (0.52, 0.10, 0.08, 0.30),
        "Q5": (0.56, 0.10, 0.08, 0.26),
        "Q6": (0.52, 0.10, 0.18, 0.20),
        "Q7": (0.30, 0.08, 0.42, 0.20),
        "Q8": (0.56, 0.14, 0.08, 0.22),
        "Q9": (0.62, 0.08, 0.06, 0.24),
        "Q10": (0.00, 0.00, 0.80, 0.20),
    }

    evidence = {
        "Q1": alignment >= 2 and contradictions == 0,
        "Q2": bool(_has_sweep_mss_poi(l, s)[0] and _has_sweep_mss_poi(l, s)[1]) or bool(_has_sweep_mss_poi(l, s)[2] and qv["Q2"] >= 70),
        "Q3": bool(_unique_tf_count(l, timeframe) >= 2 or _truth(l.get("mtf_aligned"))),
        "Q4": bool(matched or family not in {"", "UNKNOWN"}),
        "Q5": bool(l.get("volume_ratio") or l.get("relative_volume") or l.get("volume") or l.get("flow") or l.get("market_microstructure")),
        "Q6": _f(l.get("entry_score") or l.get("entry_quality_score"), 0) >= 60 and (
            _f(l.get("entry_reachability") or l.get("entry_reachability_score") or l.get("reachability_score"), -1) > 0
            or (_f(l.get("entry_score") or l.get("entry_quality_score"), 0) >= 70 and bool(l.get("entry_source")))
        ),
        "Q7": _f(l.get("tp_quality_score"), 0) > 0 and _f(l.get("sl_reliability"), 0) > 0,
        "Q8": bool(_f(v.get("atr_pct") or l.get("atr_pct"), 0) > 0 or vol_state),
        "Q9": qv["Q9"] >= MIN_Q9_EVIDENCE,
        "Q10": legacy_safety >= PARALLEL_OPERATIONAL_SAFETY_FLOOR,
    }

    filters = []
    for name in [f"Q{i}" for i in range(1, 10)]:
        a, b, c, d = profile_map[name]
        context_fit = _clip(0.70 * contextual + 0.30 * qv[name])
        score = _clip(a * qv[name] + b * committee + c * standard_exit + d * context_fit)
        if name == "Q4" and matched:
            score = _clip(score + min(5.0, 1.5 * len(matched)))
        if name == "Q8" and (vol_state in {"LOW", "NORMAL", "COMPRESSION", "EXPANSION", "HIGH"} or regime):
            score = _clip(score + 3.0)
        if name == "Q5" and (_f(l.get("volume_ratio") or v.get("volume_ratio"), 0) >= 0.8):
            score = _clip(score + 3.0)
        passed = bool(evidence[name] and score >= PARALLEL_FILTER_MIN_SCORE)
        filters.append({
            "filter": name,
            "name": _PARALLEL_FILTER_NAMES[name],
            "score": round(score, 2),
            "passed": passed,
            "evidence": bool(evidence[name]),
        })

    q10_score = _clip(
        0.50 * safety_component
        + 0.25 * committee
        + 0.15 * contextual
        + 0.10 * fast_exit
    )
    filters.append({
        "filter": "Q10",
        "name": _PARALLEL_FILTER_NAMES["Q10"],
        "score": round(q10_score, 2),
        "passed": bool(evidence["Q10"] and q10_score >= PARALLEL_FILTER_MIN_SCORE),
        "evidence": bool(evidence["Q10"]),
    })

    passed = [row for row in filters if row.get("passed")]
    passed.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("filter") or "")))
    guards = _universal_parallel_guards(
        l,
        direction=direction,
        native_stage=native_stage,
    )
    if contradictions > 0:
        guards["codes"] = list(guards.get("codes") or []) + ["DIRECTIONAL_CONTRADICTION"]
        guards["passed"] = False
    confirmed = bool(passed and guards.get("passed"))
    selected = passed[0] if passed else max(filters, key=lambda row: float(row.get("score") or 0))
    scores = {str(row["filter"]): round(float(row.get("score") or 0), 2) for row in filters}
    passed_names = [str(row["filter"]) for row in passed]
    summary = " · ".join(f"{k} {scores[k]:.0f}" + ("✓" if k in passed_names else "") for k in [f"Q{i}" for i in range(1,11)])

    return {
        "version": PARALLEL_FILTERS_VERSION,
        "threshold": PARALLEL_FILTER_MIN_SCORE,
        "filters": filters,
        "filter_scores": scores,
        "passed_filters": passed_names,
        "selected_filter": str(selected.get("filter") or "NONE"),
        "selected_filter_name": str(selected.get("name") or ""),
        "selected_filter_score": round(float(selected.get("score") or 0), 2),
        "selected_filter_passed": bool(selected.get("passed")),
        "confirmed_one_of_ten": confirmed,
        "publication_candidate": confirmed,
        "q10_required": True,
        "legacy_q10_gate_eligible": False,
        "legacy_publication_blockers": [],
        "universal_guards": guards,
        "execution_committee_score": round(committee, 2),
        "safety_authority_score": round(safety_component, 2),
        "fast_operation_mode": bool(committee_fast),
        "rr_role": "DIAGNOSTIC_INPUT_HARD_NATIVE_PUBLICATION_GATE",
        "dedupe_key": f"{_u(symbol)}|{tf}",
        "dedupe_policy": "DIAGNOSTIC_RANK_ONLY_NATIVE_GATE_OWNS_PUBLICATION",
        "summary": summary,
        "market_type": str(market_type or "futures"),
        "direction": direction,
        "context_groups": matched,
    }

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
    market_type: str = "futures",
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
    mtf_alignment_raw = l.get("mtf_alignment")
    aligned_hint = _truth(
        l.get("mtf_aligned")
        or (mtf_alignment_raw if isinstance(mtf_alignment_raw, str) and mtf_alignment_raw.upper() in {"ALIGNED", "SUPPORTIVE"} else False)
    )
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
    base_composite = sum(q[k] * Q_WEIGHTS[k] for k in Q_WEIGHTS)

    # Commit 22 — add a context-conditioned quality group without replacing the
    # established Q1..Q9 dimensions. This is a bounded, deterministic overlay:
    # strong contextual evidence can help a good candidate cross the existing
    # global quality threshold, but weak/contradictory candidates receive no
    # bonus. The Q10 hard contract remains untouched.
    try:
        context_groups = evaluate_context_quality_groups(
            l, t, m, v, s, timeframe, symbol, action,
            market_type=str(market_type or "futures"),
        )
    except Exception as exc:
        context_groups = {
            "version": "COMMIT22_CONTEXT_QUALITY_GROUPS_UNAVAILABLE",
            "primary_group": "NONE",
            "matched_groups": [],
            "group_bonus": 0.0,
            "group_score": 0.0,
            "authority_ready": False,
            "evidence_count": 0,
            "context": {},
            "error": type(exc).__name__,
        }

    group_authority = bool(context_groups.get("authority_ready"))
    selected_groups = context_groups.get("groups") or []
    primary_group_row = selected_groups[0] if isinstance(selected_groups, list) and selected_groups and isinstance(selected_groups[0], Mapping) else {}
    profile = primary_group_row.get("weights") if isinstance(primary_group_row.get("weights"), Mapping) else {}
    group_weighted_quality = base_composite
    if profile and all(k in profile for k in q):
        try:
            group_weighted_quality = sum(q[k] * float(profile[k]) for k in q)
        except Exception:
            group_weighted_quality = base_composite

    group_score = _f(context_groups.get("group_score"), 0.0)
    if group_authority and group_score > 0.0:
        # 15% of the contextual group score is allowed to complement the
        # re-weighted Q1..Q9 profile. The group score itself is evidence-only
        # and bounded (the group engine has no market-data access).
        group_composite_raw = 0.85 * group_weighted_quality + 0.15 * group_score
    else:
        group_composite_raw = base_composite

    # Group scoring is an alternative lens, not a second vote. It can help a
    # context-fit candidate recover at most +5 points over the generic score.
    # The global threshold remains 76 and all structural/execution/Q9 floors
    # remain mandatory.
    context_group_delta = max(0.0, min(MAX_CONTEXT_GROUP_BONUS, group_composite_raw - base_composite))
    group_composite = min(100.0, base_composite + context_group_delta)
    adjusted_composite = max(base_composite, group_composite)
    group_bonus = context_group_delta

    structural_floor = min(q[k] for k in ("Q1", "Q2", "Q3", "Q4"))
    execution_floor = min(q["Q6"], q["Q7"])
    q9_ok = q["Q9"] >= MIN_Q9_EVIDENCE and state not in {"RETIRED", "RETIRED_ALPHA_DECAY"}

    # Commit 27 separates signal quality from statistical route authority.
    # Q9 remains visible as a diagnostic of evidence/governance, but must not
    # be counted twice: once inside Q1..Q9 and again by the frozen Champion/OOS
    # route gate. Q1..Q8 keep their existing weights, renormalized to 1.0, and
    # the existing 76 / 64 / 70 quality thresholds are preserved unchanged.
    nonstat_weight_total = sum(Q_WEIGHTS[k] for k in Q_WEIGHTS if k != "Q9") or 1.0
    commit27_nonstat_composite = sum(
        q[k] * Q_WEIGHTS[k] for k in Q_WEIGHTS if k != "Q9"
    ) / nonstat_weight_total
    commit27_quality_ready = bool(
        direction in {"BULLISH", "BEARISH"}
        and commit27_nonstat_composite >= MIN_COMPOSITE
        and structural_floor >= MIN_STRUCTURAL_FLOOR
        and execution_floor >= MIN_EXECUTION_Q6_Q7
        and state not in {"RETIRED", "RETIRED_ALPHA_DECAY"}
    )

    generic_quality_ready = bool(
        direction in {"BULLISH", "BEARISH"}
        and base_composite >= MIN_COMPOSITE
        and structural_floor >= MIN_STRUCTURAL_FLOOR
        and execution_floor >= MIN_EXECUTION_Q6_Q7
        and q9_ok
    )

    # Context recovery path: the global threshold is still 76. A candidate that
    # has a clean, explicit context group may use up to +4 points to cross that
    # same threshold, but only from a base score >=72 and only with the same
    # structural/execution/evidence floors. Thus this is not a threshold cut.
    context_quality_ready = bool(
        direction in {"BULLISH", "BEARISH"}
        and group_authority
        and base_composite >= MIN_CONTEXT_GROUP_BASE_COMPOSITE
        and group_composite >= MIN_CONTEXT_GROUP_ADJUSTED_COMPOSITE
        and context_group_delta > 0.0
        and structural_floor >= MIN_STRUCTURAL_FLOOR
        and execution_floor >= MIN_EXECUTION_Q6_Q7
        and q9_ok
    )
    composite = adjusted_composite
    parallel_quality_filters = evaluate_parallel_quality_filters(
        l, t, m, v, s, timeframe, symbol, action,
        q={"quality": q, "composite": composite, "context_quality_groups": context_groups},
        context_groups=context_groups,
        market_type=str(market_type or "futures"),
        native_stage=str(l.get("futures_filter_stage") or "PUBLICATION_GATE"),
    )
    parallel_quality_ready = bool(parallel_quality_filters.get("publication_candidate"))
    # Commit 25 anti-overfit policy: max(Q1..Q10) is diagnostic, never an
    # additional publication authority. Native composite/context quality owns
    # quality readiness; hard economic publication gates stay downstream.
    quality_ready = bool(generic_quality_ready or context_quality_ready)
    return {
        "version": VERSION,
        "model": MODEL,
        "quality": q,
        "composite": round(composite, 2),
        "base_composite": round(base_composite, 2),
        "context_group_bonus": round(group_bonus, 2),
        "context_group_composite": round(group_composite, 2),
        "context_group_weighted_q1_q9": round(group_weighted_quality, 2),
        "context_group_score": round(group_score, 2),
        "context_quality_groups": context_groups,
        "context_quality_authority": bool(context_quality_ready),
        "parallel_quality_filters": parallel_quality_filters,
        "parallel_quality_ready": bool(parallel_quality_ready),
        "generic_quality_ready": bool(generic_quality_ready),
        "structural_floor": round(structural_floor, 2),
        "execution_floor": round(execution_floor, 2),
        "quality_ready": quality_ready,
        "commit27_nonstat_composite": round(commit27_nonstat_composite, 2),
        "commit27_quality_ready": bool(commit27_quality_ready),
        "commit27_q9_role": "STATISTICAL_GOVERNANCE_DIAGNOSTIC_ONLY",
        "route_family": family,
        "evidence_state": state,
        "direction": direction,
        "market_type": str(market_type or "futures"),
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
            "q10_contract_enforced_by_final_hard_guards": True,
            "parallel_quality_role": "DIAGNOSTIC_ONLY",
            "max_parallel_q_can_publish": False,
            "parallel_confirmation_min_filters": 0,
            "parallel_confirmation_threshold": PARALLEL_FILTER_MIN_SCORE,
        },
    }


def deep_quality_safety_upgrade(levels: Mapping[str, Any], quality: Mapping[str, Any], *, operational_min: float = 65.0, publication_min: float = 75.0) -> Dict[str, Any]:
    """Calculate an optional upward Safety authority from Q1-Q9.

    The helper never lowers Safety and never bypasses economic hard gates. It is
    intentionally constrained to candidates already inside the operational
    Safety band. The publication threshold remains unchanged.
    """
    legacy = _f((levels or {}).get("execution_safety"), 0.0)
    composite = _f((quality or {}).get("composite"), legacy)
    quality_ready = bool((quality or {}).get("quality_ready"))
    can_upgrade = legacy >= float(operational_min) and quality_ready and composite >= MIN_DEEP_QUALITY_SAFETY_UPGRADE
    upgraded = max(legacy, composite) if can_upgrade else legacy
    return {
        "legacy_execution_safety": round(legacy, 2),
        "deep_quality_composite": round(composite, 2),
        "upgraded_execution_safety": round(upgraded, 2),
        "upgrade_applied": bool(can_upgrade and upgraded >= float(publication_min)),
        "operational_min": float(operational_min),
        "publication_min": float(publication_min),
        "thresholds_lowered": False,
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
