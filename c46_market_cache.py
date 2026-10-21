"""Read-only C46 helper: reuses the *existing* native OHLCV cache, no HTTP/threads.

Never supplies candles from a different symbol/TF/source candle.
"""
from __future__ import annotations
from datetime import datetime, timezone

def _utc(value):
    try:
        if hasattr(value,'to_pydatetime'):value=value.to_pydatetime()
        if not isinstance(value,datetime):value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0)
    except (TypeError, ValueError, OverflowError):
        return None

def closed_candles_from_native_cache(symbol,timeframe,source_ts):
    """Return 130 validated rows only when the cached CLOSED bar matches the analysis."""
    stamp=_utc(source_ts)
    if stamp is None:return []
    try:
        import futures_system as native
        # Same lock and data used by the Futures and Multi-Asset native analysis.
        with native._futures_data_cache_lock:
            item=native._futures_data_cache.get((str(symbol),str(timeframe)))
            if not item or 'df' not in item:return []
            df=item['df']
            if 'time' not in df.columns:return []
            # Do not export the open candle or timestamp after the original analysis.
            row_start=max(0,len(df)-180)
            rows=df.iloc[row_start:][['time','open','high','low','close','volume']].to_dict('records')
        closed=[r for r in rows if (_utc(r.get('time')) is not None and _utc(r['time'])<=stamp)]
        if len(closed)<115 or _utc(closed[-1].get('time'))!=stamp:
            return []
        return [{k:r[k] for k in ('open','high','low','close','volume')} for r in closed[-130:]]
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        return []
