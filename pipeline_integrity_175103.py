"""Commit 33.3 — Core candidate router consolidation.

This is a core module, not a runtime monkeypatch.  It keeps the current
17.5.10.4 router as the baseline authority and adds one setup-aware recovery
pass only when that router did not produce a directional candidate.

Contracts preserved downstream:
- Entry committee
- SL committee / SL_REACTION_CONFLICT
- TP committee with realistic structural targets
- Commit31 specialised Safety
- hard risk / RR economics
- OOS / publication authority

The purpose is to reduce PRE-candidate over-selection, not to relax the final
execution/publication standard.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, Iterable, List
from datetime import datetime, timezone

import pipeline_integrity_175102 as _base

VERSION = "33.3_CORE_CANDIDATE_ROUTER_V1"
PIPELINE_GENERATION = "33.3"
RELEASED_AT_UTC = "2026-10-08T03:00:00+00:00"

_DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}

__all__ = [
    "VERSION", "PIPELINE_GENERATION", "RELEASED_AT_UTC",
    "reconcile_operational_candidate", "profitability_hard_block_authority",
    "stamp_pipeline_generation", "particular_setup_diagnostic",
    "_multiasset_strategy_from_live_layers",
]


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _action(direction: str, market: str) -> str:
    if direction == "BULLISH":
        return "LONG" if market == "FUTURES" else "COMPRA_SPOT"
    if direction == "BEARISH":
        return "SHORT" if market == "FUTURES" else "VENTA_SPOT"
    return "NO_OPERAR"


def _graded_contract(
    *,
    name: str,
    preferred_family: str,
    ev: Mapping[str, Any],
    anchors: Iterable[str],
    confirmations: Iterable[str],
    min_confirmations: int,
    strict_mtf: bool = False,
    require_any: Iterable[str] = (),
) -> Dict[str, Any]:
    """Setup-aware pre-candidate contract.

    Important anti-overfit rule: indicators remain grouped into independent
    roles.  Risk class does not change the technical evidence required for a
    hypothesis to EXIST.  Risk class is handled later by tempo, Safety, sizing
    and hard-risk controls.
    """
    anchors = list(anchors)
    confirmations = list(confirmations)
    require_any = list(require_any)

    anchor_hits = [x for x in anchors if bool(ev.get(x))]
    confirmation_hits = [x for x in confirmations if bool(ev.get(x))]
    any_hits = [x for x in require_any if bool(ev.get(x))]

    mtf_conflict = bool(ev.get("mtf_conflict"))
    mtf_opposite = bool(ev.get("mtf_opposite"))
    mtf_penalty = 1 if (mtf_conflict or mtf_opposite) and not strict_mtf else 0

    anchors_ok = len(anchor_hits) == len(anchors)
    any_ok = (not require_any) or bool(any_hits)
    mtf_ok = not (strict_mtf and (mtf_conflict or mtf_opposite))
    required_conf = int(min_confirmations) + int(mtf_penalty)
    confirms_ok = len(confirmation_hits) >= required_conf

    passed = bool(anchors_ok and any_ok and mtf_ok and confirms_ok)

    # Broad role score; no symbol/TF optimisation and no risk-class multiplier.
    quality = 66.0
    quality += 7.0 * len(anchor_hits)
    quality += 4.0 * len(any_hits)
    quality += 3.0 * len(confirmation_hits)
    if ev.get("mtf"):
        quality += 3.0
    if _f(ev.get("volume_ratio"), 1.0) >= 1.2:
        quality += 2.0
    if mtf_conflict or mtf_opposite:
        quality -= 3.0
    quality = max(0.0, min(94.0, quality))

    return {
        "setup": name,
        "preferred_family": preferred_family,
        "passed": passed,
        "quality": round(quality, 2),
        "core_required": anchors,
        "core_hits": anchor_hits,
        "support_pool": confirmations,
        "support_hits": confirmation_hits,
        "require_any": require_any,
        "require_any_hits": any_hits,
        "required_confirmation_count": required_conf,
        "mtf_policy": "STRICT" if strict_mtf else "CONTEXTUAL_EXTRA_CONFIRMATION",
        "anti_overfit": "ROLE_BASED_NO_SYMBOL_TF_OPTIMIZATION",
    }


def _evaluate_side(layers: Mapping[str, Any], operational: Mapping[str, Any], direction: str) -> Dict[str, Any]:
    ev = _base._live_evidence(layers, operational, direction)

    contracts = [
        # Early impulse: DMI impulse is the anchor.  MTF may lag; if it is
        # opposite/conflicted one extra independent confirmation is required.
        _graded_contract(
            name="DIRECTIONAL_IMPULSE_CONTINUATION",
            preferred_family="BREAKOUT_RETEST",
            ev=ev,
            anchors=("dmi_impulse",),
            require_any=("direction_anchor", "momentum"),
            confirmations=("momentum", "structure", "volume", "displacement", "breakout", "mtf"),
            min_confirmations=2,
            strict_mtf=False,
        ),
        # Reversal: sweep is mandatory; MSS OR structure must exist.  MTF is
        # context, not an automatic veto during the first reversal leg.
        _graded_contract(
            name="SWEEP_REVERSAL",
            preferred_family="SWEEP_REVERSAL",
            ev=ev,
            anchors=("sweep",),
            require_any=("mss", "structure"),
            confirmations=("mss", "structure", "momentum", "poi", "volume", "displacement"),
            min_confirmations=2,
            strict_mtf=False,
        ),
        # Continuation setup keeps strict MTF alignment.
        _graded_contract(
            name="TREND_PULLBACK",
            preferred_family="TREND_PULLBACK",
            ev=ev,
            anchors=("trend", "mtf", "pullback"),
            confirmations=("momentum", "volume", "poi"),
            min_confirmations=1,
            strict_mtf=True,
        ),
        # Breakout/retest needs a true retest plus structural/directional anchor.
        _graded_contract(
            name="BREAKOUT_RETEST",
            preferred_family="BREAKOUT_RETEST",
            ev=ev,
            anchors=("breakout_retest",),
            require_any=("structure", "direction_anchor"),
            confirmations=("displacement", "volume", "momentum", "mtf", "structure"),
            min_confirmations=2,
            strict_mtf=True,
        ),
        # Compression can lead HTF; opposite MTF demands more evidence rather
        # than killing the hypothesis before Geometry.
        _graded_contract(
            name="COMPRESSION_EXPANSION",
            preferred_family="BOLLINGER_SQUEEZE",
            ev=ev,
            anchors=("squeeze", "expansion"),
            require_any=("direction_anchor", "momentum"),
            confirmations=("volume", "momentum", "structure", "displacement", "mtf"),
            min_confirmations=2,
            strict_mtf=False,
        ),
        # Mean reversion needs range + location + extreme. Momentum becomes a
        # confirmation rather than a duplicate mandatory gate.
        _graded_contract(
            name="RANGE_MEAN_REVERSION",
            preferred_family="MEAN_REVERSION",
            ev=ev,
            anchors=("range", "extreme", "mean_reversion_location"),
            confirmations=("momentum", "structure", "volume", "mtf"),
            min_confirmations=1,
            strict_mtf=False,
        ),
    ]

    eligible = [c for c in contracts if c.get("passed")]
    eligible.sort(key=lambda c: (float(c.get("quality") or 0.0), len(c.get("support_hits") or [])), reverse=True)
    return {"direction": direction, "evidence": ev, "contracts": contracts, "best": eligible[0] if eligible else None}


def particular_setup_diagnostic(
    operational: Mapping[str, Any], *, layers: Mapping[str, Any],
    symbol: str, timeframe: str, system_type: str,
) -> Dict[str, Any]:
    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    long_side = _evaluate_side(layers, operational, "BULLISH")
    short_side = _evaluate_side(layers, operational, "BEARISH")
    candidates: List[Dict[str, Any]] = []
    if long_side.get("best"):
        candidates.append(dict(long_side["best"], direction="BULLISH"))
    if short_side.get("best"):
        candidates.append(dict(short_side["best"], direction="BEARISH"))
    candidates.sort(key=lambda c: float(c.get("quality") or 0.0), reverse=True)

    winner = None
    ambiguous = False
    if len(candidates) == 1:
        winner = candidates[0]
    elif len(candidates) >= 2:
        margin = float(candidates[0]["quality"]) - float(candidates[1]["quality"])
        if margin >= 4.0:
            winner = candidates[0]
        else:
            ambiguous = True

    return {
        "version": VERSION,
        "market": market,
        "symbol": _u(symbol).replace("/", "-"),
        "timeframe": str(timeframe),
        "winner": winner,
        "ambiguous": ambiguous,
        "long": long_side,
        "short": short_side,
        "authority": "PRE_CANDIDATE_TECHNICAL_CONTRACT_ONLY",
        "minimum_operational_timeframe": "30m",
        "can_bypass_entry_committee": False,
        "can_bypass_sl_committee": False,
        "can_bypass_tp_committee": False,
        "can_bypass_safety": False,
        "can_bypass_publication": False,
    }


def _candidate_floor(market: str, is_multi: bool) -> float:
    # PRE-candidate evidence only.  CORE/MEDIUM/HIGH are intentionally equal
    # here; the class differences remain downstream in tempo/risk/Safety.
    if market == "SPOT":
        return 78.0
    if is_multi:
        return 80.0
    return 80.0


def _setup_mtf_usable(winner: Mapping[str, Any], op: Mapping[str, Any]) -> bool:
    policy = str(winner.get("mtf_policy") or "STRICT").upper()
    conflict = bool((op.get("multi_timeframe") or {}).get("conflict"))
    if policy == "STRICT":
        return not conflict
    # Contextual contracts have already paid an extra-confirmation penalty.
    return True


def _apply_recovery(
    op: Dict[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, market: str, is_multi: bool,
) -> Dict[str, Any]:
    diag = particular_setup_diagnostic(
        op, layers=layers, symbol=symbol, timeframe=timeframe, system_type=market
    )
    op["commit33_3_setup_diagnostic"] = diag
    winner = diag.get("winner")
    if not winner or diag.get("ambiguous"):
        op["commit33_3_recovery_reason"] = "NO_UNAMBIGUOUS_SETUP"
        return op

    direction = str(winner.get("direction") or "NEUTRAL")
    action = _action(direction, market)
    if action not in _DIRECTIONAL:
        return op

    floor = _candidate_floor(market, is_multi)
    contract_quality = _f(winner.get("quality"))
    if contract_quality < floor:
        op["commit33_3_recovery_reason"] = "SETUP_QUALITY_BELOW_PRE_CANDIDATE_FLOOR"
        return op

    strategy = _base._select_default_strategy(
        op,
        layers=layers,
        symbol=symbol,
        timeframe=timeframe,
        market=market,
        action=action,
        preferred_family=str(winner.get("preferred_family") or ""),
        is_multi=is_multi,
    )
    strategy_min = 78.0 if market == "FUTURES" else 70.0
    strategy_quality = _f(strategy.get("quality"))
    strategy_ok = bool(
        strategy_quality >= strategy_min
        and strategy.get("regime_match", True)
        and strategy.get("volatility_match", True)
    )
    if not strategy_ok:
        op["commit33_3_strategy"] = strategy
        op["commit33_3_recovery_reason"] = "STRATEGY_BANK_NOT_READY"
        return op

    official = _base._official_cell(
        market, symbol, timeframe, action, fallback=bool(op.get("official_cell"))
    )
    thesis = dict(op.get("thesis") or {})
    macro = layers.get("macro_context") or {}
    macro_risk = _u(thesis.get("macro_risk") or macro.get("risk_level") or macro.get("risk"))
    mtf_usable = _setup_mtf_usable(winner, op)

    if not official:
        op["commit33_3_recovery_reason"] = "UNOFFICIAL_CELL"
        return op
    if macro_risk == "CRITICAL":
        op["commit33_3_recovery_reason"] = "MACRO_CRITICAL"
        return op
    if not mtf_usable:
        op["commit33_3_recovery_reason"] = "MTF_STRICT_CONFLICT"
        return op

    evidence = (
        diag.get("long", {}).get("evidence", {})
        if direction == "BULLISH" else diag.get("short", {}).get("evidence", {})
    )
    supports = list(dict.fromkeys(
        list(winner.get("core_hits") or [])
        + list(winner.get("require_any_hits") or [])
        + list(winner.get("support_hits") or [])
    ))

    patched_thesis = dict(thesis)
    patched_thesis.update({
        "base_direction_before_commit33_3": thesis.get("direction"),
        "base_action_before_commit33_3": thesis.get("action"),
        "direction": direction,
        "action": action,
        "quality": round(contract_quality, 2),
        "independent_support_families": supports,
        "commit33_3_setup_contract": {
            "setup": winner.get("setup"),
            "preferred_family": winner.get("preferred_family"),
            "quality": round(contract_quality, 2),
            "pre_candidate_floor": floor,
            "mtf_policy": winner.get("mtf_policy"),
            "core_hits": list(winner.get("core_hits") or []),
            "require_any_hits": list(winner.get("require_any_hits") or []),
            "support_hits": list(winner.get("support_hits") or []),
            "evidence_snapshot": {
                k: evidence.get(k)
                for k in ("adx", "rsi", "volume_ratio", "trend_direction", "structure_direction", "mtf_direction")
            },
        },
        "anti_overfit_rule": "ROLE_BASED_PRE_CANDIDATE;FINAL_GATES_UNCHANGED",
    })

    op["thesis"] = patched_thesis
    op["default_strategy"] = strategy
    op["candidate_source"] = "COMMIT33_3_SETUP_AWARE_RECOVERY+STRATEGY"
    op["candidate_action"] = action
    op["candidate_ready"] = True
    op["official_cell"] = True
    op["mtf_usable"] = mtf_usable
    op["selected_specialist_source"] = "COMMIT33_3_SETUP_AWARE"
    op["commit33_3_recovered"] = True
    op["commit33_3_setup_family"] = winner.get("setup")
    op["commit33_3_setup_quality"] = round(contract_quality, 2)
    op["commit33_3_strategy_quality"] = round(strategy_quality, 2)
    op["never_bypass_safety"] = True
    op["never_bypass_execution_committees"] = True
    op["minimum_operational_timeframe"] = "30m"
    return op


def _reconcile_core_candidate(
    operational: Mapping[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, system_type: str,
) -> Dict[str, Any]:
    """Run the current native router first, then one core recovery pass.

    Nothing after candidate_ready is bypassed.  Entry/SL/TP committees, Safety,
    RR/economics and publication/OOS remain authoritative.
    """
    out = _base.reconcile_operational_candidate(
        operational,
        layers=layers,
        symbol=symbol,
        timeframe=timeframe,
        system_type=system_type,
    )
    out = deepcopy(dict(out or {}))
    out["pipeline_integrity_base_version"] = getattr(_base, "VERSION", None)
    out["pipeline_integrity_version"] = VERSION
    out["pipeline_generation"] = PIPELINE_GENERATION
    out["commit33_3_final_gates_unchanged"] = True

    if bool(out.get("candidate_ready")) and _u(out.get("candidate_action")) in _DIRECTIONAL:
        out["commit33_3_recovery_reason"] = "BASE_ROUTER_ALREADY_READY"
        return out

    market = "FUTURES" if _u(system_type) == "FUTURES" else "SPOT"
    is_multi = _base._is_multiasset(symbol) if market == "FUTURES" else False
    return _apply_recovery(
        out, layers=layers, symbol=symbol, timeframe=timeframe,
        market=market, is_multi=is_multi,
    )


def reconcile_operational_candidate(
    operational: Mapping[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, system_type: str,
) -> Dict[str, Any]:
    """Native 33.3 reconciliation with the current SPOT market authority preserved.

    Commit32 previously installed SPOT by monkeypatching this module at WSGI
    startup.  33.3 keeps the same global-market semantics without a runtime
    wrapper: the SPOT authority is called explicitly here, while Futures/Multi
    use the core router directly.  Guardian remains downstream and per-user.
    """
    market = _u(system_type)
    if market == "SPOT":
        try:
            from commit32_spot_market_authority import (
                SUPPORTED_SYMBOLS as _SPOT_SUPPORTED,
                apply_market_signal_to_pipeline as _apply_spot_market_signal,
            )
            sym = _u(symbol).replace("/", "-")
            if sym in set(_SPOT_SUPPORTED):
                return _apply_spot_market_signal(
                    _reconcile_core_candidate,
                    _base,
                    operational,
                    layers=layers,
                    symbol=symbol,
                    timeframe=timeframe,
                    system_type=system_type,
                )
        except Exception as exc:
            # Fail safe into the native/current core router.  The caller can
            # still inspect this marker without losing the whole analysis.
            out = _reconcile_core_candidate(
                operational, layers=layers, symbol=symbol,
                timeframe=timeframe, system_type=system_type,
            )
            out["commit33_3_spot_authority_error"] = type(exc).__name__
            return out
    return _reconcile_core_candidate(
        operational, layers=layers, symbol=symbol,
        timeframe=timeframe, system_type=system_type,
    )


def _parse_dt(value: Any):
    try:
        raw = str(value or "").strip().replace("Z", "+00:00")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def profitability_hard_block_authority(route: Mapping[str, Any]) -> Dict[str, Any]:
    """Generation-aware hard block using the 33.3 pipeline identity."""
    route = dict(route or {})
    state = _u(route.get("state"))
    released = _parse_dt(RELEASED_AT_UTC)
    if not route.get("block_new_signal"):
        return {"allowed": False, "reason": "NO_BLOCK_REQUESTED", "state": state}
    if state == "NEGATIVE_EDGE_VETO":
        return {
            "allowed": False,
            "reason": "OLD_OOS_IS_COUNTER_EVIDENCE_NOT_VERSION_MATCHED_VETO",
            "state": state,
        }
    if state in {"ALPHA_DECAY_VETO", "SHADOW_DIVERGED_RETEST"}:
        evidence = route.get("best_diverged") or {}
        updated = _parse_dt(evidence.get("shadow_updated_at"))
        generation = str(evidence.get("pipeline_generation") or evidence.get("generation") or "")
        version_match = generation == PIPELINE_GENERATION
        forward_new = bool(updated and released and updated >= released)
        recent_n = int(evidence.get("recent8_n") or 0)
        if (version_match or forward_new) and recent_n >= 8:
            return {
                "allowed": True,
                "reason": "FORWARD_ALPHA_DECAY_VERSION_COMPATIBLE",
                "state": state,
            }
        return {
            "allowed": False,
            "reason": "ALPHA_DECAY_EVIDENCE_NOT_CURRENT_GENERATION",
            "state": state,
        }
    return {"allowed": False, "reason": "UNSCOPED_RESEARCH_BLOCK_SOFTENED", "state": state}


def stamp_pipeline_generation(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    result = _base.stamp_pipeline_generation(result)
    result["pipeline_generation"] = PIPELINE_GENERATION
    levels = dict(result.get("levels") or {})
    levels["pipeline_generation"] = PIPELINE_GENERATION
    result["levels"] = levels
    context = dict(result.get("context") or {})
    learning = dict(context.get("learning") or {})
    learning["pipeline_generation"] = PIPELINE_GENERATION
    learning["pipeline_integrity_version"] = VERSION
    context["learning"] = learning
    result["context"] = context
    return result


_multiasset_strategy_from_live_layers = _base._multiasset_strategy_from_live_layers
