"""Commit 24 production entrypoint.

Loads the proven Commit 23.1 boot chain first, then applies the real runtime
repair to the already-imported app.py.
"""
from __future__ import annotations

from commit23_1_main_entrypoint import app  # noqa: F401

try:
    import commit24_repair_runtime as _repair
    COMMIT24_INSTALL = _repair.install(app)
    COMMIT24_VERSION = _repair.VERSION
except Exception as exc:
    COMMIT24_VERSION = "COMMIT24_REAL_Q_AUTHORITY_FAIR_RUNTIME_V1"
    COMMIT24_INSTALL = {
        "installed": False,
        "version": COMMIT24_VERSION,
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }

COMMIT24_RUNTIME = {
    "version": COMMIT24_VERSION,
    "install": COMMIT24_INSTALL,
    "q10_is_mandatory": False,
    "thresholds_lowered": False,
    "new_market_data_requests": False,
    "new_permanent_workers": False,
}
