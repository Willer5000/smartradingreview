import unittest
from pathlib import Path

from governed_self_calibration import build_self_calibration_state, install_self_calibration_state
from dynamic_expert_committee import get_governed_multiplier
from execution_challenger_lab import (
    summarize_execution_challenger_evidence,
    apply_governed_execution_calibration,
)


class Commit14GovernedSelfCalibrationTests(unittest.TestCase):
    def _governance_ready(self):
        return {
            'coverage': {'complete': True},
            'evidence': {'total': {'model_complete_net_coverage_pct': 100.0}},
            'stale': False,
        }

    def test_expert_positive_oos_can_become_active_but_is_bounded(self):
        dynamic = {
            'weights': [{
                'trader': 'Smart Money', 'market': 'FUTURES', 'timeframe': '15M',
                'direction': 'SHORT', 'regime': 'TREND_DOWN', 'relation': 'SUPPORT',
                'multiplier': 1.22, 'n_resolved': 60, 'validation_n': 18,
                'discovery_expectancy_r': 0.30, 'validation_expectancy_r': 0.25,
                'evidence': 'POSITIVE_OOS',
            }]
        }
        state = build_self_calibration_state({}, dynamic, {'rows': []}, self._governance_ready())
        install_self_calibration_state(state)
        mult, mode = get_governed_multiplier(
            'Smart Money', 'futures', '15m', 'SHORT', 'TRENDING_BEAR', 'SUPPORT'
        )
        self.assertEqual(mode, 'ACTIVE')
        self.assertGreater(mult, 1.0)
        self.assertLessEqual(mult, 1.20)
        self.assertFalse(state['policy']['safety_threshold_can_be_lowered'])
        self.assertFalse(state['policy']['leverage_growth_allowed_here'])

    def test_negative_oos_protects_even_before_positive_economics_ready(self):
        dynamic = {
            'weights': [{
                'trader': 'Multiframe', 'market': 'FUTURES', 'timeframe': '1H',
                'direction': 'LONG', 'regime': 'TRANSITION', 'relation': 'SUPPORT',
                'multiplier': 0.80, 'n_resolved': 40, 'validation_n': 12,
                'discovery_expectancy_r': -0.5, 'validation_expectancy_r': -0.8,
                'evidence': 'NEGATIVE_OOS',
            }]
        }
        state = build_self_calibration_state(
            {}, dynamic, {'rows': []},
            {'coverage': {'complete': True}, 'evidence': {'total': {'model_complete_net_coverage_pct': 10.0}}}
        )
        install_self_calibration_state(state)
        mult, mode = get_governed_multiplier(
            'Multiframe', 'futures', '1h', 'LONG', 'TRANSITION', 'SUPPORT'
        )
        self.assertEqual(mode, 'PROTECT')
        self.assertGreaterEqual(mult, 0.85)
        self.assertLess(mult, 1.0)

    def test_execution_summary_reads_nested_persisted_evidence_and_builds_oos_net_metrics(self):
        rows = []
        for i in range(60):
            evaluation = {
                'results': [
                    {'name': 'BASELINE', 'status': 'tp_hit', 'entry_reached': True, 'realized_r': 0.15, 'mfe_r': 0.4, 'mae_r': 0.2},
                    {'name': 'DEFENSIBILITY', 'status': 'tp_hit', 'entry_reached': True, 'realized_r': 0.50, 'mfe_r': 0.7, 'mae_r': 0.15},
                ]
            }
            rows.append({
                'id': str(i), 'system_type': 'futures', 'created_at': f'2026-09-{1 + (i // 3):02d}T00:00:00+00:00',
                'signal_results': {
                    'status': 'tp_hit', 'gross_r': 0.15, 'modeled_net_r': 0.10,
                    'execution_forensics': {'execution_challenger_results': evaluation},
                },
            })
        out = summarize_execution_challenger_evidence({'FUTURES_CURRENT': rows})
        challenger = next(r for r in out['rows'] if r['candidate'] == 'DEFENSIBILITY')
        self.assertEqual(challenger['resolved'], 60)
        self.assertEqual(challenger['validation_resolved'], 18)
        self.assertEqual(challenger['net_coverage_pct'], 100.0)
        self.assertGreater(challenger['validation_net_expectancy_r'], 0.1)
        self.assertEqual(challenger['evidence_state'], 'ACTIVE_READY')

    def test_execution_active_champion_can_change_geometry_but_not_direction_or_widen_stop(self):
        challenger_summary = {'rows': [{
            'market': 'FUTURES', 'candidate': 'DEFENSIBILITY', 'resolved': 60,
            'validation_resolved': 18, 'net_expectancy_r': 0.35,
            'validation_net_expectancy_r': 0.35, 'net_profit_factor': 2.0,
            'validation_net_improvement_vs_baseline_r': 0.20,
        }]}
        state = build_self_calibration_state({}, {'weights': []}, challenger_summary, self._governance_ready())
        install_self_calibration_state(state)
        analysis = {
            'system_type': 'futures', 'symbol': 'BTC-USDT', 'timeframe': '15m',
            'source_candle_timestamp': '2026-09-10T10:00:00+00:00',
            'decision': {'action': 'SHORT'},
            'levels': {'entry': 100.0, 'stop_loss': 105.0, 'take_profit': 90.0},
        }
        lab = {'candidates': [{
            'name': 'DEFENSIBILITY', 'geometry_valid': True, 'action': 'SHORT',
            'entry': 101.0, 'stop_loss': 105.5, 'take_profit': 91.0, 'risk_reward': 2.22,
        }]}
        audit = apply_governed_execution_calibration(analysis, lab)
        self.assertTrue(audit['applied'])
        self.assertEqual(analysis['decision']['action'], 'SHORT')
        self.assertEqual(analysis['levels']['entry'], 101.0)
        self.assertLessEqual(abs(101.0 - 105.5), abs(100.0 - 105.0) * 1.05)

    def test_groq_learning_router_bug_is_fixed_and_challenger_persistence_uses_existing_json(self):
        ai_source = Path('ai_advisor.py').read_text(encoding='utf-8')
        review_source = Path('review_trader.py').read_text(encoding='utf-8')
        self.assertIn('"GROQ_LEARNING"', ai_source)
        self.assertIn('selected_provider\n        in {"GROQ", "GROQ_LEARNING"}', ai_source)
        self.assertIn("result['execution_forensics']['execution_challenger_results']", review_source)

    def test_analytics_exposes_lightweight_top_traders_and_execution_tables(self):
        html = Path('templates/analytics.html').read_text(encoding='utf-8')
        js = Path('static/analytics.js').read_text(encoding='utf-8')
        self.assertIn('sc-top-traders', html)
        self.assertIn('sc-top-strategies', html)
        self.assertIn('sc-execution-candidates', html)
        self.assertIn('function renderSelfCalibrationV1(data)', js)
        analytics_source = Path('analytics_service.py').read_text(encoding='utf-8')
        self.assertNotIn('install_self_calibration_state', analytics_source)
        self.assertIn("promotion_governance.get('self_calibration_v1')", analytics_source)
        start = js.index('function renderSelfCalibrationV1(data)')
        end = js.index('function renderLearningObservatory(data)', start)
        self.assertNotIn('Plotly.newPlot', js[start:end])



if __name__ == '__main__':
    unittest.main()
