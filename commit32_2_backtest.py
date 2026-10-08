"""Reproducible IS/OOS backtest harness for Commit 32.2 candidate techniques.

Input: CSV with time/open/high/low/close/volume. Chronological 70/30 split.
No OOS tuning. Costs are deducted from every resolved trade.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import pandas as pd


def rsi(s, n):
    d=s.diff(); up=d.clip(lower=0); dn=(-d.clip(upper=0))
    au=up.ewm(alpha=1/n, adjust=False).mean(); ad=dn.ewm(alpha=1/n, adjust=False).mean()
    rs=au/ad.replace(0, float('nan'))
    return 100-(100/(1+rs))

def atr(df,n=14):
    pc=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def triple_rsi_signals(df):
    x=df.copy(); x['r5']=rsi(x.close,5); x['r14']=rsi(x.close,14); x['r21']=rsi(x.close,21); x['ema50']=x.close.ewm(span=50,adjust=False).mean(); x['atr']=atr(x)
    long=(x.r5>x.r14)&(x.r14>x.r21)&(x.r21>50)&(x.close>x.ema50)&~((x.r5.shift(1)>x.r14.shift(1))&(x.r14.shift(1)>x.r21.shift(1)))
    short=(x.r5<x.r14)&(x.r14<x.r21)&(x.r21<50)&(x.close<x.ema50)&~((x.r5.shift(1)<x.r14.shift(1))&(x.r14.shift(1)<x.r21.shift(1)))
    return x,long,short

def crt_signals(df, lookback=8):
    x=df.copy(); x['atr']=atr(x); hi=x.high.shift(1).rolling(lookback).max(); lo=x.low.shift(1).rolling(lookback).min()
    long=(x.low<lo)&(x.close>lo)&(x.close<hi)
    short=(x.high>hi)&(x.close<hi)&(x.close>lo)
    x['crt_hi']=hi; x['crt_lo']=lo
    return x,long,short

def trades(df, long_sig, short_sig, rr=1.8, cost_r=0.04, max_bars=12, start_index=60):
    out=[]; n=len(df)
    for i in range(max(1, int(start_index)), n-1):
        side=1 if bool(long_sig.iloc[i]) else (-1 if bool(short_sig.iloc[i]) else 0)
        if not side: continue
        entry=float(df.open.iloc[i+1]); a=float(df.atr.iloc[i]) if 'atr' in df else 0
        if not math.isfinite(a) or a<=0: continue
        risk=max(a,entry*0.002)
        sl=entry-side*risk; tp=entry+side*risk*rr; result=None
        for j in range(i+1,min(n,i+1+max_bars)):
            h=float(df.high.iloc[j]); l=float(df.low.iloc[j])
            hit_tp=h>=tp if side>0 else l<=tp; hit_sl=l<=sl if side>0 else h>=sl
            if hit_tp and hit_sl: result=-1.0-cost_r; break
            if hit_sl: result=-1.0-cost_r; break
            if hit_tp: result=rr-cost_r; break
        if result is None:
            exitp=float(df.close.iloc[min(n-1,i+max_bars)])
            result=side*(exitp-entry)/risk-cost_r
        out.append(result)
    return out

def metrics(rs):
    if not rs: return {'trades':0,'expectancy_r':0,'profit_factor':0,'win_rate':0,'net_r':0,'max_drawdown_r':0}
    wins=[x for x in rs if x>0]; losses=[x for x in rs if x<0]; gp=sum(wins); gl=-sum(losses); eq=0; peak=0; dd=0
    for x in rs: eq+=x; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {'trades':len(rs),'expectancy_r':round(sum(rs)/len(rs),4),'profit_factor':round(gp/gl,4) if gl else 99.0,'win_rate':round(100*len(wins)/len(rs),2),'net_r':round(sum(rs),4),'max_drawdown_r':round(dd,4)}

def run(path,strategy):
    df=pd.read_csv(path); df.columns=[c.lower() for c in df.columns]
    for c in ['open','high','low','close','volume']: df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['open','high','low','close']).reset_index(drop=True)
    split=max(100,int(len(df)*0.70))
    if strategy=='crt': x,l,s=crt_signals(df)
    else: x,l,s=triple_rsi_signals(df)
    # IS is evaluated only on bars strictly before the chronological split.
    is_x=x.iloc[:split].reset_index(drop=True); is_l=l.iloc[:split].reset_index(drop=True); is_s=s.iloc[:split].reset_index(drop=True)
    isr=trades(is_x,is_l,is_s,start_index=60)

    # OOS receives an 80-bar indicator warm-up, but signals are forbidden until
    # the original split index. This avoids IS->OOS opportunity leakage while
    # keeping rolling indicators properly initialized.
    warm_start=max(0,split-80)
    ox=x.iloc[warm_start:].reset_index(drop=True); ol=l.iloc[warm_start:].reset_index(drop=True); osig=s.iloc[warm_start:].reset_index(drop=True)
    oos_start=split-warm_start
    oos=trades(ox,ol,osig,start_index=oos_start)
    return {'strategy':strategy,'rows':len(df),'split_index':split,'chronological_split':True,'rules_frozen_before_oos':True,'costs_included':True,'in_sample':metrics(isr),'out_of_sample':metrics(oos)}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--csv',required=True); ap.add_argument('--strategy',choices=['crt','triple_rsi'],required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args(); r=run(a.csv,a.strategy); Path(a.out).write_text(json.dumps(r,indent=2),encoding='utf-8'); print(json.dumps(r,indent=2))
