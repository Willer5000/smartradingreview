"""RC9.8 — internal execution geometry policy.

This module is intentionally backend-only.  It does not create a LONG/SHORT
thesis and it does not expose internal specialist names to the UI.  Its job is
narrower: once direction already exists, tailor Entry/SL/TP geometry by market,
instrument, timeframe, market regime and volatility.

Design principles
-----------------
* Directional committee decides *whether* an opportunity exists.
* Geometry policy decides *how* to execute it.
* A distant but technically probable pullback may beat a near-market entry.
* A near-market entry may win when price is already reacting from the correct
  structural side.
* ATR normalizes distance/noise; it is never the primary source of Entry.
* ReviewTrader evidence is bounded and sample-aware; N<8 has no authority.
* Order-flow/order-book remains shadow confluence until calibrated OOS.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping

VERSION = "COMMIT13_EXECUTION_GEOMETRY_V2"

FUTURES_GROUPS = {
    "CORE1": {"BTC-USDT", "ETH-USDT", "SOL-USDT"},
    "CORE2": {"XRP-USDT", "ADA-USDT"},
    "MEDIUM": {"BNB-USDT", "LINK-USDT", "AVAX-USDT", "NEAR-USDT", "DOT-USDT"},
    "HIGH": {"SUI-USDT", "HYPE-USDT", "APT-USDT", "INJ-USDT", "SEI-USDT"},
}

# Commit 13 — Multi-Activo shares the deterministic execution engine but keeps
# its own instrument families.  These sets are intentionally local constants:
# importing multiasset_system here would create a circular dependency.
MULTIASSET_BUCKETS = {
    "MULTI_US_INDEX": {"SPY-USDT", "QQQ-USDT"},
    "MULTI_ENERGY": {"CL-USDT", "NATGAS-USDT"},
    "MULTI_INDUSTRIAL_METAL": {"COPPER-USDT"},
    "MULTI_PRECIOUS_METAL": {"XAG-USDT"},
    "MULTI_CHINA_INDEX": {"KSTR-USDT"},
}

SPOT_CLASSES = {
    "BTC-USDT": "SPOT_BTC_USDT",
    "PAXG-USDT": "SPOT_PAXG_USDT",
    "PAXG-BTC": "SPOT_PAXG_BTC_ROTATION",
}

# Typical ATR% anchors are only normalization references. They never reject a
# trade by themselves.  The runtime's own volatility_ratio/percentile wins when
# available.
_EXPECTED_ATR_PCT = {
    "spot": {
        "4h": 1.4, "12h": 2.0, "1D": 2.8, "1W": 5.0,
        "30m": 0.65, "1h": 0.85, "2h": 1.05,
    },
    "futures": {
        "30m": 0.60, "1h": 0.80, "2h": 1.05, "4h": 1.40,
        "12h": 2.10, "1D": 3.00,
    },
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float(default)
    except (TypeError, ValueError):
        return float(default)


def canonical_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def canonical_timeframe(value: Any) -> str:
    raw = str(value or "").strip()
    upper = raw.upper()
    return {
        "30M": "30m", "1H": "1h", "2H": "2h", "4H": "4h",
        "12H": "12h", "1D": "1D", "1W": "1W", "5M": "5m",
        "15M": "15m",
    }.get(upper, raw)


def instrument_bucket(market_type: Any, symbol: Any) -> str:
    market = "futures" if str(market_type or "").lower() == "futures" else "spot"
    sym = canonical_symbol(symbol)
    if market == "spot":
        return SPOT_CLASSES.get(sym, "SPOT_OTHER")
    # Multi-Activo subclasses FuturesAnalysis, therefore market_type remains
    # "futures" inside the common geometry engine.  Symbol membership is the
    # deterministic discriminator and prevents crypto priors leaking into
    # energy/index/metals/China contracts.
    for bucket, members in MULTIASSET_BUCKETS.items():
        if sym in members:
            return bucket
    for bucket, members in FUTURES_GROUPS.items():
        if sym in members:
            return bucket
    return "FUTURES_OTHER"


def _volatility_bucket(volatility: Mapping[str, Any] | None, market: str, timeframe: str) -> Dict[str, Any]:
    volatility = volatility or {}
    percentile = _f(volatility.get("volatility_percentile"), 50.0)
    ratio = _f(volatility.get("volatility_ratio"), 0.0)
    atr_pct = max(0.0, _f(volatility.get("atr_pct"), 0.0))
    expected = _EXPECTED_ATR_PCT.get(market, {}).get(timeframe, 1.5)
    if ratio <= 0:
        ratio = atr_pct / expected if expected > 0 and atr_pct > 0 else 1.0

    if percentile >= 96 or ratio >= 2.15:
        bucket = "EXTREME"
    elif percentile >= 82 or ratio >= 1.45:
        bucket = "HIGH"
    elif percentile <= 22 or ratio <= 0.68:
        bucket = "LOW"
    else:
        bucket = "NORMAL"
    return {
        "bucket": bucket,
        "ratio": round(max(0.0, ratio), 4),
        "percentile": round(percentile, 2),
        "atr_pct": round(atr_pct, 4),
    }


def _learning_hint(market: str, symbol: str, timeframe: str, direction: str) -> Dict[str, Any]:
    """Read bounded execution evidence without creating a hard veto.

    Current all-user execution learning is Futures-only.  Spot deliberately
    stays OBSERVE_ONLY until an equivalent canonical execution dataset exists.
    """
    base = {
        "authority": "OBSERVE_ONLY",
        "sample_size": 0,
        "expectancy_r": 0.0,
        "fast_sl_rate": 0.0,
        "weak_progress_sl_rate": 0.0,
        "avg_mfe_r": None,
        "avg_mae_r": None,
        "near_bias": 0.0,
        "deep_bias": 0.0,
        "sl_buffer_bias": 0.0,
        "tp_speed_bias": 0.0,
        "weight": 0.0,
    }
    if market != "futures":
        return base
    try:
        from user_execution_learning import get_global_execution_profile
        action = "LONG" if str(direction or "").lower() == "long" else "SHORT"
        profile = get_global_execution_profile(symbol, timeframe, action) or {}
    except Exception:
        return base

    n = int(profile.get("sample_size") or 0)
    authority = str(profile.get("authority") or "OBSERVE_ONLY")
    exp_r = _f(profile.get("expectancy_r"), 0.0)
    fast_sl = max(0.0, min(1.0, _f(profile.get("fast_sl_rate"), 0.0)))
    weak_progress = max(0.0, min(1.0, _f(profile.get("weak_progress_sl_rate"), 0.0)))

    # N<8 is recorded but never changes geometry.  Afterwards influence grows
    # slowly and is capped so live learning cannot overpower structure.
    weight = 0.0
    near_bias = deep_bias = sl_buffer_bias = tp_speed_bias = 0.0
    if authority == "BOUNDED_CONTINUITY" and n >= 8:
        weight = min(0.16, 0.04 + min(32, n - 8) * 0.00375)
        adverse = max(fast_sl, weak_progress)
        if exp_r < 0 and adverse >= 0.30:
            deep_bias = min(1.0, 0.35 + adverse)
            sl_buffer_bias = min(1.0, adverse)
            tp_speed_bias = min(1.0, max(0.0, -exp_r) + adverse * 0.35)
        elif exp_r >= 0.15 and fast_sl < 0.20:
            near_bias = min(0.75, 0.25 + min(0.5, exp_r))

    out = dict(base)
    out.update({
        "authority": authority,
        "sample_size": n,
        "expectancy_r": round(exp_r, 4),
        "fast_sl_rate": round(fast_sl, 4),
        "weak_progress_sl_rate": round(weak_progress, 4),
        "avg_mfe_r": profile.get("avg_mfe_r"),
        "avg_mae_r": profile.get("avg_mae_r"),
        "near_bias": round(near_bias, 4),
        "deep_bias": round(deep_bias, 4),
        "sl_buffer_bias": round(sl_buffer_bias, 4),
        "tp_speed_bias": round(tp_speed_bias, 4),
        "weight": round(weight, 4),
    })
    return out


def build_profile(
    *,
    market_type: Any,
    symbol: Any,
    timeframe: Any,
    direction: Any,
    setup_family: Any = None,
    market_regime: Any = None,
    trend: Mapping[str, Any] | None = None,
    momentum: Mapping[str, Any] | None = None,
    volatility: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    market = "futures" if str(market_type or "").lower() == "futures" else "spot"
    sym = canonical_symbol(symbol)
    tf = canonical_timeframe(timeframe)
    bucket = instrument_bucket(market, sym)
    setup = str(setup_family or "UNSPECIFIED").strip().upper()
    regime = str(market_regime or "RANGING").strip().upper()
    vol = _volatility_bucket(volatility, market, tf)
    learning = _learning_hint(market, sym, tf, str(direction or "").lower())

    # Families are internal weights, not votes exposed to users.  Correlated
    # tools (OB/FVG/SMC) deliberately share a family so they cannot manufacture
    # fake consensus by counting the same information several times.
    weights = {
        "structure_liquidity": 1.00,
        "smc_poi": 1.00,
        "pullback_retest": 1.00,
        "trend_ema": 0.70,
        "volume_profile": 0.82,
        "fibonacci": 0.58,
        "orderflow_shadow": 0.15,
        "volatility_risk": 1.00,
        "review_learning": learning["weight"],
    }

    # Base execution-horizon policy.  Faster Futures means closer *natural TP*,
    # not a mechanically tighter SL or lower Safety.
    if market == "spot":
        mission = "ACCUMULATION_ROTATION"
        speed = "POSITIONAL"
        preferred_rr = (1.8, 4.5)
        # R/R remains an economic filter, not a target generator.  Commit 13
        # allows a nearer structural objective to compete when it is genuinely
        # reachable; the final economics/publication layers still decide if the
        # trade is worth taking.
        technical_rr_floor = 1.40
        technical_rr_ceiling = 4.50
        near_max_atr = 0.55
        deep_min_atr = 0.90
        hard_max_reach_atr = {"4h": 3.4, "12h": 3.8, "1D": 4.2, "1W": 4.8}.get(tf, 3.2)
        target_atr_soft_max = {"4h": 5.5, "12h": 6.5, "1D": 7.5, "1W": 9.0}.get(tf, 6.0)
        weights["structure_liquidity"] += 0.08
        weights["volume_profile"] += 0.08
        if bucket == "SPOT_BTC_USDT":
            technical_rr_floor = 1.50
            weights["pullback_retest"] += 0.10
            weights["trend_ema"] += 0.08
        elif bucket == "SPOT_PAXG_USDT":
            technical_rr_floor = 1.40
            weights["structure_liquidity"] += 0.10
            weights["fibonacci"] += 0.05
            hard_max_reach_atr += 0.25
        elif bucket == "SPOT_PAXG_BTC_ROTATION":
            technical_rr_floor = 1.30
            weights["volume_profile"] += 0.12
            weights["structure_liquidity"] += 0.12
            weights["fibonacci"] += 0.08
            deep_min_atr = 0.75
    else:
        mission = "FAST_TACTICAL_EXECUTION"
        # Commit 13 — market-specific execution horizons.  The floor is only
        # the minimum R/R at which an already-detected structural target may
        # compete; it never fabricates a target and it never lowers Safety.
        technical_rr_ceiling = 4.50
        if bucket == "MULTI_US_INDEX":
            speed = "FAST"
            preferred_rr = (1.7, 2.8)
            technical_rr_floor = 1.45
            near_max_atr = 0.55
            deep_min_atr = 0.82
            hard_max_reach_atr = {"1h": 2.4, "4h": 2.9, "1D": 3.3}.get(tf, 2.7)
            target_atr_soft_max = 4.1
            weights["volume_profile"] += 0.12
            weights["trend_ema"] += 0.10
            weights["pullback_retest"] += 0.10
        elif bucket == "MULTI_ENERGY":
            speed = "FASTER"
            preferred_rr = (1.6, 2.7)
            technical_rr_floor = 1.40
            near_max_atr = 0.58
            deep_min_atr = 0.86
            hard_max_reach_atr = {"1h": 2.6, "4h": 3.1, "1D": 3.5}.get(tf, 2.9)
            target_atr_soft_max = 4.2
            weights["structure_liquidity"] += 0.12
            weights["volatility_risk"] += 0.12
            weights["pullback_retest"] += 0.08
        elif bucket == "MULTI_INDUSTRIAL_METAL":
            speed = "FAST"
            preferred_rr = (1.7, 2.9)
            technical_rr_floor = 1.45
            near_max_atr = 0.56
            deep_min_atr = 0.85
            hard_max_reach_atr = {"1h": 2.5, "4h": 3.0, "1D": 3.5}.get(tf, 2.9)
            target_atr_soft_max = 4.4
            weights["structure_liquidity"] += 0.10
            weights["volume_profile"] += 0.10
        elif bucket == "MULTI_PRECIOUS_METAL":
            speed = "FAST"
            preferred_rr = (1.7, 3.0)
            technical_rr_floor = 1.45
            near_max_atr = 0.58
            deep_min_atr = 0.86
            hard_max_reach_atr = {"1h": 2.6, "4h": 3.1, "1D": 3.6}.get(tf, 3.0)
            target_atr_soft_max = 4.6
            weights["structure_liquidity"] += 0.10
            weights["volume_profile"] += 0.10
            weights["fibonacci"] += 0.05
        elif bucket == "MULTI_CHINA_INDEX":
            speed = "FASTER"
            preferred_rr = (1.6, 2.7)
            technical_rr_floor = 1.40
            near_max_atr = 0.54
            deep_min_atr = 0.82
            hard_max_reach_atr = {"1h": 2.3, "4h": 2.8, "1D": 3.2}.get(tf, 2.6)
            target_atr_soft_max = 3.9
            weights["structure_liquidity"] += 0.12
            weights["pullback_retest"] += 0.10
            weights["volatility_risk"] += 0.08
        elif bucket == "CORE1":
            speed = "FAST"
            preferred_rr = (2.0, 3.4)
            technical_rr_floor = 1.55
            near_max_atr = 0.60
            deep_min_atr = 0.90
            hard_max_reach_atr = {"30m": 2.4, "1h": 2.7, "2h": 2.9, "4h": 3.2, "12h": 3.4, "1D": 3.6}.get(tf, 3.0)
            target_atr_soft_max = 5.2
            weights["trend_ema"] += 0.04
            weights["volume_profile"] += 0.04
        elif bucket == "CORE2":
            # Same FAST mission, but a distinct geometry baseline.  Exact pair
            # behaviour is then specialized by live regime/volatility and the
            # symbol×TF×direction ReviewTrader cell, avoiding arbitrary static
            # stereotypes per coin.
            speed = "FAST"
            preferred_rr = (1.9, 3.2)
            technical_rr_floor = 1.50
            near_max_atr = 0.58
            deep_min_atr = 0.88
            hard_max_reach_atr = {"30m": 2.3, "1h": 2.6, "2h": 2.8, "4h": 3.0, "12h": 3.2, "1D": 3.4}.get(tf, 2.8)
            target_atr_soft_max = 4.8
            weights["structure_liquidity"] += 0.05
            weights["volume_profile"] += 0.05
        elif bucket == "MEDIUM":
            speed = "FASTER"
            preferred_rr = (1.9, 3.0)
            technical_rr_floor = 1.45
            near_max_atr = 0.58
            deep_min_atr = 0.85
            hard_max_reach_atr = {"30m": 2.3, "1h": 2.6, "2h": 2.8, "4h": 3.0, "12h": 3.2, "1D": 3.4}.get(tf, 2.8)
            target_atr_soft_max = 4.6
            weights["pullback_retest"] += 0.08
            weights["structure_liquidity"] += 0.05
        elif bucket == "HIGH":
            speed = "VERY_FAST"
            preferred_rr = (1.8, 2.6)
            technical_rr_floor = 1.35
            near_max_atr = 0.55
            deep_min_atr = 0.80
            hard_max_reach_atr = {"30m": 2.2, "1h": 2.4, "2h": 2.6, "4h": 2.8, "12h": 3.0, "1D": 3.2}.get(tf, 2.6)
            target_atr_soft_max = 4.0
            weights["structure_liquidity"] += 0.10
            weights["pullback_retest"] += 0.10
            weights["volatility_risk"] += 0.12
        else:
            speed = "FAST"
            preferred_rr = (1.9, 3.2)
            technical_rr_floor = 1.50
            near_max_atr = 0.58
            deep_min_atr = 0.88
            hard_max_reach_atr = 2.8
            target_atr_soft_max = 4.8
        weights["smc_poi"] += 0.10
        weights["structure_liquidity"] += 0.10

    # Regime/context specialization.
    if regime in {"TRENDING_BULL", "TRENDING_BEAR"}:
        weights["pullback_retest"] += 0.15
        weights["trend_ema"] += 0.12
        weights["smc_poi"] += 0.06
    elif regime == "RANGING":
        weights["structure_liquidity"] += 0.16
        weights["volume_profile"] += 0.13
        weights["fibonacci"] += 0.08
    elif regime == "HIGH_VOLATILITY":
        weights["structure_liquidity"] += 0.18
        weights["volatility_risk"] += 0.20
        weights["smc_poi"] += 0.08
        hard_max_reach_atr += 0.35

    if setup in {"BREAKOUT_RETEST", "STRUCTURE_RETEST"}:
        weights["pullback_retest"] += 0.20
        weights["structure_liquidity"] += 0.08
        near_max_atr += 0.10
    elif any(token in setup for token in ("PULLBACK", "RETEST")):
        weights["pullback_retest"] += 0.18
        weights["trend_ema"] += 0.08
    elif any(token in setup for token in ("REVERS", "SWEEP", "LIQUID")):
        weights["structure_liquidity"] += 0.20
        weights["smc_poi"] += 0.10
        deep_min_atr = max(0.65, deep_min_atr - 0.10)

    # Volatility changes *where* we prefer execution and how much structural
    # breathing room SL needs.  It never changes the directional thesis.
    vol_bucket = vol["bucket"]
    if vol_bucket == "LOW":
        near_max_atr += 0.08
        sl_ideal = (1.6, 3.0)
        sl_hard_min_atr = 0.65
        sl_buffer_atr = 0.18
    elif vol_bucket == "HIGH":
        hard_max_reach_atr += 0.25
        sl_ideal = (2.0, 3.7)
        sl_hard_min_atr = 0.85
        sl_buffer_atr = 0.28
        weights["volatility_risk"] += 0.08
    elif vol_bucket == "EXTREME":
        hard_max_reach_atr += 0.45
        sl_ideal = (2.2, 4.0)
        sl_hard_min_atr = 0.95
        sl_buffer_atr = 0.35
        weights["volatility_risk"] += 0.15
    else:
        sl_ideal = (1.8, 3.4)
        sl_hard_min_atr = 0.75
        sl_buffer_atr = 0.22

    # Bounded ReviewTrader continuity can bias near vs deeper placement after
    # enough canonical samples.  It cannot create a hard gate or move levels by
    # itself.
    near_bias = learning["near_bias"]
    deep_bias = learning["deep_bias"]
    if deep_bias > 0:
        hard_max_reach_atr += min(0.45, deep_bias * 0.45)
        deep_min_atr = max(0.65, deep_min_atr - min(0.12, deep_bias * 0.12))
    if near_bias > 0:
        near_max_atr += min(0.12, near_bias * 0.12)

    # Keep every multiplier bounded.  This prevents any one family from acting
    # as an accidental veto/kingmaker.
    weights = {k: round(max(0.0, min(1.35, float(v))), 4) for k, v in weights.items()}

    specialization_key = "|".join([
        market.upper(), bucket, sym or "UNKNOWN", tf or "UNKNOWN",
        str(direction or "").upper() or "UNKNOWN", regime, vol["bucket"], setup,
    ])

    return {
        "version": VERSION,
        "specialization_key": specialization_key,
        "market": market,
        "symbol": sym,
        "timeframe": tf,
        "instrument_bucket": bucket,
        "mission": mission,
        "speed": speed,
        "regime": regime,
        "setup_family": setup,
        "volatility": vol,
        "specialist_weights": weights,
        "preferred_rr_min": round(preferred_rr[0], 3),
        "preferred_rr_max": round(preferred_rr[1], 3),
        "technical_rr_floor": round(max(1.0, technical_rr_floor), 3),
        "technical_rr_ceiling": round(max(technical_rr_floor, technical_rr_ceiling), 3),
        "near_max_atr": round(near_max_atr, 4),
        "deep_min_atr": round(deep_min_atr, 4),
        "hard_max_reach_atr": round(max(1.5, hard_max_reach_atr), 4),
        "target_atr_soft_max": round(target_atr_soft_max, 4),
        "sl_ideal_min_atr": round(sl_ideal[0], 4),
        "sl_ideal_max_atr": round(sl_ideal[1], 4),
        "sl_hard_min_atr": round(sl_hard_min_atr, 4),
        "sl_buffer_atr": round(sl_buffer_atr + learning["sl_buffer_bias"] * 0.10, 4),
        "learning": learning,
        "policy": {
            "geometry_only": True,
            "does_not_change_direction": True,
            "does_not_lower_safety": True,
            "near_or_deep_is_contextual": True,
            "orderflow_shadow_only": True,
        },
    }


def entry_family(candidate_type: Any) -> str:
    ctype = str(candidate_type or "").lower()
    if ctype in {"support", "resistance", "swing", "liquidity", "sweep"}:
        return "structure_liquidity"
    if ctype in {"ob", "fvg"}:
        return "smc_poi"
    if ctype in {"poc", "hvn", "lvn", "va"}:
        return "volume_profile"
    if ctype == "fib":
        return "fibonacci"
    if ctype in {"ema", "vwap"}:
        return "trend_ema"
    if ctype == "atr":
        return "volatility_risk"
    return "structure_liquidity"


def entry_candidate_adjustment(
    profile: Mapping[str, Any],
    *,
    candidate_type: Any,
    distance_atr: float,
    market_location: Any,
    directional_extension: bool,
    correct_side_near_reaction: bool,
    independent_family_count: int = 1,
) -> Dict[str, Any]:
    """Return a bounded score adjustment and technical timing mode."""
    profile = profile or {}
    weights = profile.get("specialist_weights") or {}
    family = entry_family(candidate_type)
    family_weight = _f(weights.get(family), 1.0)
    d_atr = max(0.0, _f(distance_atr, 999.0))
    near_max = max(0.2, _f(profile.get("near_max_atr"), 0.60))
    deep_min = max(near_max + 0.05, _f(profile.get("deep_min_atr"), 0.90))
    learning = profile.get("learning") or {}

    if d_atr <= near_max:
        mode = "NEAR_REACTION"
    elif d_atr >= deep_min:
        mode = "DEEP_PULLBACK_LIMIT"
    else:
        mode = "STRUCTURAL_PULLBACK"

    adjustment = (family_weight - 1.0) * 18.0
    # Independent-family confluence is already incorporated once in the causal
    # POI score by app.py.  Do not count it a second time here.

    if directional_extension:
        if mode == "DEEP_PULLBACK_LIMIT":
            adjustment += 12.0
        elif mode == "NEAR_REACTION":
            adjustment -= 14.0
    elif correct_side_near_reaction:
        if mode == "NEAR_REACTION":
            adjustment += 11.0
        elif mode == "DEEP_PULLBACK_LIMIT":
            adjustment -= 4.0

    setup = str(profile.get("setup_family") or "").upper()
    if setup in {"BREAKOUT_RETEST", "STRUCTURE_RETEST"} and mode in {"NEAR_REACTION", "STRUCTURAL_PULLBACK"}:
        adjustment += 7.0

    regime = str(profile.get("regime") or "").upper()
    if regime == "RANGING" and mode == "DEEP_PULLBACK_LIMIT":
        adjustment += 5.0
    elif regime.startswith("TRENDING") and mode == "STRUCTURAL_PULLBACK":
        adjustment += 5.0

    adjustment += _f(learning.get("near_bias"), 0.0) * (7.0 if mode == "NEAR_REACTION" else -1.5)
    adjustment += _f(learning.get("deep_bias"), 0.0) * (7.0 if mode == "DEEP_PULLBACK_LIMIT" else -1.5)

    return {
        "adjustment": round(max(-20.0, min(20.0, adjustment)), 3),
        "timing_mode": mode,
        "family": family,
    }


def sl_candidate_adjustment(profile: Mapping[str, Any], *, candidate_type: Any, distance_atr: float) -> float:
    profile = profile or {}
    weights = profile.get("specialist_weights") or {}
    family = entry_family(candidate_type)
    family_weight = _f(weights.get(family), 1.0)
    lo = _f(profile.get("sl_ideal_min_atr"), 1.8)
    hi = _f(profile.get("sl_ideal_max_atr"), 3.4)
    d = max(0.0, _f(distance_atr, 0.0))
    adj = (family_weight - 1.0) * 14.0
    if lo <= d <= hi:
        adj += 7.0
    elif d < max(0.6, lo * 0.65):
        adj -= 10.0
    elif d > hi + 1.0:
        adj -= 7.0
    return round(max(-15.0, min(15.0, adj)), 3)


def tp_candidate_adjustment(
    profile: Mapping[str, Any],
    *,
    candidate_type: Any,
    rr: float,
    distance_atr: float | None,
) -> float:
    """Commit 13 target ranking: structure first, reachability second, R/R third.

    The function only re-ranks structural targets already detected by the base
    engine. ReviewTrader is deliberately weak at first: N<8 has zero influence;
    after that its MFE/tp_speed hint is bounded and can never create a TP.
    """
    profile = profile or {}
    weights = profile.get("specialist_weights") or {}
    learning = profile.get("learning") or {}
    family = entry_family(candidate_type)
    family_weight = _f(weights.get(family), 1.0)
    rr = max(0.0, _f(rr, 0.0))
    rr_floor = max(1.0, _f(profile.get("technical_rr_floor"), 1.8))
    rr_lo = max(rr_floor, _f(profile.get("preferred_rr_min"), 1.8))
    rr_hi = max(rr_lo, _f(profile.get("preferred_rr_max"), 3.5))
    rr_ceiling = max(rr_hi, _f(profile.get("technical_rr_ceiling"), 4.5))
    adj = (family_weight - 1.0) * 12.0

    # A target near the preferred band gets the best economic score.  Targets
    # between the technical floor and preferred band remain valid rather than
    # being discarded merely to manufacture 1.8R+.
    if rr_lo <= rr <= rr_hi:
        adj += 8.0
    elif rr_floor <= rr < rr_lo:
        span = max(0.05, rr_lo - rr_floor)
        adj += 2.0 + 4.0 * ((rr - rr_floor) / span)
    elif rr < rr_floor:
        adj -= min(16.0, 8.0 + (rr_floor - rr) * 10.0)
    elif rr > rr_ceiling:
        adj -= min(16.0, 8.0 + (rr - rr_ceiling) * 6.0)
    elif rr > rr_hi:
        adj -= min(10.0, (rr - rr_hi) * 5.0)

    if distance_atr is not None:
        d = max(0.0, _f(distance_atr, 0.0))
        soft_max = max(1.0, _f(profile.get("target_atr_soft_max"), 5.0))
        if d <= soft_max:
            adj += 5.0
        else:
            speed = str(profile.get("speed") or "")
            scale = 3.0 if speed == "VERY_FAST" else 2.2 if speed == "FASTER" else 1.5
            adj -= min(14.0, (d - soft_max) * scale)

    # ReviewTrader continuity — intentionally bounded.  The profile already
    # guarantees zero weight for N<8. avg_mfe_r is observed excursion, not a
    # promise; it can only bias ranking among technically valid targets.
    n = int(_f(learning.get("sample_size"), 0))
    weight = max(0.0, min(0.16, _f(learning.get("weight"), 0.0)))
    if n >= 8 and weight > 0:
        avg_mfe = _f(learning.get("avg_mfe_r"), 0.0)
        speed_bias = max(0.0, min(1.0, _f(learning.get("tp_speed_bias"), 0.0)))
        if avg_mfe > 0:
            # Reward targets that sit inside observed favorable excursion and
            # progressively penalize targets far beyond it.
            ratio = rr / max(0.25, avg_mfe)
            if 0.70 <= ratio <= 1.15:
                adj += 5.0 * (weight / 0.16)
            elif ratio > 1.35:
                adj -= min(8.0, (ratio - 1.35) * 5.0) * (weight / 0.16)
        if speed_bias > 0:
            # Faster-target bias is strongest close to the technical floor but
            # capped so learning never overrules structure or Safety.
            band = max(0.10, rr_hi - rr_floor)
            closeness = max(0.0, min(1.0, (rr_hi - rr) / band))
            adj += min(6.0, speed_bias * 6.0 * closeness * (weight / 0.16))

    return round(max(-18.0, min(18.0, adj)), 3)

