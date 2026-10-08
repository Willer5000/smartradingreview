"""Commit 32.2 strategy research/live governance.

A strategy can acquire LIVE authority only from a frozen evidence manifest that
contains positive chronological IS and OOS results after costs. Once LIVE, eight
consecutive resolved losses demote the strategy to SHADOW.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
from typing import Any, Dict

VERSION = "COMMIT32_2_STRATEGY_GOVERNANCE_V1"
EVIDENCE_PATH = Path(__file__).with_name("commit32_2_strategy_evidence.json")
LOSS_STREAK_DEMOTION = 8

REQUIRED_PASS = {
    "is_expectancy_r_min": 0.0,
    "is_profit_factor_min": 1.05,
    "oos_expectancy_r_min": 0.0,
    "oos_profit_factor_min": 1.05,
    "oos_min_trades": 30,
}


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def evidence_passes(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("verdict") or "").upper() != "PASS":
        return False
    isr = row.get("in_sample") or {}
    oos = row.get("out_of_sample") or {}
    checks = [
        float(isr.get("expectancy_r") or -999) > REQUIRED_PASS["is_expectancy_r_min"],
        float(isr.get("profit_factor") or 0) >= REQUIRED_PASS["is_profit_factor_min"],
        float(oos.get("expectancy_r") or -999) > REQUIRED_PASS["oos_expectancy_r_min"],
        float(oos.get("profit_factor") or 0) >= REQUIRED_PASS["oos_profit_factor_min"],
        int(oos.get("trades") or 0) >= REQUIRED_PASS["oos_min_trades"],
        bool(row.get("costs_included")),
        bool(row.get("chronological_split")),
        bool(row.get("rules_frozen_before_oos")),
    ]
    return all(checks)


def snapshot() -> Dict[str, Any]:
    data = _load()
    strategies = {}
    for key, raw in (data.get("strategies") or {}).items():
        row = deepcopy(raw or {})
        passed = evidence_passes(row)
        live_streak = int(row.get("live_consecutive_losses") or 0)
        demoted = live_streak >= LOSS_STREAK_DEMOTION
        row["evidence_pass"] = passed
        row["production_authority"] = bool(passed and not demoted)
        row["state"] = "ACTIVE" if row["production_authority"] else ("SHADOW" if demoted or not passed else "SHADOW")
        row["demotion_rule"] = f"{LOSS_STREAK_DEMOTION}_CONSECUTIVE_RESOLVED_LIVE_LOSSES"
        strategies[str(key)] = row
    return {
        "version": VERSION,
        "loss_streak_demotion": LOSS_STREAK_DEMOTION,
        "required_pass": dict(REQUIRED_PASS),
        "strategies": strategies,
    }


def live_authority(strategy_key: str) -> bool:
    return bool((snapshot().get("strategies") or {}).get(strategy_key, {}).get("production_authority"))


def apply_live_outcome(state: Dict[str, Any], *, outcome: str) -> Dict[str, Any]:
    """Pure state transition for runtime/storage integration.

    Only resolved TP/SL-like results count. A win resets the consecutive-loss
    streak. Eight consecutive losses demote to SHADOW.
    """
    out = deepcopy(state or {})
    verdict = str(outcome or "").upper()
    streak = int(out.get("live_consecutive_losses") or 0)
    if verdict in {"LOSS", "SL", "SL_HIT"}:
        streak += 1
    elif verdict in {"WIN", "TP", "TP_HIT"}:
        streak = 0
    else:
        return out
    out["live_consecutive_losses"] = streak
    if streak >= LOSS_STREAK_DEMOTION:
        out["state"] = "SHADOW"
        out["production_authority"] = False
        out["demoted_reason"] = "EIGHT_CONSECUTIVE_LIVE_LOSSES"
    return out
