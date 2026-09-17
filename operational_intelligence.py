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

VERSION = "COMMIT9_4_OPERATIONAL_INTELLIGENCE_V1"

DIRECTIONAL_ACTIONS = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}
NON_DIRECTIONAL_ACTIONS = {"ESPERAR", "PRECAUCION", "NO_OPERAR"}

SPOT_SYMBOLS = ("BTC-USDT", "PAXG-USDT", "PAXG-BTC")
FUTURES_SYMBOLS = ("BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT", "BNB-USDT", "LINK-USDT")
SPOT_EXECUTION_TFS = ("4H", "12H", "1D", "1W")
FUTURES_CORE_TFS = ("30M", "1H", "2H", "4H")
FUTURES_HTF_CELLS = {"BTC-USDT": ("12H", "1D"), "ETH-USDT": ("12H", "1D"), "SOL-USDT": ("12H", "1D")}


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


def canonical_volatility(volatility: Mapping[str, Any] | None, regime_raw: Any = None) -> str:
    v = dict(volatility or {})
    if bool(v.get("squeeze_on")) or int(_f(v.get("squeeze_length"))) > 0:
        return "COMPRESSION"
    ftm = _u(v.get("ftm_state") or v.get("state") or v.get("regime"))
    atr_pct = _f(v.get("atr_pct"))
    width = _f(v.get("bb_width"))
    raw_regime = _u(regime_raw)
    if raw_regime in {"HIGH_VOLATILITY", "VOLATILITY_SHOCK"} or ftm in {"EXTREME", "SHOCK"}:
        return "SHOCK"
    if ftm in {"HIGH", "EXPANSION", "VOLATILE", "HIGH_EXPANSION"} or atr_pct >= 4.0 or width >= 5.0:
        return "EXPANSION"
    if atr_pct > 0 and atr_pct <= 0.75 and width > 0 and width <= 1.25:
        return "LOW"
    return "NORMAL"


def official_universe_cells() -> List[Tuple[str, str, str, str]]:
    cells: List[Tuple[str, str, str, str]] = []
    for symbol in SPOT_SYMBOLS:
        for tf in SPOT_EXECUTION_TFS:
            for action in ("COMPRA_SPOT", "VENTA_SPOT"):
                cells.append(("SPOT", symbol, tf, action))
    for symbol in FUTURES_SYMBOLS:
        for tf in FUTURES_CORE_TFS:
            for action in ("LONG", "SHORT"):
                cells.append(("FUTURES", symbol, tf, action))
    for symbol, tfs in FUTURES_HTF_CELLS.items():
        for tf in tfs:
            for action in ("LONG", "SHORT"):
                cells.append(("FUTURES", symbol, tf, action))
    return cells


_OFFICIAL_CELL_SET = set(official_universe_cells())


def official_universe_audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "cells": len(_OFFICIAL_CELL_SET),
        "expected_cells": 92,
        "ok": len(_OFFICIAL_CELL_SET) == 92,
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


def mtf_required_timeframes(market: Any, timeframe: Any) -> List[str]:
    roles = _MTF_ROLE_PROFILES.get(_u(market), {}).get(_u(timeframe), {})
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

def build_multiframe_context(*, market: Any, timeframe: Any, current_layers: Mapping[str, Any], peer_analyses: Mapping[str, Mapping[str, Any]] | None = None) -> Dict[str, Any]:
    market = _u(market)
    timeframe = _u(timeframe)
    profile = _MTF_ROLE_PROFILES.get(market, {}).get(timeframe, {"setup": (timeframe,), "timing": (timeframe,)})
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


def build_independent_thesis(*, layers: Mapping[str, Any], mtf_context: Mapping[str, Any], market: Any) -> Dict[str, Any]:
    trend = dict(layers.get("trend") or {})
    momentum = dict(layers.get("momentum") or {})
    volume = dict(layers.get("volume") or {})
    structure = dict(layers.get("structure") or {})
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
    trend_score = 0.0
    if trend_dir == "BULLISH": trend_score = 0.55
    elif trend_dir == "BEARISH": trend_score = -0.55
    if adx >= 25:
        if plus_di > minus_di + 2: trend_score = max(trend_score, 0.85)
        elif minus_di > plus_di + 2: trend_score = min(trend_score, -0.85)
    elif adx < 18:
        trend_score *= 0.45
    add_family("trend", trend_score, f"ADX {adx:.1f}; +DI {plus_di:.1f}; -DI {minus_di:.1f}", 1.0)

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
    macro_bias = _norm_direction(macro.get("bias") or macro.get("direction") or macro.get("market_bias"))
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
    min_families = 4 if _u(market) == "FUTURES" else 3
    margin = abs(long_score - short_score)
    direction = "NEUTRAL"
    active = long_families if long_score > short_score else short_families
    if len(active) >= min_families and margin >= (1.15 if _u(market) == "FUTURES" else 0.9):
        direction = "BULLISH" if long_score > short_score else "BEARISH"
    if bool(mtf_context.get("conflict")) and _u(market) == "FUTURES":
        # A conflict does not erase the thesis, but it cannot be called strong.
        if margin < 2.0:
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


def prepare_operational_intelligence(
    *, layers: Mapping[str, Any], symbol: Any, timeframe: Any, system_type: Any,
    mtf_context: Mapping[str, Any], research_candidates: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Build the final pre-Safety candidate from learned + default intelligence.

    Learned evidence is evaluated *before* internal specialist opinions. It never
    bypasses live market support or Safety. A known negative exact action cannot
    be rescued by a default playbook.
    """
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    raw_regime = (layers.get("market_regime") or {}).get("regime")
    regime = canonical_regime(raw_regime)
    vol_state = canonical_volatility(layers.get("volatility") or {}, raw_regime)
    thesis = build_independent_thesis(layers=layers, mtf_context=mtf_context, market=market)
    research_map = {
        canonical_action(key, market): dict(value or {})
        for key, value in dict(research_candidates or {}).items()
    }

    bullish_action = "LONG" if market == "FUTURES" else "COMPRA_SPOT"
    bearish_action = "SHORT" if market == "FUTURES" else "VENTA_SPOT"
    long_support = len(thesis.get("long_families") or [])
    short_support = len(thesis.get("short_families") or [])
    learned_support_min = 3 if market == "FUTURES" else 2

    thesis_action = thesis.get("action") or "NO_OPERAR"
    selected_action = thesis_action
    selected_prior: Dict[str, Any] = {}
    specialist_source = "DEFAULT"

    # If the purely live thesis is neutral, a validated learned specialist may
    # open a *candidate* only when current independent families already support
    # the same side. This lets learned and default intelligence interleave while
    # refusing historical edge that the current market contradicts.
    if selected_action not in DIRECTIONAL_ACTIONS:
        candidates: List[Tuple[float, str, Dict[str, Any]]] = []
        for action, support_count in (
            (bullish_action, long_support), (bearish_action, short_support)
        ):
            prior = research_map.get(action) or {}
            if not _research_positive(prior) or support_count < learned_support_min:
                continue
            score = _f(prior.get("support_score")) - _f(prior.get("penalty_score"))
            candidates.append((score, action, prior))
        if candidates:
            candidates.sort(key=lambda row: row[0], reverse=True)
            best = candidates[0]
            # Ambiguous learned priors do not manufacture direction.
            if len(candidates) == 1 or best[0] >= candidates[1][0] + 0.15:
                selected_action = best[1]
                selected_prior = best[2]
                specialist_source = "LEARNED"
    else:
        selected_prior = research_map.get(selected_action) or {}
        if _research_positive(selected_prior):
            specialist_source = "LEARNED"

    blocked_by_research = bool(
        selected_action in DIRECTIONAL_ACTIONS
        and _research_negative(research_map.get(selected_action) or {})
    )

    strategy: Dict[str, Any] = {
        "id": "NO_PLAYBOOK", "family": "NONE", "quality": 0.0,
        "confirmations": [], "conflicts": [],
    }
    if selected_action in DIRECTIONAL_ACTIONS:
        try:
            from default_strategy_bank import select_strategy
            from contingency_strategy_engine import _indicator_groups
            groups = _indicator_groups(dict(layers))
            groups["multi_timeframe"] = dict(mtf_context or {})
            strategy = select_strategy(
                selected_action, regime, vol_state, groups,
                symbol=_u(symbol), timeframe=_u(timeframe), market=market,
            )
        except Exception as exc:
            strategy = {
                "id":"NO_PLAYBOOK", "family":"NONE", "quality":0.0,
                "confirmations":[], "conflicts":[], "error":str(exc)[:160],
            }

    official = (
        selected_action in DIRECTIONAL_ACTIONS
        and is_official_cell(market, symbol, timeframe, selected_action)
    )
    min_quality = 78.0 if market == "FUTURES" else 70.0
    mtf_usable = not bool((mtf_context or {}).get("conflict"))
    support_count = (
        long_support if action_direction(selected_action) == "BULLISH" else short_support
    )
    # Learned specialists still need live independent support. Defaults need the
    # full thesis-quality threshold as before.
    thesis_ok = bool(
        thesis.get("direction") in {"BULLISH", "BEARISH"}
        and float(thesis.get("quality") or 0) >= min_quality
    )
    learned_live_ok = bool(
        specialist_source == "LEARNED"
        and support_count >= learned_support_min
        and not bool((mtf_context or {}).get("conflict"))
    )
    strategy_ok = bool(
        float(strategy.get("quality") or 0) >= min_quality
        and strategy.get("regime_match", True)
        and strategy.get("volatility_match", True)
    )
    candidate_ready = bool(
        official
        and selected_action in DIRECTIONAL_ACTIONS
        and not blocked_by_research
        and (thesis_ok or learned_live_ok)
        and strategy_ok
        and mtf_usable
        and not (market == "FUTURES" and _u(thesis.get("macro_risk")) == "CRITICAL")
    )

    return {
        "version": VERSION,
        "market": market,
        "symbol": _u(symbol),
        "timeframe": _u(timeframe),
        "context": {"regime": regime, "volatility": vol_state},
        "multi_timeframe": dict(mtf_context or {}),
        "thesis": thesis,
        "default_strategy": strategy,
        "selected_specialist_source": specialist_source,
        "selected_research_prior": selected_prior,
        "research_candidates": research_map,
        "research_blocks_selected_action": blocked_by_research,
        "candidate_action": selected_action if candidate_ready else "NO_OPERAR",
        "candidate_ready": candidate_ready,
        "official_cell": official,
        "mtf_usable": mtf_usable,
        "mtf_complete": bool((mtf_context or {}).get("complete")),
        "never_bypass_safety": True,
    }

def moderator_candidate(operational: Mapping[str, Any], votes: Iterable[Mapping[str, Any]], market: Any) -> Dict[str, Any]:
    """Return a thesis-first candidate without using a simple trader majority.

    The candidate still needs at least one internal specialist to independently
    support it. Strong opposite support does not flip direction; it downgrades.
    """
    action = canonical_action(operational.get("candidate_action"), _u(market))
    if action not in DIRECTIONAL_ACTIONS or not operational.get("candidate_ready"):
        return {"use": False, "action": "NO_OPERAR", "reason": "THESIS_NOT_READY"}
    same = 0; opposite = 0; caution = 0
    desired = action_direction(action)
    for vote in votes or []:
        va = canonical_action(vote.get("accion_normalizada") or vote.get("accion") or vote.get("accion_original"), _u(market))
        vd = action_direction(va)
        conf = _f(vote.get("confianza_original") or vote.get("confianza"))
        if vd == desired and conf >= 55: same += 1
        elif vd in {"BULLISH","BEARISH"} and vd != desired and conf >= 65: opposite += 1
        elif va in {"PRECAUCION","ESPERAR","NO_OPERAR"} and conf >= 70: caution += 1
    if opposite >= 2:
        return {"use": False, "action": "PRECAUCION", "reason": "SPECIALIST_CONTRADICTION", "same":same, "opposite":opposite, "caution":caution}
    if same < 1:
        return {"use": False, "action": "ESPERAR", "reason": "NO_INDEPENDENT_SPECIALIST_CONFIRMATION", "same":same, "opposite":opposite, "caution":caution}
    confidence = min(88.0, max(60.0, (_f((operational.get("thesis") or {}).get("quality")) + _f((operational.get("default_strategy") or {}).get("quality"))) / 2.0))
    return {"use": True, "action": action, "confidence": round(confidence,2), "reason":"THESIS_AND_SPECIALIST_ALIGNED", "same":same, "opposite":opposite, "caution":caution}


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
    if family == "TREND_PULLBACK" and quality < (62 if _u(market)=="FUTURES" else 55):
        reasons.append("el retroceso no llega a una zona de entrada suficientemente defendible")
    if reasons:
        final = "PRECAUCION" if geometry and _u(market)=="FUTURES" else "ESPERAR"
        return {"applied": True, "action": final, "status":"SETUP_NOT_EXECUTABLE", "reasons":reasons, "original_action":action}
    return {"applied": False, "action": action, "status":"SETUP_EXECUTABLE", "reasons":[]}


_AUDIT = official_universe_audit()
if not _AUDIT["ok"]:
    raise RuntimeError(f"RC9.2 operational universe mismatch: {_AUDIT}")
