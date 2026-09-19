"""RC9.7.11 — position-aware technical leverage policy.

Leverage is never a source of edge. Entry/SL/TP, execution Safety and the
publication geometry must already be valid. RC9.7.11 fixes a coupling bug from
RC9.7.10: leverage was selected as if 100% of the reference margin were always
used, even when the system explicitly recommended a smaller position size.

The policy now searches the highest integer leverage that remains inside the
configured *target* risk budget after applying the planned risk-allocation
fraction. Independent ceilings for Safety, ATR stress, timeframe, exchange
limits, liquidation buffer, contingency authority and the emergency cap remain
hard. Reducing position size can therefore justify more leverage without
increasing the planned monetary loss; it never permits moving SL closer,
weakening Safety or fabricating a trading edge.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


POLICY_VERSION = "RC9_7_11_POSITION_AWARE_TECHNICAL_LEVERAGE_V5"


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
    risk_allocation_fraction: float = 1.0,
    emergency_max_leverage: float = 100.0,
    high_safety_threshold: float = 90.0,
) -> Optional[Dict[str, Any]]:
    """Return the maximum integer leverage inside the technical target budget.

    ``risk_allocation_fraction`` is the fraction of the reference margin that
    the system plans to expose (for example 0.35 for a 35% suggested size).
    This lets leverage and sizing work together: a smaller position may use a
    larger leverage while the *planned* Entry→SL loss stays inside the same
    risk budget. Liquidation distance, exchange limits, Safety and timeframe
    caps are not relaxed by a smaller position.
    """
    min_required = max(1.0, _finite(minimum_required, 1.0))
    sl_pct = abs(_finite(sl_distance_pct, 0.0))
    risk_cap = max(0.0, _finite(max_by_risk, 0.0))
    atr_cap = max(0.0, _finite(max_by_atr_stress, 0.0))
    safety = min(100.0, max(0.0, _finite(safety_score, 0.0)))
    tf_cap = max(1.0, _finite(timeframe_static_max, 1.0))
    fallback_cap = max(1.0, _finite(fallback_exchange_max, tf_cap))
    emergency_cap = max(1.0, _finite(emergency_max_leverage, 100.0))
    risk_fraction = min(1.0, max(0.05, _finite(risk_allocation_fraction, 1.0)))

    verified_cap = _finite(verified_exchange_max, 0.0)
    exchange_limit_verified = verified_cap >= 1.0
    exchange_cap = verified_cap if exchange_limit_verified else fallback_cap
    exchange_cap = min(exchange_cap, emergency_cap)

    liq_cap_raw = _finite(max_by_liquidation_buffer, 0.0)
    liquidation_cap_available = liq_cap_raw >= 1.0
    liquidation_cap = liq_cap_raw if liquidation_cap_available else exchange_cap

    # Safety limits exposure but can never create edge.
    security_factor = 0.25 + 0.75 * (safety / 100.0)
    if safety >= _finite(high_safety_threshold, 90.0):
        security_factor = min(1.0, security_factor + 0.05)

    if adaptive_enabled:
        policy_cap = min(exchange_cap, liquidation_cap, emergency_cap)
        timeframe_cap_mode = "SOFT_REFERENCE"
        mode = "POSITION_AWARE_EDGE_GOVERNED"
        loss_budget = min(6.0, max(2.0, _finite(target_loss_budget_pct_margin, 5.0)))
    else:
        policy_cap = min(tf_cap, exchange_cap, liquidation_cap, emergency_cap)
        timeframe_cap_mode = "HARD_TECHNICAL_CAP"
        mode = "POSITION_AWARE_TECHNICAL_MAX"
        loss_budget = min(5.0, max(2.0, _finite(target_loss_budget_pct_margin, 5.0)))

    max_by_security = policy_cap * security_factor
    max_safe = min(risk_cap, atr_cap, max_by_security, policy_cap, liquidation_cap)

    # Target risk is measured against the planned reference-margin allocation.
    # Example: SL 1%, size 35%, leverage 10x => ~3.5% planned-margin loss.
    target_by_loss_budget = (
        loss_budget / (sl_pct * risk_fraction)
        if sl_pct > 0 and risk_fraction > 0
        else 0.0
    )
    minimum_integer = int(math.ceil(min_required))
    maximum_integer = int(math.floor(max_safe))
    target_integer = int(math.floor(target_by_loss_budget)) if target_by_loss_budget > 0 else 0

    # The target budget is a real ceiling in V5. We do not exceed it merely to
    # satisfy an economic-profit target; that setup becomes non-viable instead.
    selection_ceiling = min(maximum_integer, target_integer)
    if selection_ceiling < 1 or minimum_integer > selection_ceiling:
        return None

    selected = selection_ceiling

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
        "risk_allocation_fraction": round(risk_fraction, 4),
        "target_by_loss_budget": round(target_by_loss_budget, 4),
        "selection_ceiling": int(selection_ceiling),
        "selection_policy": mode,
    }
