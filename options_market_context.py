"""Commit 17.5.10 — low-bandwidth public option-chain adapter.

For crypto Futures this module can fetch Deribit public option book summaries
only when a directional execution candidate already exists.  It is cached and
fail-open; it never creates a signal.  The mathematical transformation lives in
`market_maker_math.py`.

SPY/QQQ 0DTE is intentionally NOT scraped from Cboe delayed-quote webpages.
Those pages state that automated extraction is prohibited.  Multi-Asset can
consume a lawful option-chain snapshot supplied by another provider later; until
then its Black-Scholes fallback remains SHADOW only.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

VERSION = "COMMIT17_5_10_1_OPTIONS_CONTEXT_V1"
DERIBIT_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
CACHE_TTL = max(900, min(7200, int(os.getenv("OPTIONS_MM_CACHE_TTL_SECONDS", "3600") or 3600)))
ENABLED = str(os.getenv("OPTIONS_MM_CONTEXT_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}
_TIMEOUT = max(1.0, min(6.0, float(os.getenv("OPTIONS_MM_HTTP_TIMEOUT", "3.0") or 3.0)))
_LOCK = threading.Lock()
_CACHE: Dict[str, Dict[str, Any]] = {}


def _currency_for_symbol(symbol: Any) -> Optional[str]:
    """Return a directly matching Deribit option underlying when available.

    FINAL 17.5.10 deliberately does NOT project BTC option strikes/GEX onto
    SOL/XRP/ADA/etc.  That would mix incomparable price scales and create false
    walls.  Alts therefore fall back to theoretical, zero-authority math until
    a directly matching lawful option-chain provider is available.
    """
    sym = str(symbol or "").upper().replace("/", "-")
    if sym.startswith("BTC-"):
        return "BTC"
    if sym.startswith("ETH-"):
        return "ETH"
    return None


def _parse_instrument_name(name: str) -> Optional[Dict[str, Any]]:
    """Parse common Deribit option names such as BTC-29SEP26-70000-C."""
    raw = str(name or "").upper()
    parts = raw.split("-")
    if len(parts) < 4:
        return None
    typ = parts[-1]
    if typ not in {"C", "P"}:
        return None
    try:
        strike = float(parts[-2])
        expiry = datetime.strptime(parts[-3], "%d%b%y").replace(tzinfo=timezone.utc)
        # Deribit option expiries are conventionally 08:00 UTC; using that
        # timestamp only affects time-to-expiry for the BS transform.
        expiry = expiry.replace(hour=8)
    except Exception:
        return None
    return {"strike": strike, "expiry": expiry, "option_type": "CALL" if typ == "C" else "PUT"}


def _normalize_summary_rows(rows: Any, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    parsed: List[Dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        meta = _parse_instrument_name(raw.get("instrument_name"))
        if not meta:
            continue
        oi = raw.get("open_interest")
        iv = raw.get("mark_iv") or raw.get("iv")
        try:
            oi_f, iv_f = float(oi or 0), float(iv or 0)
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
            "volume": float(raw.get("volume") or 0),
            "contract_multiplier": 1.0,
            "underlying_price": float(raw.get("underlying_price") or 0),
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY",
        })
    if not parsed:
        return []
    # Prefer true 0DTE/near-expiry. If none exist within 24h, use the nearest
    # expiry only; the math layer reports actual nearest_expiry_hours.
    within_24 = [r for r in parsed if (r["expiry"] - now).total_seconds() <= 24 * 3600]
    if within_24:
        return within_24
    nearest = min(r["expiry"] for r in parsed)
    return [r for r in parsed if r["expiry"] == nearest]


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
            return dict(cached.get("value") or {})
    if not ENABLED or requests is None:
        return {"available": False, "currency": currency, "reason": "DISABLED_OR_REQUESTS_UNAVAILABLE", "version": VERSION}
    try:
        resp = requests.get(
            DERIBIT_URL,
            params={"currency": currency, "kind": "option"},
            timeout=_TIMEOUT,
            headers={"User-Agent": "SmartradingReview/17.5.10.1"},
        )
        resp.raise_for_status()
        payload = resp.json() if hasattr(resp, "json") else {}
        rows = _normalize_summary_rows((payload or {}).get("result") or [])
        value = {
            "available": bool(rows),
            "currency": currency,
            "rows": rows,
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY",
            "version": VERSION,
            "observed": bool(rows),
            "direct_underlying_match": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        value = {
            "available": False,
            "currency": currency,
            "rows": [],
            "source": "DERIBIT_PUBLIC_BOOK_SUMMARY",
            "version": VERSION,
            "observed": False,
            "direct_underlying_match": True,
            "reason": type(exc).__name__,
        }
    with _LOCK:
        _CACHE[currency] = {"at": now_mono, "value": dict(value)}
    return value
