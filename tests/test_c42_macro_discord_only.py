"""C42 isolated tests; no network, Telegram, keys or running trading engine."""
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import discord_macro_alerts as alerts
import macro_context as ctx


def _row(kind, title, key, stamp, level='HIGH', bias='NEUTRAL', precision='EXACT'):
    result = ctx.classify_macro_headline(title)
    return {'id':key, 'kind':kind, 'title_es':title,'source':'Fuente oficial',
            'url':'https://www.bls.gov/schedule/news_release/cpi.htm',
            'scheduled_at':stamp.isoformat() if kind == 'SCHEDULED_EVENT' else None,
            'published_at':stamp.isoformat() if kind == 'HEADLINE' else None,
            'risk_level':level,'risk_bias':bias,'risk_score':85,
            'time_precision':precision,
            'categories':result['categories']}


def _snapshot_with_news():
    now=datetime.now(timezone.utc)
    row=_row('HEADLINE','OPEC cuts: oil supply cut', 'oil-cut',now-timedelta(minutes=5))
    raw=ctx._build_alert_candidates([], [row], now)
    return {'headlines':[row], 'upcoming_events':[], 'discord_alert_candidates':raw,
            'scientist_interpretation':{'status':'DISABLED'}}


def test_alerts_for_24h_3h_30m_and_no_unknown_hour():
    now=datetime(2026,10,14,12,0,tzinfo=timezone.utc)
    cases=[('24H',24),('3H',3),('30M',.5)]
    for label, hours in cases:
        row=_row('SCHEDULED_EVENT','IPC inflación Estados Unidos', label,
                 now+timedelta(hours=hours))
        result=ctx._build_alert_candidates([row], [], now)
        assert len(result)==1
        assert result[0]['window']==label
        assert result[0]['url'].startswith('https://')
        assert result[0]['kind']=='SCHEDULED_EVENT'
    row=_row('SCHEDULED_EVENT','Reunión de la Fed','unknown_hour',
             now+timedelta(hours=24),precision='DATE_ONLY')
    date_only = ctx._build_alert_candidates([row],[],now)
    assert len(date_only)==1 and date_only[0]['window']=='DAY_AHEAD'
    assert all(a['window'] not in ('3H','30M') for a in date_only)


def test_war_and_cex_high_without_risk_off_and_stale_filter():
    now=datetime.now(timezone.utc)
    for title in ('Military strikes: war escalates', 'Major crypto exchange suspends withdrawals'):
        row=_row('HEADLINE',title, 'news',now-timedelta(minutes=7),bias='NEUTRAL')
        result=ctx._build_alert_candidates([], [row], now)
        assert len(result)==1, title
        row['published_at']=(now-timedelta(hours=6)).isoformat()
        assert ctx._build_alert_candidates([], [row], now)==[]


def test_each_news_alert_has_its_own_impact_not_combined_and_link():
    snap=_snapshot_with_news()
    msg=alerts.format_alert(snap,snap['discord_alert_candidates'][0])
    assert 'NOTICIA FUNDAMENTAL' in msg
    assert 'WTI: favorable (potencial)' in msg
    assert 'STAR 50: desfavorable (potencial)' in msg
    assert 'Abrir enlace: <https://www.bls.gov/schedule/news_release/cpi.htm>' in msg
    assert 'TraderMacro' not in msg and 'C41' not in msg
    assert 'sin evaluación individual disponible' in msg
    assert len(msg)<2000


def test_calendar_uncertainty_no_direction_and_bolivia_time():
    now=datetime.now(timezone.utc)
    row=_row('SCHEDULED_EVENT','IPC inflación Estados Unidos','cpi',now+timedelta(minutes=30))
    snap={'headlines':[], 'upcoming_events':[row],
          'scientist_interpretation':{'status':'PENDING'}}
    cands=ctx._build_alert_candidates([row], [], now)
    txt=alerts.format_alert(snap,cands[0])
    assert 'Resultado aún no publicado' in txt
    assert 'Bolivia' in txt
    assert 'favorable (potencial)' not in txt
    assert 'desfavorable (potencial)' not in txt


def test_scientist_only_claims_news_with_evidence_id():
    snap=_snapshot_with_news()
    candidate=snap['discord_alert_candidates'][0]
    snap['scientist_interpretation']={'status':'READY','summary':'no relevant',
        'asset_impacts':{'ENERGIA_PETROLEO':{'impact':'BENEFICIA','evidence_ids':['other-id'], 'why':'Inventado'}}}
    msg=alerts.format_alert(snap,candidate)
    assert 'no tiene una conclusión individual' in msg and 'Inventado' not in msg
    snap['scientist_interpretation']['asset_impacts']['ENERGIA_PETROLEO']['evidence_ids']=['oil-cut']
    snap['scientist_interpretation']['asset_impacts']['ENERGIA_PETROLEO']['why']='Recorte de oferta verificado'
    msg=alerts.format_alert(snap,candidate)
    assert 'Recorte de oferta verificado' in msg


def _reset():
    alerts._NEXT_TICK=0
    alerts._NEXT_TRY.clear()
    alerts._NEWS_NEXT=0
    alerts._SENT_RECENT.clear()
    alerts._NEWS_TODAY.clear()


def test_dispatch_only_after_ack_and_durable_key(monkeypatch):
    _reset()
    monkeypatch.setenv('DISCORD_MACRO_WEBHOOK_URL', 'https://discord.com/api/webhooks/12345/valid-token')
    snap=_snapshot_with_news()
    persisted=[]
    with patch.object(alerts,'deliver', return_value=(False,60,'HTTP_429')) as send:
        with patch.object(alerts.time,'monotonic',return_value=1000):
            assert not alerts.dispatch_macro_alerts(snap,already_sent=lambda key:False,
                        mark_sent=lambda key,text:persisted.append(key))
    assert not persisted and send.call_count==1
    with patch.object(alerts,'deliver',return_value=(True,0,'')):
        with patch.object(alerts.time,'monotonic',return_value=1100):
            assert alerts.dispatch_macro_alerts(snap,already_sent=lambda key:False,
                        mark_sent=lambda key,text:persisted.append(key))
    assert persisted==['DISCORD_C42:oil-cut:BREAKING']
    with patch.object(alerts,'deliver') as send:
        with patch.object(alerts.time,'monotonic',return_value=1200):
            assert not alerts.dispatch_macro_alerts(snap,already_sent=lambda key:False,
                        mark_sent=lambda key,text:persisted.append(key))
            send.assert_not_called()
    _reset()


def test_no_webhook_no_delivery_no_fallback(monkeypatch):
    _reset()
    monkeypatch.delenv('DISCORD_MACRO_WEBHOOK_URL', raising=False)
    monkeypatch.setenv('DISCORD_GUARDIAN_WEBHOOK_URL','https://discord.com/api/webhooks/12345/private-token')
    monkeypatch.setenv('DISCORD_CONFIRMED_WEBHOOK_URL','https://discord.com/api/webhooks/12345/public-token')
    with patch.object(alerts,'deliver') as send:
        assert not alerts.dispatch_macro_alerts(_snapshot_with_news(),already_sent=lambda _:False,
                              mark_sent=lambda *_:None)
        send.assert_not_called()
    assert not alerts.enabled()


def test_macro_only_discord_retired_telegram_pipeline():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    start=app.index('def macro_context_alert_loop():')
    end=app.index('def _start_background_threads():',start)
    section=app[start:end]
    assert 'send_telegram_alert(' not in section
    assert 'target=macro_context_alert_loop' not in app
    assert 'dispatch_macro_alerts(' in app
    html=(ROOT/'templates/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/script.js').read_text(encoding='utf-8')
    macro=(ROOT/'macro_context.py').read_text(encoding='utf-8')
    assert 'TraderMacro · impacto' not in html
    assert 'Radar C41' not in macro
    assert "'telegram_alert_candidates': []" in macro or '"telegram_alert_candidates": []' in macro
    assert 'Fuentes · ${status}' not in js
    assert 'science.status ||' not in js


def test_post_is_json_mentions_off(monkeypatch):
    monkeypatch.setenv('DISCORD_MACRO_WEBHOOK_URL','https://discord.com/api/webhooks/12345/valid-token')
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): return False
    def fake_open(req,timeout):
        assert timeout==3
        assert req.get_method()=='POST'
        assert req.full_url.endswith('?wait=true')
        content=json.loads(req.data.decode('utf-8'))
        assert content['allowed_mentions']['parse']==[]
        assert 'NOTICIA FUNDAMENTAL' in content['content']
        return Response()
    with patch.object(alerts.urllib.request,'urlopen',side_effect=fake_open):
        assert alerts.deliver('🧭 NOTICIA FUNDAMENTAL',timeout=3)==(True,0,'')


def test_invalid_link_or_missing_evidence_not_sent():
    snap=_snapshot_with_news()
    candidate=snap['discord_alert_candidates'][0]
    snap['headlines'][0]['url']='javascript:alert(1)'
    assert alerts.format_alert(snap,candidate)==''
    snap['headlines']=[]
    assert alerts.format_alert(snap,candidate)==''


def test_official_date_only_alert_does_not_invent_hour():
    now=datetime.now(timezone.utc)
    row=_row('SCHEDULED_EVENT','FOMC meeting','fomc',now+timedelta(hours=24), precision='DATE_ONLY')
    snap={'upcoming_events':[row], 'headlines':[], 'scientist_interpretation':{'status':'DISABLED'}}
    candidate=ctx._build_alert_candidates([row],[],now)[0]
    msg=alerts.format_alert(snap,candidate)
    assert 'calendario aún no confirma una hora' in msg
    assert '🕒' not in msg
    assert 'Abrir enlace' in msg

def test_supply_shock_and_stimulus_reach_alert_threshold():
    titles=('OPEC cuts oil supply', 'LNG terminal shutdown affects natural gas',
            'China stimulus package announced', 'Copper mine shutdown after strike')
    for name in titles:
        assert ctx.classify_macro_headline(name)['risk_level'] in ('HIGH', 'CRITICAL'), name
