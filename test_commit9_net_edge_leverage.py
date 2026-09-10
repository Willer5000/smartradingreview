import unittest
from datetime import datetime, timedelta, timezone

from execution_economics import build_provisional_economics, complete_economics
from leverage_policy import select_risk_budget_leverage
from promotion_governance import evaluate_promotion_gate

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def official_row(i, *, win=True, complete=True, mae=0.5):
    status = 'tp_hit' if win else 'sl_hit'
    gross_r = 2.0 if win else -1.0
    # 1% structural risk and 0.12R fee/slippage model. Funding=0 here.
    modeled_net_r = gross_r - 0.12
    result = {
        'status': status,
        'pnl_pct': 2.0 if win else -1.0,
        'mfe_r': 2.0 if win else 0.2,
        'mae_r': mae,
        'created_at': (BASE + timedelta(hours=i, minutes=30)).isoformat(),
    }
    if complete:
        result.update({
            'economics_status': 'MODELED_COMPLETE_NO_SETTLEMENT',
            'economics_cost_components_complete': True,
            'gross_r': gross_r,
            'modeled_net_r': modeled_net_r,
            'funding_calculation_status': 'NO_SETTLEMENTS_IN_WINDOW',
        })
    return {
        'id': f's{i}',
        'symbol': 'BTC-USDT',
        'timeframe': '15m',
        'system_type': 'futures',
        'action_normalized': 'SHORT',
        'status': status,
        'created_at': (BASE + timedelta(hours=i)).isoformat(),
        'entry_price': 100.0,
        'stop_loss': 101.0,
        'take_profit': 98.0,
        'risk_reward': 2.0,
        'q6_learning': {
            'cohort': 'FUTURES_PERPETUAL_REAL_CLOSED_V1',
            'market_data_source': 'KUCOIN_FUTURES_PERPETUAL_REST',
            'market_data_is_synthetic': False,
            'source_candle_closed': True,
            'statistically_eligible': True,
            'evaluation_role': 'EXECUTABLE_SIGNAL',
        },
        'signal_results': [result],
    }


class Commit9NetEdgeLeverageTests(unittest.TestCase):
    def test_fee_slippage_model_converts_two_r_to_1_88r_before_funding(self):
        signal = {
            'system_type': 'futures', 'action_normalized': 'LONG',
            'symbol': 'BTC-USDT', 'entry_price': 100.0, 'stop_loss': 99.0,
            'take_profit': 102.0, 'leverage': 4,
        }
        result = {
            'status': 'tp_hit', 'pnl_pct': 2.0,
            'entry_timestamp': '2026-01-01T00:00:00+00:00',
            'exit_timestamp': '2026-01-01T01:00:00+00:00',
        }
        economics = build_provisional_economics(signal, result, round_trip_cost_rate=0.0012)
        self.assertAlmostEqual(economics['gross_r'], 2.0, places=6)
        self.assertAlmostEqual(economics['modeled_fee_slippage_cost_r'], 0.12, places=6)
        self.assertAlmostEqual(economics['modeled_net_r'], 1.88, places=6)
        self.assertEqual(economics['economics_status'], 'FUNDING_PENDING')

    def test_positive_funding_costs_long_and_credits_short(self):
        base_signal = {
            'system_type': 'futures', 'symbol': 'BTC-USDT',
            'entry_price': 100.0, 'take_profit': 102.0, 'leverage': 4,
        }
        result = {
            'status': 'tp_hit', 'pnl_pct': 2.0,
            'entry_timestamp': '2026-01-01T00:00:00+00:00',
            'exit_timestamp': '2026-01-01T09:00:00+00:00',
        }
        funding = {'funding_calculation_status': 'OBSERVED_RATES', 'funding_rate_sum': 0.0001,
                   'funding_settlements_count': 1, 'funding_data_source': 'TEST'}
        long_econ = complete_economics(
            {**base_signal, 'action_normalized': 'LONG', 'stop_loss': 99.0}, result, funding
        )
        short_econ = complete_economics(
            {**base_signal, 'action_normalized': 'SHORT', 'stop_loss': 101.0}, result, funding
        )
        self.assertAlmostEqual(long_econ['modeled_funding_cost_r'], 0.01, places=6)
        self.assertAlmostEqual(long_econ['modeled_net_r'], 1.87, places=6)
        self.assertAlmostEqual(short_econ['modeled_funding_cost_r'], -0.01, places=6)
        self.assertAlmostEqual(short_econ['modeled_net_r'], 1.89, places=6)

    def test_current_like_six_losses_cannot_enable_risk_growth(self):
        rows = [official_row(i, win=False, complete=True, mae=1.0) for i in range(6)]
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertFalse(gate['quality_optimization_allowed'])
        self.assertFalse(gate['risk_growth_allowed'])
        self.assertIn('risk_sample_ok', gate['risk_block_reasons'])
        self.assertEqual(gate['evidence']['consecutive_sl'], 6)

    def test_strong_model_complete_sample_can_open_risk_growth(self):
        rows = [official_row(i, win=((i % 10) < 7), complete=True, mae=0.55) for i in range(60)]
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertTrue(gate['quality_optimization_allowed'])
        self.assertTrue(gate['risk_growth_allowed'])
        self.assertGreaterEqual(gate['evidence']['total']['model_complete_net_coverage_pct'], 95.0)
        self.assertLessEqual(gate['evidence']['total']['avg_mae_r'], 0.80)

    def test_missing_model_complete_economics_blocks_risk_growth(self):
        rows = [official_row(i, win=((i % 10) < 7), complete=False, mae=0.55) for i in range(60)]
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertFalse(gate['risk_growth_allowed'])
        self.assertIn('risk_net_coverage_ok', gate['risk_block_reasons'])

    def test_static_1h_policy_keeps_hard_timeframe_ceiling(self):
        policy = select_risk_budget_leverage(
            minimum_required=4.0, sl_distance_pct=0.20,
            max_by_risk=50.0, max_by_atr_stress=50.0,
            safety_score=96.0, timeframe_static_max=20.0,
            fallback_exchange_max=50.0, adaptive_enabled=False,
        )
        self.assertIsNotNone(policy)
        self.assertLessEqual(policy['leverage'], 20)
        self.assertEqual(policy['timeframe_cap_mode'], 'HARD_STATIC_FALLBACK')
        self.assertEqual(policy['selection_policy'], 'MINIMUM_SAFE_VIABLE')

    def test_governed_risk_budget_can_exceed_old_1h_cap_when_geometry_supports_it(self):
        policy = select_risk_budget_leverage(
            minimum_required=4.0, sl_distance_pct=0.20,
            max_by_risk=50.0, max_by_atr_stress=50.0,
            safety_score=96.0, timeframe_static_max=20.0,
            fallback_exchange_max=50.0, adaptive_enabled=True,
            target_loss_budget_pct_margin=5.0,
        )
        self.assertIsNotNone(policy)
        self.assertGreater(policy['leverage'], 20)
        self.assertEqual(policy['leverage'], 25)
        self.assertEqual(policy['timeframe_cap_mode'], 'SOFT_REFERENCE')
        self.assertLessEqual(policy['leverage'] * 0.20, 5.0 + 1e-9)

    def test_wide_stop_does_not_force_high_leverage(self):
        policy = select_risk_budget_leverage(
            minimum_required=4.0, sl_distance_pct=2.0,
            max_by_risk=5.0, max_by_atr_stress=6.0,
            safety_score=96.0, timeframe_static_max=20.0,
            fallback_exchange_max=50.0, adaptive_enabled=True,
            target_loss_budget_pct_margin=5.0,
        )
        self.assertIsNotNone(policy)
        self.assertEqual(policy['leverage'], 4)
        self.assertLessEqual(policy['max_safe'], 5.0)


if __name__ == '__main__':
    unittest.main()
