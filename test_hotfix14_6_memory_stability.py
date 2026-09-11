import inspect
import os
import unittest
from unittest import mock

import runtime_persistence as rp
import ai_advisor


class Hotfix146MemoryStabilityTests(unittest.TestCase):
    def test_runtime_persistence_fails_open_without_supabase(self):
        with mock.patch.object(rp, '_db', return_value=None):
            self.assertFalse(rp.save_runtime_snapshot('test', 'x', {'ok': True}))
            self.assertIsNone(rp.load_runtime_snapshot('test', 'x'))
            self.assertEqual(rp.persist_macro_events([], []), 0)
            self.assertEqual(rp.load_active_macro_events(), [])

    def test_local_ai_fallback_is_useful_and_non_authoritative(self):
        payload = ai_advisor._local_operational_fallback(
            {
                'selected_signal': {
                    'symbol': 'BTC-USDT', 'timeframe': '1h', 'action': 'SHORT',
                    'entry': 100.0, 'stop_loss': 102.0, 'take_profit': 96.0,
                },
                'macro_context': {'risk_level': 'HIGH', 'futures_posture': 'CAUTION'},
            },
            'FUTURES',
            question='¿Qué hago?',
            reason='429'
        )
        self.assertEqual(payload.get('provider'), 'LOCAL_RULES')
        self.assertTrue(payload.get('degraded_mode'))
        text = ' '.join(str(payload.get(k, '')) for k in ('headline', 'advice', 'system_alignment'))
        self.assertIn('respaldo', text.lower())
        self.assertIn('no se altera', text.lower())

    def test_analytics_frontend_is_sequential(self):
        with open(os.path.join('static', 'analytics.js'), 'r', encoding='utf-8') as fh:
            source = fh.read()
        start = source.index('window.loadAllAnalytics = async function()')
        end = source.index('// ============================================================================\n// INICIALIZACIÓN', start)
        block = source[start:end]
        self.assertIn('for (const task of tasks)', block)
        self.assertNotIn('Promise.all([', block)
        self.assertNotIn('Promise.allSettled(', block)

    def test_no_render_tmp_runtime_files_and_compact_q5_projection(self):
        with open('app.py', 'r', encoding='utf-8') as fh:
            app_source = fh.read()
        with open('analytics_service.py', 'r', encoding='utf-8') as fh:
            analytics_source = fh.read()
        self.assertNotIn("/tmp/futures_analysis_cache.json", app_source)
        self.assertNotIn("/tmp/entry_alerts_sent.json", app_source)
        self.assertNotIn("/tmp/guardian_telegram_events.json", app_source)
        self.assertIn("runtime_snapshots_v1", inspect.getsource(rp))
        self.assertIn("analytics_quality_v2_compact_v1", analytics_source)
        self.assertNotIn("select('*, signal_results(*)')", analytics_source)

    def test_v1_anti_sweep_logic_is_preserved(self):
        with open('app.py', 'r', encoding='utf-8') as fh:
            source = fh.read()
        start = source.index('def _collect_sl_candidates')
        block = source[start:start + 9000]
        self.assertIn("'type': 'sweep'", block)
        self.assertIn('sweep_level', block)
        self.assertIn('atr * 0.25', block)
        self.assertIn('Detrás Liquidity Sweep', block)

    def test_memory_defaults_leave_render_headroom(self):
        with open('.env.example', 'r', encoding='utf-8') as fh:
            source = fh.read()
        self.assertIn('MEMORY_SOFT_LIMIT_MB=250', source)
        self.assertIn('MEMORY_HARD_LIMIT_MB=340', source)
        self.assertIn('MEMORY_ANALYSIS_CACHE_KEEP=2', source)
        self.assertIn('ANALYTICS_SNAPSHOT_FRESH_SECONDS=1800', source)


if __name__ == '__main__':
    unittest.main()
