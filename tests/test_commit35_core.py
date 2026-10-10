"""Commit 35 regression tests independent of deployed services/secrets."""
import ast
from pathlib import Path
import importlib.util
import json
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)


def _isolated(*names, env=None):
    module = ast.Module(body=[n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {} if env is None else dict(env)
    exec(compile(module, 'app.py', 'exec'), ns)
    return ns


def test_futures_snapshot_compacts_before_json_validation():
    class ForbiddenOriginal:
        def __str__(self):
            raise AssertionError('attempted to serialize raw result')
    ns = _isolated('_serialize_futures_cache', env={
        '_compact_futures_runtime_result': lambda v: {'success':True, 'decision':{'action':v['decision']['action']},'levels':{'entry':3.0},'signal_id':'s'},
    })
    original = {'decision':{'action':'SHORT'},'huge_df':ForbiddenOriginal()}
    out = ns['_serialize_futures_cache']({'analysis':{('BTC-USDT','1h'):original}, 'lifecycle':{'s':{'valid_until':'2026-10-11T00:00:00Z'}}})
    assert out['analysis_serial']['BTC-USDT|1h']['decision']['action']=='SHORT'
    assert 'huge_df' not in out['analysis_serial']['BTC-USDT|1h']
    assert out['lifecycle']['s']['valid_until']=='2026-10-11T00:00:00Z'


def test_snapshot_rejects_oversized_compacted_payload():
    ns = _isolated('_serialize_futures_cache', env={
        '_compact_futures_runtime_result': lambda v: {'success':True,'message':'X'*210000},
    })
    out = ns['_serialize_futures_cache']({'analysis':{('BTC','1h'):{'anything':1}}})
    assert out['analysis_serial']['BTC|1h']['success'] is True
    assert len(out['analysis_serial']['BTC|1h'].get('message', '')) == 700



def test_backtest_authority_not_modified():
    for name in ('_apply_profitability_router', '_core_publication_authority', '_apply_96_futures_risk_policy', '_apply_36s_futures_ai_control'):
        assert any(isinstance(n, ast.FunctionDef) and n.name==name for n in TREE.body)
    assert 'COMMIT35_CORE_RESOURCE_RELIABILITY_V1' in SOURCE
    assert "'FAST_FUTURES_UI_CACHE_TTL_SECONDS', '150'" in SOURCE
    assert "'FUTURES_UI_CACHE_TTL_SECONDS', '300'" in SOURCE


def test_recommendation_is_cache_only_no_heavy_or_analysis_calls():
    fn = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='api_commit35_recommendation_ready')
    text=ast.get_source_segment(SOURCE,fn)
    for forbidden in ('analyze_full_market(', '_acquire_heavy_analysis(', 'analyze_futures_market(', 'send_telegram_alert(', '_run_spot_intrabar_preview('):
        assert forbidden not in text
    for term in ('_futures_analysis_cache', '_MULTI_ASSET_CACHE', '_ANALYSIS_CACHE'):
        assert term in text
    assert 'historical_reference' in text and 'display_only' in text


def test_delivery_uses_remote_ack_before_send():
    src=SOURCE
    assert 'require_remote=True' in src
    send=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_attempt_confirmed_outbox_event_inner')
    text=ast.get_source_segment(SOURCE,send)
    assert "if not bool(item.get('_c35_remote_persisted')):" in text
    assert text.index("if not bool(item.get('_c35_remote_persisted')):") < text.index('send_telegram_alert(')


def test_snapshot_strict_mode_no_supabase_returns_false(monkeypatch):
    spec=importlib.util.spec_from_file_location('commit35_runtime_persist', ROOT/'runtime_persistence.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, '_db', lambda:None)
    monkeypatch.setattr(mod, '_local_save_snapshot', lambda *_args, **_kwargs:True)
    assert mod.save_runtime_snapshot('telegram','test',{'events':{}},require_remote=True) is False
    assert mod.save_runtime_snapshot('runtime','test',{'events':{}},require_remote=False) is True


def test_memory_floor_not_liberalized_to_48_mb():
    fn = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_commit346_cgroup_budget')
    text = ast.get_source_segment(SOURCE,fn)
    assert 'max(64.0, min(112.0' in text
    ns=_isolated('_commit346_cgroup_budget', env={
        '_commit34_cgroup_mb':lambda:(445.,512.),
        '_commit346_inactive_file_mb':lambda:300.0,
    })
    assert ns['_commit346_cgroup_budget'](160.)['safe'] is False
    ns=_isolated('_commit346_cgroup_budget', env={
        '_commit34_cgroup_mb':lambda:(280.,512.),
        '_commit346_inactive_file_mb':lambda:0.0,
    })
    assert ns['_commit346_cgroup_budget'](160.)['safe'] is True


def test_frontend_resilience_polling_is_passive():
    src=(ROOT/'static'/'script.js').read_text(encoding='utf-8')
    assert 'watchTechnicalRecommendationReady35' in src
    assert '/api/commit35/recommendation-ready?' in src
    assert 'window.updateRecommendation(payload)' in src
    assert 'document.hidden' in src


def test_http_payload_gzip_opt_in_and_json_only():
    fn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_commit35_compress_large_json_response')
    text=ast.get_source_segment(SOURCE,fn)
    assert "request.method != 'GET'" in text
    assert "response.mimetype != 'application/json'" in text
    assert "'gzip' not in accept.lower()" in text
    assert "response.headers['Vary'] = 'Accept-Encoding'" in text


def test_http_gzip_roundtrip_small_and_large():
    from types import SimpleNamespace
    import gzip
    class Response:
        status_code=200
        mimetype='application/json'
        is_streamed=False
        direct_passthrough=False
        def __init__(self,data):
            self.data=data
            self.headers={}
        def get_data(self): return self.data
        def set_data(self,data): self.data=data
    fn=_isolated('_commit35_compress_large_json_response', env={
        'app':SimpleNamespace(after_request=lambda f:f),
        'request':SimpleNamespace(method='GET',headers={'Accept-Encoding':'gzip, br'}),
    })['_commit35_compress_large_json_response']
    src=json.dumps({'signals':[{'signal_id':str(i), 'levels':'highly redundant information'*10} for i in range(250)]}).encode()
    out=fn(Response(src))
    assert gzip.decompress(out.get_data())==src
    assert out.headers.get('Content-Encoding')=='gzip'
    assert len(out.get_data())<len(src)//2
    tiny=Response(b'{"ok":true}')
    assert fn(tiny).get_data()==b'{"ok":true}'
    assert 'Content-Encoding' not in tiny.headers


def test_readonly_recovery_all_markets_and_identity(monkeypatch):
    import sys
    import threading
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'futures_system',SimpleNamespace(FUTURES_SYMBOLS={'BTC-USDT':{}},FUTURES_TIMEFRAMES={'1h':{}}))
    monkeypatch.setitem(sys.modules,'multiasset_system',SimpleNamespace(MULTIASSET_SYMBOLS={'CL-USDT':{}},MULTIASSET_TIMEFRAMES={'4h':{}}))
    cache_f={'lock':threading.Lock(),'data':{'analysis':{('BTC-USDT','1h'):{
        'success':True,'symbol':'BTC-USDT','timeframe':'1h',
        'decision':{'action':'SHORT','confidence':88,'reason':'DMI bajista'},
        'levels':{'entry':80000.0,'stop_loss':81000.0,'take_profit':78000.0},
        'quality_context':{'momentum':{'rsi':29}}, 'source_candle_close_timestamp':'2026-10-10T12:00:00Z'
    }}}}
    cache_m={'lock':threading.Lock(),'analysis':{('CL-USDT','4h'):{
        'success':True,'symbol':'CL-USDT','timeframe':'4h',
        'decision':{'action':'LONG','confidence':85,'reason':'soporte'},
        'levels':{'entry':90.0,'stop_loss':89.0,'take_profit':92.0},
        'quality_context':{'volatility':{'atr_pct':2.3}}
    }}}
    cache_spot={('BTC-USDT','1D'):{'data':{
        'success':True,'symbol':'BTC-USDT','timeframe':'1D',
        'decision':{'action':'COMPRA_SPOT','confidence':73,'reason':'rebote'},
        'levels':{},
    }}}
    args={}
    dec=SimpleNamespace(get=lambda k,d=None:args.get(k,d))
    ns=_isolated('api_commit35_recommendation_ready',env={
        'app':SimpleNamespace(route=lambda *_args,**_kwargs:(lambda f:f)),
        'request':SimpleNamespace(args=dec), 'jsonify':lambda x:x,
        '_get_futures_ui_cached':lambda sym,tf:None,
        '_futures_analysis_cache':cache_f,
        '_MULTI_ASSET_CACHE':cache_m,
        '_ANALYSIS_CACHE':cache_spot,'_ANALYSIS_CACHE_LOCK':threading.Lock(),
        'SYMBOLS':{'BTC-USDT':{}},'TIMEFRAMES':{'1D':{}},
    })
    fn=ns['api_commit35_recommendation_ready']
    for market,symbol,tf,expected in [('futures','BTC-USDT','1h','SHORT'),('multiasset','CL-USDT','4h','LONG'),('spot','BTC-USDT','1D','COMPRA_SPOT')]:
        args.clear();args.update(market=market,symbol=symbol,timeframe=tf)
        body,code=fn()
        assert code==200 and body['ready'] is True
        assert body['data']['decision']['action']==expected
        assert body['data']['historical_reference'] is True
        assert body['data']['display_only'] is True
    args.update(market='futures',symbol='ETH-USDT',timeframe='1h')
    body,code=fn()
    assert code==400 and body['ready'] is False


def test_failed_persistence_blocks_telegram_enqueue():
    import threading
    dummy={'state':'PENDING'}
    ns=_isolated('_confirmed_outbox_enqueue',env={
        'time':time,
        '_compact_confirmed_outbox_signal':lambda m,s:{'symbol':'BTC-USDT'},
        '_confirmed_signal_outbox':{},
        '_confirmed_signal_outbox_lock':threading.Lock(),
        '_save_confirmed_signal_outbox_to_disk':lambda:False,
    })
    assert ns['_confirmed_outbox_enqueue']('futures',{},'event-a') is None
    assert ns['_confirmed_signal_outbox']['event-a']['state']=='PENDING'
    assert ns['_confirmed_signal_outbox']['event-a']['_c35_remote_persisted'] is False
    ns['_save_confirmed_signal_outbox_to_disk']=lambda:True
    # A freshly recorded event with remote success becomes deliverable.
    assert ns['_confirmed_outbox_enqueue']('futures',{},'event-b') is not None
    assert ns['_confirmed_signal_outbox']['event-b']['_c35_remote_persisted'] is True


def test_signal_cards_do_not_schedule_analysis():
    for name in ('api_futures_signals_active','api_futures_signals_previous'):
        fn = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name==name)
        text=ast.get_source_segment(SOURCE,fn)
        assert 'cache = _get_futures_analysis_snapshot_read_only()' in text
        assert 'cache = _get_or_refresh_futures_analysis()' not in text


def test_static_cache_version_matches_new_frontend():
    html=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
    assert 'COMMIT35-CORE-RELIABILITY' in html


def test_nonfinite_indicator_does_not_drop_signal_snapshot():
    ns=_isolated('_serialize_futures_cache',env={
        '_compact_futures_runtime_result': lambda v: {'success':True,'quality_context':{'momentum':{'rsi':float('nan')}},'levels':{'entry':90.0}},
    })
    out=ns['_serialize_futures_cache']({'analysis':{('CL-USDT','4h'):{}}})
    assert out['analysis_serial']['CL-USDT|4h']['quality_context']['momentum']['rsi'] is None
