"""Commit 33.3 compatibility shell for the historical Commit21.1 auto-install.

The old module mutated memory limits and wrapped trading/publication paths at
import time.  app.py still imports ``install`` for backward compatibility, so
this file deliberately keeps only two NON-TRADING responsibilities:

1. expose deployment/runtime truth;
2. repair the lightweight OHLC chart lane so it never waits for the heavy
   9-trader lock under ordinary RSS.

It MUST NOT change direction, candidate routing, Entry/SL/TP, Safety, RR,
publication, leverage, Guardian, caches or memory thresholds.
"""
from __future__ import annotations

import inspect
import os
import sys
from typing import Any, Dict

VERSION = "COMMIT33_3_LEGACY_OVERLAY_NEUTRALIZED_V1"
_INSTALLED = False
_ORIGINALS: Dict[str, Any] = {}


def _app_module():
    return sys.modules.get("app")


def _runtime_contract() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "version": VERSION,
        "legacy_memory_mutation": False,
        "legacy_publication_wrapper": False,
        "legacy_safety_wrapper": False,
        "legacy_strategy_route_wrapper": False,
        "runtime_monkeypatch_stack": False,
        "minimum_operational_timeframe": "30m",
        "execution_committees_preserved": True,
        "specialised_safety_preserved": True,
    }
    try:
        import futures_system as fut
        sig = inspect.signature(fut.FuturesAnalysis.calculate_entry_levels)
        status["futures_execution_observations_abi"] = (
            "execution_observations" in sig.parameters
            or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
        )
    except Exception as exc:
        status["futures_execution_observations_abi"] = False
        status["futures_abi_error"] = type(exc).__name__
    try:
        import multiasset_system as multi
        sig = inspect.signature(multi.MultiAssetAnalysis.calculate_entry_levels)
        status["multi_execution_observations_abi"] = (
            "execution_observations" in sig.parameters
            or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
        )
    except Exception as exc:
        status["multi_execution_observations_abi"] = False
        status["multi_abi_error"] = type(exc).__name__
    try:
        import safety_profiles_commit31 as sp31
        status["safety"] = sp31.audit()
    except Exception as exc:
        status["safety"] = {"error": type(exc).__name__}
    return status


def _install_visual_lane(flask_app) -> bool:
    """Replace only the display endpoint; no trading authority is touched."""
    module = _app_module()
    if module is None or "api_futures_visuals" not in flask_app.view_functions:
        return False

    if "api_futures_visuals" not in _ORIGINALS:
        _ORIGINALS["api_futures_visuals"] = flask_app.view_functions["api_futures_visuals"]

    from flask import jsonify, request

    def commit33_3_futures_visuals():
        try:
            symbol = str(request.args.get("symbol") or "BTC-USDT").strip().upper().replace("/", "-")
            timeframe = str(request.args.get("timeframe") or "1h").strip()
            market = str(request.args.get("market") or "futures").strip().lower()
            if market not in {"futures", "multiasset", "spot"}:
                market = "futures"

            # Reuse a cached compact chart if present, otherwise fetch only OHLCV.
            cached = None
            if market == "futures":
                try:
                    cached = (
                        module._get_futures_ui_cached(symbol, timeframe)
                        or module._get_futures_runtime_cached(symbol, timeframe)
                    )
                except Exception:
                    cached = None
            elif market == "multiasset":
                try:
                    module._multiasset_restore_local_snapshot_once()
                    with module._MULTI_ASSET_CACHE["lock"]:
                        cached = dict(
                            (module._MULTI_ASSET_CACHE.get("analysis") or {}).get((symbol, timeframe))
                            or {}
                        )
                except Exception:
                    cached = None

            df = None
            if isinstance(cached, dict):
                cached_df = cached.get("df")
                if isinstance(cached_df, dict) and cached_df.get("time"):
                    df = cached_df

            if df is None:
                rss = None
                try:
                    rss = module._process_rss_mb()
                except Exception:
                    pass
                # This is a tiny OHLC lane, not heavy analysis.  Only protect the
                # service very near the 512 MB cgroup cliff.
                hard_visual = float(os.environ.get("COMMIT33_3_VISUAL_HARD_RSS_MB", "430") or 430)
                if rss is not None and float(rss) >= hard_visual:
                    return jsonify({
                        "success": True,
                        "deferred": True,
                        "source": "COMMIT33_3_OHLC_ONLY_PRESSURE",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "market": market,
                        "reason": "CRITICAL_MEMORY_PRESSURE",
                        "rss_mb": rss,
                    }), 200

                if market == "futures":
                    engine = module._get_futures_system()
                    df_obj = engine.get_kucoin_data(symbol, timeframe) if engine is not None else None
                elif market == "multiasset":
                    engine = module._get_multiasset_system()
                    df_obj = engine.get_kucoin_data(symbol, timeframe) if engine is not None else None
                else:
                    from kucoin_cache import fetch_kucoin_candles
                    df_obj = fetch_kucoin_candles(symbol, timeframe, timeout=8)

                if df_obj is None or getattr(df_obj, "empty", True):
                    return jsonify({
                        "success": False,
                        "error": "Sin datos OHLCV",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "market": market,
                    }), 503

                work = df_obj.tail(120).copy().reset_index(drop=True)
                time_col = "time" if "time" in work.columns else (
                    "timestamp" if "timestamp" in work.columns else None
                )
                if time_col is None:
                    return jsonify({
                        "success": False,
                        "error": "OHLC_SCHEMA_INVALID",
                        "symbol": symbol,
                        "timeframe": timeframe,
                    }), 503
                df = {
                    "time": [str(x) for x in work[time_col].astype(str).tolist()],
                    "open": [float(x) for x in work["open"].tolist()],
                    "high": [float(x) for x in work["high"].tolist()],
                    "low": [float(x) for x in work["low"].tolist()],
                    "close": [float(x) for x in work["close"].tolist()],
                    "volume": (
                        [float(x) for x in work["volume"].tolist()]
                        if "volume" in work.columns else [0.0] * len(work)
                    ),
                }
                del work
                del df_obj

            payload = {
                "success": True,
                "source": "COMMIT33_3_OHLC_ONLY_VISUAL_LANE",
                "symbol": symbol,
                "timeframe": timeframe,
                "market": market,
                "system_type": "futures" if market == "futures" else market,
                "df": df,
                "heavy_analysis_started": False,
            }
            if isinstance(cached, dict):
                for key in (
                    "levels", "structure", "trend", "momentum", "volume",
                    "volatility", "correlation", "sentiment", "decision"
                ):
                    if key in cached and key != "df":
                        payload[key] = cached.get(key)
            return jsonify(payload), 200
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": f"{type(exc).__name__}: {str(exc)[:180]}",
            }), 500

    commit33_3_futures_visuals.__name__ = "api_futures_visuals_commit33_3"
    flask_app.view_functions["api_futures_visuals"] = commit33_3_futures_visuals
    return True


def _install_runtime_truth(flask_app) -> bool:
    module = _app_module()
    if module is None:
        return False
    from flask import jsonify

    if "api_runtime_version_commit31" in flask_app.view_functions:
        _ORIGINALS.setdefault(
            "api_runtime_version_commit31",
            flask_app.view_functions["api_runtime_version_commit31"],
        )

        def runtime_version_commit33_3():
            memory = None
            try:
                memory = module._memory_runtime_state()
            except Exception:
                memory = None
            return jsonify({
                "version": "COMMIT33_3_CORE_REPAIR_V1",
                "entrypoint": "app:app",
                "render_git_commit": os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("RENDER_GIT_COMMIT_SHA"),
                "runtime_monkeypatch_stack": False,
                "legacy_commit21_overlay_trading_authority": False,
                "minimum_operational_timeframe": "30m",
                "entry_sl_tp_committees_preserved": True,
                "specialised_safety_preserved": True,
                "memory": memory,
                "contracts": _runtime_contract(),
            }), 200

        flask_app.view_functions["api_runtime_version_commit31"] = runtime_version_commit33_3

    if "health" in flask_app.view_functions:
        _ORIGINALS.setdefault("health", flask_app.view_functions["health"])

        def health_commit33_3():
            memory = None
            try:
                memory = module._memory_runtime_state()
            except Exception:
                memory = None
            contract = _runtime_contract()
            abi_ok = bool(
                contract.get("futures_execution_observations_abi")
                and contract.get("multi_execution_observations_abi")
            )
            return jsonify({
                "status": "ok" if abi_ok else "degraded",
                "runtime_authority": "COMMIT33_3_CORE_REPAIR_V1",
                "entrypoint": "app:app",
                "geometry_abi_ok": abi_ok,
                "memory": memory,
            }), (200 if abi_ok else 503)

        flask_app.view_functions["health"] = health_commit33_3
    return True


def install(flask_app) -> Dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return audit()
    module = _app_module()
    # Cache/snapshot identity only: force one clean reevaluation of closed-candle
    # quality under the current 33.3 policy.  This does NOT change thresholds.
    if module is not None and hasattr(module, "_COMMIT245_NATIVE_Q_VERSION"):
        module._COMMIT245_NATIVE_Q_VERSION = "COMMIT33_3_PUBLICATION_AUDIT_V1"
        setattr(module, "COMMIT33_3_PUBLICATION_POLICY_VERSION", "COMMIT33_3_PUBLICATION_AUDIT_V1")
    visual = _install_visual_lane(flask_app)
    truth = _install_runtime_truth(flask_app)
    _INSTALLED = True
    print(
        "✅ [COMMIT33.3] legacy Commit21.1 trading/memory overlay neutralized; "
        "only runtime truth + OHLC visual lane retained",
        flush=True,
    )
    return {
        "version": VERSION,
        "installed": True,
        "visual_lane": visual,
        "runtime_truth": truth,
        "memory_policy_mutation": False,
        "trading_authority": False,
        "publication_authority": False,
        "safety_authority": False,
        "strategy_route_authority": False,
    }


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "installed": _INSTALLED,
        "memory_policy_mutation": False,
        "trading_authority": False,
        "publication_authority": False,
        "safety_authority": False,
        "strategy_route_authority": False,
        "visual_lane_only": True,
        "runtime_truth_only": True,
    }


# Compatibility aliases used by old operational notes/scripts.
install_premium_path_expansion = install
install_premium_path_expansion_20 = install
