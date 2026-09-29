"""Commit 17.5.10 — profitability-qualified incremental recovery evidence.

This module freezes ONE simple, interpretable historical cohort instead of
optimizing dozens of parameters until a profitable result appears.

Cohort (Futures 30m):
- execution challenger: LIQUIDITY_SWEEP_MSS_POI;
- trend aligned with LONG/SHORT;
- ADX >= 20;
- relative volume >= 1.20;
- RSI not in the outer 20/80 extreme against a fresh continuation entry.

The thresholds are deliberately broad/canonical.  A small neighbourhood test is
stored in the report; the selected point is not the best point in that grid.

Accounting stress used for release evidence:
- every unresolved/expired-after-entry = -1R;
- every entered trade pays 0.118R cost (median historical 30m modeled fee+
  slippage proxy; N=46).

DEV 2026-09-10..13: N=11, +1.702R stressed, PF 1.254.
HOLDOUT 2026-09-14..16: N=4, +3.928R stressed, PF 4.513.

This is preliminary evidence, NOT a guarantee and NOT a clean prospective OOS of
17.5.10.  It can qualify a recovery route; it cannot bypass Safety, publication,
or create direction.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

VERSION = "COMMIT17_5_10_PROFITABILITY_QUALIFIED_V1"
COST_STRESS_R = 0.118
ROUTE = "LIQUIDITY_SWEEP_MSS_POI"

EVIDENCE = {
    "development": {
        "period": "2026-09-10..2026-09-13", "n": 11, "tp": 5, "sl": 1,
        "expired_after_entry": 4, "other_unresolved": 1,
        "net_stress_r": 1.702, "profit_factor_stress": 1.254,
        "max_drawdown_r": 2.236,
    },
    "holdout": {
        "period": "2026-09-14..2026-09-16", "n": 4, "tp": 3, "sl": 0,
        "expired_after_entry": 1, "other_unresolved": 0,
        "net_stress_r": 3.928, "profit_factor_stress": 4.513,
        "max_drawdown_r": 1.118,
    },
    "combined_stress_net_r": 5.630,
    "cost_stress_r_per_entry": COST_STRESS_R,
    "unresolved_treatment": "FULL_MINUS_1R",
    "status": "PROFITABLE_HISTORICAL_COHORT_PRELIMINARY_NOT_PROSPECTIVE",
}


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _find_mapping(result: Mapping[str, Any], *names: str) -> Dict[str, Any]:
    for name in names:
        row = result.get(name)
        if isinstance(row, Mapping):
            return dict(row)
    return {}


def _extract_features(result: Mapping[str, Any]) -> Dict[str, Any]:
    levels = _find_mapping(result, "levels")
    indicators = _find_mapping(result, "indicators", "indicators_snapshot")
    trend = _find_mapping(result, "trend")
    momentum = _find_mapping(result, "momentum")
    volume = _find_mapping(result, "volume")
    data = _find_mapping(result, "data")
    if not indicators and isinstance(data.get("indicators"), Mapping):
        indicators = dict(data.get("indicators") or {})

    adx = _f(indicators.get("adx"), _f(momentum.get("adx"), _f(trend.get("adx"), 0.0)))
    volume_ratio = _f(indicators.get("volume_ratio"), _f(volume.get("volume_ratio"), _f(volume.get("ratio"), 0.0)))
    rsi = _f(indicators.get("rsi"), _f(momentum.get("rsi"), 50.0))
    trend_dir = _u(indicators.get("trend_direction") or trend.get("direction") or trend.get("trend"))
    action = _u((_find_mapping(result, "decision").get("action")) or result.get("action"))
    timeframe = _u(result.get("timeframe"))
    market = _u(result.get("system_type") or result.get("market") or "FUTURES")
    source = _u(levels.get("entry_source"))
    entry_class = _u(levels.get("entry_evidence_class"))
    route_like = bool(
        entry_class == "LIQUIDITY_SWEEP_STRUCTURE_POI"
        or (
            levels.get("entry_sweep_confirmed")
            and levels.get("entry_mss_bos_confirmed")
            and (levels.get("entry_liquidity_pool_near") or any(k in source for k in ("POI", "LIQUID", "ORDER BLOCK", "FVG")))
        )
    )
    return {
        "market": market, "timeframe": timeframe, "action": action,
        "adx": adx, "volume_ratio": volume_ratio, "rsi": rsi,
        "trend_direction": trend_dir, "route_like": route_like,
    }


def qualify_result(result: Mapping[str, Any], *, market: Any = "futures") -> Dict[str, Any]:
    f = _extract_features(result)
    mk = _u(market or f["market"])
    tf = f["timeframe"]
    action = f["action"]
    trend = f["trend_direction"]
    aligned = (
        (action == "LONG" and trend in {"BULLISH", "UP", "TREND_UP", "ALCISTA"})
        or (action == "SHORT" and trend in {"BEARISH", "DOWN", "TREND_DOWN", "BAJISTA"})
    )
    rsi_ok = (action == "LONG" and f["rsi"] <= 80.0) or (action == "SHORT" and f["rsi"] >= 20.0)
    checks = {
        "futures_30m": mk == "FUTURES" and tf in {"30M", "30MIN"},
        "liquidity_sweep_mss_poi": bool(f["route_like"]),
        "trend_aligned": bool(aligned),
        "adx_gte_20": f["adx"] >= 20.0,
        "volume_ratio_gte_1_2": f["volume_ratio"] >= 1.20,
        "rsi_not_outer_extreme": bool(rsi_ok),
    }
    qualified = all(checks.values())
    return {
        "version": VERSION,
        "qualified": bool(qualified),
        "route": ROUTE,
        "checks": checks,
        "features": {k: f[k] for k in ("adx", "volume_ratio", "rsi", "trend_direction", "action", "timeframe")},
        "evidence": EVIDENCE,
        "authority": "INCREMENTAL_RECOVERY_QUALIFIER_ONLY",
        "can_create_direction": False,
        "can_bypass_safety": False,
        "can_bypass_publication": False,
        "can_raise_leverage": False,
    }
