"""RC9.7 — local fail-open resilience for Supabase outages/restrictions.

The trading engine must not depend on the research/database control plane to
calculate a thesis or validate Entry/SL/TP/Safety.  This module provides two
bounded local facilities using only the Python standard library:

* runtime snapshots so a live Render process can continue restoring the most
  recent Spot/Futures state while Supabase is unavailable;
* a small idempotent outbox for critical learning writes that can be replayed
  after Supabase recovers.

Render's local filesystem is ephemeral.  This is continuity for a running
instance/restart on the same disk, not a replacement for durable storage.
The contingency strategy bank remains the cold-start fallback when both the
remote database and local snapshot are absent.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

VERSION = "RC9_7_LOCAL_RESILIENCE_V1"
def _project_fingerprint() -> str:
    """Isolate local state by Supabase project to prevent cross-project replay.

    Changing CENTRAL_SUPABASE_URL/SUPABASE_URL intentionally starts with a new
    SQLite file.  Therefore an outbox generated for an old Supabase project can
    never be replayed into a fresh database.
    """
    raw = str(
        os.getenv("CENTRAL_SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
        or "UNCONFIGURED"
    ).strip().lower()
    # Supabase URLs are normally https://<project-ref>.supabase.co.  Hashing the
    # entire URL also behaves safely with custom domains.
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]


_PROJECT_FINGERPRINT = _project_fingerprint()
_DB_PATH = os.getenv(
    "LOCAL_RESILIENCE_PATH",
    f"/tmp/smartradingreview-resilience-{_PROJECT_FINGERPRINT}.sqlite3",
)
_MAX_OUTBOX = max(200, min(10000, int(os.getenv("LOCAL_RESILIENCE_MAX_OUTBOX", "3000") or 3000)))
_MAX_SNAPSHOTS = max(30, min(1000, int(os.getenv("LOCAL_RESILIENCE_MAX_SNAPSHOTS", "250") or 250)))
_LOCK = threading.RLock()
_INIT = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _conn() -> sqlite3.Connection:
    global _INIT
    directory = os.path.dirname(_DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    con = sqlite3.connect(_DB_PATH, timeout=1.5, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    if not _INIT:
        with _LOCK:
            if not _INIT:
                con.execute(
                    """CREATE TABLE IF NOT EXISTS runtime_snapshots (
                        namespace TEXT NOT NULL,
                        snapshot_key TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        expires_at TEXT,
                        PRIMARY KEY(namespace, snapshot_key)
                    )"""
                )
                con.execute(
                    """CREATE TABLE IF NOT EXISTS rest_outbox (
                        op_key TEXT PRIMARY KEY,
                        method TEXT NOT NULL,
                        table_name TEXT NOT NULL,
                        payload TEXT,
                        params TEXT,
                        prefer TEXT,
                        created_at TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT
                    )"""
                )
                con.commit()
                _INIT = True
    return con


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def save_snapshot(namespace: str, snapshot_key: str, payload: Dict[str, Any], *, ttl_seconds: int = 21600) -> bool:
    if not isinstance(payload, dict):
        return False
    now = _utc_now()
    expires = now + timedelta(seconds=max(300, int(ttl_seconds or 21600)))
    try:
        with _LOCK, _conn() as con:
            con.execute(
                """INSERT INTO runtime_snapshots(namespace,snapshot_key,payload,updated_at,expires_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(namespace,snapshot_key) DO UPDATE SET
                     payload=excluded.payload,
                     updated_at=excluded.updated_at,
                     expires_at=excluded.expires_at""",
                (str(namespace)[:64], str(snapshot_key)[:128], _json(payload), now.isoformat(), expires.isoformat()),
            )
            # Bound stale/old keys; current keys are protected by recency.
            con.execute(
                """DELETE FROM runtime_snapshots WHERE rowid IN (
                       SELECT rowid FROM runtime_snapshots ORDER BY updated_at DESC LIMIT -1 OFFSET ?
                   )""",
                (_MAX_SNAPSHOTS,),
            )
            con.commit()
        return True
    except Exception:
        return False


def load_snapshot(namespace: str, snapshot_key: str, *, allow_expired: bool = False) -> Optional[Dict[str, Any]]:
    try:
        with _LOCK, _conn() as con:
            row = con.execute(
                "SELECT payload,updated_at,expires_at FROM runtime_snapshots WHERE namespace=? AND snapshot_key=? LIMIT 1",
                (str(namespace)[:64], str(snapshot_key)[:128]),
            ).fetchone()
        if not row:
            return None
        payload_raw, updated_at, expires_at = row
        expired = False
        if expires_at:
            try:
                exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                expired = _utc_now() >= exp.astimezone(timezone.utc)
            except Exception:
                expired = False
        if expired and not allow_expired:
            return None
        payload = json.loads(payload_raw or "{}")
        return {
            "payload": payload if isinstance(payload, dict) else {},
            "updated_at": updated_at,
            "expires_at": expires_at,
            "expired": expired,
            "source": "LOCAL_RESILIENCE",
        }
    except Exception:
        return None


def _op_key(method: str, table: str, payload: Any, params: Any) -> str:
    raw = _json({"method": str(method).upper(), "table": table, "payload": payload, "params": params or {}})
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def enqueue_rest(method: str, table: str, *, payload: Any = None, params: Optional[Dict[str, Any]] = None, prefer: str = "return=minimal") -> str:
    key = _op_key(method, table, payload, params)
    now = _utc_now().isoformat()
    try:
        with _LOCK, _conn() as con:
            con.execute(
                """INSERT OR IGNORE INTO rest_outbox(op_key,method,table_name,payload,params,prefer,created_at,attempts)
                   VALUES(?,?,?,?,?,?,?,0)""",
                (key, str(method).upper(), str(table), _json(payload), _json(params or {}), str(prefer or "return=minimal"), now),
            )
            con.execute(
                """DELETE FROM rest_outbox WHERE rowid IN (
                       SELECT rowid FROM rest_outbox ORDER BY created_at DESC LIMIT -1 OFFSET ?
                   )""",
                (_MAX_OUTBOX,),
            )
            con.commit()
    except Exception:
        pass
    return key


def pending_outbox(limit: int = 100) -> List[Dict[str, Any]]:
    limit = max(1, min(500, int(limit or 100)))
    try:
        with _LOCK, _conn() as con:
            rows = con.execute(
                "SELECT op_key,method,table_name,payload,params,prefer,created_at,attempts,last_error FROM rest_outbox ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            out.append({
                "op_key": row[0], "method": row[1], "table": row[2],
                "payload": json.loads(row[3] or "null"),
                "params": json.loads(row[4] or "{}"), "prefer": row[5],
                "created_at": row[6], "attempts": int(row[7] or 0), "last_error": row[8],
            })
        return out
    except Exception:
        return []


def mark_outbox_done(op_key: str) -> None:
    try:
        with _LOCK, _conn() as con:
            con.execute("DELETE FROM rest_outbox WHERE op_key=?", (str(op_key),))
            con.commit()
    except Exception:
        pass


def mark_outbox_error(op_key: str, error: Any) -> None:
    try:
        with _LOCK, _conn() as con:
            con.execute(
                "UPDATE rest_outbox SET attempts=attempts+1,last_error=? WHERE op_key=?",
                (str(error)[:300], str(op_key)),
            )
            con.commit()
    except Exception:
        pass


def status() -> Dict[str, Any]:
    snapshots = outbox = 0
    try:
        with _LOCK, _conn() as con:
            snapshots = int(con.execute("SELECT COUNT(*) FROM runtime_snapshots").fetchone()[0])
            outbox = int(con.execute("SELECT COUNT(*) FROM rest_outbox").fetchone()[0])
    except Exception:
        pass
    return {
        "version": VERSION,
        "project_fingerprint": _PROJECT_FINGERPRINT,
        "path": _DB_PATH,
        "snapshots": snapshots,
        "pending_outbox": outbox,
        "ephemeral": True,
    }
