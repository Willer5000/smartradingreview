"""34.6: isolated core memory-guard regression tests.

We AST-load only pure pressure functions from the complete app.py, so these
checks run without importing Flask, network services, Supabase or daemon jobs.
"""
from pathlib import Path
import ast
import os
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'app.py').read_text(encoding='utf-8')
FUNCS = {
    '_commit346_cgroup_budget',
    '_commit346_stage_reserve',
    '_commit34_guard_stage',
}

def load_core():
    tree = ast.parse(SRC, filename='app.py')
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in FUNCS]
    assert {n.name for n in nodes} == FUNCS
    dct = {'os': os}
    code = compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec')
    exec(code, dct)
    return dct


class ResourceGuard34_6(unittest.TestCase):
    def setUp(self):
        self.ns = load_core()
        self.used = 415.23046875
        self.rss = 164.5
        self.inactive = 0.0
        self.shed = MagicMock()
        self.ns.update({
            '_commit34_cgroup_mb': lambda: (self.used, 512.0),
            '_commit346_inactive_file_mb': lambda: self.inactive,
            '_process_rss_mb': lambda: self.rss,
            '_shed_recreatable_memory': self.shed,
        })

    def test_reported_live_error_is_not_a_true_mid_job_abort(self):
        # The screenshot shows 415.23 MiB cgroup, 164.5 MiB own RSS.
        self.assertTrue(self.ns['_commit34_guard_stage']('specialists:BTC-USDT:1h'))
        self.assertEqual(self.shed.call_count, 0)

    def test_heap_risk_still_aborts(self):
        self.rss = 375.0
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE_PRESSURE_ABORT'):
            self.ns['_commit34_guard_stage']('specialists:BTC-USDT:1h')
        self.assertEqual(self.shed.call_count, 1)

    def test_nonreclaimable_cgroup_cliff_still_aborts(self):
        self.used = 475.0
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE_PRESSURE_ABORT'):
            self.ns['_commit34_guard_stage']('specialists:BTC-USDT:1h')

    def test_raw_floor_rejects_even_when_inactive_file_is_huge(self):
        self.used = 480.0
        self.inactive = 300.0
        self.assertFalse(self.ns['_commit346_cgroup_budget'](88.0)['safe'])

    def test_reclaimable_cache_is_discounted_and_capped(self):
        self.used = 415.0
        self.inactive = 500.0
        budget = self.ns['_commit346_cgroup_budget'](128.0)
        self.assertEqual(budget['credit_mb'], 120.0)
        self.assertTrue(budget['safe'])

    def test_no_credit_for_unavailable_memory_stat(self):
        self.used = 415.0
        self.inactive = 0.0
        self.assertFalse(self.ns['_commit346_cgroup_budget'](128.0)['safe'])

    def test_long_timeframe_needs_larger_reserve(self):
        self.assertEqual(self.ns['_commit346_stage_reserve']('specialists:BTC-USDT:1D'), 128)
        self.assertEqual(self.ns['_commit346_stage_reserve']('specialists:BTC-USDT:1h'), 88)
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE_PRESSURE_ABORT'):
            self.ns['_commit34_guard_stage']('specialists:BTC-USDT:1D')

    def test_research_failure_remains_optional(self):
        self.used = 475.0
        self.assertFalse(self.ns['_commit34_guard_stage']('family-analysis:BTC-USDT:1h', optional=True))

    def test_no_cgroup_metrics_gracefully_uses_rss_guard(self):
        self.ns['_commit34_cgroup_mb'] = lambda: (None, None)
        self.assertTrue(self.ns['_commit34_guard_stage']('specialists:BTC-USDT:1h'))
        self.rss = 400.0
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE_PRESSURE_ABORT'):
            self.ns['_commit34_guard_stage']('specialists:BTC-USDT:1h')

    def test_does_not_promote_failed_analysis_to_ui(self):
        self.assertIn("result.get('success') is False", SRC)
        self.assertIn("_FUTURES_UI_CACHE['items'].pop(key, None)", SRC)
        self.assertIn("'RESOURCE_BACKOFF' if _pressure else 'BACKOFF'", SRC)

    def test_heavy_lock_still_serializes_jobs(self):
        self.assertIn('_HEAVY_ANALYSIS_LOCK.acquire(timeout=timeout)', SRC)
        self.assertIn('_commit346_cgroup_budget(_reserved_mb)', SRC)
        self.assertIn("'rss_mb': _process_rss_mb()", SRC)


if __name__ == '__main__':
    unittest.main()
