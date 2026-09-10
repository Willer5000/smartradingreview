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




def observation_matches_runtime_filter(
    observation: Dict[str, Any],
    config: Dict[str, Any],
    *,
    decision: str,
    timeframe: str,
    market_regime: str,
) -> bool:
    """Match one ACTIVE lab observation against its validated predicate.

    Commit 8 fails closed: a manually-created ACTIVE registry row without an
    explicit observation_filter has no runtime authority. This prevents a good
    subtype (for example FAST|ALIGNED) from accidentally authorizing the whole
    broad RSI family.
    """
    if not isinstance(observation, dict) or not isinstance(config, dict):
        return False
    rule = config.get("observation_filter") or {}
    if not isinstance(rule, dict) or not rule:
        return False

    expected_profile = str(rule.get("profile") or "").upper()
    if expected_profile and str(observation.get("profile") or "").upper() != expected_profile:
        return False

    expected_alignment = str(rule.get("alignment_with_system") or "").upper()
    if expected_alignment and str(observation.get("alignment_with_system") or "").upper() != expected_alignment:
        return False

    expected_state = str(rule.get("state") or "").upper()
    if expected_state and str(observation.get("state") or "").upper() != expected_state:
        return False

    expected_direction = str(rule.get("direction") or "").upper()
    if expected_direction and str(observation.get("direction") or "").upper() != expected_direction:
        return False

    expected_action = str(rule.get("action") or "").upper()
    if expected_action and str(decision or "").upper() != expected_action:
        return False

    expected_tf = str(rule.get("timeframe") or "").upper()
    if expected_tf and str(timeframe or "").upper() != expected_tf:
        return False

    expected_regime = str(rule.get("market_regime") or "").upper()
    if expected_regime and str(market_regime or "").upper() != expected_regime:
        return False

    return True

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

        # Commit 8: a persisted ACTIVE row is not enough by itself. Runtime
        # authority also requires the global evidence/coverage gate.
        try:
            from promotion_governance import get_promotion_governance_status
            governance = get_promotion_governance_status(db)
        except Exception:
            governance = {
                "strategy_veto_authority_allowed": False,
                "block_reasons": ["PROMOTION_GOVERNANCE_UNAVAILABLE"],
            }
        veto_authority_allowed = bool(
            governance.get("strategy_veto_authority_allowed", False)
        )

        strategies = dict(snapshot["strategies"])
        any_active = False
        for strategy_key, (_, row) in best.items():
            state = str(row.get("state") or "SHADOW").upper()
            if state not in VALID_STATES:
                state = "SHADOW"
            config = row.get("config") or {}
            if not isinstance(config, dict):
                config = {}
            has_exact_runtime_filter = bool(
                isinstance(config.get("observation_filter"), dict)
                and config.get("observation_filter")
            )
            production_authority = bool(
                state == "ACTIVE"
                and veto_authority_allowed
                and has_exact_runtime_filter
            )
            any_active = any_active or production_authority
            strategies[strategy_key] = {
                "state": state,
                "source": "SUPABASE_REGISTRY",
                "production_authority": production_authority,
                "authority_mode": "CONFLICT_VETO_ONLY" if production_authority else "NONE",
                "config": config,
                "evidence": row.get("evidence") or {},
                "updated_at": row.get("updated_at"),
            }

        snapshot = {
            "version": REGISTRY_VERSION,
            "production_authority": any_active,
            "authority_mode": "CONFLICT_VETO_ONLY",
            "promotion_governance": {
                "strategy_veto_authority_allowed": veto_authority_allowed,
                "block_reasons": list(governance.get("block_reasons") or []),
            },
            "strategies": strategies,
        }
    except Exception:
        snapshot = default_registry_snapshot()

    with _cache_lock:
        _cache[key] = (now, snapshot)
    return json.loads(json.dumps(snapshot))
