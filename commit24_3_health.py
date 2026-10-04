"""Commit 24.3 health endpoint. No network I/O; JSON only."""
from __future__ import annotations

import os
import resource
import time
from typing import Any, Mapping


def _rss_mb_estimate() -> float:
    try:
        # Linux getrusage.ru_maxrss is KB; this is a peak estimate, intentionally
        # different from /proc VmRSS so it stays portable to local QA runs.
        return round(float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0, 1)
    except Exception:
        return 0.0


def install(app_module: Any, runtime_ns: Mapping[str, Any]):
    from flask import jsonify

    runtime_version = str(runtime_ns.get("VERSION") or "COMMIT24.3")
    q_min = float(runtime_ns.get("Q_MIN_SCORE", 75.0))
    stall = float(runtime_ns.get("STALL_EXIT_SECONDS", 105.0))

    @app_module.app.get("/api/commit24/health")
    def commit24_3_health():
        stall_fn = runtime_ns.get("_maybe_stall_exit")
        if callable(stall_fn):
            stall_fn(app_module)
        metrics_fn = runtime_ns.get("audit")
        audit = metrics_fn() if callable(metrics_fn) else {}
        app_get_pending = getattr(app_module, "_get_pending_ui_analysis_snapshot", None)
        pending_details = app_get_pending() if callable(app_get_pending) else []
        holder = str(runtime_ns.get("_HOLDER_OWNER", "") or "")
        started = float(runtime_ns.get("_HOLDER_STARTED_AT", 0.0) or 0.0)
        holder_age = round(time.monotonic() - started, 1) if started else 0.0
        metrics = dict(audit.get("metrics") or {})
        payload = {
            "success": True,
            "version": runtime_version,
            "q_min_score": q_min,
            "q_cluster_enabled": bool(runtime_ns.get("Q_CLUSTER_ENABLED", True)),
            "q_cluster_min_avg": float(runtime_ns.get("Q_CLUSTER_MIN_AVG", 72.0)),
            "q10_is_mandatory": False,
            "heavy_holder": holder or None,
            "heavy_holder_age_seconds": holder_age,
            "pending_interactive_ui": bool(pending_details),
            "pending_interactive_ui_details": pending_details,
            "pending_ui_queue_size": len(pending_details),
            "pending_ui_queue_max": int(runtime_ns.get("UI_PENDING_MAX", 5)),
            "stall_exit_seconds": stall,
            "dedupe_key_mode": "symbol|timeframe|direction",
            "dedupe_product_partition": "market-product preserved (spot/futures/multiasset remain separate)",
            "hooks": {
                "classifier": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("classifier", {}).get("installed")),
                "lifecycle": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("lifecycle", {}).get("installed")),
                "hidden_candidates": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("hidden_candidates", {}).get("installed")),
                "multiasset_diagnostics": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("multiasset_diagnostics", {}).get("installed")),
                "heavy_acquire": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("heavy_acquire", {}).get("installed")),
                "heavy_release": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("heavy_release", {}).get("installed")),
                "ui_start": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("ui_start", {}).get("installed")),
                "ui_drain": bool((runtime_ns.get("_INSTALL_RESULT") or {}).get("heavy_release", {}).get("installed")),
            },
            "metrics": metrics,
            "q_cluster_promotions": metrics.get("q_cluster_promotions", 0),
            "q_cluster_rejections": metrics.get("q_cluster_rejections", 0),
            "rss_mb_estimate": _rss_mb_estimate(),
            "resource_policy": {
                "new_network_calls": False,
                "permanent_workers": False,
                "q10_mandatory": False,
                "regime_classifier_enabled": str(os.environ.get("REGIME_CLASSIFIER_ENABLED", "false")).lower() not in {"0", "false", "no", "off"},
            },
        }
        try:
            import orjson
            from flask import Response
            return Response(orjson.dumps(payload), mimetype="application/json")
        except Exception:
            return jsonify(payload)

    return {"installed": True, "path": "/api/commit24/health"}
