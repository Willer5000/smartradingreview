import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Hotfix152PriorityAndUiTests(unittest.TestCase):
    def test_heavy_background_jobs_yield_to_futures_ui(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = source.index('def _acquire_heavy_analysis')
        end = source.index('def _release_heavy_analysis', start)
        block = source[start:end]
        self.assertIn("if not owner.startswith('futures-ui:')", block)
        self.assertIn("globals().get('_futures_interactive_priority_active')", block)
        self.assertIn('cede turno a Futures interactivo', block)

    def test_learning_worker_uses_cooperative_microbatches(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = source.index('def learning_worker_loop')
        end = source.index('# COMMIT 36K', start)
        block = source[start:end]
        self.assertIn("LEARNING_MICROBATCH_ROWS", block)
        self.assertIn("max_rows=learning_batch_rows", block)
        self.assertIn("budget_seconds=learning_batch_budget", block)
        self.assertIn("should_yield=_futures_interactive_priority_active", block)
        self.assertIn("_release_heavy_analysis(owner)", block)

    def test_pending_evaluator_can_yield_before_next_signal(self):
        source = (ROOT / 'review_trader.py').read_text(encoding='utf-8')
        start = source.index('def evaluate_pending_signals')
        end = source.index('def _check_tp_sl_hit', start)
        block = source[start:end]
        self.assertIn('should_yield=None', block)
        self.assertIn("stats['yielded_for_ui'] = True", block)
        self.assertIn('signal = next(pending_iter)', block)
        self.assertIn('max_rows=max_rows', block)
        self.assertIn('budget_seconds=budget_seconds', block)

    def test_futures_http_request_has_watchdog_and_bounded_retry(self):
        source = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        self.assertIn('const analysisAbortController = new AbortController()', source)
        self.assertIn('window.IS_FUTURES_PAGE ? 12000 : 60000', source)
        self.assertIn("error?.name === 'AbortError'", source)
        self.assertIn('elapsedMs < 45000 && retryCount < 18', source)

    def test_order_flow_frontend_is_humanized(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        script = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        self.assertNotIn('En observación: todavía no modifica Entry ni Safety', html)
        self.assertNotIn('Esperando snapshot', html)
        self.assertNotIn('No es una señal autónoma', script)
        self.assertIn('Presión del libro', html)
        self.assertIn("marketReading = 'COMPRADORA'", script)
        self.assertIn("marketReading = 'VENDEDORA'", script)

    def test_one_worker_two_threads_only(self):
        proc = (ROOT / 'Procfile').read_text(encoding='utf-8')
        self.assertIn('--workers 1 --threads 2', proc)
        self.assertNotIn('--workers 2', proc)


if __name__ == '__main__':
    unittest.main()
