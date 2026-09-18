"""RC9.7 — process-wide Supabase egress/fair-use governor for Main.

All Main modules that read Supabase should share this budget.  It is application
telemetry (not Supabase billing telemetry), but it prevents one analytics/research
bridge from bypassing the client's normal free-plan guard.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

VERSION = "RC9_7_GLOBAL_EGRESS_GUARD_V1"
LOCKDOWN = str(os.getenv("FREE_PLAN_LOCKDOWN", "1")).strip().lower() not in {"0","false","no","off"}
# Goal: keep the application under roughly 1 GB/month even with five Research
# services. Main receives 12 MB/day; Research is capped separately at 2 MB/day
# per service. These are hard caps in lockdown mode even if old Render env vars
# still contain larger values.
try:
    _requested = float(os.getenv("MAIN_SUPABASE_DAILY_BUDGET_MB", "12") or 12)
except Exception:
    _requested = 12.0
DAILY_BUDGET_MB = max(6.0, _requested)
if LOCKDOWN:
    DAILY_BUDGET_MB = min(DAILY_BUDGET_MB, 12.0)

DIAGNOSTIC_GUARD = 0.62
OPTIONAL_GUARD = 0.76
IMPORTANT_GUARD = 0.90
_RESTRICTED_COOLDOWN = max(900, int(os.getenv("SUPABASE_402_COOLDOWN_SECONDS", "21600") or 21600))

_lock = threading.Lock()
_day = datetime.now(timezone.utc).date().isoformat()
_bytes = 0
_calls = 0
_restricted_until = 0.0
_restricted_reason = ""


def _roll_day() -> None:
    global _day, _bytes, _calls
    today = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        if today != _day:
            _day = today
            _bytes = 0
            _calls = 0


def _estimate(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
    except Exception:
        return 0


def track_bytes(size: int) -> None:
    global _bytes, _calls
    if not LOCKDOWN:
        return
    _roll_day()
    with _lock:
        _bytes += max(0, int(size or 0))
        _calls += 1


def track_payload(value: Any) -> None:
    track_bytes(_estimate(value))


def track_http_response(response: Any) -> None:
    try:
        content = getattr(response, "content", b"") or b""
        size = len(content)
        if not size:
            size = int((getattr(response, "headers", {}) or {}).get("Content-Length") or 0)
    except Exception:
        size = 0
    track_bytes(size)


def mark_restricted(reason: str = "HTTP_402") -> None:
    global _restricted_until, _restricted_reason
    with _lock:
        _restricted_until = max(_restricted_until, time.monotonic() + float(_RESTRICTED_COOLDOWN))
        _restricted_reason = str(reason or "HTTP_402")[:160]


def restricted() -> bool:
    with _lock:
        return time.monotonic() < _restricted_until


def status() -> Dict[str, Any]:
    _roll_day()
    with _lock:
        used = int(_bytes); calls = int(_calls); day = str(_day)
        until = float(_restricted_until); reason = str(_restricted_reason)
    budget = int(DAILY_BUDGET_MB * 1024 * 1024)
    ratio = (used / budget) if budget else 0.0
    return {
        "version": VERSION,
        "enabled": bool(LOCKDOWN),
        "day": day,
        "estimated_response_mb": round(used / 1024 / 1024, 3),
        "daily_budget_mb": round(DAILY_BUDGET_MB, 1),
        "ratio": round(ratio, 4),
        "tracked_requests": calls,
        "provider_restricted": time.monotonic() < until,
        "provider_reason": reason,
        "billing_authoritative": False,
    }


def allows(priority: str = "optional") -> bool:
    if restricted():
        return False
    if not LOCKDOWN:
        return True
    ratio = float(status().get("ratio") or 0.0)
    p = str(priority or "optional").lower()
    if p == "critical":
        return True
    if p == "important":
        return ratio < IMPORTANT_GUARD
    if p == "diagnostic":
        return ratio < DIAGNOSTIC_GUARD
    return ratio < OPTIONAL_GUARD
