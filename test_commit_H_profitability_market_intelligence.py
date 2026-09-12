import unittest
from unittest.mock import patch

import profitability_router as pr
from research_shadow_bridge import runtime_research_features, matches_research_scope


def _analysis():
    return {
        'success': True,
        'symbol': 'BTC-USDT',
        'timeframe': '30m',
        'decision': {'action': 'SHORT', 'estrategias': ['PULLBACK BAJISTA']},
        'levels': {
            'execution_safety': 82,
            'sl_reliability': 91,
            'tp_quality_score': 79,
            'entry_defensibility_score': 84,
            'entry_reachability_score': 78,
        },
        'futures_quantitative_context': {'regime': 'TREND_DOWN'},
        'futures_microstructure_context': {
            'alignment': 'ALIGNED',
            'metrics': {
                'orderbook_imbalance': -0.31,
                'recent_buy_share': 0.34,
                'oi_change_pct': 0.8,
                'funding_rate': 0.0002,
                'basis_pct': -0.02,
                'liquidity_band': 'HIGH',
            },
        },
    }


class CommitHTests(unittest.TestCase):
    def test_runtime_features_cover_market_intelligence(self):
        feat = runtime_research_features(_analysis(), 'futures')
        self.assertEqual(feat['oi_change_band'], 'BUILDING')
        self.assertEqual(feat['funding_band'], 'NEUTRAL')
        self.assertEqual(feat['basis_band'], 'NEUTRAL')
        self.assertEqual(feat['liquidity_band'], 'HIGH')
        self.assertTrue(matches_research_scope({
            'market_family': 'CRYPTO_FUTURES', 'timeframe': '30M',
            'direction': 'SHORT', 'regime': 'TREND_DOWN',
            'oi_change_band': 'BUILDING',
        }, feat))

    def test_negative_oos_can_veto_but_positive_cannot_create_trade(self):
        negative = {
            'candidate_key': 'bad', 'source_engine': 'strategy',
            'experiment': 'FACTORY_STRATEGY', 'stage': 'REJECTED_OOS',
            'scope': {'market_family':'CRYPTO_FUTURES','timeframe':'30M','direction':'SHORT','regime':'TREND_DOWN'},
            'metrics': {'all': {'resolved':40,'expectancy_r':-0.4,'net_evidence_pct':95},
                        'validation': {'resolved':12,'expectancy_r':-0.55,'profit_factor':0.6}},
            'meta': {'is_current': True},
        }
        with patch.object(pr, '_load_evidence', return_value=([negative], [])):
            route = pr.evaluate_profitability_route(_analysis(), 'futures')
        self.assertEqual(route['state'], 'NEGATIVE_EDGE_VETO')
        self.assertTrue(route['block_new_signal'])

        # A diagnostic risk/trader slice may warn, but must never cancel a
        # production signal by itself. Hard veto authority stays strategy-only.
        diagnostic = dict(negative)
        diagnostic.update(candidate_key='diag', source_engine='risk', experiment='SL_QUALITY')
        with patch.object(pr, '_load_evidence', return_value=([diagnostic], [])):
            route = pr.evaluate_profitability_route(_analysis(), 'futures')
        self.assertFalse(route['block_new_signal'])
        self.assertNotEqual(route['state'], 'NEGATIVE_EDGE_VETO')

        positive = dict(negative)
        positive.update(candidate_key='good', stage='SHADOW_READY')
        positive['metrics'] = {'all': {'resolved':50,'expectancy_r':0.3,'net_evidence_pct':95},
                               'validation': {'resolved':12,'expectancy_r':0.25,'profit_factor':1.4}}
        positive['meta'] = {'is_current': True, 'recommended_shadow_target': 8}
        shadow = [{'candidate_key':'good','resolved_n':2,'expectancy_r':0.4,'profit_factor':1.5}]
        with patch.object(pr, '_load_evidence', return_value=([positive], shadow)):
            route = pr.evaluate_profitability_route(_analysis(), 'futures')
        self.assertEqual(route['state'], 'SHADOW_READY')
        self.assertFalse(route['block_new_signal'])


if __name__ == '__main__':
    unittest.main()
