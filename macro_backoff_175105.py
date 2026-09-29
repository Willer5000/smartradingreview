"""17.5.10.5 — bounded negative-cache for GDELT macro provider.

A GDELT timeout is context loss, never a trading veto. Repeating the same
7-second timeout in many cells wastes the single Render worker and egress.
This patch adds process-local single-flight/backoff only; it does not add
network requests.
"""
from __future__ import annotations
import threading
import time
from typing import Any, Dict

VERSION = "17.5.10.5_GDELT_NEGATIVE_CACHE_V1"
_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {
    "installed": False,
    "blocked_until": 0.0,
    "failures": 0,
    "version": VERSION,
}


def install_macro_backoff_175105() -> Dict[str, Any]:
    with _LOCK:
        if _STATE["installed"]:
            return dict(_STATE)
        import macro_context as macro
        fn = getattr(macro, "_fetch_gdelt_news", None)
        if not callable(fn):
            # Some older branches use another internal name. Fail open.
            _STATE.update({"installed": True, "provider_function": "UNAVAILABLE"})
            return dict(_STATE)
        if getattr(fn, "_st175105_negative_cache", False):
            _STATE.update({"installed": True, "provider_function": "_fetch_gdelt_news"})
            return dict(_STATE)

        original = fn
        call_lock = threading.Lock()

        def wrapped(*args, **kwargs):
            now = time.monotonic()
            with _LOCK:
                if now < float(_STATE.get("blocked_until") or 0.0):
                    return []
            if not call_lock.acquire(blocking=False):
                # Another request already owns the provider call. Macro is
                # context-only, so duplicate callers fail open immediately.
                return []
            try:
                try:
                    value = original(*args, **kwargs)
                except Exception:
                    with _LOCK:
                        _STATE["failures"] = int(_STATE.get("failures") or 0) + 1
                        # 15 min first failure, 30 min after repeated failures.
                        wait = 900 if _STATE["failures"] <= 1 else 1800
                        _STATE["blocked_until"] = time.monotonic() + wait
                    raise
                with _LOCK:
                    _STATE["failures"] = 0
                    _STATE["blocked_until"] = 0.0
                return value
            finally:
                call_lock.release()

        wrapped._st175105_negative_cache = True
        wrapped._st175105_original = original
        macro._fetch_gdelt_news = wrapped
        _STATE.update({
            "installed": True,
            "provider_function": "_fetch_gdelt_news",
            "policy": "SINGLE_FLIGHT_15M_THEN_30M_FAIL_OPEN",
        })
        return dict(_STATE)
