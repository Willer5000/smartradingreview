"""Commit 20.2 — Premium Path Expansion + Runtime/Save Chart Fix."""
from __future__ import annotations

from commit19_1_runtime import install_pre_app, install_post_app

_PRE = install_pre_app()
from app import app  # noqa: E402

try:
    from cpqe_19_2_4 import install_post_app as _install_cpqe
    _CPQE = _install_cpqe(app)
except Exception as exc:
    _CPQE = {
        "version": "COMMIT19_2_4_CPQE_LIVE_QUALITY_V1",
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }

_POST = install_post_app()

try:
    from premium_path_expansion_20 import install as _install_ppe
    _PPE = _install_ppe(app)
except Exception as exc:
    _PPE = {
        "version": "COMMIT20_2_PREMIUM_PATH_EXPANSION_RUNTIME_FIX_V1",
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }

COMMIT20_RUNTIME = {
    "entrypoint": "COMMIT20_2_PREMIUM_PATH_EXPANSION_RUNTIME_FIX_V1",
    "legacy_pre": _PRE,
    "cpqe": _CPQE,
    "legacy_post": _POST,
    "ppe": _PPE,
}
