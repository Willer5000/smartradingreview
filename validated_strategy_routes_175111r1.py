"""Commit 17.5.11R.1 — validated context-route bridge.

This module does NOT create LONG/SHORT direction and does NOT bypass Safety,
Entry/SL/TP, R/R, publication, MTF conflict, or Alpha Decay.  It only maps an
exact positive Research prior to the execution semantics that were actually
validated for the same market×symbol×TF×direction cell.

Why it exists
-------------
Research already contains causal, cost-aware IS/selection/OOS/walk-forward
specialists, while Main's generic strategy bank uses broader archetypes.  Before
R.1 a valid exact Research prior could open a LEARNED+LIVE candidate, but the
price-level desk could still receive a *different generic setup family*.  That
mismatch can reduce coverage and, more importantly, can ask Entry/SL/TP to solve
the wrong geometric problem.

R.1 keeps two identities per validated route:
- bank_family: the existing generic playbook family used only for contextual
  ranking in default_strategy_bank.py;
- execution_family: the geometric setup semantics consumed by the execution
  committees.

The frozen registry below is evidence provenance, not a promise of future
profit.  Runtime activation still verifies the live Research prior, regime /
volatility compatibility, current market evidence and every downstream gate.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

VERSION = "COMMIT17_5_11R_1_VALIDATED_CONTEXT_ROUTES_V1"

_POSITIVE_PRIOR_STATES = {"OOS_VALIDATED", "OOS_PLUS_SHADOW"}
_POSITIVE_STAGES = {"SHADOW_READY", "SHADOW_READY_FAST"}


def _u(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


# Evidence was read from the project's governed Research promotions on
# 2026-09-30.  Discovery/selection/final OOS are causal candle replays with
# modeled fees/slippage/funding stress.  Only exact-cell routing is allowed.
# Only ETH 2H LONG, SOL 2H SHORT and XRP 2H SHORT have positive train/IS,
# selection holdout and final OOS in the current Research snapshot.  ADA 2H,
# LINK 2H and ADA 4H remain SHADOW because their train/IS expectancy is negative
# (and ADA 4H also has only N=6 final OOS).
_ROUTE_REGISTRY: Dict[Tuple[str, str, str], Dict[str, Any]] = {
    ("ADA-USDT", "2H", "SHORT"): {
        "research_family": "SWEEP_REVERSAL",
        "bank_family": "SWEEP_REVERSAL",
        "execution_family": "SWEEP_REVERSAL",
        "required_regime": "ALL",
        "required_volatility": "ANY",
        "strategy_id": "CI_059db607a807f377ed46",
        "historical_geometry": {"entry_style": "PULLBACK", "entry_atr": 0.18, "sl_atr": 0.90, "rr": 2.50},
        "stage": "SHADOW_READY_FAST",
        "evidence": {
            "is_n": 34, "is_expectancy_r": -0.03750, "is_pf": 0.9490,
            "selection_n": 12, "selection_expectancy_r": 1.28456, "selection_pf": 5.6099,
            "oos_n": 12, "oos_expectancy_r": 0.55960, "oos_pf": 2.1422,
            "walk_forward_positive_ratio": 1.0,
        },
        "routing_authority": "SHADOW_CONTEXT_ONLY_IS_NOT_PROFITABLE",
        "public_role": "liquidity_reversal",
        "shadow_only": True,
    },
    ("ETH-USDT", "2H", "LONG"): {
        "research_family": "RSI_TREND",
        "bank_family": "TREND_PULLBACK",
        "execution_family": "MOMENTUM_CONTINUATION",
        "required_regime": "TREND_UP",
        "required_volatility": "ANY",
        "strategy_id": "CI_7dc3d4ab4f264a96efbf",
        "historical_geometry": {"entry_style": "NEXT_OPEN", "entry_atr": 0.0, "sl_atr": 2.00, "rr": 2.00},
        "stage": "SHADOW_READY_FAST",
        "evidence": {
            "is_n": 40, "is_expectancy_r": 0.08660, "is_pf": 1.1850,
            "selection_n": 14, "selection_expectancy_r": 0.16459, "selection_pf": 1.4815,
            "oos_n": 14, "oos_expectancy_r": 0.33306, "oos_pf": 1.9675,
            "walk_forward_positive_ratio": 1.0,
        },
        "routing_authority": "VALIDATED_CONTEXT_ROUTING_ONLY",
        "public_role": "trend_momentum",
    },
    ("SOL-USDT", "2H", "SHORT"): {
        "research_family": "SUPERTREND_PULLBACK",
        "bank_family": "TREND_PULLBACK",
        "execution_family": "TREND_PULLBACK",
        "required_regime": "TREND_DOWN",
        "required_volatility": "ANY",
        "strategy_id": "CI_3f4785da4741e4832a55",
        "historical_geometry": {"entry_style": "PULLBACK", "entry_atr": 0.18, "sl_atr": 0.90, "rr": 3.00},
        "stage": "SHADOW_READY",
        "evidence": {
            "is_n": 23, "is_expectancy_r": 0.10150, "is_pf": 1.1380,
            "selection_n": 8, "selection_expectancy_r": 0.50334, "selection_pf": 1.8731,
            "oos_n": 8, "oos_expectancy_r": 0.31297, "oos_pf": 1.4160,
            "walk_forward_positive_ratio": 1.0,
        },
        "routing_authority": "VALIDATED_CONTEXT_ROUTING_ONLY",
        "public_role": "trend_pullback",
    },
    ("XRP-USDT", "2H", "SHORT"): {
        "research_family": "TREND_CONTINUATION",
        "bank_family": "TREND_PULLBACK",
        "execution_family": "MOMENTUM_CONTINUATION",
        "required_regime": "TREND_DOWN",
        "required_volatility": "ANY",
        "strategy_id": "CI_dee44897471478b235ce",
        "historical_geometry": {"entry_style": "NEXT_OPEN", "entry_atr": 0.0, "sl_atr": 1.40, "rr": 3.00},
        "stage": "SHADOW_READY_FAST",
        "evidence": {
            "is_n": 52, "is_expectancy_r": 0.11130, "is_pf": 1.2120,
            "selection_n": 17, "selection_expectancy_r": 0.33056, "selection_pf": 1.8261,
            "oos_n": 18, "oos_expectancy_r": 0.27854, "oos_pf": 1.5187,
            "walk_forward_positive_ratio": 1.0,
        },
        "routing_authority": "VALIDATED_CONTEXT_ROUTING_ONLY",
        "public_role": "trend_continuation",
    },
    ("LINK-USDT", "2H", "SHORT"): {
        "research_family": "RSI_MAVERICK_REVERSAL",
        "bank_family": "MEAN_REVERSION",
        "execution_family": "MEAN_REVERSION",
        "required_regime": "BALANCE",
        "required_volatility": "ANY",
        "strategy_id": "CI_d50a56adba839b8af9f1",
        "historical_geometry": {"entry_style": "NEXT_OPEN", "entry_atr": 0.0, "sl_atr": 0.90, "rr": 1.60},
        "stage": "SHADOW_READY",
        "evidence": {
            "is_n": 26, "is_expectancy_r": -0.11000, "is_pf": 0.8370,
            "selection_n": 9, "selection_expectancy_r": 0.86714, "selection_pf": 4.4578,
            "oos_n": 9, "oos_expectancy_r": 0.26415, "oos_pf": 1.5093,
            "walk_forward_positive_ratio": 1.0,
        },
        "routing_authority": "SHADOW_CONTEXT_ONLY_IS_NOT_PROFITABLE",
        "public_role": "balance_reversal",
        "shadow_only": True,
    },
    ("ADA-USDT", "4H", "SHORT"): {
        "research_family": "BOLLINGER_SQUEEZE",
        "bank_family": "BREAKOUT_RETEST",
        "execution_family": "COMPRESSION_EXPANSION",
        "required_regime": "ALL",
        "required_volatility": "EXPANSION",
        "strategy_id": "CI_2884bbb454909b59180a",
        "historical_geometry": {"entry_style": "NEXT_OPEN", "entry_atr": 0.0, "sl_atr": 1.15, "rr": 1.60},
        "stage": "SHADOW_READY",
        "evidence": {
            "is_n": 16, "is_expectancy_r": -0.12020, "is_pf": 0.8040,
            "selection_n": 6, "selection_expectancy_r": 0.55671, "selection_pf": 3.0143,
            "oos_n": 6, "oos_expectancy_r": 0.96485, "oos_pf": 6.6179,
            "walk_forward_positive_ratio": 1.0,
        },
        "routing_authority": "SHADOW_CONTEXT_ONLY_IS_NEGATIVE_AND_SMALL_OOS",
        "public_role": "volatility_expansion",
        "shadow_only": True,
    },
}


def route_registry() -> Dict[str, Dict[str, Any]]:
    """Serializable, immutable-ish copy for QA/audit; no DB/network work."""
    return {
        "|".join(key): {**value, "evidence": dict(value.get("evidence") or {})}
        for key, value in _ROUTE_REGISTRY.items()
    }


def _regime_compatible(required: str, actual: str) -> bool:
    required, actual = _u(required), _u(actual)
    if required in {"", "ALL", "ANY"}:
        return True
    # operational_intelligence canonicalizes RANGING/RANGE to BALANCE.
    return required == actual


def _volatility_compatible(required: str, actual: str) -> bool:
    required, actual = _u(required), _u(actual)
    if required in {"", "ALL", "ANY"}:
        return True
    if required == "EXPANSION":
        return actual in {"EXPANSION", "SHOCK", "HIGH_EXPANSION", "VOLATILITY_SHOCK"}
    if required == "COMPRESSION":
        return actual in {"COMPRESSION", "SQUEEZE"}
    return required == actual


def _prior_evidence_ok(best: Mapping[str, Any], spec: Mapping[str, Any]) -> bool:
    ev = spec.get("evidence") or {}
    oos_n = _i(best.get("oos_n"))
    oos_exp = _f(best.get("oos_exp_r"), -999.0)
    oos_pf = _f(best.get("oos_pf"), 0.0)
    # Dynamic Research evidence may have grown since the frozen audit.  It may
    # exceed, but may not fall below, the conservative thresholds below.
    min_n = 6 if spec.get("shadow_only") else max(8, min(12, _i(ev.get("oos_n"), 8)))
    return bool(
        oos_n >= min_n
        and oos_exp > 0.10
        and oos_pf > 1.20
        and str(best.get("stage") or "").upper() in _POSITIVE_STAGES
        and bool(best.get("runtime_trackable", True))
        and not bool(best.get("recycle_required"))
    )


def resolve_validated_route(
    *, prior: Mapping[str, Any] | None, symbol: Any, timeframe: Any,
    action: Any, regime: Any, volatility: Any,
) -> Dict[str, Any]:
    """Return exact validated context route, never a new directional signal.

    `eligible_for_execution_routing=True` means only that the existing live
    candidate may use the historically validated setup semantics.  It does not
    make the candidate executable and never overrides downstream controls.
    """
    key = (_u(symbol), _u(timeframe), _u(action))
    spec = _ROUTE_REGISTRY.get(key)
    base = {
        "version": VERSION,
        "cell_key": "|".join(key),
        "symbol": key[0], "timeframe": key[1], "action": key[2],
        "matched": bool(spec),
        "eligible_for_execution_routing": False,
        "authority": "NONE",
        "reason": "NO_VALIDATED_CONTEXT_ROUTE",
        "never_creates_direction": True,
        "never_bypasses_safety": True,
    }
    if not spec:
        return base

    out = {**base, **{k: v for k, v in spec.items() if k != "evidence"}}
    out["frozen_evidence"] = dict(spec.get("evidence") or {})
    out["authority"] = str(spec.get("routing_authority") or "RESEARCH_ONLY")

    p = dict(prior or {})
    best = dict(p.get("best_positive") or {})
    out["live_prior_state"] = str(p.get("state") or "UNAVAILABLE")
    out["live_prior_stage"] = str(best.get("stage") or "")
    out["live_prior_strategy_family"] = str(best.get("strategy_family") or "")
    out["live_prior_oos_n"] = _i(best.get("oos_n"))
    out["live_prior_oos_expectancy_r"] = _f(best.get("oos_exp_r"), 0.0)
    out["live_prior_oos_profit_factor"] = _f(best.get("oos_pf"), 0.0)

    if p.get("recycle_required") or str(p.get("state") or "").upper() in {"SHADOW_DIVERGED", "ALPHA_DECAY_WATCH", "NEGATIVE_OOS"}:
        out["reason"] = "RESEARCH_PRIOR_NOT_HEALTHY"
        return out
    if _u(p.get("state")) not in _POSITIVE_PRIOR_STATES:
        out["reason"] = "EXACT_POSITIVE_RESEARCH_PRIOR_NOT_ACTIVE"
        return out
    if _u(best.get("strategy_family")) != _u(spec.get("research_family")):
        out["reason"] = "RESEARCH_FAMILY_VERSION_MISMATCH"
        return out
    if not _prior_evidence_ok(best, spec):
        out["reason"] = "RESEARCH_EVIDENCE_BELOW_ROUTING_FLOOR"
        return out
    if not _regime_compatible(str(spec.get("required_regime") or "ALL"), _u(regime)):
        out["reason"] = "REGIME_NOT_COMPATIBLE_WITH_VALIDATED_ROUTE"
        return out
    if not _volatility_compatible(str(spec.get("required_volatility") or "ANY"), _u(volatility)):
        out["reason"] = "VOLATILITY_NOT_COMPATIBLE_WITH_VALIDATED_ROUTE"
        return out
    if spec.get("shadow_only"):
        out["reason"] = "POSITIVE_BUT_SMALL_OOS_SHADOW_ONLY"
        return out

    out["eligible_for_execution_routing"] = True
    out["reason"] = "EXACT_OOS_VALIDATED_CONTEXT_ROUTE"
    return out


def coverage_summary() -> Dict[str, Any]:
    live = [v for v in _ROUTE_REGISTRY.values() if not v.get("shadow_only")]
    shadow = [v for v in _ROUTE_REGISTRY.values() if v.get("shadow_only")]
    return {
        "version": VERSION,
        "exact_routes": len(_ROUTE_REGISTRY),
        "execution_routing_routes": len(live),
        "shadow_only_routes": len(shadow),
        "policy": "EXACT_CELL_OOS_PLUS_WALK_FORWARD_NO_GLOBAL_PARAMETER_PROMOTION",
    }
