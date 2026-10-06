"""Commit 25 recovery of the missing Commit-19 Champion registry.

Pure/no-I/O contextual router.  It restores ONLY routes that already have
positive frozen IS/OOS evidence in BACKTEST_COMMIT19_RESULT.json.  It never
changes Entry/SL/TP, Safety, leverage, RR, or publication gates.

The registry is deliberately sparse: no Champion authority is extrapolated to
another symbol, timeframe, direction, risk class or asset class merely because
its indicators look similar.  Unsupported cells remain in the normal
Main/Research path.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
import os

VERSION = "COMMIT26_CAUSAL_PREENTRY_CHAMPION_RECOVERY_V1"
COMMIT26_CAUSAL_PREENTRY_ENABLED = str(os.getenv("COMMIT26_CAUSAL_PREENTRY_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}
ENABLED = str(os.getenv("COMMIT25_CONTEXTUAL_AUTHORITY_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v if v is not None else default)
        return x if x == x else float(default)
    except Exception:
        return float(default)


def _truth(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() not in {"", "0", "false", "no", "none", "null", "off"}


def _dir(v: Any) -> str:
    s = _u(v)
    if s in {"LONG", "BUY", "BULLISH", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if s in {"SHORT", "SELL", "BEARISH", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _action(v: Any) -> str:
    d = _dir(v)
    return "LONG" if d == "BULLISH" else "SHORT" if d == "BEARISH" else "NO_OPERAR"


def _first(mapping: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    m = mapping or {}
    for key in keys:
        if key in m and m.get(key) is not None:
            return m.get(key)
    return default


def _risk_class(symbol: str) -> str:
    try:
        from futures_universe import risk_class_for
        return str(risk_class_for(symbol) or "UNKNOWN")
    except Exception:
        return "UNKNOWN"


_MULTI_CLASS = {
    "SPY-USDT": "US_INDEX", "QQQ-USDT": "US_INDEX",
    "CL-USDT": "ENERGY", "NATGAS-USDT": "ENERGY",
    "COPPER-USDT": "INDUSTRIAL_METAL", "XAG-USDT": "PRECIOUS_METAL",
    "KSTR-USDT": "CHINA_INDEX",
}


# Frozen evidence copied from the governed Commit-19 result.  This is metadata
# for routing/provenance; runtime never refits these numbers.
_CHAMPIONS: Dict[str, Dict[str, Any]] = {
    "F30_SHARED_LIQ_SWEEP_MSS_POI_V1": {
        "market": "FUTURES", "symbols": {"BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT", "LINK-USDT"},
        "timeframe": "30M", "action": "DYNAMIC", "required_regime": "ANY", "bank_family": "SWEEP_MSS_POI",
        "execution_family": "SWEEP_MSS_POI", "strategy_id": "F30_SHARED_LIQ_SWEEP_MSS_POI_V1",
        "historical_geometry": {"entry_style": "STRUCTURAL_POI", "sl_mode": "STRUCTURAL_INVALIDATION", "tp_mode": "STRUCTURAL_REACHABLE", "rr": None},
        "evidence": {"is_n": 11, "is_expectancy_r": 0.1547, "is_pf": 1.254, "oos_n": 4, "oos_expectancy_r": 0.9820, "oos_pf": 4.513},
        "source_type": "RAW_COHORT_REPLAY_IN_ZIP",
    },
    "ETH_2H_LONG_RSI_TREND_V1": {
        "market": "FUTURES", "symbols": {"ETH-USDT"}, "timeframe": "2H", "action": "LONG", "required_regime": "TREND_UP",
        "bank_family": "TREND_PULLBACK", "execution_family": "MOMENTUM_CONTINUATION", "strategy_id": "CI_7dc3d4ab4f264a96efbf",
        "historical_geometry": {"entry_style": "NEXT_OPEN", "entry_atr": 0.0, "sl_atr": 2.0, "rr": 2.0},
        "evidence": {"is_n": 40, "is_expectancy_r": 0.08658, "is_pf": 1.1848, "selection_n": 14, "selection_expectancy_r": 0.16459, "selection_pf": 1.4815, "oos_n": 14, "oos_expectancy_r": 0.33306, "oos_pf": 1.9675},
        "source_type": "GOVERNED_RESEARCH_CAUSAL_EVIDENCE",
    },
    "SOL_2H_SHORT_SUPERTREND_PULLBACK_V1": {
        "market": "FUTURES", "symbols": {"SOL-USDT"}, "timeframe": "2H", "action": "SHORT", "required_regime": "TREND_DOWN",
        "bank_family": "TREND_PULLBACK", "execution_family": "TREND_PULLBACK", "strategy_id": "CI_3f4785da4741e4832a55",
        "historical_geometry": {"entry_style": "PULLBACK", "entry_atr": 0.18, "sl_atr": 0.90, "rr": 3.0},
        "evidence": {"is_n": 23, "is_expectancy_r": 0.1015, "is_pf": 1.1378, "selection_n": 8, "selection_expectancy_r": 0.50334, "selection_pf": 1.8731, "oos_n": 8, "oos_expectancy_r": 0.31297, "oos_pf": 1.416},
        "source_type": "GOVERNED_RESEARCH_CAUSAL_EVIDENCE",
    },
    "XRP_2H_SHORT_TREND_CONTINUATION_V1": {
        "market": "FUTURES", "symbols": {"XRP-USDT"}, "timeframe": "2H", "action": "SHORT", "required_regime": "TREND_DOWN",
        "bank_family": "TREND_PULLBACK", "execution_family": "MOMENTUM_CONTINUATION", "strategy_id": "CI_dee44897471478b235ce",
        "historical_geometry": {"entry_style": "NEXT_OPEN", "entry_atr": 0.0, "sl_atr": 1.40, "rr": 3.0},
        "evidence": {"is_n": 52, "is_expectancy_r": 0.11126, "is_pf": 1.2117, "selection_n": 17, "selection_expectancy_r": 0.33056, "selection_pf": 1.8261, "oos_n": 18, "oos_expectancy_r": 0.27854, "oos_pf": 1.5187},
        "source_type": "GOVERNED_RESEARCH_CAUSAL_EVIDENCE",
    },
    "LINK_4H_SHORT_RSI_TREND_V1": {
        "market": "FUTURES", "symbols": {"LINK-USDT"}, "timeframe": "4H", "action": "SHORT", "required_regime": "TREND_DOWN",
        "bank_family": "TREND_PULLBACK", "execution_family": "MOMENTUM_CONTINUATION", "strategy_id": "LINK_4H_SHORT_RSI_TREND_V1",
        "historical_geometry": {"entry_style": "PULLBACK", "entry_atr": 0.18, "sl_atr": 1.15, "rr": 2.0},
        "evidence": {"is_n": 49, "is_expectancy_r": 0.00714, "is_pf": 1.0163, "selection_n": 16, "selection_expectancy_r": 0.54218, "selection_pf": 3.6331, "oos_n": 17, "oos_expectancy_r": 0.27538, "oos_pf": 1.8529},
        "source_type": "GOVERNED_RESEARCH_CAUSAL_EVIDENCE_PARITY_REPAIRED_IN_C19",
    },
    "US_INDEX_1D_TREND_PULLBACK_RR18_V1": {
        "market": "MULTIASSET", "symbols": {"SPY-USDT", "QQQ-USDT"}, "timeframe": "1D", "action": "DYNAMIC", "required_regime": "TREND",
        "asset_class": "US_INDEX", "bank_family": "TREND_PULLBACK", "execution_family": "TREND_PULLBACK", "strategy_id": "US_INDEX_1D_TREND_PULLBACK_RR18_V1",
        "historical_geometry": {"entry_style": "PULLBACK", "sl_mode": "STRUCTURAL_ATR", "rr": 1.8},
        "evidence": {"is_n": 213, "is_expectancy_r": 0.0211, "is_pf": 1.043, "selection_n": 71, "selection_expectancy_r": 0.0130, "selection_pf": 1.030, "oos_n": 72, "oos_expectancy_r": 0.5055, "oos_pf": 2.912},
        "source_type": "PRIOR_INDEPENDENT_PUBLIC_HISTORY_BACKTEST_EVIDENCE",
    },
}


def route_registry() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for cid, spec in _CHAMPIONS.items():
        row = dict(spec)
        row["symbols"] = sorted(spec.get("symbols") or [])
        row["evidence"] = dict(spec.get("evidence") or {})
        row["historical_geometry"] = dict(spec.get("historical_geometry") or {})
        out[cid] = row
    return out


def context_authority_matrix() -> Dict[str, Any]:
    """Explicit anti-extrapolation policy for every production class."""
    return {
        "CRYPTO_CORE": {"live_champions": ["30M_SHARED", "ETH_2H_LONG", "SOL_2H_SHORT", "XRP_2H_SHORT"], "policy": "EXACT_CELL_ONLY"},
        "CRYPTO_MEDIUM": {"live_champions": ["LINK_30M_SHARED", "LINK_4H_SHORT"], "policy": "EXACT_CELL_ONLY"},
        "CRYPTO_HIGH": {"live_champions": [], "policy": "RESEARCH_SHADOW_ONLY_NO_CLEAN_OOS_ROUTE"},
        "US_INDEX": {"live_champions": ["SPY_QQQ_1D_TREND_PULLBACK"], "policy": "EXACT_ASSET_CLASS_AND_TF_ONLY"},
        "ENERGY": {"live_champions": [], "policy": "RESEARCH_SHADOW_ONLY_NO_CLEAN_OOS_ROUTE"},
        "INDUSTRIAL_METAL": {"live_champions": [], "policy": "RESEARCH_SHADOW_ONLY_NO_CLEAN_OOS_ROUTE"},
        "PRECIOUS_METAL": {"live_champions": [], "policy": "RESEARCH_SHADOW_ONLY_NO_CLEAN_OOS_ROUTE"},
        "CHINA_INDEX": {"live_champions": [], "policy": "RESEARCH_SHADOW_ONLY_NO_CLEAN_OOS_ROUTE"},
    }


def _mtf_ok(mtf: Mapping[str, Any] | None, action: str) -> tuple[bool, str]:
    m = dict(mtf or {})
    state = _u(m.get("state") or m.get("alignment") or m.get("status"))

    # Commit 18.2 can identify a structurally valid lower-timeframe transition
    # against the higher timeframe.  The supplied historical replay does not
    # contain enough synchronized HTF/LTF fields to validate that branch OOS, so
    # Commit 26 records it as a research opportunity but deliberately does NOT
    # grant new LIVE Champion authority.
    if state in {"REVERSAL_TRANSITION", "COUNTERTREND_VALID"} and m.get("usable") is True:
        return False, "MTF_STRUCTURAL_TRANSITION_SHADOW_ONLY"

    if m.get("usable") is False or _truth(m.get("conflict")) or _truth(m.get("original_conflict")) or state in {"HARD_CONFLICT", "CONFLICT", "OPPOSITE"}:
        return False, "MTF_HARD_CONFLICT"
    dominant = _dir(m.get("dominant_direction") or m.get("direction"))
    expected = _dir(action)
    if dominant != "NEUTRAL" and expected != "NEUTRAL" and dominant != expected:
        return False, "MTF_DIRECTION_CONFLICT"
    return True, "MTF_OK"


def _live_action(layers: Mapping[str, Any], operational: Mapping[str, Any] | None) -> str:
    op = dict(operational or {})
    thesis = dict(op.get("thesis") or {})
    for raw in (thesis.get("action"), thesis.get("direction"), op.get("candidate_action")):
        a = _action(raw)
        if a in {"LONG", "SHORT"}:
            return a
    trend = dict(layers.get("trend") or {})
    momentum = dict(layers.get("momentum") or {})
    structure = dict(layers.get("structure") or {})
    dirs = [_dir(trend.get("direction")), _dir(momentum.get("direction")), _dir(structure.get("direction") or structure.get("structure_direction"))]
    bulls = sum(x == "BULLISH" for x in dirs)
    bears = sum(x == "BEARISH" for x in dirs)
    if bulls >= 2 and bears == 0:
        return "LONG"
    if bears >= 2 and bulls == 0:
        return "SHORT"
    return "NO_OPERAR"


def _trend_direction(layers: Mapping[str, Any]) -> str:
    return _dir((layers.get("trend") or {}).get("direction"))


def _momentum_direction(layers: Mapping[str, Any]) -> str:
    return _dir((layers.get("momentum") or {}).get("direction"))


def _rsi(layers: Mapping[str, Any]) -> Optional[float]:
    m = layers.get("momentum") or {}
    v = _first(m, "rsi", "rsi_14", "rsi_value")
    if v is None:
        v = _first(layers.get("indicators") or {}, "rsi", "rsi_14")
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _adx(layers: Mapping[str, Any]) -> Optional[float]:
    t = layers.get("trend") or {}
    v = _first(t, "adx", "adx_value")
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _volume_ratio(layers: Mapping[str, Any]) -> Optional[float]:
    for block in (layers.get("volume") or {}, layers.get("market_microstructure") or {}, layers.get("structure") or {}):
        v = _first(block, "volume_ratio", "relative_volume", "vol_ratio")
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return None


def _typed_event_matches(events: Any, expected: str) -> bool:
    """Return True only when a typed structure event points in the candidate direction."""
    if isinstance(events, Mapping):
        events = [events]
    if not isinstance(events, (list, tuple)):
        return False
    for event in events:
        if not isinstance(event, Mapping):
            continue
        side = _dir(event.get("type") or event.get("direction") or event.get("side"))
        if side == expected:
            return True
    return False


def _reaction_inventory_available(structure: Mapping[str, Any], expected: str) -> bool:
    """Check only already-observed reaction inventory; never invent a POI."""
    s = dict(structure or {})
    if _typed_event_matches(s.get("liquidity_sweeps"), expected):
        return True
    if _typed_event_matches(s.get("stop_hunts"), expected):
        return True
    if _typed_event_matches(s.get("order_blocks"), expected):
        return True
    if _typed_event_matches(s.get("fair_value_gaps"), expected):
        return True
    # A confirmed pivot/support-resistance inventory is also a legitimate input
    # for the downstream reaction-zone engine.  This is inventory only; the
    # actual Entry is still selected later and can still fail the normal gates.
    if expected == "BULLISH" and (s.get("nearest_support") or s.get("pivot_lows") or s.get("supports")):
        return True
    if expected == "BEARISH" and (s.get("nearest_resistance") or s.get("pivot_highs") or s.get("resistances")):
        return True
    return False


def _legacy_postentry_structure_trigger(layers: Mapping[str, Any], action: str) -> bool:
    """Compatibility path for fixtures/snapshots that already expose post-Entry fields.

    Production pre-Entry structure normally does NOT expose MSS/displacement as
    top-level keys, so Commit 26 does not depend on this path.
    """
    s = dict(layers.get("structure") or {})
    expected = _dir(action)
    sdir = _dir(s.get("direction") or s.get("structure_direction"))
    if sdir not in {"NEUTRAL", expected}:
        return False
    sweep = _truth(_first(s, "liquidity_sweep", "sweep")) or _typed_event_matches(s.get("liquidity_sweeps"), expected)
    mss = _truth(_first(s, "mss", "bos", "market_structure_shift", "break_of_structure"))
    displacement = _truth(_first(s, "displacement", "displacement_confirmed"))
    poi = _truth(_first(s, "order_blocks", "fair_value_gaps", "fvg", "poi", "institutional_zone"))
    return bool((sweep and mss) or (displacement and poi))


def _preentry_structure_audit(layers: Mapping[str, Any], action: str) -> tuple[bool, str]:
    """Causal pre-Entry structural gate for the 30m governed route.

    Commit 25 requested MSS/displacement before Entry selection, while the real
    structure layer exposes those confirmations later through Entry levels.
    That made the governed 30m route unreachable with the real pre-Entry schema.

    Commit 26 therefore consumes only evidence that *exists at this stage*:
    - strict closed-candle Structure direction;
    - a recent primary Structure event encoded by analyze_price_structure_layer;
    - an observed reaction-zone inventory for the downstream Entry engine.

    It does NOT create direction, Entry, SL, TP, Safety or publication authority.
    Exact MSS/displacement/reaction quality remain downstream execution evidence.
    """
    if not COMMIT26_CAUSAL_PREENTRY_ENABLED:
        ok = _legacy_postentry_structure_trigger(layers, action)
        return ok, "COMMIT26_DISABLED_LEGACY_STRUCTURE_TRIGGER" if ok else "F30_PRIMARY_STRUCTURE_TRIGGER_MISSING"

    s = dict(layers.get("structure") or {})
    expected = _dir(action)
    structure_direction = _dir(s.get("direction") or s.get("structure_direction"))

    # Preserve compatibility with already-enriched snapshots/tests. This is not
    # the primary production path, but avoids breaking closed snapshots that do
    # legitimately carry these confirmations.
    if _legacy_postentry_structure_trigger(layers, action):
        return True, "F30_ENRICHED_STRUCTURE_CONFIRMATION"

    if expected == "NEUTRAL" or structure_direction != expected:
        return False, "F30_STRICT_STRUCTURE_DIRECTION_MISMATCH"

    raw_reasons = s.get("structure_reasons") or []
    if isinstance(raw_reasons, str):
        raw_reasons = [raw_reasons]
    reasons = [str(x or "").strip().upper() for x in raw_reasons]
    primary = any(
        reason.startswith(("SWEEP_REJECTION:", "STOP_HUNT_RECOVERY:", "BOS_CLOSE:"))
        for reason in reasons
    )
    if not primary:
        return False, "F30_STRICT_CLOSED_CANDLE_EVENT_MISSING"

    if not _reaction_inventory_available(s, expected):
        return False, "F30_REACTION_INVENTORY_MISSING"

    return True, "F30_CAUSAL_PREENTRY_STRUCTURE_CONFIRMED"


def _structural_trigger(layers: Mapping[str, Any], action: str = "") -> bool:
    """Boolean compatibility wrapper used by older tests/callers."""
    ok, _ = _preentry_structure_audit(layers, action or _action((layers.get("structure") or {}).get("direction")))
    return bool(ok)


def _pullback_evidence(layers: Mapping[str, Any], operational: Mapping[str, Any] | None) -> bool:
    blob = " ".join(str(x or "") for x in (
        (operational or {}).get("default_strategy"), layers.get("structure"), layers.get("trend"), layers.get("momentum")
    )).upper()
    return any(k in blob for k in ("PULLBACK", "RETEST", "ORDER_BLOCK", "ORDER BLOCK", "POI", "FVG"))


def _route_live_evidence(spec: Mapping[str, Any], layers: Mapping[str, Any], operational: Mapping[str, Any] | None, action: str, regime: str) -> tuple[bool, str]:
    trend = _trend_direction(layers)
    momentum = _momentum_direction(layers)
    expected = _dir(action)
    rsi = _rsi(layers)
    cid = str(spec.get("strategy_id") or "")

    # All live Champions require live direction/trend consistency.  Neutral
    # momentum is allowed; explicit opposite momentum is not.
    if trend != expected:
        return False, "LIVE_TREND_NOT_ALIGNED"
    if momentum not in {"NEUTRAL", expected}:
        return False, "LIVE_MOMENTUM_CONFLICT"

    if cid == "F30_SHARED_LIQ_SWEEP_MSS_POI_V1":
        adx, vr = _adx(layers), _volume_ratio(layers)
        if adx is None or adx < 20.0:
            return False, "F30_ADX_BELOW_BACKTEST_CONTRACT"
        if vr is None or vr < 1.20:
            return False, "F30_VOLUME_BELOW_BACKTEST_CONTRACT"
        if rsi is None:
            return False, "F30_RSI_MISSING"
        if action == "LONG" and rsi > 80.0:
            return False, "F30_RSI_LONG_CHASE"
        if action == "SHORT" and rsi < 20.0:
            return False, "F30_RSI_SHORT_CHASE"
        structure_ok, structure_reason = _preentry_structure_audit(layers, action)
        if not structure_ok:
            return False, structure_reason
        return True, "F30_BACKTESTED_CONTEXT_AND_CAUSAL_PREENTRY_CONFIRMED"

    family = _u(spec.get("execution_family") or spec.get("bank_family"))
    if "MOMENTUM" in family or "CONTINUATION" in family:
        if rsi is None:
            return False, "RSI_MISSING"
        if action == "LONG" and rsi < 50.0:
            return False, "RSI_NOT_CONFIRMING_LONG"
        if action == "SHORT" and rsi > 50.0:
            return False, "RSI_NOT_CONFIRMING_SHORT"
    if "PULLBACK" in family:
        # A structural retest/POI is preferred when exposed by the live engine.
        # SOL's causal rule specifically allows RSI <=52 for SHORT.
        if rsi is not None and action == "SHORT" and rsi > 52.0:
            return False, "PULLBACK_RSI_NOT_CONFIRMING_SHORT"
        if rsi is not None and action == "LONG" and rsi < 48.0:
            return False, "PULLBACK_RSI_NOT_CONFIRMING_LONG"
        if spec.get("market") == "MULTIASSET" and not _pullback_evidence(layers, operational):
            return False, "US_INDEX_PULLBACK_EVIDENCE_MISSING"
    return True, "EXACT_CHAMPION_LIVE_CONTEXT_CONFIRMED"


def _no_match(symbol: str, timeframe: str, market: str, asset_class: str, reason: str) -> Dict[str, Any]:
    return {
        "matched": False, "eligible_for_execution_routing": False, "reason": reason,
        "symbol": symbol, "timeframe": timeframe, "market": market,
        "risk_class": _risk_class(symbol), "asset_class": asset_class,
        "authority": "RESEARCH_OR_BASE_ENGINE_ONLY",
        "version": VERSION,
    }


def resolve_champion(
    *, layers: Mapping[str, Any], symbol: Any, timeframe: Any, system_type: Any,
    regime: Any = None, volatility: Any = None, mtf_relation: Mapping[str, Any] | None = None,
    operational: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    sym, tf = _u(symbol), _u(timeframe)
    st = _u(system_type)
    if not ENABLED:
        asset_class = _MULTI_CLASS.get(sym, "")
        market = "MULTIASSET" if asset_class else "FUTURES" if st == "FUTURES" else st
        return _no_match(sym, tf, market, asset_class, "COMMIT25_CONTEXTUAL_AUTHORITY_DISABLED")
    asset_class = _MULTI_CLASS.get(sym, "")
    market = "MULTIASSET" if asset_class else "FUTURES" if st == "FUTURES" else st
    if market not in {"FUTURES", "MULTIASSET"}:
        return _no_match(sym, tf, market, asset_class, "MARKET_NOT_IN_COMMIT25_CHAMPION_SCOPE")

    macro = dict(layers.get("macro_context") or {})
    if _u(macro.get("risk_level") or macro.get("current_risk_level")) == "CRITICAL":
        return _no_match(sym, tf, market, asset_class, "CRITICAL_MACRO_RISK")

    live_action = _live_action(layers, operational)
    if live_action not in {"LONG", "SHORT"}:
        return _no_match(sym, tf, market, asset_class, "NO_UNAMBIGUOUS_LIVE_DIRECTION")

    mtf_ok, mtf_reason = _mtf_ok(mtf_relation, live_action)
    if not mtf_ok:
        return _no_match(sym, tf, market, asset_class, mtf_reason)

    reg = _u(regime or ((operational or {}).get("context") or {}).get("regime"))
    vol = _u(volatility or ((operational or {}).get("context") or {}).get("volatility"))

    for champion_id, raw in _CHAMPIONS.items():
        spec = dict(raw)
        if sym not in set(spec.get("symbols") or ()) or tf != _u(spec.get("timeframe")):
            continue
        if _u(spec.get("market")) != market:
            continue
        if spec.get("asset_class") and _u(spec.get("asset_class")) != _u(asset_class):
            continue
        fixed = _u(spec.get("action"))
        action = live_action if fixed == "DYNAMIC" else fixed
        if action != live_action:
            continue
        required_regime = _u(spec.get("required_regime"))
        if required_regime == "TREND" and reg not in {"TREND_UP", "TREND_DOWN"}:
            continue
        if required_regime not in {"", "ANY", "ALL", "TREND"} and reg != required_regime:
            continue

        evidence_ok, live_reason = _route_live_evidence(spec, layers, operational, action, reg)
        if not evidence_ok:
            return _no_match(sym, tf, market, asset_class, live_reason)

        evidence = dict(spec.get("evidence") or {})
        out = {
            **spec,
            "symbols": sorted(spec.get("symbols") or []),
            "champion_id": champion_id,
            "matched": True,
            "eligible_for_execution_routing": True,
            "authority": "LIVE_CHAMPION_COMMIT19",
            "state": "LIVE_CHAMPION",
            "action": action,
            "direction": _dir(action),
            "symbol": sym,
            "timeframe": tf,
            "regime": reg,
            "volatility": vol,
            "risk_class": _risk_class(sym),
            "asset_class": asset_class,
            "evidence": evidence,
            "historical_geometry": dict(spec.get("historical_geometry") or {}),
            "decay_key": f"C19CHAMP::{champion_id}::{sym}::{tf}::{action}",
            "research_handoff_key": f"RESEARCH::{market}::{sym}::{tf}::{action}::{champion_id}",
            "live_context_reason": live_reason,
            "mtf_state": mtf_reason,
            "version": VERSION,
            "anti_extrapolation": True,
        }
        return out

    return _no_match(sym, tf, market, asset_class, "NO_POSITIVE_IS_OOS_CHAMPION_FOR_EXACT_CELL")


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "enabled": ENABLED,
        "champions": len(_CHAMPIONS),
        "network_calls": 0,
        "db_reads": 0,
        "threads": 0,
        "llm_calls": 0,
        "anti_extrapolation": True,
        "causal_preentry_enabled": COMMIT26_CAUSAL_PREENTRY_ENABLED,
        "new_market_data_requests": 0,
        "new_supabase_queries": 0,
        "new_llm_calls": 0,
        "new_background_threads": 0,
        "context_authority": context_authority_matrix(),
    }
