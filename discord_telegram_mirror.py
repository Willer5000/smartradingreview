"""Best-effort Discord parity for non-confirmation/non-Guardian Telegram events.

Confirmed signals have their own authoritative, persistent Discord outbox in
app.py. Personal saved expirations and Guardian advice have an opt-in private
outbox in discord_guardian.py. This module mirrors other Telegram alerts
(e.g. Entry touched, macro or system notices) to the PRIVATE Guardian
webhook, without creating a worker,
rerunning market analysis or modifying Telegram ACKs.
"""
import hashlib
import os
import threading
import time

_LOCK = threading.RLock()
_EVENTS = {}
_INFLIGHT = set()
_LOADED = False
_LAST_LOAD = 0.0
_SNAPSHOT = 'telegram_misc_mirror_v1'
_MAX_ITEMS = 120
_RETENTION = 2 * 86400


def _enabled():
    # Nunca derivar notificaciones adicionales/personales al canal de
    # CONFIRMADAS compartido. El usuario configuró un webhook privado.
    return bool(os.environ.get('DISCORD_GUARDIAN_WEBHOOK_URL', '').strip())


def _eligible(message, category):
    """Avoid double delivery and leaking personal portfolio information."""
    if not _enabled() or not str(message or '').strip():
        return False
    category = str(category or '').upper()
    upper = str(message).upper()
    if category in ('CONFIRMED_SIGNAL', 'SAVED_SIGNAL_EXPIRED', 'FUTURES_GUARDIAN'):
        return False  # handled by dedicated per-event/personal outboxes
    if 'NUEVA SEÑAL CONFIRMADA' in upper:
        return False  # never bypass authoritative confirmation publication
    if 'GUARDIAN' in upper or 'TGP' in upper:
        return False  # handled by discord_guardian opt-in
    if ('PORTAFOLIO' in upper and ('👤' in message or 'USUARIO:' in upper)):
        return False  # direct Guardian notifier handles this; no duplicate
    return True


def _persist():
    try:
        from runtime_persistence import save_runtime_snapshot
        with _LOCK:
            snapshot = {key: dict(value) for key, value in _EVENTS.items()}
        return bool(save_runtime_snapshot(
            'discord', _SNAPSHOT, {'events': snapshot},
            ttl_seconds=3 * 86400, require_remote=True,
        ))
    except Exception:
        return False


def _restore():
    global _LAST_LOAD, _LOADED
    if _LOADED:
        return True
    now = time.monotonic()
    with _LOCK:
        if _LOADED:
            return True
        if now - _LAST_LOAD < 60:
            return False
        _LAST_LOAD = now
    try:
        from runtime_persistence import load_runtime_snapshot
        record = load_runtime_snapshot(
            'discord', _SNAPSHOT, allow_expired=False, require_remote=True,
        )
        events = ((record or {}).get('payload') or {}).get('events') or {}
        if not isinstance(events, dict):
            events = {}
        with _LOCK:
            for key, event in events.items():
                if isinstance(event, dict) and key not in _EVENTS:
                    _EVENTS[key] = event
            _LOADED = True
        return True
    except Exception:
        return False


def enqueue_from_telegram(message, *, category=None):
    """Persist intent independently; Telegram send result is NOT modified.

    Delivery is performed by drain() on the already running Guardian loop.
    Fail closed on missing persistence, not by raising into Telegram.
    """
    if not _eligible(message, category) or not _restore():
        return False
    body = str(message)
    category = str(category or 'OTHER').upper()[:40]
    key = hashlib.sha256((category + '\x00' + body).encode('utf-8')).hexdigest()[:40]
    now = time.time()
    with _LOCK:
        if key in _EVENTS:
            return False
        # Evict old terminal events only; never evict PENDING in order to send.
        for k, v in list(_EVENTS.items()):
            if now > float(v.get('expires_at') or 0):
                _EVENTS.pop(k, None)
        if len(_EVENTS) >= _MAX_ITEMS:
            return False
        _EVENTS[key] = {
            'state': 'PENDING', 'created_at': now,
            'expires_at': now + _RETENTION,
            'retry_at': 0.0, 'attempts': 0,
            'message': body[:1850], 'category': category,
        }
    return _persist()


def _deliver_one(key):
    with _LOCK:
        event = dict(_EVENTS.get(key) or {})
        now = time.time()
        if key in _INFLIGHT or event.get('state') != 'PENDING':
            return False
        if now > float(event.get('expires_at') or 0) or now < float(event.get('retry_at') or 0):
            return False
        _INFLIGHT.add(key)
    try:
        from discord_confirmed import deliver
        message = event.get('message') or ''
        ok, delay, reason = deliver(
            message, timeout=3,
            webhook_env='DISCORD_GUARDIAN_WEBHOOK_URL',
        )
        with _LOCK:
            record = _EVENTS.get(key)
            if record is None:
                return False
            if ok:
                record.update(state='SENT', sent_at=time.time(), message='', retry_at=0.0)
            else:
                attempts = min(9, int(record.get('attempts') or 0) + 1)
                record.update(
                    attempts=attempts,
                    retry_at=time.time() + max(float(delay or 0), min(1800.0, 30.0 * 2 ** (attempts-1))),
                    last_error=str(reason)[:50],
                )
        _persist()
        return bool(ok)
    except Exception:
        return False
    finally:
        with _LOCK:
            _INFLIGHT.discard(key)


def drain(max_items=2):
    """Retry at most 2 pending messages per existing Guardian cycle."""
    if not _enabled() or not _restore():
        return 0
    now = time.time()
    with _LOCK:
        keys = [k for k, v in _EVENTS.items()
                if v.get('state') == 'PENDING'
                and now <= float(v.get('expires_at') or 0)
                and now >= float(v.get('retry_at') or 0)]
    sent = 0
    for key in keys[:max(0, min(2, int(max_items)))]:
        sent += int(_deliver_one(key))
    return sent
