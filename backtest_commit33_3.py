"""Chronological IS/selection/OOS research backtester for SmartTradingReview.

This script never grants LIVE authority by itself and is not imported by the
web service.  It is designed for *real* OHLCV files and evaluates each allowed
symbol/timeframe cell independently, then applies cross-asset stability gates.

Input naming recommendation: BTC-USDT__30m.csv (timestamp,open,high,low,close,volume)
When 30m source files are supplied, --resample-all evaluates the allowed higher
TFs without downloading extra data.
"""
from __future__ import annotations

import argparse, hashlib, json, math, re
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

from strategies_commit33_3 import (
    STRATEGY_NAMES, PANEL_STRATEGY_NAMES, signal, features,
    cross_sectional_relative_strength, strategy_applicable,
)
try:
    from futures_universe import timeframe_allowed as _production_timeframe_allowed
except Exception:
    def _production_timeframe_allowed(symbol, timeframe): return True

TF_RULE = {'30m':'30min','1h':'1h','2h':'2h','4h':'4h','12h':'12h','1D':'1D'}
DEFAULT_TFS = ('30m','1h','2h','4h','12h','1D')
PARAM_GRID = (
    {'rr':1.6,'risk_atr':1.05,'hold':12},
    {'rr':1.8,'risk_atr':1.10,'hold':16},
    {'rr':2.0,'risk_atr':1.15,'hold':20},
    {'rr':2.2,'risk_atr':1.20,'hold':24},
)


def _metrics(rs: List[float]) -> dict:
    a = np.asarray(rs, dtype=float); n = len(a)
    if not n:
        return {'n':0,'expectancy_r':0.0,'pf':0.0,'win_rate':0.0,'net_r':0.0,'max_dd_r':0.0,'trade_sharpe':0.0}
    pos = a[a>0].sum(); neg = -a[a<0].sum(); eq = np.cumsum(a)
    peak = np.maximum.accumulate(np.r_[0,eq]); dd = np.r_[0,eq]-peak
    std = float(a.std())
    return {
        'n':int(n), 'expectancy_r':round(float(a.mean()),4),
        'pf':round(float(pos/neg),3) if neg>0 else 99.0,
        'win_rate':round(float((a>0).mean()*100),2),
        'net_r':round(float(a.sum()),3), 'max_dd_r':round(float(-dd.min()),3),
        'trade_sharpe':round(float(a.mean()/std),3) if std>1e-12 else 0.0,
    }


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    if 'timestamp' not in x and 'open_time' in x: x = x.rename(columns={'open_time':'timestamp'})
    need = {'timestamp','open','high','low','close','volume'}
    missing = need-set(x.columns)
    if missing: raise ValueError(f'missing columns: {sorted(missing)}')
    x['timestamp'] = pd.to_datetime(x.timestamp, utc=True, errors='coerce')
    for c in ['open','high','low','close','volume']: x[c] = pd.to_numeric(x[c], errors='coerce')
    return x.dropna(subset=['timestamp','open','high','low','close']).sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)


def _resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    if tf == '30m': return _clean(df)
    rule = TF_RULE[tf]
    x = _clean(df).set_index('timestamp')
    y = x.resample(rule, label='left', closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    return y.reset_index()


def _infer_symbol(path: Path) -> str:
    stem = path.stem.upper().replace('_30M','').replace('__30M','')
    m = re.search(r'([A-Z0-9]+[-_/]USDT)', stem)
    return (m.group(1).replace('_','-').replace('/','-') if m else stem.split('__')[0].replace('_','-'))


def _fingerprint(paths: List[Path]) -> str:
    h=hashlib.sha256()
    for p in sorted(paths, key=lambda z:str(z)):
        h.update(str(p.name).encode()); h.update(str(p.stat().st_size).encode()); h.update(str(int(p.stat().st_mtime)).encode())
    return h.hexdigest()[:20]


def _trade_returns_x(x: pd.DataFrame, sig: pd.Series, start: int, end: int, *, rr: float, risk_atr: float, hold: int, cost_r: float) -> List[float]:
    end = min(end, len(x)); out=[]; i=max(120,start)
    while i < end-1:
        d=int(sig.iloc[i])
        if d == 0: i += 1; continue
        entry=float(x.open.iloc[i+1]); atr=float(x.atr.iloc[i])
        if not (entry>0 and atr>0 and math.isfinite(atr)): i += 1; continue
        risk=risk_atr*atr; sl=entry-d*risk; tp=entry+d*risk*rr
        result=None; exit_i=min(end-1, i+1+hold)
        for j in range(i+1, exit_i+1):
            hi,lo=float(x.high.iloc[j]),float(x.low.iloc[j])
            hit_tp=(hi>=tp if d>0 else lo<=tp); hit_sl=(lo<=sl if d>0 else hi>=sl)
            if hit_tp and hit_sl: result=-1.0-cost_r; exit_i=j; break
            if hit_sl: result=-1.0-cost_r; exit_i=j; break
            if hit_tp: result=rr-cost_r; exit_i=j; break
        if result is None:
            close=float(x.close.iloc[exit_i]); result=d*(close-entry)/risk-cost_r
        out.append(float(result)); i=exit_i+1
    return out

def _split(n: int) -> Tuple[int,int]:
    # 60% model selection IS, 20% untouched selection check, final 20% OOS.
    return int(n*.60), int(n*.80)


def _select_params(x: pd.DataFrame, sig: pd.Series, cost_r: float) -> Tuple[dict,dict,dict]:
    a,b=_split(len(x)); candidates=[]
    for cfg in PARAM_GRID:
        is_m=_metrics(_trade_returns_x(x,sig,0,a,cost_r=cost_r,**cfg))
        sel_m=_metrics(_trade_returns_x(x,sig,a,b,cost_r=cost_r,**cfg))
        score=(min(is_m['expectancy_r'],sel_m['expectancy_r']), min(is_m['pf'],sel_m['pf']), is_m['n']+sel_m['n'])
        candidates.append((score,cfg,is_m,sel_m))
    candidates.sort(key=lambda z:z[0], reverse=True)
    _,cfg,is_m,sel_m=candidates[0]
    oos_m=_metrics(_trade_returns_x(x,sig,b,len(x),cost_r=cost_r,**cfg))
    return cfg, {'is':is_m,'selection':sel_m}, oos_m

def _pass_cell(pre: dict, oos: dict) -> bool:
    # OOS is never tuned.  Small samples stay Research regardless of headline PF.
    return bool(
        pre['is']['n'] >= 35 and pre['selection']['n'] >= 12 and oos['n'] >= 12
        and pre['is']['expectancy_r'] > 0.03 and pre['selection']['expectancy_r'] > 0
        and oos['expectancy_r'] > 0.05 and oos['pf'] >= 1.10
        and oos['max_dd_r'] <= 10.0
    )


def _strategy_stability(rows: List[dict], name: str) -> dict:
    cells=[r for r in rows if r['strategy']==name and r.get('applicable')]
    tested=[r for r in cells if r['oos']['n']>0]
    passed=[r for r in tested if r['pass_cell']]
    total_oos=sum(r['oos']['n'] for r in tested)
    weighted=(sum(r['oos']['expectancy_r']*r['oos']['n'] for r in tested)/total_oos) if total_oos else 0
    pos=sum(1 for r in tested if r['oos']['expectancy_r']>0)
    return {
        'strategy':name,'tested_cells':len(tested),'passed_cells':len(passed),
        'positive_oos_cells':pos,'positive_oos_ratio':round(pos/max(1,len(tested)),3),
        'oos_n_total':total_oos,'weighted_oos_expectancy_r':round(weighted,4),
        # Promotion is exact-cell only; the global gate prevents one lucky asset
        # from authorising a strategy family everywhere.
        'family_stable': bool(len(tested)>=6 and len(passed)>=3 and pos/max(1,len(tested))>=0.55 and weighted>0.03),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('csv', nargs='+', help='Real 30m OHLCV files, one per symbol')
    ap.add_argument('--out', default='BACKTEST_COMMIT33_4_6_RESULT.json')
    ap.add_argument('--cost-r', type=float, default=.05, help='Round-trip fees+slippage expressed in R')
    ap.add_argument('--timeframes', default=','.join(DEFAULT_TFS))
    args=ap.parse_args()
    paths=[Path(p) for p in args.csv]
    raw={_infer_symbol(p):_clean(pd.read_csv(p)) for p in paths}
    tfs=[x.strip() for x in args.timeframes.split(',') if x.strip()]
    rows=[]

    per_tf: Dict[str,Dict[str,pd.DataFrame]]={}
    for tf in tfs:
        per_tf[tf]={sym:_resample(df,tf) for sym,df in raw.items()}
        for sym,df in per_tf[tf].items():
            if not _production_timeframe_allowed(sym, tf):
                continue
            if len(df)<180: continue
            for name in STRATEGY_NAMES:
                applicable=strategy_applicable(name,tf)
                if not applicable:
                    rows.append({'symbol':sym,'timeframe':tf,'strategy':name,'applicable':False,'reason':'TIMEFRAME_NOT_APPLICABLE','pass_cell':False,'is':_metrics([]),'selection':_metrics([]),'oos':_metrics([])})
                    continue
                sig,x=signal(df,name,timeframe=tf)
                cfg,pre,oos=_select_params(x,sig,args.cost_r)
                rows.append({'symbol':sym,'timeframe':tf,'strategy':name,'applicable':True,'params':cfg,**pre,'oos':oos,'pass_cell':_pass_cell(pre,oos)})

        # Cross-sectional strategy is evaluated only if >=4 symbols align.
        if strategy_applicable('CROSS_SECTIONAL_RELATIVE_STRENGTH',tf) and len(per_tf[tf])>=4:
            panel_sig=cross_sectional_relative_strength(per_tf[tf], timeframe=tf)
            for sym,df in per_tf[tf].items():
                if not _production_timeframe_allowed(sym, tf): continue
                if len(df)<180 or sym not in panel_sig: continue
                x=features(df,timeframe=tf)
                cfg,pre,oos=_select_params(x,panel_sig[sym],args.cost_r)
                rows.append({'symbol':sym,'timeframe':tf,'strategy':'CROSS_SECTIONAL_RELATIVE_STRENGTH','applicable':True,'params':cfg,**pre,'oos':oos,'pass_cell':_pass_cell(pre,oos)})

    names=list(STRATEGY_NAMES)+list(PANEL_STRATEGY_NAMES)
    stability=[_strategy_stability(rows,n) for n in names]
    stable={r['strategy'] for r in stability if r['family_stable']}
    promotions=[
        {'symbol':r['symbol'],'timeframe':r['timeframe'],'strategy':r['strategy'],'params':r.get('params'),'oos':r['oos']}
        for r in rows if r.get('pass_cell') and r['strategy'] in stable
    ]
    payload={
        'version':'COMMIT33_4_6_RESEARCH_BACKTEST_V1',
        'data_kind':'REAL_OHLCV_REQUIRED',
        'data_fingerprint':_fingerprint(paths),
        'split':'60/20/20 chronological (IS/selection/OOS)',
        'entry':'next bar open','same_bar_tp_sl':'SL conservative','cost_r':args.cost_r,
        'rows':rows,'strategy_stability':stability,'promotion_candidates':promotions,
        'governance':{
            'live_authority_from_this_file':False,
            'rule':'Only exact cells in promotion_candidates may be reviewed for LIVE integration; OOS is never used for parameter selection.',
            'alpha_decay':'8 consecutive resolved LIVE losses -> SHADOW/blocked; recent-8 deterioration also triggers decay governance.',
        },
    }
    Path(args.out).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps({'rows':len(rows),'promotion_candidates':len(promotions),'strategy_stability':stability},indent=2))

if __name__=='__main__':
    main()
