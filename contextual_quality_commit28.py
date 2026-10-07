"""Commit 28 — unified contextual quality and publication authority.

This module is deliberately pure: no network, DB, LLM, threads, timers, or
market-data calls.  It consumes the evidence already produced by the trading
"office" and returns one final auditable publication decision.

Design goals
------------
1. Different market/movement contexts receive different quality *lenses*.
2. Indicators/traders/committees are evidence producers, not independent alpha.
3. Statistical route authority is separate from execution quality.
4. Manual/final-visibility fallback geometry can never become an official signal.
5. Universal economic/safety contracts remain hard gates.
6. Parallel Q1..Q10 scores remain diagnostic; max(Q) is never publication authority.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Tuple

VERSION = "COMMIT28_CONTEXTUAL_QUALITY_CORE_V1"

PREMIUM_SAFETY_MIN = 75.0
OPERATIONAL_SAFETY_MIN = 65.0
RR_MIN = 1.8
RR_MAX = 3.5
MAX_SL_LOSS_PCT = 8.0
MAX_ATR_STRESS_PCT = 25.0
ENTRY_QUALITY_MIN = 65.0
SL_QUALITY_MIN = 60.0
TP_QUALITY_MIN = 55.0

MULTI_CLASSES = {
    "SPY-USDT": "US_INDEX",
    "QQQ-USDT": "US_INDEX",
    "CL-USDT": "ENERGY",
    "NATGAS-USDT": "ENERGY",
    "COPPER-USDT": "INDUSTRIAL_METAL",
    "XAG-USDT": "PRECIOUS_METAL",
    "KSTR-USDT": "CHINA_INDEX",
}


def _u(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _f(value: Any, default: float = 0.0) -> float:
    fallback = 0.0 if default is None else default
    try:
        n = float(value if value is not None else fallback)
        return n if math.isfinite(n) else float(fallback)
    except (TypeError, ValueError):
        try:
            return float(fallback)
        except (TypeError, ValueError):
            return 0.0


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "none", "null", "off"}


def _direction(value: Any) -> str:
    v = _u(value)
    if v in {"LONG", "BUY", "BULLISH", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "LONG"
    if v in {"SHORT", "SELL", "BEARISH", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "SHORT"
    return ""


def _market(result: Mapping[str, Any], symbol: str) -> str:
    if _u(symbol) in MULTI_CLASSES:
        return "MULTIASSET"
    raw = _u(result.get("market") or result.get("market_segment") or result.get("system_type"))
    if raw in {"MULTIASSET", "MULTI-ASSET", "MULTI_ASSET"}:
        return "MULTIASSET"
    return "FUTURES"


def _asset_class(result: Mapping[str, Any], symbol: str) -> str:
    return _u(result.get("asset_class") or MULTI_CLASSES.get(_u(symbol)) or "CRYPTO")


def _route_block(result: Mapping[str, Any]) -> Dict[str, Any]:
    levels = result.get("levels") if isinstance(result.get("levels"), Mapping) else {}
    operational = result.get("operational_intelligence") if isinstance(result.get("operational_intelligence"), Mapping) else {}
    candidates = (
        levels.get("commit19_champion"),
        levels.get("validated_strategy_route"),
        operational.get("commit19_champion"),
        result.get("commit19_champion"),
    )
    for row in candidates:
        if isinstance(row, Mapping) and row:
            return dict(row)
    return {}


def _route_id(route: Mapping[str, Any]) -> str:
    return str(route.get("champion_id") or route.get("strategy_id") or route.get("id") or "").strip()


def _route_is_live(route: Mapping[str, Any]) -> bool:
    if not route:
        return False
    # Exact route overlays carry one or more of these fields.  Fail closed on an
    # explicit false/retired state, but allow frozen route metadata that does not
    # repeat the eligibility flag after final geometry construction.
    if route.get("eligible_for_execution_routing") is False:
        return False
    state = _u((route.get("alpha_decay") or {}).get("state") if isinstance(route.get("alpha_decay"), Mapping) else route.get("state"))
    if state in {"SHADOW", "RETIRED", "RESEARCH", "RETIRED_ALPHA_DECAY", "SHADOW_CHAMPION"}:
        return False
    rid = _route_id(route)
    return bool(rid)


def _geometry(levels: Mapping[str, Any], action: str) -> Tuple[bool, float, float, float, float]:
    entry = _f(levels.get("entry"))
    sl = _f(levels.get("stop_loss"))
    tp = _f(levels.get("take_profit"))
    ok = bool(
        min(entry, sl, tp) > 0
        and ((action == "LONG" and sl < entry < tp) or (action == "SHORT" and tp < entry < sl))
    )
    rr = _f(levels.get("risk_reward"))
    if ok and rr <= 0:
        rr = abs(tp - entry) / max(abs(entry - sl), 1e-12)
    return ok, entry, sl, tp, rr


def _sl_quality(levels: Mapping[str, Any]) -> float:
    raw = _f(levels.get("sl_quality_score"), -1.0)
    if raw >= 0:
        return raw * 100.0 if raw <= 1.0 else raw
    raw = _f(levels.get("sl_reliability"), 0.0)
    return raw * 100.0 if raw <= 1.0 else raw


def _primary_poi(levels: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    source = " ".join(
        str(x or "")
        for x in (
            levels.get("entry_source"),
            levels.get("entry_location_basis"),
            levels.get("entry_location_context"),
            levels.get("manual_geometry_source"),
            levels.get("strategy_family"),
            levels.get("setup_family"),
        )
    ).upper()
    structure = result.get("structure") if isinstance(result.get("structure"), Mapping) else {}
    explicit = any(
        _truth(structure.get(k) or levels.get(k))
        for k in (
            "order_blocks", "fair_value_gaps", "fvg", "poi", "institutional_zone",
            "entry_poi_confirmed", "support", "resistance", "liquidity_pool",
        )
    )
    textual = any(token in source for token in ("ORDER BLOCK", "OB ", "FVG", "POI", "SUPPORT", "RESIST", "LIQUID", "PIVOT", "VWAP", "RETEST", "PULLBACK"))
    return bool(explicit or textual)


def _movement_profile(result: Mapping[str, Any], symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    levels = result.get("levels") if isinstance(result.get("levels"), Mapping) else {}
    market = _market(result, symbol)
    asset_class = _asset_class(result, symbol)
    tf = _u(timeframe)
    family = _u(levels.get("strategy_family") or levels.get("setup_family") or levels.get("live_quant_setup_family"))
    group = ""
    audit = result.get("app_native_quality_audit") if isinstance(result.get("app_native_quality_audit"), Mapping) else {}
    qctx = audit.get("context_quality_groups") if isinstance(audit.get("context_quality_groups"), Mapping) else {}
    group = _u(qctx.get("primary_group"))
    if not group:
        quality = result.get("quality_context") if isinstance(result.get("quality_context"), Mapping) else {}
        group = _u(quality.get("primary_group"))

    sweep = _truth(levels.get("entry_sweep_confirmed"))
    mss = _truth(levels.get("entry_mss_bos_confirmed"))
    displacement = _truth(levels.get("entry_displacement_confirmed"))
    poi = _primary_poi(levels, result)

    if market == "FUTURES":
        if tf == "30M" and sweep and mss:
            name = "FUTURES_FAST_SWEEP_MSS_REACTION"
        elif tf == "30M" and displacement and poi:
            name = "FUTURES_FAST_DISPLACEMENT_POI_RETEST"
        elif "PULLBACK" in family or "RETEST" in family:
            name = "FUTURES_TREND_PULLBACK_REACTION"
        elif "CONTINUATION" in family or "MOMENTUM" in family:
            name = "FUTURES_TREND_CONTINUATION"
        elif "BREAKOUT" in family or "COMPRESSION" in family:
            name = "FUTURES_BREAKOUT_EXPANSION_RETEST"
        else:
            name = "FUTURES_CONTEXTUAL_DIRECTIONAL"
    else:
        suffix = {
            "US_INDEX": "US_INDEX_SESSION_TREND",
            "ENERGY": "ENERGY_VOLATILITY_EVENT_RETEST",
            "INDUSTRIAL_METAL": "INDUSTRIAL_METAL_MACRO_TREND",
            "PRECIOUS_METAL": "PRECIOUS_METAL_RATES_USD_REACTION",
            "CHINA_INDEX": "CHINA_INDEX_ASIA_MACRO_RETEST",
        }.get(asset_class, "MULTIASSET_CONTEXTUAL")
        name = f"MULTI_{suffix}"

    return {
        "name": name,
        "market": market,
        "asset_class": asset_class,
        "timeframe": tf,
        "action": action,
        "family": family,
        "context_group": group,
        "post_geometry_evidence": {
            "sweep": sweep,
            "mss_bos": mss,
            "displacement": displacement,
            "primary_poi": poi,
        },
    }


def _profile_essential_ok(profile: Mapping[str, Any], route_id: str) -> Tuple[bool, str]:
    ev = profile.get("post_geometry_evidence") if isinstance(profile.get("post_geometry_evidence"), Mapping) else {}
    # The pooled 30m route was validated as a liquidity/structure execution
    # route.  Crucially this is checked *after* Entry geometry exists; it is not
    # a pre-entry router veto.
    if route_id == "F30_SHARED_LIQ_SWEEP_MSS_POI_V1":
        ok = bool((ev.get("sweep") and ev.get("mss_bos")) or (ev.get("displacement") and ev.get("primary_poi")))
        return ok, "F30_POST_GEOMETRY_STRUCTURE_CONFIRMED" if ok else "F30_POST_GEOMETRY_STRUCTURE_MISSING"
    if route_id in {
        "SOL_2H_SHORT_SUPERTREND_PULLBACK_V1",
        "LINK_4H_SHORT_RSI_TREND_V1",
        "US_INDEX_1D_TREND_PULLBACK_RR18_V1",
    }:
        ok = bool(ev.get("primary_poi"))
        return ok, "PULLBACK_REACTION_ZONE_CONFIRMED" if ok else "PULLBACK_REACTION_ZONE_MISSING"
    return True, "PROFILE_ESSENTIAL_EVIDENCE_OK"


def _quality_domains(quality: Mapping[str, Any]) -> Dict[str, Any]:
    q = dict(quality.get("quality") or {}) if isinstance(quality, Mapping) else {}
    def avg(keys):
        vals = [_f(q.get(k), 0.0) for k in keys]
        return round(sum(vals) / len(vals), 2) if vals else 0.0
    return {
        "direction_structure": avg(("Q1", "Q2", "Q3", "Q4")),
        "flow_context": avg(("Q5", "Q8")),
        "execution": avg(("Q6", "Q7")),
        "statistical_q9_diagnostic": round(_f(q.get("Q9")), 2),
        "q_scores": {k: round(_f(v), 2) for k, v in q.items() if str(k).startswith("Q")},
        "composite": round(_f(quality.get("composite")), 2),
        "base_composite": round(_f(quality.get("base_composite")), 2),
        "commit27_nonstat_composite": round(_f(quality.get("commit27_nonstat_composite"), quality.get("base_composite")), 2),
        "legacy_quality_ready": bool(quality.get("quality_ready")),
        "quality_ready": bool(quality.get("commit27_quality_ready", quality.get("quality_ready"))),
        "q9_role": str(quality.get("commit27_q9_role") or "STATISTICAL_GOVERNANCE_DIAGNOSTIC_ONLY"),
    }



def _office_evidence_map(result: Mapping[str, Any], levels: Mapping[str, Any]) -> Dict[str, Any]:
    """Map existing office components to non-overlapping evidence roles.

    Presence is diagnostic, never a score bonus.  This prevents the same market
    fact from gaining authority simply because several traders/committees
    describe it.
    """
    decision = result.get("decision") if isinstance(result.get("decision"), Mapping) else {}
    op = result.get("operational_intelligence") if isinstance(result.get("operational_intelligence"), Mapping) else {}
    context = result.get("context") if isinstance(result.get("context"), Mapping) else {}
    return {
        "direction_structure": {
            "trend": bool(result.get("trend")),
            "momentum_indicators": bool(result.get("momentum")),
            "structure_liquidity": bool(result.get("structure")),
            "multi_timeframe": bool(op.get("multi_timeframe") or result.get("multi_timeframe")),
            "specialist_traders": bool(decision.get("registro_votacion") or op.get("worker_desk_17_5_9")),
        },
        "timing_execution": {
            "dynamic_zones": bool(result.get("dynamic_zones") or levels.get("dynamic_zones") or levels.get("entry_source")),
            "orderbook_orderflow": bool(result.get("futures_microstructure_context") or levels.get("market_microstructure")),
            "entry_committee": bool(levels.get("entry_committee") or levels.get("entry_quality_score") or levels.get("entry_score")),
            "reaction_zone": bool(_primary_poi(levels, result)),
        },
        "risk_exit": {
            "sl_committee": bool(levels.get("sl_committee") or levels.get("sl_reliability") or levels.get("sl_quality_score")),
            "tp_committee": bool(levels.get("tp_committee") or levels.get("tp_quality_score")),
            "guardian_inputs": bool(levels.get("risk_control") or levels.get("leverage")),
        },
        "context_risk": {
            "fundamental_macro": bool(result.get("macro_context") or result.get("multiasset_macro") or context.get("macro")),
            "sentiment": bool(result.get("sentiment") or context.get("sentiment")),
            "greeks_options": bool(result.get("market_maker_context") or result.get("options_context") or context.get("greeks")),
            "session_day": bool(levels.get("market_session") or context.get("session") or context.get("day_of_week")),
            "ai_context": bool(result.get("ai_analysis") or result.get("ai_context") or context.get("ai")),
        },
        "statistical_governance": {
            "validated_route": bool(_route_block(result)),
            "review_trader": bool(result.get("review_trader") or op.get("review_trader")),
            "alpha_decay": bool((_route_block(result).get("alpha_decay") if _route_block(result) else None) or result.get("alpha_decay")),
        },
        "policy": "PRESENCE_IS_CONTEXT_NOT_EXTRA_VOTE",
    }

def evaluate_publication(
    result: Mapping[str, Any],
    *,
    symbol: str,
    timeframe: str,
    quality: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """Return Commit-27 final authority for Futures/Multi closed-candle output."""
    result = dict(result or {})
    levels = dict(result.get("levels") or {})
    decision = dict(result.get("decision") or {})
    action = _direction(
        levels.get("manual_observation_action")
        or decision.get("action")
        or result.get("action")
    )
    market = _market(result, symbol)
    asset_class = _asset_class(result, symbol)
    route = _route_block(result)
    rid = _route_id(route)
    profile = _movement_profile(result, symbol, timeframe, action)
    qdomains = _quality_domains(quality or {})

    reasons = []
    hard_reasons = []
    shadow_reasons = []

    if action not in {"LONG", "SHORT"}:
        hard_reasons.append("DIRECTION_UNDEFINED")

    closed_mode = _u(result.get("analysis_mode"))
    if closed_mode and closed_mode != "CLOSED_CANDLE":
        hard_reasons.append("NOT_CLOSED_CANDLE")
    if result.get("source_candle_closed") is not True:
        hard_reasons.append("SOURCE_CANDLE_NOT_CLOSED")

    synthetic = result.get("market_data_is_synthetic")
    if synthetic is None:
        synthetic = levels.get("market_data_is_synthetic")
    if synthetic is not False:
        hard_reasons.append("SYNTHETIC_OR_UNVERIFIED_DATA")

    geometry_ok, entry, sl, tp, rr = _geometry(levels, action)
    if not geometry_ok:
        hard_reasons.append("INVALID_ENTRY_SL_TP")

    fallback = bool(levels.get("manual_geometry_fallback")) or _u(levels.get("manual_geometry_authority")) in {
        "USER_MANUAL_ANALYSIS_ONLY", "FINAL_VISIBILITY_STRUCTURE_FALLBACK", "GUARANTEED_TECHNICAL_FALLBACK"
    }
    if fallback:
        hard_reasons.append("FALLBACK_GEOMETRY_NOT_PUBLISHABLE")

    if geometry_ok and not (RR_MIN <= rr <= RR_MAX):
        hard_reasons.append("RR_OUTSIDE_HARD_RANGE")

    safety = _f(levels.get("execution_safety"))
    risk_control = dict(levels.get("risk_control") or {})
    sl_loss = _f(risk_control.get("estimated_sl_loss_pct_margin"), _f(levels.get("loss_at_sl_pct"), 0.0))
    atr_stress = _f(risk_control.get("estimated_atr_stress_loss_pct_margin"), _f(levels.get("atr_stress_pct"), 0.0))
    entry_q = _f(levels.get("entry_quality_score") or levels.get("entry_score"))
    sl_q = _sl_quality(levels)
    tp_q = _f(levels.get("tp_quality_score"))

    # COMMIT 28 — a manual/final-visibility fallback is already terminally
    # non-publishable.  Its Safety/ATR/quality fields may be absent or inherited
    # from a rejected package, so reporting them as additional causal failures
    # produces the misleading triple blocker seen in production.  Keep the
    # values for diagnostics, but evaluate economic/quality guards only on a
    # primary execution geometry.  No fallback can publish.
    if not fallback:
        if safety < PREMIUM_SAFETY_MIN:
            hard_reasons.append("PREMIUM_SAFETY_BELOW_75")
        if sl_loss > MAX_SL_LOSS_PCT:
            hard_reasons.append("LOSS_AT_SL")
        if not (0.0 < atr_stress <= MAX_ATR_STRESS_PCT):
            hard_reasons.append("ATR_STRESS")
        if entry_q < ENTRY_QUALITY_MIN:
            hard_reasons.append("ENTRY_QUALITY_BELOW_65")
        if sl_q < SL_QUALITY_MIN:
            hard_reasons.append("SL_QUALITY_BELOW_60")
        if tp_q < TP_QUALITY_MIN:
            hard_reasons.append("TP_QUALITY_BELOW_55")
        # Quality is one contextual assessment of an already-built package.
        # The parallel max-Q scores are intentionally ignored here.
        if not qdomains.get("quality_ready"):
            hard_reasons.append("CONTEXTUAL_Q1_Q9_QUALITY_NOT_READY")

    route_live = _route_is_live(route)
    if not route_live:
        shadow_reasons.append("NO_VALIDATED_LIVE_ROUTE")
        _route_reason = str(route.get("live_context_reason") or route.get("reason") or "").strip().upper()
        if _route_reason and _route_reason != "NO_VALIDATED_LIVE_ROUTE":
            shadow_reasons.append(f"ROUTE_CONTEXT:{_route_reason}"[:180])

    profile_ok, profile_reason = _profile_essential_ok(profile, rid)
    if not profile_ok:
        hard_reasons.append(profile_reason)

    # Multi fast lanes are intentionally not extrapolated from crypto.  Their
    # contextual filters still run and their outcomes remain useful for
    # Research/ReviewTrader, but LIVE authority requires frozen OOS evidence.
    if market == "MULTIASSET" and _u(timeframe) in {"1H", "4H"} and not route_live:
        shadow_reasons.append(f"{asset_class}_FAST_ROUTE_REQUIRES_OOS")

    all_reasons = hard_reasons + shadow_reasons
    eligible = bool(not all_reasons and route_live)
    state = "EXECUTABLE_SIGNAL" if eligible else ("SHADOW_QUALITY_CANDIDATE" if not hard_reasons and shadow_reasons else "ANALYSIS_ONLY")
    blocker = all_reasons[0] if all_reasons else ""

    return {
        "version": VERSION,
        "eligible": eligible,
        "publication_status": state,
        "blocker": blocker,
        "reason_codes": all_reasons,
        "hard_reason_codes": hard_reasons,
        "shadow_reason_codes": shadow_reasons,
        "market": market,
        "asset_class": asset_class,
        "movement_profile": profile,
        "quality_domains": qdomains,
        "office_evidence": _office_evidence_map(result, levels),
        "route_authority": {
            "live": route_live,
            "route_id": rid,
            "route_reason": route.get("live_context_reason") or route.get("reason"),
            "source_type": route.get("source_type"),
            "evidence": dict(route.get("evidence") or {}) if isinstance(route.get("evidence"), Mapping) else {},
            "alpha_decay": dict(route.get("alpha_decay") or {}) if isinstance(route.get("alpha_decay"), Mapping) else {},
        },
        "diagnostics": {
            "upstream_rejected_reason": str(levels.get("rejected_reason") or "")[:240],
            "execution_runtime_failed": bool(levels.get("execution_runtime_failed")),
            "fallback_secondary_guards_evaluated": False if fallback else True,
        },
        "hard_guards": {
            "primary_geometry": bool(geometry_ok and not fallback),
            "rr": round(rr, 4),
            "safety": round(safety, 2),
            "sl_loss_pct": round(sl_loss, 4),
            "atr_stress_pct": round(atr_stress, 4),
            "entry_quality": round(entry_q, 2),
            "sl_quality": round(sl_q, 2),
            "tp_quality": round(tp_q, 2),
            "real_data": synthetic is False,
            "closed_candle": result.get("source_candle_closed") is True,
        },
        "policy": {
            "parallel_q_role": "DIAGNOSTIC_ONLY",
            "max_q_can_publish": False,
            "llm_can_publish": False,
            "fallback_can_publish": False,
            "route_authority_separate_from_quality": True,
            "changes_entry_sl_tp": False,
            "changes_leverage": False,
            "new_io": False,
        },
    }


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "thresholds": {
            "premium_safety_min": PREMIUM_SAFETY_MIN,
            "rr": [RR_MIN, RR_MAX],
            "entry_quality_min": ENTRY_QUALITY_MIN,
            "sl_quality_min": SL_QUALITY_MIN,
            "tp_quality_min": TP_QUALITY_MIN,
            "max_sl_loss_pct": MAX_SL_LOSS_PCT,
            "max_atr_stress_pct": MAX_ATR_STRESS_PCT,
        },
        "new_requests": 0,
        "new_threads": 0,
        "new_db_queries": 0,
        "new_llm_calls": 0,
    }
