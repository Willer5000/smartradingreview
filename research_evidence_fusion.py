from __future__ import annotations

"""RC9.7 — profitability evidence fusion for the 60-cell active Research contract.

Rules:
- causal OOS is a historical prior, never a live trade;
- Shadow/live is current confirmation, never merged into historical N;
- a positive OOS candidate may support an already-existing setup;
- negative OOS or materially diverged Shadow can protect/block;
- every active Research market×symbol×TF×action cell is tracked separately; group priors never become local symbol authority.
"""

import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from supabase_egress_guard import allows as _egress_allows, track_http_response as _track_http_response, mark_restricted as _mark_restricted
except Exception:
    _egress_allows = lambda priority='optional': True
    _track_http_response = lambda response: None
    _mark_restricted = lambda reason='HTTP_402': None

try:
    from research_strategy_card import build_strategy_card as _build_strategy_card
except Exception:
    _build_strategy_card = None

_SESSION = requests.Session()
_LOCK = threading.Lock()
_CACHE = {"ts": 0.0, "promotions": [], "shadow": [], "watermark": None}
_TTL = max(300, int(os.getenv("RESEARCH_EVIDENCE_CACHE_SECONDS", "900") or 900))
_POSITIVE = {"SHADOW_READY", "SHADOW_READY_FAST"}
_VISIBLE = _POSITIVE | {"OBSERVE", "VALIDATION_REQUIRED", "REJECTED_OOS", "VALIDATED_SINGLE_ASSET"}
_EXPERIMENTS = {"CAUSAL_COVERAGE_STRATEGY", "CAUSAL_REGISTRY_RETEST", "CAUSAL_SHADOW_RECYCLE"}
_COVERAGE_TARGET = 60
_RESEARCH_VERSION_PREFIX = "RFV1_15_RC9_7_CONTINGENCY_COLDSTART_60CELL"
_FUTURES_RESEARCH_TFS = {
    "BTC-USDT": ("30M","1H","2H","4H","12H","1D"),
    "XRP-USDT": ("30M","1H","2H","4H","12H"),
    "LINK-USDT": ("30M","1H","2H","4H"),
    "SUI-USDT": ("30M","1H","2H"),
}
_FUTURES_SYMBOLS = tuple(_FUTURES_RESEARCH_TFS)
_FUTURES_TFS = ("30M","1H","2H","4H","12H","1D")
_SPOT_SYMBOLS = ("BTC-USDT","PAXG-USDT","PAXG-BTC")
_SPOT_TFS = ("4H","12H","1D","1W")


def _scope_action(scope: Dict[str, Any]) -> str:
    fam=str((scope or {}).get("market_family") or "").upper()
    action=str((scope or {}).get("action") or "").upper()
    direction=str((scope or {}).get("direction") or "").upper()
    if action:
        return action
    if fam == "CRYPTO_FUTURES":
        return direction if direction in {"LONG","SHORT"} else ""
    if direction == "LONG":
        return "COMPRA_SPOT"
    if direction == "SHORT":
        return "VENTA_SPOT"
    return ""


def _canonical_cell_key(row: Dict[str, Any]) -> Optional[str]:
    """Return one of the 60 active Research action cells, otherwise None."""
    scope = row.get("scope") or {}
    fam = str(scope.get("market_family") or "")
    sym = str(scope.get("symbol") or "").upper().replace("/", "-")
    tf = _norm_tf(scope.get("timeframe"))
    action=_scope_action(scope)
    if fam == "CRYPTO_FUTURES":
        if action not in {"LONG","SHORT"} or sym not in _FUTURES_SYMBOLS:
            return None
        if tf in _FUTURES_RESEARCH_TFS.get(sym, ()):
            return f"FUTURES|{sym}|{tf}|{action}"
        return None
    if fam in {"CRYPTO_SPOT","PAXG_USDT","PAXG_BTC"}:
        if action in {"COMPRA_SPOT","VENTA_SPOT"} and sym in _SPOT_SYMBOLS and tf in _SPOT_TFS:
            return f"SPOT|{sym}|{tf}|{action}"
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


def _snapshot_as_promotion(c: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical Champion -> legacy promotion shape used by fusion math."""
    evidence=c.get('evidence') or {}
    validation=dict(evidence.get('validation') or {})
    validation.update({
        'resolved':int(c.get('oos_n') or validation.get('resolved') or 0),
        'win_rate_pct':c.get('oos_wr_pct') if c.get('oos_wr_pct') is not None else validation.get('win_rate_pct'),
        'expectancy_r':c.get('oos_expectancy_r') if c.get('oos_expectancy_r') is not None else validation.get('expectancy_r'),
        'profit_factor':c.get('oos_profit_factor') if c.get('oos_profit_factor') is not None else validation.get('profit_factor'),
        'max_drawdown_r':c.get('oos_max_drawdown_r') if c.get('oos_max_drawdown_r') is not None else validation.get('max_drawdown_r'),
    })
    metrics={
        'all':evidence.get('all') or {},
        'validation':validation,
        'walk_forward':evidence.get('walk_forward') or {},
    }
    scope={
        'market_family':c.get('market_family'),'symbol':c.get('symbol'),'timeframe':c.get('timeframe'),
        'direction':c.get('direction') or 'ALL','action':c.get('action') or ('LONG' if str(c.get('system_type') or '').upper()=='FUTURES' and str(c.get('direction') or '').upper()=='LONG' else 'SHORT' if str(c.get('system_type') or '').upper()=='FUTURES' and str(c.get('direction') or '').upper()=='SHORT' else 'COMPRA_SPOT' if str(c.get('direction') or '').upper()=='LONG' else 'VENTA_SPOT' if str(c.get('direction') or '').upper()=='SHORT' else 'ALL'),'regime':c.get('regime') or 'ALL',
    }
    alpha_detail=dict(c.get('alpha_detail') or {})
    alpha_detail['state']=c.get('alpha_state') or alpha_detail.get('state') or 'HEALTHY'
    meta={
        'causal_strategy':True,'causal_candle_replay':True,'is_current':True,
        'coverage_cell_id':c.get('cell_key'),'causal_strategy_id':c.get('strategy_id'),
        'causal_strategy_family':c.get('strategy_family'),'causal_strategy_spec':c.get('strategy_spec') or {},
        'strategy_card':c.get('strategy_card') or {},'champion_role':'INCUMBENT',
        'champion_lineage_key':c.get('candidate_key'),'champion_since':c.get('champion_since'),
        'recommended_shadow_target':int(c.get('shadow_target') or 0),'recommended_canary_target':int(c.get('canary_target') or 0),
        'runtime_trackable':bool(c.get('runtime_trackable',True)),'alpha_decay_health':alpha_detail,
        'guardian_operational_replay':evidence.get('guardian_operational_replay') or {},
        'full_stack_profitability_certification':evidence.get('full_stack_profitability_certification') or {},
        'walk_forward_positive_ratio':evidence.get('walk_forward_positive_ratio'),
    }
    return {
        'candidate_key':c.get('candidate_key'),'source_engine':c.get('source_engine'),'experiment':c.get('experiment'),
        'stage':'SHADOW_READY','reason':'Champion canónico persistente','scope':scope,'metrics':metrics,'meta':meta,
        'research_version':c.get('research_version'),'updated_at':c.get('updated_at'),
    }


def _guarded_get(url: str, *, params: Dict[str, Any], headers: Dict[str, str], timeout: float, priority: str = "diagnostic"):
    if not _egress_allows(priority):
        raise RuntimeError("SUPABASE_EGRESS_GUARD_OPEN")
    r = _SESSION.get(url, params=params, headers=headers, timeout=timeout)
    _track_http_response(r)
    if int(r.status_code or 0) == 402:
        _mark_restricted("HTTP_402_RESEARCH_EVIDENCE")
        raise requests.HTTPError("Supabase HTTP 402 Fair Use restriction", response=r)
    r.raise_for_status()
    return r


def _watermark(url: str, h: Dict[str, str]):
    r=_guarded_get(
        f"{url}/rest/v1/research_governance_snapshot_v1",
        params={'select':'id,updated_at,champion_count,pending_count','id':'eq.1','limit':'1'},
        headers=h,timeout=4,priority='important',
    )
    if r.ok:
        data=r.json()
        if isinstance(data,list) and data:
            row=data[0]
            return ('KNOWLEDGE_CORE',str(row.get('updated_at') or ''),str(row.get('champion_count') or 0),str(row.get('pending_count') or 0))
    def one(table):
        rr=_guarded_get(f"{url}/rest/v1/{table}",params={'select':'candidate_key,updated_at','order':'updated_at.desc','limit':'1'},headers=h,timeout=4,priority='important')
        data=rr.json(); row=data[0] if isinstance(data,list) and data else {}
        return str(row.get('candidate_key') or ''),str(row.get('updated_at') or '')
    return one('research_promotions_v1')+one('research_shadow_live_metrics_v1')


def _load(force: bool = False):
    now = time.monotonic()
    with _LOCK:
        cached_prom=list(_CACHE["promotions"])
        cached_shadow=list(_CACHE["shadow"])
        cached_wm=_CACHE.get("watermark")
        cached_ts=float(_CACHE["ts"] or 0.0)
        if (not force) and cached_prom and now - cached_ts < _TTL:
            return cached_prom, cached_shadow

    url, h = _headers()

    # The runtime prior is consulted frequently. After TTL, ask for two tiny
    # watermarks first; if neither promotions nor Shadow changed, reuse RAM.
    if (not force) and cached_prom:
        try:
            wm=_watermark(url,h)
            if wm == cached_wm:
                with _LOCK:
                    _CACHE["ts"]=now
                return cached_prom, cached_shadow
        except Exception:
            return cached_prom, cached_shadow
    else:
        wm=None

    # Knowledge Core: one tiny row contains every active Champion + its Shadow.
    # This is the normal path; laboratory tables are only a backward-compatible fallback.
    try:
        kr=_guarded_get(
            f"{url}/rest/v1/research_governance_snapshot_v1",
            params={'select':'*','id':'eq.1','limit':'1'},headers=h,timeout=5,priority='important',
        )
        kd=kr.json()
        if isinstance(kd,list) and kd:
            snap=kd[0]
            promotions=[_snapshot_as_promotion(x) for x in (snap.get('champions') or [])]
            shadow=list(snap.get('shadow') or [])
            wm=('KNOWLEDGE_CORE',str(snap.get('updated_at') or ''),str(snap.get('champion_count') or 0),str(snap.get('pending_count') or 0))
            with _LOCK:
                _CACHE.update(ts=now,promotions=list(promotions),shadow=list(shadow),watermark=wm)
            return promotions,shadow
    except Exception:
        if cached_prom:
            return cached_prom,cached_shadow

    r = _guarded_get(
        f"{url}/rest/v1/research_promotions_v1",
        params={
            "select": "candidate_key,source_engine,experiment,stage,reason,scope,metrics,meta,research_version,updated_at",
            "experiment": "in.(CAUSAL_COVERAGE_STRATEGY,CAUSAL_REGISTRY_RETEST,CAUSAL_SHADOW_RECYCLE)",
            "stage": "in.(OBSERVE,SHADOW_READY,SHADOW_READY_FAST,VALIDATION_REQUIRED,REJECTED_OOS,VALIDATED_SINGLE_ASSET)",
            "order": "updated_at.desc",
            "limit": "320",
        },
        headers=h,
        timeout=7,
        priority='diagnostic',
    )
    raw=r.json()
    promotions = raw if isinstance(raw, list) else []
    promotions = [
        p for p in promotions
        if str(p.get("experiment") or "") in _EXPERIMENTS
        and str(p.get("stage") or "") in _VISIBLE
        and (p.get("meta") or {}).get("is_current") is not False
        and str(p.get("research_version") or "").startswith(_RESEARCH_VERSION_PREFIX)
    ]
    shadow: List[Dict[str, Any]] = []
    try:
        sr = _guarded_get(
            f"{url}/rest/v1/research_shadow_live_metrics_v1",
            params={
                "select": (
                    "candidate_key,source_engine,experiment,research_stage,market_family,symbol,timeframe,"
                    "signals_n,resolved_n,win_rate_pct,expectancy_r,profit_factor,pnl_pct_sum,avg_safety,"
                    "recent8_n,recent8_expectancy_r,recent8_profit_factor,recent8_trade_sharpe,"
                    "previous8_n,previous8_expectancy_r,previous8_trade_sharpe,current_loss_streak,updated_at"
                ),
                "order": "updated_at.desc",
                "limit": "140",
            },
            headers=h,
            timeout=7,
            priority='diagnostic',
        )
        raw_shadow = sr.json()
        if isinstance(raw_shadow, list):
            shadow = raw_shadow
    except Exception:
        shadow = cached_shadow

    if wm is None:
        wm=(
            str((promotions[0] if promotions else {}).get("candidate_key") or ""),
            str((promotions[0] if promotions else {}).get("updated_at") or ""),
            str((shadow[0] if shadow else {}).get("candidate_key") or ""),
            str((shadow[0] if shadow else {}).get("updated_at") or ""),
        )
    with _LOCK:
        _CACHE.update(ts=now, promotions=list(promotions), shadow=list(shadow), watermark=wm)
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
    requested_raw = str(direction or "").upper()
    d = requested_raw
    if d == "COMPRA_SPOT": d = "LONG"
    if d == "VENTA_SPOT": d = "SHORT"
    if wanted_direction not in {"", "ALL", d}:
        return False
    wanted_action = _scope_action(scope)
    requested_action = requested_raw
    if str(system_type or '').lower() == 'spot':
        if requested_raw == 'LONG': requested_action = 'COMPRA_SPOT'
        elif requested_raw == 'SHORT': requested_action = 'VENTA_SPOT'
    else:
        if requested_raw in {'COMPRA_SPOT','VENTA_SPOT'}:
            requested_action = 'LONG' if requested_raw == 'COMPRA_SPOT' else 'SHORT'
    if wanted_action and requested_action and wanted_action != requested_action:
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
    # RC8 Alpha Decay Shield: a Champion can lose continuity before the normal
    # Shadow target when its exact live sequence shows structural deterioration.
    loss_streak = int(row.get("current_loss_streak") or 0)
    recent_n = int(row.get("recent8_n") or 0)
    recent_exp = _num(row.get("recent8_expectancy_r"))
    recent_pf = _num(row.get("recent8_profit_factor"))
    recent_sharpe = _num(row.get("recent8_trade_sharpe"))
    previous_n = int(row.get("previous8_n") or 0)
    previous_exp = _num(row.get("previous8_expectancy_r"))
    previous_sharpe = _num(row.get("previous8_trade_sharpe"))
    baseline_exp = _num(row.get("oos_exp_r"))
    if loss_streak >= 8:
        return "ALPHA_DECAY"
    trajectory_bad = bool(previous_n >= 6 and (
        (recent_sharpe is not None and previous_sharpe is not None and recent_sharpe <= previous_sharpe - 0.25)
        or (recent_exp is not None and previous_exp is not None and recent_exp <= previous_exp - 0.15)
    ))
    baseline_bad = bool(baseline_exp is not None and baseline_exp > 0 and recent_exp is not None and recent_exp <= min(0.0, baseline_exp * 0.25))
    if recent_n >= 8 and recent_exp is not None and recent_exp < 0:
        recent_bad = ((recent_pf is not None and recent_pf < 0.90) or
                      (recent_sharpe is not None and recent_sharpe < 0.0))
        if recent_bad and (trajectory_bad or baseline_bad):
            return "ALPHA_DECAY"
    if recent_n >= 8 and (
        (recent_exp is not None and baseline_exp is not None and baseline_exp > 0 and recent_exp < baseline_exp * 0.50)
        or (recent_sharpe is not None and recent_sharpe <= 0.10)
        or (recent_pf is not None and recent_pf < 1.05)
        or trajectory_bad
    ):
        return "ALPHA_DECAY_WATCH"
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
    meta = p.get("meta") or {}
    key = str(p.get("candidate_key") or "")
    live = shadow_map.get(key) or {}

    # RC7: prefer the immutable card published by Research. For champions that
    # were validated before RC7, build the exact same deterministic card from
    # their persisted causal_strategy_spec so the UI does not have to wait for
    # a Research republish cycle. No LLM and no inferred/tuned parameters.
    strategy_spec = meta.get("causal_strategy_spec") or {}
    strategy_id = meta.get("causal_strategy_id")
    strategy_card = meta.get("strategy_card") or {}
    if (not strategy_card) and strategy_spec and _build_strategy_card is not None:
        try:
            strategy_card = _build_strategy_card(
                strategy_id=strategy_id or key,
                scope=p.get("scope") or {},
                spec=strategy_spec,
                metrics=m,
                stage=p.get("stage"),
                updated_at=p.get("updated_at"),
            )
        except Exception:
            strategy_card = {}

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
        "recent8_n": int(live.get("recent8_n") or 0),
        "recent8_expectancy_r": _num(live.get("recent8_expectancy_r")),
        "recent8_profit_factor": _num(live.get("recent8_profit_factor")),
        "recent8_trade_sharpe": _num(live.get("recent8_trade_sharpe")),
        "previous8_n": int(live.get("previous8_n") or 0),
        "previous8_expectancy_r": _num(live.get("previous8_expectancy_r")),
        "previous8_trade_sharpe": _num(live.get("previous8_trade_sharpe")),
        "current_loss_streak": int(live.get("current_loss_streak") or 0),
        "coverage_cell": (p.get("meta") or {}).get("coverage_cell") or {},
        "coverage_cell_id": (p.get("meta") or {}).get("coverage_cell_id"),
        "strategy_family": (p.get("meta") or {}).get("causal_strategy_family"),
        # RC7: deterministic, frozen description generated by Research from the
        # exact causal StrategySpec. Main only transports/displays it; it does
        # not reinterpret parameters and never asks an LLM to describe them.
        "strategy_card": strategy_card,
        "strategy_id": strategy_id,
        "strategy_spec": strategy_spec,
        "runtime_trackable": bool(
            (p.get("meta") or {}).get("runtime_trackable")
            or ((p.get("meta") or {}).get("runtime_contract") or {}).get("runtime_trackable")
        ),
        "finalist_rank": (p.get("meta") or {}).get("finalist_rank_selection_only"),
        "registry_retest": bool((p.get("meta") or {}).get("registry_retest")),
        "shadow_recycle": bool((p.get("meta") or {}).get("shadow_recycle")),
        "original_candidate_key": (p.get("meta") or {}).get("original_candidate_key"),
        "champion_role": (p.get("meta") or {}).get("champion_role"),
        "champion_lineage_key": (p.get("meta") or {}).get("champion_lineage_key"),
        "champion_since": (p.get("meta") or {}).get("champion_since"),
        "champion_degraded": bool((p.get("meta") or {}).get("champion_degraded")),
        "alpha_decay_health": (p.get("meta") or {}).get("alpha_decay_health") or {},
        "updated_at": p.get("updated_at"),
    }
    out["shadow_state"] = _shadow_state(out)
    out["recycle_required"] = out["shadow_state"] in {"DIVERGED", "EARLY_DIVERGENCE", "ALPHA_DECAY"} or out.get("champion_degraded", False)
    if int(out.get("shadow_signals_n") or 0) > 0:
        out["shadow_diagnostic"] = "OBSERVING_LIVE"
        out["shadow_wait_reason_es"] = "Shadow ya observó al menos un setup live compatible con este Champion."
    elif not key:
        out["shadow_diagnostic"] = "TRACKING_IDENTITY_MISSING"
        out["shadow_wait_reason_es"] = "Falta la identidad del Champion; Shadow no puede enlazar observaciones."
    elif not strategy_spec:
        out["shadow_diagnostic"] = "STRATEGY_SPEC_MISSING"
        out["shadow_wait_reason_es"] = "Falta el StrategySpec congelado; la celda requiere reparación de integración antes de evaluar Shadow."
    elif not out.get("runtime_trackable"):
        out["shadow_diagnostic"] = "RUNTIME_CONTRACT_NOT_TRACKABLE"
        out["shadow_wait_reason_es"] = "La estrategia existe, pero su contrato todavía no es reproducible en runtime."
    else:
        out["shadow_diagnostic"] = "WAITING_MARKET_SETUP"
        out["shadow_wait_reason_es"] = "Esperando un setup live que cumpla exactamente el StrategySpec congelado; no se fabrica evidencia."
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
    """One persistent Champion per cell; Challengers cannot silently unfill it."""
    rows=list(rows or [])
    demoted_roots=set()
    for r in rows:
        root=str(r.get("champion_lineage_key") or r.get("original_candidate_key") or r.get("candidate_key") or "")
        if r.get("champion_degraded") and root:
            demoted_roots.add(root)
        elif (str(r.get("experiment") or "") in {"CAUSAL_REGISTRY_RETEST","CAUSAL_SHADOW_RECYCLE"}
              and str(r.get("stage") or "").upper()=="REJECTED_OOS"
              and str(r.get("original_candidate_key") or "")):
            demoted_roots.add(str(r.get("original_candidate_key")))
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        cid=str(row.get("coverage_cell_id") or "")
        if cid:
            grouped.setdefault(cid,[]).append(row)

    result=[]
    for cid,items in grouped.items():
        positives=[r for r in items if str(r.get("stage") or "") in _POSITIVE and str(r.get("original_candidate_key") or r.get("candidate_key") or "") not in demoted_roots and not r.get("recycle_required")]
        if positives:
            explicit=[r for r in positives if str(r.get("champion_role") or "").upper()=="INCUMBENT"]
            pool=explicit or positives
            # For legacy rows without RC8 role metadata, the oldest validated
            # lineage is the incumbent. Newer unrelated rows remain Challengers.
            roots: Dict[str, List[Dict[str, Any]]] = {}
            for r in pool:
                root=str(r.get("original_candidate_key") or r.get("candidate_key") or "")
                roots.setdefault(root,[]).append(r)
            incumbent_root=min(roots, key=lambda root:min(str(x.get("updated_at") or "") for x in roots[root]))
            lineage=roots[incumbent_root]
            best=max(lineage,key=lambda r:(str(r.get("updated_at") or ""),_stage_priority(r.get("stage")),float(r.get("oos_exp_r") if r.get("oos_exp_r") is not None else -999),int(r.get("oos_n") or 0)))
            best=dict(best)
            best["champion_role"]="INCUMBENT"
            best["champion_lineage_key"]=incumbent_root
            result.append(best)
            continue

        # Truly unfilled cell: expose its newest/best Challenger state.
        best=max(items,key=lambda row:(
            str(row.get("updated_at") or ""),
            _stage_priority(row.get("stage")),
            float(row.get("oos_exp_r") if row.get("oos_exp_r") is not None else -999),
            float(row.get("oos_pf") if row.get("oos_pf") is not None else -999),
            int(row.get("oos_n") or 0),
            -int(row.get("finalist_rank") or 999),
        ))
        result.append(best)
    return result


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
        diverged = [x for x in positives if x.get("shadow_state") in {"DIVERGED", "EARLY_DIVERGENCE", "ALPHA_DECAY"}]
        watched = [x for x in positives if x.get("shadow_state") == "ALPHA_DECAY_WATCH"]
        confirmed = [x for x in positives if x.get("shadow_state") == "CONFIRMED"]
        pending = [x for x in positives if x.get("shadow_state") not in {"DIVERGED", "EARLY_DIVERGENCE", "CONFIRMED", "ALPHA_DECAY", "ALPHA_DECAY_WATCH"}]

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
                penalty_score=max(float(base.get("penalty_score") or 0.0), 32.0 if worst_live.get("shadow_state") == "ALPHA_DECAY" else (24.0 if worst_live.get("shadow_state") == "DIVERGED" else 14.0)),
                best_positive=worst_live,
                recycle_required=True,
                recycle_reason=("Alpha decay detectado: retirar continuidad y volver a Research/Shadow." if worst_live.get("shadow_state") == "ALPHA_DECAY" else "Shadow/live no confirmó el edge histórico; volver a backtest/Validation."),
            )
            return base
        if watched:
            weak = min(watched, key=lambda x: x.get("recent8_expectancy_r") if x.get("recent8_expectancy_r") is not None else 999)
            base.update(
                state="ALPHA_DECAY_WATCH", support_score=0.0,
                penalty_score=max(float(base.get("penalty_score") or 0.0), 8.0),
                best_positive=weak, recycle_required=False,
                recycle_reason="Decay en observación: suspender apoyo positivo y priorizar Challenger sin borrar al incumbent.",
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
                "strategy_id": r.get("strategy_id"),
                "strategy_spec": r.get("strategy_spec") or {},
                "strategy_card": r.get("strategy_card") or {},
                "champion_role": r.get("champion_role") or "INCUMBENT",
                "champion_lineage_key": r.get("champion_lineage_key") or r.get("candidate_key"),
                "champion_since": r.get("champion_since"),
                "direction": scope.get("direction"),
                "action": _scope_action(scope),
                "regime": scope.get("regime"),
                "runtime_trackable": bool(r.get("runtime_trackable")),
                "updated_at": r.get("updated_at"),
                "oos_n": r.get("oos_n"), "oos_wr": r.get("oos_wr"),
                "oos_exp_r": r.get("oos_exp_r"), "oos_pf": r.get("oos_pf"),
                "guardian_operational_replay": r.get("guardian_operational_replay") or {},
                "full_stack_profitability_certification": r.get("full_stack_profitability_certification") or {},
                "shadow_signals_n": r.get("shadow_signals_n"), "shadow_n": r.get("shadow_n"),
                "shadow_exp_r": r.get("shadow_exp_r"), "shadow_pf": r.get("shadow_pf"),
                "shadow_target": r.get("shadow_target"), "shadow_state": r.get("shadow_state"),
                "shadow_diagnostic": r.get("shadow_diagnostic"),
                "shadow_wait_reason_es": r.get("shadow_wait_reason_es"),
                "recycle_required": r.get("recycle_required"),
            })
        return {
            "version": "RC8_1_RESEARCH_EVIDENCE_FUSION_V8_ACTION_CELLS",
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
            "shadow_waiting_market": sum(1 for r in validated_cells if r.get("shadow_diagnostic") == "WAITING_MARKET_SETUP"),
            "shadow_tracking_errors": sum(1 for r in validated_cells if r.get("shadow_diagnostic") in {"TRACKING_IDENTITY_MISSING","STRATEGY_SPEC_MISSING","RUNTIME_CONTRACT_NOT_TRACKABLE"}),
            "causal_candidates": len(contract_rows),
        }
    except Exception as exc:
        return {
            "version": "RC8_1_RESEARCH_EVIDENCE_FUSION_V8_ACTION_CELLS", "authority": "EVIDENCE_PRIOR_ONLY",
            "state": "UNAVAILABLE", "error": str(exc)[:180], "coverage_cells": 0,
            "coverage_target": _COVERAGE_TARGET, "coverage_complete": False,
            "validated_cells": 0, "oos_positive_cells": 0, "searching_cells": _COVERAGE_TARGET,
        }
