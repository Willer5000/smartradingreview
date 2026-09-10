"""Commit 7 — Edge Discovery Engine (research only).

Finds small, falsifiable feature combinations that separate stronger from weaker
outcomes inside already-persisted Spot/Futures evidence.  It never changes
votes, Safety, Entry, SL, TP, leverage or publication.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import hashlib
import json
import math

EDGE_DISCOVERY_VERSION = "C7_EDGE_DISCOVERY_V1"
MAX_FACTORS = 3
MIN_DISCOVERY_RESOLVED = 3
MIN_VALIDATION_RESOLVED = 3
MIN_LOW_PRIORITY_RESOLVED = 8


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _first_result(signal: Dict[str, Any]) -> Dict[str, Any]:
    results = signal.get("signal_results") or []
    if isinstance(results, dict):
        return results
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]
    return {}


def _status(signal: Dict[str, Any]) -> str:
    result = _first_result(signal)
    return str(result.get("status") or signal.get("status") or "").lower()


def _realized_r(signal: Dict[str, Any]) -> Optional[float]:
    status = _status(signal)
    if status not in ("tp_hit", "sl_hit"):
        return None
    if status == "sl_hit":
        return -1.0
    entry = _safe_float(signal.get("entry_price") or signal.get("entry"))
    sl = _safe_float(signal.get("stop_loss"))
    tp = _safe_float(signal.get("take_profit"))
    if entry and sl and tp:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk > 0:
            return reward / risk
    rr = _safe_float(signal.get("risk_reward"))
    return rr if rr and rr > 0 else None


def _feature(key: str, label: str, value: str) -> Tuple[str, str]:
    value = str(value or "").strip().upper()
    return (f"{key}:{value}", f"{label}: {value.replace('_', ' ').title()}")


def _extract_features(signal: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Returns anchor/condition features. Features are intentionally coarse."""
    context = _as_dict(signal.get("context"))
    learning = _as_dict(context.get("learning"))
    execution = _as_dict(context.get("execution"))
    quant = _as_dict(learning.get("quantitative_shadow"))
    micro = _as_dict(learning.get("microstructure_shadow"))
    cautious = _as_dict(learning.get("cautious_shadow"))
    q7 = _as_dict(learning.get("q7_strategy_lab_shadow"))
    trendline = _as_dict(learning.get("trendline_strategy_lab_shadow"))
    attribution = _as_dict(learning.get("strategy_attribution_v2"))

    anchors: Dict[str, str] = {}
    conditions: Dict[str, str] = {}

    def add(target: Dict[str, str], item: Tuple[str, str]) -> None:
        target[item[0]] = item[1]

    action = str(signal.get("action_normalized") or signal.get("action") or "").upper()
    if action in ("COMPRA_SPOT", "BUY"):
        action = "LONG"
    elif action in ("VENTA_SPOT", "SELL"):
        action = "SHORT"
    if action in ("LONG", "SHORT"):
        add(conditions, _feature("ACTION", "Dirección", action))

    timeframe = str(signal.get("timeframe") or "").upper()
    if timeframe:
        add(conditions, _feature("TF", "Temporalidad", timeframe))

    regime = str(quant.get("regime") or "").upper()
    if regime and regime not in ("UNAVAILABLE", "UNKNOWN"):
        add(anchors, _feature("REGIME", "Régimen", regime))

    cautious_status = str(cautious.get("status") or "").upper()
    if cautious_status == "CAUTIOUS_SHADOW" and bool(cautious.get("candidate", False)):
        anchors["CAUTIOUS:NEAR_PREMIUM"] = "Candidato prudente cercano a Premium"

    q7_rsi = _as_dict(q7.get("rsi_profile"))
    profile = str(q7_rsi.get("profile") or q7.get("active_profile") or "").upper()
    alignment = str(q7_rsi.get("alignment_with_system") or "").upper()
    if profile and alignment and alignment not in ("NEUTRAL", "NOT_APPLICABLE"):
        key = f"{profile}|{alignment}"
        add(anchors, _feature("RSI_PROFILE", "RSI adaptativo", key))

    retest = _as_dict(q7.get("breakout_retest"))
    retest_state = str(retest.get("state") or "").upper()
    if retest_state and retest_state not in ("OUT_OF_SCOPE", "NO_RETEST", "NO_EDGE"):
        add(anchors, _feature("RETEST", "Ruptura/retesteo", retest_state))

    vwap = _as_dict(q7.get("vwap_reversion"))
    vwap_state = str(vwap.get("state") or "").upper()
    if vwap_state and vwap_state not in ("OUT_OF_SCOPE", "NO_EDGE", "REGIME_NOT_RANGING"):
        add(anchors, _feature("VWAP", "VWAP", vwap_state))

    micro_alignment = str(micro.get("alignment") or "").upper()
    if micro_alignment and micro_alignment not in ("UNAVAILABLE", "UNKNOWN"):
        add(conditions, _feature("MICRO", "Microestructura", micro_alignment))

    quant_alignment = str(quant.get("direction_alignment") or "").upper()
    if quant_alignment and quant_alignment not in ("NOT_APPLICABLE", "UNAVAILABLE", "UNKNOWN"):
        add(conditions, _feature("QUANT_ALIGN", "Contexto cuantitativo", quant_alignment))

    entry_location = str(quant.get("entry_location") or "").upper()
    if entry_location and entry_location not in ("UNAVAILABLE", "UNKNOWN"):
        add(conditions, _feature("ENTRY_LOC", "Ubicación de entrada", entry_location))

    def_score = _safe_float(execution.get("entry_defensibility_score"))
    if def_score is not None:
        if def_score >= 75:
            add(conditions, _feature("DEF", "Defensa de entrada", "ALTA"))
        elif def_score < 55:
            add(conditions, _feature("DEF", "Defensa de entrada", "BAJA"))

    reach = _safe_float(execution.get("entry_reachability_score"))
    if reach is not None:
        if reach >= 75:
            add(conditions, _feature("REACH", "Alcanzabilidad", "ALTA"))
        elif reach < 50:
            add(conditions, _feature("REACH", "Alcanzabilidad", "BAJA"))

    tpq = _safe_float(execution.get("tp_quality_score"))
    if tpq is not None:
        if tpq >= 70:
            add(conditions, _feature("TPQ", "Calidad de objetivo", "ALTA"))
        elif tpq < 55:
            add(conditions, _feature("TPQ", "Calidad de objetivo", "BAJA"))

    # El propio Entry ya deja en entry_source la secuencia SMC que lo reforzó.
    # La convertimos en banderas gruesas, sin recalcular mercado ni tocar niveles.
    entry_source = str(execution.get("entry_source") or "").upper()
    entry_source_features = (
        (("SWEEP",), "ENTRY_SMC:SWEEP", "Entry con barrido de liquidez"),
        (("MSS", "BOS"), "ENTRY_SMC:MSS_BOS", "Entry con cambio de estructura"),
        (("DISPLACEMENT",), "ENTRY_SMC:DISPLACEMENT", "Entry con desplazamiento"),
        (("LIQUIDITY",), "ENTRY_SMC:LIQUIDITY", "Entry próximo a liquidez"),
        (("ORDER BLOCK",), "ENTRY_POI:ORDER_BLOCK", "Entry en Order Block"),
        (("FVG",), "ENTRY_POI:FVG", "Entry en Fair Value Gap"),
        (("FIBONACCI",), "ENTRY_POI:FIBONACCI", "Entry en Fibonacci"),
        (("SOPORTE",), "ENTRY_POI:SUPPORT", "Entry en soporte"),
        (("RESISTENCIA",), "ENTRY_POI:RESISTANCE", "Entry en resistencia"),
        (("POC",), "ENTRY_POI:POC", "Entry en zona de máximo volumen"),
    )
    for tokens, key, label in entry_source_features:
        if any(token in entry_source for token in tokens):
            conditions[key] = label

    # Strategy Attribution V2 ya preserva qué estrategia realmente APOYÓ la
    # dirección final. Sólo usamos categorías estructurales gruesas para evitar
    # una explosión combinatoria y no acreditar una estrategia opuesta.
    support_items = attribution.get("items") or []
    if isinstance(support_items, list):
        strategy_groups = {
            "LIQUIDITY_SWEEP": ("STRATEGY:SWEEP", "Estrategia de barrido apoyando la señal"),
            "ORDER_BLOCK": ("STRATEGY:ORDER_BLOCK", "Order Block apoyando la señal"),
            "FVG": ("STRATEGY:FVG", "Fair Value Gap apoyando la señal"),
            "DIVERGENCIA": ("STRATEGY:DIVERGENCE", "Divergencia apoyando la señal"),
            "MAVERICK": ("STRATEGY:WHALE", "Flujo de grandes participantes apoyando la señal"),
            "ICEBERG": ("STRATEGY:ICEBERG", "Absorción iceberg apoyando la señal"),
            "DMI_CROSS": ("STRATEGY:DMI", "Cruce direccional apoyando la señal"),
            "PSAR_REVERSAL": ("STRATEGY:PSAR", "Reversión de tendencia apoyando la señal"),
        }
        for item in support_items:
            item = _as_dict(item)
            if str(item.get("relation_to_final") or "").upper() != "SUPPORT":
                continue
            strategy = str(item.get("strategy") or "").upper()
            for token, (key, label) in strategy_groups.items():
                if token in strategy:
                    conditions[key] = label

    trendline_labels = {
        "TRENDLINE_SUPPORT_BOUNCE": "Rebote en soporte dinámico",
        "TRENDLINE_RESISTANCE_REJECTION": "Rechazo en resistencia dinámica",
        "TRENDLINE_BREAK_RETEST_LONG": "Ruptura y retesteo alcista de línea dinámica",
        "TRENDLINE_BREAK_RETEST_SHORT": "Ruptura y retesteo bajista de línea dinámica",
        "FALSE_BREAK_RECLAIM_LONG": "Falsa ruptura y recuperación de soporte dinámico",
        "FALSE_BREAK_RECLAIM_SHORT": "Falsa ruptura y recuperación de resistencia dinámica",
    }
    for name, item in (_as_dict(trendline.get("strategies"))).items():
        item = _as_dict(item)
        state = str(item.get("state") or "").upper()
        direction = str(item.get("direction") or "").upper()
        if (
            state
            and state not in ("NO_EDGE", "OUT_OF_SCOPE")
            and direction in ("LONG", "SHORT")
            and action in ("LONG", "SHORT")
            and direction == action
        ):
            key = f"TRENDLINE_STATE:{state}"
            anchors[key] = trendline_labels.get(state, "Reacción en línea de tendencia dinámica")

    return {"anchors": anchors, "conditions": conditions}


def _observation(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    realized = _realized_r(signal)
    if realized is None:
        return None
    created = _parse_dt(signal.get("created_at"))
    if created is None:
        return None
    features = _extract_features(signal)
    result = _first_result(signal)
    forensic = _as_dict(result.get("execution_forensics"))
    mfe = _safe_float(forensic.get("mfe_r"), _safe_float(result.get("mfe_r")))
    mae = _safe_float(forensic.get("mae_r"), _safe_float(result.get("mae_r")))
    return {
        "created_at": created,
        "status": _status(signal),
        "realized_r": realized,
        "features": features,
        "mfe_r": mfe,
        "mae_r": mae,
    }


def _metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"resolved": 0, "tp": 0, "sl": 0, "win_rate_pct": None, "expectancy_r": None, "profit_factor": None, "avg_mfe_r": None, "avg_mae_r": None}
    r_values = [float(row["realized_r"]) for row in rows]
    tp = sum(1 for row in rows if row["status"] == "tp_hit")
    sl = sum(1 for row in rows if row["status"] == "sl_hit")
    gains = sum(v for v in r_values if v > 0)
    losses = abs(sum(v for v in r_values if v < 0))
    mfe = [row["mfe_r"] for row in rows if row.get("mfe_r") is not None]
    mae = [row["mae_r"] for row in rows if row.get("mae_r") is not None]
    return {
        "resolved": len(rows),
        "tp": tp,
        "sl": sl,
        "win_rate_pct": round(tp / len(rows) * 100.0, 2),
        "expectancy_r": round(sum(r_values) / len(r_values), 4),
        "profit_factor": round(gains / losses, 3) if losses > 0 else (None if gains <= 0 else 99.0),
        "avg_mfe_r": round(sum(mfe) / len(mfe), 4) if mfe else None,
        "avg_mae_r": round(sum(mae) / len(mae), 4) if mae else None,
    }


def _candidate_sets(discovery_rows: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, ...], Dict[str, str]]:
    candidates: Dict[Tuple[str, ...], Dict[str, str]] = {}
    for row in discovery_rows:
        features = row["features"]
        anchors = features.get("anchors") or {}
        conditions = features.get("conditions") or {}
        # Regime-only hypotheses are valid because current data already shows
        # large regime dispersion; strategy anchors get optional context.
        for anchor_key, anchor_label in anchors.items():
            base_labels = {anchor_key: anchor_label}
            keys = sorted(conditions.keys())
            for extra_count in range(0, min(MAX_FACTORS - 1, len(keys)) + 1):
                for extra in combinations(keys, extra_count):
                    factors = tuple(sorted((anchor_key,) + tuple(extra)))
                    labels = dict(base_labels)
                    for key in extra:
                        labels[key] = conditions[key]
                    candidates.setdefault(factors, labels)
    return candidates


def _matches(row: Dict[str, Any], factors: Sequence[str]) -> bool:
    features = row["features"]
    available = set((features.get("anchors") or {}).keys()) | set((features.get("conditions") or {}).keys())
    return all(factor in available for factor in factors)


def _hypothesis_state(total: Dict[str, Any], discovery: Dict[str, Any], validation: Dict[str, Any], baseline_exp: Optional[float]) -> str:
    n = int(total.get("resolved") or 0)
    dn = int(discovery.get("resolved") or 0)
    vn = int(validation.get("resolved") or 0)
    exp = total.get("expectancy_r")
    dexp = discovery.get("expectancy_r")
    vexp = validation.get("expectancy_r")
    lift = (exp - baseline_exp) if exp is not None and baseline_exp is not None else None

    if n >= MIN_LOW_PRIORITY_RESOLVED and exp is not None and exp <= -0.75 and (vn < MIN_VALIDATION_RESOLVED or (vexp is not None and vexp <= -0.50)):
        return "LOW_PRIORITY_RESEARCH"
    if dn >= 5 and dexp is not None and dexp > 0 and vn >= MIN_VALIDATION_RESOLVED and vexp is not None and vexp > 0:
        return "RESEARCH_PRIORITY"
    if n >= 10 and exp is not None and exp > 0 and vn >= MIN_VALIDATION_RESOLVED and vexp is not None and vexp > 0:
        return "RESEARCH_PRIORITY"
    if dn >= 5 and dexp is not None and (dexp > 0 or (lift is not None and lift >= 0.35)):
        return "PROMISING_NEEDS_VALIDATION"
    return "OBSERVE"


def _hash_key(market: str, factors: Sequence[str]) -> str:
    raw = f"{market}|{'|'.join(factors)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def discover_edges(rows: Iterable[Dict[str, Any]], market: str, max_results: int = 20) -> Dict[str, Any]:
    observations = [obs for obs in (_observation(row) for row in (rows or [])) if obs]
    observations.sort(key=lambda row: row["created_at"])
    baseline = _metrics(observations)
    if len(observations) < 2:
        return {
            "version": EDGE_DISCOVERY_VERSION,
            "market": market,
            "authority": "RESEARCH_ONLY",
            "resolved": len(observations),
            "baseline": baseline,
            "cutoff": None,
            "priority": [],
            "watch": [],
            "low_priority": [],
        }

    split_index = max(1, min(len(observations) - 1, int(len(observations) * 0.70)))
    cutoff = observations[split_index]["created_at"]
    discovery_rows = observations[:split_index]
    validation_rows = observations[split_index:]
    candidate_map = _candidate_sets(discovery_rows)
    baseline_exp = baseline.get("expectancy_r")
    hypotheses: List[Dict[str, Any]] = []

    for factors, labels in candidate_map.items():
        drows = [row for row in discovery_rows if _matches(row, factors)]
        if len(drows) < MIN_DISCOVERY_RESOLVED:
            continue
        vrows = [row for row in validation_rows if _matches(row, factors)]
        all_rows = drows + vrows
        dm = _metrics(drows)
        vm = _metrics(vrows)
        tm = _metrics(all_rows)
        state = _hypothesis_state(tm, dm, vm, baseline_exp)
        exp = tm.get("expectancy_r")
        lift = round(exp - baseline_exp, 4) if exp is not None and baseline_exp is not None else None
        ordered_labels = [labels[key] for key in factors if key in labels]
        hypotheses.append({
            "hypothesis_key": _hash_key(market, factors),
            "market": market,
            "factors": list(factors),
            "labels": ordered_labels,
            "label": " + ".join(ordered_labels),
            "state": state,
            "authority": "RESEARCH_ONLY",
            "production_change": False,
            "lift_vs_baseline_r": lift,
            "discovery": dm,
            "validation": vm,
            "total": tm,
        })

    rank = {"RESEARCH_PRIORITY": 0, "PROMISING_NEEDS_VALIDATION": 1, "OBSERVE": 2, "LOW_PRIORITY_RESEARCH": 3}
    hypotheses.sort(key=lambda row: (
        rank.get(row["state"], 9),
        -(row["validation"].get("expectancy_r") if row["validation"].get("expectancy_r") is not None else -99),
        -(row["total"].get("expectancy_r") if row["total"].get("expectancy_r") is not None else -99),
        -(row["total"].get("resolved") or 0),
        len(row["factors"]),
    ))

    def _compact_ranked(source, limit):
        selected = []
        for row in source:
            factors = set(row.get("factors") or [])
            total = row.get("total") or {}
            validation = row.get("validation") or {}
            redundant = False
            for previous in selected:
                prev_factors = set(previous.get("factors") or [])
                prev_total = previous.get("total") or {}
                prev_validation = previous.get("validation") or {}
                same_evidence = (
                    total.get("resolved") == prev_total.get("resolved")
                    and total.get("expectancy_r") == prev_total.get("expectancy_r")
                    and validation.get("resolved") == prev_validation.get("resolved")
                    and validation.get("expectancy_r") == prev_validation.get("expectancy_r")
                )
                if same_evidence and prev_factors.issubset(factors):
                    redundant = True
                    break
            if not redundant:
                selected.append(row)
            if len(selected) >= limit:
                break
        return selected

    priority_source = [row for row in hypotheses if row["state"] in ("RESEARCH_PRIORITY", "PROMISING_NEEDS_VALIDATION")]
    watch_source = [row for row in hypotheses if row["state"] == "OBSERVE"]
    low_source = [row for row in hypotheses if row["state"] == "LOW_PRIORITY_RESEARCH"]
    low_source.sort(key=lambda row: ((row["total"].get("expectancy_r") if row["total"].get("expectancy_r") is not None else 99), -(row["total"].get("resolved") or 0), len(row.get("factors") or [])))

    priority = _compact_ranked(priority_source, max_results)
    watch = _compact_ranked(watch_source, max_results)
    low = _compact_ranked(low_source, max_results)

    return {
        "version": EDGE_DISCOVERY_VERSION,
        "market": market,
        "authority": "RESEARCH_ONLY",
        "production_change": False,
        "policy": "IMPROVE_QUALITY_DO_NOT_LOWER_SAFETY",
        "resolved": len(observations),
        "baseline": baseline,
        "discovery_baseline": _metrics(discovery_rows),
        "validation_baseline": _metrics(validation_rows),
        "cutoff": cutoff.isoformat(),
        "priority": priority,
        "watch": watch,
        "low_priority": low,
        "candidate_count": len(hypotheses),
    }


def early_failure_watch(official_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = []
    for signal in official_rows or []:
        status = _status(signal)
        if status not in ("tp_hit", "sl_hit"):
            continue
        created = _parse_dt(signal.get("created_at"))
        if created:
            resolved.append((created, status))
    resolved.sort(key=lambda item: item[0], reverse=True)
    consecutive_sl = 0
    for _, status in resolved:
        if status == "sl_hit":
            consecutive_sl += 1
        else:
            break
    return {
        "version": EDGE_DISCOVERY_VERSION,
        "diagnostic_only": True,
        "resolved": len(resolved),
        "consecutive_sl": consecutive_sl,
        "alert": consecutive_sl >= 4,
        "severity": "HIGH" if consecutive_sl >= 6 else ("WATCH" if consecutive_sl >= 4 else "NORMAL"),
        "message": (
            f"Futures oficial acumula {consecutive_sl} resultados consecutivos en SL; priorizar investigación de defensa de entrada."
            if consecutive_sl >= 4 else "Sin racha temprana relevante."
        ),
    }


def build_edge_discovery_summary(spot_rows: Iterable[Dict[str, Any]], futures_shadow_rows: Iterable[Dict[str, Any]], futures_official_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "version": EDGE_DISCOVERY_VERSION,
        "authority": "RESEARCH_ONLY",
        "production_change": False,
        "futures_shadow": discover_edges(futures_shadow_rows, "FUTURES_SHADOW"),
        "spot": discover_edges(spot_rows, "SPOT_OFFICIAL"),
        "early_failure_watch": early_failure_watch(futures_official_rows),
    }


def _clean_futures_shadow(signal: Dict[str, Any]) -> bool:
    context = _as_dict(signal.get("context"))
    learning = _as_dict(context.get("learning"))
    return bool(
        str(signal.get("system_type") or "").lower() == "futures"
        and learning.get("cohort") == "FUTURES_PERPETUAL_REAL_CLOSED_V1"
        and learning.get("market_data_source") == "KUCOIN_FUTURES_PERPETUAL_REST"
        and not bool(learning.get("market_data_is_synthetic", True))
        and bool(learning.get("source_candle_closed", False))
        and str(learning.get("evaluation_role") or "").upper() == "SHADOW_ANALYSIS"
    )


def _clean_futures_official(signal: Dict[str, Any]) -> bool:
    context = _as_dict(signal.get("context"))
    learning = _as_dict(context.get("learning"))
    return bool(
        str(signal.get("system_type") or "").lower() == "futures"
        and learning.get("cohort") == "FUTURES_PERPETUAL_REAL_CLOSED_V1"
        and learning.get("market_data_source") == "KUCOIN_FUTURES_PERPETUAL_REST"
        and not bool(learning.get("market_data_is_synthetic", True))
        and bool(learning.get("source_candle_closed", False))
        and bool(learning.get("statistically_eligible", False))
        and str(learning.get("evaluation_role") or "").upper() == "EXECUTABLE_SIGNAL"
    )


def _clean_spot(signal: Dict[str, Any]) -> bool:
    context = _as_dict(signal.get("context"))
    learning = _as_dict(context.get("learning"))
    return bool(
        str(signal.get("system_type") or "").lower() == "spot"
        and str(learning.get("cohort") or "").upper().startswith("SPOT_")
        and bool(learning.get("statistically_eligible", False))
    )


def fetch_edge_rows(db, days_back: int = 90, max_rows: int = 2500) -> List[Dict[str, Any]]:
    if db is None or not getattr(db, "enabled", False):
        return []
    from q6_integrity import read_pages
    end = datetime.now(timezone.utc)
    cutoff = end - timedelta(days=max(1, min(int(days_back), 365)))

    def query():
        return (
            db.client.table("signals")
            .select("id,symbol,timeframe,system_type,action_normalized,status,created_at,entry_price,stop_loss,take_profit,risk_reward,context,signal_results(status,mfe_r,mae_r,execution_forensics)")
            .gte("created_at", cutoff.isoformat())
            .lt("created_at", end.isoformat())
            .in_("action_normalized", ["LONG", "SHORT", "COMPRA_SPOT", "VENTA_SPOT"])
            .eq("context->execution->>quality_score_version", "36W_V2_NORMALIZED")
            .order("created_at", desc=False)
            .order("id", desc=False)
        )
    rows = read_pages(query, max_rows=max_rows)
    return list(rows or [])


def persist_edge_discovery(db, summary: Dict[str, Any]) -> Dict[str, Any]:
    if db is None or not getattr(db, "enabled", False):
        return {"success": False, "reason": "DB_UNAVAILABLE"}
    now = datetime.now(timezone.utc).isoformat()
    stored = 0
    try:
        db.client.table("edge_discovery_runs").insert({
            "version": EDGE_DISCOVERY_VERSION,
            "summary": summary,
            "created_at": now,
        }).execute()
    except Exception as exc:
        return {"success": False, "reason": f"RUN_INSERT:{type(exc).__name__}"}

    for market_key in ("futures_shadow", "spot"):
        market_summary = _as_dict(summary.get(market_key))
        hypotheses = list(market_summary.get("priority") or []) + list(market_summary.get("low_priority") or [])
        for row in hypotheses[:40]:
            payload = {
                "hypothesis_key": row.get("hypothesis_key"),
                "market": row.get("market"),
                "state": row.get("state"),
                "factors": row.get("factors") or [],
                "label": row.get("label") or "",
                "evidence": row,
                "version": EDGE_DISCOVERY_VERSION,
                "last_seen_at": now,
            }
            try:
                db.client.table("edge_hypotheses").upsert(payload, on_conflict="hypothesis_key").execute()
                stored += 1
            except Exception:
                continue
    return {"success": True, "stored_hypotheses": stored}


def run_edge_discovery(db, days_back: int = 90) -> Dict[str, Any]:
    rows = fetch_edge_rows(db, days_back=days_back)
    shadow = [row for row in rows if _clean_futures_shadow(row)]
    official = [row for row in rows if _clean_futures_official(row)]
    spot = [row for row in rows if _clean_spot(row)]
    summary = build_edge_discovery_summary(spot, shadow, official)
    persistence = persist_edge_discovery(db, summary)
    summary["persistence"] = persistence
    summary["rows_scanned"] = len(rows)
    return summary


def get_latest_edge_discovery(db) -> Dict[str, Any]:
    if db is None or not getattr(db, "enabled", False):
        return {"version": EDGE_DISCOVERY_VERSION, "authority": "RESEARCH_ONLY", "status": "DB_UNAVAILABLE"}
    try:
        response = (
            db.client.table("edge_discovery_runs")
            .select("summary,created_at,version")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return {"version": EDGE_DISCOVERY_VERSION, "authority": "RESEARCH_ONLY", "status": "WAITING_FIRST_RUN"}
        summary = _as_dict(rows[0].get("summary"))
        summary["created_at"] = rows[0].get("created_at")
        return summary
    except Exception as exc:
        return {"version": EDGE_DISCOVERY_VERSION, "authority": "RESEARCH_ONLY", "status": f"UNAVAILABLE:{type(exc).__name__}"}
