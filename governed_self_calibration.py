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
MAX_RESOLVED_ROWS = 1200

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
    economics_ready = _governance_economics_ready(governance)
    candidates: List[Dict[str, Any]] = []
    for row in (challenger_summary or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "").upper()
        name = str(row.get("candidate") or "").upper()
        if market != "FUTURES" or name in {"", "BASELINE"}:
            continue
        n = int(row.get("resolved") or 0)
        val_n = int(row.get("validation_resolved") or 0)
        net_r = safe_float(row.get("net_expectancy_r"))
        val_net_r = safe_float(row.get("validation_net_expectancy_r"))
        pf = safe_float(row.get("net_profit_factor"))
        improvement = safe_float(row.get("validation_net_improvement_vs_baseline_r"))

        state = "OBSERVE"
        reason = "EVIDENCE_NOT_READY"
        if not economics_ready:
            reason = "WAITING_ECONOMICS_COVERAGE"
        elif (
            n >= EXEC_ACTIVE_N and val_n >= EXEC_ACTIVE_VALIDATION_N
            and net_r is not None and net_r >= EXEC_ACTIVE_NET_R
            and val_net_r is not None and val_net_r >= EXEC_ACTIVE_NET_R
            and pf is not None and pf >= 1.25
            and improvement is not None and improvement >= 0.10
        ):
            state = "ACTIVE"
            reason = "ROBUST_NET_OOS_CHAMPION"
        elif (
            n >= EXEC_CANARY_N and val_n >= EXEC_CANARY_VALIDATION_N
            and net_r is not None and net_r >= EXEC_CANARY_NET_R
            and val_net_r is not None and val_net_r >= EXEC_CANARY_NET_R
            and pf is not None and pf >= 1.15
            and improvement is not None and improvement >= 0.05
        ):
            state = "CANARY"
            reason = "NET_OOS_CHALLENGER_CANARY"
        candidates.append({**row, "state": state, "reason": reason})

    # Exactly one execution champion per market.  This keeps multiple testing
    # from turning several simultaneous experiments into production changes.
    eligible = [r for r in candidates if r.get("state") in {"CANARY", "ACTIVE"}]
    eligible.sort(
        key=lambda r: (
            1 if r.get("state") == "ACTIVE" else 0,
            safe_float(r.get("validation_net_expectancy_r"), -999.0) or -999.0,
            int(r.get("validation_resolved") or 0),
        ),
        reverse=True,
    )
    winner = eligible[0] if eligible else None
    rows = []
    for row in candidates:
        out = dict(row)
        if winner and row.get("candidate") == winner.get("candidate") and row.get("market") == winner.get("market"):
            out["selected"] = True
        else:
            out["selected"] = False
            if out.get("state") in {"CANARY", "ACTIVE"}:
                out["state"] = "OBSERVE"
                out["reason"] = "BETTER_CHALLENGER_SELECTED"
        rows.append(out)

    return {
        "version": SELF_CALIBRATION_VERSION,
        "authority": "GOVERNED_BOUNDED",
        "economics_ready": economics_ready,
        "rows": rows,
        "selected": deepcopy(winner) if winner else None,
        "canary_fraction": CANARY_FRACTION,
    }


def build_self_calibration_state(
    trader_intelligence_v2: Dict[str, Any],
    dynamic_shadow: Dict[str, Any],
    challenger_summary: Dict[str, Any],
    governance: Dict[str, Any],
) -> Dict[str, Any]:
    expert = _build_expert_profile(dynamic_shadow, governance)
    execution = _build_execution_profile(challenger_summary, governance)
    execution_selected = execution.get("selected") or {}

    active_n = int(expert.get("active") or 0) + int(str(execution_selected.get("state") or "") == "ACTIVE")
    canary_n = int(expert.get("canary") or 0) + int(str(execution_selected.get("state") or "") == "CANARY")
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
            "positive_requires_cost_coverage_pct": MIN_ECONOMICS_COVERAGE_PCT,
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
    """Bounded 4h refresh using only resolved V2 rows.

    No DataFrames are created and only resolved current-generation rows are
    loaded, keeping the operation suitable for Render's small memory budget.
    """
    if db is None or not getattr(db, "enabled", False):
        return {"version": SELF_CALIBRATION_VERSION, "state": "OBSERVE", "reason": "SUPABASE_DISABLED"}
    try:
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
                .in_("status", ["tp_hit", "sl_hit"])
                .order("created_at", desc=False)
                .order("id", desc=False)
            )

        rows = read_pages(query, page_size=200, max_rows=MAX_RESOLVED_ROWS, budget_seconds=20)
        normalized: List[Dict[str, Any]] = []
        for row in rows or []:
            row = dict(row or {})
            row["context"] = {
                "learning": row.pop("q6_learning", {}) or {},
                "execution": row.pop("q6_execution", {}) or {},
            }
            normalized.append(row)

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

        intelligence = build_trader_intelligence_v2_summary(scopes)
        shadow = build_shadow_profile(intelligence, governance)
        install_shadow_profile(shadow)
        challenger = summarize_execution_challenger_evidence(scopes)
        state = build_self_calibration_state(intelligence, shadow, challenger, governance)
        state["refresh"] = {
            "resolved_rows_loaded": len(normalized),
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
