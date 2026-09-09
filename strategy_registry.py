"""Strategy Registry — Commit 3 storage + Commit 4 governed consumption.

Commit 4 can read persisted states and expose ACTIVE strategies to the execution
layer. The registry itself never creates a trade. ACTIVE experimental evidence
may only be consumed through explicit guarded hooks in futures_system.py.
"""
from __future__ import annotations

from typing import Dict, Any
import json
import threading
import time

REGISTRY_VERSION = "C4_STRATEGY_REGISTRY_V2"
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

_cache_lock = threading.Lock()
_cache = {}
_cache_ttl = 180.0


def default_registry_snapshot() -> Dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "production_authority": False,
        "strategies": {
            key: {
                "state": state,
                "source": "CODE_DEFAULT",
                "production_authority": False,
            }
            for key, state in DEFAULT_STRATEGIES.items()
        },
    }


def invalidate_registry_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _specificity(row: Dict[str, Any], symbol: str, timeframe: str, regime: str) -> int:
    score = 0
    for key, expected in (("symbol", symbol), ("timeframe", timeframe), ("market_regime", regime)):
        value = str(row.get(key) or "*")
        if value == expected:
            score += 2
        elif value == "*":
            continue
        else:
            return -999
    return score


def get_registry_snapshot(
    symbol: str = "*",
    timeframe: str = "*",
    market_regime: str = "*",
    db=None,
) -> Dict[str, Any]:
    """Returns the most specific row per strategy. Falls back to all-SHADOW."""
    symbol = str(symbol or "*")
    timeframe = str(timeframe or "*")
    market_regime = str(market_regime or "*")
    key = (symbol, timeframe, market_regime)
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < _cache_ttl:
            return json.loads(json.dumps(cached[1]))

    snapshot = default_registry_snapshot()
    if db is None:
        try:
            from supabase_client import supabase_db as db
        except Exception:
            db = None
    if db is None or not getattr(db, "enabled", False):
        return snapshot

    try:
        response = (
            db.client.table("strategy_registry")
            .select("strategy_key,symbol,timeframe,market_regime,state,config,evidence,version,updated_at")
            .in_("symbol", [symbol, "*"])
            .in_("timeframe", [timeframe, "*"])
            .in_("market_regime", [market_regime, "*"])
            .limit(200)
            .execute()
        )
        rows = response.data or []
        best = {}
        for row in rows:
            strategy_key = str(row.get("strategy_key") or "")
            if not strategy_key:
                continue
            score = _specificity(row, symbol, timeframe, market_regime)
            if score < 0:
                continue
            previous = best.get(strategy_key)
            if previous is None or score > previous[0]:
                best[strategy_key] = (score, row)

        strategies = dict(snapshot["strategies"])
        any_active = False
        for strategy_key, (_, row) in best.items():
            state = str(row.get("state") or "SHADOW").upper()
            if state not in VALID_STATES:
                state = "SHADOW"
            production_authority = state == "ACTIVE"
            any_active = any_active or production_authority
            strategies[strategy_key] = {
                "state": state,
                "source": "SUPABASE_REGISTRY",
                "production_authority": production_authority,
                "config": row.get("config") or {},
                "evidence": row.get("evidence") or {},
                "updated_at": row.get("updated_at"),
            }

        snapshot = {
            "version": REGISTRY_VERSION,
            "production_authority": any_active,
            "strategies": strategies,
        }
    except Exception:
        snapshot = default_registry_snapshot()

    with _cache_lock:
        _cache[key] = (now, snapshot)
    return json.loads(json.dumps(snapshot))
