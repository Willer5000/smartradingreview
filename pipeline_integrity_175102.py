"""Commit 17.5.10.2 — Particular Setup Router + pipeline integrity.

Compatibility note
------------------
`app.py` from Commit 17.5.10.1 imports `pipeline_integrity_175101`.
The companion shim keeps that import stable while this module owns 17.5.10.2.

Goals
-----
1. Preserve all authoritative downstream gates: Entry, SL, TP, R/R, Safety,
   Publication and Leverage V6.
2. Stop treating every valid setup as if it needed the same evidence pattern.
3. Allow a setup-specific technical contract to restore a candidate only when
   its own core evidence is complete, Strategy Bank quality is sufficient and
   MTF/macro conditions are usable.
4. Keep Research generation-aware: stale historical negative evidence is
   counter-evidence, not an irreversible pre-candidate veto.
5. Preserve the 17.5.10.1 free-runtime Multi-Asset routing behavior.

This module deliberately contains no network calls, no DB calls, no LLM calls
and starts no threads.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
from typing import Any, Dict, Mapping, Iterable, List, Tuple

VERSION = "17.5.10.2_PIPELINE_INTEGRITY_V2"
PIPELINE_GENERATION = "17.5.10.2"
RELEASED_AT_UTC = "2026-09-29T14:45:00+00:00"

_DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}
_NEGATIVE_RESEARCH_STATES = {
    "REJECTED_OOS", "NEGATIVE_OOS", "SHADOW_DIVERGED", "ALPHA_DECAY",
    "DEGRADED", "REVOKED",
}

__all__ = [
    "VERSION", "PIPELINE_GENERATION", "RELEASED_AT_UTC",
    "reconcile_operational_candidate", "profitability_hard_block_authority",
    "stamp_pipeline_generation", "particular_setup_diagnostic",
    "_multiasset_strategy_from_live_layers",
]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else float(default)
    except Exception:
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _direction(value: Any) -> str:
    raw = _u(value)
    if raw in {"LONG", "BUY", "BULL", "BULLISH", "ALCISTA", "UP"}:
        return "BULLISH"
    if raw in {"SHORT", "SELL", "BEAR", "BEARISH", "BAJISTA", "DOWN"}:
        return "BEARISH"
    return "NEUTRAL"


def _action(direction: str, market: str) -> str:
    if direction == "BULLISH":
        return "LONG" if market == "FUTURES" else "COMPRA_SPOT"
    if direction == "BEARISH":
        return "SHORT" if market == "FUTURES" else "VENTA_SPOT"
    return "NO_OPERAR"


def _contains(blob: str, *tokens: str) -> bool:
    b = str(blob or "").upper()
    return any(str(t).upper() in b for t in tokens)


def _layer_blob(layers: Mapping[str, Any]) -> str:
    keep = {
        "trend": layers.get("trend") or {},
        "momentum": layers.get("momentum") or {},
        "volatility": layers.get("volatility") or {},
        "volume": layers.get("volume") or {},
        "structure": layers.get("structure") or {},
        "confirmation": layers.get("confirmation") or {},
        "market_hours": layers.get("market_hours") or {},
        "macro_context": layers.get("macro_context") or {},
    }
    return str(keep).upper()


def _dir_in_rows(rows: Any, direction: str) -> bool:
    desired = "BULLISH" if direction == "BULLISH" else "BEARISH"
    for row in rows or []:
        if isinstance(row, Mapping):
            raw = (
                row.get("direction") or row.get("type") or row.get("side")
                or row.get("bias") or row.get("action")
            )
            if _direction(raw) == desired:
                return True
            text = str(row).upper()
        else:
            text = str(row).upper()
        if desired == "BULLISH" and any(x in text for x in ("BULL", "ALCIST", "LONG", "BUY")):
            return True
        if desired == "BEARISH" and any(x in text for x in ("BEAR", "BAJIST", "SHORT", "SELL")):
            return True
    return False


def _indicator(container: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(container, Mapping) and container.get(key) is not None:
            return container.get(key)
    inner = container.get("indicators") if isinstance(container, Mapping) else None
    if isinstance(inner, Mapping):
        for key in keys:
            if inner.get(key) is not None:
                return inner.get(key)
    return default


def _live_evidence(
    layers: Mapping[str, Any], operational: Mapping[str, Any], direction: str
) -> Dict[str, Any]:
    """Normalize live evidence into setup roles.

    Roles are intentionally broad and correlated indicators stay inside one role.
    No role is created from Greeks/options data in 17.5.10.2.
    """
    trend = dict(layers.get("trend") or {})
    momentum = dict(layers.get("momentum") or {})
    volatility = dict(layers.get("volatility") or {})
    volume = dict(layers.get("volume") or {})
    structure = dict(layers.get("structure") or {})
    mtf = dict(operational.get("multi_timeframe") or layers.get("multi_timeframe") or {})
    blob = _layer_blob(layers)

    trend_dir = _direction(trend.get("direction") or trend.get("trend_direction"))
    momentum_dir = _direction(momentum.get("direction"))
    struct_dir = _direction(structure.get("direction") or structure.get("structure_direction"))
    mtf_dir = _direction(mtf.get("dominant_direction"))
    mtf_conflict = bool(mtf.get("conflict")) or _u(mtf.get("alignment")) == "CONFLICT"

    adx = _f(_indicator(trend, "adx", default=0.0))
    plus_di = _f(_indicator(trend, "plus_di", default=0.0))
    minus_di = _f(_indicator(trend, "minus_di", default=0.0))
    rsi = _f(_indicator(momentum, "rsi", default=50.0), 50.0)
    macd = _f(_indicator(momentum, "macd_histogram", "macd_hist", default=0.0))
    obv_dir = _direction(_indicator(volume, "obv_trend", "obv_direction", default=""))
    vol_ratio = _f(_indicator(volume, "volume_ratio", "relative_volume", default=1.0), 1.0)
    squeeze = bool(volatility.get("squeeze_on")) or _contains(blob, "SQUEEZE", "COMPRESSION", "COMPRESION")

    bullish = direction == "BULLISH"
    desired = "BULLISH" if bullish else "BEARISH"
    dmi_aligned = plus_di > minus_di + 1.5 if bullish else minus_di > plus_di + 1.5
    trend_aligned = trend_dir == desired and (adx >= 18 or dmi_aligned)
    mtf_aligned = mtf_dir == desired and not mtf_conflict
    mtf_opposite = mtf_dir not in {"NEUTRAL", desired} and not mtf_conflict

    div_blob = " ".join(
        str(x).upper()
        for x in list(momentum.get("divergences") or []) + list(momentum.get("hidden_divergences") or [])
    )
    div_aligned = (
        any(x in div_blob for x in ("BULL", "ALCIST")) if bullish
        else any(x in div_blob for x in ("BEAR", "BAJIST"))
    )
    momentum_aligned = (
        momentum_dir == desired
        or (bullish and macd > 0 and rsi >= 48)
        or ((not bullish) and macd < 0 and rsi <= 52)
        or div_aligned
    )

    whale = bool(
        volume.get("whale_buy_confirmed") or volume.get("whale_buy") or volume.get("iceberg_buy")
        if bullish
        else volume.get("whale_sell_confirmed") or volume.get("whale_sell") or volume.get("iceberg_sell")
    )
    volume_aligned = obv_dir == desired or whale
    if vol_ratio < 0.70 and not whale:
        volume_aligned = False

    sweeps = structure.get("liquidity_sweeps") or structure.get("stop_hunts") or []
    order_blocks = structure.get("order_blocks") or []
    fvgs = structure.get("fair_value_gaps") or structure.get("fvgs") or []

    has_sweep_any = bool(sweeps) or _contains(blob, "SWEEP", "STOP_HUNT", "BARRIDO")
    sweep_aligned = _dir_in_rows(sweeps, desired) or (has_sweep_any and struct_dir == desired)

    has_mss_any = _contains(blob, "MSS", "CHOCH", "CHANGE_OF_CHARACTER", "CAMBIO_ESTRUCTURA")
    # BOS is accepted only together with a directional structure anchor.
    has_bos = _contains(blob, "BOS", "BREAK_OF_STRUCTURE")
    mss_aligned = struct_dir == desired and (has_mss_any or has_bos)

    poi_aligned = (
        _dir_in_rows(order_blocks, desired)
        or _dir_in_rows(fvgs, desired)
        or (
            struct_dir == desired
            and (
                bool(order_blocks) or bool(fvgs)
                or _contains(blob, "POC", "HVN", "LVN", "FIB", "SUPPORT", "RESISTANCE", "VALUE_AREA")
            )
        )
    )
    structure_aligned = struct_dir == desired or poi_aligned or mss_aligned

    breakout = (
        _contains(blob, "BREAKOUT", "BREAKDOWN", "RUPTURA")
        or (has_bos and structure_aligned)
    )
    retest = _contains(blob, "RETEST", "PULLBACK", "RETROCESO", "RECLAIM")
    displacement = _contains(blob, "DISPLACEMENT", "IMPULSE", "IMPULSO", "VELA_FUERTE", "STRONG_CANDLE")

    # Range / reversion uses broad thresholds; they are not symbol optimized.
    ranging = (0 < adx <= 22) or _contains(blob, "RANGING", "RANGE", "BALANCE")
    extreme = rsi <= 38 if bullish else rsi >= 62
    support_resistance = (
        _contains(blob, "SUPPORT", "SOPORTE") if bullish
        else _contains(blob, "RESISTANCE", "RESISTENCIA")
    )
    mean_reversion_location = poi_aligned or support_resistance

    pullback_location = retest or poi_aligned
    breakout_retest = breakout and (retest or poi_aligned)
    expansion = breakout or displacement
    direction_anchor = structure_aligned or trend_aligned or mtf_aligned

    return {
        "trend": trend_aligned,
        "mtf": mtf_aligned,
        "mtf_conflict": mtf_conflict,
        "mtf_opposite": mtf_opposite,
        "momentum": momentum_aligned,
        "volume": volume_aligned,
        "structure": structure_aligned,
        "sweep": sweep_aligned,
        "mss": mss_aligned,
        "poi": poi_aligned,
        "pullback": pullback_location,
        "breakout": breakout,
        "breakout_retest": breakout_retest,
        "displacement": displacement,
        "squeeze": squeeze,
        "expansion": expansion,
        "range": ranging,
        "extreme": extreme,
        "mean_reversion_location": mean_reversion_location,
        "direction_anchor": direction_anchor,
        "adx": round(adx, 3),
        "rsi": round(rsi, 3),
        "volume_ratio": round(vol_ratio, 3),
        "trend_direction": trend_dir,
        "structure_direction": struct_dir,
        "mtf_direction": mtf_dir,
    }


def _contract_result(
    *, name: str, preferred_family: str, ev: Mapping[str, Any],
    core: Iterable[str], support: Iterable[str], min_support: int = 1,
    require_no_mtf_opposite: bool = True
) -> Dict[str, Any]:
    core = list(core)
    support = list(support)
    core_hits = [x for x in core if bool(ev.get(x))]
    support_hits = [x for x in support if bool(ev.get(x))]
    passed = (
        len(core_hits) == len(core)
        and len(support_hits) >= min_support
        and not bool(ev.get("mtf_conflict"))
        and (not require_no_mtf_opposite or not bool(ev.get("mtf_opposite")))
    )

    # Broad, monotonic scoring.  No symbol/TF constants are optimized here.
    quality = 62.0 + 6.0 * len(core_hits) + 3.0 * len(support_hits)
    if ev.get("mtf"):
        quality += 3.0
    if _f(ev.get("volume_ratio"), 1.0) >= 1.2:
        quality += 2.0
    quality = max(0.0, min(92.0, quality))
    return {
        "setup": name,
        "preferred_family": preferred_family,
        "passed": bool(passed),
        "quality": round(quality, 2),
        "core_required": core,
        "core_hits": core_hits,
        "support_pool": support,
        "support_hits": support_hits,
        "anti_overfit": "SETUP_ROLE_CONTRACT_NO_SYMBOL_OPTIMIZATION",
    }


def _evaluate_particular_side(
    layers: Mapping[str, Any], operational: Mapping[str, Any], direction: str
) -> Dict[str, Any]:
    ev = _live_evidence(layers, operational, direction)
    contracts = [
        _contract_result(
            name="SWEEP_REVERSAL",
            preferred_family="SWEEP_REVERSAL",
            ev=ev,
            core=("sweep", "mss", "structure"),
            support=("momentum", "poi", "volume", "mtf"),
            min_support=1,
        ),
        _contract_result(
            name="TREND_PULLBACK",
            preferred_family="TREND_PULLBACK",
            ev=ev,
            core=("trend", "mtf", "pullback"),
            support=("momentum", "volume", "poi"),
            min_support=1,
        ),
        _contract_result(
            name="BREAKOUT_RETEST",
            preferred_family="BREAKOUT_RETEST",
            ev=ev,
            core=("breakout_retest", "structure", "direction_anchor"),
            support=("displacement", "volume", "momentum", "mtf"),
            min_support=1,
        ),
        _contract_result(
            name="COMPRESSION_EXPANSION",
            preferred_family="BOLLINGER_SQUEEZE",
            ev=ev,
            core=("squeeze", "expansion", "direction_anchor"),
            support=("volume", "momentum", "mtf", "structure"),
            min_support=2,
        ),
        _contract_result(
            name="RANGE_MEAN_REVERSION",
            preferred_family="MEAN_REVERSION",
            ev=ev,
            core=("range", "extreme", "mean_reversion_location", "momentum"),
            support=("structure", "volume", "mtf"),
            min_support=1,
        ),
    ]
    eligible = [c for c in contracts if c["passed"]]
    eligible.sort(key=lambda x: (float(x["quality"]), len(x["support_hits"])), reverse=True)
    best = eligible[0] if eligible else None
    return {
        "direction": direction,
        "evidence": ev,
        "contracts": contracts,
        "best": best,
    }


def particular_setup_diagnostic(
    operational: Mapping[str, Any], *, layers: Mapping[str, Any],
    symbol: str, timeframe: str, system_type: str,
) -> Dict[str, Any]:
    """Evaluate setup-specific contracts without changing the candidate."""
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    long_side = _evaluate_particular_side(layers, operational, "BULLISH")
    short_side = _evaluate_particular_side(layers, operational, "BEARISH")
    candidates = []
    if long_side.get("best"):
        candidates.append(long_side["best"] | {"direction": "BULLISH"})
    if short_side.get("best"):
        candidates.append(short_side["best"] | {"direction": "BEARISH"})
    candidates.sort(key=lambda x: float(x.get("quality") or 0.0), reverse=True)
    winner = None
    ambiguous = False
    if candidates:
        if len(candidates) == 1:
            winner = candidates[0]
        else:
            margin = float(candidates[0]["quality"]) - float(candidates[1]["quality"])
            # A near tie means evidence is not particular enough.
            if margin >= 4.0:
                winner = candidates[0]
            else:
                ambiguous = True
    return {
        "version": VERSION,
        "market": market,
        "symbol": _u(symbol).replace("/", "-"),
        "timeframe": _u(timeframe),
        "winner": winner,
        "ambiguous": ambiguous,
        "long": long_side,
        "short": short_side,
        "authority": "PRE_CANDIDATE_TECHNICAL_CONTRACT",
        "greeks_used_for_direction": False,
        "can_bypass_safety": False,
        "can_bypass_execution": False,
    }


def _multiasset_strategy_from_live_layers(
    layers: Mapping[str, Any], symbol: str, timeframe: str, action: str
) -> Dict[str, Any]:
    """Build a real asset-class playbook BEFORE candidate_ready."""
    try:
        from multiasset_system import MULTIASSET_SYMBOLS, MULTIASSET_STRATEGY_BANK
    except Exception as exc:
        return {
            "id": "MULTIASSET_STRATEGY_UNAVAILABLE",
            "family": "NONE", "quality": 0.0,
            "regime_match": False, "volatility_match": False,
            "error": type(exc).__name__, "version": VERSION,
        }

    symbol_u = _u(symbol).replace("/", "-")
    meta = MULTIASSET_SYMBOLS.get(symbol_u) or {}
    asset_class = str(meta.get("asset_class") or "")
    families = list(MULTIASSET_STRATEGY_BANK.get(asset_class) or [])
    if not families or _u(action) not in _DIRECTIONAL:
        return {
            "id": "MULTIASSET_NO_DIRECTIONAL_PLAYBOOK",
            "family": "NONE", "quality": 0.0,
            "regime_match": True, "volatility_match": True,
            "eligible_strategy_count": len(families), "version": VERSION,
        }

    trend = layers.get("trend") or {}
    volatility = layers.get("volatility") or {}
    momentum = layers.get("momentum") or {}
    volume = layers.get("volume") or {}
    macro = layers.get("macro_context") or {}
    blob = _layer_blob(layers)

    adx = _f(_indicator(trend, "adx", default=0.0))
    atr_pct = _f(volatility.get("atr_pct") or volatility.get("atr_percent") or layers.get("atr_pct"))
    regime = "TRENDING" if adx >= 28 else ("RANGING" if 0 < adx < 18 else "MIXED")
    vol_regime = "HIGH" if atr_pct >= 3 else ("LOW" if 0 < atr_pct < 0.8 else "NORMAL")

    direction = "BULLISH" if _u(action) in {"LONG", "COMPRA_SPOT"} else "BEARISH"
    trend_dir = _direction(trend.get("direction") or trend.get("trend_direction"))
    trend_aligned = trend_dir == direction
    vol_ratio = _f(_indicator(volume, "volume_ratio", "relative_volume", default=1.0), 1.0)
    rsi = _f(_indicator(momentum, "rsi", default=50.0), 50.0)

    has_sweep = _contains(blob, "SWEEP", "LIQUIDITY_SWEEP", "STOP_HUNT", "BARRIDO")
    has_mss = _contains(blob, "MSS", "BOS", "CHANGE_OF_CHARACTER", "CHOCH", "CAMBIO_ESTRUCTURA")
    has_poi = _contains(blob, "ORDER_BLOCK", "FVG", "POC", "HVN", "LVN", "SUPPORT", "RESISTANCE", "FIB")
    has_displacement = _contains(blob, "DISPLACEMENT", "IMPULSE", "IMPULSO", "VELA_FUERTE")
    has_pullback = _contains(blob, "PULLBACK", "RETEST", "RETROCESO", "RECLAIM")
    has_breakout = _contains(blob, "BREAKOUT", "BREAKDOWN", "RUPTURA", "BOS")
    has_squeeze = bool(volatility.get("squeeze_on")) or _contains(blob, "SQUEEZE", "COMPRESSION", "COMPRESION")
    has_vwap = _contains(blob, "VWAP", "VALUE_AREA", "POC")
    has_mean_revert = (regime == "RANGING" and (rsi <= 35 or rsi >= 65 or _contains(blob, "BOLLINGER", "VALUE_AREA")))
    macro_available = bool(macro) and _u(macro.get("risk_level") or macro.get("current_risk_level")) not in {"", "UNKNOWN"}

    scored: Dict[str, Dict[str, Any]] = {}
    for family in families:
        score = 48.0
        reasons: List[str] = []
        if family in {"TREND_PULLBACK", "VWAP_SESSION_PULLBACK", "MACRO_TREND_CONFIRMATION", "RATES_USD_CONFIRMATION"}:
            if regime == "TRENDING" and trend_aligned:
                score += 14; reasons.append("trend_regime")
        elif family == "MEAN_REVERSION_SELECTIVE":
            if regime == "RANGING":
                score += 12; reasons.append("range_regime")
        elif family == "COMPRESSION_EXPANSION":
            if has_squeeze:
                score += 14; reasons.append("compression")
        else:
            if trend_aligned:
                score += 7; reasons.append("trend_alignment")

        if family == "SWEEP_MSS_POI":
            if has_sweep: score += 12; reasons.append("sweep")
            if has_mss: score += 12; reasons.append("mss_bos")
            if has_poi: score += 8; reasons.append("poi")
            if has_displacement: score += 6; reasons.append("displacement")
        elif family in {"TREND_PULLBACK", "VWAP_SESSION_PULLBACK", "VOLATILITY_RETEST", "ASIA_SESSION_RETEST"}:
            if has_pullback: score += 13; reasons.append("pullback_retest")
            if has_poi: score += 8; reasons.append("structural_zone")
            if family == "VWAP_SESSION_PULLBACK" and has_vwap:
                score += 9; reasons.append("vwap_value")
            if family == "VOLATILITY_RETEST" and vol_regime == "HIGH":
                score += 8; reasons.append("high_volatility")
        elif family == "BREAKOUT_RETEST":
            if has_breakout: score += 14; reasons.append("breakout")
            if has_pullback: score += 12; reasons.append("retest")
            if has_displacement: score += 6; reasons.append("displacement")
        elif family == "COMPRESSION_EXPANSION":
            if has_breakout or has_displacement:
                score += 12; reasons.append("expansion")
            if vol_ratio >= 1.1:
                score += 7; reasons.append("activity")
        elif family == "MEAN_REVERSION_SELECTIVE":
            if has_mean_revert:
                score += 16; reasons.append("mean_reversion_condition")
            if has_poi:
                score += 7; reasons.append("value_or_structure")
        elif family in {"POST_EVENT_CONFIRMATION", "POST_MACRO_CONFIRMATION", "MACRO_TREND_CONFIRMATION", "RATES_USD_CONFIRMATION"}:
            if macro_available:
                score += 9; reasons.append("macro_context")
            if trend_aligned:
                score += 8; reasons.append("price_confirmation")
            if has_pullback or has_breakout:
                score += 8; reasons.append("technical_confirmation")

        if vol_ratio >= 1.2:
            score += 4; reasons.append("relative_volume")
        score = max(0.0, min(100.0, score))
        scored[family] = {"quality": round(score, 2), "reasons": reasons[:8]}

    selected = max(scored, key=lambda k: scored[k]["quality"]) if scored else None
    quality = float((scored.get(selected) or {}).get("quality") or 0.0)
    return {
        "version": VERSION,
        "id": f"MULTI::{asset_class}::{selected or 'NONE'}::{_u(timeframe)}",
        "family": selected or "NONE",
        "quality": round(quality, 2),
        "confirmations": list((scored.get(selected) or {}).get("reasons") or []),
        "conflicts": [],
        "regime": regime,
        "volatility_regime": vol_regime,
        "regime_match": True,
        "volatility_match": True,
        "asset_class": asset_class,
        "eligible_strategy_count": len(families),
        "candidate_scores": {k: v["quality"] for k, v in scored.items()},
        "authority": "LIVE_CONTEXT_ROUTING_NO_DIRECTION_CREATION",
        "creates_direction": False,
        "never_bypass_safety": True,
    }


def _is_multiasset(symbol: str) -> bool:
    try:
        from multiasset_system import MULTIASSET_SYMBOLS
        return _u(symbol).replace("/", "-") in MULTIASSET_SYMBOLS
    except Exception:
        return False


def _official_cell(market: str, symbol: str, timeframe: str, action: str, fallback: bool = False) -> bool:
    try:
        from operational_intelligence import is_official_cell
        return bool(is_official_cell(market, symbol, timeframe, action))
    except Exception:
        return bool(fallback)


def _select_default_strategy(
    op: Mapping[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, market: str, action: str, preferred_family: str,
    is_multi: bool,
) -> Dict[str, Any]:
    if is_multi:
        return _multiasset_strategy_from_live_layers(layers, symbol, timeframe, action)
    try:
        from default_strategy_bank import select_strategy
        context = dict(op.get("context") or {})
        return select_strategy(
            action,
            str(context.get("regime") or "BALANCE"),
            str(context.get("volatility") or "NORMAL"),
            dict(op.get("indicator_groups") or {}),
            symbol=_u(symbol).replace("/", "-"),
            timeframe=_u(timeframe),
            market=market,
            preferred_family=str(preferred_family or ""),
        )
    except Exception as exc:
        return {
            "id": "NO_PLAYBOOK", "family": "NONE", "quality": 0.0,
            "confirmations": [], "conflicts": [],
            "regime_match": False, "volatility_match": False,
            "error": type(exc).__name__,
        }


def _particular_min_quality(market: str, risk_class: str, is_multi: bool) -> float:
    if market == "SPOT":
        return 78.0
    if is_multi:
        return 84.0
    rc = _u(risk_class)
    if rc == "HIGH":
        return 88.0
    if rc == "MEDIUM":
        return 85.0
    return 82.0


def _apply_particular_setup_fallback(
    op: Dict[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, market: str, is_multi: bool,
) -> Dict[str, Any]:
    diag = particular_setup_diagnostic(
        op, layers=layers, symbol=symbol, timeframe=timeframe, system_type=market
    )
    op["particular_setup_diagnostic"] = diag
    winner = diag.get("winner")
    if not winner or diag.get("ambiguous"):
        return op

    direction = str(winner.get("direction") or "NEUTRAL")
    action = _action(direction, market)
    if action not in _DIRECTIONAL:
        return op

    risk_class = str(op.get("risk_class") or (op.get("thesis") or {}).get("risk_class") or "")
    required_quality = _particular_min_quality(market, risk_class, is_multi)
    contract_quality = _f(winner.get("quality"))
    if contract_quality < required_quality:
        op["particular_setup_rejected_reason"] = "CONTRACT_QUALITY_BELOW_MARKET_PROFILE"
        return op

    strategy = _select_default_strategy(
        op,
        layers=layers,
        symbol=symbol,
        timeframe=timeframe,
        market=market,
        action=action,
        preferred_family=str(winner.get("preferred_family") or ""),
        is_multi=is_multi,
    )
    strategy_min = 78.0 if market == "FUTURES" else 70.0
    strategy_quality = _f(strategy.get("quality"))
    strategy_ok = bool(
        strategy_quality >= strategy_min
        and strategy.get("regime_match", True)
        and strategy.get("volatility_match", True)
    )
    if not strategy_ok:
        op["particular_setup_strategy"] = strategy
        op["particular_setup_rejected_reason"] = "STRATEGY_BANK_QUALITY_NOT_READY"
        return op

    base_thesis = dict(op.get("thesis") or {})
    mtf_usable = not bool((op.get("multi_timeframe") or {}).get("conflict"))
    macro = layers.get("macro_context") or {}
    macro_risk = _u(base_thesis.get("macro_risk") or macro.get("risk_level") or macro.get("risk"))
    official = _official_cell(
        market, symbol, timeframe, action,
        fallback=bool(op.get("official_cell")),
    )
    ready = bool(
        official
        and mtf_usable
        and macro_risk != "CRITICAL"
        and contract_quality >= required_quality
        and strategy_ok
    )
    if not ready:
        op["particular_setup_rejected_reason"] = (
            "UNOFFICIAL_CELL" if not official
            else "MTF_CONFLICT" if not mtf_usable
            else "MACRO_CRITICAL" if macro_risk == "CRITICAL"
            else "NOT_READY"
        )
        return op

    evidence = (
        diag.get("long", {}).get("evidence", {})
        if direction == "BULLISH"
        else diag.get("short", {}).get("evidence", {})
    )
    support_names = list(dict.fromkeys(
        list(winner.get("core_hits") or []) + list(winner.get("support_hits") or [])
    ))

    patched_thesis = dict(base_thesis)
    patched_thesis.update({
        "base_direction_before_particular_contract": base_thesis.get("direction"),
        "base_action_before_particular_contract": base_thesis.get("action"),
        "direction": direction,
        "action": action,
        "quality": round(contract_quality, 2),
        "independent_support_families": support_names,
        "particular_setup_contract": {
            "setup": winner.get("setup"),
            "preferred_family": winner.get("preferred_family"),
            "core_required": list(winner.get("core_required") or []),
            "core_hits": list(winner.get("core_hits") or []),
            "support_hits": list(winner.get("support_hits") or []),
            "required_quality": required_quality,
            "market_profile": risk_class or ("MULTIASSET" if is_multi else market),
            "evidence_snapshot": {
                k: evidence.get(k)
                for k in (
                    "adx", "rsi", "volume_ratio", "trend_direction",
                    "structure_direction", "mtf_direction"
                )
            },
            "anti_overfit": "SETUP_ROLE_CONTRACT_NO_SYMBOL_OPTIMIZATION",
        },
        "anti_overfit_rule": "CORRELATED_INDICATORS_STAY_GROUPED_BY_ROLE",
    })

    op["thesis"] = patched_thesis
    op["default_strategy"] = strategy
    op["candidate_source"] = "PARTICULAR_SETUP+STRATEGY"
    op["candidate_action"] = action
    op["candidate_ready"] = True
    op["official_cell"] = True
    op["selected_specialist_source"] = "PARTICULAR_SETUP"
    op["mtf_usable"] = True
    op["particular_setup_promoted"] = True
    op["particular_setup_family"] = winner.get("setup")
    op["particular_setup_quality"] = round(contract_quality, 2)
    op["particular_strategy_quality"] = round(strategy_quality, 2)
    op["never_bypass_safety"] = True

    decision_evidence = dict(op.get("decision_evidence") or {})
    decision_evidence.update({
        "candidate_source": op["candidate_source"],
        "particular_setup_family": winner.get("setup"),
        "particular_setup_core": list(winner.get("core_hits") or []),
        "particular_setup_support": list(winner.get("support_hits") or []),
        "greeks_used_for_direction": False,
    })
    op["decision_evidence"] = decision_evidence
    return op


def reconcile_operational_candidate(
    operational: Mapping[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, system_type: str
) -> Dict[str, Any]:
    """Repair routing and add setup-specific fallback without lowering final gates."""
    op = deepcopy(dict(operational or {}))
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    is_multi = _is_multiasset(symbol) if market == "FUTURES" else False

    op["pipeline_integrity_version"] = VERSION
    op["pipeline_generation"] = PIPELINE_GENERATION

    thesis = dict(op.get("thesis") or {})
    thesis_action = _u(thesis.get("action"))
    thesis_direction = _u(thesis.get("direction"))

    # Old OOS/Research is counter-evidence, not a pre-candidate deletion.
    if op.get("research_blocks_selected_action"):
        op["research_counter_evidence"] = {
            "state": str((op.get("research_candidates") or {}).get(thesis_action, {}).get("state") or "NEGATIVE_RESEARCH"),
            "former_hard_block": True,
            "authority": "COUNTER_EVIDENCE_UNTIL_VERSION_MATCHED_FORWARD",
        }
        op["research_blocks_selected_action"] = False
        op["stale_research_softened"] = True

    # Preserve an already valid candidate. We still attach the diagnostic so
    # ReviewTrader can compare generic vs particular setup coverage.
    if bool(op.get("candidate_ready")) and _u(op.get("candidate_action")) in _DIRECTIONAL:
        try:
            op["particular_setup_diagnostic"] = particular_setup_diagnostic(
                op, layers=layers, symbol=symbol, timeframe=timeframe, system_type=market
            )
        except Exception as exc:
            op["particular_setup_diagnostic_error"] = type(exc).__name__
        return op

    # 17.5.10.1 compatibility path for directional thesis.
    if thesis_action in _DIRECTIONAL and thesis_direction in {"BULLISH", "BEARISH"}:
        if is_multi:
            strategy = _multiasset_strategy_from_live_layers(layers, symbol, timeframe, thesis_action)
            op["default_strategy"] = strategy
            quality = _f(strategy.get("quality"))
            thesis_quality = _f(thesis.get("quality"))
            min_quality = 78.0
            autonomous_min = _f(op.get("autonomous_thesis_min_quality"), 82.0)
            support = len(thesis.get("independent_support_families") or [])
            required_support = int(thesis.get("required_independent_families") or 4)
            mtf_usable = bool(op.get("mtf_usable", not bool((op.get("multi_timeframe") or {}).get("conflict"))))
            official = _official_cell(market, symbol, timeframe, thesis_action, fallback=bool(op.get("official_cell", True)))
            macro_critical = _u(thesis.get("macro_risk")) == "CRITICAL"
            strategy_ok = bool(
                quality >= min_quality
                and strategy.get("regime_match", True)
                and strategy.get("volatility_match", True)
            )
            thesis_ok = thesis_quality >= min_quality
            autonomous_ok = bool(
                thesis_quality >= autonomous_min
                and support >= required_support
                and mtf_usable
            )
            source = "THESIS+MULTIASSET_STRATEGY" if thesis_ok and strategy_ok else (
                "THESIS_AUTONOMOUS" if autonomous_ok else "NONE"
            )
            ready = bool(official and source != "NONE" and mtf_usable and not macro_critical)
            op["candidate_source"] = source
            op["candidate_action"] = thesis_action if ready else "NO_OPERAR"
            op["candidate_ready"] = ready
            op["multiasset_strategy_pre_candidate"] = True
            op["multiasset_strategy_quality"] = quality
            op["multiasset_strategy_threshold_unchanged"] = min_quality
        elif op.get("stale_research_softened"):
            strategy = dict(op.get("default_strategy") or {})
            quality = _f(strategy.get("quality"))
            thesis_quality = _f(thesis.get("quality"))
            min_quality = 78.0 if market == "FUTURES" else 70.0
            autonomous_min = _f(op.get("autonomous_thesis_min_quality"), 82.0 if market == "FUTURES" else 76.0)
            support = len(thesis.get("independent_support_families") or [])
            required_support = int(thesis.get("required_independent_families") or (4 if market == "FUTURES" else 3))
            mtf_usable = bool(op.get("mtf_usable", not bool((op.get("multi_timeframe") or {}).get("conflict"))))
            official = _official_cell(market, symbol, timeframe, thesis_action, fallback=bool(op.get("official_cell", True)))
            macro_critical = _u(thesis.get("macro_risk")) == "CRITICAL"
            strategy_ok = bool(
                quality >= min_quality
                and strategy.get("regime_match", True)
                and strategy.get("volatility_match", True)
            )
            learned_live_ok = bool(
                str(op.get("selected_specialist_source") or "").upper() == "LEARNED"
                and support >= (3 if market == "FUTURES" else 2)
                and mtf_usable
            )
            autonomous_ok = bool(
                thesis_quality >= autonomous_min
                and support >= required_support
                and mtf_usable
            )
            source = "NONE"
            if learned_live_ok and strategy_ok:
                source = "LEARNED+DEFAULT"
            elif learned_live_ok:
                source = "LEARNED+LIVE"
            elif thesis_quality >= min_quality and strategy_ok:
                source = "THESIS+DEFAULT"
            elif autonomous_ok:
                source = "THESIS_AUTONOMOUS"
            ready = bool(official and source != "NONE" and mtf_usable and not macro_critical)
            op["candidate_source"] = source
            op["candidate_action"] = thesis_action if ready else "NO_OPERAR"
            op["candidate_ready"] = ready
            op["research_recompute_same_thresholds"] = True

    # If the generic route is still not ready, try the setup-specific contract.
    if not bool(op.get("candidate_ready")):
        op = _apply_particular_setup_fallback(
            op, layers=layers, symbol=symbol, timeframe=timeframe,
            market=market, is_multi=is_multi,
        )
    return op


def _parse_dt(value: Any):
    try:
        raw = str(value or "").strip().replace("Z", "+00:00")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def profitability_hard_block_authority(route: Mapping[str, Any]) -> Dict[str, Any]:
    """Generation-aware hard-block authority."""
    route = dict(route or {})
    state = _u(route.get("state"))
    released = _parse_dt(RELEASED_AT_UTC)

    if not route.get("block_new_signal"):
        return {"allowed": False, "reason": "NO_BLOCK_REQUESTED", "state": state}

    if state == "NEGATIVE_EDGE_VETO":
        return {
            "allowed": False,
            "reason": "OLD_OOS_IS_COUNTER_EVIDENCE_NOT_VERSION_MATCHED_VETO",
            "state": state,
        }

    if state in {"ALPHA_DECAY_VETO", "SHADOW_DIVERGED_RETEST"}:
        evidence = route.get("best_diverged") or {}
        updated = _parse_dt(evidence.get("shadow_updated_at"))
        generation = str(evidence.get("pipeline_generation") or evidence.get("generation") or "")
        version_match = generation == PIPELINE_GENERATION
        forward_new = bool(updated and released and updated >= released)
        recent_n = int(evidence.get("recent8_n") or 0)
        if (version_match or forward_new) and recent_n >= 8:
            return {
                "allowed": True,
                "reason": "FORWARD_ALPHA_DECAY_VERSION_COMPATIBLE",
                "state": state,
            }
        return {
            "allowed": False,
            "reason": "ALPHA_DECAY_EVIDENCE_NOT_CURRENT_GENERATION",
            "state": state,
        }

    return {"allowed": False, "reason": "UNSCOPED_RESEARCH_BLOCK_SOFTENED", "state": state}


def stamp_pipeline_generation(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    result["pipeline_generation"] = PIPELINE_GENERATION
    levels = dict(result.get("levels") or {})
    levels["pipeline_generation"] = PIPELINE_GENERATION
    result["levels"] = levels
    context = dict(result.get("context") or {})
    learning = dict(context.get("learning") or {})
    learning["pipeline_generation"] = PIPELINE_GENERATION
    learning["pipeline_integrity_version"] = VERSION
    # Explicitly tell Review/Research that Greeks cannot be a direction label.
    learning["greeks_direction_authority"] = "NONE_SHADOW_CONTEXT_ONLY"
    context["learning"] = learning
    result["context"] = context
    return result
