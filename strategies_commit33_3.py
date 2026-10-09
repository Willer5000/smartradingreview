"""Deterministic Research Alpha Lab used by Commit 33.4.x.

These rules are intentionally *research only*.  They are not imported by the
LIVE signal path.  A strategy/cell may only be promoted after a chronological
IS/selection/OOS report based on real OHLCV passes the governance rules in
``backtest_commit33_3.py``.

The module keeps the original six Commit-33.3 candidates and adds the two gaps
that are most relevant to the current coverage matrix:
- AUCTION_SESSION_STRUCTURE (acceptance/rejection around session range/VWAP)
- CROSS_SECTIONAL_RELATIVE_STRENGTH (panel strategy, volatility-normalised)

It also exposes two *research challengers* for balance/shock coverage.  They do
not change current LIVE signals.
"""
from __future__ import annotations

from typing import Dict, Tuple
import numpy as np
import pandas as pd

STRATEGY_NAMES = (
    'CRT_RANGE_RECLAIM',
    'FAILED_AUCTION',
    'OPENING_RANGE_VWAP',
    'TRIPLE_RSI',
    'EFFICIENCY_RATIO',
    'VOLATILITY_COMPRESSION_RELEASE',
    'AUCTION_SESSION_STRUCTURE',
    'VWAP_VALUE_REVERSION',
    'ER_PULLBACK_CONTINUATION',
    'ATR_SHOCK_EXHAUSTION',
)
PANEL_STRATEGY_NAMES = ('CROSS_SECTIONAL_RELATIVE_STRENGTH',)

# Do not force an intraday/session idea onto a structural 12h/1D cell merely to
# increase sample count.  This is an anti-overfitting contract.
APPLICABLE_TIMEFRAMES = {
    'CRT_RANGE_RECLAIM': {'30m','1h','2h','4h','12h','1D'},
    'FAILED_AUCTION': {'30m','1h','2h','4h','12h','1D'},
    'OPENING_RANGE_VWAP': {'30m','1h','2h'},
    'TRIPLE_RSI': {'30m','1h','2h','4h','12h','1D'},
    'EFFICIENCY_RATIO': {'30m','1h','2h','4h','12h','1D'},
    'VOLATILITY_COMPRESSION_RELEASE': {'30m','1h','2h','4h'},
    'AUCTION_SESSION_STRUCTURE': {'30m','1h','2h'},
    'VWAP_VALUE_REVERSION': {'30m','1h','2h','4h'},
    'ER_PULLBACK_CONTINUATION': {'30m','1h','2h','4h','12h','1D'},
    'ATR_SHOCK_EXHAUSTION': {'30m','1h','2h'},
    'CROSS_SECTIONAL_RELATIVE_STRENGTH': {'30m','1h','2h','4h'},
}


def _rsi(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100/(1+rs)).fillna(50)


def _atr(df, n=14):
    pc = df.close.shift(1)
    tr = pd.concat([
        (df.high-df.low).abs(),
        (df.high-pc).abs(),
        (df.low-pc).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def _timeframe_minutes(tf: str) -> int:
    text = str(tf or '30m').lower()
    if text.endswith('m'):
        return max(1, int(text[:-1]))
    if text.endswith('h'):
        return max(1, int(text[:-1])) * 60
    if text.endswith('d'):
        return max(1, int(text[:-1] or '1')) * 1440
    return 30


def features(df: pd.DataFrame, timeframe: str = '30m') -> pd.DataFrame:
    x = df.copy().reset_index(drop=True)
    if 'timestamp' not in x and 'time' in x:
        x = x.rename(columns={'time': 'timestamp'})
    for c in ['open','high','low','close','volume']:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    x['timestamp'] = pd.to_datetime(x.get('timestamp'), utc=True, errors='coerce')
    x['atr'] = _atr(x)
    x['atr_pct'] = (x.atr / x.close.replace(0, np.nan)).fillna(0)
    x['rsi7'] = _rsi(x.close, 7)
    x['rsi14'] = _rsi(x.close, 14)
    x['rsi28'] = _rsi(x.close, 28)
    x['ema20'] = x.close.ewm(span=20, adjust=False).mean()
    x['ema50'] = x.close.ewm(span=50, adjust=False).mean()
    change = (x.close-x.close.shift(20)).abs()
    path = x.close.diff().abs().rolling(20).sum()
    x['er20'] = (change/path.replace(0, np.nan)).fillna(0)
    mid = x.close.rolling(20).mean()
    sd = x.close.rolling(20).std()
    x['bb_mid'] = mid
    x['bb_u'] = mid + 2*sd
    x['bb_l'] = mid - 2*sd
    x['bb_w'] = ((x.bb_u-x.bb_l)/mid.replace(0, np.nan)).fillna(0)
    tp = (x.high+x.low+x.close)/3
    x['vwap_roll'] = (tp*x.volume).rolling(32).sum()/x.volume.rolling(32).sum().replace(0, np.nan)
    x['prev20h'] = x.high.shift(1).rolling(20).max()
    x['prev20l'] = x.low.shift(1).rolling(20).min()
    x['ret8'] = x.close.pct_change(8)
    x['ret24'] = x.close.pct_change(24)
    x['vol_z'] = ((x.volume-x.volume.rolling(50).mean())/x.volume.rolling(50).std().replace(0,np.nan)).fillna(0)

    # UTC sessions are deterministic and exchange-neutral for crypto.  The
    # backtester never tunes the session clock per symbol.
    if x.timestamp.notna().any():
        hour = x.timestamp.dt.hour
        x['session'] = np.select(
            [hour < 8, hour < 13, hour < 21],
            ['ASIA','LONDON','NEW_YORK'],
            default='LATE_US',
        )
        x['session_key'] = x.timestamp.dt.floor('D').astype(str) + '|' + x.session.astype(str)
        rank = x.groupby('session_key').cumcount()
        # First ~1 hour of each session, rounded to at least one bar.
        or_bars = max(1, int(round(60 / max(1, _timeframe_minutes(timeframe)))))
        x['session_rank'] = rank
        x['or_high'] = x.high.where(rank < or_bars).groupby(x.session_key).transform('max')
        x['or_low'] = x.low.where(rank < or_bars).groupby(x.session_key).transform('min')
        x['session_vwap'] = (
            (tp*x.volume).groupby(x.session_key).cumsum()
            / x.volume.groupby(x.session_key).cumsum().replace(0, np.nan)
        )
    else:
        x['session'] = 'UNKNOWN'
        x['session_key'] = 'UNKNOWN'
        x['session_rank'] = 999
        x['or_high'] = np.nan
        x['or_low'] = np.nan
        x['session_vwap'] = x['vwap_roll']
    return x


def strategy_applicable(name: str, timeframe: str) -> bool:
    return str(timeframe) in APPLICABLE_TIMEFRAMES.get(str(name), set())


def signal(df: pd.DataFrame, name: str, timeframe: str = '30m') -> Tuple[pd.Series, pd.DataFrame]:
    x = features(df, timeframe=timeframe)
    sig = pd.Series(0, index=x.index, dtype=int)
    if not strategy_applicable(name, timeframe):
        return sig, x

    if name == 'CRT_RANGE_RECLAIM':
        ph = x.high.shift(1).rolling(8).max(); pl = x.low.shift(1).rolling(8).min()
        sig[(x.low < pl) & (x.close > pl) & (x.close > x.open)] = 1
        sig[(x.high > ph) & (x.close < ph) & (x.close < x.open)] = -1

    elif name == 'FAILED_AUCTION':
        sig[(x.high > x.prev20h) & (x.close < x.prev20h) & ((x.high-x.close) > 0.6*x.atr)] = -1
        sig[(x.low < x.prev20l) & (x.close > x.prev20l) & ((x.close-x.low) > 0.6*x.atr)] = 1

    elif name == 'OPENING_RANGE_VWAP':
        ready = x.session_rank >= 1
        sig[ready & (x.close > x.or_high) & (x.close > x.session_vwap) & (x.close > x.ema20)] = 1
        sig[ready & (x.close < x.or_low) & (x.close < x.session_vwap) & (x.close < x.ema20)] = -1

    elif name == 'TRIPLE_RSI':
        sig[(x.rsi7 > x.rsi14) & (x.rsi14 > x.rsi28) & (x.rsi14 > 52) & (x.ema20 > x.ema50)] = 1
        sig[(x.rsi7 < x.rsi14) & (x.rsi14 < x.rsi28) & (x.rsi14 < 48) & (x.ema20 < x.ema50)] = -1

    elif name == 'EFFICIENCY_RATIO':
        sig[(x.er20 > 0.35) & (x.ema20 > x.ema50) & (x.close > x.high.shift(1).rolling(10).max())] = 1
        sig[(x.er20 > 0.35) & (x.ema20 < x.ema50) & (x.close < x.low.shift(1).rolling(10).min())] = -1

    elif name == 'VOLATILITY_COMPRESSION_RELEASE':
        q = x.bb_w.shift(1).rolling(100).quantile(.2)
        compressed = x.bb_w.shift(1) < q
        sig[compressed & (x.close > x.bb_u.shift(1)) & (x.atr > x.atr.shift(1)*1.05)] = 1
        sig[compressed & (x.close < x.bb_l.shift(1)) & (x.atr > x.atr.shift(1)*1.05)] = -1

    elif name == 'AUCTION_SESSION_STRUCTURE':
        # Failed acceptance outside the opening auction + reclaim through VWAP.
        ready = x.session_rank >= 1
        long_reject = (x.low < x.or_low) & (x.close > x.or_low) & (x.close >= x.session_vwap)
        short_reject = (x.high > x.or_high) & (x.close < x.or_high) & (x.close <= x.session_vwap)
        sig[ready & long_reject & (x.rsi14 > 42)] = 1
        sig[ready & short_reject & (x.rsi14 < 58)] = -1

    elif name == 'VWAP_VALUE_REVERSION':
        # Balance-only challenger: low ER + 1.2 ATR excursion + return toward value.
        low_eff = x.er20 < 0.22
        sig[low_eff & (x.low < x.vwap_roll-1.2*x.atr) & (x.close > x.open) & (x.close > x.low.shift(1))] = 1
        sig[low_eff & (x.high > x.vwap_roll+1.2*x.atr) & (x.close < x.open) & (x.close < x.high.shift(1))] = -1

    elif name == 'ER_PULLBACK_CONTINUATION':
        trend_up = (x.er20 > 0.28) & (x.ema20 > x.ema50)
        trend_dn = (x.er20 > 0.28) & (x.ema20 < x.ema50)
        sig[trend_up & (x.low <= x.ema20) & (x.close > x.ema20) & (x.rsi14 > 48)] = 1
        sig[trend_dn & (x.high >= x.ema20) & (x.close < x.ema20) & (x.rsi14 < 52)] = -1

    elif name == 'ATR_SHOCK_EXHAUSTION':
        med = x.atr_pct.rolling(100).median()
        shock = x.atr_pct > med*1.8
        sig[shock & (x.low < x.prev20l) & (x.close > x.prev20l) & (x.rsi7 < 35)] = 1
        sig[shock & (x.high > x.prev20h) & (x.close < x.prev20h) & (x.rsi7 > 65)] = -1

    return sig, x


def cross_sectional_relative_strength(panel: Dict[str, pd.DataFrame], timeframe: str = '30m') -> Dict[str, pd.Series]:
    """Volatility-normalised cross-sectional rank. Research-only.

    Returns {-1,0,+1} series per symbol on the common timestamp index.  It uses
    only information known at each timestamp; no future cross-section is used.
    """
    if not strategy_applicable('CROSS_SECTIONAL_RELATIVE_STRENGTH', timeframe):
        return {k: pd.Series(0, index=v.index, dtype=int) for k, v in panel.items()}

    frames = {}
    for symbol, raw in panel.items():
        x = features(raw, timeframe=timeframe)
        if x.timestamp.isna().all():
            continue
        z = pd.DataFrame({'timestamp': x.timestamp})
        z['score'] = (x.ret8*0.65 + x.ret24*0.35) / x.atr_pct.replace(0, np.nan)
        z['er20'] = x.er20
        frames[str(symbol)] = z.dropna(subset=['timestamp']).set_index('timestamp')
    if len(frames) < 4:
        return {k: pd.Series(0, index=v.index, dtype=int) for k, v in panel.items()}

    score = pd.concat({k:v.score for k,v in frames.items()}, axis=1).sort_index()
    er = pd.concat({k:v.er20 for k,v in frames.items()}, axis=1).reindex(score.index)
    pct = score.rank(axis=1, pct=True)
    out = {}
    for symbol, raw in panel.items():
        x = features(raw, timeframe=timeframe)
        if symbol not in score.columns:
            out[symbol] = pd.Series(0, index=x.index, dtype=int); continue
        common = pd.DataFrame({'timestamp': x.timestamp}).set_index('timestamp')
        p = pct[symbol].reindex(common.index)
        e = er[symbol].reindex(common.index)
        sig = pd.Series(0, index=common.index, dtype=int)
        sig[(p >= .80) & (e >= .18)] = 1
        sig[(p <= .20) & (e >= .18)] = -1
        out[symbol] = pd.Series(sig.values, index=x.index, dtype=int)
    return out
