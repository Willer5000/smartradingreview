"""Discord Guardian: independent best-effort delivery, no background thread.

Only explicit new actionable Guardian decisions and saved-signal EXPIRATIONS
are enqueued. A small durable
outbox survives restarts, is retried from an existing Guardian worker, and
never changes Telegram state or the user's trading position.
"""
import os
import re
import threading
import time

from discord_confirmed import deliver, guardian_enabled

_LOCK = threading.RLock()
_EVENTS = {}
_LAST_LOAD = 0.0
_LOADED = False
_INFLIGHT = set()
_SNAPSHOT = 'discord_guardian_v1'
_MAX_ITEMS = 160


def _allowed_owner(user):
    # Guardian may include personal portfolio/position data. Explicit opt-in.
    raw = os.environ.get('DISCORD_GUARDIAN_USERS', '').strip()
    if not raw:
        return False
    users = {name.strip().casefold() for name in raw.split(',') if name.strip()}
    return str(user or '').strip().casefold() in users


def _persist():
    try:
        from runtime_persistence import save_runtime_snapshot
        with _LOCK:
            rows = {k: dict(v) for k, v in _EVENTS.items()}
        return bool(save_runtime_snapshot('discord', _SNAPSHOT, {'events': rows},
                                         ttl_seconds=3 * 86400, require_remote=True))
    except Exception:
        return False


def _restore():
    global _LOADED, _LAST_LOAD
    now = time.monotonic()
    with _LOCK:
        if _LOADED or now - _LAST_LOAD < 60:
            return _LOADED
        _LAST_LOAD = now
    try:
        from runtime_persistence import load_runtime_snapshot
        data = load_runtime_snapshot('discord', _SNAPSHOT, allow_expired=False,
                                     require_remote=True)
        rows = ((data or {}).get('payload') or {}).get('events') or {}
        if not isinstance(rows, dict):
            rows = {}
        with _LOCK:
            # Never destroy newly recorded in-memory events on a restoration.
            for key, item in rows.items():
                if isinstance(item, dict) and key not in _EVENTS:
                    _EVENTS[key] = item
            _LOADED = True
        return True
    except Exception:
        return False


def _key(user, market, subject, action, bucket):
    # Avoid PII and large free text in the key; a fixed digest handles both.
    import hashlib
    material = '|'.join(map(str, (user, market, subject, action, bucket)))
    return hashlib.sha256(material.encode('utf-8')).hexdigest()[:36]


def queue(user, market, subject, action, bucket, message, *, ttl_seconds=900):
    """Return True only if accepted by Discord; False means queued/disabled.

    No HOLD, WAIT_ENTRY or position liveness transitions are sent.
    A signal ID + material action/level bucket identifies one Guardian advice.
    """
    if not guardian_enabled() or not _allowed_owner(user):
        return False
    action = str(action or '').upper()
    if action in ('', 'HOLD', 'WAIT_ENTRY', 'MAINTAIN', 'MANTENER'):
        return False
    if not str(message or '').strip():
        return False
    if not _restore():
        # Fail closed on unavailable remote durable storage: don't send an
        # event that could be repeated after a restart.
        return False
    now = time.time()
    key = _key(user, market, subject, action, bucket)
    with _LOCK:
        existing = _EVENTS.get(key)
        if existing:
            return False  # retries happen from drain(); don't duplicate
        # Keep terminal dedup entries until their expiry; never evict PENDING.
        expired = [k for k, v in _EVENTS.items()
                   if float(v.get('expires_at') or 0) < now]
        for k in expired:
            _EVENTS.pop(k, None)
        if len(_EVENTS) >= _MAX_ITEMS:
            return False
        _EVENTS[key] = {
            'status': 'PENDING', 'created_at': now,
            # Expiraciones personales pueden reintentarse durante 24 h.
            # Guardian normal conserva su TTL previo (< 1 hora).
            'expires_at': now + min(86400 if action == 'EXPIRED' else 3600,
                                    max(90, int(ttl_seconds))),
            'retry_after': 0.0, 'attempts': 0,
            'message': str(message)[:1750], '_persisted': False,
        }
    if not _persist():
        # Prevent sending without durable idempotency; retain pending event.
        return False
    with _LOCK:
        if key in _EVENTS:
            _EVENTS[key]['_persisted'] = True
    return _deliver_one(key)


def _deliver_one(key):
    now = time.time()
    with _LOCK:
        item = dict(_EVENTS.get(key) or {})
        if key in _INFLIGHT:
            return False
        if item.get('status') != 'PENDING' or now > float(item.get('expires_at') or 0):
            return False
        if now < float(item.get('retry_after') or 0):
            return False
        _INFLIGHT.add(key)
    try:
        if not item.get('_persisted'):
            if not _persist():
                return False
            with _LOCK:
                if key in _EVENTS:
                    _EVENTS[key]['_persisted'] = True
        ok, retry_after, error = deliver(
            item.get('message'), webhook_env='DISCORD_GUARDIAN_WEBHOOK_URL',
            fallback_env='DISCORD_CONFIRMED_WEBHOOK_URL', timeout=3)
        with _LOCK:
            current = _EVENTS.get(key)
            if current is None:
                return ok
            if ok:
                current.update(status='SENT', message='', sent_at=now, retry_after=0.0)
            else:
                attempts = min(8, int(current.get('attempts') or 0) + 1)
                current.update(attempts=attempts, retry_after=now + max(float(retry_after or 0),
                                                                        min(600, 20 * (2 ** (attempts-1)))),
                               error=str(error)[:40])
        _persist()
        return ok
    finally:
        with _LOCK:
            _INFLIGHT.discard(key)


def drain(max_items=2):
    """Called from the EXISTING Guardian loop. No new scheduler/thread."""
    if not guardian_enabled() or not _restore():
        return 0
    now = time.time()
    with _LOCK:
        pending = [k for k, v in _EVENTS.items()
                   if v.get('status') == 'PENDING'
                   and now <= float(v.get('expires_at') or 0)
                   and now >= float(v.get('retry_after') or 0)]
    count = 0
    for key in pending[:max(0, min(3, int(max_items)))]:
        count += int(_deliver_one(key))
    return count


def format_futures_guardian(user, market, signal, advice, current_price, action):
    """Only actionable recommendations; no executable orders or balances."""
    m = 'MULTI-ACTIVO' if str(market).lower() == 'multiasset' else 'FUTURES'
    name = str(signal.get('symbol') or '?').upper()[:30]
    timeframe = str(signal.get('timeframe') or '?')[:10]
    direction = str(signal.get('action') or '?').upper()[:12]
    reason = str(advice.get('management_reason') or advice.get('reason') or '')[:420]
    lines = [f'🛡️ GUARDIAN {m} · {user}', f'{name} · {timeframe} · {direction}',
             f'Acción sugerida: **{action}**',
             f'Precio observado: {current_price}',
             f'SL actual: {signal.get("stop_loss") or "—"} · TP actual: {signal.get("take_profit") or "—"}']
    sl = advice.get('suggested_stop_loss')
    tp = advice.get('suggested_take_profit')
    if sl is not None and action in ('PROTECT', 'PROTECT_AND_EXTEND','PROTECT_AND_ADD','PROTECT_ADD_AND_EXTEND'):
        lines.append(f'SL sugerido: {sl}')
    if tp is not None and action in ('EXTEND','PROTECT_AND_EXTEND','ADD_AND_EXTEND','PROTECT_ADD_AND_EXTEND'):
        lines.append(f'TP sugerido: {tp}')
    if action == 'REDUCE' and advice.get('suggested_reduce_pct') is not None:
        lines.append(f'Reducir exposición sugerida: {advice["suggested_reduce_pct"]}%')
    if reason:
        lines.append('Motivo: ' + reason)
    lines.append('⚠️ Recomendación informativa. No ejecuta órdenes.')
    return '\n'.join(lines)


def format_spot_guardian(user, result, timeframe):
    action = str(result.get('action') or 'HOLD').upper()
    risk = result.get('market_risk_watch') or {}
    if action == 'HOLD' and risk.get('alert'):
        action = 'RIESGO_PORTAFOLIO'
    reason = str(result.get('reason') or risk.get('reason') or '')[:400]
    return ('🛡️ GUARDIAN SPOT · ' + str(user)[:40]
            + '\nAcción sugerida: **' + action + '**'
            + '\nTemporalidad: ' + str(result.get('best_timeframe') or timeframe or '?')[:12]
            + '\nConfianza: ' + str(result.get('confidence') or 0) + '%'
            + ('\nMotivo: ' + reason if reason else '')
            + '\n⚠️ Orientación de portafolio. No ejecuta operaciones.')
