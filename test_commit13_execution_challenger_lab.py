import unittest
from datetime import datetime, timezone

import pandas as pd

from execution_challenger_lab import (
    build_execution_challenger_lab,
    evaluate_execution_challengers,
    summarize_execution_challenger_evidence,
)


class Commit13ExecutionChallengerLabTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            'time': pd.date_range('2026-09-01', periods=30, freq='h', tz='UTC'),
            'open': [100 + i * 0.1 for i in range(30)],
            'high': [102 + i * 0.1 for i in range(30)],
            'low': [98 + i * 0.1 for i in range(30)],
            'close': [101 + i * 0.1 for i in range(30)],
        })

    def _analysis(self):
        return {
            'system_type': 'futures',
            'analysis_price': 103.5,
            'decision': {
                'action': 'LONG',
                'estrategias': ['LIQUIDITY SWEEP', 'MSS', 'ORDER BLOCK ALCISTA'],
                'razones': ['Sweep de liquidez con desplazamiento'],
                'registro_votacion': {
                    'dynamic_expert_committee_shadow': {
                        'shadow_action': 'LONG',
                        'authority': 'SHADOW_ONLY',
                    }
                },
            },
            'levels': {
                'entry': 102.0,
                'stop_loss': 97.0,
                'take_profit': 112.0,
            },
            'strategy_lab': {
                'strategies': {
                    'breakout_retest': {'retest_price': 101.5}
                }
            },
        }

    def test_lab_is_shadow_and_never_mutates_production_levels(self):
        analysis = self._analysis()
        before = dict(analysis['levels'])
        lab = build_execution_challenger_lab(analysis, self.df)
        self.assertEqual(analysis['levels'], before)
        self.assertEqual(lab['authority'], 'SHADOW_ONLY')
        self.assertFalse(lab['production_change'])
        self.assertLessEqual(len(lab['candidates']), 4)
        self.assertEqual(lab['candidates'][0]['name'], 'BASELINE')
        self.assertEqual(lab['candidates'][0]['entry'], before['entry'])
        self.assertTrue(all(c['affects_production'] is False for c in lab['candidates']))

    def test_missing_smc_or_retest_evidence_is_not_fabricated(self):
        analysis = self._analysis()
        analysis['decision']['estrategias'] = []
        analysis['decision']['razones'] = []
        analysis['strategy_lab'] = {}
        lab = build_execution_challenger_lab(analysis, self.df)
        names = {c['name'] for c in lab['candidates']}
        self.assertNotIn('LIQUIDITY_SWEEP_MSS_POI', names)
        self.assertNotIn('TRENDLINE_RETEST', names)

    def test_candidate_evaluation_uses_same_candles_and_resolves_tp(self):
        signal = {
            'q6_learning': {
                'execution_challenger_lab': {
                    'candidates': [{
                        'name': 'BASELINE', 'geometry_valid': True,
                        'action': 'LONG', 'entry': 100.0,
                        'stop_loss': 95.0, 'take_profit': 110.0,
                        'risk_reward': 2.0,
                    }]
                }
            }
        }
        df = pd.DataFrame({
            'time': pd.to_datetime(['2026-09-10T00:00:00Z', '2026-09-10T01:00:00Z']),
            'high': [101.0, 111.0], 'low': [99.0, 100.5],
            'open': [100.0, 101.0], 'close': [100.5, 110.0],
        })
        out = evaluate_execution_challengers(
            signal, df,
            datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(out['authority'], 'SHADOW_ONLY')
        result = out['results'][0]
        self.assertEqual(result['status'], 'tp_hit')
        self.assertTrue(result['entry_reached'])
        self.assertEqual(result['realized_r'], 2.0)

    def test_same_candle_tp_and_sl_is_ambiguous(self):
        signal = {
            'q6_learning': {
                'execution_challenger_lab': {
                    'candidates': [{
                        'name': 'BASELINE', 'geometry_valid': True,
                        'action': 'LONG', 'entry': 100.0,
                        'stop_loss': 95.0, 'take_profit': 110.0,
                        'risk_reward': 2.0,
                    }]
                }
            }
        }
        df = pd.DataFrame({
            'time': pd.to_datetime(['2026-09-10T00:00:00Z']),
            'high': [111.0], 'low': [94.0], 'open': [100.0], 'close': [101.0],
        })
        out = evaluate_execution_challengers(
            signal, df,
            datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(out['results'][0]['status'], 'ambiguous')
        self.assertIsNone(out['results'][0]['realized_r'])

    def test_analytics_summary_keeps_spot_and_futures_separate(self):
        evaluation = {
            'results': [{
                'name': 'DEFENSIBILITY', 'status': 'tp_hit',
                'entry_reached': True, 'realized_r': 1.8,
                'mfe_r': 2.0, 'mae_r': 0.25,
            }]
        }
        rows = {
            'SPOT_CURRENT_OFFICIAL': [{
                'system_type': 'spot',
                'signal_results': {'status': 'tp_hit', 'execution_challenger_results': evaluation},
            }],
            'FUTURES_CURRENT_OFFICIAL': [{
                'system_type': 'futures',
                'signal_results': {'status': 'tp_hit', 'execution_challenger_results': evaluation},
            }],
        }
        out = summarize_execution_challenger_evidence(rows)
        markets = {row['market'] for row in out['rows']}
        self.assertEqual(markets, {'SPOT', 'FUTURES'})
        self.assertTrue(out['policy']['spot_futures_separate'])
        self.assertTrue(out['policy']['oos_required_before_promotion'])
        self.assertTrue(out['policy']['costs_required_before_promotion'])


if __name__ == '__main__':
    unittest.main()
