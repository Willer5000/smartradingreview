"""Commit 18 — explicit Reason-First responsibility contract.

Pure metadata/governance helper. It does not fetch market data, call an LLM,
change direction, Entry/SL/TP, Safety, publication, Guardian or leverage.
Its purpose is to make the production responsibility graph auditable and to
prevent correlated evidence or legacy trader-vote semantics from regaining
production authority.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

VERSION = "COMMIT18_REASON_FIRST_V1"

EVIDENCE_FAMILIES = {
    "trend": ("EMA", "SUPERTREND", "ADX_DMI"),
    "momentum": ("RSI", "MACD", "STOCHASTIC", "CCI", "WILLIAMS_R", "RSI_MAVERICK"),
    "volatility": ("ATR", "BOLLINGER", "KELTNER", "SQUEEZE"),
    "flow": ("VOLUME", "RELATIVE_VOLUME", "OBV", "MFI", "CVD", "ORDERFLOW"),
    "value": ("VWAP", "VOLUME_PROFILE", "POC", "VAH_VAL", "HVN_LVN"),
    "structure": ("SWINGS", "SUPPORT_RESISTANCE", "BOS_MSS", "TRENDLINES"),
    "liquidity": ("SWEEP", "STOP_HUNT", "ORDER_BLOCK", "FVG", "LIQUIDITY_POOLS"),
    "derivatives": ("FUNDING", "OPEN_INTEREST", "BASIS", "LIQUIDATIONS", "OPTIONS_GREEKS"),
    "macro_sentiment": ("MACRO", "NEWS", "CALENDAR", "SENTIMENT", "SESSION", "CORRELATION"),
}

RESPONSIBILITIES = {
    "context": {
        "owners": ("MACRO", "MULTIFRAME", "SENTIMENT", "SESSION", "CORRELATION_INTERMARKET"),
        "authority": "CLASSIFY_CONTEXT_ONLY",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "thesis": {
        "owners": ("OPERATIONAL_INTELLIGENCE",),
        "authority": "THESIS_OWNER",
        "can_create_direction": True,
        "can_move_execution": False,
    },
    "strategy": {
        "owners": ("STRATEGY_BANK", "RESEARCH"),
        "authority": "PLAYBOOK_ROUTING_WITH_STATISTICAL_EVIDENCE",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "entry": {
        "owners": ("SMART_MONEY", "PULLBACK", "STRUCTURE", "VALUE", "ORDERFLOW_WHEN_REAL"),
        "authority": "ENTRY_LOCATION_ONLY",
        "can_create_direction": False,
        "can_move_execution": True,
    },
    "stop_loss": {
        "owners": ("INVALIDATION", "STRUCTURE", "LIQUIDITY", "VOLATILITY", "MAE_EVIDENCE"),
        "authority": "INVALIDATION_ONLY",
        "can_create_direction": False,
        "can_move_execution": True,
    },
    "take_profit": {
        "owners": ("OPPOSITE_LIQUIDITY", "VALUE", "STRUCTURE", "VOLATILITY", "MFE_EVIDENCE"),
        "authority": "TARGET_LOCATION_ONLY",
        "can_create_direction": False,
        "can_move_execution": True,
    },
    "statistical_authority": {
        "owners": ("REVIEWTRADER", "RESEARCH", "ALPHA_DECAY"),
        "authority": "EDGE_AUTHORITY",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "safety": {
        "owners": ("SAFETY_ENGINE", "RISK_CHALLENGE"),
        "authority": "HARD_RISK_VETO_ONLY",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "guardian": {
        "owners": ("GUARDIAN",),
        "authority": "POST_SAVE_POST_ENTRY_PROTECTION_ONLY",
        "can_create_direction": False,
        "can_move_execution": True,
    },
    "ai_scientist": {
        "owners": ("LEARNING_SCIENTIST",),
        "authority": "SHADOW_HYPOTHESIS_GENERATOR_ONLY",
        "can_create_direction": False,
        "can_move_execution": False,
        "requires_research_validation": True,
    },
    "ai_advisor": {
        "owners": ("CONSEJO_IA",),
        "authority": "EXPLANATION_ONLY",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "ai_assistant": {
        "owners": ("ASISTENTE_IA",),
        "authority": "USER_INTERFACE_ONLY",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "options": {
        "owners": ("DELTA_GAMMA_THETA", "BLACK_SCHOLES", "GEX"),
        "authority": "OBSERVED_CHAIN_CONTEXT_OR_THEORETICAL_UI_ONLY",
        "can_create_direction": False,
        "can_move_execution": False,
    },
    "leverage": {
        "owners": ("EXISTING_LEVERAGE_ENGINE",),
        "authority": "FROZEN_EXISTING_POLICY_AFTER_FINAL_GEOMETRY",
        "can_create_direction": False,
        "can_move_execution": False,
        "policy_modified_by_commit18": False,
    },
}

MARKET_POLICIES = {
    "spot": {
        "objective": "COMPOUND_USDT_BTC_PAXG",
        "entry_precision": "FLEXIBLE_NEAR_REACTION_VALUE",
        "risk_semantics": "PROTECT_OR_ROTATE",
        "execution_priority": "VALUE_AND_HIGHER_TIMEFRAME_CONTEXT",
    },
    "futures": {
        "objective": "FAST_RISK_ADJUSTED_TRADES",
        "entry_precision": "PRECISE_REACTION_ZONE",
        "risk_semantics": "SL_BEYOND_TRUE_INVALIDATION",
        "execution_priority": "ENTRY_THEN_INVALIDATION_THEN_REACHABLE_TARGET",
    },
    "multiasset": {
        "objective": "DIVERSIFY_INDEPENDENT_OPPORTUNITIES",
        "entry_precision": "PRECISE_REACTION_ZONE",
        "risk_semantics": "ASSET_CLASS_SESSION_AND_VOLATILITY_AWARE",
        "execution_priority": "MARKET_SPECIFIC_ENTRY_INVALIDATION_TARGET",
    },
}

# Historical Research routes that passed positive discovery/train, selection,
# untouched OOS and walk-forward as of the Commit-18 pre-audit.  These are
# routing priors only; they are deliberately NOT publication authority until
# real production geometry parity is demonstrated.
POSITIVE_RESEARCH_ROUTES = {
    ("FUTURES", "ETH-USDT", "2H", "LONG", "TREND_UP"): "RSI_TREND",
    ("FUTURES", "SOL-USDT", "2H", "SHORT", "TREND_DOWN"): "SUPERTREND_PULLBACK",
    ("FUTURES", "XRP-USDT", "2H", "SHORT", "TREND_DOWN"): "TREND_CONTINUATION",
    ("SPOT", "PAXG-USDT", "12H", "COMPRA_SPOT", "TREND_UP"): "MULTI_RSI_TREND",
}


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _market(result: Mapping[str, Any]) -> str:
    if bool(result.get("is_multiasset")) or _u(result.get("market")) in {"MULTIASSET", "MULTI-ASSET", "MULTI_ASSET"}:
        return "MULTIASSET"
    raw = _u(result.get("market") or result.get("system_type"))
    if raw == "SPOT":
        return "SPOT"
    return "FUTURES"


def build_reason_first_contract(result: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    row = dict(result or {})
    market = _market(row)
    vol = row.get("volatility") or {}
    op = row.get("operational_intelligence") or {}
    thesis = op.get("thesis") or {}
    strategy = row.get("strategy_context") or row.get("strategy") or {}
    return {
        "version": VERSION,
        "market": market,
        "market_policy": dict(MARKET_POLICIES[market.lower()]),
        "regime": str(thesis.get("regime") or strategy.get("regime") or row.get("regime") or "UNKNOWN"),
        "volatility_regime": str(strategy.get("volatility_regime") or vol.get("regime") or vol.get("state") or "UNKNOWN"),
        "responsibilities": {k: dict(v) for k, v in RESPONSIBILITIES.items()},
        "evidence_family_rule": "ONE_CORRELATED_FAMILY_ONE_BOUNDED_EVIDENCE_CONTRIBUTION",
        "evidence_families": {k: list(v) for k, v in EVIDENCE_FAMILIES.items()},
        "legacy_trader_vote_authority": False,
        "majority_vote_gate": False,
        "leverage_policy": "UNCHANGED_COMMIT18",
        "production_change": False,
    }


def research_route_state(*, market: Any, symbol: Any, timeframe: Any,
                         action: Any, regime: Any) -> Dict[str, Any]:
    key = (_u(market), _u(symbol), _u(timeframe), _u(action), _u(regime))
    family = POSITIVE_RESEARCH_ROUTES.get(key)
    if not family:
        return {
            "state": "NO_EXACT_POSITIVE_ROUTE_FROM_PREAUDIT",
            "family": None,
            "production_authority": False,
        }
    return {
        "state": "POSITIVE_IS_SELECTION_OOS_WF_ROUTE",
        "family": family,
        "production_authority": False,
        "reason": "Production Entry/SL/TP parity is still required before official statistical authority.",
    }


def audit_contract() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "roles": len(RESPONSIBILITIES),
        "evidence_families": len(EVIDENCE_FAMILIES),
        "majority_vote_gate": False,
        "leverage_modified": bool(RESPONSIBILITIES["leverage"]["policy_modified_by_commit18"]),
        "ai_scientist_production_authority": False,
        "macro_creates_direction": False,
        "options_create_direction": False,
    }
