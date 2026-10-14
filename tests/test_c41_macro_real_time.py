"""C41 · offline regression (no public HTTP, LLM or trading orders)."""
import importlib.util
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

import sys
sys.path.insert(0, str(ROOT))
import macro_context as ctx
import macro_impact as impact
import scientist_support_c38 as ai


def _headline(title, key='one', hours=1):
    data = ctx.classify_macro_headline(title)
    return {'id':key,'kind':'HEADLINE','title_es':title,'source':'Example',
            'url':'https://example.com/'+key, 'published_at':ctx._iso_utc(datetime.now(timezone.utc)-timedelta(hours=hours)),
            **data}


def test_beneficiary_oil_cut_is_not_trade_signal():
    data = impact.evaluate_macro_impacts([_headline('OPEC cuts: oil supply cut', 'oil')])
    markets = data['markets']
    assert markets['ENERGIA_PETROLEO']['impact'] == 'BENEFICIA'
    assert markets['CHINA_STAR50']['impact'] == 'PERJUDICA'
    assert markets['SPOT_PAXG']['impact'] == 'PRECAUCION'
    assert markets['FUTURES_CRIPTO']['impact'] == 'PRECAUCION'
    assert data['authority'] == 'ADVISORY_ONLY'


def test_beneficiary_china_and_copper():
    data=impact.evaluate_macro_impacts([_headline('China stimulus package announced', 'china')])
    assert data['markets']['CHINA_STAR50']['impact'] == 'BENEFICIA'
    assert data['markets']['METALES_COBRE']['impact'] == 'BENEFICIA'


def test_stablecoin_risk_is_not_bitcoin_benefit():
    d = impact.evaluate_macro_impacts([_headline('USDT depeg as Tether loses peg', 'usdt')])
    assert d['markets']['SPOT_USDT']['impact'] == 'PERJUDICA'
    assert d['markets']['SPOT_BTC']['impact'] == 'PRECAUCION'
    assert d['markets']['SPOT_PAXG']['impact'] == 'PRECAUCION'


def test_exchange_hack_affects_futures_but_not_energy():
    d = impact.evaluate_macro_impacts([_headline('Major exchange hack triggers withdrawals', 'cex')])
    assert d['markets']['FUTURES_CRIPTO']['impact'] == 'PRECAUCION'
    assert d['markets']['ENERGIA_PETROLEO']['impact'] == 'INCIERTO'


def test_calendar_does_not_predict_cpi_direction():
    data = impact.evaluate_macro_impacts([{
        'id':'bls-cpi','title_es':'IPC / inflación EE.UU.', 'kind':'SCHEDULED_EVENT',
        'source':'BLS','scheduled_at':'2026-10-14T12:30:00Z',
        'categories':[{'code':'INFLATION'}]
    }])
    assert data['markets']['SPOT_BTC']['impact'] == 'PRECAUCION'
    assert data['markets']['SPOT_PAXG']['impact'] == 'PRECAUCION'
    assert all(x['impact'] not in {'BENEFICIA','PERJUDICA'} for x in data['markets'].values())


def test_conflicting_impacts_yield_caution_not_direction():
    d = impact.evaluate_macro_impacts([_headline('Federal Reserve raises rates, rate hike', 'a'),
                                       _headline('Federal Reserve cuts rates, rate cut','b')])
    assert d['markets']['SPOT_BTC']['impact'] == 'PRECAUCION'


def test_unverified_rumors_no_direction():
    d = impact.evaluate_macro_impacts([_headline('Rumor: OPEC oil supply cut unconfirmed','c')])
    assert d['markets']['ENERGIA_PETROLEO']['impact'] == 'INCIERTO'


def test_c41_no_data_is_unknown_not_low():
    ctx._DB_HYDRATED = True
    now = datetime.now(timezone.utc)
    with ctx._LOCK:
        ctx._CACHE.update(news=[],calendar=[],news_fetched_at=0,calendar_fetched_at=0,
                          errors=[],news_successful_sources=[], calendar_successful_sources=[])
    with patch('exchange_flow_context.peek_exchange_flow_context',return_value={'available':False}):
        snap = ctx.get_macro_context_snapshot(fetch_if_stale=False)
    assert snap['risk_level'] == 'UNKNOWN'
    assert snap['data_status'] == 'NO_VERIFIED_DATA'
    assert 'market_impacts' in snap and len(snap['market_impacts']) == len(impact.MARKETS)
    assert 'NO evaluado' in snap['ticker_items'][0]['text']


def test_c41_news_timestamp_expiry_and_offline_cached_read():
    ctx._DB_HYDRATED=True
    now=datetime.now(timezone.utc)
    with ctx._LOCK:
        ctx._CACHE.update(news=[_headline('China stimulus package announced','today',1),
                                _headline('Exchange hacked', 'stale',30)], calendar=[],
                          news_successful_sources=['GDELT'],calendar_successful_sources=[],
                          news_fetched_at=1,calendar_fetched_at=1, errors=[])
    with patch('exchange_flow_context.peek_exchange_flow_context',return_value={'available':False}):
        snap=ctx.get_macro_context_snapshot(fetch_if_stale=False)
    assert [x['id'] for x in snap['headlines']] == ['today']
    assert snap['data_status'] == 'PARTIAL'  # no calendar source verified
    assert snap['market_impacts']['CHINA_STAR50']['impact'] == 'BENEFICIA'


def test_background_refresh_singleton_and_non_blocking():
    started=threading.Event()
    release=threading.Event()
    with ctx._LOCK:
        ctx._CACHE.update(news_fetched_at=0.0, calendar_fetched_at=0.0)
    def slow(force=False):
        started.set()
        release.wait(3)
    with patch.object(ctx,'refresh_macro_context', side_effect=slow), \
         patch('exchange_flow_context.get_exchange_flow_context', return_value={}):
        try:
            assert ctx.schedule_macro_refresh_if_due() is True
            assert started.wait(1.5)
            assert ctx.schedule_macro_refresh_if_due() is False
        finally:
            release.set()
    for _ in range(50):
        if not ctx._REFRESH_IN_FLIGHT:
            break
        __import__('time').sleep(.01)
    assert ctx._REFRESH_IN_FLIGHT is False


def test_scientist_invalid_evidence_discarded():
    raw={'summary':'Cuidado', 'asset_impacts':{'SPOT_BTC':{'impact':'BENEFICIA',
                         'evidence_ids':['invented'],'why':'subirá seguro'}}}
    clean=ai._clean_macro(raw, 'digest', {'real-id'})
    assert clean['asset_impacts']['SPOT_BTC']['impact'] == 'INCIERTO'
    assert clean['affects_signals'] is False
    assert clean['authority'] == 'ADVISORY_ONLY'


def test_c41_integrated_with_main_and_safe_ui():
    app=(ROOT/'app.py').read_text(encoding='utf8')
    js=(ROOT/'static'/'script.js').read_text(encoding='utf8')
    html=(ROOT/'templates'/'index.html').read_text(encoding='utf8')
    assert "schedule_macro_refresh_if_due()" in app
    assert "data['refresh_scheduled']" in app
    assert "'SPOT_BTC' if symbol == 'BTC-USDT'" in app
    assert 'macro-impact-details' in html
    assert 'textContent' in js and '_macroRenderImpacts' in js
    assert 'MACRO_EVENT_RISK' in app and 'MACRO_NEWS_RISK' in app


def test_official_bls_html_fallback_reads_actual_date_and_hour():
    html = """<html><body><table><tr><th>Reference Month</th><th>Release Date</th><th>Release Time</th></tr>
    <tr><td>September 2026</td><td>Oct. 14, 2026</td><td>08:30 AM</td></tr>
    <tr><td>October 2026</td><td>Nov. 10, 2026</td><td>08:30 AM</td></tr></table></body></html>"""
    now = datetime(2026,10,14,11,0,tzinfo=timezone.utc)
    parsed = ctx._parse_bls_release_page(html,'CPI',now)
    assert len(parsed) == 1
    assert parsed[0]['scheduled_at'] == '2026-10-14T12:30:00Z'
    assert parsed[0]['time_precision'] == 'EXACT'
    assert parsed[0]['method'] == 'BLS_OFFICIAL_HTML_FALLBACK'


def test_official_bls_no_published_hour_means_no_event():
    html="<table><tr><td>September 2026</td><td>Oct. 14, 2026</td><td>unknown</td></tr></table>"
    now=datetime(2026,10,14,11,tzinfo=timezone.utc)
    assert ctx._parse_bls_release_page(html,'CPI',now) == []


def test_depeg_is_critical_market_stress():
    c=ctx.classify_macro_headline('USDT depeg as Tether loses peg')
    assert c['risk_level'] == 'CRITICAL'


def test_single_media_headline_does_not_get_live_vote_authority():
    only_one = impact.evaluate_macro_impacts([_headline('Federal Reserve cuts rates, rate cut','media')])
    assert only_one['markets']['SPOT_BTC']['impact'] == 'BENEFICIA'
    assert only_one['markets']['SPOT_BTC']['confidence'] < 55


def test_official_news_has_higher_evidence_authority_not_llm():
    news = _headline('Federal Reserve cuts rates, rate cut','fed')
    news['source']='Federal Reserve RSS'
    d = impact.evaluate_macro_impacts([news])
    assert d['markets']['SPOT_BTC']['confidence'] >= 55
    assert d['authority'] == 'ADVISORY_ONLY'


def test_generic_geopolitics_is_caution_not_guaranteed_oil_gain():
    d=impact.evaluate_macro_impacts([_headline('Unrest in Israel and Iran raises geopolitical tensions','geo')])
    assert d['markets']['ENERGIA_PETROLEO']['impact'] == 'PRECAUCION'
    assert d['markets']['SPOT_PAXG']['impact'] == 'PRECAUCION'
