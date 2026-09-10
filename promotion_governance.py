"""Commit 9 — governed quality + risk scaling from net-edge evidence.

The system does not execute exchange orders, so this module never fabricates
"realized" costs.  Positive quality/risk authority can use MODEL-COMPLETE
execution economics: the configured conservative fee+slippage model plus public
KuCoin funding observed in the actual Entry→Exit window.

Authorities remain separated:
- quality_optimization_allowed: choose only among already-valid structural
  Entry/SL/TP configurations; never lower Safety or invent a direction.
- strategy_veto_authority_allowed: validated ACTIVE strategies are veto-only.
- risk_growth_allowed: may enable risk-budget leverage only after substantially
  stronger net-edge evidence than quality optimization.

Any missing/stale evidence fails closed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
import json
import math
import threading
import time

PROMOTION_GOVERNANCE_VERSION = "C9_NET_EDGE_GOVERNANCE_V2"
QUALITY_SCORE_VERSION = "36W_V2_NORMALIZED"
GOVERNANCE_SCOPE = "FUTURES_GLOBAL"

# Quality selection gates.
MIN_RESOLVED = 25
MIN_VALIDATION_RESOLVED = 10
MIN_GROSS_EXPECTANCY_R = 0.10
MIN_MODELED_NET_EXPECTANCY_R = 0.05
MIN_PROFIT_FACTOR = 1.15
MIN_VALIDATION_PROFIT_FACTOR = 1.05
MAX_CONSECUTIVE_SL_FOR_POSITIVE_AUTHORITY = 5
RECENT_WINDOW = 10
MIN_RECENT_EXPECTANCY_R = -0.10

# Commit 9 risk-growth gates are deliberately much stronger.
MIN_RISK_GROWTH_RESOLVED = 50
MIN_RISK_GROWTH_VALIDATION = 15
MIN_RISK_GROWTH_NET_EXPECTANCY_R = 0.15
MIN_RISK_GROWTH_NET_PROFIT_FACTOR = 1.25
MIN_RISK_GROWTH_VALIDATION_EXPECTANCY_R = 0.10
MIN_RISK_GROWTH_VALIDATION_PF = 1.15
MIN_RISK_GROWTH_RECENT_EXPECTANCY_R = 0.05
MAX_RISK_GROWTH_AVG_MAE_R = 0.80
MAX_CONSECUTIVE_SL_FOR_RISK_GROWTH = 3
MIN_ECONOMICS_COMPLETE_COVERAGE_PCT = 95.0

GOVERNANCE_STALE_HOURS = 8

_cache_lock = threading.Lock()
_status_cache: Optional[tuple] = None
_status_cache_ttl = 180.0


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
    return bool(value)


def _parse_dt(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _first_result(row: Dict[str, Any]) -> Dict[str, Any]:
    result = row.get("signal_results") or row.get("result") or {}
    if isinstance(result, list):
        result = result[0] if result and isinstance(result[0], dict) else {}
    return result if isinstance(result, dict) else {}


def _is_verified_official_futures(row: Dict[str, Any]) -> bool:
    learning = _as_dict(row.get("q6_learning"))
    if not learning:
        learning = _as_dict((_as_dict(row.get("context"))).get("learning"))
    return bool(
        str(row.get("system_type") or "").lower() == "futures"
        and learning.get("cohort") == "FUTURES_PERPETUAL_REAL_CLOSED_V1"
        and learning.get("market_data_source") == "KUCOIN_FUTURES_PERPETUAL_REST"
        and not _as_bool(learning.get("market_data_is_synthetic", True))
        and _as_bool(learning.get("source_candle_closed", False))
        and _as_bool(learning.get("statistically_eligible", False))
        and str(learning.get("evaluation_role") or "").upper() == "EXECUTABLE_SIGNAL"
    )


def _gross_r(row: Dict[str, Any]) -> Optional[float]:
    result = _first_result(row)
    status = str(result.get("status") or row.get("status") or "").lower()
    stored = _safe_float(result.get("gross_r"))
    if stored is not None and status in {"tp_hit", "sl_hit"}:
        return stored
    if status == "sl_hit":
        return -1.0
    if status != "tp_hit":
        return None
    rr = _safe_float(row.get("risk_reward"))
    if rr is not None and rr > 0:
        return rr
    entry = _safe_float(row.get("entry_price") or row.get("entry"))
    sl = _safe_float(row.get("stop_loss"))
    tp = _safe_float(row.get("take_profit"))
    if entry and sl and tp:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk > 0:
            return reward / risk
    return None


def _actual_net_r(row: Dict[str, Any]) -> Optional[float]:
    """Actual account net-R only if a future exchange integration persisted it."""
    result = _first_result(row)
    raw_net = result.get("net_pnl_pct")
    if raw_net is None:
        return None
    entry = _safe_float(row.get("entry_price") or row.get("entry"))
    sl = _safe_float(row.get("stop_loss"))
    net_pct = _safe_float(raw_net)
    if entry is None or sl is None or net_pct is None or entry <= 0:
        return None
    risk_pct = abs(entry - sl) / entry * 100.0
    if risk_pct <= 0:
        return None
    return net_pct / risk_pct


def _model_complete_net_r(row: Dict[str, Any]) -> Optional[float]:
    """Return conservative model-complete net R, or stronger actual net R."""
    actual = _actual_net_r(row)
    if actual is not None:
        return actual
    result = _first_result(row)
    status = str(result.get("economics_status") or "").upper()
    complete = _as_bool(result.get("economics_cost_components_complete", False))
    if not complete or status not in {"MODELED_COMPLETE", "MODELED_COMPLETE_NO_SETTLEMENT"}:
        return None
    return _safe_float(result.get("modeled_net_r"))


def _profit_factor(values: List[float]) -> Optional[float]:
    gains = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    if losses <= 0:
        return 99.0 if gains > 0 else None
    return gains / losses


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    resolved: List[Dict[str, Any]] = []
    gross_values: List[float] = []
    complete_net_values: List[float] = []
    actual_net_values: List[float] = []
    mae_values: List[float] = []
    funding_observed = 0
    tp = sl = 0

    for row in rows or []:
        gross = _gross_r(row)
        if gross is None:
            continue
        resolved.append(row)
        gross_values.append(gross)
        result = _first_result(row)
        status = str(result.get("status") or row.get("status") or "").lower()
        tp += int(status == "tp_hit")
        sl += int(status == "sl_hit")

        net = _model_complete_net_r(row)
        if net is not None:
            complete_net_values.append(net)
        actual = _actual_net_r(row)
        if actual is not None:
            actual_net_values.append(actual)
        mae = _safe_float(result.get("mae_r"))
        if mae is not None and mae >= 0:
            mae_values.append(mae)
        funding_status = str(result.get("funding_calculation_status") or "").upper()
        if funding_status in {"OBSERVED_RATES", "NO_SETTLEMENTS_IN_WINDOW"}:
            funding_observed += 1

    resolved_n = len(resolved)
    complete_coverage = (len(complete_net_values) / resolved_n * 100.0) if resolved_n else 0.0
    actual_coverage = (len(actual_net_values) / resolved_n * 100.0) if resolved_n else 0.0
    funding_coverage = (funding_observed / resolved_n * 100.0) if resolved_n else 0.0

    complete_pf = _profit_factor(complete_net_values)
    actual_pf = _profit_factor(actual_net_values)
    gross_pf = _profit_factor(gross_values)
    complete_exp = (sum(complete_net_values) / len(complete_net_values)) if complete_net_values else None
    actual_exp = (sum(actual_net_values) / len(actual_net_values)) if actual_net_values else None

    return {
        "resolved": resolved_n,
        "tp": tp,
        "sl": sl,
        "win_rate_pct": round(tp / resolved_n * 100.0, 2) if resolved_n else None,
        "gross_expectancy_r": round(sum(gross_values) / len(gross_values), 4) if gross_values else None,
        "gross_profit_factor": round(gross_pf, 3) if gross_pf is not None else None,
        # Canonical Commit-9 economics.
        "model_complete_net_rows": len(complete_net_values),
        "model_complete_net_coverage_pct": round(complete_coverage, 2),
        "model_complete_net_expectancy_r": round(complete_exp, 4) if complete_exp is not None else None,
        "model_complete_net_profit_factor": round(complete_pf, 3) if complete_pf is not None else None,
        "funding_observed_rows": funding_observed,
        "funding_observed_coverage_pct": round(funding_coverage, 2),
        "avg_mae_r": round(sum(mae_values) / len(mae_values), 4) if mae_values else None,
        # Compatibility keys consumed by the Commit-8 frontend/tests. They now
        # mean MODEL-COMPLETE economics, not fee-only arithmetic.
        "modeled_net_rows": len(complete_net_values),
        "modeled_net_coverage_pct": round(complete_coverage, 2),
        "modeled_net_expectancy_r": round(complete_exp, 4) if complete_exp is not None else None,
        "modeled_net_profit_factor": round(complete_pf, 3) if complete_pf is not None else None,
        # Actual account fills remain informational and are never fabricated.
        "realized_net_rows": len(actual_net_values),
        "realized_net_coverage_pct": round(actual_coverage, 2),
        "realized_net_expectancy_r": round(actual_exp, 4) if actual_exp is not None else None,
        "realized_net_profit_factor": round(actual_pf, 3) if actual_pf is not None else None,
    }


def _consecutive_sl(rows: Iterable[Dict[str, Any]]) -> int:
    ordered = []
    for row in rows or []:
        gross = _gross_r(row)
        created = _parse_dt(row.get("created_at"))
        if gross is not None and created is not None:
            ordered.append((created, gross))
    ordered.sort(key=lambda item: item[0], reverse=True)
    count = 0
    for _, gross in ordered:
        if gross < 0:
            count += 1
        else:
            break
    return count


def evaluate_promotion_gate(
    rows: Iterable[Dict[str, Any]],
    *,
    coverage_complete: bool,
    coverage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure evidence gate used by tests and the persisted runtime refresh."""
    verified = [row for row in (rows or []) if _is_verified_official_futures(row)]
    verified.sort(key=lambda row: _parse_dt(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
    resolved = [row for row in verified if _gross_r(row) is not None]
    split = max(1, int(len(resolved) * 0.70)) if resolved else 0
    validation = resolved[split:]
    recent = resolved[-RECENT_WINDOW:]

    total_m = _metrics(resolved)
    validation_m = _metrics(validation)
    recent_m = _metrics(recent)
    consecutive_sl = _consecutive_sl(resolved)

    net_coverage_ok = total_m["model_complete_net_coverage_pct"] >= MIN_ECONOMICS_COMPLETE_COVERAGE_PCT
    net_expectancy_ok = (
        total_m["model_complete_net_expectancy_r"] is not None
        and total_m["model_complete_net_expectancy_r"] >= MIN_MODELED_NET_EXPECTANCY_R
    )
    validation_net_ok = (
        validation_m["model_complete_net_expectancy_r"] is not None
        and validation_m["model_complete_net_expectancy_r"] > 0.0
    )
    validation_pf_ok = (
        validation_m["model_complete_net_profit_factor"] is not None
        and validation_m["model_complete_net_profit_factor"] >= MIN_VALIDATION_PROFIT_FACTOR
    )

    quality_checks = {
        "coverage_complete": bool(coverage_complete),
        "sample_ok": total_m["resolved"] >= MIN_RESOLVED,
        "validation_sample_ok": validation_m["resolved"] >= MIN_VALIDATION_RESOLVED,
        "gross_expectancy_ok": total_m["gross_expectancy_r"] is not None and total_m["gross_expectancy_r"] >= MIN_GROSS_EXPECTANCY_R,
        "profit_factor_ok": total_m["gross_profit_factor"] is not None and total_m["gross_profit_factor"] >= MIN_PROFIT_FACTOR,
        "model_complete_net_coverage_ok": net_coverage_ok,
        "model_complete_net_expectancy_ok": net_expectancy_ok,
        "validation_net_expectancy_ok": validation_net_ok,
        "validation_profit_factor_ok": validation_pf_ok,
        "recent_health_ok": recent_m["gross_expectancy_r"] is not None and recent_m["gross_expectancy_r"] >= MIN_RECENT_EXPECTANCY_R,
        "failure_streak_ok": consecutive_sl <= MAX_CONSECUTIVE_SL_FOR_POSITIVE_AUTHORITY,
        # Legacy check names retained so existing diagnostics/tests do not break.
        # In Commit 9 these refer to cost-complete economics, whether supplied
        # by a future actual-fill integration or the conservative complete model.
        "realized_net_coverage_ok": net_coverage_ok,
        "realized_net_expectancy_ok": net_expectancy_ok,
        "validation_realized_net_expectancy_ok": validation_net_ok,
        "validation_realized_net_profit_factor_ok": validation_pf_ok,
    }
    quality_allowed = all(quality_checks.values())

    risk_checks = {
        "coverage_complete": bool(coverage_complete),
        "quality_gate_open": bool(quality_allowed),
        "risk_sample_ok": total_m["resolved"] >= MIN_RISK_GROWTH_RESOLVED,
        "risk_validation_sample_ok": validation_m["resolved"] >= MIN_RISK_GROWTH_VALIDATION,
        "risk_net_coverage_ok": net_coverage_ok,
        "risk_net_expectancy_ok": total_m["model_complete_net_expectancy_r"] is not None and total_m["model_complete_net_expectancy_r"] >= MIN_RISK_GROWTH_NET_EXPECTANCY_R,
        "risk_net_profit_factor_ok": total_m["model_complete_net_profit_factor"] is not None and total_m["model_complete_net_profit_factor"] >= MIN_RISK_GROWTH_NET_PROFIT_FACTOR,
        "risk_validation_expectancy_ok": validation_m["model_complete_net_expectancy_r"] is not None and validation_m["model_complete_net_expectancy_r"] >= MIN_RISK_GROWTH_VALIDATION_EXPECTANCY_R,
        "risk_validation_pf_ok": validation_m["model_complete_net_profit_factor"] is not None and validation_m["model_complete_net_profit_factor"] >= MIN_RISK_GROWTH_VALIDATION_PF,
        "risk_recent_health_ok": recent_m["model_complete_net_expectancy_r"] is not None and recent_m["model_complete_net_expectancy_r"] >= MIN_RISK_GROWTH_RECENT_EXPECTANCY_R,
        "risk_mae_ok": total_m["avg_mae_r"] is not None and total_m["avg_mae_r"] <= MAX_RISK_GROWTH_AVG_MAE_R,
        "risk_failure_streak_ok": consecutive_sl <= MAX_CONSECUTIVE_SL_FOR_RISK_GROWTH,
    }
    risk_growth_allowed = all(risk_checks.values())

    quality_block_reasons = [key for key, passed in quality_checks.items() if not passed]
    risk_block_reasons = [key for key, passed in risk_checks.items() if not passed]

    # Strategy ACTIVE remains veto-only. It may become available once the full
    # evidence window is demonstrably complete; strategy-specific promotion is
    # still much stricter in adaptive_autopilot.
    strategy_veto_allowed = bool(coverage_complete)

    return {
        "version": PROMOTION_GOVERNANCE_VERSION,
        "scope": GOVERNANCE_SCOPE,
        "quality_optimization_allowed": bool(quality_allowed),
        "strategy_veto_authority_allowed": strategy_veto_allowed,
        "risk_growth_allowed": bool(risk_growth_allowed),
        "risk_growth_reason": (
            "NET_EDGE_RISK_GATE_OPEN" if risk_growth_allowed
            else "NET_EDGE_RISK_GATE_BLOCKED"
        ),
        "checks": quality_checks,
        "risk_checks": risk_checks,
        "block_reasons": quality_block_reasons,
        "risk_block_reasons": risk_block_reasons,
        "coverage": dict(coverage or {}),
        "evidence": {
            "total": total_m,
            "validation_30": validation_m,
            "recent": recent_m,
            "consecutive_sl": consecutive_sl,
            "economics_requirement": "MODEL_COMPLETE_FEE_SLIPPAGE_PLUS_PUBLIC_FUNDING",
            "economics_complete_coverage_required_pct": MIN_ECONOMICS_COMPLETE_COVERAGE_PCT,
            "actual_account_costs_available": total_m["realized_net_coverage_pct"] > 0.0,
            "actual_account_cost_coverage_pct": total_m["realized_net_coverage_pct"],
            "realized_cost_claim": total_m["realized_net_coverage_pct"] >= 95.0,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_window(db, *, days_back: int = 90) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from q6_integrity import read_pages
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(7, min(int(days_back), 180)))

    def coverage_query():
        return (
            db.client.table("signals")
            .select("id")
            .gte("created_at", cutoff.isoformat())
            .lt("created_at", now.isoformat())
            .eq("context->execution->>quality_score_version", QUALITY_SCORE_VERSION)
            .in_("action_normalized", ["LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"])
            .order("created_at", desc=False)
            .order("id", desc=False)
        )

    coverage_rows = read_pages(coverage_query, page_size=500, max_rows=10000, budget_seconds=30)
    coverage = dict(getattr(coverage_rows, "coverage", {}) or {})

    def official_query():
        return (
            db.client.table("signals")
            .select(
                "id,symbol,timeframe,system_type,action_normalized,status,created_at,"
                "entry_price,stop_loss,take_profit,risk_reward,"
                "q6_learning:context->learning,signal_results(*)"
            )
            .gte("created_at", cutoff.isoformat())
            .lt("created_at", now.isoformat())
            .eq("system_type", "futures")
            .eq("context->execution->>quality_score_version", QUALITY_SCORE_VERSION)
            .in_("action_normalized", ["LONG", "SHORT"])
            .in_("status", ["tp_hit", "sl_hit", "expired"])
            .order("created_at", desc=False)
            .order("id", desc=False)
        )

    rows = read_pages(official_query, page_size=250, max_rows=2500, budget_seconds=20)
    return list(rows or []), coverage


def refresh_promotion_governance(db, *, days_back: int = 90) -> Dict[str, Any]:
    """Recompute and persist the singleton governance state. Fails closed."""
    if db is None or not getattr(db, "enabled", False):
        return fail_closed_status("SUPABASE_DISABLED")
    try:
        rows, coverage = _read_window(db, days_back=days_back)
        status = evaluate_promotion_gate(rows, coverage_complete=bool(coverage.get("complete", False)), coverage=coverage)
        payload = {
            "scope": GOVERNANCE_SCOPE,
            "quality_optimization_allowed": status["quality_optimization_allowed"],
            "strategy_veto_authority_allowed": status["strategy_veto_authority_allowed"],
            "risk_growth_allowed": status["risk_growth_allowed"],
            "evidence": status,
            "version": PROMOTION_GOVERNANCE_VERSION,
            "updated_at": status["updated_at"],
        }
        try:
            previous_rows = (
                db.client.table("autopilot_governance_state")
                .select("quality_optimization_allowed,strategy_veto_authority_allowed,risk_growth_allowed")
                .eq("scope", GOVERNANCE_SCOPE).limit(1).execute().data or []
            )
        except Exception:
            previous_rows = []
        previous = previous_rows[0] if previous_rows else {}
        db.client.table("autopilot_governance_state").upsert(payload, on_conflict="scope").execute()

        changed = bool(
            not previous_rows
            or bool(previous.get("quality_optimization_allowed", False)) != status["quality_optimization_allowed"]
            or bool(previous.get("strategy_veto_authority_allowed", False)) != status["strategy_veto_authority_allowed"]
            or bool(previous.get("risk_growth_allowed", False)) != status["risk_growth_allowed"]
        )
        if changed:
            try:
                db.client.table("adaptive_autopilot_events").insert({
                    "event_type": "PROMOTION_GOVERNANCE",
                    "component": GOVERNANCE_SCOPE,
                    "old_state": (
                        f"QUALITY={bool(previous.get('quality_optimization_allowed', False))};"
                        f"VETO={bool(previous.get('strategy_veto_authority_allowed', False))};"
                        f"RISK={bool(previous.get('risk_growth_allowed', False))}"
                    ) if previous_rows else "NONE",
                    "new_state": (
                        f"QUALITY={status['quality_optimization_allowed']};"
                        f"VETO={status['strategy_veto_authority_allowed']};"
                        f"RISK={status['risk_growth_allowed']}"
                    ),
                    "reason": ",".join((status.get("block_reasons") or []) + (status.get("risk_block_reasons") or []))[:500] or "EVIDENCE_GATES_OPEN",
                    "evidence": status,
                    "version": PROMOTION_GOVERNANCE_VERSION,
                }).execute()
            except Exception:
                pass
        invalidate_governance_cache()
        return status
    except Exception as exc:
        return fail_closed_status(f"REFRESH_FAILED:{type(exc).__name__}", error=str(exc)[:180])


def fail_closed_status(reason: str, *, error: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "version": PROMOTION_GOVERNANCE_VERSION,
        "scope": GOVERNANCE_SCOPE,
        "quality_optimization_allowed": False,
        "strategy_veto_authority_allowed": False,
        "risk_growth_allowed": False,
        "risk_growth_reason": "FAIL_CLOSED",
        "checks": {},
        "risk_checks": {},
        "block_reasons": [reason],
        "risk_block_reasons": [reason],
        "coverage": {"complete": False},
        "evidence": {},
        "updated_at": None,
    }
    if error:
        result["error"] = error
    return result


def invalidate_governance_cache() -> None:
    global _status_cache
    with _cache_lock:
        _status_cache = None


def get_promotion_governance_status(db=None) -> Dict[str, Any]:
    """Cheap runtime read. It never performs the heavy 90-day refresh."""
    global _status_cache
    now = time.monotonic()
    with _cache_lock:
        if _status_cache and now - _status_cache[0] < _status_cache_ttl:
            return json.loads(json.dumps(_status_cache[1]))

    if db is None:
        try:
            from supabase_client import supabase_db as db
        except Exception:
            db = None
    if db is None or not getattr(db, "enabled", False):
        return fail_closed_status("SUPABASE_DISABLED")

    try:
        response = (
            db.client.table("autopilot_governance_state")
            .select("scope,quality_optimization_allowed,strategy_veto_authority_allowed,risk_growth_allowed,evidence,version,updated_at")
            .eq("scope", GOVERNANCE_SCOPE).limit(1).execute()
        )
        rows = response.data or []
        if not rows:
            result = fail_closed_status("WAITING_FIRST_GOVERNANCE_REFRESH")
        else:
            row = rows[0]
            evidence = _as_dict(row.get("evidence"))
            result = evidence or fail_closed_status("EMPTY_GOVERNANCE_EVIDENCE")
            result["quality_optimization_allowed"] = bool(row.get("quality_optimization_allowed", False))
            result["strategy_veto_authority_allowed"] = bool(row.get("strategy_veto_authority_allowed", False))
            result["risk_growth_allowed"] = bool(row.get("risk_growth_allowed", False))
            result["version"] = str(row.get("version") or PROMOTION_GOVERNANCE_VERSION)
            result["updated_at"] = row.get("updated_at")

            updated = _parse_dt(row.get("updated_at"))
            if updated is None or datetime.now(timezone.utc) - updated > timedelta(hours=GOVERNANCE_STALE_HOURS):
                stale = dict(result)
                stale["quality_optimization_allowed"] = False
                stale["strategy_veto_authority_allowed"] = False
                stale["risk_growth_allowed"] = False
                stale["block_reasons"] = list(stale.get("block_reasons") or []) + ["STALE_GOVERNANCE_STATE"]
                stale["risk_block_reasons"] = list(stale.get("risk_block_reasons") or []) + ["STALE_GOVERNANCE_STATE"]
                stale["stale"] = True
                result = stale
    except Exception as exc:
        result = fail_closed_status(f"READ_FAILED:{type(exc).__name__}", error=str(exc)[:180])

    with _cache_lock:
        _status_cache = (now, result)
    return json.loads(json.dumps(result))
