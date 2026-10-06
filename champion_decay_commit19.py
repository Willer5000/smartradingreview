"""Commit-19 Champion alpha-decay contract, restored without new I/O.

The caller may inject observed loss streaks through update_runtime_decay().
No Supabase/network read is performed from the signal hot path.  In the absence
of an observed degradation state, a frozen governed Champion remains LIVE; all
normal publication/Guardian/ReviewTrader controls still apply downstream.
"""
from __future__ import annotations

import threading
from typing import Any, Dict

VERSION = "COMMIT25_CHAMPION_DECAY_RECOVERY_V1"
_LOCK = threading.Lock()
_STATE: Dict[str, Dict[str, int]] = {}


def evaluate_decay(*, live_consecutive_losses: int = 0, shadow_consecutive_losses: int = 0) -> str:
    live = max(0, int(live_consecutive_losses or 0))
    shadow = max(0, int(shadow_consecutive_losses or 0))
    if live >= 8 and shadow >= 8:
        return "RETIRED_ALPHA_DECAY"
    if live >= 8:
        return "SHADOW_DECAY"
    return "LIVE_CHAMPION"


def update_runtime_decay(champion_id: str, *, live_consecutive_losses: int = 0, shadow_consecutive_losses: int = 0) -> Dict[str, Any]:
    key = str(champion_id or "").strip()
    if not key:
        return {"state": "SHADOW_DECAY", "reason": "CHAMPION_ID_MISSING"}
    with _LOCK:
        _STATE[key] = {
            "live_consecutive_losses": max(0, int(live_consecutive_losses or 0)),
            "shadow_consecutive_losses": max(0, int(shadow_consecutive_losses or 0)),
        }
    return get_decay_state(champion_id=key)


def get_decay_state(*, champion_id: str, decay_key: str = "", research_handoff_key: str = "", **_: Any) -> Dict[str, Any]:
    key = str(champion_id or "").strip()
    with _LOCK:
        row = dict(_STATE.get(key) or {})
    live = int(row.get("live_consecutive_losses") or 0)
    shadow = int(row.get("shadow_consecutive_losses") or 0)
    state = evaluate_decay(live_consecutive_losses=live, shadow_consecutive_losses=shadow)
    return {
        "version": VERSION,
        "champion_id": key,
        "state": state,
        "live_consecutive_losses": live,
        "shadow_consecutive_losses": shadow,
        "decay_key": str(decay_key or ""),
        "research_handoff_key": str(research_handoff_key or ""),
        "policy": "8 LIVE losses -> SHADOW; 8 SHADOW losses after decay -> RETIRED",
        "new_network_calls": 0,
    }
