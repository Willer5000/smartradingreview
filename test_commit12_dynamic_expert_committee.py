import unittest
from pathlib import Path

from dynamic_expert_committee import (
    build_shadow_profile,
    get_shadow_multiplier,
    install_shadow_profile,
    simulate_shadow_decision,
)


class Commit12DynamicExpertCommitteeTests(unittest.TestCase):
    def test_profile_is_shadow_and_fails_closed_without_governance(self):
        intelligence = {
            'scorecard_v1': {'pairwise_redundancy': []},
            'temporal_validation': [
                {
                    'trader': 'Smart Money', 'market': 'FUTURES',
                    'timeframe': '15M', 'direction': 'SHORT',
                    'regime': 'TREND_DOWN', 'relation': 'SUPPORT',
                    'n_resolved': 40, 'validation_n': 12,
                    'discovery_expectancy_r': 0.4,
                    'validation_expectancy_r': 0.3,
                },
                {
                    'trader': 'Multiframe', 'market': 'FUTURES',
                    'timeframe': '15M', 'direction': 'SHORT',
                    'regime': 'TREND_DOWN', 'relation': 'SUPPORT',
                    'n_resolved': 35, 'validation_n': 11,
                    'discovery_expectancy_r': 0.2,
                    'validation_expectancy_r': 0.15,
                },
            ],
        }
        profile = build_shadow_profile(intelligence, governance={})
        self.assertEqual(profile['authority'], 'SHADOW_ONLY')
        self.assertFalse(profile['production_change'])
        self.assertFalse(profile['ready_for_canary'])
        self.assertGreaterEqual(len(profile['weights']), 2)

    def test_context_lookup_is_bounded(self):
        profile = {
            'version': 'test', 'authority': 'SHADOW_ONLY', 'production_change': False,
            'weights': [{
                'trader': 'Smart Money', 'market': 'FUTURES', 'timeframe': '15M',
                'direction': 'SHORT', 'regime': 'TREND_DOWN', 'relation': 'SUPPORT',
                'multiplier': 1.18, 'validation_n': 20,
            }],
        }
        install_shadow_profile(profile)
        self.assertAlmostEqual(
            get_shadow_multiplier('Smart Money', 'futures', '15m', 'SHORT', 'TRENDING_BEAR'),
            1.18,
        )
        self.assertEqual(
            get_shadow_multiplier('Smart Money', 'futures', '1h', 'SHORT', 'TRENDING_BEAR'),
            1.0,
        )

    def test_shadow_simulation_never_mutates_baseline(self):
        votes = [
            {'trader': 'A', 'accion': 'SHORT', 'confianza_ponderada': 70, 'multiplicador_experto_shadow': 1.2},
            {'trader': 'B', 'accion': 'LONG', 'confianza_ponderada': 80, 'multiplicador_experto_shadow': 0.8},
        ]
        result = simulate_shadow_decision(votes, 'SHORT')
        self.assertEqual(result['baseline_action'], 'SHORT')
        self.assertFalse(result['production_change'])
        self.assertEqual(result['authority'], 'SHADOW_ONLY')

    def test_app_production_weight_formula_does_not_include_shadow_multiplier(self):
        source = Path('app.py').read_text(encoding='utf-8')
        self.assertIn('peso_efectivo = trader.peso_base * regime_mult * review_mult', source)
        self.assertIn('peso_efectivo_shadow = peso_efectivo * expert_shadow_mult', source)


if __name__ == '__main__':
    unittest.main()
