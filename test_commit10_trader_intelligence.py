import os
import unittest

from learning_integrity import (
    cohort_fingerprint,
    is_verified_official_futures,
    is_verified_spot,
)
from trader_intelligence import build_trader_scorecard
from promotion_governance import evaluate_promotion_gate
from analytics_service import AnalyticsService


def _learning(role='EXECUTABLE_SIGNAL', market='futures', regime='TREND_DOWN'):
    if market == 'spot':
        return {
            'cohort': 'SPOT_REAL_CLOSED_Q6',
            'market_data_source': 'KUCOIN_SPOT_REST',
            'market_data_is_synthetic': False,
            'source_candle_closed': True,
            'analysis_version': 'spot_closed_q6_v1',
            'source_candle_timestamp': '2026-09-09T10:00:00+00:00',
            'source_candle_close_timestamp': '2026-09-09T11:00:00+00:00',
            'statistically_eligible': True,
            'strategy_attribution_v2': {'items': []},
            'quantitative_shadow': {'regime': regime},
        }
    return {
        'contract_version': 'market_separated_v1',
        'cohort': 'FUTURES_PERPETUAL_REAL_CLOSED_V1',
        'market_data_source': 'KUCOIN_FUTURES_PERPETUAL_REST',
        'market_data_is_synthetic': False,
        'source_candle_closed': True,
        'statistically_eligible': role == 'EXECUTABLE_SIGNAL',
        'evaluation_role': role,
        'strategy_attribution_v2': {'items': []},
        'quantitative_shadow': {'regime': regime},
    }


def _row(i, status, final='SHORT', market='futures', tf='15m', rr=2.0, role='EXECUTABLE_SIGNAL'):
    learning = _learning(role=role, market=market)
    learning['strategy_attribution_v2'] = {
        'items': [
            {
                'trader': 'Smart Money',
                'strategy': 'SWEEP',
                'vote_action': final,
                'confidence': 80,
                'relation_to_final': 'SUPPORT',
            },
            # Same trader, same vote, second strategy: must NOT count as another outcome.
            {
                'trader': 'Smart Money',
                'strategy': 'MSS',
                'vote_action': final,
                'confidence': 80,
                'relation_to_final': 'SUPPORT',
            },
            {
                'trader': 'Escéptico',
                'strategy': 'VETO_RISK',
                'vote_action': 'LONG' if final == 'SHORT' else 'SHORT',
                'confidence': 70,
                'relation_to_final': 'OPPOSE',
            },
        ]
    }
    action = final if market == 'futures' else ('COMPRA_SPOT' if final == 'LONG' else 'VENTA_SPOT')
    return {
        'id': f's{i}',
        'system_type': market,
        'timeframe': tf,
        'action_normalized': action,
        'status': status,
        'created_at': f'2026-09-09T1{i}:00:00+00:00',
        'entry_price': 100.0,
        'stop_loss': 101.0 if final == 'SHORT' else 99.0,
        'take_profit': 98.0 if final == 'SHORT' else 102.0,
        'risk_reward': rr,
        'context': {'learning': learning, 'execution': {'quality_score_version': '36W_V2_NORMALIZED'}},
        'signal_results': [{
            'status': status,
            'gross_r': -1.0 if status == 'sl_hit' else rr if status == 'tp_hit' else None,
            'mfe_r': 1.2,
            'mae_r': 0.4,
            'execution_forensics': {
                'diagnosis': 'ENTRY_DEFENDED_TO_TARGET' if status == 'tp_hit' else 'STOPPED_AFTER_WEAK_PROGRESS',
                'entry_reached': True,
                'mfe_r': 1.2,
                'mae_r': 0.4,
            },
            'created_at': f'2026-09-09T1{i}:30:00+00:00',
        }],
    }


class Commit10Tests(unittest.TestCase):
    def test_canonical_contracts_are_market_specific(self):
        fut = _row(1, 'tp_hit')
        self.assertTrue(is_verified_official_futures(fut))
        bad = dict(fut)
        bad['context'] = {'learning': dict(fut['context']['learning'])}
        bad['context']['learning'].pop('contract_version')
        self.assertFalse(is_verified_official_futures(bad))

        spot = _row(2, 'tp_hit', final='LONG', market='spot', tf='1h')
        self.assertTrue(is_verified_spot(spot))
        self.assertFalse(is_verified_official_futures(spot))

    def test_scorecard_separates_market_timeframe_regime_and_opposition(self):
        win = _row(1, 'tp_hit', rr=2.0)
        loss = _row(2, 'sl_hit', rr=2.0)
        spot = _row(3, 'tp_hit', final='LONG', market='spot', tf='1h', rr=1.5)
        result = build_trader_scorecard({
            'FUTURES_CURRENT_OFFICIAL': [win, loss],
            'SPOT_CURRENT_OFFICIAL': [spot],
        })
        rows = result['rows']
        support = next(r for r in rows if r['trader'] == 'Smart Money' and r['market'] == 'FUTURES' and r['timeframe'] == '15M' and r['regime'] == 'ALL')
        oppose = next(r for r in rows if r['trader'] == 'Escéptico' and r['market'] == 'FUTURES' and r['timeframe'] == '15M' and r['regime'] == 'ALL')
        spot_row = next(r for r in rows if r['trader'] == 'Smart Money' and r['market'] == 'SPOT' and r['timeframe'] == '1H')
        self.assertEqual(support['resolved'], 2)  # not 4 despite two strategies per vote
        self.assertAlmostEqual(support['judgement_expectancy_r'], 0.5)
        self.assertAlmostEqual(oppose['judgement_expectancy_r'], -0.5)
        self.assertEqual(spot_row['resolved'], 1)
        self.assertTrue(result['policy']['market_specific'])
        self.assertTrue(result['policy']['timeframe_specific'])
        self.assertTrue(result['policy']['regime_specific'])
        self.assertFalse(result['policy']['weights_changed'])

    def test_forensics_diagnosis_is_not_double_counted(self):
        row = _row(1, 'sl_hit')
        summary = AnalyticsService._execution_forensics_summary([row])
        self.assertEqual(summary['diagnoses'].get('STOPPED_AFTER_WEAK_PROGRESS'), 1)
        self.assertEqual(summary['n_with_forensics'], 1)

    def test_governance_exposes_same_scope_fingerprint(self):
        row = _row(1, 'sl_hit')
        status = evaluate_promotion_gate([row], coverage_complete=False, coverage={'complete': False})
        evidence = status['evidence']
        self.assertEqual(evidence['cohort_n'], 1)
        self.assertEqual(
            evidence['cohort_fingerprint'],
            cohort_fingerprint([row], scope='CURRENT_QUALITY_FUTURES_OFFICIAL')
        )
        self.assertFalse(status['quality_optimization_allowed'])
        self.assertFalse(status['risk_growth_allowed'])

    def test_groq_key_in_legacy_learning_slot_routes_to_groq_learning(self):
        old = os.environ.get('GEMINI_API_KEY')
        try:
            os.environ['GEMINI_API_KEY'] = 'gsk_commit10_test_key'
            import ai_advisor
            provider, key = ai_advisor._learning_key_provider()
            route, _ = ai_advisor._resolve_ai_route('LEARNING', 'LEARNING')
            self.assertEqual(provider, 'GROQ_LEARNING')
            self.assertEqual(route, 'GROQ_LEARNING')
            self.assertTrue(key.startswith('gsk_'))
        finally:
            if old is None:
                os.environ.pop('GEMINI_API_KEY', None)
            else:
                os.environ['GEMINI_API_KEY'] = old


if __name__ == '__main__':
    unittest.main()
