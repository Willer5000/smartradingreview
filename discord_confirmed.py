"""Envío ligero y opcional de CONFIRMACIONES oficiales a un webhook Discord.

No crea threads, no importa el motor de análisis, no registra secretos. El
control de idempotencia y reintentos se realiza en el outbox del llamador.
"""
import json
import os
import re
from html import unescape
from html.parser import HTMLParser
import urllib.error
import urllib.request


def enabled():
    return bool(os.environ.get('DISCORD_CONFIRMED_WEBHOOK_URL', '').strip())


def guardian_enabled():
    return bool(os.environ.get('DISCORD_GUARDIAN_WEBHOOK_URL', '').strip()
                or os.environ.get('DISCORD_CONFIRMED_WEBHOOK_URL', '').strip())


class _TelegramHTMLToText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs).get('href'))
        elif tag == 'br':
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'a' and self.links:
            url = self.links.pop()
            if url and url.startswith('https://smartradingreview.onrender.com/'):
                self.parts.append(' (' + url + ')')

    def handle_data(self, data):
        self.parts.append(data)


def _discord_text(value):
    raw = str(value or '')
    if '<b>' not in raw and '<a ' not in raw and '<i>' not in raw:
        return raw  # plain text and Telegram markdown are both acceptable
    parser = _TelegramHTMLToText()
    parser.feed(raw)
    return unescape(''.join(parser.parts))


def deliver(message, *, timeout=4, webhook_env='DISCORD_CONFIRMED_WEBHOOK_URL', fallback_env=None):
    """(ok, retry_after, error). ACK solamente con 200/204 confirmado."""
    url = os.environ.get(webhook_env, '').strip() or os.environ.get(fallback_env or '', '').strip()
    if not url:
        return False, 0.0, 'DISABLED'
    # No permitir URL arbitraria en variable de entorno mal configurada.
    if not re.fullmatch(r'https://(?:discord\.com|discordapp\.com)/api/webhooks/\d+/[A-Za-z0-9._-]+', url):
        return False, 3600.0, 'INVALID_WEBHOOK_URL'
    text = _discord_text(message)
    # Los enlaces oficiales pueden venir como markdown Telegram [texto](url).
    # Discord soporta markdown, por lo que conservamos contenido y enlaces.
    if not text.strip():
        return False, 3600.0, 'EMPTY_MESSAGE'
    # 2000 caracteres Discord, acortar sin modificar niveles económicos al cortar:
    if len(text) > 1950:
        text = text[:1950] + '\n[Mensaje truncado; consultar señal en SmartTradingReview]'
    payload = json.dumps({
        'username': os.environ.get('DISCORD_CONFIRMED_NAME', 'Captain Hook')[:80],
        'content': text,
        'allowed_mentions': {'parse': []},
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url + '?wait=true', data=payload,
                                 headers={'Content-Type': 'application/json',
                                          'User-Agent': 'SmartTradingReview-Confirmed/1.0'},
                                 method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status in (200, 204), 0.0, ''
    except urllib.error.HTTPError as exc:
        delay = 60.0
        if exc.code == 429:
            try:
                delay = max(1.0, min(3600.0, float(exc.headers.get('Retry-After', 60))))
            except (ValueError, TypeError):
                pass
        elif exc.code in (401, 403, 404):
            delay = 3600.0
        return False, delay, 'HTTP_' + str(exc.code)
    except Exception as exc:
        return False, 60.0, exc.__class__.__name__
