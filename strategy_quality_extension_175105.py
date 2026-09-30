"""Commit 17.5.10.7 — Invalidation Corridor + bounded runtime reads.

This module is loaded by the existing 17.5.10.6 execution ABI.  It preserves
17.5.10.5 Strategy Bank scope/SHADOW behaviour and adds three bounded repairs:

1) Futures/Multi-Asset SL recovery is corridor-aware.  A strong thesis is NOT
   made executable by force: only an already-existing directional setup that
   was rejected because its SL remained inside a valid reaction zone may try to
   move the SL behind the complete local invalidation corridor.  Every step is
   rechecked against the deployed SL reaction guard and the contextual R/R
   floor.  No direction, TP or Safety threshold is invented/lowered.
2) Frontend Futures GET reads use the canonical in-memory snapshot and never
   start a heavy analysis merely because /previous or /active was requested.
3) Multi-Asset interactive analysis no longer executes a deep cell inside the
   HTTP request. It reuses/prioritizes the existing fair deep-analysis queue and
   returns HTTP 202 immediately when the selected cell is not cached.
4) Futures risk-profile GET uses a tiny TTL cache + the existing bounded REST
   transport instead of the unbounded supabase-py retry path.  No new thread,
   DB table, polling loop, LLM call or market-data request is introduced.

The repair applies to Crypto Futures and the Multi-Asset subclass because both
share FuturesAnalysis.calculate_entry_levels. Spot production is not modified.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Dict, Mapping, Optional
import sys
import threading
import time

VERSION = "17.5.10.7_INVALIDATION_CORRIDOR_RUNTIME_READS_V1"
_LOCK = threading.RLock()
_STATE = {
    "installed": False,
    "version": VERSION,
    "strategy_scope_installed": False,
    "invalidation_corridor_installed": False,
    "cache_only_reads_installed": False,
    "multiasset_nonblocking_ui_installed": False,
    "risk_profile_bounded_read_installed": False,
    "leverage_visibility_consistency_installed": False,
}

_BACKTEST = {
    "scope": "FUTURES_30M_EXISTING_SYSTEM_GEOMETRY",
    "family": "TREND_DISPLACEMENT_CONTINUATION",
    "authority": "SHADOW_ONLY_SMALL_SAMPLE",
    "is": {"n": 6, "tp": 2, "expectancy_r": 0.0655, "profit_factor": 1.088, "net_r": 0.3929},
    "oos": {"n": 4, "tp": 3, "expectancy_r": 1.4797, "profit_factor": 6.294, "net_r": 5.9187},
    "overall_by_direction": {
        "LONG": {"n": 3, "expectancy_r": -0.1427, "profit_factor": 0.809},
        "SHORT": {"n": 7, "expectancy_r": 0.9628, "profit_factor": 3.009},
    },
    "promotion_reason": "NOT_PROMOTED_DIRECTIONAL_ASYMMETRY_AND_N_TOO_SMALL",
}


def _u(v: Any) -> str:
    return str(v or "").strip().upper()


def _f(v: Any, d: float = 0.0) -> float:
    try:
        n = float(v if v is not None else d)
        return n if n == n else float(d)
    except Exception:
        return float(d)


def continuation_shadow_context(
    action: str, regime: str, volatility: str, groups: Mapping[str, Any],
    *, timeframe: str, market: str
) -> Dict[str, Any]:
    """Detect the missing continuation context without production authority."""
    action = _u(action)
    regime = _u(regime)
    volatility = _u(volatility)
    timeframe = _u(timeframe)
    market = _u(market)
    side = 1 if action in {"LONG", "COMPRA_SPOT"} else -1

    trend = dict(groups.get("trend") or {})
    momentum = dict(groups.get("momentum") or {})
    flow = dict(groups.get("volume_flow") or {})
    structure = dict(groups.get("structure_liquidity") or {})
    mtf = dict(groups.get("multi_timeframe") or {})

    adx = _f(trend.get("adx"))
    pd = _f(trend.get("plus_di"))
    md = _f(trend.get("minus_di"))
    macd = _f(momentum.get("macd_histogram"))
    vr = _f(flow.get("volume_ratio"), 1.0)
    trend_dir = _u(trend.get("direction") or trend.get("trend_direction"))
    mtf_dir = _u(mtf.get("dominant_direction") or mtf.get("direction"))
    mtf_conflict = bool(mtf.get("conflict"))

    dmi = (pd > md) if side > 0 else (md > pd)
    trend_ok = trend_dir in (
        {"BULLISH", "UP", "TREND_UP"} if side > 0
        else {"BEARISH", "DOWN", "TREND_DOWN"}
    )
    mtf_ok = (
        not mtf_conflict
        and mtf_dir in (
            {"BULLISH", "UP", "TREND_UP"} if side > 0
            else {"BEARISH", "DOWN", "TREND_DOWN"}
        )
    )
    momentum_ok = macd > 0 if side > 0 else macd < 0
    displacement = bool(
        structure.get("displacement")
        or structure.get("has_displacement")
        or structure.get("mss_bos")
        or structure.get("has_bos")
    )
    regime_ok = regime in (
        {"TREND_UP", "TRANSITION"} if side > 0
        else {"TREND_DOWN", "TRANSITION"}
    )
    volatility_ok = volatility in {
        "NORMAL", "EXPANSION", "HIGH_EXPANSION", "SHOCK", "VOLATILITY_SHOCK"
    }

    evidence = {
        "regime": regime_ok,
        "trend": trend_ok,
        "adx_dmi": adx >= 25 and dmi,
        "momentum": momentum_ok,
        "activity": vr >= 1.10,
        "mtf": mtf_ok,
        "displacement": displacement,
        "volatility": volatility_ok,
    }
    hits = sum(bool(x) for x in evidence.values())
    candidate = (
        market == "FUTURES"
        and timeframe in {"30M", "1H", "2H", "4H"}
        and evidence["regime"]
        and evidence["trend"]
        and evidence["adx_dmi"]
        and evidence["mtf"]
        and evidence["volatility"]
        and (evidence["displacement"] or evidence["momentum"])
        and hits >= 6
    )
    return {
        "version": VERSION,
        "family": "TREND_DISPLACEMENT_CONTINUATION",
        "candidate": candidate,
        "evidence": evidence,
        "evidence_hits": hits,
        "authority": "SHADOW_ONLY",
        "can_create_direction": False,
        "can_select_live_strategy": False,
        "backtest": _BACKTEST,
    }


def _install_strategy_scope() -> Dict[str, Any]:
    """Preserve 17.5.10.5 declared family/timeframe scope enforcement."""
    import default_strategy_bank as bank

    original_count = len(getattr(bank, "STRATEGIES", []) or [])
    family_tf = getattr(bank, "_FAMILY_TIMEFRAMES", {}) or {}
    filtered = []
    removed = 0
    for row in list(getattr(bank, "STRATEGIES", []) or []):
        market = "FUTURES" if any(
            a in {"LONG", "SHORT"} for a in (row.get("actions") or [])
        ) else "SPOT"
        family = _u(row.get("family"))
        tfs = [_u(x) for x in (row.get("timeframes") or [])]
        allowed = {_u(x) for x in ((family_tf.get(market) or {}).get(family) or [])}
        if allowed and tfs and not any(tf in allowed for tf in tfs):
            removed += 1
            continue
        filtered.append(row)

    bank.STRATEGIES[:] = filtered
    bank.continuation_shadow_context_175105 = continuation_shadow_context
    bank.TREND_DISPLACEMENT_CONTINUATION_BACKTEST_175105 = dict(_BACKTEST)
    return {
        "original_strategy_count": original_count,
        "runtime_strategy_count": len(filtered),
        "out_of_scope_specializations_removed": removed,
        "continuation_authority": "SHADOW_ONLY_SMALL_SAMPLE",
    }


def _sl_reason(levels: Mapping[str, Any]) -> str:
    return str(
        levels.get("rejected_reason")
        or levels.get("execution_rejected_reason")
        or ""
    )


def _is_sl_collision_rejection(levels: Mapping[str, Any]) -> bool:
    reason = _sl_reason(levels).lower()
    return bool(
        "sl no defendible" in reason
        or "sl_inside_strong_reaction_zone" in reason
        or levels.get("sl_reaction_conflict") is True
    )


def _setup_family(structure: Mapping[str, Any], levels: Mapping[str, Any]) -> str:
    playbook = dict((structure or {}).get("_contingency_playbook") or {})
    return str(
        playbook.get("setup_family")
        or levels.get("execution_setup_family")
        or levels.get("setup_family")
        or "UNSPECIFIED"
    )


def _corridor_recovery(
    *, levels: Mapping[str, Any], structure: Mapping[str, Any], decision: str,
    volatility: Mapping[str, Any], timeframe: str, symbol: str = "",
    round_price=None
) -> Optional[Dict[str, Any]]:
    """Iteratively move SL behind every *local strong* conflicting reaction zone.

    The existing reaction guard is the authority.  This function never makes a
    distant historical level relevant by itself: it simply asks the deployed
    guard for the current blocking level, moves beyond that exact level by the
    required clearance, and asks again.  This naturally forms a local corridor
    (e.g. Swing -> HVN -> Fib) without predeclaring one indicator as superior.
    """
    base = dict(levels or {})
    if not _is_sl_collision_rejection(base):
        return None

    action = _u(decision)
    direction = "long" if action in {"LONG", "COMPRA_SPOT"} else "short" if action in {"SHORT", "VENTA_SPOT"} else ""
    if not direction:
        return None

    entry = _f(base.get("entry"))
    stop = _f(base.get("stop_loss"))
    tp = _f(base.get("take_profit"))
    atr = _f((volatility or {}).get("atr"))
    rr_floor = max(1.0, _f(base.get("minimum_viable_rr"), 1.5))
    rr_ceiling = max(rr_floor, _f(base.get("maximum_technical_rr"), 4.5))
    if min(entry, stop, tp, atr) <= 0:
        return None
    if direction == "long" and not (stop < entry < tp):
        return None
    if direction == "short" and not (tp < entry < stop):
        return None

    reward = abs(tp - entry)
    original_risk = abs(entry - stop)
    if reward <= 0 or original_risk <= 0:
        return None

    # Hard economic cap: corridor recovery may widen protection only while the
    # original structural target still satisfies the contextual R/R floor.
    rr_risk_cap = reward / max(rr_floor, 1e-12) * 0.995
    # Bounded geometry cap: no runaway stop caused by old/deep historical zones.
    local_risk_cap = max(original_risk * 1.85, atr * 1.40)
    local_risk_cap = min(local_risk_cap, atr * 3.50, entry * 0.06)
    max_risk = min(rr_risk_cap, local_risk_cap)
    if max_risk <= original_risk * 1.001:
        return None

    try:
        import execution_specialist_committees as esc
        guard = esc.evaluate_sl_reaction_conflict
    except Exception:
        return None

    cursor = stop
    steps = []
    seen = set()
    for _ in range(6):
        state = guard(
            structure=dict(structure or {}),
            direction=direction,
            entry=entry,
            stop_loss=cursor,
            atr=atr,
        ) or {}
        if not state.get("conflict"):
            break
        if str(state.get("reason") or "") == "SL_WRONG_SIDE":
            return None

        level = _f(state.get("level"))
        if level <= 0:
            return None
        source = str(state.get("source") or "reaction")
        key = (round(level, 10), source)
        if key in seen:
            return None
        seen.add(key)

        required_atr = max(0.12, _f(state.get("required_clearance_atr"), 0.16))
        # Small epsilon beyond the exact guard boundary prevents a float-equal
        # re-collision. It is not a new technical level.
        clearance = max(atr * (required_atr + 0.04), abs(level) * 0.0007)
        candidate = level - clearance if direction == "long" else level + clearance
        if direction == "long":
            candidate = min(candidate, cursor - atr * 0.015)
        else:
            candidate = max(candidate, cursor + atr * 0.015)

        candidate_risk = abs(entry - candidate)
        if candidate_risk > max_risk + 1e-12:
            return None

        steps.append({
            "source": source,
            "level": round(level, 12),
            "required_clearance_atr": round(required_atr, 4),
            "candidate_stop": round(candidate, 12),
            "risk_atr": round(candidate_risk / max(atr, 1e-12), 4),
        })
        cursor = candidate
    else:
        return None

    # Preserve the deployed symbol rounding contract.  Rounding can move a
    # borderline price back onto the guard boundary, so re-check it and allow
    # only a tiny extra structural clearance before failing closed.
    if callable(round_price):
        try:
            rounded = _f(round_price(cursor, symbol), cursor)
        except Exception:
            rounded = cursor
    else:
        rounded = cursor

    def _guard_for(value):
        return guard(
            structure=dict(structure or {}),
            direction=direction,
            entry=entry,
            stop_loss=value,
            atr=atr,
        ) or {}

    final_guard = _guard_for(rounded)
    if final_guard.get("conflict"):
        nudge = atr * 0.03
        raw_nudged = cursor - nudge if direction == "long" else cursor + nudge
        if callable(round_price):
            try:
                rounded = _f(round_price(raw_nudged, symbol), raw_nudged)
            except Exception:
                rounded = raw_nudged
        else:
            rounded = raw_nudged
        final_guard = _guard_for(rounded)
        if final_guard.get("conflict"):
            return None

    cursor = rounded
    risk = abs(entry - cursor)
    if risk > max_risk + 1e-12:
        return None
    rr = reward / max(risk, 1e-12)
    if not (rr_floor <= rr <= rr_ceiling):
        return None

    candidate_levels = dict(base)
    candidate_levels.update({
        "stop_loss": cursor,
        "risk_reward": round(rr, 4),
        "sl_source": "Invalidación detrás del corredor técnico",
        "sl_reaction_conflict": False,
        "sl_invalidation_corridor_recovered": True,
        "sl_invalidation_corridor_version": VERSION,
        "sl_invalidation_corridor_steps": steps,
        "sl_invalidation_corridor_sources": [row["source"] for row in steps],
        "sl_invalidation_corridor_risk_atr": round(risk / max(atr, 1e-12), 4),
        "sl_invalidation_corridor_risk_expansion": round(risk / max(original_risk, 1e-12), 4),
        "sl_invalidation_corridor_rr_floor": round(rr_floor, 4),
        "sl_invalidation_corridor_rounded": bool(abs(cursor - stop) > 0),
        "sl_reaction_guard_reason": "CLEAR_INVALIDATION",
        "sl_reaction_conflict_level": None,
        "sl_reaction_conflict_source": None,
    })

    # Keep the deployed contextual setup guard authoritative.  17.5.10.6 has
    # already patched it to use minimum_viable_rr instead of a blanket 1.50.
    try:
        import operational_intelligence as oi
        setup_guard = oi.execution_setup_guard(
            action=action,
            levels=candidate_levels,
            setup_family=_setup_family(structure, base),
            market="FUTURES",
            timeframe=str(timeframe or ""),
        ) or {}
        if setup_guard.get("applied"):
            return None
    except Exception:
        # Fail closed for a derivative geometry repair.
        return None

    candidate_levels["sl_invalidation_corridor_original_reason"] = _sl_reason(base)[:240]
    candidate_levels["rejected_reason"] = None
    candidate_levels["is_rejected"] = False
    candidate_levels["is_executable"] = True
    candidate_levels["publication_status"] = "EXECUTABLE_SIGNAL"
    return candidate_levels


def _install_invalidation_corridor() -> bool:
    """Patch the shared BASE geometry method, before Futures safety/leverage gates.

    FuturesAnalysis.calculate_entry_levels performs Entry timing, Entry reaction,
    Execution Safety, V6 leverage, loss-at-SL, ATR stress and Publication Gate
    *after* ``super().calculate_entry_levels`` returns.  Therefore corridor
    recovery must live on that direct shared base method.  Patching the outer
    Futures method would incorrectly skip those downstream gates.
    """
    try:
        import futures_system as futures_module
        futures_cls = getattr(futures_module, "FuturesAnalysis", None)
        mro = getattr(futures_cls, "__mro__", ()) if futures_cls is not None else ()
        if len(mro) < 2:
            return False
        base_cls = mro[1]
        method = getattr(base_cls, "calculate_entry_levels", None)
        if not callable(method):
            return False
        if getattr(method, "_st175107_invalidation_corridor", False):
            return True
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
            levels = original(
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
            if not isinstance(levels, dict):
                return levels
            recovered = _corridor_recovery(
                levels=levels,
                structure=structure if isinstance(structure, Mapping) else {},
                decision=str(decision or ""),
                volatility=volatility if isinstance(volatility, Mapping) else {},
                timeframe=str(timeframe or ""),
                symbol=str(symbol or ""),
                round_price=getattr(self, "_round_price", None),
            )
            return recovered if isinstance(recovered, dict) else levels

        _wrapped._st175107_invalidation_corridor = True
        _wrapped._st175107_original = original
        base_cls.calculate_entry_levels = _wrapped
        return True
    except Exception:
        return False


def _install_cache_only_futures_reads() -> bool:
    """GET /previous and /active must never start heavy market analysis."""
    appmod = sys.modules.get("app")
    if appmod is None:
        return False
    original = getattr(appmod, "_get_or_refresh_futures_analysis", None)
    read_only = getattr(appmod, "_get_futures_analysis_snapshot_read_only", None)
    if not callable(original) or not callable(read_only):
        return False
    if getattr(original, "_st175107_cache_only_reads", False):
        return True

    @wraps(original)
    def _bounded(*args, **kwargs):
        try:
            from flask import has_request_context, request
            cache_paths = {
                "/api/futures/signals/active",
                "/api/futures/signals/previous",
            }
            if has_request_context() and request.method == "GET" and request.path in cache_paths:
                snap = read_only() or {}
                if snap.get("snapshot_available") is True:
                    data = dict(snap)
                    cache = getattr(appmod, "_futures_analysis_cache", {}) or {}
                    ts = _f(cache.get("ts"), 0.0)
                    data["cache_age"] = int(max(0.0, time.time() - ts)) if ts > 0 else 0
                    data["refreshing"] = bool(cache.get("running", False))
                    data["warming_up"] = False
                    data["read_only_snapshot"] = True
                    if data["cache_age"] >= 900:
                        data["stale"] = True
                    return data
                return {
                    "analysis": {},
                    "errors": [],
                    "lifecycle": {},
                    "snapshot_available": False,
                    "read_only_snapshot": True,
                    "refreshing": False,
                    "restoring_snapshot": False,
                    "warming_up": True,
                    "cache_age": 0,
                }
        except Exception:
            pass
        return original(*args, **kwargs)

    _bounded._st175107_cache_only_reads = True
    _bounded._st175107_original = original
    appmod._get_or_refresh_futures_analysis = _bounded
    return True



def _install_multiasset_nonblocking_ui() -> bool:
    """Reuse the existing Multi deep queue instead of blocking the HTTP thread.

    The old /api/multiasset/analyze route called _multiasset_run_analysis
    synchronously, so a legitimate deep analysis could outlive the browser's
    25-second bound.  This replacement creates no worker/thread and makes no
    market request.  It either serves the existing cache or enqueues the exact
    selected cell at the front of the already-running fair queue.
    """
    appmod = sys.modules.get("app")
    if appmod is None:
        return False
    flask_app = getattr(appmod, "app", None)
    original = getattr(appmod, "api_multiasset_analyze", None)
    if flask_app is None or not callable(original):
        return False
    # 17.5.11 integrates the non-blocking Multi contract directly in app.py.
    # Do not replace that route with the older queue-only compatibility wrapper.
    if getattr(original, "_st17511_integrated_nonblocking_multi_ui", False):
        return True
    if getattr(original, "_st175107_nonblocking_multi_ui", False):
        return True

    required = (
        "_MULTI_ASSET_CACHE", "_MULTI_AUTO_LOCK", "_MULTI_PENDING_QUEUE",
        "_MULTI_PENDING_KEYS", "_multiasset_enqueue_due", "_multiasset_bucket",
    )
    if any(not hasattr(appmod, name) for name in required):
        return False

    @wraps(original)
    def _nonblocking():
        from datetime import datetime, timezone
        from flask import jsonify, request
        try:
            payload = request.get_json(silent=True) or {}
            symbol = str(payload.get("symbol") or "CL-USDT").upper().replace("/", "-")
            timeframe = str(payload.get("timeframe") or "4h")
            try:
                from multiasset_system import MULTIASSET_SYMBOLS, MULTIASSET_TIMEFRAMES
                if symbol not in MULTIASSET_SYMBOLS or timeframe not in MULTIASSET_TIMEFRAMES:
                    return jsonify({
                        "success": False,
                        "error": "Símbolo/temporalidad fuera del universo Multi-Activo",
                    }), 400
            except Exception:
                return original()

            cache = getattr(appmod, "_MULTI_ASSET_CACHE")
            with cache["lock"]:
                cached = dict((cache.get("analysis") or {}).get((symbol, timeframe)) or {})
            if cached:
                cached.setdefault("success", True)
                cached["ui_cache"] = True
                cached["nonblocking_ui_version"] = VERSION
                return jsonify(cached), 200

            marker = getattr(appmod, "_mark_system_interactive_priority", None)
            if callable(marker):
                try:
                    marker(seconds=120)
                except Exception:
                    pass

            now = datetime.now(timezone.utc)
            enqueue = getattr(appmod, "_multiasset_enqueue_due")
            enqueue([(symbol, timeframe)], now)
            bucket_fn = getattr(appmod, "_multiasset_bucket")
            bucket = str(bucket_fn(symbol, timeframe, now))

            # Explicit human selection gets queue priority, but it still uses the
            # same one-cell-per-tick heavy slot and all RAM/network backpressure.
            lock = getattr(appmod, "_MULTI_AUTO_LOCK")
            queue = getattr(appmod, "_MULTI_PENDING_QUEUE")
            with lock:
                idx = next(
                    (i for i, row in enumerate(queue)
                     if str((row or {}).get("bucket") or "") == bucket),
                    None,
                )
                if idx is not None and idx > 0:
                    row = queue.pop(idx)
                    queue.insert(0, row)
                pending = len(queue)
                retry_row = dict((getattr(appmod, "_MULTI_DEEP_RETRY", {}) or {}).get(bucket) or {})

            return jsonify({
                "success": False,
                "busy": True,
                "deferred": True,
                "queued": True,
                "job_state": "QUEUED_EXISTING_DEEP_LANE",
                "symbol": symbol,
                "timeframe": timeframe,
                "pending_queue": pending,
                "retry_after_ms": 7000,
                "runtime_retry_state": retry_row.get("state"),
                "error": (
                    "Multi-Activo fue colocado en la cola profunda existente; "
                    "la página no esperará el cálculo pesado dentro del request."
                ),
            }), 202
        except Exception as exc:
            return jsonify({
                "success": False,
                "busy": True,
                "deferred": True,
                "retry_after_ms": 7000,
                "error": str(exc)[:180],
            }), 202

    _nonblocking._st175107_nonblocking_multi_ui = True
    _nonblocking._st175107_original = original
    appmod.api_multiasset_analyze = _nonblocking
    try:
        flask_app.view_functions["api_multiasset_analyze"] = _nonblocking
    except Exception:
        return False
    return True

def _install_leverage_visibility_consistency() -> bool:
    """17.5.10 says x4 is diagnostic only; UI reads must honor that contract."""
    appmod = sys.modules.get("app")
    if appmod is None:
        return False
    original = getattr(appmod, "_derivative_premium_leverage_ok", None)
    if not callable(original):
        return False
    if getattr(original, "_st175107_visibility_consistency", False):
        return True

    @wraps(original)
    def _visible(leverage):
        try:
            from flask import has_request_context, request
            if has_request_context() and request.method == "GET" and request.path in {
                "/api/futures/signals/active",
                "/api/futures/signals/previous",
            }:
                # The technical per-timeframe leverage range remains enforced by
                # _leverage_in_valid_range.  Only the obsolete x4 *product*
                # filter is neutralized on visibility routes.
                return True
        except Exception:
            pass
        return original(leverage)

    _visible._st175107_visibility_consistency = True
    _visible._st175107_original = original
    appmod._derivative_premium_leverage_ok = _visible
    return True


def _risk_defaults() -> Dict[str, Any]:
    return {
        "futures_risk_mode": "MANUAL",
        "futures_margin_policy": "FIXED_USDT",
        "futures_equity_usdt": None,
        "futures_max_allocation_pct": None,
        "futures_max_loss_pct_equity_per_trade": None,
        "futures_preferred_margin_usdt": None,
        "futures_personal_max_leverage": None,
        "futures_risk_updated_at": None,
    }


def _normalize_risk_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    out = _risk_defaults()
    row = dict(row or {})
    mode = _u(row.get("futures_risk_mode") or "MANUAL")
    out["futures_risk_mode"] = mode if mode in {"MANUAL", "PROFILE_ADVISORY"} else "MANUAL"
    policy = _u(row.get("futures_margin_policy") or "FIXED_USDT")
    out["futures_margin_policy"] = policy if policy in {"FIXED_USDT", "EQUITY_PCT"} else "FIXED_USDT"
    for key in (
        "futures_equity_usdt",
        "futures_max_allocation_pct",
        "futures_max_loss_pct_equity_per_trade",
        "futures_preferred_margin_usdt",
    ):
        raw = row.get(key)
        try:
            out[key] = float(raw) if raw is not None else None
        except Exception:
            out[key] = None
    try:
        raw_lev = row.get("futures_personal_max_leverage")
        out["futures_personal_max_leverage"] = int(raw_lev) if raw_lev is not None else None
    except Exception:
        out["futures_personal_max_leverage"] = None
    out["futures_risk_updated_at"] = row.get("futures_risk_updated_at")
    return out


def _install_bounded_risk_profile_read() -> bool:
    """Use existing bounded REST transport; no new worker/thread or polling."""
    try:
        from supabase_client import supabase_client
    except Exception:
        return False
    if supabase_client is None:
        return False
    original = getattr(supabase_client, "get_user_futures_risk_profile", None)
    if not callable(original):
        return False
    if getattr(original, "_st175107_bounded_risk_read", False):
        return True

    cache: Dict[str, Dict[str, Any]] = {}
    cache_lock = threading.RLock()
    ttl = 300.0

    @wraps(original)
    def _bounded(user_name: str) -> Dict[str, Any]:
        user = str(user_name or "").strip()
        if not user:
            return _risk_defaults()
        now = time.monotonic()
        with cache_lock:
            hit = cache.get(user) or {}
            if hit and now - _f(hit.get("ts"), 0.0) < ttl:
                return dict(hit.get("value") or _risk_defaults())

        # The app's current Supabase project must be the real project configured
        # by Render env vars. No URL/key is hard-coded here.
        try:
            if not getattr(supabase_client, "enabled", False):
                raise RuntimeError("SUPABASE_DISABLED")
            if callable(getattr(supabase_client, "provider_restricted", None)) and supabase_client.provider_restricted():
                raise RuntimeError("SUPABASE_PROVIDER_RESTRICTED")
            if callable(getattr(supabase_client, "read_circuit_open", None)) and supabase_client.read_circuit_open():
                raise RuntimeError("SUPABASE_CIRCUIT_OPEN")
            request_fn = getattr(supabase_client, "_rest_minimal", None)
            if not callable(request_fn):
                raise RuntimeError("BOUNDED_REST_UNAVAILABLE")
            select = (
                "futures_risk_mode,futures_margin_policy,futures_equity_usdt,"
                "futures_max_allocation_pct,futures_max_loss_pct_equity_per_trade,"
                "futures_preferred_margin_usdt,futures_personal_max_leverage,"
                "futures_risk_updated_at"
            )
            response = request_fn(
                "GET",
                "user_preferences",
                params={
                    "select": select,
                    "user_name": f"eq.{user}",
                    "limit": "1",
                },
                timeout=(0.9, 2.2),
                prefer="return=minimal",
            )
            rows = response.json() if response is not None and callable(getattr(response, "json", None)) else []
            value = _normalize_risk_row(rows[0] if isinstance(rows, list) and rows else {})
            with cache_lock:
                cache[user] = {"ts": now, "value": dict(value)}
            return value
        except Exception:
            with cache_lock:
                stale = cache.get(user) or {}
                if stale:
                    return dict(stale.get("value") or _risk_defaults())
            return _risk_defaults()

    _bounded._st175107_bounded_risk_read = True
    _bounded._st175107_original = original
    supabase_client.get_user_futures_risk_profile = _bounded

    # Keep the cache coherent after an explicit profile save.  No extra read.
    upsert = getattr(supabase_client, "upsert_user_futures_risk_profile", None)
    if callable(upsert) and not getattr(upsert, "_st175107_risk_cache_write", False):
        @wraps(upsert)
        def _upsert(user_name: str, profile: Mapping[str, Any]):
            ok = upsert(user_name, profile)
            if ok:
                value = _normalize_risk_row(profile or {})
                value["futures_risk_updated_at"] = value.get("futures_risk_updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                with cache_lock:
                    cache[str(user_name or "").strip()] = {"ts": time.monotonic(), "value": value}
            return ok
        _upsert._st175107_risk_cache_write = True
        _upsert._st175107_original = upsert
        supabase_client.upsert_user_futures_risk_profile = _upsert

    return True


def install_strategy_quality_extension_175105() -> Dict[str, Any]:
    """Compatibility entry point already called by execution_abi_175104.py.

    Runtime hooks are retried on later ABI calls if the very first import
    happened while app.py was still defining its routes/helpers.
    """
    with _LOCK:
        if not _STATE["strategy_scope_installed"]:
            scope = _install_strategy_scope()
            _STATE.update(scope)
            _STATE["strategy_scope_installed"] = True

        if not _STATE["invalidation_corridor_installed"]:
            _STATE["invalidation_corridor_installed"] = _install_invalidation_corridor()
        if not _STATE["cache_only_reads_installed"]:
            _STATE["cache_only_reads_installed"] = _install_cache_only_futures_reads()
        if not _STATE["multiasset_nonblocking_ui_installed"]:
            _STATE["multiasset_nonblocking_ui_installed"] = _install_multiasset_nonblocking_ui()
        if not _STATE["risk_profile_bounded_read_installed"]:
            _STATE["risk_profile_bounded_read_installed"] = _install_bounded_risk_profile_read()
        if not _STATE["leverage_visibility_consistency_installed"]:
            _STATE["leverage_visibility_consistency_installed"] = _install_leverage_visibility_consistency()

        _STATE.update({
            "installed": True,
            "version": VERSION,
            "continuation_authority": "SHADOW_ONLY_SMALL_SAMPLE",
            "no_signal_count_quota": True,
            "sl_guard_preserved": True,
            "rr_floor_preserved": True,
            "safety_preserved": True,
            "no_new_threads": True,
            "no_new_db_tables": True,
            "no_new_market_requests": True,
            "no_new_llm_calls": True,
        })
        return dict(_STATE)
