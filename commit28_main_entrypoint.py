"""Commit 28 production entrypoint — core execution recovery and observability.

One-deploy repair focused on proven pipeline defects:
- native Futures/Multi execution ABI accepts execution_observations;
- same-TF BTC context is reused from existing cache (no new request);
- zero-confidence non-applicable specialists abstain instead of voting NO_OPERAR;
- Commit-28 contextual publication authority remains strict and fallback geometry
  is never publishable;
- startup fails fast if the execution ABI regresses again.

No Safety/RR/SL/TP/leverage threshold is lowered and no new worker/provider/LLM
loop is introduced.
"""
from __future__ import annotations

import inspect

from commit25_main_entrypoint import app  # noqa: F401

VERSION = "COMMIT28_CORE_EXECUTION_RECOVERY_V1"

import app as _app_module
import contextual_quality_commit28 as _c28_quality
import champion_registry_commit19 as _champions
import commit28_core as _c28_core

# Fail fast at boot instead of silently running for days with a broken geometry ABI.
_futures_module = _app_module._configured_futures_module()
_sig = inspect.signature(_futures_module.FuturesAnalysis.calculate_entry_levels)
if "execution_observations" not in _sig.parameters:
    raise RuntimeError(
        "COMMIT28_BOOT_GUARD: FuturesAnalysis.calculate_entry_levels missing "
        "execution_observations"
    )

COMMIT28_RUNTIME = {
    "version": VERSION,
    "installed": True,
    "execution_abi_native": True,
    "execution_observations_supported": True,
    "btc_context_policy": "SAME_TF_CACHE_REUSE_NO_NEW_IO",
    "specialist_abstention_policy": "ZERO_CONFIDENCE_NO_OPERAR_TO_ABSTAIN",
    "core_authority": _c28_quality.audit(),
    "core_helpers": _c28_core.audit(),
    "champion_registry": _champions.audit(),
    "spot_signal_logic_changed": False,
    "parallel_q_role": "DIAGNOSTIC_ONLY",
    "fallback_geometry_can_publish": False,
    "safety_thresholds_lowered": False,
    "frequency_quota": None,
    "new_market_data_requests": 0,
    "new_supabase_queries": 0,
    "new_llm_calls": 0,
    "new_background_threads": 0,
}

_app_module.COMMIT28_RUNTIME = COMMIT28_RUNTIME

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ Native Futures/Multi execution ABI verified at startup", flush=True)
print("✅ Same-TF BTC context reuse enabled without new market-data requests", flush=True)
print("✅ Non-applicable zero-confidence specialists are ABSTAIN, not NO_OPERAR", flush=True)
print("✅ Primary geometry -> contextual quality -> hard Safety remains the only LIVE path", flush=True)
print("✅ Fallback geometry remains ANALYSIS_ONLY; no Safety/RR thresholds lowered", flush=True)
print("=" * 72, flush=True)
