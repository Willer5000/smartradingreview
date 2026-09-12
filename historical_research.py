"""Commit 3 — bounded historical strategy research (RESEARCH ONLY).

This module deliberately does not reproduce the production committee. It
replays only experimental timing/structure strategies against closed candles,
with a fixed research geometry, and keeps its results separate from LIVE.
"""
from __future__ import annotations
from typing import Any, Dict, List
import numpy as np

RESEARCH_VERSION = "C16_3_HISTORICAL_RESEARCH_V2"


def _rsi(values, period: int):
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), 50.0, dtype=float)
    if len(values) <= period: return out
    delta = np.diff(values)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    for i in range(period, len(values)):
        g = float(np.mean(gains[max(0, i-period):i]))
        l = float(np.mean(losses[max(0, i-period):i]))
        out[i] = 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g/l)
    return out


def _atr(df, end: int, period: int = 14) -> float:
    h = np.asarray(df["high"].values[:end+1], dtype=float)
    l = np.asarray(df["low"].values[:end+1], dtype=float)
    c = np.asarray(df["close"].values[:end+1], dtype=float)
    if len(c) < 3: return 0.0
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-period:])) if len(tr) else 0.0


def _directional_rsi_profile(close: np.ndarray, timeframe: str) -> str:
    if timeframe in ("5m", "15m"):
        a,b,c = _rsi(close,3),_rsi(close,7),_rsi(close,14)
        if a[-1] > a[-2] and a[-1] >= b[-1] and b[-1] >= b[-2] and c[-1] >= 40: return "LONG"
        if a[-1] < a[-2] and a[-1] <= b[-1] and b[-1] <= b[-2] and c[-1] <= 60: return "SHORT"
    else:
        b,c = _rsi(close,14),_rsi(close,21)
        if b[-1] > 50 and b[-1] > b[-2] and c[-1] >= 45: return "LONG"
        if b[-1] < 50 and b[-1] < b[-2] and c[-1] <= 55: return "SHORT"
    return "NEUTRAL"


def _evaluate_forward(df, idx: int, direction: str, atr: float, horizon: int = 12) -> Dict[str, Any]:
    entry = float(df["close"].iloc[idx])
    if atr <= 0 or direction not in ("LONG", "SHORT"):
        return {"resolved": False}
    # Research-only standardized geometry. Never reused in production.
    risk = atr
    sl = entry - risk if direction == "LONG" else entry + risk
    tp = entry + 1.8*risk if direction == "LONG" else entry - 1.8*risk
    mfe = mae = 0.0
    for j in range(idx+1, min(len(df), idx+1+horizon)):
        hi, lo = float(df["high"].iloc[j]), float(df["low"].iloc[j])
        if direction == "LONG":
            mfe = max(mfe, (hi-entry)/risk); mae = max(mae, (entry-lo)/risk)
            hit_tp, hit_sl = hi >= tp, lo <= sl
        else:
            mfe = max(mfe, (entry-lo)/risk); mae = max(mae, (hi-entry)/risk)
            hit_tp, hit_sl = lo <= tp, hi >= sl
        if hit_tp and hit_sl: return {"resolved": False, "ambiguous": True, "mfe_r": mfe, "mae_r": mae}
        if hit_tp: return {"resolved": True, "outcome": "TP", "r": 1.8, "mfe_r": mfe, "mae_r": mae}
        if hit_sl: return {"resolved": True, "outcome": "SL", "r": -1.0, "mfe_r": mfe, "mae_r": mae}
    return {"resolved": True, "outcome": "EXPIRED", "r": 0.0, "mfe_r": mfe, "mae_r": mae}


def run_historical_strategy_research(df, symbol: str, timeframe: str, max_observations: int = 120) -> Dict[str, Any]:
    result = {"version": RESEARCH_VERSION, "cohort": "HISTORICAL_RESEARCH", "production_authority": False,
              "symbol": symbol, "timeframe": timeframe, "observations": 0, "resolved": 0, "strategies": {}, "split": {},
              "data_start": None, "data_end": None}
    if df is None or len(df) < 80: return result

    # Commit 4: persist the exact research window so the same candles cannot be
    # counted repeatedly as independent evidence by the Autopilot.
    try:
        idx = getattr(df, "index", None)
        if idx is not None and len(idx):
            result["data_start"] = str(idx[max(0, len(df) - max_observations - 12)])
            result["data_end"] = str(idx[-1])
    except Exception:
        pass
    start = max(50, len(df) - max_observations - 12)
    rows: List[Dict[str, Any]] = []
    close_all = np.asarray(df["close"].values, dtype=float)
    for idx in range(start, len(df)-12):
        direction = _directional_rsi_profile(close_all[:idx+1], timeframe)
        if direction == "NEUTRAL": continue
        ev = _evaluate_forward(df, idx, direction, _atr(df, idx))
        rows.append({"strategy": "Q7_RSI_PROFILE_REPLAY", "direction": direction, **ev})
        if len(rows) >= max_observations: break
    result["observations"] = len(rows)
    resolved = [r for r in rows if r.get("resolved") and r.get("outcome") in ("TP","SL")]
    result["resolved"] = len(resolved)
    if resolved:
        cut = max(1, int(len(resolved)*0.70))
        # Small purge/embargo around the split so adjacent observations that
        # share forward candles are not treated as fully independent.
        embargo = max(1, min(6, int(len(resolved) * 0.03))) if len(resolved) >= 20 else 0
        calibration = resolved[:max(1, cut - embargo)]
        validation = resolved[min(len(resolved), cut + embargo):]
        def stats(part):
            if not part: return {"n":0}
            rs = [float(x.get("r",0)) for x in part]
            wins = sum(1 for x in part if x.get("outcome")=="TP")
            gross_win = sum(max(0,r) for r in rs); gross_loss = abs(sum(min(0,r) for r in rs))
            return {"n":len(part), "wr_pct":round(wins/len(part)*100,2), "expectancy_r":round(float(np.mean(rs)),4),
                    "profit_factor":round(gross_win/gross_loss,3) if gross_loss>0 else None,
                    "avg_mfe_r":round(float(np.mean([x.get("mfe_r",0) for x in part])),3),
                    "avg_mae_r":round(float(np.mean([x.get("mae_r",0) for x in part])),3)}
        result["split"] = {
            "calibration_70": stats(calibration),
            "validation_30": stats(validation),
            "embargo_observations": embargo,
            "methodology": "BOUNDED_CLOSED_CANDLE_REPLAY_WITH_EMBARGO",
        }
        result["strategies"]["Q7_RSI_PROFILE_REPLAY"] = stats(resolved)
    return result
