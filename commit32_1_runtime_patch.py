"""Commit 32.1 — recovery over Commit 32.

Repairs observed production failures without relaxing final trading authority:
1) Multi/Futures execution ABI self-heal + boot-visible diagnostics.
2) Lightweight chart lane that cannot be starved by the heavy analysis lock.
3) Memory admission tuned to observed steady RSS, with single-heavy discipline,
   actual Futures/Multi geometry checkpoints and post-job heap trim.
4) Second-chance graded setup candidate generation. Geometry, specialised Safety,
   hard risk and validated OOS/LIVE route remain mandatory.
5) Research-only registry for CRT / Triple RSI / other hypotheses.
"""
from __future__ import annotations

import functools
import inspect
import os
import threading
from collections import Counter
from typing import Any, Dict

from commit32_1_candidate_recovery import VERSION as RECOVERY_VERSION, recover_candidate
from commit32_1_research_registry import VERSION as RESEARCH_VERSION, assert_no_live_authority, snapshot as research_snapshot

VERSION = "COMMIT32_1_RECOVERY_V1"
PUBLICATION_POLICY_VERSION = "COMMIT32_1_PUBLICATION_AUDIT_V1"
_COUNTERS = Counter()
_COUNTER_LOCK = threading.Lock()
_INSTALLED = False


def _inc(key: str, n: int = 1) -> None:
    with _COUNTER_LOCK:
        _COUNTERS[str(key)] += int(n)


def counters() -> Dict[str, int]:
    with _COUNTER_LOCK:
        return dict(_COUNTERS)


def _rss(app_module: Any) -> float | None:
    try:
        fn = getattr(app_module, "_process_rss_mb", None)
        value = fn() if callable(fn) else None
        return float(value) if value is not None else None
    except Exception:
        return None


def _shed(app_module: Any, reason: str, *, aggressive: bool = True) -> float | None:
    fn = getattr(app_module, "_shed_recreatable_memory", None)
    if callable(fn):
        try:
            fn(reason=f"commit32.1:{reason}", aggressive=aggressive)
            _inc("memory_shed")
        except Exception:
            pass
    trim = getattr(app_module, "_trim_process_heap", None)
    if callable(trim):
        try:
            trim()
            _inc("heap_trim")
        except Exception:
            pass
    return _rss(app_module)


def _memory_checkpoint(app_module: Any, label: str, *, abort: bool = True) -> float | None:
    rss = _rss(app_module)
    if rss is None:
        return None
    shed_mb = float(os.getenv("COMMIT32_1_RAM_SHED_MB", "285") or 285)
    abort_mb = float(os.getenv("COMMIT32_1_RAM_ABORT_MB", "335") or 335)
    if rss >= shed_mb:
        rss = _shed(app_module, label, aggressive=True)
    if abort and rss is not None and rss >= abort_mb:
        _inc("memory_abort_" + label)
        raise RuntimeError(f"RESOURCE_PRESSURE_ABORT_COMMIT32_1:{label}:{rss:.1f}MB")
    return rss


def _install_memory_authority(app_module: Any) -> None:
    """Replace starvation-prone admission limits while preserving one heavy slot."""
    start_mb = float(os.getenv("COMMIT32_1_JOB_START_MB", "240") or 240)
    soft_mb = float(os.getenv("COMMIT32_1_MEMORY_SOFT_MB", "280") or 280)
    hard_mb = float(os.getenv("COMMIT32_1_MEMORY_HARD_MB", "350") or 350)
    app_module._MEMORY_JOB_START_LIMIT_MB = start_mb
    app_module._MEMORY_SOFT_LIMIT_MB = soft_mb
    app_module._MEMORY_HARD_LIMIT_MB = hard_mb
    # C32 checkpoint reads its own env variables at call time. Keep both layers
    # consistent so C32 cannot abort at the old 285 MB threshold before 32.1.
    os.environ["COMMIT32_RAM_SHED_MB"] = os.getenv("COMMIT32_1_RAM_SHED_MB", "285")
    os.environ["COMMIT32_RAM_ABORT_MB"] = os.getenv("COMMIT32_1_RAM_ABORT_MB", "335")
    os.environ["MEMORY_IN_JOB_ABORT_MB"] = os.getenv("COMMIT32_1_RAM_ABORT_MB", "335")

    original = getattr(app_module, "_free_runtime_background_start_limit", None)
    if callable(original) and not getattr(original, "_commit32_1_wrapped", False):
        @functools.wraps(original)
        def start_limit(owner):
            text = str(owner or "")
            # Long-context passes keep slightly more headroom but are no longer
            # pinned below the observed idle/steady RSS (~215-250 MB).
            if text.startswith("multi-background:") and text.endswith(":1D"):
                return min(start_mb, 235.0)
            if text.startswith("futures-incremental:") and (text.endswith(":12h") or text.endswith(":1D")):
                return min(start_mb, 235.0)
            return start_mb
        start_limit._commit32_1_wrapped = True
        app_module._free_runtime_background_start_limit = start_limit
    setattr(app_module, "COMMIT32_1_MEMORY_AUTHORITY", {
        "job_start_mb": start_mb, "soft_mb": soft_mb, "hard_mb": hard_mb,
        "single_heavy_slot": True,
    })


def _install_execution_abi_and_geometry_guard(app_module: Any) -> None:
    import futures_system as fut
    import multiasset_system as multi

    fs_cls = fut.FuturesAnalysis
    multi_cls = multi.MultiAssetAnalysis
    fs_method = getattr(fs_cls, "calculate_entry_levels", None)
    if not callable(fs_method):
        raise RuntimeError("Commit32.1: Futures calculate_entry_levels missing")
    if "execution_observations" not in inspect.signature(fs_method).parameters:
        raise RuntimeError("Commit32.1: current Futures ABI does not expose execution_observations")

    # Guard the ACTUAL Futures override, not only the app.py base class.
    if not getattr(fs_method, "_commit32_1_geometry_wrapped", False):
        original_fs = fs_method
        @functools.wraps(original_fs)
        def fs_wrapped(self, decision, trend, momentum, volatility, structure,
                       symbol, timeframe, liquidation=None, execution_observations=None):
            _memory_checkpoint(app_module, "before_futures_geometry")
            try:
                return original_fs(
                    self, decision, trend, momentum, volatility, structure,
                    symbol, timeframe, liquidation=liquidation,
                    execution_observations=execution_observations,
                )
            finally:
                rss = _rss(app_module)
                if rss is not None and rss >= float(os.getenv("COMMIT32_1_RAM_SHED_MB", "285") or 285):
                    _shed(app_module, "after_futures_geometry", aggressive=True)
        fs_wrapped._commit32_1_geometry_wrapped = True
        fs_cls.calculate_entry_levels = fs_wrapped

    # Explicit Multi ABI method. This removes ambiguity from inherited/stale
    # wrappers and makes the runtime contract inspectable by the boot guard.
    old_multi = getattr(multi_cls, "calculate_entry_levels", None)
    if not getattr(old_multi, "_commit32_1_multi_abi", False):
        @functools.wraps(fs_cls.calculate_entry_levels)
        def multi_wrapped(self, decision, trend, momentum, volatility, structure,
                          symbol, timeframe, liquidation=None, execution_observations=None):
            _inc("multi_geometry_calls")
            _memory_checkpoint(app_module, "before_multi_geometry")
            return fs_cls.calculate_entry_levels(
                self, decision, trend, momentum, volatility, structure,
                symbol, timeframe, liquidation=liquidation,
                execution_observations=execution_observations,
            )
        multi_wrapped._commit32_1_multi_abi = True
        multi_cls.calculate_entry_levels = multi_wrapped

    # Recreate singleton only if it is not actually an instance of the declared
    # class. Normal healthy runtime keeps the existing cache-bearing instance.
    instance = getattr(multi, "multiasset_system", None)
    if not isinstance(instance, multi_cls):
        multi.multiasset_system = multi_cls()
        instance = multi.multiasset_system
        _inc("multi_singleton_recreated")
    if hasattr(app_module, "multiasset_system") and not isinstance(getattr(app_module, "multiasset_system"), multi_cls):
        app_module.multiasset_system = instance

    # Hard postcondition: both the class and live singleton expose the ABI.
    for target, label in ((multi_cls.calculate_entry_levels, "MultiAssetAnalysis"), (instance.calculate_entry_levels, "multiasset_system singleton")):
        if "execution_observations" not in inspect.signature(target).parameters:
            raise RuntimeError(f"Commit32.1: {label} ABI still missing execution_observations")
    setattr(multi, "COMMIT32_1_EXECUTION_ABI", VERSION)
    setattr(app_module, "COMMIT32_1_MULTI_ABI_OK", True)


def _extract_response_payload(result: Any):
    status = 200
    response = result
    extra = ()
    if isinstance(result, tuple):
        response = result[0]
        if len(result) > 1 and isinstance(result[1], int):
            status = result[1]
            extra = tuple(result[2:])
    try:
        payload = response.get_json(silent=True) if hasattr(response, "get_json") else None
    except Exception:
        payload = None
    return response, status, extra, payload


def _build_light_df(df_obj: Any) -> Dict[str, Any] | None:
    if df_obj is None or getattr(df_obj, "empty", True):
        return None
    work = df_obj.tail(120)
    time_col = "time" if "time" in work.columns else ("timestamp" if "timestamp" in work.columns else None)
    if time_col is None:
        return None
    n = len(work)
    return {
        "time": [str(x) for x in work[time_col].astype(str).tolist()],
        "open": [float(x) for x in work["open"].tolist()],
        "high": [float(x) for x in work["high"].tolist()],
        "low": [float(x) for x in work["low"].tolist()],
        "close": [float(x) for x in work["close"].tolist()],
        "volume": [float(x) for x in work["volume"].tolist()] if "volume" in work.columns else [0.0] * n,
    }


def _install_visual_lane(app_module: Any) -> None:
    flask_app = getattr(app_module, "app", None)
    jsonify = getattr(app_module, "jsonify", None)
    request = getattr(app_module, "request", None)
    if flask_app is None or not callable(jsonify) or request is None:
        return
    endpoint = "api_futures_visuals"
    original = flask_app.view_functions.get(endpoint)
    if not callable(original) or getattr(original, "_commit32_1_visual", False):
        return

    @functools.wraps(original)
    def visual_lane(*args, **kwargs):
        result = original(*args, **kwargs)
        _, status, _, payload = _extract_response_payload(result)
        if status < 400 and isinstance(payload, dict) and payload.get("df"):
            return result
        if not (isinstance(payload, dict) and payload.get("deferred") and not payload.get("df")):
            return result
        rss = _rss(app_module)
        extreme = float(os.getenv("COMMIT32_1_VISUAL_HARD_RSS_MB", "360") or 360)
        if rss is not None and rss >= extreme:
            _inc("visual_extreme_defer")
            return result
        symbol = str(request.args.get("symbol") or "BTC-USDT").strip().upper().replace("/", "-")
        timeframe = str(request.args.get("timeframe") or "1h").strip()
        market = str(request.args.get("market") or "futures").strip().lower()
        try:
            if market == "multiasset":
                engine = app_module._get_multiasset_system()
                df_obj = engine.get_kucoin_data(symbol, timeframe) if engine is not None else None
            elif market == "futures":
                engine = app_module._get_futures_system()
                df_obj = engine.get_kucoin_data(symbol, timeframe) if engine is not None else None
            else:
                from kucoin_cache import fetch_kucoin_candles
                df_obj = fetch_kucoin_candles(symbol, timeframe, timeout=8)
            df = _build_light_df(df_obj)
            if not df:
                _inc("visual_light_fetch_empty")
                return result
            _inc("visual_light_lane_served")
            return jsonify({
                "success": True,
                "source": "COMMIT32_1_OHLC_ONLY_VISUAL_LANE",
                "symbol": symbol, "timeframe": timeframe, "market": market,
                "system_type": "futures" if market == "futures" else market,
                "df": df,
                "heavy_analysis_bypassed_for_display_only": True,
                "rss_mb": rss,
            }), 200
        except Exception as exc:
            _inc("visual_light_fetch_error")
            # Preserve original deferred response rather than turn a display-only
            # recovery failure into a 500.
            return result

    visual_lane._commit32_1_visual = True
    flask_app.view_functions[endpoint] = visual_lane
    setattr(app_module, "COMMIT32_1_VISUAL_LANE", True)


def _install_candidate_recovery(app_module: Any) -> None:
    import pipeline_integrity_175101 as shim
    import pipeline_integrity_175102 as impl
    original = getattr(impl, "reconcile_operational_candidate", None)
    if not callable(original) or getattr(original, "_commit32_1_candidate", False):
        return

    @functools.wraps(original)
    def wrapped(operational, *, layers, symbol, timeframe, system_type):
        out = original(operational, layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type)
        if str(system_type or "").upper() == "FUTURES" and isinstance(out, dict) and not out.get("candidate_ready"):
            _inc("candidate_second_chance_evaluated")
            recovered = recover_candidate(
                impl, out, layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type,
            )
            if recovered.get("commit32_1_candidate_recovered"):
                _inc("candidate_second_chance_recovered")
            else:
                reason = str(recovered.get("commit32_1_recovery_rejected_reason") or "UNKNOWN")
                _inc("candidate_second_chance_rejected_" + reason)
            return recovered
        return out

    wrapped._commit32_1_candidate = True
    impl.reconcile_operational_candidate = wrapped
    shim.reconcile_operational_candidate = wrapped
    setattr(impl, "COMMIT32_1_GRADED_RECOVERY", RECOVERY_VERSION)
    setattr(shim, "COMMIT32_1_GRADED_RECOVERY", RECOVERY_VERSION)


def _install_post_heavy_trim(app_module: Any) -> None:
    """Trim retained allocator pages after the actual Futures/Multi heavy pass."""
    try:
        import futures_system as fut
    except Exception:
        return
    cls = fut.FuturesAnalysis
    original = getattr(cls, "analyze_futures_market", None)
    if not callable(original) or getattr(original, "_commit32_1_post_trim", False):
        return
    @functools.wraps(original)
    def wrapped(self, *args, **kwargs):
        _memory_checkpoint(app_module, "before_futures_analysis")
        try:
            return original(self, *args, **kwargs)
        finally:
            rss = _rss(app_module)
            if rss is not None and rss >= float(os.getenv("COMMIT32_1_POST_JOB_TRIM_MB", "250") or 250):
                _shed(app_module, "after_futures_analysis", aggressive=True)
    wrapped._commit32_1_post_trim = True
    cls.analyze_futures_market = wrapped


def _install_publication_version(app_module: Any) -> None:
    if hasattr(app_module, "_COMMIT245_NATIVE_Q_VERSION"):
        app_module._COMMIT245_NATIVE_Q_VERSION = PUBLICATION_POLICY_VERSION
    setattr(app_module, "COMMIT32_1_PUBLICATION_POLICY_VERSION", PUBLICATION_POLICY_VERSION)


def _install_runtime_truth(app_module: Any) -> None:
    flask_app = getattr(app_module, "app", None)
    jsonify = getattr(app_module, "jsonify", None)
    if flask_app is None or not callable(jsonify):
        return
    endpoint = "api_runtime_version_commit31"
    original = flask_app.view_functions.get(endpoint)
    if callable(original) and not getattr(original, "_commit32_1_truth", False):
        @functools.wraps(original)
        def version_view(*args, **kwargs):
            result = original(*args, **kwargs)
            response, status, _, payload = _extract_response_payload(result)
            data = dict(payload or {})
            data.update({
                "version": VERSION,
                "entrypoint": "commit32_1_main_entrypoint:app",
                "publication_policy": PUBLICATION_POLICY_VERSION,
                "multi_execution_abi": "SELF_HEALED_AND_BOOT_GUARDED",
                "visual_lane": "OHLC_ONLY_HEAVY_LOCK_INDEPENDENT",
                "candidate_recovery": RECOVERY_VERSION,
                "research_registry": RESEARCH_VERSION,
            })
            contracts = dict(data.get("contracts") or {})
            contracts.update({
                "final_safety_unchanged": True,
                "validated_live_route_still_required": True,
                "fallback_can_publish": False,
                "research_strategies_can_publish": False,
                "signal_quota": False,
                "guardian_untouched": True,
            })
            data["contracts"] = contracts
            return jsonify(data), status
        version_view._commit32_1_truth = True
        flask_app.view_functions[endpoint] = version_view

    if "commit32_1_status" not in flask_app.view_functions:
        def status():
            require_auth = getattr(app_module, "_require_auth", None)
            if callable(require_auth):
                auth = require_auth()
                if not isinstance(auth, str):
                    return auth
            import futures_system as fut
            import multiasset_system as multi
            return jsonify({
                "success": True,
                "version": VERSION,
                "publication_policy": PUBLICATION_POLICY_VERSION,
                "rss_mb": _rss(app_module),
                "memory": dict(getattr(app_module, "COMMIT32_1_MEMORY_AUTHORITY", {}) or {}),
                "futures_abi": list(inspect.signature(fut.FuturesAnalysis.calculate_entry_levels).parameters),
                "multi_abi": list(inspect.signature(multi.MultiAssetAnalysis.calculate_entry_levels).parameters),
                "multi_singleton_type": type(multi.multiasset_system).__name__,
                "visual_lane": bool(getattr(app_module, "COMMIT32_1_VISUAL_LANE", False)),
                "candidate_recovery": RECOVERY_VERSION,
                "counters": counters(),
                "research": research_snapshot(),
            }), 200
        flask_app.add_url_rule("/api/commit32-1/status", "commit32_1_status", status, methods=["GET"])


def install(app_module: Any) -> Dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"installed": True, "version": VERSION, "idempotent": True}
    if not assert_no_live_authority():
        raise RuntimeError("Commit32.1: research registry unexpectedly has LIVE authority")
    _install_publication_version(app_module)
    _install_memory_authority(app_module)
    _install_execution_abi_and_geometry_guard(app_module)
    _install_post_heavy_trim(app_module)
    _install_visual_lane(app_module)
    _install_candidate_recovery(app_module)
    _install_runtime_truth(app_module)
    setattr(app_module, "COMMIT32_1_RUNTIME", {
        "version": VERSION,
        "publication_policy": PUBLICATION_POLICY_VERSION,
        "multi_abi_self_heal": True,
        "visual_lane_independent": True,
        "candidate_recovery": RECOVERY_VERSION,
        "research_registry": RESEARCH_VERSION,
        "guardian_untouched": True,
        "validated_live_route_still_mandatory": True,
    })
    _INSTALLED = True
    return {"installed": True, "version": VERSION, "idempotent": False}
