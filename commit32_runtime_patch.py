"""Commit 32 final runtime integration.

Narrow, reversible repairs on top of Commit31:
- publication-policy version truth / stale snapshot invalidation,
- SPOT Market Signal Authority in the modern pipeline (not legacy vote_on_actions),
- Futures/Multi execution tempo without threshold relaxation,
- shared heavy-job serialization,
- repeated RAM checkpoints + elimination of a large structure.df duplicate,
- lightweight funnel telemetry.
"""
from __future__ import annotations

import copy
import functools
import os
import threading
import time
from collections import Counter
from typing import Any, Dict, Mapping

from commit32_execution_policy import MULTIASSET_TEMPO, VERSION as TEMPO_VERSION, annotate_multiasset_result, install_futures_tempo
from commit32_spot_market_authority import VERSION as SPOT_VERSION, apply_market_signal_to_pipeline

VERSION = "COMMIT32_ROOT_CAUSE_RECOVERY_V2"
PUBLICATION_POLICY_VERSION = "COMMIT32_PUBLICATION_AUDIT_V2"
_FUNNEL = Counter()
_FUNNEL_LOCK = threading.Lock()
_INSTALLED = False


def _inc(key: str, n: int = 1) -> None:
    with _FUNNEL_LOCK:
        _FUNNEL[str(key)] += int(n)


def funnel_snapshot() -> Dict[str, Any]:
    with _FUNNEL_LOCK:
        counts = dict(_FUNNEL)
    return {"version": VERSION, "counts": counts, "timestamp": time.time()}


def _rss(app_module: Any) -> float | None:
    fn = getattr(app_module, "_process_rss_mb", None)
    try:
        value = fn() if callable(fn) else None
        return float(value) if value is not None else None
    except Exception:
        return None


def _ram_checkpoint(app_module: Any, label: str, *, allow_abort: bool = True) -> float | None:
    """Best-effort memory checkpoint before known allocation-heavy stages."""
    rss = _rss(app_module)
    if rss is None:
        return None
    shed_mb = float(os.getenv("COMMIT32_RAM_SHED_MB", "245") or 245)
    abort_mb = float(os.getenv("COMMIT32_RAM_ABORT_MB", "285") or 285)
    if rss >= shed_mb:
        _inc("ram_shed")
        shed = getattr(app_module, "_shed_recreatable_memory", None)
        if callable(shed):
            try:
                shed(reason=f"commit32:{label}", aggressive=True)
            except Exception:
                pass
        rss = _rss(app_module)
    if allow_abort and rss is not None and rss >= abort_mb:
        _inc("ram_abort_" + str(label))
        raise RuntimeError(f"RESOURCE_PRESSURE_ABORT_COMMIT32:{label}:{rss:.1f}MB")
    return rss


class _CompactStructureDict(dict):
    """Keep structure dict ABI while preventing a full second OHLCV copy.

    app.py later assigns structure['df'] to six Python lists. SmartMoney only
    consumes len(structure['df']['time']); UI explicitly removes structure.df.
    Store only that length marker.
    """
    @staticmethod
    def _compact_df(value: Any) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            return {"time": []}
        try:
            n = len(value.get("time") or [])
        except Exception:
            n = 0
        return {"time": [0] * int(max(0, n)), "_commit32_compacted": True}

    def __setitem__(self, key: Any, value: Any) -> None:
        if key == "df":
            value = self._compact_df(value)
        super().__setitem__(key, value)


def _install_policy_version(app_module: Any) -> None:
    if not hasattr(app_module, "_COMMIT245_NATIVE_Q_VERSION"):
        raise RuntimeError("Commit32: expected publication policy version symbol missing")
    app_module._COMMIT245_NATIVE_Q_VERSION = PUBLICATION_POLICY_VERSION
    setattr(app_module, "COMMIT32_PUBLICATION_POLICY_VERSION", PUBLICATION_POLICY_VERSION)


def _install_modern_spot_pipeline() -> None:
    import pipeline_integrity_175101 as shim
    import pipeline_integrity_175102 as impl
    original = getattr(impl, "reconcile_operational_candidate", None)
    if not callable(original):
        raise RuntimeError("Commit32: modern pipeline reconcile unavailable")
    if getattr(original, "_commit32_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(operational, *, layers, symbol, timeframe, system_type):
        market = str(system_type or "").upper()
        if market != "SPOT":
            return original(operational, layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type)
        _inc("spot_market_authority_evaluated")
        out = apply_market_signal_to_pipeline(
            original, impl, operational, layers=layers, symbol=symbol,
            timeframe=timeframe, system_type=system_type,
        )
        assessment = out.get("commit32_spot_market_signal") if isinstance(out, dict) else None
        if isinstance(assessment, dict):
            _inc("spot_market_" + str(assessment.get("action") or "unknown").lower())
            if out.get("candidate_ready"):
                _inc("spot_candidate_ready")
            if out.get("commit32_spot_suppressed_opposite"):
                _inc("spot_opposite_suppressed")
        return out

    wrapped._commit32_wrapped = True
    impl.reconcile_operational_candidate = wrapped
    shim.reconcile_operational_candidate = wrapped
    setattr(impl, "COMMIT32_SPOT_MARKET_SIGNAL_AUTHORITY", SPOT_VERSION)
    setattr(shim, "COMMIT32_SPOT_MARKET_SIGNAL_AUTHORITY", SPOT_VERSION)


def _install_structure_compaction(app_module: Any) -> None:
    expert = getattr(app_module, "expert_system", None)
    if expert is None:
        return
    cls = expert.__class__
    original = getattr(cls, "analyze_price_structure_layer", None)
    if not callable(original) or getattr(original, "_commit32_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(self, *args, **kwargs):
        out = original(self, *args, **kwargs)
        if isinstance(out, dict) and not isinstance(out, _CompactStructureDict):
            compact = _CompactStructureDict()
            for k, v in out.items():
                compact[k] = v
            out = compact
        _ram_checkpoint(app_module, "after_structure")
        return out

    wrapped._commit32_wrapped = True
    cls.analyze_price_structure_layer = wrapped
    setattr(app_module, "COMMIT32_STRUCTURE_DF_COMPACTION", True)


def _wrap_before(app_module: Any, owner: Any, name: str, label: str) -> None:
    original = getattr(owner, name, None)
    if not callable(original) or getattr(original, "_commit32_ram_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        _ram_checkpoint(app_module, label)
        return original(*args, **kwargs)

    wrapped._commit32_ram_wrapped = True
    setattr(owner, name, wrapped)


def _install_ram_stage_checkpoints(app_module: Any) -> None:
    expert = getattr(app_module, "expert_system", None)
    if expert is not None:
        _wrap_before(app_module, expert.__class__, "calculate_entry_levels", "before_geometry")
    moderator = getattr(app_module, "Moderador", None)
    if moderator is not None:
        _wrap_before(app_module, moderator, "procesar_votacion", "before_specialists")
    heatmap = getattr(app_module, "LiquidationHeatmap", None)
    if heatmap is not None:
        _wrap_before(app_module, heatmap, "load_price_history", "before_heatmap_history")
        _wrap_before(app_module, heatmap, "update_heatmap", "before_heatmap_update")
    try:
        import operational_intelligence as oi
        _wrap_before(app_module, oi, "prepare_operational_intelligence", "before_operational_intelligence")
    except Exception:
        pass
    setattr(app_module, "COMMIT32_RAM_STAGE_CHECKPOINTS", True)


def _install_futures_policy() -> None:
    import futures_universe
    install_futures_tempo(futures_universe)


def _install_multiasset_policy() -> None:
    try:
        import multiasset_system as multi
    except Exception:
        return
    cls = getattr(multi, "MultiAssetAnalysis", None)
    if cls is None:
        return
    original = getattr(cls, "_post_market_analysis_hook", None)
    if not callable(original) or getattr(original, "_commit32_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(self, result, symbol, timeframe):
        out = original(self, result, symbol, timeframe)
        if isinstance(out, dict):
            annotate_multiasset_result(out, str(timeframe))
            _inc("multi_evaluated")
            if out.get("publication_eligible") or out.get("is_executable"):
                _inc("multi_executable")
        return out

    wrapped._commit32_wrapped = True
    cls._post_market_analysis_hook = wrapped
    setattr(multi, "COMMIT32_EXECUTION_TEMPO_VERSION", TEMPO_VERSION)


def _install_entry_monitor_tempo(app_module: Any) -> None:
    name = "_entry_zone_tolerance_pct"
    original = getattr(app_module, name, None)
    if not callable(original) or getattr(original, "_commit32_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(signal=None):
        sig = signal or {}
        market = str(sig.get("market") or sig.get("system") or sig.get("system_type") or "").lower()
        if market in {"multiasset", "multi-asset", "multi_activo", "multi-activo"} or bool(sig.get("is_multiasset")):
            tf = str(sig.get("timeframe") or "4h")
            return float((MULTIASSET_TEMPO.get(tf) or MULTIASSET_TEMPO["4h"])["entry_zone_pct_cap"])
        return original(signal)

    wrapped._commit32_wrapped = True
    setattr(app_module, name, wrapped)


def _install_telegram_truth_patch(app_module: Any) -> None:
    name = "_build_confirmed_signal_telegram_message"
    original = getattr(app_module, name, None)
    if not callable(original) or getattr(original, "_commit32_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(market, signal, *args, **kwargs):
        s = copy.deepcopy(signal or {})
        levels = dict(s.get("levels") or {})
        if not (s.get("risk_class") or levels.get("risk_class") or levels.get("safety_band")):
            s["risk_class"] = "NO_EVALUADO"
        message = original(market, s, *args, **kwargs)
        if str(market or "").lower() == "spot" and isinstance(message, str):
            op = s.get("operational_intelligence") if isinstance(s.get("operational_intelligence"), dict) else {}
            meta = s.get("commit32_spot_market_signal") or op.get("commit32_spot_market_signal")
            if isinstance(meta, dict):
                rotation = str(meta.get("market_rotation_signal") or "NEUTRAL")
                if rotation not in {"", "NEUTRAL"}:
                    message += "\n🧭 Señal relativa de mercado: <b>" + rotation.replace("_", " ") + "</b>"
                message += "\nℹ️ Señal SPOT global; Guardian gestiona cada portafolio por separado."
        return message

    wrapped._commit32_wrapped = True
    setattr(app_module, name, wrapped)


def _heavy_endpoint_wrapper(app_module: Any, endpoint: str, owner: str, *, scheduler_key: bool = False, user_auth: bool = False) -> None:
    flask_app = getattr(app_module, "app", None)
    if flask_app is None:
        return
    view = flask_app.view_functions.get(endpoint)
    if not callable(view) or getattr(view, "_commit32_wrapped", False):
        return
    acquire = getattr(app_module, "_acquire_heavy_analysis", None)
    release = getattr(app_module, "_release_heavy_analysis", None)
    jsonify = getattr(app_module, "jsonify", None)
    if not callable(acquire) or not callable(release) or not callable(jsonify):
        raise RuntimeError(f"Commit32: heavy coordinator unavailable for {endpoint}")

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if scheduler_key and not str(os.getenv("SCHEDULED_AUTH_KEY") or "").strip():
            _inc("scheduler_auth_fail_closed")
            return jsonify({"success": False, "error": "SCHEDULED_AUTH_KEY_NOT_CONFIGURED", "commit32": VERSION}), 503
        if user_auth:
            require_auth = getattr(app_module, "_require_auth", None)
            if not callable(require_auth):
                return jsonify({"success": False, "error": "AUTH_HELPER_UNAVAILABLE", "commit32": VERSION}), 503
            auth = require_auth()
            if not isinstance(auth, str):
                return auth
        _ram_checkpoint(app_module, "before_" + endpoint)
        acquired = False
        try:
            acquired = bool(acquire(owner, timeout=0.0))
            if not acquired:
                _inc("memory_heavy_rejected_busy")
                return jsonify({"success": False, "error": "HEAVY_ANALYSIS_BUSY_OR_MEMORY_PRESSURE", "commit32": VERSION}), 503
            _inc("memory_heavy_acquired")
            return view(*args, **kwargs)
        finally:
            if acquired:
                release(owner)

    wrapped._commit32_wrapped = True
    flask_app.view_functions[endpoint] = wrapped


def _install_memory_serialization(app_module: Any) -> None:
    _heavy_endpoint_wrapper(app_module, "api_run_scheduled", "commit32:api_run_scheduled", scheduler_key=True)
    _heavy_endpoint_wrapper(app_module, "api_review_run_now", "commit32:api_review_run_now", scheduler_key=True)
    _heavy_endpoint_wrapper(app_module, "api_review_learning_pdf", "commit32:api_review_learning_pdf", user_auth=True)
    setattr(app_module, "COMMIT32_HEAVY_ENDPOINT_SERIALIZATION", True)


def _install_funnel_wrapper(app_module: Any) -> None:
    name = "_app244_native_quality_authority"
    original = getattr(app_module, name, None)
    if not callable(original) or getattr(original, "_commit32_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        _ram_checkpoint(app_module, "before_publication")
        _inc("publication_authority_evaluated")
        result = original(*args, **kwargs)
        if isinstance(result, dict):
            levels = result.get("levels") if isinstance(result.get("levels"), dict) else {}
            audit = result.get("app_native_quality_audit") if isinstance(result.get("app_native_quality_audit"), dict) else {}
            gate = result.get("futures_publication_gate") if isinstance(result.get("futures_publication_gate"), dict) else {}
            reasons = list(audit.get("reason_codes") or gate.get("reasons") or [])
            text = " ".join(map(str, reasons)).upper()
            if "FALLBACK_GEOMETRY" in text: _inc("publication_fallback_geometry")
            if "NO_VALIDATED_LIVE_ROUTE" in text: _inc("publication_no_live_route")
            if "ATR_STRESS" in text: _inc("publication_atr_stress")
            if "SAFETY" in text and "READY" in text: _inc("publication_safety_not_ready")
            if bool(result.get("publication_eligible") or result.get("is_executable") or levels.get("publication_eligible") or audit.get("eligible")):
                _inc("publication_eligible")
        return result

    wrapped._commit32_wrapped = True
    setattr(app_module, name, wrapped)


def _install_runtime_version_truth(app_module: Any) -> None:
    flask_app = getattr(app_module, "app", None)
    jsonify = getattr(app_module, "jsonify", None)
    if flask_app is None or not callable(jsonify):
        return
    endpoint = "api_runtime_version_commit31"
    view = flask_app.view_functions.get(endpoint)
    if not callable(view) or getattr(view, "_commit32_wrapped", False):
        return

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        original_result = view(*args, **kwargs)
        status = 200
        response = original_result
        if isinstance(original_result, tuple):
            response = original_result[0]
            if len(original_result) > 1 and isinstance(original_result[1], int): status = original_result[1]
        try:
            payload = dict(response.get_json(silent=True) or {})
        except Exception:
            payload = {}
        payload.update({
            "version": VERSION,
            "entrypoint": "commit32_main_entrypoint:app",
            "publication_policy": PUBLICATION_POLICY_VERSION,
            "spot_market_signal_authority": SPOT_VERSION,
            "execution_tempo": TEMPO_VERSION,
            "commit32_structure_df_compaction": bool(getattr(app_module, "COMMIT32_STRUCTURE_DF_COMPACTION", False)),
            "commit32_ram_checkpoints": bool(getattr(app_module, "COMMIT32_RAM_STAGE_CHECKPOINTS", False)),
        })
        contracts = dict(payload.get("contracts") or {})
        contracts.update({
            "spot_signal_global_not_user_portfolio": True,
            "portfolio_guardian_untouched_downstream": True,
            "legacy_vote_on_actions_patched": False,
            "legacy_safety_75_publication_gate": False,
            "q1_q10_publication_authority": False,
            "validated_route_still_required": True,
            "fallback_can_publish": False,
        })
        payload["contracts"] = contracts
        return jsonify(payload), status

    wrapped._commit32_wrapped = True
    flask_app.view_functions[endpoint] = wrapped


def _install_status_endpoint(app_module: Any) -> None:
    flask_app = getattr(app_module, "app", None)
    jsonify = getattr(app_module, "jsonify", None)
    if flask_app is None or not callable(jsonify) or "commit32_status" in flask_app.view_functions:
        return

    def status():
        require_auth = getattr(app_module, "_require_auth", None)
        if not callable(require_auth):
            return jsonify({"success": False, "error": "AUTH_HELPER_UNAVAILABLE"}), 503
        auth = require_auth()
        if not isinstance(auth, str): return auth
        return jsonify({
            "success": True,
            "version": VERSION,
            "publication_policy": PUBLICATION_POLICY_VERSION,
            "spot_market_signal_authority": SPOT_VERSION,
            "guardian_untouched": True,
            "execution_tempo": TEMPO_VERSION,
            "rss_mb": _rss(app_module),
            "ram_shed_mb": float(os.getenv("COMMIT32_RAM_SHED_MB", "245") or 245),
            "ram_abort_mb": float(os.getenv("COMMIT32_RAM_ABORT_MB", "285") or 285),
            "funnel": funnel_snapshot(),
        })

    flask_app.add_url_rule("/api/commit32/status", "commit32_status", status, methods=["GET"])


def install(app_module: Any) -> Dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"installed": True, "version": VERSION, "idempotent": True}
    _install_policy_version(app_module)
    _install_modern_spot_pipeline()
    _install_structure_compaction(app_module)
    _install_ram_stage_checkpoints(app_module)
    _install_futures_policy()
    _install_multiasset_policy()
    _install_entry_monitor_tempo(app_module)
    _install_telegram_truth_patch(app_module)
    _install_memory_serialization(app_module)
    _install_funnel_wrapper(app_module)
    _install_runtime_version_truth(app_module)
    _install_status_endpoint(app_module)
    setattr(app_module, "COMMIT32_RUNTIME", {
        "version": VERSION,
        "publication_policy": PUBLICATION_POLICY_VERSION,
        "spot_market_signal_authority": SPOT_VERSION,
        "guardian_untouched": True,
        "legacy_vote_on_actions_patched": False,
        "execution_tempo": TEMPO_VERSION,
        "validated_live_route_still_mandatory": True,
    })
    _INSTALLED = True
    return {"installed": True, "version": VERSION, "idempotent": False}
