"""Commit 9 — net-edge economics for ReviewTrader outcomes.

The system does not execute exchange orders, therefore this module never calls
modeled costs "realized".  It combines:

* market outcome observed by ReviewTrader;
* the configured conservative round-trip fee+slippage model; and
* public KuCoin funding rates observed inside the Entry→Exit window.

This produces a MODEL-COMPLETE net R suitable for research/governance, while
keeping actual account costs explicitly unavailable unless a future exchange
integration supplies them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json
import math
import os


ECONOMICS_VERSION = "C9_NET_EDGE_ECONOMICS_V1"
DEFAULT_ROUND_TRIP_COST_RATE = 0.0012  # 0.12% of notional, entry+exit combined
FUNDING_HISTORY_URL = "https://api.kucoin.com/api/ua/v1/market/funding-rate-history"
CONTRACT_SYMBOLS = {
    "BTC-USDT": "XBTUSDTM",
    "ETH-USDT": "ETHUSDTM",
    "SOL-USDT": "SOLUSDTM",
    "XRP-USDT": "XRPUSDTM",
    "ADA-USDT": "ADAUSDTM",
}
COMPLETE_STATUSES = {"MODELED_COMPLETE", "MODELED_COMPLETE_NO_SETTLEMENT"}


def configured_round_trip_cost_rate() -> float:
    raw = os.environ.get("FUTURES_ROUND_TRIP_COST_RATE", "")
    try:
        value = float(raw) if raw else DEFAULT_ROUND_TRIP_COST_RATE
    except (TypeError, ValueError):
        value = DEFAULT_ROUND_TRIP_COST_RATE
    if not math.isfinite(value) or value < 0 or value > 0.02:
        value = DEFAULT_ROUND_TRIP_COST_RATE
    return float(value)


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


def _iso_to_ms(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def _entry_timestamp(result: Dict[str, Any]) -> Optional[str]:
    value = result.get("entry_timestamp")
    if value:
        return str(value)
    forensic = _as_dict(result.get("execution_forensics"))
    value = forensic.get("entry_timestamp")
    return str(value) if value else None


def _risk_pct(signal: Dict[str, Any]) -> Optional[float]:
    entry = _safe_float(signal.get("entry_price") or signal.get("entry"))
    sl = _safe_float(signal.get("stop_loss"))
    if entry is None or sl is None or entry <= 0:
        return None
    risk = abs(entry - sl) / entry * 100.0
    return risk if risk > 0 else None


def build_provisional_economics(
    signal: Dict[str, Any],
    result: Dict[str, Any],
    *,
    round_trip_cost_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """Build fee/slippage net economics immediately when TP/SL is resolved."""
    if str(signal.get("system_type") or "").lower() != "futures":
        return {}
    action = str(signal.get("action_normalized") or signal.get("action") or "").upper()
    status = str(result.get("status") or "").lower()
    if action not in {"LONG", "SHORT"} or status not in {"tp_hit", "sl_hit"}:
        return {}

    risk_pct = _risk_pct(signal)
    gross_price_pct = _safe_float(result.get("pnl_pct"))
    leverage = max(1.0, _safe_float(signal.get("leverage"), 1.0) or 1.0)
    if risk_pct is None or gross_price_pct is None:
        return {
            "economics_model_version": ECONOMICS_VERSION,
            "economics_status": "INVALID_GEOMETRY",
            "economics_cost_components_complete": False,
            "economics_updated_at": datetime.now(timezone.utc).isoformat(),
        }

    rate = configured_round_trip_cost_rate() if round_trip_cost_rate is None else float(round_trip_cost_rate)
    rate = max(0.0, min(0.02, rate))
    gross_r = gross_price_pct / risk_pct
    fee_slippage_cost_r = (rate * 100.0) / risk_pct
    provisional_net_r = gross_r - fee_slippage_cost_r
    entry_ts = _entry_timestamp(result)
    exit_ts = result.get("exit_timestamp")
    funding_pending = bool(entry_ts and exit_ts and _iso_to_ms(exit_ts) and _iso_to_ms(entry_ts))

    return {
        "entry_timestamp": entry_ts,
        "economics_model_version": ECONOMICS_VERSION,
        "economics_status": "FUNDING_PENDING" if funding_pending else "FUNDING_WINDOW_UNAVAILABLE",
        "economics_cost_model_source": "MODELED_FEE_SLIPPAGE_PLUS_PUBLIC_FUNDING",
        "economics_round_trip_cost_rate": round(rate, 8),
        "economics_cost_components_complete": False,
        "gross_r": round(gross_r, 6),
        "gross_pnl_pct_margin": round(gross_price_pct * leverage, 6),
        "modeled_fee_slippage_cost_r": round(fee_slippage_cost_r, 6),
        "funding_data_source": "KUCOIN_PUBLIC_FUNDING_HISTORY",
        "funding_calculation_status": "PENDING" if funding_pending else "NO_ENTRY_EXIT_WINDOW",
        "funding_contract_symbol": CONTRACT_SYMBOLS.get(str(signal.get("symbol") or "").upper()),
        "funding_settlements_count": None,
        "funding_rate_sum": None,
        "modeled_funding_cost_r": None,
        "modeled_total_cost_r": round(fee_slippage_cost_r, 6),
        "modeled_net_r": round(provisional_net_r, 6),
        "modeled_net_pnl_pct_margin": round(
            gross_price_pct * leverage - rate * 100.0 * leverage,
            6,
        ),
        "economics_quality": "PROVISIONAL_FEE_SLIPPAGE_ONLY",
        "economics_updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_public_funding(signal: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch public funding rates inside the actual observed Entry→Exit window."""
    symbol = str(signal.get("symbol") or "").upper()
    action = str(signal.get("action_normalized") or signal.get("action") or "").upper()
    contract = CONTRACT_SYMBOLS.get(symbol)
    start_value = result.get("entry_timestamp") or _entry_timestamp(result)
    end_value = result.get("exit_timestamp")
    start_ms = _iso_to_ms(start_value)
    end_ms = _iso_to_ms(end_value)
    base = {
        "funding_data_source": "KUCOIN_PUBLIC_FUNDING_HISTORY",
        "funding_contract_symbol": contract,
        "funding_calculation_status": "UNAVAILABLE",
        "funding_settlements_count": None,
        "funding_rate_sum": None,
        "funding_observed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not contract or action not in {"LONG", "SHORT"}:
        base["funding_calculation_status"] = "UNSUPPORTED_SIGNAL"
        return base
    if start_ms is None or end_ms is None or end_ms <= start_ms:
        base["funding_calculation_status"] = "INVALID_WINDOW"
        return base

    try:
        import requests
        response = requests.get(
            FUNDING_HISTORY_URL,
            params={"symbol": contract, "startAt": start_ms, "endAt": end_ms},
            timeout=5,
        )
        if response.status_code != 200:
            base["funding_calculation_status"] = f"HTTP_{response.status_code}"
            return base
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != "200000":
            base["funding_calculation_status"] = "API_REJECTED"
            return base
        data = payload.get("data") or {}
        rows = data.get("list") or [] if isinstance(data, dict) else (data if isinstance(data, list) else [])
        rates = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                rate = float(item.get("fundingRate"))
                ts_ms = int(item.get("ts", item.get("timepoint", 0)) or 0)
            except (TypeError, ValueError):
                continue
            if start_ms <= ts_ms <= end_ms and math.isfinite(rate):
                rates.append(rate)
        base.update({
            "funding_calculation_status": "OBSERVED_RATES" if rates else "NO_SETTLEMENTS_IN_WINDOW",
            "funding_settlements_count": len(rates),
            "funding_rate_sum": round(sum(rates), 12),
        })
        return base
    except Exception as exc:
        base["funding_calculation_status"] = f"REQUEST_FAILED:{type(exc).__name__}"
        return base


def complete_economics(
    signal: Dict[str, Any],
    result: Dict[str, Any],
    funding: Dict[str, Any],
) -> Dict[str, Any]:
    """Complete model net-R after public funding observation is available."""
    provisional = build_provisional_economics(signal, result)
    status = str(funding.get("funding_calculation_status") or "UNAVAILABLE")
    if status not in {"OBSERVED_RATES", "NO_SETTLEMENTS_IN_WINDOW"}:
        return {
            **provisional,
            **funding,
            "economics_status": "FUNDING_RETRY",
            "economics_cost_components_complete": False,
            "economics_quality": "PROVISIONAL_FEE_SLIPPAGE_ONLY",
            "economics_updated_at": datetime.now(timezone.utc).isoformat(),
        }

    risk_pct = _risk_pct(signal)
    gross_price_pct = _safe_float(result.get("pnl_pct"))
    leverage = max(1.0, _safe_float(signal.get("leverage"), 1.0) or 1.0)
    if risk_pct is None or gross_price_pct is None:
        return provisional

    round_trip_rate = _safe_float(provisional.get("economics_round_trip_cost_rate"), configured_round_trip_cost_rate()) or configured_round_trip_cost_rate()
    rate_sum = _safe_float(funding.get("funding_rate_sum"), 0.0) or 0.0
    side_multiplier = 1.0 if str(signal.get("action_normalized") or "").upper() == "LONG" else -1.0
    funding_cost_pct_notional = rate_sum * side_multiplier * 100.0
    funding_cost_r = funding_cost_pct_notional / risk_pct
    fee_cost_r = (round_trip_rate * 100.0) / risk_pct
    total_cost_r = fee_cost_r + funding_cost_r
    gross_r = gross_price_pct / risk_pct
    net_r = gross_r - total_cost_r
    net_margin_pct = (
        gross_price_pct * leverage
        - (round_trip_rate * 100.0 + funding_cost_pct_notional) * leverage
    )

    return {
        **provisional,
        **funding,
        "economics_status": (
            "MODELED_COMPLETE" if status == "OBSERVED_RATES"
            else "MODELED_COMPLETE_NO_SETTLEMENT"
        ),
        "economics_cost_components_complete": True,
        "gross_r": round(gross_r, 6),
        "modeled_funding_cost_r": round(funding_cost_r, 6),
        "modeled_total_cost_r": round(total_cost_r, 6),
        "modeled_net_r": round(net_r, 6),
        "modeled_net_pnl_pct_margin": round(net_margin_pct, 6),
        "economics_quality": "MODEL_COMPLETE_PUBLIC_FUNDING",
        "economics_updated_at": datetime.now(timezone.utc).isoformat(),
    }


def enrich_pending_execution_economics(db, *, limit: int = 4) -> Dict[str, int]:
    """Bounded enrichment pass; failures never alter TP/SL lifecycle."""
    stats = {"pending": 0, "completed": 0, "retry": 0, "errors": 0}
    if db is None or not getattr(db, "enabled", False):
        return stats
    try:
        response = (
            db.client.table("signal_results")
            .select(
                "id,signal_id,status,exit_timestamp,pnl_pct,entry_timestamp,execution_forensics,"
                "economics_status,economics_updated_at,funding_attempts,"
                "signals(id,symbol,system_type,action_normalized,entry_price,stop_loss,take_profit,leverage,risk_reward,created_at)"
            )
            .in_("economics_status", ["FUNDING_PENDING", "FUNDING_RETRY"])
            .lt("funding_attempts", 3)
            .order("economics_updated_at", desc=False)
            .limit(max(1, min(int(limit), 12)))
            .execute()
        )
        rows = response.data or []
        stats["pending"] = len(rows)
        for row in rows:
            try:
                nested = row.get("signals") or {}
                if isinstance(nested, list):
                    nested = nested[0] if nested and isinstance(nested[0], dict) else {}
                signal = nested if isinstance(nested, dict) else {}
                if not signal:
                    lookup = (
                        db.client.table("signals")
                        .select("id,symbol,system_type,action_normalized,entry_price,stop_loss,take_profit,leverage,risk_reward,created_at")
                        .eq("id", row.get("signal_id"))
                        .limit(1)
                        .execute().data or []
                    )
                    signal = lookup[0] if lookup else {}
                funding = fetch_public_funding(signal, row)
                economics = complete_economics(signal, row, funding)
                attempts = int(row.get("funding_attempts") or 0) + 1
                economics["funding_attempts"] = attempts
                if economics.get("economics_status") == "FUNDING_RETRY":
                    economics["economics_last_error"] = str(funding.get("funding_calculation_status") or "UNAVAILABLE")[:180]
                    stats["retry"] += 1
                else:
                    economics["economics_last_error"] = None
                    stats["completed"] += 1
                (
                    db.client.table("signal_results")
                    .update(economics)
                    .eq("id", row.get("id"))
                    .in_("economics_status", ["FUNDING_PENDING", "FUNDING_RETRY"])
                    .execute()
                )
            except Exception:
                stats["errors"] += 1
        return stats
    except Exception:
        stats["errors"] += 1
        return stats


def seed_missing_execution_economics(db, *, limit: int = 4) -> Dict[str, int]:
    """Bounded safe backfill for already-resolved Futures rows.

    It uses only persisted Entry/SL/outcome/forensics.  If the exact Entry
    timestamp is unavailable, the row remains explicitly incomplete; the
    function never substitutes signal creation time for a real fill time.
    """
    stats = {"scanned": 0, "seeded": 0, "completed": 0, "incomplete": 0, "errors": 0}
    if db is None or not getattr(db, "enabled", False):
        return stats
    try:
        response = (
            db.client.table("signal_results")
            .select(
                "id,signal_id,status,exit_timestamp,pnl_pct,entry_timestamp,execution_forensics,"
                "economics_status,funding_attempts,"
                "signals(id,symbol,system_type,action_normalized,entry_price,stop_loss,take_profit,leverage,risk_reward,created_at)"
            )
            .in_("status", ["tp_hit", "sl_hit"])
            .is_("economics_status", "null")
            .order("created_at", desc=True)
            .limit(max(1, min(int(limit), 12)))
            .execute()
        )
        rows = response.data or []
        stats["scanned"] = len(rows)
        for row in rows:
            try:
                nested = row.get("signals") or {}
                if isinstance(nested, list):
                    nested = nested[0] if nested and isinstance(nested[0], dict) else {}
                signal = nested if isinstance(nested, dict) else {}
                if str(signal.get("system_type") or "").lower() != "futures":
                    continue
                provisional = build_provisional_economics(signal, row)
                if not provisional:
                    continue
                final_payload = provisional
                if provisional.get("economics_status") == "FUNDING_PENDING":
                    funding = fetch_public_funding(signal, {**row, **provisional})
                    final_payload = complete_economics(signal, {**row, **provisional}, funding)
                    final_payload["funding_attempts"] = int(row.get("funding_attempts") or 0) + 1
                    if final_payload.get("economics_status") in COMPLETE_STATUSES:
                        stats["completed"] += 1
                    else:
                        stats["incomplete"] += 1
                        final_payload["economics_last_error"] = str(
                            funding.get("funding_calculation_status") or "UNAVAILABLE"
                        )[:180]
                else:
                    stats["incomplete"] += 1
                db.client.table("signal_results").update(final_payload).eq("id", row.get("id")).execute()
                stats["seeded"] += 1
            except Exception:
                stats["errors"] += 1
        return stats
    except Exception:
        stats["errors"] += 1
        return stats
