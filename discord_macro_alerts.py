"""C42 · Economic and fundamental alerts to an *exclusive* Discord webhook.

No Telegram, persistent daemon, extra source polling, market analysis or
control of trade levels. Called only from the existing Futures lifecycle loop.
Only confirmed webhook ACKs are marked delivered by the caller's durable dedup.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

# Bounded in-memory scheduling; the durable sent register lives in review_logs.
_LOCK = threading.Lock()
_NEXT_TICK = 0.0
_NEXT_TRY = {}
_SENT_RECENT = set()
_NEWS_TODAY = {}  # best effort cap; durable dedup is checked per alert key
_NEWS_NEXT = 0.0


def _flag(name, default='true'):
    return str(os.getenv(name, default)).strip().lower() in {'1','true','yes','on','si','sí'}


def enabled():
    # Intentionally NO fallback to Guardian/confirmed: macros belong in a
    # separate channel, not a private portfolio or signal-only destination.
    return _flag('MACRO_DISCORD_ALERTS_ENABLED') and bool(
        os.getenv('DISCORD_MACRO_WEBHOOK_URL', '').strip())


def _valid_webhook(url):
    return bool(re.fullmatch(
        r'https://(?:discord\.com|discordapp\.com)/api/webhooks/\d+/[A-Za-z0-9._-]+',
        url or '', flags=re.IGNORECASE))


def _safe_source_link(raw):
    """Only genuine HTTPS source links; never supply an invented destination."""
    url = str(raw or '').strip()
    if len(url) > 480 or any(x in url for x in ('\n','\r','<','>',' ',')','(')):
        return ''
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return ''
        if parsed.port and parsed.port != 443:
            return ''
        if parsed.hostname in ('localhost', '127.0.0.1', '::1'):
            return ''
        return url
    except ValueError:
        return ''


def _safe_text(raw, length=220):
    # Markdown links and mentions are untrusted input. Disable mentions in
    # payload too; stripping formatting prevents misleading inline links.
    text = re.sub(r'[\r\n\t]+', ' ', str(raw or ''))
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace('`','').replace('@','＠').replace('||','')
    return text[:length]


def _local_when(raw):
    try:
        when = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        if when.tzinfo is None:
            return ''
        return when.astimezone(ZoneInfo('America/La_Paz')).strftime('%d/%m/%Y %H:%M (Bolivia)')
    except (ValueError, TypeError):
        return ''


def _event_row(snapshot, alert):
    kind = str(alert.get('kind') or '')
    rows = (snapshot.get('upcoming_events') or []) if kind == 'SCHEDULED_EVENT' else (snapshot.get('headlines') or [])
    event_id = str(alert.get('evidence_id') or '')
    return next((r for r in rows if isinstance(r, dict) and str(r.get('id') or '') == event_id), None)


_MARKET_EMOJI = {
    'ENERGIA_PETROLEO': '🛢️ WTI',
    'ENERGIA_GAS': '🔥 NATGAS',
    'EEUU_SP500': '🇺🇸 S&P 500 (SPY)',
    'EEUU_NASDAQ': '🇺🇸 Nasdaq (QQQ)',
    'CHINA_STAR50': '🇨🇳 STAR 50',
    'METALES_COBRE': '⛏️ Cobre',
    'METALES_PLATA': '🥈 Plata',
    'SPOT_BTC': '₿ BTC Spot',
    'SPOT_PAXG': '🥇 Oro (PAXG)',
    'SPOT_USDT': '💵 USDT Spot',
    'FUTURES_CRIPTO': '📉 Futures cripto',
}
_IMPACT_LABEL = {'BENEFICIA':'favorable (potencial)',
                 'PERJUDICA':'desfavorable (potencial)',
                 'PRECAUCION':'precaución', 'NEUTRAL':'neutral',
                 'INCIERTO':'impacto sin determinar'}


def _impact_lines(row):
    from macro_impact import evaluate_macro_impacts
    if not row:
        return ['⚠️ Efectos por mercado aún sin evidencia suficiente.']
    evaluated = evaluate_macro_impacts([row], limit=1)
    markets = evaluated.get('markets') or {}
    chosen = [key for key in _MARKET_EMOJI if (markets.get(key) or {}).get('impact')
              in ('BENEFICIA','PERJUDICA','PRECAUCION')]
    if not chosen:
        return ['⚠️ Aún no existe evidencia para asignar un impacto por mercado.']
    lines = []
    for key in chosen[:11]:
        code = str((markets.get(key) or {}).get('impact') or 'INCIERTO')
        lines.append(f'{_MARKET_EMOJI[key]}: {_IMPACT_LABEL.get(code, "precaución")}.')
    return lines


def _ai_interpretation(snapshot, alert):
    """Avoid claiming a general AI summary specifically validated this story."""
    interpretation = snapshot.get('scientist_interpretation') or {}
    if interpretation.get('status') != 'READY':
        return ('🧠 IA Científica: sin evaluación individual disponible; '
                'los efectos anteriores son escenarios condicionales basados en la fuente.')
    evid = str(alert.get('evidence_id') or '')
    evidence_rows = [
        (key, entry) for key, entry in (interpretation.get('asset_impacts') or {}).items()
        if isinstance(entry, dict) and evid in (entry.get('evidence_ids') or [])
        and entry.get('impact') in ('BENEFICIA','PERJUDICA','PRECAUCION')
    ]
    if not evidence_rows:
        return ('🧠 IA Científica: disponible para el contexto general; '
                'esta noticia no tiene una conclusión individual corroborada por la IA.')
    first = evidence_rows[0][1]
    return ('🧠 IA Científica (evidencia de esta noticia): ' +
            _safe_text(first.get('why') or 'escenario sujeto a confirmación', 170) +
            ' · Evaluación condicional, no hecho confirmado.')


def format_alert(snapshot, alert):
    """Readable public text with news source URL and only event-specific impact."""
    row = _event_row(snapshot, alert)
    if not row:
        return ''  # Do not attribute impacts to a stale/mismatched headline.
    kind = str(alert.get('kind') or '')
    title = _safe_text(row.get('title_es') or alert.get('title') or 'Acontecimiento económico')
    source = _safe_text(row.get('source') or alert.get('source') or 'Fuente pública', 75)
    url = _safe_source_link(row.get('url') or alert.get('url'))
    if not url:
        return ''  # User requires a real, openable news/calendar link.

    if kind == 'SCHEDULED_EVENT':
        date_only = str(row.get('time_precision') or '').upper() == 'DATE_ONLY'
        if date_only:
            opening = (f'📅 Evento programado: {title}. Próximo día de publicación/reunión; '
                       'el calendario aún no confirma una hora específica.')
        else:
            when = _local_when(row.get('scheduled_at'))
            horizon = {'24H':'aproximadamente 24 horas', '3H':'aproximadamente 3 horas',
                       '30M':'menos de 45 minutos'}.get(str(alert.get('window') or ''), 'pronto')
            opening = f'📅 Evento programado: {title}. Previsto en {horizon}.'
            if when:
                opening += f'\n🕒 {when}'
        opening += '\n⚠️ Resultado aún no publicado: la dirección de los mercados es incierta.'
    else:
        opening = f'🚨 Noticia relevante: {title}.'
        when = _local_when(row.get('published_at'))
        if when:
            opening += f'\n🕒 Publicada: {when}'

    lines = [
        '🧭 NOTICIA FUNDAMENTAL — ALERTA FUNDAMENTAL',
        '',
        opening,
        f'📰 Fuente: {source}',
        '',
        '**Impacto potencial (no es señal de trading):**',
        *_impact_lines(row),
        '',
        _ai_interpretation(snapshot, alert),
        '',
    ]
    # Keep the link at the end even if the content approaches the 2000-char cap.
    link_line = '🔗 Abrir enlace: <' + url + '>'
    prefix = '\n'.join(lines)
    reserve = len(link_line) + 1
    if len(prefix) + reserve > 1900:
        prefix = prefix[:1900 - reserve - 1].rstrip() + '…'
    return prefix + '\n' + link_line


def deliver(message, *, timeout=3.0):
    """Discord webhook: ACK only on 200/204, no credentials in log output."""
    url = os.getenv('DISCORD_MACRO_WEBHOOK_URL','').strip()
    if not _valid_webhook(url):
        return False, 3600, 'INVALID_WEBHOOK'
    if not message:
        return False, 3600, 'EMPTY_MESSAGE'
    payload = json.dumps({
        'username': _safe_text(os.getenv('DISCORD_MACRO_NAME', 'Noticias Fundamentales'), 80),
        'content': message[:1950],
        'allowed_mentions': {'parse': []},
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url+'?wait=true', data=payload, method='POST',
        headers={'Content-Type':'application/json','User-Agent':'SmartTradingReview-MacroDiscord/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status in (200, 204):
                return True, 0, ''
            return False, 60, 'HTTP_' + str(response.status)
    except urllib.error.HTTPError as exc:
        wait = 60.0
        if exc.code == 429:
            try:
                wait = min(3600.0, max(1.0, float(exc.headers.get('Retry-After','60'))))
            except (ValueError, TypeError, AttributeError):
                pass
        elif exc.code in (401,403,404):
            wait = 3600.0
        return False, wait, 'HTTP_' + str(exc.code)
    except Exception as exc:
        return False, 60.0, type(exc).__name__


def dispatch_macro_alerts(snapshot, *, already_sent, mark_sent):
    """Dispatch at most one due alert per 60s in an existing monitor.

    Dedup keys are scoped to C42 Discord (legacy Telegram dedup is separate).
    Retry if webhook fails; mark *only* after ACK. Rate limit news bursts.
    """
    global _NEXT_TICK, _NEWS_NEXT
    if not enabled() or not isinstance(snapshot, dict):
        return False
    if not _valid_webhook(os.getenv('DISCORD_MACRO_WEBHOOK_URL','').strip()):
        return False
    now = time.monotonic()
    if not _LOCK.acquire(blocking=False):
        return False
    try:
        if now < _NEXT_TICK:
            return False
        _NEXT_TICK = now + 60.0
        candidates = snapshot.get('discord_alert_candidates') or []
        # Priority to time-bound official events. Skip old or unsupported rows.
        candidates = sorted(candidates, key=lambda item: (
            0 if item.get('kind') == 'SCHEDULED_EVENT' else 1,
            0 if item.get('level') == 'CRITICAL' else 1,
        ))
        try:
            max_news = max(1, min(24, int(os.getenv('MACRO_DISCORD_MAX_NEWS_PER_DAY','8'))))
        except ValueError:
            max_news = 8
        today = datetime.now(ZoneInfo('America/La_Paz')).strftime('%Y-%m-%d')
        for old_day in list(_NEWS_TODAY):
            if old_day != today:
                _NEWS_TODAY.pop(old_day, None)
        for alert in candidates[:16]:
            raw_key = str(alert.get('key') or '')
            if not raw_key:
                continue
            key = 'DISCORD_C42:' + raw_key
            if key in _SENT_RECENT or now < _NEXT_TRY.get(key, 0):
                continue
            is_news = alert.get('kind') == 'HEADLINE'
            if is_news and (now < _NEWS_NEXT or _NEWS_TODAY.get(today,0) >= max_news):
                continue
            # Durable sent check survives Render restart. No expensive check
            # for alerts without an actual openable official/source URL.
            message = format_alert(snapshot, alert)
            if not message:
                continue
            if already_sent(key):
                _SENT_RECENT.add(key)
                continue
            ok, wait, reason = deliver(message)
            if ok:
                mark_sent(key, _safe_text(alert.get('title') or '', 120))
                _SENT_RECENT.add(key)
                _NEXT_TRY.pop(key, None)
                if is_news:
                    _NEWS_TODAY[today] = _NEWS_TODAY.get(today,0) + 1
                    _NEWS_NEXT = now + 600.0
                print(f'✅ [DISCORD MACRO] {alert.get("kind")}: SENT', flush=True)
                return True
            _NEXT_TRY[key] = now + max(30.0, min(3600.0,float(wait or 60.0)))
            print(f'⚠️ [DISCORD MACRO] {reason}: RETRY', flush=True)
            return False
        return False
    finally:
        if len(_SENT_RECENT) > 1500:
            _SENT_RECENT.clear()  # Supabase dedup is still authoritative.
        if len(_NEXT_TRY) > 200:
            for key in list(_NEXT_TRY):
                if _NEXT_TRY[key] < now:
                    _NEXT_TRY.pop(key, None)
        _LOCK.release()
