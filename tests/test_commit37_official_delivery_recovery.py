"""Offline regression for Telegram->web parity after OOM/rolling deployment.

No external APIs are used, no LIVE signal is generated, no RAM-consuming
strategy is run.  These tests exercise the exact production AST functions.
"""
import ast
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from threading import Lock
import importlib
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from candle_close_authority_19_2_3 import signal_close_utc, tf_seconds, parse_utc
import official_signal_store as store


def _event(sid, market='futures', tf='2h', close='2026-10-11T04:00:00+00:00',
           until='2026-10-11T10:00:00+00:00', state='SENT'):
    is_spot = market == 'spot'
    return {
        'key': f'{market}|{sid}|{tf}', 'market': market, 'state': state,
        '_c35_remote_persisted': True,
        'created_at': 1791691200.0,
        'signal': {
            'signal_id': sid, 'symbol': 'SOL-USDT' if not is_spot else 'BTC-USDT',
            'timeframe': tf, 'source_candle_close_timestamp': close,
            'source_candle_timestamp': (parse_utc(close)-timedelta(seconds=tf_seconds(tf))).isoformat(),
            'valid_until': until, 'decision': {'action': 'SHORT' if not is_spot else 'COMPRA_SPOT', 'confidence': 83},
            'publication_status': 'EXECUTABLE_SIGNAL',
            'source_candle_closed': True, 'publication_eligible': True,
            'levels': {'entry': 111.135 if not is_spot else 82000,
                       'stop_loss': 113.552 if not is_spot else 81500,
                       'take_profit': 105.604 if not is_spot else 83500,
                       'leverage': 24 if not is_spot else 1,
                       'publication_status': 'EXECUTABLE_SIGNAL'}
        }
    }


def test_one_individual_snapshot_survives_aggregate_oom(monkeypatch):
    from types import ModuleType
    db_rows = {}
    fake = ModuleType('runtime_persistence')
    def save(namespace, key, payload, **kw):
        db_rows[(namespace,key)] = payload
        return True
    def load(namespace, key, **kw):
        if (namespace,key) not in db_rows: return None
        return {'payload': db_rows[(namespace,key)]}
    fake.save_runtime_snapshot = save
    fake.load_runtime_snapshot = load
    monkeypatch.setitem(sys.modules, 'runtime_persistence', fake)
    evt = _event('1fc0f37196da79089a6a2d23')
    assert store.persist_official(evt)
    # In-process and aggregate snapshot can be wiped; exact per-ID still exists.
    got = store.get_official('1fc0f37196da79089a6a2d23')
    assert got['signal']['symbol'] == 'SOL-USDT'
    assert got['signal']['levels']['stop_loss'] == 113.552
    assert store.get_official('missing') is None


def test_failed_remote_save_blocks_confirmed_dispatch(monkeypatch):
    fake = ModuleType('runtime_persistence')
    fake.save_runtime_snapshot = lambda *a, **k: False
    monkeypatch.setitem(sys.modules, 'runtime_persistence', fake)
    assert store.persist_official(_event('fb48ae6c11e89a5c6f1a6faf')) is False


def _load_real_def(name, extra):
    tree = ast.parse((BASE/'app.py').read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    scope = dict(extra)
    exec(compile(ast.Module(body=[fn],type_ignores=[]), str(BASE/'app.py'), 'exec'), scope)
    return scope[name]


def test_all_four_telegram_examples_are_web_visible(monkeypatch):
    # Simulate 4 alerts already safely in Supabase and no in-process outbox:
    # a real deployment OOM can recreate exactly this situation.
    examples=[
      _event('1fc0f37196da79089a6a2d23',tf='2h'),
      _event('fb48ae6c11e89a5c6f1a6faf',tf='2h'),
      _event('5aae16955aa75933a2cf531d',tf='30m'),
      _event('250f0204cdd88ed908673c20',tf='1h'),
    ]
    monkeypatch.setattr(store, 'recent_official_events', lambda: examples)
    import pandas as pd
    scope = {
      '_confirmed_signal_outbox_lock': Lock(), '_confirmed_signal_outbox': {},
      '_confirmed_signal_alerts_lock': Lock(), '_confirmed_signal_alerts_sent': {},
      '_confirmed_signal_tf_seconds': tf_seconds,
      '_confirmed_signal_close_timestamp': signal_close_utc,
      '_parse_utc_iso': parse_utc, 'pd': pd, 'datetime': datetime,
      'timedelta': timedelta,'timezone': timezone, '_futures_analysis_cache': {'data': {}},
    }
    registry = _load_real_def('_confirmed_web_registry_rows_34_4', scope)
    now = datetime(2026,10,11,4,15,tzinfo=timezone.utc)
    current = registry('futures','previous',55,now)
    assert len(current)==4, [(r['signal_id'],r['symbol']) for r in current]
    assert {r['signal_id'] for r in current} == {e['signal']['signal_id'] for e in examples}
    assert all(r['source_context']=='PREVIOUS_CONFIRMED' for r in current)
    # Confirmed runs one TF, Vigentes depend on ORIGINAL technical until.
    later = registry('futures','active',55,datetime(2026,10,11,6,15,tzinfo=timezone.utc))
    assert len(later)==4
    assert all(r['source_context']=='ACTIVE_CONFIRMED' for r in later)
    expired = registry('futures','active',55,datetime(2026,10,11,11,tzinfo=timezone.utc))
    assert not expired


def test_spot_index_does_not_require_live_heavy_analysis(monkeypatch):
    evt = _event('spot-daily-1',market='spot',tf='1D',close='2026-10-11T00:00:00+00:00',
                 until='2026-10-13T00:00:00+00:00')
    monkeypatch.setattr(store,'recent_official_events', lambda:[evt])
    import pandas as pd
    scope={'_confirmed_signal_outbox_lock':Lock(),'_confirmed_signal_outbox':{},
           '_parse_utc_iso':parse_utc,'_confirmed_signal_close_timestamp':signal_close_utc,
           '_confirmed_signal_tf_seconds':tf_seconds,'datetime':datetime,'timezone':timezone,'timedelta':timedelta}
    cards=_load_real_def('_c37_spot_official_cards',scope)
    cur=cards('confirmed',datetime(2026,10,11,1,tzinfo=timezone.utc))
    assert len(cur)==1 and next(iter(cur.values()))['decision']=='COMPRA_SPOT'
    later=cards('vigent',datetime(2026,10,12,1,tzinfo=timezone.utc))
    assert len(later)==1
    expired=cards('vigent',datetime(2026,10,14,1,tzinfo=timezone.utc))
    assert not expired


def test_telegram_is_only_for_confirmed_not_for_vigent():
    text=(BASE/'app.py').read_text()
    # No new telegram invocation was added to ACTIVE or PREVIOUS routes.
    for name in ('api_futures_signals_active','api_multiasset_signals_active',
                 'api_spot_signals_vigent'):
        tree=ast.parse(text)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        frag=ast.get_source_segment(text,fn)
        assert '_send_confirmed_signal_telegram' not in frag
    assert (BASE/'templates/official_signal.html').exists()
    assert 'POST' in (BASE/'templates/official_signal.html').read_text()


def test_repo_and_runtime_contracts():
    required=['app.py','runtime_persistence.py','official_signal_store.py',
      'static/script.js','static/futures.js','templates/index.html',
      'templates/official_signal.html','render.yaml','Procfile','build.sh','requirements.txt']
    assert all((BASE/n).exists() for n in required)
    cfg=(BASE/'render.yaml').read_text()
    assert 'gunicorn app:app' in cfg
    assert 'LOW_MEMORY_MODE' in cfg
