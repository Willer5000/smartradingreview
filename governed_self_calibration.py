"""Commit 14 — governed closed-loop self-calibration for SmartradingReview v1.0.

The controller connects the diagnostic learning created in Commits 11-13 with
bounded production authority.  It never invents a direction, never lowers the
publication/Safety gates and never grows leverage.  Positive adjustments need
chronological evidence plus cost coverage; negative evidence may attenuate a
trader earlier as a protective action.

The state is deterministic from persisted evidence.  A process restart therefore
falls back to neutral weights until the next bounded governance/autopilot refresh.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional
import hashlib
import math
import threading

from learning_integrity import learning_context, normalize_market, safe_float
from trader_intelligence import build_trader_intelligence_v2_summary
from dynamic_expert_committee import (
    build_shadow_profile,
    install_shadow_profile,
    install_governed_profile,
)
from execution_challenger_lab import (
    summarize_execution_challenger_evidence,
    install_governed_execution_profile,
)

SELF_CALIBRATION_VERSION = "C14_GOVERNED_SELF_CALIBRATION_V1"
QUALITY_SCORE_VERSION = "36W_V2_NORMALIZED"
CANARY_FRACTION = 0.25
MAX_RESOLVED_ROWS = 800

# Positive authority is deliberately harder than merely displaying a promising
# row in Analytics.
EXPERT_ACTIVE_N = 50
EXPERT_ACTIVE_VALIDATION_N = 15
EXPERT_ACTIVE_VALIDATION_R = 0.15
EXEC_CANARY_N = 25
EXEC_CANARY_VALIDATION_N = 10
EXEC_CANARY_NET_R = 0.05
EXEC_ACTIVE_N = 50
EXEC_ACTIVE_VALIDATION_N = 15
EXEC_ACTIVE_NET_R = 0.10
MIN_ECONOMICS_COVERAGE_PCT = 95.0

_STATE_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {
    "version": SELF_CALIBRATION_VERSION,
    "state": "OBSERVE",
    "production_change": False,
    "updated_at": None,
    "expert_profile": {"rows": []},
    "execution_profile": {"rows": []},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _governance_economics_ready(governance: Dict[str, Any]) -> bool:
    governance = governance or {}
    if governance.get("stale"):
        return False
    coverage = governance.get("coverage") or {}
    evidence = governance.get("evidence") or {}
    total = evidence.get("total") or {}
    pct = safe_float(total.get("model_complete_net_coverage_pct"), 0.0) or 0.0
    return bool(coverage.get("complete", False) and pct >= MIN_ECONOMICS_COVERAGE_PCT)


def _build_expert_profile(
    dynamic_shadow: Dict[str, Any],
    governance: Dict[str, Any],
) -> Dict[str, Any]:
    economics_ready = _governance_economics_ready(governance)
    rows: List[Dict[str, Any]] = []

    for row in (dynamic_shadow or {}).get("weights") or []:
        if not isinstance(row, dict):
            continue
        shadow_mult = safe_float(row.get("multiplier"), 1.0) or 1.0
        val_r = safe_float(row.get("validation_expectancy_r"))
        disc_r = safe_float(row.get("discovery_expectancy_r"))
        n = int(row.get("n_resolved") or 0)
        validation_n = int(row.get("validation_n") or 0)
        evidence = str(row.get("evidence") or "OBSERVE").upper()

        state = "OBSERVE"
        applied = 1.0
        reason = "EVIDENCE_NOT_READY"

        # Negative OOS evidence can protect earlier.  The attenuation is capped
        # so one trader can never disappear from the committee solely because of
        # an adaptive layer.
        if evidence == "NEGATIVE_OOS" and validation_n >= 10 and val_r is not None:
            state = "PROTECT"
            applied = _clamp(min(1.0, shadow_mult), 0.85, 1.0)
            reason = "NEGATIVE_OOS_PROTECTION"
        elif (
            evidence == "POSITIVE_OOS"
            and economics_ready
            and n >= 25
            and validation_n >= 10
            and val_r is not None
            and val_r >= 0.05
            and disc_r is not None
            and disc_r > 0
        ):
            if n >= EXPERT_ACTIVE_N and validation_n >= EXPERT_ACTIVE_VALIDATION_N and val_r >= EXPERT_ACTIVE_VALIDATION_R:
                state = "ACTIVE"
                applied = _clamp(shadow_mult, 1.0, 1.20)
                reason = "ROBUST_POSITIVE_OOS"
            else:
                state = "CANARY"
                # Only a fraction of the proposed uplift is allowed before the
                # larger sample exists.
                applied = 1.0 + (max(1.0, shadow_mult) - 1.0) * 0.35
                applied = _clamp(applied, 1.0, 1.08)
                reason = "POSITIVE_OOS_CANARY"
        elif evidence == "POSITIVE_OOS" and not economics_ready:
            reason = "WAITING_ECONOMICS_COVERAGE"

        out = dict(row)
        out.update({
            "state": state,
            "production_multiplier": round(applied, 4),
            "reason": reason,
            "canary_fraction": CANARY_FRACTION if state == "CANARY" else 1.0,
        })
        rows.append(out)

    return {
        "version": SELF_CALIBRATION_VERSION,
        "authority": "GOVERNED_BOUNDED",
        "economics_ready": economics_ready,
        "rows": rows,
        "active": sum(1 for r in rows if r.get("state") == "ACTIVE"),
        "canary": sum(1 for r in rows if r.get("state") == "CANARY"),
        "protect": sum(1 for r in rows if r.get("state") == "PROTECT"),
    }


def _build_execution_profile(
    challenger_summary: Dict[str, Any],
    governance: Dict[str, Any],
) -> Dict[str, Any]:
    """Select at most one governed execution champion per market×symbol×TF.

    RC9.8.8 adds Entry reachability as evidence without redefining a missed
    limit order as a losing trade.  Positive authority remains slow and
    bounded; negative eight-trade evidence removes authority immediately.
    """
    economics_ready = _governance_economics_ready(governance)
    governance_fresh = not bool((governance or {}).get("stale", False))

    summary_rows = [
        row for row in ((challenger_summary or {}).get("rows") or [])
        if isinstance(row, dict)
    ]
    baseline_by_cell: Dict[tuple, Dict[str, Any]] = {}
    for row in summary_rows:
        if str(row.get("candidate") or "").upper() != "BASELINE":
            continue
        key = (
            str(row.get("market") or "").upper(),
            str(row.get("symbol") or "").upper(),
            str(row.get("timeframe") or "").upper(),
            str(row.get("action") or "ALL").upper(),
        )
        baseline_by_cell[key] = row

    candidates: List[Dict[str, Any]] = []
    for row in summary_rows:
        market = str(row.get("market") or "").upper()
        name = str(row.get("candidate") or "").upper()
        if market not in {"FUTURES", "SPOT"} or name in {"", "BASELINE"}:
            continue

        key = (
            market,
            str(row.get("symbol") or "").upper(),
            str(row.get("timeframe") or "").upper(),
            str(row.get("action") or "ALL").upper(),
        )
        baseline = baseline_by_cell.get(key) or {}
        n = int(row.get("resolved") or 0)
        val_n = int(row.get("validation_resolved") or 0)
        entry_gain = safe_float(row.get("entry_reach_improvement_pp"), 0.0) or 0.0
        baseline_resolved = int(baseline.get("resolved") or 0)
        reachability_candidate = name == "REACHABILITY_BALANCED"
        alpha_decay = bool(row.get("alpha_decay"))
        alpha_reason = str(row.get("alpha_decay_reason") or "")

        gross_r = safe_float(row.get("expectancy_r"))
        val_gross_r = safe_float(row.get("validation_expectancy_r"))
        gross_pf = safe_float(row.get("profit_factor"))
        val_gross_pf = safe_float(row.get("validation_profit_factor"))
        baseline_val_gross = safe_float(baseline.get("validation_expectancy_r"))
        gross_improvement = (
            val_gross_r - baseline_val_gross
            if val_gross_r is not None and baseline_val_gross is not None
            else None
        )

        net_r = safe_float(row.get("net_expectancy_r"))
        val_net_r = safe_float(row.get("validation_net_expectancy_r"))
        net_pf = safe_float(row.get("net_profit_factor"))
        val_net_pf = safe_float(row.get("validation_net_profit_factor"))
        net_improvement = safe_float(row.get("validation_net_improvement_vs_baseline_r"))

        state = "OBSERVE"
        reason = "EVIDENCE_NOT_READY"

        # Alpha decay is asymmetric by design: slow promotion, fast rollback.
        if alpha_decay:
            reason = f"ALPHA_DECAY:{alpha_reason or 'RECENT_EDGE_DECAY'}"
        elif not governance_fresh:
            reason = "WAITING_FRESH_GOVERNANCE"
        elif reachability_candidate and entry_gain < 8.0:
            reason = "ENTRY_REACHABILITY_GAIN_TOO_SMALL"
        elif market == "FUTURES":
            # Futures keeps the conservative cost-complete gate.
            improvement_canary = bool(
                (net_improvement is not None and net_improvement >= 0.05)
                or (reachability_candidate and baseline_resolved < 10)
            )
            improvement_active = bool(
                (net_improvement is not None and net_improvement >= 0.10)
                or (reachability_candidate and baseline_resolved < 10)
            )
            if not economics_ready:
                reason = "WAITING_ECONOMICS_COVERAGE"
            elif (
                n >= EXEC_ACTIVE_N and val_n >= EXEC_ACTIVE_VALIDATION_N
                and net_r is not None and net_r >= EXEC_ACTIVE_NET_R
                and val_net_r is not None and val_net_r >= EXEC_ACTIVE_NET_R
                and net_pf is not None and net_pf >= 1.25
                and (val_net_pf is None or val_net_pf >= 1.15)
                and improvement_active
                and (not reachability_candidate or entry_gain >= 12.0)
            ):
                state = "ACTIVE"
                reason = "ROBUST_NET_OOS_ENTRY_CHAMPION"
            elif (
                n >= EXEC_CANARY_N and val_n >= EXEC_CANARY_VALIDATION_N
                and net_r is not None and net_r >= EXEC_CANARY_NET_R
                and val_net_r is not None and val_net_r >= EXEC_CANARY_NET_R
                and net_pf is not None and net_pf >= 1.15
                and improvement_canary
            ):
                state = "CANARY"
                reason = "NET_OOS_ENTRY_CHALLENGER_CANARY"
        else:
            # Spot has no leverage/funding risk-growth authority here. Entry
            # geometry is allowed to learn from its own market×symbol×TF evidence
            # even while the broader Research federation is still incomplete.
            # Promotion remains slow through larger local samples + chronological
            # validation + PF/expectancy + reachability gates.
            improvement_canary = bool(
                (gross_improvement is not None and gross_improvement >= 0.10)
                or (reachability_candidate and baseline_resolved < 10)
            )
            improvement_active = bool(
                (gross_improvement is not None and gross_improvement >= 0.15)
                or (reachability_candidate and baseline_resolved < 10)
            )
            if (
                n >= 60 and val_n >= 18
                and gross_r is not None and gross_r >= 0.15
                and val_gross_r is not None and val_gross_r >= 0.15
                and gross_pf is not None and gross_pf >= 1.35
                and (val_gross_pf is None or val_gross_pf >= 1.20)
                and improvement_active
                and (not reachability_candidate or entry_gain >= 12.0)
            ):
                state = "ACTIVE"
                reason = "ROBUST_SPOT_OOS_ENTRY_CHAMPION"
            elif (
                n >= 30 and val_n >= 10
                and gross_r is not None and gross_r >= 0.10
                and val_gross_r is not None and val_gross_r >= 0.10
                and gross_pf is not None and gross_pf >= 1.25
                and improvement_canary
            ):
                state = "CANARY"
                reason = "SPOT_OOS_ENTRY_CHALLENGER_CANARY"

        candidates.append({
            **row,
            "state": state,
            "reason": reason,
            "entry_learning": True,
            "no_entry_counts_in_win_rate": False,
            "baseline_resolved": baseline_resolved,
            "gross_validation_improvement_vs_baseline_r": (
                round(gross_improvement, 4) if gross_improvement is not None else None
            ),
        })

    by_cell: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in candidates:
        key = (
            str(row.get("market") or ""),
            str(row.get("symbol") or ""),
            str(row.get("timeframe") or ""),
            str(row.get("action") or "ALL"),
        )
        by_cell.setdefault(key, []).append(row)

    selected_rows: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    for key, cell_rows in by_cell.items():
        eligible = [r for r in cell_rows if r.get("state") in {"CANARY", "ACTIVE"}]
        eligible.sort(key=lambda r: (
            1 if r.get("state") == "ACTIVE" else 0,
            safe_float(r.get("validation_net_expectancy_r"),
                       safe_float(r.get("validation_expectancy_r"), -999.0)) or -999.0,
            safe_float(r.get("entry_reach_improvement_pp"), 0.0) or 0.0,
            int(r.get("validation_resolved") or 0),
        ), reverse=True)
        winner = eligible[0] if eligible else None
        if winner:
            selected_rows.append(dict(winner))
        for row in cell_rows:
            out = dict(row)
            if winner and row.get("candidate") == winner.get("candidate"):
                out["selected"] = True
            else:
                out["selected"] = False
                if out.get("state") in {"CANARY", "ACTIVE"}:
                    out["state"] = "OBSERVE"
                    out["reason"] = "BETTER_CHALLENGER_SELECTED_FOR_CELL"
            rows.append(out)

    return {
        "version": "RC9_8_8_GOVERNED_ENTRY_LEARNING_V1",
        "authority": "GOVERNED_BOUNDED",
        "economics_ready": economics_ready,
        "rows": rows,
        "selected": selected_rows,
        "canary_fraction": CANARY_FRACTION,
        "policy": {
            "selection_scope": "MARKET_SYMBOL_TIMEFRAME_ACTION",
            "one_champion_per_cell": True,
            "spot_futures_separate": True,
            "global_research_completion_required_for_entry_geometry": False,
            "no_entry_counts_as_trade": False,
            "no_entry_counts_in_win_rate": False,
            "entry_reachability_can_adjust_geometry": True,
            "direction_change_allowed": False,
            "safety_threshold_can_be_lowered": False,
            "stop_widening_allowed": False,
            "alpha_decay_window_resolved_trades": 8,
            "alpha_decay_rollback": "IMMEDIATE_TO_OBSERVE_BASELINE",
        },
    }


def build_self_calibration_state(
    trader_intelligence_v2: Dict[str, Any],
    dynamic_shadow: Dict[str, Any],
    challenger_summary: Dict[str, Any],
    governance: Dict[str, Any],
) -> Dict[str, Any]:
    expert = _build_expert_profile(dynamic_shadow, governance)
    execution = _build_execution_profile(challenger_summary, governance)
    execution_selected = execution.get("selected") or []
    if isinstance(execution_selected, dict):
        execution_selected = [execution_selected]

    active_n = int(expert.get("active") or 0) + sum(1 for r in execution_selected if str(r.get("state") or "") == "ACTIVE")
    canary_n = int(expert.get("canary") or 0) + sum(1 for r in execution_selected if str(r.get("state") or "") == "CANARY")
    protect_n = int(expert.get("protect") or 0)
    if active_n:
        state = "ACTIVE"
    elif canary_n:
        state = "CANARY"
    elif protect_n:
        state = "PROTECT"
    else:
        state = "OBSERVE"

    result = {
        "version": SELF_CALIBRATION_VERSION,
        "state": state,
        "production_change": bool(active_n or canary_n or protect_n),
        "updated_at": _now_iso(),
        "expert_profile": expert,
        "execution_profile": execution,
        "summary": {
            "active_adjustments": active_n,
            "canary_adjustments": canary_n,
            "protective_adjustments": protect_n,
            "economics_ready": bool(expert.get("economics_ready") and execution.get("economics_ready")),
        },
        "policy": {
            "objective": "MAXIMIZE_ROBUST_NET_EDGE_UNDER_SAFETY_CONSTRAINTS",
            "safety_threshold_can_be_lowered": False,
            "direction_can_be_invented": False,
            "leverage_growth_allowed_here": False,
            "spot_futures_separate": True,
            "positive_requires_oos": True,
            "futures_positive_requires_cost_coverage_pct": MIN_ECONOMICS_COVERAGE_PCT,
            "spot_entry_positive_requires_local_oos": True,
            "negative_evidence_can_protect_earlier": True,
            "canary_fraction": CANARY_FRACTION,
            "rollback": "AUTOMATIC_TO_BASELINE_WHEN_EVIDENCE_NO_LONGER_QUALIFIES",
        },
    }
    return result


def install_self_calibration_state(state: Dict[str, Any]) -> None:
    global _STATE
    safe_state = deepcopy(state if isinstance(state, dict) else {})
    with _STATE_LOCK:
        _STATE = safe_state
    install_governed_profile(safe_state.get("expert_profile") or {})
    install_governed_execution_profile(safe_state.get("execution_profile") or {})


def get_self_calibration_state() -> Dict[str, Any]:
    with _STATE_LOCK:
        return deepcopy(_STATE)


def _result_list(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    value = row.get("signal_results") or row.get("result") or []
    if isinstance(value, dict):
        return [value]
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def refresh_self_calibration_from_db(db, governance: Dict[str, Any], *, days_back: int = 90) -> Dict[str, Any]:
    """Slow bounded refresh for execution + Entry-reachability learning.

    RC9.8.8 loads terminal current-generation rows (TP/SL/expired) in one
    bounded query. `expired_no_entry` participates only in activation learning;
    it never enters WR/expectancy. No DataFrames or new Supabase tables are
    created. The caller throttles this to at most twice per day.
    """
    if db is None or not getattr(db, "enabled", False):
        return {"version": SELF_CALIBRATION_VERSION, "state": "OBSERVE", "reason": "SUPABASE_DISABLED"}
    try:
        # Respect the existing Main Supabase free-plan budget.  When the guard
        # is near its limit we keep the last installed profile and simply wait
        # for a later cycle; learning is slower, not less safe.
        if hasattr(db, "free_plan_allows") and not db.free_plan_allows("important"):
            state = get_self_calibration_state()
            state["refresh"] = {
                "deferred": True,
                "reason": "SUPABASE_FREE_PLAN_GUARD",
                "max_rows": MAX_RESOLVED_ROWS,
            }
            return state
        from q6_integrity import read_pages
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(14, min(int(days_back), 180)))

        def query():
            return (
                db.client.table("signals")
                .select(
                    "id,symbol,timeframe,system_type,action_normalized,status,created_at,"
                    "entry_price,stop_loss,take_profit,risk_reward,"
                    "q6_learning:context->learning,q6_execution:context->execution,"
                    "signal_results(status,gross_r,modeled_net_r,economics_cost_components_complete,"
                    "execution_forensics,mfe_r,mae_r,created_at)"
                )
                .gte("created_at", cutoff.isoformat())
                .lt("created_at", now.isoformat())
                .eq("context->execution->>quality_score_version", QUALITY_SCORE_VERSION)
                .in_("action_normalized", ["LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"])
                .in_("status", ["tp_hit", "sl_hit", "expired"])
                .order("created_at", desc=True)
                .order("id", desc=True)
            )

        rows = read_pages(query, page_size=160, max_rows=MAX_RESOLVED_ROWS, budget_seconds=12)
        normalized: List[Dict[str, Any]] = []
        for row in rows or []:
            row = dict(row or {})
            row["context"] = {
                "learning": row.pop("q6_learning", {}) or {},
                "execution": row.pop("q6_execution", {}) or {},
            }
            normalized.append(row)

        # Query newest-first so a bounded window always contains the freshest
        # evidence needed for alpha decay; restore chronological order locally.
        normalized.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))

        scopes: Dict[str, List[Dict[str, Any]]] = {
            "SPOT_CURRENT": [],
            "FUTURES_CURRENT": [],
        }
        for row in normalized:
            market = normalize_market(row).upper()
            if market == "SPOT":
                scopes["SPOT_CURRENT"].append(row)
            elif market == "FUTURES":
                scopes["FUTURES_CURRENT"].append(row)

        # Existing trader-intelligence statistics remain trade-only.  Expired
        # no-entry rows are passed only to the execution challenger summary.
        resolved_scopes: Dict[str, List[Dict[str, Any]]] = {
            "SPOT_CURRENT": [],
            "FUTURES_CURRENT": [],
        }
        for scope_name, scope_rows in scopes.items():
            resolved_scopes[scope_name] = [
                row for row in scope_rows
                if str(row.get("status") or "").lower() in {"tp_hit", "sl_hit"}
            ]

        intelligence = build_trader_intelligence_v2_summary(resolved_scopes)
        shadow = build_shadow_profile(intelligence, governance)
        install_shadow_profile(shadow)
        challenger = summarize_execution_challenger_evidence(scopes)
        state = build_self_calibration_state(intelligence, shadow, challenger, governance)
        state["refresh"] = {
            "terminal_rows_loaded": len(normalized),
            "resolved_trade_rows_loaded": sum(len(v) for v in resolved_scopes.values()),
            "expired_rows_loaded": sum(
                1 for row in normalized if str(row.get("status") or "").lower() == "expired"
            ),
            "max_rows": MAX_RESOLVED_ROWS,
            "query_budget_seconds": 12,
            "no_entry_affects_win_rate": False,
            "coverage_complete": bool((getattr(rows, "coverage", {}) or {}).get("complete", False)),
        }
        install_self_calibration_state(state)
        return state
    except Exception as exc:
        # Fail-neutral: existing core trading continues with baseline settings.
        state = {
            "version": SELF_CALIBRATION_VERSION,
            "state": "OBSERVE",
            "production_change": False,
            "updated_at": _now_iso(),
            "reason": f"REFRESH_FAILED:{type(exc).__name__}",
            "error": str(exc)[:180],
        }
        install_self_calibration_state(state)
        return state
