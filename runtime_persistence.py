"""Hotfix 14.6 — bounded persistence for ephemeral runtime state.

Keeps bounded runtime snapshots in Supabase *and* a local fail-open copy.
The local copy is intentionally ephemeral (Render /tmp) but prevents a live
process from becoming blind when Supabase is unavailable or returns 402. A DB
problem never blocks Spot/Futures trading.
"""
from __future__ import annotations

import time
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from local_resilience import save_snapshot as _local_save_snapshot, load_snapshot as _local_load_snapshot
except Exception:
    _local_save_snapshot = None
    _local_load_snapshot = None

RUNTIME_TABLE = 'runtime_snapshots_v1'
MACRO_TABLE = 'macro_context_events_v1'

_CLEANUP_LAST = 0.0
_RC8_WRITE_LOCK = threading.Lock()
_RC8_SNAPSHOT_WRITES = {}
_RC8_MACRO_WRITE = {'digest': None, 'ts': 0.0}
_RC8_IDENTICAL_WRITE_SECONDS = 900.0
_RC83_READ_CACHE = {}
_RC83_READ_CACHE_TTL = 300.0
_RC83_MACRO_READ_CACHE = {'ts': 0.0, 'value': []}


def _stable_digest(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    except Exception:
        raw = repr(value)
    return hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()


def _db():
    try:
        from supabase_client import supabase_db
        return supabase_db if getattr(supabase_db, 'enabled', False) else None
    except Exception:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def save_runtime_snapshot(namespace: str, snapshot_key: str, payload: Dict[str, Any], *, ttl_seconds: int = 21600) -> bool:
    if not isinstance(payload, dict):
        return False
    local_ok = False
    try:
        if _local_save_snapshot is not None:
            local_ok = bool(_local_save_snapshot(namespace, snapshot_key, payload, ttl_seconds=ttl_seconds))
    except Exception:
        local_ok = False
    db = _db()
    if db is None or bool(getattr(db, 'provider_restricted', lambda: False)()):
        return local_ok
    now = utc_now()
    cache_key = (str(namespace or 'runtime')[:64], str(snapshot_key or 'default')[:128])
    digest = _stable_digest(payload)
    with _RC8_WRITE_LOCK:
        prior = _RC8_SNAPSHOT_WRITES.get(cache_key)
        if prior and prior.get('digest') == digest and (time.monotonic() - float(prior.get('ts') or 0.0)) < _RC8_IDENTICAL_WRITE_SECONDS:
            cleanup_ephemeral_storage()
            return True
    row = {
        'namespace': str(namespace or 'runtime')[:64],
        'snapshot_key': str(snapshot_key or 'default')[:128],
        'payload': payload,
        'updated_at': now.isoformat(),
        'expires_at': (now + timedelta(seconds=max(300, int(ttl_seconds or 21600)))).isoformat(),
    }
    try:
        # RC8.3 Free Plan: do not ask PostgREST to echo the JSONB snapshot.
        if hasattr(db, '_rest_minimal'):
            db._rest_minimal(
                'POST', RUNTIME_TABLE, payload=row,
                params={'on_conflict': 'namespace,snapshot_key'},
                prefer='resolution=merge-duplicates,return=minimal',
            )
        else:
            db.client.table(RUNTIME_TABLE).upsert(
                row, on_conflict='namespace,snapshot_key'
            ).execute()
        with _RC8_WRITE_LOCK:
            _RC8_SNAPSHOT_WRITES[cache_key] = {'digest': digest, 'ts': time.monotonic()}
            _RC83_READ_CACHE[cache_key] = {
                'ts': time.monotonic(),
                'value': {
                    'payload': dict(payload),
                    'updated_at': row['updated_at'],
                    'expires_at': row['expires_at'],
                    'expired': False,
                },
            }
        cleanup_ephemeral_storage()
        return True
    except Exception as exc:
        print(f"⚠️ [PERSIST] runtime snapshot save {namespace}/{snapshot_key}: {exc}")
        return local_ok


def load_runtime_snapshot(namespace: str, snapshot_key: str, *, allow_expired: bool = False) -> Optional[Dict[str, Any]]:
    db = _db()
    cache_key = (str(namespace or 'runtime')[:64], str(snapshot_key or 'default')[:128])
    with _RC8_WRITE_LOCK:
        cached = _RC83_READ_CACHE.get(cache_key) or {}
        if cached and (time.monotonic() - float(cached.get('ts') or 0.0)) < _RC83_READ_CACHE_TTL:
            value = cached.get('value')
            if isinstance(value, dict):
                return dict(value)
    if db is None or bool(getattr(db, 'provider_restricted', lambda: False)()):
        try:
            return _local_load_snapshot(namespace, snapshot_key, allow_expired=allow_expired) if _local_load_snapshot else None
        except Exception:
            return None
    try:
        response = (
            db.client.table(RUNTIME_TABLE)
            .select('payload,updated_at,expires_at')
            .eq('namespace', str(namespace or 'runtime')[:64])
            .eq('snapshot_key', str(snapshot_key or 'default')[:128])
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        row = rows[0]
        expires_raw = row.get('expires_at')
        expired = False
        if expires_raw:
            try:
                expires = datetime.fromisoformat(str(expires_raw).replace('Z', '+00:00'))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                expired = utc_now() >= expires.astimezone(timezone.utc)
            except Exception:
                expired = False
        if expired and not allow_expired:
            return None
        value = {
            'payload': row.get('payload') if isinstance(row.get('payload'), dict) else {},
            'updated_at': row.get('updated_at'),
            'expires_at': row.get('expires_at'),
            'expired': expired,
        }
        try:
            if _local_save_snapshot is not None:
                _local_save_snapshot(namespace, snapshot_key, value['payload'], ttl_seconds=21600)
        except Exception:
            pass
        with _RC8_WRITE_LOCK:
            _RC83_READ_CACHE[cache_key] = {'ts': time.monotonic(), 'value': dict(value)}
        return value
    except Exception as exc:
        print(f"⚠️ [PERSIST] runtime snapshot load {namespace}/{snapshot_key}: {exc}")
        try:
            return _local_load_snapshot(namespace, snapshot_key, allow_expired=allow_expired) if _local_load_snapshot else None
        except Exception:
            return None


def persist_macro_events(news, calendar_rows) -> int:
    """Persist only compact metadata; never article bodies.

    Headlines remain relevant for 72h from publication. Scheduled events remain
    until 72h after their event/end. The table is deduplicated by event_key.
    """
    db = _db()
    if db is None:
        return 0
    now = utc_now()
    rows = []
    for item in list(news or []) + list(calendar_rows or []):
        if not isinstance(item, dict) or not item.get('id'):
            continue
        kind = str(item.get('kind') or 'HEADLINE').upper()
        anchor = item.get('published_at') if kind == 'HEADLINE' else (item.get('scheduled_end_at') or item.get('scheduled_at'))
        try:
            dt = datetime.fromisoformat(str(anchor).replace('Z', '+00:00')) if anchor else now
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except Exception:
            dt = now
        relevant_until = dt + timedelta(hours=72)
        categories = item.get('categories') if isinstance(item.get('categories'), list) else []
        category = ''
        if categories and isinstance(categories[0], dict):
            category = str(categories[0].get('code') or categories[0].get('label_es') or '')[:64]
        compact_payload = {
            key: item.get(key) for key in (
                'scheduled_at', 'scheduled_end_at', 'published_at', 'risk_bias',
                'threat_level', 'opportunity_level', 'opportunity_note_es',
                'time_precision', 'method'
            ) if item.get(key) is not None
        }
        rows.append({
            'event_key': str(item.get('id'))[:96],
            'kind': kind[:32],
            'title_es': str(item.get('title_es') or '')[:280],
            'source': str(item.get('source') or '')[:120],
            'url': str(item.get('url') or '')[:1000],
            'category': category,
            'risk_level': str(item.get('risk_level') or 'LOW')[:16],
            'risk_score': int(item.get('risk_score') or 0),
            'futures_posture': str(item.get('futures_posture') or 'NORMAL')[:32],
            'occurred_at': dt.isoformat(),
            'relevant_until': relevant_until.isoformat(),
            'payload': compact_payload,
            'updated_at': now.isoformat(),
        })
    if not rows:
        cleanup_ephemeral_storage()
        return 0
    macro_digest = _stable_digest(rows)
    with _RC8_WRITE_LOCK:
        if _RC8_MACRO_WRITE.get('digest') == macro_digest and (time.monotonic() - float(_RC8_MACRO_WRITE.get('ts') or 0.0)) < _RC8_IDENTICAL_WRITE_SECONDS:
            cleanup_ephemeral_storage()
            return len(rows)
    try:
        if hasattr(db, '_rest_minimal'):
            db._rest_minimal(
                'POST', MACRO_TABLE, payload=rows, params={'on_conflict': 'event_key'},
                prefer='resolution=merge-duplicates,return=minimal',
            )
        else:
            db.client.table(MACRO_TABLE).upsert(rows, on_conflict='event_key').execute()
        with _RC8_WRITE_LOCK:
            _RC8_MACRO_WRITE.update(digest=macro_digest, ts=time.monotonic())
        cleanup_ephemeral_storage(force=True)
        return len(rows)
    except Exception as exc:
        print(f"⚠️ [PERSIST] macro events save: {exc}")
        return 0


def load_active_macro_events(*, limit: int = 80):
    db = _db()
    if db is None:
        return []
    cached = _RC83_MACRO_READ_CACHE
    if cached.get('value') and (time.monotonic() - float(cached.get('ts') or 0.0)) < 600:
        return list(cached.get('value') or [])[:max(1, int(limit or 80))]
    if hasattr(db, 'free_plan_allows') and not db.free_plan_allows('optional'):
        return list(cached.get('value') or [])[:max(1, int(limit or 80))]
    now = utc_now().isoformat()
    try:
        response = (
            db.client.table(MACRO_TABLE)
            .select('event_key,kind,title_es,source,url,category,risk_level,risk_score,futures_posture,occurred_at,relevant_until,payload')
            .gte('relevant_until', now)
            .order('occurred_at', desc=True)
            .limit(max(1, min(250, int(limit or 80))))
            .execute()
        )
        result = []
        for row in response.data or []:
            payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
            item = {
                'id': row.get('event_key'),
                'kind': row.get('kind'),
                'title_es': row.get('title_es'),
                'source': row.get('source'),
                'url': row.get('url'),
                'risk_level': row.get('risk_level'),
                'risk_score': row.get('risk_score'),
                'futures_posture': row.get('futures_posture'),
                **payload,
            }
            result.append(item)
        _RC83_MACRO_READ_CACHE['ts'] = time.monotonic()
        _RC83_MACRO_READ_CACHE['value'] = list(result)
        return result
    except Exception as exc:
        print(f"⚠️ [PERSIST] macro events load: {exc}")
        return []


def cleanup_ephemeral_storage(*, force: bool = False) -> bool:
    global _CLEANUP_LAST
    now_mono = time.monotonic()
    if not force and now_mono - _CLEANUP_LAST < 3600:
        return True
    db = _db()
    if db is None:
        return False
    _CLEANUP_LAST = now_mono
    now = utc_now().isoformat()
    ok = True
    try:
        db.client.table(RUNTIME_TABLE).delete().lt('expires_at', now).execute()
        # Keep only a small number of recent ephemeral snapshots. Durable
        # signals/results are in other tables and are never touched here.
        extra = (
            db.client.table(RUNTIME_TABLE)
            .select('namespace,snapshot_key')
            .order('updated_at', desc=True)
            .range(60, 159)
            .execute()
        )
        for row in extra.data or []:
            db.client.table(RUNTIME_TABLE).delete() \
                .eq('namespace', row.get('namespace')) \
                .eq('snapshot_key', row.get('snapshot_key')).execute()
    except Exception as exc:
        ok = False
        print(f"⚠️ [PERSIST] cleanup runtime snapshots: {exc}")
    try:
        db.client.table(MACRO_TABLE).delete().lt('relevant_until', now).execute()
    except Exception as exc:
        ok = False
        print(f"⚠️ [PERSIST] cleanup macro events: {exc}")
    # Hard cap the ephemeral macro table to the newest 250 rows. We deliberately
    # leave durable trading outcomes/signals untouched.
    try:
        response = (
            db.client.table(MACRO_TABLE)
            .select('event_key')
            .order('updated_at', desc=True)
            .range(250, 499)
            .execute()
        )
        old_keys = [r.get('event_key') for r in (response.data or []) if r.get('event_key')]
        if old_keys:
            db.client.table(MACRO_TABLE).delete().in_('event_key', old_keys).execute()
    except Exception as exc:
        ok = False
        print(f"⚠️ [PERSIST] cleanup macro cap: {exc}")
    return ok
