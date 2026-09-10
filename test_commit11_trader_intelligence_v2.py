import unittest

from trader_intelligence import (
    build_runtime_trader_theses,
    build_trader_intelligence_v2_summary,
)


def _row(i, status='tp_hit', relation='SUPPORT', final='SHORT'):
    gross_r = 2.0 if status == 'tp_hit' else -1.0
    return {
        'id': f'c11-{i:02d}',
        'system_type': 'futures',
        'timeframe': '15m',
        'action_normalized': final,
        'status': status,
        'created_at': f'2026-08-{(i % 28) + 1:02d}T{i % 24:02d}:00:00+00:00',
        'context': {'learning': {
            'contract_version': 'market_separated_v1',
            'cohort': 'FUTURES_PERPETUAL_REAL_CLOSED_V1',
            'market_data_source': 'KUCOIN_FUTURES_PERPETUAL_REST',
            'market_data_is_synthetic': False,
            'source_candle_closed': True,
            'statistically_eligible': True,
            'evaluation_role': 'EXECUTABLE_SIGNAL',
            'quantitative_shadow': {'regime': 'TREND_DOWN'},
            'strategy_attribution_v2': {'items': [{
                'trader': 'Smart Money',
                'strategy': 'SWEEP_MSS',
                'vote_action': final,
                'confidence': 82,
                'relation_to_final': relation,
            }]},
        }},
        'signal_results': [{'status': status, 'gross_r': gross_r, 'created_at': f'2026-08-{(i % 28) + 1:02d}T23:00:00+00:00'}],
    }


class Commit11TraderIntelligenceV2Tests(unittest.TestCase):
    def test_runtime_thesis_is_post_decision_and_does_not_change_levels(self):
        analysis = {
            'system_type': 'futures',
            'symbol': 'BTC-USDT',
            'timeframe': '15m',
            'market_regime': {'regime': 'TRENDING_BEAR'},
            'levels': {'entry': 100.0, 'stop_loss': 102.0, 'take_profit': 96.0},
            'decision': {
                'action': 'SHORT',
                'audit': {'votes': [
                    {
                        'trader': 'Smart Money', 'normalized_action': 'SHORT',
                        'original_confidence': 88, 'disposition': 'APOYO_FINAL',
                        'strategies': ['SWEEP', 'MSS'], 'reasons': ['Barrido confirmado'],
                    },
                    {
                        'trader': 'Escéptico', 'normalized_action': 'NO_OPERAR',
                        'original_confidence': 75, 'disposition': 'CAUTELA_NO_OPERAR',
                        'strategies': ['RISK'], 'reasons': ['Riesgo elevado'],
                    },
                ]},
            },
        }
        before = dict(analysis['levels'])
        result = build_runtime_trader_theses(analysis)
        self.assertEqual(before, analysis['levels'])
        self.assertFalse(result['production_change'])
        self.assertTrue(result['policy']['abstention_allowed'])
        support = next(t for t in result['theses'] if t['trader'] == 'Smart Money')
        abstain = next(t for t in result['theses'] if t['trader'] == 'Escéptico')
        self.assertEqual(support['regime'], 'TREND_DOWN')
        self.assertEqual(support['entry_zone'], 100.0)
        self.assertEqual(abstain['stance'], 'ABSTAIN')
        self.assertIsNone(abstain['entry_zone'])

    def test_temporal_validation_stays_shadow_even_with_large_sample(self):
        rows = [_row(i, 'tp_hit' if i % 2 == 0 else 'sl_hit') for i in range(30)]
        summary = build_trader_intelligence_v2_summary({'FUTURES_CURRENT_OFFICIAL': rows})
        self.assertEqual(summary['authority'], 'SHADOW_DIAGNOSTIC')
        self.assertFalse(summary['production_change'])
        candidate = next(r for r in summary['temporal_validation'] if r['trader'] == 'Smart Money' and r['timeframe'] == '15M')
        self.assertEqual(candidate['n_resolved'], 30)
        self.assertGreater(candidate['validation_n'], 0)
        self.assertFalse(summary['policy']['weights_changed'])


if __name__ == '__main__':
    unittest.main()
