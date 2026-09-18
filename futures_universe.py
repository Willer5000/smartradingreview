"""Commit 9.6 — governed multi-risk Futures universe.

This module is intentionally small and pure.  It centralises the production
universe and the risk-class policy without increasing the number of DataFrames
kept in memory.  app.py applies the contract to futures_system at runtime so
older imports remain backwards compatible.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Tuple

VERSION = "COMMIT9_6_MULTI_RISK_FUTURES_V1"

RISK_CLASS_SYMBOLS: Dict[str, Tuple[str, ...]] = {
    "CORE1": ("BTC-USDT", "ETH-USDT", "SOL-USDT"),
    "CORE2": ("XRP-USDT", "ADA-USDT"),
    "MEDIUM": ("BNB-USDT", "LINK-USDT", "AVAX-USDT", "NEAR-USDT", "DOT-USDT"),
    "HIGH": ("SUI-USDT", "HYPE-USDT", "APT-USDT", "INJ-USDT", "SEI-USDT"),
}

RISK_CLASS_TIMEFRAMES: Dict[str, Tuple[str, ...]] = {
    "CORE1": ("30m", "1h", "2h", "4h", "12h", "1D"),
    "CORE2": ("30m", "1h", "2h", "4h", "12h"),
    "MEDIUM": ("30m", "1h", "2h", "4h"),
    "HIGH": ("30m", "1h", "2h"),
}

SYMBOL_META: Dict[str, Dict[str, Any]] = {
    "BTC-USDT": {"name": "BTC/USDT", "type": "crypto_major", "decimals": 2},
    "ETH-USDT": {"name": "ETH/USDT", "type": "crypto_major", "decimals": 2},
    "SOL-USDT": {"name": "SOL/USDT", "type": "crypto_major", "decimals": 3},
    "XRP-USDT": {"name": "XRP/USDT", "type": "crypto_major", "decimals": 4},
    "ADA-USDT": {"name": "ADA/USDT", "type": "crypto_major", "decimals": 4},
    "BNB-USDT": {"name": "BNB/USDT", "type": "crypto_alt", "decimals": 2},
    "LINK-USDT": {"name": "LINK/USDT", "type": "crypto_alt", "decimals": 3},
    "AVAX-USDT": {"name": "AVAX/USDT", "type": "crypto_alt", "decimals": 3},
    "NEAR-USDT": {"name": "NEAR/USDT", "type": "crypto_alt", "decimals": 4},
    "DOT-USDT": {"name": "DOT/USDT", "type": "crypto_alt", "decimals": 4},
    "SUI-USDT": {"name": "SUI/USDT", "type": "crypto_high_beta", "decimals": 4},
    "HYPE-USDT": {"name": "HYPE/USDT", "type": "crypto_high_beta", "decimals": 3},
    "APT-USDT": {"name": "APT/USDT", "type": "crypto_high_beta", "decimals": 4},
    "INJ-USDT": {"name": "INJ/USDT", "type": "crypto_high_beta", "decimals": 3},
    "SEI-USDT": {"name": "SEI/USDT", "type": "crypto_high_beta", "decimals": 5},
}

CONTRACT_SYMBOLS: Dict[str, str] = {
    "BTC-USDT": "XBTUSDTM",
    "ETH-USDT": "ETHUSDTM",
    "SOL-USDT": "SOLUSDTM",
    "XRP-USDT": "XRPUSDTM",
    "ADA-USDT": "ADAUSDTM",
    "BNB-USDT": "BNBUSDTM",
    "LINK-USDT": "LINKUSDTM",
    "AVAX-USDT": "AVAXUSDTM",
    "NEAR-USDT": "NEARUSDTM",
    "DOT-USDT": "DOTUSDTM",
    "SUI-USDT": "SUIUSDTM",
    "HYPE-USDT": "HYPEUSDTM",
    "APT-USDT": "APTUSDTM",
    "INJ-USDT": "INJUSDTM",
    "SEI-USDT": "SEIUSDTM",
}

TIMEFRAME_META = {
    "30m": {"name": "30 Minutos", "type": "intraday", "kucoin": "30min"},
    "1h": {"name": "1 Hora", "type": "intraday", "kucoin": "1hour"},
    "2h": {"name": "2 Horas", "type": "intraday", "kucoin": "2hour"},
    "4h": {"name": "4 Horas", "type": "swing", "kucoin": "4hour"},
    "12h": {"name": "12 Horas", "type": "swing_context", "kucoin": "12hour"},
    "1D": {"name": "1 Día", "type": "macro_swing", "kucoin": "1day"},
}

# The class changes execution tempo, never the minimum production Safety.
EXIT_PROFILES: Dict[str, Dict[str, Any]] = {
    "CORE1": {"name": "NORMAL", "risk_budget_multiplier": 1.00, "entry_zone_pct": 0.15, "max_entry_wait_bars": 5, "guardian_reduce_score": 65, "guardian_exit_score": 85, "allow_scale_in": True},
    "CORE2": {"name": "CONTROLLED", "risk_budget_multiplier": 0.85, "entry_zone_pct": 0.13, "max_entry_wait_bars": 4, "guardian_reduce_score": 60, "guardian_exit_score": 82, "allow_scale_in": True},
    "MEDIUM": {"name": "FAST", "risk_budget_multiplier": 0.65, "entry_zone_pct": 0.10, "max_entry_wait_bars": 3, "guardian_reduce_score": 52, "guardian_exit_score": 75, "allow_scale_in": False},
    "HIGH": {"name": "VERY_FAST", "risk_budget_multiplier": 0.45, "entry_zone_pct": 0.08, "max_entry_wait_bars": 2, "guardian_reduce_score": 42, "guardian_exit_score": 68, "allow_scale_in": False},
}

# Heavy Research representatives only.  This is a prior for the class; it is
# never a local Champion for another symbol.
RESEARCH_REPRESENTATIVE: Dict[str, str] = {
    "CORE1": "BTC-USDT",
    "CORE2": "XRP-USDT",
    "MEDIUM": "LINK-USDT",
    "HIGH": "SUI-USDT",
}


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def risk_class_for(symbol: Any) -> str:
    symbol = _symbol(symbol)
    for risk_class, symbols in RISK_CLASS_SYMBOLS.items():
        if symbol in symbols:
            return risk_class
    return "UNKNOWN"




def learning_bucket_for(symbol: Any) -> str:
    """ReviewTrader aggregation bucket without weakening execution classes.

    CORE1/CORE2 keep different production TF/risk policies, while backtest
    diagnostics may aggregate them as CORE. MEDIUM/HIGH stay separate.
    """
    rc = risk_class_for(symbol)
    return "CORE" if rc in ("CORE1", "CORE2") else rc

def allowed_timeframes(symbol: Any) -> Tuple[str, ...]:
    return RISK_CLASS_TIMEFRAMES.get(risk_class_for(symbol), tuple())


def timeframe_allowed(symbol: Any, timeframe: Any) -> bool:
    return str(timeframe or "").strip() in allowed_timeframes(symbol)


def exit_profile_for(symbol: Any) -> Dict[str, Any]:
    rc = risk_class_for(symbol)
    return {"risk_class": rc, **dict(EXIT_PROFILES.get(rc) or {})}


def representative_for(symbol: Any) -> str:
    return RESEARCH_REPRESENTATIVE.get(risk_class_for(symbol), "")


def all_symbols() -> Tuple[str, ...]:
    return tuple(SYMBOL_META.keys())


def operational_combinations() -> List[Tuple[str, str]]:
    return [(symbol, tf) for symbol in all_symbols() for tf in allowed_timeframes(symbol)]


def operational_action_cells() -> List[Tuple[str, str, str]]:
    return [(symbol, tf, action) for symbol, tf in operational_combinations() for action in ("LONG", "SHORT")]


def universe_audit() -> Dict[str, Any]:
    combos = operational_combinations()
    cells = operational_action_cells()
    return {
        "version": VERSION,
        "symbols": len(all_symbols()),
        "combinations": len(combos),
        "action_cells": len(cells),
        "expected_symbols": 15,
        "expected_combinations": 63,
        "expected_action_cells": 126,
        "ok": len(all_symbols()) == 15 and len(combos) == 63 and len(cells) == 126,
        "by_class": {rc: {"symbols": len(symbols), "timeframes": list(RISK_CLASS_TIMEFRAMES[rc])} for rc, symbols in RISK_CLASS_SYMBOLS.items()},
    }


def configure_futures_module(module: Any) -> Any:
    """Idempotently apply the V2 universe to the legacy futures_system module."""
    if getattr(module, "_COMMIT96_UNIVERSE_VERSION", None) == VERSION:
        return module
    module.FUTURES_SYMBOLS = {k: dict(v) for k, v in SYMBOL_META.items()}
    module.FUTURES_RESEARCH_SYMBOLS = {}
    module.FUTURES_RESEARCH_TIMEFRAMES = tuple()
    module.FUTURES_RESEARCH_ENABLED = False
    module.FUTURES_ALL_SYMBOLS = {k: dict(v) for k, v in SYMBOL_META.items()}
    module.FUTURES_CONTRACT_SYMBOLS = dict(CONTRACT_SYMBOLS)
    module.FUTURES_TIMEFRAMES = {k: dict(v) for k, v in TIMEFRAME_META.items()}
    module.FUTURES_HIGH_TIMEFRAME_SYMBOLS = tuple(RISK_CLASS_SYMBOLS["CORE1"])
    module.FUTURES_HIGH_TIMEFRAMES = ("12h", "1D")
    module.futures_timeframe_allowed = timeframe_allowed
    module._COMMIT96_UNIVERSE_VERSION = VERSION
    return module


def annotate_result(result: Mapping[str, Any] | None, symbol: Any, timeframe: Any) -> Dict[str, Any]:
    out = dict(result or {})
    profile = exit_profile_for(symbol)
    out["risk_class"] = profile.get("risk_class")
    out["exit_profile"] = profile.get("name")
    out["risk_budget_multiplier"] = profile.get("risk_budget_multiplier")
    out["entry_zone_pct"] = profile.get("entry_zone_pct")
    out["max_entry_wait_bars"] = profile.get("max_entry_wait_bars")
    out["operational_timeframe_allowed"] = timeframe_allowed(symbol, timeframe)
    out["research_representative"] = representative_for(symbol)
    return out


_AUDIT = universe_audit()
if not _AUDIT["ok"]:
    raise RuntimeError(f"Commit 9.6 Futures universe invalid: {_AUDIT}")
