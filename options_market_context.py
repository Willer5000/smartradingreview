"""Commit 17.5.10.2 — low-bandwidth public option-chain adapter.

BTC/ETH only.  No projection of BTC option strikes/GEX onto altcoins.
No polling.  Cache defaults to one hour.

The module fetches Deribit public book summaries only when the already-existing
application path requests them.  It does not create direction or trigger a full
Futures analysis.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

VERSION = "COMMIT19_1_OPTIONS_BANDWIDTH_GUARD_V1"
DERIBIT_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
CACHE_TTL = max(
    900,
    min(21600, int(os.getenv("OPTIONS_MM_CACHE_TTL_SECONDS", "7200") or 7200)),
)
ENABLED = str(os.getenv("OPTIONS_MM_CONTEXT_ENABLED", "1")).strip().lower() not in {
    "0", "false", "no", "off"
}
_TIMEOUT = max(
    1.0,
    min(6.0, float(os.getenv("OPTIONS_MM_HTTP_TIMEOUT", "3.0") or 3.0)),
)
MAX_NORMALIZED_ROWS = max(
    80,
    min(320, int(os.getenv("OPTIONS_MM_MAX_CHAIN_ROWS", "220") or 220)),
)
MAX_RESPONSE_BYTES = max(262144, min(2097152, int(os.getenv("OPTIONS_MM_MAX_RESPONSE_BYTES", "1572864") or 1572864)))
# Added provider egress is bounded independently from the main service budget.
# 12 MB/day ~= 360 MB/month worst-case additional service-initiated traffic.
DAILY_PROVIDER_BUDGET_BYTES = max(2 * 1024 * 1024, min(32 * 1024 * 1024, int(float(os.getenv("OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB", "12") or 12) * 1024 * 1024)))

_LOCK = threading.Lock()
_CACHE: Dict[str, Dict[str, Any]] = {}
_INFLIGHT = set()
_DAILY_NETWORK = {"day": None, "bytes": 0}


def _network_budget_state(now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    with _LOCK:
        if _DAILY_NETWORK.get("day") != day:
            _DAILY_NETWORK["day"] = day
            _DAILY_NETWORK["bytes"] = 0
        return {
            "day": day,
            "bytes": int(_DAILY_NETWORK.get("bytes") or 0),
            "budget_bytes": int(DAILY_PROVIDER_BUDGET_BYTES),
        }


def _record_network_bytes(count: int, now: Optional[datetime] = None) -> None:
    if count <= 0:
        return
    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    with _LOCK:
        if _DAILY_NETWORK.get("day") != day:
            _DAILY_NETWORK["day"] = day
            _DAILY_NETWORK["bytes"] = 0
        _DAILY_NETWORK["bytes"] = int(_DAILY_NETWORK.get("bytes") or 0) + int(count)


def _currency_for_symbol(symbol: Any) -> Optional[str]:
    sym = str(symbol or "").upper().replace("/", "-")
    if sym.startswith("BTC-"):
        return "BTC"
    if sym.startswith("ETH-"):
        return "ETH"
    return None


def _parse_instrument_name(name: str) -> Optional[Dict[str, Any]]:
    raw = str(name or "").upper()
    parts = raw.split("-")
    if len(parts) < 4:
        return None
    typ = parts[-1]
    if typ not in {"C", "P"}:
        return None
    try:
        strike = float(parts[-2])
        expiry = datetime.strptime(parts[-3], "%d%b%y").replace(
            tzinfo=timezone.utc, hour=8
        )
    except Exception:
        return None
    return {
        "strike": strike,
        "expiry": expiry,
        "option_type": "CALL" if typ == "C" else "PUT",
    }


def _normalize_summary_rows(
    rows: Any, *, now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    parsed: List[Dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        meta = _parse_instrument_name(raw.get("instrument_name"))
        if not meta:
            continue
        try:
            oi_f = float(raw.get("open_interest") or 0)
            iv_f = float(raw.get("mark_iv") or raw.get("iv") or 0)
            vol_f = float(raw.get("volume") or 0)
            underlying = float(
                raw.get("underlying_price")
                or raw.get("estimated_delivery_price")
                or 0
            )
        except Exception:
            continue
        if oi_f <= 0 or iv_f <= 0:
            continue
        hours = (meta["expiry"] - now).total_seconds() / 3600.0
        if hours <= 0:
            continue
        parsed.append({
            **meta,
            "open_interest": oi_f,
            "iv": iv_f,
            "volume": max(0.0, vol_f),
            "contract_multiplier": 1.0,
            "underlying_price": underlying,
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY",
        })

    if not parsed:
        return []

    within_24 = [
        r for r in parsed
        if (r["expiry"] - now).total_seconds() <= 24 * 3600
    ]
    if within_24:
        selected = within_24
    else:
        nearest = min(r["expiry"] for r in parsed)
        selected = [r for r in parsed if r["expiry"] == nearest]

    # CPU/RAM guard. Gamma naturally suppresses far OTM strikes, but public
    # chains can still contain hundreds of rows. Keep the most relevant OI and
    # traded rows without creating a second provider request.
    if len(selected) > MAX_NORMALIZED_ROWS:
        selected = sorted(
            selected,
            key=lambda r: (
                float(r.get("open_interest") or 0.0),
                float(r.get("volume") or 0.0),
            ),
            reverse=True,
        )[:MAX_NORMALIZED_ROWS]
    return selected


def get_crypto_option_chain(symbol: Any) -> Dict[str, Any]:
    currency = _currency_for_symbol(symbol)
    if not currency:
        return {
            "available": False, "currency": None, "rows": [],
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY", "version": VERSION,
            "observed": False, "direct_underlying_match": False,
            "reason": "NO_DIRECT_OPTION_UNDERLYING_FOR_SYMBOL",
        }

    now_mono = time.monotonic()
    with _LOCK:
        cached = dict(_CACHE.get(currency) or {})
        if cached and now_mono - float(cached.get("at") or 0.0) < CACHE_TTL:
            value = dict(cached.get("value") or {})
            value["cache_hit"] = True
            return value
        if currency in _INFLIGHT:
            return {
                "available": False, "currency": currency, "rows": [],
                "source": "DERIBIT_PUBLIC_BOOK_SUMMARY", "version": VERSION,
                "observed": False, "direct_underlying_match": True,
                "reason": "FETCH_IN_PROGRESS", "cache_hit": False,
            }

    if not ENABLED or requests is None:
        return {
            "available": False, "currency": currency, "rows": [],
            "reason": "DISABLED_OR_REQUESTS_UNAVAILABLE", "version": VERSION,
            "observed": False, "direct_underlying_match": True,
        }

    with _LOCK:
        # Recheck after the fast path to avoid a race between readers.
        if currency in _INFLIGHT:
            return {
                "available": False, "currency": currency, "rows": [],
                "source": "DERIBIT_PUBLIC_BOOK_SUMMARY", "version": VERSION,
                "observed": False, "direct_underlying_match": True,
                "reason": "FETCH_IN_PROGRESS", "cache_hit": False,
            }
        _INFLIGHT.add(currency)

    budget = _network_budget_state()
    if int(budget.get("bytes") or 0) >= int(budget.get("budget_bytes") or DAILY_PROVIDER_BUDGET_BYTES):
        with _LOCK:
            _INFLIGHT.discard(currency)
        return {
            "available": False, "currency": currency, "rows": [],
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY", "version": VERSION,
            "observed": False, "direct_underlying_match": True,
            "reason": "DAILY_PROVIDER_BUDGET_REACHED", "cache_hit": False,
            "provider_bytes_today": int(budget.get("bytes") or 0),
            "provider_daily_budget_bytes": int(budget.get("budget_bytes") or DAILY_PROVIDER_BUDGET_BYTES),
        }

    resp = None
    received = 0
    try:
        resp = requests.get(
            DERIBIT_URL, params={"currency": currency, "kind": "option"},
            timeout=_TIMEOUT, headers={"User-Agent": "SmartradingReview/19.1"},
            stream=True,
        )
        content_length = 0
        try:
            content_length = int((getattr(resp, "headers", {}) or {}).get("Content-Length") or 0)
        except Exception:
            content_length = 0
        remaining_daily = max(0, int(budget.get("budget_bytes") or DAILY_PROVIDER_BUDGET_BYTES) - int(budget.get("bytes") or 0))
        if content_length > MAX_RESPONSE_BYTES or (content_length and content_length > remaining_daily):
            raise ValueError("OPTION_RESPONSE_TOO_LARGE_OR_BUDGET")
        resp.raise_for_status()
        chunks = []
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES or received > remaining_daily:
                raise ValueError("OPTION_RESPONSE_TOO_LARGE_OR_BUDGET")
            chunks.append(chunk)
        payload = json.loads(b"".join(chunks).decode("utf-8")) if chunks else {}
        _record_network_bytes(received)
        _recorded_bytes = received
        received = 0
        rows = _normalize_summary_rows((payload or {}).get("result") or [])
        value = {
            "available": bool(rows), "currency": currency, "rows": rows,
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY", "version": VERSION,
            "observed": bool(rows), "direct_underlying_match": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "cache_ttl_seconds": CACHE_TTL, "rows_used": len(rows),
            "cache_hit": False,
            "provider_bytes_last_fetch": int(locals().get("_recorded_bytes", 0) or received),
            "provider_bytes_today": int(_network_budget_state().get("bytes") or 0),
            "provider_daily_budget_bytes": int(DAILY_PROVIDER_BUDGET_BYTES),
        }
    except Exception as exc:
        if received > 0:
            _record_network_bytes(received)
        _reason = str(exc)
        value = {
            "available": False, "currency": currency, "rows": [],
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY", "version": VERSION,
            "observed": False, "direct_underlying_match": True,
            "reason": ("OPTION_RESPONSE_TOO_LARGE_OR_BUDGET" if _reason == "OPTION_RESPONSE_TOO_LARGE_OR_BUDGET" else type(exc).__name__),
            "cache_hit": False,
            "provider_bytes_last_fetch": int(received),
            "provider_bytes_today": int(_network_budget_state().get("bytes") or 0),
            "provider_daily_budget_bytes": int(DAILY_PROVIDER_BUDGET_BYTES),
        }
    finally:
        try:
            if resp is not None and hasattr(resp, "close"):
                resp.close()
            elif resp is not None and hasattr(resp, "__exit__"):
                resp.__exit__(None, None, None)
        except Exception:
            pass
        with _LOCK:
            _INFLIGHT.discard(currency)

    with _LOCK:
        _CACHE[currency] = {"at": now_mono, "value": dict(value)}
    return value

