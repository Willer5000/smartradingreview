"""FINAL V1 RC4 — Hierarchical Trading Intelligence.

This module reorganises the ten voices of SmartradingReview into a professional
trading-desk workflow without replacing any trader:

CONTEXT -> SETUP -> EXECUTION -> CONTROL/LEARNING.

Safety properties:
- Context traders cannot create a direction on their own.
- The hierarchy cannot reopen a baseline NO_OPERAR/ESPERAR decision.
- It can confirm the existing direction, lower confidence, or veto/delay it.
- Correlated opinions are capped by evidence family so five momentum-flavoured
  opinions do not count as five independent proofs.
- Spot and Futures use different role/timeframe priorities.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

RC4_HIERARCHICAL_COMMITTEE_VERSION = "RC4_HIERARCHICAL_TRADING_INTELLIGENCE_V1"

# Trader name -> (desk role, independent evidence family)
TRADER_PROFILES: Dict[str, Tuple[str, str]] = {
    "Técnico Puro": ("SETUP", "MOMENTUM_TREND"),
    "Chartista": ("SETUP", "PRICE_ACTION_PATTERN"),
    "Cazador de Ballenas": ("CONTEXT", "WHALE_VOLUME"),
    "Macroeconomista": ("CONTEXT", "MACRO"),
    "Pullback": ("EXECUTION", "TIMING_PULLBACK"),
    "Smart Money": ("EXECUTION", "STRUCTURE_LIQUIDITY"),
    "Escéptico": ("CONTROL", "RISK_CHALLENGE"),
    "Multiframe": ("CONTEXT", "MULTITIMEFRAME"),
    "El Liquidador": ("EXECUTION", "LEVERAGED_LIQUIDITY"),
    "Trader de Revisión": ("CONTROL", "HISTORICAL_EDGE"),
}

# Modest multipliers: existing base/regime/ReviewTrader weights remain intact.
# RC4 only adjusts *where* each specialist is most useful.
_ROLE_WEIGHTS = {
    "FUTURES": {
        "LOW": {"CONTEXT": 0.78, "SETUP": 1.00, "EXECUTION": 1.16, "CONTROL": 1.05},  # 30m/1h
        "MID": {"CONTEXT": 0.92, "SETUP": 1.06, "EXECUTION": 1.12, "CONTROL": 1.08},  # 2h/4h
        "HIGH": {"CONTEXT": 1.16, "SETUP": 1.02, "EXECUTION": 0.90, "CONTROL": 1.10}, # 12h/1D
    },
    "SPOT": {
        "LOW": {"CONTEXT": 0.90, "SETUP": 1.02, "EXECUTION": 0.92, "CONTROL": 1.06},   # 4h/12h execution
        "HIGH": {"CONTEXT": 1.16, "SETUP": 1.00, "EXECUTION": 0.78, "CONTROL": 1.10}, # 1D/1W decision
    },
}


def _market_key(market: Any) -> str:
    return "FUTURES" if str(market or "").upper() == "FUTURES" else "SPOT"


def _tf_key(timeframe: Any) -> str:
    raw = str(timeframe or "").strip().upper()
    aliases = {"30MIN": "30M", "60M": "1H", "120M": "2H", "240M": "4H", "1DAY": "1D"}
    return aliases.get(raw, raw)


def _bucket(market: str, timeframe: str) -> str:
    tf = _tf_key(timeframe)
    if market == "FUTURES":
        if tf in {"30M", "1H"}:
            return "LOW"
        if tf in {"2H", "4H"}:
            return "MID"
        return "HIGH"
    return "LOW" if tf in {"4H", "12H"} else "HIGH"


def _direction(action: Any) -> str:
    value = str(action or "").upper()
    if value in {"LONG", "COMPRA_SPOT", "BUY"}:
        return "LONG"
    if value in {"SHORT", "VENTA_SPOT", "SELL"}:
        return "SHORT"
    return "NEUTRAL"


def _confidence(vote: Dict[str, Any]) -> float:
    for key in ("confianza_contabilizada", "confianza_ponderada", "confianza", "confianza_original"):
        try:
            value = vote.get(key)
            if value is not None:
                return max(0.0, min(100.0, float(value)))
        except Exception:
            pass
    return 0.0


def role_for_trader(name: Any) -> Dict[str, str]:
    trader = str(name or "UNKNOWN")
    role, family = TRADER_PROFILES.get(trader, ("SETUP", f"OTHER:{trader}"))
    return {"role": role, "family": family}


def role_multiplier(trader: Any, market: Any, timeframe: Any) -> float:
    market_key = _market_key(market)
    role = role_for_trader(trader)["role"]
    return float(_ROLE_WEIGHTS[market_key][_bucket(market_key, timeframe)].get(role, 1.0))


def build_hierarchical_assessment(
    votes: Iterable[Dict[str, Any]],
    *,
    baseline_action: Any,
    market: Any,
    timeframe: Any,
    symbol: Any = None,
    regime: Any = None,
) -> Dict[str, Any]:
    """Assess the already-produced committee vote as a hierarchical desk.

    The result is a production *quality gate*, not a second signal generator.
    It never turns NO_OPERAR/ESPERAR into a trade and never flips LONG<->SHORT.
    """
    market_key = _market_key(market)
    tf = _tf_key(timeframe)
    base_dir = _direction(baseline_action)
    base_raw = str(baseline_action or "NO_OPERAR").upper()

    # Family-level capping: within one evidence family use the mean, not the sum.
    family_support: Dict[str, List[float]] = defaultdict(list)
    family_oppose: Dict[str, List[float]] = defaultdict(list)
    role_support: Dict[str, List[float]] = defaultdict(list)
    role_oppose: Dict[str, List[float]] = defaultdict(list)
    enriched: List[Dict[str, Any]] = []
    hard_vetoes: List[str] = []

    for raw in votes or []:
        if not isinstance(raw, dict):
            continue
        trader = str(raw.get("trader") or "UNKNOWN")
        profile = role_for_trader(trader)
        role = profile["role"]
        family = profile["family"]
        action_raw = raw.get("accion_normalizada") or raw.get("accion")
        direction = _direction(action_raw)
        base_conf = _confidence(raw)
        rmult = role_multiplier(trader, market_key, tf)
        effective = max(0.0, min(100.0, base_conf * rmult))

        # Hard control/context vetoes remain possible, but require high conviction.
        action_text = str(action_raw or "").upper()
        if action_text == "NO_OPERAR":
            if trader == "Macroeconomista" and base_conf >= 80:
                hard_vetoes.append("MACRO_HARD_RISK")
            elif trader == "Escéptico" and base_conf >= 90:
                hard_vetoes.append("SKEPTIC_HARD_VETO")
            elif trader == "Trader de Revisión" and base_conf >= 90:
                hard_vetoes.append("REVIEWTRADER_NEGATIVE_EDGE")

        relation = "NEUTRAL"
        if base_dir in {"LONG", "SHORT"} and direction in {"LONG", "SHORT"}:
            relation = "SUPPORT" if direction == base_dir else "OPPOSE"
            if relation == "SUPPORT":
                family_support[family].append(effective)
                role_support[role].append(effective)
            else:
                family_oppose[family].append(effective)
                role_oppose[role].append(effective)

        enriched.append({
            "trader": trader,
            "role": role,
            "evidence_family": family,
            "direction": direction,
            "relation_to_baseline": relation,
            "base_confidence": round(base_conf, 2),
            "role_multiplier": round(rmult, 3),
            "hierarchical_confidence": round(effective, 2),
        })

    def fam_mean(values: Dict[str, List[float]]) -> Dict[str, float]:
        return {k: sum(v) / len(v) for k, v in values.items() if v}

    support_f = fam_mean(family_support)
    oppose_f = fam_mean(family_oppose)

    # One family = one unit of evidence. This prevents correlated indicator spam.
    support_values = list(support_f.values())
    oppose_values = list(oppose_f.values())
    support_score = sum(support_values) / len(support_values) if support_values else 0.0
    oppose_score = sum(oppose_values) / len(oppose_values) if oppose_values else 0.0

    def role_mean(bucket: Dict[str, List[float]], role: str) -> float:
        vals = bucket.get(role) or []
        return sum(vals) / len(vals) if vals else 0.0

    context_support = role_mean(role_support, "CONTEXT")
    setup_support = role_mean(role_support, "SETUP")
    execution_support = role_mean(role_support, "EXECUTION")
    control_support = role_mean(role_support, "CONTROL")
    context_oppose = role_mean(role_oppose, "CONTEXT")
    setup_oppose = role_mean(role_oppose, "SETUP")
    execution_oppose = role_mean(role_oppose, "EXECUTION")
    control_oppose = role_mean(role_oppose, "CONTROL")

    independent_support = len([v for v in support_f.values() if v >= 45.0])
    independent_oppose = len([v for v in oppose_f.values() if v >= 45.0])

    # Timeframe-sensitive desk requirements. They are intentionally modest:
    # RC4 should reject weak one-factor signals, not demand every module agrees.
    bucket = _bucket(market_key, tf)
    if market_key == "FUTURES" and bucket == "LOW":
        requirements = {
            "min_families": 2,
            "needs_setup_or_execution": True,
            "needs_context": False,
            "lower_tf_entry_confirmation": False,
        }
    elif market_key == "FUTURES" and bucket == "MID":
        requirements = {
            "min_families": 2,
            "needs_setup_or_execution": True,
            "needs_context": False,
            "lower_tf_entry_confirmation": False,
        }
    elif market_key == "FUTURES":
        requirements = {
            "min_families": 2,
            "needs_setup_or_execution": True,
            "needs_context": True,
            "lower_tf_entry_confirmation": True,
        }
    elif bucket == "HIGH":
        requirements = {
            "min_families": 2,
            "needs_setup_or_execution": True,
            "needs_context": True,
            "lower_tf_entry_confirmation": False,
        }
    else:
        requirements = {
            "min_families": 2,
            "needs_setup_or_execution": True,
            "needs_context": False,
            "lower_tf_entry_confirmation": False,
        }

    directional_baseline = base_dir in {"LONG", "SHORT"}
    enough_families = independent_support >= requirements["min_families"]
    thesis_ok = max(setup_support, execution_support) >= 45.0
    context_available = bool(role_support.get("CONTEXT") or role_oppose.get("CONTEXT"))
    context_ok = (not requirements["needs_context"]) or (not context_available) or context_support >= 40.0
    opposition_dominates = independent_oppose >= 2 and oppose_score >= max(55.0, support_score + 8.0)
    hard_veto = bool(hard_vetoes)

    quality_gate = bool(
        directional_baseline
        and enough_families
        and (not requirements["needs_setup_or_execution"] or thesis_ok)
        and context_ok
        and not opposition_dominates
        and not hard_veto
    )

    if not directional_baseline:
        recommendation = base_raw  # never reopen no-trade
        reason = "BASELINE_NOT_DIRECTIONAL"
    elif hard_veto:
        recommendation = "NO_OPERAR"
        reason = "+".join(hard_vetoes)
    elif opposition_dominates:
        recommendation = "NO_OPERAR"
        reason = "INDEPENDENT_EVIDENCE_CONFLICT"
    elif not quality_gate:
        recommendation = "ESPERAR"
        missing = []
        if not enough_families:
            missing.append("INDEPENDENT_EVIDENCE")
        if requirements["needs_setup_or_execution"] and not thesis_ok:
            missing.append("SETUP_EXECUTION")
        if not context_ok:
            missing.append("HIGH_TF_CONTEXT")
        reason = "+".join(missing) or "QUALITY_GATE"
    else:
        recommendation = base_raw
        reason = "HIERARCHY_CONFIRMS_BASELINE"

    # Confidence changes are bounded; RC4 is about evidence quality, not leverage.
    if quality_gate:
        diversity_bonus = min(0.05, max(0, independent_support - 2) * 0.015)
        conf_mult = min(1.06, 1.0 + diversity_bonus)
    elif recommendation == "ESPERAR":
        conf_mult = 0.88
    elif recommendation == "NO_OPERAR" and directional_baseline:
        conf_mult = 0.75
    else:
        conf_mult = 1.0

    return {
        "version": RC4_HIERARCHICAL_COMMITTEE_VERSION,
        "authority": "PRODUCTION_QUALITY_GATE",
        "can_create_direction": False,
        "can_flip_direction": False,
        "baseline_action": base_raw,
        "baseline_direction": base_dir,
        "recommended_action": recommendation,
        "quality_gate_passed": quality_gate,
        "reason": reason,
        "market": market_key,
        "symbol": str(symbol or "UNKNOWN").upper(),
        "timeframe": tf,
        "regime": str(regime or "UNKNOWN").upper(),
        "independent_support_families": independent_support,
        "independent_oppose_families": independent_oppose,
        "support_score": round(support_score, 2),
        "opposition_score": round(oppose_score, 2),
        "role_support": {
            "context": round(context_support, 2),
            "setup": round(setup_support, 2),
            "execution": round(execution_support, 2),
            "control": round(control_support, 2),
        },
        "role_opposition": {
            "context": round(context_oppose, 2),
            "setup": round(setup_oppose, 2),
            "execution": round(execution_oppose, 2),
            "control": round(control_oppose, 2),
        },
        "requirements": requirements,
        "hard_vetoes": hard_vetoes,
        "confidence_multiplier": round(conf_mult, 3),
        "family_support": {k: round(v, 2) for k, v in sorted(support_f.items())},
        "family_opposition": {k: round(v, 2) for k, v in sorted(oppose_f.items())},
        "votes": enriched,
        "policy": {
            "context_cannot_create_direction": True,
            "family_caps_prevent_double_counting": True,
            "baseline_no_trade_cannot_be_reopened": True,
            "spot_futures_separate": True,
            "timeframe_sensitive": True,
            "leverage_unchanged": True,
            "safety_unchanged": True,
        },
    }
