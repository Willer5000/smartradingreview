"""Commit 17.5.10.1 — Opportunity Pipeline Integrity.

Small, dependency-light coordination layer.  It does not alter Safety, RR,
Entry/SL/TP thresholds or Leverage V6.  Its job is to prevent infrastructure,
old-generation Research and Multi-Asset routing order from deleting otherwise
valid technical opportunities before the authoritative gates see them.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
from typing import Any, Dict, Mapping

VERSION = "17.5.10.1_PIPELINE_INTEGRITY_V1"
PIPELINE_GENERATION = "17.5.10.1"
# Evidence older than this release cannot hard-veto the changed execution
# generation merely because it had a negative result under an older geometry.
RELEASED_AT_UTC = "2026-09-29T11:45:00+00:00"

_DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else float(default)
    except Exception:
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _contains(blob: str, *tokens: str) -> bool:
    b = blob.upper()
    return any(str(t).upper() in b for t in tokens)


def _layer_blob(layers: Mapping[str, Any]) -> str:
    # Diagnostic/routing only.  No user-facing message and no network I/O.
    keep = {
        "trend": layers.get("trend") or {},
        "momentum": layers.get("momentum") or {},
        "volatility": layers.get("volatility") or {},
        "volume": layers.get("volume") or {},
        "structure": layers.get("structure") or {},
        "confirmation": layers.get("confirmation") or {},
        "market_hours": layers.get("market_hours") or {},
        "macro_context": layers.get("macro_context") or {},
    }
    return str(keep).upper()


def _multiasset_strategy_from_live_layers(
    layers: Mapping[str, Any], symbol: str, timeframe: str, action: str
) -> Dict[str, Any]:
    """Build a real asset-class playbook BEFORE candidate_ready.

    The existing Multi-Asset bank already contains the right families.  This
    function does not add optimized families; it scores those existing routes
    against current live structure/context so they can participate at the same
    stage as the crypto Strategy Bank.
    """
    try:
        from multiasset_system import MULTIASSET_SYMBOLS, MULTIASSET_STRATEGY_BANK
    except Exception as exc:
        return {
            "id": "MULTIASSET_STRATEGY_UNAVAILABLE",
            "family": "NONE", "quality": 0.0,
            "regime_match": False, "volatility_match": False,
            "error": type(exc).__name__, "version": VERSION,
        }

    symbol_u = _u(symbol).replace("/", "-")
    meta = MULTIASSET_SYMBOLS.get(symbol_u) or {}
    asset_class = str(meta.get("asset_class") or "")
    families = list(MULTIASSET_STRATEGY_BANK.get(asset_class) or [])
    if not families or _u(action) not in _DIRECTIONAL:
        return {
            "id": "MULTIASSET_NO_DIRECTIONAL_PLAYBOOK",
            "family": "NONE", "quality": 0.0,
            "regime_match": True, "volatility_match": True,
            "eligible_strategy_count": len(families), "version": VERSION,
        }

    trend = layers.get("trend") or {}
    volatility = layers.get("volatility") or {}
    momentum = layers.get("momentum") or {}
    volume = layers.get("volume") or {}
    structure = layers.get("structure") or {}
    macro = layers.get("macro_context") or {}
    blob = _layer_blob(layers)

    adx = _f(trend.get("adx") or (trend.get("indicators") or {}).get("adx"))
    atr_pct = _f(volatility.get("atr_pct") or volatility.get("atr_percent") or layers.get("atr_pct"))
    regime = "TRENDING" if adx >= 28 else ("RANGING" if 0 < adx < 18 else "MIXED")
    vol_regime = "HIGH" if atr_pct >= 3 else ("LOW" if 0 < atr_pct < 0.8 else "NORMAL")

    direction = "BULLISH" if _u(action) in {"LONG", "COMPRA_SPOT"} else "BEARISH"
    trend_dir = _u(trend.get("direction") or trend.get("trend_direction"))
    trend_aligned = (
        (direction == "BULLISH" and trend_dir in {"BULLISH", "ALCISTA", "UP"})
        or (direction == "BEARISH" and trend_dir in {"BEARISH", "BAJISTA", "DOWN"})
    )
    vol_ratio = _f(volume.get("volume_ratio") or volume.get("relative_volume") or 1.0, 1.0)
    rsi = _f(momentum.get("rsi") or (momentum.get("indicators") or {}).get("rsi"), 50.0)

    # Generic current-market observations.  They are evidence pieces, not
    # independent votes and they do not change direction by themselves.
    has_sweep = _contains(blob, "SWEEP", "LIQUIDITY_SWEEP", "STOP_HUNT", "BARRIDO")
    has_mss = _contains(blob, "MSS", "BOS", "CHANGE_OF_CHARACTER", "CHOCH", "CAMBIO_ESTRUCTURA")
    has_poi = _contains(blob, "ORDER_BLOCK", "FVG", "POC", "HVN", "LVN", "SUPPORT", "RESISTANCE", "FIB")
    has_displacement = _contains(blob, "DISPLACEMENT", "IMPULSE", "IMPULSO", "VELA_FUERTE")
    has_pullback = _contains(blob, "PULLBACK", "RETEST", "RETROCESO", "RECLAIM")
    has_breakout = _contains(blob, "BREAKOUT", "BREAKDOWN", "RUPTURA", "BOS")
    has_squeeze = _contains(blob, "SQUEEZE", "COMPRESSION", "COMPRESION")
    has_vwap = _contains(blob, "VWAP", "VALUE_AREA", "POC")
    has_mean_revert = (regime == "RANGING" and (rsi <= 35 or rsi >= 65 or _contains(blob, "BOLLINGER", "VALUE_AREA")))
    macro_available = bool(macro) and _u(macro.get("risk_level") or macro.get("current_risk_level")) not in {"", "UNKNOWN"}

    scored: Dict[str, Dict[str, Any]] = {}
    for family in families:
        score = 48.0
        reasons = []
        # Regime/context compatibility contributes, but cannot be enough alone.
        if family in {"TREND_PULLBACK", "VWAP_SESSION_PULLBACK", "MACRO_TREND_CONFIRMATION", "RATES_USD_CONFIRMATION"}:
            if regime == "TRENDING" and trend_aligned:
                score += 14; reasons.append("trend_regime")
        elif family == "MEAN_REVERSION_SELECTIVE":
            if regime == "RANGING": score += 12; reasons.append("range_regime")
        elif family == "COMPRESSION_EXPANSION":
            if has_squeeze: score += 14; reasons.append("compression")
        else:
            if trend_aligned: score += 7; reasons.append("trend_alignment")

        if family == "SWEEP_MSS_POI":
            if has_sweep: score += 12; reasons.append("sweep")
            if has_mss: score += 12; reasons.append("mss_bos")
            if has_poi: score += 8; reasons.append("poi")
            if has_displacement: score += 6; reasons.append("displacement")
        elif family in {"TREND_PULLBACK", "VWAP_SESSION_PULLBACK", "VOLATILITY_RETEST", "ASIA_SESSION_RETEST"}:
            if has_pullback: score += 13; reasons.append("pullback_retest")
            if has_poi: score += 8; reasons.append("structural_zone")
            if family == "VWAP_SESSION_PULLBACK" and has_vwap: score += 9; reasons.append("vwap_value")
            if family == "VOLATILITY_RETEST" and vol_regime == "HIGH": score += 8; reasons.append("high_volatility")
        elif family == "BREAKOUT_RETEST":
            if has_breakout: score += 14; reasons.append("breakout")
            if has_pullback: score += 12; reasons.append("retest")
            if has_displacement: score += 6; reasons.append("displacement")
        elif family == "COMPRESSION_EXPANSION":
            if has_breakout or has_displacement: score += 12; reasons.append("expansion")
            if vol_ratio >= 1.1: score += 7; reasons.append("activity")
        elif family == "MEAN_REVERSION_SELECTIVE":
            if has_mean_revert: score += 16; reasons.append("mean_reversion_condition")
            if has_poi: score += 7; reasons.append("value_or_structure")
        elif family in {"POST_EVENT_CONFIRMATION", "POST_MACRO_CONFIRMATION", "MACRO_TREND_CONFIRMATION", "RATES_USD_CONFIRMATION"}:
            if macro_available: score += 9; reasons.append("macro_context")
            if trend_aligned: score += 8; reasons.append("price_confirmation")
            if has_pullback or has_breakout: score += 8; reasons.append("technical_confirmation")

        # Volume is a supporting quality input, never a family by itself here.
        if vol_ratio >= 1.2: score += 4; reasons.append("relative_volume")
        score = max(0.0, min(100.0, score))
        scored[family] = {"quality": round(score, 2), "reasons": reasons[:8]}

    selected = max(scored, key=lambda k: scored[k]["quality"]) if scored else None
    quality = float((scored.get(selected) or {}).get("quality") or 0.0)
    return {
        "version": VERSION,
        "id": f"MULTI::{asset_class}::{selected or 'NONE'}::{_u(timeframe)}",
        "family": selected or "NONE",
        "quality": round(quality, 2),
        "confirmations": list((scored.get(selected) or {}).get("reasons") or []),
        "conflicts": [],
        "regime": regime,
        "volatility_regime": vol_regime,
        "regime_match": True,
        "volatility_match": True,
        "asset_class": asset_class,
        "eligible_strategy_count": len(families),
        "candidate_scores": {k: v["quality"] for k, v in scored.items()},
        "authority": "LIVE_CONTEXT_ROUTING_NO_DIRECTION_CREATION",
        "creates_direction": False,
        "never_bypass_safety": True,
    }


def reconcile_operational_candidate(
    operational: Mapping[str, Any], *, layers: Mapping[str, Any], symbol: str,
    timeframe: str, system_type: str
) -> Dict[str, Any]:
    """Repair routing order without lowering any trading threshold."""
    op = deepcopy(dict(operational or {}))
    thesis = dict(op.get("thesis") or {})
    thesis_action = _u(thesis.get("action"))
    thesis_direction = _u(thesis.get("direction"))
    market = _u(system_type)

    op["pipeline_integrity_version"] = VERSION
    op["pipeline_generation"] = PIPELINE_GENERATION

    # Old OOS/Research is counter-evidence, not an early irreversible gate.
    # Generation-aware alpha decay is handled later by Profitability Router.
    if op.get("research_blocks_selected_action"):
        op["research_counter_evidence"] = {
            "state": str((op.get("research_candidates") or {}).get(thesis_action, {}).get("state") or "NEGATIVE_RESEARCH"),
            "former_hard_block": True,
            "authority": "COUNTER_EVIDENCE_UNTIL_VERSION_MATCHED_FORWARD",
        }
        op["research_blocks_selected_action"] = False
        op["stale_research_softened"] = True

    try:
        from multiasset_system import MULTIASSET_SYMBOLS
        is_multi = _u(symbol).replace("/", "-") in MULTIASSET_SYMBOLS
    except Exception:
        is_multi = False

    if market != "FUTURES" or thesis_action not in _DIRECTIONAL or thesis_direction not in {"BULLISH", "BEARISH"}:
        return op

    # Crypto Futures: if the only reason candidate_ready was false was the old
    # pre-candidate Research block, recompute with the SAME live requirements.
    # Current-generation alpha decay still has a later, generation-aware gate.
    if not is_multi:
        if not op.get("stale_research_softened"):
            return op
        strategy = dict(op.get("default_strategy") or {})
        quality = _f(strategy.get("quality"))
        thesis_quality = _f(thesis.get("quality"))
        min_quality = 78.0
        autonomous_min = _f(op.get("autonomous_thesis_min_quality"), 82.0)
        support = len(thesis.get("independent_support_families") or [])
        required_support = int(thesis.get("required_independent_families") or 4)
        mtf_usable = bool(op.get("mtf_usable", not bool((op.get("multi_timeframe") or {}).get("conflict"))))
        official = bool(op.get("official_cell", True))
        macro_critical = _u(thesis.get("macro_risk")) == "CRITICAL"
        strategy_ok = bool(
            quality >= min_quality
            and strategy.get("regime_match", True)
            and strategy.get("volatility_match", True)
        )
        learned_live_ok = bool(
            str(op.get("selected_specialist_source") or "").upper() == "LEARNED"
            and support >= 3 and mtf_usable
        )
        autonomous_ok = bool(
            thesis_quality >= autonomous_min
            and support >= required_support
            and mtf_usable
        )
        thesis_ok = thesis_quality >= min_quality
        source = "NONE"
        if learned_live_ok and strategy_ok:
            source = "LEARNED+DEFAULT"
        elif learned_live_ok:
            source = "LEARNED+LIVE"
        elif thesis_ok and strategy_ok:
            source = "THESIS+DEFAULT"
        elif autonomous_ok:
            source = "THESIS_AUTONOMOUS"
        ready = bool(official and source != "NONE" and mtf_usable and not macro_critical)
        op["candidate_source"] = source
        op["candidate_action"] = thesis_action if ready else "NO_OPERAR"
        op["candidate_ready"] = ready
        op["research_recompute_same_thresholds"] = True
        return op

    strategy = _multiasset_strategy_from_live_layers(layers, symbol, timeframe, thesis_action)
    op["default_strategy"] = strategy
    quality = _f(strategy.get("quality"))
    thesis_quality = _f(thesis.get("quality"))
    min_quality = 78.0  # unchanged from operational_intelligence.py
    autonomous_min = _f(op.get("autonomous_thesis_min_quality"), 82.0)
    support = len(thesis.get("independent_support_families") or [])
    required_support = int(thesis.get("required_independent_families") or 4)
    mtf_usable = bool(op.get("mtf_usable", not bool((op.get("multi_timeframe") or {}).get("conflict"))))
    official = bool(op.get("official_cell", True))
    macro_critical = _u(thesis.get("macro_risk")) == "CRITICAL"

    strategy_ok = bool(quality >= min_quality and strategy.get("regime_match", True) and strategy.get("volatility_match", True))
    thesis_ok = bool(thesis_quality >= min_quality)
    autonomous_ok = bool(thesis_quality >= autonomous_min and support >= required_support and mtf_usable)

    source = "NONE"
    if thesis_ok and strategy_ok:
        source = "THESIS+MULTIASSET_STRATEGY"
    elif autonomous_ok:
        source = "THESIS_AUTONOMOUS"

    ready = bool(
        official and source != "NONE" and mtf_usable and not macro_critical
    )
    op["candidate_source"] = source
    op["candidate_action"] = thesis_action if ready else "NO_OPERAR"
    op["candidate_ready"] = ready
    op["multiasset_strategy_pre_candidate"] = True
    op["multiasset_strategy_quality"] = quality
    op["multiasset_strategy_threshold_unchanged"] = min_quality
    return op


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
    """Decide whether Research may hard-block this pipeline generation.

    Old REJECTED_OOS remains valuable counter-evidence, but cannot veto a new
    execution geometry.  Alpha decay can regain hard authority only from a
    forward/live shadow cohort observed after this generation release.
    """
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
        # Require a meaningful recent cohort before a live alpha-decay veto.
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
