"""Reproducible chronological IS/OOS backtest for Commit 33.3 30m research strategies.
Input CSV: timestamp,open,high,low,close,volume. No look-ahead. Entry next bar open.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np, pandas as pd
from strategies_commit33_3 import STRATEGY_NAMES, signal

def _metrics(rs):
    a=np.asarray(rs,dtype=float); n=len(a)
    if not n: return {'n':0,'expectancy_r':0,'pf':0,'win_rate':0,'net_r':0,'max_dd_r':0}
    pos=a[a>0].sum(); neg=-a[a<0].sum(); eq=np.cumsum(a); peak=np.maximum.accumulate(np.r_[0,eq]); dd=np.r_[0,eq]-peak
    return {'n':n,'expectancy_r':round(float(a.mean()),4),'pf':round(float(pos/neg),3) if neg>0 else 99.0,'win_rate':round(float((a>0).mean()*100),2),'net_r':round(float(a.sum()),3),'max_dd_r':round(float(-dd.min()),3)}

def run_trades(df,name,start=0,end=None,rr=1.8,hold=16,cost_r=.04):
    sig,x=signal(df,name); end=len(x) if end is None else min(end,len(x)); out=[]; i=max(120,start)
    while i<end-1:
        d=int(sig.iloc[i])
        if d==0: i+=1; continue
        entry=float(x.open.iloc[i+1]); atr=float(x.atr.iloc[i]);
        if not (entry>0 and atr>0 and math.isfinite(atr)): i+=1; continue
        risk=1.15*atr; sl=entry-d*risk; tp=entry+d*risk*rr; result=None; exit_i=min(end-1,i+1+hold)
        for j in range(i+1,exit_i+1):
            hi,lo=float(x.high.iloc[j]),float(x.low.iloc[j]); hit_tp=(hi>=tp if d>0 else lo<=tp); hit_sl=(lo<=sl if d>0 else hi>=sl)
            if hit_tp and hit_sl: result=-1.0-cost_r; exit_i=j; break # conservative same-bar rule
            if hit_sl: result=-1.0-cost_r; exit_i=j; break
            if hit_tp: result=rr-cost_r; exit_i=j; break
        if result is None:
            close=float(x.close.iloc[exit_i]); result=d*(close-entry)/risk-cost_r
        out.append(float(result)); i=exit_i+1
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv',nargs='+'); ap.add_argument('--out',default='BACKTEST_COMMIT33_3_RESULT.json'); args=ap.parse_args()
    rows=[]
    for f in args.csv:
        df=pd.read_csv(f)
        if 'timestamp' not in df and 'open_time' in df: df=df.rename(columns={'open_time':'timestamp'})
        split=int(len(df)*.70)
        for name in STRATEGY_NAMES:
            ins=run_trades(df,name,0,split); oos=run_trades(df,name,split,len(df))
            mi,mo=_metrics(ins),_metrics(oos)
            passed=mi['n']>=50 and mo['n']>=30 and mi['expectancy_r']>0 and mo['expectancy_r']>0 and mi['pf']>=1.05 and mo['pf']>=1.05
            rows.append({'dataset':Path(f).name,'strategy':name,'is':mi,'oos':mo,'pass_live':bool(passed)})
    payload={'version':'COMMIT33_3_BACKTEST_30M_V2','split':'70/30 chronological','entry':'next bar open','same_bar_tp_sl':'SL conservative','minimum_timeframe':'30m','rows':rows}
    Path(args.out).write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))
if __name__=='__main__': main()
