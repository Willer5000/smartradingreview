"""RC9.2 — Operational Intelligence Closure.

Pure/deterministic trading intelligence shared by Main decision flow.
It does not call exchanges, databases, AI providers or mutate Safety/leverage.
Its job is to convert the already-calculated market layers into one canonical
context, one multi-timeframe thesis and one auditable default specialist.

Design rules:
- Market thesis first; internal specialists are supporting/contradicting evidence.
- Correlated indicators count as one evidence family, not many votes.
- Missing higher-timeframe data is explicit; alignment is never invented.
- A Default Specialist is technical fallback, never statistical alpha.
- The layer may preserve or downgrade a directional proposal. It may only create
  a default directional candidate when evidence is strong, the cell is supported,
  the default strategy matches context and no hard block is active.
- Safety/publication gates remain final authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "COMMIT17_4_ADAPTIVE_REASONING_ORCHESTRATOR_V2_SIGNAL_EXECUTION_DECOUPLED"

DIRECTIONAL_ACTIONS = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}
NON_DIRECTIONAL_ACTIONS = {"ESPERAR", "PRECAUCION", "NO_OPERAR"}

SPOT_SYMBOLS = ("BTC-USDT", "PAXG-USDT", "PAXG-BTC")
from futures_universe import (
    all_symbols as _futures_all_symbols,
    allowed_timeframes as _futures_allowed_timeframes,
    risk_class_for as futures_risk_class_for,
    exit_profile_for as futures_exit_profile_for,
)

FUTURES_SYMBOLS = tuple(_futures_all_symbols())
SPOT_EXECUTION_TFS = ("4H", "12H", "1D", "1W")

# Commit 17.3.1 — Multi-Asset reuses the Futures execution engine but is not
# part of the crypto Futures universe in futures_universe.py.  The thesis layer
# must therefore recognize these contracts as governed operational cells instead
# of rejecting them as ``official_cell=False`` before the Multi-Asset router can
# annotate the result.  Keep this list deliberately small and identical to the
# production Multi-Asset universe; it is a routing contract, not alpha.
MULTIASSET_SYMBOLS = {
    "SPY-USDT", "QQQ-USDT", "CL-USDT", "NATGAS-USDT",
    "COPPER-USDT", "XAG-USDT", "KSTR-USDT",
}
MULTIASSET_EXECUTION_TFS = {"1H", "4H", "1D"}

# Commit 17.4 — Multi-Asset is a first-class market segment, not a crypto
# Futures alias.  These are routing semantics only; no symbol-specific alpha is
# encoded here.  Strategy/volatility thresholds are shared by asset class.
MULTIASSET_ASSET_CLASS = {
    "SPY-USDT": "US_INDEX", "QQQ-USDT": "US_INDEX",
    "CL-USDT": "ENERGY", "NATGAS-USDT": "ENERGY",
    "COPPER-USDT": "INDUSTRIAL_METAL", "XAG-USDT": "PRECIOUS_METAL",
    "KSTR-USDT": "CHINA_INDEX",
}

_MULTI_MTF_ROLE_PROFILES: Dict[str, Dict[str, Sequence[str]]] = {
    "1H": {"context": ("1D",), "structure": ("4H",), "setup": ("1H",), "timing": ("1H",)},
    "4H": {"context": ("1D",), "structure": ("4H",), "setup": ("4H",), "timing": ("1H",)},
    "1D": {"context": ("1D",), "structure": ("1D",), "setup": ("1D",), "timing": ("4H",)},
}

_MULTI_FAMILIES = {
    "US_INDEX": ("MOMENTUM_CONTINUATION", "TREND_PULLBACK", "BREAKOUT_RETEST", "COMPRESSION_EXPANSION", "STRUCTURE_REVERSAL", "MEAN_REVERSION"),
    "ENERGY": ("MOMENTUM_CONTINUATION", "BREAKOUT_RETEST", "COMPRESSION_EXPANSION", "STRUCTURE_REVERSAL", "TREND_PULLBACK", "MEAN_REVERSION"),
    "INDUSTRIAL_METAL": ("TREND_PULLBACK", "BREAKOUT_RETEST", "COMPRESSION_EXPANSION", "MOMENTUM_CONTINUATION", "STRUCTURE_REVERSAL", "MEAN_REVERSION"),
    "PRECIOUS_METAL": ("TREND_PULLBACK", "MEAN_REVERSION", "BREAKOUT_RETEST", "COMPRESSION_EXPANSION", "MOMENTUM_CONTINUATION", "STRUCTURE_REVERSAL"),
    "CHINA_INDEX": ("BREAKOUT_RETEST", "COMPRESSION_EXPANSION", "TREND_PULLBACK", "MOMENTUM_CONTINUATION", "STRUCTURE_REVERSAL", "MEAN_REVERSION"),
}


def market_segment_for(market: Any, symbol: Any) -> str:
    if _u(market) == "SPOT":
        return "SPOT"
    if _u(symbol) in MULTIASSET_SYMBOLS:
        return "MULTIASSET"
    return "FUTURES"


def market_objective_for(market: Any, symbol: Any) -> str:
    segment = market_segment_for(market, symbol)
    sym = _u(symbol)
    if segment == "SPOT":
        if sym == "BTC-USDT": return "PORTFOLIO_SNOWBALL_ACCUMULATE_SATOSHIS_AND_USDT"
        if sym == "PAXG-USDT": return "PORTFOLIO_SNOWBALL_ACCUMULATE_GOLD_AND_USDT"
        if sym == "PAXG-BTC": return "PORTFOLIO_SNOWBALL_ROTATE_BTC_GOLD_RELATIVE_UNITS"
        return "PORTFOLIO_SNOWBALL"
    if segment == "MULTIASSET":
        return "RAPID_CLASS_AWARE_EXPECTANCY_R_WITH_TECHNICAL_INVALIDATION"
    return "RAPID_CRYPTO_EXPECTANCY_R_WITH_TECHNICAL_INVALIDATION"


def timeframe_reasoning_profile(market: Any, symbol: Any, timeframe: Any) -> Dict[str, Any]:
    segment = market_segment_for(market, symbol)
    tf = _u(timeframe)
    rc = futures_risk_class_for(symbol) if segment == "FUTURES" else segment
    # Structural thresholds by horizon/class. They are deliberately coarse and
    # not fitted per symbol, preventing parameter proliferation/overfitting.
    if segment == "SPOT":
        adx_strong = {"4H":23.0,"12H":22.0,"1D":21.0,"1W":20.0}.get(tf,22.0)
        adx_weak = 16.0
        tempo = "ACCUMULATION_SWING"
    elif segment == "MULTIASSET":
        cls = MULTIASSET_ASSET_CLASS.get(_u(symbol), "MULTIASSET")
        base = {"US_INDEX":21.0,"ENERGY":23.0,"INDUSTRIAL_METAL":22.0,"PRECIOUS_METAL":21.0,"CHINA_INDEX":23.0}.get(cls,22.0)
        adx_strong = base + (1.0 if tf == "1H" else -1.0 if tf == "1D" else 0.0)
        adx_weak = max(15.0, adx_strong - 7.0)
        tempo = "FAST_INTRADAY" if tf == "1H" else "TACTICAL" if tf == "4H" else "SWING_CONTEXT"
    else:
        base = {"30M":24.0,"1H":23.0,"2H":22.0,"4H":21.0,"12H":20.0,"1D":19.0}.get(tf,22.0)
        if rc == "HIGH": base += 2.0
        elif rc == "MEDIUM": base += 1.0
        adx_strong = base
        adx_weak = max(16.0, base - 7.0)
        tempo = "VERY_FAST" if rc == "HIGH" else "FAST" if rc == "MEDIUM" else "CONTROLLED_FAST"
    return {
        "segment": segment, "timeframe": tf, "risk_class": rc, "tempo": tempo,
        "adx_strong": round(adx_strong,1), "adx_weak": round(adx_weak,1),
        "objective": market_objective_for(market, symbol),
        "policy": "HORIZON_AND_CLASS_CONTEXT_NOT_SYMBOL_FITTED",
    }


def is_multiasset_cell(market: Any, symbol: Any, timeframe: Any, action: Any) -> bool:
    return bool(
        _u(market) == "FUTURES"
        and _u(symbol) in MULTIASSET_SYMBOLS
        and _u(timeframe) in MULTIASSET_EXECUTION_TFS
        and canonical_action(action, "FUTURES") in {"LONG", "SHORT"}
    )


def _u(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def canonical_action(value: Any, market: str = "") -> str:
    raw = _u(value).replace(" ", "_")
    if raw in {"CAUTION", "PRECAUCIÓN", "PRECAUCION"}:
        return "PRECAUCION"
    if raw in {"WAIT", "WAITING"}:
        return "ESPERAR"
    if raw in {"NO_TRADE", "NO-TRADE", "NONE", "NEUTRAL", ""}:
        return "NO_OPERAR"
    market = _u(market)
    if market == "FUTURES":
        return {"COMPRA_SPOT": "LONG", "VENTA_SPOT": "SHORT", "BUY": "LONG", "SELL": "SHORT"}.get(raw, raw)
    if market == "SPOT":
        return {"LONG": "COMPRA_SPOT", "SHORT": "VENTA_SPOT", "BUY": "COMPRA_SPOT", "SELL": "VENTA_SPOT"}.get(raw, raw)
    return raw


def action_direction(action: Any) -> str:
    raw = canonical_action(action)
    if raw in {"LONG", "COMPRA_SPOT"}:
        return "BULLISH"
    if raw in {"SHORT", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def direction_action(direction: Any, market: str) -> str:
    d = _u(direction)
    m = _u(market)
    if d == "BULLISH":
        return "LONG" if m == "FUTURES" else "COMPRA_SPOT"
    if d == "BEARISH":
        return "SHORT" if m == "FUTURES" else "VENTA_SPOT"
    return "NO_OPERAR"


def canonical_regime(value: Any) -> str:
    raw = _u(value).replace(" ", "_")
    mapping = {
        "TRENDING_BULL": "TREND_UP", "BULL_TREND": "TREND_UP", "BULLISH": "TREND_UP",
        "TRENDING_BEAR": "TREND_DOWN", "BEAR_TREND": "TREND_DOWN", "BEARISH": "TREND_DOWN",
        "RANGING": "BALANCE", "RANGE": "BALANCE", "SIDEWAYS": "BALANCE", "LATERAL": "BALANCE",
        "HIGH_VOLATILITY": "VOLATILITY_SHOCK", "VOLATILITY_SHOCK": "VOLATILITY_SHOCK",
        "TREND_UP": "TREND_UP", "TREND_DOWN": "TREND_DOWN", "BALANCE": "BALANCE", "TRANSITION": "TRANSITION", "VOLATILITY_SHOCK": "VOLATILITY_SHOCK",
    }
    return mapping.get(raw, raw if raw else "BALANCE")


def volatility_reasoning(volatility: Mapping[str, Any] | None, regime_raw: Any = None, *, market: Any = "", symbol: Any = "", timeframe: Any = "") -> Dict[str, Any]:
    """Classify volatility primarily from relative state already in memory.

    No new candles/API calls are introduced. Percentiles/ratios are used when
    available; absolute ATR/BB thresholds are only a conservative fallback.
    """
    v = dict(volatility or {})
    profile = timeframe_reasoning_profile(market, symbol, timeframe)
    segment = profile.get("segment")
    ftm = _u(v.get("ftm_state") or v.get("state") or v.get("regime"))
    squeeze = bool(v.get("squeeze_on")) or int(_f(v.get("squeeze_length"))) > 0
    atr_pct = _f(v.get("atr_pct"))
    width = _f(v.get("bb_width"))
    width_prev = _f(v.get("bb_width_prev"))
    vol_ratio = _f(v.get("volatility_ratio"), 1.0)
    atr_p = _f(v.get("atr_percentile") or v.get("volatility_percentile"), -1.0)
    width_p = _f(v.get("bb_width_percentile"), -1.0)
    if 0 <= atr_p <= 1: atr_p *= 100.0
    if 0 <= width_p <= 1: width_p *= 100.0
    width_growth = (width / width_prev) if width_prev > 0 and width >= 0 else 1.0
    raw_regime = _u(regime_raw)

    state = "NORMAL"; basis = []
    if squeeze:
        state = "COMPRESSION"; basis.append("SQUEEZE_ACTIVE")
    elif raw_regime in {"HIGH_VOLATILITY", "VOLATILITY_SHOCK"} or ftm in {"EXTREME", "SHOCK"}:
        state = "SHOCK"; basis.append("SHOCK_STATE")
    elif ftm in {"HIGH", "EXPANSION", "VOLATILE", "HIGH_EXPANSION"}:
        state = "EXPANSION"; basis.append("RELATIVE_STATE_EXPANSION")
    elif atr_p >= 85 or width_p >= 85 or vol_ratio >= 1.35 or (vol_ratio >= 1.15 and width_growth >= 1.10):
        state = "EXPANSION"; basis.append("RELATIVE_EXPANSION")
    elif (0 <= atr_p <= 20) or (0 <= width_p <= 20) or (vol_ratio > 0 and vol_ratio <= 0.72 and width_growth <= 1.0):
        state = "LOW"; basis.append("RELATIVE_LOW_VOLATILITY")
    else:
        # Fallback only when richer relative evidence is absent. The bands differ
        # by market/horizon, not by individual symbol outcome history.
        tf = _u(timeframe)
        if segment == "SPOT":
            exp_atr = {"4H":3.2,"12H":4.0,"1D":5.0,"1W":8.0}.get(tf,4.0)
            low_atr = {"4H":0.65,"12H":0.9,"1D":1.2,"1W":1.8}.get(tf,0.8)
        elif segment == "MULTIASSET":
            cls = MULTIASSET_ASSET_CLASS.get(_u(symbol), "MULTIASSET")
            base = {"US_INDEX":1.5,"ENERGY":3.0,"INDUSTRIAL_METAL":2.2,"PRECIOUS_METAL":2.0,"CHINA_INDEX":2.5}.get(cls,2.2)
            factor = {"1H":0.65,"4H":1.0,"1D":1.55}.get(tf,1.0)
            exp_atr = base * factor; low_atr = exp_atr * 0.24
        else:
            rc = futures_risk_class_for(symbol)
            base = {"CORE1":2.2,"CORE2":2.6,"MEDIUM":3.1,"HIGH":3.8}.get(rc,2.8)
            factor = {"30M":0.55,"1H":0.70,"2H":0.85,"4H":1.0,"12H":1.35,"1D":1.65}.get(tf,1.0)
            exp_atr = base * factor; low_atr = exp_atr * 0.24
        if atr_pct > 0 and atr_pct >= exp_atr:
            state = "EXPANSION"; basis.append("CONTEXTUAL_ATR_FALLBACK")
        elif atr_pct > 0 and atr_pct <= low_atr and (width <= 0 or width_growth <= 1.0):
            state = "LOW"; basis.append("CONTEXTUAL_LOW_ATR_FALLBACK")
        else:
            basis.append("NORMAL_RELATIVE_STATE")
    return {
        "state": state, "basis": basis, "segment": segment, "timeframe": _u(timeframe),
        "atr_pct": round(atr_pct,4), "volatility_ratio": round(vol_ratio,4),
        "bb_width": round(width,4), "bb_width_growth": round(width_growth,4),
        "atr_percentile": None if atr_p < 0 else round(atr_p,2),
        "bb_width_percentile": None if width_p < 0 else round(width_p,2),
        "resource_policy": "REUSE_EXISTING_FEATURES_NO_EXTRA_FETCH",
    }


def canonical_volatility(volatility: Mapping[str, Any] | None, regime_raw: Any = None, *, market: Any = "", symbol: Any = "", timeframe: Any = "") -> str:
    return str(volatility_reasoning(volatility, regime_raw, market=market, symbol=symbol, timeframe=timeframe).get("state") or "NORMAL")


def official_universe_cells() -> List[Tuple[str, str, str, str]]:
    cells: List[Tuple[str, str, str, str]] = []
    for symbol in SPOT_SYMBOLS:
        for tf in SPOT_EXECUTION_TFS:
            for action in ("COMPRA_SPOT", "VENTA_SPOT"):
                cells.append(("SPOT", symbol, tf, action))
    for symbol in FUTURES_SYMBOLS:
        for tf in _futures_allowed_timeframes(symbol):
            for action in ("LONG", "SHORT"):
                cells.append(("FUTURES", symbol, _u(tf), action))
    return cells


_OFFICIAL_CELL_SET = set(official_universe_cells())


def official_universe_audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "cells": len(_OFFICIAL_CELL_SET),
        "expected_cells": 150,
        "ok": len(_OFFICIAL_CELL_SET) == 150,
        "spot_cells": sum(1 for c in _OFFICIAL_CELL_SET if c[0] == "SPOT"),
        "futures_cells": sum(1 for c in _OFFICIAL_CELL_SET if c[0] == "FUTURES"),
    }


def is_official_cell(market: Any, symbol: Any, timeframe: Any, action: Any) -> bool:
    cell = (_u(market), _u(symbol), _u(timeframe), canonical_action(action, _u(market)))
    return cell in _OFFICIAL_CELL_SET


# Timeframes used only as context may exist even when they are not action cells.
_MTF_ROLE_PROFILES: Dict[str, Dict[str, Dict[str, Sequence[str]]]] = {
    "SPOT": {
        "4H": {"context": ("1W", "1D"), "structure": ("12H",), "setup": ("4H",), "timing": ("4H",)},
        "12H": {"context": ("1W",), "structure": ("1D",), "setup": ("12H",), "timing": ("4H",)},
        "1D": {"context": ("1W",), "structure": ("1D",), "setup": ("1D",), "timing": ("12H",)},
        "1W": {"context": ("1W",), "structure": ("1W",), "setup": ("1W",), "timing": ("1D", "12H")},
    },
    "FUTURES": {
        "30M": {"context": ("4H",), "structure": ("2H",), "setup": ("1H",), "timing": ("30M",)},
        "1H": {"context": ("4H",), "structure": ("2H",), "setup": ("1H",), "timing": ("30M",)},
        "2H": {"context": ("4H",), "structure": ("4H",), "setup": ("2H",), "timing": ("1H",)},
        "4H": {"context": ("1D", "12H"), "structure": ("4H",), "setup": ("4H",), "timing": ("2H",)},
        "12H": {"context": ("1D",), "structure": ("12H",), "setup": ("12H",), "timing": ("4H",)},
        "1D": {"context": ("1D",), "structure": ("1D",), "setup": ("1D",), "timing": ("12H", "4H")},
        "1W": {"context": ("1W",), "structure": ("1W",), "setup": ("1W",), "timing": ("1D", "12H")},
    },
}


_RISK_MTF_PROFILES: Dict[str, Dict[str, Dict[str, Sequence[str]]]] = {
    "CORE2": {
        "12H": {"context": ("12H",), "structure": ("12H",), "setup": ("12H",), "timing": ("4H",)},
    },
    "MEDIUM": {
        "30M": {"context": ("4H",), "structure": ("2H",), "setup": ("1H",), "timing": ("30M",)},
        "1H": {"context": ("4H",), "structure": ("2H",), "setup": ("1H",), "timing": ("30M",)},
        "2H": {"context": ("4H",), "structure": ("4H",), "setup": ("2H",), "timing": ("1H",)},
        "4H": {"context": ("4H",), "structure": ("4H",), "setup": ("4H",), "timing": ("2H",)},
    },
    "HIGH": {
        "30M": {"context": ("2H",), "structure": ("1H",), "setup": ("30M",), "timing": ("30M",)},
        "1H": {"context": ("2H",), "structure": ("2H",), "setup": ("1H",), "timing": ("30M",)},
        "2H": {"context": ("2H",), "structure": ("2H",), "setup": ("2H",), "timing": ("1H",)},
    },
}

def _mtf_profile_for(market: Any, timeframe: Any, symbol: Any = "") -> Dict[str, Sequence[str]]:
    market_u, timeframe_u = _u(market), _u(timeframe)
    if market_u == "FUTURES" and _u(symbol) in MULTIASSET_SYMBOLS:
        return dict(_MULTI_MTF_ROLE_PROFILES.get(timeframe_u, {"setup": (timeframe_u,), "timing": (timeframe_u,)}))
    if market_u == "FUTURES":
        rc = futures_risk_class_for(symbol)
        if timeframe_u in _RISK_MTF_PROFILES.get(rc, {}):
            return dict(_RISK_MTF_PROFILES[rc][timeframe_u])
    return dict(_MTF_ROLE_PROFILES.get(market_u, {}).get(timeframe_u, {"setup": (timeframe_u,), "timing": (timeframe_u,)}))


def mtf_required_timeframes(market: Any, timeframe: Any, symbol: Any = "") -> List[str]:
    roles = _mtf_profile_for(market, timeframe, symbol)
    out: List[str] = []
    for values in roles.values():
        for tf in values:
            if tf not in out:
                out.append(tf)
    return out


def _norm_direction(value: Any) -> str:
    raw = _u(value)
    if raw in {"BULLISH", "LONG", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if raw in {"BEARISH", "SHORT", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _analysis_snapshot(tf: str, analysis: Mapping[str, Any] | None, *, current_layers: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Compact MTF snapshot including higher-timeframe anomalous-volume context."""
    if current_layers is not None:
        trend = dict(current_layers.get("trend") or {})
        momentum = dict(current_layers.get("momentum") or {})
        structure = dict(current_layers.get("structure") or {})
        volume = dict(current_layers.get("volume") or {})
        return {
            "available": True,
            "timeframe": _u(tf),
            "direction": _norm_direction(trend.get("direction")),
            "adx": round(_f(trend.get("adx")), 2),
            "momentum": _norm_direction(momentum.get("direction")),
            "structure": _norm_direction(structure.get("direction") or structure.get("structure_direction")),
            "whale_buy_confirmed": bool(volume.get("whale_buy_confirmed") or volume.get("whale_buy")),
            "whale_sell_confirmed": bool(volume.get("whale_sell_confirmed") or volume.get("whale_sell")),
            "whale_extended_buy": bool(volume.get("whale_extended_buy")),
            "whale_extended_sell": bool(volume.get("whale_extended_sell")),
            "whale_event_pending": bool(volume.get("whale_event_pending")),
            "whale_event_age_bars": volume.get("whale_event_age_bars"),
            "whale_signal_strength": _f(volume.get("whale_signal_strength")),
            "closed_candle": True,
            "source": "CURRENT",
        }
    row = dict(analysis or {})
    if not row or not row.get("success"):
        return {"available": False, "timeframe": _u(tf)}
    trend = dict(row.get("trend") or {})
    momentum = dict(row.get("momentum") or {})
    structure = dict(row.get("structure") or {})
    volume = dict(row.get("volume") or {})
    # Some compact Guardian snapshots carry the volume layer under `layers`.
    if not volume and isinstance(row.get("layers"), Mapping):
        volume = dict((row.get("layers") or {}).get("volume") or {})
    closed = row.get("source_candle_closed")
    if closed is None:
        closed = str(row.get("analysis_mode") or "").upper() in {"CLOSED_CANDLE", ""}
    return {
        "available": True,
        "timeframe": _u(tf),
        "direction": _norm_direction(trend.get("direction")),
        "adx": round(_f(trend.get("adx")), 2),
        "momentum": _norm_direction(momentum.get("direction")),
        "structure": _norm_direction(structure.get("direction") or structure.get("structure_direction")),
        "whale_buy_confirmed": bool(volume.get("whale_buy_confirmed") or volume.get("whale_buy")),
        "whale_sell_confirmed": bool(volume.get("whale_sell_confirmed") or volume.get("whale_sell")),
        "whale_extended_buy": bool(volume.get("whale_extended_buy")),
        "whale_extended_sell": bool(volume.get("whale_extended_sell")),
        "whale_event_pending": bool(volume.get("whale_event_pending")),
        "whale_event_age_bars": volume.get("whale_event_age_bars"),
        "whale_signal_strength": _f(volume.get("whale_signal_strength")),
        "closed_candle": bool(closed),
        "synthetic": row.get("market_data_is_synthetic"),
        "source": "CACHE",
    }

def build_multiframe_context(*, market: Any, timeframe: Any, current_layers: Mapping[str, Any], peer_analyses: Mapping[str, Mapping[str, Any]] | None = None, symbol: Any = "") -> Dict[str, Any]:
    market = _u(market)
    timeframe = _u(timeframe)
    profile = _mtf_profile_for(market, timeframe, symbol)
    peers = { _u(k): v for k, v in dict(peer_analyses or {}).items() }
    role_rows: Dict[str, Any] = {}
    all_dirs: List[str] = []
    missing: List[str] = []

    for role, tfs in profile.items():
        snapshots: List[Dict[str, Any]] = []
        for tf in tfs:
            tfn = _u(tf)
            if tfn == timeframe:
                snap = _analysis_snapshot(tfn, None, current_layers=current_layers)
            else:
                snap = _analysis_snapshot(tfn, peers.get(tfn))
            if market == "FUTURES" and tfn != timeframe and snap.get("available"):
                if snap.get("synthetic") is True or snap.get("closed_candle") is False:
                    snap = {"available": False, "timeframe": tfn, "reason": "NEEDS_REAL_CLOSED_CANDLE"}
            snapshots.append(snap)
            if not snap.get("available"):
                missing.append(tfn)
        dirs = [s.get("direction") for s in snapshots if s.get("available") and s.get("direction") in {"BULLISH", "BEARISH"}]
        if not dirs:
            role_dir = "NEUTRAL"
        elif len(set(dirs)) == 1:
            role_dir = dirs[0]
        else:
            role_dir = "CONFLICT"
        if role_dir in {"BULLISH", "BEARISH"}:
            all_dirs.append(role_dir)
        role_rows[role] = {"direction": role_dir, "timeframes": list(tfs), "snapshots": snapshots}

    context_dir = (role_rows.get("context") or {}).get("direction", "NEUTRAL")
    structure_dir = (role_rows.get("structure") or {}).get("direction", "NEUTRAL")
    setup_dir = (role_rows.get("setup") or {}).get("direction", "NEUTRAL")
    timing_dir = (role_rows.get("timing") or {}).get("direction", "NEUTRAL")
    conflict = any((role_rows.get(r) or {}).get("direction") == "CONFLICT" for r in role_rows)
    if context_dir in {"BULLISH", "BEARISH"} and setup_dir in {"BULLISH", "BEARISH"} and context_dir != setup_dir:
        conflict = True
    if structure_dir in {"BULLISH", "BEARISH"} and setup_dir in {"BULLISH", "BEARISH"} and structure_dir != setup_dir:
        conflict = True

    # One timeframe is one independent observation. The same 4H snapshot may
    # serve structure and setup, but it never counts twice as "alignment".
    unique_snapshots: Dict[str, Dict[str, Any]] = {}
    for row in role_rows.values():
        for snap in row.get("snapshots", []):
            if snap.get("available"):
                unique_snapshots.setdefault(str(snap.get("timeframe") or ""), snap)
    unique_dirs = [
        s.get("direction") for s in unique_snapshots.values()
        if s.get("direction") in {"BULLISH", "BEARISH"}
    ]
    bulls = sum(1 for d in unique_dirs if d == "BULLISH")
    bears = sum(1 for d in unique_dirs if d == "BEARISH")
    dominant = "BULLISH" if bulls > bears else "BEARISH" if bears > bulls else "NEUTRAL"
    available_roles = sum(1 for row in role_rows.values() if any(s.get("available") for s in row.get("snapshots", [])))
    unique_timeframes = len(unique_snapshots)
    if conflict:
        alignment = "CONFLICT"
    elif unique_timeframes < 2:
        alignment = "INCOMPLETE"
    elif dominant in {"BULLISH", "BEARISH"} and max(bulls, bears) >= 3:
        alignment = "ALIGNED"
    elif dominant in {"BULLISH", "BEARISH"}:
        alignment = "SUPPORTIVE"
    else:
        alignment = "MIXED"

    # Commit 9.4 — higher-TF anomalous-volume context. A 12H/1D/1W event
    # may support lower-TF timing for up to seven source bars, but never creates
    # a trade by itself. Confirmed reactions outrank pending events.
    whale_rows: List[Dict[str, Any]] = []
    for snap in unique_snapshots.values():
        tf_name = _u(snap.get("timeframe"))
        if tf_name not in {"12H", "1D", "1W"}:
            continue
        age = snap.get("whale_event_age_bars")
        try:
            age_ok = age is not None and 0 <= int(age) <= 7
        except Exception:
            age_ok = False
        buy_confirmed = bool(snap.get("whale_buy_confirmed")) and age_ok
        sell_confirmed = bool(snap.get("whale_sell_confirmed")) and age_ok
        pending = bool(snap.get("whale_event_pending")) and age_ok
        extended_buy = bool(snap.get("whale_extended_buy")) and age_ok
        extended_sell = bool(snap.get("whale_extended_sell")) and age_ok
        if buy_confirmed or sell_confirmed or pending or extended_buy or extended_sell:
            whale_rows.append({
                "timeframe": tf_name,
                "age_bars": int(age) if age_ok else None,
                "buy_confirmed": buy_confirmed,
                "sell_confirmed": sell_confirmed,
                "pending_buy": bool(pending and extended_buy and not sell_confirmed),
                "pending_sell": bool(pending and extended_sell and not buy_confirmed),
                "strength": round(_f(snap.get("whale_signal_strength")), 2),
            })
    whale_rows.sort(
        key=lambda r: (
            1 if (r.get("buy_confirmed") or r.get("sell_confirmed")) else 0,
            _f(r.get("strength")),
            -int(r.get("age_bars") or 0),
        ),
        reverse=True,
    )
    whale_best = whale_rows[0] if whale_rows else {}
    whale_context = {
        "active": bool(whale_best),
        "source_timeframe": whale_best.get("timeframe"),
        "age_bars": whale_best.get("age_bars"),
        "buy_confirmed": bool(whale_best.get("buy_confirmed")),
        "sell_confirmed": bool(whale_best.get("sell_confirmed")),
        "pending_buy": bool(whale_best.get("pending_buy")),
        "pending_sell": bool(whale_best.get("pending_sell")),
        "strength": _f(whale_best.get("strength")),
        "observations": whale_rows[:4],
        "policy": "ANOMALOUS_VOLUME_REACTION_CONTEXT_MAX_7_SOURCE_BARS",
    }

    return {
        "version": VERSION,
        "market": market,
        "timeframe": timeframe,
        "roles": role_rows,
        "dominant_direction": dominant,
        "alignment": alignment,
        "conflict": bool(conflict),
        "available_roles": available_roles,
        "available_unique_timeframes": unique_timeframes,
        "missing_timeframes": sorted(set(missing)),
        "complete": unique_timeframes >= 3 and not conflict,
        "public_summary": _mtf_public_summary(role_rows, alignment),
        "whale_context": whale_context,
    }


def _mtf_public_summary(role_rows: Mapping[str, Any], alignment: str) -> str:
    parts: List[str] = []
    names = {"context": "contexto", "structure": "estructura", "setup": "señal", "timing": "entrada"}
    seen = set()
    context_available = False
    for role in ("context", "structure", "setup", "timing"):
        row = role_rows.get(role) or {}
        d = row.get("direction")
        available_tfs = [
            str(s.get("timeframe")) for s in (row.get("snapshots") or [])
            if s.get("available")
        ]
        if role == "context" and available_tfs:
            context_available = True
        if d in {"BULLISH", "BEARISH", "CONFLICT"} and available_tfs:
            human = "alcista" if d == "BULLISH" else "bajista" if d == "BEARISH" else "en conflicto"
            tf_text = "/".join(dict.fromkeys(available_tfs))
            key = (tf_text, human)
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"{names[role]} {tf_text} {human}")
    if not parts:
        return "No hay suficientes temporalidades reales disponibles para confirmar el contexto multitemporal."
    if alignment in {"ALIGNED", "SUPPORTIVE"} and context_available:
        prefix = "Alineación multitemporal"
    elif alignment == "CONFLICT":
        prefix = "Conflicto multitemporal"
    else:
        prefix = "Lectura multitemporal parcial"
    return prefix + ": " + "; ".join(parts[:4]) + "."


def _indicator_value(container: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in container and container.get(key) is not None:
            return container.get(key)
    indicators = container.get("indicators") if isinstance(container, Mapping) else None
    if isinstance(indicators, Mapping):
        for key in keys:
            if indicators.get(key) is not None:
                return indicators.get(key)
    return default


def build_independent_thesis(*, layers: Mapping[str, Any], mtf_context: Mapping[str, Any], market: Any, symbol: Any = "", timeframe: Any = "") -> Dict[str, Any]:
    trend = dict(layers.get("trend") or {})
    momentum = dict(layers.get("momentum") or {})
    volume = dict(layers.get("volume") or {})
    structure = dict(layers.get("structure") or {})
    volatility = dict(layers.get("volatility") or {})
    macro = dict(layers.get("macro_context") or {})
    liquidation = dict(layers.get("liquidation") or {})

    families: Dict[str, Dict[str, Any]] = {}

    def add_family(name: str, score: float, detail: str, weight: float = 1.0) -> None:
        score = max(-1.0, min(1.0, float(score)))
        families[name] = {"score": round(score, 3), "weight": float(weight), "detail": str(detail)[:220]}

    # Trend family: ADX/DMI/EMA are one family, never multiple independent votes.
    trend_dir = _norm_direction(trend.get("direction"))
    adx = _f(trend.get("adx"))
    plus_di = _f(trend.get("plus_di")); minus_di = _f(trend.get("minus_di"))
    tf_profile = timeframe_reasoning_profile(market, symbol, timeframe)
    adx_strong = _f(tf_profile.get("adx_strong"), 25.0)
    adx_weak = _f(tf_profile.get("adx_weak"), 18.0)
    trend_score = 0.0
    if trend_dir == "BULLISH": trend_score = 0.55
    elif trend_dir == "BEARISH": trend_score = -0.55
    if adx >= adx_strong:
        if plus_di > minus_di + 2: trend_score = max(trend_score, 0.85)
        elif minus_di > plus_di + 2: trend_score = min(trend_score, -0.85)
    elif adx < adx_weak:
        trend_score *= 0.45
    add_family("trend", trend_score, f"ADX {adx:.1f} (fuerte≥{adx_strong:.1f}); +DI {plus_di:.1f}; -DI {minus_di:.1f}", 1.0)

    # Structure/liquidity family.
    struct_dir = _norm_direction(structure.get("direction") or structure.get("structure_direction"))
    ob = bool(structure.get("order_blocks") or structure.get("order_blocks_active"))
    fvg = bool(structure.get("fair_value_gaps") or structure.get("fvgs"))
    sweeps = bool(structure.get("liquidity_sweeps") or structure.get("stop_hunts"))
    struct_score = 0.65 if struct_dir == "BULLISH" else -0.65 if struct_dir == "BEARISH" else 0.0
    if (ob or fvg or sweeps) and struct_score:
        struct_score = 0.85 if struct_score > 0 else -0.85
    add_family("structure", struct_score, f"estructura {struct_dir.lower()}; zona institucional={'sí' if (ob or fvg) else 'no'}; barrido={'sí' if sweeps else 'no'}", 1.25)

    # Momentum family: RSI/MACD/divergences count once.
    mom_dir = _norm_direction(momentum.get("direction"))
    rsi = _f(_indicator_value(momentum, "rsi", default=50), 50)
    macd_hist = _f(_indicator_value(momentum, "macd_histogram", "macd_hist", default=0), 0)
    regular_divs = momentum.get("divergences") or []
    hidden_divs = momentum.get("hidden_divergences") or []
    mom_score = 0.55 if mom_dir == "BULLISH" else -0.55 if mom_dir == "BEARISH" else 0.0
    if macd_hist > 0 and rsi >= 50: mom_score = max(mom_score, 0.7)
    if macd_hist < 0 and rsi <= 50: mom_score = min(mom_score, -0.7)
    # Divergence is used as a modifier, not an extra independent vote.
    div_text = "sin divergencia dominante"
    div_blob = " ".join(str(x).lower() for x in list(regular_divs) + list(hidden_divs))
    if "bull" in div_blob or "alcist" in div_blob:
        mom_score = max(mom_score, 0.75); div_text = "divergencia alcista"
    if "bear" in div_blob or "bajist" in div_blob:
        mom_score = min(mom_score, -0.75); div_text = "divergencia bajista"
    add_family("momentum", mom_score, f"RSI {rsi:.1f}; MACD hist {macd_hist:.4f}; {div_text}", 1.0)

    # Volume/flow family.
    ratio = _f(_indicator_value(volume, "volume_ratio", default=1.0), 1.0)
    obv = _norm_direction(_indicator_value(volume, "obv_trend", "obv_direction", default=""))
    whale_buy = bool(volume.get("whale_buy_confirmed") or volume.get("whale_buy") or volume.get("iceberg_buy"))
    whale_sell = bool(volume.get("whale_sell_confirmed") or volume.get("whale_sell") or volume.get("iceberg_sell"))
    vol_score = 0.0
    if obv == "BULLISH" or whale_buy: vol_score = 0.65
    if obv == "BEARISH" or whale_sell: vol_score = -0.65
    if ratio < 0.75: vol_score *= 0.55
    elif ratio >= 1.2 and vol_score: vol_score = 0.85 if vol_score > 0 else -0.85
    add_family("volume", vol_score, f"volumen {ratio:.2f}x; OBV {obv.lower() if obv!='NEUTRAL' else 'neutral'}", 0.9)

    # Commit 17.3 — volatility expansion is a separate *bounded* evidence family.
    # It closes the accidental HIGH-risk 5-of-5 dependency on structure without
    # lowering the required family count.  It cannot create direction by itself:
    # only an expanding envelope with price clearly on one side contributes.
    vol_ratio = _f(volatility.get("volatility_ratio"), 1.0)
    bb_width = _f(volatility.get("bb_width"), 0.0)
    bb_width_prev = _f(volatility.get("bb_width_prev"), 0.0)
    bb_position = _f(volatility.get("bb_position"), 0.5)
    squeeze_on = bool(volatility.get("squeeze_on"))
    operable = bool(volatility.get("operability", True))
    width_expanding = bool(
        (vol_ratio >= 1.15)
        or (bb_width_prev > 0 and bb_width >= bb_width_prev * 1.10)
    )
    expansion_score = 0.0
    if operable and width_expanding and not squeeze_on:
        if bb_position >= 0.72:
            expansion_score = 0.55 if vol_ratio < 1.50 else 0.65
        elif bb_position <= 0.28:
            expansion_score = -0.55 if vol_ratio < 1.50 else -0.65
    add_family(
        "expansion", expansion_score,
        f"expansión vol {vol_ratio:.2f}x; BB pos {bb_position:.2f}; ancho {bb_width:.2f}/{bb_width_prev:.2f}",
        0.75,
    )

    # Multi-timeframe is one independent family.
    mtf_dir = _norm_direction(mtf_context.get("dominant_direction"))
    mtf_alignment = _u(mtf_context.get("alignment"))
    mtf_score = 0.0
    if mtf_alignment == "CONFLICT":
        mtf_score = 0.0
    elif mtf_dir == "BULLISH": mtf_score = 0.8 if mtf_alignment == "ALIGNED" else 0.55
    elif mtf_dir == "BEARISH": mtf_score = -0.8 if mtf_alignment == "ALIGNED" else -0.55
    add_family("multiframe", mtf_score, str(mtf_context.get("public_summary") or "multiframe incompleto"), 1.15)

    # Macro: risk context, never a sole direction maker.
    macro_bias = _norm_direction(
        macro.get("bias") or macro.get("directional_bias")
        or macro.get("direction") or macro.get("market_bias")
    )
    macro_risk = _u(macro.get("risk_level") or macro.get("risk"))
    macro_score = 0.3 if macro_bias == "BULLISH" else -0.3 if macro_bias == "BEARISH" else 0.0
    add_family("macro", macro_score, f"sesgo {macro_bias.lower()}; riesgo {macro_risk or 'desconocido'}", 0.45)

    # Liquidation map only modifies the location/risk thesis. Direction is used
    # only when the input explicitly carries a dominant side.
    liq_bias = _norm_direction(liquidation.get("direction") or liquidation.get("bias"))
    liq_score = 0.35 if liq_bias == "BULLISH" else -0.35 if liq_bias == "BEARISH" else 0.0
    add_family("liquidity", liq_score, f"mapa de liquidaciones {liq_bias.lower() if liq_bias!='NEUTRAL' else 'sin sesgo direccional fiable'}", 0.55)

    long_score = sum(max(0.0, row["score"]) * row["weight"] for row in families.values())
    short_score = sum(max(0.0, -row["score"]) * row["weight"] for row in families.values())
    long_families = [k for k,v in families.items() if v["score"] >= 0.45]
    short_families = [k for k,v in families.items() if v["score"] <= -0.45]
    market_u = _u(market)
    segment = market_segment_for(market_u, symbol)
    if segment == "SPOT":
        risk_class = "SPOT"; min_families = 3; margin_required = 0.90
    elif segment == "MULTIASSET":
        asset_class = MULTIASSET_ASSET_CLASS.get(_u(symbol), "MULTIASSET")
        risk_class = f"MULTI_{asset_class}"
        min_families = 4
        margin_required = {"US_INDEX":1.15,"ENERGY":1.30,"INDUSTRIAL_METAL":1.22,"PRECIOUS_METAL":1.18,"CHINA_INDEX":1.30}.get(asset_class,1.22)
    else:
        risk_class = futures_risk_class_for(symbol)
        min_families = 5 if risk_class == "HIGH" else 4
        margin_required = 1.45 if risk_class == "HIGH" else 1.25 if risk_class == "MEDIUM" else 1.15
    # Anti-overfitting differentiation is structural by market/class/horizon,
    # never fitted to an individual symbol's recent wins.
    margin = abs(long_score - short_score)
    direction = "NEUTRAL"
    active = long_families if long_score > short_score else short_families
    if len(active) >= min_families and margin >= margin_required:
        direction = "BULLISH" if long_score > short_score else "BEARISH"
    if bool(mtf_context.get("conflict")) and market_u == "FUTURES":
        # A conflict does not erase the thesis, but it cannot be called strong.
        if margin < max(2.0, margin_required + 0.7):
            direction = "NEUTRAL"

    quality = min(100.0, 45.0 + 9.0 * len(active) + 7.0 * min(2.5, margin)) if direction != "NEUTRAL" else min(69.0, 35.0 + 7.0 * max(len(long_families), len(short_families)))
    return {
        "version": VERSION,
        "direction": direction,
        "action": direction_action(direction, _u(market)),
        "quality": round(quality, 2),
        "long_score": round(long_score, 3),
        "short_score": round(short_score, 3),
        "margin": round(margin, 3),
        "independent_support_families": list(active),
        "long_families": long_families,
        "short_families": short_families,
        "families": families,
        "mtf_conflict": bool(mtf_context.get("conflict")),
        "macro_risk": macro_risk,
        "risk_class": risk_class,
        "timeframe": _u(timeframe),
        "required_independent_families": min_families,
        "required_direction_margin": round(margin_required, 3),
        "anti_overfit_rule": "ONE_REPRESENTATIVE_EFFECT_PER_CORRELATED_FAMILY; HIGH_KEEPS_5_SUPPORTS_FROM_A_BROADER_INDEPENDENT_SET",
    }


_POSITIVE_RESEARCH_STATES = {
    "SHADOW_READY", "OOS_VALIDATED", "OOS_PLUS_SHADOW", "CHAMPION", "VALIDATED",
}
_NEGATIVE_RESEARCH_STATES = {
    "REJECTED_OOS", "NEGATIVE_OOS", "SHADOW_DIVERGED", "ALPHA_DECAY",
    "DEGRADED", "REVOKED",
}


def _research_state(row: Mapping[str, Any] | None) -> str:
    return _u((row or {}).get("state"))


def _research_positive(row: Mapping[str, Any] | None) -> bool:
    return _research_state(row) in _POSITIVE_RESEARCH_STATES and not bool((row or {}).get("recycle_required"))


def _research_negative(row: Mapping[str, Any] | None) -> bool:
    return _research_state(row) in _NEGATIVE_RESEARCH_STATES or bool((row or {}).get("recycle_required"))


def _research_reasoning(row: Mapping[str, Any] | None) -> Dict[str, Any]:
    row = dict(row or {})
    state = _research_state(row)
    penalty = max(0.0, _f(row.get("penalty_score")))
    hard = False; reason = "ADVISORY_OR_NO_NEGATIVE_EVIDENCE"
    best_neg = dict(row.get("best_negative") or {})
    best_pos = dict(row.get("best_positive") or {})
    if state in {"NEGATIVE_OOS", "REJECTED_OOS"}:
        n = int(_f(best_neg.get("oos_n")))
        exp = _f(best_neg.get("oos_exp_r"), 0.0)
        hard = bool(n >= 20 and exp <= -0.15)
        reason = "ROBUST_NEGATIVE_OOS" if hard else "NEGATIVE_OOS_INSUFFICIENT_FOR_HARD_BLOCK"
    elif state in {"SHADOW_DIVERGED", "ALPHA_DECAY", "DEGRADED", "REVOKED"} or bool(row.get("recycle_required")):
        shadow_n = int(_f(best_pos.get("shadow_n")))
        recent_n = int(_f(best_pos.get("recent8_n")))
        recent_exp = _f(best_pos.get("recent8_expectancy_r"), 0.0)
        hard = bool((shadow_n >= 12 and _f(best_pos.get("shadow_exp_r"), 0.0) < 0) or (recent_n >= 8 and recent_exp < 0))
        reason = "ROBUST_LIVE_ALPHA_DECAY" if hard else "DECAY_WARNING_NOT_YET_HARD_BLOCK"
    quality_extra = min(5.0, penalty / 8.0) if not hard else 0.0
    margin_extra = min(0.35, penalty / 100.0) if not hard else 0.0
    return {"state":state,"hard_block":hard,"reason":reason,"penalty_score":round(penalty,2),"quality_extra":round(quality_extra,2),"margin_extra":round(margin_extra,3)}


def _macro_reasoning(macro: Mapping[str, Any] | None, *, segment: str) -> Dict[str, Any]:
    m = dict(macro or {})
    risk = _u(m.get("risk_level") or m.get("current_risk_level") or m.get("risk"))
    posture = _u(m.get("futures_posture") or m.get("posture"))
    gate = _u(m.get("gate"))
    hours = _f(m.get("next_event_hours") or ((m.get("next_high_impact_event") or {}).get("hours_until")), 9999.0)
    hard = bool(posture == "NO_NEW_TRADES" or gate == "WAIT_EVENT")
    quality_extra = 0.0; margin_extra = 0.0
    session = _u(m.get("market_session"))
    asset_class = _u(m.get("asset_class"))
    reasons: List[str] = []
    if not hard:
        if risk == "CRITICAL":
            quality_extra += 4.0; margin_extra += 0.30; reasons.append("ELEVATED_MACRO_RISK")
        elif risk == "HIGH":
            quality_extra += 2.0; margin_extra += 0.15; reasons.append("ELEVATED_MACRO_RISK")
        # Multi-Asset synthetic contracts can trade outside the underlying's
        # main session.  Off-hours are not a veto, but require cleaner evidence
        # because spreads/liquidity/price discovery can differ from cash hours.
        if _u(segment) == "MULTIASSET" and ("OFFHOURS" in session or "CLOSED" in session):
            quality_extra += 1.5; margin_extra += 0.10; reasons.append("UNDERLYING_OFFHOURS")
    return {
        "risk":risk or "UNKNOWN", "posture":posture or "NORMAL", "gate":gate or "NORMAL",
        "market_session":session or None, "asset_class":asset_class or None,
        "next_event_hours":None if hours >= 9990 else round(hours,2),
        "hard_block_new_entry":hard,
        "reason":"IMMINENT_EVENT_RISK" if hard else "+".join(reasons) if reasons else "NORMAL",
        "quality_extra":round(quality_extra,2), "margin_extra":round(margin_extra,3),
        "policy":"MACRO_AND_SESSION_MODIFY_REQUIREMENTS;_ONLY_IMMINENT_UNMODELLED_EVENT_BLOCKS_NEW_ENTRY",
    }


def _multiasset_strategy_reasoning(*, selected_action: str, regime: str, vol_state: str, thesis: Mapping[str, Any], symbol: Any, timeframe: Any, macro_reasoning: Mapping[str, Any]) -> Dict[str, Any]:
    cls = MULTIASSET_ASSET_CLASS.get(_u(symbol), "MULTIASSET")
    eligible = list(_MULTI_FAMILIES.get(cls) or _MULTI_FAMILIES.get("US_INDEX") or ())
    families = dict((thesis or {}).get("families") or {})
    desired = action_direction(selected_action)
    sign = 1.0 if desired == "BULLISH" else -1.0
    scores: Dict[str, float] = {}
    for fam in eligible:
        score = 50.0
        if fam in {"MOMENTUM_CONTINUATION","TREND_PULLBACK"}:
            score += 12 if regime in {"TREND_UP","TREND_DOWN"} else -5
            score += 10 if sign * _f((families.get("trend") or {}).get("score")) >= 0.45 else -5
            score += 8 if sign * _f((families.get("momentum") or {}).get("score")) >= 0.45 else 0
        elif fam == "COMPRESSION_EXPANSION":
            score += 14 if vol_state in {"COMPRESSION","EXPANSION"} else -6
            score += 10 if sign * _f((families.get("expansion") or {}).get("score")) >= 0.45 else 0
        elif fam == "STRUCTURE_REVERSAL":
            score += 13 if regime == "TRANSITION" else 0
            score += 12 if sign * _f((families.get("structure") or {}).get("score")) >= 0.45 else -4
            score += 6 if sign * _f((families.get("momentum") or {}).get("score")) >= 0.45 else 0
        elif fam == "BREAKOUT_RETEST":
            score += 8 if regime in {"TREND_UP","TREND_DOWN","TRANSITION"} else 0
            score += 10 if sign * _f((families.get("structure") or {}).get("score")) >= 0.45 else 0
            score += 6 if sign * _f((families.get("volume") or {}).get("score")) >= 0.45 else 0
        elif fam == "MEAN_REVERSION":
            score += 14 if regime == "BALANCE" else -8
            score += 6 if vol_state in {"LOW","NORMAL"} else -4
        if cls == "ENERGY" and fam in {"MOMENTUM_CONTINUATION","COMPRESSION_EXPANSION","BREAKOUT_RETEST"}: score += 3
        if cls == "US_INDEX" and fam in {"TREND_PULLBACK","MEAN_REVERSION","BREAKOUT_RETEST"}: score += 2
        if cls == "PRECIOUS_METAL" and fam in {"TREND_PULLBACK","MEAN_REVERSION","STRUCTURE_REVERSAL"}: score += 2
        if bool(macro_reasoning.get("hard_block_new_entry")): score -= 30
        scores[fam] = max(0.0, min(100.0, score))
    family = max(scores, key=scores.get) if scores else "NONE"
    quality = scores.get(family, 0.0)
    return {
        "id":f"MULTI_{cls}_{_u(timeframe)}_{family}", "family":family, "quality":round(quality,2),
        "confirmations":[f"asset_class={cls}",f"regime={regime}",f"volatility={vol_state}"], "conflicts":[],
        "regime_match":quality >= 64.0, "volatility_match":quality >= 64.0,
        "asset_class":cls, "eligible_strategy_count":len(eligible), "candidate_scores":scores,
        "specialization_key":f"MULTI|{cls}|{_u(symbol)}|{_u(timeframe)}|{selected_action}|{family}",
        "learning_cell":f"MULTI::{cls}::{_u(symbol)}::{_u(timeframe)}::{regime}::{vol_state}::{family}",
        "authority":"ADAPTIVE_MULTI_CONTEXT_ROUTER_V2",
    }


def _mtf_execution_gate(
    *, mtf_context: Mapping[str, Any], thesis: Mapping[str, Any],
    strategy: Mapping[str, Any], selected_action: Any, market: str,
    risk_class: str, timeframe: Any, is_multiasset: bool = False,
) -> Tuple[bool, str]:
    """Context-aware MTF gate without weakening the normal alignment rule.

    A blanket ``not conflict`` veto prevents the very first technically mature
    reversal/impulse from ever becoming executable: by definition the faster
    frames turn before the higher context frame.  Commit 17.3 added families for
    those states, but the old blanket gate still discarded them.

    Exception policy is intentionally narrow:
    - only crypto Futures CORE/MEDIUM, 30M/1H/2H; HIGH remains strict;
    - only transition-capable families;
    - structure + setup + timing roles must already agree with the candidate;
    - higher ``context`` may be the sole disagreement;
    - at least the normal number of independent *local* families must agree and
      the thesis margin must be stronger than the normal directional threshold.
    Multi-Asset remains aligned-MTF only in this hotfix; its bug is the governed
    cell routing, not a request to relax its context gate.
    """
    if not bool((mtf_context or {}).get("conflict")):
        return True, "MTF_ALIGNED_OR_NON_CONFLICT"
    if _u(market) != "FUTURES" or is_multiasset:
        return False, "MTF_CONFLICT"
    if _u(risk_class) == "HIGH" or _u(timeframe) not in {"30M", "1H", "2H"}:
        return False, "MTF_CONFLICT_STRICT_PROFILE"

    family = _u((strategy or {}).get("family"))
    if family not in {"STRUCTURE_REVERSAL", "MOMENTUM_CONTINUATION", "COMPRESSION_EXPANSION"}:
        return False, "MTF_CONFLICT_FAMILY_NOT_TRANSITION_CAPABLE"

    desired = action_direction(selected_action)
    if desired not in {"BULLISH", "BEARISH"}:
        return False, "MTF_CONFLICT_NO_DIRECTION"

    roles = dict((mtf_context or {}).get("roles") or {})
    role_dirs = {name: _u((roles.get(name) or {}).get("direction")) for name in ("context", "structure", "setup", "timing")}

    # Internal disagreement inside structure/setup/timing is never waived.
    for name in ("structure", "setup", "timing"):
        if role_dirs.get(name) == "CONFLICT":
            return False, f"MTF_{name.upper()}_INTERNAL_CONFLICT"
        if role_dirs.get(name) != desired:
            return False, f"MTF_{name.upper()}_NOT_ALIGNED"

    # The exception exists only for a lagging/opposite higher context. If context
    # already agrees, the conflict originated elsewhere and should remain blocked.
    context_dir = role_dirs.get("context")
    if context_dir == desired:
        return False, "MTF_CONFLICT_NOT_CONTEXT_ONLY"

    families = dict((thesis or {}).get("families") or {})
    threshold = 0.45 if desired == "BULLISH" else -0.45
    local_names = ("trend", "structure", "momentum", "volume", "expansion")
    if desired == "BULLISH":
        local_support = [n for n in local_names if _f((families.get(n) or {}).get("score")) >= threshold]
    else:
        local_support = [n for n in local_names if _f((families.get(n) or {}).get("score")) <= threshold]
    required = int((thesis or {}).get("required_independent_families") or 4)
    margin = _f((thesis or {}).get("margin"))
    margin_required = _f((thesis or {}).get("required_direction_margin"), 1.15)
    if len(local_support) < required:
        return False, "MTF_TRANSITION_LOCAL_SUPPORT_INSUFFICIENT"
    if margin < margin_required + 0.60:
        return False, "MTF_TRANSITION_MARGIN_INSUFFICIENT"
    return True, "MTF_CONTEXT_LAG_TRANSITION_CONFIRMED"


def prepare_operational_intelligence(
    *, layers: Mapping[str, Any], symbol: Any, timeframe: Any, system_type: Any,
    mtf_context: Mapping[str, Any], research_candidates: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Adaptive pre-Safety orchestrator: objective -> context -> thesis -> strategy.

    It never calls networks/DB/LLMs and never bypasses the downstream
    Entry/SL/TP/Safety/Publication gates. Hard blocks are reserved for evidence
    that is genuinely non-modelled (imminent event) or statistically robust.
    """
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    segment = market_segment_for(market, symbol)
    is_multiasset = segment == "MULTIASSET"
    raw_regime = (layers.get("market_regime") or {}).get("regime")
    regime = canonical_regime(raw_regime)
    vol_reason = volatility_reasoning(layers.get("volatility") or {}, raw_regime, market=market, symbol=symbol, timeframe=timeframe)
    vol_state = str(vol_reason.get("state") or "NORMAL")
    tf_profile = timeframe_reasoning_profile(market, symbol, timeframe)
    thesis = build_independent_thesis(layers=layers, mtf_context=mtf_context, market=market, symbol=symbol, timeframe=timeframe)
    research_map = {canonical_action(key, market): dict(value or {}) for key, value in dict(research_candidates or {}).items()}

    try:
        from contingency_strategy_engine import _indicator_groups
        indicator_groups = _indicator_groups(dict(layers))
        indicator_groups["multi_timeframe"] = dict(mtf_context or {})
    except Exception as exc:
        indicator_groups = {"multi_timeframe": dict(mtf_context or {}), "normalization_error": str(exc)[:160]}

    bullish_action = "LONG" if market == "FUTURES" else "COMPRA_SPOT"
    bearish_action = "SHORT" if market == "FUTURES" else "VENTA_SPOT"
    long_support = len(thesis.get("long_families") or [])
    short_support = len(thesis.get("short_families") or [])
    learned_support_min = 3 if market == "FUTURES" else 2
    selected_action = thesis.get("action") or "NO_OPERAR"
    selected_prior: Dict[str, Any] = {}
    specialist_source = "THESIS"

    if selected_action not in DIRECTIONAL_ACTIONS:
        candidates: List[Tuple[float, str, Dict[str, Any]]] = []
        for action, support_count in ((bullish_action,long_support),(bearish_action,short_support)):
            prior = research_map.get(action) or {}
            if not _research_positive(prior) or support_count < learned_support_min: continue
            score = _f(prior.get("support_score")) - _f(prior.get("penalty_score"))
            candidates.append((score, action, prior))
        if candidates:
            candidates.sort(key=lambda row: row[0], reverse=True); best=candidates[0]
            if len(candidates)==1 or best[0] >= candidates[1][0] + 0.15:
                selected_action=best[1]; selected_prior=best[2]; specialist_source="LEARNED"
    else:
        selected_prior = research_map.get(selected_action) or {}
        if _research_positive(selected_prior): specialist_source="LEARNED"

    research_reason = _research_reasoning(research_map.get(selected_action) or {}) if selected_action in DIRECTIONAL_ACTIONS else _research_reasoning({})
    macro_reason = _macro_reasoning(layers.get("macro_context") or {}, segment=segment)

    strategy: Dict[str, Any] = {"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[],"conflicts":[]}
    if selected_action in DIRECTIONAL_ACTIONS:
        if is_multiasset:
            strategy = _multiasset_strategy_reasoning(
                selected_action=selected_action, regime=regime, vol_state=vol_state, thesis=thesis,
                symbol=symbol, timeframe=timeframe, macro_reasoning=macro_reason,
            )
        else:
            try:
                from default_strategy_bank import select_strategy
                prior_for_strategy = research_map.get(selected_action) or {}
                strategy = select_strategy(
                    selected_action, regime, vol_state, indicator_groups, symbol=_u(symbol),
                    timeframe=_u(timeframe), market=market,
                    preferred_family=str(prior_for_strategy.get("group_prior_strategy_family") or ""),
                )
            except Exception as exc:
                strategy={"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[],"conflicts":[],"error":str(exc)[:160]}

    official = bool(selected_action in DIRECTIONAL_ACTIONS and (is_official_cell(market,symbol,timeframe,selected_action) or is_multiasset_cell(market,symbol,timeframe,selected_action)))
    risk_profile = (
        {"risk_class": f"MULTI_{MULTIASSET_ASSET_CLASS.get(_u(symbol),'MULTIASSET')}", "name":"MULTIASSET_CLASS_AWARE", "risk_budget_multiplier":1.0, "max_entry_wait_bars": 2 if _u(timeframe)=="1H" else 3 if _u(timeframe)=="4H" else 4}
        if is_multiasset else futures_exit_profile_for(symbol) if market=="FUTURES" else {"risk_class":"SPOT","name":"PORTFOLIO_SNOWBALL","risk_budget_multiplier":1.0}
    )
    risk_class=str(risk_profile.get("risk_class") or ("SPOT" if market=="SPOT" else "CORE1"))
    min_quality = 78.0 if market=="FUTURES" else 70.0
    autonomous_min_quality = 76.0 if market=="SPOT" else 87.0 if risk_class=="HIGH" else 84.0 if risk_class=="MEDIUM" else 83.0 if is_multiasset else 82.0
    # Context raises requirements instead of deleting a valid thesis.
    adaptive_quality_min = autonomous_min_quality + _f(macro_reason.get("quality_extra")) + _f(research_reason.get("quality_extra"))
    adaptive_margin_min = _f(thesis.get("required_direction_margin"),1.0) + _f(macro_reason.get("margin_extra")) + _f(research_reason.get("margin_extra"))

    mtf_usable, mtf_gate_mode = _mtf_execution_gate(
        mtf_context=mtf_context, thesis=thesis, strategy=strategy, selected_action=selected_action,
        market=market, risk_class=risk_class, timeframe=timeframe, is_multiasset=is_multiasset,
    )
    support_count = long_support if action_direction(selected_action)=="BULLISH" else short_support
    thesis_ok = bool(thesis.get("direction") in {"BULLISH","BEARISH"} and _f(thesis.get("quality")) >= min_quality)
    contextual_strength_ok = bool(_f(thesis.get("margin")) >= adaptive_margin_min)
    autonomous_thesis_ok = bool(
        thesis.get("direction") in {"BULLISH","BEARISH"}
        and _f(thesis.get("quality")) >= adaptive_quality_min
        and support_count >= int(thesis.get("required_independent_families") or (4 if market=="FUTURES" else 3))
        and contextual_strength_ok and mtf_usable
    )
    learned_live_ok = bool(specialist_source=="LEARNED" and support_count>=learned_support_min and contextual_strength_ok and mtf_usable)
    # Multi-Asset strategy quality is context routing, not a backtested alpha score.
    strategy_min = 68.0 if is_multiasset else min_quality
    strategy_ok = bool(_f(strategy.get("quality")) >= strategy_min and strategy.get("regime_match",True) and strategy.get("volatility_match",True))
    default_path_ok = bool(thesis_ok and strategy_ok and contextual_strength_ok)
    candidate_source="NONE"
    if learned_live_ok and strategy_ok: candidate_source="LEARNED+DEFAULT"
    elif learned_live_ok: candidate_source="LEARNED+LIVE"
    elif default_path_ok: candidate_source="THESIS+DEFAULT"
    elif autonomous_thesis_ok: candidate_source="THESIS_AUTONOMOUS"

    hard_research = bool(research_reason.get("hard_block"))
    hard_macro = bool(macro_reason.get("hard_block_new_entry")) and market=="FUTURES"
    candidate_ready = bool(official and selected_action in DIRECTIONAL_ACTIONS and not hard_research and not hard_macro and candidate_source!="NONE" and mtf_usable)
    blockers: List[str] = []
    if selected_action not in DIRECTIONAL_ACTIONS: blockers.append("NO_DIRECTIONAL_THESIS")
    if selected_action in DIRECTIONAL_ACTIONS and not official: blockers.append("OUTSIDE_GOVERNED_OPERATIONAL_CELL")
    if hard_research: blockers.append(str(research_reason.get("reason") or "ROBUST_NEGATIVE_RESEARCH"))
    if hard_macro: blockers.append("IMMINENT_UNMODELLED_MACRO_EVENT")
    if selected_action in DIRECTIONAL_ACTIONS and candidate_source=="NONE": blockers.append("NO_ELIGIBLE_CONTEXTUAL_PATH")
    if not mtf_usable: blockers.append(mtf_gate_mode)
    if selected_action in DIRECTIONAL_ACTIONS and not contextual_strength_ok: blockers.append("CONTEXT_REQUIRES_STRONGER_DIRECTIONAL_MARGIN")

    return {
        "version":VERSION, "market":market, "operational_segment":segment,
        "market_objective":market_objective_for(market,symbol),
        "risk_class":risk_profile.get("risk_class"), "exit_profile":risk_profile.get("name"),
        "risk_budget_multiplier":risk_profile.get("risk_budget_multiplier",1.0), "max_entry_wait_bars":risk_profile.get("max_entry_wait_bars"),
        "symbol":_u(symbol), "timeframe":_u(timeframe),
        "context":{"regime":regime,"volatility":vol_state,"timeframe_profile":tf_profile,"volatility_reasoning":vol_reason,"macro_reasoning":macro_reason,"research_reasoning":research_reason},
        "multi_timeframe":dict(mtf_context or {}), "thesis":thesis, "default_strategy":strategy,
        "indicator_groups":indicator_groups,
        "decision_evidence":{
            "version":"COMMIT17_4_DECISION_EVIDENCE_V2", "selected_indicators":list(strategy.get("indicators") or []),
            "functional_evidence":list(strategy.get("functional_evidence") or []), "independent_families":list(strategy.get("independent_functional_families") or []),
            "thesis_families":list(thesis.get("independent_support_families") or []), "candidate_source":candidate_source,
            "default_archetype_id":strategy.get("archetype_id"), "default_specialization_key":strategy.get("specialization_key"),
        },
        "selected_specialist_source":specialist_source, "candidate_source":candidate_source,
        "autonomous_thesis_min_quality":round(autonomous_min_quality,2), "adaptive_quality_min":round(adaptive_quality_min,2),
        "adaptive_margin_min":round(adaptive_margin_min,3), "default_strategy_required":False,
        "selected_research_prior":selected_prior,
        "group_prior_advisory":dict(research_map.get(selected_action) or {}) if str((research_map.get(selected_action) or {}).get("state") or "")=="GROUP_PRIOR" else {},
        "research_candidates":research_map, "research_blocks_selected_action":hard_research,
        "candidate_action":selected_action if candidate_ready else "NO_OPERAR", "candidate_ready":candidate_ready,
        "official_cell":official, "mtf_usable":mtf_usable, "mtf_gate_mode":mtf_gate_mode, "candidate_blockers":blockers,
        "mtf_complete":bool((mtf_context or {}).get("complete")),
        "reasoning_policy":"OBJECTIVE_CONTEXT_VOLATILITY_MTF_STRATEGY_SPECIALISTS_EXECUTION_SAFETY_LEARNING",
        "resource_policy":{"extra_network_calls":0,"extra_db_writes":0,"extra_llm_calls":0,"extra_workers":0},
        "never_bypass_safety":True,
    }


def moderator_candidate(operational: Mapping[str, Any], votes: Iterable[Mapping[str, Any]], market: Any) -> Dict[str, Any]:
    """Thesis-first moderation: specialists challenge/confirm, never vote by majority.

    Absence of a legacy directional vote is no longer an automatic veto when the
    independent thesis is exceptionally strong. Strong contradictory specialists
    still raise the execution bar or force PRECAUCION.
    """
    action=canonical_action(operational.get("candidate_action"),_u(market))
    if action not in DIRECTIONAL_ACTIONS or not operational.get("candidate_ready"):
        return {"use":False,"action":"NO_OPERAR","reason":"THESIS_NOT_READY"}
    desired=action_direction(action); same=0; opposite=0; caution=0; same_strength=0.0; opposite_strength=0.0
    for vote in votes or []:
        va=canonical_action(vote.get("accion_normalizada") or vote.get("accion") or vote.get("accion_original"),_u(market)); vd=action_direction(va)
        conf=_f(vote.get("confianza_original") or vote.get("confianza"))
        if vd==desired and conf>=55: same+=1; same_strength+=conf
        elif vd in {"BULLISH","BEARISH"} and vd!=desired and conf>=65: opposite+=1; opposite_strength+=conf
        elif va in {"PRECAUCION","ESPERAR","NO_OPERAR"} and conf>=70: caution+=1
    thesis=dict(operational.get("thesis") or {}); strategy=dict(operational.get("default_strategy") or {})
    tq=_f(thesis.get("quality")); sq=_f(strategy.get("quality")); margin=_f(thesis.get("margin")); req_margin=_f(operational.get("adaptive_margin_min") or thesis.get("required_direction_margin"),1.0)
    support=len(thesis.get("independent_support_families") or []); req_support=int(thesis.get("required_independent_families") or 4)
    exceptional=bool(tq>=max(88.0,_f(operational.get("adaptive_quality_min"))+2.0) and margin>=req_margin+0.55 and support>=req_support and sq>=68.0)

    if opposite>=3 or (opposite>=2 and opposite_strength > same_strength + 80 and not exceptional):
        return {"use":False,"action":"PRECAUCION","reason":"MATERIAL_SPECIALIST_CONTRADICTION","same":same,"opposite":opposite,"caution":caution}
    if same<1 and not exceptional:
        return {"use":False,"action":"ESPERAR","reason":"SPECIALISTS_NOT_YET_CONFIRMING_STRONG_THESIS","same":same,"opposite":opposite,"caution":caution}

    source=str(operational.get("candidate_source") or "")
    confidence_base=tq if source=="THESIS_AUTONOMOUS" or sq<=0 else 0.62*tq+0.38*sq
    if same<1: confidence_base-=5.0
    if opposite: confidence_base-=min(8.0,3.0*opposite)
    if caution>=2: confidence_base-=3.0
    confidence=min(88.0,max(60.0,confidence_base))
    reason="EXCEPTIONAL_THESIS_WITH_NON_DIRECTIONAL_SPECIALISTS" if same<1 else "THESIS_AND_SPECIALISTS_CONTEXTUALLY_ALIGNED"
    return {"use":True,"action":action,"confidence":round(confidence,2),"reason":reason,"candidate_source":source,"same":same,"opposite":opposite,"caution":caution,"exceptional_thesis":exceptional}


def execution_setup_guard(*, action: Any, levels: Mapping[str, Any] | None, setup_family: Any, market: Any, timeframe: Any) -> Dict[str, Any]:
    action = canonical_action(action, _u(market)); levels = dict(levels or {})
    if action not in DIRECTIONAL_ACTIONS:
        return {"applied": False, "action": action, "status": "NON_DIRECTIONAL"}
    family = _u(setup_family)
    entry = _f(levels.get("entry")); sl = _f(levels.get("stop_loss")); tp = _f(levels.get("take_profit")); rr = _f(levels.get("risk_reward"))
    quality = _f(levels.get("entry_quality_score") or levels.get("entry_score"))
    sweep = bool(levels.get("entry_sweep_confirmed")); mss = bool(levels.get("entry_mss_bos_confirmed")); displacement = bool(levels.get("entry_displacement_confirmed"))
    source = str(levels.get("entry_source") or "")
    direction = action_direction(action)
    geometry = entry > 0 and sl > 0 and tp > 0 and ((direction == "BULLISH" and sl < entry < tp) or (direction == "BEARISH" and tp < entry < sl))
    reasons: List[str] = []
    if not geometry:
        reasons.append("Entry, Stop Loss y Take Profit no forman una geometría válida")
    if _u(market) == "FUTURES" and quality < 60:
        reasons.append(f"la calidad de la zona de entrada es {quality:.0f}/100, insuficiente para Futuros")
    if rr > 0 and _u(market) == "FUTURES" and rr < 1.5:
        reasons.append(f"la relación riesgo/beneficio disponible es 1:{rr:.2f}")
    if family == "SWEEP_REVERSAL" and not (sweep and mss):
        missing = []
        if not sweep: missing.append("barrido de liquidez")
        if not mss: missing.append("cambio de estructura")
        reasons.append("la reversión todavía no confirma " + " y ".join(missing))
    if family in {"BREAKOUT_RETEST", "STRUCTURE_RETEST"}:
        structural = any(token in source.lower() for token in ("order block", "fvg", "support", "resistance", "poc", "fibonacci", "retest"))
        if not structural and not (mss or displacement):
            reasons.append("la ruptura todavía no tiene retest o zona estructural suficientemente definida")
    if family == "MOMENTUM_CONTINUATION":
        structural = any(token in source.lower() for token in ("order block", "fvg", "support", "resistance", "vwap", "poc", "swing", "retest"))
        if quality < (64 if _u(market)=="FUTURES" else 56):
            reasons.append("la continuación de momentum aún no ofrece una zona de reacción suficientemente defendible")
        elif not structural and not displacement:
            reasons.append("la continuación tiene impulso, pero todavía no ofrece micro-retest/POI para entrar sin perseguir precio")
    if family == "COMPRESSION_EXPANSION":
        structural = any(token in source.lower() for token in ("fvg", "support", "resistance", "vwap", "poc", "retest", "swing"))
        if not structural and not (mss or displacement):
            reasons.append("la expansión de volatilidad todavía no tiene liberación y zona de reacción defendible")
    if family == "STRUCTURE_REVERSAL":
        structural = any(token in source.lower() for token in ("order block", "fvg", "support", "resistance", "swing", "fibonacci"))
        if not (mss or structural):
            reasons.append("la reversión de estructura todavía no confirma invalidación/reacción suficiente")
    if family == "TREND_PULLBACK" and quality < (62 if _u(market)=="FUTURES" else 55):
        reasons.append("el retroceso no llega a una zona de entrada suficientemente defendible")
    if reasons:
        # Commit 17.4 FINAL — execution can wait, direction cannot be rewritten here.
        # The thesis/market decision already exists before this helper.  Entry/SL/TP
        # readiness is an execution state, never a second directional vote.
        return {
            "applied": True,
            "action": action,
            "status": "EXECUTION_PENDING",
            "execution_ready": False,
            "reasons": reasons,
            "original_action": action,
            "direction_preserved": True,
        }
    return {
        "applied": False,
        "action": action,
        "status": "EXECUTION_READY",
        "execution_ready": True,
        "reasons": [],
        "direction_preserved": True,
    }


_AUDIT = official_universe_audit()
if not _AUDIT["ok"]:
    raise RuntimeError(f"RC9.2 operational universe mismatch: {_AUDIT}")
