"""C46 proposal: causal countertrend hypotheses, no LIVE publishing authority.

This is deliberately isolated from SmartTradingReview's nine specialists,
Entry/SL/TP committees, Safety, Guardian and dispatch. It consumes historical
CLOSED OHLCV only, makes no HTTP calls, performs no ML fitting, and returns
hypotheses (not production recommendations).
"""
from __future__ import annotations
from typing import Mapping, Sequence
import math

VERSION='C46_COUNTERTREND_PROPOSAL_V1'
TF={'30m','1h','2h','4h'}

def _num(x):
    try:
        f=float(x)
        return f if math.isfinite(f) else 0.0
    except (TypeError,ValueError,OverflowError):
        return 0.0

def _ema(values, length):
    alpha=2.0/(length+1)
    curr=values[0]
    for v in values[1:]:curr=alpha*v+(1-alpha)*curr
    return curr

def _rsi_series(prices, period=14):
    out=[50.0]*len(prices)
    if len(prices)<period+1:return out
    dif=[prices[i]-prices[i-1] for i in range(1,len(prices))]
    up=sum(max(v,0) for v in dif[:period])/period
    dn=sum(max(-v,0) for v in dif[:period])/period
    for i in range(period,len(prices)):
        if i>period:
            delta=dif[i-1]
            up=(up*(period-1)+max(delta,0))/period
            dn=(dn*(period-1)+max(-delta,0))/period
        out[i]=100.0 if dn==0 and up>0 else (50.0 if dn==0 else 100.0-100.0/(1.0+up/dn))
    return out

def _swing_indexes(prices, side, radius=2):
    """Only confirmed pivots: never use any candle beyond last closed bar."""
    out=[]
    for i in range(radius,len(prices)-radius):
        left=prices[i-radius:i]
        right=prices[i+1:i+radius+1]
        if side=='low' and prices[i] < min(left) and prices[i]<=min(right):out.append(i)
        if side=='high' and prices[i] > max(left) and prices[i]>=max(right):out.append(i)
    return out

def detect(closed_candles: Sequence[Mapping], *, symbol: str,
           timeframe: str, market: str='futures') -> list[dict]:
    """Detections at the close of the LAST provided bar; no future information.

    Candidate evidence needs a sweep, an independent momentum divergence,
    a confirmed local structure reclaim/loss and meaningful volume. Countertrend
    alignment is intrinsic, but not a claim of profitable backtest evidence.
    """
    if timeframe not in TF or market not in {'futures','multiasset'}:
        return []
    if closed_candles is None or len(closed_candles)<115:return []
    x=closed_candles[-130:]
    try:
        o=[_num(r['open']) for r in x]; h=[_num(r['high']) for r in x]
        l=[_num(r['low']) for r in x]; c=[_num(r['close']) for r in x]
        v=[_num(r.get('volume')) for r in x]
    except (KeyError,TypeError):return []
    if any(lo<=0 or hi<max(op,cl) or lo>min(op,cl) for op,hi,lo,cl in zip(o,h,l,c)):
        return []
    n=len(c)
    true_ranges=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,n)]
    atr=sum(true_ranges[-14:])/14
    if atr<=0 or atr/c[-1]>0.14:return []
    recent_vol=sorted(v[-31:-1])[15]
    if recent_vol<=0 or sum(v[-3:])/3 < 0.8*recent_vol:return []
    rsi=_rsi_series(c)
    ema_fast=_ema(c[-95:],20);ema_slow=_ema(c[-115:],50)
    # Sweep must precede the structural confirmation and be at most six bars old.
    # Reference band excludes ALL candidate sweep and confirmation bars.
    floor=min(l[-27:-7]);ceiling=max(h[-27:-7])
    candidates=[]
    confirmed_lows=_swing_indexes(l,'low')
    confirmed_highs=_swing_indexes(h,'high')
    for direction, sweep_indexes, pivots, context, rejection in (
        ('LONG', [i for i in range(n-6,n-2) if l[i]<floor-0.08*atr and c[i]>floor], confirmed_lows, ema_fast<ema_slow, 'floor'),
        ('SHORT',[i for i in range(n-6,n-2) if h[i]>ceiling+0.08*atr and c[i]<ceiling],confirmed_highs,ema_fast>ema_slow,'ceiling'),
    ):
        if not context or not sweep_indexes:continue
        idx=sweep_indexes[-1]
        # A pivot must be confirmed before the sweep, so RSI comparison is causal.
        earlier=[j for j in pivots if 6<=idx-j<=29]
        if not earlier:continue
        anchor=earlier[-1]
        if direction=='LONG':
            divergence=l[idx]<l[anchor] and rsi[idx]>=rsi[anchor]+3
            break_ok=c[-1]>max(h[idx: n-1]) and c[-1]>o[-1] and c[-1]>floor
            sl=l[idx]-0.25*atr
            invalidate=c[-1]<=sl
        else:
            divergence=h[idx]>h[anchor] and rsi[idx]<=rsi[anchor]-3
            break_ok=c[-1]<min(l[idx:n-1]) and c[-1]<o[-1] and c[-1]<ceiling
            sl=h[idx]+0.25*atr
            invalidate=c[-1]>=sl
        if not (divergence and break_ok) or invalidate:continue
        # Prices are diagnostic invalidation levels, NOT committee Entry/SL/TP.
        candidates.append({
            'version':VERSION, 'family':('FLOOR_SWEEP_DIVERGENCE_MSS' if direction=='LONG'
                                        else 'CEILING_SWEEP_DIVERGENCE_MSS'),
            'market':market,'symbol':symbol,'timeframe':timeframe,
            'action':direction, 'publication_status':'UNVALIDATED_HYPOTHESIS',
            'source_candle_closed':True,
            'invalidating_price_reference':round(sl,8),
            'reference_price':round(c[-1],8),
            'risk_unit_reference':round(abs(c[-1]-sl),8),
            'evidence':{'rejection':rejection,'sweep_bar_offset':idx-(n-1),
                'anchor_bar_offset':anchor-(n-1),'rsi_sweep':round(rsi[idx],2),
                'rsi_anchor':round(rsi[anchor],2),'confirmed_structure':True,
                'volume_ratio_proxy':round((sum(v[-3:])/3)/recent_vol,3),
                'opposite_ema_context':True},
            'requires_original_entry_sl_tp_safety':True,
            'live_authority':False,
        })
    return candidates
