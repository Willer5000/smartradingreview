"""Commit 19 — Champion Edge Execution runtime overlay.

Base: Commit 18.2.  The patch is intentionally narrow:
* keeps every 18.2 stability/resource guard;
* promotes only audited profitable Champions;
* lets an exact Champion construct the candidate directly in its validated
  context instead of re-winning generic family-count voting;
* still leaves Entry/SL/TP, economics/RR, Safety, leverage V6 and publication
  fully downstream;
* applies 8-loss LIVE alpha decay before any Champion authority;
* keeps Multi deep work at the same limit (2), only reprioritizing 1D US index.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, Mapping

VERSION = "COMMIT19_CHAMPION_EDGE_EXECUTION_V1"
_ORIGINALS: Dict[str, Any] = {}


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v if v is not None else default)
        return x if x == x else float(default)
    except Exception:
        return float(default)


def _install_champion_prepare() -> Dict[str, Any]:
    import operational_intelligence as oi
    if getattr(oi, "_COMMIT19_INSTALLED", False):
        return {"installed": True, "already": True}
    original = oi.prepare_operational_intelligence
    _ORIGINALS["prepare_operational_intelligence"] = original

    def prepare_operational_intelligence_commit19(*, layers: Mapping[str, Any], symbol: Any,
                                                   timeframe: Any, system_type: Any,
                                                   mtf_context: Mapping[str, Any],
                                                   research_candidates=None):
        out = dict(original(
            layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type,
            mtf_context=mtf_context, research_candidates=research_candidates,
        ) or {})
        try:
            from champion_registry_commit19 import resolve_champion
            from champion_decay_commit19 import get_decay_state
            route = resolve_champion(
                layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type,
                regime=(out.get("context") or {}).get("regime"),
                volatility=(out.get("context") or {}).get("volatility"),
                mtf_relation=out.get("mtf_relation_18_2") or {
                    "state": "HARD_CONFLICT" if bool((out.get("multi_timeframe") or {}).get("conflict")) else "ALIGNED_OR_NON_BLOCKING",
                    "usable": not bool((out.get("multi_timeframe") or {}).get("conflict")),
                    "original_conflict": bool((out.get("multi_timeframe") or {}).get("conflict")),
                    "dominant_direction": (out.get("multi_timeframe") or {}).get("dominant_direction"),
                },
                operational=out,
            )
            out["commit19_champion"] = route
            if not route.get("eligible_for_execution_routing"):
                return out

            decay = get_decay_state(
                champion_id=str(route.get("champion_id")),
                decay_key=str(route.get("decay_key")),
                research_handoff_key=str(route.get("research_handoff_key")),
            )
            route["alpha_decay"] = decay
            out["commit19_champion"] = route
            if decay.get("state") != "LIVE_CHAMPION":
                # The failed Champion cannot be silently rescued by generic fallback
                # in the same cell. Research/Shadow must supply a newly validated edge.
                out["candidate_ready"] = False
                out["candidate_action"] = "NO_OPERAR"
                out["candidate_source"] = str(decay.get("state") or "SHADOW_DECAY")
                out["research_blocks_selected_action"] = True
                out["coverage_route_state"] = str(decay.get("state") or "SHADOW_DECAY")
                out["validated_strategy_route"] = {**route, "eligible_for_execution_routing": False,
                                                   "authority": str(decay.get("state")),
                                                   "reason": "ALPHA_DECAY_RESEARCH_HANDOFF"}
                return out

            action = _u(route.get("action"))
            # Exact Champion authority: build the candidate without a second
            # generic family-election gate. The current market/context checks
            # live in champion_registry_commit19; all execution/risk gates remain.
            out["candidate_action"] = action
            out["candidate_ready"] = True
            out["candidate_source"] = "COMMIT19_LIVE_CHAMPION"
            out["selected_specialist_source"] = "CHAMPION"
            out["research_blocks_selected_action"] = False
            out["official_cell"] = True
            out["coverage_route_state"] = "LIVE_CHAMPION_COMMIT19"
            out["validated_strategy_route"] = route
            strategy = dict(out.get("default_strategy") or {})
            strategy.update({
                "id": route.get("strategy_id") or route.get("champion_id"),
                "family": route.get("bank_family") or route.get("execution_family"),
                "champion_id": route.get("champion_id"),
                "commit19_live_champion": True,
            })
            out["default_strategy"] = strategy
            evidence = dict(out.get("decision_evidence") or {})
            evidence.update({
                "candidate_source": "COMMIT19_LIVE_CHAMPION",
                "validated_context_route": True,
                "coverage_route_state": "LIVE_CHAMPION",
            })
            out["decision_evidence"] = evidence
            return out
        except Exception as exc:
            out["commit19_champion"] = {"matched": False, "eligible_for_execution_routing": False,
                                         "reason": "COMMIT19_FAIL_SAFE_TO_BASE_18_2",
                                         "error": str(exc)[:160]}
            return out

    oi.prepare_operational_intelligence = prepare_operational_intelligence_commit19
    oi._COMMIT19_INSTALLED = True
    return {"installed": True, "already": False}


def install_pre_app() -> Dict[str, Any]:
    from commit18_2_runtime import install_pre_app as install_18_2_pre
    base = install_18_2_pre()
    champion = _install_champion_prepare()
    return {"version": VERSION, "base18_2": base, "champion": champion}


def _install_champion_geometry_overlay() -> Dict[str, Any]:
    """Apply the audited Champion geometry before Futures leverage is recalculated.

    The base Entry engine still runs first and supplies live quality/structure
    metadata.  Only a LIVE Commit-19 route may replace the numerical geometry.
    The normal Futures wrapper then recalculates leverage, and all later Entry
    reaction, SL collision, Safety, RR and publication gates remain unchanged.
    """
    app_mod = sys.modules.get("app")
    if app_mod is None:
        return {"installed": False, "reason": "APP_MODULE_NOT_LOADED"}
    cls = getattr(app_mod, "TradingExpertSystem", None)
    if cls is None:
        return {"installed": False, "reason": "BASE_CLASS_NOT_FOUND"}
    original = getattr(cls, "calculate_entry_levels", None)
    if not callable(original):
        return {"installed": False, "reason": "BASE_LEVEL_METHOD_NOT_FOUND"}
    if getattr(original, "_commit19_geometry_overlay", False):
        return {"installed": True, "already": True}
    _ORIGINALS["base_calculate_entry_levels"] = original

    def calculate_entry_levels_commit19(self, decision, trend, momentum, volatility, structure,
                                        symbol, timeframe, liquidation=None, execution_observations=None):
        levels = original(
            self, decision, trend, momentum, volatility, structure, symbol, timeframe,
            liquidation=liquidation, execution_observations=execution_observations,
        )
        if not isinstance(levels, dict):
            return levels
        try:
            obs = execution_observations if isinstance(execution_observations, dict) else {}
            if not obs and isinstance(structure, dict):
                obs = structure.get("_execution_observations_175103") or {}
            op = dict((obs or {}).get("operational_intelligence") or {})
            route = dict(op.get("validated_strategy_route") or {})
            if not (
                route.get("eligible_for_execution_routing")
                and _u(route.get("authority")) == "LIVE_CHAMPION_COMMIT19"
            ):
                return levels
            geom = dict(route.get("historical_geometry") or {})
            style = _u(geom.get("entry_style"))
            action = _u(route.get("action") or decision)
            if action not in {"LONG", "SHORT"}:
                return levels
            current = _f((structure or {}).get("current_price"))
            atr = _f((volatility or {}).get("atr"))
            if current <= 0 or atr <= 0:
                levels["commit19_geometry_parity"] = False
                levels["commit19_geometry_reason"] = "PRICE_OR_ATR_UNAVAILABLE"
                return levels

            # 30m keeps the production structural geometry represented by its raw
            # replay cohort. The execution guard separately requires the exact
            # sweep/MSS or displacement/POI trigger.
            if style == "STRUCTURAL_POI":
                levels["commit19_geometry_parity"] = True
                levels["commit19_geometry_mode"] = "STRUCTURAL_PRODUCTION_REPLAY"
                levels["commit19_champion_id"] = route.get("champion_id")
                # Commit 25: preserve compact governed evidence through the
                # Entry/SL/TP snapshot so Q9 does not see a false GAP after
                # champion routing. No I/O and no score fabrication.
                levels["commit19_champion"] = dict(route)
                levels["validated_strategy_route"] = dict(route)
                levels["setup_family"] = route.get("execution_family") or route.get("bank_family")
                levels["strategy_family"] = route.get("execution_family") or route.get("bank_family")
                levels["commit25_contextual_authority"] = True
                return levels

            entry = _f(levels.get("entry"), current)
            entry_atr = geom.get("entry_atr")
            if style == "NEXT_OPEN":
                # In production the analysis is emitted on the just-closed bar;
                # current_price is the executable next-open proxy available to the
                # live engine without fabricating a future quote.
                entry = current
            elif style == "PULLBACK" and entry_atr is not None:
                offset = max(0.0, _f(entry_atr)) * atr
                entry = current - offset if action == "LONG" else current + offset
            # US_INDEX PULLBACK has no fixed ATR offset in the audited contract;
            # keep its structural Entry selected by the production desk.

            sl = _f(levels.get("stop_loss"))
            sl_atr = geom.get("sl_atr")
            if sl_atr is not None:
                risk = max(1e-12, _f(sl_atr) * atr)
                sl = entry - risk if action == "LONG" else entry + risk
            else:
                risk = abs(entry - sl) if sl > 0 else 0.0

            rr_target = _f(geom.get("rr"))
            tp = _f(levels.get("take_profit"))
            if rr_target > 0 and risk > 0:
                tp = entry + rr_target * risk if action == "LONG" else entry - rr_target * risk

            valid = bool(
                entry > 0 and sl > 0 and tp > 0 and risk > 0
                and ((action == "LONG" and sl < entry < tp)
                     or (action == "SHORT" and tp < entry < sl))
            )
            if not valid:
                levels["commit19_geometry_parity"] = False
                levels["commit19_geometry_reason"] = "INVALID_RECONSTRUCTED_GEOMETRY"
                return levels

            rounder = getattr(self, "_round_price", lambda x, _s: x)
            levels["entry"] = rounder(entry, symbol)
            levels["stop_loss"] = rounder(sl, symbol)
            levels["take_profit"] = rounder(tp, symbol)
            levels["risk_reward"] = round(abs(tp-entry) / max(abs(entry-sl), 1e-12), 2)
            levels["entry_source"] = f"Champion {style} · contexto validado"
            if sl_atr is not None:
                levels["sl_source"] = f"Champion SL {float(sl_atr):.2f} ATR · sujeto a invalidación/Safety"
            if rr_target > 0:
                levels["tp_source"] = f"Champion objetivo {float(rr_target):.2f}R · sujeto a reachability/Safety"
            levels["commit19_geometry_parity"] = True
            levels["commit19_geometry_mode"] = "AUDITED_CHAMPION_GEOMETRY"
            levels["commit19_champion_id"] = route.get("champion_id")
            levels["commit19_historical_geometry"] = geom
            levels["commit19_never_bypass_safety"] = True
            levels["commit19_champion"] = dict(route)
            levels["validated_strategy_route"] = dict(route)
            levels["setup_family"] = route.get("execution_family") or route.get("bank_family")
            levels["strategy_family"] = route.get("execution_family") or route.get("bank_family")
            levels["commit25_contextual_authority"] = True
            return levels
        except Exception as exc:
            levels["commit19_geometry_parity"] = False
            levels["commit19_geometry_reason"] = f"OVERLAY_ERROR:{type(exc).__name__}"
            return levels

    calculate_entry_levels_commit19._commit19_geometry_overlay = True
    cls.calculate_entry_levels = calculate_entry_levels_commit19
    return {"installed": True, "already": False}


def install_post_app() -> Dict[str, Any]:
    from commit18_2_runtime import install_post_app as install_18_2_post
    base = install_18_2_post()
    geometry = _install_champion_geometry_overlay()
    ma = sys.modules.get("multiasset_system")
    if ma is None:
        try:
            import multiasset_system as ma
        except Exception as exc:
            return {"version": VERSION, "base18_2": base, "geometry": geometry, "multi": {"installed": False, "error": str(exc)[:160]}}
    if getattr(ma, "_COMMIT19_INSTALLED", False):
        return {"version": VERSION, "base18_2": base, "geometry": geometry, "multi": {"installed": True, "already": True}}
    original_scan = ma.scan_opportunities
    _ORIGINALS["multi_scan_opportunities"] = original_scan

    def scan_opportunities_commit19(timeframe="4h", force=False):
        rows = [dict(x) for x in (original_scan(timeframe=timeframe, force=force) or [])]
        if str(timeframe).upper() != "1D" or not rows:
            return rows
        deep_limit = max(1, min(2, int(getattr(ma, "MULTIASSET_DEEP_LIMIT", 2) or 2)))
        # Same two deep slots. On 1D, reserve one for the backtested US_INDEX
        # class when present, then use the best remaining candidate globally.
        for row in rows:
            row["deep_candidate"] = False
            row["deep_selection_reason"] = None
        index_rows = [r for r in rows if str(r.get("asset_class") or "").upper() == "US_INDEX"
                      and _u(r.get("symbol")) in {"SPY-USDT", "QQQ-USDT"}]
        index_rows.sort(key=lambda r: float(r.get("router_score") or 0.0), reverse=True)
        chosen = []
        if index_rows:
            first = index_rows[0]
            first["deep_candidate"] = True
            first["deep_selection_reason"] = "BACKTESTED_US_INDEX_CHAMPION_SLOT"
            chosen.append(first)
        remaining = sorted([r for r in rows if r not in chosen],
                           key=lambda r: float(r.get("router_score") or 0.0), reverse=True)
        while len(chosen) < deep_limit and remaining:
            r = remaining.pop(0)
            r["deep_candidate"] = True
            r["deep_selection_reason"] = "BEST_REMAINING_QUALITY_SLOT"
            chosen.append(r)
        try:
            with ma._router_lock:
                ma._router_cache[str(timeframe)] = {"stored_at": ma.time.monotonic(), "rows": [dict(x) for x in rows]}
        except Exception:
            pass
        return rows

    ma.scan_opportunities = scan_opportunities_commit19
    ma._COMMIT19_INSTALLED = True
    return {"version": VERSION, "base18_2": base, "geometry": geometry,
            "multi": {"installed": True, "deep_limit_preserved": int(getattr(ma, "MULTIASSET_DEEP_LIMIT", 2) or 2),
                      "extra_market_requests": 0}}


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "base": "COMMIT18_2_QUALITY_SIGNAL_COVERAGE_V1",
        "changes_safety_thresholds": False,
        "changes_publication_rr_floor": False,
        "changes_leverage_v6": False,
        "changes_guardian": False,
        "adds_llm_calls": False,
        "adds_background_threads": False,
        "adds_market_data_requests": False,
        "multi_deep_limit_preserved": 2,
        "alpha_decay": "8 LIVE consecutive losses -> SHADOW/Research; 8 Shadow consecutive losses -> RETIRED",
    }
