"""Commit 25 production entrypoint — contextual Champion recovery + anti-overfit authority.

Boots the existing Commit-24.5R-compatible application.  Commit-25 itself adds
no workers, no polling, no market-data request, no Supabase read/write and no
LLM call.  Its signal-frequency change comes from restoring the missing pure
Champion registry/decay modules and carrying their governed evidence through Q.
"""
from __future__ import annotations

from commit24_main_entrypoint import app  # noqa: F401

VERSION = "COMMIT25_CONTEXTUAL_CHAMPION_RECOVERY_ANTI_OVERFIT_V1"

try:
    import champion_registry_commit19 as _registry
    import champion_decay_commit19 as _decay
    import synthesis_decay_commit19_1 as _synth_decay
    import quality_9q_engine_21 as _quality
    import commit24_repair_runtime as _c24

    # Make the public runtime metadata match the restored native-gate policy.
    try:
        _c24._INSTALL_RESULT.setdefault("policy", {})["q10_is_mandatory"] = True
        _c24._INSTALL_RESULT["policy"]["parallel_quality_role"] = "DIAGNOSTIC_ONLY"
    except Exception:
        pass

    COMMIT25_RUNTIME = {
        "version": VERSION,
        "installed": True,
        "champion_registry": _registry.audit(),
        "champion_decay": getattr(_decay, "VERSION", "UNKNOWN"),
        "synthesis_decay": getattr(_synth_decay, "VERSION", "UNKNOWN"),
        "quality_engine": getattr(_quality, "VERSION", "UNKNOWN"),
        "parallel_quality_role": "DIAGNOSTIC_ONLY",
        "native_publication_gate_authority": True,
        "q10_is_mandatory": True,
        "new_market_data_requests": 0,
        "new_supabase_queries": 0,
        "new_llm_calls": 0,
        "new_background_threads": 0,
    }
except Exception as exc:
    # Do not hide startup failure: this commit's missing governance modules are
    # a hard deployment defect, unlike the prior silent fail-safe.
    COMMIT25_RUNTIME = {
        "version": VERSION,
        "installed": False,
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }
    raise

try:
    import app as _app_module
    _app_module.COMMIT25_RUNTIME = COMMIT25_RUNTIME
except Exception:
    pass

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ Contextual Champions restored; no cross-asset extrapolation", flush=True)
print("✅ Q1..Q10 parallel scores diagnostic-only; native economic gate authoritative", flush=True)
print("✅ No new requests / Supabase reads / LLM calls / background threads", flush=True)
print("=" * 72, flush=True)
