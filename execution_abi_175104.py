"""Commit 17.5.10.6 — gate-aware recovery + Multi-Asset pre-execution routing.

Base expected: d328d42c6211ad530d85fef519bc63f2ae64a862 (17.5.10.5)

Why this module exists
----------------------
17.5.10.4 fixed the Futures/Multi-Asset ABI mismatch without changing trading
thresholds.  17.5.10.6 keeps that fix and hardens the bounded second-chance
execution pass for an already-valid LONG/SHORT thesis when the shared Entry/SL/TP
engine ends specifically in:

- R/R below the existing technical floor; or
- an SL that still collides with an observed technical reaction level.

This pass cannot create direction, cannot lower the R/R floor, cannot invent
ATR/RR targets, cannot bypass Safety and cannot publish by itself.  It only
returns a better *base geometry* to FuturesAnalysis; the existing Futures
timing, reaction, Safety, leverage and Publication gates still run afterwards.

17.5.10.6 also routes Multi-Asset context BEFORE execution geometry and makes
recovery gate-aware using only already-loaded data. No network, DB, LLM, thread
or polling work is added here.
"""
from __future__ import annotations

from functools import wraps
import inspect
import threading
from typing import Any, Dict, Mapping

VERSION = "17.5.10.6_GATE_AWARE_RECOVERY_MULTI_PREEXEC_V1"
_BASELINE_HEAD = "d328d42c6211ad530d85fef519bc63f2ae64a862"
_LOCK = threading.RLock()
_STATE: Dict[str, Any] = {
    "installed": False,
    "native": False,
    "base_recovery_installed": False,
    "strategy_scope_installed": False,
    "macro_backoff_installed": False,
    "contextual_setup_guard_installed": False,
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



def _bool_observed(structure: Mapping[str, Any], *keys: str) -> bool:
    """Read already-computed structural facts without fetching anything."""
    s = dict(structure or {})
    nested = []
    for name in ("smc", "smart_money", "structure", "liquidity"):
        value = s.get(name)
        if isinstance(value, Mapping):
            nested.append(value)
    for key in keys:
        if bool(s.get(key)):
            return True
        for row in nested:
            if bool(row.get(key)):
                return True
    return False


def _multiasset_pre_execution_route(
    instance: Any,
    *,
    decision: str,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    volatility: Mapping[str, Any],
    structure: Mapping[str, Any],
    symbol: str,
    timeframe: str,
) -> Dict[str, Any]:
    """Select the Multi-Asset execution procedure before Entry/SL/TP.

    This is deliberately NOT a directional router. LONG/SHORT already exists.
    It reuses the existing Multi-Asset Strategy Bank/context functions with the
    already-loaded analysis dictionaries, then maps the selected public family
    onto the execution engine's existing family vocabulary.
    """
    if _market_type(instance) != "multiasset":
        return {}
    if str(decision or "").upper() not in {"LONG", "SHORT"}:
        return {}
    try:
        import multiasset_system as ma
        meta = dict((getattr(ma, "MULTIASSET_SYMBOLS", {}) or {}).get(str(symbol or "")) or {})
        if not meta:
            return {}
        atr_pct = _f((volatility or {}).get("atr_pct"), 0.0)
        raw_patterns = (structure or {}).get("patterns") if isinstance(structure, Mapping) else {}
        fake_result = {
            "trend": dict(trend or {}),
            "momentum": dict(momentum or {}),
            "structure": dict(structure or {}),
            "patterns": dict(raw_patterns) if isinstance(raw_patterns, Mapping) else {},
            "levels": {"atr_pct": atr_pct},
            "atr_pct": atr_pct,
            "message": "",
        }
        strategy = ma._strategy_context(meta, str(timeframe or ""), fake_result) or {}
        families = list(strategy.get("families") or [])
        preferred = list(strategy.get("preferred_for_context") or [])
        route = ma._route_strategy_family(fake_result, strategy, {}) or {}
        selected = str(route.get("selected_family") or "").upper()

        # Do not let a tie in the descriptive router manufacture a reversal
        # procedure. Sweep-reversal is selected only when both observed sweep
        # and structure-shift evidence already exist.
        sweep = _bool_observed(structure, "liquidity_sweep", "sweep", "stop_hunt", "has_liquidity_sweep", "has_stop_hunt")
        mss = _bool_observed(structure, "mss", "bos", "mss_bos", "has_mss", "has_bos")
        displacement = _bool_observed(structure, "displacement", "has_displacement")
        regime = str(strategy.get("regime") or "MIXED").upper()
        vol_regime = str(strategy.get("volatility_regime") or "NORMAL").upper()
        allowed = {str(x or "").upper() for x in families}

        if sweep and mss and "SWEEP_MSS_POI" in allowed:
            selected = "SWEEP_MSS_POI"
        elif regime == "TRENDING" and "TREND_PULLBACK" in allowed:
            selected = "TREND_PULLBACK"
        elif vol_regime == "HIGH" and displacement and "BREAKOUT_RETEST" in allowed:
            selected = "BREAKOUT_RETEST"
        elif regime == "RANGING" and "MEAN_REVERSION_SELECTIVE" in allowed:
            selected = "MEAN_REVERSION_SELECTIVE"
        elif "COMPRESSION_EXPANSION" in preferred and "COMPRESSION_EXPANSION" in allowed:
            selected = "COMPRESSION_EXPANSION"
        elif selected == "SWEEP_MSS_POI" and not (sweep and mss):
            # Fall back to a non-reversal family already declared by the bank.
            selected = next((x for x in preferred if str(x).upper() in {
                "TREND_PULLBACK", "BREAKOUT_RETEST", "COMPRESSION_EXPANSION",
                "MEAN_REVERSION_SELECTIVE", "VWAP_SESSION_PULLBACK",
            }), selected)

        mapping = {
            "SWEEP_MSS_POI": "SWEEP_REVERSAL",
            "VWAP_SESSION_PULLBACK": "TREND_PULLBACK",
            "MEAN_REVERSION_SELECTIVE": "MEAN_REVERSION",
            "VOLATILITY_RETEST": "BREAKOUT_RETEST",
            "POST_EVENT_CONFIRMATION": "BREAKOUT_RETEST",
            "POST_MACRO_CONFIRMATION": "TREND_PULLBACK",
            "MACRO_TREND_CONFIRMATION": "TREND_PULLBACK",
            "RATES_USD_CONFIRMATION": "TREND_PULLBACK",
            "ASIA_SESSION_RETEST": "BREAKOUT_RETEST",
        }
        engine_family = mapping.get(str(selected).upper(), str(selected).upper())
        if not engine_family:
            return {}
        return {
            "version": VERSION,
            "selected_family": str(selected).upper(),
            "engine_family": engine_family,
            "regime": regime,
            "volatility_regime": vol_regime,
            "asset_class": meta.get("asset_class"),
            "creates_direction": False,
            "network_calls": 0,
            "db_writes": 0,
            "llm_calls": 0,
        }
    except Exception as exc:
        return {"error": type(exc).__name__, "creates_direction": False}


def _recovered_entry_metadata(
    instance: Any,
    *,
    decision: str,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    volatility: Mapping[str, Any],
    structure: Mapping[str, Any],
    symbol: str,
    timeframe: str,
    levels: Mapping[str, Any],
    recovery: Mapping[str, Any],
) -> Dict[str, Any]:
    """Rebuild entry metadata for the NEW recovered price.

    17.5.10.5 changed the price but could leave timing/reaction metadata from
    the rejected baseline Entry.  That makes the next gates evaluate two
    different geometries. This helper keeps one coherent geometry end-to-end.
    """
    entry = _f(recovery.get("entry"))
    current = _f((structure or {}).get("current_price")) or _f(levels.get("current_price"))
    atr = _f((volatility or {}).get("atr"))
    if atr <= 0 and current > 0:
        atr = current * max(0.0001, _f((volatility or {}).get("atr_pct")) / 100.0)
    d_atr = abs(current - entry) / max(atr, 1e-12) if current > 0 and entry > 0 else 999.0
    direction = "long" if str(decision or "").upper() == "LONG" else "short"
    erow = dict(recovery.get("entry_committee") or {})
    srow = dict(recovery.get("sl_committee") or {})
    escores = dict(erow.get("specialist_scores") or {})
    setup_family = str(
        (((structure or {}).get("_contingency_playbook") or {}).get("setup_family"))
        or levels.get("setup_family")
        or "UNSPECIFIED"
    ).upper()

    timing_mode = str(levels.get("entry_timing_mode") or "STRUCTURAL_PULLBACK").upper()
    try:
        from execution_geometry_committee import build_profile, entry_candidate_adjustment
        regime = str((structure or {}).get("_adaptive_market_regime") or (structure or {}).get("market_regime") or "RANGING")
        try:
            detector = getattr(instance, "detect_market_regime", None)
            if callable(detector):
                detected = detector(dict(trend or {}), dict(momentum or {}), dict(volatility or {}), dict(structure or {})) or {}
                regime = str(detected.get("regime") or regime)
        except Exception:
            pass
        profile = build_profile(
            market_type="futures", symbol=symbol, timeframe=timeframe,
            direction=direction, setup_family=setup_family, market_regime=regime,
            trend=dict(trend or {}), momentum=dict(momentum or {}), volatility=dict(volatility or {}),
        ) or {}
        timing_mode = str(entry_candidate_adjustment(
            profile,
            candidate_type=erow.get("family") or "structure",
            distance_atr=d_atr,
            market_location=levels.get("entry_market_location"),
            directional_extension=bool(levels.get("entry_directional_extension")),
            correct_side_near_reaction=False,
            independent_family_count=int(_f(levels.get("entry_independent_confluence_families"), 1)),
        ).get("timing_mode") or timing_mode).upper()
    except Exception:
        pass

    smc = dict((structure or {}).get("smc") or (structure or {}).get("smart_money") or {})
    sweep = _bool_observed(structure, "liquidity_sweep", "sweep", "stop_hunt", "has_liquidity_sweep", "has_stop_hunt")
    mss = _bool_observed(structure, "mss", "bos", "mss_bos", "has_mss", "has_bos")
    displacement = _bool_observed(structure, "displacement", "has_displacement")
    source = str(erow.get("source") or erow.get("family") or "zona técnica")
    liquidity = (
        "LIQUID" in source.upper()
        or bool(smc.get("liquidity_pool_near"))
        or _bool_observed(structure, "liquidity_pool_near")
    )
    entry_quality = _f(recovery.get("entry_quality"))
    sl_quality = _f(recovery.get("sl_quality"))
    return {
        "entry_distance_atr": round(d_atr, 4),
        "entry_distance_pct": round(abs(current-entry) / max(current, 1e-12) * 100.0, 4) if current > 0 else None,
        "entry_timing_mode": timing_mode,
        "entry_reachability_score": round(_f(escores.get("reachability"), entry_quality), 2),
        "entry_defensibility_score": round(min(entry_quality or 100.0, sl_quality or 100.0), 2),
        "entry_smc_raw_score": round(_f(escores.get("smc"), entry_quality), 2),
        "entry_liquidity_pool_near": bool(liquidity),
        "entry_sweep_confirmed": bool(sweep),
        "entry_mss_bos_confirmed": bool(mss),
        "entry_displacement_confirmed": bool(displacement),
        "entry_source": "Recuperación estructural final · " + source,
        "setup_family": setup_family,
        "recovery_metadata_rebuilt": True,
    }


def _candidate_downstream_preflight(
    instance: Any,
    *,
    decision: str,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    volatility: Mapping[str, Any],
    structure: Mapping[str, Any],
    symbol: str,
    timeframe: str,
    levels: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[bool, str, Dict[str, Any]]:
    """Local-only preflight for mandatory gates immediately after recovery."""
    meta = _recovered_entry_metadata(
        instance, decision=decision, trend=trend, momentum=momentum,
        volatility=volatility, structure=structure, symbol=symbol,
        timeframe=timeframe, levels=levels, recovery=candidate,
    )
    proposal = dict(levels or {})
    proposal.update(meta)
    proposal.update({
        "entry": _f(candidate.get("entry")),
        "stop_loss": _f(candidate.get("stop_loss")),
        "take_profit": _f(candidate.get("take_profit")),
        "risk_reward": _f(candidate.get("risk_reward")),
        "entry_score": _f(candidate.get("entry_quality")),
        "sl_reliability": _f(candidate.get("sl_quality")) / 100.0,
        "tp_quality_score": _f(candidate.get("tp_quality")),
    })

    gate = getattr(instance, "_futures_entry_timing_gate", None)
    if callable(gate):
        try:
            timing = gate(
                str(decision).upper(), dict(trend or {}), dict(momentum or {}),
                dict(volatility or {}), dict(structure or {}), proposal,
            ) or {}
            if timing.get("status") == "TIMING_DIAGNOSTIC_ERROR" or timing.get("passed") is not True:
                return False, "ENTRY_TIMING", proposal
        except Exception:
            return False, "ENTRY_TIMING_ERROR", proposal

    try:
        from entry_reaction_engine import evaluate_entry_reaction
        reaction = evaluate_entry_reaction(
            proposal, structure=dict(structure or {}), volatility=dict(volatility or {}),
            timeframe=timeframe, market_type="futures",
        ) or {}
        if reaction.get("passed") is not True:
            return False, "ENTRY_REACTION", proposal
    except Exception:
        return False, "ENTRY_REACTION_ERROR", proposal

    try:
        from operational_intelligence import execution_setup_guard
        guard = execution_setup_guard(
            action=str(decision).upper(), levels=proposal,
            setup_family=meta.get("setup_family"), market="FUTURES", timeframe=timeframe,
        ) or {}
        if guard.get("applied") and str(guard.get("status") or "").upper() == "SETUP_NOT_EXECUTABLE":
            return False, "SETUP_GUARD", proposal
    except Exception:
        return False, "SETUP_GUARD_ERROR", proposal

    return True, "OK", proposal


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

    preflight_rejections: Dict[str, int] = {}

    def _reject(code: str) -> bool:
        key = str(code or "OTHER").upper()
        preflight_rejections[key] = int(preflight_rejections.get(key) or 0) + 1
        return False

    def quality_filter(candidate: Mapping[str, Any]) -> bool:
        entry = _f(candidate.get("entry"))
        sl = _f(candidate.get("stop_loss"))
        tp = _f(candidate.get("take_profit"))
        rr = _f(candidate.get("risk_reward"))
        if min(entry, sl, tp) <= 0:
            return _reject("INVALID_PRICE")
        if not (floor <= rr <= ceiling):
            return _reject("RR")
        if direction == "long" and not (sl < entry < tp and entry <= current):
            return _reject("GEOMETRY_SIDE")
        if direction == "short" and not (tp < entry < sl and entry >= current):
            return _reject("GEOMETRY_SIDE")
        if _f(candidate.get("geometry_quality")) < 62.0:
            return _reject("GEOMETRY_QUALITY")
        if _f(candidate.get("entry_quality")) < 55.0:
            return _reject("ENTRY_QUALITY")
        if _f(candidate.get("sl_quality")) < 60.0:
            return _reject("SL_QUALITY")
        if _f(candidate.get("tp_quality")) < 60.0:
            return _reject("TP_QUALITY")
        guard = evaluate_sl_reaction_conflict(
            structure=dict(structure or {}),
            direction=direction,
            entry=entry,
            stop_loss=sl,
            atr=atr,
        ) or {}
        if bool(guard.get("conflict")):
            return _reject("SL_REACTION")
        passed, code, _proposal = _candidate_downstream_preflight(
            instance, decision=decision, trend=trend, momentum=momentum,
            volatility=volatility, structure=structure, symbol=symbol,
            timeframe=timeframe, levels=levels, candidate=candidate,
        )
        if not passed:
            return _reject(code)
        return True

    recovery = recover_execution_geometry_from_structure(
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
    if isinstance(recovery, dict):
        recovery["downstream_preflight_rejections"] = dict(preflight_rejections)
        recovery["downstream_preflight_version"] = VERSION
    return recovery


def _apply_recovered_base_geometry(
    instance: Any,
    levels: Mapping[str, Any],
    recovery: Mapping[str, Any],
    *,
    decision: str,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    structure: Mapping[str, Any],
    volatility: Mapping[str, Any],
    symbol: str,
    timeframe: str,
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
    refreshed_entry = _recovered_entry_metadata(
        instance, decision=decision, trend=trend, momentum=momentum,
        volatility=volatility, structure=structure, symbol=symbol,
        timeframe=timeframe, levels=out, recovery=recovery,
    )

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
        "entry_source": refreshed_entry.get("entry_source") or ("Recuperación estructural final · " + str(erow.get("source") or erow.get("family") or "zona técnica")),
        "sl_source": "Invalidación estructural final · " + str(srow.get("source") or srow.get("family") or "nivel técnico"),
        "tp_source": "Objetivo estructural final · " + str(trow.get("source") or trow.get("family") or "objetivo técnico"),
        "rejected_reason": None,
        "is_rejected": False,
        "is_executable": True,
        "publication_status": "RECOVERED_BASE_PENDING_GATES",
        "final_geometry_recovery_attempted": True,
        "final_geometry_recovery_applied": True,
        "final_geometry_recovery_version": VERSION,
        "final_geometry_quality": recovery.get("geometry_quality"),
        "final_geometry_entry_quality": recovery.get("entry_quality"),
        "final_geometry_sl_quality": recovery.get("sl_quality"),
        "final_geometry_tp_quality": recovery.get("tp_quality"),
        "final_geometry_tested_combinations": recovery.get("tested_combinations"),
        "final_geometry_sl_reaction_rejections": recovery.get("sl_reaction_rejections"),
        "final_geometry_downstream_preflight_rejections": recovery.get("downstream_preflight_rejections"),
        "final_geometry_authority": "BASE_GEOMETRY_ONLY_DOWNSTREAM_SAFETY_UNCHANGED",
    })
    out.update({k: v for k, v in refreshed_entry.items() if v is not None})
    # Base-level status only. FuturesAnalysis will still execute its timing,
    # Entry Reaction, Safety, leverage and publication logic after super().
    return out



def _install_contextual_execution_setup_guard() -> bool:
    """Make the legacy setup guard consume the cell's already-computed RR floor.

    The original guard used a global 1.50 Futures floor even when the execution
    geometry profile had already selected 1.35/1.40/1.45 (or 1.55) for the
    specific asset/TF context.  This wrapper removes only that duplicated RR
    contradiction; every geometry/family/Entry-quality rule remains original.
    """
    try:
        import operational_intelligence as oi
        original = getattr(oi, "execution_setup_guard", None)
        if not callable(original):
            return False
        if getattr(original, "_st175106_contextual_rr_floor", False):
            return True

        @wraps(original)
        def _guard_wrapped(*, action, levels, setup_family, market, timeframe):
            lv = dict(levels or {})
            effective_setup_family = lv.get("_execution_setup_family_175106") or setup_family
            # The base Entry engine emits Spanish source labels (Soporte /
            # Resistencia), while the legacy BREAKOUT_RETEST guard only
            # recognized the English tokens support / resistance. Normalize
            # terminology only; do not add new structural evidence.
            source_l = str(lv.get("entry_source") or "").lower()
            aliases = []
            if "soporte" in source_l and "support" not in source_l:
                aliases.append("support")
            if "resistencia" in source_l and "resistance" not in source_l:
                aliases.append("resistance")
            if aliases:
                lv["entry_source"] = str(lv.get("entry_source") or "") + " [" + "/".join(aliases) + "]"
            result = original(
                action=action, levels=lv, setup_family=effective_setup_family,
                market=market, timeframe=timeframe,
            ) or {}
            if str(market or "").upper() != "FUTURES":
                return result
            rr = _f(lv.get("risk_reward"), 0.0)
            raw_floor = lv.get("minimum_viable_rr")
            floor = max(1.0, _f(raw_floor, 1.50) if raw_floor is not None else 1.50)
            if rr <= 0:
                return result

            rr_prefix = "la relación riesgo/beneficio disponible"
            reasons = [str(x) for x in (result.get("reasons") or []) if x]
            non_rr = [x for x in reasons if not x.lower().startswith(rr_prefix)]

            if rr < floor:
                contextual_reason = (
                    f"la relación riesgo/beneficio disponible es 1:{rr:.2f} "
                    f"< piso técnico 1:{floor:.2f}"
                )
                final_reasons = non_rr + [contextual_reason]
                out = dict(result)
                original_action = str(result.get("original_action") or result.get("action") or action).upper()
                out.update({
                    "applied": True,
                    "action": "PRECAUCION",
                    "status": "SETUP_NOT_EXECUTABLE",
                    "reasons": final_reasons,
                    "original_action": original_action,
                    "rr_floor": round(floor, 3),
                    "rr_floor_source": "levels.minimum_viable_rr",
                    "rr_guard_version": VERSION,
                })
                return out

            # rr satisfies the contextual floor. Remove only the obsolete
            # generic-1.50 reason; all other original reasons stay authoritative.
            if non_rr:
                out = dict(result)
                out.update({
                    "applied": True,
                    "status": "SETUP_NOT_EXECUTABLE",
                    "reasons": non_rr,
                    "rr_floor": round(floor, 3),
                    "rr_floor_source": "levels.minimum_viable_rr",
                    "rr_guard_version": VERSION,
                })
                return out

            if len(non_rr) != len(reasons) or result.get("applied"):
                out = dict(result)
                original_action = str(result.get("original_action") or result.get("action") or action).upper()
                out.update({
                    "applied": False,
                    "action": original_action,
                    "status": "SETUP_EXECUTABLE",
                    "reasons": [],
                    "rr_floor": round(floor, 3),
                    "rr_floor_source": "levels.minimum_viable_rr",
                    "rr_guard_version": VERSION,
                })
                out.pop("original_action", None)
                return out
            return result

        _guard_wrapped._st175106_contextual_rr_floor = True
        _guard_wrapped._st175106_original = original
        oi.execution_setup_guard = _guard_wrapped
        return True
    except Exception:
        return False


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
            decision=str(decision).upper(),
            trend=dict(trend or {}),
            momentum=dict(momentum or {}),
            structure=dict(structure or {}),
            volatility=dict(volatility or {}),
            symbol=str(symbol or ""),
            timeframe=str(timeframe or ""),
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
                    had_playbook = False
                    previous_playbook = None
                    route: Dict[str, Any] = {}
                    if isinstance(structure, dict):
                        had_previous = _BRIDGE_KEY in structure
                        previous = structure.get(_BRIDGE_KEY)
                        if isinstance(execution_observations, dict):
                            structure[_BRIDGE_KEY] = execution_observations

                        # 17.5.10.6: Multi-Asset Strategy Bank must influence
                        # execution geometry BEFORE Entry/SL/TP, not merely
                        # describe the result in the post-market hook.
                        route = _multiasset_pre_execution_route(
                            self, decision=str(decision or "").upper(),
                            trend=dict(trend or {}), momentum=dict(momentum or {}),
                            volatility=dict(volatility or {}), structure=structure,
                            symbol=str(symbol or ""), timeframe=str(timeframe or ""),
                        )
                        if route.get("engine_family"):
                            had_playbook = "_contingency_playbook" in structure
                            previous_playbook = structure.get("_contingency_playbook")
                            playbook = dict(previous_playbook or {})
                            playbook["active"] = bool(playbook.get("active", True))
                            playbook["setup_family"] = route["engine_family"]
                            playbook["multiasset_pre_execution_route_175106"] = route
                            structure["_contingency_playbook"] = playbook
                    try:
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
                        )
                        if isinstance(result, dict) and route.get("engine_family"):
                            result["_execution_setup_family_175106"] = route["engine_family"]
                            result["_multiasset_pre_execution_route_applied_175106"] = True
                        return result
                    finally:
                        if isinstance(structure, dict):
                            if had_previous:
                                structure[_BRIDGE_KEY] = previous
                            else:
                                structure.pop(_BRIDGE_KEY, None)
                            if had_playbook:
                                structure["_contingency_playbook"] = previous_playbook
                            else:
                                structure.pop("_contingency_playbook", None)

                _wrapped._st175104_execution_abi = True
                _wrapped._st175105_execution_quality = True
                _wrapped._st175104_original = original
                cls.calculate_entry_levels = _wrapped
                _STATE.update({"native": False})

        _STATE["contextual_setup_guard_installed"] = _install_contextual_execution_setup_guard()
        _STATE["base_recovery_installed"] = _install_base_final_recovery(cls)
        _STATE["strategy_scope_installed"] = _install_strategy_scope_and_shadow()
        _STATE["macro_backoff_installed"] = _install_macro_backoff()
        _STATE["installed"] = True
        _STATE["version"] = VERSION
        return dict(_STATE)
