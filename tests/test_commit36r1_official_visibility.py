"""36R.1 regression: official delivery must not disappear from the UI due to saved refs or index lag.

No live network, no heavy analysis, no Telegram dispatch.
"""
from __future__ import annotations
import ast
import importlib
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock
from types import ModuleType

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import official_signal_store as store


def event(sid, state='SENT', *, market='futures', created=None):
    ts = time.time() if created is None else created
    return {'market': market, 'key': 'confirmed-' + sid, 'state': state,
            'created_at': ts, 'updated_at': ts,
            'signal': {'signal_id': sid, 'symbol': 'SOL-USDT', 'timeframe': '2h',
                       'decision': {'action':'SHORT','confidence':83},
                       'levels': {'entry':111.135,'stop_loss':113.552,
                                  'take_profit':105.604,'leverage':24,
                                  'publication_status':'EXECUTABLE_SIGNAL'},
                       'publication_status':'EXECUTABLE_SIGNAL',
                       'source_candle_close_timestamp':'2026-10-11T04:00:00+00:00',
                       'source_candle_closed':True,'publication_eligible':True,
                       'valid_until':'2026-10-11T10:00:00+00:00'}}


def test_index_published_immediately_after_durable_write(monkeypatch):
    store.reset_index_for_tests()
    fake = ModuleType('runtime_persistence')
    fake.save_runtime_snapshot = lambda *a, **kw: True
    monkeypatch.setitem(sys.modules, 'runtime_persistence', fake)
    assert store.persist_official(event('immediate'))
    assert [x['signal']['signal_id'] for x in store.recent_official_events()] == ['immediate']


def test_persist_failure_does_not_invent_publication(monkeypatch):
    store.reset_index_for_tests()
    fake = ModuleType('runtime_persistence')
    fake.save_runtime_snapshot = lambda *a, **kw: False
    monkeypatch.setitem(sys.modules, 'runtime_persistence', fake)
    assert not store.persist_official(event('not-persisted'))
    assert store.recent_official_events() == []


def test_refresh_does_not_overwrite_concurrent_persist(monkeypatch):
    store.reset_index_for_tests()
    fake = ModuleType('runtime_persistence')
    fake.save_runtime_snapshot = lambda *a, **kw: True
    class Builder:
        def select(self,*args): return self
        def eq(self,*args): return self
        def order(self,*args,**kwargs): return self
        def limit(self,*args): return self
        def execute(self):
            # Persist occurs after DB query starts but before results come back.
            assert store.persist_official(event('new-race'))
            return type('Response',(),{'data': []})()
    class Db:
        client = type('Client',(),{'table': lambda self,*a: Builder()})()
        provider_restricted = lambda self: False
    fake._db = lambda: Db()
    fake.RUNTIME_TABLE = 'runtime_snapshots_v1'
    monkeypatch.setitem(sys.modules,'runtime_persistence',fake)
    assert any(x['signal']['signal_id']=='new-race' for x in store.recent_official_events(refresh=True))


def test_frontend_does_not_filter_real_signals_based_on_saved_refs():
    js = (BASE/'static/futures.js').read_text()
    assert 'const signals = allSignals.filter(sig => !_isSignalSavedByCurrentUser(sig));' not in js
    assert js.count('const signals = allSignals;') >= 2
    assert js.count('🔖 Ya guardada · disponible en Guardadas') >= 2
    assert 'void window.refreshUserSavedSignalRefs(false);' in js
    assert 'if (!signalsList.querySelector(\'[data-signal-id]\'))' in js
    assert 'context !== \'previous\'' in js


def test_history_is_audit_not_operational(monkeypatch):
    import pandas as pd
    from candle_close_authority_19_2_3 import signal_close_utc, tf_seconds, parse_utc
    tree = ast.parse((BASE/'app.py').read_text())
    fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_confirmed_web_recent_history_34_5')
    scope = {'_confirmed_signal_outbox_lock':Lock(),'_confirmed_signal_outbox':{},
             '_confirmed_signal_alerts_lock':Lock(),'_confirmed_signal_alerts_sent':{},
             '_parse_utc_iso':parse_utc,'_confirmed_signal_close_timestamp':signal_close_utc,
             '_confirmed_signal_tf_seconds':tf_seconds,'datetime':datetime,'timedelta':timedelta,
             'timezone':timezone,'pd':pd}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(BASE/'app.py'), 'exec'),scope)
    ev = event('expired-reference')
    ev['signal']['valid_until']='2026-10-11T06:00:00+00:00'
    monkeypatch.setattr(store,'recent_official_events',lambda:[ev])
    rows = scope['_confirmed_web_recent_history_34_5']('futures',datetime(2026,10,11,7,0,tzinfo=timezone.utc))
    assert len(rows)==1
    assert rows[0]['tradable'] is False
    assert rows[0]['manual_save_allowed'] is False


def test_official_alerts_never_emitted_on_vigency_reads():
    tree = ast.parse((BASE/'app.py').read_text())
    for func in ['api_futures_signals_active','api_multiasset_signals_active',
                 'api_futures_signals_previous','api_multiasset_signals_previous']:
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==func)
        assert '_send_confirmed_signal_telegram' not in ast.get_source_segment((BASE/'app.py').read_text(),fn)
    assert 'recent_official_history' in ast.get_source_segment((BASE/'app.py').read_text(),next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='api_futures_signals_previous'))
