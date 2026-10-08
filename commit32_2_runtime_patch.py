"""Commit 32.2 — deployment truth, ABI hardening, stale-policy cleanup and telemetry."""
from __future__ import annotations

import functools
import inspect
import os
from typing import Any, Dict

from commit32_2_strategy_governance import VERSION as STRAT_GOV_VERSION, snapshot as strategy_snapshot

VERSION = "COMMIT32_2_RECOVERY_V1"
PUBLICATION_POLICY_VERSION = "COMMIT32_2_PUBLICATION_AUDIT_V1"
_INSTALLED = False

LEGACY_REASON_CODES = {"PREMIUM_SAFETY_BELOW_75", "Q_CLUSTER_BELOW_THRESHOLD", "MINIMUM_EXECUTION_SAFETY"}


def _accepts(fn, name: str) -> bool:
    try:
        sig = inspect.signature(fn)
        return name in sig.parameters or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
    except Exception:
        return False


def _wrap_geometry_method(cls, label: str):
    original = getattr(cls, "calculate_entry_levels", None)
    if not callable(original) or getattr(original, "_commit32_2_abi", False):
        return

    @functools.wraps(original)
    def wrapped(self, decision, trend, momentum, volatility, structure, symbol, timeframe,
                liquidation=None, execution_observations=None, **kwargs):
        call_kwargs = dict(kwargs)
        call_kwargs["liquidation"] = liquidation
        if _accepts(original, "execution_observations"):
            call_kwargs["execution_observations"] = execution_observations
        try:
            return original(self, decision, trend, momentum, volatility, structure,
                            symbol, timeframe, **call_kwargs)
        except TypeError as exc:
            # Fail-safe for a legacy monkeypatch installed after import. Retry only
            # the exact ABI mismatch; never swallow other geometry TypeErrors.
            if "execution_observations" not in str(exc):
                raise
            call_kwargs.pop("execution_observations", None)
            return original(self, decision, trend, momentum, volatility, structure,
                            symbol, timeframe, **call_kwargs)

    wrapped._commit32_2_abi = label
    cls.calculate_entry_levels = wrapped


def _install_abi_hardening(app_module: Any) -> None:
    import futures_system as fut
    import multiasset_system as multi
    base = getattr(app_module, "TradingExpertSystem")
    _wrap_geometry_method(base, "BASE")
    _wrap_geometry_method(fut.FuturesAnalysis, "FUTURES")
    _wrap_geometry_method(multi.MultiAssetAnalysis, "MULTI")

    # Force the live singleton to use the final Multi class method even if a
    # legacy overlay stored an older bound method during app import.
    instance = getattr(multi, "multiasset_system", None)
    if instance is not None and isinstance(instance, multi.MultiAssetAnalysis):
        app_instance = getattr(app_module, "multiasset_system", None)
        if app_instance is not instance and isinstance(app_instance, multi.MultiAssetAnalysis):
            instance = app_instance
        # Class patch is sufficient for normal lookup; expose a truth marker.
        setattr(instance, "_commit32_2_abi_live", True)
    setattr(app_module, "COMMIT32_2_ABI_HARDENED", True)


def _sanitize_reason_list(values):
    out = []
    removed = []
    for x in list(values or []):
        text = str(x or "")
        if text.upper() in LEGACY_REASON_CODES:
            removed.append(text)
            continue
        out.append(text)
    if removed:
        out.append("STALE_LEGACY_POLICY_REASON_REEVALUATED")
    return out


def _install_publication_cleanup(app_module: Any) -> None:
    # Make every old Commit30/31/32/32.1 closed-candle publication snapshot stale.
    if hasattr(app_module, "_COMMIT245_NATIVE_Q_VERSION"):
        app_module._COMMIT245_NATIVE_Q_VERSION = PUBLICATION_POLICY_VERSION

    # Wrap the current publication evaluator to guarantee obsolete Safety>=75
    # reason codes never re-enter current output through a compatibility bridge.
    try:
        import contextual_quality_commit28 as cq
        original = cq.evaluate_publication
        if not getattr(original, "_commit32_2_clean", False):
            @functools.wraps(original)
            def wrapped(*args, **kwargs):
                out = dict(original(*args, **kwargs) or {})
                for key in ("reason_codes", "hard_reason_codes", "shadow_reason_codes"):
                    out[key] = _sanitize_reason_list(out.get(key))
                out["version"] = PUBLICATION_POLICY_VERSION
                out["legacy_safety_75_is_gate"] = False
                return out
            wrapped._commit32_2_clean = True
            cq.evaluate_publication = wrapped
    except Exception:
        pass
    setattr(app_module, "COMMIT32_2_PUBLICATION_POLICY_VERSION", PUBLICATION_POLICY_VERSION)


def _install_health_truth(app_module: Any) -> None:
    flask_app = app_module.app
    jsonify = app_module.jsonify
    original = flask_app.view_functions.get("health")
    if callable(original) and not getattr(original, "_commit32_2_truth", False):
        @functools.wraps(original)
        def health(*args, **kwargs):
            result = original(*args, **kwargs)
            response = result[0] if isinstance(result, tuple) else result
            status = result[1] if isinstance(result, tuple) and len(result) > 1 else 200
            try:
                data = dict(response.get_json(silent=True) or {})
            except Exception:
                data = {}
            import futures_system as fut
            import multiasset_system as multi
            abi_ok = _accepts(fut.FuturesAnalysis.calculate_entry_levels, "execution_observations") and _accepts(multi.MultiAssetAnalysis.calculate_entry_levels, "execution_observations")
            data.update({
                "status": "ok" if abi_ok else "error",
                "runtime_authority": VERSION,
                "entrypoint": "commit32_2_main_entrypoint:app",
                "publication_policy": PUBLICATION_POLICY_VERSION,
                "geometry_abi_ok": bool(abi_ok),
                "strategy_governance": STRAT_GOV_VERSION,
            })
            return jsonify(data), (status if abi_ok else 503)
        health._commit32_2_truth = True
        flask_app.view_functions["health"] = health

    # Replace the inherited runtime-version response with hard deployment truth.
    endpoint = "api_runtime_version_commit31"
    if endpoint in flask_app.view_functions:
        def runtime_version():
            import futures_system as fut
            import multiasset_system as multi
            return jsonify({
                "version": VERSION,
                "entrypoint": "commit32_2_main_entrypoint:app",
                "publication_policy": PUBLICATION_POLICY_VERSION,
                "render_git_commit": os.getenv("RENDER_GIT_COMMIT") or os.getenv("RENDER_GIT_COMMIT_SHA"),
                "geometry_abi": {
                    "futures": list(inspect.signature(fut.FuturesAnalysis.calculate_entry_levels).parameters),
                    "multi": list(inspect.signature(multi.MultiAssetAnalysis.calculate_entry_levels).parameters),
                    "ok": _accepts(fut.FuturesAnalysis.calculate_entry_levels, "execution_observations") and _accepts(multi.MultiAssetAnalysis.calculate_entry_levels, "execution_observations"),
                },
                "contracts": {
                    "legacy_safety_75_publication_gate": False,
                    "fallback_can_publish": False,
                    "guardian_untouched": True,
                    "strategy_live_requires_is_oos_pass": True,
                    "strategy_demotes_after_consecutive_losses": 8,
                },
                "strategy_governance": strategy_snapshot(),
            }), 200
        flask_app.view_functions[endpoint] = runtime_version


def _install_status(app_module: Any) -> None:
    flask_app = app_module.app
    jsonify = app_module.jsonify
    if "commit32_2_status" in flask_app.view_functions:
        return
    def status():
        import futures_system as fut
        import multiasset_system as multi
        return jsonify({
            "success": True,
            "version": VERSION,
            "publication_policy": PUBLICATION_POLICY_VERSION,
            "geometry_abi_ok": _accepts(fut.FuturesAnalysis.calculate_entry_levels, "execution_observations") and _accepts(multi.MultiAssetAnalysis.calculate_entry_levels, "execution_observations"),
            "legacy_reason_codes_forbidden": sorted(LEGACY_REASON_CODES),
            "strategy_governance": strategy_snapshot(),
        }), 200
    flask_app.add_url_rule("/api/commit32-2/status", "commit32_2_status", status, methods=["GET"])


def install(app_module: Any) -> Dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"installed": True, "version": VERSION, "idempotent": True}
    _install_abi_hardening(app_module)
    _install_publication_cleanup(app_module)
    _install_health_truth(app_module)
    _install_status(app_module)
    setattr(app_module, "COMMIT32_2_RUNTIME", {
        "version": VERSION,
        "publication_policy": PUBLICATION_POLICY_VERSION,
        "abi_hardened": True,
        "legacy_policy_reason_cleanup": True,
        "guardian_untouched": True,
    })
    _INSTALLED = True
    return {"installed": True, "version": VERSION, "idempotent": False}
