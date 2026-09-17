"""RC8.4 default strategy bank.

Fallback/contingency playbooks only. They never become statistical Champions
without Research/OOS/Shadow validation. The bank gives every technical input a
real role in at least two specialized playbooks while avoiding the anti-pattern
of putting every indicator in one giant strategy.
"""
from __future__ import annotations
from collections import Counter
from typing import Any, Dict, List

VERSION = "RC8_4_DEFAULT_STRATEGY_BANK_V1"

# Canonical indicator/market components already calculated by the main engine.
INDICATOR_UNIVERSE = {
    "sma", "ema_stack", "adx_dmi", "supertrend", "ichimoku", "psar",
    "rsi", "rsi_maverick", "macd", "stochastic", "williams_r", "cci",
    "regular_divergence", "hidden_divergence",
    "atr", "bollinger", "ftmaverick", "squeeze",
    "volume_ratio", "force_index", "mfi", "obv", "whale_proxy", "iceberg",
    "vwap", "volume_profile_poc", "hvn_lvn",
    "order_block", "fvg", "liquidity_sweep", "stop_hunt",
    "support_resistance", "fibonacci", "candlestick_patterns",
    "liquidation_map", "sentiment", "macro_context", "correlation_rotation",
    "market_session",
}

# Each strategy is intentionally specialized.  Indicators are shared across
# several playbooks, but no strategy consumes the whole universe.
STRATEGIES: List[Dict[str, Any]] = [
    {"id":"SPOT_FLOOR_LIQUIDITY_ACCUMULATION","actions":["COMPRA_SPOT"],"family":"SWEEP_REVERSAL","indicators":["rsi","rsi_maverick","regular_divergence","liquidity_sweep","stop_hunt","order_block","volume_ratio","mfi","whale_proxy","atr","support_resistance"]},
    {"id":"SPOT_VALUE_RECLAIM","actions":["COMPRA_SPOT"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","rsi","stochastic","williams_r","mfi","obv","volume_profile_poc","hvn_lvn","candlestick_patterns","support_resistance"]},
    {"id":"SPOT_TREND_PULLBACK_ACCUMULATION","actions":["COMPRA_SPOT"],"family":"TREND_PULLBACK","indicators":["sma","ema_stack","adx_dmi","supertrend","ichimoku","psar","hidden_divergence","atr","order_block","fvg","volume_ratio","market_session"]},
    {"id":"SPOT_BREAKOUT_RETEST_ACCUMULATION","actions":["COMPRA_SPOT"],"family":"BREAKOUT_RETEST","indicators":["squeeze","ftmaverick","bollinger","macd","adx_dmi","volume_ratio","force_index","obv","hvn_lvn","fibonacci","candlestick_patterns","market_session"]},
    {"id":"SPOT_CEILING_DISTRIBUTION","actions":["VENTA_SPOT"],"family":"SWEEP_REVERSAL","indicators":["rsi","rsi_maverick","regular_divergence","liquidity_sweep","stop_hunt","order_block","volume_ratio","mfi","whale_proxy","atr","support_resistance"]},
    {"id":"SPOT_OVEREXTENSION_EXIT","actions":["VENTA_SPOT"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","cci","stochastic","williams_r","mfi","volume_profile_poc","hvn_lvn","candlestick_patterns","support_resistance","sentiment"]},
    {"id":"SPOT_TREND_BREAK_EXIT","actions":["VENTA_SPOT"],"family":"TREND_BREAK","indicators":["ema_stack","adx_dmi","supertrend","ichimoku","psar","macd","hidden_divergence","fvg","volume_ratio","obv","macro_context","correlation_rotation"]},
    {"id":"SPOT_BTC_PAXG_ROTATION","actions":["COMPRA_SPOT","VENTA_SPOT"],"family":"ROTATION","indicators":["correlation_rotation","macro_context","sentiment","sma","ema_stack","adx_dmi","rsi","vwap","volume_profile_poc","hvn_lvn","market_session"]},
    {"id":"FUT_LONG_SWEEP_MSS","actions":["LONG"],"family":"SWEEP_REVERSAL","indicators":["liquidity_sweep","stop_hunt","order_block","fvg","regular_divergence","hidden_divergence","rsi_maverick","volume_ratio","whale_proxy","iceberg","liquidation_map","atr","support_resistance"]},
    {"id":"FUT_LONG_BREAKOUT_RETEST","actions":["LONG"],"family":"BREAKOUT_RETEST","indicators":["squeeze","ftmaverick","bollinger","macd","adx_dmi","volume_ratio","force_index","obv","hvn_lvn","volume_profile_poc","fibonacci","candlestick_patterns","liquidation_map","market_session"]},
    {"id":"FUT_LONG_TREND_PULLBACK","actions":["LONG"],"family":"TREND_PULLBACK","indicators":["ema_stack","adx_dmi","supertrend","ichimoku","psar","rsi","hidden_divergence","atr","order_block","fvg","volume_ratio","macro_context"]},
    {"id":"FUT_LONG_VALUE_REVERSAL","actions":["LONG"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","rsi","stochastic","williams_r","cci","force_index","mfi","volume_profile_poc","support_resistance","regular_divergence","sentiment"]},
    {"id":"FUT_SHORT_SWEEP_MSS","actions":["SHORT"],"family":"SWEEP_REVERSAL","indicators":["liquidity_sweep","stop_hunt","order_block","fvg","regular_divergence","hidden_divergence","rsi_maverick","volume_ratio","whale_proxy","iceberg","liquidation_map","atr","support_resistance"]},
    {"id":"FUT_SHORT_BREAKDOWN_RETEST","actions":["SHORT"],"family":"BREAKOUT_RETEST","indicators":["squeeze","ftmaverick","bollinger","macd","adx_dmi","volume_ratio","force_index","obv","hvn_lvn","volume_profile_poc","fibonacci","candlestick_patterns","liquidation_map","market_session"]},
    {"id":"FUT_SHORT_TREND_PULLBACK","actions":["SHORT"],"family":"TREND_PULLBACK","indicators":["ema_stack","adx_dmi","supertrend","ichimoku","psar","rsi","hidden_divergence","atr","order_block","fvg","volume_ratio","macro_context"]},
    {"id":"FUT_SHORT_VALUE_REVERSAL","actions":["SHORT"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","rsi","stochastic","williams_r","cci","force_index","mfi","volume_profile_poc","support_resistance","regular_divergence","sentiment"]},
]


def coverage_counts() -> Dict[str, int]:
    c = Counter()
    for row in STRATEGIES:
        c.update(set(row.get("indicators") or []))
    return {k: int(c.get(k, 0)) for k in sorted(INDICATOR_UNIVERSE)}


def validate_bank() -> Dict[str, Any]:
    counts = coverage_counts()
    missing = sorted(k for k, n in counts.items() if n < 2)
    oversized = [r["id"] for r in STRATEGIES if len(set(r.get("indicators") or [])) >= len(INDICATOR_UNIVERSE)]
    return {"ok": not missing and not oversized, "missing_twice": missing, "oversized": oversized, "counts": counts}


def _u(v: Any) -> str:
    return str(v or "").upper()


def _f(v: Any, d: float = 0.0) -> float:
    try: return float(v if v is not None else d)
    except Exception: return d


def select_strategy(action: str, regime: str, vol_state: str, groups: Dict[str, Any], symbol: str = "") -> Dict[str, Any]:
    """Select one action-specialist playbook and a 0..100 technical quality score.

    This is deterministic and uses existing technical evidence only. It does not
    create statistical authority; the production publication gate remains final.
    """
    action = _u(action)
    regime = _u(regime)
    vol_state = _u(vol_state)
    candidates = [r for r in STRATEGIES if action in r.get("actions", [])]
    if not candidates:
        return {"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[]}

    m = groups.get("momentum") or {}; v = groups.get("volatility") or {}
    t = groups.get("trend") or {}; vf = groups.get("volume_flow") or {}
    st = groups.get("structure_liquidity") or {}; rot = groups.get("rotation") or {}
    direction = "LONG" if action in {"LONG","COMPRA_SPOT"} else "SHORT"
    rsi = _f(m.get("rsi"), 50); rsim = _f(m.get("rsi_maverick"), .5)
    divs = set(m.get("divergences") or []); hidden = set(m.get("hidden_divergences") or [])
    has_reversal = bool(st.get("has_liquidity_sweep") or st.get("has_stop_hunt") or divs)
    extreme = (direction == "LONG" and (rsi <= 42 or rsim <= .25)) or (direction == "SHORT" and (rsi >= 58 or rsim >= .75))
    rotation = _u(rot.get("signal")) not in {"","NONE","NEUTRAL"}

    if action in {"COMPRA_SPOT","VENTA_SPOT"} and rotation and "PAXG" in str(symbol).upper():
        family = "ROTATION"
    elif vol_state == "SQUEEZE": family = "BREAKOUT_RETEST"
    elif regime in {"RANGING","BALANCE","RANGE"} and (has_reversal or extreme): family = "SWEEP_REVERSAL"
    elif regime in {"RANGING","BALANCE","RANGE"}: family = "MEAN_REVERSION"
    elif vol_state == "HIGH_EXPANSION": family = "BREAKOUT_RETEST"
    else: family = "TREND_PULLBACK"

    chosen = next((r for r in candidates if r.get("family") == family), None) or candidates[0]
    confirmations=[]; score=0.0
    trend_dir=_u(t.get("direction")); mom_dir=_u(m.get("direction")); struct_dir=_u(st.get("direction"))
    wanted = "BULLISH" if direction == "LONG" else "BEARISH"
    if trend_dir == wanted: score += 16; confirmations.append("tendencia")
    if _f(t.get("adx")) >= 22: score += 10; confirmations.append("fuerza ADX/DMI")
    if mom_dir == wanted: score += 14; confirmations.append("momentum")
    if divs or hidden: score += 10; confirmations.append("divergencia")
    if struct_dir == wanted or st.get("has_order_blocks") or st.get("has_fvg"): score += 16; confirmations.append("estructura/POI")
    if st.get("has_liquidity_sweep") or st.get("has_stop_hunt"): score += 10; confirmations.append("liquidez")
    if _f(vf.get("volume_ratio"),1) >= 1.05 or vf.get("whale_buy") or vf.get("whale_sell") or vf.get("iceberg_buy") or vf.get("iceberg_sell"): score += 10; confirmations.append("volumen/flujo")
    if vol_state != "UNKNOWN": score += 7; confirmations.append("volatilidad")
    if _u((groups.get("macro") or {}).get("risk")) not in {"CRITICAL"}: score += 4
    if _u((groups.get("market_time") or {}).get("liquidity")) not in {"LOW","VERY_LOW"}: score += 3
    return {"id": chosen["id"], "family": chosen["family"], "quality": round(min(100.0, score),2), "confirmations": confirmations[:6], "indicators": list(chosen.get("indicators") or [])}


_BANK_VALIDATION = validate_bank()
if not _BANK_VALIDATION["ok"]:
    raise RuntimeError(f"RC8.4 strategy bank invalid: {_BANK_VALIDATION}")
