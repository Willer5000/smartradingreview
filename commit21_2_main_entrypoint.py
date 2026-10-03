"""Commit 21.2 entrypoint.

Imports the central Flask app and ensures the 21.2 route/CPQE overlay is installed
exactly once. No extra workers or threads are introduced.
"""
from app import app

try:
    from premium_path_expansion_20 import install as _install_premium_21_2
    _COMMIT21_2_OVERLAY = _install_premium_21_2(app) or {}
    print(f"✅ [COMMIT21.2] entrypoint overlay: {_COMMIT21_2_OVERLAY}", flush=True)
except Exception as exc:
    _COMMIT21_2_OVERLAY = {"version": "COMMIT21_2", "error": f"{type(exc).__name__}: {str(exc)[:220]}"}
    print(f"⚠️ [COMMIT21.2] overlay error: {_COMMIT21_2_OVERLAY['error']}", flush=True)
