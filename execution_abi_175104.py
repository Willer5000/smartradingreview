"""Commit 17.5.10.4 — Futures/Multi-Asset execution ABI adapter.

Purpose
-------
FuturesAnalysis.calculate_entry_levels historically omits the
``execution_observations`` keyword supported by the shared TradingExpertSystem.
17.5.10.3 worked around that mismatch inside app.py using a mutable market flag.
That flag is shared by concurrent requests and can race.

This adapter patches the *class boundary once* so FuturesAnalysis and its
MultiAssetAnalysis subclass expose the same call contract as Spot. It performs
no I/O, starts no threads, adds no DB/LLM/network work, and does not change any
trading threshold or signal-count policy.
"""
from __future__ import annotations

from functools import wraps
import inspect
import threading
from typing import Any, Dict

VERSION = "17.5.10.4_EXECUTION_ABI_V1"
_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {"installed": False, "native": False, "version": VERSION}
_BRIDGE_KEY = "_execution_observations_175103"  # consumed by shared base method


def install_futures_execution_abi_175104(futures_module) -> Dict[str, Any]:
    """Install once; safe for already-created FuturesAnalysis instances."""
    cls = getattr(futures_module, "FuturesAnalysis", None)
    if cls is None:
        raise AttributeError("FuturesAnalysis not found")

    with _LOCK:
        method = getattr(cls, "calculate_entry_levels", None)
        if not callable(method):
            raise AttributeError("FuturesAnalysis.calculate_entry_levels not callable")

        if getattr(method, "_st175104_execution_abi", False):
            _STATE.update({"installed": True, "native": False})
            return dict(_STATE)

        try:
            params = inspect.signature(method).parameters
        except Exception:
            params = {}

        if "execution_observations" in params:
            _STATE.update({"installed": True, "native": True})
            return dict(_STATE)

        original = method

        @wraps(original)
        def _wrapped(
            self,
            decision,
            trend,
            momentum,
            volatility,
            structure,
            symbol,
            timeframe,
            liquidation=None,
            execution_observations=None,
        ):
            had_previous = False
            previous = None
            if isinstance(structure, dict):
                had_previous = _BRIDGE_KEY in structure
                previous = structure.get(_BRIDGE_KEY)
                if isinstance(execution_observations, dict):
                    structure[_BRIDGE_KEY] = execution_observations
            try:
                return original(
                    self,
                    decision,
                    trend,
                    momentum,
                    volatility,
                    structure,
                    symbol,
                    timeframe,
                    liquidation,
                )
            finally:
                if isinstance(structure, dict):
                    if had_previous:
                        structure[_BRIDGE_KEY] = previous
                    else:
                        structure.pop(_BRIDGE_KEY, None)

        _wrapped._st175104_execution_abi = True
        _wrapped._st175104_original = original
        cls.calculate_entry_levels = _wrapped
        _STATE.update({"installed": True, "native": False})
        return dict(_STATE)
