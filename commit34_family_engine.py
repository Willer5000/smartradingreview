"""Commit 34: four causal, bounded, supplementary market-setup families.

This module is deliberately NOT an independent publishing authority.  Signals
from these families are hypotheses.  Routing can occur only for exact audited
symbol/timeframe/side/family rows explicitly promoted by a verified IS/OOS
manifest; all original Entry/SL/TP/Safety/publication rules remain authoritative.

Consumes the CLOSED candle DataFrame already obtained by the canonical core;
does not call market-data providers, build charts or persist OHLCV in memory.
"""
from __future__ import annotations

import math
from typing import Mapping

FAMILIES = (
    'VOLATILITY_DISLOCATION_RETEST',
    'FAILED_AUCTION_RANGE_ACCEPTANCE',
    'SESSION_AUCTION_VWAP',
    'POST_MACRO_CONFIRMATION',
)
BANK_FAMILY = {
    'VOLATILITY_DISLOCATION_RETEST': 'BREAKOUT_RETEST',
    'FAILED_AUCTION_RANGE_ACCEPTANCE': 'SWEEP_REVERSAL',
    'SESSION_AUCTION_VWAP': 'BREAKOUT_RETEST',
    'POST_MACRO_CONFIRMATION': 'BREAKOUT_RETEST',
}
MIN_BARS = 56


def _safe_num(x, fallback=0.0):
    try:
        value = float(x)
        return value if math.isfinite(value) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def _dt(value):
    try:
        from datetime import datetime, timezone
        if hasattr(value, 'to_pydatetime'):
            value = value.to_pydatetime()
        if isinstance(value, (float, int)):
            return datetime.fromtimestamp(value, timezone.utc)
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    except (ValueError, TypeError, OSError, OverflowError, AttributeError):
        return None


def discover_families(closed_frame, *, timeframe, market='futures', asset_class='', macro=None):
    """Return compact, causal candidates; never a trade decision.

    Caller MUST provide a frame with ONLY completed bars.  Candle index i is
    never classified with data after i.  No parameter optimisation in LIVE.
    Macro and exchange-session candidates are skipped if their event clock
    cannot be established without peeking into the future.
    """
    output = {'version': 'COMMIT34_FOUR_FAMILIES_V1', 'market': str(market),
              'timeframe': str(timeframe), 'candidates': [],
              'mode': 'OBSERVATION_UNLESS_EXACT_OOS_AUTHORITY'}
    try:
        if closed_frame is None or len(closed_frame) < MIN_BARS:
            output['reason'] = 'INSUFFICIENT_CLOSED_HISTORY'
            return output
        cols = {str(c).lower(): c for c in closed_frame.columns}
        if not all(k in cols for k in ('open','high','low','close','volume')):
            output['reason'] = 'MISSING_OHLCV'
            return output
        # Keep temporary arrays to <=56 candles per request, not the whole
        # research/history frame.  No deep copies of input/DataFrames.
        frame = closed_frame.iloc[-MIN_BARS:]
        price = [_safe_num(v) for v in frame[cols['close']].tolist()]
        highs = [_safe_num(v) for v in frame[cols['high']].tolist()]
        lows = [_safe_num(v) for v in frame[cols['low']].tolist()]
        vols = [_safe_num(v) for v in frame[cols['volume']].tolist()]
        opens = [_safe_num(v) for v in frame[cols['open']].tolist()]
        if any(not(hi >= max(op,cl) >= min(op,cl) >= lo > 0) for hi,lo,op,cl in zip(highs,lows,opens,price)):
            output['reason'] = 'INVALID_OHLC'
            return output
        tcol = cols.get('time') or cols.get('timestamp')
        candle_time = _dt(frame[tcol].iloc[-1]) if tcol else None
        if candle_time is None:
            output['reason'] = 'MISSING_CANDLE_TIME'
            return output
        close = price[-1]
        ranges = [max(highs[i]-lows[i], abs(highs[i]-price[i-1]),abs(lows[i]-price[i-1])) for i in range(1,MIN_BARS)]
        atr = sum(ranges[-14:]) / 14
        if atr <= 0: return output
        atr_p = atr / close
        historical_atr = [sum(ranges[j-14:j])/14 for j in range(14,len(ranges)+1)]
        baseline = sorted(historical_atr[:-1])
        base_med = baseline[len(baseline)//2] if baseline else atr
        shock = atr > 1.55*base_med or (highs[-1]-lows[-1]) > 2.3*atr
        recent = slice(-21,-1)  # excludes signal candle
        top = max(highs[recent]); bottom = min(lows[recent]); span=max(top-bottom,atr)
        volume_base = sum(vols[-31:-1])/30
        rv = vols[-1] / volume_base if volume_base > 0 else 0.0
        body = abs(close-opens[-1]); candle_span = max(highs[-1]-lows[-1],1e-10)
        def add(fam, side, evidence):
            output['candidates'].append({'family':fam,'action':side,
              'evidence':evidence,'strategy_bank_family':BANK_FAMILY[fam],
              'source_close_time':candle_time.isoformat(),
              'entry_sl_tp': 'CANONICAL_COMMIT33_4_6_COMMITTEES',
              'statistical_authority': False})

        # A shock continuation with retrace/acceptance is not a chase.  The
        # previous bar must break the PREVIOUS closed 20-bar range and the
        # current bar must retest that boundary from the correct side.
        prior_top=max(highs[-22:-2]); prior_bottom=min(lows[-22:-2])
        prior_break_up=price[-2]>prior_top and vols[-2] > 1.2*max(1e-10,sum(vols[-32:-2])/30)
        prior_break_dn=price[-2]<prior_bottom and vols[-2] > 1.2*max(1e-10,sum(vols[-32:-2])/30)
        if shock or max(ranges[-4:])>1.55*base_med:
            if prior_break_up and lows[-1] <= prior_top+0.40*atr and close > prior_top and close > opens[-1]:
                add(FAMILIES[0],'LONG',{'atr_pct':round(atr_p,5),'retest_of':round(prior_top,6),'vol_ratio':round(rv,3)})
            elif prior_break_dn and highs[-1] >= prior_bottom-0.40*atr and close < prior_bottom and close < opens[-1]:
                add(FAMILIES[0],'SHORT',{'atr_pct':round(atr_p,5),'retest_of':round(prior_bottom,6),'vol_ratio':round(rv,3)})

        # Failed auction: wick beyond a PREVIOUS range then acceptance back
        # inside with rejection body and meaningful participation.
        if span > 2.0*atr and rv >= 0.8:
            if lows[-1] < bottom-0.12*atr and close>bottom+0.12*atr and close>opens[-1] and (close-lows[-1])/candle_span >= .66:
                add(FAMILIES[1],'LONG',{'reclaimed':round(bottom,6),'vol_ratio':round(rv,3)})
            elif highs[-1] > top+0.12*atr and close<top-0.12*atr and close<opens[-1] and (highs[-1]-close)/candle_span >= .66:
                add(FAMILIES[1],'SHORT',{'rejected':round(top,6),'vol_ratio':round(rv,3)})

        # Cash/session auction research.  Use historical local clocks and
        # zoneinfo (DST), never the current UTC hour.  US equity: NY 09:30;
        # China cash: Shanghai 09:30; CME commodities: 18:00 ET Globex
        # reference.  Exchange holidays/special calendars are NOT available;
        # such rows may be observed but may not gain LIVE authority without a
        # historically verified session-calendar replay.
        tf=str(timeframe).lower()
        if tf in ('30m','1h','2h') and tcol:
            from datetime import datetime, timedelta, timezone
            from zoneinfo import ZoneInfo
            asset=str(asset_class or '').upper()
            if asset in ('US_INDEX',):
                zone=ZoneInfo('America/New_York'); hour=9;minute=30;duration=6.5
            elif asset=='CHINA_INDEX':
                zone=ZoneInfo('Asia/Shanghai');hour=9;minute=30;duration=4.0
            elif asset in ('ENERGY','INDUSTRIAL_METAL','PRECIOUS_METAL'):
                zone=ZoneInfo('America/New_York');hour=18;minute=0;duration=23.0
            else:
                # Crypto UTC partitions are research conventions, not claims
                # about exchange cash sessions.
                zone=timezone.utc
                hour=(13 if candle_time.hour>=13 else 8 if candle_time.hour>=8 else 0)
                minute=0; duration=(11 if hour==13 else 5 if hour==8 else 8)
            local=candle_time.astimezone(zone)
            open_date=local.date()
            if local.hour < hour or (local.hour==hour and local.minute<minute):
                open_date=open_date-timedelta(days=1)
            start=datetime.combine(open_date,datetime.min.time(),tzinfo=zone).replace(hour=hour,minute=minute)
            end=start+timedelta(hours=duration)
            # No after-hours US/China signals; commodity sessions must also
            # fit in the actual Globex trading-day reference window.
            if start<=local<end and local.weekday()<5:
                bars=[]
                for j in range(len(frame)):
                    ts=_dt(frame[tcol].iloc[j])
                    if ts is not None and start<=ts.astimezone(zone)<end:
                        bars.append(j)
                if len(bars)>=3:
                    opening=bars[:max(1,min(2,len(bars)-1))]
                    if bars[-1] not in opening:
                        or_hi=max(highs[i] for i in opening)
                        or_lo=min(lows[i] for i in opening)
                        denom=sum(vols[i] for i in bars)
                        vwap=(sum(((highs[i]+lows[i]+price[i])/3)*vols[i] for i in bars)/denom) if denom>0 else close
                        if rv>=1.15 and price[-2]<=or_hi and close>or_hi+0.1*atr and close>vwap:
                            add(FAMILIES[2],'LONG',{'opening_range_high':round(or_hi,6),
                                  'session_vwap':round(vwap,6),'session_zone':str(zone),
                                  'session_calendar_verified':False})
                        elif rv>=1.15 and price[-2]>=or_lo and close<or_lo-0.1*atr and close<vwap:
                            add(FAMILIES[2],'SHORT',{'opening_range_low':round(or_lo,6),
                                  'session_vwap':round(vwap,6),'session_zone':str(zone),
                                  'session_calendar_verified':False})

        # Only explicit, historically timestamped macro releases are accepted.
        # A next-event prediction / undated calendar headline is insufficient.
        macro = macro if isinstance(macro, Mapping) else {}
        event=macro.get('last_high_impact_event') or macro.get('observed_event') or {}
        if isinstance(event, Mapping):
            pub=_dt(event.get('published_at') or event.get('observed_at'))
            event_time=_dt(event.get('event_time') or event.get('timestamp'))
            if pub and event_time and pub<=candle_time and event_time<=candle_time:
                hours=(candle_time-event_time).total_seconds()/3600.0
                if 0 <= hours <= max(2.0, min(8.0, 2*atr_p*100)) and rv>=1.4 and body/candle_span>=.62:
                    if close>top+.15*atr and close>opens[-1]:
                        add(FAMILIES[3],'LONG',{'age_hours':round(hours,2),'vol_ratio':round(rv,3)})
                    elif close<bottom-.15*atr and close<opens[-1]:
                        add(FAMILIES[3],'SHORT',{'age_hours':round(hours,2),'vol_ratio':round(rv,3)})
        output['reason'] = 'EVALUATED'
    except Exception as exc:
        output['reason'] = 'EVALUATION_ERROR:'+type(exc).__name__
    return output
