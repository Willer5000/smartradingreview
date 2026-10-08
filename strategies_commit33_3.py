"""Commit 33.3: six deterministic 30m research strategies.
No strategy has production authority unless a reproducible IS/OOS report passes.
"""
from __future__ import annotations
import numpy as np, pandas as pd

STRATEGY_NAMES=(
 'CRT_RANGE_RECLAIM','FAILED_AUCTION','OPENING_RANGE_VWAP',
 'TRIPLE_RSI','EFFICIENCY_RATIO','VOLATILITY_COMPRESSION_RELEASE')

def _rsi(s,n):
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    rs=up/dn.replace(0,np.nan); return (100-100/(1+rs)).fillna(50)

def _atr(df,n=14):
    pc=df.close.shift(1); tr=pd.concat([(df.high-df.low).abs(),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def features(df):
    x=df.copy().reset_index(drop=True)
    for c in ['open','high','low','close','volume']: x[c]=pd.to_numeric(x[c],errors='coerce')
    x['atr']=_atr(x); x['rsi7']=_rsi(x.close,7); x['rsi14']=_rsi(x.close,14); x['rsi28']=_rsi(x.close,28)
    x['ema20']=x.close.ewm(span=20,adjust=False).mean(); x['ema50']=x.close.ewm(span=50,adjust=False).mean()
    change=(x.close-x.close.shift(20)).abs(); vol=x.close.diff().abs().rolling(20).sum(); x['er20']=(change/vol.replace(0,np.nan)).fillna(0)
    mid=x.close.rolling(20).mean(); sd=x.close.rolling(20).std(); x['bb_u']=mid+2*sd; x['bb_l']=mid-2*sd; x['bb_w']=((x.bb_u-x.bb_l)/mid.replace(0,np.nan)).fillna(0)
    tp=(x.high+x.low+x.close)/3; x['vwap_roll']=(tp*x.volume).rolling(32).sum()/x.volume.rolling(32).sum().replace(0,np.nan)
    x['prev20h']=x.high.shift(1).rolling(20).max(); x['prev20l']=x.low.shift(1).rolling(20).min()
    return x

def signal(df,name):
    x=features(df); sig=pd.Series(0,index=x.index,dtype=int)
    if name=='CRT_RANGE_RECLAIM':
        ph=x.high.shift(1).rolling(8).max(); pl=x.low.shift(1).rolling(8).min()
        sig[(x.low<pl)&(x.close>pl)&(x.close>x.open)]=1
        sig[(x.high>ph)&(x.close<ph)&(x.close<x.open)]=-1
    elif name=='FAILED_AUCTION':
        sig[(x.high>x.prev20h)&(x.close<x.prev20h)&((x.high-x.close)>0.6*x.atr)]=-1
        sig[(x.low<x.prev20l)&(x.close>x.prev20l)&((x.close-x.low)>0.6*x.atr)]=1
    elif name=='OPENING_RANGE_VWAP':
        # UTC 2-bar (1 hour) opening range for 30m research; deterministic and timezone-neutral.
        t=pd.to_datetime(x.get('timestamp',x.index),utc=True,errors='coerce')
        if t.notna().any():
            day=t.dt.floor('D'); rank=t.groupby(day).cumcount(); orh=x.high.where(rank<2).groupby(day).transform('max'); orl=x.low.where(rank<2).groupby(day).transform('min')
            sig[(rank>=2)&(x.close>orh)&(x.close>x.vwap_roll)]=1; sig[(rank>=2)&(x.close<orl)&(x.close<x.vwap_roll)]=-1
    elif name=='TRIPLE_RSI':
        sig[(x.rsi7>x.rsi14)&(x.rsi14>x.rsi28)&(x.rsi14>52)&(x.ema20>x.ema50)]=1
        sig[(x.rsi7<x.rsi14)&(x.rsi14<x.rsi28)&(x.rsi14<48)&(x.ema20<x.ema50)]=-1
    elif name=='EFFICIENCY_RATIO':
        sig[(x.er20>0.35)&(x.ema20>x.ema50)&(x.close>x.high.shift(1).rolling(10).max())]=1
        sig[(x.er20>0.35)&(x.ema20<x.ema50)&(x.close<x.low.shift(1).rolling(10).min())]=-1
    elif name=='VOLATILITY_COMPRESSION_RELEASE':
        q=x.bb_w.shift(1).rolling(100).quantile(.2); compressed=x.bb_w.shift(1)<q
        sig[compressed&(x.close>x.bb_u.shift(1))&(x.atr>x.atr.shift(1)*1.05)]=1
        sig[compressed&(x.close<x.bb_l.shift(1))&(x.atr>x.atr.shift(1)*1.05)]=-1
    return sig, x
