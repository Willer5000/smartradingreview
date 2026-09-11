import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_function(path: Path, function_name: str):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            module = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(module)
            namespace = {}
            exec(compile(module, str(path), 'exec'), namespace)
            return namespace[function_name]
    raise AssertionError(f'{function_name} not found in {path}')


class Hotfix149Tests(unittest.TestCase):
    def test_analytics_uses_compact_server_side_view(self):
        source = (ROOT / 'analytics_service.py').read_text(encoding='utf-8')
        self.assertIn("table('analytics_quality_v2_compact_v1')", source)
        self.assertIn("coverage['source'] = 'analytics_quality_v2_compact_v1'", source)

    def test_bad_empty_analytics_snapshot_is_not_usable(self):
        fn = load_function(ROOT / 'app.py', '_analytics_quality_snapshot_usable')
        self.assertFalse(fn({'coverage': {'complete': False, 'fetched_rows': 0, 'errors': ['APIError']}}))
        self.assertTrue(fn({'coverage': {'complete': True, 'fetched_rows': 0, 'errors': []}}))
        self.assertTrue(fn({'coverage': {'complete': False, 'fetched_rows': 241, 'errors': []}}))

    def test_futures_ui_payload_keeps_chart_data_but_drops_duplicate_df(self):
        fn = load_function(ROOT / 'app.py', '_compact_futures_ui_result')
        payload = {
            'success': True,
            'df': {'time': ['x'], 'close': [1.0]},
            'structure': {'df': {'time': ['x']}, 'supports': [0.9]},
            'momentum': {'indicators': {'rsi': 50}},
            'decision': {
                'action': 'LONG',
                'registro_votacion': {'accion_ganadora': 'LONG', 'todos_los_votos': [{'trader': 'A'}]},
            },
            'trader_intelligence_v2': {'large': True},
        }
        result = fn(payload)
        self.assertIn('df', result)
        self.assertIn('momentum', result)
        self.assertNotIn('df', result['structure'])
        self.assertNotIn('todos_los_votos', result['decision']['registro_votacion'])
        self.assertNotIn('trader_intelligence_v2', result)

    def test_futures_endpoint_returns_ui_payload_not_runtime_payload(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = source.index("@app.route('/api/futures/analyze', methods=['POST'])")
        end = source.index("@app.route('/api/futures/analyze_all/<timeframe>')", start)
        block = source[start:end]
        # Hotfix 15.1 moved the heavy chart calculation out of Gunicorn's only
        # request thread. The endpoint returns the short-lived rich UI cache.
        self.assertIn('_get_futures_ui_cached(symbol, timeframe)', block)
        self.assertIn("'data': cached_ui if cached_ui.get('success', True) else None", block)
        helper_start = source.index('def _start_futures_ui_analysis_async')
        helper_end = source.index('def _serialize_futures_cache', helper_start)
        helper = source[helper_start:helper_end]
        self.assertIn('ui_result = _compact_futures_ui_result(result)', helper)
        self.assertIn('runtime_result = _compact_futures_runtime_result(result)', helper)

    def test_futures_frontend_does_not_launch_spot_correlation_analysis(self):
        source = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        self.assertIn('if (window.IS_FUTURES_PAGE)', source)
        self.assertIn("window.showToast('✅ Análisis Futures completado', 'success')", source)
        self.assertIn('futures.js tiene su endpoint de', source)

    def test_frontend_retries_when_single_heavy_slot_is_busy(self):
        source = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        self.assertIn('window.__FUTURES_ANALYSIS_BUSY_RETRIES__', source)
        self.assertIn('error?.busy', source)
        self.assertIn('Preparando gráficos Futures.', source)

    def test_sql_only_invalidates_ephemeral_analytics_snapshots(self):
        sql = (ROOT / 'schema_hotfix14_9_restore_learning.sql').read_text(encoding='utf-8')
        self.assertIn('analytics_quality_v2_compact_v1', sql)
        self.assertIn("WHERE namespace = 'analytics'", sql)
        self.assertNotIn('DELETE FROM public.signals', sql)
        self.assertNotIn('DELETE FROM public.signal_results', sql)
        self.assertNotIn('DELETE FROM public.q6_job_runs', sql)


if __name__ == '__main__':
    unittest.main()
