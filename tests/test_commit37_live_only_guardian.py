"""C37 LIVE-only/adaptive UI/Guardian regression; no network or secrets.

These are isolated contracts and are NOT an end-to-end Render load test.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import threading

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'app.py').read_text(encoding='utf8')
TREE = ast.parse(SRC)


def isolate(name, env):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = dict(env)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(ROOT/'app.py'), 'exec'), namespace)
    return namespace[name]


def segment(name):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SRC, node)


def test_background_learning_disabled_without_disabling_live():
    startup=segment('_start_background_threads')
    assert 'if _LIVE_ONLY_RUNTIME:' in startup
    assert 'threading.Thread(target=learning_worker_loop' in startup
    assert 'monitor_entries_loop' in startup
    assert 'saved_futures_lifecycle_loop' in startup
    assert 'monitor_guardian_telegram_loop' in startup
    assert 'futures_standard_alert_loop' in startup
    assert '_ensure_ai_learning_scientist_thread()' in startup


def test_scientist_does_not_start_even_if_dashboard_override():
    states = []
    fn = isolate('_ensure_ai_learning_scientist_thread', {
        'globals': lambda: {'_LIVE_ONLY_RUNTIME': True},
        '_ai_learning_runtime_update':lambda **kwargs: states.append(kwargs),
        '_AI_SCIENTIST_THREAD_STARTED':False,
    })
    assert fn() is False
    assert states[0]['status'] == 'DISABLED_LIVE_ONLY_C37'


def test_q6_daily_disabled_but_closed_candle_scheduler_preserved():
    fn = isolate('_q6_run_daily_review', {'globals':lambda:{'_LIVE_ONLY_RUNTIME': True}})
    assert fn() is None
    assert '_run_scheduled_spot_analysis' in segment('verificar_y_ejecutar')


def test_guardian_real_mark_price_ttl_reuses_network(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'code':'200000','data':{'value':'111.23'}}
    class Session:
        calls = 0
        def get(self,url, timeout=3):
            assert url.endswith('SOLUSDTM') and timeout <= 3
            self.calls += 1
            return Response()
    sess=Session()
    fake_fs=SimpleNamespace(FUTURES_CONTRACT_SYMBOLS={'SOL-USDT':'SOLUSDTM'},
                            KUCOIN_FUTURES_MARK_PRICE_URL='https://example.org/{symbol}',
                            _get_futures_http_session=lambda:sess)
    namespace={
        '_GUARDIAN_MARK_PRICE_CACHE':{},
        '_GUARDIAN_MARK_PRICE_LOCK':threading.Lock(),
        '_GUARDIAN_MARK_PRICE_TTL_SECONDS':25,
        '_configured_futures_module': lambda:fake_fs,
        'time': SimpleNamespace(monotonic=lambda:1000.0),
        'math':__import__('math')
    }
    fn=isolate('_guardian_recent_mark_price',namespace)
    assert fn('SOL-USDT')==111.23
    assert fn('SOL-USDT')==111.23
    assert sess.calls==1
    assert len(namespace['_GUARDIAN_MARK_PRICE_CACHE'])==1


def test_guardian_cached_structure_uses_live_price_not_ohlcv():
    now=400.0
    key=('SOL-USDT','2h')
    cache={key:{'_cached_at':300.0,'current_price':108.0,'candles':{'close':[110,109]}}}
    class Forbidden:
        def _prepare_closed_candle_analysis_data(self,*args):
            raise AssertionError('guardian allocated OHLCV despite fresh structure cache')
    fn=isolate('_guardian_prepare_futures_market_data', {
        '_GUARDIAN_MARKET_CACHE_LOCK':threading.Lock(),
        '_GUARDIAN_MARKET_CACHE':cache,
        '_GUARDIAN_MARKET_CACHE_TTL_SECONDS':240,
        'time':SimpleNamespace(monotonic=lambda:now),
        '_guardian_with_recent_price':lambda sym,snapshot:{**snapshot,'current_price':109.25,'price_is_live':True},
    })
    result=fn(Forbidden(),*key)
    assert result['current_price']==109.25
    assert result['candles']['close']==[110,109]
    assert result['price_is_live']


def test_guardian_adaptive_urgency_no_new_confirmation():
    s=segment('monitor_guardian_telegram_loop')
    assert 'urgent_guardian = False' in s
    assert 'risk * 0.35' in s
    assert '15 if urgent_guardian' in s
    assert "'entry_touched'" in s
    assert '_send_confirmed_signal_telegram(' not in s


def test_ui_temporal_cache_longer_without_modifying_official_signals():
    s=segment('_get_futures_ui_cached')
    assert '_FUTURES_INTRABAR_REFRESH_SECONDS.get(item_tf, 300)' in s
    assert '_send_confirmed_signal_telegram' not in s
    assert '_confirmed_outbox_enqueue' not in s
    spot_cache = (ROOT/'static/script.js').read_text(encoding='utf8')
    assert 'if (document.hidden) {' in spot_cache
    assert 'watchTechnicalRecommendationReady35' in spot_cache


def test_no_symbols_or_levels_removed():
    assert 'LIVE_ONLY_RUNTIME' in (ROOT/'render.yaml').read_text()
    assert "'30m': 3 * 60" in SRC
    for name in ('_core_publication_authority','_send_confirmed_signal_telegram',
                 '_merge_official_telegram_rows_34_4','_attempt_confirmed_outbox_event_inner'):
        assert len([n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name==name]) == 1
    assert (ROOT/'official_signal_store.py').exists()
    assert (ROOT/'templates/official_signal.html').exists()
