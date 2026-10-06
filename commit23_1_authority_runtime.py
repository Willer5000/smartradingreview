"""Commit 23.1 Fix — final quality authority reconciliation.

This overlay is deliberately loaded AFTER the proven 19.1 -> 20.2.1 -> 23 boot
chain. It does not create directions, lower risk thresholds, add market-data
requests, or add workers/threads. It repairs the integration contract between
Q1..Q10, app.py classification, Futures lifecycle, Multi-Asset executability,
cache migration and per-cell deduplication.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Dict, Iterable, Mapping, Tuple

VERSION = "COMMIT23_1_AUTHORITY_INTEGRATION_FIX_V1"
QUALITY_AUTHORITY_VERSION = "COMMIT23_TEN_FILTER_PARALLEL_AUTHORITY_V1"
Q_MIN_SCORE = 75.0
OPERATIONAL_SAFETY_MIN = 65.0
MAX_SL_LOSS_PCT = 8.0
MAX_ATR_STRESS_PCT = 25.0
ALLOWED_LEGACY_BLOCKERS = {"SAFETY", "TP_QUALITY", "SL_QUALITY", "RR"}

_ORIGINALS: Dict[str, Any] = {}
_INSTALLED = False


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _action(value: Any) -> str:
    raw = _u(value)
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


def _parallel_trace(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    result = result or {}
    levels = result.get("levels") if isinstance(result.get("levels"), Mapping) else {}
    trace = result.get("quality_filter_trace") or result.get("parallel_quality_filters")
    if not isinstance(trace, Mapping):
        trace = levels.get("quality_filter_trace") or levels.get("parallel_quality_filters")
    return dict(trace) if isinstance(trace, Mapping) else {}


def _gate(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    result = result or {}
    levels = result.get("levels") if isinstance(result.get("levels"), Mapping) else {}
    gate = result.get("futures_publication_gate") or levels.get("futures_publication_gate")
    return dict(gate) if isinstance(gate, Mapping) else {}


def _quality_authority_from(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Return the single trusted final Q authority contract.

    Promotion is never inferred from a bare score. The Q23 trace, selected
    filter, current version, universal guards, native publication stage and
    legacy blocker contract all have to agree.
    """
    result = result or {}
    levels = result.get("levels") if isinstance(result.get("levels"), Mapping) else {}
    trace = _parallel_trace(result)
    gate = _gate(result)
    decision = result.get("decision") if isinstance(result.get("decision"), Mapping) else {}

    action = _action(
        decision.get("action")
        or levels.get("manual_observation_action")
        or trace.get("direction")
    )
    version = str(
        trace.get("version")
        or result.get("quality_authority_version")
        or levels.get("quality_authority_version")
        or ""
    )
    selected = str(
        result.get("quality_filter_authority")
        or result.get("quality_authority")
        or trace.get("selected_filter")
        or levels.get("quality_filter_authority")
        or "NONE"
    ).upper()
    selected_name = str(
        result.get("quality_filter_name")
        or result.get("quality_authority_name")
        or trace.get("selected_filter_name")
        or ""
    )
    score = _f(
        result.get("quality_filter_score")
        or result.get("quality_authority_score")
        or trace.get("selected_filter_score")
        or levels.get("quality_filter_authority_score"),
        0.0,
    )
    confirmed = bool(
        result.get("quality_filter_confirmed")
        or trace.get("confirmed_one_of_ten")
        or trace.get("selected_filter_passed") and trace.get("selected_filter_score", 0) >= Q_MIN_SCORE
    )
    passed_filters = [str(x).upper() for x in (trace.get("passed_filters") or result.get("quality_filter_passed") or [])]
    guards = trace.get("universal_guards") if isinstance(trace.get("universal_guards"), Mapping) else {}
    guard_codes = [str(x).upper() for x in (guards.get("codes") or result.get("parallel_quality_guard_codes") or [])]
    legacy_codes = [
        str(x).upper()
        for x in (
            result.get("legacy_q10_reason_codes")
            or trace.get("legacy_publication_blockers")
            or gate.get("reason_codes")
            or []
        )
    ]
    native_stage = str(
        result.get("futures_filter_stage")
        or gate.get("stage")
        or levels.get("futures_filter_stage")
        or ""
    ).upper()

    geometry_valid = bool(guards.get("geometry_valid"))
    entry = _f(levels.get("entry"))
    sl = _f(levels.get("stop_loss"))
    tp = _f(levels.get("take_profit"))
    safety = _f(levels.get("execution_safety"))
    risk_control = levels.get("risk_control") if isinstance(levels.get("risk_control"), Mapping) else {}
    sl_loss = _f(
        risk_control.get("estimated_sl_loss_pct_margin"),
        abs(_f(levels.get("roi_sl"))),
    )
    atr_stress = _f(risk_control.get("estimated_atr_stress_loss_pct_margin"))
    synthetic = bool(result.get("market_data_is_synthetic", levels.get("market_data_is_synthetic", False)))

    if action not in {"LONG", "SHORT"}:
        return {
            "version": version,
            "confirmed": False,
            "reason": "DIRECTION_UNDEFINED",
            "authority": "NONE",
            "authority_name": "",
            "score": score,
            "passed_filters": passed_filters,
            "guard_codes": guard_codes,
            "legacy_codes": legacy_codes,
            "native_stage": native_stage,
        }

    hard_codes = list(guard_codes)
    if synthetic and "SYNTHETIC_MARKET_DATA" not in hard_codes:
        hard_codes.append("SYNTHETIC_MARKET_DATA")
    if safety < OPERATIONAL_SAFETY_MIN and "OPERATIONAL_SAFETY_BELOW_65" not in hard_codes:
        hard_codes.append("OPERATIONAL_SAFETY_BELOW_65")
    if sl_loss > MAX_SL_LOSS_PCT and "LOSS_AT_SL" not in hard_codes:
        hard_codes.append("LOSS_AT_SL")
    if not (0.0 < atr_stress <= MAX_ATR_STRESS_PCT) and "ATR_STRESS" not in hard_codes:
        hard_codes.append("ATR_STRESS")
    if not geometry_valid:
        if not (
            entry > 0 and sl > 0 and tp > 0
            and ((action == "LONG" and sl < entry < tp) or (action == "SHORT" and tp < entry < sl))
        ):
            hard_codes.append("INVALID_ENTRY_SL_TP")
    if native_stage != "PUBLICATION_GATE":
        hard_codes.append("PRE_GATE_REJECTION")
    if not version or version != QUALITY_AUTHORITY_VERSION:
        hard_codes.append("QUALITY_AUTHORITY_VERSION_STALE")
    if not selected or selected == "NONE" or score < Q_MIN_SCORE:
        hard_codes.append("NO_Q_GE75")
    if not confirmed:
        hard_codes.append("Q_NOT_CONFIRMED")
    if legacy_codes and not set(legacy_codes).issubset(ALLOWED_LEGACY_BLOCKERS):
        hard_codes.append("NON_Q10_LEGACY_BLOCKER")
    publication_status = str(result.get("publication_status") or levels.get("publication_status") or "").upper()
    gate_status = str(gate.get("status") or "").upper()
    if publication_status in {"AI_BLOCKED", "EDGE_BLOCKED", "WAIT_EVENT"} or gate_status == "WAIT_EVENT":
        hard_codes.append("HARD_POST_GATE_BLOCK")

    # Remove duplicates without changing order for human-readable diagnostics.
    seen = set()
    hard_codes = [x for x in hard_codes if not (x in seen or seen.add(x))]
    final_confirmed = bool(
        confirmed
        and score >= Q_MIN_SCORE
        and version == QUALITY_AUTHORITY_VERSION
        and not hard_codes
    )

    return {
        "version": version,
        "confirmed": final_confirmed,
        "authority": selected if final_confirmed else "NONE",
        "authority_name": selected_name,
        "score": round(score, 2),
        "passed_filters": passed_filters,
        "guard_codes": hard_codes,
        "legacy_codes": legacy_codes,
        "native_stage": native_stage or "PUBLICATION_GATE",
        "action": action,
        "summary": str(result.get("quality_filter_summary") or trace.get("summary") or ""),
        "q10_is_mandatory": True,
        "hard_q10_thresholds_unchanged": True,
        "geometry_valid": bool(
            entry > 0 and sl > 0 and tp > 0
            and ((action == "LONG" and sl < entry < tp) or (action == "SHORT" and tp < entry < sl))
        ),
        "execution_safety": round(safety, 2),
        "loss_at_sl_pct": round(sl_loss, 3),
        "atr_stress_pct": round(atr_stress, 3),
    }


def reconcile_final_quality_authority(result: Mapping[str, Any] | None, *, symbol: str = "", timeframe: str = "") -> Dict[str, Any]:
    """Make Q23 publication authority authoritative at the final app boundary."""
    out = dict(result or {})
    levels = dict(out.get("levels") or {})
    authority = _quality_authority_from({**out, "levels": levels})
    diagnostic_confirmed = bool(authority.get("confirmed"))
    authority["diagnostic_confirmed"] = diagnostic_confirmed
    authority["confirmed"] = False
    authority["authority"] = "NONE"
    authority["reason"] = "COMMIT25_PARALLEL_QUALITY_DIAGNOSTIC_ONLY"
    authority["q10_is_mandatory"] = True
    out["commit25_parallel_quality_would_confirm"] = diagnostic_confirmed
    out["final_quality_authority"] = authority
    out["final_quality_authority_version"] = VERSION
    out["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
    levels["final_quality_authority"] = authority
    levels["final_quality_authority_version"] = VERSION
    levels["quality_authority_version"] = QUALITY_AUTHORITY_VERSION

    if authority.get("confirmed"):
        gate = dict(_gate(out))
        gate.update({
            "eligible": True,
            "tier": "PREMIUM",
            "status": "PREMIUM_CONTEXT_QUALITY",
            "reasons": [],
            "reason_codes": [],
            "quality_authority": authority["authority"],
            "quality_authority_name": authority["authority_name"],
            "quality_authority_score": authority["score"],
            "q10_is_mandatory": True,
            "hard_q10_thresholds_unchanged": True,
            "final_authority_version": VERSION,
            "legacy_q10_reason_codes": authority.get("legacy_codes") or [],
        })
        out["futures_publication_gate"] = gate
        levels["futures_publication_gate"] = gate
        for key, value in {
            "publication_status": "EXECUTABLE_SIGNAL",
            "publication_eligible": True,
            "is_executable": True,
            "is_rejected": False,
            "futures_signal_tier": "PREMIUM",
            "premium_confirmation_mode": "ONE_OF_TEN_QUALITY_FILTERS",
            "quality_filter_confirmed": True,
            "quality_filter_authority": authority["authority"],
            "quality_filter_authority_score": authority["score"],
            "quality_authority": authority["authority"],
            "quality_authority_name": authority["authority_name"],
            "quality_authority_score": authority["score"],
            "premium_blocker_stage_21": "NONE",
            "premium_blocker_codes": [],
            "premium_blocker": "",
            "q10_is_mandatory": True,
        }.items():
            out[key] = value
            levels[key] = value
        out["publication_reconciled_by"] = VERSION
        out["publication_reconciliation_reason"] = (
            f"{authority['authority']} {authority['score']:.1f}/100 + universal guards"
        )
    else:
        # Do not downgrade an already-valid native signal. This is strictly a
        # reconciliation layer; it never invents a veto.
        if str(out.get("publication_status") or levels.get("publication_status") or "").upper() == "EXECUTABLE_SIGNAL":
            out["final_quality_authority_note"] = "NATIVE_EXECUTABLE_SIGNAL_PRESERVED"

    out["levels"] = levels
    return out


def _replay_quality_over_existing_futures_result(result: Mapping[str, Any] | None, symbol: str, timeframe: str, engine: Any) -> Tuple[Dict[str, Any], bool]:
    """Re-run only the Q authority contract on an old same-candle snapshot.

    Entry/SL/TP and the directional thesis remain unchanged. The only refreshed
    decision is whether the already-generated package has current Q23 authority.
    """
    out = dict(result or {})
    if not out.get("success") or not isinstance(engine, object):
        return out, False
    existing_version = str(out.get("quality_authority_version") or "")
    trace = _parallel_trace(out)
    if existing_version == QUALITY_AUTHORITY_VERSION and trace:
        return reconcile_final_quality_authority(out, symbol=symbol, timeframe=timeframe), False

    levels = dict(out.get("levels") or {})
    action = _action((out.get("decision") or {}).get("action") or levels.get("manual_observation_action"))
    if action not in {"LONG", "SHORT"}:
        return out, False

    # Give Q23 the stored contextual evidence, not a fresh market request.
    levels["market_data_is_synthetic"] = out.get("market_data_is_synthetic", levels.get("market_data_is_synthetic", False))
    levels["_commit21_quality_context"] = {
        "trend": out.get("trend") or {},
        "momentum": out.get("momentum") or {},
        "volatility": out.get("volatility") or {},
        "structure": out.get("structure") or {},
    }
    gate_method = getattr(engine, "_apply_futures_publication_gate", None)
    if not callable(gate_method):
        return reconcile_final_quality_authority(out, symbol=symbol, timeframe=timeframe), False

    try:
        gated = gate_method(levels, timeframe, symbol=symbol, action=action)
    except TypeError:
        gated = gate_method(levels, timeframe, symbol, action)
    except Exception as exc:
        out["quality_authority_replay_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return out, False

    if isinstance(gated, dict):
        out["levels"] = gated
        for key in (
            "publication_status", "publication_eligible", "is_executable", "is_rejected",
            "futures_publication_gate", "futures_signal_tier", "quality_9q", "q10_safety",
            "parallel_quality_filters", "quality_filter_trace", "quality_filter_authority",
            "quality_filter_authority_score", "quality_filter_score", "quality_filter_confirmed",
            "quality_filter_passed", "quality_filter_summary", "quality_filter_membership",
            "legacy_q10_reason_codes", "parallel_quality_guard_codes", "premium_confirmation_mode",
            "premium_blocker", "premium_blocker_codes", "premium_blocker_stage_21",
        ):
            if key in gated:
                out[key] = gated[key]
    out = reconcile_final_quality_authority(out, symbol=symbol, timeframe=timeframe)
    out["quality_authority_reprocessed"] = True
    out["quality_authority_reprocess_reason"] = (
        "SNAPSHOT_AUTHORITY_VERSION_STALE" if existing_version else "SNAPSHOT_WITHOUT_Q_AUTHORITY_VERSION"
    )
    return out, True


def _wrap_classifier(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_classify_futures_analysis_result", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "CLASSIFIER_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["classifier"] = original

    @wraps(original)
    def wrapped(symbol, timeframe, result, lifecycle=None, min_confidence=0, _original=original):
        reconciled = reconcile_final_quality_authority(result, symbol=symbol, timeframe=timeframe)
        if isinstance(result, dict):
            result.clear()
            result.update(reconciled)
        classified = _original(
            symbol=symbol,
            timeframe=timeframe,
            result=reconciled,
            lifecycle=lifecycle,
            min_confidence=min_confidence,
        )
        if not isinstance(classified, dict):
            return classified
        authority = reconciled.get("final_quality_authority") or {}
        if authority.get("confirmed") and authority.get("score", 0) >= Q_MIN_SCORE:
            classified.update({
                "classification": "EXECUTABLE_SIGNAL",
                "engine_publication_status": "EXECUTABLE_SIGNAL",
                "status_label": "SEÑAL EJECUTABLE · CALIDAD Q",
                "reason": (
                    f"Confirmada por {authority.get('authority')} "
                    f"({authority.get('score', 0):.1f}/100) + guards universales."
                ),
                "is_executable": True,
                "directional": str(classified.get("action") or "").upper() in {"LONG", "SHORT"},
                "diagnostic_action": None,
                "quality_filter_authority": authority.get("authority"),
                "quality_filter_authority_score": authority.get("score"),
                "quality_filter_name": authority.get("authority_name"),
                "quality_filter_confirmed": True,
                "quality_filter_membership": authority.get("passed_filters") or [],
                "final_quality_authority": authority,
            })
            classified["manual_risk_reason"] = reconciled.get("quality_filter_summary") or classified.get("manual_risk_reason")
        return classified

    wrapped._commit23_1_authority = True
    app_module._classify_futures_analysis_result = wrapped
    return {"installed": True}


def _wrap_lifecycle(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_refresh_futures_signal_lifecycle", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "LIFECYCLE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["lifecycle"] = original

    @wraps(original)
    def wrapped(lifecycle, symbol, timeframe, result, _original=original):
        reconciled = reconcile_final_quality_authority(result, symbol=symbol, timeframe=timeframe)
        if isinstance(result, dict):
            result.clear()
            result.update(reconciled)
        out = _original(lifecycle, symbol, timeframe, reconciled)
        authority = reconciled.get("final_quality_authority") or {}
        if authority.get("confirmed") and isinstance(out, dict):
            sid = str(reconciled.get("signal_id") or "").strip()
            if sid and sid in out:
                rec = dict(out[sid])
                rec["publication_status"] = "EXECUTABLE_SIGNAL"
                rec["engine_publication_status"] = "EXECUTABLE_SIGNAL"
                rec["system_executable"] = True
                rec["quality_filter_authority"] = authority.get("authority")
                rec["quality_filter_score"] = authority.get("score")
                rec["quality_filter_confirmed"] = True
                rec["quality_authority_version"] = QUALITY_AUTHORITY_VERSION
                out[sid] = rec
        return out

    wrapped._commit23_1_authority = True
    app_module._refresh_futures_signal_lifecycle = wrapped
    return {"installed": True}


def _wrap_representative_score(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_representative_signal_score", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "REP_SCORE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["representative_score"] = original

    @wraps(original)
    def wrapped(row, _original=original):
        trace = _parallel_trace(row or {})
        confirmed = bool((row or {}).get("quality_filter_confirmed") or trace.get("confirmed_one_of_ten"))
        qscore = _f((row or {}).get("quality_filter_score") or (row or {}).get("quality_authority_score") or trace.get("selected_filter_score"), 0)
        if confirmed and qscore >= Q_MIN_SCORE:
            # Keep the old quality score available as a tie-break, but make
            # validated Q authority the first technical criterion after the
            # official/manual class priority.
            legacy = _f(_original(row), 0)
            return 1000.0 + qscore * 5.0 + legacy * 0.01
        return _original(row)

    wrapped._commit23_1_authority = True
    app_module._representative_signal_score = wrapped
    return {"installed": True}


def _wrap_hidden_candidates(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_futures_directional_hidden_candidates", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "HIDDEN_CANDIDATES_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["hidden_candidates"] = original

    @wraps(original)
    def wrapped(*args, **kwargs):
        rows = original(*args, **kwargs) or []
        best = {}
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            symbol = _u(raw.get("symbol"))
            timeframe = str(raw.get("timeframe") or "")
            if not symbol or not timeframe:
                continue
            trace = _parallel_trace(raw)
            qscore = _f(raw.get("quality_filter_score") or raw.get("quality_authority_score") or trace.get("selected_filter_score"), 0)
            confirmed = bool(raw.get("quality_filter_confirmed") or trace.get("confirmed_one_of_ten"))
            confidence = _f(raw.get("confidence"), 0)
            rr = _f(raw.get("risk_reward"), 0)
            rank = (1 if confirmed else 0, qscore, confidence, rr)
            key = (symbol, timeframe)
            previous = best.get(key)
            if previous is None or rank > previous[0]:
                item = dict(raw)
                item["quality_filter_authority"] = str(raw.get("quality_filter_authority") or trace.get("selected_filter") or "NONE")
                item["quality_filter_score"] = qscore
                item["quality_filter_confirmed"] = confirmed
                best[key] = (rank, item)
        return [v[1] for v in sorted(best.values(), key=lambda x: (-x[0][0], -x[0][1], -x[0][2], -x[0][3]))]

    wrapped._commit23_1_authority = True
    app_module._futures_directional_hidden_candidates = wrapped
    return {"installed": True}


def _wrap_multiasset_engine() -> Dict[str, Any]:
    """Patch the actual MultiAssetAnalysis runtime when the legacy app-level
    helper functions are absent. This is the current production integration
    point: MultiAsset delegates into the common Futures execution engine.
    """
    try:
        import multiasset_system as mas
        cls = getattr(mas, "MultiAssetAnalysis", None)
        if cls is None:
            return {"installed": False, "reason": "MULTIASSET_CLASS_NOT_FOUND"}
        original = getattr(cls, "analyze_multiasset_market", None)
        if not callable(original) or getattr(original, "_commit23_1_authority", False):
            return {"installed": False, "reason": "MULTIASSET_ANALYZE_NOT_FOUND_OR_ALREADY_PATCHED"}
        _ORIGINALS["multiasset_analyze"] = original

        @wraps(original)
        def wrapped(self, symbol, timeframe, *args, _original=original, **kwargs):
            result = _original(self, symbol, timeframe, *args, **kwargs)
            if isinstance(result, dict):
                result = reconcile_final_quality_authority(result, symbol=symbol, timeframe=timeframe)
            return result

        wrapped._commit23_1_authority = True
        cls.analyze_multiasset_market = wrapped
        return {"installed": True, "target": "MultiAssetAnalysis.analyze_multiasset_market"}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def _wrap_multiasset_executable(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_multiasset_is_executable", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "MULTI_EXECUTABLE_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["multiasset_executable"] = original

    @wraps(original)
    def wrapped(result, _original=original):
        if isinstance(result, dict):
            reconciled = reconcile_final_quality_authority(result, symbol=result.get("symbol"), timeframe=result.get("timeframe"))
            result.clear()
            result.update(reconciled)
        native = bool(_original(result))
        authority = (result.get("final_quality_authority") or {}) if isinstance(result, dict) else {}
        return bool(native or authority.get("confirmed"))

    wrapped._commit23_1_authority = True
    app_module._multiasset_is_executable = wrapped
    return {"installed": True}


def _wrap_multiasset_diagnostics(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_multiasset_directional_diagnostics_17511", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "MULTI_DIAGNOSTICS_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["multiasset_diagnostics"] = original

    @wraps(original)
    def wrapped(analyses, _original=original):
        enriched = {}
        for key, raw in (analyses or {}).items():
            if isinstance(raw, dict):
                symbol = raw.get("symbol") or (key[0] if isinstance(key, tuple) and key else "")
                timeframe = raw.get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else "")
                enriched[key] = reconcile_final_quality_authority(raw, symbol=symbol, timeframe=timeframe)
            else:
                enriched[key] = raw
        rows = _original(enriched)
        out = []
        for row in rows or []:
            item = dict(row)
            raw = enriched.get((item.get("symbol"), item.get("timeframe")))
            if raw is None:
                # Normalize common symbol/timeframe formatting.
                target = (_u(item.get("symbol")), str(item.get("timeframe") or ""))
                for key, candidate in enriched.items():
                    k = (_u(candidate.get("symbol") if isinstance(candidate, dict) else ""), str(candidate.get("timeframe") if isinstance(candidate, dict) else ""))
                    if k == target:
                        raw = candidate
                        break
            authority = (raw or {}).get("final_quality_authority") or {}
            trace = _parallel_trace(raw or {})
            item["quality_filter_authority"] = authority.get("authority") or trace.get("selected_filter") or item.get("quality_filter_authority")
            item["quality_filter_name"] = authority.get("authority_name") or trace.get("selected_filter_name") or item.get("quality_filter_name")
            item["quality_filter_score"] = authority.get("score") or trace.get("selected_filter_score") or item.get("quality_filter_score") or 0
            item["quality_filter_confirmed"] = bool(authority.get("confirmed") or trace.get("confirmed_one_of_ten"))
            item["quality_filter_membership"] = authority.get("passed_filters") or trace.get("passed_filters") or []
            item["quality_filter_summary"] = (raw or {}).get("quality_filter_summary") or trace.get("summary") or ""
            item["final_quality_authority_version"] = VERSION
            if item["quality_filter_confirmed"]:
                item["reason"] = (
                    f"Confirmada por {item['quality_filter_authority']} "
                    f"({float(item['quality_filter_score'] or 0):.1f}/100) + guards universales."
                )
                item["classification"] = "EXECUTABLE_SIGNAL"
                item["status_label"] = "SEÑAL EJECUTABLE · CALIDAD Q"
                item["is_executable"] = True
                item["diagnostic_only"] = False
            out.append(item)
        return out

    wrapped._commit23_1_authority = True
    app_module._multiasset_directional_diagnostics_17511 = wrapped
    return {"installed": True}


def _wrap_futures_refresh(app_module: Any) -> Dict[str, Any]:
    original = getattr(app_module, "_analyze_futures_all_parallel", None)
    if not callable(original) or getattr(original, "_commit23_1_authority", False):
        return {"installed": False, "reason": "FUTURES_REFRESH_NOT_FOUND_OR_ALREADY_PATCHED"}
    _ORIGINALS["futures_refresh"] = original

    @wraps(original)
    def wrapped(combos_override=None, _original=original):
        payload = _original(combos_override)
        if not isinstance(payload, dict):
            return payload
        try:
            engine = app_module._get_futures_system()
            changed = False
            analysis = dict(payload.get("analysis") or {})
            for key, raw in list(analysis.items()):
                if not isinstance(raw, dict) or not raw.get("success"):
                    continue
                symbol = raw.get("symbol") or (key[0] if isinstance(key, tuple) and key else "")
                timeframe = raw.get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else "")
                current_version = str(raw.get("quality_authority_version") or _parallel_trace(raw).get("version") or "")
                if current_version != QUALITY_AUTHORITY_VERSION:
                    migrated, did_change = _replay_quality_over_existing_futures_result(raw, str(symbol), str(timeframe), engine)
                    if did_change:
                        analysis[key] = migrated
                        changed = True
            if changed:
                payload["analysis"] = analysis
                cache = getattr(app_module, "_futures_analysis_cache", None)
                if isinstance(cache, dict) and cache.get("lock") is not None:
                    with cache["lock"]:
                        data = dict(cache.get("data") or {})
                        data["analysis"] = analysis
                        cache["data"] = data
                # Rebuild lifecycle for migrated cells without recalculating market data.
                lifecycle = dict(payload.get("lifecycle") or {})
                for key, raw in analysis.items():
                    if not isinstance(raw, dict) or not raw.get("quality_authority_reprocessed"):
                        continue
                    symbol = raw.get("symbol") or (key[0] if isinstance(key, tuple) and key else "")
                    timeframe = raw.get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else "")
                    lifecycle = app_module._refresh_futures_signal_lifecycle(lifecycle, str(symbol), str(timeframe), raw)
                payload["lifecycle"] = lifecycle
                if isinstance(cache, dict) and cache.get("lock") is not None:
                    with cache["lock"]:
                        data = dict(cache.get("data") or {})
                        data["analysis"] = analysis
                        data["lifecycle"] = lifecycle
                        cache["data"] = data
                print(f"✅ [{VERSION}] Reconciliación de autoridad aplicada a snapshots antiguos")
            return payload
        except Exception as exc:
            payload["quality_authority_reprocess_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            return payload

    wrapped._commit23_1_authority = True
    app_module._analyze_futures_all_parallel = wrapped
    return {"installed": True}


def _install_health_route(app_module: Any) -> Dict[str, Any]:
    try:
        if getattr(app_module, "_COMMIT23_1_HEALTH_ROUTE", False):
            return {"installed": True, "already": True}
        from flask import jsonify

        @app_module.app.get("/api/commit23-1/health")
        def _commit23_1_health():
            return jsonify({
                "success": True,
                "version": VERSION,
                "quality_authority_version": QUALITY_AUTHORITY_VERSION,
                "q_threshold": Q_MIN_SCORE,
                "operational_safety_floor": OPERATIONAL_SAFETY_MIN,
                "max_sl_loss_pct": MAX_SL_LOSS_PCT,
                "max_atr_stress_pct": MAX_ATR_STRESS_PCT,
                "q10_is_mandatory": True,
                "boot_chain": "19.1_PRE -> app.py -> CPQE_19.2.4 -> 19.1_POST -> PPE20 -> Q23 -> 23.1",
                "no_new_network_calls": True,
                "no_new_workers": True,
            })
        app_module._COMMIT23_1_HEALTH_ROUTE = True
        return {"installed": True}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install(app: Any) -> Dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"installed": True, "already": True, "version": VERSION}
    app_module = __import__("app")
    result = {
        "version": VERSION,
        "installed": True,
        "classifier": _wrap_classifier(app_module),
        "lifecycle": _wrap_lifecycle(app_module),
        "representative_score": _wrap_representative_score(app_module),
        "hidden_candidates": _wrap_hidden_candidates(app_module),
        "multiasset_engine": _wrap_multiasset_engine(),
        "multiasset_executable": _wrap_multiasset_executable(app_module),
        "multiasset_diagnostics": _wrap_multiasset_diagnostics(app_module),
        "futures_refresh_reconciliation": _wrap_futures_refresh(app_module),
        "health": _install_health_route(app_module),
        "policy": {
            "q_min_score": Q_MIN_SCORE,
            "q10_is_mandatory": True,
            "operational_safety_floor": OPERATIONAL_SAFETY_MIN,
            "max_sl_loss_pct": MAX_SL_LOSS_PCT,
            "max_atr_stress_pct": MAX_ATR_STRESS_PCT,
            "legacy_blockers_allowed_for_q_promotion": sorted(ALLOWED_LEGACY_BLOCKERS),
        },
    }
    app_module.COMMIT23_1_AUTHORITY_RUNTIME = result
    _INSTALLED = True
    return result


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "quality_authority_version": QUALITY_AUTHORITY_VERSION,
        "q_min_score": Q_MIN_SCORE,
        "q10_is_mandatory": True,
        "thresholds_lowered": False,
        "new_network_calls": False,
        "new_workers": False,
        "snapshot_migration": True,
        "single_final_authority": True,
        "dedupe_primary_metric": "QUALITY_FILTER_SCORE",
        "multiasset_runtime_hook": "MultiAssetAnalysis.analyze_multiasset_market",
        "boot_chain_required": "19.1_PRE -> app.py -> CPQE_19.2.4 -> 19.1_POST -> PPE20 -> Q23 -> 23.1",
    }
