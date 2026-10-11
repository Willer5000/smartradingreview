"""Commit36: isolated regression checks (no API keys/providers, no real signals)."""
import ast
import importlib.util
from pathlib import Path
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'app.py').read_text(encoding='utf8')
TREE = ast.parse(SOURCE)


def isolate(name, **deps):
    fns = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(fns) == 1, name
    fn = fns[0]
    fn.decorator_list = []
    code = compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), 'app.py', 'exec')
    ns = dict(deps)
    exec(code, ns)
    return ns[name]


def test_render_worker_scientist_outside_512mb_by_default(monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_WEB_ENABLED', raising=False)
    fn = isolate('_c36_allow_web_scientist', os=__import__('os'), _LOW_MEMORY_MODE=True)
    assert fn() is False
    monkeypatch.setenv('AI_SCIENTIST_WEB_ENABLED', '1')
    assert fn() is True
    monkeypatch.setenv('AI_SCIENTIST_WEB_ENABLED', '0')
    assert fn() is False
    monkeypatch.delenv('AI_SCIENTIST_WEB_ENABLED', raising=False)
    fn_regular = isolate('_c36_allow_web_scientist', os=__import__('os'), _LOW_MEMORY_MODE=False)
    assert fn_regular() is True


def test_candle_priority_does_not_assume_multiasset_is_due():
    fn = isolate('_c36_closed_candle_priority', globals=lambda: {'_futures_combo_due_for_closed_candle': lambda s, tf: (s,tf)==('BTC-USDT','1h')})
    assert fn('futures-incremental:BTC-USDT:1h') is True
    assert fn('futures-incremental:ADA-USDT:1h') is False
    assert fn('spot-scheduled-1D') is True
    assert fn('multi-background:CL-USDT:4h') is False
    assert fn('reviewtrader-learning:1') is False


def test_preflight_reclaim_does_not_clear_while_analysis_active():
    import unittest.mock
    lock = threading.Lock()
    global_env = {'_C36_LAST_RECLAIM': 0., '_C36_RECLAIM_LOCK': threading.Lock(),
                  '_HEAVY_ANALYSIS_LOCK': lock, 'time': SimpleNamespace(monotonic=lambda: 1000.),
                  '_shed_recreatable_memory': unittest.mock.Mock(return_value={})}
    fn = isolate('_c36_preflight_reclaim', **global_env)
    with lock:
        assert fn('futures-incremental:BTC-USDT:1h') is False
    assert fn('futures-incremental:BTC-USDT:1h') is True
    assert global_env['_shed_recreatable_memory'].call_count == 1


def test_bounded_scheduler_metrics_keys():
    metrics = {'admitted':0,'deferred':0,'reasons':{},'last_deferred':None}
    fn = isolate('_c36_sched_event', _C36_SCHED_METRICS_LOCK=threading.Lock(), _C36_SCHED_METRICS=metrics, time=time)
    for i in range(120):
        fn(f'engine{i}:cell', 'deferred', f'code_{i}')
    assert metrics['deferred']==120
    assert len(metrics['reasons'])<=29
    fn('futures-incremental:BTC-USDT:1h','admitted')
    assert metrics['admitted']==1


def test_official_id_endpoint_cache_only_and_no_telegram_send():
    node = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='api_c36_official_signal_by_id')
    segment = ast.get_source_segment(SOURCE,node)
    for forbidden in ('analyze_', '_get_futures_system(', 'send_telegram_alert(', 'load_runtime_snapshot('):
        assert forbidden not in segment
    req=SimpleNamespace(args={'market':'futures'})
    jsonify=lambda obj:obj
    rows=[{'signal_id':'id123','source_authority':'OFFICIAL_CONFIRMED_OUTBOX', 'entry':1.2}]
    fn=isolate('api_c36_official_signal_by_id', request=req,jsonify=jsonify,
               _confirmed_web_registry_rows_34_4=lambda market,lane,threshold:rows if lane=='previous' else [])
    result,status=fn('id123')
    assert status==200 and result['lane']=='confirmed' and result['signal']['entry']==1.2
    result,status=fn('no-such-id')
    assert status==404 and result['success'] is False


def test_confirmation_only_telegram_existing_authority_untouched():
    send = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_send_confirmed_signal_telegram')
    src=ast.get_source_segment(SOURCE,send)
    assert '_confirmed_signal_recent_enough(signal, timeframe)' in src
    assert '_confirmed_outbox_enqueue(market, signal, key)' in src
    assert '_attempt_confirmed_outbox_event(key)' in src
    assert 'vigent' not in src.lower()
    for name in ('_core_publication_authority','_signal_execution_geometry_status','_confirmed_web_registry_rows_34_4'):
        assert any(isinstance(n,ast.FunctionDef) and n.name==name for n in TREE.body)


def test_snapshot_read_cache_has_hard_entry_and_byte_bounds():
    spec=importlib.util.spec_from_file_location('runtime_c36',ROOT/'runtime_persistence.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with mod._RC8_WRITE_LOCK:
        for i in range(75):
            mod._cache_runtime_read_locked(('runtime',str(i)),{'payload':{'x':'A'*1000}})
        assert len(mod._RC83_READ_CACHE)<=12
        mod._cache_runtime_read_locked(('runtime','over'),{'payload':{'x':'A'*300000}})
        assert ('runtime','over') not in mod._RC83_READ_CACHE
    assert mod._RC83_READ_CACHE_MAX_BYTES<=1024*1024


def test_old_commit35_regression_source_contract_still_present():
    assert 'COMMIT35_CORE_RESOURCE_RELIABILITY_V1' in SOURCE
    assert 'RESOURCE_PRESSURE_ABORT:' in SOURCE
    assert "'memory_job_start_limit_mb'" in SOURCE
    assert '_HEAVY_ANALYSIS_LOCK' in SOURCE
    assert 'def _merge_official_telegram_rows_34_4' in SOURCE


def test_spot_lookup_is_official_confirmed_only_and_never_revives_expired():
    from datetime import datetime, timezone, timedelta
    import unittest.mock as mock
    clock=datetime(2026,10,10,6,0,tzinfo=timezone.utc)
    entry={'state':'SENT','market':'spot','signal':{
        'signal_id':'spot-id', 'symbol':'BTC-USDT','timeframe':'1D',
        'source_candle_close_timestamp':'2026-10-10T00:00:00+00:00',
        'decision':{'action':'COMPRA_SPOT','confidence':77},
        'levels':{'entry':80000,'stop_loss':78000,'take_profit':84000},
        'valid_until':'2026-10-10T18:00:00+00:00',
    }}
    from datetime import datetime as dt
    parse=lambda x: dt.fromisoformat(str(x).replace('Z','+00:00')) if x else None
    ns={
        '_confirmed_signal_outbox_lock':threading.Lock(),
        '_confirmed_signal_outbox':{'key1':entry},
        '_parse_utc_iso':parse,
        '_confirmed_signal_tf_seconds':lambda tf:86400 if tf=='1D' else 0,
        '_confirmed_signal_close_timestamp':lambda sig,tf:sig.get('source_candle_close_timestamp'),
        'datetime':datetime,'timezone':timezone,'timedelta':timedelta,
    }
    fn=isolate('_c36_official_spot_by_id',**ns)
    row=fn('spot-id',clock)
    assert row and row['lane']=='confirmed' and row['entry']==80000
    assert fn('spot-id',datetime(2026,10,11,0,0,tzinfo=timezone.utc)) is None
    assert fn('nonexistent',clock) is None
    entry['signal']['decision']['action']='ESPERAR'
    assert fn('spot-id',clock) is None
