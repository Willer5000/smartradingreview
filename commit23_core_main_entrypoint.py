"""Commit 23 CORE — actual production entrypoint for the quality-authority nucleus."""
from __future__ import annotations
from app import app  # noqa: F401,E402

BASE_INSTALL = {}
QUALITY_INSTALL = {}

try:
    from premium_path_expansion_20 import install as install_base, VERSION as BASE_VERSION
    BASE_INSTALL = install_base(app)
except Exception as exc:
    BASE_VERSION = "COMMIT20_2_1_STABILITY_FIX_V1"
    BASE_INSTALL = {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:240]}"}

try:
    import premium_path_expansion_21 as p21
    QUALITY_INSTALL = p21.install(app)
    QUALITY_VERSION = p21.VERSION
except Exception as exc:
    QUALITY_VERSION = "COMMIT23_TEN_FILTER_QUALITY_AUTHORITY_V1"
    QUALITY_INSTALL = {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:240]}"}

COMMIT23_CORE_RUNTIME = {
    "base_version": BASE_VERSION,
    "quality_version": QUALITY_VERSION,
    "base_install": BASE_INSTALL,
    "quality_install": QUALITY_INSTALL,
    "q10_is_mandatory": False,
    "q10_thresholds_unchanged": True,
    "one_of_ten_quality_authority": True,
    "new_network_calls": False,
    "new_threads": False,
}
