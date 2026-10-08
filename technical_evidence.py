"""Canonical technical-evidence normalization for SmartTradingReview 33.4.1.

Pure normalization only: no I/O, DB, LLM, runtime patching or direction authority.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

VERSION = "CORE_TECHNICAL_EVIDENCE_33_4_1_V1"

def _u(value: Any) -> str:
    return str(value or "").strip().upper()

def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value if value is not None else default)
        return n if math.isfinite(n) else float(default)
    except Exception:
        return float(default)

def indicator_groups(layers: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize every live technical component used by the default bank.

    Commit 9.4 deliberately exposes *observed values*, not synthetic defaults.
    A missing component stays unavailable and therefore cannot create quality.
    """
    trend = layers.get("trend") or {}
    ti = trend.get("indicators") or {}
    momentum = layers.get("momentum") or {}
    mi = momentum.get("indicators") or {}
    vol = layers.get("volatility") or {}
    volume = layers.get("volume") or {}
    structure = layers.get("structure") or {}
    liq = layers.get("liquidation") or {}
    macro = layers.get("macro_context") or {}
    sentiment = layers.get("sentiment") or {}
    correlation = layers.get("correlation") or {}
    hours = layers.get("market_hours") or {}
    time_factor = layers.get("time_factor") or {}
    mtf = layers.get("multi_timeframe_context") or layers.get("multi_timeframe") or {}

    def _dir_list(rows: Any) -> List[str]:
        output: List[str] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            raw = _u(row.get("type") or row.get("direction") or row.get("side"))
            if raw in {"BULLISH", "BUY", "LONG", "ALCISTA"}:
                value = "BULLISH"
            elif raw in {"BEARISH", "SELL", "SHORT", "BAJISTA"}:
                value = "BEARISH"
            else:
                continue
            if value not in output:
                output.append(value)
        return output

    volume_profile = structure.get("volume_profile") or {}
    patterns = structure.get("patterns") or {}
    trend_dir = _u(trend.get("direction"))
    momentum_dir = _u(momentum.get("direction"))
    obv_dir = _u(volume.get("obv_trend"))
    macro_bias = _u(
        macro.get("directional_bias")
        or macro.get("direction")
        or macro.get("bias")
    )

    groups = {
        "trend": {
            "available": bool(trend),
            "direction": trend_dir or "NEUTRAL",
            "adx": round(_f(trend.get("adx")), 2),
            "plus_di": round(_f(trend.get("plus_di")), 2),
            "minus_di": round(_f(trend.get("minus_di")), 2),
            "sma20": _f(ti.get("sma20") or trend.get("sma20")),
            "sma50": _f(ti.get("sma50") or trend.get("sma50")),
            "ema9": _f(ti.get("ema9") or trend.get("ema9")),
            "ema21": _f(ti.get("ema21") or trend.get("ema21")),
            "ema50": _f(ti.get("ema50") or trend.get("ema50")),
            "ema200": _f(ti.get("ema200") or trend.get("ema200")),
            "supertrend": _u(ti.get("supertrend_trend")),
            "ichimoku_cloud": _u(ti.get("ichimoku_cloud")),
            "ichimoku_tk": _u(ti.get("ichimoku_tk")),
            "psar": _u(ti.get("parabolic_sar_trend")),
        },
        "momentum": {
            "available": bool(momentum),
            "direction": momentum_dir or "NEUTRAL",
            "score": round(_f(momentum.get("score")), 2),
            "rsi": (round(_f(mi.get("rsi")), 2) if mi.get("rsi") is not None else None),
            "rsi_maverick": (
                round(_f(mi.get("rsi_maverick")), 4)
                if mi.get("rsi_maverick") is not None else None
            ),
            "macd_histogram": (
                round(_f(mi.get("macd_histogram")), 6)
                if mi.get("macd_histogram") is not None else None
            ),
            "divergences": list(momentum.get("divergences") or []),
            "hidden_divergences": list(momentum.get("hidden_divergences") or []),
            "stoch_k": (
                round(_f(mi.get("stoch_k")), 2)
                if mi.get("stoch_k") is not None else None
            ),
            "stoch_d": (
                round(_f(mi.get("stoch_d")), 2)
                if mi.get("stoch_d") is not None else None
            ),
            "williams": (
                round(_f(mi.get("williams")), 2)
                if mi.get("williams") is not None else None
            ),
            "cci": (
                round(_f(mi.get("cci")), 2)
                if mi.get("cci") is not None else None
            ),
        },
        "volatility": {
            "available": bool(vol),
            "atr": _f(vol.get("atr")),
            "atr_pct": round(_f(vol.get("atr_pct")), 4),
            "bb_width": (
                round(_f(vol.get("bb_width")), 4)
                if vol.get("bb_width") is not None else None
            ),
            "bb_position": (
                round(_f(vol.get("bb_position")), 4)
                if vol.get("bb_position") is not None else None
            ),
            "squeeze_on": (
                bool(vol.get("squeeze_on"))
                if vol.get("squeeze_on") is not None else None
            ),
            "squeeze_length": int(_f(vol.get("squeeze_length"))),
            "ftm_state": _u(
                vol.get("ftm_state")
                or vol.get("trend_force_state")
                or vol.get("maverick_state")
            ) or "NEUTRAL",
        },
        "volume_flow": {
            "available": bool(volume),
            "volume_ratio": (
                round(_f(volume.get("volume_ratio")), 3)
                if volume.get("volume_ratio") is not None else None
            ),
            "mfi": (
                round(_f(volume.get("mfi")), 2)
                if volume.get("mfi") is not None else None
            ),
            "force_index": (
                round(_f(volume.get("force_index")), 4)
                if volume.get("force_index") is not None else None
            ),
            "obv_trend": obv_dir or "NEUTRAL",
            "vwap": _f(volume.get("vwap")),
            "whale_buy": bool(volume.get("whale_buy_confirmed") or volume.get("whale_buy")),
            "whale_sell": bool(volume.get("whale_sell_confirmed") or volume.get("whale_sell")),
            "whale_extended_buy": bool(volume.get("whale_extended_buy")),
            "whale_extended_sell": bool(volume.get("whale_extended_sell")),
            "whale_event_pending": bool(volume.get("whale_event_pending")),
            "whale_event_age_bars": volume.get("whale_event_age_bars"),
            "whale_signal_strength": _f(volume.get("whale_signal_strength")),
            # Compatibility names represent an OHLCV absorption proxy, not a
            # directly observed exchange iceberg order.
            "iceberg_buy": bool(volume.get("iceberg_buy")),
            "iceberg_sell": bool(volume.get("iceberg_sell")),
        },
        "structure_liquidity": {
            "available": bool(structure),
            "current_price": _f(structure.get("current_price")),
            "direction": _u(
                structure.get("direction") or structure.get("structure_direction")
            ) or "NEUTRAL",
            "support": _f(structure.get("nearest_support") or structure.get("support")),
            "resistance": _f(structure.get("nearest_resistance") or structure.get("resistance")),
            "fib_levels": dict(structure.get("fib_levels") or {}),
            "poc": _f(volume_profile.get("poc")),
            "hvn_nodes": list(
                structure.get("hvn_nodes")
                or volume_profile.get("hvn_nodes")
                or []
            ),
            "lvn_nodes": list(
                structure.get("lvn_nodes")
                or volume_profile.get("lvn_nodes")
                or []
            ),
            "bullish_patterns_count": int(_f(
                structure.get("bullish_patterns_count")
                if structure.get("bullish_patterns_count") is not None
                else patterns.get("bullish_count")
            )),
            "bearish_patterns_count": int(_f(
                structure.get("bearish_patterns_count")
                if structure.get("bearish_patterns_count") is not None
                else patterns.get("bearish_count")
            )),
            "order_block_directions": _dir_list(structure.get("order_blocks")),
            "fvg_directions": _dir_list(
                structure.get("fair_value_gaps") or structure.get("fvgs")
            ),
            "sweep_directions": _dir_list(structure.get("liquidity_sweeps")),
            "stop_hunt_directions": _dir_list(structure.get("stop_hunts")),
            "has_patterns": bool(patterns.get("recent_patterns") or patterns.get("all_patterns")),
            "has_order_blocks": bool(structure.get("order_blocks")),
            "has_fvg": bool(structure.get("fair_value_gaps") or structure.get("fvgs")),
            "has_liquidity_sweep": bool(structure.get("liquidity_sweeps")),
            "has_stop_hunt": bool(structure.get("stop_hunts")),
            "has_volume_profile": bool(volume_profile),
        },
        "liquidations": {
            "available": bool(liq),
            "long_weight": round(_f(liq.get("total_long_weight")), 3),
            "short_weight": round(_f(liq.get("total_short_weight")), 3),
            "events": int(_f(liq.get("total_spikes"))),
            "data_type": str(liq.get("data_type") or ""),
        },
        "macro": {
            "available": bool(macro.get("enabled", bool(macro))),
            "risk": _u(macro.get("risk_level") or macro.get("risk")) or "UNKNOWN",
            "bias": macro_bias or "NEUTRAL",
            "futures_posture": _u(macro.get("futures_posture")) or "NORMAL",
        },
        "sentiment": {
            "available": bool(sentiment),
            "value": (
                round(_f(sentiment.get("current_value")), 2)
                if sentiment.get("current_value") is not None else None
            ),
            "bias": _u(sentiment.get("sentiment_bias") or sentiment.get("bias")) or "NEUTRAL",
        },
        "rotation": {
            "available": bool(correlation),
            "signal": _u(correlation.get("rotation_signal")) or "NEUTRAL",
            "weight_modifier": round(_f(correlation.get("weight_modifier"), 1), 3),
        },
        "market_time": {
            "available": bool(hours or time_factor),
            "session": str(hours.get("session") or "UNKNOWN"),
            "liquidity": str(hours.get("liquidity") or "unknown"),
            "day_type": str(hours.get("day_type") or "UNKNOWN"),
            "time_score": round(_f(time_factor.get("score"), 0), 2),
        },
        "multi_timeframe": dict(mtf or {}),
    }
    groups["coverage"] = {
        "available_groups": sum(
            1 for key, value in groups.items()
            if key != "coverage" and isinstance(value, dict) and value.get("available")
        ),
        "total_groups": 10,
    }
    return groups



def audit() -> dict:
    return {"version": VERSION, "pure": True, "creates_direction": False, "new_io": 0}
