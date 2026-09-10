"""Commit 8 — governed promotion authority.

This module decides whether positive learning is allowed to influence production.
It is intentionally separate from the trading engine and from Gemini.

Authorities are split:
- quality_optimization_allowed: may select among already-valid Entry/SL/TP/Q2
  configurations. It never lowers Safety and never creates a direction.
- strategy_veto_authority_allowed: an ACTIVE experimental strategy may only veto
  a conflicting production direction. It cannot create or boost a trade.
- risk_growth_allowed: kept FALSE in Commit 8. Commit 9 owns leverage scaling.

The gate fails closed when evidence/coverage cannot be verified.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
import json
import math
import threading
import time

PROMOTION_GOVERNANCE_VERSION = "C8_PROMOTION_GOVERNANCE_V1"
QUALITY_SCORE_VERSION = "36W_V2_NORMALIZED"
GOVERNANCE_SCOPE = "FUTURES_GLOBAL"

MIN_RESOLVED = 25
MIN_VALIDATION_RESOLVED = 10
MIN_GROSS_EXPECTANCY_R = 0.10
MIN_MODELED_NET_EXPECTANCY_R = 0.05
MIN_PROFIT_FACTOR = 1.15
MIN_VALIDATION_PROFIT_FACTOR = 1.05
MAX_CONSECUTIVE_SL_FOR_POSITIVE_AUTHORITY = 5
RECENT_WINDOW = 10
MIN_RECENT_EXPECTANCY_R = -0.10
GOVERNANCE_STALE_HOURS = 8

# Same configured round-trip assumption currently used by Futures (0.0012 =
# 0.12%). This is explicitly MODELED, not a realized fee claim.
MODELED_ROUND_TRIP_COST_PCT = 0.12

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


def _realized_net_r(row: Dict[str, Any]) -> Optional[float]:
    """Return realized net R only when the lifecycle actually persisted it.

    We deliberately do not manufacture commissions/funding/slippage here.
    If net_pnl_pct is absent, positive quality authority stays blocked.
    """
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


def _modeled_cost_r(row: Dict[str, Any]) -> Optional[float]:
    entry = _safe_float(row.get("entry_price") or row.get("entry"))
    sl = _safe_float(row.get("stop_loss"))
    if entry is None or sl is None or entry <= 0:
        return None
    risk_pct = abs(entry - sl) / entry * 100.0
    if risk_pct <= 0:
        return None
    return MODELED_ROUND_TRIP_COST_PCT / risk_pct


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    resolved: List[Dict[str, Any]] = []
    gross_values: List[float] = []
    modeled_net_values: List[float] = []
    realized_net_values: List[float] = []
    tp = sl = 0
    for row in rows or []:
        gross = _gross_r(row)
        if gross is None:
            continue
        resolved.append(row)
        gross_values.append(gross)
        status = str(_first_result(row).get("status") or row.get("status") or "").lower()
        tp += int(status == "tp_hit")
        sl += int(status == "sl_hit")
        cost_r = _modeled_cost_r(row)
        if cost_r is not None:
            modeled_net_values.append(gross - cost_r)
        realized_net = _realized_net_r(row)
        if realized_net is not None:
            realized_net_values.append(realized_net)

    def pf(values: List[float]) -> Optional[float]:
        gains = sum(v for v in values if v > 0)
        losses = abs(sum(v for v in values if v < 0))
        if losses <= 0:
            return 99.0 if gains > 0 else None
        return gains / losses

    return {
        "resolved": len(resolved),
        "tp": tp,
        "sl": sl,
        "win_rate_pct": round(tp / len(resolved) * 100.0, 2) if resolved else None,
        "gross_expectancy_r": round(sum(gross_values) / len(gross_values), 4) if gross_values else None,
        "gross_profit_factor": round(pf(gross_values), 3) if pf(gross_values) is not None else None,
        "modeled_net_rows": len(modeled_net_values),
        "modeled_net_coverage_pct": round(len(modeled_net_values) / len(resolved) * 100.0, 2) if resolved else 0.0,
        "modeled_net_expectancy_r": round(sum(modeled_net_values) / len(modeled_net_values), 4) if modeled_net_values else None,
        "modeled_net_profit_factor": round(pf(modeled_net_values), 3) if pf(modeled_net_values) is not None else None,
        "realized_net_rows": len(realized_net_values),
        "realized_net_coverage_pct": round(len(realized_net_values) / len(resolved) * 100.0, 2) if resolved else 0.0,
        "realized_net_expectancy_r": round(sum(realized_net_values) / len(realized_net_values), 4) if realized_net_values else None,
        "realized_net_profit_factor": round(pf(realized_net_values), 3) if pf(realized_net_values) is not None else None,
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
    """Pure gate used by tests and the persisted runtime refresh."""
    verified = [row for row in (rows or []) if _is_verified_official_futures(row)]
    verified.sort(key=lambda row: _parse_dt(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
    resolved = [row for row in verified if _gross_r(row) is not None]
    split = max(1, int(len(resolved) * 0.70)) if resolved else 0
    calibration = resolved[:split]
    validation = resolved[split:]
    recent = resolved[-RECENT_WINDOW:]

    total_m = _metrics(resolved)
    validation_m = _metrics(validation)
    recent_m = _metrics(recent)
    consecutive_sl = _consecutive_sl(resolved)

    checks = {
        "coverage_complete": bool(coverage_complete),
        "sample_ok": total_m["resolved"] >= MIN_RESOLVED,
        "validation_sample_ok": validation_m["resolved"] >= MIN_VALIDATION_RESOLVED,
        "gross_expectancy_ok": total_m["gross_expectancy_r"] is not None and total_m["gross_expectancy_r"] >= MIN_GROSS_EXPECTANCY_R,
        "profit_factor_ok": total_m["gross_profit_factor"] is not None and total_m["gross_profit_factor"] >= MIN_PROFIT_FACTOR,
        "modeled_net_coverage_ok": total_m["modeled_net_coverage_pct"] >= 95.0,
        "modeled_net_expectancy_ok": total_m["modeled_net_expectancy_r"] is not None and total_m["modeled_net_expectancy_r"] >= MIN_MODELED_NET_EXPECTANCY_R,
        "validation_net_expectancy_ok": validation_m["modeled_net_expectancy_r"] is not None and validation_m["modeled_net_expectancy_r"] > 0.0,
        "validation_profit_factor_ok": validation_m["modeled_net_profit_factor"] is not None and validation_m["modeled_net_profit_factor"] >= MIN_VALIDATION_PROFIT_FACTOR,
        "realized_net_coverage_ok": total_m["realized_net_coverage_pct"] >= 95.0,
        "realized_net_expectancy_ok": total_m["realized_net_expectancy_r"] is not None and total_m["realized_net_expectancy_r"] >= MIN_MODELED_NET_EXPECTANCY_R,
        "validation_realized_net_expectancy_ok": validation_m["realized_net_expectancy_r"] is not None and validation_m["realized_net_expectancy_r"] > 0.0,
        "validation_realized_net_profit_factor_ok": validation_m["realized_net_profit_factor"] is not None and validation_m["realized_net_profit_factor"] >= MIN_VALIDATION_PROFIT_FACTOR,
        "recent_health_ok": recent_m["gross_expectancy_r"] is not None and recent_m["gross_expectancy_r"] >= MIN_RECENT_EXPECTANCY_R,
        "failure_streak_ok": consecutive_sl <= MAX_CONSECUTIVE_SL_FOR_POSITIVE_AUTHORITY,
    }
    quality_allowed = all(checks.values())

    block_reasons = [key for key, passed in checks.items() if not passed]
    # Strategy ACTIVE is veto-only in Commit 8, so it can be allowed once the
    # data window itself is demonstrably complete. Strategy-specific gates in
    # adaptive_autopilot remain much stricter (research + live evidence).
    # Veto authority is deliberately protective-only. It may become available
    # before the current official engine is profitable, but only when the full
    # governance window is demonstrably complete. Strategy-specific promotion
    # still requires independent research + live-shadow evidence in Autopilot.
    strategy_veto_allowed = bool(coverage_complete)

    return {
        "version": PROMOTION_GOVERNANCE_VERSION,
        "scope": GOVERNANCE_SCOPE,
        "quality_optimization_allowed": bool(quality_allowed),
        "strategy_veto_authority_allowed": strategy_veto_allowed,
        # Commit 9 explicitly owns risk/leverage expansion.
        "risk_growth_allowed": False,
        "risk_growth_reason": "RESERVED_FOR_COMMIT9_NET_EDGE_SCALING",
        "checks": checks,
        "block_reasons": block_reasons,
        "coverage": dict(coverage or {}),
        "evidence": {
            "total": total_m,
            "validation_30": validation_m,
            "recent": recent_m,
            "consecutive_sl": consecutive_sl,
            "modeled_round_trip_cost_pct": MODELED_ROUND_TRIP_COST_PCT,
            "cost_quality": (
                "REALIZED_NET_AVAILABLE"
                if total_m["realized_net_coverage_pct"] >= 95.0
                else "MODELED_ONLY_REALIZED_NET_INCOMPLETE"
            ),
            "realized_cost_claim": bool(total_m["realized_net_coverage_pct"] >= 95.0),
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

    # ID-only probe: much cheaper than reading the complete analytics payload.
    coverage_rows = read_pages(
        coverage_query,
        page_size=500,
        max_rows=10000,
        budget_seconds=30,
    )
    coverage = dict(getattr(coverage_rows, "coverage", {}) or {})

    def official_query():
        return (
            db.client.table("signals")
            .select(
                "id,symbol,timeframe,system_type,action_normalized,status,created_at,"
                "entry_price,stop_loss,take_profit,risk_reward,"
                "q6_learning:context->learning,"
                "signal_results(*)"
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

    rows = read_pages(
        official_query,
        page_size=250,
        max_rows=2500,
        budget_seconds=20,
    )
    return list(rows or []), coverage


def refresh_promotion_governance(db, *, days_back: int = 90) -> Dict[str, Any]:
    """Recomputes and persists the singleton governance state. Fails closed."""
    if db is None or not getattr(db, "enabled", False):
        return fail_closed_status("SUPABASE_DISABLED")
    try:
        rows, coverage = _read_window(db, days_back=days_back)
        status = evaluate_promotion_gate(
            rows,
            coverage_complete=bool(coverage.get("complete", False)),
            coverage=coverage,
        )
        payload = {
            "scope": GOVERNANCE_SCOPE,
            "quality_optimization_allowed": status["quality_optimization_allowed"],
            "strategy_veto_authority_allowed": status["strategy_veto_authority_allowed"],
            "risk_growth_allowed": False,
            "evidence": status,
            "version": PROMOTION_GOVERNANCE_VERSION,
            "updated_at": status["updated_at"],
        }
        try:
            previous_rows = (
                db.client.table("autopilot_governance_state")
                .select("quality_optimization_allowed,strategy_veto_authority_allowed,risk_growth_allowed")
                .eq("scope", GOVERNANCE_SCOPE)
                .limit(1)
                .execute().data or []
            )
        except Exception:
            previous_rows = []
        previous = previous_rows[0] if previous_rows else {}

        db.client.table("autopilot_governance_state").upsert(payload, on_conflict="scope").execute()

        changed = bool(
            not previous_rows
            or bool(previous.get("quality_optimization_allowed", False)) != status["quality_optimization_allowed"]
            or bool(previous.get("strategy_veto_authority_allowed", False)) != status["strategy_veto_authority_allowed"]
            or bool(previous.get("risk_growth_allowed", False)) is not False
        )
        if changed:
            try:
                db.client.table("adaptive_autopilot_events").insert({
                    "event_type": "PROMOTION_GOVERNANCE",
                    "component": GOVERNANCE_SCOPE,
                    "old_state": (
                        f"QUALITY={bool(previous.get('quality_optimization_allowed', False))};"
                        f"VETO={bool(previous.get('strategy_veto_authority_allowed', False))}"
                    ) if previous_rows else "NONE",
                    "new_state": (
                        f"QUALITY={status['quality_optimization_allowed']};"
                        f"VETO={status['strategy_veto_authority_allowed']}"
                    ),
                    "reason": ",".join(status.get("block_reasons") or ["EVIDENCE_GATE_OPEN"])[:500],
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
        "risk_growth_reason": "RESERVED_FOR_COMMIT9_NET_EDGE_SCALING",
        "checks": {},
        "block_reasons": [reason],
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
            .eq("scope", GOVERNANCE_SCOPE)
            .limit(1)
            .execute()
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
            # Commit 8 never trusts a persisted true here. Risk growth belongs to Commit 9.
            result["risk_growth_allowed"] = False
            result["version"] = str(row.get("version") or PROMOTION_GOVERNANCE_VERSION)
            result["updated_at"] = row.get("updated_at")

            # A previously-open gate must never remain authoritative forever if
            # the ReviewTrader scheduler stops refreshing it. Fail closed when
            # the singleton is stale for more than two normal 4h cycles.
            updated = _parse_dt(row.get("updated_at"))
            if updated is None or datetime.now(timezone.utc) - updated > timedelta(hours=GOVERNANCE_STALE_HOURS):
                stale = dict(result)
                stale["quality_optimization_allowed"] = False
                stale["strategy_veto_authority_allowed"] = False
                stale["risk_growth_allowed"] = False
                stale["block_reasons"] = list(stale.get("block_reasons") or []) + ["STALE_GOVERNANCE_STATE"]
                stale["stale"] = True
                result = stale
    except Exception as exc:
        result = fail_closed_status(f"READ_FAILED:{type(exc).__name__}", error=str(exc)[:180])

    with _cache_lock:
        _status_cache = (now, result)
    return json.loads(json.dumps(result))
