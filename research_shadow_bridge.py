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


def _headers():
    url,key=_cfg()
    if not url or not key:
        raise RuntimeError('Supabase no configurado')
    return url, {'apikey':key,'Authorization':f'Bearer {key}','Content-Type':'application/json','Accept':'application/json'}


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
    items=r.json() if isinstance(r.json(),list) else []
    with _LOCK:
        _CACHE['ts']=now; _CACHE['items']=list(items)
    return items


def _market_family(system_type: str, symbol: str) -> str:
    st=str(system_type or '').lower(); s=str(symbol or '').upper().replace('/','-')
    if st=='futures': return 'CRYPTO_FUTURES'
    if s in ('PAXG-USDT','PAXGUSDT'): return 'PAXG_USDT'
    if s in ('PAXG-BTC','PAXGBTC'): return 'PAXG_BTC'
    return 'CRYPTO_SPOT'


def _runtime_features(result: Dict[str,Any], system_type: str) -> Dict[str,Any]:
    decision=result.get('decision') or {}; levels=result.get('levels') or {}
    quant=result.get('futures_quantitative_context') or {}
    micro=result.get('futures_microstructure_context') or {}
    symbol=str(result.get('symbol') or '').upper().replace('/','-')
    tf=str(result.get('timeframe') or '').upper()
    direction=str(decision.get('action') or '').upper()
    regime=str(quant.get('regime') or quant.get('mode') or 'UNKNOWN').upper()
    entry_source=str(levels.get('entry_source') or levels.get('entry_method') or 'UNKNOWN').upper()
    strategies=[]
    for x in (decision.get('estrategias') or []):
        if isinstance(x,dict):
            strategies.append(str(x.get('strategy') or x.get('name') or x.get('estrategia') or '').upper())
        else: strategies.append(str(x).upper())
    micro_alignment=str(micro.get('alignment') or 'UNAVAILABLE').upper()
    def band(v,cuts,labels):
        try: x=float(v)
        except Exception: return 'UNKNOWN'
        for c,l in zip(cuts,labels):
            if x<c: return l
        return labels[-1]
    return {
        'market_family':_market_family(system_type,symbol), 'system_type':str(system_type or '').upper(),
        'symbol':symbol, 'timeframe':tf, 'direction':direction, 'regime':regime,
        'entry_source':entry_source, 'micro_alignment':micro_alignment,
        'sl_quality':band(levels.get('sl_reliability'),[60,75,90],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'tp_quality':band(levels.get('tp_quality_score'),[55,70,80],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'defensibility':band(levels.get('entry_defensibility_score'),[55,70,80],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'reachability':band(levels.get('entry_reachability_score'),[55,70,80],['LOW','MEDIUM','HIGH','VERY_HIGH']),
        'strategies':strategies,
        'safety':levels.get('execution_safety'),
    }


def _matches(scope: Dict[str,Any], feat: Dict[str,Any]) -> bool:
    aliases={'sl_quality':'sl_quality','sl_quality_band':'sl_quality','defensibility_band':'defensibility','reachability_band':'reachability'}
    for key,wanted in (scope or {}).items():
        k=aliases.get(key,key)
        if k=='component':
            token=str(wanted or '').upper()
            if token.startswith('STRATEGY:'): token=token.split(':',1)[1]
            if token and not any(token in s or s in token for s in feat.get('strategies',[])):
                return False
            continue
        if k not in feat:
            # No inventar coincidencia cuando el runtime no puede demostrarla.
            return False
        actual=str(feat.get(k) if feat.get(k) is not None else '').upper()
        target=str(wanted if wanted is not None else '').upper()
        if target and actual != target:
            return False
    return True


def track_research_shadow_signal(signal_id: str, analysis_result: Dict[str,Any], system_type: str) -> int:
    """Best-effort. Sólo registra coincidencias SHADOW_READY; jamás cambia la señal."""
    if not signal_id or not isinstance(analysis_result,dict): return 0
    try:
        candidates=_load_candidates()
        if not candidates: return 0
        feat=_runtime_features(analysis_result,system_type)
        matches=[c for c in candidates if _matches(c.get('scope') or {},feat)]
        if not matches: return 0
        decision=analysis_result.get('decision') or {}; levels=analysis_result.get('levels') or {}
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
        print(f"🧪 [RESEARCH SHADOW] {len(rows)} candidato(s) vinculados · {feat['symbol']} {feat['timeframe']} {feat['direction']}")
        return len(rows)
    except Exception as exc:
        print(f'⚠️ Research Shadow fail-open: {str(exc)[:180]}')
        return 0
