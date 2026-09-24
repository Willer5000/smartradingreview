"""Commit 12 — Multi-Activo, resource-governed derivatives layer.

Design goals:
- reuse the proven Futures Entry/Safety/Publication/ReviewTrader engine;
- keep market-specific strategy/context/specialist logic separate;
- never store scanner candles in Supabase;
- scan sequentially, shortlist <=2, and invoke no LLM automatically;
- reuse the already-cached macro snapshot (no extra macro network calls).
"""
from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from futures_system import (
    FuturesAnalysis,
    KUCOIN_FUTURES_KLINES_URL,
    KUCOIN_FUTURES_CONTRACT_URL,
    _get_futures_http_session,
    _track_futures_network_response,
)

MULTIASSET_VERSION = 'COMMIT12_MULTI_V1_RESOURCE_GOVERNED'
MULTIASSET_ENABLED = str(os.getenv('MULTIASSET_ENABLED', '1')).lower() not in ('0','false','no','off')
MULTIASSET_DEEP_LIMIT = max(1, min(2, int(os.getenv('MULTIASSET_DEEP_LIMIT', '2') or 2)))
MULTIASSET_ROUTER_TTL_SECONDS = max(300, int(os.getenv('MULTIASSET_ROUTER_TTL_SECONDS', '900') or 900))
MULTIASSET_ROUTER_CANDLES = max(48, min(96, int(os.getenv('MULTIASSET_ROUTER_CANDLES', '72') or 72)))
MULTIASSET_AUTO_DEEP_DAILY_MAX = max(4, min(16, int(os.getenv('MULTIASSET_AUTO_DEEP_DAILY_MAX', '12') or 12)))

# Logical symbols remain readable/stable inside the application and DB. KuCoin
# contract IDs are transport details only.
MULTIASSET_SYMBOLS = {
    'SPY-USDT': {'code':'SPY', 'name':'SPY (S&P 500)', 'asset_class':'US_INDEX', 'group':'INDEX', 'decimals':2, 'contract':'SPYUSDTM'},
    'QQQ-USDT': {'code':'QQQ', 'name':'QQQ (Nasdaq 100)', 'asset_class':'US_INDEX', 'group':'INDEX', 'decimals':2, 'contract':'QQQUSDTM'},
    'CL-USDT': {'code':'CL', 'name':'CL (Petróleo WTI)', 'asset_class':'ENERGY', 'group':'ENERGY', 'decimals':2, 'contract':'CLUSDTM'},
    'NATGAS-USDT': {'code':'NATGAS', 'name':'NATGAS (Gas Natural)', 'asset_class':'ENERGY', 'group':'ENERGY', 'decimals':3, 'contract':'NATGASUSDTM'},
    'COPPER-USDT': {'code':'COPPER', 'name':'COPPER (Cobre)', 'asset_class':'INDUSTRIAL_METAL', 'group':'METALS', 'decimals':4, 'contract':'COPPERUSDTM'},
    'XAG-USDT': {'code':'XAG', 'name':'XAG (Plata)', 'asset_class':'PRECIOUS_METAL', 'group':'METALS', 'decimals':3, 'contract':'XAGUSDTM'},
    # KSTR is verified at runtime because KuCoin can rename/retire synthetic contracts.
    'KSTR-USDT': {'code':'KSTR', 'name':'KSTR (China STAR 50)', 'asset_class':'CHINA_INDEX', 'group':'ASIA', 'decimals':2, 'contract':'KSTRUSDTM', 'runtime_verify':True},
}
MULTIASSET_CONTRACT_SYMBOLS = {k:v['contract'] for k,v in MULTIASSET_SYMBOLS.items()}
MULTIASSET_TIMEFRAMES = {
    '1h': {'name':'1 Hora · Fast Lane', 'type':'dynamic_fast_lane'},
    '4h': {'name':'4 Horas · Principal', 'type':'execution'},
    '1D': {'name':'1 Día · Swing/Contexto', 'type':'swing'},
}
MULTIASSET_GRANULARITY_MINUTES = {'1h':60, '4h':240, '1D':1440}
MULTIASSET_TIMEFRAME_SECONDS = {'1h':3600, '4h':14400, '1D':86400}
MULTIASSET_GROUP_ORDER = ['INDEX','ENERGY','METALS','ASIA']
MULTIASSET_GROUP_LABELS = {
    'INDEX':'Índices EE.UU.', 'ENERGY':'Energía', 'METALS':'Metales', 'ASIA':'Asia / China'
}

# Strategy families are not independent database objects. The same family gets
# calibrated by symbol/timeframe/context, avoiding strategy-table explosion.
MULTIASSET_STRATEGY_BANK = {
    'US_INDEX': [
        'SWEEP_MSS_POI', 'VWAP_SESSION_PULLBACK', 'BREAKOUT_RETEST',
        'COMPRESSION_EXPANSION', 'TREND_PULLBACK', 'POST_MACRO_CONFIRMATION',
        'MEAN_REVERSION_SELECTIVE',
    ],
    'ENERGY': [
        'SWEEP_MSS_POI', 'TREND_PULLBACK', 'BREAKOUT_RETEST',
        'COMPRESSION_EXPANSION', 'POST_EVENT_CONFIRMATION',
        'VOLATILITY_RETEST',
    ],
    'INDUSTRIAL_METAL': [
        'SWEEP_MSS_POI', 'TREND_PULLBACK', 'BREAKOUT_RETEST',
        'COMPRESSION_EXPANSION', 'MACRO_TREND_CONFIRMATION',
    ],
    'PRECIOUS_METAL': [
        'SWEEP_MSS_POI', 'TREND_PULLBACK', 'MEAN_REVERSION_SELECTIVE',
        'BREAKOUT_RETEST', 'RATES_USD_CONFIRMATION',
    ],
    'CHINA_INDEX': [
        'SWEEP_MSS_POI', 'TREND_PULLBACK', 'BREAKOUT_RETEST',
        'COMPRESSION_EXPANSION', 'ASIA_SESSION_RETEST', 'MACRO_TREND_CONFIRMATION',
    ],
}
SPECIALIST_BY_CLASS = {
    'US_INDEX':'Equity Index Specialist',
    'ENERGY':'Energy Specialist',
    'INDUSTRIAL_METAL':'Metals / Industrial Cycle Specialist',
    'PRECIOUS_METAL':'Precious Metals Specialist',
    'CHINA_INDEX':'Asia / China Specialist',
}

_router_lock = threading.Lock()
_router_cache = {'stored_at':0.0, 'timeframe':None, 'rows':[]}
_contract_lock = threading.Lock()
_contract_cache: Dict[str, Dict] = {}


def _safe_float(value, default=0.0):
    try:
        v=float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _market_session(asset_class: str) -> str:
    now=datetime.now(timezone.utc)
    h=now.hour + now.minute/60.0
    if asset_class in {'US_INDEX'}:
        return 'US_CASH' if 13.5 <= h <= 20.0 else 'UNDERLYING_CLOSED_OR_OFFHOURS'
    if asset_class == 'CHINA_INDEX':
        return 'ASIA' if 1.0 <= h <= 8.0 else 'OFFHOURS'
    if 12.0 <= h <= 21.0:
        return 'US_COMMODITY_SESSION'
    if 6.0 <= h < 12.0:
        return 'EUROPE'
    return 'OVERNIGHT'


def _macro_context_for_asset(meta: Dict) -> Dict:
    """Derive market-specific macro gate from the existing shared macro cache."""
    try:
        from macro_context import get_macro_context_snapshot
        snap=get_macro_context_snapshot(fetch_if_stale=False) or {}
    except Exception as exc:
        return {'available':False, 'gate':'NORMAL', 'reason':str(exc)[:120], 'affects_direction':False}

    asset_class=meta.get('asset_class')
    next_event=snap.get('next_high_impact_event') or {}
    hours=_safe_float(next_event.get('hours_until'), 9999.0)
    precision=str(next_event.get('time_precision') or 'EXACT').upper()
    current_risk=str(snap.get('current_risk_level') or snap.get('risk_level') or 'LOW').upper()
    bias=str(snap.get('directional_bias') or 'NEUTRAL').upper()
    title=' '.join(str(next_event.get(k) or '') for k in ('title','name','event','label')).upper()

    relevant=False
    if asset_class == 'US_INDEX':
        relevant=True
    elif asset_class in {'INDUSTRIAL_METAL','PRECIOUS_METAL','CHINA_INDEX'}:
        relevant=any(k in title for k in ('FED','FOMC','CPI','PCE','NFP','EMPLOY','RATE','PMI','CHINA','TRADE')) or not title
    elif asset_class == 'ENERGY':
        relevant=any(k in title for k in ('OIL','EIA','OPEC','ENERGY','CPI','FED','FOMC'))

    gate='NORMAL'
    reason=None
    # Only an exact imminent high-impact event may hold a NEW position. Macro
    # never manufactures direction and never edits Entry/SL/TP.
    if relevant and precision == 'EXACT' and 0 <= hours <= 0.75:
        gate='WAIT_EVENT'
        reason='EVENT_RISK_WITHIN_45M'
    elif current_risk in {'HIGH','CRITICAL'}:
        gate='CAUTION'
        reason='ELEVATED_CURRENT_MACRO_RISK'

    return {
        'available':True, 'gate':gate, 'reason':reason,
        'risk_level':current_risk, 'directional_bias':bias,
        'next_event_hours': None if hours >= 9990 else round(hours,2),
        'next_event': next_event.get('title') or next_event.get('name') or next_event.get('event'),
        'policy':'CONFIRM_OR_VETO_ONLY_NEVER_CREATE_DIRECTION',
        'affects_direction':False,
    }


def _strategy_context(meta: Dict, timeframe: str, result: Dict) -> Dict:
    levels=result.get('levels') or {}
    trend=result.get('trend') or {}
    adx=_safe_float(trend.get('adx') or levels.get('adx'))
    atr_pct=_safe_float(levels.get('atr_pct') or result.get('atr_pct'))
    if adx >= 28:
        regime='TRENDING'
    elif adx and adx < 18:
        regime='RANGING'
    else:
        regime='MIXED'
    volatility='HIGH' if atr_pct >= 3.0 else ('LOW' if atr_pct and atr_pct < 0.8 else 'NORMAL')
    families=list(MULTIASSET_STRATEGY_BANK.get(meta['asset_class']) or [])
    preferred=[]
    if regime == 'TRENDING':
        preferred += [x for x in families if x in ('TREND_PULLBACK','SWEEP_MSS_POI','BREAKOUT_RETEST','VWAP_SESSION_PULLBACK','MACRO_TREND_CONFIRMATION')]
    elif regime == 'RANGING':
        preferred += [x for x in families if x in ('MEAN_REVERSION_SELECTIVE','SWEEP_MSS_POI','COMPRESSION_EXPANSION')]
    else:
        preferred += [x for x in families if x in ('SWEEP_MSS_POI','COMPRESSION_EXPANSION','BREAKOUT_RETEST')]
    if volatility == 'HIGH':
        preferred += [x for x in families if x in ('VOLATILITY_RETEST','POST_EVENT_CONFIRMATION','POST_MACRO_CONFIRMATION')]
    # Preserve order, no strategy is promoted by name alone; ReviewTrader still governs authority.
    preferred=list(dict.fromkeys(preferred))[:4]
    return {
        'bank_version':'MULTI_BANK_V1',
        'asset_class':meta['asset_class'],
        'symbol':meta['code'], 'timeframe':timeframe,
        'regime':regime, 'volatility_regime':volatility,
        'session':_market_session(meta['asset_class']),
        'families':families, 'preferred_for_context':preferred,
        'authority':'CONTEXT_ROUTING_ONLY_REVIEWTRADER_GOVERNS',
        'learning_cell':f"MULTI::{meta['asset_class']}::{meta['code']}::{timeframe}::{regime}::{volatility}",
    }


def _contract_spec(logical_symbol: str) -> Dict:
    meta=MULTIASSET_SYMBOLS.get(logical_symbol) or {}
    contract=meta.get('contract')
    base={'symbol':logical_symbol,'contract_symbol':contract,'verified':False,'status':'UNAVAILABLE','source':'KUCOIN_PUBLIC_CONTRACT'}
    if not contract:
        return {**base,'status':'CONTRACT_NOT_MAPPED'}
    now=time.monotonic()
    with _contract_lock:
        row=_contract_cache.get(contract)
        if row and now-row['stored_at'] < 3600:
            return dict(row['data'])
    try:
        r=_get_futures_http_session().get(KUCOIN_FUTURES_CONTRACT_URL.format(symbol=contract),timeout=4)
        _track_futures_network_response(r,'multi_contract_spec')
        r.raise_for_status(); payload=r.json()
        if str(payload.get('code')) != '200000':
            raise ValueError('KuCoin contract code '+str(payload.get('code')))
        d=payload.get('data') or {}
        def pos(k):
            v=_safe_float(d.get(k),0); return v if v>0 else None
        data={**base,'verified':bool(pos('maxLeverage') and pos('maintainMargin')),
              'max_leverage':pos('maxLeverage'),'maintenance_margin_rate':pos('maintainMargin'),
              'initial_margin_rate':pos('initialMargin'),'taker_fee_rate':pos('takerFeeRate'),
              'status':str(d.get('status') or 'UNKNOWN'),'mark_price':pos('markPrice')}
        with _contract_lock:
            _contract_cache[contract]={'stored_at':now,'data':dict(data)}
            while len(_contract_cache)>7:
                oldest=min(_contract_cache,key=lambda k:_contract_cache[k]['stored_at']); _contract_cache.pop(oldest,None)
        return data
    except Exception:
        return {**base,'status':'FETCH_FAILED'}


def _router_fetch(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    meta=MULTIASSET_SYMBOLS.get(symbol) or {}
    gran=MULTIASSET_GRANULARITY_MINUTES.get(timeframe)
    contract=meta.get('contract')
    if not contract or not gran:
        return None
    end=int(time.time())
    start=end-int(gran*60*(MULTIASSET_ROUTER_CANDLES+3))
    try:
        r=_get_futures_http_session().get(KUCOIN_FUTURES_KLINES_URL,params={'symbol':contract,'granularity':gran,'from':start*1000,'to':end*1000},timeout=4)
        _track_futures_network_response(r,'multi_router_ohlcv')
        r.raise_for_status(); payload=r.json()
        if str(payload.get('code')) != '200000': return None
        rows=payload.get('data') or []
        # Legacy KuCoin futures format: [time, open, high, low, close, volume, turnover]
        parsed=[]
        for row in rows:
            if not isinstance(row,(list,tuple)) or len(row)<6: continue
            parsed.append([pd.to_datetime(int(row[0]),unit='ms',utc=True),*[_safe_float(x) for x in row[1:6]]])
        if len(parsed)<30: return None
        df=pd.DataFrame(parsed,columns=['timestamp','open','high','low','close','volume']).sort_values('timestamp')
        return df.tail(MULTIASSET_ROUTER_CANDLES).reset_index(drop=True)
    except Exception:
        return None


def _router_score(df: pd.DataFrame) -> Dict:
    close=df['close']; high=df['high']; low=df['low']; vol=df['volume']
    ema12=close.ewm(span=12,adjust=False).mean(); ema26=close.ewm(span=26,adjust=False).mean()
    ret12=(close.iloc[-1]/close.iloc[-13]-1) if len(close)>13 and close.iloc[-13] else 0
    tr=pd.concat([(high-low),(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14).mean().iloc[-1]; atr_pct=(atr/close.iloc[-1]*100) if close.iloc[-1] else 0
    vol_ratio=(vol.iloc[-1]/max(1e-9,vol.tail(20).mean()))
    trend_strength=min(35, abs(ema12.iloc[-1]/max(1e-9,ema26.iloc[-1])-1)*2500)
    momentum=min(25,abs(ret12)*800)
    activity=min(20,max(0,(vol_ratio-0.6)*14))
    usable_vol=min(20,max(0,atr_pct*5))
    score=max(0,min(100,trend_strength+momentum+activity+usable_vol))
    direction='LONG_BIAS' if ema12.iloc[-1]>ema26.iloc[-1] and ret12>0 else ('SHORT_BIAS' if ema12.iloc[-1]<ema26.iloc[-1] and ret12<0 else 'MIXED')
    return {'score':round(score,1),'bias':direction,'atr_pct':round(atr_pct,3),'volume_ratio':round(vol_ratio,2),'last_price':round(float(close.iloc[-1]),8)}


def scan_opportunities(timeframe: str='4h', force: bool=False) -> List[Dict]:
    """Cheap sequential scanner. No Supabase, no LLM, no full committee."""
    if timeframe not in MULTIASSET_TIMEFRAMES: timeframe='4h'
    now=time.monotonic()
    with _router_lock:
        if (not force and _router_cache['timeframe']==timeframe and now-_router_cache['stored_at']<MULTIASSET_ROUTER_TTL_SECONDS):
            return [dict(x) for x in _router_cache['rows']]
    rows=[]
    for symbol,meta in MULTIASSET_SYMBOLS.items():
        df=_router_fetch(symbol,timeframe)
        if df is None: continue
        q=_router_score(df); macro=_macro_context_for_asset(meta)
        # Off-hours are not a veto: merely a quality penalty for synthetic index contracts.
        session=_market_session(meta['asset_class']); penalty=8 if 'OFFHOURS' in session or 'CLOSED' in session else 0
        macro_penalty=12 if macro.get('gate')=='WAIT_EVENT' else (4 if macro.get('gate')=='CAUTION' else 0)
        effective=max(0,round(q['score']-penalty-macro_penalty,1))
        rows.append({
            'symbol':symbol,'code':meta['code'],'display_name':meta['name'],'asset_class':meta['asset_class'],'group':meta['group'],
            'timeframe':timeframe,'router_score':effective,'raw_score':q['score'],'bias':q['bias'],
            'atr_pct':q['atr_pct'],'volume_ratio':q['volume_ratio'],'last_price':q['last_price'],
            'session':session,'macro_gate':macro.get('gate'),'deep_candidate':False,
        })
    rows.sort(key=lambda x:x['router_score'],reverse=True)
    for row in rows[:MULTIASSET_DEEP_LIMIT]: row['deep_candidate']=True
    with _router_lock:
        _router_cache.update({'stored_at':now,'timeframe':timeframe,'rows':[dict(x) for x in rows]})
    return rows


def _route_strategy_family(result: Dict, strategy: Dict, macro: Dict) -> Dict:
    """Deterministic market-specific strategy router; no LLM and no direction creation."""
    preferred=list(strategy.get('preferred_for_context') or [])
    blob=str({
        'message': result.get('message'),
        'levels': result.get('levels'),
        'structure': result.get('structure'),
        'patterns': result.get('patterns'),
    }).upper()
    scores={}
    for family in preferred:
        score=45.0
        if family == 'SWEEP_MSS_POI':
            score += 12 if 'SWEEP' in blob else 0; score += 12 if ('MSS' in blob or 'STRUCTURE' in blob) else 0; score += 8 if ('FVG' in blob or 'ORDER_BLOCK' in blob or 'POI' in blob) else 0
        elif family in ('TREND_PULLBACK','VWAP_SESSION_PULLBACK'):
            score += 18 if strategy.get('regime') == 'TRENDING' else 0; score += 10 if ('RETEST' in blob or 'PULLBACK' in blob or 'VWAP' in blob or 'EMA' in blob) else 0
        elif family == 'BREAKOUT_RETEST':
            score += 18 if ('BREAKOUT' in blob or 'RUPTURA' in blob) else 0; score += 8 if ('RETEST' in blob or 'RETROCESO' in blob) else 0
        elif family == 'COMPRESSION_EXPANSION':
            score += 15 if ('SQUEEZE' in blob or 'COMPRESSION' in blob or 'COMPRESI' in blob) else 0; score += 8 if strategy.get('volatility_regime') == 'HIGH' else 0
        elif family == 'MEAN_REVERSION_SELECTIVE':
            score += 18 if strategy.get('regime') == 'RANGING' else 0; score += 8 if ('RSI' in blob or 'BOLLINGER' in blob) else 0
        elif family in ('POST_EVENT_CONFIRMATION','POST_MACRO_CONFIRMATION'):
            score += 12 if macro.get('risk_level') in ('HIGH','CRITICAL') and macro.get('gate') != 'WAIT_EVENT' else 0
        scores[family]=min(100.0,score)
    selected=max(scores,key=scores.get) if scores else None
    return {
        'selected_family':selected,
        'confirmation_score':round(scores.get(selected,0.0),1) if selected else 0.0,
        'candidates':scores,
        'authority':'CONTEXT_FILTER_ONLY_INITIAL_V1',
        'creates_direction':False,
        'changes_entry_sl_tp':False,
        'learning_scope':strategy.get('learning_cell'),
    }


def _specialist_evaluation(meta: Dict, strategy: Dict, macro: Dict, result: Dict) -> Dict:
    asset_class=meta.get('asset_class')
    observations=[]
    if macro.get('gate')=='WAIT_EVENT': observations.append('Evento macro de alto impacto demasiado próximo para abrir una posición nueva.')
    elif macro.get('gate')=='CAUTION': observations.append('Riesgo macro elevado: exigir confirmación técnica completa y evitar perseguir precio.')
    session=str(strategy.get('session') or '')
    if 'CLOSED' in session or 'OFFHOURS' in session:
        observations.append('Subyacente fuera de su sesión principal: liquidez sintética penalizada por el Router.')
    regime=str(strategy.get('regime') or '')
    volatility=str(strategy.get('volatility_regime') or '')
    observations.append(f'Régimen {regime}; volatilidad {volatility}; banco prioriza {", ".join(strategy.get("preferred_for_context") or ["sin preferencia"])}.')
    if asset_class=='ENERGY': observations.append('Energy Specialist pondera shocks/eventos, volatilidad y retest; no extrapola parámetros BTC.')
    elif asset_class=='US_INDEX': observations.append('Equity Index Specialist pondera sesión, macro/tasas y calidad del pullback/VWAP.')
    elif asset_class in {'INDUSTRIAL_METAL','PRECIOUS_METAL'}: observations.append('Metals Specialist pondera ciclo macro/USD y estructura propia del metal.')
    elif asset_class=='CHINA_INDEX': observations.append('Asia/China Specialist pondera sesión asiática y riesgo macro/regulatorio.')
    return {
        'name':SPECIALIST_BY_CLASS.get(asset_class,'Multi-Asset Specialist'),
        'macro_specialist':'Macro / Intermarket Specialist',
        'mode':'CONTEXT_AND_VETO_ONLY','changes_direction':False,
        'observations':observations[:5],
        'entry_policy':'Liquidity>Sweep>MSS>Displacement>POI>Entry',
    }


class MultiAssetAnalysis(FuturesAnalysis):
    """Futures execution engine with Multi-Asset market semantics."""
    def _market_label(self): return 'MULTI-ACTIVO'
    def _market_symbols(self): return MULTIASSET_SYMBOLS
    def _market_all_symbols(self): return MULTIASSET_SYMBOLS
    def _market_timeframes(self): return MULTIASSET_TIMEFRAMES
    def _market_timeframe_allowed(self,symbol,timeframe): return symbol in MULTIASSET_SYMBOLS and timeframe in MULTIASSET_TIMEFRAMES
    def _market_contract_symbols(self): return MULTIASSET_CONTRACT_SYMBOLS
    def _market_granularity_minutes(self): return MULTIASSET_GRANULARITY_MINUTES
    def _market_timeframe_seconds(self): return MULTIASSET_TIMEFRAME_SECONDS
    def _market_data_source(self): return 'KUCOIN_FUTURES_PERPETUAL_REST'
    def _get_contract_risk_spec(self,symbol): return _contract_spec(symbol)

    def _analyze_futures_microstructure(self, symbol: str, action: str) -> Dict:
        # Deliberately lightweight: Multi-Asset does not download orderbook +
        # trades + OI + funding on every candidate. Price/volume structure and
        # the common Entry engine remain authoritative. This saves bandwidth/RAM.
        return {
            'available':False,'model_version':'MULTI_LIGHT_MICRO_V1','mode':'RESOURCE_GUARDED_PROXY',
            'calibrated':False,'affects_entry':False,'affects_safety':False,
            'affects_publication':False,'affects_leverage':False,
            'quality_score_status':'NO_EXTRA_ORDERBOOK_REQUESTS',
            'action_evaluated':str(action or '').upper(),
            'reason':'Commit 12 evita descargas adicionales de order book/trades en el ciclo automático.',
        }

    def _post_market_analysis_hook(self, result, symbol, timeframe):
        if not isinstance(result,dict) or not result.get('success',True): return result
        meta=MULTIASSET_SYMBOLS.get(symbol) or {}
        macro=_macro_context_for_asset(meta)
        strategy=_strategy_context(meta,timeframe,result)
        result['is_multiasset']=True
        result['market']='multiasset'; result['market_segment']='MULTIASSET'
        result['asset_class']=meta.get('asset_class'); result['display_name']=meta.get('name',symbol)
        result['multiasset_version']=MULTIASSET_VERSION
        result['multiasset_macro']=macro
        result['multiasset_specialist']=_specialist_evaluation(meta,strategy,macro,result)
        result['multiasset_strategy_bank']=strategy
        result['multiasset_strategy_route']=_route_strategy_family(result,strategy,macro)
        context=dict(result.get('context') or {})
        context.update({'market_segment':'MULTIASSET','asset_class':meta.get('asset_class'),'multiasset_strategy_bank':strategy,'multiasset_strategy_route':result.get('multiasset_strategy_route'),'multiasset_macro':macro})
        result['context']=context

        # Imminent macro event only prevents a NEW executable publication.
        # Entry/SL/TP/direction stay untouched and the analysis remains useful
        # as evidence/Shadow material.
        if macro.get('gate')=='WAIT_EVENT':
            action=str((result.get('decision') or {}).get('action') or '').upper()
            if action in {'LONG','SHORT'}:
                result['publication_eligible']=False; result['is_executable']=False
                result['publication_status']='WAIT_EVENT'
                result['rejected_reason']='MULTI_MACRO_EVENT_RISK'
                levels=dict(result.get('levels') or {})
                levels.update({'publication_eligible':False,'is_executable':False,'publication_status':'WAIT_EVENT'})
                result['levels']=levels
                gate=dict(result.get('futures_publication_gate') or {})
                reasons=list(gate.get('reasons') or [])
                if 'MULTI_MACRO_EVENT_RISK' not in reasons: reasons.append('MULTI_MACRO_EVENT_RISK')
                gate.update({'eligible':False,'status':'WAIT_EVENT','reasons':reasons,'market_gate':'MACRO_EVENT'})
                result['futures_publication_gate']=gate
        return result

    def analyze_multiasset_market(self,symbol,timeframe,**kwargs):
        return self.analyze_futures_market(symbol,timeframe,**kwargs)


def universe_payload() -> Dict:
    groups={g:{'symbols':[s for s,m in MULTIASSET_SYMBOLS.items() if m['group']==g],'timeframes':list(MULTIASSET_TIMEFRAMES)} for g in MULTIASSET_GROUP_ORDER}
    return {
        'success':True,'version':MULTIASSET_VERSION,'enabled':MULTIASSET_ENABLED,
        'group_order':list(MULTIASSET_GROUP_ORDER),'group_labels':dict(MULTIASSET_GROUP_LABELS),
        'groups':groups,'symbols':{s:{**m,'timeframes':list(MULTIASSET_TIMEFRAMES)} for s,m in MULTIASSET_SYMBOLS.items()},
        'timeframes':dict(MULTIASSET_TIMEFRAMES),
        'resource_policy':{
            'router':'SEQUENTIAL_NO_DB_NO_LLM','deep_limit':MULTIASSET_DEEP_LIMIT,'auto_deep_daily_max':MULTIASSET_AUTO_DEEP_DAILY_MAX,
            'auto_ai_calls':0,'scanner_supabase_writes':0,'extra_worker_threads':0,
            'macro_source':'SHARED_EXISTING_CACHE',
        }
    }

multiasset_system = MultiAssetAnalysis()
