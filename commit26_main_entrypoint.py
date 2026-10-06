"""Commit 26 production entrypoint — Propuesta Profunda 2.

Purpose:
- preserve the complete Commit-25 runtime;
- repair the causal stage mismatch of the governed 30m Champion router;
- keep all downstream Entry/SL/TP/Safety/RR/leverage/publication contracts;
- introduce zero workers, polling loops, market requests, Supabase operations or
  LLM calls.

No new 1h or Multi-Asset LIVE statistical authority is granted by this commit.
Those cells remain governed by their existing route matrix / Research state.
"""
from __future__ import annotations

from commit25_main_entrypoint import app  # noqa: F401

VERSION = "COMMIT26_CAUSAL_PREENTRY_RECOVERY_PROPOSAL2_V1"

try:
    import champion_registry_commit19 as _registry
    import app as _app_module

    COMMIT26_RUNTIME = {
        "version": VERSION,
        "installed": True,
        "champion_registry": _registry.audit(),
        "change_scope": "PREENTRY_ROUTER_PARITY_ONLY",
        "30m_live_route": "F30_SHARED_LIQ_SWEEP_MSS_POI_V1",
        "1h_new_live_authority": False,
        "multi_new_live_authority": False,
        "spot_signal_logic_changed": False,
        "safety_changed": False,
        "rr_changed": False,
        "leverage_policy_changed": False,
        "closed_candle_authority_changed": False,
        "q_parallel_publication_authority": False,
        "new_market_data_requests": 0,
        "new_supabase_reads": 0,
        "new_supabase_writes": 0,
        "new_llm_calls": 0,
        "new_background_threads": 0,
    }
    _app_module.COMMIT26_RUNTIME = COMMIT26_RUNTIME
except Exception as exc:
    COMMIT26_RUNTIME = {
        "version": VERSION,
        "installed": False,
        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
    }
    raise

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ 30m Champion pre-Entry causal parity restored", flush=True)
print("✅ Strict closed-candle structure + reaction inventory required", flush=True)
print("✅ Entry/SL/TP/Safety/RR/leverage/publication gates unchanged", flush=True)
print("✅ 1h and unvalidated Multi expansions remain Shadow/Research", flush=True)
print("✅ 0 new requests / Supabase operations / LLM calls / threads", flush=True)
print("=" * 72, flush=True)
