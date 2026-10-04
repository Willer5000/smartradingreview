"""Commit 24.3 — Q-Cluster authority + preemptive UI runtime.

The module is loaded after the existing Commit 23.1/24.x boot chain. It does not
create permanent workers, add runtime network calls, or lower the hard publication
contract. It adds a deterministic promotion path only after the existing universal
guards pass, and coordinates the already-existing single heavy-analysis lock with a
bounded in-process UI queue.
"""
from __future__ import annotations

import math
import os
import statistics
import threading
import time
from functools import wraps
from typing import Any, Dict, Mapping, Tuple

VERSION = "COMMIT24.3_Q_CLUSTER_PREEMPTIVE_RUNTIME_V1"
QUALITY_AUTHORITY_VERSION = "COMMIT24.3_TEN_FILTER_CLUSTER_AUTHORITY_V1"
Q_MIN_SCORE = 75.0
Q_CLUSTER_MIN_AVG = float(os.environ.get("Q_CLUSTER_MIN_AVG", "72") or 72)
Q_CLUSTER_MIN_TWO = float(os.environ.get("Q_CLUSTER_MIN_TWO", "70") or 70)
Q_CLUSTER_STD_MIN = float(os.environ.get("Q_CLUSTER_STD_MIN", "5") or 5)
Q_CLUSTER_ENABLED = str(os.environ.get("Q_CLUSTER_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"}
Q_CLUSTER_GEOMETRIC = ("Q3", "Q6", "Q7", "Q9")
OPERATING_SAFETY_FLOOR = 65.0
MAX_SL_LOSS_PCT = 8.0
MAX_ATR_STRESS_PCT = 25.0
ALLOWED_LEGACY_BLOCKERS = {"SAFETY", "TP_QUALITY", "SL_QUALITY", "RR"}
UI_PENDING_MAX = max(1, int(os.environ.get("UI_PENDING_MAX", "5") or 5))
STALL_EXIT_SECONDS = max(60.0, float(os.environ.get("STALL_EXIT_SECONDS", os.environ.get("COMMIT24_STALL_EXIT_SECONDS", "105")) or 105))

_ORIGINALS: Dict[str, Any] = {}
_INSTALL_RESULT: Dict[str, Any] = {}
_INSTALLED = False
_STATE_LOCK = threading.RLock()
_HOLDER_STARTED_AT = 0.0
_HOLDER_OWNER = ""
_UI_DRAINING = False
_METRICS_LOCK = threading.Lock()
_METRICS = {
    "q_cluster_enabled": Q_CLUSTER_ENABLED,
    "q_cluster_evaluations": 0,
    "q_cluster_eligible": 0,
    "q_cluster_promotions": 0,
    "q_cluster_rejections": 0,
    "direct_q_promotions": 0,
    "dedupe_dropped": 0,
    "ui_queue_enqueued": 0,
    "ui_queue_dropped_oldest": 0,
    "ui_queue_drains": 0,
    "ui_queue_drained_items": 0,
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _action(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return {
        "BULLISH": "LONG", "BUY": "LONG", "COMPRA": "LONG", "COMPRA_SPOT": "LONG",
        "BEARISH": "SHORT", "SELL": "SHORT", "VENTA": "SHORT", "VENTA_SPOT": "SHORT",
    }.get(raw, raw)


def _levels(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    block = (result or {}).get("levels")
    return dict(block) if isinstance(block, Mapping) else {}


def _gate(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    result = result or {}
    levels = _levels(result)
    block = result.get("futures_publication_gate") or levels.get("futures_publication_gate")
    return dict(block) if isinstance(block, Mapping) else {}


def _explicit_stage(result: Mapping[str, Any] | None) -> str:
    result = result or {}
    levels = _levels(result)
    trace = levels.get("futures_filter_trace") or result.get("futures_filter_trace") or {}
    if not isinstance(trace, Mapping):
        trace = {}
    raw = (
        result.get("futures_filter_stage") or trace.get("stage") or levels.get("futures_filter_stage")
        or _gate(result).get("stage") or ""
    )
    return str(raw or "").strip().upper()


def _geometry_ok(action: str, levels: Mapping[str, Any]) -> bool:
    e, sl, tp = _f(levels.get("entry")), _f(levels.get("stop_loss")), _f(levels.get("take_profit"))
    if min(e, sl, tp) <= 0:
        return False
    return (sl < e < tp) if action == "LONG" else (tp < e < sl) if action == "SHORT" else False


def _rr(action: str, levels: Dict[str, Any]) -> float:
    e, sl, tp = _f(levels.get("entry")), _f(levels.get("stop_loss")), _f(levels.get("take_profit"))
    risk = abs(e - sl)
    if risk <= 0:
        return 0.0
    rr = abs(tp - e) / risk
    levels["risk_reward"] = round(rr, 4)
    return rr


def _revalue_safety_for_geometry(app_module: Any, result: Dict[str, Any], action: str) -> Dict[str, Any]:
    levels = dict(result.get("levels") or {})
    if not levels:
        return result
    try:
        futures = app_module._get_futures_system()
        calc = getattr(futures, "_calculate_execution_safety", None) if futures else None
        if callable(calc):
            safety = calc(levels, result.get("trend") or {}, result.get("momentum") or {}, result.get("structure") or {}, str(result.get("timeframe") or ""))
            if isinstance(safety, Mapping) and _f(safety.get("score")) > 0:
                levels["execution_safety"] = round(_f(safety.get("score")), 2)
                levels["execution_safety_label"] = safety.get("label")
                levels["execution_safety_components"] = dict(safety.get("components") or {})
    except Exception:
        pass
    try:
        risk_control = dict(levels.get("risk_control") or {})
        leverage = _f(levels.get("leverage"), 0.0)
        allocation = _f(levels.get("risk_allocation_fraction"), _f(risk_control.get("risk_allocation_fraction"), -1.0))
        e, sl = _f(levels.get("entry")), _f(levels.get("stop_loss"))
        if leverage > 0 and 0.0 < allocation <= 1.0 and e > 0 and sl > 0:
            sl_pct = abs(e - sl) / e * 100.0
            risk_control["estimated_sl_loss_pct_margin"] = round(sl_pct * leverage * allocation, 2)
            risk_control["estimated_sl_loss_pct_position_margin"] = round(sl_pct * leverage, 2)
            risk_control["sl_loss_revaluation_source"] = "COMMIT24.3_GEOMETRY_PLUS_EXISTING_RISK_ALLOCATION"
            levels["risk_control"] = risk_control
    except Exception:
        pass
    result["levels"] = levels
    return result


def _q_scores_from_parallel(parallel: Mapping[str, Any]) -> Dict[str, float]:
    raw = parallel.get("filter_scores")
    if isinstance(raw, Mapping):
        scores = {str(k).upper(): _f(v) for k, v in raw.items() if str(k).upper().startswith("Q")}
        if len(scores) >= 9:
            return {f"Q{i}": _f(scores.get(f"Q{i}")) for i in range(1, 11)}
    rows = parallel.get("filters") or []
    scores = {}
    for row in rows:
        if isinstance(row, Mapping):
            name = str(row.get("filter") or "").upper()
            if name.startswith("Q"):
                scores[name] = _f(row.get("score"))
    return {f"Q{i}": _f(scores.get(f"Q{i}")) for i in range(1, 11)}


def _apply_q_cluster_boost(base_scores: Mapping[str, float], evaluated: Mapping[str, Any]) -> Dict[str, float]:
    """24.3: replace only geometric Q cluster lanes with raw Q evidence from the same evaluation.

    This is deliberately *not* an arbitrary +N bonus. The Q engine already computes
    Q3/Q6/Q7/Q9 directly from validated geometry/context. The cluster review uses
    those raw deterministic values as the geometric re-evaluation, preserving the
    underlying evidence and avoiding invented data.
    """
    boosted = {f"Q{i}": round(_f(base_scores.get(f"Q{i}")), 2) for i in range(1, 11)}
    raw_quality = evaluated.get("quality") if isinstance(evaluated, Mapping) else {}
    if not isinstance(raw_quality, Mapping):
        return boosted
    for name in Q_CLUSTER_GEOMETRIC:
        raw = _f(raw_quality.get(name), -1.0)
        if raw >= 0:
            boosted[name] = round(max(boosted.get(name, 0.0), raw), 2)
    return boosted


def _evaluate_q_cluster(parallel: Mapping[str, Any], evaluated: Mapping[str, Any]) -> Dict[str, Any]:
    """24.3: cluster eligibility and deterministic geometric review."""
    scores = _q_scores_from_parallel(parallel)
    ordered = sorted(scores.values(), reverse=True)
    top3_avg = sum(ordered[:3]) / 3.0 if len(ordered) >= 3 else 0.0
    two_ge70 = sum(1 for score in scores.values() if score >= Q_CLUSTER_MIN_TWO) >= 2
    stddev = statistics.pstdev(list(scores.values())) if len(scores) >= 2 else 0.0
    eligible = bool(Q_CLUSTER_ENABLED and top3_avg >= Q_CLUSTER_MIN_AVG and two_ge70 and stddev >= Q_CLUSTER_STD_MIN)
    boosted = _apply_q_cluster_boost(scores, evaluated) if eligible else dict(scores)
    geometric_hits = [name for name in Q_CLUSTER_GEOMETRIC if boosted.get(name, 0.0) >= Q_MIN_SCORE]
    winner = max(geometric_hits, key=lambda name: boosted[name]) if geometric_hits else None
    return {
        "enabled": Q_CLUSTER_ENABLED,
        "eligible": eligible,
        "top3_avg": round(top3_avg, 2),
        "q70_count": sum(1 for score in scores.values() if score >= Q_CLUSTER_MIN_TWO),
        "stddev": round(stddev, 2),
        "variance": round(stddev * stddev, 2),
        "base_scores": scores,
        "boosted_scores": boosted,
        "geometric_qs": list(Q_CLUSTER_GEOMETRIC),
        "geometric_hits": geometric_hits,
        "winner": winner,
        "reason": (
            "Q_CLUSTER_GEOMETRIC_REVIEW_CROSSED_75" if winner else
            "Q_CLUSTER_REVIEW_DID_NOT_CROSS_75" if eligible else
            "Q_CLUSTER_NOT_ELIGIBLE"
        ),
    }


def _build_q_evaluation(app_module: Any, result: Dict[str, Any], action: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    levels = dict(result.get("levels") or {})
    try:
        import quality_9q_engine_21 as q9_module
    except Exception:
        return result, {"confirmed": False, "reason": "Q_ENGINE_UNAVAILABLE", "score": 0.0, "authority": "NONE"}
    if not _geometry_ok(action, levels):
        return result, {"confirmed": False, "reason": "INVALID_ENTRY_SL_TP", "score": 0.0, "authority": "NONE"}
    if _rr(action, levels) <= 0:
        return result, {"confirmed": False, "reason": "INVALID_RR", "score": 0.0, "authority": "NONE"}

    trend = result.get("trend") or {}
    momentum = result.get("momentum") or {}
    volatility = result.get("volatility") or {}
    structure = result.get("structure") or {}
    for source_key, target_key in (("futures_microstructure_context", "market_microstructure"), ("futures_quantitative_context", "quantitative_context")):
        block = result.get(source_key)
        if isinstance(block, Mapping) and block and not levels.get(target_key):
            levels[target_key] = dict(block)
    op = result.get("operational_intelligence") or {}
    if isinstance(op, Mapping):
        for key in ("candidate_action", "coverage_route_state", "validated_strategy_route", "strategy_reasoning_17_5_9", "thesis", "default_strategy"):
            if op.get(key) is not None and levels.get(key) is None:
                levels[key] = op.get(key)
    stage = _explicit_stage(result)
    levels["futures_filter_stage"] = stage

    try:
        evaluated = q9_module.evaluate(
            levels=levels, trend=trend, momentum=momentum, volatility=volatility, structure=structure,
            timeframe=str(result.get("timeframe") or ""), symbol=str(result.get("symbol") or ""),
            action=action, market_type="multiasset" if result.get("is_multiasset") else "futures",
        )
    except Exception as exc:
        return result, {"confirmed": False, "reason": f"Q_EVALUATION_ERROR:{type(exc).__name__}", "score": 0.0, "authority": "NONE"}

    parallel = dict(evaluated.get("parallel_quality_filters") or {})
    rows = parallel.get("filters") or []
    passed_rows = [r for r in rows if isinstance(r, Mapping) and bool(r.get("passed")) and _f(r.get("score")) >= Q_MIN_SCORE]
    passed_rows.sort(key=lambda r: (-_f(r.get("score")), str(r.get("filter") or "")))
    direct = passed_rows[0] if passed_rows else None

    gate = _gate(result)
    gate_codes = [str(x).upper() for x in (gate.get("reason_codes") or [])]
    legacy_blockers = [str(x).upper() for x in (parallel.get("legacy_publication_blockers") or [])]
    if gate_codes:
        legacy_blockers = gate_codes
    synthetic = bool(result.get("market_data_is_synthetic") or levels.get("market_data_is_synthetic"))
    safety = _f(levels.get("execution_safety"))
    risk_control = levels.get("risk_control") if isinstance(levels.get("risk_control"), Mapping) else {}
    sl_loss = _f(risk_control.get("estimated_sl_loss_pct_margin"), abs(_f(levels.get("roi_sl"))))
    atr_stress = _f(risk_control.get("estimated_atr_stress_loss_pct_margin"))
    universal_codes = [str(x).upper() for x in ((parallel.get("universal_guards") or {}).get("codes") or [])]
    if safety < OPERATING_SAFETY_FLOOR and "OPERATIONAL_SAFETY_BELOW_65" not in universal_codes:
        universal_codes.append("OPERATIONAL_SAFETY_BELOW_65")
    if sl_loss > MAX_SL_LOSS_PCT and "LOSS_AT_SL" not in universal_codes:
        universal_codes.append("LOSS_AT_SL")
    if not (0.0 < atr_stress <= MAX_ATR_STRESS_PCT) and "ATR_STRESS" not in universal_codes:
        universal_codes.append("ATR_STRESS")
    if synthetic and "SYNTHETIC_MARKET_DATA" not in universal_codes:
        universal_codes.append("SYNTHETIC_MARKET_DATA")
    if stage != "PUBLICATION_GATE" and "PRE_GATE_REJECTION" not in universal_codes:
        universal_codes.append("PRE_GATE_REJECTION")
    if not _geometry_ok(action, levels) and "INVALID_ENTRY_SL_TP" not in universal_codes:
        universal_codes.append("INVALID_ENTRY_SL_TP")
    if direct is None:
        universal_codes.append("NO_Q_GE75")
    if legacy_blockers and not set(legacy_blockers).issubset(ALLOWED_LEGACY_BLOCKERS):
        universal_codes.append("NON_Q10_LEGACY_BLOCKER")
    seen = set()
    universal_codes = [x for x in universal_codes if not (x in seen or seen.add(x))]

    cluster = _evaluate_q_cluster(parallel, evaluated)
    with _METRICS_LOCK:
        if cluster["eligible"]:
            _METRICS["q_cluster_eligible"] += 1
        if direct is None:
            _METRICS["q_cluster_evaluations"] += 1
        if cluster["eligible"] and not cluster["winner"]:
            _METRICS["q_cluster_rejections"] += 1

    authority_row = direct
    cluster_confirmed = bool(cluster["eligible"] and cluster["winner"] and not any(code for code in universal_codes if code not in {"NO_Q_GE75"}))
    if direct is not None:
        with _METRICS_LOCK:
            _METRICS["direct_q_promotions"] += 1
    if cluster_confirmed:
        with _METRICS_LOCK:
            _METRICS["q_cluster_promotions"] += 1
        winner = cluster["winner"]
        authority_row = {
            "filter": winner,
            "name": f"{winner} · GEOMETRIC CLUSTER REVIEW",
            "score": cluster["boosted_scores"].get(winner, 0.0),
            "passed": True,
            "evidence": True,
        }
        universal_codes = [code for code in universal_codes if code != "NO_Q_GE75"]

    confirmed = bool(
        authority_row is not None
        and _f(authority_row.get("score")) >= Q_MIN_SCORE
        and stage == "PUBLICATION_GATE"
        and safety >= OPERATING_SAFETY_FLOOR
        and sl_loss <= MAX_SL_LOSS_PCT
        and 0.0 < atr_stress <= MAX_ATR_STRESS_PCT
        and not synthetic
        and not universal_codes
        and (direct is not None or cluster_confirmed)
    )

    # A correlated (<5 stddev) set is rejected only from the cluster route; the
    # existing direct Q>=75 contract remains authoritative.
    authority_mode = "ONE_OF_TEN_QUALITY_FILTERS" if direct is not None else "Q_CLUSTER_GEOMETRIC_REVIEW" if cluster_confirmed else None
    authority = {
        "version": QUALITY_AUTHORITY_VERSION,
        "repair_version": VERSION,
        "confirmed": confirmed,
        "authority": str(authority_row.get("filter") or "NONE") if confirmed else "NONE",
        "authority_name": str(authority_row.get("name") or "") if confirmed else "",
        "score": round(_f(authority_row.get("score")) if authority_row else 0.0, 2),
        "passed_filters": [str(r.get("filter")).upper() for r in (parallel.get("filters") or []) if isinstance(r, Mapping) and bool(r.get("passed"))],
        "selected_filter_passed": bool(direct),
        "summary": str(parallel.get("summary") or ""),
        "stage": stage,
        "legacy_blockers": legacy_blockers,
        "universal_guard_codes": universal_codes,
        "safety": round(safety, 2),
        "sl_loss_pct": round(sl_loss, 2),
        "atr_stress_pct": round(atr_stress, 2),
        "q10_required": False,
        "dedupe_key": _dedupe_key(result),
        "confirmation_mode": authority_mode,
        "q_cluster": cluster,
    }

    result = dict(result)
    result["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
    result["quality_filter_version"] = QUALITY_AUTHORITY_VERSION
    result["quality_filter_authority"] = authority["authority"]
    result["quality_filter_name"] = authority["authority_name"]
    result["quality_filter_score"] = authority["score"]
    result["quality_filter_passed"] = authority["passed_filters"]
    result["quality_filter_confirmed"] = confirmed
    result["quality_filter_summary"] = authority["summary"]
    result["quality_filter_membership"] = authority["passed_filters"]
    result["parallel_quality_filters"] = parallel
    result["parallel_quality_guard_codes"] = universal_codes
    result["final_quality_authority"] = authority
    result["final_quality_authority_version"] = VERSION
    result["q_cluster_review"] = cluster

    levels = dict(result.get("levels") or {})
    levels.update({
        "quality_filter_authority": authority["authority"],
        "quality_filter_name": authority["authority_name"],
        "quality_filter_score": authority["score"],
        "quality_filter_confirmed": confirmed,
        "quality_filter_passed": authority["passed_filters"],
        "quality_filter_summary": authority["summary"],
        "quality_filter_membership": authority["passed_filters"],
        "parallel_quality_filters": parallel,
        "parallel_quality_guard_codes": universal_codes,
        "quality_authority_version": QUALITY_AUTHORITY_VERSION,
        "quality_authority_repair_version": VERSION,
        "q_cluster_review": cluster,
    })
    result["levels"] = levels
    if confirmed:
        levels["publication_status"] = "EXECUTABLE_SIGNAL"
        levels["publication_eligible"] = True
        levels["is_rejected"] = False
        levels["is_executable"] = True
        result["publication_status"] = "EXECUTABLE_SIGNAL"
        result["publication_eligible"] = True
        result["is_executable"] = True
        result["is_rejected"] = False
        result["quality_filter_confirmation_mode"] = authority_mode
        result["premium_confirmation_mode"] = authority_mode
        result["premium_blocker_stage_24_3"] = None
        result["quality_authority_reason"] = f"{authority['authority']} {authority['score']:.1f}/100 + universal guards ({authority_mode})."
        levels.pop("manual_geometry_authority", None)
        levels.pop("manual_geometry_fallback_rejected", None)
        result["levels"] = levels
    else:
        result["premium_blocker_stage_24_3"] = ";".join(universal_codes[:8]) or "Q_NOT_AUTHORISED"
    return result, authority


def _normalize_quality_candidate(app_module: Any, result: Dict[str, Any], symbol: str, timeframe: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not isinstance(result, dict) or result.get("success") is False:
        return result, {"confirmed": False, "authority": "NONE", "score": 0.0}
    out = dict(result)
    out.setdefault("symbol", symbol)
    out.setdefault("timeframe", timeframe)
    action = _action(
        ((out.get("levels") or {}).get("manual_observation_action"))
        or ((out.get("decision") or {}).get("action"))
        or ((out.get("operational_intelligence") or {}).get("candidate_action"))
        or ((out.get("decision") or {}).get("original_action"))
        or ((out.get("operational_intelligence") or {}).get("thesis") or {}).get("direction")
    )
    if action not in {"LONG", "SHORT"}:
        return out, {"confirmed": False, "authority": "NONE", "score": 0.0, "reason": "DIRECTION_UNDEFINED"}
    try:
        geometry_fn = getattr(app_module, "_ensure_manual_diagnostic_geometry_175114", None)
        if callable(geometry_fn):
            geometry_fn(out, action, symbol, timeframe)
    except Exception:
        pass
    out = _revalue_safety_for_geometry(app_module, out, action)
    return _build_q_evaluation(app_module, out, action)


def _force_executable_output(out: Dict[str, Any], authority: Mapping[str, Any]) -> Dict[str, Any]:
    if not authority.get("confirmed"):
        return out
    result = dict(out)
    levels = dict(result.get("levels") or {})
    levels.update({
        "publication_status": "EXECUTABLE_SIGNAL", "publication_eligible": True,
        "is_rejected": False, "is_executable": True, "quality_filter_confirmed": True,
        "quality_filter_authority": authority.get("authority"), "quality_filter_score": authority.get("score"),
        "quality_filter_name": authority.get("authority_name"),
    })
    result["levels"] = levels
    result.update({
        "publication_status": "EXECUTABLE_SIGNAL", "publication_eligible": True,
        "is_executable": True, "is_rejected": False, "quality_filter_confirmed": True,
        "quality_filter_authority": authority.get("authority"), "quality_filter_score": authority.get("score"),
        "premium_confirmation_mode": authority.get("confirmation_mode"),
        "final_quality_authority": dict(authority), "quality_authority_version": QUALITY_AUTHORITY_VERSION,
    })
    return result


def _wrap_classifier(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_classify_futures_analysis_result", None)
    if not callable(original) or getattr(original, "_commit24_3_repair", False):
        return {"installed": False, "reason": "CLASSIFIER_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["classifier"] = original
    @wraps(original)
    def wrapped(symbol, timeframe, result, lifecycle=None, min_confidence=0, _original=original):
        enriched, authority = _normalize_quality_candidate(app_module, result, str(symbol), str(timeframe))
        out = _original(symbol=str(symbol), timeframe=str(timeframe), result=enriched, lifecycle=lifecycle, min_confidence=min_confidence)
        if isinstance(out, dict):
            out.update({
                "quality_filter_authority": authority.get("authority"),
                "quality_filter_name": authority.get("authority_name"),
                "quality_filter_score": authority.get("score"),
                "quality_filter_passed": authority.get("passed_filters") or [],
                "quality_filter_confirmed": bool(authority.get("confirmed")),
                "quality_filter_summary": authority.get("summary") or "",
                "quality_filter_membership": authority.get("passed_filters") or [],
                "final_quality_authority": dict(authority),
                "premium_confirmation_mode": authority.get("confirmation_mode") if authority.get("confirmed") else None,
            })
            if authority.get("confirmed"):
                out.update({
                    "classification": "EXECUTABLE_SIGNAL",
                    "engine_publication_status": "EXECUTABLE_SIGNAL",
                    "status_label": f"SEÑAL EJECUTABLE · {authority.get('authority')} {float(authority.get('score') or 0):.0f}/100",
                    "reason": f"Confirmada por {authority.get('authority')} ({float(authority.get('score') or 0):.1f}/100) y guardas universales.",
                    "is_executable": True, "diagnostic_action": None, "manual_save_allowed": True,
                })
                out["result_quality_score"] = authority.get("score")
            elif out.get("classification") == "ANALYSIS_ONLY":
                blockers = authority.get("universal_guard_codes") or []
                if blockers:
                    out["reason"] = "No publicada: " + "; ".join(blockers[:5])
        if isinstance(enriched, dict) and authority.get("confirmed"):
            result.clear()
            result.update(_force_executable_output(enriched, authority))
        return out
    wrapped._commit24_3_repair = True
    app_module._classify_futures_analysis_result = wrapped
    return {"installed": True}


def _wrap_lifecycle(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_refresh_futures_signal_lifecycle", None)
    if not callable(original) or getattr(original, "_commit24_3_repair", False):
        return {"installed": False, "reason": "LIFECYCLE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["lifecycle"] = original
    @wraps(original)
    def wrapped(lifecycle, symbol, timeframe, result, _original=original):
        enriched, authority = _normalize_quality_candidate(app_module, result, str(symbol), str(timeframe))
        if authority.get("confirmed"):
            enriched = _force_executable_output(enriched, authority)
        return _original(lifecycle, symbol, timeframe, enriched)
    wrapped._commit24_3_repair = True
    app_module._refresh_futures_signal_lifecycle = wrapped
    return {"installed": True}


def _market_product(row: Mapping[str, Any]) -> str:
    raw = str(row.get("market") or row.get("market_type") or "futures").strip().upper()
    if raw in {"SPOT", "FUTURES", "MULTIASSET", "MULTI-ASSET", "MULTI"}:
        return "MULTIASSET" if raw in {"MULTI-ASSET", "MULTI"} else raw
    return "MULTIASSET" if bool(row.get("is_multiasset")) else "FUTURES"


def _dedupe_key(candidate: Mapping[str, Any]) -> str:
    symbol = str(candidate.get("symbol") or "").upper().replace("/", "-")
    timeframe = str(candidate.get("timeframe") or "")
    thesis = candidate.get("thesis") if isinstance(candidate.get("thesis"), Mapping) else {}
    decision = candidate.get("decision") if isinstance(candidate.get("decision"), Mapping) else {}
    direction = _action(
        candidate.get("direction")
        or candidate.get("action")
        or decision.get("action")
        or thesis.get("direction")
        or candidate.get("original_action")
    )
    direction = direction if direction in {"LONG", "SHORT"} else "UNKNOWN"
    product = _market_product(candidate)
    return f"{product}|{symbol}|{timeframe}|{direction}"


def _dedupe_candidates(candidates):
    """24.3 final dedupe by market×symbol×TF×direction."""
    best = {}
    dropped = 0
    for item in candidates or []:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        key = _dedupe_key(row)
        rank = (
            1 if row.get("quality_filter_confirmed") else 0,
            _f(row.get("quality_filter_score")),
            _f(row.get("confidence")),
            _f(row.get("risk_reward")),
        )
        previous = best.get(key)
        if previous is None or rank > previous[0]:
            if previous is not None:
                dropped += 1
            best[key] = (rank, row)
        else:
            dropped += 1
    with _METRICS_LOCK:
        _METRICS["dedupe_dropped"] += dropped
    return [pair[1] for pair in sorted(best.values(), key=lambda pair: (-pair[0][0], -pair[0][1], -pair[0][2], -pair[0][3], _dedupe_key(pair[1])))]


def _wrap_hidden_candidates(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_futures_directional_hidden_candidates", None)
    if not callable(original) or getattr(original, "_commit24_3_repair", False):
        return {"installed": False, "reason": "HIDDEN_CANDIDATES_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["hidden_candidates"] = original
    @wraps(original)
    def wrapped(visibility, source_context, representative_ids=None, _original=original):
        rows = _original(visibility, source_context, representative_ids=representative_ids) or []
        out = []
        for row in rows:
            item = dict(row)
            authority = dict(item.get("final_quality_authority") or {})
            item["quality_filter_membership"] = authority.get("passed_filters") or item.get("quality_filter_membership") or []
            item["quality_filter_authority"] = authority.get("authority") or "NONE"
            item["quality_filter_score"] = authority.get("score") or 0
            item["quality_filter_confirmed"] = bool(authority.get("confirmed"))
            item["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
            item["quality_repair_version"] = VERSION
            out.append(item)
        return _dedupe_candidates(out)
    wrapped._commit24_3_repair = True
    app_module._futures_directional_hidden_candidates = wrapped
    return {"installed": True}


def _wrap_multiasset_diagnostics(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_multiasset_directional_diagnostics_17511", None)
    if not callable(original) or getattr(original, "_commit24_3_repair", False):
        return {"installed": False, "reason": "MULTI_DIAGNOSTICS_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["multi_diag"] = original
    @wraps(original)
    def wrapped(analyses, _original=original):
        enriched = {}
        for key, raw in (analyses or {}).items():
            if not isinstance(raw, dict):
                enriched[key] = raw
                continue
            symbol = str(raw.get("symbol") or (key[0] if isinstance(key, tuple) and key else ""))
            timeframe = str(raw.get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else ""))
            copy_raw, authority = _normalize_quality_candidate(app_module, raw, symbol, timeframe)
            if authority.get("confirmed"):
                copy_raw = _force_executable_output(copy_raw, authority)
            enriched[key] = copy_raw
        rows = _original(enriched) or []
        out = []
        for row in rows:
            item = dict(row)
            target = None
            for key, raw in enriched.items():
                rs = str((raw or {}).get("symbol") or (key[0] if isinstance(key, tuple) and key else "")) if isinstance(raw, Mapping) else ""
                rt = str((raw or {}).get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else "")) if isinstance(raw, Mapping) else ""
                if rs.upper().replace("/", "-") == str(item.get("symbol") or "").upper().replace("/", "-") and rt == str(item.get("timeframe") or ""):
                    target = raw
                    break
            authority = dict((target or {}).get("final_quality_authority") or {}) if isinstance(target, Mapping) else {}
            item.update({
                "quality_filter_authority": authority.get("authority") or "NONE",
                "quality_filter_name": authority.get("authority_name") or "",
                "quality_filter_score": authority.get("score") or 0,
                "quality_filter_confirmed": bool(authority.get("confirmed")),
                "quality_filter_membership": authority.get("passed_filters") or [],
                "quality_filter_summary": authority.get("summary") or "",
            })
            if authority.get("confirmed"):
                item.update({
                    "classification": "EXECUTABLE_SIGNAL",
                    "status_label": f"SEÑAL EJECUTABLE · {authority.get('authority')} {float(authority.get('score') or 0):.0f}/100",
                    "reason": f"Confirmada por {authority.get('authority')} ({float(authority.get('score') or 0):.1f}/100) + guardas universales.",
                    "is_executable": True, "diagnostic_only": False,
                })
            out.append(item)
        return _dedupe_candidates(out)
    wrapped._commit24_3_repair = True
    app_module._multiasset_directional_diagnostics_17511 = wrapped
    return {"installed": True}


def _pending_snapshot(app_module: Any):
    getter = getattr(app_module, "_get_pending_ui_analysis_snapshot", None)
    if callable(getter):
        try:
            return getter() or []
        except Exception:
            return []
    return []


def _record_queue_enqueue(dropped: bool = False):
    """# 24.3: métricas livianas de encolado; no hace I/O ni crea threads."""
    with _METRICS_LOCK:
        _METRICS["ui_queue_enqueued"] += 1
        if dropped:
            _METRICS["ui_queue_dropped_oldest"] += 1


def _maybe_stall_exit(app_module: Any):
    pending = _pending_snapshot(app_module)
    with _STATE_LOCK:
        owner = _HOLDER_OWNER
        started = _HOLDER_STARTED_AT
    age = time.monotonic() - started if started else 0.0
    if pending and owner and age > STALL_EXIT_SECONDS:
        print(f"🚨 [COMMIT24.3] holder stall {age:.1f}s with {len(pending)} pending UI; recycling worker", flush=True)
        os._exit(1)


def _wrap_heavy_acquire(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_acquire_heavy_analysis", None)
    if not callable(original) or getattr(original, "_commit24_3_repair", False):
        return {"installed": False, "reason": "HEAVY_ACQUIRE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["acquire"] = original
    @wraps(original)
    def wrapped(owner, timeout=None, _original=original):
        owner_text = str(owner or "heavy-analysis")
        if (not owner_text.startswith(("futures-ui:", "spot-ui:", "multi-ui:", "multiasset-ui:"))) and _pending_snapshot(app_module):
            print(f"⏸️ [COMMIT24.3] {owner_text}: pending interactive UI has priority", flush=True)
            return False
        if _UI_DRAINING and not owner_text.startswith(("futures-ui:", "spot-ui:", "multi-ui:", "multiasset-ui:")):
            return False
        if owner_text.startswith(("futures-ui:", "spot-ui:", "multi-ui:", "multiasset-ui:")):
            try:
                app_module._mark_system_interactive_priority(seconds=120)
            except Exception:
                pass
            safe_timeout = 0.0 if timeout is None else max(0.0, float(timeout))
        else:
            # 24.3: background work never waits on the heavy lock. This avoids
            # blocked worker threads winning the race when UI releases it.
            safe_timeout = 0.0
        acquired = _original(owner_text, timeout=safe_timeout)
        if acquired:
            global _HOLDER_STARTED_AT, _HOLDER_OWNER
            with _STATE_LOCK:
                _HOLDER_STARTED_AT = time.monotonic()
                _HOLDER_OWNER = owner_text
        return acquired
    wrapped._commit24_3_repair = True
    app_module._acquire_heavy_analysis = wrapped
    return {"installed": True}


def _release_heavy_lock_and_drain_queue(app_module: Any):
    global _UI_DRAINING
    # 24.3: impedir drains recursivos cuando el análisis de la propia cola
    # libera el heavy lock. El worker exterior conserva el control FIFO.
    if _UI_DRAINING:
        return 0
    getter = getattr(app_module, "_get_pending_ui_analysis_snapshot", None)
    pending = getter() if callable(getter) else []
    if not pending:
        return 0
    drained = 0
    _UI_DRAINING = True
    try:
        drain = getattr(app_module, "_drain_ui_analysis_queue", None)
        if callable(drain):
            max_items = min(UI_PENDING_MAX, len(pending))
            drained = int(drain(max_items=max_items) or 0)
    finally:
        _UI_DRAINING = False
    with _METRICS_LOCK:
        _METRICS["ui_queue_drains"] += 1 if drained else 0
        _METRICS["ui_queue_drained_items"] += drained
    return drained


def _wrap_heavy_release(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_release_heavy_analysis", None)
    if not callable(original) or getattr(original, "_commit24_3_repair", False):
        return {"installed": False, "reason": "HEAVY_RELEASE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["release"] = original
    @wraps(original)
    def wrapped(owner, _original=original):
        global _HOLDER_STARTED_AT, _HOLDER_OWNER
        try:
            return _original(owner)
        finally:
            with _STATE_LOCK:
                _HOLDER_STARTED_AT = 0.0
                _HOLDER_OWNER = ""
            _release_heavy_lock_and_drain_queue(app_module)
    wrapped._commit24_3_repair = True
    app_module._release_heavy_analysis = wrapped
    return {"installed": True}


def _wrap_ui_start(app_module: Any) -> Dict[str, Any]:
    # 24.3: the actual queue lives in app.py so the same worker that releases the
    # lock can drain it. We intentionally do not wrap the function with another
    # thread-based waiter.
    fn = getattr(app_module, "_start_futures_ui_analysis_async", None)
    if not callable(fn):
        return {"installed": False, "reason": "UI_START_NOT_FOUND"}
    return {"installed": True, "mode": "APP_NATIVE_PREEMPTIVE_QUEUE", "function": fn.__name__}


def _install_health(app_module: Any) -> Dict[str, Any]:
    try:
        import commit24_3_health as health_module
        return health_module.install(app_module, globals())
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}:{str(exc)[:180]}"}


def install(app: Any) -> Dict[str, Any]:
    global _INSTALLED, _INSTALL_RESULT
    if _INSTALLED:
        return dict(_INSTALL_RESULT)
    app_module = __import__("app")
    _INSTALL_RESULT = {
        "version": VERSION,
        "installed": True,
        "classifier": _wrap_classifier(app_module),
        "lifecycle": _wrap_lifecycle(app_module),
        "hidden_candidates": _wrap_hidden_candidates(app_module),
        "multiasset_diagnostics": _wrap_multiasset_diagnostics(app_module),
        "heavy_acquire": _wrap_heavy_acquire(app_module),
        "heavy_release": _wrap_heavy_release(app_module),
        "ui_start": _wrap_ui_start(app_module),
        "health": _install_health(app_module),
        "policy": {
            "q_min_score": Q_MIN_SCORE,
            "q_cluster_enabled": Q_CLUSTER_ENABLED,
            "q_cluster_min_avg": Q_CLUSTER_MIN_AVG,
            "q_cluster_min_two": Q_CLUSTER_MIN_TWO,
            "q_cluster_std_min": Q_CLUSTER_STD_MIN,
            "q10_is_mandatory": False,
            "operational_safety_floor": OPERATING_SAFETY_FLOOR,
            "max_sl_loss_pct": MAX_SL_LOSS_PCT,
            "max_atr_stress_pct": MAX_ATR_STRESS_PCT,
            "allowed_legacy_blockers": sorted(ALLOWED_LEGACY_BLOCKERS),
            "ui_pending_max": UI_PENDING_MAX,
            "stall_exit_seconds": STALL_EXIT_SECONDS,
            "dedupe_key_mode": "symbol|timeframe|direction",
        },
    }
    app_module.COMMIT24_RUNTIME = _INSTALL_RESULT
    _INSTALLED = True
    print(f"✅ [{VERSION}] runtime installed", flush=True)
    return dict(_INSTALL_RESULT)


def audit() -> Dict[str, Any]:
    with _METRICS_LOCK:
        metrics = dict(_METRICS)
    return {
        "version": VERSION,
        "quality_authority_version": QUALITY_AUTHORITY_VERSION,
        "q_min_score": Q_MIN_SCORE,
        "q_cluster_enabled": Q_CLUSTER_ENABLED,
        "q_cluster_min_avg": Q_CLUSTER_MIN_AVG,
        "q_cluster_std_min": Q_CLUSTER_STD_MIN,
        "q10_is_mandatory": False,
        "thresholds_lowered": False,
        "new_market_data_requests": False,
        "new_permanent_workers": False,
        "interactive_queue": True,
        "no_waiting_threads_for_ui_lock": True,
        "bounded_stall_recycle": True,
        "stall_exit_seconds": STALL_EXIT_SECONDS,
        "dedupe_key_mode": "symbol|timeframe|direction",
        "metrics": metrics,
    }
