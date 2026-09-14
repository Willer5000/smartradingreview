from __future__ import annotations

"""RC4 cohort standardization for profitability statistics.

No database row is deleted or rewritten.  This module gives every analytics row
an explicit statistical role so pre-audit/legacy/research records can remain
available without contaminating current official WR/PF/expectancy.
"""
from typing import Any, Dict

from q6_integrity import spot_cell_active

VERSION = "RC4_1_COHORT_INTEGRITY_V2"
CORE_FUTURES_TFS = {"30m", "1h", "2h", "4h"}
HIGH_FUTURES_TFS = {"12h", "1D"}
HIGH_FUTURES_SYMBOLS = {"BTC-USDT", "ETH-USDT", "SOL-USDT"}


def _b(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def futures_cell_active(symbol: Any, timeframe: Any) -> bool:
    symbol = str(symbol or "").upper().replace("/", "-")
    tf_raw = str(timeframe or "").strip()
    tf = "1D" if tf_raw.upper() == "1D" else tf_raw.lower()
    if tf in CORE_FUTURES_TFS:
        return symbol in {"BTC-USDT","ETH-USDT","SOL-USDT","XRP-USDT","ADA-USDT","LINK-USDT","BNB-USDT"}
    if tf in HIGH_FUTURES_TFS:
        return symbol in HIGH_FUTURES_SYMBOLS
    return False


def classify_quality_signal(signal: Dict[str, Any], *, spot_verified: bool = False) -> Dict[str, Any]:
    signal = signal or {}
    market = str(signal.get("system_type") or "").lower()
    context = signal.get("context") or {}
    learning = context.get("learning") or {} if isinstance(context, dict) else {}
    if not isinstance(learning, dict):
        learning = {}

    if market == "spot":
        if not spot_cell_active(signal.get("symbol"), signal.get("timeframe") or signal.get("interval")):
            return {
                "version": VERSION,
                "cohort": "LEGACY_ARCHIVE",
                "official": False,
                "reason": "OUTSIDE_RC4_1_SPOT_ACTIVE_CELL_CONTRACT",
            }
        cohort = "OFFICIAL_CURRENT_SPOT" if spot_verified else "LEGACY_OR_UNVERIFIED_SPOT"
        return {
            "version": VERSION,
            "cohort": cohort,
            "official": bool(spot_verified),
            "reason": "Q6_VERIFIED_ACTIVE_CELL" if spot_verified else "SPOT_PROVENANCE_NOT_VERIFIED",
        }

    if market != "futures":
        return {"version": VERSION, "cohort": "NON_TRADING_OR_UNKNOWN", "official": False, "reason": "UNKNOWN_MARKET"}

    if not futures_cell_active(signal.get("symbol"), signal.get("timeframe") or signal.get("interval")):
        return {"version": VERSION, "cohort": "LEGACY_ARCHIVE", "official": False, "reason": "OUTSIDE_RC4_ACTIVE_CELL_CONTRACT"}

    clean = (
        learning.get("cohort") == "FUTURES_PERPETUAL_REAL_CLOSED_V1"
        and learning.get("market_data_source") == "KUCOIN_FUTURES_PERPETUAL_REST"
        and not _b(learning.get("market_data_is_synthetic", True))
        and _b(learning.get("source_candle_closed", False))
    )
    role = str(learning.get("evaluation_role") or "").upper()
    eligible = _b(learning.get("statistically_eligible", False))
    if clean and eligible and role == "EXECUTABLE_SIGNAL":
        return {"version": VERSION, "cohort": "OFFICIAL_CURRENT_FUTURES", "official": True, "reason": "VERIFIED_EXECUTABLE"}
    if clean and role == "SHADOW_ANALYSIS":
        return {"version": VERSION, "cohort": "SHADOW_CURRENT_FUTURES", "official": False, "reason": "VERIFIED_SHADOW"}
    if clean:
        return {"version": VERSION, "cohort": "RESEARCH_ONLY_CURRENT_FUTURES", "official": False, "reason": role or "NOT_STATISTICALLY_ELIGIBLE"}
    return {"version": VERSION, "cohort": "LEGACY_OR_UNVERIFIED_FUTURES", "official": False, "reason": "FUTURES_PROVENANCE_NOT_VERIFIED"}


def summarize_cohorts(rows, classifier):
    counts: Dict[str, int] = {}
    for row in rows or []:
        info = classifier(row) or {}
        name = str(info.get("cohort") or "UNKNOWN")
        counts[name] = counts.get(name, 0) + 1
    return {"version": VERSION, "rows_seen": sum(counts.values()), "counts": counts, "policy": "KEEP_HISTORY; ONLY_ACTIVE_VERIFIED_CELLS_CALIBRATE_PROFITABILITY"}
