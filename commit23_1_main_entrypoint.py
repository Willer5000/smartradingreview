"""Commit 23.1 Fix — preserves the known-good 19.1 -> 20.2.1 boot chain and
adds Q23 + final authority reconciliation only after app.py is loaded."""
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

try:
    import premium_path_expansion_21 as _p21
    _Q23 = _p21.install(app)
    _Q23_VERSION = getattr(_p21, "VERSION", "COMMIT23_TEN_FILTER_QUALITY_AUTHORITY_V1")
except Exception as exc:
    _Q23_VERSION = "COMMIT23_TEN_FILTER_QUALITY_AUTHORITY_V1"
    _Q23 = {
        "version": _Q23_VERSION,
        "installed": False,
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }

try:
    import commit23_1_authority_runtime as _authority
    _AUTHORITY = _authority.install(app)
    _AUTHORITY_VERSION = _authority.VERSION
except Exception as exc:
    _AUTHORITY_VERSION = "COMMIT23_1_AUTHORITY_INTEGRATION_FIX_V1"
    _AUTHORITY = {
        "version": _AUTHORITY_VERSION,
        "installed": False,
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }

COMMIT23_1_RUNTIME = {
    "entrypoint": "COMMIT23_1_AUTHORITY_INTEGRATION_FIX_V1",
    "legacy_pre": _PRE,
    "cpqe": _CPQE,
    "legacy_post": _POST,
    "ppe20": _PPE,
    "q23": _Q23,
    "q23_version": _Q23_VERSION,
    "authority": _AUTHORITY,
    "authority_version": _AUTHORITY_VERSION,
    "q10_is_mandatory": False,
    "new_network_calls": False,
    "new_workers": False,
    "render_blueprint_alignment": True,
}

# Startup diagnostics contain no secrets.
print("=" * 72, flush=True)
print("✅ COMMIT 23.1 FIX BOOT", flush=True)
print("✅ Boot chain: 19.1 PRE -> app.py -> CPQE 19.2.4 -> 19.1 POST -> PPE20 -> Q23 -> 23.1", flush=True)
print(f"✅ Q23 install: {bool(_Q23.get('installed'))}", flush=True)
print(f"✅ 23.1 authority install: {bool(_AUTHORITY.get('installed'))}", flush=True)
print("✅ Q10 remains diagnostic; thresholds unchanged", flush=True)
print("=" * 72, flush=True)
