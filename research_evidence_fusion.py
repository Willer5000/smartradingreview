from __future__ import annotations

"""Commit J — fusiona evidencia causal Research + Shadow sin mezclar muestras.

Backtest/OOS is a historical prior. Shadow/live is current confirmation.
Neither source is relabeled as the other and positive evidence never creates a
trade on its own. The module is fail-open and compact for the 512 MB main app.
"""

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
            "limit": "1000",
        },
        headers=h,
        timeout=7,
    )
    r.raise_for_status()
    promotions = r.json() if isinstance(r.json(), list) else []
    promotions = [
        p for p in promotions
        if str(p.get("experiment") or "") in {"CAUSAL_COVERAGE_STRATEGY","CAUSAL_REGISTRY_RETEST"}
        and str(p.get("stage") or "") in _VISIBLE
        and (p.get("meta") or {}).get("is_current") is not False
    ]
    shadow: List[Dict[str, Any]] = []
    try:
        sr = _SESSION.get(
            f"{url}/rest/v1/research_shadow_live_metrics_v1",
            params={"select": "*", "order": "updated_at.desc", "limit": "300"},
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


def _summary(p: Dict[str, Any], shadow_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    m = p.get("metrics") or {}; allm = m.get("all") or {}; val = m.get("validation") or {}
    key = str(p.get("candidate_key") or "")
    live = shadow_map.get(key) or {}
    return {
        "candidate_key": key,
        "stage": p.get("stage"),
        "source_engine": p.get("source_engine"),
        "experiment": p.get("experiment"),
        "scope": p.get("scope") or {},
        "reason": p.get("reason"),
        "backtest_n": int(allm.get("resolved") or 0),
        "backtest_exp_r": _num(allm.get("expectancy_r")),
        "backtest_pf": _num(allm.get("profit_factor")),
        "oos_n": int(val.get("resolved") or 0),
        "oos_wr": _num(val.get("win_rate_pct")),
        "oos_exp_r": _num(val.get("expectancy_r")),
        "oos_pf": _num(val.get("profit_factor")),
        "oos_dd_r": _num(val.get("max_drawdown_r")),
        "shadow_target": int((p.get("meta") or {}).get("recommended_shadow_target") or 0),
        "shadow_n": int(live.get("resolved_n") or 0),
        "shadow_exp_r": _num(live.get("expectancy_r")),
        "shadow_pf": _num(live.get("profit_factor")),
        "coverage_cell": (p.get("meta") or {}).get("coverage_cell") or {},
        "coverage_cell_id": (p.get("meta") or {}).get("coverage_cell_id"),
        "strategy_family": (p.get("meta") or {}).get("causal_strategy_family"),
        "registry_retest": bool((p.get("meta") or {}).get("registry_retest")),
        "original_candidate_key": (p.get("meta") or {}).get("original_candidate_key"),
        "updated_at": p.get("updated_at"),
    }


def _latest_by_lineage(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Avoid counting a rolling registry retest as a second independent sample."""
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        lineage = str(row.get("original_candidate_key") or row.get("candidate_key") or "")
        if not lineage:
            continue
        previous = latest.get(lineage)
        if previous is None or str(row.get("updated_at") or "") >= str(previous.get("updated_at") or ""):
            latest[lineage] = row
    return list(latest.values())


def edge_prior(symbol: str, timeframe: str, direction: str, system_type: str, regime: Optional[str] = None, runtime_features: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bounded prior for ReviewTrader; cannot create direction by itself."""
    base = {"state": "NO_CAUSAL_EVIDENCE", "support_score": 0.0, "penalty_score": 0.0, "candidates": [], "authority": "EVIDENCE_PRIOR_ONLY"}
    try:
        promotions, shadow = _load()
        smap = {str(x.get("candidate_key") or ""): x for x in shadow}
        matches = _latest_by_lineage([_summary(p, smap) for p in promotions if _match(p, symbol, timeframe, direction, system_type, regime, runtime_features=runtime_features)])
        base["candidates"] = matches[:4]
        positives = [x for x in matches if str(x.get("stage")) in _POSITIVE]
        negatives = [x for x in matches if str(x.get("stage")) == "REJECTED_OOS"]
        if negatives:
            worst = min(negatives, key=lambda x: x.get("oos_exp_r") if x.get("oos_exp_r") is not None else 0.0)
            base.update(state="NEGATIVE_OOS", penalty_score=min(35.0, 15.0 + abs(float(worst.get("oos_exp_r") or 0.0))*20.0), best_negative=worst)
        if positives:
            best = max(positives, key=lambda x: (float(x.get("oos_exp_r") or -999), int(x.get("oos_n") or 0)))
            score = 72.0 if best.get("stage") == "SHADOW_READY" else 82.0
            score += min(10.0, max(0.0, float(best.get("oos_exp_r") or 0.0))*8.0)
            if int(best.get("shadow_n") or 0) >= max(1, int(best.get("shadow_target") or 999)) and float(best.get("shadow_exp_r") or -999) > 0:
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
    if not rows:
        return {"name": name, "state": "NO_EVIDENCE", "strategies": 0, "oos_n": 0, "oos_exp_r_weighted": None, "best": None}
    ready = [r for r in rows if str(r.get("stage")) in _POSITIVE]
    validation = [r for r in rows if str(r.get("stage")) == "VALIDATION_REQUIRED"]
    observe = [r for r in rows if str(r.get("stage")) == "OBSERVE"]
    source = ready or validation or observe
    weights = [max(0, int(r.get("oos_n") or 0)) for r in source if r.get("oos_exp_r") is not None]
    vals = [r for r in source if r.get("oos_exp_r") is not None]
    denom = sum(max(0, int(r.get("oos_n") or 0)) for r in vals)
    weighted = (sum(float(r.get("oos_exp_r"))*max(0,int(r.get("oos_n") or 0)) for r in vals)/denom) if denom else None
    best = max(source, key=lambda r: (float(r.get("oos_exp_r") or -999), int(r.get("oos_n") or 0))) if source else None
    return {
        "name": name,
        "state": "VALIDATED_OOS_POSITIVE" if ready else "CANDIDATES_ONLY",
        "strategies": len(source),
        "validated_strategies": len(ready),
        "oos_n": sum(int(r.get("oos_n") or 0) for r in source),
        "oos_exp_r_weighted": round(weighted, 4) if weighted is not None else None,
        "best": best,
        "note": "Backtest/OOS y live se muestran separados; no se suman como una sola muestra.",
    }


def profitability_snapshot(force: bool = False) -> Dict[str, Any]:
    try:
        promotions, shadow = _load(force=force)
        smap = {str(x.get("candidate_key") or ""): x for x in shadow}
        all_rows = [_summary(p, smap) for p in promotions]
        cells = {
            str(r.get("coverage_cell_id") or "|").upper()
            for r in all_rows
            if r.get("coverage_cell") and str(r.get("experiment") or "") == "CAUSAL_COVERAGE_STRATEGY"
        }
        cells.discard("|")
        rows = _latest_by_lineage(all_rows)
        spot = [r for r in rows if str((r.get("scope") or {}).get("market_family") or "") in {"CRYPTO_SPOT","PAXG_USDT","PAXG_BTC"}]
        fut = [r for r in rows if str((r.get("scope") or {}).get("market_family") or "") == "CRYPTO_FUTURES"]
        by_market = {}
        for fam in ("CRYPTO_SPOT","PAXG_USDT","PAXG_BTC"):
            by_market[fam] = _bucket([r for r in spot if str((r.get("scope") or {}).get("market_family") or "") == fam], fam)
        return {
            "version": "J_RESEARCH_EVIDENCE_FUSION_V1",
            "authority": "EVIDENCE_PRIOR_ONLY",
            "coverage_cells": len(cells),
            "coverage_target": 18,
            "coverage_complete": len(cells) >= 18,
            "spot": _bucket(spot, "SPOT"),
            "futures_official": _bucket([r for r in fut if str(r.get("stage")) in _POSITIVE], "FUTURES_VALIDATED"),
            "futures_evaluation": _bucket([r for r in fut if str(r.get("stage")) != "REJECTED_OOS"], "FUTURES_EVALUATION"),
            "spot_by_market": by_market,
            "shadow_live_candidates": sum(1 for r in rows if int(r.get("shadow_n") or 0) > 0),
            "causal_candidates": len(rows),
        }
    except Exception as exc:
        return {"version": "J_RESEARCH_EVIDENCE_FUSION_V1", "authority": "EVIDENCE_PRIOR_ONLY", "state": "UNAVAILABLE", "error": str(exc)[:180], "coverage_cells": 0, "coverage_target": 18, "coverage_complete": False}
