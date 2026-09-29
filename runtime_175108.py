"""
Commit 17.5.10.8 — Signal visibility + deterministic Render bootstrap.

Purpose
-------
This is an overlay for HEAD 17.5.10.7. It does NOT lower Safety, Entry, SL, TP,
R/R, leverage or publication thresholds and it never manufactures direction.

It fixes three integration defects:
1) Render Blueprint could still boot app:app, bypassing the late 17.5.10.7 hooks.
2) A directional thesis could be downgraded to ESPERAR/PRECAUCION after a
   technical execution rejection and disappear from diagnostic lists.
3) "Por qué no aparecen otras señales" was coupled to manual-save eligibility,
   so only a narrow MEDIUM/HIGH subset was visible. Multi-Asset even returned
   those diagnostic arrays hard-coded as empty.

All diagnostic lanes are cache-only. No new market, DB or LLM calls are added.
"""
from __future__ import annotations

from functools import wraps
import math
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional

VERSION = "COMMIT17_5_10_8_SIGNAL_VISIBILITY_BOOTSTRAP_V1"
EXPECTED_BASE_SHA = "b747dc44dc081afdff3e77224d5125e6d2c8d2d6"
EXPECTED_SUPABASE_REF = "frganummqwzzsukdefqd"

_LOCK = threading.RLock()
_STATE = {
    "installed": False,
    "base_175107_installed": False,
    "direction_preservation_installed": False,
    "futures_diagnostics_installed": False,
    "intrabar_diagnostics_installed": False,
    "multiasset_diagnostics_installed": False,
    "frontend_runtime_injection_installed": False,
}


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_directional(action: Any) -> bool:
    return _u(action) in {"LONG", "SHORT"}


def _diagnostic_direction(result: Mapping[str, Any] | None) -> Optional[str]:
    """Recover the already-governed directional hypothesis without creating one."""
    result = _d(result)
    decision = _d(result.get("decision"))
    action = _u(decision.get("action"))
    if _is_directional(action):
        return action

    # A later execution guard may have converted LONG/SHORT to ESPERAR or
    # PRECAUCION. Operational Intelligence keeps the governed pre-execution
    # candidate. candidate_action is directional only when candidate_ready passed.
    op = _d(result.get("operational_intelligence"))
    candidate_action = _u(op.get("candidate_action"))
    if bool(op.get("candidate_ready")) and _is_directional(candidate_action):
        return candidate_action

    original_action = _u(
        decision.get("original_action")
        or result.get("original_action")
    )
    if _is_directional(original_action):
        return original_action
    return None


def _technical_reason(result: Mapping[str, Any] | None, fallback: str = "") -> str:
    result = _d(result)
    levels = _d(result.get("levels"))
    decision = _d(result.get("decision"))
    trace = _d(levels.get("futures_filter_trace"))
    candidates = [
        levels.get("rejected_reason"),
        result.get("rejected_reason"),
        trace.get("reason"),
        decision.get("reason"),
    ]
    reasons = decision.get("razones")
    if isinstance(reasons, list) and reasons:
        candidates.append(reasons[0])

    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            raw = "; ".join(str(x) for x in raw if x)
        text = str(raw).strip()
        if text:
            # Public-safe wording for runtime codes; technical human-readable
            # reasons pass through unchanged.
            if text.startswith("EXECUTION_RUNTIME_FAILED"):
                return "El cálculo de niveles no terminó correctamente; no se publica una entrada hasta recalcular."
            if text == "MISSING_EXECUTION_GEOMETRY":
                return "Entry, Stop Loss y Take Profit todavía no forman una geometría operable."
            return text[:420]
    return fallback or "Existe una hipótesis direccional, pero no superó una condición técnica de ejecución/publicación."


def _diagnostic_label(reason: str, final_action: str = "") -> str:
    reason_u = _u(reason)
    final_u = _u(final_action)
    if final_u in {"ESPERAR", "PRECAUCION", "PRECAUCIÓN"}:
        return "ESPERAR" if final_u == "ESPERAR" else "PRECAUCIÓN"
    if any(token in reason_u for token in (
        "ENTRY", "RETROCESO", "PULLBACK", "REACTION", "REACCIÓN",
        "CONFIRMACIÓN", "CONFIRMACION", "TIMING",
    )):
        return "ESPERAR"
    return "NO EJECUTABLE"


def _install_base_175107(appmod: Any) -> Dict[str, Any]:
    """Force 17.5.10.7 late hooks after app.py finished defining every route."""
    state: Dict[str, Any] = {}
    try:
        configured = getattr(appmod, "_configured_futures_module", None)
        if callable(configured):
            configured()
    except Exception as exc:
        state["configured_futures_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    try:
        from strategy_quality_extension_175105 import (
            install_strategy_quality_extension_175105,
        )
        state.update(install_strategy_quality_extension_175105() or {})
    except Exception as exc:
        state["extension_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    required = (
        "invalidation_corridor_installed",
        "cache_only_reads_installed",
        "multiasset_nonblocking_ui_installed",
        "risk_profile_bounded_read_installed",
        "leverage_visibility_consistency_installed",
    )
    state["base_175107_ready"] = all(bool(state.get(key)) for key in required)
    return state


def _install_direction_preservation() -> bool:
    """Keep LONG/SHORT as the diagnostic direction after an earlier hard reject.

    This wrapper NEVER makes a rejected setup executable. If levels are already
    ANALYSIS_ONLY/is_rejected, the downstream setup guard has no need to replace
    the direction with ESPERAR/PRECAUCION; the existing rejection reason remains
    authoritative. Executable setups still pass through the original guard
    unchanged.
    """
    try:
        import operational_intelligence as oi
        original = getattr(oi, "execution_setup_guard", None)
        if not callable(original):
            return False
        if getattr(original, "_st175108_preserve_rejected_direction", False):
            return True

        @wraps(original)
        def wrapped(*, action, levels, setup_family, market, timeframe):
            lv = _d(levels)
            market_u = _u(market)
            publication = _u(lv.get("publication_status"))
            already_rejected = bool(
                lv.get("is_rejected")
                or lv.get("is_executable") is False
                or publication == "ANALYSIS_ONLY"
            )
            if (
                market_u == "FUTURES"
                and _is_directional(action)
                and already_rejected
            ):
                reason = str(lv.get("rejected_reason") or "").strip()
                return {
                    "applied": False,
                    "action": _u(action),
                    "status": "ALREADY_NON_EXECUTABLE_DIRECTION_PRESERVED",
                    "reasons": [reason] if reason else [],
                    "diagnostic_only": True,
                    "publication_bypass": False,
                    "version": VERSION,
                }
            return original(
                action=action,
                levels=levels,
                setup_family=setup_family,
                market=market,
                timeframe=timeframe,
            )

        wrapped._st175108_preserve_rejected_direction = True
        # Keep the 17.5.10.6 marker so a later idempotent ABI call does not
        # wrap an obsolete generic R/R guard around this function.
        wrapped._st175106_contextual_rr_floor = bool(
            getattr(original, "_st175106_contextual_rr_floor", True)
        )
        wrapped._st175108_original = original
        oi.execution_setup_guard = wrapped
        return True
    except Exception:
        return False


def _install_futures_diagnostics(appmod: Any) -> bool:
    original_classifier = getattr(appmod, "_classify_futures_analysis_result", None)
    if not callable(original_classifier):
        return False

    if not getattr(original_classifier, "_st175108_directional_diagnostics", False):
        @wraps(original_classifier)
        def classify_wrapped(symbol, timeframe, result, lifecycle=None, min_confidence=0):
            out = dict(original_classifier(
                symbol, timeframe, result,
                lifecycle=lifecycle,
                min_confidence=min_confidence,
            ) or {})
            if not isinstance(result, dict) or not result.get("success"):
                return out

            diag_action = _diagnostic_direction(result)
            if not diag_action:
                return out

            levels = _d(result.get("levels"))
            final_action = _u((_d(result.get("decision"))).get("action"))
            engine_status = _u(
                levels.get("publication_status")
                or result.get("publication_status")
                or out.get("engine_publication_status")
            )
            rejected = bool(
                levels.get("is_rejected")
                or levels.get("is_executable") is False
                or engine_status == "ANALYSIS_ONLY"
                or out.get("classification") == "ANALYSIS_ONLY"
            )

            out["diagnostic_action"] = diag_action
            out["final_action"] = final_action
            out["had_directional_candidate"] = True

            # Do not relabel a genuinely executable signal. For a rejected
            # directional thesis, make the diagnostic identity explicit even
            # if a later display-oriented guard changed final_action.
            if rejected or out.get("classification") == "NO_TRADE":
                reason = _technical_reason(result, str(out.get("reason") or ""))
                out.update({
                    "classification": "ANALYSIS_ONLY",
                    "engine_publication_status": engine_status or "ANALYSIS_ONLY",
                    "status_label": "ANÁLISIS DIRECCIONAL · NO EJECUTABLE",
                    "reason": reason,
                    "active_reason": "La hipótesis existe, pero no se publica como señal ejecutable.",
                    "action": diag_action,
                    "directional": True,
                    "is_executable": False,
                    "is_active": False,
                    "diagnostic_only": True,
                    "diagnostic_label": _diagnostic_label(reason, final_action),
                })
            return out

        classify_wrapped._st175108_directional_diagnostics = True
        classify_wrapped._st175108_original = original_classifier
        appmod._classify_futures_analysis_result = classify_wrapped

    # Replace ONLY the diagnostic selector. Manual-save authorization remains
    # exactly where it was: server-side policy + save endpoint.
    def hidden_candidates(visibility, source_context, representative_ids=None):
        raw_candidates = list((_d(visibility)).get("candidates") or [])
        allow_manual_lane = _u(source_context) == "PREVIOUS_ANALYSIS_ONLY"
        selected: Dict[tuple, Dict[str, Any]] = {}

        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            classification = _u(raw.get("classification"))
            action = _u(raw.get("diagnostic_action") or raw.get("action"))
            if classification != "ANALYSIS_ONLY" or not _is_directional(action):
                continue

            item = dict(raw)
            item["action"] = action
            item["source_context"] = _u(source_context)
            item["diagnostic_only"] = not bool(item.get("manual_save_allowed"))
            item["diagnostic_label"] = str(
                item.get("diagnostic_label")
                or _diagnostic_label(
                    str(item.get("reason") or item.get("manual_risk_reason") or ""),
                    str(item.get("final_action") or ""),
                )
            )
            item["reason"] = str(
                item.get("reason")
                or item.get("manual_risk_reason")
                or "No superó una condición técnica de ejecución/publicación."
            )[:420]

            # Current/intrabar diagnostic lists are never saveable. Previous
            # keeps the old manual-save decision only when the exact server
            # policy already authorized it.
            existing_manual = bool(item.get("manual_save_allowed"))
            item["manual_save_allowed"] = bool(existing_manual and allow_manual_lane)

            signal_id = str(item.get("signal_id") or "")
            if (
                item["manual_save_allowed"]
                and representative_ids is not None
                and signal_id
                and signal_id not in representative_ids
            ):
                # Representative filtering applies to a saveable lifecycle row,
                # not to read-only diagnostics that may not have a signal_id.
                item["manual_save_allowed"] = False

            key = (
                str(item.get("symbol") or ""),
                str(item.get("timeframe") or ""),
            )
            previous = selected.get(key)
            if previous is None or _f(item.get("confidence")) > _f(previous.get("confidence")):
                selected[key] = item

        rows = list(selected.values())
        rows.sort(key=lambda item: (
            0 if item.get("manual_save_allowed") else 1,
            -_f(item.get("confidence")),
            str(item.get("symbol") or ""),
            str(item.get("timeframe") or ""),
        ))
        return rows

    hidden_candidates._st175108_all_directional_diagnostics = True
    appmod._futures_directional_hidden_candidates = hidden_candidates
    return True


def _install_intrabar_diagnostics(appmod: Any) -> bool:
    original = getattr(appmod, "_futures_intrabar_diagnostic_candidate", None)
    if not callable(original):
        return False
    if getattr(original, "_st175108_intrabar_diagnostics", False):
        return True

    @wraps(original)
    def wrapped(symbol, timeframe, result):
        row = original(symbol, timeframe, result)
        if isinstance(row, dict):
            row = dict(row)
            row.setdefault("diagnostic_only", not bool(row.get("manual_save_allowed")))
            row.setdefault("diagnostic_label", _diagnostic_label(
                str(row.get("manual_risk_reason") or row.get("reason") or "")
            ))
            row.setdefault("preview_ts", time.time())
            return row

        if not isinstance(result, dict) or not result.get("success"):
            return None
        if _u(result.get("analysis_mode")) != "INTRABAR_PREVIEW":
            return None
        if result.get("source_candle_closed") is not False:
            return None

        action = _diagnostic_direction(result)
        if not action:
            return None
        levels = _d(result.get("levels"))
        publication = _u(
            levels.get("publication_status")
            or result.get("publication_status")
        )
        if publication == "EXECUTABLE_SIGNAL" and levels.get("is_executable") is not False:
            return None

        decision = _d(result.get("decision"))
        reason = _technical_reason(result)
        return {
            "symbol": str(symbol),
            "timeframe": str(timeframe),
            "action": action,
            "final_action": _u(decision.get("action")),
            "confidence": _f(decision.get("confidence")),
            "classification": "ANALYSIS_ONLY",
            "engine_publication_status": publication or "ANALYSIS_ONLY",
            "manual_risk_class": "BLOCKED",
            "manual_risk_reason": "",
            "manual_save_allowed": False,
            "source_context": "INTRABAR_ANALYSIS_ONLY",
            "preview_only": True,
            "source_candle_closed": False,
            "signal_id": None,
            "entry": levels.get("entry"),
            "stop_loss": levels.get("stop_loss"),
            "take_profit": levels.get("take_profit"),
            "leverage": levels.get("leverage"),
            "risk_reward": levels.get("risk_reward"),
            "execution_safety": levels.get("execution_safety"),
            "execution_safety_minimum": levels.get("execution_safety_operational_min"),
            "reason": reason,
            "diagnostic_only": True,
            "diagnostic_label": _diagnostic_label(
                reason, _u(decision.get("action"))
            ),
            "source_candle_timestamp": result.get("source_candle_timestamp"),
            "source_candle_close_timestamp": result.get("source_candle_close_timestamp"),
            "analysis_price": result.get("analysis_price"),
            "current_price": result.get("live_price") or result.get("current_price"),
            "preview_ts": time.time(),
        }

    wrapped._st175108_intrabar_diagnostics = True
    wrapped._st175108_original = original
    appmod._futures_intrabar_diagnostic_candidate = wrapped
    return True


def _multiasset_diagnostics(appmod: Any) -> List[Dict[str, Any]]:
    try:
        cache = getattr(appmod, "_MULTI_ASSET_CACHE")
        lock = cache.get("lock")
        if lock is not None:
            with lock:
                analyses = dict(cache.get("analysis") or {})
        else:
            analyses = dict(cache.get("analysis") or {})
    except Exception:
        return []

    rows: Dict[tuple, Dict[str, Any]] = {}
    is_exec = getattr(appmod, "_multiasset_is_executable", None)

    for key, result in analyses.items():
        if not isinstance(result, dict) or result.get("success") is False:
            continue
        try:
            if callable(is_exec) and bool(is_exec(result)):
                continue
        except Exception:
            pass

        action = _diagnostic_direction(result)
        if not action:
            continue

        symbol = str(result.get("symbol") or (key[0] if isinstance(key, tuple) and key else ""))
        timeframe = str(result.get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else ""))
        decision = _d(result.get("decision"))
        levels = _d(result.get("levels"))
        op = _d(result.get("operational_intelligence"))
        thesis = _d(op.get("thesis"))
        reason = _technical_reason(result)
        confidence = _f(decision.get("confidence"), _f(thesis.get("quality")))

        item = {
            "symbol": symbol,
            "timeframe": timeframe,
            "action": action,
            "final_action": _u(decision.get("action")),
            "confidence": round(confidence, 2),
            "classification": "ANALYSIS_ONLY",
            "engine_publication_status": _u(
                levels.get("publication_status")
                or result.get("publication_status")
                or "ANALYSIS_ONLY"
            ),
            "status_label": "ANÁLISIS DIRECCIONAL · NO EJECUTABLE",
            "reason": reason,
            "directional": True,
            "is_executable": False,
            "manual_save_allowed": False,
            "manual_risk_class": "BLOCKED",
            "manual_risk_reason": "",
            "diagnostic_only": True,
            "diagnostic_label": _diagnostic_label(
                reason, _u(decision.get("action"))
            ),
            "entry": levels.get("entry"),
            "stop_loss": levels.get("stop_loss"),
            "take_profit": levels.get("take_profit"),
            "leverage": levels.get("leverage"),
            "risk_reward": levels.get("risk_reward"),
            "execution_safety": levels.get("execution_safety"),
            "execution_safety_minimum": levels.get("execution_safety_operational_min"),
            "source_candle_timestamp": result.get("source_candle_timestamp"),
            "source_candle_close_timestamp": result.get("source_candle_close_timestamp"),
            "analysis_price": result.get("analysis_price"),
            "current_price": result.get("live_price") or result.get("current_price"),
            "thesis_quality": thesis.get("quality"),
            "source_context": "MULTIASSET_ANALYSIS_ONLY",
        }
        cell = (symbol, timeframe)
        prev = rows.get(cell)
        if prev is None or confidence > _f(prev.get("confidence")):
            rows[cell] = item

    out = list(rows.values())
    out.sort(key=lambda row: (
        -_f(row.get("confidence")),
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
    ))
    return out[:20]


def _install_multiasset_diagnostics(appmod: Any) -> bool:
    flask_app = getattr(appmod, "app", None)
    if flask_app is None:
        return False

    endpoint_modes = {
        "api_multiasset_opportunities": "active",
        "api_multiasset_signals_previous": "previous",
        "api_multiasset_signals_active": "vigent",
    }
    installed = 0

    for endpoint, mode in endpoint_modes.items():
        original = flask_app.view_functions.get(endpoint)
        if not callable(original):
            continue
        if getattr(original, "_st175108_multiasset_diagnostics", False):
            installed += 1
            continue

        def make_wrapper(fn, lane):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                rv = fn(*args, **kwargs)
                response = flask_app.make_response(rv)
                try:
                    payload = response.get_json(silent=True)
                except Exception:
                    payload = None
                if not isinstance(payload, dict) or not payload.get("success"):
                    return response

                diagnostics = _multiasset_diagnostics(appmod)
                payload["analysis_candidates"] = diagnostics
                payload["other_directional_signals"] = diagnostics
                if lane == "vigent":
                    payload["vigent_other_directional_signals"] = diagnostics
                payload["diagnostic_visibility_version"] = VERSION
                payload["diagnostics_are_signals"] = False
                payload["diagnostics_manual_save_allowed"] = False

                new_response = appmod.jsonify(payload)
                new_response.status_code = response.status_code
                # Preserve cache/auth headers if the original view set any.
                for key, value in response.headers.items():
                    if key.lower() not in {"content-type", "content-length"}:
                        new_response.headers[key] = value
                return new_response
            wrapper._st175108_multiasset_diagnostics = True
            wrapper._st175108_original = fn
            return wrapper

        flask_app.view_functions[endpoint] = make_wrapper(original, mode)
        installed += 1

    return installed == len(endpoint_modes)


def _install_frontend_runtime_injection(appmod: Any) -> bool:
    flask_app = getattr(appmod, "app", None)
    if flask_app is None:
        return False
    if getattr(flask_app, "_st175108_frontend_injection", False):
        return True

    @flask_app.after_request
    def _st175108_inject_runtime(response):
        try:
            response.headers["X-SmarTrading-Commit"] = "17.5.10.8"
            path = str(getattr(appmod, "request").path or "")
            content_type = str(response.headers.get("Content-Type") or "")
            if path not in {"/futures", "/multiasset"} or "text/html" not in content_type:
                return response

            body = response.get_data(as_text=True)
            marker = "runtime_175108.js"
            if marker in body:
                return response
            tag = (
                '\n<script src="/static/runtime_175108.js'
                '?v=20260929-COMMIT17-5-10-8"></script>\n'
            )
            if "</body>" in body:
                body = body.replace("</body>", tag + "</body>", 1)
            else:
                body += tag
            response.set_data(body)
        except Exception:
            # Presentation patch must never break the page.
            return response
        return response

    flask_app._st175108_frontend_injection = True
    return True


def install_commit_175108(appmod: Any) -> Dict[str, Any]:
    with _LOCK:
        base_state = _install_base_175107(appmod)
        _STATE["base_175107_installed"] = bool(base_state.get("base_175107_ready"))
        _STATE["base_175107_state"] = base_state

        _STATE["direction_preservation_installed"] = _install_direction_preservation()
        _STATE["futures_diagnostics_installed"] = _install_futures_diagnostics(appmod)
        _STATE["intrabar_diagnostics_installed"] = _install_intrabar_diagnostics(appmod)
        _STATE["multiasset_diagnostics_installed"] = _install_multiasset_diagnostics(appmod)
        _STATE["frontend_runtime_injection_installed"] = _install_frontend_runtime_injection(appmod)

        _STATE.update({
            "installed": all(bool(_STATE.get(key)) for key in (
                "base_175107_installed",
                "direction_preservation_installed",
                "futures_diagnostics_installed",
                "intrabar_diagnostics_installed",
                "multiasset_diagnostics_installed",
                "frontend_runtime_injection_installed",
            )),
            "version": VERSION,
            "no_thresholds_lowered": True,
            "no_signal_count_quota": True,
            "no_new_market_requests": True,
            "no_new_db_reads": True,
            "no_new_db_writes": True,
            "no_new_llm_calls": True,
            "no_new_threads": True,
            "manual_save_policy_preserved": True,
        })
        return dict(_STATE)


def verify_supabase_target() -> Dict[str, Any]:
    url = str(os.environ.get("SUPABASE_URL") or "").strip()
    if not url:
        return {
            "configured": False,
            "project_ref": None,
            "matches_expected": None,
        }
    host = url.split("://")[-1].split("/")[0].split(":")[0]
    ref = host.split(".")[0] if host.endswith(".supabase.co") else None
    return {
        "configured": True,
        "project_ref": ref,
        "matches_expected": ref == EXPECTED_SUPABASE_REF,
    }
