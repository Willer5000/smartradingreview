from __future__ import annotations
import os
import time
import threading
import requests
from flask import Blueprint, jsonify, render_template, Response

_bp = Blueprint('research_federation_bridge', __name__)
_session = requests.Session()
_CACHE = {'ts': 0.0, 'payload': None, 'error': None}
_PROFIT_CACHE = {'ts': 0.0, 'payload': None}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = max(30, int(os.getenv('RESEARCH_BRIDGE_CACHE_SECONDS','60') or 60))
_BRIDGE_FAILURES = 0
_BRIDGE_CIRCUIT_UNTIL = 0.0
_BRIDGE_STATE_LOCK = threading.Lock()

def _cfg():
    url = str(
        os.getenv('CENTRAL_SUPABASE_URL')
        or os.getenv('SUPABASE_URL')
        or ''
    ).rstrip('/')
    key = str(
        os.getenv('CENTRAL_SUPABASE_SERVICE_KEY')
        or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        or os.getenv('SUPABASE_KEY')
        or ''
    ).strip()
    return url, key

def _bridge_circuit_open():
    with _BRIDGE_STATE_LOCK:
        return time.monotonic() < _BRIDGE_CIRCUIT_UNTIL


def _bridge_failure(exc):
    global _BRIDGE_FAILURES, _BRIDGE_CIRCUIT_UNTIL
    with _BRIDGE_STATE_LOCK:
        _BRIDGE_FAILURES += 1
        if _BRIDGE_FAILURES >= 2:
            _BRIDGE_CIRCUIT_UNTIL = time.monotonic() + 60.0
    with _CACHE_LOCK:
        _CACHE['error'] = f'{type(exc).__name__}: {str(exc)[:180]}'


def _bridge_success():
    global _BRIDGE_FAILURES, _BRIDGE_CIRCUIT_UNTIL
    with _BRIDGE_STATE_LOCK:
        _BRIDGE_FAILURES = 0
        _BRIDGE_CIRCUIT_UNTIL = 0.0


def _get(table, params):
    if _bridge_circuit_open():
        raise RuntimeError('SUPABASE_BRIDGE_CIRCUIT_OPEN')
    url,key=_cfg()
    if not url or not key:
        raise RuntimeError('Supabase Research Bridge no configurado')
    h={'apikey':key,'Accept':'application/json'}
    if key.count('.') == 2:
        h['Authorization']=f'Bearer {key}'
    try:
        r=_session.get(f'{url}/rest/v1/{table}',params=params,headers=h,timeout=5)
        if int(r.status_code or 0) in {500,502,503,504,520,521,522,523,524}:
            raise requests.HTTPError(f'Supabase transient HTTP {r.status_code}',response=r)
        r.raise_for_status()
        ctype=str(r.headers.get('content-type') or '').lower()
        if 'json' not in ctype:
            raise ValueError(f'Supabase devolvió contenido no JSON ({ctype or "sin content-type"})')
        data=r.json()
        return data if isinstance(data,list) else []
    except Exception as exc:
        _bridge_failure(exc)
        raise

def _auth_guard(auth_fn):
    return auth_fn()

def _num(value):
    try:
        return float(value) if value is not None else None
    except Exception:
        return None

_TF_ORDER = ('30M','1H','2H','4H','12H','1D','1W','ALL')
_CAUSAL_EXPERIMENTS = {'CAUSAL_COVERAGE_STRATEGY','CAUSAL_REGISTRY_RETEST','CAUSAL_SHADOW_RECYCLE'}

def _tf(value):
    return str(value or 'ALL').strip().upper() or 'ALL'

def _stage_priority(stage):
    return {
        'SHADOW_READY_FAST': 60, 'SHADOW_READY': 55,
        'VALIDATION_REQUIRED': 40, 'VALIDATED_SINGLE_ASSET': 38,
        'OBSERVE': 25, 'REJECTED_OOS': 10,
    }.get(str(stage or '').upper(), 20)

def _causal_cell_id(row):
    meta=row.get('meta') or {}; scope=row.get('scope') or {}
    cid=str(meta.get('coverage_cell_id') or '').strip()
    if cid:
        return cid.upper()
    market=str(scope.get('market_family') or 'UNKNOWN').upper()
    symbol=str(scope.get('symbol') or 'ALL').upper()
    tf=_tf(scope.get('timeframe'))
    return f'{market}|{symbol}|{tf}'

def _best_causal_per_cell(rows):
    """One representative per specialist cell for Analytics visibility.

    I.2 persists several pre-declared finalists per cell so Validation can test
    alternatives without touching Final OOS.  The central UI must not let those
    finalists consume all 240 visible slots.  This selector is display-only;
    Research evidence fusion still reads every finalist directly from Supabase.
    """
    best={}; scores={}
    for row in rows or []:
        if str(row.get('experiment') or '') not in _CAUSAL_EXPERIMENTS:
            continue
        cid=_causal_cell_id(row)
        metrics=row.get('metrics') or {}; val=metrics.get('validation') or {}
        exp=_num(val.get('expectancy_r')); pf=_num(val.get('profit_factor'))
        score=(
            _stage_priority(row.get('stage')),
            exp if exp is not None else -999.0,
            pf if pf is not None else -999.0,
            int(val.get('resolved') or 0),
            -int((row.get('meta') or {}).get('finalist_rank_selection_only') or 999),
        )
        if cid not in best or score > scores[cid]:
            best[cid]=row; scores[cid]=score
    return list(best.values())

def _balanced_candidates(rows, limit=240):
    """Keep all 40 active V1 specialist cells visible without crowding out diagnostics."""
    rows=list(rows or [])
    limit=max(1,int(limit or 1))
    picked=[]; seen=set()
    def key(row): return str(row.get('candidate_key') or '')
    def add(row):
        k=key(row)
        if not k or k in seen or len(picked)>=limit: return
        seen.add(k); picked.append(row)

    # J.1: one best representative for each active V1 symbol×TF causal cell.
    causal=_best_causal_per_cell(rows)
    causal.sort(key=lambda r: _causal_cell_id(r))
    for row in causal:
        add(row)
        if len(picked)>=limit: return picked

    causal_keys={key(x) for x in rows if str(x.get('experiment') or '') in _CAUSAL_EXPERIMENTS}
    noncausal=[x for x in rows if key(x) not in causal_keys]
    if len(picked)+len(noncausal)<=limit:
        for row in noncausal: add(row)
        return picked

    # Guarantee one observational row for every existing engine x timeframe.
    markers=set()
    for tf in _TF_ORDER:
        for row in noncausal:
            scope=row.get('scope') or {}
            if _tf(scope.get('timeframe')) != tf: continue
            marker=(str(row.get('source_engine') or 'UNKNOWN'),tf)
            if marker in markers: continue
            markers.add(marker); add(row)
            if len(picked)>=limit: return picked

    buckets={tf:[] for tf in _TF_ORDER}; other=[]
    for row in noncausal:
        tf=_tf((row.get('scope') or {}).get('timeframe'))
        (buckets[tf] if tf in buckets else other).append(row)
    active=[tf for tf in _TF_ORDER if buckets[tf]]; idx=0
    while active and len(picked)<limit:
        tf=active[idx % len(active)]; bucket=buckets[tf]
        while bucket and key(bucket[0]) in seen: bucket.pop(0)
        if bucket: add(bucket.pop(0))
        if not bucket:
            active.remove(tf); idx=0
        else:
            idx += 1
    for row in other + noncausal:
        add(row)
        if len(picked)>=limit: break
    return picked

def _coverage(rows):
    by_tf={}; by_engine={}; by_market={}
    for row in rows or []:
        scope=row.get('scope') or {}
        tf=_tf(scope.get('timeframe'))
        eng=str(row.get('source_engine') or 'UNKNOWN')
        market=str(scope.get('market_family') or 'UNKNOWN')
        by_tf[tf]=by_tf.get(tf,0)+1
        by_engine[eng]=by_engine.get(eng,0)+1
        by_market[market]=by_market.get(market,0)+1
    strategic={tf:int(by_tf.get(tf,0)) for tf in ('4H','12H','1D','1W')}
    return {
        'by_timeframe':dict(sorted(by_tf.items())),
        'by_engine':dict(sorted(by_engine.items())),
        'by_market':dict(sorted(by_market.items())),
        'strategic_timeframes':strategic,
        'missing_strategic_timeframes':[tf for tf,n in strategic.items() if n<=0],
        'total_current':len(rows or []),
    }

def _compact_promotion(row):
    metrics = row.get('metrics') or {}
    allm = metrics.get('all') or {}
    val = metrics.get('validation') or {}
    meta = row.get('meta') or {}
    scope = row.get('scope') or {}
    # RC8 P0: StrategySpec/Card are part of the immutable Champion contract.
    # Do not strip them at the Research→Main bridge; Analytics must display the
    # exact parameters that were validated, never BOTH/ALL/{} fallbacks.
    strategy_spec = meta.get('causal_strategy_spec') or {}
    strategy_card = meta.get('strategy_card') or {}
    strategy_id = meta.get('causal_strategy_id')
    return {
        'candidate_key': row.get('candidate_key'),
        'source_engine': row.get('source_engine'),
        'experiment': row.get('experiment'),
        'stage': row.get('stage'),
        'reason': row.get('reason'),
        'market_family': scope.get('market_family') or '--',
        'symbol': scope.get('symbol') or 'ALL',
        'timeframe': scope.get('timeframe') or 'ALL',
        'direction': scope.get('direction') or 'ALL',
        'regime': scope.get('regime') or 'ALL',
        'backtest_n': int(allm.get('resolved') or 0),
        'backtest_wr': _num(allm.get('win_rate_pct')),
        'backtest_exp_r': _num(allm.get('expectancy_r')),
        'backtest_pf': _num(allm.get('profit_factor')),
        'oos_n': int(val.get('resolved') or 0),
        'oos_wr': _num(val.get('win_rate_pct')),
        'oos_exp_r': _num(val.get('expectancy_r')),
        'oos_pf': _num(val.get('profit_factor')),
        'oos_max_dd_r': _num(val.get('max_drawdown_r')),
        'shadow_target': int(meta.get('recommended_shadow_target') or 0),
        'canary_target': int(meta.get('recommended_canary_target') or 0),
        'research_version': row.get('research_version'),
        'updated_at': row.get('updated_at'),
        'causal_strategy': bool(meta.get('causal_strategy') or meta.get('causal_candle_replay')),
        'coverage_cell': meta.get('coverage_cell') or {},
        'coverage_cell_id': meta.get('coverage_cell_id') or _causal_cell_id(row),
        'finalist_rank': meta.get('finalist_rank_selection_only'),
        'strategy_family': meta.get('causal_strategy_family') or meta.get('factory_family'),
        'walk_forward_positive_ratio': _num(meta.get('walk_forward_positive_ratio')),
        'scope': scope,
        'strategy_id': strategy_id,
        'strategy_spec': strategy_spec,
        'strategy_card': strategy_card,
        'runtime_trackable': bool(meta.get('runtime_trackable') or (meta.get('runtime_contract') or {}).get('runtime_trackable')),
        'dataset_fingerprint': meta.get('dataset_fingerprint'),
        'causal_dataset_signature': meta.get('causal_dataset_signature'),
    }

def _compact(force=False):
    now=time.monotonic()
    with _CACHE_LOCK:
        if (not force) and _CACHE['payload'] and (now-_CACHE['ts']) < _CACHE_TTL:
            return _CACHE['payload']

    try:
        raw_promotions=_get('research_promotions_v1',{
            'select':'candidate_key,source_engine,experiment,stage,reason,scope,metrics,meta,research_version,updated_at',
            'order':'updated_at.desc',
            'limit':'1800',
        })
        raw_promotions=[x for x in raw_promotions if (x.get('meta') or {}).get('is_current') is not False and str(x.get('stage') or '') != 'STALE']
        coverage=_coverage(raw_promotions)
        visible=_balanced_candidates(raw_promotions,240)
        candidates=[_compact_promotion(x) for x in visible]
        states=_get('research_engine_state_v1',{
            'select':'engine,status,last_seen_at,rss_mb,research_version,meta',
            'order':'engine.asc',
            'limit':'10',
        })
        shadow=_get('research_shadow_live_metrics_v1',{
            'select':'*',
            'order':'updated_at.desc',
            'limit':'600',
        })
        payload=(candidates,states,shadow,coverage)
    except Exception as exc:
        with _CACHE_LOCK:
            cached=_CACHE.get('payload')
            _CACHE['error']=f'{type(exc).__name__}: {str(exc)[:180]}'
        if cached:
            return cached
        raise
    _bridge_success()
    with _CACHE_LOCK:
        _CACHE['ts']=now
        _CACHE['payload']=payload
        _CACHE['error']=None
    return payload

def _report(candidates,states,shadow,coverage):
    lines=['# Research Federation · sistema central','','- Bridge V1.2.1: evidencia externa + Shadow central observado.','- Nunca concede autoridad productiva automáticamente.','','## Motores']
    for s in states:
        lines.append(f"- {s.get('engine')}: {s.get('status')} · RSS {s.get('rss_mb')} MB · {s.get('last_seen_at')}")
    strategic=(coverage or {}).get('strategic_timeframes') or {}
    lines += ['','## Cobertura de temporalidades', f"- 4H={strategic.get('4H',0)} · 12H={strategic.get('12H',0)} · 1D={strategic.get('1D',0)} · 1W={strategic.get('1W',0)}", '', '## Evidencia Discovery/Holdout temporal','- CAUSAL_COVERAGE_STRATEGY/RETEST/RECYCLE usan replay causal; el resto conserva evidencia observacional temporal. I.2/J.1 muestran una fila por celda de 54 en Analytics.']
    for x in candidates[:35]:
        lines.append(f"- {x.get('stage')} | {x.get('source_engine')} | {x.get('experiment')} | {x.get('market_family')} {x.get('timeframe')} | Discovery.N={x.get('backtest_n')} | WR={x.get('backtest_wr')}% | Exp.R={x.get('backtest_exp_r')} | Holdout.N={x.get('oos_n')} | Holdout.WR={x.get('oos_wr')}% | Holdout.Exp.R={x.get('oos_exp_r')} | PF={x.get('oos_pf')}")
    lines += ['','## Shadow central live']
    for x in shadow[:35]:
        lines.append(f"- {x.get('research_stage')} | {x.get('source_engine')} | {x.get('experiment')} | {x.get('market_family')} {x.get('symbol')} {x.get('timeframe')} | señales={x.get('signals_n')} | resueltas={x.get('resolved_n')} | WR={x.get('win_rate_pct')}% | Exp.R={x.get('expectancy_r')} | PF={x.get('profit_factor')} | PnL={x.get('pnl_pct_sum')}% | Safety={x.get('avg_safety')}")
    return '\n'.join(lines)

def _profitability_snapshot_safe(degraded=False):
    if degraded or _bridge_circuit_open():
        return _PROFIT_CACHE.get('payload') or {'state':'UNAVAILABLE','degraded':True}
    try:
        from research_evidence_fusion import profitability_snapshot
        payload=profitability_snapshot(force=False)
        _PROFIT_CACHE.update(ts=time.monotonic(), payload=payload)
        return payload
    except Exception as exc:
        cached=_PROFIT_CACHE.get('payload')
        if cached:
            return cached
        return {'state':'UNAVAILABLE','degraded':True,'error':str(exc)[:160]}


def _degraded_empty_payload(exc):
    return {
        'success': True, 'connected': False, 'degraded': True,
        'data_available': False, 'stale': False,
        'candidates': [], 'engines': [], 'shadow_live': [],
        'authority': 'RESEARCH_SHADOW_BRIDGE_J_V2', 'visible_rows': 0,
        'coverage': {'by_timeframe':{},'by_engine':{},'by_market':{},'strategic_timeframes':{},'missing_strategic_timeframes':[],'total_current':0},
        'profitability_evidence': _PROFIT_CACHE.get('payload') or {'state':'UNAVAILABLE','degraded':True},
        'error': f'{type(exc).__name__}: {str(exc)[:180]}',
        'retry_after_seconds': 60,
    }


def register_research_bridge(app, auth_fn):
    @_bp.get('/research-federation')
    def page():
        user=_auth_guard(auth_fn)
        if not isinstance(user,str):
            return user
        return render_template('research_federation.html')

    @_bp.get('/api/research-federation/summary')
    def summary():
        user=_auth_guard(auth_fn)
        if not isinstance(user,str):
            return user
        try:
            c,s,l,cov=_compact()
            with _CACHE_LOCK:
                bridge_error=_CACHE.get('error')
            degraded=bool(bridge_error)
            profitability=_profitability_snapshot_safe(degraded=degraded)
            return jsonify({
                'success':True,
                'connected':not degraded,
                'degraded':degraded,
                'data_available':bool(c or s or l),
                'stale':degraded and bool(c or s or l),
                'error':bridge_error,
                'retry_after_seconds':60 if degraded else 0,
                'candidates':c,
                'engines':s,
                'shadow_live':l,
                'authority':'RESEARCH_SHADOW_BRIDGE_J_V2',
                'visible_rows':len(c),
                'coverage':cov,
                'profitability_evidence': profitability,
            })
        except Exception as exc:
            # Observability must not become HTTP-500 during a provider outage.
            # Empty/degraded is distinct from zero evidence and the UI preserves
            # its last good state instead of repainting misleading zeros.
            return jsonify(_degraded_empty_payload(exc)),200

    @_bp.get('/api/research-federation/export')
    def export():
        user=_auth_guard(auth_fn)
        if not isinstance(user,str):
            return user
        try:
            c,s,l,cov=_compact()
            text=_report(c,s,l,cov)
            with _CACHE_LOCK:
                err=_CACHE.get('error')
            if err:
                text += '\n\n> Datos cacheados: Supabase no respondió al último refresco.\n'
            return Response(text,status=200,mimetype='text/markdown; charset=utf-8')
        except Exception as exc:
            return Response('# Research Federation\n\nDatos temporalmente no disponibles. La indisponibilidad de Supabase no se interpreta como pérdida de Champions ni evidencia de trading.\n',status=200,mimetype='text/markdown; charset=utf-8')

    app.register_blueprint(_bp)
