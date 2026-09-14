from __future__ import annotations

"""V1 RC4 — profitability evidence fusion for 46 active specialist cells.

Rules:
- causal OOS is a historical prior, never a live trade;
- Shadow/live is current confirmation, never merged into historical N;
- a positive OOS candidate may support an already-existing setup;
- negative OOS or materially diverged Shadow can protect/block;
- every Futures symbol×TF and every Spot market×TF is tracked separately.
"""

import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests

_SESSION = requests.Session()
_LOCK = threading.Lock()
_CACHE = {"ts": 0.0, "promotions": [], "shadow": []}
_TTL = max(45, int(os.getenv("RESEARCH_EVIDENCE_CACHE_SECONDS", "90") or 90))
_POSITIVE = {"SHADOW_READY", "SHADOW_READY_FAST"}
_VISIBLE = _POSITIVE | {"OBSERVE", "VALIDATION_REQUIRED", "REJECTED_OOS", "VALIDATED_SINGLE_ASSET"}
_EXPERIMENTS = {"CAUSAL_COVERAGE_STRATEGY", "CAUSAL_REGISTRY_RETEST", "CAUSAL_SHADOW_RECYCLE"}
_COVERAGE_TARGET = 46
_RESEARCH_VERSION_PREFIX = "RFV1_10_RC4_46CELL"
_FUTURES_SYMBOLS = ("BTC-USDT","ETH-USDT","SOL-USDT","XRP-USDT","ADA-USDT","LINK-USDT","BNB-USDT")
_FUTURES_CORE_TFS = ("30M","1H","2H","4H")
_FUTURES_HIGH_TFS = ("12H","1D")
_FUTURES_HIGH_TF_SYMBOLS = ("BTC-USDT","ETH-USDT","SOL-USDT")
_FUTURES_TFS = _FUTURES_CORE_TFS + _FUTURES_HIGH_TFS
_SPOT_SYMBOLS = ("BTC-USDT","PAXG-USDT","PAXG-BTC")
_SPOT_TFS = ("4H","12H","1D","1W")


def _canonical_cell_key(row: Dict[str, Any]) -> Optional[str]:
    """Return one of the 40 active V1 symbol×TF cells, otherwise None."""
    scope = row.get("scope") or {}
    fam = str(scope.get("market_family") or "")
    sym = str(scope.get("symbol") or "").upper().replace("/", "-")
    tf = _norm_tf(scope.get("timeframe"))
    if fam == "CRYPTO_FUTURES":
        if sym not in _FUTURES_SYMBOLS:
            return None
        if tf in _FUTURES_CORE_TFS:
            return f"FUTURES|{sym}|{tf}"
        if tf in _FUTURES_HIGH_TFS and sym in _FUTURES_HIGH_TF_SYMBOLS:
            return f"FUTURES|{sym}|{tf}"
        return None
    if fam in {"CRYPTO_SPOT","PAXG_USDT","PAXG_BTC"}:
        if sym in _SPOT_SYMBOLS and tf in _SPOT_TFS:
            return f"SPOT|{sym}|{tf}"
    return None


def _cfg():
    url = str(os.getenv("CENTRAL_SUPABASE_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = str(
        os.getenv("CENTRAL_SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()
    return url, key


def _headers():
    url, key = _cfg()
    if not url or not key:
        raise RuntimeError("Research Evidence Fusion: Supabase no configurado")
    h = {"apikey": key, "Accept": "application/json"}
    if key.count(".") == 2:
        h["Authorization"] = f"Bearer {key}"
    return url, h


def _num(v, default=None):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def _load(force: bool = False):
    now = time.monotonic()
    with _LOCK:
        if (not force) and _CACHE["promotions"] and now - _CACHE["ts"] < _TTL:
            return list(_CACHE["promotions"]), list(_CACHE["shadow"])
    url, h = _headers()
    r = _SESSION.get(
        f"{url}/rest/v1/research_promotions_v1",
        params={
            "select": "candidate_key,source_engine,experiment,stage,reason,scope,metrics,meta,research_version,updated_at",
            "stage": "in.(OBSERVE,SHADOW_READY,SHADOW_READY_FAST,VALIDATION_REQUIRED,REJECTED_OOS,VALIDATED_SINGLE_ASSET)",
            "order": "updated_at.desc",
            "limit": "1800",
        },
        headers=h,
        timeout=7,
    )
    r.raise_for_status()
    promotions = r.json() if isinstance(r.json(), list) else []
    promotions = [
        p for p in promotions
        if str(p.get("experiment") or "") in _EXPERIMENTS
        and str(p.get("stage") or "") in _VISIBLE
        and (p.get("meta") or {}).get("is_current") is not False
        and str(p.get("research_version") or "").startswith(_RESEARCH_VERSION_PREFIX)
    ]
    shadow: List[Dict[str, Any]] = []
    try:
        sr = _SESSION.get(
            f"{url}/rest/v1/research_shadow_live_metrics_v1",
            params={"select": "*", "order": "updated_at.desc", "limit": "600"},
            headers=h,
            timeout=7,
        )
        sr.raise_for_status()
        raw = sr.json()
        if isinstance(raw, list):
            shadow = raw
    except Exception:
        pass
    with _LOCK:
        _CACHE.update(ts=now, promotions=list(promotions), shadow=list(shadow))
    return promotions, shadow


def market_family(system_type: str, symbol: str) -> str:
    st = str(system_type or "").lower()
    sym = str(symbol or "").upper().replace("/", "-")
    if st == "futures":
        return "CRYPTO_FUTURES"
    if sym == "PAXG-USDT":
        return "PAXG_USDT"
    if sym == "PAXG-BTC":
        return "PAXG_BTC"
    return "CRYPTO_SPOT"


def _norm_tf(v: Any) -> str:
    return str(v or "").strip().upper()


def _match(p: Dict[str, Any], symbol: str, timeframe: str, direction: str, system_type: str, regime: Optional[str] = None, runtime_features: Optional[Dict[str, Any]] = None) -> bool:
    scope = p.get("scope") or {}
    fam = market_family(system_type, symbol)
    if str(scope.get("market_family") or "") != fam:
        return False
    if _norm_tf(scope.get("timeframe")) not in {"", "ALL", _norm_tf(timeframe)}:
        return False
    wanted_symbol = str(scope.get("symbol") or "ALL").upper().replace("/", "-")
    if wanted_symbol not in {"", "ALL", str(symbol or "").upper().replace("/", "-")}:
        return False
    wanted_direction = str(scope.get("direction") or "ALL").upper()
    d = str(direction or "").upper()
    if d == "COMPRA_SPOT": d = "LONG"
    if d == "VENTA_SPOT": d = "SHORT"
    if wanted_direction not in {"", "ALL", d}:
        return False
    wanted_regime = str(scope.get("regime") or "ALL").upper()
    if regime and wanted_regime not in {"", "ALL", str(regime).upper()}:
        return False
    features = runtime_features or {}
    for key in ("has_pullback", "has_sweep", "has_order_block"):
        wanted = str(scope.get(key) or "").upper()
        if not wanted:
            continue
        actual = str(features.get(key) or "NO").upper()
        if actual != wanted:
            return False
    return True


def _shadow_state(row: Dict[str, Any]) -> str:
    target = max(1, int(row.get("shadow_target") or 0) or 1)
    n = int(row.get("shadow_n") or 0)
    exp = _num(row.get("shadow_exp_r"))
    pf = _num(row.get("shadow_pf"))
    if n >= target:
        if exp is not None and exp > 0.10 and (pf is None or pf > 1.15):
            return "CONFIRMED"
        return "DIVERGED"
    if n >= max(3, int(math.ceil(target * 0.50))) and exp is not None and exp <= -0.25:
        return "EARLY_DIVERGENCE"
    if n > 0:
        return "OBSERVING"
    return "WAITING"


def _summary(p: Dict[str, Any], shadow_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    m = p.get("metrics") or {}; allm = m.get("all") or {}; val = m.get("validation") or {}
    key = str(p.get("candidate_key") or "")
    live = shadow_map.get(key) or {}
    out = {
        "candidate_key": key,
        "stage": p.get("stage"),
        "source_engine": p.get("source_engine"),
        "experiment": p.get("experiment"),
        "scope": p.get("scope") or {},
        "reason": p.get("reason"),
        "backtest_n": int(allm.get("resolved") or 0),
        "backtest_wr": _num(allm.get("win_rate_pct")),
        "backtest_exp_r": _num(allm.get("expectancy_r")),
        "backtest_pf": _num(allm.get("profit_factor")),
        "oos_n": int(val.get("resolved") or 0),
        "oos_wr": _num(val.get("win_rate_pct")),
        "oos_exp_r": _num(val.get("expectancy_r")),
        "oos_pf": _num(val.get("profit_factor")),
        "oos_dd_r": _num(val.get("max_drawdown_r")),
        "guardian_operational_replay": (
            val.get("guardian_operational_replay")
            or (p.get("meta") or {}).get("guardian_operational_replay")
            or {}
        ),
        "full_stack_profitability_certification": (
            (p.get("meta") or {}).get("full_stack_profitability_certification") or {}
        ),
        "shadow_target": int((p.get("meta") or {}).get("recommended_shadow_target") or 0),
        "shadow_n": int(live.get("resolved_n") or 0),
        "shadow_signals_n": int(live.get("signals_n") or 0),
        "shadow_exp_r": _num(live.get("expectancy_r")),
        "shadow_pf": _num(live.get("profit_factor")),
        "shadow_updated_at": live.get("updated_at"),
        "coverage_cell": (p.get("meta") or {}).get("coverage_cell") or {},
        "coverage_cell_id": (p.get("meta") or {}).get("coverage_cell_id"),
        "strategy_family": (p.get("meta") or {}).get("causal_strategy_family"),
        "finalist_rank": (p.get("meta") or {}).get("finalist_rank_selection_only"),
        "registry_retest": bool((p.get("meta") or {}).get("registry_retest")),
        "shadow_recycle": bool((p.get("meta") or {}).get("shadow_recycle")),
        "original_candidate_key": (p.get("meta") or {}).get("original_candidate_key"),
        "updated_at": p.get("updated_at"),
    }
    out["shadow_state"] = _shadow_state(out)
    out["recycle_required"] = out["shadow_state"] in {"DIVERGED", "EARLY_DIVERGENCE"}
    return out


def _latest_by_lineage(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        lineage = str(row.get("original_candidate_key") or row.get("candidate_key") or "")
        if not lineage:
            continue
        previous = latest.get(lineage)
        if previous is None or str(row.get("updated_at") or "") >= str(previous.get("updated_at") or ""):
            latest[lineage] = row
    return list(latest.values())


def _stage_priority(stage: Any) -> int:
    return {
        "SHADOW_READY_FAST": 60, "SHADOW_READY": 55,
        "VALIDATION_REQUIRED": 40, "VALIDATED_SINGLE_ASSET": 38,
        "OBSERVE": 25, "REJECTED_OOS": 10,
    }.get(str(stage or "").upper(), 20)


def _best_per_cell(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    scores: Dict[str, tuple] = {}
    for row in rows or []:
        cid = str(row.get("coverage_cell_id") or "")
        if not cid:
            continue
        # Prefer validated state, then OOS performance/sample. A retest can
        # replace its lineage first via _latest_by_lineage.
        # Current cell state must win over an older SHADOW_READY. RC1 exposed
        # a stale-count bug where an old validated lineage could keep a cell
        # green after the OOS Guard had replaced it with VALIDATION_REQUIRED.
        # ISO timestamps sort chronologically, then stage/OOS break ties.
        score = (
            str(row.get("updated_at") or ""),
            _stage_priority(row.get("stage")),
            float(row.get("oos_exp_r") if row.get("oos_exp_r") is not None else -999),
            float(row.get("oos_pf") if row.get("oos_pf") is not None else -999),
            int(row.get("oos_n") or 0),
            -int(row.get("finalist_rank") or 999),
        )
        if cid not in best or score > scores[cid]:
            best[cid] = row; scores[cid] = score
    return list(best.values())


def edge_prior(symbol: str, timeframe: str, direction: str, system_type: str, regime: Optional[str] = None, runtime_features: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bounded prior for ReviewTrader; cannot create direction by itself."""
    base = {
        "state": "NO_CAUSAL_EVIDENCE", "support_score": 0.0, "penalty_score": 0.0,
        "candidates": [], "authority": "EVIDENCE_PRIOR_ONLY", "recycle_required": False,
    }
    try:
        promotions, shadow = _load()
        smap = {str(x.get("candidate_key") or ""): x for x in shadow}
        matches = _latest_by_lineage([
            _summary(p, smap) for p in promotions
            if _match(p, symbol, timeframe, direction, system_type, regime, runtime_features=runtime_features)
        ])
        matches.sort(key=lambda x: (_stage_priority(x.get("stage")), float(x.get("oos_exp_r") or -999), int(x.get("oos_n") or 0)), reverse=True)
        base["candidates"] = matches[:6]
        positives = [x for x in matches if str(x.get("stage")) in _POSITIVE]
        negatives = [x for x in matches if str(x.get("stage")) == "REJECTED_OOS"]
        diverged = [x for x in positives if x.get("shadow_state") in {"DIVERGED", "EARLY_DIVERGENCE"}]
        confirmed = [x for x in positives if x.get("shadow_state") == "CONFIRMED"]
        pending = [x for x in positives if x.get("shadow_state") not in {"DIVERGED", "EARLY_DIVERGENCE", "CONFIRMED"}]

        if negatives:
            worst = min(negatives, key=lambda x: x.get("oos_exp_r") if x.get("oos_exp_r") is not None else 0.0)
            base.update(
                state="NEGATIVE_OOS",
                penalty_score=min(35.0, 15.0 + abs(float(worst.get("oos_exp_r") or 0.0))*20.0),
                best_negative=worst,
            )
        if diverged:
            worst_live = min(diverged, key=lambda x: x.get("shadow_exp_r") if x.get("shadow_exp_r") is not None else -999)
            base.update(
                state="SHADOW_DIVERGED",
                support_score=0.0,
                penalty_score=max(float(base.get("penalty_score") or 0.0), 24.0 if worst_live.get("shadow_state") == "DIVERGED" else 14.0),
                best_positive=worst_live,
                recycle_required=True,
                recycle_reason="Shadow/live no confirmó el edge histórico; volver a backtest/Validation.",
            )
            return base
        source = confirmed or pending
        if source:
            best = max(source, key=lambda x: (float(x.get("oos_exp_r") or -999), int(x.get("oos_n") or 0)))
            score = 72.0 if best.get("stage") == "SHADOW_READY" else 82.0
            score += min(10.0, max(0.0, float(best.get("oos_exp_r") or 0.0))*8.0)
            if best.get("shadow_state") == "CONFIRMED":
                score = min(96.0, score + 8.0)
                state = "OOS_PLUS_SHADOW"
            else:
                state = "OOS_VALIDATED"
            base.update(state=state, support_score=min(95.0, score), best_positive=best)
        return base
    except Exception as exc:
        base.update(state="UNAVAILABLE", error=str(exc)[:160])
        return base


def _bucket(rows: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    rows = _best_per_cell(rows)
    if not rows:
        return {
            "name": name, "state": "NO_EVIDENCE", "strategies": 0,
            "validated_strategies": 0, "oos_n": 0, "oos_wr_weighted": None,
            "oos_exp_r_weighted": None, "oos_total_r": None,
            "best": None, "cells": 0, "shadow_ready": 0,
            "shadow_observed": 0, "shadow_signals": 0, "shadow_resolved": 0,
        }
    ready = [r for r in rows if str(r.get("stage")) in _POSITIVE and not r.get("recycle_required")]
    validation = [r for r in rows if str(r.get("stage")) == "VALIDATION_REQUIRED"]
    observe = [r for r in rows if str(r.get("stage")) == "OBSERVE"]
    source = ready or validation or observe
    vals = [r for r in source if r.get("oos_exp_r") is not None and int(r.get("oos_n") or 0) > 0]
    denom = sum(int(r.get("oos_n") or 0) for r in vals)
    total_r = sum(float(r.get("oos_exp_r"))*int(r.get("oos_n") or 0) for r in vals)
    weighted = total_r / denom if denom else None
    wr_rows = [r for r in vals if r.get("oos_wr") is not None]
    wr_den = sum(int(r.get("oos_n") or 0) for r in wr_rows)
    wr_num = sum(float(r.get("oos_wr"))*int(r.get("oos_n") or 0) for r in wr_rows)
    wr_weighted = wr_num / wr_den if wr_den else None
    best = max(source, key=lambda r: (float(r.get("oos_exp_r") or -999), int(r.get("oos_n") or 0))) if source else None
    return {
        "name": name,
        "state": "VALIDATED_OOS_POSITIVE" if ready else "CANDIDATES_ONLY",
        "strategies": len(source),
        "validated_strategies": len(ready),
        "cells": len(rows),
        "oos_n": denom,
        "oos_wr_weighted": round(wr_weighted, 2) if wr_weighted is not None else None,
        "oos_exp_r_weighted": round(weighted, 4) if weighted is not None else None,
        "oos_total_r": round(total_r, 3) if denom else None,
        "best": best,
        "recycle_required": sum(1 for r in rows if r.get("recycle_required")),
        "shadow_ready": len(ready),
        "shadow_observed": sum(1 for r in ready if int(r.get("shadow_signals_n") or 0) > 0),
        "shadow_signals": sum(int(r.get("shadow_signals_n") or 0) for r in ready),
        "shadow_resolved": sum(int(r.get("shadow_n") or 0) for r in ready),
        "note": "Backtest/OOS y live se muestran separados; no se suman como una sola muestra.",
    }


def profitability_snapshot(force: bool = False) -> Dict[str, Any]:
    try:
        promotions, shadow = _load(force=force)
        smap = {str(x.get("candidate_key") or ""): x for x in shadow}
        all_rows = [_summary(p, smap) for p in promotions]
        rows = _latest_by_lineage(all_rows)
        contract_rows = []
        for row in rows:
            canonical = _canonical_cell_key(row)
            if not canonical:
                continue
            item = dict(row)
            item["canonical_cell_key"] = canonical
            item["coverage_cell_id"] = canonical
            contract_rows.append(item)
        cell_rows = _best_per_cell(contract_rows)
        cells = {str(r.get("coverage_cell_id") or "").upper() for r in cell_rows if r.get("coverage_cell_id")}
        validated_cells = [r for r in cell_rows if str(r.get("stage")) in _POSITIVE and not r.get("recycle_required")]
        # RC3 distingue dos conceptos para no mostrar dos verdades distintas:
        # - vigente: representante actual de la celda (puede haber degradado/retest);
        # - evidencia final positiva: existe al menos un linaje OOS+ vigente en
        #   Research para esa misma celda, aunque todavía no sea SHADOW_READY.
        oos_positive_cells = [
            r for r in cell_rows
            if r.get("oos_exp_r") is not None and float(r.get("oos_exp_r")) > 0
            and r.get("oos_pf") is not None and float(r.get("oos_pf")) > 1.0
        ]
        oos_positive_evidence_cell_ids = {
            str(r.get("coverage_cell_id") or "").upper()
            for r in contract_rows
            if r.get("coverage_cell_id")
            and str(r.get("stage") or "").upper() != "REJECTED_OOS"
            and r.get("oos_exp_r") is not None and float(r.get("oos_exp_r")) > 0
            and (
                r.get("oos_pf") is None
                or float(r.get("oos_pf")) > 1.0
            )
        }
        spot = [r for r in contract_rows if str((r.get("scope") or {}).get("market_family") or "") in {"CRYPTO_SPOT","PAXG_USDT","PAXG_BTC"}]
        fut = [r for r in contract_rows if str((r.get("scope") or {}).get("market_family") or "") == "CRYPTO_FUTURES"]
        by_market = {}
        for fam in ("CRYPTO_SPOT","PAXG_USDT","PAXG_BTC"):
            by_market[fam] = _bucket([r for r in spot if str((r.get("scope") or {}).get("market_family") or "") == fam], fam)
        by_symbol = {}
        for sym in ("BTC-USDT","ETH-USDT","SOL-USDT","XRP-USDT","ADA-USDT","LINK-USDT","BNB-USDT"):
            by_symbol[sym] = _bucket([r for r in fut if str((r.get("scope") or {}).get("symbol") or "").upper() == sym], sym)
        by_tf = {}
        for tf in ("30M","1H","2H","4H","12H","1D"):
            by_tf[tf] = _bucket([r for r in fut if _norm_tf((r.get("scope") or {}).get("timeframe")) == tf], tf)
        matrix = []
        for r in sorted(cell_rows, key=lambda x: str(x.get("coverage_cell_id") or "")):
            scope = r.get("scope") or {}
            matrix.append({
                "candidate_key": r.get("candidate_key"),
                "cell": r.get("canonical_cell_key") or r.get("coverage_cell_id"),
                "market_family": scope.get("market_family"),
                "symbol": scope.get("symbol"),
                "timeframe": scope.get("timeframe"),
                "stage": r.get("stage"),
                "strategy_family": r.get("strategy_family"),
                "oos_n": r.get("oos_n"), "oos_wr": r.get("oos_wr"),
                "oos_exp_r": r.get("oos_exp_r"), "oos_pf": r.get("oos_pf"),
                "guardian_operational_replay": r.get("guardian_operational_replay") or {},
                "full_stack_profitability_certification": r.get("full_stack_profitability_certification") or {},
                "shadow_signals_n": r.get("shadow_signals_n"), "shadow_n": r.get("shadow_n"),
                "shadow_exp_r": r.get("shadow_exp_r"), "shadow_pf": r.get("shadow_pf"),
                "shadow_target": r.get("shadow_target"), "shadow_state": r.get("shadow_state"),
                "recycle_required": r.get("recycle_required"),
            })
        return {
            "version": "V1_RC4_RESEARCH_EVIDENCE_FUSION_V5",
            "authority": "EVIDENCE_PRIOR_ONLY",
            "coverage_cells": len(cells),
            "coverage_target": _COVERAGE_TARGET,
            "coverage_complete": len(cells) >= _COVERAGE_TARGET,
            "validated_cells": len(validated_cells),
            "oos_positive_cells": len(oos_positive_cells),
            "oos_positive_evidence_cells": len(oos_positive_evidence_cell_ids),
            "oos_positive_semantics": {
                "current_representative": len(oos_positive_cells),
                "research_evidence_any_current_lineage": len(oos_positive_evidence_cell_ids),
            },
            "searching_cells": max(0, _COVERAGE_TARGET - len(validated_cells)),
            "recycle_required_cells": sum(1 for r in cell_rows if r.get("recycle_required")),
            "spot": _bucket(spot, "SPOT"),
            "futures_official": _bucket([r for r in fut if str(r.get("stage")) in _POSITIVE], "FUTURES_VALIDATED"),
            "futures_evaluation": _bucket([r for r in fut if str(r.get("stage")) != "REJECTED_OOS"], "FUTURES_EVALUATION"),
            "spot_by_market": by_market,
            "futures_by_symbol": by_symbol,
            "futures_by_timeframe": by_tf,
            "coverage_matrix": matrix,
            "shadow_ready_cells": len(validated_cells),
            "shadow_live_candidates": sum(1 for r in validated_cells if int(r.get("shadow_signals_n") or 0) > 0),
            "shadow_live_signals": sum(int(r.get("shadow_signals_n") or 0) for r in validated_cells),
            "shadow_live_resolved": sum(int(r.get("shadow_n") or 0) for r in validated_cells),
            "causal_candidates": len(contract_rows),
        }
    except Exception as exc:
        return {
            "version": "V1_RC4_RESEARCH_EVIDENCE_FUSION_V5", "authority": "EVIDENCE_PRIOR_ONLY",
            "state": "UNAVAILABLE", "error": str(exc)[:180], "coverage_cells": 0,
            "coverage_target": _COVERAGE_TARGET, "coverage_complete": False,
            "validated_cells": 0, "oos_positive_cells": 0, "searching_cells": _COVERAGE_TARGET,
        }
