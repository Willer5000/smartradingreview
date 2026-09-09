"""Commit 3 — Strategy Registry contracts.

Registry states are metadata only in Commit 3. Production authority remains
unchanged. Commit 4 may consume validated transitions under governance.
"""
from __future__ import annotations
from typing import Dict, Any

REGISTRY_VERSION = "C3_STRATEGY_REGISTRY_V1"
VALID_STATES = {"SHADOW", "CHALLENGER", "CANARY", "ACTIVE", "DEGRADED", "DISABLED"}

DEFAULT_STRATEGIES = {
    "Q7_RSI_PROFILE_V1": "SHADOW",
    "Q7_ROLLING_VWAP_REVERSION_V1": "SHADOW",
    "Q7_BREAKOUT_RETEST_V1": "SHADOW",
    "TRENDLINE_SUPPORT_REACTION_V1": "SHADOW",
    "TRENDLINE_RESISTANCE_REACTION_V1": "SHADOW",
    "TRENDLINE_BREAK_RETEST_LONG_V1": "SHADOW",
    "TRENDLINE_BREAK_RETEST_SHORT_V1": "SHADOW",
    "TRENDLINE_FIB_CONFLUENCE_V1": "SHADOW",
}


def default_registry_snapshot() -> Dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "production_authority": False,
        "strategies": {k: {"state": v, "source": "CODE_DEFAULT"} for k, v in DEFAULT_STRATEGIES.items()},
    }
