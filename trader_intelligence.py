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
