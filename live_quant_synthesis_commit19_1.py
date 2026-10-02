"""Commit 19.1 — LIVE Quantitative Synthesis Lane.

Purpose
-------
Commit 19 makes statistically validated Champions first-class LIVE routes.  This
module solves the complementary problem: the native nine-specialist desk must
still be able to construct NEW, technically coherent LIVE opportunities when no
exact Champion is responsible for the current context.

This is deliberately NOT a return to majority voting.  The legacy specialist
outputs are treated as work products grouped into independent desks:
CONTEXT, SETUP, EXECUTION and CONTROL.  A candidate needs coherent work across
independent desks + market evidence + a recognizable setup fingerprint.

The lane may create direction/candidate authority.  It may NOT bypass:
- Entry reaction-zone selection/refinement;
- SL invalidation / reaction-conflict protection;
- TP reachability/barrier logic;
- technical R/R / economics;
- Safety/publication;
- Leverage V6;
- Alpha Decay.

No network, database, LLM, background thread, or new market-data request occurs
here.  Review/decay is injected by the runtime only after a candidate exists.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Mapping, Tuple

VERSION = "COMMIT19_2_LIVE_QUANT_SYNTHESIS_PATTERN_CONTRACT_V1"
_DIRECTIONAL = {"LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"}


def _u(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "-")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v if v is not None else default)
        return x if x == x else float(default)
    except Exception:
        return float(default)


def _market(system_type: Any, symbol: Any) -> str:
    raw = _u(system_type)
    sym = _u(symbol)
    if sym in {"SPY-USDT", "QQQ-USDT", "CL-USDT", "NATGAS-USDT", "COPPER-USDT", "XAG-USDT", "KSTR-USDT"}:
        return "MULTIASSET"
    return "FUTURES" if raw == "FUTURES" else "SPOT"


def _action_for(direction: str, market: str) -> str:
    if direction == "BULLISH":
        return "LONG" if market in {"FUTURES", "MULTIASSET"} else "COMPRA_SPOT"
    if direction == "BEARISH":
        return "SHORT" if market in {"FUTURES", "MULTIASSET"} else "VENTA_SPOT"
    return "NO_OPERAR"


def _direction(v: Any) -> str:
    raw = _u(v)
    if raw in {"LONG", "BUY", "BULLISH", "UP", "TREND_UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if raw in {"SHORT", "SELL", "BEARISH", "DOWN", "TREND_DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _risk_class(symbol: Any, market: str) -> str:
    if market == "SPOT":
        return "SPOT"
    if market == "MULTIASSET":
        return "MULTIASSET"
    try:
        from futures_universe import risk_class_for
        return str(risk_class_for(symbol) or "CORE1").upper()
    except Exception:
        return "CORE1"


def _workers(vote_record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    desk = dict((vote_record or {}).get("worker_desk_17_5_9") or {})
    rows = [dict(x) for x in (desk.get("workers") or []) if isinstance(x, Mapping)]
    if rows:
        return rows
    out: List[Dict[str, Any]] = []
    role_map = {
        "TÉCNICO PURO": "SETUP", "TECNICO PURO": "SETUP", "CHARTISTA": "SETUP",
        "CAZADOR DE BALLENAS": "CONTEXT", "MACROECONOMISTA": "CONTEXT", "MULTIFRAME": "CONTEXT",
        "PULLBACK": "EXECUTION", "SMART MONEY": "EXECUTION", "EL LIQUIDADOR": "EXECUTION",
        "ESCÉPTICO": "CONTROL", "ESCEPTICO": "CONTROL",
    }
    for raw in (vote_record or {}).get("todos_los_votos") or []:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("trader") or "")
        out.append({
            "worker": name,
            "desk": role_map.get(_u(name), "SETUP"),
            "legacy_direction_hint": _direction(raw.get("accion") or raw.get("accion_original")),
            "legacy_confidence": _f(raw.get("confianza_original") or raw.get("confianza")),
            "timeframe_emphasis": 1.0,
            "strategies_observed": list(raw.get("estrategias") or []),
            "work_notes": list(raw.get("razones") or []),
        })
    return out


def _desk_scores(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, float]]:
    buckets: Dict[str, Dict[str, List[float]]] = {
        "CONTEXT": {"BULLISH": [], "BEARISH": []},
        "SETUP": {"BULLISH": [], "BEARISH": []},
        "EXECUTION": {"BULLISH": [], "BEARISH": []},
        "CONTROL": {"BULLISH": [], "BEARISH": []},
    }
    for row in rows:
        desk = _u(row.get("desk"))
        if desk not in buckets:
            continue
        direction = _direction(row.get("legacy_direction_hint"))
        if direction not in {"BULLISH", "BEARISH"}:
            continue
        conf = max(0.0, min(100.0, _f(row.get("legacy_confidence")))) / 100.0
        emphasis = max(0.70, min(1.30, _f(row.get("timeframe_emphasis"), 1.0)))
        # One specialist cannot dominate a desk: each contribution is bounded.
        buckets[desk][direction].append(min(1.0, conf * emphasis))
    out: Dict[str, Dict[str, float]] = {}
    for desk, dirs in buckets.items():
        out[desk] = {}
        for direction, vals in dirs.items():
            out[desk][direction] = round(sum(vals) / max(1, len(vals)), 4) if vals else 0.0
    return out


def _market_features(capas: Mapping[str, Any], workers: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    trend = dict(capas.get("trend") or {})
    momentum = dict(capas.get("momentum") or {})
    volume = dict(capas.get("volume") or {})
    volatility = dict(capas.get("volatility") or {})
    structure = dict(capas.get("structure") or {})
    patterns = capas.get("patterns") or {}
    op = dict(capas.get("operational_intelligence") or {})
    mtf = dict(op.get("multi_timeframe") or {})
    thesis = dict(op.get("thesis") or {})

    worker_blob = " ".join(
        [str(x) for r in workers for x in (list(r.get("strategies_observed") or []) + list(r.get("work_notes") or []))]
    ).upper()
    struct_blob = (str(structure) + " " + str(patterns) + " " + worker_blob).upper()
    mom_ind = dict(momentum.get("indicators") or {})
    rsi = _f(momentum.get("rsi") if momentum.get("rsi") is not None else mom_ind.get("rsi"), 50.0)
    macd = _f(momentum.get("macd_histogram") if momentum.get("macd_histogram") is not None else mom_ind.get("macd_histogram") or mom_ind.get("macd_hist"))
    ratio = _f(volume.get("volume_ratio"), 1.0)
    adx = _f(trend.get("adx"))

    sweep = bool(structure.get("liquidity_sweep") or structure.get("sweep") or "SWEEP" in struct_blob or "STOP_HUNT" in struct_blob)
    mss = bool(structure.get("mss") or structure.get("bos") or structure.get("market_structure_shift") or any(x in struct_blob for x in ("MSS", "BOS", "CHOCH")))
    displacement = bool(structure.get("displacement") or structure.get("displacement_confirmed") or "DISPLACEMENT" in struct_blob)
    poi = bool(
        structure.get("order_blocks") or structure.get("fvg") or structure.get("fair_value_gaps")
        or structure.get("nearest_support") or structure.get("nearest_resistance") or structure.get("poc") or structure.get("vwap")
        or any(x in struct_blob for x in ("ORDER BLOCK", "ORDER_BLOCK", "FVG", "POC", "VWAP", "SUPPORT", "RESISTANCE", "FIBONACCI", "RETEST"))
    )
    breakout = any(x in struct_blob for x in ("BREAKOUT", "BREAK OUT", "RUPTURA")) or mss
    retest = any(x in struct_blob for x in ("RETEST", "PULLBACK", "RETROCESO")) or poi
    squeeze = bool(volatility.get("squeeze_on") or int(_f(volatility.get("squeeze_length"))) > 0)

    multi_macro = dict(capas.get("multiasset_macro") or {})
    multi_bank = dict(capas.get("multiasset_strategy_bank") or {})
    macro_generic = dict(capas.get("macro_context") or {})
    market_segment = _u(capas.get("market_segment"))
    macro_risk = _u(
        (multi_macro.get("risk_level") if market_segment == "MULTIASSET" else None)
        or macro_generic.get("risk_level") or macro_generic.get("risk")
    )
    preferred_patterns = [_u(x) for x in list(multi_bank.get("preferred_for_context") or [])]

    return {
        "trend_direction": _direction(trend.get("direction")),
        "momentum_direction": _direction(momentum.get("direction")),
        "structure_direction": _direction(structure.get("direction") or structure.get("structure_direction")),
        "mtf_direction": _direction(mtf.get("dominant_direction")),
        "mtf_alignment": _u(mtf.get("alignment")),
        "mtf_conflict": bool(mtf.get("conflict")),
        "macro_risk": macro_risk,
        "multiasset_macro_gate": _u(multi_macro.get("gate")),
        "market_segment": market_segment,
        "asset_class": _u(capas.get("asset_class")),
        "preferred_patterns": preferred_patterns,
        "regime": _u((op.get("context") or {}).get("regime") or multi_bank.get("regime") or (capas.get("market_regime") or {}).get("regime")),
        "volatility_state": _u((op.get("context") or {}).get("volatility") or volatility.get("ftm_state") or volatility.get("state")),
        "adx": adx, "rsi": rsi, "macd_hist": macd, "volume_ratio": ratio,
        "sweep": sweep, "mss": mss, "displacement": displacement, "poi": poi,
        "breakout": breakout, "retest": retest, "squeeze": squeeze,
        "thesis": thesis,
        "blob": struct_blob,
    }


def _pattern(direction: str, f: Mapping[str, Any], desk: Mapping[str, Mapping[str, float]]) -> Tuple[str, float, List[str]]:
    reasons: List[str] = []
    sign_ok_trend = f.get("trend_direction") == direction
    sign_ok_mom = f.get("momentum_direction") == direction
    exec_score = _f((desk.get("EXECUTION") or {}).get(direction))
    setup_score = _f((desk.get("SETUP") or {}).get(direction))

    candidates: List[Tuple[float, str, List[str]]] = []
    if f.get("sweep") and (f.get("mss") or f.get("displacement")) and f.get("poi"):
        candidates.append((0.96, "SWEEP_REVERSAL", ["barrido de liquidez", "cambio/desplazamiento de estructura", "POI estructural"]))
    if sign_ok_trend and f.get("poi") and exec_score >= 0.48:
        score = 0.80 + min(0.12, max(0.0, (_f(f.get("adx")) - 18.0) / 100.0))
        candidates.append((score, "TREND_PULLBACK", ["tendencia alineada", "retroceso/POI", "timing de ejecución alineado"]))
    if f.get("breakout") and f.get("retest") and setup_score >= 0.48:
        candidates.append((0.84, "BREAKOUT_RETEST", ["ruptura estructural", "retest/zona de reacción", "setup confirmado"]))
    if f.get("squeeze") and sign_ok_trend and sign_ok_mom and _f(f.get("volume_ratio"), 1.0) >= 1.05:
        candidates.append((0.83, "COMPRESSION_EXPANSION", ["compresión previa", "dirección y momentum alineados", "volumen confirma expansión"]))
    if sign_ok_trend and sign_ok_mom and _f(f.get("adx")) >= 18.0:
        v_bonus = 0.05 if _f(f.get("volume_ratio"), 1.0) >= 1.0 else 0.0
        candidates.append((0.73 + v_bonus, "MOMENTUM_CONTINUATION", ["tendencia y momentum alineados", f"ADX {_f(f.get('adx')):.1f}", f"volumen {_f(f.get('volume_ratio'),1.0):.2f}x"]))
    if f.get("poi") and setup_score >= 0.55 and exec_score >= 0.55:
        candidates.append((0.70, "STRUCTURE_RETEST", ["zona estructural de reacción", "setup y ejecución alineados"]))
    if not candidates:
        return "", 0.0, []
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], round(candidates[0][0], 3), candidates[0][2]


def _family_support(op: Mapping[str, Any], direction: str) -> List[str]:
    thesis = dict(op.get("thesis") or {})
    return list(thesis.get("long_families") if direction == "BULLISH" else thesis.get("short_families") or [])



def _pattern_support_contract(pattern: str, direction: str, f: Mapping[str, Any],
                              desks: Mapping[str, Mapping[str, float]],
                              families: List[str], market: str, risk_class: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Commit 19.2: pattern-specific evidence replaces generic family quotas.

    A generic ``3/4 families`` count was useful as an anti-noise guard, but in
    production it became an authority bottleneck: a concrete Sweep+MSS+POI or a
    Trend+Pullback+MTF setup could be rejected simply because the thesis layer
    had not labelled enough generic families.  This function does *not* lower
    the synthesis score, Entry/SL/TP quality, Safety or publication thresholds.
    It asks each pattern for the evidence that actually defines that pattern.
    """
    pattern=_u(pattern); risk_class=_u(risk_class); market=_u(market)
    setup=_f((desks.get("SETUP") or {}).get(direction))
    execution=_f((desks.get("EXECUTION") or {}).get(direction))
    context=_f((desks.get("CONTEXT") or {}).get(direction))
    mtf_support=bool(f.get("mtf_direction")==direction or f.get("mtf_alignment") in {"ALIGNED","SUPPORTIVE"})
    trend_support=bool(f.get("trend_direction")==direction)
    mom_support=bool(f.get("momentum_direction")==direction)
    volume=_f(f.get("volume_ratio"),1.0)
    adx=_f(f.get("adx"))
    high_extra=True
    # HIGH crypto remains stricter, but the extra condition is market evidence
    # (MTF/volume), not an arbitrary count of labels.
    if risk_class=="HIGH":
        high_extra=bool(mtf_support or volume>=1.15)

    details={
        "setup":round(setup,3),"execution":round(execution,3),"context":round(context,3),
        "mtf_support":mtf_support,"trend_support":trend_support,"momentum_support":mom_support,
        "volume_ratio":round(volume,3),"adx":round(adx,2),"family_labels":len(set(families)),
        "high_extra":high_extra,
    }
    ok=False; reason="PATTERN_EVIDENCE_INCOMPLETE"
    if pattern=="SWEEP_REVERSAL":
        ok=bool(f.get("sweep") and (f.get("mss") or f.get("displacement")) and f.get("poi")
                and setup>=0.48 and execution>=0.48 and high_extra)
        reason="SWEEP_MSS_POI_CONTRACT"
    elif pattern=="TREND_PULLBACK":
        ok=bool(trend_support and f.get("poi") and adx>=18.0
                and setup>=0.48 and execution>=0.50
                and (mtf_support or context>=0.38 or volume>=0.90) and high_extra)
        reason="TREND_PULLBACK_CONTEXT_CONTRACT"
    elif pattern=="BREAKOUT_RETEST":
        ok=bool(f.get("breakout") and f.get("retest") and setup>=0.50 and execution>=0.48
                and (f.get("displacement") or volume>=0.95 or mtf_support) and high_extra)
        reason="BREAKOUT_RETEST_CONFIRMATION_CONTRACT"
    elif pattern=="COMPRESSION_EXPANSION":
        ok=bool(f.get("squeeze") and trend_support and mom_support and volume>=1.05
                and setup>=0.48 and execution>=0.48 and high_extra)
        reason="COMPRESSION_EXPANSION_CONTRACT"
    elif pattern=="MOMENTUM_CONTINUATION":
        ok=bool(trend_support and mom_support and adx>=18.0 and volume>=1.0
                and setup>=0.48 and execution>=0.48
                and (mtf_support or context>=0.42) and high_extra)
        reason="MOMENTUM_MTF_VOLUME_CONTRACT"
    elif pattern=="STRUCTURE_RETEST":
        structure_support=bool(f.get("structure_direction")==direction or mtf_support or trend_support)
        ok=bool(f.get("poi") and structure_support and setup>=0.55 and execution>=0.55 and high_extra)
        reason="STRUCTURE_RETEST_CONTRACT"
    return ok,reason,details


def _public_reasons(direction: str, pattern: str, f: Mapping[str, Any], pattern_reasons: List[str], family_support: List[str]) -> List[str]:
    human = "alcista" if direction == "BULLISH" else "bajista"
    out = [f"La lectura de mercado es {human} y el patrón operativo identificado es {pattern.replace('_',' ').lower()}."]
    if f.get("mtf_alignment") in {"ALIGNED", "SUPPORTIVE"}:
        out.append("La estructura multitemporal disponible acompaña la dirección de la operación.")
    if _f(f.get("volume_ratio"), 1.0) >= 1.0:
        out.append(f"El volumen relativo es {_f(f.get('volume_ratio'),1.0):.2f}x y participa como confirmación, no como señal aislada.")
    if pattern_reasons:
        out.append("La entrada se construye sobre " + ", ".join(pattern_reasons[:3]) + ".")
    if family_support:
        translated = {"trend":"tendencia", "structure":"estructura", "momentum":"momentum", "volume":"volumen", "multiframe":"multitemporalidad", "liquidity":"liquidez", "macro":"contexto macro"}
        names = [translated.get(str(x).lower(), str(x).lower()) for x in family_support[:4]]
        out.append("La tesis combina evidencia independiente de " + ", ".join(names) + ".")
    return out[:4]


def synthesize_live_candidate(*, capas: Mapping[str, Any], vote_record: Mapping[str, Any], symbol: Any,
                              timeframe: Any, system_type: Any, review_trader: Any = None) -> Dict[str, Any]:
    """Create a LIVE synthesis candidate only when independent desks cohere.

    This function does not query history.  Exact per-fingerprint Alpha Decay is
    applied by commit19_1_runtime after synthesis has produced a fingerprint.
    """
    op = dict(capas.get("operational_intelligence") or {})
    existing = _u(op.get("candidate_action"))
    if bool(op.get("candidate_ready")) and existing in _DIRECTIONAL:
        return {"use": False, "reason": "EXISTING_GOVERNED_CANDIDATE", "version": VERSION}

    # If an exact Commit-19 Champion has already decayed, do not silently replace
    # that same cell with a generic rescue.  It belongs to Research/Shadow.
    c19 = dict(op.get("commit19_champion") or {})
    decay = dict(c19.get("alpha_decay") or {})
    if c19.get("matched") and decay.get("state") in {"SHADOW_DECAY", "RETIRED_ALPHA_DECAY"}:
        return {"use": False, "reason": "EXACT_CHAMPION_DECAY_RESEARCH_HANDOFF", "version": VERSION}

    market = _market(system_type, symbol)
    rows = _workers(vote_record)
    if len(rows) < 5:
        return {"use": False, "reason": "INSUFFICIENT_SPECIALIST_WORK_PRODUCTS", "version": VERSION}
    desks = _desk_scores(rows)
    f = _market_features(capas, rows)
    if f.get("mtf_conflict"):
        return {"use": False, "reason": "HARD_MTF_CONFLICT", "version": VERSION}
    if market in {"FUTURES", "MULTIASSET"} and f.get("macro_risk") == "CRITICAL":
        return {"use": False, "reason": "CRITICAL_MACRO_RISK", "version": VERSION}
    if market == "MULTIASSET" and f.get("multiasset_macro_gate") == "WAIT_EVENT":
        return {"use": False, "reason": "MULTIASSET_IMMINENT_EVENT_WAIT", "version": VERSION}

    # Direction comes from independent DESKS, not headcount. SETUP + EXECUTION
    # are mandatory; CONTEXT can be supplied either by the context desk or by
    # actual MTF/thesis evidence.
    candidate_rows: List[Dict[str, Any]] = []
    for direction in ("BULLISH", "BEARISH"):
        setup = _f((desks.get("SETUP") or {}).get(direction))
        execution = _f((desks.get("EXECUTION") or {}).get(direction))
        context = _f((desks.get("CONTEXT") or {}).get(direction))
        control_same = _f((desks.get("CONTROL") or {}).get(direction))
        opposite = "BEARISH" if direction == "BULLISH" else "BULLISH"
        control_opp = _f((desks.get("CONTROL") or {}).get(opposite))
        if setup < 0.48 or execution < 0.48:
            continue
        context_market_support = bool(
            context >= 0.38
            or f.get("mtf_direction") == direction
            or f.get("trend_direction") == direction
        )
        if not context_market_support:
            continue
        fams = _family_support(op, direction)
        risk_class = _risk_class(symbol, market)
        pattern, pattern_score, pattern_reasons = _pattern(direction, f, desks)
        if not pattern:
            continue
        # Commit 19.2: validate the setup by the concrete evidence required by
        # its own pattern.  We keep the global synthesis quality floor at 0.66
        # and all downstream Premium thresholds unchanged.
        pattern_ok, pattern_contract, pattern_evidence = _pattern_support_contract(
            pattern, direction, f, desks, fams, market, risk_class
        )
        if not pattern_ok:
            continue
        desk_strength = (setup + execution + min(1.0, context + 0.15)) / 3.0
        family_bonus = min(0.12, 0.025 * len(fams))
        multi_context_bonus = 0.025 if (market == "MULTIASSET" and pattern in set(f.get("preferred_patterns") or [])) else 0.0
        control_penalty = min(0.12, max(0.0, control_opp - control_same) * 0.16)
        score = 0.47 * desk_strength + 0.38 * pattern_score + family_bonus + multi_context_bonus - control_penalty
        candidate_rows.append({
            "direction": direction, "score": score, "setup": setup, "execution": execution,
            "context": context, "control_penalty": control_penalty, "families": fams,
            "pattern": pattern, "pattern_score": pattern_score, "pattern_reasons": pattern_reasons,
            "pattern_contract": pattern_contract, "pattern_evidence": pattern_evidence,
        })

    if not candidate_rows:
        return {"use": False, "reason": "NO_COHERENT_DESK_PATTERN_SYNTHESIS", "version": VERSION, "desk_scores": desks}
    candidate_rows.sort(key=lambda x: x["score"], reverse=True)
    best = candidate_rows[0]
    if len(candidate_rows) > 1 and best["score"] < candidate_rows[1]["score"] + 0.10:
        return {"use": False, "reason": "DIRECTIONAL_SYNTHESIS_AMBIGUOUS", "version": VERSION, "desk_scores": desks}
    if best["score"] < 0.66:
        return {"use": False, "reason": "SYNTHESIS_QUALITY_BELOW_MINIMUM", "version": VERSION, "quality_raw": round(best["score"],4)}

    action = _action_for(best["direction"], market)
    review_mult = 1.0
    if review_trader is not None:
        try:
            review_mult = _f(review_trader.get_confidence_adjustment(
                symbol, timeframe, action, system_type=("futures" if market in {"FUTURES","MULTIASSET"} else "spot")
            ), 1.0)
        except Exception:
            review_mult = 1.0
    # ReviewTrader is statistical context here, not a pre-LIVE veto. Exact 8-loss
    # authority is handled by fingerprint decay below this layer.
    review_mult = max(0.92, min(1.08, review_mult))
    confidence = min(88.0, max(70.0, (58.0 + 34.0 * best["score"]) * review_mult))
    setup_family = best["pattern"]
    fingerprint_raw = f"{market}|{_u(symbol)}|{_u(timeframe)}|{action}|{setup_family}|V1"
    short_hash = hashlib.sha1(fingerprint_raw.encode("utf-8")).hexdigest()[:10].upper()
    synthesis_id = f"QS_{_u(symbol)}_{_u(timeframe)}_{action}_{setup_family}_{short_hash}"
    decay_key = f"{synthesis_id}::{_u(symbol)}::{action}"
    public_reasons = _public_reasons(best["direction"], setup_family, f, best["pattern_reasons"], best["families"])

    return {
        "use": True,
        "version": VERSION,
        "authority": "LIVE_QUANT_SYNTHESIS_COMMIT19_1",
        "action": action,
        "direction": best["direction"],
        "confidence": round(confidence, 2),
        "synthesis_quality": round(best["score"] * 100.0, 2),
        "setup_family": setup_family,
        "pattern_score": round(best["pattern_score"] * 100.0, 2),
        "pattern_contract": best.get("pattern_contract"),
        "pattern_evidence": best.get("pattern_evidence"),
        "synthesis_id": synthesis_id,
        "decay_key": decay_key,
        "research_handoff_key": f"C19_1_SHADOW::{decay_key}",
        "desk_scores": desks,
        "independent_families": best["families"],
        "review_multiplier": round(review_mult, 3),
        "market_context": {
            "regime": f.get("regime"), "volatility": f.get("volatility_state"),
            "adx": round(_f(f.get("adx")),2), "volume_ratio": round(_f(f.get("volume_ratio"),1.0),3),
            "mtf_alignment": f.get("mtf_alignment"),
        },
        "public_reasons": public_reasons,
        "policy": {
            "majority_vote_used": False,
            "single_indicator_can_create_live_alone": False,
            "entry_reaction_zone_required_downstream": True,
            "sl_outside_reaction_required_downstream": True,
            "tp_barrier_reachability_required_downstream": True,
            "safety_unchanged": True,
            "rr_unchanged": True,
            "leverage_v6_unchanged": True,
        },
    }
