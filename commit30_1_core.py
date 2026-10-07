"""Commit 30.1 / Proposal 3 integration repair.

This module is intentionally pure/no-I/O.  It documents the adjusted fast-lane
contract and exposes deterministic helpers/tests for the one-deploy patch.

30.1 does NOT create a new 1h alpha.  It repairs the hand-off from a confirmed
1h directional impulse to the already-governed 30m execution route and widens
only the F30 relative-volume floor to a pre-existing frozen stability point.
"""
from __future__ import annotations

from typing import Any, Mapping

VERSION = "COMMIT30_1_PROPOSAL3_FAST_LANE_BRIDGE_V1"

F30_FROZEN_STABILITY_CONTRACT = {
    "adx_min": 20.0,
    "volume_ratio_min": 1.0,
    "rsi_long_max": 80.0,
    "rsi_short_min": 20.0,
    "source": "BACKTEST_PARAMETER_STABILITY_17_5_10.json",
    "frozen_before_current_incident": True,
    "development": {"n": 16, "net_stress_r": 2.563, "expectancy_r": round(2.563 / 16.0, 5)},
    "holdout": {"n": 5, "net_stress_r": 5.610, "expectancy_r": round(5.610 / 5.0, 5)},
}


def route_contract_ok(*, adx: Any, volume_ratio: Any, rsi: Any, action: str) -> tuple[bool, str]:
    """Pure representation of the broadened frozen F30 pre-entry contract."""
    try:
        adx_v = float(adx)
        vol_v = float(volume_ratio)
        rsi_v = float(rsi)
    except Exception:
        return False, "F30_CONTRACT_INPUT_MISSING"
    if adx_v < F30_FROZEN_STABILITY_CONTRACT["adx_min"]:
        return False, "F30_ADX_BELOW_FROZEN_STABILITY_CONTRACT"
    if vol_v < F30_FROZEN_STABILITY_CONTRACT["volume_ratio_min"]:
        return False, "F30_VOLUME_BELOW_FROZEN_STABILITY_CONTRACT"
    action_u = str(action or "").upper()
    if action_u == "LONG" and rsi_v > F30_FROZEN_STABILITY_CONTRACT["rsi_long_max"]:
        return False, "F30_RSI_LONG_CHASE"
    if action_u == "SHORT" and rsi_v < F30_FROZEN_STABILITY_CONTRACT["rsi_short_min"]:
        return False, "F30_RSI_SHORT_CHASE"
    if action_u not in {"LONG", "SHORT"}:
        return False, "F30_DIRECTION_UNDEFINED"
    return True, "F30_PREENTRY_FROZEN_STABILITY_CONTRACT_OK"


def audit() -> Mapping[str, Any]:
    return {
        "version": VERSION,
        "proposal3_directional_impulse_preserved": True,
        "impulse_is_context_only": True,
        "same_symbol_30m_recheck_same_closed_candle_once": True,
        "impulse_queue_persists_until_success_ack": True,
        "ui_cooldown_may_starve_impulse_lane": False,
        "memory_backoff_may_still_defer_impulse_lane": True,
        "f30_contract": dict(F30_FROZEN_STABILITY_CONTRACT),
        "adx_lowered": False,
        "rr_lowered": False,
        "safety_lowered": False,
        "new_live_1h_route": False,
        "new_multiasset_live_route": False,
        "new_io": 0,
        "new_db_queries": 0,
        "new_llm_calls": 0,
        "new_threads": 0,
    }
