"""Commit 19.2.4 — Conditional Premium Quality Engine (CPQE).

This module is an incremental LIVE quality layer for Futures and Multi-Asset.
It does NOT create direction, alter Entry/SL/TP, lower existing hard risk limits,
add network calls, create threads, or create a Research/Shadow state.

The core idea is to calculate nine orthogonal quality dimensions Q1..Q9 and use
them as an additional execution-quality authority. The existing publication
minimums (Safety 75, TP 55, SL 60, RR 1.8..3.5, loss-at-SL and ATR stress) are
never lowered. CPQE may only improve the execution-safety score when the new
quality contract is stronger than the legacy proxy and the legacy operational
safety floor was already met.
"""
from __future__ import annotations

import math
import os
from functools import wraps
from typing import Any, Dict, Mapping, Tuple

VERSION = "COMMIT19_2_4_CPQE_LIVE_QUALITY_V2_CONTEXT_COMPLETE"

HARD_OPERATIONAL_SAFETY = 65.0
CPQE_MIN_COMPOSITE = float(os.getenv("CPQE_MIN_COMPOSITE", "76.0"))
CPQE_MIN_EXECUTION = float(os.getenv("CPQE_MIN_EXECUTION", "70.0"))
CPQE_MIN_ECONOMIC = float(os.getenv("CPQE_MIN_ECONOMIC", "75.0"))
CPQE_MAX_ROUTE = 8


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _s(v: Any) -> str:
    return str(v or "").strip().upper()


def _clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _bool(v: Any) -> bool:
    return bool(v) and str(v).strip().lower() not in {"0", "false", "no", "off", "none"}


def _blob(*items: Any) -> str:
    return " ".join(str(x or "") for x in items).upper()


def _action_direction(action: Any) -> str:
    a = _s(action)
    if a in {"LONG", "BUY", "BULLISH", "COMPRA_SPOT"}:
        return "BULLISH"
    if a in {"SHORT", "SELL", "BEARISH", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _risk_class(symbol: str) -> str:
    try:
        from futures_universe import risk_class_for
        return _s(risk_class_for(symbol)) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _asset_class(symbol: str) -> str:
    s = _s(symbol).replace("/", "-")
    mapping = {
        "SPY-USDT": "US_INDEX", "QQQ-USDT": "US_INDEX",
        "CL-USDT": "ENERGY", "NATGAS-USDT": "ENERGY",
        "COPPER-USDT": "INDUSTRIAL_METAL", "XAG-USDT": "PRECIOUS_METAL",
        "KSTR-USDT": "CHINA_INDEX",
    }
    return mapping.get(s, "CRYPTO")


def _tf_bucket(tf: str) -> str:
    tf = str(tf or "")
    if tf in {"30m", "1h"}:
        return "FAST"
    if tf in {"2h", "4h"}:
        return "SWING"
    return "MACRO"


def _quality_features(levels: Mapping[str, Any], trend: Mapping[str, Any], momentum: Mapping[str, Any],
                      structure: Mapping[str, Any], timeframe: str, symbol: str = "", action: str = "") -> Dict[str, Any]:
    l = dict(levels or {})
    t = dict(trend or {})
    m = dict(momentum or {})
    st = dict(structure or {})
    nested = [l, l.get("risk_control") or {}, l.get("entry_context") or {}, l.get("execution_context") or {}, l.get("operational_intelligence") or {}]
    all_blob = _blob(*nested, st, t, m)

    direction = _action_direction(action or l.get("action") or l.get("direction"))
    trend_dir = _action_direction(t.get("direction"))
    structure_dir = _action_direction(st.get("direction") or st.get("structure_direction"))
    mtf = _s(l.get("mtf_alignment") or (l.get("multi_timeframe") or {}).get("alignment"))

    sweep = _bool(l.get("entry_sweep_confirmed") or st.get("liquidity_sweep") or st.get("sweep") or "SWEEP" in all_blob)
    mss = _bool(l.get("entry_mss_bos_confirmed") or st.get("mss") or st.get("bos") or st.get("market_structure_shift") or any(x in all_blob for x in (" MSS ", " BOS ", "CHOCH")))
    displacement = _bool(l.get("entry_displacement_confirmed") or st.get("displacement") or st.get("displacement_confirmed") or "DISPLACEMENT" in all_blob)
    poi = _bool(l.get("entry_poi_confirmed") or st.get("order_blocks") or st.get("fair_value_gaps") or st.get("fvg") or l.get("entry_source"))
    squeeze = _bool(l.get("squeeze_on") or (l.get("volatility") or {}).get("squeeze_on") or "SQUEEZE" in all_blob)

    entry_score = _f(l.get("entry_score"), 50.0)
    tp_score_raw = _f(l.get("tp_quality_score"), 50.0)
    sl_raw = _f(l.get("sl_reliability"), 0.5)
    sl_score = sl_raw * 100.0 if sl_raw <= 1.0 else sl_raw
    rr = _f(l.get("risk_reward"), 0.0)
    adx = _f(t.get("adx") if t.get("adx") is not None else l.get("adx"), 20.0)
    volume_ratio = _f((l.get("volume") or {}).get("volume_ratio") if isinstance(l.get("volume"), dict) else l.get("volume_ratio"), 1.0)
    if volume_ratio <= 0:
        volume_ratio = 1.0
    atr_pct = _f((l.get("volatility") or {}).get("atr_pct") if isinstance(l.get("volatility"), dict) else l.get("atr_pct"), 0.0)
    vol_state = _s((l.get("volatility") or {}).get("state") if isinstance(l.get("volatility"), dict) else l.get("volatility_state"))
    regime = _s(l.get("regime") or t.get("regime") or (l.get("market_regime") or {}).get("regime"))

    divs = list(m.get("divergences") or []) + list(m.get("hidden_divergences") or []) + list(l.get("divergences") or []) + list(l.get("hidden_divergences") or [])
    div_blob = _blob(*divs, l.get("divergence_details"))
    divergence_count = len(divs)
    div_support = (
        (direction == "BULLISH" and any("BULL" in _s(x) for x in divs)) or
        (direction == "BEARISH" and any("BEAR" in _s(x) for x in divs))
    )

    families = list(l.get("independent_support_families") or l.get("families") or [])
    family_blob = _blob(*families, l.get("setup_family"), l.get("strategy_family"), l.get("entry_source"))

    champion = l.get("commit19_champion") or l.get("validated_strategy_route") or l.get("research_evidence") or {}
    stat_evidence = 55.0
    if isinstance(champion, dict) and champion:
        is_block = champion.get("is") or champion.get("train") or {}
        oos_block = champion.get("oos") or {}
        n = _f(is_block.get("n"), 0)
        pf = _f((oos_block.get("pf") if oos_block else None) or is_block.get("pf"), 0)
        exp = _f((oos_block.get("expectancy_r") if oos_block else None) or is_block.get("expectancy_r") or is_block.get("exp_r"), 0)
        stat_evidence = 50.0 + min(30.0, max(0.0, n - 8.0) * 0.6) + min(12.0, max(0.0, pf - 1.0) * 5.0) + min(8.0, max(0.0, exp) * 8.0)
    elif "CHAMPION" in all_blob or "OOS_VALIDATED" in all_blob:
        stat_evidence = 78.0

    return {
        "symbol": str(symbol or "").upper().replace("/", "-"),
        "timeframe": timeframe,
        "tf_bucket": _tf_bucket(timeframe),
        "risk_class": _risk_class(symbol),
        "asset_class": _asset_class(symbol),
        "direction": direction,
        "trend_direction": trend_dir,
        "structure_direction": structure_dir,
        "mtf_alignment": mtf,
        "sweep": sweep,
        "mss": mss,
        "displacement": displacement,
        "poi": poi,
        "squeeze": squeeze,
        "entry_score": _clip(entry_score),
        "tp_score": _clip(tp_score_raw),
        "sl_score": _clip(sl_score),
        "rr": rr,
        "adx": adx,
        "volume_ratio": volume_ratio,
        "atr_pct": atr_pct,
        "vol_state": vol_state,
        "regime": regime,
        "divergence_count": divergence_count,
        "div_support": bool(div_support),
        "div_blob": div_blob,
        "families": families,
        "family_blob": family_blob,
        "stat_evidence": _clip(stat_evidence),
        "all_blob": all_blob,
    }


def _route(features: Mapping[str, Any]) -> str:
    f = features
    if f["sweep"] and (f["mss"] or f["displacement"]) and f["poi"]:
        return "LIQUIDITY"
    if f["divergence_count"] and f["div_support"] and (f["mss"] or f["poi"]):
        return "DIVERGENCE"
    if f["squeeze"] and (f["mss"] or f["displacement"] or f["volume_ratio"] >= 1.15):
        return "COMPRESSION"
    if f["regime"] in {"RANGING", "BALANCED", "MEAN_REVERSION", "RANGE"} and f["poi"]:
        return "BALANCE"
    if f["asset_class"] in {"US_INDEX", "ENERGY", "PRECIOUS_METAL", "INDUSTRIAL_METAL", "CHINA_INDEX"}:
        if f["poi"] or f["mss"] or f["mtf_alignment"] in {"ALIGNED", "SUPPORTIVE"}:
            return "ASSET_CONTEXT"
    if f["trend_direction"] == f["direction"] and f["adx"] >= 18 and f["poi"]:
        return "TREND"
    return "CONFLUENCE"


def _score_q(features: Mapping[str, Any]) -> Dict[str, float]:
    f = features
    q1 = 48.0 + (18 if f["poi"] else 0) + (12 if f["sweep"] else 0) + (10 if f["mss"] else 0) + (7 if f["displacement"] else 0)
    if f["structure_direction"] == f["direction"] and f["direction"] != "NEUTRAL":
        q1 += 5

    q2 = 50.0
    if f["trend_direction"] == f["direction"] and f["direction"] != "NEUTRAL":
        q2 += 16
    if f["mtf_alignment"] in {"ALIGNED", "SUPPORTIVE"}:
        q2 += 15
    elif f["mtf_alignment"] in {"CONFLICT", "BEARISH", "BULLISH"}:
        q2 -= 7
    q2 += min(14.0, max(0.0, f["adx"] - 18.0) * 0.6)

    if f["vol_state"] in {"SHOCK", "EXTREME", "CRASH"}:
        q3 = 48.0
    elif f["vol_state"] in {"LOW", "QUIET"}:
        q3 = 66.0
    elif f["vol_state"] in {"HIGH", "EXPANSION"}:
        q3 = 76.0
    else:
        q3 = 72.0
    if f["atr_pct"] > 0:
        if 0.6 <= f["atr_pct"] <= 5.0:
            q3 += 5
        elif f["atr_pct"] > 8:
            q3 -= 8

    q4 = 48.0 + min(24.0, max(-10.0, math.log(max(f["volume_ratio"], 0.25), 2.0) * 12.0))
    q4 += 10 if f["displacement"] else 0
    q4 += 8 if "OPEN_INTEREST" in f["all_blob"] or "ORDER BOOK" in f["all_blob"] or "FUNDING" in f["all_blob"] else 0

    if f["regime"] in {"RANGING", "BALANCED", "MEAN_REVERSION", "RANGE"}:
        q5 = 82.0 if f["poi"] else 65.0
    elif f["trend_direction"] == f["direction"]:
        q5 = 72.0
    else:
        q5 = 58.0

    q6 = 56.0 + min(20.0, 6.0 * max(len(f["families"]), 1))
    q6 += 10 if f["div_support"] else 0
    q6 += 12 if f["sweep"] and f["mss"] else 0
    q6 += 8 if f["mtf_alignment"] in {"ALIGNED", "SUPPORTIVE"} else 0
    q6 = _clip(q6)

    rr_component = 40.0 if f["rr"] <= 0 else (55.0 if f["rr"] < 1.8 else 70.0 if f["rr"] < 2.0 else 82.0 if f["rr"] < 2.5 else 92.0 if f["rr"] <= 3.5 else 62.0)
    q7 = 0.34 * f["entry_score"] + 0.22 * f["sl_score"] + 0.26 * f["tp_score"] + 0.18 * rr_component

    q8 = f["stat_evidence"]

    q9 = 55.0 + 0.34 * max(f["rr"], 0.0) * 20.0
    q9 += 12 if 1.8 <= f["rr"] <= 3.2 else -6
    q9 = _clip(q9)

    return {f"Q{i}": round(_clip(v), 2) for i, v in enumerate((q1,q2,q3,q4,q5,q6,q7,q8,q9), start=1)}


_ROUTE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "LIQUIDITY": {"Q1": .20,"Q2": .10,"Q3": .08,"Q4": .12,"Q5": .06,"Q6": .16,"Q7": .18,"Q8": .05,"Q9": .05},
    "TREND": {"Q1": .12,"Q2": .18,"Q3": .10,"Q4": .10,"Q5": .08,"Q6": .10,"Q7": .20,"Q8": .06,"Q9": .06},
    "DIVERGENCE": {"Q1": .15,"Q2": .12,"Q3": .08,"Q4": .08,"Q5": .08,"Q6": .16,"Q7": .18,"Q8": .07,"Q9": .08},
    "COMPRESSION": {"Q1": .12,"Q2": .10,"Q3": .18,"Q4": .14,"Q5": .08,"Q6": .12,"Q7": .16,"Q8": .04,"Q9": .06},
    "BALANCE": {"Q1": .12,"Q2": .10,"Q3": .10,"Q4": .08,"Q5": .20,"Q6": .12,"Q7": .18,"Q8": .04,"Q9": .06},
    "ASSET_CONTEXT": {"Q1": .12,"Q2": .20,"Q3": .10,"Q4": .10,"Q5": .10,"Q6": .12,"Q7": .16,"Q8": .05,"Q9": .05},
    "CONFLUENCE": {"Q1": .14,"Q2": .13,"Q3": .09,"Q4": .10,"Q5": .07,"Q6": .16,"Q7": .18,"Q8": .05,"Q9": .08},
}


def evaluate(levels: Mapping[str, Any], trend: Mapping[str, Any], momentum: Mapping[str, Any], structure: Mapping[str, Any], timeframe: str, symbol: str = "", action: str = "") -> Dict[str, Any]:
    features = _quality_features(levels, trend, momentum, structure, timeframe, symbol, action)
    route = _route(features)
    q = _score_q(features)
    weights = _ROUTE_WEIGHTS.get(route, _ROUTE_WEIGHTS["CONFLUENCE"])
    composite = sum(q[k] * w for k, w in weights.items())
    # Family-specific contracts: no single weak dimension is allowed to hide a
    # broken execution or economic package.
    execution_floor = min(q["Q7"], q["Q9"])
    structural_floor = min(q["Q1"], q["Q2"], q["Q6"])
    qualifying = (
        composite >= CPQE_MIN_COMPOSITE and
        execution_floor >= CPQE_MIN_EXECUTION and
        q["Q9"] >= CPQE_MIN_ECONOMIC and
        structural_floor >= 64.0 and
        features["direction"] in {"BULLISH", "BEARISH"}
    )
    return {
        "version": VERSION,
        "authority": "CPQE_LIVE_QUALITY",
        "route": route,
        "quality": q,
        "composite": round(composite, 2),
        "execution_floor": round(execution_floor, 2),
        "structural_floor": round(structural_floor, 2),
        "qualifying": bool(qualifying),
        "features": features,
        "weights": weights,
        "policy": {
            "creates_direction": False,
            "changes_entry": False,
            "changes_sl": False,
            "changes_tp": False,
            "lowers_legacy_thresholds": False,
            "new_network_requests": False,
        },
    }


def _decorate_gate(result: Dict[str, Any], cpqe: Mapping[str, Any], legacy: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(result or {})
    levels = dict(out.get("levels") or {})
    levels.pop("_cpqe_context", None)
    gate = dict(out.get("futures_publication_gate") or {})
    levels["cpqe_19_2_4"] = dict(cpqe)
    levels["legacy_execution_safety"] = legacy.get("execution_safety")
    levels["execution_safety_quality_authority"] = "CPQE" if cpqe.get("qualifying") else "LEGACY"
    out["levels"] = levels
    out["cpqe_19_2_4"] = dict(cpqe)
    out["futures_publication_gate"] = gate
    return out


def _patch_futures_class(cls: Any) -> bool:
    if cls is None or not hasattr(cls, "_apply_futures_publication_gate") or getattr(cls, "_cpqe_19_2_4_installed", False):
        return False
    original_gate = cls._apply_futures_publication_gate

    @wraps(original_gate)
    def wrapped_gate(self, levels, timeframe, symbol="", action=""):
        out = original_gate(self, levels, timeframe, symbol=symbol, action=action)
        legacy_levels = dict(out.get("levels") or {})
        legacy_safety = _f(legacy_levels.get("execution_safety"))
        ctx = legacy_levels.get("_cpqe_context") if isinstance(legacy_levels.get("_cpqe_context"), dict) else {}
        trend = dict(ctx.get("trend") or {})
        momentum = dict(ctx.get("momentum") or {})
        structure = dict(ctx.get("structure") or {})
        symbol = str(ctx.get("symbol") or symbol or legacy_levels.get("symbol") or "")
        action = str(ctx.get("action") or action or legacy_levels.get("action") or "")
        # Common aliases used by older payloads.
        trend = trend or (legacy_levels.get("trend") if isinstance(legacy_levels.get("trend"), dict) else {})
        momentum = momentum or (legacy_levels.get("momentum") if isinstance(legacy_levels.get("momentum"), dict) else {})
        structure = structure or (legacy_levels.get("structure") if isinstance(legacy_levels.get("structure"), dict) else {})
        trend = trend or (out.get("trend") if isinstance(out.get("trend"), dict) else {})
        momentum = momentum or (out.get("momentum") if isinstance(out.get("momentum"), dict) else {})
        structure = structure or (out.get("structure") if isinstance(out.get("structure"), dict) else {})
        cpqe = evaluate(legacy_levels, trend, momentum, structure, timeframe, symbol, action)

        # First authority: a higher, holistic safety score may replace the old
        # proxy aggregation. The publication threshold itself remains 75.
        if legacy_safety >= HARD_OPERATIONAL_SAFETY and cpqe.get("qualifying"):
            upgraded = dict(legacy_levels)
            upgraded["legacy_execution_safety"] = legacy_safety
            upgraded["execution_safety"] = max(legacy_safety, _f(cpqe.get("composite"), legacy_safety))
            upgraded["execution_safety_authority"] = "CPQE_LIVE_QUALITY"
            upgraded["cpqe_19_2_4"] = cpqe
            out = original_gate(self, upgraded, timeframe, symbol=symbol, action=action)
            legacy_levels = dict(out.get("levels") or {})

        out = _decorate_gate(out, cpqe, {"execution_safety": legacy_safety})

        if out.get("publication_eligible"):
            return out

        reasons = [str(x) for x in ((out.get("futures_publication_gate") or {}).get("reason_codes") or [])]
        # CPQE is an additional execution-quality authority. It never turns a
        # non-directional thesis into a trade and never bypasses hard economic
        # or geometric safety conditions. It is allowed to replace only the
        # legacy TP/SL proxy aggregation when the old operational Safety floor
        # was already met and the holistic Q1..Q9 contract is stronger.
        hard_codes = {"RR", "LOSS_AT_SL", "ATR_STRESS"}
        if (legacy_safety >= HARD_OPERATIONAL_SAFETY and cpqe.get("qualifying") and
            not hard_codes.intersection(reasons) and
            any(code in {"TP_QUALITY", "SL_QUALITY", "SAFETY"} for code in reasons)):
            # Do not lower the publication thresholds; publish under the new
            # holistic safety authority with the SAME universal economic rules.
            levels = dict(out.get("levels") or {})
            levels["legacy_execution_safety"] = legacy_safety
            levels["execution_safety"] = max(legacy_safety, float(cpqe.get("composite") or legacy_safety))
            levels["cpqe_promoted_legacy_quality"] = True
            levels["publication_status"] = "EXECUTABLE_SIGNAL"
            levels["is_rejected"] = False
            levels["is_executable"] = True
            levels.pop("rejected_reason", None)
            gate = dict(out.get("futures_publication_gate") or {})
            gate["eligible"] = True
            gate["tier"] = "PREMIUM"
            gate["reasons"] = []
            gate["reason_codes"] = []
            gate["quality_authority"] = "CPQE_LIVE_QUALITY"
            gate["legacy_reasons"] = reasons
            gate["cpqe_composite"] = cpqe.get("composite")
            gate["cpqe_route"] = cpqe.get("route")
            gate["cpqe_quality"] = cpqe.get("quality")
            gate["thresholds"] = dict(gate.get("thresholds") or {})
            out["levels"] = levels
            out["futures_publication_gate"] = gate
            out["futures_signal_tier"] = "PREMIUM"
            out["publication_eligible"] = True
            out["publication_status"] = "EXECUTABLE_SIGNAL"
            out["is_executable"] = True
            out["is_rejected"] = False
            out["quality_authority"] = "CPQE_LIVE_QUALITY"
        return out

    cls._apply_futures_publication_gate = wrapped_gate
    cls._cpqe_19_2_4_installed = True
    return True


def _patch_safety_class(cls: Any) -> bool:
    if cls is None or not hasattr(cls, "_calculate_execution_safety") or getattr(cls, "_cpqe_safety_19_2_4_installed", False):
        return False
    original = cls._calculate_execution_safety

    @wraps(original)
    def wrapped_safety(self, levels, trend, momentum, structure, timeframe):
        out = original(self, levels, trend, momentum, structure, timeframe)
        result = dict(out or {})
        legacy = _f(result.get("execution_safety"))
        ctx = (levels or {}).get("_cpqe_context") if isinstance((levels or {}).get("_cpqe_context"), dict) else {}
        symbol = str(ctx.get("symbol") or (levels or {}).get("symbol") or "")
        action = str(ctx.get("action") or (levels or {}).get("action") or "")
        cpqe_trend = dict(ctx.get("trend") or trend or {})
        cpqe_momentum = dict(ctx.get("momentum") or momentum or {})
        cpqe_structure = dict(ctx.get("structure") or structure or {})
        cpqe = evaluate(levels or {}, cpqe_trend, cpqe_momentum, cpqe_structure, timeframe, symbol, action)
        result["legacy_execution_safety"] = legacy
        result["cpqe_19_2_4"] = cpqe
        if legacy >= HARD_OPERATIONAL_SAFETY and cpqe.get("qualifying"):
            result["execution_safety"] = round(max(legacy, float(cpqe.get("composite") or legacy)), 2)
            result["execution_safety_authority"] = "CPQE_LIVE_QUALITY"
        else:
            result["execution_safety_authority"] = "LEGACY"
        return result

    cls._calculate_execution_safety = wrapped_safety
    cls._cpqe_safety_19_2_4_installed = True
    return True


def install_post_app(app: Any) -> Dict[str, Any]:
    status = {"version": VERSION, "futures_gate": False, "futures_safety": False, "memory": False, "frontend": False}
    try:
        import futures_system
        status["futures_gate"] = _patch_futures_class(getattr(futures_system, "FuturesAnalysis", None))
        status["futures_safety"] = _patch_safety_class(getattr(futures_system, "FuturesAnalysis", None))
        try:
            import multiasset_system
            status["multiasset_gate"] = _patch_futures_class(getattr(multiasset_system, "MultiAssetAnalysis", None))
            status["multiasset_safety"] = _patch_safety_class(getattr(multiasset_system, "MultiAssetAnalysis", None))
        except Exception as exc:
            status["multiasset_error"] = str(exc)[:180]
    except Exception as exc:
        status["futures_error"] = str(exc)[:180]

    # Runtime recovery: the 200MB static start guard was below the observed
    # 204–218MB service baseline. We keep hard 300MB and dynamically give the
    # heavy-slot start check enough headroom above baseline.
    try:
        import app as app_module
        original_acquire = getattr(app_module, "_acquire_heavy_analysis", None)
        if callable(original_acquire) and not getattr(original_acquire, "_cpqe_memory_19_2_4", False):
            @wraps(original_acquire)
            def adaptive_acquire(owner, timeout=None):
                previous = getattr(app_module, "_MEMORY_JOB_START_LIMIT_MB", None)
                try:
                    rss = app_module._process_rss_mb() if hasattr(app_module, "_process_rss_mb") else None
                    hard = _f(getattr(app_module, "_MEMORY_HARD_LIMIT_MB", 300), 300)
                    baseline = _f(getattr(app_module, "_FREE_RUNTIME_THREAD_BASELINE", 0), 0)
                    # Dynamic ceiling: never above hard-25 and never below the
                    # old configured limit. This fixes false BUSY at ~204–218MB.
                    if rss is not None:
                        dynamic = min(max(_f(previous, 200), float(rss) + 50.0), max(225.0, hard - 25.0))
                        setattr(app_module, "_MEMORY_JOB_START_LIMIT_MB", dynamic)
                    return original_acquire(owner, timeout)
                finally:
                    if previous is not None:
                        setattr(app_module, "_MEMORY_JOB_START_LIMIT_MB", previous)
            adaptive_acquire._cpqe_memory_19_2_4 = True
            app_module._acquire_heavy_analysis = adaptive_acquire
            status["memory"] = True

            # Small backoff/dedup script injected into HTML responses. It does
            # not add a fetch; it only throttles duplicate heavy analysis calls.
            try:
                @app.after_request
                def _cpqe_19_2_4_frontend_recovery(response):
                    ctype = str(response.headers.get("Content-Type") or "")
                    if "text/html" not in ctype:
                        return response
                    try:
                        body = response.get_data(as_text=True)
                        marker = "/static/commit19_2_4_recovery.js"
                        if marker not in body and "</body>" in body:
                            body = body.replace("</body>", f'<script src="{marker}"></script></body>', 1)
                            response.set_data(body)
                            response.headers["Content-Length"] = str(len(response.get_data()))
                            status["frontend"] = True
                    except Exception:
                        pass
                    return response
            except Exception:
                pass
    except Exception as exc:
        status["memory_error"] = str(exc)[:180]
    return status
