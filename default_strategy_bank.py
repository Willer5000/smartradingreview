"""Commit 9.4 — governed default strategy bank.

Technical fallback only.  A default playbook is not statistical alpha and can
never bypass the production Safety / Entry / SL / TP / economics gates.

Commit 9.4 closes two old gaps:
* every declared indicator has a *functional* rule used by the selector, not
  merely a name in metadata;
* correlated indicators are capped by evidence family so adding oscillators
  cannot manufacture confidence (anti-overfitting).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping

VERSION = "COMMIT9_4_DEFAULT_STRATEGY_BANK_V1"

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

# Sixteen compact families remain the stable default bank.  Commit 9.4 does
# not create hundreds of symbol-specific rules.  The same indicator may be
# useful in several playbooks but its actual value must pass a functional rule.
STRATEGIES: List[Dict[str, Any]] = [
    {"id":"SPOT_FLOOR_LIQUIDITY_ACCUMULATION","actions":["COMPRA_SPOT"],"family":"SWEEP_REVERSAL","indicators":["rsi","rsi_maverick","regular_divergence","liquidity_sweep","stop_hunt","order_block","volume_ratio","mfi","whale_proxy","atr","support_resistance"]},
    {"id":"SPOT_VALUE_RECLAIM","actions":["COMPRA_SPOT"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","rsi","stochastic","williams_r","mfi","obv","volume_profile_poc","hvn_lvn","candlestick_patterns","support_resistance"]},
    {"id":"SPOT_TREND_PULLBACK_ACCUMULATION","actions":["COMPRA_SPOT"],"family":"TREND_PULLBACK","indicators":["sma","ema_stack","adx_dmi","supertrend","ichimoku","psar","hidden_divergence","atr","order_block","fvg","volume_ratio","market_session","whale_proxy"]},
    {"id":"SPOT_BREAKOUT_RETEST_ACCUMULATION","actions":["COMPRA_SPOT"],"family":"BREAKOUT_RETEST","indicators":["squeeze","ftmaverick","bollinger","macd","adx_dmi","volume_ratio","force_index","obv","hvn_lvn","fibonacci","candlestick_patterns","market_session"]},
    {"id":"SPOT_CEILING_DISTRIBUTION","actions":["VENTA_SPOT"],"family":"SWEEP_REVERSAL","indicators":["rsi","rsi_maverick","regular_divergence","liquidity_sweep","stop_hunt","order_block","volume_ratio","mfi","whale_proxy","atr","support_resistance"]},
    {"id":"SPOT_OVEREXTENSION_EXIT","actions":["VENTA_SPOT"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","cci","stochastic","williams_r","mfi","volume_profile_poc","hvn_lvn","candlestick_patterns","support_resistance","sentiment"]},
    {"id":"SPOT_TREND_BREAK_EXIT","actions":["VENTA_SPOT"],"family":"TREND_BREAK","indicators":["ema_stack","adx_dmi","supertrend","ichimoku","psar","macd","hidden_divergence","fvg","volume_ratio","obv","macro_context","correlation_rotation"]},
    {"id":"SPOT_BTC_PAXG_ROTATION","actions":["COMPRA_SPOT","VENTA_SPOT"],"family":"ROTATION","indicators":["correlation_rotation","macro_context","sentiment","sma","ema_stack","adx_dmi","rsi","vwap","volume_profile_poc","hvn_lvn","market_session"]},
    {"id":"FUT_LONG_SWEEP_MSS","actions":["LONG"],"family":"SWEEP_REVERSAL","indicators":["liquidity_sweep","stop_hunt","order_block","fvg","regular_divergence","hidden_divergence","rsi_maverick","volume_ratio","whale_proxy","iceberg","liquidation_map","atr","support_resistance"]},
    {"id":"FUT_LONG_BREAKOUT_RETEST","actions":["LONG"],"family":"BREAKOUT_RETEST","indicators":["squeeze","ftmaverick","bollinger","macd","adx_dmi","volume_ratio","force_index","obv","hvn_lvn","volume_profile_poc","fibonacci","candlestick_patterns","liquidation_map","market_session"]},
    {"id":"FUT_LONG_TREND_PULLBACK","actions":["LONG"],"family":"TREND_PULLBACK","indicators":["ema_stack","adx_dmi","supertrend","ichimoku","psar","rsi","hidden_divergence","atr","order_block","fvg","volume_ratio","macro_context","whale_proxy"]},
    {"id":"FUT_LONG_VALUE_REVERSAL","actions":["LONG"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","rsi","stochastic","williams_r","cci","force_index","mfi","volume_profile_poc","support_resistance","regular_divergence","sentiment"]},
    {"id":"FUT_SHORT_SWEEP_MSS","actions":["SHORT"],"family":"SWEEP_REVERSAL","indicators":["liquidity_sweep","stop_hunt","order_block","fvg","regular_divergence","hidden_divergence","rsi_maverick","volume_ratio","whale_proxy","iceberg","liquidation_map","atr","support_resistance"]},
    {"id":"FUT_SHORT_BREAKDOWN_RETEST","actions":["SHORT"],"family":"BREAKOUT_RETEST","indicators":["squeeze","ftmaverick","bollinger","macd","adx_dmi","volume_ratio","force_index","obv","hvn_lvn","volume_profile_poc","fibonacci","candlestick_patterns","liquidation_map","market_session"]},
    {"id":"FUT_SHORT_TREND_PULLBACK","actions":["SHORT"],"family":"TREND_PULLBACK","indicators":["ema_stack","adx_dmi","supertrend","ichimoku","psar","rsi","hidden_divergence","atr","order_block","fvg","volume_ratio","macro_context"]},
    {"id":"FUT_SHORT_VALUE_REVERSAL","actions":["SHORT"],"family":"MEAN_REVERSION","indicators":["vwap","bollinger","rsi","stochastic","williams_r","cci","force_index","mfi","volume_profile_poc","support_resistance","regular_divergence","sentiment"]},
]

RC9_SUPPORTED = {
    "SPOT": {
        "symbols": ["BTC-USDT", "PAXG-USDT", "PAXG-BTC"],
        "timeframes": ["4H", "12H", "1D", "1W"],
        "actions": ["COMPRA_SPOT", "VENTA_SPOT"],
    },
    "FUTURES": {
        "symbols": ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT", "BNB-USDT", "LINK-USDT"],
        "timeframes": ["30M", "1H", "2H", "4H", "12H", "1D"],
        "actions": ["LONG", "SHORT"],
    },
}

_FAMILY_TIMEFRAMES = {
    "SPOT": {
        "SWEEP_REVERSAL": ["4H", "12H", "1D"],
        "MEAN_REVERSION": ["4H", "12H", "1D"],
        "TREND_PULLBACK": ["4H", "12H", "1D", "1W"],
        "BREAKOUT_RETEST": ["4H", "12H", "1D"],
        "TREND_BREAK": ["4H", "12H", "1D", "1W"],
        "ROTATION": ["4H", "12H", "1D", "1W"],
    },
    "FUTURES": {
        "SWEEP_REVERSAL": ["30M", "1H", "2H", "4H"],
        "MEAN_REVERSION": ["30M", "1H", "2H"],
        "TREND_PULLBACK": ["1H", "2H", "4H", "12H", "1D"],
        "BREAKOUT_RETEST": ["30M", "1H", "2H", "4H", "12H"],
    },
}

_FAMILY_REGIMES = {
    "SWEEP_REVERSAL": ["BALANCE", "RANGE", "RANGING", "TRANSITION", "TREND_UP", "TREND_DOWN"],
    "MEAN_REVERSION": ["BALANCE", "RANGE", "RANGING", "TRANSITION"],
    "TREND_PULLBACK": ["TREND_UP", "TREND_DOWN", "TRANSITION"],
    "BREAKOUT_RETEST": ["BALANCE", "RANGE", "RANGING", "TRANSITION", "TREND_UP", "TREND_DOWN", "VOLATILITY_SHOCK"],
    "TREND_BREAK": ["TREND_UP", "TREND_DOWN", "TRANSITION", "VOLATILITY_SHOCK"],
    "ROTATION": ["BALANCE", "TREND_UP", "TREND_DOWN", "TRANSITION", "VOLATILITY_SHOCK"],
}
_FAMILY_VOLATILITY = {
    "SWEEP_REVERSAL": ["LOW", "NORMAL", "EXPANSION", "COMPRESSION"],
    "MEAN_REVERSION": ["LOW", "NORMAL", "COMPRESSION"],
    "TREND_PULLBACK": ["LOW", "NORMAL", "EXPANSION"],
    "BREAKOUT_RETEST": ["COMPRESSION", "NORMAL", "EXPANSION", "SHOCK"],
    "TREND_BREAK": ["NORMAL", "EXPANSION", "SHOCK"],
    "ROTATION": ["LOW", "NORMAL", "EXPANSION", "SHOCK"],
}

# Correlated tools share a cap.  This is the anti-overfitting contract: e.g.
# RSI+Stochastic+CCI do not become three independent confirmations.
INDICATOR_RULES: Dict[str, Dict[str, str]] = {
    "sma":{"family":"trend","role":"contexto"}, "ema_stack":{"family":"trend","role":"contexto"},
    "adx_dmi":{"family":"trend","role":"confirmacion"}, "supertrend":{"family":"trend","role":"confirmacion"},
    "ichimoku":{"family":"trend","role":"confirmacion"}, "psar":{"family":"trend","role":"confirmacion"},
    "rsi":{"family":"momentum","role":"confirmacion"}, "rsi_maverick":{"family":"momentum","role":"confirmacion"},
    "macd":{"family":"momentum","role":"confirmacion"}, "stochastic":{"family":"momentum","role":"confirmacion"},
    "williams_r":{"family":"momentum","role":"confirmacion"}, "cci":{"family":"momentum","role":"confirmacion"},
    "regular_divergence":{"family":"momentum","role":"confirmacion"}, "hidden_divergence":{"family":"momentum","role":"confirmacion"},
    "atr":{"family":"volatility","role":"riesgo"}, "bollinger":{"family":"volatility","role":"contexto"},
    "ftmaverick":{"family":"volatility","role":"confirmacion"}, "squeeze":{"family":"volatility","role":"confirmacion"},
    "volume_ratio":{"family":"flow","role":"confirmacion"}, "force_index":{"family":"flow","role":"confirmacion"},
    "mfi":{"family":"flow","role":"confirmacion"}, "obv":{"family":"flow","role":"confirmacion"},
    "whale_proxy":{"family":"flow","role":"contexto"}, "iceberg":{"family":"flow","role":"confirmacion"},
    "vwap":{"family":"value","role":"entry"}, "volume_profile_poc":{"family":"value","role":"entry"},
    "hvn_lvn":{"family":"value","role":"entry"},
    "order_block":{"family":"structure","role":"entry"}, "fvg":{"family":"structure","role":"entry"},
    "liquidity_sweep":{"family":"structure","role":"entry"}, "stop_hunt":{"family":"structure","role":"entry"},
    "support_resistance":{"family":"structure","role":"invalidacion"}, "fibonacci":{"family":"structure","role":"entry"},
    "candlestick_patterns":{"family":"structure","role":"confirmacion"},
    "liquidation_map":{"family":"execution","role":"riesgo"}, "sentiment":{"family":"context","role":"contexto"},
    "macro_context":{"family":"context","role":"riesgo"}, "correlation_rotation":{"family":"context","role":"contexto"},
    "market_session":{"family":"execution","role":"riesgo"},
}


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v if v is not None else d)
    except Exception:
        return float(d)


def _bool_dir(value: Any) -> int:
    raw = _u(value)
    if raw in {"BULLISH","LONG","UP","TREND_UP","COMPRA_SPOT","STRONG_UP","WEAK_UP"}: return 1
    if raw in {"BEARISH","SHORT","DOWN","TREND_DOWN","VENTA_SPOT","STRONG_DOWN","WEAK_DOWN"}: return -1
    return 0


def _contains_direction(items: Any, side: int) -> bool:
    blob = " ".join(str(x).lower() for x in (items or []))
    return (side > 0 and ("bull" in blob or "alcist" in blob)) or (side < 0 and ("bear" in blob or "bajist" in blob))


def _proximity(price: float, levels: Any, pct: float = 0.012) -> bool:
    if price <= 0: return False
    vals: List[float] = []
    if isinstance(levels, Mapping):
        for value in levels.values():
            try: vals.append(float(value))
            except Exception: pass
    elif isinstance(levels, (list, tuple)):
        for row in levels:
            value = row.get("price") if isinstance(row, Mapping) else row
            try: vals.append(float(value))
            except Exception: pass
    return any(v > 0 and abs(price-v)/price <= pct for v in vals)


def _indicator_effect(name: str, groups: Mapping[str, Any], *, side: int, family: str, market: str, timeframe: str) -> Dict[str, Any]:
    """Return -1..+1 alignment *from the requested action's perspective*.

    `available=False` means no live value was supplied; missing data never gains
    points.  Context/risk tools can be useful without choosing direction.
    """
    t = dict(groups.get("trend") or {}); m = dict(groups.get("momentum") or {})
    v = dict(groups.get("volatility") or {}); f = dict(groups.get("volume_flow") or {})
    s = dict(groups.get("structure_liquidity") or {}); liq = dict(groups.get("liquidations") or {})
    sent = dict(groups.get("sentiment") or {}); macro = dict(groups.get("macro") or {})
    rot = dict(groups.get("rotation") or {}); mt = dict(groups.get("market_time") or {})
    mtf = dict(groups.get("multi_timeframe") or {})
    price = _f(s.get("current_price"))
    detail = ""; effect = 0.0; available = True

    if name == "sma":
        a,b=_f(t.get("sma20")),_f(t.get("sma50")); available=bool(a and b)
        sig=1 if available and a>b else -1 if available and a<b else 0; effect=sig*side; detail=f"SMA20 {a:.2f} / SMA50 {b:.2f}"
    elif name == "ema_stack":
        e9,e21,e50,e200=(_f(t.get(k)) for k in ("ema9","ema21","ema50","ema200")); available=bool(e9 and e21 and e50 and e200)
        sig=1 if e9>e21>e50>e200 else -1 if e9<e21<e50<e200 else 0; effect=sig*side; detail="alineación EMA 9/21/50/200"
    elif name == "adx_dmi":
        adx,pd,md=_f(t.get("adx")),_f(t.get("plus_di")),_f(t.get("minus_di")); available=bool(adx or pd or md)
        sig=1 if pd>md+2 else -1 if md>pd+2 else 0; effect=(sig*side)*(1.0 if adx>=25 else .55 if adx>=18 else .25); detail=f"ADX {adx:.1f}; +DI {pd:.1f}; -DI {md:.1f}"
    elif name in {"supertrend","ichimoku","psar"}:
        key={"supertrend":"supertrend","ichimoku":"ichimoku_cloud","psar":"psar"}[name]; raw=t.get(key); available=raw not in (None,"",0,"NEUTRAL")
        effect=_bool_dir(raw)*side; detail=f"{name} {_u(raw).lower()}"
    elif name == "rsi":
        x=_f(m.get("rsi"),50); available=m.get("rsi") is not None
        sig=1 if x>=52 else -1 if x<=48 else 0
        if family in {"MEAN_REVERSION","SWEEP_REVERSAL"}: sig=1 if x<=42 else -1 if x>=58 else 0
        effect=sig*side; detail=f"RSI {x:.1f}"
    elif name == "rsi_maverick":
        x=_f(m.get("rsi_maverick"),.5); available=m.get("rsi_maverick") is not None
        sig=1 if x<=.25 else -1 if x>=.75 else (1 if x>.55 and family=="TREND_PULLBACK" else -1 if x<.45 and family=="TREND_PULLBACK" else 0)
        effect=sig*side; detail=f"RSI Maverick {x:.2f}"
    elif name == "macd":
        x=_f(m.get("macd_histogram")); available=m.get("macd_histogram") is not None; effect=(1 if x>0 else -1 if x<0 else 0)*side; detail=f"MACD hist {x:.4f}"
    elif name == "stochastic":
        k,d=_f(m.get("stoch_k"),50),_f(m.get("stoch_d"),50); available=m.get("stoch_k") is not None
        sig=1 if (k<30 and k>=d) else -1 if (k>70 and k<=d) else 0; effect=sig*side; detail=f"Stoch {k:.1f}/{d:.1f}"
    elif name == "williams_r":
        x=_f(m.get("williams"),-50); available=m.get("williams") is not None; sig=1 if x<-80 else -1 if x>-20 else 0; effect=sig*side; detail=f"Williams %R {x:.1f}"
    elif name == "cci":
        x=_f(m.get("cci")); available=m.get("cci") is not None; sig=1 if x<-100 else -1 if x>100 else (1 if x>25 and family=="TREND_PULLBACK" else -1 if x<-25 and family=="TREND_PULLBACK" else 0); effect=sig*side; detail=f"CCI {x:.1f}"
    elif name == "regular_divergence":
        rows=m.get("divergences") or []; available=bool(rows); effect=1.0 if _contains_direction(rows,side) else -1.0 if _contains_direction(rows,-side) else 0.0; detail="divergencia regular"
    elif name == "hidden_divergence":
        rows=m.get("hidden_divergences") or []; available=bool(rows); effect=1.0 if _contains_direction(rows,side) else -1.0 if _contains_direction(rows,-side) else 0.0; detail="divergencia oculta de continuación"
    elif name == "atr":
        x=_f(v.get("atr_pct")); available=x>0; effect=.35 if 0<x<=4 else -.55 if x>=8 else 0.0; detail=f"ATR {x:.2f}%"
    elif name == "bollinger":
        pos=_f(v.get("bb_position"),.5); available=v.get("bb_position") is not None
        if family in {"MEAN_REVERSION","SWEEP_REVERSAL"}: sig=1 if pos<=.25 else -1 if pos>=.75 else 0
        else: sig=1 if pos>=.6 else -1 if pos<=.4 else 0
        effect=sig*side; detail=f"posición Bollinger {pos:.2f}"
    elif name == "ftmaverick":
        raw=v.get("ftm_state"); available=raw not in (None,"","NEUTRAL"); effect=_bool_dir(raw)*side; detail=f"Fuerza Maverick {_u(raw)}"
    elif name == "squeeze":
        on=bool(v.get("squeeze_on")); length=int(_f(v.get("squeeze_length"))); available=(v.get("squeeze_on") is not None)
        effect=.75 if on and family=="BREAKOUT_RETEST" and length<12 else -.35 if on and length>=12 else 0.0; detail=f"squeeze {'activo' if on else 'inactivo'} ({length} velas)"
    elif name == "volume_ratio":
        x=_f(f.get("volume_ratio"),1); available=f.get("volume_ratio") is not None; effect=.65 if x>=1.2 else .25 if x>=1.05 else -.45 if x<.65 else 0.0; detail=f"volumen {x:.2f}x"
    elif name == "force_index":
        x=_f(f.get("force_index")); available=f.get("force_index") is not None; effect=(1 if x>0 else -1 if x<0 else 0)*side; detail="Force Index"
    elif name == "mfi":
        x=_f(f.get("mfi"),50); available=f.get("mfi") is not None
        sig=1 if x>=55 else -1 if x<=45 else 0
        if family in {"MEAN_REVERSION","SWEEP_REVERSAL"}: sig=1 if x<=35 else -1 if x>=65 else 0
        effect=sig*side; detail=f"MFI {x:.1f}"
    elif name == "obv":
        raw=f.get("obv_trend"); available=raw not in (None,"","NEUTRAL"); effect=_bool_dir(raw)*side; detail=f"OBV {_u(raw).lower()}"
    elif name == "whale_proxy":
        # Anomalous-volume reaction: event or confirmed reaction may remain valid
        # for up to seven source bars.  12H/1D/1W context may support a 4H entry.
        wc=dict(mtf.get("whale_context") or {}); age=wc.get("age_bars")
        buy=bool(f.get("whale_buy") or wc.get("buy_confirmed")); sell=bool(f.get("whale_sell") or wc.get("sell_confirmed"))
        pending_buy=bool(wc.get("pending_buy")); pending_sell=bool(wc.get("pending_sell"))
        available=bool(buy or sell or pending_buy or pending_sell or f.get("whale_event_pending"))
        sig=1 if buy else -1 if sell else 1 if pending_buy else -1 if pending_sell else 0
        # Higher-timeframe accumulation is deliberately more useful for LONG /
        # spot accumulation than for a short thesis, as requested by the desk.
        strength=1.0 if (sig==side and side>0) else .70 if sig==side else 1.0
        if (pending_buy or pending_sell) and not (buy or sell): strength*=.55
        effect=sig*side*strength; detail=f"reacción a volumen anómalo, edad {age if age is not None else '--'} velas"
    elif name == "iceberg":
        buy,sell=bool(f.get("iceberg_buy")),bool(f.get("iceberg_sell")); available=buy or sell; sig=1 if buy else -1 if sell else 0; effect=sig*side*.65; detail="proxy de absorción volumen/precio"
    elif name == "vwap":
        x=_f(f.get("vwap")); available=bool(x and price)
        if available:
            sig=1 if price>x else -1 if price<x else 0
            if family=="MEAN_REVERSION": sig=-sig
            effect=sig*side
        detail=f"VWAP {x:.2f}"
    elif name == "volume_profile_poc":
        poc=_f(s.get("poc")); available=bool(poc and price); sig=1 if available and price>=poc else -1 if available else 0; effect=sig*side*.7; detail=f"POC {poc:.2f}"
    elif name == "hvn_lvn":
        available=bool(s.get("hvn_nodes") or s.get("lvn_nodes")); effect=.45 if available and (_proximity(price,s.get("hvn_nodes"),.015) or _proximity(price,s.get("lvn_nodes"),.012)) else 0.0; detail="nodo de volumen cercano"
    elif name in {"order_block","fvg","liquidity_sweep","stop_hunt"}:
        key={"order_block":"order_block_directions","fvg":"fvg_directions","liquidity_sweep":"sweep_directions","stop_hunt":"stop_hunt_directions"}[name]; rows=s.get(key) or []; available=bool(rows)
        wanted="BULLISH" if side>0 else "BEARISH"; opposite="BEARISH" if side>0 else "BULLISH"
        effect=1.0 if wanted in rows else -1.0 if opposite in rows else 0.0; detail=name.replace('_',' ')
    elif name == "support_resistance":
        sup,res=_f(s.get("support")),_f(s.get("resistance")); available=bool(price and (sup or res))
        if side>0: effect=.8 if sup and abs(price-sup)/price<=.02 else -.7 if res and abs(res-price)/price<=.006 else 0.0
        else: effect=.8 if res and abs(res-price)/price<=.02 else -.7 if sup and abs(price-sup)/price<=.006 else 0.0
        detail="soporte/resistencia"
    elif name == "fibonacci":
        levels=s.get("fib_levels") or {}; available=bool(levels); effect=.65 if available and _proximity(price,levels,.012) else 0.0; detail="zona Fibonacci"
    elif name == "candlestick_patterns":
        bull,bear=int(_f(s.get("bullish_patterns_count"))),int(_f(s.get("bearish_patterns_count"))); available=(bull+bear)>0; sig=1 if bull>bear else -1 if bear>bull else 0; effect=sig*side*.7; detail=f"patrones {bull} alcistas / {bear} bajistas"
    elif name == "liquidation_map":
        lw,sw=_f(liq.get("long_weight")),_f(liq.get("short_weight")); available=bool(lw or sw or liq.get("events"));
        # map is execution context, not a direction oracle: opposing pool raises risk
        if available and lw+sw>0:
            dominant=1 if sw>lw*1.15 else -1 if lw>sw*1.15 else 0; effect=dominant*side*.45
        detail="mapa de liquidaciones"
    elif name == "sentiment":
        raw=sent.get("bias"); available=raw not in (None,"","NEUTRAL"); effect=_bool_dir(raw)*side*.45; detail=f"sentimiento {_u(raw).lower()}"
    elif name == "macro_context":
        risk=_u(macro.get("risk")); raw=macro.get("bias"); available=bool(macro.get("available")); effect=_bool_dir(raw)*side*.35
        if market=="FUTURES" and risk=="CRITICAL": effect=-1.0
        detail=f"macro {risk or 'normal'}"
    elif name == "correlation_rotation":
        raw=rot.get("signal"); available=raw not in (None,"","NEUTRAL"); effect=.7 if available else 0.0; detail=f"rotación {_u(raw)}"
    elif name == "market_session":
        liquidity=_u(mt.get("liquidity")); available=bool(mt.get("available")); effect=.35 if liquidity not in {"LOW","VERY_LOW"} else -.75; detail=f"liquidez de sesión {liquidity or 'desconocida'}"
    else:
        available=False

    return {"indicator":name,"family":INDICATOR_RULES[name]["family"],"role":INDICATOR_RULES[name]["role"],"available":bool(available),"effect":round(max(-1.0,min(1.0,effect)),3),"detail":detail[:150]}


def coverage_counts() -> Dict[str, int]:
    c=Counter()
    for row in STRATEGIES: c.update(set(row.get("indicators") or []))
    return {k:int(c.get(k,0)) for k in sorted(INDICATOR_UNIVERSE)}


def _functional_probe_groups(side: int, family: str) -> Dict[str, Any]:
    """Synthetic market state used only by startup tests.

    It does not optimize thresholds. It verifies that a declared component can
    actually alter strategy evaluation through its live rule. A component whose
    rule always returns zero would fail Commit 9.4 even if listed in metadata.
    """
    bullish = side > 0
    mean = family in {"MEAN_REVERSION", "SWEEP_REVERSAL"}
    price = 100.0
    if bullish:
        sma20, sma50 = 105.0, 100.0
        ema9, ema21, ema50, ema200 = 109.0, 107.0, 104.0, 100.0
        rsi = 35.0 if mean else 60.0
        rsim = .20 if mean else .65
        stoch_k, stoch_d = 20.0, 15.0
        williams, cci = -85.0, (-120.0 if mean else 50.0)
        bbpos = .20 if mean else .70
        mfi = 30.0 if mean else 60.0
        vwap = 105.0 if mean else 95.0
        poc = 95.0
        support, resistance = 99.0, 106.0
        liq_long, liq_short = 5.0, 20.0
        raw_dir = "BULLISH"
        opposite = "BEARISH"
    else:
        sma20, sma50 = 95.0, 100.0
        ema9, ema21, ema50, ema200 = 91.0, 93.0, 96.0, 100.0
        rsi = 65.0 if mean else 40.0
        rsim = .80 if mean else .35
        stoch_k, stoch_d = 80.0, 85.0
        williams, cci = -15.0, (120.0 if mean else -50.0)
        bbpos = .80 if mean else .30
        mfi = 70.0 if mean else 40.0
        vwap = 95.0 if mean else 105.0
        poc = 105.0
        support, resistance = 94.0, 101.0
        liq_long, liq_short = 20.0, 5.0
        raw_dir = "BEARISH"
        opposite = "BULLISH"
    return {
        "trend": {
            "available": True, "direction": raw_dir,
            "adx": 30.0, "plus_di": 30.0 if bullish else 10.0,
            "minus_di": 10.0 if bullish else 30.0,
            "sma20": sma20, "sma50": sma50,
            "ema9": ema9, "ema21": ema21, "ema50": ema50, "ema200": ema200,
            "supertrend": raw_dir, "ichimoku_cloud": raw_dir,
            "ichimoku_tk": raw_dir, "psar": raw_dir,
        },
        "momentum": {
            "available": True, "direction": raw_dir, "rsi": rsi,
            "rsi_maverick": rsim, "macd_histogram": 1.0 if bullish else -1.0,
            "divergences": ["bullish_regular"] if bullish else ["bearish_regular"],
            "hidden_divergences": ["bullish_hidden"] if bullish else ["bearish_hidden"],
            "stoch_k": stoch_k, "stoch_d": stoch_d,
            "williams": williams, "cci": cci,
        },
        "volatility": {
            "available": True, "atr_pct": 2.0, "bb_position": bbpos,
            "bb_width": 2.0, "ftm_state": raw_dir,
            "squeeze_on": family == "BREAKOUT_RETEST", "squeeze_length": 4,
        },
        "volume_flow": {
            "available": True, "volume_ratio": 1.40,
            "force_index": 10.0 if bullish else -10.0, "mfi": mfi,
            "obv_trend": raw_dir, "vwap": vwap,
            "whale_buy": bullish, "whale_sell": not bullish,
            "whale_event_pending": False,
            "iceberg_buy": bullish, "iceberg_sell": not bullish,
        },
        "structure_liquidity": {
            "available": True, "current_price": price, "direction": raw_dir,
            "support": support, "resistance": resistance,
            "fib_levels": {"0.618": 100.5}, "poc": poc,
            "hvn_nodes": [{"price": 100.4}], "lvn_nodes": [{"price": 99.4}],
            "order_block_directions": [raw_dir], "fvg_directions": [raw_dir],
            "sweep_directions": [raw_dir], "stop_hunt_directions": [raw_dir],
            "bullish_patterns_count": 3 if bullish else 1,
            "bearish_patterns_count": 1 if bullish else 3,
        },
        "liquidations": {
            "available": True, "long_weight": liq_long,
            "short_weight": liq_short, "events": 2,
        },
        "sentiment": {"available": True, "bias": raw_dir, "value": 60 if bullish else 40},
        "macro": {"available": True, "risk": "NORMAL", "bias": raw_dir},
        "rotation": {"available": True, "signal": "BTC_TO_PAXG" if bullish else "PAXG_TO_BTC"},
        "market_time": {"available": True, "liquidity": "HIGH", "session": "ACTIVE"},
        "multi_timeframe": {
            "whale_context": {
                "active": True, "age_bars": 2,
                "buy_confirmed": bullish, "sell_confirmed": not bullish,
                "pending_buy": False, "pending_sell": False,
            }
        },
    }


def functional_coverage_audit() -> Dict[str, Any]:
    counts=coverage_counts()
    missing_twice=sorted(k for k,n in counts.items() if n<2)
    missing_rule=sorted(INDICATOR_UNIVERSE-set(INDICATOR_RULES))
    oversized=[r["id"] for r in STRATEGIES if len(set(r.get("indicators") or []))>=len(INDICATOR_UNIVERSE)]
    weak=[]
    functional_counts=Counter()
    for row in STRATEGIES:
        fams={INDICATOR_RULES[i]["family"] for i in row.get("indicators",[]) if i in INDICATOR_RULES}
        if len(fams)<3: weak.append(row["id"])
        actions=list(row.get("actions") or [])
        action=actions[0] if actions else "COMPRA_SPOT"
        side=1 if action in {"LONG","COMPRA_SPOT"} else -1
        market="FUTURES" if action in {"LONG","SHORT"} else "SPOT"
        family=_u(row.get("family"))
        probe=_functional_probe_groups(side,family)
        for indicator in set(row.get("indicators") or []):
            if indicator not in INDICATOR_RULES:
                continue
            observed=_indicator_effect(
                indicator,probe,side=side,family=family,market=market,
                timeframe="2H" if market=="FUTURES" else "12H",
            )
            if observed.get("available") and abs(float(observed.get("effect") or 0))>=0.20:
                functional_counts[indicator]+=1
    missing_functional_twice=sorted(
        name for name in INDICATOR_UNIVERSE if int(functional_counts.get(name,0))<2
    )
    return {
        "ok":not(missing_twice or missing_rule or oversized or weak or missing_functional_twice),
        "missing_twice":missing_twice,
        "missing_functional_rule":missing_rule,
        "missing_functional_twice":missing_functional_twice,
        "functional_counts":{k:int(functional_counts.get(k,0)) for k in sorted(INDICATOR_UNIVERSE)},
        "oversized":oversized,"weak_family_diversity":weak,"counts":counts,
    }

def validate_bank() -> Dict[str, Any]:
    return functional_coverage_audit()


def _rc9_enrich_strategy(row: Dict[str, Any]) -> None:
    market="FUTURES" if any(a in {"LONG","SHORT"} for a in row.get("actions",[])) else "SPOT"
    family=_u(row.get("family"))
    row.setdefault("markets",[market])
    row.setdefault("symbols",list(RC9_SUPPORTED[market]["symbols"]))
    row.setdefault("timeframes",list(_FAMILY_TIMEFRAMES.get(market,{}).get(family,RC9_SUPPORTED[market]["timeframes"])))
    row.setdefault("regimes",list(_FAMILY_REGIMES.get(family,["BALANCE","TRANSITION","TREND_UP","TREND_DOWN"])))
    row.setdefault("volatility",list(_FAMILY_VOLATILITY.get(family,["LOW","NORMAL","EXPANSION"])))
    row["functional_roles"]={i:INDICATOR_RULES[i]["role"] for i in row.get("indicators",[]) if i in INDICATOR_RULES}


for _row in STRATEGIES: _rc9_enrich_strategy(_row)


def _tf(value: Any) -> str: return _u(value)


def coverage_matrix() -> Dict[str, Any]:
    try:
        from operational_intelligence import official_universe_cells
        cells=official_universe_cells()
    except Exception:
        cells=[]
    missing=[]
    for market,symbol,timeframe,action in cells:
        rows=[r for r in STRATEGIES if market in r.get("markets",[]) and symbol in r.get("symbols",[]) and timeframe in r.get("timeframes",[]) and action in r.get("actions",[])]
        if not rows: missing.append({"market":market,"symbol":symbol,"timeframe":timeframe,"action":action})
    return {"ok":len(cells)==92 and not missing,"checked":len(cells),"missing":missing}


def _choose_family(action: str, regime: str, vol_state: str, groups: Mapping[str, Any], symbol: str) -> str:
    m=groups.get("momentum") or {}; st=groups.get("structure_liquidity") or {}; rot=groups.get("rotation") or {}; mtf=groups.get("multi_timeframe") or {}
    direction=1 if action in {"LONG","COMPRA_SPOT"} else -1
    rsi=_f(m.get("rsi"),50); rsim=_f(m.get("rsi_maverick"),.5)
    divs=list(m.get("divergences") or [])
    has_reversal=bool(st.get("has_liquidity_sweep") or st.get("has_stop_hunt") or divs)
    extreme=(direction>0 and (rsi<=42 or rsim<=.25)) or (direction<0 and (rsi>=58 or rsim>=.75))
    rotation=_u(rot.get("signal")) not in {"","NONE","NEUTRAL"}
    whale=dict(mtf.get("whale_context") or {})
    # Confirmed/pending higher-TF anomalous-volume context is a *setup selector*,
    # never an automatic trade. Current-TF momentum/structure still has to pass.
    whale_reaction=bool(whale.get("active"))
    if action in {"COMPRA_SPOT","VENTA_SPOT"} and rotation and "PAXG" in symbol: return "ROTATION"
    if whale_reaction and direction>0 and regime in {"BALANCE","TRANSITION","TREND_UP"}: return "SWEEP_REVERSAL" if has_reversal or extreme else "TREND_PULLBACK"
    if vol_state in {"SQUEEZE","COMPRESSION"}: return "BREAKOUT_RETEST"
    if regime in {"RANGING","BALANCE","RANGE"} and (has_reversal or extreme): return "SWEEP_REVERSAL"
    if regime in {"RANGING","BALANCE","RANGE"}: return "MEAN_REVERSION"
    if vol_state in {"EXPANSION","SHOCK","HIGH_EXPANSION","VOLATILITY_SHOCK"}: return "BREAKOUT_RETEST"
    if action=="VENTA_SPOT" and regime in {"TREND_DOWN","TRANSITION"}: return "TREND_BREAK"
    return "TREND_PULLBACK"


def select_strategy(action: str, regime: str, vol_state: str, groups: Dict[str, Any], symbol: str="", timeframe: str="", market: str="") -> Dict[str, Any]:
    action=_u(action); regime=_u(regime) or "BALANCE"; vol_state=_u(vol_state) or "NORMAL"
    market=_u(market) or ("FUTURES" if action in {"LONG","SHORT"} else "SPOT"); symbol=_u(symbol); timeframe=_tf(timeframe)
    try:
        from operational_intelligence import is_official_cell
        if symbol and timeframe and not is_official_cell(market,symbol,timeframe,action):
            return {"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[],"indicators":[],"coverage_reason":"outside_governed_universe"}
    except Exception:
        pass
    candidates=[r for r in STRATEGIES if action in r.get("actions",[]) and market in r.get("markets",[]) and (not symbol or symbol in r.get("symbols",[])) and (not timeframe or timeframe in r.get("timeframes",[]))]
    if not candidates:
        return {"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[],"indicators":[],"coverage_reason":"unsupported_cell"}
    family=_choose_family(action,regime,vol_state,groups,symbol)
    preferred=[r for r in candidates if _u(r.get("family"))==family]
    chosen=preferred[0] if preferred else candidates[0]
    side=1 if action in {"LONG","COMPRA_SPOT"} else -1
    effects=[_indicator_effect(name,groups,side=side,family=_u(chosen.get("family")),market=market,timeframe=timeframe) for name in chosen.get("indicators",[]) if name in INDICATOR_RULES]
    available=[e for e in effects if e.get("available")]
    # Cap correlated evidence: at most the strongest positive and strongest
    # negative observation per family matter to quality.
    per_family=defaultdict(list)
    for e in available: per_family[e["family"]].append(e)
    family_effects={}
    for fam,rows in per_family.items():
        strongest=max(rows,key=lambda r:abs(float(r.get("effect") or 0)))
        family_effects[fam]=strongest
    positive=[e for e in family_effects.values() if float(e.get("effect") or 0)>=.25]
    negative=[e for e in family_effects.values() if float(e.get("effect") or 0)<=-.25]
    regime_match=regime in chosen.get("regimes",[]) or regime in {"","UNKNOWN"}
    vol_match=vol_state in chosen.get("volatility",[]) or vol_state in {"","UNKNOWN"}
    # Base + context + independent family alignment. Missing values never score.
    score=48.0 + (8.0 if regime_match else -12.0) + (7.0 if vol_match else -10.0)
    score += sum(max(-1.0,min(1.0,float(e["effect"]))) * 7.0 for e in family_effects.values())
    # Futures needs at least four independent positive families; Spot three.
    minimum=4 if market=="FUTURES" else 3
    if len(positive)<minimum: score-=8.0*(minimum-len(positive))
    score=max(0.0,min(100.0,score))
    confirmations=[e["detail"] for e in positive if e.get("detail")][:6]
    conflicts=[e["detail"] for e in negative if e.get("detail")][:4]
    return {
        "id":chosen["id"],"family":chosen["family"],"quality":round(score,2),
        "confirmations":confirmations,"conflicts":conflicts,"indicators":list(chosen.get("indicators") or []),
        "functional_evidence":available,"independent_functional_families":sorted(family_effects),
        "positive_functional_families":len(positive),"negative_functional_families":len(negative),
        "market":market,"symbol":symbol,"timeframe":timeframe,"regime_match":regime_match,"volatility_match":vol_match,
    }


_BANK_VALIDATION=functional_coverage_audit()
if not _BANK_VALIDATION["ok"]:
    raise RuntimeError(f"Commit 9.4 strategy bank invalid: {_BANK_VALIDATION}")
_RC9_MATRIX=coverage_matrix()
if not _RC9_MATRIX["ok"]:
    raise RuntimeError(f"Commit 9.4 default coverage incomplete: {_RC9_MATRIX}")
