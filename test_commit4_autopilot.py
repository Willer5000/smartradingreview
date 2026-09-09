import unittest

from adaptive_autopilot import (
    DEFAULT_Q2_WEIGHTS,
    derive_execution_profile,
    default_execution_profile,
)
from strategy_registry import default_registry_snapshot


class Commit4AutopilotTests(unittest.TestCase):
    def test_current_tiny_negative_sample_has_no_authority(self):
        profile = derive_execution_profile({
            'resolved': 4,
            'tp': 0,
            'sl': 4,
            'expectancy_r': -1.0,
            'profit_factor': 0.0,
            'avg_mfe_r': 0.1,
            'avg_mae_r': 1.0,
            'stop_without_progress_ratio': 1.0,
            'stop_tight_suspect_ratio': 0.0,
        }, symbol='XRP-USDT', timeframe='1h')
        self.assertEqual(profile['state'], 'OBSERVE')
        self.assertFalse(profile['production_authority'])
        self.assertFalse(profile['config']['allow_leverage_growth'])
        self.assertEqual(profile['config']['leverage_target_factor'], 1.0)

    def test_robust_negative_evidence_can_only_protect(self):
        profile = derive_execution_profile({
            'resolved': 30,
            'tp': 4,
            'sl': 26,
            'expectancy_r': -0.42,
            'profit_factor': 0.31,
            'avg_mfe_r': 0.25,
            'avg_mae_r': 1.05,
            'stop_without_progress_ratio': 0.55,
            'stop_tight_suspect_ratio': 0.30,
        }, symbol='BTC-USDT', timeframe='15m')
        self.assertEqual(profile['state'], 'PROTECT')
        self.assertTrue(profile['production_authority'])
        self.assertLessEqual(profile['config']['leverage_cap_factor'], 1.0)
        self.assertFalse(profile['config']['allow_leverage_growth'])
        self.assertGreaterEqual(profile['config']['entry_min_defensibility'], 60.0)
        self.assertAlmostEqual(sum(profile['config']['q2_weights'].values()), 1.0, places=5)

    def test_positive_edge_needs_fifty_results_for_leverage_growth(self):
        p25 = derive_execution_profile({
            'resolved': 30,
            'tp': 18,
            'sl': 12,
            'expectancy_r': 0.22,
            'profit_factor': 1.35,
            'avg_mfe_r': 1.4,
            'avg_mae_r': 0.60,
        })
        self.assertEqual(p25['state'], 'ACTIVE')
        self.assertFalse(p25['config']['allow_leverage_growth'])

        p50 = derive_execution_profile({
            'resolved': 60,
            'tp': 36,
            'sl': 24,
            'expectancy_r': 0.22,
            'profit_factor': 1.35,
            'avg_mfe_r': 1.4,
            'avg_mae_r': 0.60,
        })
        self.assertTrue(p50['config']['allow_leverage_growth'])
        self.assertEqual(p50['config']['leverage_target_factor'], 1.10)

    def test_strong_growth_is_still_bounded(self):
        profile = derive_execution_profile({
            'resolved': 120,
            'tp': 80,
            'sl': 40,
            'expectancy_r': 0.35,
            'profit_factor': 1.70,
            'avg_mfe_r': 1.8,
            'avg_mae_r': 0.50,
        })
        self.assertTrue(profile['config']['allow_leverage_growth'])
        self.assertLessEqual(profile['config']['leverage_target_factor'], 1.20)

    def test_registry_defaults_have_zero_production_authority(self):
        snapshot = default_registry_snapshot()
        self.assertFalse(snapshot['production_authority'])
        self.assertTrue(snapshot['strategies'])
        self.assertTrue(all(not row['production_authority'] for row in snapshot['strategies'].values()))


if __name__ == '__main__':
    unittest.main()
