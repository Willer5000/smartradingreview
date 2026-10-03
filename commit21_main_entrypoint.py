"""Commit 21 — Premium Strategy Route Engine entrypoint."""
from __future__ import annotations

# Importing app.py auto-installs the Commit 21 overlay through the retained
# premium_path_expansion_20 module name, which keeps manual Render
# ``gunicorn app:app`` deployments safe.
from app import app  # noqa: F401,E402

try:
    from premium_path_expansion_20 import install, VERSION
    _COMMIT21 = install(app)
except Exception as exc:
    VERSION = "COMMIT21_PREMIUM_STRATEGY_ROUTE_ENGINE_V1"
    _COMMIT21 = {"version": VERSION, "installed": False, "error": f"{type(exc).__name__}: {str(exc)[:240]}"}

COMMIT21_RUNTIME = {
    "entrypoint": VERSION,
    "overlay": _COMMIT21,
    "premium_thresholds_unchanged": True,
    "fallback_never_promoted": True,
    "live_parameter_fitting": False,
}
