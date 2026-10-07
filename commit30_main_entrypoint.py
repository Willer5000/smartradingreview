"""Commit 30 / Proposal 3 production entrypoint — directional impulse recovery.

One-deploy contract:
- retains Commit29 runtime/memory/ABI repairs;
- detects early DMI+momentum directional displacement even while ADX lags;
- treats the 1h impulse as context/event evidence, NEVER as standalone alpha;
- reprioritizes only existing validated 30m Champion cells on the same close;
- direct 1h publication still needs an independently validated live route;
- all Safety/RR/SL/TP/fallback contracts remain hard.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app import app  # noqa: F401
import app as _app_module
import commit30_core as _c30_core
import contextual_quality_commit28 as _quality

VERSION = "COMMIT30_PROPOSAL3_DIRECTIONAL_IMPULSE_RECOVERY_V1"

_futures_module = _app_module._configured_futures_module()
_sig = inspect.signature(_futures_module.FuturesAnalysis.calculate_entry_levels)
if "execution_observations" not in _sig.parameters:
    raise RuntimeError("COMMIT30_BOOT_GUARD: execution_observations ABI missing")

_root = Path(__file__).resolve().parent
for _name in ("Procfile", "render.yaml"):
    try:
        _text = (_root / _name).read_text(encoding="utf-8")
        if "commit30_main_entrypoint:app" not in _text:
            raise RuntimeError(f"COMMIT30_BOOT_GUARD: {_name} does not target Commit 30")
    except FileNotFoundError:
        pass

# Deterministic regression guard for the observed missed-crash class.
_probe = _c30_core.detect_directional_impulse(
    {"direction":"bearish", "adx":17.7, "plus_di":9.5, "minus_di":42.2},
    {"direction":"bearish", "indicators":{"rsi":23.9}},
    {"volume_ratio":2.82, "obv_direction":"bearish"},
    {"structure_direction":"bearish", "order_blocks":[{"direction":"bearish"}]},
)
if not (_probe.get("active") and _probe.get("direction") == "bearish"):
    raise RuntimeError("COMMIT30_BOOT_GUARD: directional-impulse detector regression")

COMMIT30_RUNTIME = {
    "version": VERSION,
    "installed": True,
    "entrypoint": "commit30_main_entrypoint:app",
    "execution_abi_native": True,
    "directional_impulse_context": True,
    "directional_impulse_can_publish_directly": False,
    "impulse_bridges_to_validated_30m": True,
    "missing_context_is_neutral": False,
    "fallback_geometry_can_publish": False,
    "parallel_q_role": "DIAGNOSTIC_ONLY",
    "frequency_quota": None,
    "safety_thresholds_lowered": False,
    "new_market_data_requests": 0,
    "new_supabase_queries": 0,
    "new_llm_calls": 0,
    "new_threads": 0,
    "quality_core": _quality.audit(),
    "core": _c30_core.audit(),
}
_app_module.COMMIT30_RUNTIME = COMMIT30_RUNTIME

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ Commit30 entrypoint is authoritative", flush=True)
print("✅ Early DMI directional impulse is recognized even when ADX lags", flush=True)
print("✅ 1h impulse is CONTEXT ONLY; it cannot self-promote to Premium", flush=True)
print("✅ Existing validated 30m Champion cells are reprioritized after a 1h impulse", flush=True)
print("✅ Direct 1h route remains Shadow until clean IS/Selection/OOS validates it", flush=True)
print("✅ Commit29 ABI, ABSTAIN, context and free-runtime protections are preserved", flush=True)
print("✅ Safety>=75, RR 1.8..3.5 and fallback ANALYSIS_ONLY remain hard contracts", flush=True)
print("=" * 72, flush=True)
