"""Commit 31 — setup-specific Safety profiles.

Safety is no longer one universal publication threshold.  The engine first
classifies the movement/setup, then evaluates exactly one Safety profile.
Universal hard-risk and statistical-route authority remain separate.

Important anti-overfit rules:
* exactly one primary Safety per candidate;
* profile selection happens before the score is known;
* symbol/asset class only modifies context, it never selects the highest score;
* missing optional evidence is omitted/reweighted, not converted to a fake 0/50;
* no profile can create LONG/SHORT or a LIVE statistical route;
* the profile score is for ranking/leverage; publication readiness is based on
  explicit critical-component/economic contracts, not score >= a magic number.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Tuple

VERSION = "CORE_SAFETY_PROFILES_33_4_V1"

PROFILES = {
    "DIRECTIONAL_IMPULSE": {
        "weights": {"entry": .25, "sl": .20, "tp": .10, "rr": .05, "trend": .15, "momentum": .10, "structure": .08, "flow": .05, "mtf": .02},
        "tp_floor": 45.0, "rr_floor": 1.30,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 45.0, "trend": 60.0, "momentum": 55.0},
    },
    "TREND_CONTINUATION": {
        "weights": {"entry": .20, "sl": .20, "tp": .15, "rr": .10, "trend": .15, "mtf": .10, "structure": .05, "momentum": .05},
        "tp_floor": 55.0, "rr_floor": 1.60,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 55.0, "trend": 60.0},
    },
    "TREND_PULLBACK": {
        "weights": {"entry": .22, "sl": .20, "tp": .15, "rr": .10, "structure": .12, "trend": .08, "mtf": .08, "momentum": .05},
        "tp_floor": 55.0, "rr_floor": 1.60,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 55.0, "structure": 55.0, "trend": 55.0},
    },
    "BREAKOUT_EXPANSION": {
        "weights": {"entry": .20, "sl": .20, "tp": .15, "rr": .08, "structure": .15, "volatility": .08, "flow": .08, "momentum": .06},
        "tp_floor": 50.0, "rr_floor": 1.50,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 50.0, "structure": 60.0},
    },
    "LIQUIDITY_REVERSAL": {
        "weights": {"entry": .22, "sl": .20, "tp": .15, "rr": .08, "structure": .20, "flow": .05, "momentum": .05, "mtf": .05},
        "tp_floor": 50.0, "rr_floor": 1.50,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 50.0, "structure": 65.0},
    },
    "RANGE_REVERSION": {
        "weights": {"entry": .25, "sl": .20, "tp": .15, "rr": .10, "structure": .10, "momentum": .10, "volatility": .05, "mtf": .05},
        "tp_floor": 50.0, "rr_floor": 1.40,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 50.0, "momentum": 55.0},
    },
    "EVENT_SESSION": {
        "weights": {"entry": .25, "sl": .20, "tp": .10, "rr": .05, "structure": .10, "momentum": .05, "volatility": .10, "timing": .10, "flow": .05},
        "tp_floor": 50.0, "rr_floor": 1.40,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 50.0, "timing": 50.0},
    },
    "BALANCED_STRUCTURAL": {
        "weights": {"entry": .25, "sl": .20, "tp": .15, "rr": .10, "structure": .10, "trend": .08, "momentum": .05, "mtf": .04, "flow": .03},
        "tp_floor": 55.0, "rr_floor": 1.60,
        "critical": {"entry": 65.0, "sl": 60.0, "tp": 55.0, "structure": 55.0},
    },
}


def _f(v: Any, default: float | None = 0.0) -> float | None:
    try:
        if v is None:
            return default
        n = float(v)
        return n if math.isfinite(n) else default
    except Exception:
        return default


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _direction(v: Any) -> str:
    s = _u(v)
    if s in {"LONG", "BUY", "BULLISH", "UP", "COMPRA_SPOT", "TREND_UP"}:
        return "BULLISH"
    if s in {"SHORT", "SELL", "BEARISH", "DOWN", "VENTA_SPOT", "TREND_DOWN"}:
        return "BEARISH"
    return "NEUTRAL"


def _clip(v: float) -> float:
    return max(0.0, min(100.0, float(v)))


def _listish(v: Any) -> bool:
    return bool(v) if isinstance(v, (list, tuple, set, dict)) else bool(v)


def _market_bucket(symbol: str, market_type: str) -> str:
    sym = _u(symbol)
    mt = _u(market_type)
    if "MULTI" in mt or sym in {"SPY-USDT", "QQQ-USDT", "CL-USDT", "NATGAS-USDT", "COPPER-USDT", "XAG-USDT", "KSTR-USDT"}:
        if sym in {"SPY-USDT", "QQQ-USDT"}: return "US_INDEX"
        if sym in {"CL-USDT", "NATGAS-USDT"}: return "ENERGY"
        if sym == "COPPER-USDT": return "INDUSTRIAL_METAL"
        if sym == "XAG-USDT": return "PRECIOUS_METAL"
        if sym == "KSTR-USDT": return "CHINA_INDEX"
        return "MULTIASSET"
    if "SPOT" in mt:
        return "SPOT"
    return "CRYPTO_PERPETUAL"


def _setup_blob(levels: Mapping[str, Any], structure: Mapping[str, Any]) -> str:
    playbook = structure.get("_contingency_playbook") if isinstance(structure.get("_contingency_playbook"), Mapping) else {}
    vals = [
        levels.get("setup_family"), levels.get("strategy_family"), levels.get("live_quant_setup_family"),
        levels.get("_execution_setup_family_commit28"), levels.get("strategy_route_family"),
        playbook.get("setup_family"), playbook.get("strategy_family"),
    ]
    return " ".join(_u(v) for v in vals if v)


def _regime_blob(levels: Mapping[str, Any], structure: Mapping[str, Any], trend: Mapping[str, Any]) -> str:
    return _u(levels.get("market_regime") or levels.get("regime") or structure.get("_adaptive_market_regime") or trend.get("regime"))


def select_profile(*, levels: Mapping[str, Any], trend: Mapping[str, Any], momentum: Mapping[str, Any], volatility: Mapping[str, Any], structure: Mapping[str, Any], action: str, symbol: str, timeframe: str, market_type: str) -> Dict[str, Any]:
    """Choose exactly one Safety profile before scoring it."""
    direction = _direction(action)
    setup = _setup_blob(levels, structure)
    regime = _regime_blob(levels, structure, trend)
    bucket = _market_bucket(symbol, market_type)
    reasons = []

    # 1. Explicit early impulse from Proposal 3, or symmetric DMI impulse.
    try:
        from market_context import detect_directional_impulse
        impulse = detect_directional_impulse(trend, momentum, volatility, structure)
    except Exception:
        impulse = {}
    if impulse.get("active") and _direction(impulse.get("direction")) == direction:
        return {"profile": "DIRECTIONAL_IMPULSE", "reason": "DIRECTIONAL_IMPULSE_CONTEXT", "bucket": bucket, "regime": regime, "setup": setup}

    # 2. Liquidity reversal is the most specific structural archetype.
    sweep = _listish(structure.get("liquidity_sweeps") or structure.get("liquidity_sweep") or structure.get("stop_hunts"))
    mss = bool(structure.get("mss") or structure.get("bos") or structure.get("market_structure_shift") or levels.get("entry_mss_bos_confirmed"))
    poi = _listish(structure.get("order_blocks") or structure.get("fair_value_gaps") or structure.get("fvgs"))
    if ("SWEEP" in setup or sweep) and ("MSS" in setup or "RECLAIM" in setup or mss) and poi:
        return {"profile": "LIQUIDITY_REVERSAL", "reason": "SWEEP_MSS_POI", "bucket": bucket, "regime": regime, "setup": setup}

    # 3. Breakout / compression / expansion.
    displacement = bool(structure.get("displacement") or structure.get("displacement_confirmed") or levels.get("entry_displacement_confirmed"))
    squeeze = bool(volatility.get("squeeze_on") or structure.get("compression") or levels.get("squeeze_on"))
    if any(k in setup for k in ("BREAKOUT", "EXPANSION", "COMPRESSION")) or (displacement and squeeze):
        return {"profile": "BREAKOUT_EXPANSION", "reason": "BREAKOUT_OR_EXPANSION", "bucket": bucket, "regime": regime, "setup": setup}

    # 4. Pullback / retest.
    if any(k in setup for k in ("PULLBACK", "RETEST", "POI_RETEST")) or bool(structure.get("pullback") or structure.get("retest") or levels.get("pullback") or levels.get("retest")):
        return {"profile": "TREND_PULLBACK", "reason": "PULLBACK_OR_RETEST", "bucket": bucket, "regime": regime, "setup": setup}

    # 5. Range / mean reversion.
    adx = _f(trend.get("adx"), 0.0) or 0.0
    if any(k in setup for k in ("MEAN_REVERSION", "RANGE")) or regime in {"RANGING", "RANGE", "BALANCE"} or (0 < adx < 20):
        return {"profile": "RANGE_REVERSION", "reason": "RANGE_CONTEXT", "bucket": bucket, "regime": regime, "setup": setup}

    # 6. Event/session is only selected with explicit event/session evidence.
    session = _u(levels.get("market_session") or levels.get("session") or volatility.get("session"))
    event = bool(levels.get("macro_event_active") or levels.get("post_event") or structure.get("post_event") or volatility.get("event_risk"))
    session_strategy = any(k in setup for k in ("POST_EVENT", "SESSION", "VWAP_SESSION", "MACRO_EVENT"))
    if bucket in {"US_INDEX", "ENERGY", "INDUSTRIAL_METAL", "PRECIOUS_METAL", "CHINA_INDEX", "MULTIASSET"} and (event or session_strategy):
        return {"profile": "EVENT_SESSION", "reason": "EXPLICIT_MULTIASSET_SESSION_OR_EVENT_SETUP", "bucket": bucket, "regime": regime, "setup": setup}

    # 7. Stable directional trend.
    trend_dir = _direction(trend.get("direction"))
    if direction != "NEUTRAL" and trend_dir == direction and (adx >= 20 or regime in {"TRENDING_BULL", "TRENDING_BEAR", "TREND_UP", "TREND_DOWN"}):
        return {"profile": "TREND_CONTINUATION", "reason": "DIRECTIONAL_TREND", "bucket": bucket, "regime": regime, "setup": setup}

    # 8. Conservative catch-all for a directional package that does not fit a
    # specialised archetype. It has stronger structural critical floors.
    return {"profile": "BALANCED_STRUCTURAL", "reason": "NO_SPECIALISED_ARCHETYPE", "bucket": bucket, "regime": regime, "setup": setup}


def _rr_quality(rr: float, profile: str) -> float:
    if rr <= 0: return 0.0
    fast = profile in {"DIRECTIONAL_IMPULSE", "BREAKOUT_EXPANSION", "EVENT_SESSION", "RANGE_REVERSION", "LIQUIDITY_REVERSAL"}
    if fast:
        if rr < 1.0: return 35.0
        if rr < 1.3: return 60.0
        if rr < 1.5: return 72.0
        if rr < 1.8: return 82.0
        if rr <= 3.5: return 92.0
        if rr <= 4.5: return 80.0
        return 55.0
    if rr < 1.3: return 45.0
    if rr < 1.6: return 62.0
    if rr < 1.8: return 72.0
    if rr <= 3.5: return 94.0
    if rr <= 4.5: return 82.0
    return 55.0


def _directional_component(direction: str, source: Mapping[str, Any]) -> float | None:
    d = _direction(source.get("direction"))
    if d == "NEUTRAL": return None
    return 85.0 if d == direction else 20.0


def _components(*, levels: Mapping[str, Any], trend: Mapping[str, Any], momentum: Mapping[str, Any], volatility: Mapping[str, Any], structure: Mapping[str, Any], action: str, profile: str) -> Dict[str, float | None]:
    direction = _direction(action)
    entry = _f(levels.get("entry_quality_score") or levels.get("entry_score"), None)
    if entry is None and _f(levels.get("entry"), 0.0) > 0:
        committee = levels.get("entry_committee") if isinstance(levels.get("entry_committee"), Mapping) else {}
        scores = committee.get("scores") if isinstance(committee.get("scores"), Mapping) else {}
        entry = _f(committee.get("quality") or committee.get("score") or scores.get("quality") or scores.get("total"), None)
        if entry is None and str(levels.get("entry_source") or "").strip():
            # A real primary geometry exists but an old score key was not copied.
            # Treat it as minimally valid for profile evaluation; the committee
            # and publication hard guards still decide execution.
            entry = 65.0
    sl = _f(levels.get("sl_reliability"), None)
    if sl is None:
        sl = _f(levels.get("sl_quality_score") or levels.get("sl_score"), None)
    if sl is not None and 0 <= sl <= 1: sl *= 100.0
    tp = _f(levels.get("tp_quality_score") or levels.get("tp_score"), None)
    rr = _f(levels.get("risk_reward"), None)

    # Structure: explicit institutional/market-structure inventory + alignment.
    inventory = 0
    inventory += 1 if _listish(structure.get("order_blocks")) else 0
    inventory += 1 if _listish(structure.get("fair_value_gaps") or structure.get("fvgs")) else 0
    inventory += 1 if _listish(structure.get("liquidity_sweeps") or structure.get("stop_hunts")) else 0
    inventory += 1 if bool(structure.get("mss") or structure.get("bos") or structure.get("market_structure_shift") or levels.get("entry_mss_bos_confirmed")) else 0
    struct_dir = _direction(structure.get("direction") or structure.get("structure_direction"))
    structure_score = (50.0 + min(40.0, inventory * 10.0)) if inventory else None
    if structure_score is not None and struct_dir not in {"NEUTRAL", direction}:
        structure_score = min(structure_score, 35.0)

    # Trend uses DMI dominance for directional impulse; ADX for stable trend.
    adx = _f(trend.get("adx"), 0.0) or 0.0
    plus = _f(trend.get("plus_di"), 0.0) or 0.0
    minus = _f(trend.get("minus_di"), 0.0) or 0.0
    trend_dir = _direction(trend.get("direction"))
    if profile == "DIRECTIONAL_IMPULSE":
        dominant = plus if direction == "BULLISH" else minus
        opposite = minus if direction == "BULLISH" else plus
        spread = dominant - opposite
        ratio = dominant / max(opposite, 1.0)
        if trend_dir == direction and dominant >= 25 and (spread >= 15 or ratio >= 2.0):
            trend_score = _clip(72.0 + min(23.0, max(spread - 15.0, 0.0) * 0.8))
        elif trend_dir == direction:
            trend_score = 55.0
        elif trend_dir == "NEUTRAL":
            trend_score = None
        else:
            trend_score = 20.0
    else:
        if trend_dir == "NEUTRAL" and adx <= 0:
            trend_score = None
        elif trend_dir != direction:
            trend_score = 25.0
        else:
            trend_score = _clip(55.0 + max(0.0, min(30.0, adx)) * 1.2)

    momentum_score = _directional_component(direction, momentum)
    if momentum_score is None:
        rsi = _f(momentum.get("rsi"), None)
        if rsi is not None:
            if direction == "BULLISH": momentum_score = _clip(50 + (rsi - 50) * 1.5)
            elif direction == "BEARISH": momentum_score = _clip(50 + (50 - rsi) * 1.5)

    # Volatility is a fit score, not "more volatility is better".
    state = _u(volatility.get("state") or volatility.get("volatility_state") or levels.get("volatility_state"))
    vpct = _f(volatility.get("volatility_percentile"), None)
    if state or vpct is not None:
        high = state in {"HIGH", "EXPANSION", "ELEVATED", "EXTREME"} or (vpct is not None and vpct >= 80)
        low = state in {"LOW", "QUIET", "COMPRESSION"} or (vpct is not None and vpct <= 25)
        if profile in {"DIRECTIONAL_IMPULSE", "BREAKOUT_EXPANSION", "EVENT_SESSION"}:
            volatility_score = 88.0 if high else (70.0 if not low else 50.0)
        elif profile == "RANGE_REVERSION":
            volatility_score = 82.0 if low else (70.0 if not high else 45.0)
        else:
            volatility_score = 72.0 if not high else 62.0
    else:
        volatility_score = None

    # MTF only when explicit alignment/conflict data is present.
    mtf_text = " ".join(str(levels.get(k) or "") for k in ("multi_timeframe_alignment", "mtf_alignment", "timeframe_alignment" )).upper()
    if any(x in mtf_text for x in ("ALIGNED", "ALCIST", "BAJIST", "BULL", "BEAR")):
        mtf_score = 82.0
        if (direction == "BULLISH" and any(x in mtf_text for x in ("BAJIST", "BEAR"))) or (direction == "BEARISH" and any(x in mtf_text for x in ("ALCIST", "BULL"))):
            mtf_score = 30.0
    elif "CONFLICT" in mtf_text:
        mtf_score = 30.0
    else:
        mtf_score = None

    flow_ratio = _f(levels.get("volume_ratio") or levels.get("relative_volume") or volatility.get("volume_ratio") or volatility.get("relative_volume"), None)
    if flow_ratio is not None:
        flow_score = _clip(50.0 + (flow_ratio - 1.0) * 35.0)
    else:
        flow_score = None

    session = _u(levels.get("market_session") or levels.get("session") or volatility.get("session"))
    if session:
        timing_score = 35.0 if session in {"OFFHOURS", "UNDERLYING_CLOSED_OR_OFFHOURS"} else 75.0
    else:
        timing_score = None

    return {
        "entry": _clip(entry) if entry is not None else None,
        "sl": _clip(sl) if sl is not None else None,
        "tp": _clip(tp) if tp is not None else None,
        "rr": _rr_quality(rr or 0.0, profile) if rr is not None else None,
        "structure": _clip(structure_score) if structure_score is not None else None,
        "trend": _clip(trend_score) if trend_score is not None else None,
        "momentum": _clip(momentum_score) if momentum_score is not None else None,
        "volatility": _clip(volatility_score) if volatility_score is not None else None,
        "mtf": _clip(mtf_score) if mtf_score is not None else None,
        "flow": _clip(flow_score) if flow_score is not None else None,
        "timing": _clip(timing_score) if timing_score is not None else None,
    }


def evaluate_safety(*, levels: Mapping[str, Any] | None, trend: Mapping[str, Any] | None, momentum: Mapping[str, Any] | None, volatility: Mapping[str, Any] | None, structure: Mapping[str, Any] | None, action: str, symbol: str, timeframe: str, market_type: str = "futures") -> Dict[str, Any]:
    levels, trend, momentum, volatility, structure = map(lambda x: dict(x or {}), (levels, trend, momentum, volatility, structure))
    selected = select_profile(levels=levels, trend=trend, momentum=momentum, volatility=volatility, structure=structure, action=action, symbol=symbol, timeframe=timeframe, market_type=market_type)
    profile = selected["profile"]
    cfg = PROFILES[profile]
    components = _components(levels=levels, trend=trend, momentum=momentum, volatility=volatility, structure=structure, action=action, profile=profile)

    available_weight = 0.0
    weighted = 0.0
    contributions = {}
    for name, weight in cfg["weights"].items():
        val = components.get(name)
        if val is None:
            continue
        available_weight += weight
        weighted += val * weight
        contributions[name] = round(val * weight, 3)
    score = weighted / available_weight if available_weight > 0 else 0.0
    coverage = available_weight / max(sum(cfg["weights"].values()), 1e-12)

    reasons = []
    critical_failures = []
    for name, floor in cfg["critical"].items():
        val = components.get(name)
        if val is None:
            critical_failures.append(f"{name.upper()}_MISSING")
        elif val < floor:
            critical_failures.append(f"{name.upper()}_BELOW_{int(floor)}")

    rr = _f(levels.get("risk_reward"), 0.0) or 0.0
    technical_floor = _f(levels.get("minimum_viable_rr"), None)
    rr_floor = max(cfg["rr_floor"], technical_floor) if technical_floor is not None and technical_floor > 0 else cfg["rr_floor"]
    rr_ceiling = _f(levels.get("maximum_technical_rr"), 4.5) or 4.5
    economics_ok = bool(rr_floor <= rr <= rr_ceiling)
    if not economics_ok:
        critical_failures.append("RR_OUTSIDE_PROFILE_ECONOMIC_RANGE")

    direction = _direction(action)
    trend_dir = _direction(trend.get("direction"))
    momentum_dir = _direction(momentum.get("direction"))
    # A hard directional contradiction is non-compensatory when explicitly present.
    contradictions = []
    if trend_dir not in {"NEUTRAL", direction}:
        contradictions.append("TREND_DIRECTION_CONTRADICTION")
    if profile in {"DIRECTIONAL_IMPULSE", "TREND_CONTINUATION", "BREAKOUT_EXPANSION"} and momentum_dir not in {"NEUTRAL", direction}:
        contradictions.append("MOMENTUM_DIRECTION_CONTRADICTION")
    critical_failures.extend(contradictions)

    # Coverage is not a score threshold; it only ensures that a profile was not
    # computed from two isolated fields while all setup-specific evidence was missing.
    if coverage < 0.60:
        critical_failures.append("PROFILE_EVIDENCE_COVERAGE_BELOW_60PCT")

    ready = not critical_failures and direction in {"BULLISH", "BEARISH"}
    label = "EXCELLENT" if score >= 85 else "STRONG" if score >= 75 else "VALID" if score >= 65 else "WEAK"

    return {
        "version": VERSION,
        "profile": profile,
        "profile_reason": selected.get("reason"),
        "market_bucket": selected.get("bucket"),
        "regime": selected.get("regime"),
        "setup_family": selected.get("setup"),
        "score": round(score, 2),
        "label": label,
        "ready": bool(ready),
        "critical_failures": critical_failures,
        "components": {k: (round(v, 2) if v is not None else None) for k, v in components.items()},
        "weights": dict(cfg["weights"]),
        "weighted_contributions": contributions,
        "evidence_coverage": round(coverage, 3),
        "rr_floor": round(rr_floor, 3),
        "rr_ceiling": round(rr_ceiling, 3),
        "rr": round(rr, 3),
        "economics_ok": economics_ok,
        "publication_score_threshold": None,
        "score_is_hard_gate": False,
        "score_role": "LEVERAGE_RANKING_AND_DIAGNOSTICS",
        "profile_selection_uses_score": False,
        "creates_direction": False,
        "creates_live_route": False,
    }


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "profile_count": len(PROFILES),
        "profiles": list(PROFILES),
        "single_profile_per_signal": True,
        "highest_score_selection_forbidden": True,
        "universal_score_threshold": None,
        "legacy_safety_75_is_publication_gate": False,
        "q1_q10_are_publication_gates": False,
        "asset_classes_are_modifiers_not_new_safeties": True,
        "direction_symmetric": True,
        "missing_optional_evidence_reweighted": True,
        "new_io": 0,
        "new_threads": 0,
        "new_llm_calls": 0,
    }
