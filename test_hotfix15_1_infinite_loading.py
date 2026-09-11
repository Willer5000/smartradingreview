import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Hotfix151InfiniteLoadingTests(unittest.TestCase):
    def test_futures_web_endpoint_no_longer_runs_heavy_analysis_inline(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = source.index("@app.route('/api/futures/analyze', methods=['POST'])")
        end = source.index("@app.route('/api/futures/analyze_all/<timeframe>')", start)
        block = source[start:end]
        self.assertIn('_get_futures_ui_cached', block)
        self.assertIn('_start_futures_ui_analysis_async', block)
        self.assertIn("'retry_after_ms': 1800", block)
        self.assertNotIn('_acquire_heavy_analysis(', block)
        self.assertNotIn('analyze_futures_market(', block)

    def test_async_ui_job_uses_existing_single_heavy_slot(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = source.index('def _start_futures_ui_analysis_async')
        end = source.index('def _serialize_futures_cache', start)
        block = source[start:end]
        self.assertIn("_acquire_heavy_analysis(owner, timeout=35)", block)
        self.assertIn('futures.analyze_futures_market(symbol, timeframe)', block)
        self.assertIn('_store_futures_ui_cached(symbol, timeframe, ui_result)', block)
        self.assertIn('_compact_futures_runtime_result(result)', block)

    def test_incremental_research_yields_to_interactive_charts(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('if _futures_interactive_priority_active():', source)
        self.assertIn('Human chart requests have priority', source)
        self.assertIn('UI priority prevents the 15-second round-robin', source)

    def test_frontend_polling_has_hard_ceiling(self):
        source = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        self.assertIn('elapsedMs < 45000 && retryCount < 18', source)
        self.assertIn('error?.serverData?.retry_after_ms', source)
        self.assertIn('__FUTURES_ANALYSIS_RETRY_STARTED_AT__', source)
        self.assertIn('Reintentar análisis', source)
        self.assertNotIn('máximo cuatro veces', source)

    def test_memory_safe_single_worker_with_small_web_concurrency_is_preserved(self):
        proc = (ROOT / 'Procfile').read_text(encoding='utf-8')
        self.assertIn('--workers 1 --threads 2', proc)
        env = (ROOT / '.env.example').read_text(encoding='utf-8')
        self.assertIn('FUTURES_INTERACTIVE_PRIORITY_SECONDS=45', env)
        self.assertIn('FUTURES_UI_CACHE_TTL_SECONDS=90', env)

    def test_script_cache_bust_is_bumped(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('20260911-H15-2-UI-PRIORITY', html)


if __name__ == '__main__':
    unittest.main()
