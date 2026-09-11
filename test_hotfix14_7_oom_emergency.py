import os
import unittest


class Hotfix147EmergencyOOMTests(unittest.TestCase):
    def test_render_uses_single_worker_and_bounded_web_threads(self):
        with open('Procfile', 'r', encoding='utf-8') as fh:
            proc = fh.read()
        with open('render.yaml', 'r', encoding='utf-8') as fh:
            render = fh.read()
        self.assertIn('--workers 1 --threads 2', proc)
        self.assertIn('--workers 1 --threads 2', render)

    def test_low_memory_defaults_have_large_headroom(self):
        with open('.env.example', 'r', encoding='utf-8') as fh:
            env = fh.read()
        self.assertIn('LOW_MEMORY_MODE=1', env)
        self.assertIn('MEMORY_SOFT_LIMIT_MB=250', env)
        self.assertIn('MEMORY_HARD_LIMIT_MB=340', env)
        self.assertIn('MEMORY_JOB_START_LIMIT_MB=240', env)
        self.assertIn('MEMORY_ANALYSIS_CACHE_KEEP=2', env)
        self.assertIn('FUTURES_DATA_CACHE_MAX_ENTRIES=2', env)

    def test_futures_boot_is_incremental_not_30_combo_sweep(self):
        with open('app.py', 'r', encoding='utf-8') as fh:
            source = fh.read()
        self.assertIn('Futures LOW_MEMORY_MODE', source)
        self.assertIn('_trigger_futures_combo_refresh_async', source)
        self.assertIn('combos_override=[(symbol, timeframe)]', source)
        self.assertIn('sin warm-up masivo al arranque', source)

    def test_runtime_futures_cache_drops_research_payloads(self):
        with open('app.py', 'r', encoding='utf-8') as fh:
            source = fh.read()
        start = source.index('def _compact_futures_runtime_result')
        block = source[start:start + 6500]
        self.assertIn('registro_votacion', block)
        self.assertNotIn("compact['structure']", block)
        self.assertNotIn("compact['strategy_lab']", block)
        self.assertNotIn("compact['execution_challenger_lab']", block)

    def test_old_rich_futures_snapshot_is_deleted_by_migration(self):
        with open('schema_hotfix14_7_oom.sql', 'r', encoding='utf-8') as fh:
            sql = fh.read()
        self.assertIn("namespace = 'futures'", sql)
        self.assertIn("snapshot_key = 'analysis_cache'", sql)
        self.assertNotIn('DELETE FROM signals', sql)
        self.assertNotIn('DELETE FROM signal_results', sql)

    def test_raw_futures_cache_can_be_reduced_below_four(self):
        with open('futures_system.py', 'r', encoding='utf-8') as fh:
            source = fh.read()
        self.assertIn("FUTURES_DATA_CACHE_MAX_ENTRIES = max(1", source)


if __name__ == '__main__':
    unittest.main()
