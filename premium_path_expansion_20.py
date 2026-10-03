"""Commit 20 — Premium Path Expansion (PPE).

Objective
---------
Increase the number of *genuine* paths that can reach the existing Premium
contract without weakening any Premium threshold, creating direction, adding
network calls, or promoting fallback geometry.

PPE is intentionally bounded:
- at most two alternate execution routes are tested after the native geometry;
- alternatives reuse already-computed market data;
- no new worker/thread/poll/API is created;
- the baseline geometry always remains eligible to win if it is stronger;
- fallback geometry remains non-Premium.

The module also adds a diagnostic funnel and fixes Saved Signals so Multi-Asset
can use its own candle provider instead of the Futures perpetual provider.
"""
from __future__ import annotations

import copy
import math
from functools import wraps
from typing import Any, Dict, Iterable, List, Mapping, Optional

VERSION = "COMMIT20_1_PREMIUM_PATH_EXPANSION_FIX_V1"
MAX_ALTERNATIVE_ROUTES = 2
MAX_ALTERNATIVE_ROUTES_PRESSURE = 1
PPE_ROUTE_EXPANSION_MAX_RSS_MB = 215.0
PPE_ROUTE_EXPANSION_PRESSURE_RSS_MB = 185.0

# Existing hard publication contract. PPE never changes these values.
PREMIUM_MIN_SAFETY = 75.0
PREMIUM_MIN_TP = 55.0
PREMIUM_MIN_SL = 60.0
PREMIUM_MIN_RR = 1.8
PREMIUM_MAX_RR = 3.5

# Routes are not votes. They are execution-geometry hypotheses for an already
# selected direction. Names are deliberately aligned with the strategy bank /
# execution geometry contracts already present in the repository.
ROUTE_ORDER = (
    "LIQUIDITY_SWEEP_MSS_POI",
    "TREND_PULLBACK",
    "BREAKOUT_RETEST",
    "STRUCTURE_RETEST",
    "COMPRESSION_EXPANSION",
    "VWAP_SESSION_PULLBACK",
    "MEAN_REVERSION_SELECTIVE",
    "VOLATILITY_RETEST",
    "POST_EVENT_CONFIRMATION",
    "ASIA_SESSION_RETEST",
)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _rss_mb() -> Optional[float]:
    try:
        import app as app_module
        fn = getattr(app_module, "_process_rss_mb", None)
        value = fn() if callable(fn) else None
        return float(value) if value is not None else None
    except Exception:
        return None


def _memory_safe_route_budget() -> int:
    """Bound route expansion by live RSS without changing publication gates."""
    rss = _rss_mb()
    if rss is None:
        return MAX_ALTERNATIVE_ROUTES
    if rss >= PPE_ROUTE_EXPANSION_MAX_RSS_MB:
        return 0
    if rss >= PPE_ROUTE_EXPANSION_PRESSURE_RSS_MB:
        return MAX_ALTERNATIVE_ROUTES_PRESSURE
    return MAX_ALTERNATIVE_ROUTES


def _regime(*blobs: Any) -> str:
    text = " ".join(str(x or "").upper() for x in blobs if x is not None)
    for key in ("TRENDING_BULL", "TRENDING_BEAR", "TREND_UP", "TREND_DOWN", "RANGING", "BALANCE", "RANGE", "COMPRESSION", "HIGH_VOLATILITY"):
        if key in text:
            return key
    return "UNKNOWN"


def _route_families(
    *,
    setup_family: str,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    volatility: Mapping[str, Any],
    structure: Mapping[str, Any],
    symbol: str,
    timeframe: str,
    market_type: str,
) -> List[str]:
    """Return max two alternative routes supported by already-observed context."""
    setup = str(setup_family or "").upper()
    blob = " ".join(
        str(x or "").upper()
        for x in (
            structure.get("setup_family"),
            structure.get("_strategy_family"),
            structure.get("_validated_strategy_route"),
            structure.get("_contingency_playbook"),
        )
    )
    regime = _regime(
        trend.get("regime"),
        structure.get("regime"),
        structure.get("market_regime"),
        volatility.get("state"),
        volatility.get("regime"),
        blob,
    )
    vol_state = str(volatility.get("state") or volatility.get("volatility_state") or "").upper()
    sweeps = bool(structure.get("liquidity_sweeps") or structure.get("liquidity_sweep") or structure.get("sweep"))
    mss = bool(structure.get("mss") or structure.get("bos") or structure.get("market_structure_shift") or " MSS " in f" {blob} ")
    displacement = bool(structure.get("displacement") or structure.get("displacement_confirmed") or "DISPLACEMENT" in blob)
    poi = bool(
        structure.get("order_blocks")
        or structure.get("fair_value_gaps")
        or structure.get("fvg")
        or structure.get("volume_profile")
        or structure.get("nearest_support")
        or structure.get("nearest_resistance")
    )
    squeeze = bool(
        structure.get("squeeze_on")
        or volatility.get("squeeze_on")
        or "SQUEEZE" in blob
        or "COMPRESSION" in blob
    )
    adx = _f(trend.get("adx"), 20.0)
    rsi = _f(momentum.get("rsi"), 50.0)
    direction = _u(structure.get("direction") or trend.get("direction"))
    atr_pct = _f(volatility.get("atr_pct"), 0.0)

    routes: List[str] = []

    # Highest informational value first: liquidity event -> structural retest.
    if sweeps and (mss or displacement) and poi:
        routes.extend(["LIQUIDITY_SWEEP_MSS_POI", "STRUCTURE_RETEST"])

    # Compression gets its own route before generic breakout.
    if squeeze or vol_state in {"COMPRESSION", "EXPANSION"}:
        routes.extend(["COMPRESSION_EXPANSION", "BREAKOUT_RETEST"])

    # Trend route: give the execution committee another structurally distinct
    # pullback/retest interpretation of the same direction.
    if regime in {"TRENDING_BULL", "TRENDING_BEAR", "TREND_UP", "TREND_DOWN"} or adx >= 24:
        routes.extend(["TREND_PULLBACK", "BREAKOUT_RETEST"])

    # Balance route: value/mean reversion only when context says balance. It
    # never creates a reversal by itself.
    if regime in {"RANGING", "BALANCE", "RANGE"}:
        routes.extend(["MEAN_REVERSION_SELECTIVE", "VWAP_SESSION_PULLBACK"])
        if abs(rsi - 50.0) >= 8.0:
            routes.append("LIQUIDITY_SWEEP_MSS_POI")

    # High-volatility conditions can often benefit from a retest geometry that
    # uses the same direction but changes where the Entry/SL package is placed.
    if atr_pct > 0 and atr_pct >= 2.5:
        routes.extend(["VOLATILITY_RETEST", "STRUCTURE_RETEST"])

    # Multi-Asset session-aware alternatives are only chosen from already known
    # route labels; no new market-data request is introduced.
    if str(market_type).lower() == "multiasset":
        sym = _u(symbol)
        if sym == "KSTR-USDT":
            routes.extend(["ASIA_SESSION_RETEST", "BREAKOUT_RETEST"])
        elif sym in {"CL-USDT", "NATGAS-USDT"}:
            routes.extend(["POST_EVENT_CONFIRMATION", "VOLATILITY_RETEST"])
        elif sym in {"SPY-USDT", "QQQ-USDT"}:
            routes.extend(["VWAP_SESSION_PULLBACK", "BREAKOUT_RETEST"])
        elif sym == "XAG-USDT":
            routes.extend(["TREND_PULLBACK", "STRUCTURE_RETEST"])

    # If no context-specific route was found, use the existing setup bank as a
    # bounded fallback for geometry exploration, never as publication authority.
    if not routes:
        routes.extend(["TREND_PULLBACK", "BREAKOUT_RETEST"])

    out: List[str] = []
    for route in routes:
        route = str(route or "").upper()
        if route == setup:
            continue
        if route not in ROUTE_ORDER:
            continue
        if route not in out:
            out.append(route)
        if len(out) >= MAX_ALTERNATIVE_ROUTES:
            break
    return out


def _geometry_score(levels: Mapping[str, Any]) -> float:
    """Bounded quality score for comparing geometry packages only.

    This is not a probability, not a Premium gate, and not an alternative source
    of authority. It only chooses the strongest geometry already produced by
    the native execution committee.
    """
    entry = _f(levels.get("entry_score") or levels.get("entry_quality_score"), 0.0)
    sl = _f(levels.get("sl_reliability"), 0.0)
    if sl <= 1.0:
        sl *= 100.0
    tp = _f(levels.get("tp_quality_score"), 0.0)
    rr = _f(levels.get("risk_reward"), 0.0)
    rr_score = 0.0
    if PREMIUM_MIN_RR <= rr <= PREMIUM_MAX_RR:
        # Peak softly around 2.3R; do not reward extreme targets.
        rr_score = 100.0 - min(45.0, abs(rr - 2.3) * 22.0)
    elif rr > 0:
        rr_score = max(0.0, 68.0 - abs(rr - 2.3) * 18.0)
    gq = _f(levels.get("execution_geometry_quality"), 0.0)
    if gq > 0:
        return round(max(0.0, min(100.0, 0.26 * entry + 0.26 * sl + 0.28 * tp + 0.10 * rr_score + 0.10 * gq)), 3)
    return round(max(0.0, min(100.0, 0.30 * entry + 0.30 * sl + 0.30 * tp + 0.10 * rr_score)), 3)


def _needs_route_expansion(levels: Mapping[str, Any]) -> bool:
    entry = _f(levels.get("entry_score") or levels.get("entry_quality_score"), 0.0)
    sl = _f(levels.get("sl_reliability"), 0.0)
    if sl <= 1.0:
        sl *= 100.0
    tp = _f(levels.get("tp_quality_score"), 0.0)
    rr = _f(levels.get("risk_reward"), 0.0)
    fallback = bool(levels.get("manual_geometry_fallback") or levels.get("opportunity_recovery_applied"))
    hard_miss = bool(rr > 0 and (rr < PREMIUM_MIN_RR or rr > PREMIUM_MAX_RR))
    return fallback or entry < 82.0 or sl < 72.0 or tp < 72.0 or hard_miss


def _market_type_for_symbol(symbol: str) -> str:
    sym = _u(symbol)
    try:
        from multiasset_system import MULTIASSET_SYMBOLS
        if sym in set(MULTIASSET_SYMBOLS or {}):
            return "multiasset"
    except Exception:
        pass
    return "futures" if sym else "unknown"


def _clone_route_structure(structure: Mapping[str, Any], route: str) -> Dict[str, Any]:
    out = dict(structure or {})
    pb = dict(out.get("_contingency_playbook") or {})
    pb["setup_family"] = route
    pb["strategy_route_source"] = "COMMIT20_PPE"
    out["_contingency_playbook"] = pb
    # Expose the route to the existing execution geometry layer without adding
    # a new data source.
    out["setup_family"] = route
    out["_ppe_route_candidate"] = route
    return out


def _route_candidate_payload(levels: Mapping[str, Any], route: str, score: float) -> Dict[str, Any]:
    return {
        "route": route,
        "geometry_score": round(score, 3),
        "entry": levels.get("entry"),
        "stop_loss": levels.get("stop_loss"),
        "take_profit": levels.get("take_profit"),
        "risk_reward": levels.get("risk_reward"),
        "entry_score": levels.get("entry_score"),
        "sl_quality": round((_f(levels.get("sl_reliability"), 0.0) * 100.0), 2) if _f(levels.get("sl_reliability"), 0.0) <= 1.0 else _f(levels.get("sl_reliability"), 0.0),
        "tp_quality": levels.get("tp_quality_score"),
        "fallback": bool(levels.get("manual_geometry_fallback") or levels.get("opportunity_recovery_applied")),
    }


def _run_alternative_geometry(original, self, decision, trend, momentum, volatility, alt_structure, symbol, timeframe, liquidation, execution_observations):
    """Re-run only the local geometry calculator; suppress repeated option-provider calls.
    Marker: _commit20_1_route_shadow.

    Commit 20.1 fixes the main free-RAM regression introduced by bounded route
    expansion: the original Entry routine may consult the external crypto
    options context when called without an option-chain snapshot. Alternative
    geometry is comparative only, so it must never trigger a new provider call.
    """
    alt = dict(alt_structure or {})
    alt["_commit20_1_route_shadow"] = True
    try:
        # The existing engine reads the option-chain from execution observations
        # when available. For a route comparison we intentionally pass an empty
        # observed chain and let the existing market-maker layer remain shadow.
        local_obs = dict(execution_observations or {}) if isinstance(execution_observations, dict) else {}
        if not local_obs.get("option_chain"):
            local_obs["option_chain"] = []
        return original(
            self, decision, dict(trend or {}), dict(momentum or {}),
            dict(volatility or {}), alt, symbol, timeframe,
            liquidation=liquidation, execution_observations=local_obs,
        )
    finally:
        alt.clear()


def install_geometry_router() -> Dict[str, Any]:
    """Patch TradingExpertSystem.calculate_entry_levels with bounded alternatives."""
    try:
        import app as app_module
        cls = getattr(app_module, "TradingExpertSystem", None)
        original = getattr(cls, "calculate_entry_levels", None) if cls else None
        if not callable(original):
            return {"installed": False, "reason": "LEVEL_METHOD_NOT_FOUND"}
        if getattr(original, "_commit20_ppe", False):
            return {"installed": True, "already": True}

        @wraps(original)
        def wrapped(self, decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation=None, execution_observations=None):
            baseline = original(
                self, decision, trend, momentum, volatility, structure, symbol, timeframe,
                liquidation=liquidation, execution_observations=execution_observations,
            )
            if not isinstance(baseline, dict):
                return baseline
            if _u(decision) not in {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}:
                return baseline

            market_type = _market_type_for_symbol(symbol)
            is_multi = market_type == "multiasset"
            is_futures = _u(decision) in {"LONG", "SHORT"}
            # Spot remains stable by default; PPE's extra search is reserved for
            # the routes where the observed frequency problem currently exists.
            if not (is_futures or is_multi):
                baseline["ppe_version"] = VERSION
                baseline["ppe_route_expansion"] = False
                baseline["ppe_selected_route"] = str(((structure or {}).get("_contingency_playbook") or {}).get("setup_family") or "UNSPECIFIED")
                return baseline
            if not _needs_route_expansion(baseline):
                baseline["ppe_version"] = VERSION
                baseline["ppe_route_expansion"] = False
                baseline["ppe_selected_route"] = str(((structure or {}).get("_contingency_playbook") or {}).get("setup_family") or "UNSPECIFIED")
                return baseline

            route_budget = _memory_safe_route_budget()
            if route_budget <= 0:
                baseline["ppe_version"] = VERSION
                baseline["ppe_route_expansion"] = False
                baseline["ppe_route_expansion_skipped"] = "MEMORY_PRESSURE"
                baseline["ppe_route_expansion_rss_mb"] = _rss_mb()
                baseline["ppe_route_candidates"] = []
                return baseline

            setup = str(
                ((structure or {}).get("_contingency_playbook") or {}).get("setup_family")
                or (structure or {}).get("setup_family")
                or "UNSPECIFIED"
            ).upper()
            routes = _route_families(
                setup_family=setup,
                trend=trend or {}, momentum=momentum or {}, volatility=volatility or {},
                structure=structure or {}, symbol=symbol, timeframe=timeframe, market_type=market_type,
            )
            if not routes:
                baseline["ppe_version"] = VERSION
                baseline["ppe_route_expansion"] = False
                baseline["ppe_route_candidates"] = []
                return baseline

            candidates = [{
                "route": setup or "BASELINE",
                "levels": baseline,
                "geometry_score": _geometry_score(baseline),
            }]
            route_meta = [_route_candidate_payload(baseline, setup or "BASELINE", candidates[0]["geometry_score"])]

            for route in routes[:route_budget]:
                try:
                    alt_structure = _clone_route_structure(structure or {}, route)
                    alt_levels = _run_alternative_geometry(
                        original, self, decision, trend, momentum, volatility,
                        alt_structure, symbol, timeframe, liquidation, execution_observations,
                    )
                    if not isinstance(alt_levels, dict):
                        continue
                    # Never let a route that fabricated an invalid package replace
                    # the baseline. Hard geometry sanity is checked here only.
                    entry = _f(alt_levels.get("entry"), 0)
                    sl = _f(alt_levels.get("stop_loss"), 0)
                    tp = _f(alt_levels.get("take_profit"), 0)
                    rr = _f(alt_levels.get("risk_reward"), 0)
                    if not (entry > 0 and sl > 0 and tp > 0 and rr > 0):
                        continue
                    score = _geometry_score(alt_levels)
                    candidates.append({"route": route, "levels": alt_levels, "geometry_score": score})
                    route_meta.append(_route_candidate_payload(alt_levels, route, score))
                except Exception as exc:
                    route_meta.append({"route": route, "error": type(exc).__name__})
                finally:
                    try:
                        import gc
                        gc.collect()
                    except Exception:
                        pass

            candidates.sort(key=lambda row: (-float(row["geometry_score"]), 0 if row["route"] == setup else 1))
            selected = candidates[0]
            out = dict(selected["levels"])
            out["ppe_version"] = VERSION
            out["ppe_route_expansion"] = len(candidates) > 1
            out["ppe_base_route"] = setup or "UNSPECIFIED"
            out["ppe_selected_route"] = selected["route"]
            out["ppe_route_candidates"] = route_meta[:MAX_ALTERNATIVE_ROUTES + 1]
            out["ppe_geometry_score"] = float(selected["geometry_score"])
            out["ppe_alternative_route_count"] = max(0, len(candidates) - 1)
            out["ppe_route_authority"] = "EXECUTION_GEOMETRY_COMPARISON_ONLY"
            # A route is not a vote. Only the selected package is passed onward.
            return out

        wrapped._commit20_ppe = True
        cls.calculate_entry_levels = wrapped
        return {"installed": True, "already": False, "max_alternative_routes": MAX_ALTERNATIVE_ROUTES}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def _champion_cell(levels: Mapping[str, Any], symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    setup = str(levels.get("ppe_selected_route") or levels.get("setup_family") or "UNSPECIFIED").upper()
    route = levels.get("validated_strategy_route") or levels.get("research_evidence") or levels.get("commit19_champion") or {}
    authority = "UNVERIFIED"
    state = "GAP_OR_RESEARCH"
    if isinstance(route, Mapping):
        raw_state = str(route.get("state") or route.get("status") or route.get("authority") or "").upper()
        if "CHAMPION" in raw_state or raw_state in {"LIVE", "LIVE_CHAMPION"}:
            authority = raw_state
            state = "LIVE_CHAMPION"
        elif raw_state:
            authority = raw_state[:80]
    cell_id = f"{_u(levels.get('market_type') or 'FUTURES')}|{_u(symbol)}|{str(timeframe).upper()}|{_u(action)}|{_u(setup)}"
    return {
        "cell_id": cell_id,
        "state": state,
        "authority": authority,
        "source": "COMMIT20_DIAGNOSTIC_REGISTRY",
    }


def _funnel(result: Mapping[str, Any], levels: Mapping[str, Any], symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    gate = dict(result.get("futures_publication_gate") or {})
    codes = [str(x).upper() for x in (gate.get("reason_codes") or [])]
    stage = "PREMIUM"
    primary = True
    if levels.get("manual_geometry_fallback") or levels.get("manual_geometry_authority") == "USER_MANUAL_ANALYSIS_ONLY":
        primary = False
    if "LOSS_AT_SL" in codes or "ATR_STRESS" in codes:
        stage = "ECONOMIC_RISK"
    elif "RR" in codes:
        stage = "RR"
    elif "SL_QUALITY" in codes:
        stage = "SL_QUALITY"
    elif "TP_QUALITY" in codes:
        stage = "TP_QUALITY"
    elif "SAFETY" in codes:
        stage = "SAFETY"
    else:
        cpqe = result.get("cpqe_19_2_4") or {}
        if cpqe and not cpqe.get("qualifying", False):
            stage = "CPQE_FAIL"
        elif not gate.get("eligible", False):
            stage = "PUBLICATION_GATE"
    champion = _champion_cell(levels, symbol, timeframe, action)
    return {
        "version": VERSION,
        "stage": stage,
        "reason_codes": codes,
        "reached_publication_gate": bool(gate),
        "premium": bool(gate.get("eligible")),
        "primary_geometry": bool(primary),
        "fallback_geometry": bool(not primary),
        "selected_route": str(levels.get("ppe_selected_route") or levels.get("setup_family") or "UNSPECIFIED"),
        "alternative_route_count": int(levels.get("ppe_alternative_route_count") or 0),
        "champion": champion,
    }


def install_gate_diagnostics() -> Dict[str, Any]:
    try:
        import futures_system
        patched = []
        for cls_name in ("FuturesAnalysis",):
            cls = getattr(futures_system, cls_name, None)
            original = getattr(cls, "_apply_futures_publication_gate", None) if cls else None
            if not callable(original):
                continue
            if getattr(original, "_commit20_ppe_gate", False):
                patched.append({"class": cls_name, "already": True})
                continue

            @wraps(original)
            def wrapped(self, levels, timeframe, symbol="", action="", _original=original):
                out = _original(self, levels, timeframe, symbol=symbol, action=action)
                if not isinstance(out, dict):
                    return out
                try:
                    lv = dict(out.get("levels") or levels or {})
                    funnel = _funnel(out, lv, symbol, timeframe, action)
                    gate = dict(out.get("futures_publication_gate") or {})
                    gate["commit20_premium_funnel"] = funnel
                    gate["premium_path_expansion_version"] = VERSION
                    out["futures_publication_gate"] = gate
                    out["premium_path_expansion_20"] = funnel
                    out["premium_blocker_codes"] = list(funnel.get("reason_codes") or [])
                    out["premium_blocker_stage"] = funnel.get("stage")
                    out["premium_route"] = funnel.get("selected_route")
                    # Keep a compact, safe diagnostic string for the frontend.
                    if not funnel.get("premium"):
                        out["premium_blocker"] = "; ".join(funnel.get("reason_codes") or []) or funnel.get("stage")
                    return out
                except Exception as exc:
                    out["premium_path_expansion_20"] = {"version": VERSION, "stage": "DIAGNOSTIC_ERROR", "error": type(exc).__name__}
                    return out

            wrapped._commit20_ppe_gate = True
            cls._apply_futures_publication_gate = wrapped
            patched.append({"class": cls_name, "already": False})

        # Multi-Asset subclasses FuturesAnalysis. Patch explicitly as well so
        # the diagnostic contract remains visible if inheritance changes later.
        try:
            import multiasset_system
            mcls = getattr(multiasset_system, "MultiAssetAnalysis", None)
            original = getattr(mcls, "_apply_futures_publication_gate", None) if mcls else None
            if callable(original) and not getattr(original, "_commit20_ppe_gate", False):
                @wraps(original)
                def multi_wrapped(self, levels, timeframe, symbol="", action="", _original=original):
                    out = _original(self, levels, timeframe, symbol=symbol, action=action)
                    if not isinstance(out, dict):
                        return out
                    try:
                        lv = dict(out.get("levels") or levels or {})
                        funnel = _funnel(out, lv, symbol, timeframe, action)
                        funnel["market"] = "MULTIASSET"
                        gate = dict(out.get("futures_publication_gate") or {})
                        gate["commit20_premium_funnel"] = funnel
                        gate["premium_path_expansion_version"] = VERSION
                        out["futures_publication_gate"] = gate
                        out["premium_path_expansion_20"] = funnel
                        out["premium_blocker_codes"] = list(funnel.get("reason_codes") or [])
                        out["premium_blocker_stage"] = funnel.get("stage")
                        out["premium_route"] = funnel.get("selected_route")
                        if not funnel.get("premium"):
                            out["premium_blocker"] = "; ".join(funnel.get("reason_codes") or []) or funnel.get("stage")
                        return out
                    except Exception as exc:
                        out["premium_path_expansion_20"] = {"version": VERSION, "stage": "DIAGNOSTIC_ERROR", "error": type(exc).__name__}
                        return out
                multi_wrapped._commit20_ppe_gate = True
                mcls._apply_futures_publication_gate = multi_wrapped
                patched.append({"class": "MultiAssetAnalysis", "already": False})
        except Exception as exc:
            patched.append({"class": "MultiAssetAnalysis", "error": type(exc).__name__})
        return {"installed": bool(patched), "patches": patched}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install_saved_signals_market_contract(app: Any) -> Dict[str, Any]:
    """Persist market/provider metadata and make saved-chart routing market aware."""
    status: Dict[str, Any] = {"market_metadata": False, "chart_route": False, "frontend_route": False}
    try:
        import saved_signals
        original_create = getattr(saved_signals, "create_saved_signal", None)
        if callable(original_create) and not getattr(original_create, "_commit20_market", False):
            @wraps(original_create)
            def create_wrapper(data, _original=original_create):
                payload = dict(data or {})
                market = str(payload.get("market_type") or payload.get("market") or "futures").strip().lower()
                if market not in {"futures", "multiasset", "spot"}:
                    market = "futures"
                payload["market_type"] = market
                if market == "multiasset":
                    try:
                        from multiasset_system import MULTIASSET_SYMBOLS
                        meta = dict((MULTIASSET_SYMBOLS or {}).get(_u(payload.get("symbol"))) or {})
                    except Exception:
                        meta = {}
                    payload["asset_class"] = str(meta.get("asset_class") or "MULTI")[:60]
                    payload["data_provider"] = "MULTIASSET_KUCOIN_REST"
                elif market == "futures":
                    payload["asset_class"] = "CRYPTO_FUTURES"
                    payload["data_provider"] = "KUCOIN_FUTURES_PERPETUAL_REST"
                else:
                    payload["asset_class"] = str(payload.get("asset_class") or "SPOT")[:60]
                    payload["data_provider"] = "KUCOIN_SPOT_REST"
                return _original(payload)
            create_wrapper._commit20_market = True
            saved_signals.create_saved_signal = create_wrapper
            status["market_metadata"] = True
    except Exception as exc:
        status["market_metadata_error"] = str(exc)[:160]

    try:
        endpoint = None
        for rule in app.url_map.iter_rules():
            if str(rule.rule) == "/api/saved_signals/<signal_id>/chart_data":
                endpoint = rule.endpoint
                break
        endpoint = endpoint or "api_saved_signals_chart_data"
        view = app.view_functions.get(endpoint)
        if callable(view) and not getattr(view, "_commit20_1_saved_chart", False):
            @wraps(view)
            def chart_wrapper(signal_id, _original=view):
                from flask import jsonify
                try:
                    from saved_signals import get_saved_signal
                    user = app_module_user(app)
                    if not user:
                        return _original(signal_id)
                    sig = get_saved_signal(signal_id)
                    if not sig or sig.get("user_name") != user:
                        return _original(signal_id)
                    market = str(sig.get("market_type") or sig.get("market") or "").lower()
                    symbol = str(sig.get("symbol") or "")
                    timeframe = str(sig.get("timeframe") or "")
                    # Existing rows created before Commit 20 may have no market_type.
                    if not market and _is_multi_symbol(symbol):
                        market = "multiasset"
                    if market != "multiasset":
                        return _original(signal_id)
                    from multiasset_system import multiasset_system
                    df = multiasset_system.get_kucoin_data(symbol, timeframe)
                    if df is None or len(df) < 5:
                        return jsonify({"success": False, "error": "Sin datos de velas Multi-Activo para este par/timeframe", "market_data_source": "MULTIASSET_KUCOIN_REST"}), 200
                    df = df.tail(100).copy().reset_index(drop=True)
                    candles = {
                        "time": [str(t) for t in df["time"].astype(str).tolist()],
                        "open": [float(v) for v in df["open"].tolist()],
                        "high": [float(v) for v in df["high"].tolist()],
                        "low": [float(v) for v in df["low"].tolist()],
                        "close": [float(v) for v in df["close"].tolist()],
                    }
                    current_price = float(df["close"].iloc[-1])
                    learning_bundle = {
                        "configuration": {},
                        "forensics": {},
                        "global_profile": {},
                        "guardian_global_profile": {},
                    }
                    try:
                        from user_execution_learning import get_trade_learning_bundle
                        learning_bundle = get_trade_learning_bundle(sig) or learning_bundle
                    except Exception:
                        pass
                    try:
                        del df
                    except Exception:
                        pass
                    return jsonify({
                        "success": True,
                        "signal": sig,
                        "candles": candles,
                        "current_price": current_price,
                        "market_data_source": "MULTIASSET_KUCOIN_REST",
                        "signal_configuration": learning_bundle.get("configuration") or {},
                        "trade_forensics": learning_bundle.get("forensics") or {},
                        "global_execution_learning": learning_bundle.get("global_profile") or {},
                        "guardian_global_learning": learning_bundle.get("guardian_global_profile") or {},
                    })
                except Exception:
                    return _original(signal_id)
            chart_wrapper._commit20_1_saved_chart = True
            app.view_functions[endpoint] = chart_wrapper
            try:
                import app as app_module
                if hasattr(app_module, "api_saved_signals_chart_data"):
                    app_module.api_saved_signals_chart_data = chart_wrapper
            except Exception:
                pass
            status["chart_route"] = True
            status["chart_endpoint"] = endpoint
    except Exception as exc:
        status["chart_route_error"] = str(exc)[:160]

    return status


def _is_multi_symbol(symbol: str) -> bool:
    try:
        from multiasset_system import MULTIASSET_SYMBOLS
        return _u(symbol) in set(MULTIASSET_SYMBOLS or {})
    except Exception:
        return False


def app_module_user(app: Any) -> Optional[str]:
    try:
        import app as app_module
        fn = getattr(app_module, "_authenticated_user", None)
        if callable(fn):
            return fn()
    except Exception:
        pass
    try:
        view = app.view_functions.get("_authenticated_user")
        if callable(view):
            return view()
    except Exception:
        pass
    return None


def install_health_contract(app: Any) -> Dict[str, Any]:
    """Expose deployed entrypoint + PPE runtime state through /health."""
    try:
        original = app.view_functions.get("health")
        if not callable(original) or getattr(original, "_commit20_health", False):
            return {"installed": False, "reason": "HEALTH_NOT_FOUND_OR_ALREADY"}
        from flask import jsonify
        @wraps(original)
        def wrapped(*args, **kwargs):
            response = original(*args, **kwargs)
            try:
                payload = response.get_json() if hasattr(response, "get_json") else None
            except Exception:
                payload = None
            if not isinstance(payload, dict):
                return response
            memory_policy = getattr(app, "_COMMIT20_1_MEMORY_POLICY", {}) or {}
            payload["runtime_contract"] = {
                "commit": "20.1",
                "entrypoint": VERSION,
                "ppe_installed": True,
                "premium_thresholds_unchanged": True,
                "max_alternative_routes": MAX_ALTERNATIVE_ROUTES,
                "max_alternative_routes_under_pressure": MAX_ALTERNATIVE_ROUTES_PRESSURE,
                "route_expansion_rss_cap_mb": PPE_ROUTE_EXPANSION_MAX_RSS_MB,
                "memory_policy": memory_policy,
                "no_new_network_calls": True,
                "alternative_route_external_calls": False,
                "no_new_threads": True,
            }
            try:
                import cpqe_19_2_4
                payload["cpqe"] = {"version": getattr(cpqe_19_2_4, "VERSION", ""), "loaded": True}
            except Exception as exc:
                payload["cpqe"] = {"loaded": False, "error": type(exc).__name__}
            try:
                import sys
                payload["module_runtime"] = {
                    "python": sys.version.split()[0],
                    "premium_path_expansion_file": __file__,
                }
            except Exception:
                pass
            return jsonify(payload)
        wrapped._commit20_health = True
        app.view_functions["health"] = wrapped
        return {"installed": True}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install(app: Any) -> Dict[str, Any]:
    return {
        "version": VERSION,
        "geometry_router": install_geometry_router(),
        "gate_diagnostics": install_gate_diagnostics(),
        "saved_signals": install_saved_signals_market_contract(app),
        "health": install_health_contract(app),
    }


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "max_alternative_routes": MAX_ALTERNATIVE_ROUTES,
        "max_alternative_routes_under_pressure": MAX_ALTERNATIVE_ROUTES_PRESSURE,
        "route_expansion_max_rss_mb": PPE_ROUTE_EXPANSION_MAX_RSS_MB,
        "route_expansion_pressure_rss_mb": PPE_ROUTE_EXPANSION_PRESSURE_RSS_MB,
        "premium_thresholds": {
            "safety": PREMIUM_MIN_SAFETY,
            "tp": PREMIUM_MIN_TP,
            "sl": PREMIUM_MIN_SL,
            "rr_min": PREMIUM_MIN_RR,
            "rr_max": PREMIUM_MAX_RR,
        },
        "changes_direction": False,
        "changes_hard_thresholds": False,
        "adds_network_calls": False,
        "alternative_route_external_calls": False,
        "adds_threads": False,
        "promotes_fallback": False,
        "research_authority": "DIAGNOSTIC_ONLY",
    }
