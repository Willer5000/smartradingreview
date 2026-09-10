import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from edge_discovery import _extract_features, build_edge_discovery_summary, discover_edges, early_failure_watch


def make_signal(i, *, status='tp_hit', rr=2.0, profile='FAST', alignment='ALIGNED', regime='TREND_DOWN', action='SHORT', retest=None):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    q7 = {
        'shadow_only': True,
        'eligible': True,
        'active_profile': profile,
        'rsi_profile': {
            'profile': profile,
            'alignment_with_system': alignment,
            'direction': action,
        },
        'vwap_reversion': {'state': 'NO_EDGE'},
        'breakout_retest': {'state': retest or 'NO_RETEST', 'direction': action},
    }
    return {
        'id': f's{i}',
        'symbol': 'BTC-USDT',
        'timeframe': '15m',
        'system_type': 'futures',
        'action_normalized': action,
        'status': status,
        'created_at': created.isoformat(),
        'entry_price': 100.0,
        'stop_loss': 99.0 if action == 'LONG' else 101.0,
        'take_profit': 102.0 if action == 'LONG' else 98.0,
        'risk_reward': rr,
        'context': {
            'execution': {
                'quality_score_version': '36W_V2_NORMALIZED',
                'entry_reachability_score': 82,
                'entry_defensibility_score': 78,
                'tp_quality_score': 74,
            },
            'learning': {
                'cohort': 'FUTURES_PERPETUAL_REAL_CLOSED_V1',
                'market_data_source': 'KUCOIN_FUTURES_PERPETUAL_REST',
                'market_data_is_synthetic': False,
                'source_candle_closed': True,
                'evaluation_role': 'SHADOW_ANALYSIS',
                'statistically_eligible': False,
                'quantitative_shadow': {
                    'regime': regime,
                    'direction_alignment': 'ALIGNED',
                    'entry_location': 'FAVORABLE',
                },
                'microstructure_shadow': {'alignment': 'ALIGNED'},
                'q7_strategy_lab_shadow': q7,
            },
        },
        'signal_results': [{
            'status': status,
            'mfe_r': 1.2 if status == 'tp_hit' else 0.15,
            'mae_r': 0.35 if status == 'tp_hit' else 1.0,
            'execution_forensics': {},
        }],
    }


class Commit7EdgeDiscoveryTests(unittest.TestCase):
    def test_positive_pattern_requires_out_of_sample_confirmation(self):
        rows = []
        # Interleave families so the positive setup exists before and after
        # the global temporal cutoff.
        for i in range(30):
            if i % 2 == 0:
                rows.append(make_signal(i, status='tp_hit' if i % 6 != 0 else 'sl_hit'))
            else:
                rows.append(make_signal(i, status='sl_hit', profile='BALANCED', alignment='CONFLICT', regime='TREND_UP', action='LONG'))
        result = discover_edges(rows, 'FUTURES_SHADOW')
        priority = result['priority']
        self.assertTrue(priority)
        self.assertTrue(any((row['validation']['resolved'] >= 3 and row['validation']['expectancy_r'] > 0) for row in priority))
        self.assertTrue(all(row['authority'] == 'RESEARCH_ONLY' for row in priority))

    def test_combinations_are_bounded(self):
        rows = [make_signal(i, status='tp_hit' if i % 2 == 0 else 'sl_hit') for i in range(20)]
        result = discover_edges(rows, 'FUTURES_SHADOW')
        all_rows = result['priority'] + result['watch'] + result['low_priority']
        self.assertTrue(all(len(row['factors']) <= 3 for row in all_rows))

    def test_bad_pattern_is_low_priority(self):
        rows = [make_signal(i, status='sl_hit', profile='BALANCED', alignment='CONFLICT', regime='TREND_UP', action='LONG') for i in range(20)]
        result = discover_edges(rows, 'FUTURES_SHADOW')
        self.assertTrue(result['low_priority'])
        self.assertTrue(all(row['state'] == 'LOW_PRIORITY_RESEARCH' for row in result['low_priority']))

    def test_early_failure_watch_flags_six_consecutive_sl(self):
        rows = []
        for i in range(6):
            signal = make_signal(i, status='sl_hit')
            signal['context']['learning']['evaluation_role'] = 'EXECUTABLE_SIGNAL'
            signal['context']['learning']['statistically_eligible'] = True
            rows.append(signal)
        watch = early_failure_watch(rows)
        self.assertTrue(watch['alert'])
        self.assertEqual(watch['consecutive_sl'], 6)
        self.assertEqual(watch['severity'], 'HIGH')

    def test_summary_never_changes_production(self):
        shadow = [make_signal(i, status='tp_hit' if i % 2 == 0 else 'sl_hit') for i in range(12)]
        official = []
        summary = build_edge_discovery_summary([], shadow, official)
        self.assertEqual(summary['authority'], 'RESEARCH_ONLY')
        self.assertFalse(summary['production_change'])

    def test_smc_entry_and_only_supporting_trader_strategy_become_features(self):
        signal = make_signal(1, status='tp_hit', action='LONG')
        signal['context']['execution']['entry_source'] = (
            'Order Block alcista + Liquidity + Sweep + MSS/BOS + Displacement [SMC 91/100]'
        )
        signal['context']['learning']['strategy_attribution_v2'] = {
            'items': [
                {
                    'strategy': 'LIQUIDITY_SWEEP_ALCISTA',
                    'relation_to_final': 'SUPPORT',
                },
                {
                    'strategy': 'ORDER_BLOCK_BAJISTA',
                    'relation_to_final': 'OPPOSE',
                },
            ]
        }
        features = _extract_features(signal)
        conditions = features['conditions']
        self.assertIn('ENTRY_SMC:SWEEP', conditions)
        self.assertIn('ENTRY_SMC:MSS_BOS', conditions)
        self.assertIn('ENTRY_SMC:DISPLACEMENT', conditions)
        self.assertIn('ENTRY_POI:ORDER_BLOCK', conditions)
        self.assertIn('STRATEGY:SWEEP', conditions)
        self.assertNotIn('STRATEGY:ORDER_BLOCK', conditions)

    def test_gemini_recovery_and_trendline_snapshot_are_present(self):
        app_source = Path('app.py').read_text(encoding='utf-8')
        review_source = Path('review_trader.py').read_text(encoding='utf-8')
        self.assertIn("def _run_ai_learning_daily", app_source)
        self.assertIn("claim_daily_job(\n            review_trader.db,\n            'AI_LEARNING'", app_source)
        self.assertIn("trendline_strategy_lab_shadow", review_source)
        self.assertIn("entry_defensibility_score", review_source)


if __name__ == '__main__':
    unittest.main()
