"""Canonical Futures presentation clock; never changes technical validity.

CONFIRMED: one complete timeframe from SOURCE CANDLE CLOSE.
VIGENT: original lifecycle.valid_until, independently calculated from geometry.

No persistence mutation, no new signals, no Entry/SL/TP computation.
"""
from datetime import datetime, timedelta, timezone
import math

TF_SECONDS = {
    '30m': 1800, '1h': 3600, '2h': 7200, '4h': 14400,
    '12h': 43200, '1D': 86400,
}


def _parse_utc(raw):
    if raw is None or raw == '':
        return None
    try:
        if isinstance(raw, datetime):
            val = raw
        elif isinstance(raw, (int, float)):
            if not math.isfinite(float(raw)):
                return None
            epoch = float(raw)
            if abs(epoch) > 1e11:
                epoch /= 1000
            val = datetime.fromtimestamp(epoch, timezone.utc)
        else:
            s = str(raw).strip().replace('Z', '+00:00')
            # Some older snapshots serialized the opening/closing epoch as
            # numeric TEXT rather than ISO-8601. Interpret seconds or millis.
            if s.replace('.', '', 1).isdigit() and len(s.split('.', 1)[0]) >= 10:
                return _parse_utc(float(s))
            val = datetime.fromisoformat(s)
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def in_confirmation_window(source_close, source_open, timeframe, now_utc=None):
    """Return whether the latest source candle remains a *new confirmation*.

    Missing/invalid source metadata fails closed. The record may still appear in
    VIGENT if the persisted lifecycle marks it waiting_entry/entry_touched and
    technical valid_until remains in the future; this helper never expires it.
    """
    seconds = TF_SECONDS.get(str(timeframe or ''))
    if seconds is None:
        return False
    close = _parse_utc(source_close)
    if close is None:
        open_dt = _parse_utc(source_open)
        if open_dt is None:
            return False
        close = open_dt + timedelta(seconds=seconds)
    now = _parse_utc(now_utc) if now_utc is not None else datetime.now(timezone.utc)
    if now is None:
        return False
    # Exact confirmation authority: [source_close, next_close).
    return close <= now < close + timedelta(seconds=seconds)
