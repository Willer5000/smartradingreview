"""RC9.7.10 — pure technical risk-budget leverage policy.

The policy is intentionally arithmetic-only so it can be tested without Flask,
Supabase or exchange connectivity.  Leverage is an exposure decision, never a
source of edge: Entry/SL/TP and Safety must already be valid before this module
is called.

RC9.7.10 changes the static fallback from "minimum viable leverage" to a
bounded technical risk budget.  A tighter structural SL may therefore justify
more leverage, but only below independent ceilings for Safety, ATR stress,
timeframe, exchange limits and a conservative liquidation-buffer estimate.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


POLICY_VERSION = "RC9_7_10_TECHNICAL_LEVERAGE_V4"


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
    max_by_liquidation_buffer: Optional[float] = None,
    adaptive_enabled: bool = False,
    target_loss_budget_pct_margin: float = 5.0,
    emergency_max_leverage: float = 100.0,
    high_safety_threshold: float = 90.0,
) -> Optional[Dict[str, Any]]:
    """Return the highest *targeted* leverage justified by the risk budget.

    The selected integer never exceeds any independent hard ceiling.  The loss
    budget is a target, not permission to exceed ``max_by_risk``.  In the normal
    (non-adaptive) path, the timeframe cap remains hard.  Governed adaptive mode
    may treat the timeframe cap as a soft reference, but exchange/liquidation,
    ATR, Safety and emergency ceilings remain hard.
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

    liq_cap_raw = _finite(max_by_liquidation_buffer, 0.0)
    liquidation_cap_available = liq_cap_raw >= 1.0
    liquidation_cap = liq_cap_raw if liquidation_cap_available else exchange_cap

    # Safety cannot create edge.  It only limits how close the policy may get
    # to the otherwise valid ceilings.
    security_factor = 0.25 + 0.75 * (safety / 100.0)
    if safety >= _finite(high_safety_threshold, 90.0):
        security_factor = min(1.0, security_factor + 0.05)

    if adaptive_enabled:
        # Only an already-governed profile may soften the timeframe ceiling.
        policy_cap = min(exchange_cap, liquidation_cap, emergency_cap)
        timeframe_cap_mode = "SOFT_REFERENCE"
        mode = "RISK_BUDGET_EDGE_GOVERNED"
        loss_budget = min(6.0, max(2.0, _finite(target_loss_budget_pct_margin, 5.0)))
    else:
        # Normal production fallback: timeframe still protects the user, but
        # we no longer stop at the minimum economically viable integer.
        policy_cap = min(tf_cap, exchange_cap, liquidation_cap, emergency_cap)
        timeframe_cap_mode = "HARD_TECHNICAL_CAP"
        mode = "TECHNICAL_RISK_BUDGET"
        loss_budget = min(5.0, max(2.0, _finite(target_loss_budget_pct_margin, 5.0)))

    max_by_security = policy_cap * security_factor
    max_safe = min(risk_cap, atr_cap, max_by_security, policy_cap, liquidation_cap)

    target_by_loss_budget = (loss_budget / sl_pct) if sl_pct > 0 else 0.0
    minimum_integer = int(math.ceil(min_required))
    maximum_integer = int(math.floor(max_safe))
    target_integer = int(math.floor(target_by_loss_budget)) if target_by_loss_budget > 0 else 0

    if maximum_integer < 1 or minimum_integer > maximum_integer:
        return None

    # The risk-budget target can raise leverage above the old minimum viable
    # value, but can never exceed maximum_integer.  If the technical geometry
    # only supports the minimum, the policy stays at the minimum.
    selected = max(minimum_integer, target_integer)
    selected = min(selected, maximum_integer)
    selected = max(minimum_integer, selected)

    return {
        "version": POLICY_VERSION,
        "leverage": int(selected),
        "minimum_required": round(min_required, 4),
        "max_safe": round(max_safe, 4),
        "max_by_security": round(max_by_security, 4),
        "max_by_liquidation_buffer": (
            round(liquidation_cap, 4) if liquidation_cap_available else None
        ),
        "liquidation_cap_available": bool(liquidation_cap_available),
        "policy_cap": round(policy_cap, 4),
        "exchange_cap": round(exchange_cap, 4),
        "exchange_limit_verified": bool(exchange_limit_verified),
        "exchange_limit_source": (
            "KUCOIN_PUBLIC_CONTRACT" if exchange_limit_verified
            else "SAFE_FALLBACK_UNVERIFIED"
        ),
        "timeframe_static_max": round(tf_cap, 4),
        "timeframe_cap_mode": timeframe_cap_mode,
        "target_loss_budget_pct_margin": round(loss_budget, 4),
        "target_by_loss_budget": round(target_by_loss_budget, 4),
        "selection_policy": mode,
    }
