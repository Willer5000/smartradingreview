"""Commit 32.1 — research-only strategy registry.

Nothing in this module may create, veto, publish, size or manage a LIVE trade.
It records hypotheses that may expand lower-timeframe opportunity coverage only
after chronological IS/OOS + walk-forward evidence.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

VERSION = "COMMIT32_1_RESEARCH_REGISTRY_V1"

_PROMOTION_PROTOCOL = {
    "authority_now": "SHADOW_ONLY",
    "live_authority": False,
    "no_signal_quota": True,
    "rules_frozen_before_test": True,
    "chronological_split_required": True,
    "walk_forward_required": True,
    "fees_slippage_required": True,
    "parameter_neighbourhood_stability_required": True,
    "regime_breakdown_required": True,
    "incremental_edge_vs_existing_family_required": True,
    "forward_shadow_required": True,
    "oos_sample_guidance": "30 minimum to inspect; 50+ preferred before route promotion",
    "promotion_metrics": [
        "positive_oos_expectancy_R",
        "profit_factor_above_1_after_costs",
        "max_drawdown_acceptable_for_risk_class",
        "no_single_asset_or_single_regime_dependence",
        "neighbour_parameter_stability",
    ],
}

_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "CRT_LIQUIDITY_RANGE_RECLAIM": {
        "state": "SHADOW_ONLY",
        "markets": ["FUTURES"],
        "timeframes_research": ["5m", "15m", "30m", "1h"],
        "role": "SETUP_ARCHETYPE_NOT_TRADER",
        "hypothesis": "HTF parent range -> liquidity raid of one side -> reclaim/close back inside -> LTF MSS/displacement/retest -> target opposing liquidity.",
        "overlap": ["SWEEP_REVERSAL", "MSS", "POI", "BREAKOUT_RETEST"],
        "incremental_question": "Does explicit parent-range state improve timing/expectancy beyond the existing Sweep/MSS/POI family?",
        "production_authority": False,
    },
    "TRIPLE_RSI_MOMENTUM_TIMING": {
        "state": "SHADOW_ONLY",
        "markets": ["FUTURES"],
        "timeframes_research": ["5m", "15m", "30m", "1h"],
        "role": "MOMENTUM_FEATURE_NOT_TRADER",
        "hypothesis": "Three RSI horizons/lengths are used only as momentum state/timing confirmation; never as standalone direction authority.",
        "variants_to_test_separately": [
            "MULTI_LENGTH_5_14_21",
            "MULTI_TIMEFRAME_EXECUTION_PARENT_CONTEXT",
        ],
        "overlap": ["RSI", "MOMENTUM", "DIVERGENCES"],
        "incremental_question": "Does the three-horizon state add OOS information after the existing momentum family, rather than duplicate it?",
        "production_authority": False,
    },
    "EFFICIENCY_RATIO_NOISE_FILTER": {
        "state": "SHADOW_ONLY",
        "markets": ["FUTURES", "MULTIASSET"],
        "timeframes_research": ["15m", "30m", "1h", "4h"],
        "role": "REGIME_FEATURE_NOT_TRADER",
        "hypothesis": "Use directional efficiency versus path noise to distinguish trend/impulse from mean-reversion regimes.",
        "overlap": ["ADX", "REGIME_CLASSIFIER"],
        "incremental_question": "Does efficiency add regime discrimination when ADX lags or remains elevated after trend exhaustion?",
        "production_authority": False,
    },
    "SESSION_OPENING_RANGE_VWAP": {
        "state": "SHADOW_ONLY",
        "markets": ["FUTURES", "MULTIASSET"],
        "timeframes_research": ["5m", "15m", "30m", "1h"],
        "role": "SESSION_EXECUTION_ARCHETYPE_NOT_TRADER",
        "hypothesis": "Session opening-range expansion/reclaim combined with VWAP/value context for execution timing.",
        "overlap": ["BREAKOUT_RETEST", "VWAP", "MARKET_HOURS"],
        "incremental_question": "Does session anchoring improve entry timing after costs without creating a time-of-day overfit?",
        "production_authority": False,
    },
}


def snapshot() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "authority": "RESEARCH_ONLY",
        "strategies": deepcopy(_STRATEGIES),
        "promotion_protocol": deepcopy(_PROMOTION_PROTOCOL),
    }


def assert_no_live_authority() -> bool:
    return all(not bool(v.get("production_authority")) and v.get("state") == "SHADOW_ONLY" for v in _STRATEGIES.values())
