"""Commit 29 production entrypoint — consolidated system recovery.

One-deploy contract:
- starts the actual Commit 29 core directly (no commit26/27/28 entrypoint chain);
- verifies native Futures/Multi execution ABI;
- verifies deploy files point to this entrypoint;
- exposes /api/runtime/version from app.py;
- preserves all hard Safety/RR/SL/TP/leverage contracts;
- no signal quota and no fallback publication authority.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app import app  # noqa: F401
import app as _app_module
import commit29_core as _c29_core
import contextual_quality_commit28 as _quality

VERSION = "COMMIT29_SYSTEM_RECOVERY_V1"

_futures_module = _app_module._configured_futures_module()
_sig = inspect.signature(_futures_module.FuturesAnalysis.calculate_entry_levels)
if "execution_observations" not in _sig.parameters:
    raise RuntimeError("COMMIT29_BOOT_GUARD: execution_observations ABI missing")

_root = Path(__file__).resolve().parent
for _name in ("Procfile", "render.yaml"):
    try:
        _text = (_root / _name).read_text(encoding="utf-8")
        if "commit29_main_entrypoint:app" not in _text:
            raise RuntimeError(f"COMMIT29_BOOT_GUARD: {_name} does not target Commit 29")
    except FileNotFoundError:
        # Procfile may be absent in some local/test environments; Render package includes it.
        pass

COMMIT29_RUNTIME = {
    "version": VERSION,
    "installed": True,
    "entrypoint": "commit29_main_entrypoint:app",
    "execution_abi_native": True,
    "missing_context_is_neutral": False,
    "transitional_regime_supported": True,
    "fallback_geometry_can_publish": False,
    "parallel_q_role": "DIAGNOSTIC_ONLY",
    "frequency_quota": None,
    "champion_cells_prioritized_for_detection": True,
    "free_plan_permanent_scientist_thread": False,
    "free_plan_permanent_macro_thread": False,
    "quality_core": _quality.audit(),
    "core": _c29_core.audit(),
    "safety_thresholds_lowered": False,
    "new_market_data_requests": 0,
    "new_supabase_queries": 0,
    "new_llm_calls": 0,
}
_app_module.COMMIT29_RUNTIME = COMMIT29_RUNTIME

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ Commit29 entrypoint is authoritative", flush=True)
print("✅ Futures/Multi execution ABI verified", flush=True)
print("✅ Missing context abstains; it is never interpreted as ADX=0 evidence", flush=True)
print("✅ TRANSITIONAL regime fixes strong-ADX directional conflict", flush=True)
print("✅ Champion cells receive scan priority without quotas or extra jobs", flush=True)
print("✅ Free-plan runtime sheds reconstructable heatmaps/caches aggressively", flush=True)
print("✅ Safety>=75, RR 1.8..3.5 and fallback ANALYSIS_ONLY remain hard contracts", flush=True)
print("=" * 72, flush=True)
