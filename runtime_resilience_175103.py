"""Commit 17.5.10.3 bounded runtime resilience.

No new thread, polling, LLM call, DB query or scheduled network request.
Known blocked public providers fail open and are negative-cached in-process.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "17.5.10.3_RUNTIME_RESILIENCE_V1"
_INSTALLED = False
_STATE: Dict[str, Any] = {
    "installed": False,
    "bls_http_403_seen": False,
    "bls_disabled_for_process": False,
}


def install_runtime_resilience_175103() -> Dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return dict(_STATE)
    _INSTALLED = True
    try:
        import macro_context as mc
        original = getattr(mc, "_fetch_bls_calendar", None)
        if callable(original) and not getattr(original, "_st175103_wrapped", False):
            disabled = {"value": False}

            def _safe_bls(*args, **kwargs):
                if disabled["value"]:
                    return []
                try:
                    return original(*args, **kwargs)
                except Exception as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if int(status or 0) == 403:
                        disabled["value"] = True
                        _STATE["bls_http_403_seen"] = True
                        _STATE["bls_disabled_for_process"] = True
                        # Preserve diagnostic truth without escalating a known
                        # provider refusal into a trading failure.
                        try:
                            with mc._LOCK:
                                errors = list(mc._CACHE.get("errors") or [])
                                errors.append("BLS: HTTP_403_PROVIDER_UNAVAILABLE")
                                mc._CACHE["errors"] = errors[-8:]
                        except Exception:
                            pass
                        return []
                    raise

            _safe_bls._st175103_wrapped = True
            mc._fetch_bls_calendar = _safe_bls
        _STATE["installed"] = True
        _STATE["version"] = VERSION
    except Exception as exc:
        _STATE["installed"] = False
        _STATE["error"] = type(exc).__name__
    return dict(_STATE)
