"""Commit 32 execution-tempo policy.

Changes entry reaction tempo only. It never changes Entry/SL/TP calculation,
RR, Safety, risk budgets, Guardian or statistical LIVE authority.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict

VERSION = "COMMIT32_EXECUTION_TEMPO_V2"

TEMPO_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "CORE1": {"name": "QUICK_CORE", "entry_zone_pct": 0.12, "max_entry_wait_bars": 3},
    "CORE2": {"name": "QUICK_CORE_CONTROLLED", "entry_zone_pct": 0.11, "max_entry_wait_bars": 3},
    "MEDIUM": {"name": "FASTER", "entry_zone_pct": 0.08, "max_entry_wait_bars": 2},
    "HIGH": {"name": "ULTRA_FAST", "entry_zone_pct": 0.05, "max_entry_wait_bars": 1},
}

MULTIASSET_TEMPO: Dict[str, Dict[str, Any]] = {
    "1h": {"lane": "FAST_LANE", "entry_zone_pct_cap": 0.08, "max_entry_wait_bars": 1},
    "4h": {"lane": "PRECISE_EXECUTION", "entry_zone_pct_cap": 0.10, "max_entry_wait_bars": 2},
    "1D": {"lane": "VALIDATED_SWING_CONTEXT", "entry_zone_pct_cap": 0.12, "max_entry_wait_bars": 2},
}


def install_futures_tempo(futures_universe_module: Any) -> Dict[str, Dict[str, Any]]:
    profiles = getattr(futures_universe_module, "EXIT_PROFILES", None)
    if not isinstance(profiles, dict):
        raise RuntimeError("Commit32: futures_universe.EXIT_PROFILES unavailable")
    before = deepcopy(profiles)
    for risk_class, override in TEMPO_OVERRIDES.items():
        if risk_class not in profiles:
            raise RuntimeError(f"Commit32: missing risk class {risk_class}")
        profiles[risk_class].update(override)
    setattr(futures_universe_module, "COMMIT32_EXECUTION_TEMPO_VERSION", VERSION)
    return before


def annotate_multiasset_result(result: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    policy = dict(MULTIASSET_TEMPO.get(str(timeframe)) or MULTIASSET_TEMPO["4h"])
    result["commit32_execution_tempo"] = {"version": VERSION, **policy}
    levels = dict(result.get("levels") or {})
    cap = float(policy["entry_zone_pct_cap"])
    max_wait = int(policy["max_entry_wait_bars"])
    try:
        existing_zone = float(levels.get("entry_zone_pct") or result.get("entry_zone_pct") or cap)
        active_zone = min(existing_zone, cap) if existing_zone > 0 else cap
    except Exception:
        active_zone = cap
    try:
        existing_wait = int(levels.get("max_entry_wait_bars") or result.get("max_entry_wait_bars") or max_wait)
        active_wait = min(existing_wait, max_wait) if existing_wait > 0 else max_wait
    except Exception:
        active_wait = max_wait
    levels.update({
        "entry_zone_pct": active_zone,
        "max_entry_wait_bars": active_wait,
        "commit32_entry_zone_pct_cap": cap,
        "commit32_max_entry_wait_bars": max_wait,
    })
    result["entry_zone_pct"] = active_zone
    result["max_entry_wait_bars"] = active_wait
    result["levels"] = levels
    return result
