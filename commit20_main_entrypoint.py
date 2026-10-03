"""Commit 20 — Premium Path Expansion production entrypoint.

Keeps the existing Commit 19.x runtime when available, installs CPQE 19.2.4,
then installs the bounded Commit 20 PPE layer. All overlays are fail-open for
boot: diagnostics must never prevent the application from serving traffic.
"""
from __future__ import annotations

_PRE = {"version": "COMMIT20_BOOT", "legacy_runtime": "UNAVAILABLE"}
_POST = {}

try:
    from commit19_1_runtime import install_pre_app
    _PRE = install_pre_app()
except Exception as exc:
    # The source repository historically had a missing legacy runtime module in
    # some recovery ZIPs. Commit 20 remains bootable directly from app.py while
    # exposing the mismatch through /health. No trading threshold is changed.
    _PRE = {
        "version": "COMMIT20_BOOT",
        "legacy_runtime": "IMPORT_FAILED",
        "legacy_runtime_error": f"{type(exc).__name__}: {str(exc)[:180]}",
    }

from app import app  # noqa: E402

try:
    from cpqe_19_2_4 import install_post_app as _install_cpqe
    _CPQE = _install_cpqe(app)
except Exception as exc:  # fail-open
    _CPQE = {
        "version": "COMMIT19_2_4_CPQE_LIVE_QUALITY_V1",
        "error": f"{type(exc).__name__}: {str(exc)[:180]}",
    }

try:
    from commit19_1_runtime import install_post_app
    _POST = install_post_app()
except Exception as exc:
    _POST = {
        "legacy_runtime_post": "IMPORT_FAILED",
        "legacy_runtime_error": f"{type(exc).__name__}: {str(exc)[:180]}",
    }

try:
    from premium_path_expansion_20 import install as _install_ppe
    _PPE = _install_ppe(app)
except Exception as exc:  # fail-open: PPE is an enhancer, not a boot prerequisite
    _PPE = {
        "version": "COMMIT20_PREMIUM_PATH_EXPANSION_V1",
        "error": f"{type(exc).__name__}: {str(exc)[:180]}",
    }

# Public module state is intentionally compact and safe for /health diagnostics.
COMMIT20_RUNTIME = {
    "entrypoint": "COMMIT20_PREMIUM_PATH_EXPANSION_V1",
    "legacy_pre": _PRE,
    "cpqe": _CPQE,
    "legacy_post": _POST,
    "ppe": _PPE,
}
