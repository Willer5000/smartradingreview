"""Pure helpers for Commit 28 core recovery.

No network, DB, LLM, threads, timers or mutable global state.
"""
from __future__ import annotations

from typing import Any, Mapping, Tuple

VERSION = "COMMIT28_CORE_HELPERS_V1"


def normalize_specialist_action(action: Any, confidence: Any) -> Tuple[str, str, bool]:
    """Return (normalized_action, legacy_action, is_abstention).

    Zero-confidence NO_OPERAR is absence of applicable evidence, not a negative
    trading opinion. Real NO_OPERAR objections keep their semantics because they
    carry positive confidence/evidence.
    """
    legacy = str(action or "NO_OPERAR").strip().upper()
    try:
        conf = float(confidence or 0.0)
    except Exception:
        conf = 0.0
    if legacy == "NO_OPERAR" and conf <= 0.0:
        return "ABSTAIN", legacy, True
    if legacy in {"ABSTAIN", "NO_APLICA"}:
        return "ABSTAIN", legacy, True
    return legacy, legacy, False


def select_cached_btc_context(
    current_results: Mapping[Any, Any] | None,
    previous_results: Mapping[Any, Any] | None,
    timeframe: Any,
) -> Tuple[dict | None, str]:
    """Reuse a valid same-timeframe BTC snapshot without opening new I/O."""
    tf = str(timeframe or "")
    for source_name, source in (
        ("CURRENT_REFRESH", current_results or {}),
        ("PREVIOUS_CACHE", previous_results or {}),
    ):
        try:
            row = source.get(("BTC-USDT", tf))
        except Exception:
            row = None
        if not isinstance(row, dict) or row.get("success") is False:
            continue
        trend = row.get("trend") or {}
        if not isinstance(trend, dict):
            continue
        try:
            adx = float(trend.get("adx") or 0.0)
        except Exception:
            adx = 0.0
        if adx > 0.0:
            return row, source_name
    return None, "NONE"


def audit() -> dict:
    return {
        "version": VERSION,
        "new_io": 0,
        "new_threads": 0,
        "new_db_queries": 0,
        "new_llm_calls": 0,
    }
