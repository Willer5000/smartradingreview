"""
Commit 17.5.10.9 — Signal-lane truth + Multi-Asset render bridge.

Overlay for 17.5.10.8 (HEAD 85784fb242137801acb4cc29593e2a97bf2bae61).

This commit fixes integration/visibility defects only. It does NOT lower Safety,
Entry, SL, TP, R/R, leverage or publication thresholds; it does not manufacture
LONG/SHORT; and it adds no market, DB or LLM calls, worker or polling loop.
"""
from __future__ import annotations

from functools import wraps
import math
import os
import threading
from typing import Any, Dict, List, Mapping, Optional, Tuple

VERSION = "COMMIT17_5_10_9_SIGNAL_LANE_TRUTH_V1"
EXPECTED_BASE_SHA = "85784fb242137801acb4cc29593e2a97bf2bae61"
EXPECTED_SUPABASE_REF = "frganummqwzzsukdefqd"

_LOCK = threading.RLock()
_STATE: Dict[str, Any] = {
    "installed": False,
    "base_175108_installed": False,
    "diagnostic_direction_bridge_installed": False,
    "futures_diagnostic_enrichment_installed": False,
    "multiasset_response_bridge_installed": False,
    "multiasset_lane_truth_installed": False,
    "frontend_runtime_injection_installed": False,
}


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _direction(value: Any) -> Optional[str]:
    value = _u(value)
    return value if value in {"LONG", "SHORT"} else None


def _direction_with_source(result: Mapping[str, Any] | None) -> Tuple[Optional[str], str]:
    """Recover only direction already present in the governed analysis.

    Crucially, thesis.direction is observational evidence already computed by the
    existing engine. Reading it does not promote the thesis to an executable
    signal and does not bypass candidate/publication gates.
    """
    result = _d(result)
    decision = _d(result.get("decision"))
    op = _d(result.get("operational_intelligence"))
    thesis = _d(op.get("thesis"))

    checks = (
        (decision.get("action"), "DECISION"),
        (op.get("candidate_action"), "CANDIDATE"),
        (decision.get("original_action"), "ORIGINAL_DECISION"),
        (result.get("original_action"), "ORIGINAL_RESULT"),
        (thesis.get("direction"), "THESIS"),
        ((_d(result.get("thesis"))).get("direction"), "RESULT_THESIS"),
    )
    for raw, source in checks:
        action = _direction(raw)
        if action:
            return action, source
    return None, "NONE"


def _diagnostic_direction(result: Mapping[str, Any] | None) -> Optional[str]:
    return _direction_with_source(result)[0]


def _funnel_stage(appmod: Any, result: Mapping[str, Any] | None) -> Dict[str, Any]:
    fn = getattr(appmod, "_technical_signal_funnel_row", None)
    if not callable(fn) or not isinstance(result, dict):
        return {}
    try:
        return _d(fn(result))
    except Exception:
        return {}


def _public_reason(appmod: Any, result: Mapping[str, Any] | None, fallback: str = "") -> str:
    result = _d(result)
    levels = _d(result.get("levels"))
    decision = _d(result.get("decision"))
    op = _d(result.get("operational_intelligence"))
    thesis = _d(op.get("thesis"))
    funnel = _funnel_stage(appmod, result)

    candidates: List[Any] = [
        levels.get("rejected_reason"),
        result.get("rejected_reason"),
        funnel.get("reason"),
        op.get("particular_setup_rejected_reason"),
        decision.get("reason"),
    ]
    reasons = decision.get("razones")
    if isinstance(reasons, (list, tuple)) and reasons:
        candidates.extend(reasons[:2])
    thesis_reasons = thesis.get("reasons")
    if isinstance(thesis_reasons, (list, tuple)) and thesis_reasons:
        candidates.extend(thesis_reasons[:2])

    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            raw = "; ".join(str(x) for x in raw if x)
        text = str(raw).strip()
        if not text:
            continue
        upper = text.upper()
        if "EXECUTION_RUNTIME_FAILED" in upper:
            return "El cálculo de niveles no terminó correctamente; no se publica una entrada hasta recalcular."
        if upper == "MISSING_EXECUTION_GEOMETRY":
            return "Entry, Stop Loss y Take Profit todavía no forman una geometría operable."
        # Internal stage codes by themselves are not useful to an external user.
        if text.replace("_", "").isalnum() and text == upper and " " not in text:
            continue
        return text[:520]

    stage = _u(funnel.get("stage"))
    if stage == "CANDIDATE":
        return "Existe una tesis LONG/SHORT, pero aún no completó la confirmación técnica necesaria para construir una entrada ejecutable."
    if stage == "DIRECTION_CONFIRMATION":
        return "Existe una tesis direccional, pero la confirmación final de dirección todavía no es suficiente para publicar una operación."
    if stage == "ENTRY":
        return "La dirección existe, pero el Entry todavía no es técnicamente defendible."
    if stage == "SL":
        return "La dirección existe, pero el Stop Loss propuesto todavía no es técnicamente defendible."
    if stage == "TP":
        return "La dirección existe, pero el Take Profit todavía no cumple la geometría requerida."
    if stage == "RR":
        return "La dirección existe, pero la relación riesgo/beneficio no alcanza el piso técnico vigente."
    if stage == "SAFETY":
        return "La dirección existe, pero no alcanza el Safety mínimo vigente."
    if stage in {"PUBLICATION", "OPPORTUNITY_RECOVERY"}:
        return "La hipótesis direccional existe, pero no superó la publicación técnica final."
    return fallback or "Existe una hipótesis direccional real en el análisis, pero no es una señal ejecutable."


def _score_meta(result: Mapping[str, Any] | None) -> Dict[str, Any]:
    result = _d(result)
    decision = _d(result.get("decision"))
    op = _d(result.get("operational_intelligence"))
    thesis = _d(op.get("thesis"))
    confidence = _f(decision.get("confidence"), -1.0)
    thesis_quality = _f(thesis.get("quality"), -1.0)
    if confidence >= 0:
        return {
            "diagnostic_score": round(confidence, 2),
            "diagnostic_score_kind": "DECISION_CONFIDENCE",
            "diagnostic_quality": round(thesis_quality, 2) if thesis_quality >= 0 else None,
        }
    if thesis_quality >= 0:
        return {
            "diagnostic_score": round(thesis_quality, 2),
            "diagnostic_score_kind": "THESIS_QUALITY",
            "diagnostic_quality": round(thesis_quality, 2),
        }
    return {
        "diagnostic_score": None,
        "diagnostic_score_kind": "UNSCORED_DIRECTIONAL_THESIS",
        "diagnostic_quality": None,
    }


def _install_base_175108(appmod: Any) -> Dict[str, Any]:
    from runtime_175108 import install_commit_175108
    return dict(install_commit_175108(appmod) or {})


def _install_direction_bridge() -> bool:
    """Upgrade the 17.5.10.8 diagnostic lookup used by its existing wrappers."""
    try:
        import runtime_175108 as r108
        r108._diagnostic_direction = _diagnostic_direction
        return True
    except Exception:
        return False


def _install_futures_diagnostic_enrichment(appmod: Any) -> bool:
    current = getattr(appmod, "_classify_futures_analysis_result", None)
    if not callable(current):
        return False
    if getattr(current, "_st175109_diagnostic_enrichment", False):
        return True

    @wraps(current)
    def wrapped(symbol, timeframe, result, lifecycle=None, min_confidence=0):
        out = dict(current(
            symbol, timeframe, result,
            lifecycle=lifecycle,
            min_confidence=min_confidence,
        ) or {})
        if not isinstance(result, dict) or result.get("success") is False:
            return out

        action, source = _direction_with_source(result)
        if not action:
            return out

        funnel = _funnel_stage(appmod, result)
        reason = _public_reason(appmod, result, str(out.get("reason") or ""))
        score = _score_meta(result)
        final_action = _u((_d(result.get("decision"))).get("action"))

        # 17.5.10.8 has already decided whether the row is ANALYSIS_ONLY.
        # We only enrich observational fields and, if an older mixed-deploy
        # classifier still returned NO_TRADE, preserve the existing thesis as a
        # non-executable diagnostic row. No publication field is changed.
        if _u(out.get("classification")) == "NO_TRADE":
            out.update({
                "classification": "ANALYSIS_ONLY",
                "status_label": "ANÁLISIS DIRECCIONAL · NO EJECUTABLE",
                "action": action,
                "directional": True,
                "is_executable": False,
                "is_active": False,
                "diagnostic_only": True,
            })

        if _u(out.get("classification")) == "ANALYSIS_ONLY":
            out.update({
                "action": action,
                "diagnostic_action": action,
                "final_action": final_action,
                "had_directional_candidate": True,
                "diagnostic_direction_source": source,
                "reason": reason,
                "diagnostic_stage": _u(funnel.get("stage")) or None,
                "candidate_ready": funnel.get("candidate_ready"),
                "thesis_quality": funnel.get("thesis_quality"),
                **score,
            })
        return out

    wrapped._st175109_diagnostic_enrichment = True
    wrapped._st175109_original = current
    appmod._classify_futures_analysis_result = wrapped
    return True


def _multiasset_allowed_symbols() -> set[str]:
    try:
        from multiasset_system import MULTIASSET_SYMBOLS
        return {str(x).upper().replace("/", "-") for x in MULTIASSET_SYMBOLS.keys()}
    except Exception:
        return set()


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

    allowed = _multiasset_allowed_symbols()
    is_exec = getattr(appmod, "_multiasset_is_executable", None)
    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for key, result in analyses.items():
        if not isinstance(result, dict) or result.get("success") is False:
            continue
        symbol = str(result.get("symbol") or (key[0] if isinstance(key, tuple) and key else "")).upper().replace("/", "-")
        timeframe = str(result.get("timeframe") or (key[1] if isinstance(key, tuple) and len(key) > 1 else ""))
        if allowed and symbol not in allowed:
            continue
        try:
            if callable(is_exec) and bool(is_exec(result)):
                continue
        except Exception:
            pass

        action, source = _direction_with_source(result)
        if not action:
            continue

        decision = _d(result.get("decision"))
        levels = _d(result.get("levels"))
        funnel = _funnel_stage(appmod, result)
        score = _score_meta(result)
        reason = _public_reason(appmod, result)
        state: Dict[str, Any] = {}
        temporal = getattr(appmod, "_multiasset_signal_temporal_state", None)
        if callable(temporal):
            try:
                state = _d(temporal(result))
            except Exception:
                state = {}

        item = {
            "symbol": symbol,
            "timeframe": timeframe,
            "display_name": result.get("display_name"),
            "asset_class": result.get("asset_class"),
            "market": "multiasset",
            "action": action,
            "diagnostic_action": action,
            "final_action": _u(decision.get("action")),
            "classification": "ANALYSIS_ONLY",
            "status_label": "ANÁLISIS DIRECCIONAL · NO EJECUTABLE",
            "directional": True,
            "is_executable": False,
            "diagnostic_only": True,
            "diagnostic_direction_source": source,
            "diagnostic_stage": _u(funnel.get("stage")) or None,
            "reason": reason,
            "manual_save_allowed": False,
            "manual_risk_class": "BLOCKED",
            "entry": levels.get("entry"),
            "stop_loss": levels.get("stop_loss"),
            "take_profit": levels.get("take_profit"),
            "leverage": levels.get("leverage"),
            "risk_reward": levels.get("risk_reward"),
            "execution_safety": levels.get("execution_safety"),
            "execution_safety_minimum": levels.get("execution_safety_operational_min"),
            "publication_status": levels.get("publication_status") or result.get("publication_status"),
            "source_candle_timestamp": result.get("source_candle_timestamp"),
            "source_candle_close_timestamp": result.get("source_candle_close_timestamp"),
            "valid_until": state.get("valid_until") or result.get("valid_until") or levels.get("valid_until"),
            "tiempo_restante": state.get("remaining_seconds"),
            "temporal_valid": state.get("valid"),
            "temporal_fresh": state.get("fresh"),
            **score,
        }
        # Keep the legacy field for mixed frontends, but it is descriptive only.
        if score.get("diagnostic_score_kind") == "DECISION_CONFIDENCE":
            item["confidence"] = score.get("diagnostic_score") or 0.0
        else:
            item["confidence"] = 0.0

        cell = (symbol, timeframe)
        previous = rows.get(cell)
        cur_score = _f(item.get("diagnostic_score"), -1.0)
        prev_score = _f((previous or {}).get("diagnostic_score"), -1.0)
        if previous is None or cur_score > prev_score:
            rows[cell] = item

    out = list(rows.values())
    out.sort(key=lambda row: (
        -_f(row.get("diagnostic_score"), -1.0),
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
    ))
    return out[:24]


def _response_payload(flask_app: Any, rv: Any):
    response = flask_app.make_response(rv)
    try:
        payload = response.get_json(silent=True)
    except Exception:
        payload = None
    return response, payload


def _json_response(appmod: Any, original_response: Any, payload: Dict[str, Any]):
    response = appmod.jsonify(payload)
    response.status_code = original_response.status_code
    for key, value in original_response.headers.items():
        if key.lower() not in {"content-type", "content-length"}:
            response.headers[key] = value
    return response


def _sanitize_multiasset_rows(rows: Any, allowed: set[str]) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").upper().replace("/", "-")
        if allowed and symbol not in allowed:
            continue
        item = dict(raw)
        item["market"] = "multiasset"
        out.append(item)
    return out


def _install_multiasset_response_bridge(appmod: Any) -> bool:
    flask_app = getattr(appmod, "app", None)
    if flask_app is None:
        return False

    endpoint = "api_multiasset_analyze"
    original = flask_app.view_functions.get(endpoint)
    if not callable(original):
        return False
    if getattr(original, "_st175109_response_bridge", False):
        return True

    @wraps(original)
    def wrapper(*args, **kwargs):
        rv = original(*args, **kwargs)
        response, payload = _response_payload(flask_app, rv)
        if not isinstance(payload, dict):
            return response

        # BUSY with cached data already has the correct envelope. A completed
        # analysis may be returned raw; normalize transport shape only.
        if not payload.get("busy") and payload.get("success") is not False and response.status_code < 400:
            payload["success"] = True
            payload["market"] = "multiasset"
            payload["response_contract_version"] = VERSION
            if not isinstance(payload.get("data"), dict):
                snapshot = dict(payload)
                snapshot.pop("data", None)
                payload["data"] = snapshot
        elif isinstance(payload.get("data"), dict):
            payload["market"] = "multiasset"
            payload["response_contract_version"] = VERSION

        return _json_response(appmod, response, payload)

    wrapper._st175109_response_bridge = True
    wrapper._st175109_original = original
    flask_app.view_functions[endpoint] = wrapper
    return True


def _install_multiasset_lane_truth(appmod: Any) -> bool:
    flask_app = getattr(appmod, "app", None)
    if flask_app is None:
        return False

    endpoint_modes = {
        "api_multiasset_opportunities": "active",
        "api_multiasset_signals_previous": "previous",
        "api_multiasset_signals_active": "vigent",
    }
    installed = 0

    for endpoint, lane in endpoint_modes.items():
        current = flask_app.view_functions.get(endpoint)
        if not callable(current):
            continue
        if getattr(current, "_st175109_lane_truth", False):
            installed += 1
            continue

        def make_wrapper(fn, lane_name):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                rv = fn(*args, **kwargs)
                response, payload = _response_payload(flask_app, rv)
                if not isinstance(payload, dict) or payload.get("success") is False:
                    return response

                allowed = _multiasset_allowed_symbols()
                diagnostics = _multiasset_diagnostics(appmod)

                # Server-side market isolation: a Futures/Spot symbol can never
                # leak into Multi-Asset lanes even if a stale browser state exists.
                if "signals" in payload:
                    payload["signals"] = _sanitize_multiasset_rows(payload.get("signals"), allowed)
                if "opportunities" in payload:
                    payload["opportunities"] = _sanitize_multiasset_rows(payload.get("opportunities"), allowed)

                # Keep the response truthful: diagnostic rows are not signals.
                payload["analysis_candidates"] = diagnostics
                payload["other_directional_signals"] = diagnostics
                if lane_name == "vigent":
                    # Older non-executable hypotheses are shown only when their
                    # technical window is still valid and no longer fresh. If
                    # temporal metadata is unavailable, do not invent vigency.
                    vigent = [
                        row for row in diagnostics
                        if row.get("temporal_valid") is True and row.get("temporal_fresh") is False
                    ]
                    payload["vigent_other_directional_signals"] = vigent

                signals = payload.get("signals") if isinstance(payload.get("signals"), list) else None
                opportunities = payload.get("opportunities") if isinstance(payload.get("opportunities"), list) else None
                if signals is not None:
                    payload["total"] = len(signals)
                    payload["active_count"] = len(signals)
                if opportunities is not None:
                    payload["count"] = len(opportunities)
                    payload["total"] = len(opportunities)

                payload["market"] = "multiasset"
                payload["market_scope"] = "MULTIASSET_ONLY"
                payload["diagnostic_visibility_version"] = VERSION
                payload["diagnostics_are_signals"] = False
                payload["diagnostics_manual_save_allowed"] = False
                payload["diagnostic_count"] = len(diagnostics)
                return _json_response(appmod, response, payload)

            wrapper._st175109_lane_truth = True
            wrapper._st175109_original = fn
            return wrapper

        flask_app.view_functions[endpoint] = make_wrapper(current, lane)
        installed += 1

    return installed == len(endpoint_modes)


def _install_frontend_runtime_injection(appmod: Any) -> bool:
    flask_app = getattr(appmod, "app", None)
    if flask_app is None:
        return False
    if getattr(flask_app, "_st175109_frontend_injection", False):
        return True

    @flask_app.after_request
    def _st175109_inject_runtime(response):
        try:
            response.headers["X-SmarTrading-Commit"] = "17.5.10.9"
            path = str(getattr(appmod, "request").path or "")
            content_type = str(response.headers.get("Content-Type") or "")
            if path not in {"/futures", "/multiasset"} or "text/html" not in content_type:
                return response
            body = response.get_data(as_text=True)
            marker = "runtime_175109.js"
            if marker in body:
                return response
            tag = '\n<script src="/static/runtime_175109.js?v=20260929-COMMIT17-5-10-9"></script>\n'
            if "</body>" in body:
                body = body.replace("</body>", tag + "</body>", 1)
            else:
                body += tag
            response.set_data(body)
        except Exception:
            return response
        return response

    flask_app._st175109_frontend_injection = True
    return True


def install_commit_175109(appmod: Any) -> Dict[str, Any]:
    with _LOCK:
        base = _install_base_175108(appmod)
        _STATE["base_175108_installed"] = bool(base.get("installed"))
        _STATE["base_175108_state"] = base
        _STATE["diagnostic_direction_bridge_installed"] = _install_direction_bridge()
        _STATE["futures_diagnostic_enrichment_installed"] = _install_futures_diagnostic_enrichment(appmod)
        _STATE["multiasset_response_bridge_installed"] = _install_multiasset_response_bridge(appmod)
        _STATE["multiasset_lane_truth_installed"] = _install_multiasset_lane_truth(appmod)
        _STATE["frontend_runtime_injection_installed"] = _install_frontend_runtime_injection(appmod)

        required = (
            "base_175108_installed",
            "diagnostic_direction_bridge_installed",
            "futures_diagnostic_enrichment_installed",
            "multiasset_response_bridge_installed",
            "multiasset_lane_truth_installed",
            "frontend_runtime_injection_installed",
        )
        _STATE.update({
            "installed": all(bool(_STATE.get(k)) for k in required),
            "version": VERSION,
            "expected_base_sha": EXPECTED_BASE_SHA,
            "no_thresholds_lowered": True,
            "no_direction_manufactured": True,
            "no_signal_quota": True,
            "no_new_market_requests": True,
            "no_new_db_reads": True,
            "no_new_db_writes": True,
            "no_new_llm_calls": True,
            "no_new_threads": True,
            "no_new_polling": True,
        })
        return dict(_STATE)


def verify_supabase_target() -> Dict[str, Any]:
    url = str(os.environ.get("SUPABASE_URL") or "").strip()
    if not url:
        return {"configured": False, "project_ref": None, "matches_expected": None}
    host = url.split("://")[-1].split("/")[0].split(":")[0]
    ref = host.split(".")[0] if host.endswith(".supabase.co") else None
    return {
        "configured": True,
        "project_ref": ref,
        "matches_expected": ref == EXPECTED_SUPABASE_REF,
    }
