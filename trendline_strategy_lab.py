"""Commit 3 — Trendline Structure Lab (SHADOW ONLY).

Detects objective dynamic support/resistance from closed-candle pivots and emits
compact strategy observations. It has no authority over votes, Safety, Entry,
SL, TP, leverage or publication.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

TRENDLINE_LAB_VERSION = "C3_TRENDLINE_SHADOW_V1"


def _pivot_indices(values: np.ndarray, left: int = 3, right: int = 3, mode: str = "low") -> List[int]:
    out: List[int] = []
    for i in range(left, len(values) - right):
        window = values[i-left:i+right+1]
        value = values[i]
        if mode == "low" and value <= np.min(window):
            out.append(i)
        elif mode == "high" and value >= np.max(window):
            out.append(i)
    return out


def _fit_line(indices: List[int], values: np.ndarray, atr: float) -> Optional[Dict[str, Any]]:
    if len(indices) < 2:
        return None
    # Prefer recent pivots while preserving enough history to judge quality.
    idx = np.asarray(indices[-6:], dtype=float)
    y = np.asarray([values[int(i)] for i in idx], dtype=float)
    if len(idx) < 2 or not np.isfinite(y).all():
        return None
    slope, intercept = np.polyfit(idx, y, 1)
    fitted = slope * idx + intercept
    residual = np.abs(y - fitted)
    tolerance = max(float(atr) * 0.35, np.mean(y) * 0.001)
    touches = int(np.sum(residual <= tolerance))
    rmse = float(np.sqrt(np.mean((y - fitted) ** 2)))
    quality = 0.0
    quality += min(45.0, touches * 11.0)
    if atr > 0:
        quality += max(0.0, 35.0 - (rmse / atr) * 35.0)
    span = max(1.0, idx[-1] - idx[0])
    quality += min(20.0, span / 40.0 * 20.0)
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "touches": touches,
        "rmse": rmse,
        "quality": round(min(100.0, quality), 2),
        "first_index": int(idx[0]),
        "last_pivot_index": int(idx[-1]),
        "pivot_indices": [int(v) for v in idx.tolist()],
    }


def _line_value(line: Optional[Dict[str, Any]], index: int) -> Optional[float]:
    if not line:
        return None
    return float(line["slope"] * index + line["intercept"])


def analyze_trendline_strategy_lab(
    df,
    symbol: str,
    timeframe: str,
    system_type: str,
    final_action: str = "NO_OPERAR",
    fib_levels: Optional[Dict[str, Any]] = None,
    atr: Optional[float] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "version": TRENDLINE_LAB_VERSION,
        "shadow_only": True,
        "affects_vote": False,
        "affects_safety": False,
        "affects_entry": False,
        "affects_levels": False,
        "affects_publication": False,
        "affects_leverage": False,
        "eligible": False,
        "symbol": str(symbol or ""),
        "timeframe": str(timeframe or ""),
        "system_type": str(system_type or "").lower(),
        "strategies": {},
        "geometry": {},
        "reason": None,
    }
    try:
        if df is None or len(df) < 40:
            result["reason"] = "INSUFFICIENT_CLOSED_CANDLES"
            return result
        high = np.asarray(df["high"].values, dtype=float)
        low = np.asarray(df["low"].values, dtype=float)
        close = np.asarray(df["close"].values, dtype=float)
        if not all(np.isfinite(v).all() for v in (high, low, close)):
            result["reason"] = "INVALID_OHLC"
            return result

        tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        local_atr = float(atr or (np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)))
        local_atr = max(local_atr, float(close[-1]) * 0.001)

        lows = _pivot_indices(low, mode="low")
        highs = _pivot_indices(high, mode="high")
        support = _fit_line(lows, low, local_atr)
        resistance = _fit_line(highs, high, local_atr)
        now_i = len(close) - 1
        prev_i = now_i - 1
        support_now = _line_value(support, now_i)
        resistance_now = _line_value(resistance, now_i)
        support_prev = _line_value(support, prev_i)
        resistance_prev = _line_value(resistance, prev_i)
        price = float(close[-1])
        prev_close = float(close[-2])
        tolerance = max(local_atr * 0.35, price * 0.0015)

        def align(direction: str) -> str:
            action = str(final_action or "").upper()
            if action in ("COMPRA_SPOT", "BUY"): action = "LONG"
            if action in ("VENTA_SPOT", "SELL"): action = "SHORT"
            if direction not in ("LONG", "SHORT"): return "NEUTRAL"
            if action == direction: return "ALIGNED"
            if action in ("LONG", "SHORT"): return "CONFLICT"
            return "OBSERVATION_ONLY"

        fib_levels = fib_levels if isinstance(fib_levels, dict) else {}
        fib_vals = []
        for key in ("0.382", "0.5", "0.618"):
            try:
                val = float(fib_levels.get(key) or 0)
                if val > 0: fib_vals.append((key, val))
            except Exception:
                pass

        strategies: Dict[str, Any] = {}
        if support and support_now is not None and support["quality"] >= 45:
            near_support = abs(price - support_now) <= tolerance
            bounce = near_support and close[-1] > close[-2] and low[-1] <= support_now + tolerance
            broke_prev = support_prev is not None and prev_close < support_prev - tolerance
            reclaimed = price > support_now and low[-1] <= support_now + tolerance
            direction = "LONG" if bounce or (broke_prev and reclaimed) else "NEUTRAL"
            state = "FALSE_BREAK_RECLAIM_LONG" if broke_prev and reclaimed else ("TRENDLINE_SUPPORT_BOUNCE" if bounce else "NO_EDGE")
            strategies["support_reaction"] = {
                "name": "TRENDLINE_SUPPORT_REACTION_V1", "direction": direction, "state": state,
                "alignment_with_system": align(direction), "quality": support["quality"], "shadow_only": True,
            }

        if resistance and resistance_now is not None and resistance["quality"] >= 45:
            near_res = abs(price - resistance_now) <= tolerance
            reject = near_res and close[-1] < close[-2] and high[-1] >= resistance_now - tolerance
            broke_prev = resistance_prev is not None and prev_close > resistance_prev + tolerance
            rejected_back = price < resistance_now and high[-1] >= resistance_now - tolerance
            direction = "SHORT" if reject or (broke_prev and rejected_back) else "NEUTRAL"
            state = "FALSE_BREAK_RECLAIM_SHORT" if broke_prev and rejected_back else ("TRENDLINE_RESISTANCE_REJECTION" if reject else "NO_EDGE")
            strategies["resistance_reaction"] = {
                "name": "TRENDLINE_RESISTANCE_REACTION_V1", "direction": direction, "state": state,
                "alignment_with_system": align(direction), "quality": resistance["quality"], "shadow_only": True,
            }

        # Break + retest of dynamic lines.
        if resistance and resistance_prev is not None and resistance_now is not None:
            broke_up = prev_close > resistance_prev + tolerance
            retest = low[-1] <= resistance_now + tolerance and price > resistance_now
            direction = "LONG" if broke_up and retest else "NEUTRAL"
            strategies["break_retest_long"] = {
                "name": "TRENDLINE_BREAK_RETEST_LONG_V1", "direction": direction,
                "state": "TRENDLINE_BREAK_RETEST_LONG" if direction == "LONG" else "NO_EDGE",
                "alignment_with_system": align(direction), "quality": resistance["quality"], "shadow_only": True,
            }
        if support and support_prev is not None and support_now is not None:
            broke_down = prev_close < support_prev - tolerance
            retest = high[-1] >= support_now - tolerance and price < support_now
            direction = "SHORT" if broke_down and retest else "NEUTRAL"
            strategies["break_retest_short"] = {
                "name": "TRENDLINE_BREAK_RETEST_SHORT_V1", "direction": direction,
                "state": "TRENDLINE_BREAK_RETEST_SHORT" if direction == "SHORT" else "NO_EDGE",
                "alignment_with_system": align(direction), "quality": support["quality"], "shadow_only": True,
            }

        # Fibonacci confluence is observation only; it never creates direction alone.
        fib_confluence = []
        for key, val in fib_vals:
            if support_now and abs(val - support_now) <= tolerance:
                fib_confluence.append({"fib": key, "line": "support", "price": round(val, 8)})
            if resistance_now and abs(val - resistance_now) <= tolerance:
                fib_confluence.append({"fib": key, "line": "resistance", "price": round(val, 8)})
        if fib_confluence:
            strategies["fib_confluence"] = {
                "name": "TRENDLINE_FIB_CONFLUENCE_V1", "direction": "NEUTRAL", "state": "CONFLUENCE_PRESENT",
                "alignment_with_system": "NEUTRAL", "points": fib_confluence, "shadow_only": True,
            }

        def geom(line: Optional[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
            if not line:
                return None
            start = max(0, int(line["first_index"]))
            return {
                "kind": kind,
                "start_index": start,
                "end_index": now_i,
                "start_price": round(_line_value(line, start), 8),
                "end_price": round(_line_value(line, now_i), 8),
                "quality": line["quality"],
                "touches": line["touches"],
                "slope_per_candle": round(float(line["slope"]), 8),
            }

        result["eligible"] = bool(support or resistance)
        result["reason"] = "SHADOW_OBSERVATION_ONLY" if result["eligible"] else "NO_VALID_TRENDLINE"
        result["strategies"] = strategies
        result["geometry"] = {"support": geom(support, "support"), "resistance": geom(resistance, "resistance"), "atr": round(local_atr, 8)}
        return result
    except Exception as exc:
        result["reason"] = f"TRENDLINE_SHADOW_ERROR:{type(exc).__name__}"
        result["error"] = str(exc)[:180]
        return result
