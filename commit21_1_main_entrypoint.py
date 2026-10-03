"""Commit 21.1 — Premium Strategy Route Engine + runtime/chart fixes."""
from __future__ import annotations

from app import app  # noqa: F401,E402

try:
    from premium_path_expansion_20 import install, VERSION
    _COMMIT21_1 = install(app)
except Exception as exc:
    VERSION = "COMMIT21_1_PREMIUM_STRATEGY_ROUTE_ENGINE_FIX_V1"
    _COMMIT21_1 = {
        "version": VERSION,
        "installed": False,
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }

COMMIT21_1_RUNTIME = {
    "entrypoint": VERSION,
    "overlay": _COMMIT21_1,
    "premium_thresholds_unchanged": True,
    "fallback_never_promoted": True,
    "live_parameter_fitting": False,
    "light_visuals_endpoint": True,
    "memory_start_limit_target_mb": 225,
}
