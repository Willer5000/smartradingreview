"""Commit 18.2 — Quality Signal Coverage runtime overlay.

Base required: Main Commit 18.1.1.

The overlay deliberately patches only pure/lightweight decision helpers before
the Flask app is imported. It does NOT change:
- Safety thresholds;
- publication R/R thresholds;
- leverage V6;
- Guardian;
- Groq cadence;
- Supabase budgets;
- worker/thread counts;
- market-data request cadence;
- Multi DEEP_LIMIT / daily deep budget.

The goal is better use of existing evidence:
1) Reason-First moderator: specialist counts become diagnostics, not a second
   majority-vote gate. Explicit hard vetoes remain respected.
2) MTF classification: not every lower-TF countertrend is treated as the same
   hard conflict. A transition requires real structure evidence.
3) Entry reaction deduplication: a complete current-TF structural trigger does
   not also require a redundant lower-TF trigger.
4) Multi router: same scans, same two deep slots, but the second slot can be
   diversified by asset class and obviously extended/choppy candidates are
   penalized using the candles already loaded.
5) Multi execution semantics: map the existing thesis/context to an execution
   family before downstream Entry/SL/TP geometry. No direction is created.
"""
from __future__ import annotations

import math
import sys
from typing import Any, Dict, Iterable, Mapping

VERSION = "COMMIT18_2_QUALITY_SIGNAL_COVERAGE_V1"

_ORIGINALS: Dict[str, Any] = {}


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v if v is not None else default)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _direction(v: Any) -> str:
    raw = _u(v)
    if raw in {"LONG", "BUY", "COMPRA", "COMPRA_SPOT", "BULLISH", "UP", "TREND_UP"}:
        return "BULLISH"
    if raw in {"SHORT", "SELL", "VENTA", "VENTA_SPOT", "BEARISH", "DOWN", "TREND_DOWN"}:
        return "BEARISH"
    return "NEUTRAL"


def _bool_from_blob(obj: Any, *tokens: str) -> bool:
    blob = str(obj or "").upper()
    return any(str(t).upper() in blob for t in tokens)


def _structure_transition_evidence(layers: Mapping[str, Any]) -> Dict[str, bool]:
    layers = dict(layers or {})
    s = dict(layers.get("structure") or layers.get("price_structure") or {})
    blob = " ".join([
        str(s),
        str(layers.get("liquidity") or {}),
        str(layers.get("patterns") or {}),
    ]).upper()
    sweep = bool(
        s.get("has_liquidity_sweep") or s.get("liquidity_sweep")
        or _bool_from_blob(blob, "SWEEP", "BARRIDO", "STOP_HUNT", "STOP HUNT")
    )
    mss = bool(
        s.get("mss") or s.get("bos") or s.get("market_structure_shift")
        or _bool_from_blob(blob, "MSS", "BOS", "CHANGE OF CHARACTER", "CHOCH")
    )
    displacement = bool(
        s.get("displacement") or s.get("displacement_confirmed")
        or _bool_from_blob(blob, "DISPLACEMENT", "IMPULSO", "EXPANSION")
    )
    poi = bool(
        s.get("order_blocks") or s.get("fvg") or s.get("nearest_support")
        or s.get("nearest_resistance")
        or _bool_from_blob(blob, "ORDER_BLOCK", "ORDER BLOCK", "FVG", "POC", "VWAP")
    )
    return {"sweep": sweep, "mss": mss, "displacement": displacement, "poi": poi}


def _short_term_direction(layers: Mapping[str, Any]) -> str:
    layers = dict(layers or {})
    dirs = []
    for key in ("trend", "momentum", "structure", "price_structure"):
        row = layers.get(key) or {}
        if isinstance(row, Mapping):
            d = _direction(
                row.get("direction") or row.get("trend") or row.get("bias")
                or row.get("structure_direction")
            )
            if d != "NEUTRAL":
                dirs.append(d)
    if not dirs:
        return "NEUTRAL"
    bull = dirs.count("BULLISH")
    bear = dirs.count("BEARISH")
    if bull == bear:
        return dirs[0]
    return "BULLISH" if bull > bear else "BEARISH"


def classify_mtf_relation(
    *, layers: Mapping[str, Any], mtf_context: Mapping[str, Any],
    system_type: Any, timeframe: Any,
) -> Dict[str, Any]:
    """Contextual MTF classification without lowering any downstream risk gate."""
    mtf = dict(mtf_context or {})
    market = _u(system_type)
    tf = _u(timeframe)
    conflict = bool(mtf.get("conflict")) or _u(mtf.get("alignment")) == "CONFLICT"
    if market != "FUTURES" or not conflict:
        return {
            "state": "ALIGNED_OR_NON_BLOCKING",
            "usable": True,
            "original_conflict": conflict,
            "requires_extra_structure": False,
        }

    htf = _direction(mtf.get("dominant_direction") or mtf.get("direction"))
    ltf = _short_term_direction(layers)
    ev = _structure_transition_evidence(layers)
    structure_count = sum(1 for x in ("sweep", "mss", "displacement", "poi") if ev[x])

    # A reversal transition must show a structure change, not just oscillators.
    if (
        tf in {"30M", "1H", "2H", "4H"}
        and ltf in {"BULLISH", "BEARISH"}
        and htf in {"BULLISH", "BEARISH"}
        and ltf != htf
        and ev["mss"]
        and (ev["sweep"] or ev["displacement"])
        and structure_count >= 2
    ):
        return {
            "state": "REVERSAL_TRANSITION",
            "usable": True,
            "original_conflict": True,
            "requires_extra_structure": True,
            "structure_evidence": ev,
        }

    # A short-horizon countertrend is allowed to reach the normal Entry/Safety
    # stack only when structure + local direction agree. It receives no boost.
    if (
        tf in {"30M", "1H"}
        and ltf in {"BULLISH", "BEARISH"}
        and htf in {"BULLISH", "BEARISH"}
        and ltf != htf
        and ev["poi"]
        and (ev["sweep"] or ev["mss"])
    ):
        return {
            "state": "COUNTERTREND_VALID",
            "usable": True,
            "original_conflict": True,
            "requires_extra_structure": True,
            "structure_evidence": ev,
        }

    return {
        "state": "HARD_CONFLICT",
        "usable": False,
        "original_conflict": True,
        "requires_extra_structure": True,
        "structure_evidence": ev,
    }


def _multi_execution_family(
    operational: Mapping[str, Any], layers: Mapping[str, Any],
    research_candidates: Mapping[str, Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    """Choose execution semantics only. Never invent LONG/SHORT."""
    op = dict(operational or {})
    thesis = dict(op.get("thesis") or {})
    action = _u(op.get("candidate_action"))
    if action not in {"LONG", "SHORT"}:
        return {"family": "MULTIASSET_DELEGATED", "source": "NO_DIRECTION"}

    # If Main already supplied a healthy exact/local research prior, use only
    # its family as a routing prior. No new Supabase read is introduced here.
    for _key, row in dict(research_candidates or {}).items():
        row = dict(row or {})
        state = _u(row.get("state"))
        best = dict(row.get("best_positive") or {})
        fam = _u(
            best.get("strategy_family")
            or row.get("strategy_family")
            or row.get("family")
        )
        if state in {"OOS_VALIDATED", "OOS_PLUS_SHADOW", "SHADOW_READY", "VALIDATED"} and fam:
            mapping = {
                "RSI_TREND": "MOMENTUM_CONTINUATION",
                "TREND_CONTINUATION": "MOMENTUM_CONTINUATION",
                "MACD_TREND": "MOMENTUM_CONTINUATION",
                "ADX_DI_TREND": "MOMENTUM_CONTINUATION",
                "SUPERTREND_PULLBACK": "TREND_PULLBACK",
                "TREND_PULLBACK": "TREND_PULLBACK",
                "SWEEP_REVERSAL": "SWEEP_REVERSAL",
                "MEAN_REVERSION": "MEAN_REVERSION",
                "VWAP_REVERSION": "MEAN_REVERSION",
                "BOLLINGER_SQUEEZE": "COMPRESSION_EXPANSION",
                "MOMENTUM_BREAKOUT": "COMPRESSION_EXPANSION",
                "BREAKOUT_RETEST": "BREAKOUT_RETEST",
            }
            if fam in mapping:
                return {"family": mapping[fam], "source": "EXISTING_RESEARCH_PRIOR"}

    context = dict(op.get("context") or {})
    regime = _u(context.get("regime"))
    vol = _u(context.get("volatility"))
    ev = _structure_transition_evidence(layers)
    momentum = dict((layers or {}).get("momentum") or {})
    trend = dict((layers or {}).get("trend") or {})
    adx = _f(trend.get("adx"))
    volrow = dict((layers or {}).get("volume") or (layers or {}).get("volume_flow") or {})
    volume_ratio = _f(volrow.get("volume_ratio"), 1.0)

    if ev["sweep"] and ev["mss"]:
        return {"family": "SWEEP_REVERSAL", "source": "LIVE_STRUCTURE"}
    if vol in {"COMPRESSION", "SQUEEZE"}:
        return {"family": "COMPRESSION_EXPANSION", "source": "LIVE_VOLATILITY"}
    if vol in {"EXPANSION", "SHOCK", "VOLATILITY_SHOCK", "HIGH_EXPANSION"} and (ev["displacement"] or volume_ratio >= 1.05):
        return {"family": "COMPRESSION_EXPANSION", "source": "LIVE_EXPANSION"}
    if regime in {"TREND_UP", "TREND_DOWN", "TRENDING"} and adx >= 28 and volume_ratio >= 1.0:
        return {"family": "MOMENTUM_CONTINUATION", "source": "LIVE_TREND_STRENGTH"}
    if regime in {"TREND_UP", "TREND_DOWN", "TRENDING", "TRANSITION"}:
        return {"family": "TREND_PULLBACK", "source": "LIVE_REGIME"}
    if regime in {"BALANCE", "RANGE", "RANGING"}:
        return {"family": "MEAN_REVERSION", "source": "LIVE_REGIME"}
    if ev["displacement"] or ev["poi"]:
        return {"family": "BREAKOUT_RETEST", "source": "LIVE_STRUCTURE"}
    return {"family": "MULTIASSET_DELEGATED", "source": "NO_STRONG_ROUTE"}


def _quality_index(operational: Mapping[str, Any], mtf_relation: Mapping[str, Any]) -> Dict[str, Any]:
    """Non-probabilistic quality index for diagnostics/routing only."""
    op = dict(operational or {})
    thesis = _f((op.get("thesis") or {}).get("quality"))
    strategy = _f((op.get("default_strategy") or {}).get("quality"))
    if strategy <= 0:
        strategy = thesis
    relation = _u((mtf_relation or {}).get("state"))
    mtf_component = {
        "ALIGNED_OR_NON_BLOCKING": 82.0,
        "REVERSAL_TRANSITION": 72.0,
        "COUNTERTREND_VALID": 66.0,
        "HARD_CONFLICT": 25.0,
    }.get(relation, 55.0)
    score = max(0.0, min(100.0, 0.58 * thesis + 0.27 * strategy + 0.15 * mtf_component))
    return {
        "score": round(score, 2),
        "probability": False,
        "role": "QUALITY_INDEX_NOT_WIN_PROBABILITY",
        "components": {
            "thesis": round(thesis, 2),
            "strategy": round(strategy, 2),
            "mtf": round(mtf_component, 2),
        },
    }


def install_pre_app() -> Dict[str, Any]:
    """Patch lightweight decision helpers before app.py imports them."""
    import operational_intelligence as oi
    import entry_reaction_engine as ere

    if getattr(oi, "_COMMIT18_2_INSTALLED", False):
        return {"installed": True, "already": True, "version": VERSION}

    _ORIGINALS["prepare_operational_intelligence"] = oi.prepare_operational_intelligence
    _ORIGINALS["moderator_candidate"] = oi.moderator_candidate
    _ORIGINALS["evaluate_entry_reaction"] = ere.evaluate_entry_reaction

    original_prepare = oi.prepare_operational_intelligence

    def prepare_operational_intelligence_18_2(
        *, layers, symbol, timeframe, system_type, mtf_context,
        research_candidates=None,
    ):
        relation = classify_mtf_relation(
            layers=layers, mtf_context=mtf_context,
            system_type=system_type, timeframe=timeframe,
        )
        mtf_for_core = dict(mtf_context or {})
        if relation.get("usable") and relation.get("original_conflict"):
            # Preserve the original fact but prevent a valid structural
            # countertrend/transition from being erased before Entry/Safety.
            mtf_for_core["_commit18_2_original_conflict"] = True
            mtf_for_core["_commit18_2_relation"] = relation.get("state")
            mtf_for_core["conflict"] = False
            if _u(mtf_for_core.get("alignment")) == "CONFLICT":
                mtf_for_core["alignment"] = relation.get("state")

        out = original_prepare(
            layers=layers, symbol=symbol, timeframe=timeframe,
            system_type=system_type, mtf_context=mtf_for_core,
            research_candidates=research_candidates,
        )
        out = dict(out or {})
        out["mtf_relation_18_2"] = relation
        out["mtf_original_conflict"] = bool(relation.get("original_conflict"))
        out["mtf_usable"] = bool(relation.get("usable"))

        is_multi = _u(symbol) in set(getattr(oi, "MULTIASSET_SYMBOLS", set()) or set())
        if is_multi:
            route = _multi_execution_family(out, layers, research_candidates)
            out["multiasset_execution_route_18_2"] = route
            current = dict(out.get("default_strategy") or {})
            current.update({
                "id": "MULTIASSET_CONTEXT_EXECUTION_ROUTE_18_2",
                "family": route.get("family"),
                "setup_family": route.get("family"),
                "routing_source": route.get("source"),
                "regime_match": True,
                "volatility_match": True,
                "creates_direction": False,
                "statistical_authority": False,
            })
            # Do not manufacture a separate quality score. The thesis remains
            # authoritative for candidate readiness; routing only supplies
            # geometry semantics.
            out["default_strategy"] = current

        out["signal_quality_index_18_2"] = _quality_index(out, relation)

        try:
            from quality_funnel_18_2 import record
            market = "MULTIASSET" if is_multi else _u(system_type)
            record(market, "THESIS_BUILT")
            if relation.get("state") == "HARD_CONFLICT":
                record(market, "MTF_HARD_CONFLICT")
            if out.get("candidate_ready"):
                record(market, "CANDIDATE_READY")
            else:
                record(market, "NO_CANDIDATE")
        except Exception:
            pass
        return out

    def moderator_candidate_18_2(operational, votes: Iterable[Mapping[str, Any]], market):
        """Reason-First: votes are diagnostics, not a majority production gate."""
        op = dict(operational or {})
        action = oi.canonical_action(op.get("candidate_action"), _u(market))
        if action not in oi.DIRECTIONAL_ACTIONS or not op.get("candidate_ready"):
            return {"use": False, "action": "NO_OPERAR", "reason": "THESIS_NOT_READY"}

        # Explicit machine-readable hard veto remains authoritative.
        hard_vetoes = []
        same = opposite = caution = 0
        desired = oi.action_direction(action)
        for vote in votes or []:
            vote = dict(vote or {})
            if bool(vote.get("hard_veto") or vote.get("safety_veto") or vote.get("risk_hard_veto")):
                hard_vetoes.append(str(vote.get("reason") or vote.get("razon") or "EXPLICIT_HARD_VETO")[:160])
            va = oi.canonical_action(
                vote.get("accion_normalizada") or vote.get("accion") or vote.get("accion_original"),
                _u(market),
            )
            vd = oi.action_direction(va)
            conf = _f(vote.get("confianza_original") or vote.get("confianza"))
            if vd == desired and conf >= 55:
                same += 1
            elif vd in {"BULLISH", "BEARISH"} and vd != desired and conf >= 65:
                opposite += 1
            elif va in {"PRECAUCION", "ESPERAR", "NO_OPERAR"} and conf >= 70:
                caution += 1

        if hard_vetoes:
            return {
                "use": False, "action": "PRECAUCION",
                "reason": "EXPLICIT_HARD_RISK_VETO",
                "hard_vetoes": hard_vetoes[:3],
                "same": same, "opposite": opposite, "caution": caution,
            }

        thesis_quality = _f((op.get("thesis") or {}).get("quality"))
        strategy_quality = _f((op.get("default_strategy") or {}).get("quality"))
        source = str(op.get("candidate_source") or "")
        if source == "THESIS_AUTONOMOUS" or strategy_quality <= 0:
            confidence_base = thesis_quality
        else:
            confidence_base = 0.60 * thesis_quality + 0.40 * strategy_quality
        confidence = min(88.0, max(60.0, confidence_base))

        return {
            "use": True,
            "action": action,
            "confidence": round(confidence, 2),
            "reason": "REASON_FIRST_THESIS_READY_SPECIALISTS_DIAGNOSTIC",
            "candidate_source": source,
            "same": same, "opposite": opposite, "caution": caution,
            "specialist_count_is_publication_gate": False,
        }

    original_entry = ere.evaluate_entry_reaction

    def evaluate_entry_reaction_18_2(levels, *, structure=None, volatility=None, timeframe=None, market_type="spot"):
        out = dict(original_entry(
            levels, structure=structure, volatility=volatility,
            timeframe=timeframe, market_type=market_type,
        ) or {})
        if _u(out.get("market")) != "FUTURES":
            return out
        ev = dict(out.get("reaction_evidence") or {})
        components = dict(out.get("components") or {})
        score = _f(out.get("score"))
        threshold = _f(out.get("threshold"))
        current_tf_complete = bool(
            ev.get("structural_poi")
            and ev.get("mss_bos")
            and (ev.get("sweep") or ev.get("displacement"))
            and score >= threshold
        )
        if out.get("lower_tf_confirmation_required") and current_tf_complete:
            out["lower_tf_confirmation_required"] = False
            out["status"] = "ENTRY_CONFIRMED_BY_CURRENT_TF_STRUCTURE"
            policy = dict(out.get("policy") or {})
            policy["commit18_2_no_duplicate_lower_tf_veto"] = True
            policy["threshold_lowered"] = False
            out["policy"] = policy
        out["authority_state_18_2"] = (
            "ENTRY_READY" if out.get("passed") and not out.get("lower_tf_confirmation_required")
            else "WAIT_LOWER_TF" if out.get("passed")
            else "ENTRY_INVALID"
        )
        return out

    oi.prepare_operational_intelligence = prepare_operational_intelligence_18_2
    oi.moderator_candidate = moderator_candidate_18_2
    ere.evaluate_entry_reaction = evaluate_entry_reaction_18_2
    oi._COMMIT18_2_INSTALLED = True
    ere._COMMIT18_2_INSTALLED = True
    return {"installed": True, "already": False, "version": VERSION}


def install_post_app() -> Dict[str, Any]:
    """Patch Multi scanner after app import. No additional market requests."""
    ma = sys.modules.get("multiasset_system")
    if ma is None:
        try:
            import multiasset_system as ma
        except Exception as exc:
            return {"installed": False, "reason": f"MULTI_IMPORT_FAILED:{type(exc).__name__}"}

    if getattr(ma, "_COMMIT18_2_INSTALLED", False):
        return {"installed": True, "already": True, "version": VERSION}

    original_score = ma._router_score
    original_scan = ma.scan_opportunities
    _ORIGINALS["multi_router_score"] = original_score
    _ORIGINALS["multi_scan_opportunities"] = original_scan

    def router_score_18_2(df):
        q = dict(original_score(df) or {})
        try:
            close = df["close"].astype(float)
            if len(close) >= 14:
                diffs = close.diff().abs().tail(12)
                path = float(diffs.sum() or 0.0)
                net = abs(float(close.iloc[-1]) - float(close.iloc[-13]))
                efficiency = min(1.0, net / path) if path > 0 else 0.0
            else:
                efficiency = 0.0

            ema12 = close.ewm(span=12, adjust=False).mean()
            atr_pct = max(0.0, _f(q.get("atr_pct")))
            price = max(1e-12, float(close.iloc[-1]))
            atr_abs = price * atr_pct / 100.0 if atr_pct > 0 else 0.0
            extension_atr = abs(price - float(ema12.iloc[-1])) / atr_abs if atr_abs > 0 else 0.0

            score = _f(q.get("score"))
            score += min(12.0, efficiency * 12.0)
            if _u(q.get("bias")) == "MIXED":
                score -= 7.0
            if extension_atr > 2.5:
                score -= min(14.0, (extension_atr - 2.5) * 5.0)
            if _f(q.get("volume_ratio"), 1.0) < 0.70:
                score -= 4.0
            q["score"] = round(max(0.0, min(100.0, score)), 1)
            q["trend_efficiency"] = round(efficiency, 3)
            q["extension_atr"] = round(extension_atr, 3)
            q["quality_router_version"] = VERSION
        except Exception:
            q["quality_router_version"] = VERSION
        return q

    ma._router_score = router_score_18_2

    def scan_opportunities_18_2(timeframe="4h", force=False):
        rows = [dict(x) for x in (original_scan(timeframe=timeframe, force=force) or [])]
        if not rows:
            return rows
        rows.sort(key=lambda x: _f(x.get("router_score")), reverse=True)
        for row in rows:
            row["deep_candidate"] = False
            row["deep_selection_reason"] = None

        deep_limit = max(1, min(2, int(getattr(ma, "MULTIASSET_DEEP_LIMIT", 2) or 2)))
        chosen = [rows[0]]
        rows[0]["deep_candidate"] = True
        rows[0]["deep_selection_reason"] = "BEST_QUALITY_GLOBAL"

        if deep_limit >= 2 and len(rows) > 1:
            top_score = max(1e-9, _f(rows[0].get("router_score")))
            top_class = str(rows[0].get("asset_class") or "")
            diversified = [
                row for row in rows[1:]
                if str(row.get("asset_class") or "") != top_class
                and _f(row.get("router_score")) >= top_score * 0.78
            ]
            second = diversified[0] if diversified else rows[1]
            second["deep_candidate"] = True
            second["deep_selection_reason"] = (
                "DIVERSIFIED_QUALITY_SLOT"
                if diversified else "SECOND_BEST_QUALITY_GLOBAL"
            )
            chosen.append(second)

        # Keep cache coherent without expanding it or making any request.
        try:
            with ma._router_lock:
                ma._router_cache[str(timeframe)] = {
                    "stored_at": ma.time.monotonic(),
                    "rows": [dict(x) for x in rows],
                }
        except Exception:
            pass
        return rows

    ma.scan_opportunities = scan_opportunities_18_2
    ma._COMMIT18_2_INSTALLED = True
    return {
        "installed": True,
        "already": False,
        "version": VERSION,
        "deep_limit_preserved": int(getattr(ma, "MULTIASSET_DEEP_LIMIT", 2) or 2),
        "daily_max_preserved": int(getattr(ma, "MULTIASSET_AUTO_DEEP_DAILY_MAX", 12) or 12),
        "extra_network_calls": 0,
    }


def audit() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "changes_safety_thresholds": False,
        "changes_publication_rr": False,
        "changes_leverage_v6": False,
        "changes_guardian": False,
        "adds_network_calls": False,
        "adds_supabase_reads": False,
        "adds_llm_calls": False,
        "adds_background_threads": False,
        "multi_deep_limit_target": 2,
        "multi_auto_deep_daily_max_target": 12,
        "quality_funnel_bounded": True,
    }
