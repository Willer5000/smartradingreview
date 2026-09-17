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

VERSION = "RC9_2_CONTINGENCY_PLAYBOOK_V1"
_DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}
_NEGATIVE_RESEARCH = {"REJECTED_OOS", "NEGATIVE_OOS", "SHADOW_DIVERGED", "ALPHA_DECAY", "DEGRADED", "REVOKED"}
_POSITIVE_RESEARCH = {"SHADOW_READY", "OOS_VALIDATED", "OOS_PLUS_SHADOW", "CHAMPION", "VALIDATED"}


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

def _vol_state(groups: Dict[str, Any]) -> str:
    try:
        from operational_intelligence import canonical_volatility
        raw = groups.get("volatility") or {}
        return canonical_volatility(raw)
    except Exception:
        v = groups["volatility"]
        if v.get("squeeze_on"):
            return "COMPRESSION"
        atr = _f(v.get("atr_pct")); width = _f(v.get("bb_width"))
        if atr >= 4.0 or width >= 5.0:
            return "EXPANSION"
        return "NORMAL"


def _regime(layers: Dict[str, Any], groups: Dict[str, Any]) -> str:
    raw = _u((layers.get("market_regime") or {}).get("regime"))
    try:
        from operational_intelligence import canonical_regime
        if raw:
            return canonical_regime(raw)
    except Exception:
        pass
    d = groups["trend"]["direction"]
    adx = _f(groups["trend"]["adx"])
    if adx >= 25 and d == "BULLISH":
        return "TREND_UP"
    if adx >= 25 and d == "BEARISH":
        return "TREND_DOWN"
    return "BALANCE"


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
    if vol_state == "COMPRESSION":
        return "DEFAULT_BREAKOUT_RETEST", "BREAKOUT_RETEST"
    if regime in {"RANGING", "BALANCE", "RANGE"}:
        rsi = _f(groups["momentum"].get("rsi"), 50)
        if (direction == "LONG" and rsi <= 42) or (direction == "SHORT" and rsi >= 58):
            return "DEFAULT_LIQUIDITY_SWEEP_REVERSAL", "SWEEP_REVERSAL"
        return "DEFAULT_RANGE_MEAN_REVERSION", "MEAN_REVERSION"
    if vol_state in {"EXPANSION", "SHOCK"}:
        return "DEFAULT_STRUCTURE_RETEST", "STRUCTURE_RETEST"
    return "DEFAULT_TREND_PULLBACK", "TREND_PULLBACK"


def _portfolio_intent(market: str, symbol: str, direction: str, rotation_signal: str) -> str:
    if market == "FUTURES":
        return "TACTICAL_LONG" if direction == "LONG" else "TACTICAL_SHORT" if direction == "SHORT" else "FLAT"
    sym = symbol.upper()
    if direction == "LONG":
        if sym == "BTC-USDT": return "BUY_BTC_WITH_USDT"
        if sym == "PAXG-USDT": return "BUY_PAXG_WITH_USDT"
        if sym == "PAXG-BTC": return "ROTATE_BTC_TO_PAXG"
    if direction == "SHORT":
        if sym == "BTC-USDT": return "SELL_BTC_TO_USDT"
        if sym == "PAXG-USDT": return "SELL_PAXG_TO_USDT"
        if sym == "PAXG-BTC": return "ROTATE_PAXG_TO_BTC"
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
    operational = dict((layers or {}).get("operational_intelligence") or {})
    if operational.get("multi_timeframe"):
        groups["multi_timeframe"] = dict(operational.get("multi_timeframe") or {})
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
    vote_support = _vote_support(_votes(vote_record), committee_dir)

    macro_risk = _u(groups["macro"].get("risk"))
    macro_posture = _u(groups["macro"].get("futures_posture"))
    data_ok = bool(groups["structure_liquidity"].get("current_price")) and groups["coverage"]["available_groups"] >= 6

    selected_dir = committee_dir if committee_dir != "NEUTRAL" else directional
    target_action = _action(selected_dir, market)
    bank_pick = dict(operational.get("default_strategy") or {})
    if not bank_pick or str(bank_pick.get("id") or "") in {"", "NO_PLAYBOOK"}:
        try:
            from default_strategy_bank import select_strategy
            bank_pick = select_strategy(
                target_action, regime, vol_state, groups,
                symbol=symbol, timeframe=timeframe, market=market,
            )
        except Exception:
            strategy, setup_family = _strategy_name(market, symbol, regime, vol_state, selected_dir, groups)
            bank_pick = {"id": strategy, "family": setup_family, "quality": 0.0, "confirmations": [], "indicators": []}
    strategy = str(bank_pick.get("id") or "NO_PLAYBOOK")
    setup_family = str(bank_pick.get("family") or "NONE")
    strategy_quality = float(bank_pick.get("quality") or 0.0)

    thesis = dict(operational.get("thesis") or {})
    live_families = list(thesis.get("independent_support_families") or [])
    minimum_live_families = 4 if market == "FUTURES" else 3
    learned = str(operational.get("selected_specialist_source") or "DEFAULT").upper() == "LEARNED"
    # A learned specialist may use a slightly smaller *directional* family set
    # because exact historical evidence is one prior, but it still needs at
    # least 3 Futures / 2 Spot live independent families and all later Safety.
    minimum_if_learned = 3 if market == "FUTURES" else 2
    family_requirement = minimum_if_learned if learned else minimum_live_families

    gates = {
        "data_health": data_ok,
        "context_known": regime not in {"", "UNKNOWN"},
        "volatility_known": vol_state != "UNKNOWN",
        "independent_market_evidence": len(live_families) >= family_requirement,
        "macro_safe": not (
            market == "FUTURES"
            and (macro_risk == "CRITICAL" or macro_posture in {"BLOCK", "HALT", "NO_TRADE"})
        ),
        "research_not_negative": not blocked_by_research,
        "strategy_quality": strategy_quality >= (78.0 if market == "FUTURES" else 70.0),
        "operational_candidate_ready": bool(operational.get("candidate_ready")) if action in _DIRECTIONAL else True,
    }
    green = sum(1 for x in gates.values() if x)
    required = len(gates)
    # Commit 9.4: contingency no longer re-runs a second committee-majority
    # permission layer. It accepts only a thesis-first candidate that already
    # passed live context + learned/default strategy selection. Safety remains
    # downstream and unchanged.
    executable_contingency = bool(
        active
        and action in _DIRECTIONAL
        and target_action == action
        and all(gates.values())
    )

    effective_action = action
    downgrade_reason = ""
    if blocked_by_research and action in _DIRECTIONAL:
        effective_action = "NO_OPERAR"
        downgrade_reason = (
            "El comportamiento reciente de esta estrategia no conserva evidencia "
            "suficiente para abrir una nueva operación."
        )
    elif active and action in _DIRECTIONAL and not executable_contingency:
        effective_action = "ESPERAR" if data_ok and gates["macro_safe"] else "NO_OPERAR"
        if not data_ok:
            downgrade_reason = (
                "Faltan datos suficientes de precio, estructura o volatilidad para "
                "validar una entrada defendible."
            )
        elif not gates["macro_safe"]:
            downgrade_reason = (
                "El riesgo macroeconómico actual no permite asumir una nueva "
                "exposición apalancada con seguridad."
            )
        elif not gates["independent_market_evidence"]:
            downgrade_reason = (
                "La señal todavía no reúne suficientes familias independientes de "
                "evidencia entre tendencia, estructura, momentum, volumen y contexto."
            )
        elif not gates["operational_candidate_ready"]:
            downgrade_reason = (
                "La tesis de mercado todavía no alcanza la calidad operativa requerida "
                "para enviar una entrada a los controles finales de ejecución."
            )
        else:
            downgrade_reason = (
                "La estructura y el punto de entrada todavía no ofrecen una zona "
                "defendible con invalidación clara."
            )

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

    # RC9: public explanation is built from observable market values, never from
    # internal gate/role names.  Internal gates remain in this payload for audit.
    try:
        from reason_presenter import build_public_decision_evidence
        public_evidence = build_public_decision_evidence(
            effective_action,
            trend=groups.get("trend"),
            momentum=groups.get("momentum"),
            volatility=groups.get("volatility"),
            volume=groups.get("volume_flow"),
            structure=groups.get("structure_liquidity"),
            correlation=groups.get("rotation"),
            market_hours=groups.get("market_time"),
            confirmation=groups.get("confirmation"),
            sentiment=groups.get("sentiment"),
            liquidation=groups.get("liquidations"),
            limit=4,
        )
    except Exception:
        public_evidence = []

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
        "strategy_quality": round(strategy_quality, 2),
        "strategy_confirmations": list(bank_pick.get("confirmations") or []),
        "strategy_indicators": list(bank_pick.get("indicators") or []),
        "setup_code": setup_family,
        "entry": {"rule": entry_rule, "requires_closed_candle": True, "anti_fomo": True},
        "risk": {"size_cap": size_cap, "leverage_cap": leverage_cap, "confidence_cap": confidence_cap, "never_bypass_safety": True},
        "gates": gates,
        "green_gates": green,
        "total_gates": required,
        "executable_contingency": bool(executable_contingency),
        "downgrade_reason": downgrade_reason,
        "public_evidence": public_evidence,
        "vote_support": vote_support,
        "indicator_groups": groups,
        "direction_scores": {"long": round(long_score, 3), "short": round(short_score, 3), "reasons": score_reasons},
        "ai_role": "Trader IA may explain conflicts/context and propose research questions; it cannot create direction or bypass gates.",
    }
