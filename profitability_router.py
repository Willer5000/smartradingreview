from __future__ import annotations

"""Profitability Router for SmartradingReview.

Safety answers "is this trade technically well built?".
This router answers "has this *type* of trade shown enough evidence to deserve
extra trust or an early veto?".

Policy:
- Positive research NEVER creates/promotes a trade by itself.
- Negative OOS evidence may veto a new executable signal earlier.
- SHADOW_READY/positive Shadow is advisory/supportive until governance promotes.
- Fail-open on data/service errors so Research can never break the trading app.
"""

import os
import threading
import time
from typing import Any, Dict, List

import requests

try:
    from supabase_egress_guard import allows as _egress_allows, track_http_response as _track_http_response, mark_restricted as _mark_restricted
except Exception:
    _egress_allows = lambda priority='optional': True
    _track_http_response = lambda response: None
    _mark_restricted = lambda reason='HTTP_402': None

from research_shadow_bridge import runtime_research_features, matches_research_scope

_SESSION = requests.Session()
_LOCK = threading.Lock()
_CACHE = {"ts": 0.0, "promotions": [], "shadow": []}
_TTL = max(60, int(os.getenv("PROFITABILITY_ROUTER_CACHE_SECONDS", "120") or 120))
_NEGATIVE_VETO = str(os.getenv("PROFITABILITY_ROUTER_NEGATIVE_VETO", "1")).strip().lower() not in {"0", "false", "no", "off"}


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
        raise RuntimeError("Profitability Router: Supabase no configurado")
    headers = {"apikey": key, "Accept": "application/json"}
    if key.count(".") == 2:
        headers["Authorization"] = f"Bearer {key}"
    return url, headers


def _num(value, default=None):
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


def _load_evidence(force: bool = False):
    now = time.monotonic()
    with _LOCK:
        if (not force) and _CACHE["promotions"] and (now - _CACHE["ts"]) < _TTL:
            return list(_CACHE["promotions"]), list(_CACHE["shadow"])

    if not _egress_allows('diagnostic'):
        with _LOCK:
            return list(_CACHE["promotions"]), list(_CACHE["shadow"])

    url, headers = _headers()
    pr = _SESSION.get(
        f"{url}/rest/v1/research_promotions_v1",
        params={
            "select": "candidate_key,source_engine,experiment,stage,reason,scope,metrics,meta,research_version,updated_at",
            "stage": "in.(REJECTED_OOS,SHADOW_READY,SHADOW_READY_FAST,VALIDATED_SINGLE_ASSET,VALIDATION_REQUIRED)",
            "order": "updated_at.desc",
            "limit": "600",
        },
        headers=headers,
        timeout=6,
    )
    _track_http_response(pr)
    if int(pr.status_code or 0) == 402:
        _mark_restricted('HTTP_402_PROFITABILITY_ROUTER')
    pr.raise_for_status()
    promotions = pr.json() if isinstance(pr.json(), list) else []
    promotions = [
        p for p in promotions
        if (p.get("meta") or {}).get("is_current") is not False
        and str(p.get("stage") or "") != "STALE"
    ]

    shadow = []
    try:
        sr = _SESSION.get(
            f"{url}/rest/v1/research_shadow_live_metrics_v1",
            params={"select": "*", "order": "updated_at.desc", "limit": "300"},
            headers=headers,
            timeout=6,
        )
        _track_http_response(sr)
        if int(sr.status_code or 0) == 402:
            _mark_restricted('HTTP_402_PROFITABILITY_ROUTER_SHADOW')
        sr.raise_for_status()
        raw = sr.json()
        if isinstance(raw, list):
            shadow = raw
    except Exception:
        shadow = []

    with _LOCK:
        _CACHE.update(ts=now, promotions=list(promotions), shadow=list(shadow))
    return promotions, shadow


def _shadow_by_key(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        key = str(row.get("candidate_key") or "")
        if key and key not in out:
            out[key] = row
    return out




def _negative_veto_eligible(candidate: Dict[str, Any]) -> bool:
    """Hard veto only from strategy hypotheses built to represent a trade setup.

    Risk/trader/component diagnostics are valuable evidence, but a single
    diagnostic slice must never cancel a production signal.  Commit H keeps
    the first live authority intentionally narrow: only continuously generated
    Strategy Factory or structured AI strategy proposals can become a hard
    negative edge veto after temporal Holdout failure.
    """
    engine = str(candidate.get("source_engine") or "").strip().lower()
    experiment = str(candidate.get("experiment") or "").strip().upper()
    if experiment in {"CAUSAL_COVERAGE_STRATEGY", "CAUSAL_REGISTRY_RETEST", "CAUSAL_SHADOW_RECYCLE"}:
        return engine in {"execution", "risk", "strategy", "traders"}
    if engine != "strategy":
        return False
    return experiment in {"FACTORY_STRATEGY", "AI_STRATEGY_PROPOSAL"}


def _negative_veto_min_oos(scope: Dict[str, Any]) -> int:
    tf = str((scope or {}).get("timeframe") or "").upper()
    return {"5M":10,"15M":8,"30M":6,"1H":5,"2H":4,"4H":4,"12H":3,"1D":3,"1W":2}.get(tf, 8)

def _evidence_summary(candidate: Dict[str, Any], shadow: Dict[str, Any] | None = None) -> Dict[str, Any]:
    metrics = candidate.get("metrics") or {}
    val = metrics.get("validation") or {}
    allm = metrics.get("all") or {}
    meta = candidate.get("meta") or {}
    return {
        "candidate_key": candidate.get("candidate_key"),
        "source_engine": candidate.get("source_engine"),
        "experiment": candidate.get("experiment"),
        "stage": candidate.get("stage"),
        "reason": candidate.get("reason"),
        "scope": candidate.get("scope") or {},
        "discovery_n": int(allm.get("resolved") or 0),
        "discovery_expectancy_r": _num(allm.get("expectancy_r")),
        "holdout_n": int(val.get("resolved") or 0),
        "holdout_expectancy_r": _num(val.get("expectancy_r")),
        "holdout_pf": _num(val.get("profit_factor")),
        "net_evidence_pct": _num(allm.get("net_evidence_pct"), 0.0),
        "shadow_target": int(meta.get("recommended_shadow_target") or 0),
        "shadow_resolved": int((shadow or {}).get("resolved_n") or 0),
        "shadow_expectancy_r": _num((shadow or {}).get("expectancy_r")),
        "shadow_pf": _num((shadow or {}).get("profit_factor")),
        "shadow_updated_at": (shadow or {}).get("updated_at"),
        "recent8_n": int((shadow or {}).get("recent8_n") or 0),
        "recent8_expectancy_r": _num((shadow or {}).get("recent8_expectancy_r")),
        "recent8_profit_factor": _num((shadow or {}).get("recent8_profit_factor")),
        "recent8_trade_sharpe": _num((shadow or {}).get("recent8_trade_sharpe")),
        "previous8_n": int((shadow or {}).get("previous8_n") or 0),
        "previous8_expectancy_r": _num((shadow or {}).get("previous8_expectancy_r")),
        "previous8_trade_sharpe": _num((shadow or {}).get("previous8_trade_sharpe")),
        "current_loss_streak": int((shadow or {}).get("current_loss_streak") or 0),
        "champion_degraded": bool(meta.get("champion_degraded")),
        "alpha_decay_health": meta.get("alpha_decay_health") or {},
        "factory_family": meta.get("factory_family"),
        "factory_strategy_id": meta.get("factory_strategy_id"),
    }


def _shadow_confirmation_state(summary: Dict[str, Any]) -> str:
    if summary.get("champion_degraded"):
        return "ALPHA_DECAY"
    loss_streak=int(summary.get("current_loss_streak") or 0)
    recent_n=int(summary.get("recent8_n") or 0)
    recent_exp=summary.get("recent8_expectancy_r")
    recent_pf=summary.get("recent8_profit_factor")
    recent_sharpe=summary.get("recent8_trade_sharpe")
    prev_n=int(summary.get("previous8_n") or 0)
    prev_exp=summary.get("previous8_expectancy_r")
    prev_sharpe=summary.get("previous8_trade_sharpe")
    base_exp=summary.get("holdout_expectancy_r")
    if loss_streak >= 8:
        return "ALPHA_DECAY"
    if recent_n >= 8 and recent_exp is not None and float(recent_exp) < 0:
        recent_bad=((recent_pf is not None and float(recent_pf)<0.90) or (recent_sharpe is not None and float(recent_sharpe)<0.0))
        trajectory_bad=(prev_n>=6 and ((recent_sharpe is not None and prev_sharpe is not None and float(recent_sharpe)<=float(prev_sharpe)-0.25) or (prev_exp is not None and float(recent_exp)<=float(prev_exp)-0.15)))
        baseline_bad=(base_exp is not None and float(base_exp)>0 and float(recent_exp)<=min(0.0,float(base_exp)*0.25))
        if recent_bad and (trajectory_bad or baseline_bad):
            return "ALPHA_DECAY"
    target=max(1,int(summary.get("shadow_target") or 0) or 1)
    n=int(summary.get("shadow_resolved") or 0)
    exp=summary.get("shadow_expectancy_r")
    pf=summary.get("shadow_pf")
    if n>=target:
        if exp is not None and float(exp)>0.10 and (pf is None or float(pf)>1.15):
            return "CONFIRMED"
        return "DIVERGED"
    if n>=max(3,(target+1)//2) and exp is not None and float(exp)<=-0.25:
        return "EARLY_DIVERGENCE"
    if n>0:
        return "OBSERVING"
    return "WAITING"


def evaluate_profitability_route(result: Dict[str, Any], system_type: str = "futures") -> Dict[str, Any]:
    """Read-only edge decision. Never creates LONG/SHORT or edits levels."""
    base = {
        "version": "PROFITABILITY_ROUTER_J_V2",
        "state": "UNKNOWN",
        "block_new_signal": False,
        "negative_veto_enabled": _NEGATIVE_VETO,
        "matched": 0,
        "negative_matches": [],
        "positive_matches": [],
        "shadow_confirmed_matches": [],
        "reason": "Sin evidencia Research reproducible para este contexto.",
        "authority": "NEGATIVE_VETO_ONLY",
    }
    if not isinstance(result, dict):
        return base

    try:
        feat = runtime_research_features(result, system_type)
        base["runtime_features"] = {
            k: v for k, v in feat.items()
            if k not in {"strategies"}
        }
        promotions, shadow_rows = _load_evidence()
        shadow_map = _shadow_by_key(shadow_rows)
        matched = [p for p in promotions if matches_research_scope(p.get("scope") or {}, feat)]
        base["matched"] = len(matched)

        negatives = []
        positives = []
        confirmed = []
        diverged = []
        for candidate in matched:
            key = str(candidate.get("candidate_key") or "")
            summary = _evidence_summary(candidate, shadow_map.get(key))
            summary["shadow_state"]=_shadow_confirmation_state(summary)
            stage = str(candidate.get("stage") or "").upper()
            if stage == "REJECTED_OOS":
                if (
                    _negative_veto_eligible(candidate)
                    and summary["holdout_n"] >= _negative_veto_min_oos(summary.get("scope") or {})
                    and summary["holdout_expectancy_r"] is not None
                    and summary["holdout_expectancy_r"] <= -0.15
                ):
                    summary["veto_eligible"] = True
                    negatives.append(summary)
            elif stage in {"SHADOW_READY", "SHADOW_READY_FAST"}:
                if summary.get("shadow_state") in {"DIVERGED","EARLY_DIVERGENCE","ALPHA_DECAY"}:
                    diverged.append(summary)
                else:
                    positives.append(summary)
                    if summary.get("shadow_state") == "CONFIRMED":
                        confirmed.append(summary)

        # Keep payload compact for UI/LLM.
        base["negative_matches"] = negatives[:3]
        base["positive_matches"] = positives[:3]
        base["shadow_confirmed_matches"] = confirmed[:3]
        base["shadow_diverged_matches"] = diverged[:3]

        if diverged:
            worst_live = sorted(diverged, key=lambda x: x.get("shadow_expectancy_r") if x.get("shadow_expectancy_r") is not None else -999)[0]
            hard = str(worst_live.get("shadow_state")) in {"DIVERGED","ALPHA_DECAY"}
            base.update(
                state=("ALPHA_DECAY_VETO" if worst_live.get("shadow_state") == "ALPHA_DECAY" else "SHADOW_DIVERGED_RETEST"),
                block_new_signal=bool(hard),
                reason=(
                    ("Alpha decay detectado en la secuencia live del Champion; se bloquea nueva ejecución de ese edge y vuelve a Research/Shadow." if worst_live.get("shadow_state") == "ALPHA_DECAY" else "El edge histórico no está siendo confirmado por Shadow/live; la estrategia vuelve a rebacktest/Validation antes de recuperar apoyo.")
                ),
                best_diverged=worst_live,
                recycle_required=True,
            )
        elif negatives and _NEGATIVE_VETO:
            worst = sorted(negatives, key=lambda x: x.get("holdout_expectancy_r") or 0.0)[0]
            base.update(
                state="NEGATIVE_EDGE_VETO",
                block_new_signal=True,
                reason=(
                    "El mismo contexto tiene Holdout temporal negativo "
                    f"({worst.get('holdout_expectancy_r'):.3f}R, N={worst.get('holdout_n')})."
                ),
            )
        elif confirmed:
            best = sorted(confirmed, key=lambda x: x.get("shadow_expectancy_r") or -999, reverse=True)[0]
            base.update(
                state="EDGE_CONFIRMED_SHADOW",
                reason=(
                    "Existe edge positivo validado y confirmado en Shadow; "
                    "apoya la señal pero no reemplaza Safety ni Governance."
                ),
                best_positive=best,
            )
        elif positives:
            best = sorted(positives, key=lambda x: (x.get("holdout_expectancy_r") or -999, x.get("holdout_n") or 0), reverse=True)[0]
            if str(best.get("experiment") or "").upper() in {"CAUSAL_COVERAGE_STRATEGY","CAUSAL_REGISTRY_RETEST","CAUSAL_SHADOW_RECYCLE"}:
                state = "HISTORICAL_EDGE_VALIDATED"
                reason = (
                    "Replay causal + OOS muestran edge positivo. Se usa como prior de rentabilidad; "
                    "Shadow live debe confirmar vigencia antes de Canary/Active."
                )
            else:
                state = "SHADOW_READY"
                reason = "Existe candidato prometedor, pero todavía necesita completar Shadow live."
            base.update(state=state, reason=reason, best_positive=best)
        elif matched:
            base.update(
                state="OBSERVE",
                reason="Hay evidencia relacionada, todavía sin edge suficiente para apoyo o veto.",
            )
        return base
    except Exception as exc:
        base.update(state="UNAVAILABLE", reason=f"Research no disponible: {str(exc)[:160]}")
        return base
