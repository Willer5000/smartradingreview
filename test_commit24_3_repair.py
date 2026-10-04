import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('commit24_repair_runtime', ROOT / 'commit24_repair_runtime.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_result(**overrides):
    result = {
        'success': True, 'symbol': 'BTC-USDT', 'timeframe': '1h', 'is_multiasset': False,
        'decision': {'action': 'LONG', 'confidence': 68},
        'levels': {
            'entry': 100.0, 'stop_loss': 98.0, 'take_profit': 104.0, 'risk_reward': 2.0,
            'leverage': 5, 'risk_allocation_fraction': 0.50, 'execution_safety': 80.0,
            'futures_filter_stage': 'PUBLICATION_GATE',
            'futures_publication_gate': {'stage': 'PUBLICATION_GATE', 'reason_codes': [], 'reasons': []},
            'risk_control': {'estimated_sl_loss_pct_margin': 5.0, 'estimated_atr_stress_loss_pct_margin': 10.0},
            'entry_score': 80.0, 'entry_reachability': 80.0, 'tp_quality_score': 85.0,
            'sl_reliability': 0.85,
        },
        'trend': {'direction': 'bullish', 'adx': 30}, 'momentum': {'direction': 'bullish'},
        'volatility': {'atr_pct': 2.0, 'state': 'NORMAL'}, 'structure': {'direction': 'bullish'},
        'market_data_is_synthetic': False,
    }
    result.update(overrides)
    return result


class FakeFutures:
    def _calculate_execution_safety(self, levels, trend, momentum, structure, timeframe):
        return {'score': float(levels.get('execution_safety', 80.0)), 'label': 'ALTA', 'components': {}}


class FakeApp:
    def _get_futures_system(self):
        return FakeFutures()

    def _ensure_manual_diagnostic_geometry_175114(self, result, action, symbol, timeframe):
        return result['levels']


def install_fake_q(score=84.0, passed=True, blockers=(), filter_scores=None, quality=None, stage='PUBLICATION_GATE'):
    if filter_scores is None:
        filter_scores = {'Q1': 61, 'Q2': 63, 'Q3': 64, 'Q4': 66, 'Q5': 65, 'Q6': 70, 'Q7': score, 'Q8': 60, 'Q9': 62, 'Q10': 55}
    if quality is None:
        quality = {'Q1': 60, 'Q2': 65, 'Q3': 74, 'Q4': 65, 'Q5': 62, 'Q6': 74, 'Q7': 84, 'Q8': 60, 'Q9': 62}
    class Q:
        @staticmethod
        def evaluate(**kwargs):
            rows = []
            for i in range(1, 11):
                name = f'Q{i}'
                value = float(filter_scores.get(name, 0))
                rows.append({'filter': name, 'name': name, 'score': value, 'passed': bool(passed and value >= 75), 'evidence': True})
            passed_names = [r['filter'] for r in rows if r['passed']]
            selected = max(rows, key=lambda r: r['score'])
            return {
                'quality': dict(quality),
                'parallel_quality_filters': {
                    'filters': rows,
                    'filter_scores': dict(filter_scores),
                    'selected_filter': selected['filter'],
                    'selected_filter_name': selected['name'],
                    'selected_filter_score': selected['score'],
                    'selected_filter_passed': bool(selected['passed']),
                    'passed_filters': passed_names,
                    'summary': ' · '.join(f"Q{i} {float(filter_scores.get(f'Q{i}',0)):.0f}" for i in range(1,11)),
                    'legacy_publication_blockers': list(blockers),
                    'universal_guards': {'passed': stage == 'PUBLICATION_GATE', 'codes': []},
                },
            }
    sys.modules['quality_9q_engine_21'] = Q


def test_direct_q_promotes():
    install_fake_q()
    out, auth = mod._normalize_quality_candidate(FakeApp(), make_result(), 'BTC-USDT', '1h')
    assert auth['confirmed'] is True
    assert auth['authority'] == 'Q7'
    assert auth['confirmation_mode'] == 'ONE_OF_TEN_QUALITY_FILTERS'


def test_below_75_rejects_when_cluster_not_eligible():
    scores = {'Q1': 61, 'Q2': 63, 'Q3': 64, 'Q4': 66, 'Q5': 65, 'Q6': 69, 'Q7': 69, 'Q8': 60, 'Q9': 62, 'Q10': 55}
    quality = {k: min(v, 74) for k, v in scores.items() if k != 'Q10'}
    install_fake_q(filter_scores=scores, passed=False, quality=quality)
    out, auth = mod._normalize_quality_candidate(FakeApp(), make_result(), 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert 'NO_Q_GE75' in auth['universal_guard_codes']


def test_cluster_promotes_with_valid_geometry():
    scores = {'Q1': 70, 'Q2': 71, 'Q3': 72, 'Q4': 73, 'Q5': 70, 'Q6': 73, 'Q7': 74, 'Q8': 68, 'Q9': 71, 'Q10': 55}
    quality = {'Q1': 70, 'Q2': 71, 'Q3': 76, 'Q4': 73, 'Q5': 70, 'Q6': 74, 'Q7': 79, 'Q8': 68, 'Q9': 70}
    install_fake_q(filter_scores=scores, passed=False, quality=quality)
    out, auth = mod._normalize_quality_candidate(FakeApp(), make_result(), 'BTC-USDT', '1h')
    assert auth['q_cluster']['eligible'] is True
    assert auth['q_cluster']['winner'] == 'Q7'
    assert auth['confirmed'] is True
    assert auth['confirmation_mode'] == 'Q_CLUSTER_GEOMETRIC_REVIEW'


def test_cluster_rejects_when_std_below_5():
    scores = {f'Q{i}': 71.0 + (i % 2) * 0.2 for i in range(1,11)}
    quality = {f'Q{i}': 80.0 if i in (3,7) else 71.0 for i in range(1,10)}
    install_fake_q(filter_scores=scores, passed=False, quality=quality)
    _, auth = mod._normalize_quality_candidate(FakeApp(), make_result(), 'BTC-USDT', '1h')
    assert auth['q_cluster']['eligible'] is False


def test_pre_gate_fails_closed():
    install_fake_q(stage='CANDIDATE')
    r = make_result(); r['levels']['futures_filter_stage'] = 'CANDIDATE'; r['levels']['futures_publication_gate']['stage'] = 'CANDIDATE'
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False and 'PRE_GATE_REJECTION' in auth['universal_guard_codes']


def test_safety_floor_fails_closed():
    install_fake_q()
    r = make_result(); r['levels']['execution_safety'] = 64.9
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False and 'OPERATIONAL_SAFETY_BELOW_65' in auth['universal_guard_codes']


def test_sl_loss_fails_closed():
    install_fake_q()
    r = make_result(); r['levels']['risk_allocation_fraction'] = 1.0
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False and 'LOSS_AT_SL' in auth['universal_guard_codes']


def test_atr_stress_fails_closed():
    install_fake_q()
    r = make_result(); r['levels']['risk_control']['estimated_atr_stress_loss_pct_margin'] = 25.1
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False and 'ATR_STRESS' in auth['universal_guard_codes']


def test_non_q10_blocker_fails_closed():
    install_fake_q(blockers=('LOSS_AT_SL',), score=84)
    r = make_result(); r['levels']['futures_publication_gate']['reason_codes'] = ['LOSS_AT_SL']
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False and 'NON_Q10_LEGACY_BLOCKER' in auth['universal_guard_codes']


def test_stage_missing_fails_closed():
    install_fake_q()
    r = make_result(); r['levels'].pop('futures_filter_stage', None); r['levels']['futures_publication_gate'].pop('stage', None)
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False


def test_synthetic_data_fails_closed():
    install_fake_q()
    r = make_result(); r['market_data_is_synthetic'] = True
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False and 'SYNTHETIC_MARKET_DATA' in auth['universal_guard_codes']


def test_invalid_geometry_fails_closed():
    install_fake_q()
    r = make_result(); r['levels']['take_profit'] = 97
    _, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False


def test_dedupe_preserves_different_timeframes():
    rows = [
        {'symbol':'ETH-USDT','timeframe':'1h','direction':'LONG','quality_filter_score':81},
        {'symbol':'ETH-USDT','timeframe':'4h','direction':'LONG','quality_filter_score':79},
    ]
    out = mod._dedupe_candidates(rows)
    assert len(out) == 2


def test_dedupe_preserves_different_directions():
    rows = [
        {'symbol':'ETH-USDT','timeframe':'1h','direction':'LONG','quality_filter_score':81},
        {'symbol':'ETH-USDT','timeframe':'1h','direction':'SHORT','quality_filter_score':80},
    ]
    out = mod._dedupe_candidates(rows)
    assert len(out) == 2


def test_dedupe_preserves_spot_and_futures():
    rows = [
        {'market':'futures','symbol':'BTC-USDT','timeframe':'1h','direction':'LONG','quality_filter_score':81},
        {'market':'spot','symbol':'BTC-USDT','timeframe':'1h','direction':'LONG','quality_filter_score':80},
    ]
    assert len(mod._dedupe_candidates(rows)) == 2


def test_dedupe_keeps_highest_score_same_key():
    rows = [
        {'market':'futures','symbol':'BTC-USDT','timeframe':'1h','direction':'LONG','quality_filter_score':81},
        {'market':'futures','symbol':'BTC-USDT','timeframe':'1h','direction':'LONG','quality_filter_score':79},
    ]
    out = mod._dedupe_candidates(rows)
    assert len(out) == 1 and out[0]['quality_filter_score'] == 81


def test_health_module_exists_and_contract_constants():
    import commit24_3_health
    assert callable(commit24_3_health.install)
    assert mod.Q_MIN_SCORE == 75.0
    assert mod.STALL_EXIT_SECONDS == max(60.0, mod.STALL_EXIT_SECONDS)


def test_app_queue_has_no_waiting_thread_contract():
    # Static contract: the queue function is present and no Timer-based waiter remains in 24.3 runtime.
    app_text = (ROOT / 'app.py').read_text(encoding='utf-8')
    runtime_text = (ROOT / 'commit24_repair_runtime.py').read_text(encoding='utf-8')
    assert 'def _enqueue_ui_analysis' in app_text
    assert 'def _drain_ui_analysis_queue' in app_text
    assert 'threading.Timer' not in runtime_text


def test_cluster_not_enabled_is_nonpromoting():
    old = mod.Q_CLUSTER_ENABLED
    mod.Q_CLUSTER_ENABLED = False
    scores = {'Q1': 70, 'Q2': 71, 'Q3': 72, 'Q4': 73, 'Q5': 70, 'Q6': 73, 'Q7': 74, 'Q8': 68, 'Q9': 71, 'Q10': 55}
    evaluated = {'quality': {'Q3': 80, 'Q6': 80, 'Q7': 80, 'Q9': 80}}
    cluster = mod._evaluate_q_cluster({'filter_scores': scores}, evaluated)
    assert cluster['eligible'] is False
    mod.Q_CLUSTER_ENABLED = old


def _load_app_queue_functions():
    import ast, os, threading, time
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    wanted = {
        '_pending_ui_analysis_key', '_get_pending_ui_analysis_snapshot',
        '_enqueue_ui_analysis', '_pop_pending_ui_analysis',
        '_drain_ui_analysis_queue',
    }
    namespace = {
        'os': os, 'threading': threading, 'time': time,
        '_UI_PENDING_MAX': 5,
        '_PENDING_UI_ANALYSIS_QUEUE': [],
        '_PENDING_UI_ANALYSIS_LOCK': threading.RLock(),
        '_FUTURES_UI_CACHE': {'running': set(), 'errors': {}, 'lock': threading.RLock()},
        '_futures_ui_key': lambda symbol, timeframe: f'{symbol}|{timeframe}',
    }
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / 'app.py'), 'exec'), namespace)
    return namespace


def test_ui_queue_respects_limit_and_drops_oldest():
    ns = _load_app_queue_functions()
    for i in range(5):
        ns['_enqueue_ui_analysis'](f'SYM{i}-USDT', '1h', 'futures')
    result = ns['_enqueue_ui_analysis']('SYM5-USDT', '1h', 'futures')
    snapshot = ns['_get_pending_ui_analysis_snapshot']()
    assert len(snapshot) == 5
    assert result['dropped_oldest'] is True
    assert snapshot[0]['symbol'] == 'SYM1-USDT'
    assert snapshot[-1]['symbol'] == 'SYM5-USDT'


def test_ui_queue_enqueue_does_not_create_thread():
    ns = _load_app_queue_functions()
    original_thread = ns['threading'].Thread
    class ForbiddenThread:
        def __init__(self, *args, **kwargs):
            raise AssertionError('Queue path must not create a waiting thread')
    ns['threading'].Thread = ForbiddenThread
    try:
        ns['_enqueue_ui_analysis']('BTC-USDT', '1h', 'futures')
    finally:
        ns['threading'].Thread = original_thread
    assert len(ns['_get_pending_ui_analysis_snapshot']()) == 1


def test_ui_queue_drain_executes_pending_on_releasing_worker():
    ns = _load_app_queue_functions()
    ns['_run_futures_ui_analysis_sync'] = None
    calls = []
    def fake_run(symbol, timeframe, market, pre_acquired=False):
        calls.append((symbol, timeframe, market, pre_acquired))
        return 'COMPLETED'
    # Inject the dependency only for the exact drain function.
    import ast
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    drain_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_drain_ui_analysis_queue')
    ns['exec_run'] = fake_run
    # Rebind the global name expected by the function.
    exec(compile(ast.Module(body=[drain_node], type_ignores=[]), str(ROOT / 'app.py'), 'exec'), {**ns, '_run_futures_ui_analysis_sync': fake_run}, ns)
    ns['_FUTURES_UI_CACHE']['running'].clear()
    ns['_enqueue_ui_analysis']('BTC-USDT', '1h', 'futures')
    ns['_enqueue_ui_analysis']('ETH-USDT', '4h', 'multiasset')
    # The exact function is recompiled above, so it sees the same namespace globals.
    drained = ns['_drain_ui_analysis_queue'](max_items=2)
    assert drained == 2
    assert [c[:3] for c in calls] == [('BTC-USDT', '1h', 'futures'), ('ETH-USDT', '4h', 'multiasset')]
    assert not ns['_get_pending_ui_analysis_snapshot']()


def test_health_24_3_exposes_required_metrics():
    import types
    import sys
    flask_stub = types.ModuleType('flask')
    flask_stub.jsonify = lambda payload: payload
    flask_stub.Response = lambda body, mimetype=None: body
    previous_flask = sys.modules.get('flask')
    sys.modules['flask'] = flask_stub
    sys.modules['orjson'] = types.SimpleNamespace(dumps=lambda payload: payload)
    try:
        import commit24_3_health
        class FakeApp:
            def __init__(self):
                self.routes = {}
            def get(self, path):
                def decorator(fn):
                    self.routes[path] = fn
                    return fn
                return decorator
        fake = type('FakeModule', (), {})()
        fake.app = FakeApp()
        fake._get_pending_ui_analysis_snapshot = lambda: [{'symbol':'BTC-USDT','timeframe':'1h','market':'futures','age_seconds':1,'blocked_by':'x'}]
        runtime_ns = {
            'VERSION': 'COMMIT24.3_TEST', 'Q_MIN_SCORE': 75.0,
            'Q_CLUSTER_ENABLED': True, 'Q_CLUSTER_MIN_AVG': 72.0,
            'UI_PENDING_MAX': 5, 'STALL_EXIT_SECONDS': 105.0,
            '_HOLDER_OWNER': 'futures-ui:BTC-USDT:1h', '_HOLDER_STARTED_AT': 0.0,
            '_INSTALL_RESULT': {
                'classifier': {'installed': True}, 'lifecycle': {'installed': True},
                'hidden_candidates': {'installed': True}, 'multiasset_diagnostics': {'installed': True},
                'heavy_acquire': {'installed': True}, 'heavy_release': {'installed': True},
                'ui_start': {'installed': True},
            },
            'audit': lambda: {'metrics': {'q_cluster_promotions': 2}},
            '_maybe_stall_exit': lambda app_module: None,
        }
        result = commit24_3_health.install(fake, runtime_ns)
        assert result['installed'] is True
        body = fake.app.routes['/api/commit24/health']()
        required = {
            'version','q_min_score','q_cluster_enabled','q_cluster_min_avg','q10_is_mandatory',
            'heavy_holder','heavy_holder_age_seconds','pending_interactive_ui','pending_ui_queue_size',
            'stall_exit_seconds','dedupe_key_mode','hooks','rss_mb_estimate','metrics',
        }
        assert required.issubset(body.keys())
        assert body['hooks']['ui_drain'] is True
        assert body['q_cluster_promotions'] == 2
    finally:
        if previous_flask is None:
            sys.modules.pop('flask', None)
        else:
            sys.modules['flask'] = previous_flask
        sys.modules.pop('orjson', None)


if __name__ == '__main__':
    funcs = [name for name in globals() if name.startswith('test_')]
    for name in sorted(funcs):
        globals()[name]()
        print('PASS', name)
    print('ALL PASS', len(funcs))
