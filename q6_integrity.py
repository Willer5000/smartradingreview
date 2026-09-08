"""Q6: shared data contracts and bounded reads. No trading authority."""
from datetime import datetime, timedelta, timezone
import json
import time

SPOT_SOURCE = 'KUCOIN_SPOT_REST'
SPOT_COHORT = 'SPOT_REAL_CLOSED_Q6'
SPOT_LEGACY = 'SPOT_LEGACY_UNVERIFIED'
SPOT_VERSION = 'spot_closed_q6_v1'
TIMEFRAME_SECONDS = {
    '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
    '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600,
    '8h': 28800, '12h': 43200, '1D': 86400, '1d': 86400,
    '1W': 604800, '1w': 604800,
}


def as_bool(value):
    return value.strip().lower() in ('true', '1', 'yes', 'si') if isinstance(value, str) else bool(value)


def learning_context(row):
    context = row.get('context') or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except (ValueError, TypeError):
            return {}
    learning = context.get('learning', {}) if isinstance(context, dict) else {}
    return learning if isinstance(learning, dict) else {}


def clean_spot_learning(learning):
    return bool(
        learning.get('cohort') == SPOT_COHORT
        and learning.get('market_data_source') == SPOT_SOURCE
        and not as_bool(learning.get('market_data_is_synthetic', True))
        and as_bool(learning.get('source_candle_closed', False))
        and learning.get('analysis_version') == SPOT_VERSION
        and learning.get('source_candle_timestamp')
        and learning.get('source_candle_close_timestamp')
    )


def verified_spot(row):
    learning = learning_context(row)
    return bool(str(row.get('system_type', '')).lower() == 'spot'
                and clean_spot_learning(learning)
                and as_bool(learning.get('statistically_eligible', False)))


def prepare_spot_frame(df, timeframe, previous=False, now=None, check_fresh=True):
    """Select closed rows by UTC close time, preserving the caller's raw frame.

    Raw fetches still include the live candle for charts/price monitoring.
    This function is used only at decision and historical evaluation boundaries.
    """
    import pandas as pd
    import numpy as np
    if df is None or df.empty:
        raise ValueError('SPOT_DATA_UNAVAILABLE')
    attrs = dict(getattr(df, 'attrs', {}) or {})
    if attrs.get('market_data_source') != SPOT_SOURCE or as_bool(attrs.get('market_data_is_synthetic', True)):
        raise ValueError('SPOT_SOURCE_UNVERIFIED')
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if not seconds:
        raise ValueError('SPOT_TIMEFRAME_UNSUPPORTED')
    result = df.copy(deep=True)
    stamps = pd.to_datetime(result['time'], utc=True, errors='coerce')
    if stamps.isna().any() or stamps.duplicated().any() or not stamps.is_monotonic_increasing:
        raise ValueError('SPOT_TIMESTAMPS_INVALID')
    values = result[['open', 'high', 'low', 'close', 'volume']].astype(float)
    if (not np.isfinite(values.to_numpy()).all()
            or (values[['open', 'high', 'low', 'close']] <= 0).any().any()
            or (values['volume'] < 0).any()
            or (values['high'] < values[['open', 'close', 'low']].max(axis=1)).any()
            or (values['low'] > values[['open', 'close', 'high']].min(axis=1)).any()):
        raise ValueError('SPOT_OHLCV_INVALID')
    now = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    duration = pd.Timedelta(seconds=seconds)
    result = result.loc[stamps + duration <= now].copy()
    if previous:
        result = result.iloc[:-1].copy()
    if result.empty:
        raise ValueError('SPOT_NO_CLOSED_CANDLES')
    source_open = pd.Timestamp(result['time'].iloc[-1])
    source_open = source_open.tz_localize('UTC') if source_open.tzinfo is None else source_open.tz_convert('UTC')
    source_close = source_open + duration
    allowed_lag = duration * (2 if previous else 1)
    # Already prepared historical overrides retain their explicit mode.
    mode = 'PREVIOUS_CLOSED_CANDLE' if previous else attrs.get('analysis_mode', 'CLOSED_CANDLE')
    if mode == 'PREVIOUS_CLOSED_CANDLE':
        allowed_lag = duration * 2
    if check_fresh and now >= source_close + allowed_lag:
        raise ValueError('SPOT_CANDLES_STALE')
    result = result.reset_index(drop=True)
    result.attrs = {**attrs, 'live_price': attrs.get('live_price', float(df['close'].iloc[-1])),
                    'market_data_source': SPOT_SOURCE,
                    'market_data_is_synthetic': False, 'analysis_version': SPOT_VERSION,
                    'analysis_mode': mode, 'source_candle_closed': True,
                    'source_candle_timestamp': source_open.isoformat(),
                    'source_candle_close_timestamp': source_close.isoformat(),
                    'source_valid_until': (source_close + allowed_lag).isoformat()}
    return result


class ReadRows(list):
    """A list-compatible result carrying per-request coverage (no shared state)."""
    def __init__(self, rows=(), coverage=None):
        super().__init__(rows)
        self.coverage = coverage or {'complete': False}


def read_pages(query_factory, page_size=200, max_rows=4000, budget_seconds=20):
    """Bounded stable pagination; only an empty page proves window exhaustion.

    Advance by actual rows, not requested size: handles a server-side row cap.
    A one-row probe distinguishes exactly max_rows from a truncated window.
    """
    started = time.monotonic()
    rows, seen = [], set()
    offset = 0
    coverage = {'complete': False, 'fetched_rows': 0, 'pages': 0, 'errors': [],
                'max_rows_guard': max_rows, 'time_budget_exhausted': False}
    while True:
        if time.monotonic() - started >= budget_seconds:
            coverage['time_budget_exhausted'] = True
            break
        size = min(page_size, max_rows - len(rows)) if len(rows) < max_rows else 1
        try:
            response = query_factory().range(offset, offset + size - 1).execute()
            batch = response.data or []
            coverage['pages'] += 1
        except Exception as exc:
            coverage['errors'].append(type(exc).__name__)
            break
        if not batch:
            coverage['complete'] = True
            break
        if len(rows) >= max_rows:
            break
        added = 0
        for row in batch:
            key = row.get('id')
            if key is None or key in seen:
                coverage['errors'].append('MISSING_OR_DUPLICATE_ID')
                coverage['fetched_rows'] = len(rows)
                return ReadRows(rows, coverage)
            seen.add(key)
            rows.append(row)
            added += 1
        offset += len(batch)
        if not added:
            break
    coverage.update(fetched_rows=len(rows), elapsed_seconds=round(time.monotonic()-started, 3))
    return ReadRows(rows, coverage)


def daily_slot(now):
    """Most recent scheduled 20:00 America/La_Paz, including wake-up next day."""
    local = now.astimezone(timezone(timedelta(hours=-4)))
    due = local.replace(hour=20, minute=0, second=0, microsecond=0)
    if local < due:
        due -= timedelta(days=1)
    return due.strftime('%Y-%m-%d')


def claim_daily_job(db, job_name, slot, retry=False):
    """Atomic primary-key claim. Missing DB/table fails closed, never fake success.

    AI attempts are at-most-once. Review may recover a two-hour abandoned lease.
    """
    if not getattr(db, 'enabled', False):
        return False
    key = f'{job_name}:{slot}'
    now = datetime.now(timezone.utc)
    payload = {'job_key': key, 'status': 'RUNNING', 'updated_at': now.isoformat()}
    try:
        db.client.table('q6_job_runs').insert(payload).execute()
        return True
    except Exception:
        if not retry:
            return False
        try:
            rows = db.client.table('q6_job_runs').select('status,updated_at').eq('job_key', key).execute().data or []
            if not rows or rows[0]['status'] == 'DONE':
                return False
            previous = rows[0]['updated_at']
            age = now - datetime.fromisoformat(previous.replace('Z', '+00:00'))
            delay = timedelta(minutes=15) if rows[0]['status'] == 'FAILED' else timedelta(hours=2)
            if age < delay:
                return False
            claimed = db.client.table('q6_job_runs').update(payload).eq('job_key', key).eq('updated_at', previous).execute()
            return bool(claimed.data)
        except Exception:
            return False


def finish_daily_job(db, job_name, slot, success):
    try:
        db.client.table('q6_job_runs').update({'status': 'DONE' if success else 'FAILED',
            'updated_at': datetime.now(timezone.utc).isoformat()}).eq('job_key', f'{job_name}:{slot}').execute()
    except Exception:
        return False
    return True
