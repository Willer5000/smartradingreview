"""C38: bounded, optional LLM support for macro interpretation and AI fallback.

No worker loop, no training, no trading decisions, no persistence, no new
third-party dependencies. An independent learning-scientist credential is used
only when actually configured. Context is reduced before remote requests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger('SCIENTIST_SUPPORT_C38')
_lock = threading.Lock()
_macro = {'digest': '', 'at': 0.0, 'data': None, 'error_at': 0.0, 'running': False}
_usage = {'date': '', 'tokens': 0, 'calls': 0, 'backoff_until': 0.0}
_ALLOWED_ACTIONS = {'NO_OPERAR', 'PRECAUCION', 'COMPRAR', 'VENDER', 'LONG', 'SHORT', 'NEUTRAL'}


def _enabled():
    return str(os.getenv('AI_SCIENTIST_SUPPORT_ENABLED', 'true')).strip().lower() in {'1', 'true', 'yes', 'on'}


def _key():
    # The learning-scientist key is NEVER replaced with the operational key.
    k = os.getenv('GROQ_LEARNING_API_KEY', '').strip()
    if k:
        return ('GROQ', k)
    k = os.getenv('GEMINI_API_KEY', '').strip()
    if k.lower().startswith('gsk_'):
        return ('GROQ', k)
    if k:
        return ('GEMINI', k)
    return ('NONE', '')


def _budget():
    try:
        return max(1000, min(150000, int(os.getenv('AI_SCIENTIST_SUPPORT_DAILY_TOKENS', '18000'))))
    except (TypeError, ValueError):
        return 18000


def _reserve():
    now = time.time()
    date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    with _lock:
        if _usage['date'] != date:
            _usage.update({'date': date, 'tokens': 0, 'calls': 0})
        if _usage['tokens'] + 700 > _budget() or _usage['calls'] >= 40 or now < _usage['backoff_until']:
            return False
        # Reserve before request. Network errors still consume one attempt, not a storm.
        _usage['tokens'] += 700
        _usage['calls'] += 1
        return True


def _account(actual_tokens):
    try:
        extra = max(0, min(2000, int(actual_tokens) - 700))
        with _lock:
            _usage['tokens'] += extra
    except (TypeError, ValueError):
        pass


def _request_json(system, payload, max_tokens=500):
    if not _enabled():
        return None
    provider, key = _key()
    if not key or not _reserve():
        return None
    system = (system + '\nResponde SOLO JSON válido en español, sin markdown. '
                      'No inventes titulares, eventos, precios ni confirmaciones. '
                      'Tu respuesta es informativa y NO tiene autoridad para publicar, vetar, crear o modificar señales.').strip()
    content = json.dumps(payload, ensure_ascii=False, default=str)[:6000]
    try:
        if provider == 'GROQ':
            model = os.getenv('GROQ_LEARNING_MODEL', 'llama-3.3-70b-versatile').strip() or 'llama-3.3-70b-versatile'
            response = requests.post('https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': 'Bearer ' + key},
                json={'model': model, 'messages': [{'role':'system','content':system},
                                                  {'role':'user','content':content}],
                      'temperature': 0.1, 'max_completion_tokens': max_tokens,
                      'response_format': {'type': 'json_object'}}, timeout=9)
        else:
            model = os.getenv('GEMINI_LEARNING_MODEL', 'gemini-2.5-flash').strip() or 'gemini-2.5-flash'
            # Model name is configured by the owner; no tokens are borrowed from Groq.
            response = requests.post(
                'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent',
                headers={'x-goog-api-key': key, 'Content-Type': 'application/json'},
                json={'contents':[{'parts':[{'text': system + '\n' + content}]}],
                      'generationConfig': {'temperature': 0.1, 'maxOutputTokens': max_tokens,
                                           'responseMimeType': 'application/json'}}, timeout=9)
        if response.status_code == 429:
            retry = response.headers.get('Retry-After', '600')
            try: seconds = max(120, min(7200, int(float(retry))))
            except (ValueError, TypeError): seconds = 600
            with _lock: _usage['backoff_until'] = time.time() + seconds
            return None
        if not response.ok:
            # A failed model/version/credential should not cause repeated calls.
            with _lock: _usage['backoff_until'] = time.time() + 900
            log.warning('Secondary model unavailable: %s (%s)', provider, response.status_code)
            return None
        body = response.json()
        if provider == 'GROQ':
            text = body['choices'][0]['message']['content']
            _account((body.get('usage') or {}).get('total_tokens', 700))
        else:
            text = body['candidates'][0]['content']['parts'][0]['text']
            _account((body.get('usageMetadata') or {}).get('totalTokenCount', 700))
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        with _lock: _usage['backoff_until'] = max(_usage['backoff_until'], time.time() + 180)
        log.info('Secondary LLM skipped: %s', type(exc).__name__)
        return None


def _macro_payload(snapshot):
    news = []
    for row in (snapshot.get('headlines') or [])[:6]:
        if not isinstance(row, dict): continue
        news.append({'title': str(row.get('title_es') or row.get('title') or '')[:160],
                     'published_at': row.get('published_at'), 'source': row.get('source'),
                     'risk': row.get('risk_level')})
    events = []
    for row in (snapshot.get('upcoming_events') or [])[:3]:
        if not isinstance(row, dict): continue
        events.append({'title':str(row.get('title_es') or row.get('title') or '')[:120],
                       'scheduled_at': row.get('scheduled_at'), 'risk': row.get('risk_level')})
    return {'headlines':news, 'upcoming_events':events,
            'risk_level':snapshot.get('risk_level'),
            'rule_bias':snapshot.get('directional_bias'),
            'futures_posture':snapshot.get('futures_posture')}


def _clean_macro(data, digest):
    if not isinstance(data, dict): return None
    views = data.get('markets') or {}
    if not isinstance(views, dict): return None
    out = {}
    for key in ('SPOT', 'FUTURES', 'MULTIASSET'):
        row = views.get(key) or views.get(key.lower()) or {}
        if not isinstance(row, dict): row = {}
        action = str(row.get('posture') or 'PRECAUCION').upper().strip().replace('Ó','O')
        if action not in _ALLOWED_ACTIONS: action = 'NEUTRAL'
        out[key] = {'posture':action, 'rationale': str(row.get('rationale') or '')[:320]}
    return {'status':'READY', 'source':'SECONDARY_LEARNING_CREDENTIAL',
            'authority':'ADVISORY_ONLY', 'affects_signals':False,
            'headlines_digest':digest, 'summary':str(data.get('summary') or '')[:440],
            'markets':out, 'generated_at':datetime.now(timezone.utc).isoformat()}


def _macro_worker(payload, digest):
    try:
        response = _request_json(
            'Interpreta exclusivamente las noticias y calendario provistos. '
            'Distingue una implicación de riesgo general de una señal técnica. '
            'JSON: {"summary":"", "markets":{"SPOT":{"posture":"NEUTRAL","rationale":""}, '
            '"FUTURES":{"posture":"PRECAUCION","rationale":""}, '
            '"MULTIASSET":{"posture":"NEUTRAL","rationale":""}}}. '
            'posture permitido: NO_OPERAR, PRECAUCION, COMPRAR, VENDER, LONG, SHORT, NEUTRAL. '
            'Una postura no es autorización de trading.', payload, 580)
        clean = _clean_macro(response, digest)
        with _lock:
            if clean:
                _macro.update({'data':clean, 'at':time.time(), 'digest':digest})
            else:
                _macro['error_at'] = time.time()
    finally:
        with _lock:
            _macro['running'] = False


def macro_overlay(snapshot):
    """Return cached macro opinion, schedule at most one bounded on-demand call.

    Never blocks the HTTP request or the closed-candle trading engine.
    """
    if not isinstance(snapshot, dict): return {'status':'UNAVAILABLE'}
    if not _enabled() or _key()[0] == 'NONE': return {'status':'DISABLED', 'authority':'ADVISORY_ONLY'}
    payload = _macro_payload(snapshot)
    if not payload['headlines'] and not payload['upcoming_events']:
        return {'status':'NO_VERIFIED_NEWS', 'authority':'ADVISORY_ONLY'}
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()[:16]
    now = time.time()
    with _lock:
        if _macro['digest'] == digest and _macro['data'] and now-_macro['at'] < 3600:
            return dict(_macro['data'])
        can_start = not _macro['running'] and now-_macro['error_at'] > 900 and now-_macro['at'] > 2700
        if can_start:
            _macro['running'] = True
        previous = dict(_macro['data']) if _macro['data'] else None
    if can_start:
        threading.Thread(target=_macro_worker, args=(payload,digest),daemon=True,
                         name='c38-macro-llm-on-demand').start()
    if previous:
        previous['status'] = 'STALE_ADVISORY'
        return previous
    return {'status':'PENDING', 'authority':'ADVISORY_ONLY', 'affects_signals':False}


def backup_advice(context, market, question=None):
    """Optional secondary LLM for Advisor/Assistant only if primary is limited.

    Strict allowlist avoids exporting user portfolio, secrets or raw chat history.
    """
    if not _enabled() or _key()[0] == 'NONE': return None
    context = context if isinstance(context,dict) else {}
    # Copy only technical context (no balances, credentials or raw history).
    selected = context.get('selected_signal') or {}
    if not isinstance(selected, dict): selected = {}
    safe_selected = {k:selected.get(k) for k in (
        'symbol','timeframe','action','direction','confidence','risk_class','safety')
        if k in selected}
    levels = selected.get('levels') or {}
    if isinstance(levels, dict):
        safe_selected['levels'] = {k:levels.get(k) for k in (
            'entry','stop_loss','take_profit','risk_reward') if k in levels}
    macro = context.get('macro_context') or {}
    if not isinstance(macro, dict): macro = {}
    safe_macro = {k:macro.get(k) for k in (
        'risk_level','directional_bias','futures_posture','scientist_interpretation') if k in macro}
    safe_macro['headlines'] = [{'title':str(x.get('title_es') or x.get('title') or '')[:130],
                                'source':str(x.get('source') or '')[:45],
                                'published_at':x.get('published_at')}
                               for x in (macro.get('headlines') or [])[:4] if isinstance(x,dict)]
    safe = {'selected_signal':safe_selected, 'system_action':context.get('system_action'),
            'macro_context':safe_macro,
            'market':str(market)[:24], 'question':str(question or '')[:500]}
    if not safe_macro.get('risk_level'):
        try:
            from macro_context import get_macro_context_snapshot
            m = get_macro_context_snapshot(fetch_if_stale=False) or {}
            safe['macro_context'] = {k:m.get(k) for k in ('risk_level','directional_bias','futures_posture','scientist_interpretation')}
        except Exception: pass
    data = _request_json(
        'Actúa como asesor explicativo. JSON obligatorio: '
        '{"verdict":"INFO","confidence":0,"headline":"","advice":"",'
        '"why":[],"risks":[],"what_to_watch":[],"learning_hypotheses":[], '
        '"strategy_proposals":[],"system_alignment":"","personal_risk_note":"","portfolio_note":""}. '
        'No generes operaciones ni niveles nuevos; comenta el contexto suministrado.', safe, 650)
    if not data: return None
    try:
        from ai_advisor import _normalize_ai_advice
        normalized = _normalize_ai_advice(data)
        normalized['secondary_scientist_support'] = True
        normalized['production_authority'] = 'NONE'
        return normalized
    except Exception:
        return None
