"""Commit 21 compatibility overlay.

Keeps the proven Commit 20.2 runtime and Multi-Activo saved-signal fixes while
replacing the old *geometry-only* route expansion with the Commit 21 strategy
route engine.  The module name is intentionally retained because app.py from
Commit 20.2 auto-installs ``premium_path_expansion_20`` even when Render uses
``gunicorn app:app``.

Commit 21 principles
--------------------
* no Premium threshold is lowered or raised;
* no direction is created by the route engine;
* no new strategy parameters are fitted from live outcomes;
* only pre-declared Strategy Bank families already eligible for the exact
  market/symbol/timeframe/action cell may be tried;
* at most two alternative families are tested sequentially;
* alternatives must match the already observed regime/volatility and the
  Strategy Bank's own independent-family requirement;
* only the existing publication gate/CPQE can grant Premium;
* when no alternative becomes Premium, the baseline result is preserved;
* Multi-Activo Saved Signals remains on the Commit 20.2 provider/renderer.
"""
from __future__ import annotations

import math
import os
from functools import wraps
from typing import Any, Dict, List, Mapping, Optional

VERSION = "COMMIT21_2_PREMIUM_STRATEGY_ROUTE_ENGINE_FIX_V1"
MAX_ALTERNATIVE_ROUTES = 2
MAX_FALLBACK_ALTERNATIVE_ROUTES = 1
ALT_BANK_MIN_QUALITY = 55.0
ROUTE_RSS_SOFT_MB = 215.0
ROUTE_RSS_HARD_MB = 235.0
ROUTE_MAX_RSS_AFTER_SHED_MB = 222.0
ROUTE_MIN_SAFETY_TO_SEARCH = 68.0

# Existing immutable publication contract.
PREMIUM_MIN_SAFETY = 75.0
PREMIUM_MIN_TP = 55.0
PREMIUM_MIN_SL = 60.0
PREMIUM_MIN_RR = 1.8
PREMIUM_MAX_RR = 3.5


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
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
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return None


def _premium_gate(result: Mapping[str, Any]) -> bool:
    return bool(
        result.get("publication_eligible")
        or str(result.get("futures_signal_tier") or "").upper() == "PREMIUM"
        or str((result.get("futures_publication_gate") or {}).get("tier") or "").upper() == "PREMIUM"
    )


def _reason_codes(result: Mapping[str, Any]) -> List[str]:
    gate = result.get("futures_publication_gate") or {}
    return [str(x).upper() for x in (gate.get("reason_codes") or [])]


def _clone_structure(structure: Mapping[str, Any], *, route_family: str, route_id: str) -> Dict[str, Any]:
    out = dict(structure or {})
    pb = dict(out.get("_contingency_playbook") or {})
    strategy = dict(pb.get("strategy") or {})
    if route_family:
        pb["setup_family"] = route_family
        pb["strategy_family"] = route_family
    if route_id:
        pb["strategy_id"] = route_id
        strategy["id"] = route_id
        strategy["family"] = route_family
    pb["strategy"] = strategy
    pb["strategy_route_source"] = "COMMIT21_STRATEGY_BANK_ALTERNATIVE"
    out["_contingency_playbook"] = pb
    out["setup_family"] = route_family
    out["_strategy_family"] = route_family
    out["_commit21_route_family"] = route_family
    out["_commit21_route_id"] = route_id
    return out


def _candidate_source(structure: Mapping[str, Any]) -> Dict[str, Any]:
    pb = dict((structure.get("_contingency_playbook") or {}))
    raw = pb.get("strategy")
    strategy = dict(raw) if isinstance(raw, Mapping) else {}
    # Commit 20/21 originally expected a nested strategy dict. The real
    # contingency playbook stores strategy/id/family as top-level metadata.
    # Normalize both forms so the route engine can actually see alternatives.
    if not strategy and raw:
        strategy = {"id": str(raw)}
    strategy.setdefault("id", pb.get("strategy_id") or pb.get("strategy"))
    strategy.setdefault("family", pb.get("setup_family") or pb.get("strategy_family"))
    strategy.setdefault("quality", pb.get("strategy_quality"))
    strategy.setdefault("indicators", pb.get("strategy_indicators") or [])
    return strategy


def _research_blocks(structure: Mapping[str, Any]) -> bool:
    pb = structure.get("_contingency_playbook") or {}
    state = str(pb.get("research_state") or "").upper()
    if state in {
        "NEGATIVE_OOS", "NEGATIVE", "ALPHA_DECAY", "DECAYED", "REJECTED_OOS",
        "BLOCKED", "DISABLED", "DEGRADED",
    }:
        return True
    if pb.get("research_blocks_selected_action"):
        return True
    return False


def _route_engine_enabled_for(structure: Mapping[str, Any], decision: str) -> bool:
    if _u(decision) not in {"LONG", "SHORT"}:
        return False
    pb = structure.get("_contingency_playbook") or {}
    if str(pb.get("market") or "FUTURES").upper() != "FUTURES":
        return False
    if _research_blocks(structure):
        return False
    return True


def _strategy_alternatives(
    *, structure: Mapping[str, Any], decision: str, symbol: str, timeframe: str,
    max_routes: int = MAX_ALTERNATIVE_ROUTES,
) -> List[Dict[str, Any]]:
    """Resolve real, predeclared Strategy Bank families for the exact cell.

    The old Commit 21 implementation depended on ``strategy.alternatives``
    being embedded in the contingency strategy object. Production actually
    stores the strategy family/quality at the playbook top level, so the route
    engine often saw zero alternatives and did no useful work.

    This fix derives candidate *families* directly from the frozen Strategy
    Bank for the exact Futures symbol/TF/action cell, then evaluates them with
    the Bank's deterministic selector. No live outcomes or new thresholds are
    used.
    """
    if not _route_engine_enabled_for(structure, decision):
        return []

    pb = dict(structure.get("_contingency_playbook") or {})
    strategy = _candidate_source(structure)
    primary_family = _u(pb.get("setup_family") or strategy.get("family"))
    groups = dict(pb.get("indicator_groups") or {})
    context = dict(pb.get("context") or {})
    regime = str(context.get("regime") or "BALANCE").upper()
    vol_state = str((pb.get("volatility") or {}).get("state") or "NORMAL").upper()
    market = "FUTURES"
    action = _u(decision)

    try:
        import default_strategy_bank as bank
        select_strategy = getattr(bank, "select_strategy")
        rows = list(getattr(bank, "STRATEGIES", []) or [])
    except Exception:
        return []

    # Build a small deterministic family universe for this exact governed cell.
    families = []
    seen = set([primary_family]) if primary_family else set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if action not in [str(x).upper() for x in (row.get("actions") or [])]:
            continue
        if market not in [str(x).upper() for x in (row.get("markets") or [])]:
            continue
        symbols = {str(x).upper().replace("/", "-") for x in (row.get("symbols") or [])}
        tfs = {str(x).upper() for x in (row.get("timeframes") or [])}
        if symbols and _u(symbol) not in symbols:
            continue
        if tfs and _u(timeframe) not in tfs:
            continue
        family = _u(row.get("family"))
        if not family or family in seen:
            continue
        seen.add(family)
        families.append(family)

    evaluated: List[Dict[str, Any]] = []
    for family in families:
        try:
            pick = select_strategy(
                action, regime, vol_state, groups,
                symbol=_u(symbol), timeframe=_u(timeframe), market=market,
                preferred_family=family,
            )
        except Exception:
            continue
        if _u(pick.get("family")) != family:
            continue
        quality = _f(pick.get("quality"), 0.0)
        if quality < ALT_BANK_MIN_QUALITY:
            continue
        if not bool(pick.get("regime_match", True)) or not bool(pick.get("volatility_match", True)):
            continue
        required = int(pick.get("required_independent_families") or 4)
        positive = int(pick.get("positive_functional_families") or 0)
        if positive < required:
            continue
        evaluated.append({
            "family": family,
            "strategy_id": str(pick.get("id") or "")[:120],
            "quality": round(quality, 2),
            "regime_match": True,
            "volatility_match": True,
            "positive_functional_families": positive,
            "required_independent_families": required,
            "source": "DEFAULT_STRATEGY_BANK_EXACT_CELL",
            "ranked_alternative": True,
        })

    evaluated.sort(key=lambda x: (-float(x.get("quality") or 0.0), -int(x.get("positive_functional_families") or 0), str(x.get("family") or "")))
    return evaluated[:max(0, int(max_routes or 0))]


def _route_search_allowed(base: Mapping[str, Any]) -> bool:
    """Cheap preflight: only spend CPU on candidates with a plausible route.

    This is a resource/quality budget, not a publication bypass. It prevents
    Commit 21 from rerunning the full execution pipeline for hopeless hard
    failures while still giving fallback/near-Premium theses a second path.
    """
    levels = dict(base.get("levels") or {})
    if not levels:
        return False
    codes = set(_reason_codes(base))
    hard_blockers = {
        "LOSS_AT_SL", "ATR_STRESS", "ACTIVE_STRATEGY_CONFLICT",
        "EXECUTION_RUNTIME_FAILED", "HIGH_TF_LOWER_TRIGGER_REQUIRED",
    }
    if codes & hard_blockers:
        return False
    if bool(levels.get("manual_geometry_fallback")):
        return True
    safety = _f(levels.get("execution_safety"), 0.0)
    rr = _f(levels.get("risk_reward"), 0.0)
    near_rr = 1.65 <= rr <= 3.60
    near_safety = safety >= ROUTE_MIN_SAFETY_TO_SEARCH
    gate = base.get("futures_publication_gate") or {}
    if gate and not gate.get("eligible"):
        return near_rr or near_safety
    return near_rr or near_safety


def _route_attempt_record(result: Mapping[str, Any], route: Mapping[str, Any]) -> Dict[str, Any]:
    levels = dict(result.get("levels") or {})
    return {
        "family": str(route.get("family") or ""),
        "strategy_id": str(route.get("strategy_id") or ""),
        "bank_quality": route.get("quality"),
        "publication_eligible": _premium_gate(result),
        "reason_codes": _reason_codes(result),
        "execution_safety": _f(levels.get("execution_safety"), 0.0),
        "tp_quality": _f(levels.get("tp_touch_quality_score") or levels.get("tp_quality_score"), 0.0),
        "sl_quality": _f(levels.get("sl_avoidance_quality_score") or levels.get("sl_reliability"), 0.0),
        "risk_reward": _f(levels.get("risk_reward"), 0.0),
        "fallback": bool(levels.get("manual_geometry_fallback")),
    }


def _funnel(result: Mapping[str, Any], levels: Mapping[str, Any], attempts: List[Dict[str, Any]], selected: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    gate = dict(result.get("futures_publication_gate") or {})
    codes = _reason_codes(result)
    stage = "PREMIUM" if gate.get("eligible") else "PUBLICATION_GATE"
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
    cpqe = result.get("cpqe_19_2_4") or {}
    if not gate.get("eligible") and cpqe and not cpqe.get("qualifying", False):
        stage = "CPQE_FAIL"
    return {
        "version": VERSION,
        "stage": stage,
        "premium": bool(gate.get("eligible")),
        "reason_codes": codes,
        "selected_route": str(
            (selected or {}).get("family")
            or levels.get("setup_family")
            or levels.get("_strategy_family")
            or "UNSPECIFIED"
        ),
        "selected_strategy_id": str((selected or {}).get("strategy_id") or ""),
        "attempt_count": len(attempts),
        "attempts": attempts[:3],
        "route_engine_authority": "STRATEGY_BANK_CONTEXT_ONLY",
        "hard_thresholds_changed": False,
        "parameters_optimized_from_live": False,
        "fallback_promoted": False,
    }



# ---------------------------------------------------------------------------
# Commit 21.2 — FULL CONTEXT CPQE REVALIDATION
# The original CPQE wrapper receives ``levels`` at publication time, but the
# full trend/momentum/structure dictionaries live in calculate_entry_levels' 
# call arguments.  Without restoring that context, CPQE saw neutral/default
# structure and could reject otherwise eligible candidates.  This helper only
# re-runs the SAME publication gate with the SAME hard thresholds and the exact
# causal context already computed by the engine.  It never changes Entry/SL/TP.
# ---------------------------------------------------------------------------
def _revalidate_with_full_context(
    self,
    result: Mapping[str, Any],
    *,
    trend: Mapping[str, Any],
    momentum: Mapping[str, Any],
    volatility: Mapping[str, Any],
    structure: Mapping[str, Any],
    timeframe: str,
    symbol: str,
    decision: str,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    gate_fn = getattr(self, "_apply_futures_publication_gate", None)
    if not callable(gate_fn):
        return result
    levels = dict(result.get("levels") or {})
    levels["_cpqe_context"] = {
        "trend": dict(trend or {}),
        "momentum": dict(momentum or {}),
        "volatility": dict(volatility or {}),
        "structure": dict(structure or {}),
        "symbol": symbol,
        "action": decision,
        "timeframe": timeframe,
    }
    try:
        refreshed = gate_fn(self, levels, timeframe, symbol=symbol, action=decision)
        out = dict(refreshed or result)
    except Exception as exc:
        out = dict(result)
        out.setdefault("premium_route_engine_21", {})["cpqe_revalidation_error"] = type(exc).__name__
    # The full context is too large and may contain DataFrames. Keep only the
    # compact CPQE result and remove the hidden transport payload immediately.
    out_levels = dict(out.get("levels") or {})
    out_levels.pop("_cpqe_context", None)
    out["levels"] = out_levels
    return out


def _compact_route_context(structure: Mapping[str, Any], route: Mapping[str, Any]) -> Dict[str, Any]:
    ctx = dict((structure or {}).get("_commit21_route_context") or {})
    return {
        "source": "DEFAULT_STRATEGY_BANK",
        "family": str(route.get("family") or ""),
        "strategy_id": str(route.get("strategy_id") or ""),
        "bank_quality": route.get("quality"),
        "regime_match": route.get("regime_match"),
        "volatility_match": route.get("volatility_match"),
        "research_state": ctx.get("research_state"),
    }

# ---------------------------------------------------------------------------
# Strategy route engine
# ---------------------------------------------------------------------------
def install_strategy_route_engine() -> Dict[str, Any]:
    try:
        import futures_system
        cls = getattr(futures_system, "FuturesAnalysis", None)
        original = getattr(cls, "calculate_entry_levels", None) if cls else None
        if not callable(original):
            return {"installed": False, "reason": "CALCULATE_ENTRY_LEVELS_NOT_FOUND"}
        if getattr(original, "_commit21_route_engine", False):
            return {"installed": True, "already": True, "max_alternatives": MAX_ALTERNATIVE_ROUTES}

        @wraps(original)
        def wrapped(self, decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation=None):
            base_structure = dict(structure or {})
            base = original(
                self,
                decision,
                trend,
                momentum,
                volatility,
                base_structure,
                symbol,
                timeframe,
                liquidation,
            )
            if not isinstance(base, dict):
                return base

            # Commit 21.2: re-run the SAME publication gate with the full causal
            # context. This fixes a data-plumbing hole in CPQE without changing
            # any threshold or trade geometry.
            base = _revalidate_with_full_context(
                self, base, trend=trend, momentum=momentum, volatility=volatility,
                structure=base_structure, timeframe=timeframe,
                symbol=symbol, decision=decision,
            )

            # Premium baseline is already sufficient: never spend CPU searching
            # for another route after a valid Premium result exists.
            if _premium_gate(base):
                lv = dict(base.get("levels") or {})
                lv["premium_route_engine_21"] = _funnel(base, lv, [], None)
                return {**base, "levels": lv, "premium_route_engine_21": lv["premium_route_engine_21"]}

            if not _route_engine_enabled_for(base_structure, decision):
                lv = dict(base.get("levels") or {})
                lv["premium_route_engine_21"] = _funnel(base, lv, [], None)
                return {**base, "levels": lv, "premium_route_engine_21": lv["premium_route_engine_21"]}

            rss = _rss_mb()
            if rss is not None and rss >= ROUTE_RSS_SOFT_MB:
                # Reclaim only recreatable caches before attempting an alternate.
                # Never add threads, never fetch new market data here.
                try:
                    import app as _app_for_shed
                    shed = getattr(_app_for_shed, "_shed_recreatable_memory", None)
                    if callable(shed):
                        shed(reason="commit21.2:route-preflight", aggressive=False)
                except Exception:
                    pass
                rss = _rss_mb()

            if rss is not None and rss > ROUTE_MAX_RSS_AFTER_SHED_MB:
                lv = dict(base.get("levels") or {})
                lv["premium_route_engine_21"] = {
                    **_funnel(base, lv, [], None),
                    "stage": "MEMORY_BUDGET",
                    "memory_rss_mb": round(rss, 1),
                    "attempt_count": 0,
                    "route_search_skipped_reason": "RSS_AFTER_SHED_ABOVE_SAFE_ALTERNATIVE_BUDGET",
                }
                return {**base, "levels": lv, "premium_route_engine_21": lv["premium_route_engine_21"]}

            if not _route_search_allowed(base):
                lv = dict(base.get("levels") or {})
                lv["premium_route_engine_21"] = _funnel(base, lv, [], None)
                return {**base, "levels": lv, "premium_route_engine_21": lv["premium_route_engine_21"]}

            fallback_mode = bool((base.get("levels") or {}).get("manual_geometry_fallback"))
            routes = _strategy_alternatives(
                structure=base_structure,
                decision=decision,
                symbol=symbol,
                timeframe=timeframe,
                max_routes=MAX_FALLBACK_ALTERNATIVE_ROUTES if fallback_mode else MAX_ALTERNATIVE_ROUTES,
            )
            if not routes:
                lv = dict(base.get("levels") or {})
                lv["premium_route_engine_21"] = _funnel(base, lv, [], None)
                return {**base, "levels": lv, "premium_route_engine_21": lv["premium_route_engine_21"]}

            attempts = [_route_attempt_record(base, {
                "family": str(((base_structure.get("_contingency_playbook") or {}).get("setup_family")) or "BASELINE"),
                "strategy_id": str((((base_structure.get("_contingency_playbook") or {}).get("strategy")) or {}).get("id") or ""),
                "quality": (((base_structure.get("_contingency_playbook") or {}).get("strategy")) or {}).get("quality"),
            })]

            # More than one alternate can raise RSS materially.  At the observed
            # 205–220MB range we intentionally reduce to one sequential route.
            max_routes_now = 1 if rss is not None and rss >= ROUTE_RSS_SOFT_MB else (MAX_FALLBACK_ALTERNATIVE_ROUTES if fallback_mode else MAX_ALTERNATIVE_ROUTES)

            for route in routes[:max_routes_now]:
                route_structure = _clone_structure(
                    base_structure,
                    route_family=str(route.get("family") or ""),
                    route_id=str(route.get("strategy_id") or ""),
                )
                route_structure["_commit21_route_context"] = {
                    "source": "DEFAULT_STRATEGY_BANK",
                    "bank_quality": route.get("quality"),
                    "regime_match": route.get("regime_match"),
                    "volatility_match": route.get("volatility_match"),
                }
                try:
                    candidate = original(
                        self,
                        decision,
                        trend,
                        momentum,
                        volatility,
                        route_structure,
                        symbol,
                        timeframe,
                        liquidation,
                    )
                    if isinstance(candidate, dict):
                        candidate = _revalidate_with_full_context(
                            self, candidate, trend=trend, momentum=momentum,
                            volatility=volatility, structure=route_structure,
                            timeframe=timeframe, symbol=symbol, decision=decision,
                        )
                except Exception as exc:
                    attempts.append({
                        "family": route.get("family"),
                        "strategy_id": route.get("strategy_id"),
                        "error": f"{type(exc).__name__}",
                        "publication_eligible": False,
                    })
                    continue

                attempts.append(_route_attempt_record(candidate if isinstance(candidate, dict) else {}, route))
                if isinstance(candidate, dict) and _premium_gate(candidate):
                    lv = dict(candidate.get("levels") or {})
                    selected = {
                        "family": route.get("family"),
                        "strategy_id": route.get("strategy_id"),
                    }
                    funnel = _funnel(candidate, lv, attempts, selected)
                    funnel["baseline_reason_codes"] = _reason_codes(base)
                    funnel["baseline_was_premium"] = False
                    funnel["memory_rss_mb_before_routes"] = round(rss, 1) if rss is not None else None
                    lv["premium_route_engine_21"] = funnel
                    lv["strategy_route_family"] = str(route.get("family") or "")
                    lv["strategy_route_id"] = str(route.get("strategy_id") or "")
                    lv["strategy_route_authority"] = "DEFAULT_STRATEGY_BANK_EXACT_CELL"
                    lv["premium_route_source_version"] = VERSION
                    gate = dict(candidate.get("futures_publication_gate") or {})
                    lv["premium_blocker_codes"] = [str(x) for x in (gate.get("reason_codes") or [])]
                    candidate["levels"] = lv
                    candidate["premium_route_engine_21"] = funnel
                    candidate["premium_route_promoted"] = True
                    candidate["premium_route_promoted_from"] = str(
                        (((base_structure.get("_contingency_playbook") or {}).get("setup_family")) or "")
                    )
                    return candidate

                current_rss = _rss_mb()
                if current_rss is not None and current_rss >= ROUTE_RSS_HARD_MB:
                    break

            lv = dict(base.get("levels") or {})
            funnel = _funnel(base, lv, attempts, None)
            funnel["baseline_reason_codes"] = _reason_codes(base)
            funnel["baseline_was_premium"] = False
            funnel["memory_rss_mb_before_routes"] = round(rss, 1) if rss is not None else None
            lv["premium_route_engine_21"] = funnel
            base["levels"] = lv
            base["premium_route_engine_21"] = funnel
            base["premium_route_promoted"] = False
            return base

        wrapped._commit21_route_engine = True
        cls.calculate_entry_levels = wrapped
        return {"installed": True, "already": False, "max_alternatives": MAX_ALTERNATIVE_ROUTES, "version": VERSION}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


# ---------------------------------------------------------------------------
# Commit 20.2 saved-signal Multi-Activo contract (preserved)
# ---------------------------------------------------------------------------
def _canonical_market_symbol(symbol: Any) -> str:
    return _u(symbol).replace("_", "-")


def _is_multi_symbol(symbol: str) -> bool:
    try:
        from multiasset_system import MULTIASSET_SYMBOLS
        return _u(symbol) in set(MULTIASSET_SYMBOLS or {})
    except Exception:
        return False


def _market_for_saved_signal(sig: Mapping[str, Any]) -> str:
    market = str(sig.get("market_type") or sig.get("market") or "").strip().lower()
    symbol = _canonical_market_symbol(sig.get("symbol") or "")
    if market in {"multiasset", "multi-asset", "multi"} or _is_multi_symbol(symbol):
        return "multiasset"
    if market == "spot":
        return "spot"
    return "futures"


def _saved_signal_learning_bundle(sig: Mapping[str, Any]) -> Dict[str, Any]:
    bundle = {"configuration": {}, "forensics": {}, "global_profile": {}, "guardian_global_profile": {}}
    try:
        from user_execution_learning import get_trade_learning_bundle
        data = get_trade_learning_bundle(sig) or {}
        if isinstance(data, dict):
            bundle.update(data)
    except Exception as exc:
        print(f"⚠️ Commit21 saved trade review: {exc}")
    return bundle


def _saved_signal_chart_payload(sig: Mapping[str, Any], df: Any, source: str, learning_bundle: Mapping[str, Any]) -> Dict[str, Any]:
    import pandas as pd
    work = df.tail(100).copy().reset_index(drop=True)
    time_col = "time" if "time" in work.columns else ("timestamp" if "timestamp" in work.columns else None)
    if time_col is None or not {"open", "high", "low", "close"}.issubset(set(work.columns)):
        raise ValueError("OHLC_SCHEMA_INVALID")
    candles = {
        "time": [str(x) for x in work[time_col].astype(str).tolist()],
        "open": [float(x) for x in pd.to_numeric(work["open"], errors="coerce").tolist()],
        "high": [float(x) for x in pd.to_numeric(work["high"], errors="coerce").tolist()],
        "low": [float(x) for x in pd.to_numeric(work["low"], errors="coerce").tolist()],
        "close": [float(x) for x in pd.to_numeric(work["close"], errors="coerce").tolist()],
    }
    return {
        "success": True,
        "signal": dict(sig),
        "candles": candles,
        "current_price": float(candles["close"][-1]),
        "market_data_source": source,
        "signal_configuration": learning_bundle.get("configuration") or {},
        "trade_forensics": learning_bundle.get("forensics") or {},
        "global_execution_learning": learning_bundle.get("global_profile") or {},
        "guardian_global_learning": learning_bundle.get("guardian_global_profile") or {},
    }


def app_module_user(app: Any) -> Optional[str]:
    try:
        view = app.view_functions.get("_authenticated_user")
        if callable(view):
            return view()
    except Exception:
        pass
    try:
        import app as app_module
        fn = getattr(app_module, "_authenticated_user", None)
        return fn() if callable(fn) else None
    except Exception:
        return None


def install_saved_signals_market_contract(app: Any) -> Dict[str, Any]:
    status = {"market_metadata": False, "chart_route": False, "frontend_route": True}
    try:
        import saved_signals
        original_create = getattr(saved_signals, "create_saved_signal", None)
        if callable(original_create) and not getattr(original_create, "_commit20_2_market", False):
            @wraps(original_create)
            def create_wrapper(data, _original=original_create):
                payload = dict(data or {})
                market = str(payload.get("market_type") or payload.get("market") or "").strip().lower()
                symbol = _canonical_market_symbol(payload.get("symbol") or "")
                if market in {"multiasset", "multi-asset", "multi"} or _is_multi_symbol(symbol):
                    market = "multiasset"
                elif market == "spot":
                    market = "spot"
                else:
                    market = "futures"
                payload["symbol"] = symbol
                payload["market_type"] = market
                payload["market"] = market
                if market == "multiasset":
                    try:
                        from multiasset_system import MULTIASSET_SYMBOLS
                        meta = dict((MULTIASSET_SYMBOLS or {}).get(symbol) or {})
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
                result = _original(payload)
                try:
                    row = result[0] if isinstance(result, tuple) and result else None
                    err = result[1] if isinstance(result, tuple) and len(result) > 1 else None
                    if row is None and err and "column" in str(err).lower() and "does not exist" in str(err).lower():
                        legacy = dict(payload)
                        for key in ("market_type", "market", "asset_class", "data_provider"):
                            legacy.pop(key, None)
                        return _original(legacy)
                except Exception:
                    pass
                return result
            create_wrapper._commit20_2_market = True
            saved_signals.create_saved_signal = create_wrapper
            status["market_metadata"] = True
    except Exception as exc:
        status["market_metadata_error"] = str(exc)[:180]

    try:
        endpoint = next((r.endpoint for r in app.url_map.iter_rules() if str(r.rule) == "/api/saved_signals/<signal_id>/chart_data"), "api_saved_signals_chart_data")
        original_view = app.view_functions.get(endpoint)
        if callable(original_view) and not getattr(original_view, "_commit20_2_saved_chart", False):
            @wraps(original_view)
            def chart_wrapper(signal_id, _original=original_view):
                from flask import jsonify
                market = "unknown"
                try:
                    from saved_signals import get_saved_signal
                    user = app_module_user(app)
                    if not user:
                        return jsonify({"success": False, "authenticated": False, "error": "Debes iniciar sesión."}), 401
                    sig = get_saved_signal(signal_id)
                    if not sig or sig.get("user_name") != user:
                        return jsonify({"success": False, "error": "No encontrada"}), 404
                    market = _market_for_saved_signal(sig)
                    symbol = _canonical_market_symbol(sig.get("symbol") or "")
                    timeframe = str(sig.get("timeframe") or "").strip()
                    if market != "multiasset":
                        return _original(signal_id)
                    from multiasset_system import multiasset_system
                    df = multiasset_system.get_kucoin_data(symbol, timeframe)
                    if df is None or len(df) < 5:
                        return jsonify({
                            "success": False,
                            "error": f"Sin datos de velas Multi-Activo para {symbol} {timeframe}.",
                            "market": "multiasset",
                            "market_data_source": "MULTIASSET_KUCOIN_REST",
                            "signal": sig,
                        }), 200
                    try:
                        payload = _saved_signal_chart_payload(sig, df, "MULTIASSET_KUCOIN_REST", _saved_signal_learning_bundle(sig))
                        payload["market"] = "multiasset"
                        payload["market_type"] = "multiasset"
                        return jsonify(payload), 200
                    finally:
                        try:
                            del df
                        except Exception:
                            pass
                except Exception as exc:
                    print(f"❌ Commit21 saved chart: {type(exc).__name__}: {exc}")
                    if market == "multiasset":
                        return jsonify({
                            "success": False,
                            "error": f"Error cargando gráfico Multi-Activo: {type(exc).__name__}: {str(exc)[:160]}",
                            "market": "multiasset",
                            "market_data_source": "MULTIASSET_KUCOIN_REST",
                        }), 200
                    return _original(signal_id)
            chart_wrapper._commit20_2_saved_chart = True
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
        status["chart_route_error"] = str(exc)[:180]
    return status


def install_health_contract(app: Any) -> Dict[str, Any]:
    try:
        original = app.view_functions.get("health")
        if not callable(original) or getattr(original, "_commit21_health", False):
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
            payload["runtime_contract"] = {
                "commit": "21.1",
                "entrypoint": VERSION,
                "strategy_route_engine_loaded": True,
                "route_engine_v": "21.1_PREDECLARED_BANK",
                "premium_thresholds_unchanged": True,
                "max_alternative_strategy_routes": MAX_ALTERNATIVE_ROUTES,
                "no_new_network_calls": True,
                "no_new_threads": True,
                "fallback_never_promoted": True,
                "live_parameter_fitting": False,
                "multiasset_saved_chart_contract": "COMMIT20_2_PRESERVED",
            }
            try:
                import cpqe_19_2_4
                payload["cpqe"] = {"version": getattr(cpqe_19_2_4, "VERSION", ""), "loaded": True}
            except Exception as exc:
                payload["cpqe"] = {"loaded": False, "error": type(exc).__name__}
            return jsonify(payload)

        wrapped._commit21_health = True
        app.view_functions["health"] = wrapped
        return {"installed": True}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install(app: Any) -> Dict[str, Any]:
    status: Dict[str, Any] = {"version": VERSION}

    # Preserve Commit 20.2 memory policy. Single worker / 2 threads remains the
    # deployment contract. Route expansion is sequential and RSS bounded.
    try:
        hard = min(300.0, max(280.0, float(getattr(app, "_MEMORY_HARD_LIMIT_MB", 300.0) or 300.0)))
        soft = min(235.0, hard - 45.0)
        start = min(215.0, soft - 20.0)
        app._MEMORY_HARD_LIMIT_MB = hard
        app._MEMORY_SOFT_LIMIT_MB = soft
        app._MEMORY_JOB_START_LIMIT_MB = min(225.0, max(210.0, start))
        app._MEMORY_ANALYSIS_CACHE_KEEP = 1
        # app.py's guards read module globals, not only Flask app attributes.
        # Commit 20.2 changed the attributes but left the real guards at the
        # old 200 MB clamp. Synchronize both surfaces explicitly.
        try:
            import app as _app_module
            _app_module._MEMORY_HARD_LIMIT_MB = hard
            _app_module._MEMORY_SOFT_LIMIT_MB = soft
            _app_module._MEMORY_JOB_START_LIMIT_MB = min(225.0, max(210.0, start))
            _app_module._MEMORY_ANALYSIS_CACHE_KEEP = 1
        except Exception:
            pass
        app._COMMIT21_MEMORY_POLICY = {
            "memory_job_start_limit_mb": min(225.0, max(210.0, start)),
            "memory_soft_limit_mb": soft,
            "memory_hard_limit_mb": hard,
            "single_heavy_slot": True,
            "interactive_priority": True,
            "route_rss_soft_mb": ROUTE_RSS_SOFT_MB,
            "route_rss_hard_mb": ROUTE_RSS_HARD_MB,
        }
    except Exception as exc:
        app._COMMIT21_MEMORY_POLICY = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    # Ensure CPQE is present even if Render is manually configured with
    # ``gunicorn app:app`` instead of the versioned entrypoint.
    try:
        from cpqe_19_2_4 import install_post_app as install_cpqe
        status["cpqe"] = install_cpqe(app)
    except Exception as exc:
        status["cpqe"] = {"installed": False, "error": type(exc).__name__}

    status["saved_signals"] = install_saved_signals_market_contract(app)
    status["health"] = install_health_contract(app)
    status["strategy_route_engine"] = install_strategy_route_engine()
    status["memory_policy"] = getattr(app, "_COMMIT21_MEMORY_POLICY", {})
    return status


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "fix": "21.1",
        "max_alternative_routes": MAX_ALTERNATIVE_ROUTES,
        "bank_min_quality": ALT_BANK_MIN_QUALITY,
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
        "adds_threads": False,
        "promotes_fallback": False,
        "live_parameter_fitting": False,
        "route_source": "PREDECLARED_DEFAULT_STRATEGY_BANK_EXACT_CELL",
        "research_authority": "NO_NEW_ALPHA_AUTHORITY",
        "multiasset_saved_chart": "PRESERVED_FROM_COMMIT20_2",
    }
