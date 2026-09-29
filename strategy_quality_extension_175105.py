"""17.5.10.5 — Strategy Bank temporal scope + continuation SHADOW candidate.

This module deliberately does NOT activate a new production family from a small
backtest.  It fixes the existing temporal specialization bug and exposes
TREND_DISPLACEMENT_CONTINUATION only as shadow diagnostic until its forward
cohort is large enough.

Historical evidence (production geometries, Futures 30m):
- band-walk aligned with complete MTF alignment
- chronological 70/30 split
- cost stress 0.118R per entered trade
- IS: 6 trades, Exp +0.0655R, PF 1.088
- OOS: 4 trades, Exp +1.4797R, PF 6.294
But LONG-only aggregate was negative and total N=10, therefore this is not
sufficient for LIVE family authority without overfitting.

No signal-count quota is introduced.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping
import threading

VERSION = "17.5.10.5_STRATEGY_SCOPE_CONTINUATION_SHADOW_V1"
_LOCK = threading.RLock()
_STATE = {"installed": False, "version": VERSION}

_BACKTEST = {
    "scope": "FUTURES_30M_EXISTING_SYSTEM_GEOMETRY",
    "family": "TREND_DISPLACEMENT_CONTINUATION",
    "authority": "SHADOW_ONLY_SMALL_SAMPLE",
    "is": {"n": 6, "tp": 2, "expectancy_r": 0.0655, "profit_factor": 1.088, "net_r": 0.3929},
    "oos": {"n": 4, "tp": 3, "expectancy_r": 1.4797, "profit_factor": 6.294, "net_r": 5.9187},
    "overall_by_direction": {
        "LONG": {"n": 3, "expectancy_r": -0.1427, "profit_factor": 0.809},
        "SHORT": {"n": 7, "expectancy_r": 0.9628, "profit_factor": 3.009},
    },
    "promotion_reason": "NOT_PROMOTED_DIRECTIONAL_ASYMMETRY_AND_N_TOO_SMALL",
}


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v if v is not None else d)
    except Exception:
        return float(d)


def continuation_shadow_context(
    action: str, regime: str, volatility: str, groups: Mapping[str, Any],
    *, timeframe: str, market: str
) -> Dict[str, Any]:
    """Detect the missing continuation context without granting production authority."""
    action = _u(action)
    regime = _u(regime)
    volatility = _u(volatility)
    timeframe = _u(timeframe)
    market = _u(market)
    side = 1 if action in {"LONG", "COMPRA_SPOT"} else -1

    trend = dict(groups.get("trend") or {})
    momentum = dict(groups.get("momentum") or {})
    flow = dict(groups.get("volume_flow") or {})
    structure = dict(groups.get("structure_liquidity") or {})
    mtf = dict(groups.get("multi_timeframe") or {})

    adx = _f(trend.get("adx"))
    pd = _f(trend.get("plus_di"))
    md = _f(trend.get("minus_di"))
    macd = _f(momentum.get("macd_histogram"))
    vr = _f(flow.get("volume_ratio"), 1.0)
    trend_dir = _u(trend.get("direction") or trend.get("trend_direction"))
    mtf_dir = _u(mtf.get("dominant_direction") or mtf.get("direction"))
    mtf_conflict = bool(mtf.get("conflict"))

    dmi = (pd > md) if side > 0 else (md > pd)
    trend_ok = trend_dir in (
        {"BULLISH", "UP", "TREND_UP"} if side > 0
        else {"BEARISH", "DOWN", "TREND_DOWN"}
    )
    mtf_ok = (
        not mtf_conflict and
        mtf_dir in (
            {"BULLISH", "UP", "TREND_UP"} if side > 0
            else {"BEARISH", "DOWN", "TREND_DOWN"}
        )
    )
    momentum_ok = macd > 0 if side > 0 else macd < 0
    displacement = bool(
        structure.get("displacement")
        or structure.get("has_displacement")
        or structure.get("mss_bos")
        or structure.get("has_bos")
    )
    regime_ok = regime in (
        {"TREND_UP", "TRANSITION"} if side > 0
        else {"TREND_DOWN", "TRANSITION"}
    )
    volatility_ok = volatility in {
        "NORMAL", "EXPANSION", "HIGH_EXPANSION", "SHOCK", "VOLATILITY_SHOCK"
    }

    evidence = {
        "regime": regime_ok,
        "trend": trend_ok,
        "adx_dmi": adx >= 25 and dmi,
        "momentum": momentum_ok,
        "activity": vr >= 1.10,
        "mtf": mtf_ok,
        "displacement": displacement,
        "volatility": volatility_ok,
    }
    hits = sum(bool(x) for x in evidence.values())
    candidate = (
        market == "FUTURES"
        and timeframe in {"30M", "1H", "2H", "4H"}
        and evidence["regime"]
        and evidence["trend"]
        and evidence["adx_dmi"]
        and evidence["mtf"]
        and evidence["volatility"]
        and (evidence["displacement"] or evidence["momentum"])
        and hits >= 6
    )
    return {
        "version": VERSION,
        "family": "TREND_DISPLACEMENT_CONTINUATION",
        "candidate": candidate,
        "evidence": evidence,
        "evidence_hits": hits,
        "authority": "SHADOW_ONLY",
        "can_create_direction": False,
        "can_select_live_strategy": False,
        "backtest": _BACKTEST,
    }


def install_strategy_quality_extension_175105() -> Dict[str, Any]:
    """Make declared family/timeframe scopes real in the already-loaded bank."""
    with _LOCK:
        if _STATE["installed"]:
            return dict(_STATE)
        import default_strategy_bank as bank

        original_count = len(getattr(bank, "STRATEGIES", []) or [])
        family_tf = getattr(bank, "_FAMILY_TIMEFRAMES", {}) or {}
        filtered = []
        removed = 0
        for row in list(getattr(bank, "STRATEGIES", []) or []):
            market = "FUTURES" if any(
                a in {"LONG", "SHORT"} for a in (row.get("actions") or [])
            ) else "SPOT"
            family = _u(row.get("family"))
            tfs = [_u(x) for x in (row.get("timeframes") or [])]
            allowed = {_u(x) for x in ((family_tf.get(market) or {}).get(family) or [])}
            # Families with explicit declared scope must obey it. Unknown/new
            # families are left untouched until separately governed.
            if allowed and tfs and not any(tf in allowed for tf in tfs):
                removed += 1
                continue
            filtered.append(row)

        bank.STRATEGIES[:] = filtered

        # Expose SHADOW diagnostic to callers/research without changing
        # select_strategy() production behavior.
        bank.continuation_shadow_context_175105 = continuation_shadow_context
        bank.TREND_DISPLACEMENT_CONTINUATION_BACKTEST_175105 = dict(_BACKTEST)

        _STATE.update({
            "installed": True,
            "original_strategy_count": original_count,
            "runtime_strategy_count": len(filtered),
            "out_of_scope_specializations_removed": removed,
            "continuation_authority": "SHADOW_ONLY_SMALL_SAMPLE",
            "no_signal_count_quota": True,
        })
        return dict(_STATE)
