"""RC9 final default strategy bank.

Fallback/contingency playbooks only. They never become statistical Champions
without Research/OOS/Shadow validation. The bank gives every technical input a
real role in at least two specialized playbooks while avoiding the anti-pattern
of putting every indicator in one giant strategy.
"""
from __future__ import annotations
from collections import Counter
from typing import Any, Dict, List

VERSION = "RC9_2_DEFAULT_STRATEGY_BANK_V1"

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

# ============================== RC9 FINAL ==============================
# Metadata de elegibilidad.  Las familias siguen siendo compactas para evitar
# sobreajuste; la selección se especializa por mercado, símbolo, temporalidad,
# acción, régimen y volatilidad usando evidencia ya calculada.
RC9_SUPPORTED = {
    "SPOT": {
        "symbols": ["BTC-USDT", "PAXG-USDT", "PAXG-BTC"],
        "timeframes": ["4H", "12H", "1D", "1W"],
        "actions": ["COMPRA_SPOT", "VENTA_SPOT"],
    },
    "FUTURES": {
        "symbols": ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT", "BNB-USDT", "LINK-USDT"],
        # Execution core. 12H/1D are added per symbol only where the governed
        # Research universe contains those cells (BTC/ETH/SOL).
        "timeframes": ["30M", "1H", "2H", "4H", "12H", "1D"],
        "actions": ["LONG", "SHORT"],
    },
}

# Family/timeframe preferences are technical defaults, not learned alpha. A
# strategy is not made universal merely to fill a matrix.
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


def _rc9_enrich_strategy(row: Dict[str, Any]) -> None:
    market = "FUTURES" if any(a in {"LONG", "SHORT"} for a in row.get("actions", [])) else "SPOT"
    family = str(row.get("family") or "").upper()
    row.setdefault("markets", [market])
    row.setdefault("symbols", list(RC9_SUPPORTED[market]["symbols"]))
    row.setdefault("timeframes", list(_FAMILY_TIMEFRAMES.get(market, {}).get(family, RC9_SUPPORTED[market]["timeframes"])))
    row.setdefault("regimes", list(_FAMILY_REGIMES.get(family, ["BALANCE", "TRANSITION", "TREND_UP", "TREND_DOWN"])))
    row.setdefault("volatility", list(_FAMILY_VOLATILITY.get(family, ["LOW", "NORMAL", "HIGH"])))
    # Un indicador sólo cuenta como funcional si participa en una de estas
    # tareas del setup.  Se declara por familia, no por activo, para evitar
    # memorizar el pasado de cada par.
    row.setdefault("roles", ["contexto", "confirmacion", "entry", "invalidacion", "objetivo"])


for _row in STRATEGIES:
    _rc9_enrich_strategy(_row)


def _tf(value: Any) -> str:
    return str(value or "").strip().upper()


def coverage_matrix() -> Dict[str, Any]:
    """Audit the exact 92 governed action cells.

    Coverage means at least one technically suitable Default family exists for
    the cell. It is not proof of profitability.
    """
    try:
        from operational_intelligence import official_universe_cells
        cells = official_universe_cells()
    except Exception:
        cells = []
    missing = []
    checked = 0
    for market, symbol, timeframe, action in cells:
        checked += 1
        rows = [
            r for r in STRATEGIES
            if market in r.get("markets", [])
            and symbol in r.get("symbols", [])
            and timeframe in r.get("timeframes", [])
            and action in r.get("actions", [])
        ]
        if not rows:
            missing.append({"market":market,"symbol":symbol,"timeframe":timeframe,"action":action})
    return {"ok": not missing and checked == 92, "checked": checked, "missing": missing}


# Replace RC8 selector with RC9 context-aware version while keeping backwards
# compatibility for old callers that do not yet provide market/timeframe.
def select_strategy(action: str, regime: str, vol_state: str, groups: Dict[str, Any], symbol: str = "", timeframe: str = "", market: str = "") -> Dict[str, Any]:
    action = _u(action)
    regime = _u(regime) or "BALANCE"
    vol_state = _u(vol_state) or "NORMAL"
    market = _u(market) or ("FUTURES" if action in {"LONG", "SHORT"} else "SPOT")
    symbol = _u(symbol)
    timeframe = _tf(timeframe)

    try:
        from operational_intelligence import is_official_cell
        if symbol and timeframe and not is_official_cell(market, symbol, timeframe, action):
            return {"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[],"indicators":[],"coverage_reason":"outside_governed_universe"}
    except Exception:
        pass

    candidates = [r for r in STRATEGIES if action in r.get("actions", []) and market in r.get("markets", [])]
    if symbol:
        candidates = [r for r in candidates if symbol in r.get("symbols", [])]
    if timeframe:
        candidates = [r for r in candidates if timeframe in r.get("timeframes", [])]
    if not candidates:
        return {"id":"NO_PLAYBOOK","family":"NONE","quality":0.0,"confirmations":[],"indicators":[],"coverage_reason":"unsupported_cell"}

    m = groups.get("momentum") or {}; v = groups.get("volatility") or {}
    t = groups.get("trend") or {}; vf = groups.get("volume_flow") or {}
    st = groups.get("structure_liquidity") or {}; rot = groups.get("rotation") or {}
    direction = "LONG" if action in {"LONG","COMPRA_SPOT"} else "SHORT"
    rsi = _f(m.get("rsi"), 50); rsim = _f(m.get("rsi_maverick"), .5)
    divs = set(m.get("divergences") or []); hidden = set(m.get("hidden_divergences") or [])
    has_reversal = bool(st.get("has_liquidity_sweep") or st.get("has_stop_hunt") or divs)
    extreme = (direction == "LONG" and (rsi <= 42 or rsim <= .25)) or (direction == "SHORT" and (rsi >= 58 or rsim >= .75))
    rotation = _u(rot.get("signal")) not in {"","NONE","NEUTRAL"}

    # Family choice is driven by today's market state, not by historical memorization.
    if action in {"COMPRA_SPOT","VENTA_SPOT"} and rotation and "PAXG" in symbol:
        family = "ROTATION"
    elif vol_state in {"SQUEEZE", "COMPRESSION"}:
        family = "BREAKOUT_RETEST"
    elif regime in {"RANGING","BALANCE","RANGE"} and (has_reversal or extreme):
        family = "SWEEP_REVERSAL"
    elif regime in {"RANGING","BALANCE","RANGE"}:
        family = "MEAN_REVERSION"
    elif vol_state in {"EXPANSION", "SHOCK", "HIGH_EXPANSION", "VOLATILITY_SHOCK"}:
        family = "BREAKOUT_RETEST"
    elif action == "VENTA_SPOT" and regime in {"TREND_DOWN", "TRANSITION"}:
        family = "TREND_BREAK"
    else:
        family = "TREND_PULLBACK"

    preferred = [r for r in candidates if r.get("family") == family]
    chosen = preferred[0] if preferred else candidates[0]

    confirmations=[]; score=0.0
    trend_dir=_u(t.get("direction")); mom_dir=_u(m.get("direction")); struct_dir=_u(st.get("direction"))
    wanted = "BULLISH" if direction == "LONG" else "BEARISH"
    if trend_dir == wanted: score += 16; confirmations.append("tendencia")
    if _f(t.get("adx")) >= 22: score += 10; confirmations.append("fuerza de tendencia")
    if mom_dir == wanted: score += 14; confirmations.append("momentum")
    if divs or hidden: score += 10; confirmations.append("divergencia")
    if struct_dir == wanted or st.get("has_order_blocks") or st.get("has_fvg"): score += 16; confirmations.append("estructura")
    if st.get("has_liquidity_sweep") or st.get("has_stop_hunt"): score += 10; confirmations.append("liquidez")
    if _f(vf.get("volume_ratio"),1) >= 1.05 or vf.get("whale_buy") or vf.get("whale_sell") or vf.get("iceberg_buy") or vf.get("iceberg_sell"): score += 10; confirmations.append("volumen")
    if vol_state != "UNKNOWN": score += 7; confirmations.append("volatilidad")
    if _u((groups.get("macro") or {}).get("risk")) not in {"CRITICAL"}: score += 4
    if _u((groups.get("market_time") or {}).get("liquidity")) not in {"LOW","VERY_LOW"}: score += 3

    regime_match = regime in chosen.get("regimes", []) or regime in {"", "UNKNOWN"}
    vol_match = vol_state in chosen.get("volatility", []) or vol_state in {"", "UNKNOWN"}
    if not regime_match: score = max(0.0, score - 12.0)
    if not vol_match: score = max(0.0, score - 10.0)

    return {
        "id": chosen["id"], "family": chosen["family"],
        "quality": round(min(100.0, score),2),
        "confirmations": confirmations[:6], "indicators": list(chosen.get("indicators") or []),
        "market": market, "symbol": symbol, "timeframe": timeframe,
        "regime_match": regime_match, "volatility_match": vol_match,
    }


_RC9_MATRIX = coverage_matrix()
if not _RC9_MATRIX["ok"]:
    raise RuntimeError(f"RC9 default coverage incomplete: {_RC9_MATRIX}")
