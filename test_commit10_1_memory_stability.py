import ast
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class _FakeTradingExpertSystem:
    def __init__(self):
        self.bolivia_tz = None

    def analyze_full_market(self, *args, **kwargs):
        return {'success': False}


class Commit101MemoryStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_app = types.ModuleType('app')
        fake_app.TradingExpertSystem = _FakeTradingExpertSystem
        fake_app.KUCOIN_INTERVALS = {}
        fake_app.SYMBOLS = {}
        cls.previous_app = sys.modules.get('app')
        sys.modules['app'] = fake_app
        sys.modules.pop('futures_system', None)
        cls.futures_system = importlib.import_module('futures_system')

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop('futures_system', None)
        if cls.previous_app is None:
            sys.modules.pop('app', None)
        else:
            sys.modules['app'] = cls.previous_app

    def tearDown(self):
        self.futures_system.clear_futures_runtime_caches(include_microstructure=True)

    def test_app_contains_soft_and_hard_rss_guard(self):
        source = Path('app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn('_memory_pressure_guard', names)
        self.assertIn('_shed_recreatable_memory', names)
        self.assertIn('_trim_process_heap', names)
        self.assertIn('MEMORY_HARD_LIMIT_MB', source)
        self.assertIn("data.get('memory_guard_abort')", source)

    def test_futures_raw_cache_has_a_hard_entry_bound(self):
        fs = self.futures_system
        frame = pd.DataFrame({
            'time': pd.date_range('2026-09-10', periods=3, freq='5min'),
            'open': [1.0, 1.0, 1.0], 'high': [2.0, 2.0, 2.0],
            'low': [0.5, 0.5, 0.5], 'close': [1.5, 1.5, 1.5],
            'volume': [10.0, 10.0, 10.0], 'turnover': [15.0, 15.0, 15.0],
        })
        original_limit = fs.FUTURES_DATA_CACHE_MAX_ENTRIES
        try:
            fs.FUTURES_DATA_CACHE_MAX_ENTRIES = 4
            for i in range(10):
                fs._store_futures_data(f'SYM{i}', '5m', frame)
            self.assertLessEqual(len(fs._futures_data_cache), 4)
        finally:
            fs.FUTURES_DATA_CACHE_MAX_ENTRIES = original_limit

    def test_clear_futures_runtime_caches_does_not_touch_analysis_lifecycle(self):
        fs = self.futures_system
        frame = pd.DataFrame({'x': [1, 2]})
        fs._store_futures_data('BTC-USDT', '5m', frame)
        fs._store_futures_microstructure('BTC-USDT', {'available': True})
        stats = fs.clear_futures_runtime_caches(include_microstructure=True)
        self.assertEqual(stats['raw_ohlcv'], 1)
        self.assertEqual(stats['microstructure'], 1)
        self.assertEqual(len(fs._futures_data_cache), 0)
        self.assertEqual(len(fs._futures_microstructure_cache), 0)

    def test_prepared_closed_candle_context_is_reused(self):
        fs = self.futures_system
        obj = fs.FuturesAnalysis.__new__(fs.FuturesAnalysis)
        obj._futures_data_errors = {}
        obj._skip_supabase_register = False
        prepared = {
            'success': True,
            'closed_df': pd.DataFrame({'close': [1.0, 1.1]}),
            'source_candle_timestamp': '2026-09-10T08:00:00+00:00',
            'source_candle_close_timestamp': '2026-09-10T08:05:00+00:00',
            'live_price': 1.1,
            'live_candle_timestamp': '2026-09-10T08:05:00+00:00',
            'open_candle_present': True,
            'market_data_source': fs.KUCOIN_FUTURES_DATA_SOURCE,
            'market_data_fetched_at': '2026-09-10T08:05:01+00:00',
            'market_data_candles': 200,
        }
        with patch.object(obj, '_prepare_closed_candle_analysis_data', side_effect=AssertionError('duplicate prepare')), \
             patch.object(obj, 'analyze_full_market', return_value={'success': False, 'error': 'stop after parent'}):
            result = obj.analyze_futures_market(
                'BTC-USDT', '5m', closed_candle_only=True, prepared_context=prepared,
            )
        self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
