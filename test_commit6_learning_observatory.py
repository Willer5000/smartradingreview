import os
import unittest
from pathlib import Path

import pandas as pd

from analytics_service import AnalyticsService
from adaptive_autopilot import _positive_authority_enabled
from chart_renderer import render_main_chart, render_indicator_chart


class Commit6LearningObservatoryTests(unittest.TestCase):
    def test_forensics_exposes_defensibility_and_stop_diagnostics(self):
        rows = [
            {
                'status': 'sl_hit',
                'signal_results': [{
                    'status': 'sl_hit',
                    'mfe_r': 0.05,
                    'mae_r': 1.0,
                    'execution_forensics': {
                        'entry_reached': True,
                        'diagnosis': 'STOPPED_WITHOUT_PROGRESS',
                        'mfe_r': 0.05,
                        'mae_r': 1.0,
                        'stop_was_possibly_tight': False,
                    },
                }],
            },
            {
                'status': 'sl_hit',
                'signal_results': [{
                    'status': 'sl_hit',
                    'mfe_r': 0.8,
                    'mae_r': 1.0,
                    'execution_forensics': {
                        'entry_reached': True,
                        'diagnosis': 'STOPPED_AFTER_MEANINGFUL_PROGRESS',
                        'mfe_r': 0.8,
                        'mae_r': 1.0,
                        'stop_was_possibly_tight': True,
                        'post_stop_recovery': {
                            'reclaimed_entry': True,
                            'tp_reached_after_stop': True,
                        },
                    },
                }],
            },
        ]
        result = AnalyticsService._execution_forensics_summary(rows)
        self.assertEqual(result['n_with_forensics'], 2)
        self.assertEqual(result['direct_stop_rate_pct'], 50.0)
        self.assertEqual(result['entry_defensibility_proxy_pct'], 50.0)
        self.assertEqual(result['stop_tight_suspect_rate_pct'], 50.0)
        self.assertEqual(result['post_stop_tp_rate_pct'], 50.0)
        self.assertAlmostEqual(result['avg_mfe_r'], 0.425, places=3)

    def test_positive_authority_is_fail_closed_by_default(self):
        previous = os.environ.pop('AUTOPILOT_POSITIVE_AUTHORITY_ENABLED', None)
        try:
            self.assertFalse(_positive_authority_enabled())
        finally:
            if previous is not None:
                os.environ['AUTOPILOT_POSITIVE_AUTHORITY_ENABLED'] = previous

    def test_report_charts_use_frontend_like_candles_and_vwap(self):
        n = 80
        times = pd.date_range('2026-09-01', periods=n, freq='h')
        opens = [100 + i * 0.08 for i in range(n)]
        closes = [o + (0.35 if i % 2 == 0 else -0.22) for i, o in enumerate(opens)]
        highs = [max(o, c) + 0.4 for o, c in zip(opens, closes)]
        lows = [min(o, c) - 0.4 for o, c in zip(opens, closes)]
        volumes = [1000 + (i % 10) * 75 for i in range(n)]
        analysis = {
            'symbol': 'BTC-USDT',
            'timeframe': '1h',
            'current_price': closes[-1],
            'decision': {'action': 'LONG', 'confidence': 82},
            'levels': {'entry': 105.0, 'stop_loss': 103.5, 'take_profit': 108.0},
            'structure': {'supports': [103.0], 'resistances': [109.0]},
            'zones': {'active_zones': {'LONG': {'price_min': 104.5, 'price_max': 105.5}}},
            'strategy_lab': {'trendlines': {'geometry': {
                'support': {'start_index': 20, 'start_price': 101.0, 'slope_per_candle': 0.06},
                'resistance': {'start_index': 20, 'start_price': 107.0, 'slope_per_candle': 0.05},
            }}},
            'df': {
                'time': [t.isoformat() for t in times],
                'open': opens,
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': volumes,
            },
        }
        main = render_main_chart('BTC-USDT', '1h', analysis)
        self.assertIsInstance(main, (bytes, bytearray))
        self.assertGreater(len(main), 5000)
        df = pd.DataFrame({
            'time': times, 'open': opens, 'high': highs, 'low': lows,
            'close': closes, 'volume': volumes,
        })
        vwap = render_indicator_chart(df, 'vwap', analysis)
        self.assertIsInstance(vwap, (bytes, bytearray))
        self.assertGreater(len(vwap), 3000)

    def test_zone_header_is_compact_and_trendlines_are_thin(self):
        js = Path('static/script.js').read_text(encoding='utf-8')
        css = Path('static/style.css').read_text(encoding='utf-8')
        self.assertIn("width: 1.1, dash: 'solid'", js)
        self.assertNotIn("else if (priceStatus.estado) summary", js)
        self.assertIn('text-overflow: ellipsis', css)

    def test_observatory_is_visible_in_analytics(self):
        html = Path('templates/analytics.html').read_text(encoding='utf-8')
        js = Path('static/analytics.js').read_text(encoding='utf-8')
        self.assertIn('learning-observatory-section', html)
        self.assertIn('renderLearningObservatory', js)
        self.assertIn('/api/review/autopilot/status', js)
        self.assertIn('/api/ai/gemini-activity', js)


if __name__ == '__main__':
    unittest.main()
