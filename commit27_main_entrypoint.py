"""Commit 27 production entrypoint — unified contextual signal authority.

Commit 27 deliberately boots the fully hardened Commit-25/24 runtime first, then
exposes the core policy implemented directly in app.py and
contextual_quality_commit27.py.  No extra worker, scheduler, provider request,
Supabase call or LLM loop is added.
"""
from __future__ import annotations

from commit25_main_entrypoint import app  # noqa: F401

VERSION = "COMMIT27_UNIFIED_CONTEXTUAL_SIGNAL_CORE_V1"

import contextual_quality_commit27 as _c27_quality
import champion_registry_commit19 as _c27_registry

COMMIT27_RUNTIME = {
    "version": VERSION,
    "installed": True,
    "core_authority": _c27_quality.audit(),
    "champion_registry": _c27_registry.audit(),
    "spot_signal_logic_changed": False,
    "futures_final_authority": "APP_PY_COMMIT27_SINGLE_CONTEXTUAL_AUTHORITY",
    "multiasset_final_authority": "APP_PY_COMMIT27_SINGLE_CONTEXTUAL_AUTHORITY",
    "parallel_q_role": "DIAGNOSTIC_ONLY",
    "max_q_can_publish": False,
    "fallback_geometry_can_publish": False,
    "frequency_quota": None,
    "new_market_data_requests": 0,
    "new_supabase_queries": 0,
    "new_llm_calls": 0,
    "new_background_threads": 0,
}

try:
    import app as _app_module
    _app_module.COMMIT27_RUNTIME = COMMIT27_RUNTIME
except Exception:
    pass

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ One final contextual authority for Futures + Multi-Asset", flush=True)
print("✅ 30m structure confirmation moved to post-geometry (backtest parity)", flush=True)
print("✅ Q1..Q10 parallel lanes are diagnostics; max(Q) cannot publish", flush=True)
print("✅ Manual/final-visibility fallback geometry can never publish", flush=True)
print("✅ Spot signal logic unchanged; no frequency quota", flush=True)
print("✅ No new requests / Supabase reads / LLM calls / background threads", flush=True)
print("=" * 72, flush=True)
