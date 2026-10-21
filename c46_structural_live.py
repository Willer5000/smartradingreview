"""C46 additive LIVE candidate discovery (Futures/Multi-Activo only).

NO trading direction quota, NO price generation, NO custom win probability, NO
premium shortcut. Return a *candidate* only if the canonical router produced no
candidate and strong evidence is ALREADY in the original closed-bar analysis.
The original 9-specialist vote and Entry/SL/TP/Safety/publication can refuse it.

This module holds no caches, spawns no threads, performs no I/O and imports no
large dataframes. It deliberately does not use asset-optimized backtest routes:
those were selected with weak OOS evidence and are not independent proof.
"""
from __future__ import annotations

from collections.abc import Mapping
import os
import logging
from typing import Any

VERSION = "C46_STRUCTURAL_LIVE_SAFE_1"
DIRECTIONS = {"BULLISH": "LONG", "BEARISH": "SHORT"}
_DISABLED = {"0", "false", "no", "off"}
_VALID_TF = {"30M", "1H", "2H", "4H"}
_MULTI_TF = {"1H", "4H"}


def _enabled(name, default="1"):
    return os.getenv(name, default).strip().lower() not in _DISABLED


def _uppercase(value):
    return str(value or "").strip().upper().replace("/", "-")


def _direction(value):
    value = _uppercase(value)
    if value in ("BULLISH", "LONG", "BUY", "ALCISTA", "COMPRA"):
        return "BULLISH"
    if value in ("BEARISH", "SHORT", "SELL", "BAJISTA", "VENTA"):
        return "BEARISH"
    return ""


def _signed_evidence(rows, desired):
    if isinstance(rows, Mapping):
        # A single row OR a mapping of numeric labels to rows.
        rows = [rows] if any(k in rows for k in ("direction", "side", "type", "bias")) else list(rows.values())
    if not isinstance(rows, (list, tuple)):
        return False
    for row in rows[:48]:  # bound time and avoid scanning arbitrary JSON
        if isinstance(row, Mapping) and _direction(row.get("direction") or row.get("side") or row.get("bias") or row.get("type")) == desired:
            return True
    return False


def _divergence(momentum, desired):
    if not isinstance(momentum, Mapping):
        return False
    for key in ("divergences", "divergence_details"):
        raw = momentum.get(key) or []
        if not isinstance(raw, (list, tuple)):
            continue
        for row in raw[:24]:
            if isinstance(row, Mapping):
                kind = _uppercase(row.get("type") or row.get("direction") or row.get("side"))
            else:
                kind = _uppercase(row)
            if "HIDDEN" in kind or "OCULT" in kind:
                continue
            if desired == "BULLISH" and ("BULL" in kind or "ALCIST" in kind):
                return True
            if desired == "BEARISH" and ("BEAR" in kind or "BAJIST" in kind):
                return True
    return False


def collect_additional_candidates(op: Mapping[str, Any], layers: Mapping[str, Any], *,
                                  symbol: str, timeframe: str, system_type: str,
                                  is_multiasset, evidence_builder) -> list[dict]:
    """Return a bounded list of fact-checked directional candidates, never Premium.

    Returned contracts are *not* official signals, and no action is taken here.
    The caller controls winner selection and invokes the ORIGINAL playbook.
    """
    if not _enabled("C46_STRUCTURAL_LIVE_ENABLED"):
        return []
    if _uppercase(system_type) != "FUTURES" or op.get("candidate_ready"):
        return []
    if _uppercase(op.get("candidate_action")) not in ("", "NO_OPERAR"):
        return []
    if _uppercase(op.get("candidate_source")) == "MACRO_CRITICAL_HOLD":
        return []
    thesis = op.get("thesis") or {}
    macro = layers.get("macro_context") or {}
    if _uppercase(thesis.get("macro_risk") or macro.get("risk_level") or macro.get("risk")) == "CRITICAL":
        return []
    if bool((op.get("multi_timeframe") or {}).get("conflict")):
        return []
    multi = bool(is_multiasset(symbol))
    if _uppercase(timeframe) not in (_MULTI_TF if multi else _VALID_TF):
        return []
    if multi and not _enabled("C46_MULTI_LIVE_ENABLED"):
        return []
    structure = layers.get("structure") or {}
    momentum = layers.get("momentum") or {}
    volume = layers.get("volume") or {}
    candidates = []
    for desired, action in DIRECTIONS.items():
        ev = evidence_builder(layers, op, desired)
        if not isinstance(ev, Mapping):
            continue
        # Strict directional price-location evidence; an untyped OB/FVG list
        # cannot prove demand for LONG or supply for SHORT.
        ob = _signed_evidence(structure.get("order_blocks") or [], desired)
        fvg = _signed_evidence(structure.get("fair_value_gaps") or structure.get("fvgs") or [], desired)
        poizone = ob or fvg
        sweep = _signed_evidence(structure.get("liquidity_sweeps") or structure.get("stop_hunts") or [], desired)
        div = _divergence(momentum, desired)
        roles = {
            "structure": bool(ev.get("structure")),
            "price_zone": poizone,
            "momentum": bool(ev.get("momentum")),
            "volume_flow": bool(ev.get("volume")),
            "sweep": sweep,
            "mss": bool(ev.get("mss")),
            "divergence": div,
            "trend": bool(ev.get("trend")),
            "pullback": bool(ev.get("pullback")),
            "range": bool(ev.get("range")),
        }
        # Four universal, indicator-family contracts. Their parameters do not
        # depend on BTC/ETH/etc, on optimized PF, or on chosen OOS windows.
        contracts = (
            ("SWEEP_MSS_REJECTION", "SWEEP_REVERSAL",
             ("structure", "price_zone", "sweep", "mss", "momentum"),
             ("volume_flow", "divergence")),
            ("DIVERGENCE_STRUCTURE_RECLAIM", "SWEEP_REVERSAL",
             ("structure", "price_zone", "mss", "divergence", "momentum"),
             ("volume_flow", "sweep")),
            ("VALUE_RANGE_REVERSAL", "MEAN_REVERSION",
             ("structure", "price_zone", "range", "momentum", "volume_flow"),
             ("sweep", "divergence")),
            ("PULLBACK_STRUCTURE_CONTINUATION", "TREND_PULLBACK",
             ("trend", "structure", "price_zone", "pullback", "momentum"),
             ("volume_flow",)),
        )
        for family, playbook, core, corroborations in contracts:
            if not all(roles[x] for x in core) or not any(roles[x] for x in corroborations):
                continue
            # For reversals against the dominant trend require BOTH volume
            # participation and directional sweep/MSS or measured divergence.
            opposite = _uppercase((op.get("multi_timeframe") or {}).get("dominant_direction"))
            if opposite in DIRECTIONS and opposite != desired and "CONTINUATION" not in family:
                if not (roles["volume_flow"] and roles["mss"] and (roles["sweep"] or roles["divergence"])):
                    continue
            # A passed technical contract is NOT a probability. Use the
            # existing core setup floor to avoid any made-up 85% confidence.
            role_names = tuple(k for k, v in roles.items() if v)
            candidates.append({
                "action": action, "direction": desired, "family": family,
                "playbook": playbook, "core": tuple(core), "corroborations":tuple(k for k in corroborations if roles[k]),
                "evidence_roles": role_names,
                "source": VERSION, "premium": False, "overfit_certified": False,
            })
    # Ambiguous independent LONG and SHORT contracts are NOT forced into one
    # canonical result. They need separate full execution/lifecycle authority.
    if len({c["direction"] for c in candidates}) > 1:
        return []
    return candidates[:8]


def try_add_candidate(op: Mapping[str, Any], layers: Mapping[str, Any], *,
                      symbol: str, timeframe: str, system_type: str,
                      is_multiasset, evidence_builder, select_strategy,
                      official_cell):
    """Return the unchanged original on ANY uncertainty; never force a trade."""
    candidates = collect_additional_candidates(
        op, layers, symbol=symbol, timeframe=timeframe, system_type=system_type,
        is_multiasset=is_multiasset, evidence_builder=evidence_builder)
    if not candidates:
        return op
    # Fixed PRIORITY by causal specificity, not the best historical return.
    rank = {"SWEEP_MSS_REJECTION": 0, "DIVERGENCE_STRUCTURE_RECLAIM": 1,
            "VALUE_RANGE_REVERSAL": 2, "PULLBACK_STRUCTURE_CONTINUATION": 3}
    winner = sorted(candidates, key=lambda c: rank[c["family"]])[0]
    action = winner["action"]
    if not official_cell("FUTURES", symbol, timeframe, action):
        return op
    # Original statistical veto is consulted if the authority supplied it.
    history = op.get("research_candidates") or {}
    prior = history.get(action) if isinstance(history, Mapping) else {}
    if isinstance(prior, Mapping) and _uppercase(prior.get("state")) in {
        "ALPHA_DECAY", "REJECTED_OOS", "NEGATIVE_OOS", "REVOKED", "DEGRADED"
    }:
        return op
    strategy = select_strategy(op, layers=layers, symbol=symbol,
                               timeframe=timeframe, market="FUTURES", action=action,
                               preferred_family=winner["playbook"],
                               is_multi=bool(is_multiasset(symbol)))
    if not isinstance(strategy, Mapping) or _uppercase(strategy.get("family")) in ("", "NONE") or _uppercase(strategy.get("id")) in ("NO_PLAYBOOK", "MULTIASSET_NO_DIRECTIONAL_PLAYBOOK", "MULTIASSET_STRATEGY_UNAVAILABLE"):
        return op
    # Do not synthesize an overconfident technical quality; the original
    # PRE-CANDIDATE floor and genuine playbook quality are both required.
    quality = float(strategy.get("quality") or 0)
    minimum = 84.0 if is_multiasset(symbol) else 82.0
    if quality < minimum:
        return op
    result = dict(op)
    old_thesis = dict(result.get("thesis") or {})
    old_thesis.update({
        "direction": winner["direction"], "action": action,
        "independent_support_families": list(winner["evidence_roles"]),
        "c46_candidate_not_premium": True,
    })
    result.update({
        "thesis": old_thesis,
        "candidate_ready": True, "candidate_action": action,
        "candidate_source": "C46_ADD_ON_CLOSED_BAR",
        "candidate_quality": quality,
        "default_strategy": dict(strategy),
        "core_setup_family": winner["family"],
        "official_cell": True,
        "never_bypass_safety": True,
        "candidate_contract": {
            "version": VERSION, "passed": True, "source": "C46_ADD_ON_CLOSED_BAR",
            "action": action, "quality": quality, "quality_floor": minimum,
            "support": list(winner["evidence_roles"]),
            "support_count": len(winner["evidence_roles"]), "support_floor": len(winner["core"]),
            "setup_family": winner["family"], "safety_is_downstream": True,
            "primary_geometry_is_downstream": True, "quality_is_rechecked_at_publication": False,
        },
        "c46_audit": {
            "version": VERSION, "family": winner["family"], "direction": action,
            "evidence_roles": list(winner["evidence_roles"]),
            "requires_nine_specialists": True,
            "publishes_on_its_own": False,
            "historical_profitability_proven": False,
        },
    })
    logging.getLogger("C46_STRUCTURAL").info(
        "[C46 CANDIDATE] %s %s %s %s; original specialists/Safety still decide",
        symbol, timeframe, action, winner["family"],
    )
    return result
