"""Commit 10 — Trader Intelligence Foundation / Scorecard.

Research-only scorecard for the nine domain traders plus ReviewTrader.  It is
explicitly market-, timeframe-, direction- and regime-aware.  Nothing in this
module changes a vote, a trader weight, Safety, Entry, SL, TP or leverage.

The scorecard evaluates *judgement* rather than blindly crediting every
strategy attached to a signal:
- SUPPORT + TP is favourable evidence; SUPPORT + SL is unfavourable.
- OPPOSE + SL is potentially useful veto evidence; OPPOSE + TP is a false veto.
- NEUTRAL is counted for coverage but not scored as directional skill.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple
import math

from learning_integrity import (
    canonical_status,
    latest_result,
    learning_context,
    normalize_action,
    normalize_market,
    realized_r,
    safe_float,
)

SCORECARD_VERSION = "C10_TRADER_INTELLIGENCE_FOUNDATION_V1"


def _regime(row: Dict[str, Any]) -> str:
    learning = learning_context(row)
    quant = learning.get("quantitative_shadow") or {}
    if isinstance(quant, dict):
        value = str(quant.get("regime") or "").strip().upper()
        if value and value not in {"UNKNOWN", "UNAVAILABLE"}:
            return value
    return "UNKNOWN"


def _forensics(row: Dict[str, Any]) -> Dict[str, Any]:
    result = latest_result(row)
    value = result.get("execution_forensics") or {}
    return value if isinstance(value, dict) else {}


def _attribution_items(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    learning = learning_context(row)
    attribution = learning.get("strategy_attribution_v2") or {}
    if not isinstance(attribution, dict):
        return []
    items = attribution.get("items") or []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _judge_r(relation: str, final_r: Optional[float]) -> Optional[float]:
    if final_r is None:
        return None
    relation = str(relation or "").upper()
    if relation == "SUPPORT":
        return final_r
    if relation == "OPPOSE":
        return -final_r
    return None


def _success(relation: str, status: str) -> Optional[int]:
    relation = str(relation or "").upper()
    if status not in {"tp_hit", "sl_hit"}:
        return None
    if relation == "SUPPORT":
        return 1 if status == "tp_hit" else 0
    if relation == "OPPOSE":
        return 1 if status == "sl_hit" else 0
    return None


def _new_group() -> Dict[str, Any]:
    return {
        "n": 0,
        "resolved": 0,
        "tp": 0,
        "sl": 0,
        "expired": 0,
        "confidence_sum": 0.0,
        "confidence_n": 0,
        "judgement_r_sum": 0.0,
        "judgement_r_n": 0,
        "correct": 0,
        "correct_n": 0,
        "mfe_sum": 0.0,
        "mfe_n": 0,
        "mae_sum": 0.0,
        "mae_n": 0,
        "signals": set(),
        "outcome_signals": set(),
        "strategies": set(),
    }


def _add(group: Dict[str, Any], row: Dict[str, Any], item: Dict[str, Any]) -> None:
    signal_id = str(row.get("id") or "")
    group["n"] += 1
    if signal_id:
        group["signals"].add(signal_id)
    strategy = str(item.get("strategy") or "").strip().upper()
    if strategy:
        group["strategies"].add(strategy)

    confidence = safe_float(item.get("confidence"))
    if confidence is not None:
        group["confidence_sum"] += max(0.0, min(100.0, confidence))
        group["confidence_n"] += 1

    # Outcome/judgement is signal-level, not strategy-item-level. A trader may
    # attach several strategies to the same vote; counting each strategy as a
    # separate trade would inflate N and confidence in the scorecard.
    if signal_id not in group["outcome_signals"]:
        if signal_id:
            group["outcome_signals"].add(signal_id)
        status = canonical_status(row)
        if status == "tp_hit":
            group["tp"] += 1
            group["resolved"] += 1
        elif status == "sl_hit":
            group["sl"] += 1
            group["resolved"] += 1
        elif status == "expired":
            group["expired"] += 1

        final_r = realized_r(row)
        judged = _judge_r(item.get("relation_to_final"), final_r)
        if judged is not None:
            group["judgement_r_sum"] += judged
            group["judgement_r_n"] += 1

        correctness = _success(item.get("relation_to_final"), status)
        if correctness is not None:
            group["correct"] += correctness
            group["correct_n"] += 1

        forensics = _forensics(row)
        mfe = safe_float(forensics.get("mfe_r"), safe_float(latest_result(row).get("mfe_r")))
        mae = safe_float(forensics.get("mae_r"), safe_float(latest_result(row).get("mae_r")))
        if mfe is not None:
            group["mfe_sum"] += mfe
            group["mfe_n"] += 1
        if mae is not None:
            group["mae_sum"] += mae
            group["mae_n"] += 1


def _finalize(key: Tuple[str, ...], data: Dict[str, Any], *, dimensionality: str) -> Dict[str, Any]:
    trader, market, timeframe, direction, regime, relation = key
    resolved = int(data["resolved"])
    avg_conf = data["confidence_sum"] / data["confidence_n"] if data["confidence_n"] else None
    success_rate = data["correct"] / data["correct_n"] * 100.0 if data["correct_n"] else None
    calibration_gap = None
    if avg_conf is not None and success_rate is not None:
        calibration_gap = avg_conf - success_rate
    judgement_r = data["judgement_r_sum"] / data["judgement_r_n"] if data["judgement_r_n"] else None
    avg_mfe = data["mfe_sum"] / data["mfe_n"] if data["mfe_n"] else None
    avg_mae = data["mae_sum"] / data["mae_n"] if data["mae_n"] else None

    if resolved < 10:
        evidence = "INSUFFICIENT"
    elif judgement_r is not None and judgement_r >= 0.10:
        evidence = "PROMISING"
    elif judgement_r is not None and judgement_r <= -0.20:
        evidence = "DEGRADED"
    else:
        evidence = "OBSERVE"

    return {
        "trader": trader,
        "market": market,
        "timeframe": timeframe,
        "direction": direction,
        "regime": regime,
        "relation": relation,
        "dimensionality": dimensionality,
        "n": len(data["signals"]),
        "attribution_items": int(data["n"]),
        "resolved": resolved,
        "tp": int(data["tp"]),
        "sl": int(data["sl"]),
        "expired": int(data["expired"]),
        "strategy_count": len(data["strategies"]),
        "judgement_success_pct": round(success_rate, 2) if success_rate is not None else None,
        "judgement_expectancy_r": round(judgement_r, 4) if judgement_r is not None else None,
        "avg_confidence_pct": round(avg_conf, 2) if avg_conf is not None else None,
        "confidence_calibration_gap_pp": round(calibration_gap, 2) if calibration_gap is not None else None,
        "avg_mfe_r": round(avg_mfe, 4) if avg_mfe is not None else None,
        "avg_mae_r": round(avg_mae, 4) if avg_mae is not None else None,
        "evidence_state": evidence,
    }


def build_trader_scorecard(scoped_rows: Dict[str, Iterable[Dict[str, Any]]], *, top_n: int = 120) -> Dict[str, Any]:
    """Build aggregate and specialization scorecards without changing weights."""
    groups: Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]] = defaultdict(_new_group)
    pair_counts: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: {"co_signal": 0, "same_side": 0, "opposite_side": 0})
    total_signals = 0
    with_attribution = 0

    for scope_name, rows in (scoped_rows or {}).items():
        for row in rows or []:
            total_signals += 1
            items = _attribution_items(row)
            if not items:
                continue
            with_attribution += 1
            market = normalize_market(row).upper() or "UNKNOWN"
            timeframe = str(row.get("timeframe") or "UNKNOWN").upper()
            direction = normalize_action(row.get("action_normalized") or row.get("action"))
            regime = _regime(row)

            # Deduplicate one trader/relation/strategy per signal while retaining
            # strategy coverage.  Aggregate skill is signal-based through the
            # signals set in each group.
            for item in items:
                trader = str(item.get("trader") or "UNKNOWN").strip() or "UNKNOWN"
                relation = str(item.get("relation_to_final") or "UNKNOWN").upper()
                # Market-only baseline for trader.
                for tf, rg, dim in (("ALL", "ALL", "MARKET"), (timeframe, "ALL", "TIMEFRAME"), (timeframe, regime, "REGIME")):
                    key = (trader, market, tf, direction, rg, relation)
                    _add(groups[key], row, item)

            # Pairwise redundancy proxy: how often traders co-occur and vote the
            # same/opposite direction.  It does NOT change committee weights.
            trader_votes: Dict[str, str] = {}
            for item in items:
                trader = str(item.get("trader") or "UNKNOWN").strip() or "UNKNOWN"
                vote = normalize_action(item.get("vote_action"))
                if vote in {"LONG", "SHORT"}:
                    trader_votes[trader] = vote
            names = sorted(trader_votes)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    pair = (a, b)
                    pair_counts[pair]["co_signal"] += 1
                    if trader_votes[a] == trader_votes[b]:
                        pair_counts[pair]["same_side"] += 1
                    else:
                        pair_counts[pair]["opposite_side"] += 1

    rows_out: List[Dict[str, Any]] = []
    for key, data in groups.items():
        dim = "MARKET" if key[2] == "ALL" else ("TIMEFRAME" if key[4] == "ALL" else "REGIME")
        rows_out.append(_finalize(key, data, dimensionality=dim))

    # Prioritize evidence-bearing rows, then larger resolved samples.
    state_rank = {"PROMISING": 0, "DEGRADED": 1, "OBSERVE": 2, "INSUFFICIENT": 3}
    rows_out.sort(key=lambda r: (state_rank.get(r["evidence_state"], 9), -(r["resolved"] or 0), -(r["n"] or 0), r["trader"]))

    redundancy = []
    for (a, b), data in pair_counts.items():
        n = data["co_signal"]
        redundancy.append({
            "trader_a": a,
            "trader_b": b,
            "co_signal_n": n,
            "same_side_pct": round(data["same_side"] / n * 100.0, 2) if n else None,
            "opposite_side_pct": round(data["opposite_side"] / n * 100.0, 2) if n else None,
        })
    redundancy.sort(key=lambda r: (-(r["co_signal_n"] or 0), -(r["same_side_pct"] or 0)))

    return {
        "version": SCORECARD_VERSION,
        "authority": "RESEARCH_ONLY",
        "production_change": False,
        "scope_names": sorted(str(name) for name in (scoped_rows or {}).keys()),
        "signals_seen": total_signals,
        "signals_with_attribution": with_attribution,
        "rows": rows_out[:max(20, int(top_n))],
        "pairwise_redundancy": redundancy[:30],
        "policy": {
            "market_specific": True,
            "timeframe_specific": True,
            "regime_specific": True,
            "direction_specific": True,
            "weights_changed": False,
            "min_resolved_before_review": 10,
            "note": "El scorecard mide especialización; Commit 10 no modifica pesos del comité.",
        },
    }

# ============================================================================
# COMMIT 11 — TRADER INTELLIGENCE V2 (SHADOW / DIAGNOSTIC)
# ============================================================================
TRADER_INTELLIGENCE_V2_VERSION = "C11_TRADER_INTELLIGENCE_V2"

_REGIME_CANONICAL = {
    "TRENDING_BULL": "TREND_UP",
    "TRENDING_BEAR": "TREND_DOWN",
    "RANGING": "BALANCE",
    "HIGH_VOLATILITY": "VOLATILITY_SHOCK",
    "TREND_UP": "TREND_UP",
    "TREND_DOWN": "TREND_DOWN",
    "BALANCE": "BALANCE",
    "TRANSITION": "TRANSITION",
    "VOLATILITY_SHOCK": "VOLATILITY_SHOCK",
}


def canonical_regime(value: Any) -> str:
    raw = str(value or "UNKNOWN").strip().upper()
    return _REGIME_CANONICAL.get(raw, raw if raw else "UNKNOWN")


def _runtime_votes(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    decision = analysis.get("decision") or {}
    audit = decision.get("audit") or analysis.get("decision_audit") or {}
    if isinstance(audit, dict) and isinstance(audit.get("votes"), list):
        return [v for v in audit.get("votes") if isinstance(v, dict)]

    register = decision.get("registro_votacion") or {}
    if isinstance(register, dict) and isinstance(register.get("todos_los_votos"), list):
        return [v for v in register.get("todos_los_votos") if isinstance(v, dict)]
    return []


def build_runtime_trader_theses(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the already-finished committee vote into structured theses.

    This function executes AFTER the moderator has decided.  It never calls a
    trader again and never changes the final vote.  Missing trader-specific
    geometry is left explicit instead of being invented.
    """
    if not isinstance(analysis, dict):
        analysis = {}
    decision = analysis.get("decision") or {}
    final_action = normalize_action(decision.get("action"))
    market = str(analysis.get("system_type") or "spot").upper()
    timeframe = str(analysis.get("timeframe") or "UNKNOWN").upper()
    symbol = str(analysis.get("symbol") or "UNKNOWN")
    regime = canonical_regime((analysis.get("market_regime") or {}).get("regime"))
    levels = analysis.get("levels") or {}

    def _level(name: str) -> Optional[float]:
        value = safe_float(levels.get(name))
        return value if value is not None and value > 0 else None

    final_entry = _level("entry")
    final_sl = _level("stop_loss")
    final_tp = _level("take_profit")
    theses: List[Dict[str, Any]] = []

    for raw in _runtime_votes(analysis):
        trader = str(raw.get("trader") or "UNKNOWN")
        raw_action = str(
            raw.get("normalized_action")
            or raw.get("accion_normalizada")
            or raw.get("accion")
            or raw.get("original_action")
            or "NO_OPERAR"
        ).upper()
        direction = normalize_action(raw_action)
        confidence = safe_float(
            raw.get("original_confidence"),
            safe_float(raw.get("confianza_original"), safe_float(raw.get("confianza"), 0.0)),
        ) or 0.0
        confidence = max(0.0, min(100.0, confidence))

        disposition = str(raw.get("disposition") or "").upper()
        if disposition == "APOYO_FINAL" or (direction in {"LONG", "SHORT"} and direction == final_action):
            relation = "SUPPORT"
        elif disposition == "OPOSICION_DIRECCIONAL" or (
            direction in {"LONG", "SHORT"}
            and final_action in {"LONG", "SHORT"}
            and direction != final_action
        ):
            relation = "OPPOSE"
        else:
            relation = "NEUTRAL"

        if raw_action in {"NO_OPERAR", "NEUTRAL", "ESPERAR"}:
            stance = "VETO" if raw_action == "NO_OPERAR" and confidence >= 80.0 else "ABSTAIN"
        else:
            stance = "DIRECTIONAL"

        strategies = raw.get("strategies") or raw.get("estrategias") or []
        reasons = raw.get("reasons") or raw.get("razones") or []
        strategies = [str(v)[:120] for v in strategies if str(v).strip()][:8]
        reasons = [str(v)[:240] for v in reasons if str(v).strip()][:4]

        has_shared_geometry = relation == "SUPPORT" and final_action in {"LONG", "SHORT"}
        thesis = {
            "trader": trader,
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction if direction in {"LONG", "SHORT"} else "NO_EDGE",
            "conviction_pct": round(confidence, 2),
            "regime": regime,
            "stance": stance,
            "relation_to_final": relation,
            "setups": strategies,
            "entry_zone": final_entry if has_shared_geometry else None,
            "invalidation": final_sl if has_shared_geometry else None,
            "objective": final_tp if has_shared_geometry else None,
            "geometry_source": "FINAL_SYSTEM_LEVELS" if has_shared_geometry else "TRADER_SPECIFIC_GEOMETRY_NOT_AVAILABLE",
            "evidence_for": reasons,
            "evidence_against": [],
            "explicit_counter_evidence_available": False,
            "competence_key": f"{market}|{timeframe}|{direction}|{regime}",
            "affects_vote": False,
            "affects_levels": False,
        }
        theses.append(thesis)

    abstain_n = sum(1 for t in theses if t["stance"] == "ABSTAIN")
    veto_n = sum(1 for t in theses if t["stance"] == "VETO")
    directional_n = sum(1 for t in theses if t["stance"] == "DIRECTIONAL")
    return {
        "version": TRADER_INTELLIGENCE_V2_VERSION,
        "authority": "SHADOW_DIAGNOSTIC",
        "production_change": False,
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "final_direction": final_action,
        "theses": theses,
        "coverage": {
            "traders_seen": len(theses),
            "directional": directional_n,
            "abstentions": abstain_n,
            "veto_stances": veto_n,
        },
        "policy": {
            "market_specific": True,
            "timeframe_specific": True,
            "direction_specific": True,
            "regime_specific": True,
            "abstention_allowed": True,
            "missing_geometry_is_not_invented": True,
            "weights_changed": False,
        },
    }


def _created_key(row: Dict[str, Any]) -> str:
    return str(row.get("created_at") or row.get("source_candle_timestamp") or row.get("id") or "")


def build_trader_intelligence_v2_summary(
    scoped_rows: Dict[str, Iterable[Dict[str, Any]]], *, top_n: int = 120
) -> Dict[str, Any]:
    """Temporal validation + calibration diagnostics for Commit 11.

    The split is chronological 70/30 and remains research-only.  One trader is
    counted once per signal/relation, even when it emitted multiple strategies.
    """
    baseline = build_trader_scorecard(scoped_rows, top_n=top_n)
    groups: Dict[Tuple[str, str, str, str, str, str], List[Tuple[str, float]]] = defaultdict(list)
    thesis_snapshots = 0
    thesis_signals = 0
    total_rows = 0

    for rows in (scoped_rows or {}).values():
        for row in rows or []:
            total_rows += 1
            learning = learning_context(row)
            runtime = learning.get("trader_intelligence_v2") or {}
            if isinstance(runtime, dict) and isinstance(runtime.get("theses"), list):
                thesis_signals += 1
                thesis_snapshots += len([t for t in runtime.get("theses") if isinstance(t, dict)])

            final_r = realized_r(row)
            if final_r is None:
                continue
            market = normalize_market(row).upper() or "UNKNOWN"
            timeframe = str(row.get("timeframe") or "UNKNOWN").upper()
            direction = normalize_action(row.get("action_normalized") or row.get("action"))
            regime = canonical_regime(_regime(row))
            seen = set()
            for item in _attribution_items(row):
                trader = str(item.get("trader") or "UNKNOWN").strip() or "UNKNOWN"
                relation = str(item.get("relation_to_final") or "UNKNOWN").upper()
                if relation not in {"SUPPORT", "OPPOSE"}:
                    continue
                dedupe = (trader, relation)
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                judged = _judge_r(relation, final_r)
                if judged is None:
                    continue
                # Market, TF and regime rows. Direction is always kept separate.
                for tf, rg in (("ALL", "ALL"), (timeframe, "ALL"), (timeframe, regime)):
                    key = (trader, market, tf, direction, rg, relation)
                    groups[key].append((_created_key(row), judged))

    validation_rows: List[Dict[str, Any]] = []
    for key, observations in groups.items():
        observations.sort(key=lambda item: item[0])
        n = len(observations)
        if n < 3:
            continue
        cut = max(1, min(n - 1, int(math.floor(n * 0.70))))
        discovery = [v for _, v in observations[:cut]]
        validation = [v for _, v in observations[cut:]]
        discovery_exp = sum(discovery) / len(discovery) if discovery else None
        validation_exp = sum(validation) / len(validation) if validation else None
        trader, market, tf, direction, regime, relation = key

        if n < 25:
            state = "INSUFFICIENT"
        elif len(validation) < 10:
            state = "NEEDS_OOS"
        elif discovery_exp is not None and validation_exp is not None and discovery_exp > 0 and validation_exp >= 0.05:
            state = "PROMISING_OOS"
        elif validation_exp is not None and validation_exp <= -0.20:
            state = "DEGRADED_OOS"
        else:
            state = "OBSERVE"

        validation_rows.append({
            "trader": trader,
            "market": market,
            "timeframe": tf,
            "direction": direction,
            "regime": regime,
            "relation": relation,
            "n_resolved": n,
            "discovery_n": len(discovery),
            "validation_n": len(validation),
            "discovery_expectancy_r": round(discovery_exp, 4) if discovery_exp is not None else None,
            "validation_expectancy_r": round(validation_exp, 4) if validation_exp is not None else None,
            "state": state,
        })

    state_rank = {"PROMISING_OOS": 0, "DEGRADED_OOS": 1, "OBSERVE": 2, "NEEDS_OOS": 3, "INSUFFICIENT": 4}
    validation_rows.sort(key=lambda r: (state_rank.get(r["state"], 9), -r["n_resolved"], r["trader"]))

    return {
        "version": TRADER_INTELLIGENCE_V2_VERSION,
        "authority": "SHADOW_DIAGNOSTIC",
        "production_change": False,
        "scorecard_v1": baseline,
        "temporal_validation": validation_rows[:max(20, int(top_n))],
        "runtime_thesis_coverage": {
            "signals_seen": total_rows,
            "signals_with_c11_theses": thesis_signals,
            "theses_persisted": thesis_snapshots,
        },
        "policy": {
            "min_total_resolved_for_weight_review": 25,
            "min_validation_resolved_for_weight_review": 10,
            "validation_split": "70_30_CHRONOLOGICAL",
            "confidence_is_diagnostic_only": True,
            "abstention_is_measured": True,
            "weights_changed": False,
        },
    }
