from __future__ import annotations
import os
import time
import threading
from typing import Any, Dict, List
import requests

_CACHE = {'ts': 0.0, 'items': []}
_LOCK = threading.Lock()
_TTL = max(300, int(os.getenv('RESEARCH_SHADOW_CANDIDATE_TTL_SECONDS','600') or 600))
_SESSION = requests.Session()


def _cfg():
    url = str(os.getenv('CENTRAL_SUPABASE_URL') or os.getenv('SUPABASE_URL') or '').rstrip('/')
    key = str(os.getenv('CENTRAL_SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY') or '').strip()
    return url, key


def _headers():
    url,key=_cfg()
    if not url or not key:
        raise RuntimeError('Supabase no configurado')
    headers={'apikey':key,'Content-Type':'application/json','Accept':'application/json'}
    # Legacy service-role keys are JWTs. Modern sb_secret_* keys are API keys,
    # not JWT Bearer tokens.
    if key.count('.') == 2:
        headers['Authorization']=f'Bearer {key}'
    return url, headers


def _load_candidates() -> List[Dict[str,Any]]:
    now=time.monotonic()
    with _LOCK:
        if _CACHE['items'] and now-_CACHE['ts'] < _TTL:
            return list(_CACHE['items'])
    url,headers=_headers()
    params={
        'select':'candidate_key,source_engine,experiment,stage,scope,meta,research_version,updated_at',
        'stage':'in.(SHADOW_READY,SHADOW_READY_FAST)',
        'order':'updated_at.desc',
        'limit':'120',
    }
    r=_SESSION.get(f'{url}/rest/v1/research_promotions_v1',params=params,headers=headers,timeout=8)
    r.raise_for_status()
    raw=r.json()
    items=[]
    for item in raw if isinstance(raw,list) else []:
        meta=item.get('meta') or {}
        if meta.get('is_current') is False:
            continue
        contract=meta.get('runtime_contract') or {}
        if contract and contract.get('runtime_trackable') is not True:
            continue
        items.append(item)
    with _LOCK:
        _CACHE['ts']=now; _CACHE['items']=list(items)
    return items


def _market_family(system_type: str, symbol: str) -> str:
    st=str(system_type or '').lower(); s=str(symbol or '').upper().replace('/','-')
    if st=='futures': return 'CRYPTO_FUTURES'
    if s in ('PAXG-USDT','PAXGUSDT'): return 'PAXG_USDT'
    if s in ('PAXG-BTC','PAXGBTC'): return 'PAXG_BTC'
    return 'CRYPTO_SPOT'


def _band(value,cuts,labels,missing='NO_DATA'):
    try: x=float(value)
    except Exception: return missing
    for c,l in zip(cuts,labels):
        if x<c: return l
    return labels[-1]


def _runtime_features(result: Dict[str,Any], system_type: str) -> Dict[str,Any]:
    decision=result.get('decision') or {}; levels=result.get('levels') or {}
    quant=result.get('futures_quantitative_context') or {}
    micro=result.get('futures_microstructure_context') or {}
    micro_metrics=micro.get('metrics') if isinstance(micro,dict) else {}
    if not isinstance(micro_metrics,dict): micro_metrics={}
    symbol=str(result.get('symbol') or '').upper().replace('/','-')
    tf=str(result.get('timeframe') or '').upper()
    direction=str(decision.get('action') or '').upper()
    if direction=='COMPRA_SPOT': direction='LONG'
    elif direction=='VENTA_SPOT': direction='SHORT'
    regime=str(quant.get('regime') or quant.get('mode') or 'UNKNOWN').upper()
    entry_source=str(levels.get('entry_source') or levels.get('entry_method') or 'UNKNOWN').upper()
    strategies=[]
    for x in (decision.get('estrategias') or []):
        if isinstance(x,dict): strategies.append(str(x.get('strategy') or x.get('name') or x.get('estrategia') or '').upper())
        else: strategies.append(str(x).upper())
    strategy_blob=' | '.join(strategies)
    return {
        'market_family':_market_family(system_type,symbol), 'system_type':str(system_type or '').upper(),
        'symbol':symbol, 'timeframe':tf, 'direction':direction, 'regime':regime,
        'entry_source':entry_source, 'micro_alignment':str(micro.get('alignment') or 'UNAVAILABLE').upper(),
        'sl_quality':_band(levels.get('sl_reliability'),[60,75,90],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'tp_quality':_band(levels.get('tp_quality_score'),[55,70,80],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'defensibility':_band(levels.get('entry_defensibility_score'),[55,70,80],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'reachability':_band(levels.get('entry_reachability_score'),[55,70,80],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'orderbook_imbalance_band':_band(micro_metrics.get('orderbook_imbalance'),[-0.25,0.25],['SELL_HEAVY','BALANCED','BUY_HEAVY']),
        'recent_buy_share_band':_band(micro_metrics.get('recent_buy_share'),[0.40,0.60],['SELL_HEAVY','BALANCED','BUY_HEAVY']),
        'has_order_block':'YES' if ('ORDER BLOCK' in strategy_blob or 'ORDER_BLOCK' in strategy_blob) else 'NO',
        'has_sweep':'YES' if ('SWEEP' in strategy_blob or 'LIQUIDITY' in strategy_blob) else 'NO',
        'has_pullback':'YES' if ('PULLBACK' in strategy_blob or 'RETEST' in strategy_blob) else 'NO',
        'strategies':strategies,
        'safety':levels.get('execution_safety'),
    }


def _matches(scope: Dict[str,Any], feat: Dict[str,Any]) -> bool:
    aliases={
        'sl_quality':'sl_quality','sl_quality_band':'sl_quality',
        'tp_quality':'tp_quality','tp_quality_band':'tp_quality',
        'defensibility_band':'defensibility','reachability_band':'reachability',
    }
    for key,wanted in (scope or {}).items():
        k=aliases.get(key,key)
        if k=='component':
            token=str(wanted or '').upper()
            if not token.startswith('STRATEGY:'):
                return False
            token=token.split(':',1)[1]
            if token and not any(token in s or s in token for s in feat.get('strategies',[])):
                return False
            continue
        if k not in feat:
            return False
        actual=str(feat.get(k) if feat.get(k) is not None else '').upper()
        target=str(wanted if wanted is not None else '').upper()
        if target and actual != target:
            return False
    return True


def track_research_shadow_signal(signal_id: str, analysis_result: Dict[str,Any], system_type: str) -> int:
    """Best-effort. Registra sólo candidatos reproducibles; jamás cambia la señal."""
    if not signal_id or not isinstance(analysis_result,dict): return 0
    try:
        candidates=_load_candidates()
        if not candidates: return 0
        feat=_runtime_features(analysis_result,system_type)
        matches=[c for c in candidates if _matches(c.get('scope') or {},feat)]
        if not matches: return 0
        levels=analysis_result.get('levels') or {}
        rows=[]
        for c in matches[:12]:
            rows.append({
                'candidate_key':str(c.get('candidate_key') or '')[:500], 'signal_id':signal_id,
                'source_engine':str(c.get('source_engine') or '')[:40], 'experiment':str(c.get('experiment') or '')[:100],
                'research_stage':str(c.get('stage') or '')[:40], 'research_version':str(c.get('research_version') or '')[:80],
                'system_type':str(system_type or '').lower(), 'market_family':feat['market_family'], 'symbol':feat['symbol'],
                'timeframe':feat['timeframe'], 'direction':feat['direction'], 'regime':feat['regime'],
                'execution_safety':levels.get('execution_safety'), 'risk_reward':levels.get('risk_reward'),
                'entry':levels.get('entry'), 'stop_loss':levels.get('stop_loss'), 'take_profit':levels.get('take_profit'),
                'scope':c.get('scope') or {}, 'matched_features':{k:v for k,v in feat.items() if k!='strategies'},
            })
        url,headers=_headers(); headers=dict(headers); headers['Prefer']='resolution=merge-duplicates,return=minimal'
        r=_SESSION.post(f'{url}/rest/v1/research_shadow_live_v1',params={'on_conflict':'candidate_key,signal_id'},headers=headers,json=rows,timeout=8)
        r.raise_for_status()
        print(f"🧪 [RESEARCH SHADOW] {len(rows)} candidato(s) reproducibles vinculados · {feat['symbol']} {feat['timeframe']} {feat['direction']}")
        return len(rows)
    except Exception as exc:
        print(f'⚠️ Research Shadow fail-open: {str(exc)[:180]}')
        return 0
