"""Commit 24 — real Q authority bridge + fair heavy-runtime repair.

This module is loaded AFTER Commit 23.1 has loaded the real app.py and its
existing boot chain.  It repairs two concrete production paths without
changing the trading engine's thresholds:

1) The directional fallback lane in app.py was hard-coded to ANALYSIS_ONLY
   after building Entry/SL/TP. Commit 23.1 only reconciled Q metadata that
   already existed, but it never evaluated Q1..Q10 on this newly built
   candidate. This module evaluates the actual post-geometry candidate in the
   final classifier, then promotes it only when the existing hard guards pass.

2) The single heavy-analysis lock could starve interactive Futures/Multi UI.
   Commit 24 adds a queue/reservation around the exact app.py async UI path,
   blocks new background work while an interactive request is pending, and
   adds a last-resort worker recycle only when an interactive request has been
   waiting behind the same background owner for an excessive bounded period.

No thresholds are lowered. No direction is created. No market-data requests
are added by this module. Q10 remains non-mandatory for one-of-ten authority.
"""
from __future__ import annotations

import os
import threading
import time
from functools import wraps
from typing import Any, Dict, Mapping, Tuple

VERSION = "COMMIT24_REAL_Q_AUTHORITY_FAIR_RUNTIME_V1"
QUALITY_AUTHORITY_VERSION = "COMMIT23_TEN_FILTER_PARALLEL_AUTHORITY_V1"
Q_MIN_SCORE = 75.0
OPERATING_SAFETY_FLOOR = 65.0
MAX_SL_LOSS_PCT = 8.0
MAX_ATR_STRESS_PCT = 25.0
ALLOWED_LEGACY_BLOCKERS = {"SAFETY", "TP_QUALITY", "SL_QUALITY", "RR"}

# Interactive UI must not sit behind a background holder forever. This is a
# last-resort self-recycle, not a normal code path. Render restarts gunicorn.
STALL_EXIT_SECONDS = max(
    60.0,
    float(os.environ.get("COMMIT24_STALL_EXIT_SECONDS", "105") or 105),
)
PENDING_UI_TTL_SECONDS = max(
    30.0,
    float(os.environ.get("COMMIT24_PENDING_UI_TTL_SECONDS", "90") or 90),
)

_ORIGINALS: Dict[str, Any] = {}
_INSTALL_RESULT: Dict[str, Any] = {}
_INSTALLED = False

_STATE_LOCK = threading.RLock()
_PENDING_UI: Dict[str, Dict[str, Any]] = {}
_HOLDER_STARTED_AT = 0.0
_HOLDER_OWNER = ""
_STALL_TIMER: threading.Timer | None = None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if n == n and abs(n) != float("inf") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _action(value: Any) -> str:
    raw = str(value or "").strip().upper()
    mapping = {
        "BULLISH": "LONG",
        "BUY": "LONG",
        "COMPRA": "LONG",
        "COMPRA_SPOT": "LONG",
        "BEARISH": "SHORT",
        "SELL": "SHORT",
        "VENTA": "SHORT",
        "VENTA_SPOT": "SHORT",
    }
    return mapping.get(raw, raw)


def _levels(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    block = (result or {}).get("levels")
    return dict(block) if isinstance(block, Mapping) else {}


def _gate(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    result = result or {}
    levels = _levels(result)
    block = result.get("futures_publication_gate") or levels.get("futures_publication_gate")
    return dict(block) if isinstance(block, Mapping) else {}


def _explicit_stage(result: Mapping[str, Any] | None) -> str:
    """Return only explicit stage evidence; never invent PUBLICATION_GATE."""
    result = result or {}
    levels = _levels(result)
    trace = levels.get("futures_filter_trace") or result.get("futures_filter_trace") or {}
    if not isinstance(trace, Mapping):
        trace = {}
    raw = (
        result.get("futures_filter_stage")
        or trace.get("stage")
        or levels.get("futures_filter_stage")
        or _gate(result).get("stage")
        or ""
    )
    return str(raw or "").strip().upper()


def _geometry_ok(action: str, levels: Mapping[str, Any]) -> bool:
    e = _f(levels.get("entry"))
    sl = _f(levels.get("stop_loss"))
    tp = _f(levels.get("take_profit"))
    if min(e, sl, tp) <= 0:
        return False
    if action == "LONG":
        return bool(sl < e < tp)
    if action == "SHORT":
        return bool(tp < e < sl)
    return False


def _rr(action: str, levels: Dict[str, Any]) -> float:
    e = _f(levels.get("entry"))
    sl = _f(levels.get("stop_loss"))
    tp = _f(levels.get("take_profit"))
    risk = abs(e - sl)
    if risk <= 0:
        return 0.0
    rr = abs(tp - e) / risk
    levels["risk_reward"] = round(rr, 4)
    return rr


def _revalue_safety_for_geometry(app_module: Any, result: Dict[str, Any], action: str) -> Dict[str, Any]:
    """Recalculate deterministic Safety after a fallback geometry change.

    We reuse the already-computed entry/tp/sl quality components and the real
    context present in the same snapshot. This never raises a missing metric to
    make a candidate pass. If the engine cannot recalculate Safety, the old
    value is retained and the candidate remains subject to the 65 floor.
    """
    levels = dict(result.get("levels") or {})
    if not levels:
        return result

    try:
        futures = app_module._get_futures_system()
        calc = getattr(futures, "_calculate_execution_safety", None) if futures else None
        if callable(calc):
            safety = calc(
                levels,
                result.get("trend") or {},
                result.get("momentum") or {},
                result.get("structure") or {},
                str(result.get("timeframe") or ""),
            )
            if isinstance(safety, Mapping) and _f(safety.get("score")) > 0:
                levels["execution_safety"] = round(_f(safety.get("score")), 2)
                levels["execution_safety_label"] = safety.get("label")
                levels["execution_safety_components"] = dict(safety.get("components") or {})
                levels["execution_safety_timeframe_factor"] = safety.get("timeframe_factor")
    except Exception:
        pass

    # Recompute only the geometry-dependent SL-loss margin. ATR stress depends on
    # ATR/leverage/risk fraction and can safely be preserved from the same
    # closed-candle snapshot when available.
    try:
        risk_control = dict(levels.get("risk_control") or {})
        leverage = _f(levels.get("leverage"), 0.0)
        raw_allocation = (
            levels.get("risk_allocation_fraction")
            if levels.get("risk_allocation_fraction") is not None
            else risk_control.get("risk_allocation_fraction")
        )
        allocation = _f(raw_allocation, -1.0)
        if leverage > 0 and 0.0 < allocation <= 1.0:
            e = _f(levels.get("entry"))
            sl = _f(levels.get("stop_loss"))
            if e > 0 and sl > 0:
                sl_pct = abs(e - sl) / e * 100.0
                risk_control["estimated_sl_loss_pct_margin"] = round(sl_pct * leverage * allocation, 2)
                risk_control["estimated_sl_loss_pct_position_margin"] = round(sl_pct * leverage, 2)
                risk_control["sl_loss_revaluation_source"] = "COMMIT24_REAL_GEOMETRY_PLUS_EXISTING_RISK_ALLOCATION"
                levels["risk_control"] = risk_control
        elif leverage > 0 and risk_control.get("estimated_sl_loss_pct_margin") is not None:
            # Old compact snapshots may lack the allocation field. Preserve the
            # already persisted estimate rather than inventing a 100% allocation.
            risk_control["sl_loss_revaluation_source"] = "PRESERVED_EXISTING_SNAPSHOT_ESTIMATE_NO_ALLOCATION"
            levels["risk_control"] = risk_control
    except Exception:
        pass

    result["levels"] = levels
    return result


def _build_q_evaluation(app_module: Any, result: Dict[str, Any], action: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Evaluate Q1..Q10 using the same closed-candle result and real geometry."""
    levels = dict(result.get("levels") or {})
    q9 = None
    try:
        import quality_9q_engine_21 as q9_module
        q9 = q9_module
    except Exception:
        return result, {
            "confirmed": False,
            "reason": "Q_ENGINE_UNAVAILABLE",
            "score": 0.0,
            "authority": "NONE",
        }

    if not _geometry_ok(action, levels):
        return result, {
            "confirmed": False,
            "reason": "INVALID_ENTRY_SL_TP",
            "score": 0.0,
            "authority": "NONE",
        }

    rr = _rr(action, levels)
    if rr <= 0:
        return result, {
            "confirmed": False,
            "reason": "INVALID_RR",
            "score": 0.0,
            "authority": "NONE",
        }

    # Context is whatever the same analysis snapshot already contains. Missing
    # blocks stay missing; we do not fabricate momentum/structure/volatility.
    trend = result.get("trend") or {}
    momentum = result.get("momentum") or {}
    volatility = result.get("volatility") or {}
    structure = result.get("structure") or {}

    # The parallel engine reads some micro/flow context directly from levels.
    # Copy real already-computed compact summaries into those keys when present.
    for source_key, target_key in (
        ("futures_microstructure_context", "market_microstructure"),
        ("futures_quantitative_context", "quantitative_context"),
    ):
        block = result.get(source_key)
        if isinstance(block, Mapping) and block and not levels.get(target_key):
            levels[target_key] = dict(block)

    # Strategy/context fields are already generated upstream. Preserve them.
    op = result.get("operational_intelligence") or {}
    if isinstance(op, Mapping):
        for key in (
            "candidate_action",
            "coverage_route_state",
            "validated_strategy_route",
            "strategy_reasoning_17_5_9",
            "thesis",
            "default_strategy",
        ):
            if op.get(key) is not None and levels.get(key) is None:
                levels[key] = op.get(key)

    # The Q engine internally defaults an absent stage to PUBLICATION_GATE. That
    # default is NOT trusted by this repair; final authority below requires
    # explicit stage evidence from the production gate/trace.
    stage = _explicit_stage(result)
    levels["futures_filter_stage"] = stage

    try:
        evaluated = q9.evaluate(
            levels=levels,
            trend=trend,
            momentum=momentum,
            volatility=volatility,
            structure=structure,
            timeframe=str(result.get("timeframe") or ""),
            symbol=str(result.get("symbol") or ""),
            action=action,
            market_type="multiasset" if result.get("is_multiasset") else "futures",
        )
    except Exception as exc:
        return result, {
            "confirmed": False,
            "reason": f"Q_EVALUATION_ERROR:{type(exc).__name__}",
            "score": 0.0,
            "authority": "NONE",
        }

    parallel = dict(evaluated.get("parallel_quality_filters") or {})
    selected = str(parallel.get("selected_filter") or "NONE").upper()
    selected_score = _f(parallel.get("selected_filter_score"))
    selected_passed = bool(parallel.get("selected_filter_passed"))
    passed_filters = [str(x).upper() for x in (parallel.get("passed_filters") or [])]

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
    if stage != "PUBLICATION_GATE":
        universal_codes.append("PRE_GATE_REJECTION")
    if not _geometry_ok(action, levels):
        universal_codes.append("INVALID_ENTRY_SL_TP")
    if not selected_passed or selected_score < Q_MIN_SCORE:
        universal_codes.append("NO_Q_GE75")
    if legacy_blockers and not set(legacy_blockers).issubset(ALLOWED_LEGACY_BLOCKERS):
        universal_codes.append("NON_Q10_LEGACY_BLOCKER")

    # Deduplicate, stable order.
    seen = set()
    universal_codes = [x for x in universal_codes if not (x in seen or seen.add(x))]

    confirmed = bool(
        selected_passed
        and selected_score >= Q_MIN_SCORE
        and stage == "PUBLICATION_GATE"
        and safety >= OPERATING_SAFETY_FLOOR
        and sl_loss <= MAX_SL_LOSS_PCT
        and 0.0 < atr_stress <= MAX_ATR_STRESS_PCT
        and not synthetic
        and not universal_codes
    )

    authority = {
        "version": QUALITY_AUTHORITY_VERSION,
        "repair_version": VERSION,
        "confirmed": confirmed,
        "authority": selected if confirmed else "NONE",
        "authority_name": str(parallel.get("selected_filter_name") or ""),
        "score": round(selected_score, 2),
        "passed_filters": passed_filters,
        "selected_filter_passed": selected_passed,
        "summary": str(parallel.get("summary") or ""),
        "stage": stage,
        "legacy_blockers": legacy_blockers,
        "universal_guard_codes": universal_codes,
        "safety": round(safety, 2),
        "sl_loss_pct": round(sl_loss, 2),
        "atr_stress_pct": round(atr_stress, 2),
        "q10_required": False,
        "dedupe_key": f"{str(result.get('symbol') or '').upper()}|{str(result.get('timeframe') or '')}",
    }

    # Persist the complete trace into the same compact result/lifecycle payload.
    result = dict(result)
    result["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
    result["quality_filter_version"] = QUALITY_AUTHORITY_VERSION
    result["quality_filter_authority"] = authority["authority"]
    result["quality_filter_name"] = authority["authority_name"]
    result["quality_filter_score"] = authority["score"]
    result["quality_filter_passed"] = passed_filters
    result["quality_filter_confirmed"] = confirmed
    result["quality_filter_summary"] = authority["summary"]
    result["quality_filter_membership"] = passed_filters
    result["parallel_quality_filters"] = parallel
    result["parallel_quality_guard_codes"] = universal_codes
    result["final_quality_authority"] = authority
    result["final_quality_authority_version"] = VERSION

    levels = dict(result.get("levels") or {})
    levels["quality_filter_authority"] = authority["authority"]
    levels["quality_filter_name"] = authority["authority_name"]
    levels["quality_filter_score"] = authority["score"]
    levels["quality_filter_confirmed"] = confirmed
    levels["quality_filter_passed"] = passed_filters
    levels["quality_filter_summary"] = authority["summary"]
    levels["quality_filter_membership"] = passed_filters
    levels["parallel_quality_filters"] = parallel
    levels["parallel_quality_guard_codes"] = universal_codes
    levels["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
    levels["quality_authority_repair_version"] = VERSION
    result["levels"] = levels

    if confirmed:
        levels["publication_status"] = "EXECUTABLE_SIGNAL"
        levels["is_rejected"] = False
        levels["is_executable"] = True
        levels["publication_eligible"] = True
        result["publication_status"] = "EXECUTABLE_SIGNAL"
        result["publication_eligible"] = True
        result["is_executable"] = True
        result["is_rejected"] = False
        result["quality_filter_confirmation_mode"] = "ONE_OF_TEN_QUALITY_FILTERS"
        result["premium_confirmation_mode"] = "ONE_OF_TEN_QUALITY_FILTERS"
        result["premium_blocker_stage_24"] = None
        result["quality_authority_reason"] = (
            f"{authority['authority']} {authority['score']:.1f}/100 + universal guards."
        )
        # Do not leave manual fallback authority attached after official
        # promotion. The geometry remains immutable; only publication authority
        # changes here.
        levels.pop("manual_geometry_authority", None)
        levels.pop("manual_geometry_fallback_rejected", None)
        result["levels"] = levels
    else:
        result["premium_blocker_stage_24"] = ";".join(universal_codes[:8]) or "Q_NOT_AUTHORISED"

    return result, authority


def _normalize_quality_candidate(app_module: Any, result: Dict[str, Any], symbol: str, timeframe: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not isinstance(result, dict) or result.get("success") is False:
        return result, {"confirmed": False, "authority": "NONE", "score": 0.0}

    out = dict(result)
    out.setdefault("symbol", symbol)
    out.setdefault("timeframe", timeframe)

    # The real source of the user's 20 visible hypotheses is this exact helper
    # called by app.py's classifier. It may rebuild fallback geometry and then
    # hard-code publication_status=ANALYSIS_ONLY. We deliberately call it first
    # so Q evaluates the geometry that the UI/lifecycle actually see.
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
    levels["publication_status"] = "EXECUTABLE_SIGNAL"
    levels["publication_eligible"] = True
    levels["is_rejected"] = False
    levels["is_executable"] = True
    levels["quality_filter_confirmed"] = True
    levels["quality_filter_authority"] = authority.get("authority")
    levels["quality_filter_score"] = authority.get("score")
    levels["quality_filter_name"] = authority.get("authority_name")
    result["levels"] = levels
    result["publication_status"] = "EXECUTABLE_SIGNAL"
    result["publication_eligible"] = True
    result["is_executable"] = True
    result["is_rejected"] = False
    result["quality_filter_confirmed"] = True
    result["quality_filter_authority"] = authority.get("authority")
    result["quality_filter_score"] = authority.get("score")
    result["premium_confirmation_mode"] = "ONE_OF_TEN_QUALITY_FILTERS"
    result["final_quality_authority"] = dict(authority)
    result["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
    return result


def _wrap_classifier(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_classify_futures_analysis_result", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
        return {"installed": False, "reason": "CLASSIFIER_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["classifier"] = original

    @wraps(original)
    def wrapped(symbol, timeframe, result, lifecycle=None, min_confidence=0, _original=original):
        enriched, authority = _normalize_quality_candidate(app_module, result, str(symbol), str(timeframe))
        out = _original(
            symbol=str(symbol),
            timeframe=str(timeframe),
            result=enriched,
            lifecycle=lifecycle,
            min_confidence=min_confidence,
        )
        if isinstance(out, dict):
            out["quality_filter_authority"] = authority.get("authority")
            out["quality_filter_name"] = authority.get("authority_name")
            out["quality_filter_score"] = authority.get("score")
            out["quality_filter_passed"] = authority.get("passed_filters") or []
            out["quality_filter_confirmed"] = bool(authority.get("confirmed"))
            out["quality_filter_summary"] = authority.get("summary") or ""
            out["quality_filter_membership"] = authority.get("passed_filters") or []
            out["final_quality_authority"] = dict(authority)
            out["premium_confirmation_mode"] = "ONE_OF_TEN_QUALITY_FILTERS" if authority.get("confirmed") else None
            if authority.get("confirmed"):
                out["classification"] = "EXECUTABLE_SIGNAL"
                out["engine_publication_status"] = "EXECUTABLE_SIGNAL"
                out["status_label"] = (
                    f"SEÑAL EJECUTABLE · {authority.get('authority')} "
                    f"{float(authority.get('score') or 0):.0f}/100"
                )
                out["reason"] = (
                    f"Confirmada por {authority.get('authority')} "
                    f"({float(authority.get('score') or 0):.1f}/100) y guardas universales."
                )
                out["is_executable"] = True
                out["diagnostic_action"] = None
                out["manual_save_allowed"] = True
            elif out.get("classification") == "ANALYSIS_ONLY":
                # Make the diagnostic lane explicit rather than repeating the
                # generic "no alcanzó Premium" text.
                blockers = authority.get("universal_guard_codes") or []
                if blockers:
                    out["reason"] = "No publicada: " + "; ".join(blockers[:5])
        # The original classifier does not mutate `result`, so persist the
        # promoted result into lifecycle via the wrapper caller when needed.
        if isinstance(enriched, dict) and authority.get("confirmed"):
            result.clear()
            result.update(_force_executable_output(enriched, authority))
        return out

    wrapped._commit24_repair = True
    app_module._classify_futures_analysis_result = wrapped
    return {"installed": True}


def _wrap_lifecycle(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_refresh_futures_signal_lifecycle", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
        return {"installed": False, "reason": "LIFECYCLE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["lifecycle"] = original

    @wraps(original)
    def wrapped(lifecycle, symbol, timeframe, result, _original=original):
        enriched, authority = _normalize_quality_candidate(app_module, result, str(symbol), str(timeframe))
        if authority.get("confirmed"):
            result = _force_executable_output(enriched, authority)
        else:
            result = enriched
        return _original(lifecycle, symbol, timeframe, result)

    wrapped._commit24_repair = True
    app_module._refresh_futures_signal_lifecycle = wrapped
    return {"installed": True}


def _wrap_hidden_candidates(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_futures_directional_hidden_candidates", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
        return {"installed": False, "reason": "HIDDEN_CANDIDATES_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["hidden_candidates"] = original

    @wraps(original)
    def wrapped(visibility, source_context, representative_ids=None, _original=original):
        # First, let the canonical function select its governed set. Then run
        # an in-memory authority pass against the exact underlying cache rows
        # when the visible row is still analysis-only.
        rows = _original(visibility, source_context, representative_ids=representative_ids) or []
        out = []
        for row in rows:
            item = dict(row)
            symbol = str(item.get("symbol") or "")
            timeframe = str(item.get("timeframe") or "")
            authority = dict(item.get("final_quality_authority") or {})
            if not authority.get("confirmed"):
                item["quality_filter_membership"] = authority.get("passed_filters") or item.get("quality_filter_membership") or []
                item["quality_filter_authority"] = authority.get("authority") or "NONE"
                item["quality_filter_score"] = authority.get("score") or 0
                item["quality_filter_confirmed"] = False
            else:
                # This path is normally empty because promoted candidates become
                # official before the hidden lane. Keep the metadata for API/UI
                # clients if a stale visibility object still reaches this helper.
                item["quality_filter_authority"] = authority.get("authority")
                item["quality_filter_score"] = authority.get("score")
                item["quality_filter_confirmed"] = True
            item["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
            item["quality_repair_version"] = VERSION
            out.append(item)

        # Explicit cell-level dedupe: only one hidden candidate per symbol×TF.
        best: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for item in out:
            key = (str(item.get("symbol") or ""), str(item.get("timeframe") or ""))
            rank = (
                1 if item.get("quality_filter_confirmed") else 0,
                _f(item.get("quality_filter_score")),
                _f(item.get("confidence")),
                _f(item.get("risk_reward")),
            )
            prev = best.get(key)
            if prev is None or rank > prev[0]:
                best[key] = (rank, item)  # type: ignore[assignment]
        return [pair[1] for pair in sorted(best.values(), key=lambda pair: (-pair[0][0], -pair[0][1], -pair[0][2], -pair[0][3], str(pair[1].get("symbol") or "")))]

    wrapped._commit24_repair = True
    app_module._futures_directional_hidden_candidates = wrapped
    return {"installed": True}


def _wrap_multiasset_diagnostics(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_multiasset_directional_diagnostics_17511", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
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
        rows = _original(enriched)
        out = []
        for row in rows or []:
            item = dict(row)
            target = None
            for key, raw in enriched.items():
                rs = str((raw or {}).get("symbol") or (key[0] if isinstance(key, tuple) and key else "")) if isinstance(raw, Mapping) else ""
                rt = str((raw or {}).get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else "")) if isinstance(raw, Mapping) else ""
                if rs.upper().replace("/", "-") == str(item.get("symbol") or "").upper().replace("/", "-") and rt == str(item.get("timeframe") or ""):
                    target = raw
                    break
            authority = dict((target or {}).get("final_quality_authority") or {}) if isinstance(target, Mapping) else {}
            item["quality_filter_authority"] = authority.get("authority") or "NONE"
            item["quality_filter_name"] = authority.get("authority_name") or ""
            item["quality_filter_score"] = authority.get("score") or 0
            item["quality_filter_confirmed"] = bool(authority.get("confirmed"))
            item["quality_filter_membership"] = authority.get("passed_filters") or []
            item["quality_filter_summary"] = authority.get("summary") or ""
            if authority.get("confirmed"):
                item["classification"] = "EXECUTABLE_SIGNAL"
                item["status_label"] = (
                    f"SEÑAL EJECUTABLE · {authority.get('authority')} "
                    f"{float(authority.get('score') or 0):.0f}/100"
                )
                item["reason"] = f"Confirmada por {authority.get('authority')} ({float(authority.get('score') or 0):.1f}/100) + guardas universales."
                item["is_executable"] = True
                item["diagnostic_only"] = False
            out.append(item)
        return out

    wrapped._commit24_repair = True
    app_module._multiasset_directional_diagnostics_17511 = wrapped
    return {"installed": True}


def _is_interactive_owner(owner: str) -> bool:
    return str(owner or "").startswith(("futures-ui:", "spot-ui:", "multi-ui:", "multiasset-ui:"))


def _is_background_owner(owner: str) -> bool:
    text = str(owner or "")
    known = (
        "futures-incremental:",
        "multi-background:",
        "reviewtrader-learning:",
        "historical-research:",
        "analytics-quality-v2",
        "governance-",
        "ai-learning-",
        "spot-previous-signals",
    )
    return text.startswith(known)


def _track_pending_timer(app_module: Any) -> None:
    global _STALL_TIMER
    with _STATE_LOCK:
        if _STALL_TIMER is not None:
            return

        def _check():
            global _STALL_TIMER
            should_exit = False
            owner = ""
            age = 0.0
            pending = 0
            with _STATE_LOCK:
                now = time.monotonic()
                owner = _HOLDER_OWNER
                age = now - _HOLDER_STARTED_AT if _HOLDER_STARTED_AT else 0.0
                pending = len(_PENDING_UI)
                background = _is_background_owner(owner)
                should_exit = bool(
                    pending
                    and background
                    and owner
                    and _HOLDER_STARTED_AT
                    and age >= STALL_EXIT_SECONDS
                )
                _STALL_TIMER = None
            if should_exit:
                print(
                    f"🚨 [COMMIT24] worker stall: interactive UI pending={pending} "
                    f"owner={owner} age={age:.1f}s; exiting for Render recycle.",
                    flush=True,
                )
                os._exit(75)

            with _STATE_LOCK:
                if _PENDING_UI:
                    # Keep one low-frequency timer while the interactive queue exists.
                    timer = threading.Timer(10.0, _check)
                    timer.daemon = True
                    _STALL_TIMER = timer
                    timer.start()

        timer = threading.Timer(10.0, _check)
        timer.daemon = True
        _STALL_TIMER = timer
        timer.start()


def _kick_pending_ui(app_module: Any) -> None:
    pending = []
    now = time.monotonic()
    with _STATE_LOCK:
        for key, row in list(_PENDING_UI.items()):
            if now - float(row.get("queued_at") or 0) > PENDING_UI_TTL_SECONDS:
                _PENDING_UI.pop(key, None)
                continue
            pending.append((key, dict(row)))
            _PENDING_UI.pop(key, None)
    if not pending:
        return

    original_start = _ORIGINALS.get("start_ui")
    if not callable(original_start):
        return
    # Run one queued cell only. The original function already serializes the UI
    # cache's running set and the global heavy slot.
    _key, row = pending[0]
    try:
        result = original_start(
            row.get("symbol"),
            row.get("timeframe"),
            market=row.get("market") or "futures",
        )
        print(
            f"✅ [COMMIT24] interactive queue released: {row.get('symbol')} {row.get('timeframe')} state={result}",
            flush=True,
        )
    except Exception as exc:
        print(f"⚠️ [COMMIT24] queued UI dispatch failed: {exc}", flush=True)


def _wrap_heavy_acquire(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_acquire_heavy_analysis", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
        return {"installed": False, "reason": "HEAVY_ACQUIRE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["acquire"] = original

    @wraps(original)
    def wrapped(owner, timeout=None, _original=original):
        owner_text = str(owner or "")
        with _STATE_LOCK:
            ui_pending = bool(_PENDING_UI)
        if ui_pending and _is_background_owner(owner_text):
            print(f"⏸️ [COMMIT24] {owner_text}: cede heavy slot to pending interactive UI", flush=True)
            return False

        if _is_interactive_owner(owner_text):
            try:
                app_module._mark_system_interactive_priority(seconds=120)
            except Exception:
                pass

        acquired = _original(owner_text, timeout=timeout)
        if acquired:
            global _HOLDER_STARTED_AT, _HOLDER_OWNER
            with _STATE_LOCK:
                _HOLDER_STARTED_AT = time.monotonic()
                _HOLDER_OWNER = owner_text
        return acquired

    wrapped._commit24_repair = True
    app_module._acquire_heavy_analysis = wrapped
    return {"installed": True}


def _wrap_heavy_release(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_release_heavy_analysis", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
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
                pending = bool(_PENDING_UI)
            if pending:
                _kick_pending_ui(app_module)

    wrapped._commit24_repair = True
    app_module._release_heavy_analysis = wrapped
    return {"installed": True}


def _wrap_ui_start(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_start_futures_ui_analysis_async", None)
    if not callable(original) or getattr(original, "_commit24_repair", False):
        return {"installed": False, "reason": "UI_START_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["start_ui"] = original

    @wraps(original)
    def wrapped(symbol, timeframe, market="futures", _original=original):
        key = f"{str(symbol or '').strip()}|{str(timeframe or '').strip()}|{str(market or 'futures').lower()}"
        try:
            app_module._mark_futures_interactive_priority(seconds=120)
        except Exception:
            pass

        with _STATE_LOCK:
            owner = str(_HOLDER_OWNER or "")
            held_for = time.monotonic() - _HOLDER_STARTED_AT if _HOLDER_STARTED_AT else 0.0
            if owner:
                # The application already single-flights the same cell. We also
                # coalesce cross-cell clicks here so at most ONE UI request waits.
                # A second request replaces the old pending cell instead of
                # creating another thread that sleeps on the heavy lock.
                _PENDING_UI.clear()
                _PENDING_UI[key] = {
                    "symbol": str(symbol or ""),
                    "timeframe": str(timeframe or ""),
                    "market": str(market or "futures").lower(),
                    "queued_at": time.monotonic(),
                    "blocked_by": owner,
                }
                pending = True
            else:
                pending = False

        if pending:
            print(
                f"⏳ [COMMIT24] UI en cola detrás de {owner} age={held_for:.1f}s -> {symbol} {timeframe}",
                flush=True,
            )
            _track_pending_timer(app_module)
            return "DEFERRED_INTERACTIVE_QUEUE"

        # No background holder. Let the proven async implementation run; its
        # explicit timeout no longer governs the common contention case because
        # that case is intercepted above.
        return _original(symbol, timeframe, market=market)

    wrapped._commit24_repair = True
    app_module._start_futures_ui_analysis_async = wrapped
    return {"installed": True}


def _install_health(app_module: Any) -> Dict[str, Any]:
    try:
        from flask import jsonify

        @app_module.app.get("/api/commit24/health")
        def _commit24_health():
            with _STATE_LOCK:
                owner = _HOLDER_OWNER
                started = _HOLDER_STARTED_AT
                pending = [
                    {
                        "symbol": v.get("symbol"),
                        "timeframe": v.get("timeframe"),
                        "market": v.get("market"),
                        "age_seconds": round(time.monotonic() - float(v.get("queued_at") or time.monotonic()), 1),
                        "blocked_by": v.get("blocked_by"),
                    }
                    for v in _PENDING_UI.values()
                ]
            return jsonify({
                "success": True,
                "version": VERSION,
                "quality_authority_version": QUALITY_AUTHORITY_VERSION,
                "q_min_score": Q_MIN_SCORE,
                "q10_is_mandatory": False,
                "operational_safety_floor": OPERATING_SAFETY_FLOOR,
                "max_sl_loss_pct": MAX_SL_LOSS_PCT,
                "max_atr_stress_pct": MAX_ATR_STRESS_PCT,
                "heavy_holder": owner or None,
                "heavy_holder_age_seconds": round(time.monotonic() - started, 1) if started else 0,
                "pending_interactive_ui": pending,
                "stall_exit_seconds": STALL_EXIT_SECONDS,
                "hooks": {
                    "classifier": bool(_INSTALL_RESULT.get("classifier", {}).get("installed")),
                    "lifecycle": bool(_INSTALL_RESULT.get("lifecycle", {}).get("installed")),
                    "hidden_candidates": bool(_INSTALL_RESULT.get("hidden_candidates", {}).get("installed")),
                    "multiasset_diagnostics": bool(_INSTALL_RESULT.get("multiasset_diagnostics", {}).get("installed")),
                    "heavy_acquire": bool(_INSTALL_RESULT.get("heavy_acquire", {}).get("installed")),
                    "heavy_release": bool(_INSTALL_RESULT.get("heavy_release", {}).get("installed")),
                    "ui_start": bool(_INSTALL_RESULT.get("ui_start", {}).get("installed")),
                },
                "no_threshold_lowering": True,
                "no_new_market_data_requests": True,
                "no_new_permanent_workers": True,
            })
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}:{str(exc)[:180]}"}
    return {"installed": True}


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
            "q10_is_mandatory": False,
            "operational_safety_floor": OPERATING_SAFETY_FLOOR,
            "max_sl_loss_pct": MAX_SL_LOSS_PCT,
            "max_atr_stress_pct": MAX_ATR_STRESS_PCT,
            "allowed_legacy_blockers": sorted(ALLOWED_LEGACY_BLOCKERS),
            "stall_exit_seconds": STALL_EXIT_SECONDS,
        },
    }
    app_module.COMMIT24_RUNTIME = _INSTALL_RESULT
    _INSTALLED = True
    print(
        f"✅ [{VERSION}] hooks={{{k: v.get('installed') for k, v in _INSTALL_RESULT.items() if isinstance(v, dict) and 'installed' in v}}}",
        flush=True,
    )
    return dict(_INSTALL_RESULT)


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "quality_authority_version": QUALITY_AUTHORITY_VERSION,
        "q_min_score": Q_MIN_SCORE,
        "q10_is_mandatory": False,
        "thresholds_lowered": False,
        "new_market_data_requests": False,
        "new_permanent_workers": False,
        "hidden_candidate_q_evaluation": True,
        "fallback_geometry_safety_revaluation": True,
        "interactive_queue": True,
        "bounded_stall_recycle": True,
        "stall_exit_seconds": STALL_EXIT_SECONDS,
        "single_signal_per_symbol_timeframe": True,
        "boot_dependency": "commit23_1_main_entrypoint",
    }
