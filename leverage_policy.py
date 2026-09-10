"""Commit 9 — pure risk-budget leverage policy.

This module contains only arithmetic.  It deliberately has no Flask, database,
exchange or project imports so the leverage contract can be unit-tested without
booting the application.

The policy does NOT turn Safety into a probability and does NOT force leverage.
When adaptive authority is closed it reproduces the old minimum-safe-viable
selection under the static timeframe ceiling.  When governed risk scaling is
open, timeframe becomes a soft reference and leverage is derived primarily from
Entry→SL geometry, ATR stress, Safety and a bounded loss budget.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


POLICY_VERSION = "C9_RISK_BUDGET_LEVERAGE_V3"


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else float(default)
    except (TypeError, ValueError):
        return float(default)


def select_risk_budget_leverage(
    *,
    minimum_required: float,
    sl_distance_pct: float,
    max_by_risk: float,
    max_by_atr_stress: float,
    safety_score: float,
    timeframe_static_max: float,
    fallback_exchange_max: float,
    verified_exchange_max: Optional[float] = None,
    adaptive_enabled: bool = False,
    target_loss_budget_pct_margin: float = 5.0,
    emergency_max_leverage: float = 100.0,
    high_safety_threshold: float = 90.0,
) -> Optional[Dict[str, Any]]:
    """Select leverage without exceeding independent safety ceilings.

    `target_loss_budget_pct_margin` is a target, not a permission to exceed the
    hard `max_by_risk` ceiling.  A tighter structural SL can therefore justify a
    larger notional/leverage while the planned loss budget stays bounded.
    """
    min_required = max(1.0, _finite(minimum_required, 1.0))
    sl_pct = abs(_finite(sl_distance_pct, 0.0))
    risk_cap = max(0.0, _finite(max_by_risk, 0.0))
    atr_cap = max(0.0, _finite(max_by_atr_stress, 0.0))
    safety = min(100.0, max(0.0, _finite(safety_score, 0.0)))
    tf_cap = max(1.0, _finite(timeframe_static_max, 1.0))
    fallback_cap = max(1.0, _finite(fallback_exchange_max, tf_cap))
    emergency_cap = max(1.0, _finite(emergency_max_leverage, 100.0))

    verified_cap = _finite(verified_exchange_max, 0.0)
    exchange_limit_verified = verified_cap >= 1.0
    exchange_cap = verified_cap if exchange_limit_verified else fallback_cap
    exchange_cap = min(exchange_cap, emergency_cap)

    security_factor = 0.25 + 0.75 * (safety / 100.0)
    if safety >= _finite(high_safety_threshold, 90.0):
        security_factor = min(1.0, security_factor + 0.05)

    if adaptive_enabled:
        # Commit 9: timeframe is diagnostic/soft once the global net-edge gate
        # explicitly authorizes risk-budget scaling.
        policy_cap = exchange_cap
        max_by_security = policy_cap * security_factor
        max_safe = min(risk_cap, atr_cap, max_by_security, policy_cap)

        loss_budget = min(7.0, max(2.0, _finite(target_loss_budget_pct_margin, 5.0)))
        target_by_loss_budget = (loss_budget / sl_pct) if sl_pct > 0 else 0.0

        minimum_integer = int(math.ceil(min_required))
        maximum_integer = int(math.floor(max_safe))
        target_integer = int(math.floor(target_by_loss_budget)) if target_by_loss_budget > 0 else 0
        if maximum_integer < 1 or minimum_integer > maximum_integer:
            return None

        # Never force a larger leverage merely because adaptive mode is active.
        # It grows only when the risk-budget geometry itself supports it.
        selected = max(minimum_integer, target_integer)
        selected = min(selected, maximum_integer)
        selected = max(minimum_integer, selected)
        mode = "RISK_BUDGET_EDGE_GOVERNED"
        timeframe_cap_mode = "SOFT_REFERENCE"
    else:
        policy_cap = min(tf_cap, fallback_cap, emergency_cap)
        max_by_security = policy_cap * security_factor
        max_safe = min(risk_cap, atr_cap, max_by_security, policy_cap)
        minimum_integer = int(math.ceil(min_required))
        maximum_integer = int(math.floor(max_safe))
        if maximum_integer < 1 or minimum_integer > maximum_integer:
            return None
        selected = minimum_integer
        loss_budget = None
        target_by_loss_budget = None
        mode = "MINIMUM_SAFE_VIABLE"
        timeframe_cap_mode = "HARD_STATIC_FALLBACK"

    return {
        "version": POLICY_VERSION,
        "leverage": int(selected),
        "minimum_required": round(min_required, 4),
        "max_safe": round(max_safe, 4),
        "max_by_security": round(max_by_security, 4),
        "policy_cap": round(policy_cap, 4),
        "exchange_cap": round(exchange_cap, 4),
        "exchange_limit_verified": bool(exchange_limit_verified),
        "exchange_limit_source": (
            "VERIFIED_RUNTIME_LIMIT" if exchange_limit_verified
            else "SAFE_FALLBACK_UNVERIFIED"
        ),
        "timeframe_static_max": round(tf_cap, 4),
        "timeframe_cap_mode": timeframe_cap_mode,
        "target_loss_budget_pct_margin": (
            round(loss_budget, 4) if loss_budget is not None else None
        ),
        "target_by_loss_budget": (
            round(target_by_loss_budget, 4)
            if target_by_loss_budget is not None else None
        ),
        "selection_policy": mode,
    }
