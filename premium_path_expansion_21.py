"""Commit 23 — Parallel ten-filter quality authority built on stable Commit 20.2.1 + Commit 22 context groups.

The stable 20.2.1 runtime remains the base. This overlay changes only how the
already-bounded alternative geometries are compared: Q1..Q9 are preserved; ten parallel quality filters may confirm a route when
any one filter reaches 75/100 and universal execution guards pass. The legacy
Q10 contract remains fully visible as a diagnostic/legacy gate but is no longer
a mandatory second veto for a contextual quality-confirmed trade.
"""
from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Dict, Mapping

import quality_9q_engine_21 as q9

VERSION = "COMMIT23_TEN_FILTER_QUALITY_AUTHORITY_V1"
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




def _quality_filter_summary_text(parallel: Mapping[str, Any]) -> str:
    if not isinstance(parallel, Mapping):
        return ""
    selected = str(parallel.get("selected_filter") or "NONE").upper()
    selected_name = str(parallel.get("selected_filter_name") or "").strip()
    score = _f(parallel.get("selected_filter_score"), 0.0)
    passed = [str(x).upper() for x in (parallel.get("passed_filters") or [])]
    summary = str(parallel.get("summary") or "").strip()
    status = "✅ CONFIRMA" if parallel.get("confirmed_one_of_ten") else "⚪ NO CONFIRMA"
    passed_text = ", ".join(passed) if passed else "ninguno"
    label = f"{status} · filtro principal {selected}"
    if selected_name:
        label += f" {selected_name}"
    label += f" {score:.1f}/100 · pasan: {passed_text}"
    if summary:
        label += f" · {summary}"
    return label[:900]


def _attach_parallel_quality_metadata(
    out: Dict[str, Any],
    q: Mapping[str, Any],
    q10: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    symbol: str,
    timeframe: str,
    action: str,
) -> Dict[str, Any]:
    """Flatten the ten-filter trace so the frontend/Telegram serializers retain it."""
    result = dict(out or {})
    parallel = dict(q.get("parallel_quality_filters") or {})
    legacy_reasons = [str(x).upper() for x in (gate.get("reason_codes") or [])]
    parallel["legacy_publication_blockers"] = legacy_reasons
    parallel["legacy_q10_gate_eligible"] = bool(gate.get("eligible"))
    parallel["q10_is_required"] = False
    parallel["dedupe_key"] = f"{_u(symbol)}|{str(timeframe or '').strip()}"
    parallel["direction"] = str(action or "").upper()
    summary = _quality_filter_summary_text(parallel)
    result["quality_filter_trace"] = parallel
    result["parallel_quality_filters"] = parallel
    result["quality_filter_authority"] = str(parallel.get("selected_filter") or "NONE")
    result["quality_filter_name"] = str(parallel.get("selected_filter_name") or "")
    result["quality_filter_score"] = round(_f(parallel.get("selected_filter_score"), 0.0), 2)
    result["quality_filter_passed"] = list(parallel.get("passed_filters") or [])
    result["quality_filter_summary"] = summary
    result["quality_filter_confirmed"] = bool(parallel.get("confirmed_one_of_ten"))
    result["quality_filter_dedupe_key"] = parallel["dedupe_key"]
    result["quality_filter_dedupe_score"] = result["quality_filter_score"]
    result["q10_is_mandatory"] = True
    result["legacy_q10_gate_eligible"] = bool(gate.get("eligible"))
    result["legacy_q10_reason_codes"] = legacy_reasons
    result["parallel_quality_guard_codes"] = list((parallel.get("universal_guards") or {}).get("codes") or [])
    result["parallel_quality_safety_score"] = round(_f(parallel.get("safety_authority_score"), 0.0), 2)
    result["parallel_quality_min_score"] = float(q9.PARALLEL_FILTER_MIN_SCORE)
    result["quality_authority_policy"] = "COMMIT25_PARALLEL_DIAGNOSTIC_NATIVE_GATE_AUTHORITY"
    result["quality_filter_membership"] = list(parallel.get("passed_filters") or [])
    if isinstance(result.get("levels"), dict):
        lv = result["levels"]
        for key in (
            "quality_filter_trace", "parallel_quality_filters", "quality_filter_authority",
            "quality_filter_name", "quality_filter_score", "quality_filter_passed",
            "quality_filter_summary", "quality_filter_confirmed", "quality_filter_dedupe_key",
            "quality_filter_dedupe_score", "q10_is_mandatory", "legacy_q10_gate_eligible",
            "legacy_q10_reason_codes", "parallel_quality_guard_codes", "parallel_quality_safety_score",
            "parallel_quality_min_score", "quality_authority_policy", "quality_filter_membership",
        ):
            lv[key] = result.get(key)
    return result


def _try_parallel_quality_promotion(
    out: Dict[str, Any],
    q: Mapping[str, Any],
    q10: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    symbol: str,
    timeframe: str,
    action: str,
) -> tuple[Dict[str, Any], bool]:
    """Commit 25: Q1..Q10 parallel filters are diagnostics only.

    The former implementation could turn legacy SAFETY/TP/SL/RR failures into
    Premium when one correlated filter reached 75. That increases apparent
    frequency via winner's-curse/rule-fitting. The native publication gate is
    now the only authority; all Q traces remain available for diagnostics.
    """
    result = dict(out or {})
    parallel = dict(q.get("parallel_quality_filters") or {})
    result["commit25_parallel_quality_diagnostic_only"] = True
    result["commit25_parallel_quality_would_confirm"] = bool(parallel.get("confirmed_one_of_ten"))
    result["q10_is_mandatory"] = True
    return result, False

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
            baseline_parallel = dict(baseline_q.get("parallel_quality_filters") or {})
            candidates.append({
                "route": setup or "BASELINE",
                "levels": baseline,
                "geometry_score": _route_geometry_score(baseline),
                "quality": baseline_q,
                "parallel": baseline_parallel,
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
                    parallel = dict(quality.get("parallel_quality_filters") or {})
                    candidates.append({"route": route, "levels": alt_levels, "geometry_score": geometry_score, "quality": quality, "parallel": parallel})
                    meta.append({
                        "route": route,
                        "geometry_score": round(geometry_score, 2),
                        "q9_composite": quality.get("composite"),
                        "q9_quality_ready": bool(quality.get("quality_ready")),
                        "q9_quality": quality.get("quality"),
                        "rr": _f(alt_levels.get("risk_reward")),
                        "quality_filter": parallel.get("selected_filter"),
                        "quality_filter_score": parallel.get("selected_filter_score"),
                        "quality_filter_confirmed": bool(parallel.get("publication_candidate")),
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
            # Commit 23 — route selection now considers the parallel quality authority
            # before the legacy Q10 gate. A route with one valid >=75 quality filter
            # can win even when the legacy gate rejects only SAFETY/TP/SL/RR.
            ranking_pool = candidates
            ranking_pool.sort(key=lambda row: (
                -int(bool((row.get("parallel") or {}).get("publication_candidate"))),
                -_f((row.get("parallel") or {}).get("selected_filter_score"), 0.0),
                -row["q9_route_score"],
                -row["geometry_score"],
                0 if row["route"] == setup else 1,
            ))
            selected = ranking_pool[0]
            for item in meta:
                route = item.get("route")
                match = next((c for c in candidates if c.get("route") == route), None)
                if match:
                    item["q10_preeligible"] = bool(match.get("q10_preeligible"))
                    item["q10_hard_violation_codes"] = list(match.get("q10_hard_violation_codes") or [])
                    item["quality_filter"] = (match.get("parallel") or {}).get("selected_filter")
                    item["quality_filter_score"] = (match.get("parallel") or {}).get("selected_filter_score")
                    item["quality_filter_confirmed"] = bool((match.get("parallel") or {}).get("publication_candidate"))
            out = _context_levels(selected["levels"], trend, momentum, volatility, structure, symbol, timeframe, decision)
            out["commit21_9q_version"] = VERSION
            out["commit21_9q_route_selection"] = len(candidates) > 1
            out["commit21_9q_base_route"] = setup or "UNSPECIFIED"
            out["commit21_9q_selected_route"] = selected["route"]
            out["commit21_9q_route_candidates"] = meta[:max_routes]
            out["commit21_9q_route_score"] = selected["q9_route_score"]
            out["quality_9q"] = selected["quality"]
            out["parallel_quality_filters"] = dict(selected.get("parallel") or {})
            out["quality_filter_authority"] = (selected.get("parallel") or {}).get("selected_filter")
            out["quality_filter_score"] = (selected.get("parallel") or {}).get("selected_filter_score")
            out["quality_filter_summary"] = _quality_filter_summary_text(selected.get("parallel") or {})
            out["q10_safety_contract"] = "LEGACY_DIAGNOSTIC_NOT_MANDATORY"
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
                market_type = _market_type(symbol, lv)
                q = _evaluate(lv, trend, momentum, volatility, structure, symbol, timeframe, action, market_type=market_type)
                q10 = q9.q10_safety_snapshot(out, lv)
                context_groups = dict(q.get("context_quality_groups") or {})
                gate = dict(out.get("futures_publication_gate") or {})

                # Attach the parallel authority trace first. This is intentionally
                # independent from the legacy Q10 veto list so the frontend can
                # explain exactly which quality filter owns the candidate.
                out = _attach_parallel_quality_metadata(
                    out, q, q10, gate, symbol=symbol, timeframe=timeframe, action=action
                )
                lv = dict(out.get("levels") or lv or {})
                gate = dict(out.get("futures_publication_gate") or gate)

                # Legacy Q10 stays untouched for audit. Commit 23 permits one of
                # ten contextual quality filters to become publication authority
                # when the only legacy failures are SAFETY/TP/SL/RR and all
                # universal economic guards remain valid.
                out, parallel_promoted = _try_parallel_quality_promotion(
                    out, q, q10, gate, symbol=symbol, timeframe=timeframe, action=action
                )
                gate = dict(out.get("futures_publication_gate") or gate)
                gate["commit23_parallel_quality"] = dict(q.get("parallel_quality_filters") or {})
                gate["legacy_q10_reason_codes"] = [str(x).upper() for x in (gate.get("legacy_q10_reason_codes") or gate.get("reason_codes") or [])]
                gate["q10_is_mandatory"] = True
                gate["hard_q10_thresholds_unchanged"] = True
                gate["parallel_quality_promoted"] = bool(parallel_promoted)
                gate["quality_authority"] = str((q.get("parallel_quality_filters") or {}).get("selected_filter") or "NONE")
                gate["quality_authority_score"] = _f((q.get("parallel_quality_filters") or {}).get("selected_filter_score"), 0.0)
                out["futures_publication_gate"] = gate
                out["quality_9q"] = q
                out["q10_safety"] = q10
                out["context_quality_groups"] = context_groups
                out["parallel_quality_filters"] = dict(q.get("parallel_quality_filters") or {})
                out["quality_authority"] = str((q.get("parallel_quality_filters") or {}).get("selected_filter") or "NONE")
                out["quality_authority_name"] = str((q.get("parallel_quality_filters") or {}).get("selected_filter_name") or "")
                out["quality_authority_score"] = _f((q.get("parallel_quality_filters") or {}).get("selected_filter_score"), 0.0)
                out["q10_is_mandatory"] = True
                out["premium_confirmation_mode"] = "ONE_OF_TEN_QUALITY_FILTERS" if parallel_promoted else "NOT_CONFIRMED"
                out["q1_q9_safety_upgrade_applied"] = False
                if isinstance(out.get("levels"), dict):
                    out["levels"]["quality_9q"] = q
                    out["levels"]["q10_safety"] = q10
                    out["levels"]["context_quality_groups"] = context_groups
                    out["levels"]["parallel_quality_filters"] = dict(q.get("parallel_quality_filters") or {})
                    out["levels"]["quality_filter_authority"] = out["quality_authority"]
                    out["levels"]["quality_filter_authority_score"] = out["quality_authority_score"]
                    out["levels"]["q10_is_mandatory"] = True
                    out["levels"].pop("_commit21_quality_context", None)

                if parallel_promoted:
                    out["premium_blocker_stage_21"] = "NONE"
                    out["premium_blocker_codes"] = []
                    out["premium_blocker"] = ""
                else:
                    out["premium_blocker_stage_21"] = (
                        "PARALLEL_QUALITY_FILTERS" if not (q.get("parallel_quality_filters") or {}).get("selected_filter_passed")
                        else "UNIVERSAL_GUARD_OR_PRE_GATE"
                    )
                # Preserve the visible reason in manual diagnostic cards while
                # adding the exact quality filter membership.
                summary = _quality_filter_summary_text(q.get("parallel_quality_filters") or {})
                if summary:
                    base_reason = str(out.get("manual_risk_reason") or out.get("rejected_reason") or "").strip()
                    if summary not in base_reason:
                        out["manual_risk_reason"] = ((base_reason + " · ") if base_reason else "") + summary
                    out["quality_filter_summary"] = summary
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
                    market_type = _market_type(symbol, lv)
                    q = _evaluate(lv, ctx.get("trend") or {}, ctx.get("momentum") or {}, ctx.get("volatility") or {}, ctx.get("structure") or {}, symbol, timeframe, action, market_type=market_type)
                    q10 = q9.q10_safety_snapshot(out, lv)
                    context_groups = dict(q.get("context_quality_groups") or {})
                    gate = dict(out.get("futures_publication_gate") or {})
                    out = _attach_parallel_quality_metadata(
                        out, q, q10, gate, symbol=symbol, timeframe=timeframe, action=action
                    )
                    gate = dict(out.get("futures_publication_gate") or gate)
                    out, parallel_promoted = _try_parallel_quality_promotion(
                        out, q, q10, gate, symbol=symbol, timeframe=timeframe, action=action
                    )
                    gate = dict(out.get("futures_publication_gate") or gate)
                    gate["commit23_parallel_quality"] = dict(q.get("parallel_quality_filters") or {})
                    gate["legacy_q10_reason_codes"] = [str(x).upper() for x in (gate.get("legacy_q10_reason_codes") or gate.get("reason_codes") or [])]
                    gate["q10_is_mandatory"] = True
                    gate["hard_q10_thresholds_unchanged"] = True
                    gate["parallel_quality_promoted"] = bool(parallel_promoted)
                    out["futures_publication_gate"] = gate
                    out["quality_9q"] = q
                    out["q10_safety"] = q10
                    out["context_quality_groups"] = context_groups
                    out["parallel_quality_filters"] = dict(q.get("parallel_quality_filters") or {})
                    out["quality_authority"] = str((q.get("parallel_quality_filters") or {}).get("selected_filter") or "NONE")
                    out["quality_authority_name"] = str((q.get("parallel_quality_filters") or {}).get("selected_filter_name") or "")
                    out["quality_authority_score"] = _f((q.get("parallel_quality_filters") or {}).get("selected_filter_score"), 0.0)
                    out["q10_is_mandatory"] = True
                    out["premium_confirmation_mode"] = "ONE_OF_TEN_QUALITY_FILTERS" if parallel_promoted else "NOT_CONFIRMED"
                    if isinstance(out.get("levels"), dict):
                        out["levels"]["quality_9q"] = q
                        out["levels"]["q10_safety"] = q10
                        out["levels"]["context_quality_groups"] = context_groups
                        out["levels"]["parallel_quality_filters"] = dict(q.get("parallel_quality_filters") or {})
                        out["levels"]["quality_filter_authority"] = out["quality_authority"]
                        out["levels"]["quality_filter_authority_score"] = out["quality_authority_score"]
                        out["levels"]["q10_is_mandatory"] = True
                        out["levels"].pop("_commit21_quality_context", None)
                    if parallel_promoted:
                        out["premium_blocker_stage_21"] = "NONE"
                        out["premium_blocker_codes"] = []
                        out["premium_blocker"] = ""
                    summary = _quality_filter_summary_text(q.get("parallel_quality_filters") or {})
                    if summary:
                        base_reason = str(out.get("manual_risk_reason") or out.get("rejected_reason") or "").strip()
                        if summary not in base_reason:
                            out["manual_risk_reason"] = ((base_reason + " · ") if base_reason else "") + summary
                        out["quality_filter_summary"] = summary
                    return out
                multi_wrapped._commit21_9q_gate = True
                cls._apply_futures_publication_gate = multi_wrapped
                status.append({"class": "MultiAssetAnalysis", "installed": True})
        except Exception as exc:
            status.append({"class": "MultiAssetAnalysis", "error": type(exc).__name__})
    except Exception as exc:
        status.append({"error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return {"patches": status}




def install_frontend_quality_overlay(app: Any) -> Dict[str, Any]:
    """Inject the Commit 23 frontend overlay without modifying app.py/index.html."""
    try:
        if getattr(app, "_commit23_frontend_quality_overlay", False):
            return {"installed": True, "already": True}
        from flask import request

        @app.after_request
        def _commit23_quality_overlay(response):
            try:
                if response.status_code != 200:
                    return response
                path = str(request.path or "")
                if path not in {"/futures", "/multiasset"}:
                    return response
                content_type = str(response.headers.get("Content-Type") or "")
                if "text/html" not in content_type.lower():
                    return response
                html = response.get_data(as_text=True)
                src = '/static/quality_filters_frontend.js?v=20261003-COMMIT23-10Q-1'
                if src in html:
                    return response
                tag = f'<script src="{src}"></script>'
                # Load BEFORE futures.js so its fetch wrapper sees the very first
                # analysis request. If the exact script tag is not found, place
                # the overlay immediately before </body>.
                future_idx = html.find('futures.js')
                if future_idx >= 0:
                    start = html.rfind('<script', 0, future_idx)
                    if start >= 0:
                        html = html[:start] + tag + '\n' + html[start:]
                    else:
                        html = html.replace('</body>', tag + '\n</body>', 1)
                else:
                    html = html.replace('</body>', tag + '\n</body>', 1)
                response.set_data(html)
                response.headers.pop('Content-Length', None)
                response.headers['X-Commit23-Quality-Overlay'] = '1'
            except Exception:
                # Frontend enhancement must never turn a valid page into a 500.
                return response
            return response

        app._commit23_frontend_quality_overlay = True
        return {"installed": True, "script": "quality_filters_frontend.js", "index_untouched": True}
    except Exception as exc:
        return {"installed": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}

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
                "parallel_quality_filters": "COMMIT23_TEN_FILTER_PARALLEL_AUTHORITY_V1",
                "one_of_ten_min_score": q9.PARALLEL_FILTER_MIN_SCORE,
                "q10_is_mandatory": True,
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
        "frontend_quality_overlay": install_frontend_quality_overlay(app),
        "health": install_health_contract(app),
        "base_runtime": "COMMIT20_2_1_STABILITY_FIX_V1",
    }


def audit() -> Dict[str, Any]:
    return {"version": VERSION, "one_of_ten_min_score": q9.PARALLEL_FILTER_MIN_SCORE, "q10_mandatory": False, "new_network_calls": False, "new_threads": False, "index_untouched": True}
