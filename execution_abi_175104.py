"""Commit 17.5.10.5 — execution ABI + final structural recovery.

Base expected: 6b26d8327ff5df7bc60cad238f903fbd3cdc4a5a (17.5.10.4)

Why this module exists
----------------------
17.5.10.4 fixed the Futures/Multi-Asset ABI mismatch without changing trading
thresholds.  17.5.10.5 keeps that fix and adds ONE bounded second-chance
execution pass for an already-valid LONG/SHORT thesis when the shared Entry/SL/TP
engine ends specifically in:

- R/R below the existing technical floor; or
- an SL that still collides with an observed technical reaction level.

This pass cannot create direction, cannot lower the R/R floor, cannot invent
ATR/RR targets, cannot bypass Safety and cannot publish by itself.  It only
returns a better *base geometry* to FuturesAnalysis; the existing Futures
timing, reaction, Safety, leverage and Publication gates still run afterwards.

No network, DB, LLM, thread or polling work is added here.
"""
from __future__ import annotations

from functools import wraps
import inspect
import threading
from typing import Any, Dict, Mapping

VERSION = "17.5.10.5_EXECUTION_QUALITY_RECOVERY_V1"
_BASELINE_HEAD = "6b26d8327ff5df7bc60cad238f903fbd3cdc4a5a"
_LOCK = threading.RLock()
_STATE: Dict[str, Any] = {
    "installed": False,
    "native": False,
    "base_recovery_installed": False,
    "strategy_scope_installed": False,
    "macro_backoff_installed": False,
    "version": VERSION,
}
_BRIDGE_KEY = "_execution_observations_175103"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if n == n else float(default)
    except Exception:
        return float(default)


def _market_type(instance: Any) -> str:
    try:
        label = str(instance._market_label()).upper()
        if "MULTI" in label:
            return "multiasset"
    except Exception:
        pass
    return "futures"


def _structural_recovery_candidate(
    instance: Any,
    *,
    decision: str,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    volatility: Mapping[str, Any],
    structure: Mapping[str, Any],
    symbol: str,
    timeframe: str,
    liquidation: Any,
    levels: Mapping[str, Any],
) -> Dict[str, Any]:
    """Search independent Entry -> SL -> TP geometry from already loaded data."""
    from execution_specialist_committees import (
        recover_execution_geometry_from_structure,
        evaluate_sl_reaction_conflict,
    )

    current = _f((structure or {}).get("current_price"))
    atr = _f((volatility or {}).get("atr"))
    if current <= 0:
        current = _f(levels.get("current_price")) or _f(levels.get("entry"))
    if atr <= 0 and current > 0:
        atr = current * max(0.0001, _f((volatility or {}).get("atr_pct")) / 100.0)
    if current <= 0 or atr <= 0:
        return {"success": False, "reason": "FINAL_RECOVERY_MISSING_PRICE_OR_ATR"}

    direction = "long" if str(decision).upper() == "LONG" else "short"
    floor = max(1.0, _f(levels.get("minimum_viable_rr"), 1.8))
    ceiling = max(floor, _f(levels.get("maximum_technical_rr"), 4.5))
    setup_family = str(
        (((structure or {}).get("_contingency_playbook") or {}).get("setup_family"))
        or levels.get("setup_family")
        or ""
    ).upper()

    obs = {}
    if isinstance(structure, dict):
        obs = structure.get(_BRIDGE_KEY) or {}
    execution_context = {}
    if isinstance(obs, dict):
        execution_context = (
            obs.get("execution_context")
            or obs.get("market_maker_context")
            or {}
        )
    if not isinstance(execution_context, dict):
        execution_context = {}

    def quality_filter(candidate: Mapping[str, Any]) -> bool:
        entry = _f(candidate.get("entry"))
        sl = _f(candidate.get("stop_loss"))
        tp = _f(candidate.get("take_profit"))
        rr = _f(candidate.get("risk_reward"))
        if min(entry, sl, tp) <= 0:
            return False
        if not (floor <= rr <= ceiling):
            return False
        if direction == "long" and not (sl < entry < tp and entry <= current):
            return False
        if direction == "short" and not (tp < entry < sl and entry >= current):
            return False
        if _f(candidate.get("geometry_quality")) < 62.0:
            return False
        if _f(candidate.get("entry_quality")) < 55.0:
            return False
        if _f(candidate.get("sl_quality")) < 60.0:
            return False
        if _f(candidate.get("tp_quality")) < 60.0:
            return False
        guard = evaluate_sl_reaction_conflict(
            structure=dict(structure or {}),
            direction=direction,
            entry=entry,
            stop_loss=sl,
            atr=atr,
        ) or {}
        return not bool(guard.get("conflict"))

    return recover_execution_geometry_from_structure(
        direction=direction,
        current_price=current,
        atr=atr,
        structure=dict(structure or {}),
        trend=dict(trend or {}),
        momentum=dict(momentum or {}),
        volatility=dict(volatility or {}),
        setup_family=setup_family,
        liquidation=liquidation,
        market_type=_market_type(instance),
        symbol=symbol,
        timeframe=timeframe,
        execution_context=execution_context,
        entry_hint=_f(levels.get("entry")),
        rr_floor=floor,
        rr_ceiling=ceiling,
        preferred_rr_min=max(floor, min(2.0, ceiling)),
        preferred_rr_max=min(ceiling, max(floor, 3.2)),
        leverage_hint=max(1.0, _f(levels.get("leverage"), 1.0)),
        candidate_filter=quality_filter,
    ) or {}


def _apply_recovered_base_geometry(
    instance: Any,
    levels: Mapping[str, Any],
    recovery: Mapping[str, Any],
    *,
    structure: Mapping[str, Any],
    volatility: Mapping[str, Any],
    symbol: str,
) -> Dict[str, Any]:
    """Adopt recovery only as the base geometry; downstream gates remain intact."""
    out = dict(levels or {})
    entry = _f(recovery.get("entry"))
    sl = _f(recovery.get("stop_loss"))
    tp = _f(recovery.get("take_profit"))
    rr = _f(recovery.get("risk_reward"))
    current = _f((structure or {}).get("current_price"))
    atr = max(_f((volatility or {}).get("atr")), 1e-12)

    erow = dict(recovery.get("entry_committee") or {})
    srow = dict(recovery.get("sl_committee") or {})
    trow = dict(recovery.get("tp_committee") or {})

    out.update({
        "entry": instance._round_price(entry, symbol),
        "stop_loss": instance._round_price(sl, symbol),
        "take_profit": instance._round_price(tp, symbol),
        "risk_reward": round(rr, 2),
        # Use committee role quality on the same 0..100 scale consumed by
        # FuturesExecutionSafety.  This is not a calibrated probability.
        "entry_score": round(_f(recovery.get("entry_quality")), 1),
        "entry_smc_raw_score": round(_f(recovery.get("entry_quality")), 2),
        "sl_reliability": round(_f(recovery.get("sl_quality")) / 100.0, 4),
        "tp_quality_score": round(_f(recovery.get("tp_quality")), 1),
        "entry_source": "Recuperación estructural final · " + str(erow.get("source") or erow.get("family") or "zona técnica"),
        "sl_source": "Invalidación estructural final · " + str(srow.get("source") or srow.get("family") or "nivel técnico"),
        "tp_source": "Objetivo estructural final · " + str(trow.get("source") or trow.get("family") or "objetivo técnico"),
        "rejected_reason": None,
        "is_rejected": False,
        "is_executable": True,
        "publication_status": "EXECUTABLE_SIGNAL",
        "final_geometry_recovery_attempted": True,
        "final_geometry_recovery_applied": True,
        "final_geometry_recovery_version": VERSION,
        "final_geometry_quality": recovery.get("geometry_quality"),
        "final_geometry_entry_quality": recovery.get("entry_quality"),
        "final_geometry_sl_quality": recovery.get("sl_quality"),
        "final_geometry_tp_quality": recovery.get("tp_quality"),
        "final_geometry_tested_combinations": recovery.get("tested_combinations"),
        "final_geometry_sl_reaction_rejections": recovery.get("sl_reaction_rejections"),
        "final_geometry_authority": "BASE_GEOMETRY_ONLY_DOWNSTREAM_SAFETY_UNCHANGED",
    })
    if current > 0 and atr > 0:
        out["entry_distance_atr"] = round(abs(current - entry) / atr, 4)
        out["entry_distance_pct"] = round(abs(current - entry) / current * 100.0, 4)
    # Base-level status only. FuturesAnalysis will still execute its timing,
    # Entry Reaction, Safety, leverage and publication logic after super().
    return out


def _install_base_final_recovery(futures_cls: Any) -> bool:
    """Patch the direct shared base method, so recovery occurs BEFORE Futures gates."""
    mro = getattr(futures_cls, "__mro__", ())
    if len(mro) < 2:
        return False
    base_cls = mro[1]
    method = getattr(base_cls, "calculate_entry_levels", None)
    if not callable(method):
        return False
    if getattr(method, "_st175105_final_geometry_recovery", False):
        return True

    original = method

    @wraps(original)
    def _base_wrapped(
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
        result = original(
            self,
            decision,
            trend,
            momentum,
            volatility,
            structure,
            symbol,
            timeframe,
            liquidation,
            execution_observations=execution_observations,
        )
        if str(decision or "").upper() not in {"LONG", "SHORT"}:
            return result
        if not isinstance(result, dict):
            return result

        reason = str(result.get("rejected_reason") or "")
        recoverable = (
            reason.startswith("R/R desfavorable")
            or reason.startswith("SL no defendible")
        )
        if not recoverable:
            return result

        original_copy = dict(result)
        original_copy["final_geometry_recovery_attempted"] = True
        original_copy["final_geometry_recovery_applied"] = False
        original_copy["final_geometry_recovery_version"] = VERSION
        original_copy["final_geometry_original_rejection"] = reason[:220]

        try:
            recovery = _structural_recovery_candidate(
                self,
                decision=str(decision).upper(),
                trend=dict(trend or {}),
                momentum=dict(momentum or {}),
                volatility=dict(volatility or {}),
                structure=dict(structure or {}),
                symbol=str(symbol or ""),
                timeframe=str(timeframe or ""),
                liquidation=liquidation,
                levels=original_copy,
            )
        except Exception as exc:
            original_copy["final_geometry_recovery_reason"] = (
                f"RECOVERY_ERROR:{type(exc).__name__}"
            )
            return original_copy

        if not recovery.get("success"):
            original_copy["final_geometry_recovery_reason"] = str(
                recovery.get("reason") or "NO_COHERENT_RECOVERY"
            )[:220]
            original_copy["final_geometry_tested_combinations"] = recovery.get(
                "tested_combinations"
            )
            return original_copy

        recovered = _apply_recovered_base_geometry(
            self,
            original_copy,
            recovery,
            structure=dict(structure or {}),
            volatility=dict(volatility or {}),
            symbol=str(symbol or ""),
        )
        recovered["final_geometry_original_rejection"] = reason[:220]
        return recovered

    _base_wrapped._st175105_final_geometry_recovery = True
    _base_wrapped._st175105_original = original
    base_cls.calculate_entry_levels = _base_wrapped
    return True


def _install_strategy_scope_and_shadow() -> bool:
    try:
        from strategy_quality_extension_175105 import install_strategy_quality_extension_175105
        state = install_strategy_quality_extension_175105()
        return bool(state.get("installed"))
    except Exception:
        return False


def _install_macro_backoff() -> bool:
    try:
        from macro_backoff_175105 import install_macro_backoff_175105
        state = install_macro_backoff_175105()
        return bool(state.get("installed"))
    except Exception:
        return False


def install_futures_execution_abi_175104(futures_module) -> Dict[str, Any]:
    """Compatibility entry-point kept because app.py 17.5.10.4 imports it."""
    cls = getattr(futures_module, "FuturesAnalysis", None)
    if cls is None:
        raise AttributeError("FuturesAnalysis not found")

    with _LOCK:
        method = getattr(cls, "calculate_entry_levels", None)
        if not callable(method):
            raise AttributeError("FuturesAnalysis.calculate_entry_levels not callable")

        if not getattr(method, "_st175104_execution_abi", False):
            try:
                params = inspect.signature(method).parameters
            except Exception:
                params = {}
            if "execution_observations" in params:
                _STATE.update({"native": True})
            else:
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
                _wrapped._st175105_execution_quality = True
                _wrapped._st175104_original = original
                cls.calculate_entry_levels = _wrapped
                _STATE.update({"native": False})

        _STATE["base_recovery_installed"] = _install_base_final_recovery(cls)
        _STATE["strategy_scope_installed"] = _install_strategy_scope_and_shadow()
        _STATE["macro_backoff_installed"] = _install_macro_backoff()
        _STATE["installed"] = True
        _STATE["version"] = VERSION
        return dict(_STATE)
