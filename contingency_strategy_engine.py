"""RC8.2 — deterministic contingency trading playbook.

This is NOT a statistical Champion and never fabricates validated alpha.
It gives the live committee a coherent operating playbook while Research is
unavailable or an action-specific cell is still unfilled.

Desk workflow:
DATA HEALTH -> CONTEXT/REGIME -> VOLATILITY -> DIRECTION -> SETUP -> ENTRY -> CONTROL/RISK.

All indicator families are consumed, but correlated indicators are grouped so
RSI/MACD/EMAs/ADX/etc. cannot masquerade as independent proofs.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "RC8_2_CONTINGENCY_PLAYBOOK_V1"
_DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}
_NEGATIVE_RESEARCH = {"NEGATIVE_OOS", "SHADOW_DIVERGED", "ALPHA_DECAY"}
_POSITIVE_RESEARCH = {"OOS_VALIDATED", "OOS_PLUS_SHADOW"}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except Exception:
        return float(default)


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _direction(action: Any) -> str:
    value = _u(action)
    if value in {"LONG", "COMPRA_SPOT", "BUY", "BULLISH"}:
        return "LONG"
    if value in {"SHORT", "VENTA_SPOT", "SELL", "BEARISH"}:
        return "SHORT"
    return "NEUTRAL"


def _action(direction: str, market: str) -> str:
    if direction == "LONG":
        return "LONG" if market == "FUTURES" else "COMPRA_SPOT"
    if direction == "SHORT":
        return "SHORT" if market == "FUTURES" else "VENTA_SPOT"
    return "NO_OPERAR"


def _votes(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        rows = raw.get("todos_los_votos") or raw.get("votes") or []
        return [x for x in rows if isinstance(x, dict)]
    return []


def _vote_support(votes: Iterable[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    # Existing committee roles are intentionally reused.  One role/family is one
    # proof; the contingency layer does not create another 10-vote committee.
    try:
        from hierarchical_committee import role_for_trader
    except Exception:
        def role_for_trader(name):
            return {"role": "SETUP", "family": str(name or "UNKNOWN")}

    families: Dict[str, float] = {}
    roles: Dict[str, float] = {}
    aligned_traders: List[str] = []
    opposed_traders: List[str] = []
    for vote in votes:
        trader = str(vote.get("trader") or "UNKNOWN")
        vd = _direction(vote.get("accion_normalizada") or vote.get("accion"))
        conf = max(0.0, min(100.0, _f(vote.get("confianza_original", vote.get("confianza", 0)))))
        profile = role_for_trader(trader)
        fam = str(profile.get("family") or trader)
        role = str(profile.get("role") or "SETUP")
        if vd == direction:
            families[fam] = max(families.get(fam, 0.0), conf)
            roles[role] = max(roles.get(role, 0.0), conf)
            aligned_traders.append(trader)
        elif vd in {"LONG", "SHORT"} and vd != direction:
            opposed_traders.append(trader)
    independent = sum(1 for v in families.values() if v >= 45.0)
    return {
        "independent_families": independent,
        "families": families,
        "roles": roles,
        "aligned_traders": aligned_traders,
        "opposed_traders": opposed_traders,
        "has_setup": roles.get("SETUP", 0) >= 45,
        "has_execution": roles.get("EXECUTION", 0) >= 45,
        "has_context": roles.get("CONTEXT", 0) >= 45,
        "has_control_support": roles.get("CONTROL", 0) >= 45,
    }


def _indicator_groups(layers: Dict[str, Any]) -> Dict[str, Any]:
    trend = layers.get("trend") or {}
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

    trend_dir = _u(trend.get("direction"))
    momentum_dir = _u(momentum.get("direction"))
    obv_dir = _u(volume.get("obv_trend"))
    macro_bias = _u(macro.get("directional_bias"))

    groups = {
        "trend": {
            "available": bool(trend), "direction": trend_dir or "NEUTRAL",
            "adx": round(_f(trend.get("adx")), 2), "plus_di": round(_f(trend.get("plus_di")), 2),
            "minus_di": round(_f(trend.get("minus_di")), 2),
            "ema9": _f(trend.get("ema9")), "ema21": _f(trend.get("ema21")),
            "ema50": _f(trend.get("ema50")), "ema200": _f(trend.get("ema200")),
        },
        "momentum": {
            "available": bool(momentum), "direction": momentum_dir or "NEUTRAL",
            "score": round(_f(momentum.get("score")), 2), "rsi": round(_f(mi.get("rsi"), 50), 2),
            "rsi_maverick": round(_f(mi.get("rsi_maverick"), .5), 4),
            "macd_histogram": round(_f(mi.get("macd_histogram")), 6),
            "stoch_k": round(_f(mi.get("stoch_k"), 50), 2),
            "williams": round(_f(mi.get("williams"), -50), 2), "cci": round(_f(mi.get("cci")), 2),
        },
        "volatility": {
            "available": bool(vol), "atr_pct": round(_f(vol.get("atr_pct")), 4),
            "bb_width": round(_f(vol.get("bb_width")), 4), "bb_position": round(_f(vol.get("bb_position"), .5), 4),
            "squeeze_on": bool(vol.get("squeeze_on")), "squeeze_length": int(_f(vol.get("squeeze_length"))),
            "ftm_state": _u(vol.get("ftm_state")) or "NEUTRAL",
        },
        "volume_flow": {
            "available": bool(volume), "volume_ratio": round(_f(volume.get("volume_ratio"), 1), 3),
            "mfi": round(_f(volume.get("mfi"), 50), 2), "obv_trend": obv_dir or "NEUTRAL",
            "whale_buy": bool(volume.get("whale_buy_confirmed") or volume.get("whale_buy")),
            "whale_sell": bool(volume.get("whale_sell_confirmed") or volume.get("whale_sell")),
            "iceberg_buy": bool(volume.get("iceberg_buy")), "iceberg_sell": bool(volume.get("iceberg_sell")),
        },
        "structure_liquidity": {
            "available": bool(structure), "current_price": _f(structure.get("current_price")),
            "direction": _u(structure.get("direction") or structure.get("structure_direction")) or "NEUTRAL",
            "support": _f(structure.get("nearest_support") or structure.get("support")),
            "resistance": _f(structure.get("nearest_resistance") or structure.get("resistance")),
            "has_patterns": bool((structure.get("patterns") or {}).get("recent_patterns")),
            "has_order_blocks": bool(structure.get("order_blocks") or structure.get("order_blocks_active")),
            "has_fvg": bool(structure.get("fvgs") or structure.get("fair_value_gaps")),
        },
        "liquidations": {
            "available": bool(liq), "long_weight": round(_f(liq.get("total_long_weight")), 3),
            "short_weight": round(_f(liq.get("total_short_weight")), 3),
            "events": int(_f(liq.get("total_spikes"))), "data_type": str(liq.get("data_type") or ""),
        },
        "macro": {
            "available": bool(macro.get("enabled", bool(macro))), "risk": _u(macro.get("risk_level")) or "UNKNOWN",
            "bias": macro_bias or "NEUTRAL", "futures_posture": _u(macro.get("futures_posture")) or "NORMAL",
        },
        "sentiment": {
            "available": bool(sentiment), "value": round(_f(sentiment.get("current_value"), 50), 2),
            "bias": _u(sentiment.get("sentiment_bias")) or "NEUTRAL",
        },
        "rotation": {
            "available": bool(correlation), "signal": _u(correlation.get("rotation_signal")) or "NEUTRAL",
            "weight_modifier": round(_f(correlation.get("weight_modifier"), 1), 3),
        },
        "market_time": {
            "available": bool(hours or time_factor), "session": str(hours.get("session") or "UNKNOWN"),
            "liquidity": str(hours.get("liquidity") or "unknown"), "day_type": str(hours.get("day_type") or "UNKNOWN"),
            "time_score": round(_f(time_factor.get("score"), 0), 2),
        },
    }
    groups["coverage"] = {
        "available_groups": sum(1 for k, v in groups.items() if isinstance(v, dict) and v.get("available")),
        "total_groups": 10,
    }
    return groups


def _vol_state(groups: Dict[str, Any]) -> str:
    v = groups["volatility"]
    if v.get("squeeze_on"):
        return "SQUEEZE"
    ftm = _u(v.get("ftm_state"))
    atr = _f(v.get("atr_pct"))
    width = _f(v.get("bb_width"))
    if ftm in {"EXTREME", "HIGH", "EXPANSION", "VOLATILE"} or atr >= 4.0 or width >= 5.0:
        return "HIGH_EXPANSION"
    if atr <= 0 and width <= 0:
        return "UNKNOWN"
    return "NORMAL"


def _regime(layers: Dict[str, Any], groups: Dict[str, Any]) -> str:
    raw = _u((layers.get("market_regime") or {}).get("regime"))
    if raw:
        return raw
    d = groups["trend"]["direction"]
    adx = _f(groups["trend"]["adx"])
    if adx >= 25 and d == "BULLISH":
        return "TRENDING_BULL"
    if adx >= 25 and d == "BEARISH":
        return "TRENDING_BEAR"
    return "RANGING"


def _raw_direction_score(groups: Dict[str, Any]) -> Tuple[float, float, List[str]]:
    long = 0.0; short = 0.0; reasons: List[str] = []
    t = groups["trend"]; m = groups["momentum"]; vf = groups["volume_flow"]
    st = groups["structure_liquidity"]; macro = groups["macro"]; sent = groups["sentiment"]
    adx = _f(t.get("adx"))
    weight = 1.25 if adx >= 25 else 0.75
    if t.get("direction") == "BULLISH": long += weight; reasons.append("trend_bullish")
    if t.get("direction") == "BEARISH": short += weight; reasons.append("trend_bearish")
    if m.get("direction") == "BULLISH" or _f(m.get("score")) >= 3: long += 1.0; reasons.append("momentum_bullish")
    if m.get("direction") == "BEARISH" or _f(m.get("score")) <= -3: short += 1.0; reasons.append("momentum_bearish")
    macd = _f(m.get("macd_histogram")); rsi = _f(m.get("rsi"), 50)
    if macd > 0 and rsi >= 50: long += .45
    elif macd < 0 and rsi <= 50: short += .45
    if vf.get("obv_trend") == "BULLISH" or vf.get("whale_buy") or vf.get("iceberg_buy"): long += .75; reasons.append("flow_bullish")
    if vf.get("obv_trend") == "BEARISH" or vf.get("whale_sell") or vf.get("iceberg_sell"): short += .75; reasons.append("flow_bearish")
    if st.get("direction") == "BULLISH": long += .7
    elif st.get("direction") == "BEARISH": short += .7
    if macro.get("bias") == "BULLISH": long += .35
    elif macro.get("bias") == "BEARISH": short += .35
    if sent.get("bias") in {"BULLISH", "BULLISH_OPPORTUNITY"}: long += .25
    elif sent.get("bias") in {"BEARISH", "BEARISH_OPPORTUNITY"}: short += .25
    return long, short, reasons


def _strategy_name(market: str, symbol: str, regime: str, vol_state: str, direction: str, groups: Dict[str, Any]) -> Tuple[str, str]:
    rotation = _u(groups["rotation"].get("signal"))
    if market == "SPOT" and symbol.upper() in {"BTC-USDT", "PAXG-USDT", "PAXG-BTC"} and rotation not in {"", "NEUTRAL", "NONE"}:
        return "DEFAULT_SPOT_ROTATION", "ROTATION"
    if vol_state == "SQUEEZE":
        return "DEFAULT_BREAKOUT_RETEST", "BREAKOUT_RETEST"
    if regime in {"RANGING", "BALANCE", "RANGE"}:
        rsi = _f(groups["momentum"].get("rsi"), 50)
        if (direction == "LONG" and rsi <= 42) or (direction == "SHORT" and rsi >= 58):
            return "DEFAULT_LIQUIDITY_SWEEP_REVERSAL", "SWEEP_REVERSAL"
        return "DEFAULT_RANGE_MEAN_REVERSION", "MEAN_REVERSION"
    if vol_state == "HIGH_EXPANSION":
        return "DEFAULT_STRUCTURE_RETEST", "STRUCTURE_RETEST"
    return "DEFAULT_TREND_PULLBACK", "TREND_PULLBACK"


def _portfolio_intent(market: str, symbol: str, direction: str, rotation_signal: str) -> str:
    if market == "FUTURES":
        return "TACTICAL_LONG" if direction == "LONG" else "TACTICAL_SHORT" if direction == "SHORT" else "FLAT"
    sym = symbol.upper()
    rot = _u(rotation_signal)
    if "PAXG" in rot and ("BTC" in rot or "GOLD" in rot):
        return "ROTATE_BTC_TO_PAXG"
    if "BTC" in rot and ("PAXG" in rot or "GOLD" in rot):
        return "ROTATE_PAXG_TO_BTC"
    if direction == "LONG":
        if sym == "BTC-USDT": return "ACCUMULATE_SATOSHIS"
        if sym == "PAXG-USDT": return "ACCUMULATE_PAXG"
        if sym == "PAXG-BTC": return "ROTATION_ACCUMULATE_PAXG_VS_BTC"
        return "ACCUMULATE_ASSET"
    if direction == "SHORT":
        return "REDUCE_TO_USDT_OR_ROTATE"
    return "HOLD_RESERVES"


def build_contingency_playbook(
    *, layers: Dict[str, Any], symbol: str, timeframe: str, system_type: str,
    committee_action: str, committee_confidence: float, vote_record: Any = None,
    research_prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    action = _u(committee_action) or "NO_OPERAR"
    committee_dir = _direction(action)
    groups = _indicator_groups(layers or {})
    regime = _regime(layers or {}, groups)
    vol_state = _vol_state(groups)
    research = dict(research_prior or {})
    research_state = _u(research.get("state")) or "UNAVAILABLE"

    # A known negative/decayed cell is NOT rescued by a default strategy.
    blocked_by_research = research_state in _NEGATIVE_RESEARCH or bool(research.get("recycle_required"))
    champion_governs = research_state in _POSITIVE_RESEARCH
    active = not champion_governs and not blocked_by_research
    active_reason = (
        "VALIDATED_CHAMPION_AVAILABLE" if champion_governs else
        "KNOWN_NEGATIVE_OR_DECAY" if blocked_by_research else
        "RESEARCH_UNAVAILABLE" if research_state == "UNAVAILABLE" else
        "ACTION_CELL_NOT_YET_VALIDATED"
    )

    long_score, short_score, score_reasons = _raw_direction_score(groups)
    directional = "LONG" if long_score >= short_score + .75 else "SHORT" if short_score >= long_score + .75 else "NEUTRAL"
    vote_support = _vote_support(_votes(vote_record), directional if directional != "NEUTRAL" else committee_dir)

    macro_risk = _u(groups["macro"].get("risk"))
    macro_posture = _u(groups["macro"].get("futures_posture"))
    data_ok = bool(groups["structure_liquidity"].get("current_price")) and groups["coverage"]["available_groups"] >= 6
    direction_agrees = committee_dir != "NEUTRAL" and directional == committee_dir
    families = int(vote_support.get("independent_families") or 0)

    strategy, setup_family = _strategy_name(market, symbol, regime, vol_state, committee_dir if committee_dir != "NEUTRAL" else directional, groups)
    selected_dir = committee_dir if committee_dir != "NEUTRAL" else directional
    target_action = _action(selected_dir, market)

    gates = {
        "data_health": data_ok,
        "context_known": regime not in {"", "UNKNOWN"},
        "volatility_known": vol_state != "UNKNOWN",
        "direction_agrees_committee": direction_agrees,
        "independent_evidence": families >= (3 if market == "FUTURES" else 2),
        "setup_or_execution_role": bool(vote_support.get("has_setup") or vote_support.get("has_execution")),
        "macro_safe": not (market == "FUTURES" and (macro_risk == "CRITICAL" or macro_posture in {"BLOCK", "HALT", "NO_TRADE"})),
        "research_not_negative": not blocked_by_research,
    }
    green = sum(1 for x in gates.values() if x)
    required = len(gates)

    # Futures contingency is intentionally stricter than Spot. It can only keep
    # an already-issued committee direction; it never manufactures one.
    min_green = 8 if market == "FUTURES" else 7
    executable_contingency = active and action in _DIRECTIONAL and target_action == action and green >= min_green

    effective_action = action
    downgrade_reason = ""
    if blocked_by_research and action in _DIRECTIONAL:
        effective_action = "NO_OPERAR"
        downgrade_reason = "Evidencia OOS/Shadow negativa o Alpha Decay: la contingencia no puede rescatar la celda."
    elif active and action in _DIRECTIONAL and not executable_contingency:
        effective_action = "ESPERAR" if data_ok and gates["macro_safe"] else "NO_OPERAR"
        downgrade_reason = "Playbook de contingencia incompleto: falta alineación independiente para ejecutar sin Champion."

    if market == "FUTURES":
        size_cap = 0.35
        leverage_cap = 10
        confidence_cap = 68.0
        entry_rule = "Closed candle + structure/liquidity confirmation + Pullback/Retest; no market-chasing."
    else:
        size_cap = 0.60
        leverage_cap = 1
        confidence_cap = 74.0
        entry_rule = "Pullback/POI or confirmed close; preserve BTC/PAXG/USDT reserves and avoid FOMO."

    rotation_signal = groups["rotation"].get("signal") or "NEUTRAL"
    intent = _portfolio_intent(market, symbol, selected_dir, rotation_signal)

    return {
        "version": VERSION,
        "authority": "CONTINGENCY_PLAYBOOK_NOT_VALIDATED_ALPHA",
        "active": bool(active),
        # Machine identifiers are preserved for audit/Research only. Public
        # explanations are generated separately by reason_presenter.py.
        "reason": active_reason,
        "reason_code": active_reason,
        "research_state": research_state,
        "market": market,
        "symbol": str(symbol or "").upper(),
        "timeframe": str(timeframe or "").upper(),
        "committee_action": action,
        "committee_confidence": round(max(0.0, min(100.0, _f(committee_confidence))), 2),
        "effective_action": effective_action,
        "direction": selected_dir,
        "context": {"regime": regime, "macro_risk": macro_risk, "portfolio_intent": intent},
        "volatility": {"state": vol_state, "atr_pct": groups["volatility"].get("atr_pct"), "squeeze_on": groups["volatility"].get("squeeze_on")},
        "strategy": strategy,
        "setup_family": setup_family,
        "setup_code": setup_family,
        "entry": {"rule": entry_rule, "requires_closed_candle": True, "anti_fomo": True},
        "risk": {"size_cap": size_cap, "leverage_cap": leverage_cap, "confidence_cap": confidence_cap, "never_bypass_safety": True},
        "gates": gates,
        "green_gates": green,
        "total_gates": required,
        "executable_contingency": bool(executable_contingency),
        "downgrade_reason": downgrade_reason,
        "vote_support": vote_support,
        "indicator_groups": groups,
        "direction_scores": {"long": round(long_score, 3), "short": round(short_score, 3), "reasons": score_reasons},
        "ai_role": "Trader IA may explain conflicts/context and propose research questions; it cannot create direction or bypass gates.",
    }
