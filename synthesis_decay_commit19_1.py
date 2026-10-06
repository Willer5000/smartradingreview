"""Compatibility alpha-decay for Commit-19.1 Quant Synthesis.

Important Commit-25 policy: an unvalidated synthesized fingerprint is SHADOW by
default.  This restores the missing module without granting fresh production
alpha to a lane that has no clean frozen IS/Selection/OOS evidence in the
attached bundle.  evaluate_decay() preserves the historical 8+8 contract for
QA/governance.
"""
from __future__ import annotations

import threading
from typing import Any, Dict

VERSION = "COMMIT25_SYNTHESIS_DECAY_SHADOW_DEFAULT_V1"
_LOCK = threading.Lock()
_STATE: Dict[str, Dict[str, int | bool]] = {}


def evaluate_decay(*, live_consecutive_losses: int = 0, shadow_consecutive_losses: int = 0) -> str:
    live = max(0, int(live_consecutive_losses or 0))
    shadow = max(0, int(shadow_consecutive_losses or 0))
    if live >= 8 and shadow >= 8:
        return "RETIRED_ALPHA_DECAY"
    if live >= 8:
        return "SHADOW_DECAY"
    return "LIVE_SYNTHESIS"


def authorize_validated_synthesis(synthesis_id: str, *, live_consecutive_losses: int = 0, shadow_consecutive_losses: int = 0) -> None:
    key = str(synthesis_id or "").strip()
    if not key:
        return
    with _LOCK:
        _STATE[key] = {
            "validated": True,
            "live_consecutive_losses": max(0, int(live_consecutive_losses or 0)),
            "shadow_consecutive_losses": max(0, int(shadow_consecutive_losses or 0)),
        }


def get_decay_state(*, synthesis_id: str, decay_key: str = "", research_handoff_key: str = "", **_: Any) -> Dict[str, Any]:
    key = str(synthesis_id or "").strip()
    with _LOCK:
        row = dict(_STATE.get(key) or {})
    if not row.get("validated"):
        state = "SHADOW_DECAY"
        reason = "COMMIT25_NO_CLEAN_OOS_AUTHORITY_FOR_SYNTHESIS_FINGERPRINT"
    else:
        state = evaluate_decay(
            live_consecutive_losses=int(row.get("live_consecutive_losses") or 0),
            shadow_consecutive_losses=int(row.get("shadow_consecutive_losses") or 0),
        )
        reason = "GOVERNED_VALIDATED_SYNTHESIS"
    return {
        "version": VERSION,
        "synthesis_id": key,
        "state": state,
        "reason": reason,
        "decay_key": str(decay_key or ""),
        "research_handoff_key": str(research_handoff_key or ""),
        "default_live_authority": False,
        "new_network_calls": 0,
    }
