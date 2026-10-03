"""Commit 22 — Quality Path Expansion built from stable Commit 20.2.1 + Q1-Q9 context groups.

The stable 20.2.1 runtime remains the base. This overlay changes only how the
already-bounded alternative geometries are compared: Q1..Q9 select the route
with the deepest contextual quality, while Q10 is the unchanged hard safety /
economic publication gate.
"""
from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Dict, Mapping

import quality_9q_engine_21 as q9

VERSION = "COMMIT22_CONTEXT_QUALITY_AUTHORITY_V1"
MAX_ALTERNATIVE_ROUTES = 2


def _f(v: Any, d: float = 0.0) -> float:
    try:
        n = float(v)
        return n if n == n and abs(n) != float("inf") else d
    except Exception:
        return d


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _context_levels(levels: Mapping[str, Any], trend: Mapping[str, Any], momentum: Mapping[str, Any], volatility: Mapping[str, Any], structure: Mapping[str, Any], symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    out = dict(levels or {})
    out["_commit21_quality_context"] = {
        "trend": dict(trend or {}),
        "momentum": dict(momentum or {}),
        "volatility": dict(volatility or {}),
        "structure": dict(structure or {}),
        "symbol": str(symbol or ""),
        "timeframe": str(timeframe or ""),
        "action": str(action or ""),
    }
    return out


def _market_type(symbol: str, levels: Mapping[str, Any] | None = None) -> str:
    l = dict(levels or {})
    raw = str(l.get("market_type") or l.get("market") or "").strip().lower()
    if raw in {"multiasset", "multi-asset", "multi"}:
        return "multiasset"
    try:
        from premium_path_expansion_20 import _market_type_for_symbol
        return str(_market_type_for_symbol(symbol) or "futures")
    except Exception:
        return "futures"


def _evaluate(levels: Mapping[str, Any], trend: Mapping[str, Any], momentum: Mapping[str, Any], volatility: Mapping[str, Any], structure: Mapping[str, Any], symbol: str, timeframe: str, action: str, market_type: str | None = None) -> Dict[str, Any]:
    resolved = str(market_type or _market_type(symbol, levels) or "futures")
    return q9.evaluate(levels, trend, momentum, volatility, structure, timeframe, symbol, action, market_type=resolved)


def _q10_hard_violation_codes(levels: Mapping[str, Any], timeframe: str = "") -> list[str]:
    """Pre-publication hard-contract screen used only to rank route candidates.

    This mirrors the already-existing Futures publication limits so Q1-Q9 never
    selects an alternative that is known in advance to fail Q10 while another
    generated route is economically/publication-valid. The final native gate
    remains authoritative and is still executed downstream.
    """
    l = dict(levels or {})
    risk_control = dict(l.get("risk_control") or {})

    def f(value, default=0.0):
        try:
            x = float(value if value is not None else default)
            return x if x == x else float(default)
        except Exception:
            return float(default)

    try:
        import futures_system
        cfg = getattr(futures_system, "FUTURES_RISK_CONFIG", {}) or {}
    except Exception:
        cfg = {}

    safety_min = f(cfg.get("minimum_publication_execution_safety"), 75.0)
    tp_min = f(cfg.get("minimum_publication_tp_quality"), 55.0)
    sl_min = f(cfg.get("minimum_publication_sl_avoidance_quality"), 60.0)
    rr_min = max(1.0, f(l.get("minimum_viable_rr"), f(cfg.get("minimum_publication_rr"), 1.8)))
    rr_max = max(rr_min, f(l.get("maximum_technical_rr"), f(cfg.get("maximum_publication_rr"), 3.5)))
    sl = f(l.get("sl_reliability"), 0.0)
    sl_quality = sl * 100.0 if sl <= 1.0 else sl
    rr = f(l.get("risk_reward"), 0.0)
    safety = f(l.get("execution_safety"), 0.0)
    tp = f(l.get("tp_quality_score"), 0.0)
    planned_sl = f(risk_control.get("estimated_sl_loss_pct_margin"), abs(f(l.get("roi_sl"), 0.0)))
    atr_stress = f(risk_control.get("estimated_atr_stress_loss_pct_margin"), 0.0)
    loss_max = f(cfg.get("maximum_publication_loss_pct_margin"), 8.0)
    atr_max = f(cfg.get("maximum_publication_atr_stress_loss_pct_margin"), 25.0)

    codes = []
    if safety < safety_min: codes.append("SAFETY")
    if tp < tp_min: codes.append("TP_QUALITY")
    if sl_quality < sl_min: codes.append("SL_QUALITY")
    if not (rr_min <= rr <= rr_max): codes.append("RR")
    if planned_sl > loss_max: codes.append("LOSS_AT_SL")
    if not (0 < atr_stress <= atr_max): codes.append("ATR_STRESS")
    return codes


def _route_geometry_score(levels: Mapping[str, Any]) -> float:
    try:
        from premium_path_expansion_20 import _geometry_score
        return float(_geometry_score(levels))
    except Exception:
        entry = _f(levels.get("entry_score") or levels.get("entry_quality_score"))
        sl = _f(levels.get("sl_reliability")); sl = sl * 100 if sl <= 1 else sl
        tp = _f(levels.get("tp_quality_score"))
        return max(0.0, min(100.0, .34 * entry + .33 * sl + .33 * tp))


def install_quality_geometry_router() -> Dict[str, Any]:
    try:
        import app as app_module
        cls = getattr(app_module, "TradingExpertSystem", None)
        current = getattr(cls, "calculate_entry_levels", None) if cls else None
        if not callable(current):
            return {"installed": False, "reason": "LEVEL_METHOD_NOT_FOUND"}
        if getattr(current, "_commit21_9q_geometry", False):
            return {"installed": True, "already": True}

        # Remove only the immediately preceding 20.2 PPE wrapper when it is
        # present. Do not recursively unwrap older execution layers because
        # those may contain legitimate baseline behaviour.
        if getattr(current, "_commit20_ppe", False) and callable(getattr(current, "__wrapped__", None)):
            native = current.__wrapped__
        else:
            native = current

        from premium_path_expansion_20 import (
            MAX_ALTERNATIVE_ROUTES as BASE_MAX_ROUTES,
            _clone_route_structure,
            _needs_route_expansion,
            _route_families,
        )
        max_routes = min(int(BASE_MAX_ROUTES), MAX_ALTERNATIVE_ROUTES)

        @wraps(current)
        def wrapped(self, decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation=None, execution_observations=None):
            baseline = native(
                self, decision, trend, momentum, volatility, structure, symbol, timeframe,
                liquidation=liquidation, execution_observations=execution_observations,
            )
            if not isinstance(baseline, dict):
                return baseline
            if _u(decision) not in {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}:
                return baseline

            # Spot keeps the stable 20.2.1 path. The new 9Q router is primarily
            # for Futures/Multi-Asset where the signal-density problem exists.
            try:
                from premium_path_expansion_20 import _market_type_for_symbol
                market_type = _market_type_for_symbol(symbol)
            except Exception:
                market_type = "futures"
            is_multi = market_type == "multiasset"
            is_futures = _u(decision) in {"LONG", "SHORT"}
            if not (is_futures or is_multi):
                baseline["commit21_9q_version"] = VERSION
                baseline["commit21_9q_route_selection"] = False
                return baseline
            if not _needs_route_expansion(baseline):
                q = _evaluate(baseline, trend, momentum, volatility, structure, symbol, timeframe, decision, market_type=market_type)
                baseline = _context_levels(baseline, trend, momentum, volatility, structure, symbol, timeframe, decision)
                baseline["commit21_9q_version"] = VERSION
                baseline["commit21_9q_route_selection"] = False
                baseline["quality_9q"] = q
                baseline["q10_safety_contract"] = "UNCHANGED"
                return baseline

            setup = str(
                ((structure or {}).get("_contingency_playbook") or {}).get("setup_family")
                or (structure or {}).get("setup_family")
                or "UNSPECIFIED"
            ).upper()
            routes = _route_families(
                setup_family=setup,
                trend=trend or {}, momentum=momentum or {}, volatility=volatility or {},
                structure=structure or {}, symbol=symbol, timeframe=timeframe,
                market_type=market_type,
            )[:max_routes]

            candidates = []
            baseline_q = _evaluate(baseline, trend, momentum, volatility, structure, symbol, timeframe, decision, market_type=market_type)
            candidates.append({
                "route": setup or "BASELINE",
                "levels": baseline,
                "geometry_score": _route_geometry_score(baseline),
                "quality": baseline_q,
            })
            meta = []
            for route in routes:
                try:
                    alt_structure = _clone_route_structure(structure or {}, route)
                    alt_levels = native(
                        self, decision, dict(trend or {}), dict(momentum or {}), dict(volatility or {}),
                        alt_structure, symbol, timeframe, liquidation=liquidation,
                        execution_observations=execution_observations,
                    )
                    if not isinstance(alt_levels, dict):
                        continue
                    if not (_f(alt_levels.get("entry")) > 0 and _f(alt_levels.get("stop_loss")) > 0 and _f(alt_levels.get("take_profit")) > 0 and _f(alt_levels.get("risk_reward")) > 0):
                        continue
                    quality = _evaluate(alt_levels, trend, momentum, volatility, alt_structure, symbol, timeframe, decision, market_type=market_type)
                    geometry_score = _route_geometry_score(alt_levels)
                    candidates.append({"route": route, "levels": alt_levels, "geometry_score": geometry_score, "quality": quality})
                    meta.append({
                        "route": route,
                        "geometry_score": round(geometry_score, 2),
                        "q9_composite": quality.get("composite"),
                        "q9_quality_ready": bool(quality.get("quality_ready")),
                        "q9_quality": quality.get("quality"),
                        "rr": _f(alt_levels.get("risk_reward")),
                    })
                except Exception as exc:
                    meta.append({"route": route, "error": type(exc).__name__})

            q10_viable = []
            for row in candidates:
                row["q9_route_score"] = q9.route_score(row["quality"], row["geometry_score"])
                row["q10_hard_violation_codes"] = _q10_hard_violation_codes(row["levels"], timeframe)
                row["q10_preeligible"] = not row["q10_hard_violation_codes"]
                if row["q10_preeligible"]:
                    q10_viable.append(row)

            # Q1-Q9 chooses quality ONLY among route geometries that do not
            # already violate the existing Q10 hard contract. If every generated
            # route fails Q10, keep the best Q1-Q9 route for diagnostics and let
            # the native publication gate reject it downstream. This prevents a
            # high 9Q score on an invalid RR/Safety package from replacing a
            # publishable baseline candidate.
            ranking_pool = q10_viable or candidates
            ranking_pool.sort(key=lambda row: (-row["q9_route_score"], -row["geometry_score"], 0 if row["route"] == setup else 1))
            selected = ranking_pool[0]
            for item in meta:
                route = item.get("route")
                match = next((c for c in candidates if c.get("route") == route), None)
                if match:
                    item["q10_preeligible"] = bool(match.get("q10_preeligible"))
                    item["q10_hard_violation_codes"] = list(match.get("q10_hard_violation_codes") or [])
            out = _context_levels(selected["levels"], trend, momentum, volatility, structure, symbol, timeframe, decision)
            out["commit21_9q_version"] = VERSION
            out["commit21_9q_route_selection"] = len(candidates) > 1
            out["commit21_9q_base_route"] = setup or "UNSPECIFIED"
            out["commit21_9q_selected_route"] = selected["route"]
            out["commit21_9q_route_candidates"] = meta[:max_routes]
            out["commit21_9q_route_score"] = selected["q9_route_score"]
            out["quality_9q"] = selected["quality"]
            out["q10_safety_contract"] = "UNCHANGED"
            return out

        wrapped._commit21_9q_geometry = True
        wrapped._commit20_ppe_superseded_for_quality = True
        cls.calculate_entry_levels = wrapped
        return {"installed": True, "already": False, "base": "20.2.1", "max_alternative_routes": max_routes}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install_quality_gate_contract() -> Dict[str, Any]:
    status = []
    try:
        import futures_system
        targets = [("FuturesAnalysis", getattr(futures_system, "FuturesAnalysis", None))]
        for name, cls in targets:
            current = getattr(cls, "_apply_futures_publication_gate", None) if cls else None
            if not callable(current) or getattr(current, "_commit21_9q_gate", False):
                continue
            @wraps(current)
            def wrapped(self, levels, timeframe, symbol="", action="", _original=current):
                out = _original(self, levels, timeframe, symbol=symbol, action=action)
                if not isinstance(out, dict):
                    return out
                lv = dict(out.get("levels") or levels or {})
                ctx = lv.get("_commit21_quality_context") if isinstance(lv.get("_commit21_quality_context"), dict) else {}
                trend = ctx.get("trend") or getattr(self, "_last_trend", {}) or {}
                momentum = ctx.get("momentum") or getattr(self, "_last_momentum", {}) or {}
                volatility = ctx.get("volatility") or getattr(self, "_last_volatility", {}) or {}
                structure = ctx.get("structure") or getattr(self, "_last_structure", {}) or {}
                q = _evaluate(lv, trend, momentum, volatility, structure, symbol, timeframe, action, market_type=_market_type(symbol, lv))
                q10 = q9.q10_safety_snapshot(out, lv)
                context_groups = dict(q.get("context_quality_groups") or {})
                gate = dict(out.get("futures_publication_gate") or {})
                legacy_safety = float(q10.get("execution_safety") or 0.0)
                reasons = [str(x).upper() for x in (gate.get("reason_codes") or [])]
                deep_upgrade_applied = False

                # COMMIT21.2 — Q1-Q9 becomes a genuine quality authority for the
                # legacy Safety score, but only inside the already-existing
                # operational safety band.  This does NOT lower any Q10 hard
                # threshold and does not rescue RR/loss/ATR violations.
                #
                # Why this bridge is necessary:
                # the old system calculates execution_safety first (65 operational,
                # 75 Premium) and the original 21.0/21.1 implementation only
                # recorded Q1-Q9 diagnostically.  Therefore a high deep-quality
                # thesis could never become the quality score consumed by the
                # existing publication filter.
                try:
                    from futures_system import FUTURES_RISK_CONFIG
                    operational_min = float((FUTURES_RISK_CONFIG or {}).get("minimum_execution_safety", 65.0) or 65.0)
                    q10_safety_min = float((FUTURES_RISK_CONFIG or {}).get("minimum_publication_execution_safety", 75.0) or 75.0)
                except Exception:
                    operational_min, q10_safety_min = 65.0, 75.0

                if (
                    not bool(gate.get("eligible"))
                    and bool(q.get("quality_ready"))
                    and legacy_safety >= operational_min
                    and set(reasons).issubset({"SAFETY"})
                ):
                    upgraded_safety = max(legacy_safety, float(q.get("composite") or legacy_safety))
                    if upgraded_safety >= q10_safety_min:
                        upgraded_levels = dict(out.get("levels") or lv or {})
                        upgraded_levels["legacy_execution_safety"] = legacy_safety
                        upgraded_levels["execution_safety"] = round(upgraded_safety, 1)
                        upgraded_levels["execution_safety_authority"] = "Q1_Q9_DEEP_QUALITY"
                        upgraded_levels["q1_q9_safety_upgrade"] = True
                        upgraded_levels.pop("_commit21_quality_context", None)
                        upgraded = current(self, upgraded_levels, timeframe, symbol=symbol, action=action)
                        if isinstance(upgraded, dict):
                            upgraded_gate = dict(upgraded.get("futures_publication_gate") or {})
                            if upgraded_gate.get("eligible"):
                                out = upgraded
                                gate = upgraded_gate
                                deep_upgrade_applied = True
                                q10 = q9.q10_safety_snapshot(out, upgraded_levels)
                                q10["legacy_execution_safety"] = round(legacy_safety, 2)
                                q10["deep_quality_safety_authority"] = True
                                q10["upgrade_points"] = round(upgraded_safety - legacy_safety, 2)

                gate["commit21_9q"] = q
                gate["q10_safety"] = q10
                gate["context_quality_groups"] = context_groups
                gate["context_quality_group_authority"] = bool(q.get("context_quality_authority"))
                gate["quality_model"] = q9.MODEL
                gate["q1_q9_safety_upgrade_applied"] = bool(deep_upgrade_applied)
                gate["legacy_execution_safety"] = round(legacy_safety, 2)
                gate["final_execution_safety"] = round(float((out.get("levels") or {}).get("execution_safety") or legacy_safety), 2)
                gate["hard_q10_thresholds_unchanged"] = True
                out["futures_publication_gate"] = gate
                out["quality_9q"] = q
                out["q10_safety"] = q10
                out["context_quality_groups"] = context_groups
                out["quality_authority"] = "Q1_Q9_PLUS_CONTEXT_GROUPS_PLUS_Q10_HARD_SAFETY"
                out["q1_q9_safety_upgrade_applied"] = bool(deep_upgrade_applied)
                if isinstance(out.get("levels"), dict):
                    out["levels"]["quality_9q"] = q
                    out["levels"]["q10_safety"] = q10
                    out["levels"]["context_quality_groups"] = context_groups
                    out["levels"]["q1_q9_safety_upgrade_applied"] = bool(deep_upgrade_applied)
                    out["levels"].pop("_commit21_quality_context", None)
                out["premium_blocker_stage_21"] = (
                    "Q10_SAFETY" if not gate.get("eligible") and not deep_upgrade_applied
                    else ("Q1_Q9_QUALITY_DIAGNOSTIC" if not q.get("quality_ready") else "NONE")
                )
                return out
            wrapped._commit21_9q_gate = True
            cls._apply_futures_publication_gate = wrapped
            status.append({"class": name, "installed": True})

        try:
            import multiasset_system
            cls = getattr(multiasset_system, "MultiAssetAnalysis", None)
            current = getattr(cls, "_apply_futures_publication_gate", None) if cls else None
            if callable(current) and not getattr(current, "_commit21_9q_gate", False):
                @wraps(current)
                def multi_wrapped(self, levels, timeframe, symbol="", action="", _original=current):
                    out = _original(self, levels, timeframe, symbol=symbol, action=action)
                    if not isinstance(out, dict):
                        return out
                    lv = dict(out.get("levels") or levels or {})
                    ctx = lv.get("_commit21_quality_context") if isinstance(lv.get("_commit21_quality_context"), dict) else {}
                    q = _evaluate(lv, ctx.get("trend") or {}, ctx.get("momentum") or {}, ctx.get("volatility") or {}, ctx.get("structure") or {}, symbol, timeframe, action, market_type=_market_type(symbol, lv))
                    q10 = q9.q10_safety_snapshot(out, lv)
                    context_groups = dict(q.get("context_quality_groups") or {})
                    gate = dict(out.get("futures_publication_gate") or {})
                    gate["commit21_9q"] = q
                    gate["q10_safety"] = q10
                    gate["context_quality_groups"] = context_groups
                    gate["context_quality_group_authority"] = bool(q.get("context_quality_authority"))
                    gate["quality_model"] = q9.MODEL
                    out["futures_publication_gate"] = gate
                    out["quality_9q"] = q
                    out["q10_safety"] = q10
                    out["context_quality_groups"] = context_groups
                    out["quality_authority"] = "Q1_Q9_PLUS_CONTEXT_GROUPS_PLUS_Q10_HARD_SAFETY"
                    if isinstance(out.get("levels"), dict):
                        out["levels"]["quality_9q"] = q
                        out["levels"]["q10_safety"] = q10
                        out["levels"]["context_quality_groups"] = context_groups
                        out["levels"].pop("_commit21_quality_context", None)
                    return out
                multi_wrapped._commit21_9q_gate = True
                cls._apply_futures_publication_gate = multi_wrapped
                status.append({"class": "MultiAssetAnalysis", "installed": True})
        except Exception as exc:
            status.append({"class": "MultiAssetAnalysis", "error": type(exc).__name__})
    except Exception as exc:
        status.append({"error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return {"patches": status}


def install_health_contract(app: Any) -> Dict[str, Any]:
    try:
        original = app.view_functions.get("health")
        if not callable(original):
            return {"installed": False, "reason": "HEALTH_NOT_FOUND"}
        if getattr(original, "_commit21_9q_health", False):
            return {"installed": True, "already": True}
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
            payload["commit21_9q"] = {
                "version": VERSION,
                "quality_engine": q9.VERSION,
                "quality_model": q9.MODEL,
                "context_quality_groups": "COMMIT22_CONTEXT_QUALITY_GROUPS_V1",
                "q10_safety_unchanged": True,
                "base_runtime": "COMMIT20_2_1_STABILITY_FIX_V1",
                "max_alternative_routes": MAX_ALTERNATIVE_ROUTES,
                "new_network_calls": False,
                "new_threads": False,
                "runtime_recovery": {
                    "request_timeout_seconds": 120,
                    "worker_recycle_max_requests": 80,
                    "worker_recycle_jitter": 20,
                    "policy": "RESTART_OVER_PERMANENT_HANG",
                },
            }
            return jsonify(payload)
        wrapped._commit21_9q_health = True
        app.view_functions["health"] = wrapped
        return {"installed": True}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install(app: Any) -> Dict[str, Any]:
    return {
        "version": VERSION,
        "quality_engine": q9.VERSION,
        "geometry": install_quality_geometry_router(),
        "gate": install_quality_gate_contract(),
        "health": install_health_contract(app),
        "base_runtime": "COMMIT20_2_1_STABILITY_FIX_V1",
    }
