"""Commit 18.2 — bounded in-memory quality funnel.

Resource contract:
- no network;
- no Supabase;
- no LLM;
- no background thread;
- no DataFrames;
- bounded aggregate dictionary only.

This module is diagnostic. It never creates direction, Entry, SL, TP, leverage
or publication authority.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Dict

VERSION = "COMMIT18_2_QUALITY_FUNNEL_V1"
_MAX_BUCKETS = 64
_TTL_SECONDS = 6 * 60 * 60

_lock = threading.RLock()
_buckets: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def _key(market: Any, stage: Any) -> str:
    return f"{str(market or 'UNKNOWN').upper()}::{str(stage or 'UNKNOWN').upper()}"


def _prune(now: float) -> None:
    stale = [
        key for key, row in _buckets.items()
        if now - float(row.get("last_seen") or 0.0) > _TTL_SECONDS
    ]
    for key in stale:
        _buckets.pop(key, None)
    while len(_buckets) > _MAX_BUCKETS:
        _buckets.popitem(last=False)


def record(market: Any, stage: Any, amount: int = 1) -> None:
    """Increment one bounded aggregate counter."""
    now = time.monotonic()
    key = _key(market, stage)
    with _lock:
        row = _buckets.pop(key, None) or {
            "market": str(market or "UNKNOWN").upper(),
            "stage": str(stage or "UNKNOWN").upper(),
            "count": 0,
            "first_seen": now,
        }
        row["count"] = int(row.get("count") or 0) + max(1, int(amount or 1))
        row["last_seen"] = now
        _buckets[key] = row
        _prune(now)


def snapshot() -> Dict[str, Any]:
    """Compact operator snapshot. No persistence and no market-data work."""
    now = time.monotonic()
    with _lock:
        _prune(now)
        rows = [
            {
                "market": row["market"],
                "stage": row["stage"],
                "count": int(row["count"]),
                "age_seconds": round(max(0.0, now - float(row["last_seen"])), 1),
            }
            for row in _buckets.values()
        ]
    return {
        "version": VERSION,
        "bounded": True,
        "max_buckets": _MAX_BUCKETS,
        "ttl_seconds": _TTL_SECONDS,
        "rows": rows,
        "resource_authority": "DIAGNOSTIC_ONLY_NO_DB_NO_NETWORK_NO_LLM",
    }
