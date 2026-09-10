"""Commit 10 — shared learning/cohort integrity helpers.

This module has ZERO trading authority.  It centralizes the data-contract
questions that Analytics, the learning PDF, governance and the trader
scorecard must answer consistently:

- is this Spot row a verified closed-candle learning observation?
- is this Futures row a verified executable observation?
- is this Futures row a clean Shadow observation?
- what is the latest persisted outcome?
- what exact row set (fingerprint) is a component looking at?

Different products may intentionally use different scopes (for example the
"current quality engine" dashboard versus the broader 90-day learning PDF).
The goal is not to force all scopes to have the same N; it is to make the
scope explicit and make equal scopes comparable instead of silently mixing
contracts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Optional
import json
import math

SPOT_SOURCE = "KUCOIN_SPOT_REST"
SPOT_COHORT = "SPOT_REAL_CLOSED_Q6"
SPOT_VERSION = "spot_closed_q6_v1"
FUTURES_SOURCE = "KUCOIN_FUTURES_PERPETUAL_REST"
FUTURES_COHORT = "FUTURES_PERPETUAL_REAL_CLOSED_V1"
LEARNING_CONTRACT_VERSION = "market_separated_v1"

FINAL_STATUSES = {"tp_hit", "sl_hit", "expired", "ambiguous", "invalid_setup"}
RESOLVED_STATUSES = {"tp_hit", "sl_hit"}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
    return bool(value)


def as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def learning_context(row: Dict[str, Any]) -> Dict[str, Any]:
    """Read learning JSON from normal rows or PostgREST aliases."""
    direct = row.get("q6_learning")
    if isinstance(direct, dict):
        return direct
    context = as_dict(row.get("context"))
    learning = context.get("learning") or {}
    return learning if isinstance(learning, dict) else {}


def execution_context(row: Dict[str, Any]) -> Dict[str, Any]:
    direct = row.get("q6_execution")
    if isinstance(direct, dict):
        return direct
    context = as_dict(row.get("context"))
    execution = context.get("execution") or {}
    return execution if isinstance(execution, dict) else {}


def normalize_market(row: Dict[str, Any]) -> str:
    return str(row.get("system_type") or row.get("market") or "").strip().lower()


def normalize_action(value: Any) -> str:
    action = str(value or "").strip().upper()
    if action in {"COMPRA_SPOT", "BUY", "COMPRAR"}:
        return "LONG"
    if action in {"VENTA_SPOT", "SELL", "VENDER"}:
        return "SHORT"
    return action if action in {"LONG", "SHORT"} else "NO_OPERAR"


def is_verified_spot(row: Dict[str, Any]) -> bool:
    learning = learning_context(row)
    return bool(
        normalize_market(row) == "spot"
        and learning.get("cohort") == SPOT_COHORT
        and str(learning.get("market_data_source") or "").upper() == SPOT_SOURCE
        and not as_bool(learning.get("market_data_is_synthetic", True))
        and as_bool(learning.get("source_candle_closed", False))
        and learning.get("analysis_version") == SPOT_VERSION
        and bool(learning.get("source_candle_timestamp"))
        and bool(learning.get("source_candle_close_timestamp"))
        and as_bool(learning.get("statistically_eligible", False))
    )


def is_clean_futures(row: Dict[str, Any]) -> bool:
    learning = learning_context(row)
    # The contract_version requirement matches the learning-PDF contract.
    # It deliberately avoids silently admitting pre-contract rows into a
    # current verified cohort.
    return bool(
        normalize_market(row) == "futures"
        and learning.get("contract_version") == LEARNING_CONTRACT_VERSION
        and learning.get("cohort") == FUTURES_COHORT
        and str(learning.get("market_data_source") or "").upper() == FUTURES_SOURCE
        and not as_bool(learning.get("market_data_is_synthetic", True))
        and as_bool(learning.get("source_candle_closed", False))
    )


def is_verified_official_futures(row: Dict[str, Any]) -> bool:
    learning = learning_context(row)
    return bool(
        is_clean_futures(row)
        and as_bool(learning.get("statistically_eligible", False))
        and str(learning.get("evaluation_role") or "").upper() == "EXECUTABLE_SIGNAL"
    )


def is_clean_futures_shadow(row: Dict[str, Any]) -> bool:
    learning = learning_context(row)
    return bool(
        is_clean_futures(row)
        and str(learning.get("evaluation_role") or "").upper() == "SHADOW_ANALYSIS"
    )


def latest_result(row: Dict[str, Any]) -> Dict[str, Any]:
    results = row.get("signal_results") or row.get("result") or {}
    if isinstance(results, dict):
        return results
    if not isinstance(results, list) or not results:
        return {}
    candidates = [item for item in results if isinstance(item, dict)]
    if not candidates:
        return {}
    return max(candidates, key=lambda item: str(item.get("created_at") or item.get("exit_timestamp") or ""))


def canonical_status(row: Dict[str, Any]) -> str:
    result = latest_result(row)
    status = str(result.get("status") or row.get("status") or "").strip().lower()
    return status


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def realized_r(row: Dict[str, Any]) -> Optional[float]:
    status = canonical_status(row)
    if status == "sl_hit":
        return -1.0
    if status != "tp_hit":
        return None
    result = latest_result(row)
    stored = safe_float(result.get("gross_r"))
    if stored is not None:
        return stored
    rr = safe_float(row.get("risk_reward"))
    if rr is not None and rr > 0:
        return rr
    entry = safe_float(row.get("entry_price") or row.get("entry"))
    stop = safe_float(row.get("stop_loss"))
    target = safe_float(row.get("take_profit"))
    if entry and stop and target:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk > 0:
            return reward / risk
    return None


def cohort_fingerprint(rows: Iterable[Dict[str, Any]], *, scope: str = "") -> str:
    """Stable diagnostic fingerprint; not a security hash or trade ID."""
    normalized: List[Dict[str, Any]] = []
    for row in rows or []:
        normalized.append(
            {
                "id": str(row.get("id") or row.get("signal_id") or ""),
                "market": normalize_market(row),
                "action": normalize_action(row.get("action_normalized") or row.get("action")),
                "timeframe": str(row.get("timeframe") or ""),
                "created_at": str(row.get("created_at") or ""),
                "status": canonical_status(row),
            }
        )
    normalized.sort(key=lambda item: (item["created_at"], item["id"], item["status"]))
    payload = json.dumps({"scope": scope, "rows": normalized}, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()[:24]


def summarize_scope(rows: Iterable[Dict[str, Any]], *, scope: str) -> Dict[str, Any]:
    rows = list(rows or [])
    statuses: Dict[str, int] = {}
    for row in rows:
        status = canonical_status(row) or "unknown"
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "scope": scope,
        "n": len(rows),
        "resolved": sum(statuses.get(s, 0) for s in RESOLVED_STATUSES),
        "tp": statuses.get("tp_hit", 0),
        "sl": statuses.get("sl_hit", 0),
        "expired": statuses.get("expired", 0),
        "fingerprint": cohort_fingerprint(rows, scope=scope),
        "statuses": statuses,
    }


def build_integrity_manifest(
    *,
    spot_rows: Iterable[Dict[str, Any]],
    futures_official_rows: Iterable[Dict[str, Any]],
    futures_shadow_rows: Iterable[Dict[str, Any]],
    quality_score_version: str,
    coverage: Optional[Dict[str, Any]] = None,
    governance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Describe scope explicitly and compare equal-scope governance snapshots."""
    spot = summarize_scope(spot_rows, scope="CURRENT_QUALITY_SPOT")
    futures = summarize_scope(futures_official_rows, scope="CURRENT_QUALITY_FUTURES_OFFICIAL")
    shadow = summarize_scope(futures_shadow_rows, scope="CURRENT_QUALITY_FUTURES_SHADOW")
    governance = governance or {}
    gov_evidence = governance.get("evidence") or {}
    gov_fp = str(gov_evidence.get("cohort_fingerprint") or "")
    gov_n = gov_evidence.get("cohort_n")

    if not gov_fp:
        governance_match = None
        governance_state = "WAITING_REFRESH"
    else:
        governance_match = bool(gov_fp == futures["fingerprint"])
        governance_state = "MATCH" if governance_match else "STALE_OR_DIFFERENT_SNAPSHOT"

    return {
        "version": "C10_LEARNING_INTEGRITY_V1",
        "authority": "DIAGNOSTIC_ONLY",
        "quality_score_version": str(quality_score_version or ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": dict(coverage or {}),
        "scopes": {
            "spot_current": spot,
            "futures_official_current": futures,
            "futures_shadow_current": shadow,
        },
        "governance_comparison": {
            "state": governance_state,
            "same_scope_match": governance_match,
            "analytics_fingerprint": futures["fingerprint"],
            "governance_fingerprint": gov_fp or None,
            "analytics_n": futures["n"],
            "governance_n": gov_n,
        },
        "note": (
            "El PDF de aprendizaje puede tener un N distinto porque estudia una cohorte Q6 de 90 días más amplia. "
            "Sólo se exige igualdad entre componentes que declaran el mismo scope."
        ),
    }
