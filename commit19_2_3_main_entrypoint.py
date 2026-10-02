"""Commit 19.2.4 incremental entrypoint.

Preserves Commit 19.2.3 Candle Close Authority while installing the new CPQE
quality authority and runtime/frontend recovery layer before serving traffic.
"""
from commit19_1_runtime import install_pre_app, install_post_app
_PRE = install_pre_app()
from app import app  # noqa: E402
try:
    from cpqe_19_2_4 import install_post_app as _install_c19_2_4
    _CPQE = _install_c19_2_4(app)
except Exception as exc:  # fail-open: never prevent the service from booting
    _CPQE = {"version": "COMMIT19_2_4_CPQE_LIVE_QUALITY_V1", "error": str(exc)[:240]}
_POST = install_post_app()
