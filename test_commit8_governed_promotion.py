import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from promotion_governance import evaluate_promotion_gate
from strategy_registry import get_registry_snapshot, invalidate_registry_cache, observation_matches_runtime_filter


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_row(i, win=True, realized=True):
    status = 'tp_hit' if win else 'sl_hit'
    result = {
        'status': status,
        'pnl_pct': 2.0 if win else -1.0,
        'created_at': (BASE + timedelta(hours=i, minutes=30)).isoformat(),
    }
    if realized:
        # 1% Entry->SL risk => these values are directly comparable in R.
        result['net_pnl_pct'] = 1.80 if win else -1.10
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


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *args, **kwargs): return self
    def in_(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def execute(self): return FakeResponse(self.rows)


class FakeClient:
    def __init__(self, rows): self.rows = rows
    def table(self, name): return FakeTable(self.rows)


class FakeDB:
    enabled = True
    def __init__(self, rows): self.client = FakeClient(rows)


class Commit8GovernedPromotionTests(unittest.TestCase):
    def test_current_like_six_losses_cannot_open_positive_quality_authority(self):
        rows = [make_row(i, win=False) for i in range(6)]
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertFalse(gate['quality_optimization_allowed'])
        self.assertFalse(gate['risk_growth_allowed'])
        self.assertIn('sample_ok', gate['block_reasons'])
        self.assertIn('failure_streak_ok', gate['block_reasons'])

    def test_robust_positive_complete_realized_sample_can_open_quality_gate(self):
        rows = []
        # 70% winners / 30% losers, distributed through the whole window so the
        # final 30% validation segment remains positive.
        for i in range(40):
            rows.append(make_row(i, win=(i % 10) < 7, realized=True))
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertTrue(gate['quality_optimization_allowed'])
        self.assertTrue(gate['strategy_veto_authority_allowed'])
        self.assertFalse(gate['risk_growth_allowed'])
        self.assertGreaterEqual(gate['evidence']['total']['realized_net_coverage_pct'], 95.0)

    def test_missing_realized_cost_attribution_keeps_positive_quality_gate_closed(self):
        rows = [make_row(i, win=(i % 10) < 7, realized=False) for i in range(40)]
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertFalse(gate['quality_optimization_allowed'])
        self.assertIn('realized_net_coverage_ok', gate['block_reasons'])
        self.assertIn('realized_net_expectancy_ok', gate['block_reasons'])

    def test_incomplete_window_fails_closed_even_with_good_results(self):
        rows = [make_row(i, win=(i % 10) < 7, realized=True) for i in range(40)]
        gate = evaluate_promotion_gate(rows, coverage_complete=False, coverage={'complete': False})
        self.assertFalse(gate['quality_optimization_allowed'])
        self.assertFalse(gate['strategy_veto_authority_allowed'])
        self.assertIn('coverage_complete', gate['block_reasons'])

    def test_six_consecutive_losses_block_positive_authority(self):
        rows = [make_row(i, win=True, realized=True) for i in range(34)]
        rows.extend(make_row(i, win=False, realized=True) for i in range(34, 40))
        gate = evaluate_promotion_gate(rows, coverage_complete=True, coverage={'complete': True})
        self.assertFalse(gate['quality_optimization_allowed'])
        self.assertEqual(gate['evidence']['consecutive_sl'], 6)
        self.assertIn('failure_streak_ok', gate['block_reasons'])


    def test_runtime_filter_prevents_broad_rsi_family_overpromotion(self):
        config = {
            'observation_filter': {
                'profile': 'FAST',
                'alignment_with_system': 'ALIGNED',
                'timeframe': '15M',
            }
        }
        fast_aligned = {
            'profile': 'FAST',
            'alignment_with_system': 'ALIGNED',
            'direction': 'SHORT',
            'state': 'FAST_RSI_RECOVERY_SHORT',
        }
        balanced_conflict = {
            'profile': 'BALANCED',
            'alignment_with_system': 'CONFLICT',
            'direction': 'SHORT',
            'state': 'BALANCED_RSI_PULLBACK_SHORT',
        }
        self.assertTrue(observation_matches_runtime_filter(
            fast_aligned, config, decision='SHORT', timeframe='15m', market_regime='BALANCE'
        ))
        self.assertFalse(observation_matches_runtime_filter(
            balanced_conflict, config, decision='SHORT', timeframe='15m', market_regime='BALANCE'
        ))
        self.assertFalse(observation_matches_runtime_filter(
            fast_aligned, {}, decision='SHORT', timeframe='15m', market_regime='BALANCE'
        ))

    def test_active_registry_row_has_no_runtime_authority_when_global_veto_gate_is_closed(self):
        row = {
            'strategy_key': 'Q7_RSI_PROFILE_V1',
            'symbol': '*', 'timeframe': '*', 'market_regime': '*',
            'state': 'ACTIVE', 'config': {'observation_filter': {'profile': 'FAST', 'alignment_with_system': 'ALIGNED'}}, 'evidence': {},
            'version': 'x', 'updated_at': BASE.isoformat(),
        }
        db = FakeDB([row])
        invalidate_registry_cache()
        with patch('promotion_governance.get_promotion_governance_status', return_value={
            'strategy_veto_authority_allowed': False,
            'block_reasons': ['coverage_complete'],
        }):
            snapshot = get_registry_snapshot('BTC-USDT', '15m', 'BALANCE', db=db)
        self.assertFalse(snapshot['production_authority'])
        self.assertFalse(snapshot['strategies']['Q7_RSI_PROFILE_V1']['production_authority'])

    def test_active_registry_row_is_veto_only_when_global_gate_is_open(self):
        row = {
            'strategy_key': 'Q7_RSI_PROFILE_V1',
            'symbol': '*', 'timeframe': '*', 'market_regime': '*',
            'state': 'ACTIVE', 'config': {'observation_filter': {'profile': 'FAST', 'alignment_with_system': 'ALIGNED'}}, 'evidence': {},
            'version': 'x', 'updated_at': BASE.isoformat(),
        }
        db = FakeDB([row])
        invalidate_registry_cache()
        with patch('promotion_governance.get_promotion_governance_status', return_value={
            'strategy_veto_authority_allowed': True,
            'block_reasons': [],
        }):
            snapshot = get_registry_snapshot('BTC-USDT', '15m', 'BALANCE', db=db)
        strategy = snapshot['strategies']['Q7_RSI_PROFILE_V1']
        self.assertTrue(snapshot['production_authority'])
        self.assertTrue(strategy['production_authority'])
        self.assertEqual(strategy['authority_mode'], 'CONFLICT_VETO_ONLY')


if __name__ == '__main__':
    unittest.main()
