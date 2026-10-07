"""Commit 30.1 production entrypoint — Proposal 3 fast-lane bridge repair.

One-deploy contract:
- preserves Commit29/30 ABI, memory and directional-impulse repairs;
- keeps a 1h impulse CONTEXT_ONLY (never standalone live alpha);
- persists the impulse queue until a successful 30m analysis ACKs it;
- re-evaluates the same-symbol 30m closed candle once when fresh 1h context arrives;
- prevents ordinary UI cooldown from starving the impulse fast lane;
- uses the broader pre-existing ADX20/Vol1.00/RSI80 F30 stability point;
- preserves hard Safety/RR/SL/TP/fallback rules.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app import app  # noqa: F401
import app as _app_module
import commit30_core as _c30_core
import commit30_1_core as _c301_core
import contextual_quality_commit28 as _quality
import champion_registry_commit19 as _champions

VERSION = "COMMIT30_1_PROPOSAL3_FAST_LANE_BRIDGE_V1"

# Native execution ABI must remain correct.
_futures_module = _app_module._configured_futures_module()
_sig = inspect.signature(_futures_module.FuturesAnalysis.calculate_entry_levels)
if "execution_observations" not in _sig.parameters:
    raise RuntimeError("COMMIT30_1_BOOT_GUARD: execution_observations ABI missing")

# Deployment files must target 30.1 in the shipped package.
_root = Path(__file__).resolve().parent
for _name in ("Procfile", "render.yaml"):
    try:
        _text = (_root / _name).read_text(encoding="utf-8")
        if "commit30_1_main_entrypoint:app" not in _text:
            raise RuntimeError(f"COMMIT30_1_BOOT_GUARD: {_name} does not target Commit 30.1")
    except FileNotFoundError:
        pass

# The missed-crash class must still be detected.
_probe = _c30_core.detect_directional_impulse(
    {"direction":"bearish", "adx":17.7, "plus_di":9.5, "minus_di":42.2},
    {"direction":"bearish", "indicators":{"rsi":23.9}},
    {"volume_ratio":2.82, "obv_direction":"bearish"},
    {"structure_direction":"bearish", "order_blocks":[{"direction":"bearish"}]},
)
if not (_probe.get("active") and _probe.get("direction") == "bearish"):
    raise RuntimeError("COMMIT30_1_BOOT_GUARD: directional impulse regression")

# The F30 live contract must use the pre-existing broader stability point.
_registry = _champions.route_registry()
_f30 = dict((_registry or {}).get("F30_SHARED_LIQ_SWEEP_MSS_POI_V1") or {})
_contract = dict(_f30.get("routing_contract") or {})
if float(_contract.get("volume_ratio_min", 999)) != 1.0 or float(_contract.get("adx_min", -1)) != 20.0:
    raise RuntimeError("COMMIT30_1_BOOT_GUARD: frozen F30 stability contract not active")

COMMIT30_1_RUNTIME = {
    "version": VERSION,
    "installed": True,
    "entrypoint": "commit30_1_main_entrypoint:app",
    "execution_abi_native": True,
    "directional_impulse_context": True,
    "directional_impulse_can_publish_directly": False,
    "impulse_queue_persists_until_ack": True,
    "same_symbol_30m_same_candle_recheck_once": True,
    "ui_cooldown_can_starve_impulse_lane": False,
    "f30_frozen_volume_min": 1.0,
    "f30_adx_min": 20.0,
    "fallback_geometry_can_publish": False,
    "parallel_q_role": "DIAGNOSTIC_ONLY",
    "frequency_quota": None,
    "safety_thresholds_lowered": False,
    "new_live_1h_route": False,
    "new_multiasset_live_route": False,
    "new_market_data_requests": 0,
    "new_supabase_queries": 0,
    "new_llm_calls": 0,
    "new_threads": 0,
    "quality_core": _quality.audit(),
    "champion_registry": _champions.audit(),
    "core": _c301_core.audit(),
}
_app_module.COMMIT30_1_RUNTIME = COMMIT30_1_RUNTIME

print("=" * 72, flush=True)
print(f"✅ {VERSION}", flush=True)
print("✅ Commit30.1 entrypoint is authoritative", flush=True)
print("✅ Proposal3 impulse remains CONTEXT ONLY; no direct 1h publication", flush=True)
print("✅ Impulse queue persists until successful 30m ACK", flush=True)
print("✅ Same-symbol 30m may re-evaluate the same closed candle once after fresh 1h context", flush=True)
print("✅ UI navigation cooldown cannot starve the impulse lane; heavy lock + memory guards remain hard", flush=True)
print("✅ F30 uses frozen broader stability contract ADX>=20 / Vol>=1.00 / RSI anti-chase", flush=True)
print("✅ Safety>=75, RR 1.8..3.5 and fallback ANALYSIS_ONLY remain hard contracts", flush=True)
print("=" * 72, flush=True)
