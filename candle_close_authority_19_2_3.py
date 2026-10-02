"""Commit 19.2.3 — canonical closed-candle authority.

Pure UTC calendar helpers shared by Spot/Futures/Multi confirmed-notification
paths.  No network, no trading-score authority and no background threads.

Why it exists
-------------
A fixed ``epoch // 604800`` grid anchors weeks to the Unix epoch weekday
(Thursday), which is not the exchange weekly candle calendar.  Confirmed
signals also used broad anti-cold-start windows (up to hours), so an old daily
or weekly result could be announced as "new" long after its actual close.

This module makes the close itself the authority:
- intraday / daily boundaries are UTC aligned;
- 1W is Monday 00:00 UTC -> next Monday 00:00 UTC;
- Telegram discovery has a bounded post-close grace;
- Spot closed-candle refresh uses per-timeframe watermarks so 1D/1W are not
  recomputed on every 4h close.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

VERSION = "COMMIT19_2_3_CANDLE_CLOSE_AUTHORITY_V1"

TF_SECONDS: Dict[str, int] = {
    "30m": 30 * 60,
    "1h": 60 * 60,
    "2h": 2 * 60 * 60,
    "4h": 4 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1D": 24 * 60 * 60,
    "1d": 24 * 60 * 60,
    "1W": 7 * 24 * 60 * 60,
    "1w": 7 * 24 * 60 * 60,
}

# A confirmed Telegram event may be discovered a little after the real close,
# but not several hours later.  4h keeps a 60-minute allowance because the
# production worker can legitimately finish tens of minutes after the close.
CONFIRMED_DISCOVERY_GRACE_SECONDS: Dict[str, int] = {
    "30m": 20 * 60,
    "1h": 45 * 60,
    "2h": 45 * 60,
    "4h": 60 * 60,
    "12h": 60 * 60,
    "1D": 60 * 60,
    "1d": 60 * 60,
    "1W": 90 * 60,
    "1w": 90 * 60,
}

# Small data-settlement delay before the background closed-candle replay starts.
SPOT_SETTLE_GRACE_SECONDS: Dict[str, int] = {
    "4h": 90,
    "12h": 120,
    "1D": 180,
    "1W": 300,
}


def _tf_key(timeframe: Any) -> str:
    raw = str(timeframe or "").strip()
    if raw.upper() == "1D":
        return "1D"
    if raw.upper() == "1W":
        return "1W"
    return raw.lower()


def tf_seconds(timeframe: Any) -> int:
    return int(TF_SECONDS.get(_tf_key(timeframe), 0) or 0)


def parse_utc(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            # Conservative compatibility with legacy "YYYY-mm-dd HH:MM:SS".
            dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    dt = datetime.strptime(text.split("+")[0].split("Z")[0].strip(), fmt)
                    break
                except Exception:
                    continue
            if dt is None:
                return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonical_start_utc(timeframe: Any, timestamp: Any) -> Optional[datetime]:
    """Canonical candle start containing ``timestamp``.

    Weekly candles are explicitly Monday 00:00 UTC.  This avoids the Unix-epoch
    Thursday anchor created by ``epoch // 604800``.
    """
    dt = parse_utc(timestamp)
    seconds = tf_seconds(timeframe)
    if dt is None or seconds <= 0:
        return None
    key = _tf_key(timeframe)
    if key == "1W":
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=midnight.weekday())
    if seconds >= 86400:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    epoch = int(dt.timestamp())
    return datetime.fromtimestamp((epoch // seconds) * seconds, tz=timezone.utc)


def canonical_close_from_open_utc(timeframe: Any, source_open: Any) -> Optional[datetime]:
    start = canonical_start_utc(timeframe, source_open)
    seconds = tf_seconds(timeframe)
    if start is None or seconds <= 0:
        return None
    return start + timedelta(seconds=seconds)


def nearest_boundary_utc(timeframe: Any, timestamp: Any) -> Optional[datetime]:
    """Snap an already-close-like timestamp to the nearest canonical boundary."""
    dt = parse_utc(timestamp)
    start = canonical_start_utc(timeframe, dt)
    seconds = tf_seconds(timeframe)
    if dt is None or start is None or seconds <= 0:
        return None
    nxt = start + timedelta(seconds=seconds)
    return start if abs((dt - start).total_seconds()) <= abs((nxt - dt).total_seconds()) else nxt


def latest_boundary_utc(timeframe: Any, now: Any = None) -> Optional[datetime]:
    return canonical_start_utc(timeframe, now or datetime.now(timezone.utc))


def signal_close_utc(signal: Mapping[str, Any], timeframe: Any) -> Optional[datetime]:
    """Canonical close represented by a signal snapshot.

    Prefer the explicit source close.  Fall back to source-open + duration.
    """
    signal = signal if isinstance(signal, Mapping) else {}
    raw_close = signal.get("source_candle_close_timestamp")
    if raw_close:
        snapped = nearest_boundary_utc(timeframe, raw_close)
        if snapped is not None:
            return snapped
    raw_open = (
        signal.get("source_candle_timestamp")
        or signal.get("candle_timestamp")
        or signal.get("previous_candle_timestamp")
    )
    return canonical_close_from_open_utc(timeframe, raw_open)


def discovery_grace_seconds(timeframe: Any) -> int:
    key = _tf_key(timeframe)
    return int(CONFIRMED_DISCOVERY_GRACE_SECONDS.get(key, 30 * 60))


def confirmed_recent_enough(signal: Mapping[str, Any], timeframe: Any, now: Any = None) -> bool:
    close = signal_close_utc(signal, timeframe)
    current = parse_utc(now or datetime.now(timezone.utc))
    if close is None or current is None:
        return False
    age = (current - close).total_seconds()
    # Tiny clock jitter is tolerated; a materially future close is not.
    if age < -120:
        return False
    return age <= discovery_grace_seconds(timeframe)


def due_spot_timeframes(
    watermarks: Mapping[str, Any],
    now: Any = None,
    timeframes: Iterable[str] = ("4h", "12h", "1D", "1W"),
) -> Dict[str, datetime]:
    """Return TF -> newest close that still needs one closed-candle replay."""
    current = parse_utc(now or datetime.now(timezone.utc))
    if current is None:
        return {}
    wm = watermarks if isinstance(watermarks, Mapping) else {}
    due: Dict[str, datetime] = {}
    for raw_tf in timeframes:
        key = _tf_key(raw_tf)
        boundary = latest_boundary_utc(key, current)
        if boundary is None:
            continue
        settle = int(SPOT_SETTLE_GRACE_SECONDS.get(key, 90))
        if current < boundary + timedelta(seconds=settle):
            continue
        prior = parse_utc(wm.get(key) or wm.get(raw_tf))
        if prior is None or prior < boundary:
            due[raw_tf] = boundary
    return due


def iso_utc(value: Any) -> Optional[str]:
    dt = parse_utc(value)
    return dt.isoformat() if dt is not None else None
