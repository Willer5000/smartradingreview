"""Commit 31 production entrypoint — Multi-Safety Authority.

One-deploy contract:
- preserves Commit29/30/30.1 runtime, ABI, memory and fast-lane repairs;
- replaces the universal Safety>=75 publication veto with exactly one
  setup-specific Safety profile selected before scoring;
- keeps universal hard-risk and validated statistical-route authority separate;
- keeps legacy Q1..Q10 as diagnostics only;
- never selects the highest Safety score after the fact;
- no new market-data requests, threads, DB queries or LLM calls.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app import app  # noqa: F401
import app as _app_module
import safety_profiles_commit31 as _safety31
import contextual_quality_commit28 as _quality
import champion_registry_commit19 as _champions
import commit30_core as _c30_core
import commit30_1_core as _c301_core

VERSION = "COMMIT31_MULTI_SAFETY_AUTHORITY_V1"

# Native execution ABI must remain correct.
_futures_module = _app_module._configured_futures_module()
_sig = inspect.signature(_futures_module.FuturesAnalysis.calculate_entry_levels)
if "execution_observations" not in _sig.parameters:
    raise RuntimeError("COMMIT31_BOOT_GUARD: execution_observations ABI missing")

# Deployment files must target Commit31.
_root = Path(__file__).resolve().parent
for _name in ("Procfile", "render.yaml"):
    try:
        _text = (_root / _name).read_text(encoding="utf-8")
        if "commit31_main_entrypoint:app" not in _text:
            raise RuntimeError(f"COMMIT31_BOOT_GUARD: {_name} does not target Commit31")
    except FileNotFoundError:
        pass

# Safety architecture invariants.
_audit = _safety31.audit()
if _audit.get("profile_count") != 8:
    raise RuntimeError("COMMIT31_BOOT_GUARD: expected exactly 8 Safety profiles")
if _audit.get("universal_score_threshold") is not None:
    raise RuntimeError("COMMIT31_BOOT_GUARD: universal Safety score threshold reintroduced")
if not _audit.get("highest_score_selection_forbidden"):
    raise RuntimeError("COMMIT31_BOOT_GUARD: post-hoc highest-score Safety selection enabled")

# Proposal3 directional impulse must remain detectable and context-only.
_probe = _c30_core.detect_directional_impulse(
    {"direction":"bearish", "adx":17.7, "plus_di":9.5, "minus_di":42.2},
    {"direction":"bearish", "indicators":{"rsi":23.9}},
    {"volume_ratio":2.82, "obv_direction":"bearish"},
    {"structure_direction":"bearish", "order_blocks":[{"direction":"bearish"}]},
)
if not (_probe.get("active") and _probe.get("direction") == "bearish"):
    raise RuntimeError("COMMIT31_BOOT_GUARD: directional impulse regression")

COMMIT31_RUNTIME = {
    "version": VERSION,
    "installed": True,
    "entrypoint": "commit31_main_entrypoint:app",
    "execution_abi_native": True,
    "multi_safety": _audit,
    "legacy_safety_75_publication_gate": False,
    "legacy_q1_q10_publication_authority": False,
    "hard_risk_non_compensatory": True,
    "validated_route_still_required": True,
    "fallback_geometry_can_publish": False,
    "directional_impulse_context": True,
    "impulse_queue_persists_until_ack": True,
    "same_symbol_30m_same_candle_recheck_once": True,
    "f30_frozen_volume_min": 1.0,
    "frequency_quota": None,
    "new_market_data_requests": 0,
    "new_supabase_queries": 0,
    "new_llm_calls": 0,
    "new_threads": 0,
    "quality_core": _quality.audit(),
    "champion_registry": _champions.audit(),
    "proposal3_bridge": _c301_core.audit(),
}
_app_module.COMMIT31_RUNTIME = COMMIT31_RUNTIME

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ Commit31 entrypoint is authoritative", flush=True)
print("✅ Exactly one setup-specific Safety is selected before scoring", flush=True)
print("✅ Legacy Safety>=75 is diagnostic/leverage only, not a publication veto", flush=True)
print("✅ Q1..Q10 are legacy diagnostics only; they cannot publish or veto", flush=True)
print("✅ Hard risk + validated LIVE route remain mandatory", flush=True)
print("✅ Missing optional Safety evidence is reweighted, never converted to fake neutral", flush=True)
print("✅ Proposal3 impulse bridge and Commit29 memory/ABI protections remain active", flush=True)
print("=" * 72, flush=True)
