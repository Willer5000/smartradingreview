"""RC9.7.14 FINAL — standard technical maximum leverage policy (V6).

Leverage is an instrument/exposure recommendation, not a user wallet setting.
It is therefore selected from market geometry and execution quality, while
POSITION SIZE is reduced separately to keep the standard monetary risk budget.

Hard ceilings are only those that represent a real technical/contract risk:
exchange contract max, estimated liquidation distance beyond structural SL +
ATR buffer, and an emergency absolute cap. Timeframe bands remain diagnostics,
not arbitrary hard ceilings.

No model score is treated as a literal probability of TP. ``quality_score`` is
a bounded quality proxy. Future statistically calibrated probabilities may
replace/augment this proxy only after governed evidence exists.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


POLICY_VERSION = "RC9_7_14_STANDARD_TECHNICAL_MAX_LEVERAGE_V6"


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
    quality_score: Optional[float] = None,
    calibrated_tp_probability_lower: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Select the highest technically admissible integer leverage.

    V6 deliberately decouples leverage from a user's configured margin/position
    size. Monetary risk is controlled afterwards by the recommended allocation
    fraction. This avoids the old behaviour where a wide structural SL forced
    leverage down to 2x/3x purely because of a 5% money-risk target.

    ``calibrated_tp_probability_lower`` is optional and must represent a governed
    lower-bound probability from sufficient live/OOS evidence. Uncalibrated
    confidence percentages must never be passed as if they were probabilities.
    """
    min_required = max(1.0, _finite(minimum_required, 1.0))
    sl_pct = abs(_finite(sl_distance_pct, 0.0))
    safety = min(100.0, max(0.0, _finite(safety_score, 0.0)))
    tf_reference = max(1.0, _finite(timeframe_static_max, 1.0))
    fallback_cap = max(1.0, _finite(fallback_exchange_max, tf_reference))
    emergency_cap = max(1.0, _finite(emergency_max_leverage, 100.0))
    risk_fraction = min(1.0, max(0.01, _finite(risk_allocation_fraction, 1.0)))

    verified_cap = _finite(verified_exchange_max, 0.0)
    exchange_limit_verified = verified_cap >= 1.0
    exchange_cap = verified_cap if exchange_limit_verified else fallback_cap
    exchange_cap = min(exchange_cap, emergency_cap)

    liq_cap_raw = _finite(max_by_liquidation_buffer, 0.0)
    liquidation_cap_available = liq_cap_raw >= 1.0
    liquidation_cap = liq_cap_raw if liquidation_cap_available else exchange_cap

    # These inputs are retained for compatibility/diagnostics. Under V6 they
    # must already express TECHNICAL caps, not a wallet-loss budget.
    risk_cap_raw = _finite(max_by_risk, 0.0)
    atr_cap_raw = _finite(max_by_atr_stress, 0.0)
    risk_cap = risk_cap_raw if risk_cap_raw >= 1.0 else exchange_cap
    atr_cap = atr_cap_raw if atr_cap_raw >= 1.0 else exchange_cap

    technical_hard_cap = min(
        exchange_cap,
        liquidation_cap,
        risk_cap,
        atr_cap,
        emergency_cap,
    )
    if technical_hard_cap < 1.0:
        return None

    # Quality is NOT TP probability. It controls how much of the technically
    # available leverage headroom is used. At 100/100 it approaches the hard
    # technical ceiling; mediocre quality uses materially less.
    quality = _finite(quality_score, safety)
    quality = min(100.0, max(0.0, quality))
    quality_factor = 0.35 + 0.65 * ((quality / 100.0) ** 1.20)

    calibrated_p = _finite(calibrated_tp_probability_lower, -1.0)
    probability_authority = 0.0 <= calibrated_p <= 1.0
    if probability_authority:
        # A statistically governed lower bound can replace part of the proxy.
        # 50% lower-bound still remains conservative; 100% is only a limiting
        # mathematical case, never something the system assumes from confidence.
        p_factor = 0.30 + 0.70 * calibrated_p
        quality_factor = min(1.0, max(0.25, 0.55 * quality_factor + 0.45 * p_factor))

    quality_cap = technical_hard_cap * quality_factor
    maximum_integer = int(math.floor(min(technical_hard_cap, quality_cap)))
    minimum_integer = int(math.ceil(min_required))
    if maximum_integer < 1 or minimum_integer > maximum_integer:
        return None

    selected = maximum_integer

    loss_budget = min(8.0, max(2.0, _finite(target_loss_budget_pct_margin, 5.0)))
    # Standard allocation needed to keep Entry→SL planned loss near budget.
    recommended_allocation = (
        min(1.0, loss_budget / (sl_pct * selected))
        if sl_pct > 0 and selected > 0
        else risk_fraction
    )
    recommended_allocation = max(0.01, recommended_allocation)

    return {
        "version": POLICY_VERSION,
        "leverage": int(selected),
        "minimum_required": round(min_required, 4),
        "max_safe": round(technical_hard_cap, 4),
        "max_by_security": round(quality_cap, 4),
        "max_by_liquidation_buffer": (
            round(liquidation_cap, 4) if liquidation_cap_available else None
        ),
        "liquidation_cap_available": bool(liquidation_cap_available),
        "policy_cap": round(technical_hard_cap, 4),
        "exchange_cap": round(exchange_cap, 4),
        "exchange_limit_verified": bool(exchange_limit_verified),
        "exchange_limit_source": (
            "KUCOIN_PUBLIC_CONTRACT" if exchange_limit_verified
            else "SAFE_FALLBACK_UNVERIFIED"
        ),
        "timeframe_static_max": round(tf_reference, 4),
        "timeframe_cap_mode": "REFERENCE_ONLY_NOT_HARD_CAP",
        "target_loss_budget_pct_margin": round(loss_budget, 4),
        "risk_allocation_fraction": round(risk_fraction, 4),
        "recommended_risk_allocation_fraction": round(recommended_allocation, 4),
        "target_by_loss_budget": round(recommended_allocation, 4),
        "quality_score": round(quality, 2),
        "quality_factor": round(quality_factor, 4),
        "quality_is_probability": False,
        "calibrated_probability_authority": bool(probability_authority),
        "calibrated_tp_probability_lower": (
            round(calibrated_p, 4) if probability_authority else None
        ),
        "selection_ceiling": int(maximum_integer),
        "selection_policy": "STANDARD_TECHNICAL_MAX_V6",
    }
