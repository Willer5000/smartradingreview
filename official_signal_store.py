"""Commit 37 recovery: independent durable index of OFFICIAL Telegram confirmations.

This is NOT a signal generator.  Each immutable confirmation uses the existing
runtime_snapshots_v1 table (one row per signal ID).  A lost/replaced aggregate
snapshot cannot erase an individually committed confirmation.  The bounded
read-only index is shared by the three web markets.  No daemon is created.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

NAMESPACE = 'official_confirmed_v37'
TTL_SECONDS = 10 * 86400
_INDEX_LOCK = threading.Lock()
_INDEX_MONO = 0.0
_INDEX_ROWS = []
# 120 seconds avoids spending scarce 5 GB monthly Supabase egress on polling.
_INDEX_TTL = max(60, min(600, int(os.getenv('OFFICIAL_SIGNAL_INDEX_REFRESH_SECONDS', '120'))))
_INDEX_LIMIT = 120


def _sid(item: dict) -> str:
    sig = item.get('signal') or {}
    lev = sig.get('levels') or {}
    value = str(sig.get('signal_id') or sig.get('source_signal_id') or lev.get('signal_id') or '').strip()
    if not value:
        return ''  # Never invent a signal identity for a Telegram link.
    if len(value) > 120 or '/' in value or '\\' in value:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()[:40]
    return value


def _snapshot_payload(item: dict) -> dict:
    sig = item.get('signal') or {}
    return {'event': {
        'key': str(item.get('key') or '')[:250],
        'market': str(item.get('market') or '').lower(),
        'state': str(item.get('state') or 'PENDING').upper(),
        'signal': sig if isinstance(sig, dict) else {},
        'created_at': float(item.get('created_at') or time.time()),
        'updated_at': float(item.get('updated_at') or time.time()),
        '_c35_remote_persisted': True,
    }}



def _merge_index_rows(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Keep unique, recently committed IDs when the DB index refresh races a write.

    Runs on <= 240 small compact official events, no network or market data.
    Ten-day TTL is still enforced by the remote runtime snapshot; this local
    cache cannot make an expired setup tradable (web lifecycle validates it).
    """
    newest = {}
    oldest_allowed = time.time() - TTL_SECONDS
    for row in list(primary) + list(secondary):
        if not isinstance(row, dict):
            continue
        sid = _sid(row)
        if not sid:
            continue
        try:
            updated = float(row.get('updated_at') or row.get('created_at') or 0)
        except (TypeError, ValueError):
            continue
        if updated < oldest_allowed:
            continue
        existing = newest.get(sid)
        if existing is None or updated > float(existing.get('updated_at') or existing.get('created_at') or 0):
            newest[sid] = row
    return sorted(newest.values(), key=lambda row: float(row.get('updated_at') or row.get('created_at') or 0), reverse=True)[:_INDEX_LIMIT]

def persist_official(item: dict) -> bool:
    """Durable once-per-signal upsert; must succeed *before* Telegram delivery.

    The existing aggregate outbox is still written for compatibility. This
    independent DB row protects a signal when that aggregate is later replaced
    or its in-process state is lost on an OOM/restart.
    """
    if not isinstance(item, dict):
        return False
    sid = _sid(item)
    if not sid or str(item.get('market') or '').lower() not in ('spot','futures','multiasset'):
        return False
    try:
        from runtime_persistence import save_runtime_snapshot
        saved = bool(save_runtime_snapshot(NAMESPACE, sid, _snapshot_payload(item),
                                          ttl_seconds=TTL_SECONDS, require_remote=True))
        if saved:
            # A freshly committed OFFICIAL signal must immediately be visible
            # in web readers on this process.  No query or new worker needed.
            # The background DB index refresh can still discover other workers.
            event = _snapshot_payload(item)['event']
            global _INDEX_ROWS
            with _INDEX_LOCK:
                previous = [r for r in _INDEX_ROWS if _sid(r) != sid]
                _INDEX_ROWS = _merge_index_rows([event], previous)
        return saved
    except Exception as exc:
        print(f'⚠️ [OFFICIAL DURABILITY] save {sid}: {type(exc).__name__}', flush=True)
        return False


def get_official(signal_id: str) -> Optional[dict]:
    """Look up an exact ID only. Never run a strategy or mark a trade active."""
    sid = str(signal_id or '').strip()
    if not sid or len(sid) > 120 or '/' in sid or '\\' in sid:
        return None
    try:
        from runtime_persistence import load_runtime_snapshot
        saved = load_runtime_snapshot(NAMESPACE, sid, allow_expired=False, require_remote=True)
        event = ((saved or {}).get('payload') or {}).get('event')
        return event if isinstance(event, dict) and _sid(event) == sid else None
    except Exception as exc:
        print(f'⚠️ [OFFICIAL DURABILITY] read {sid}: {type(exc).__name__}', flush=True)
        return None


def recent_official_events(*, refresh: bool = False) -> list[dict]:
    """Bounded multi-market index; at most one DB query each TTL interval.

    Fallback on a failed query is the last successful index; the web must not
    erase a confirmed card simply because Supabase is briefly unavailable.
    """
    global _INDEX_MONO, _INDEX_ROWS
    now = time.monotonic()
    with _INDEX_LOCK:
        # HTTP read paths are strictly cache-only: never make page loads wait
        # for a 3rd-party DB call or increase latency under Render pressure.
        if not refresh or now - _INDEX_MONO < _INDEX_TTL:
            return list(_INDEX_ROWS)
        # Suppress concurrent bursts while the remote request is in flight.
        _INDEX_MONO = now
    try:
        from runtime_persistence import _db, RUNTIME_TABLE
        db = _db()
        if db is None or bool(getattr(db, 'provider_restricted', lambda: False)()):
            return list(_INDEX_ROWS)
        result = (db.client.table(RUNTIME_TABLE)
                  .select('snapshot_key,payload,updated_at,expires_at')
                  .eq('namespace', NAMESPACE)
                  .order('updated_at', desc=True)
                  .limit(_INDEX_LIMIT).execute())
        now_utc = datetime.now(timezone.utc)
        valid = []
        for row in list(result.data or []):
            if not isinstance(row, dict):
                continue
            expires = row.get('expires_at')
            if expires:
                try:
                    dt = datetime.fromisoformat(str(expires).replace('Z','+00:00'))
                    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if dt <= now_utc: continue
                except Exception:
                    continue
            event = ((row.get('payload') or {}).get('event') or {})
            if (isinstance(event,dict)
                    and _sid(event) == row.get('snapshot_key')
                    and str(event.get('market') or '') in ('spot','futures','multiasset')):
                valid.append(event)
        with _INDEX_LOCK:
            _INDEX_ROWS = _merge_index_rows(valid, _INDEX_ROWS)
            return list(_INDEX_ROWS)
    except Exception as exc:
        print(f'⚠️ [OFFICIAL DURABILITY] index: {type(exc).__name__}', flush=True)
        with _INDEX_LOCK:
            return list(_INDEX_ROWS)


def reset_index_for_tests():
    global _INDEX_MONO, _INDEX_ROWS
    with _INDEX_LOCK:
        _INDEX_MONO = 0.0
        _INDEX_ROWS = []
