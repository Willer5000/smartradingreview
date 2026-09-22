import unittest
from datetime import datetime, timedelta

import pandas as pd

from execution_challenger_lab import (
    build_execution_challenger_lab,
    evaluate_execution_challengers,
    summarize_execution_challenger_evidence,
    install_governed_execution_profile,
    apply_governed_execution_calibration,
)
from governed_self_calibration import _build_execution_profile, MAX_RESOLVED_ROWS
from review_trader import ReviewTrader


class RC988EntryReachabilityLearningTests(unittest.TestCase):
    def _analysis(self, market='spot'):
        times = pd.date_range('2026-09-01', periods=30, freq='h', tz='UTC')
        df = pd.DataFrame({
            'time': times,
            'open': [100 + i * 0.08 for i in range(30)],
            'high': [101 + i * 0.08 for i in range(30)],
            'low': [99 + i * 0.08 for i in range(30)],
            'close': [100.3 + i * 0.08 for i in range(30)],
        })
        return {
            'symbol': 'PAXG-USDT',
            'timeframe': '4h',
            'system_type': market,
            'current_price': 105.0,
            'analysis_price': 105.0,
            'decision': {'action': 'COMPRA_SPOT' if market == 'spot' else 'LONG', 'registro_votacion': {}},
            'levels': {'entry': 100.0, 'stop_loss': 95.0, 'take_profit': 110.0},
            'strategy_lab': {},
        }, df

    def test_reachability_candidate_is_bounded_and_preserves_risk(self):
        analysis, df = self._analysis('spot')
        lab = build_execution_challenger_lab(analysis, df)
        self.assertLessEqual(len(lab['candidates']), 4)
        c = lab['reachability_candidate']
        self.assertEqual(c['name'], 'REACHABILITY_BALANCED')
        self.assertGreater(c['entry'], 100.0)
        self.assertLess(c['entry'], 105.0)
        self.assertEqual(c['stop_loss'], 95.0)
        self.assertLessEqual(abs(c['entry'] - c['stop_loss']), 5.0 * 1.05 + 1e-9)
        self.assertGreaterEqual(c['risk_reward'], 1.8)
        self.assertFalse(c['affects_production'])

    def test_no_entry_does_not_enter_win_rate(self):
        rows = []
        statuses = ['expired_no_entry'] * 12 + ['tp_hit', 'tp_hit', 'sl_hit']
        for i, status in enumerate(statuses):
            rows.append({
                'symbol': 'PAXG-USDT', 'timeframe': '4H', 'system_type': 'spot',
                'created_at': f'2026-09-{i+1:02d}T00:00:00+00:00',
                'signal_results': [{
                    'status': 'expired' if status.startswith('expired') else status,
                    'execution_forensics': {
                        'execution_challenger_results': {
                            'results': [{
                                'name': 'BASELINE', 'status': status,
                                'entry_reached': status != 'expired_no_entry',
                                'realized_r': 2.0 if status == 'tp_hit' else (-1.0 if status == 'sl_hit' else None),
                                'mfe_r': 0.0, 'mae_r': 0.0,
                            }]
                        }
                    },
                }],
            })
        summary = summarize_execution_challenger_evidence({'SPOT_CURRENT': rows})
        baseline = next(r for r in summary['rows'] if r['candidate'] == 'BASELINE')
        self.assertEqual(baseline['resolved'], 3)
        self.assertEqual(baseline['no_entry_count'], 12)
        self.assertAlmostEqual(baseline['win_rate_pct'], 66.67, places=2)
        self.assertFalse(summary['policy']['no_entry_counts_in_win_rate'])

    def test_entry_reach_improvement_is_measured_against_baseline(self):
        rows = []
        for i in range(10):
            base_entered = i < 2
            reach_entered = i < 7
            results = [
                {'name': 'BASELINE', 'status': 'tp_hit' if base_entered else 'expired_no_entry',
                 'entry_reached': base_entered, 'realized_r': 2.0 if base_entered else None,
                 'mfe_r': 1.0 if base_entered else 0.0, 'mae_r': 0.2 if base_entered else 0.0},
                {'name': 'REACHABILITY_BALANCED', 'status': 'tp_hit' if reach_entered else 'expired_no_entry',
                 'entry_reached': reach_entered, 'realized_r': 1.8 if reach_entered else None,
                 'mfe_r': 1.0 if reach_entered else 0.0, 'mae_r': 0.3 if reach_entered else 0.0},
            ]
            rows.append({
                'symbol': 'PAXG-USDT', 'timeframe': '4H', 'system_type': 'spot',
                'created_at': f'2026-08-{i+1:02d}T00:00:00+00:00',
                'signal_results': [{'status': 'expired', 'execution_forensics': {'execution_challenger_results': {'results': results}}}],
            })
        summary = summarize_execution_challenger_evidence({'SPOT_CURRENT': rows})
        reach = next(r for r in summary['rows'] if r['candidate'] == 'REACHABILITY_BALANCED')
        self.assertEqual(reach['baseline_entry_reached_pct'], 20.0)
        self.assertEqual(reach['entry_reached_pct'], 70.0)
        self.assertEqual(reach['entry_reach_improvement_pp'], 50.0)

    def test_eight_consecutive_losses_trigger_alpha_decay(self):
        rows = []
        for i in range(12):
            status = 'tp_hit' if i < 4 else 'sl_hit'
            rows.append({
                'symbol': 'BTC-USDT', 'timeframe': '1H', 'system_type': 'futures',
                'created_at': f'2026-09-{i+1:02d}T00:00:00+00:00',
                'signal_results': [{
                    'status': status,
                    'gross_r': 2.0 if status == 'tp_hit' else -1.0,
                    'modeled_net_r': 1.9 if status == 'tp_hit' else -1.1,
                    'execution_forensics': {'execution_challenger_results': {'results': [{
                        'name': 'REACHABILITY_BALANCED', 'status': status, 'entry_reached': True,
                        'realized_r': 2.0 if status == 'tp_hit' else -1.0, 'mfe_r': 1.0, 'mae_r': 0.5,
                    }]}}
                }]
            })
        summary = summarize_execution_challenger_evidence({'FUTURES_CURRENT': rows})
        row = summary['rows'][0]
        self.assertTrue(row['alpha_decay'])
        self.assertEqual(row['alpha_decay_reason'], 'EIGHT_CONSECUTIVE_LOSSES')
        self.assertEqual(row['consecutive_losses'], 8)

    def test_spot_governance_can_promote_reachability_without_counting_no_entry(self):
        summary = {'rows': [
            {
                'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'BASELINE',
                'resolved': 5, 'validation_resolved': 2, 'validation_expectancy_r': 0.05,
                'entry_reached_pct': 20.0,
            },
            {
                'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'REACHABILITY_BALANCED',
                'resolved': 30, 'validation_resolved': 10,
                'expectancy_r': 0.25, 'validation_expectancy_r': 0.20,
                'profit_factor': 1.6, 'validation_profit_factor': 1.4,
                'entry_reach_improvement_pp': 35.0, 'alpha_decay': False,
            },
        ]}
        governance = {'coverage': {'complete': True}, 'stale': False}
        profile = _build_execution_profile(summary, governance)
        selected = profile['selected']
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['candidate'], 'REACHABILITY_BALANCED')
        self.assertEqual(selected[0]['state'], 'CANARY')
        self.assertFalse(profile['policy']['no_entry_counts_in_win_rate'])

    def test_alpha_decay_prevents_promotion_even_if_historical_metrics_are_good(self):
        summary = {'rows': [
            {'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'BASELINE', 'resolved': 30,
             'validation_resolved': 10, 'validation_expectancy_r': 0.1, 'entry_reached_pct': 20.0},
            {'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'REACHABILITY_BALANCED',
             'resolved': 60, 'validation_resolved': 18, 'expectancy_r': 0.3, 'validation_expectancy_r': 0.2,
             'profit_factor': 1.8, 'validation_profit_factor': 1.4, 'entry_reach_improvement_pp': 40.0,
             'alpha_decay': True, 'alpha_decay_reason': 'EIGHT_CONSECUTIVE_LOSSES'},
        ]}
        profile = _build_execution_profile(summary, {'coverage': {'complete': True}, 'stale': False})
        self.assertEqual(profile['selected'], [])
        decayed = next(r for r in profile['rows'] if r['candidate'] == 'REACHABILITY_BALANCED')
        self.assertEqual(decayed['state'], 'OBSERVE')
        self.assertIn('ALPHA_DECAY', decayed['reason'])

    def test_spot_governed_calibration_changes_geometry_not_direction(self):
        analysis, df = self._analysis('spot')
        analysis['source_candle_timestamp'] = '2026-09-01T00:00:00+00:00'
        lab = build_execution_challenger_lab(analysis, df)
        reach = lab['reachability_candidate']
        install_governed_execution_profile({
            'selected': [{'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'REACHABILITY_BALANCED', 'state': 'ACTIVE'}],
            'canary_fraction': 0.25,
        })
        old_action = analysis['decision']['action']
        old_risk = abs(analysis['levels']['entry'] - analysis['levels']['stop_loss'])
        audit = apply_governed_execution_calibration(analysis, lab)
        self.assertTrue(audit['applied'])
        self.assertEqual(analysis['decision']['action'], old_action)
        self.assertLessEqual(abs(analysis['levels']['entry'] - analysis['levels']['stop_loss']), old_risk * 1.05)
        self.assertAlmostEqual(analysis['levels']['entry'], reach['entry'])

    def test_reviewtrader_marks_direction_right_no_entry_as_learning_only(self):
        trader = ReviewTrader()
        start = datetime(2026, 9, 1, 0, 0, 0)
        times = pd.date_range(start, periods=4, freq='4h', tz='UTC')
        df = pd.DataFrame({
            'time': times,
            'open': [105, 106, 107, 108],
            'high': [107, 108, 110, 112],
            'low': [104, 104.5, 105, 106],
            'close': [106, 107, 109, 111],
        })
        signal = {
            'id': 'x', 'symbol': 'PAXG-USDT', 'timeframe': '4h', 'system_type': 'spot',
            'action_normalized': 'LONG', 'entry_price': 100.0, 'stop_loss': 95.0,
            'take_profit': 110.0, 'current_price': 105.0,
        }
        pending = {'status': 'pending_no_entry', 'entry_touched': False, 'candles_to_result': 4,
                   'mfe_r': 0, 'mae_r': 0, 'mfe_pct': 0, 'mae_pct': 0}
        out = trader._build_execution_forensics_payload(signal, pending, df, start, start + timedelta(hours=16))
        reach = out['entry_reachability']
        self.assertFalse(reach['counts_as_trade'])
        self.assertFalse(out['win_rate_eligible'])
        self.assertEqual(reach['classification'], 'DIRECTION_RIGHT_ENTRY_TOO_DEEP')
        self.assertTrue(reach['eligible_for_entry_geometry_learning'])

    def test_reachability_is_evaluated_without_consuming_core_candidate_slot(self):
        analysis, df = self._analysis('spot')
        lab = build_execution_challenger_lab(analysis, df)
        self.assertLessEqual(len(lab['candidates']), 4)
        self.assertEqual(lab['reachability_candidate']['name'], 'REACHABILITY_BALANCED')
        signal = {
            'context': {'learning': {'execution_challenger_lab': lab}},
            'action_normalized': 'LONG',
        }
        start = pd.Timestamp('2026-09-02T00:00:00Z')
        eval_df = pd.DataFrame({
            'time': pd.date_range(start, periods=3, freq='h', tz='UTC'),
            'open': [105.0, 105.4, 105.8],
            'high': [106.0, 106.5, 107.0],
            # Baseline Entry=100 remains untouched; bounded challenger is 100.25.
            'low': [100.20, 100.40, 100.60],
            'close': [105.4, 105.8, 106.4],
        })
        out = evaluate_execution_challengers(signal, eval_df, start, start + pd.Timedelta(hours=4))
        rows = {row['name']: row for row in out['results']}
        self.assertFalse(rows['BASELINE']['entry_reached'])
        self.assertTrue(rows['REACHABILITY_BALANCED']['entry_reached'])

    def test_alpha_decay_detects_eight_trade_sharpe_collapse_without_eight_losses(self):
        rows = []
        # Strong prior edge, then eight alternating weak wins/losses. The last
        # eight are not eight consecutive losses, but their Sharpe proxy flips
        # below zero and must revoke authority.
        sequence = ([('tp_hit', 2.0)] * 8) + [
            ('tp_hit', 0.2), ('sl_hit', -1.0),
            ('tp_hit', 0.2), ('sl_hit', -1.0),
            ('tp_hit', 0.2), ('sl_hit', -1.0),
            ('tp_hit', 0.2), ('sl_hit', -1.0),
        ]
        for i, (status, realized) in enumerate(sequence):
            rows.append({
                'symbol': 'XRP-USDT', 'timeframe': '2H', 'system_type': 'futures',
                'created_at': f'2026-08-{i+1:02d}T00:00:00+00:00',
                'signal_results': [{
                    'status': status, 'gross_r': realized, 'modeled_net_r': realized,
                    'execution_forensics': {'execution_challenger_results': {'results': [{
                        'name': 'REACHABILITY_BALANCED', 'status': status, 'entry_reached': True,
                        'realized_r': realized, 'mfe_r': max(realized, 0), 'mae_r': 1.0 if realized < 0 else 0.2,
                    }]}}
                }]
            })
        summary = summarize_execution_challenger_evidence({'FUTURES_CURRENT': rows})
        row = next(r for r in summary['rows'] if r['candidate'] == 'REACHABILITY_BALANCED')
        self.assertTrue(row['alpha_decay'])
        self.assertEqual(row['alpha_decay_reason'], 'EIGHT_TRADE_SHARPE_DECAY')
        self.assertLess(row['recent8_sharpe_proxy'], 0)

    def test_spot_entry_learning_does_not_wait_for_global_research_completion(self):
        summary = {'rows': [
            {'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'BASELINE',
             'resolved': 5, 'validation_resolved': 2, 'validation_expectancy_r': 0.05, 'entry_reached_pct': 20.0},
            {'market': 'SPOT', 'symbol': 'PAXG-USDT', 'timeframe': '4H', 'candidate': 'REACHABILITY_BALANCED',
             'resolved': 30, 'validation_resolved': 10, 'expectancy_r': 0.25,
             'validation_expectancy_r': 0.20, 'profit_factor': 1.6,
             'validation_profit_factor': 1.4, 'entry_reach_improvement_pp': 35.0, 'alpha_decay': False},
        ]}
        governance = {'coverage': {'complete': False}, 'stale': False}
        profile = _build_execution_profile(summary, governance)
        self.assertEqual(profile['selected'][0]['candidate'], 'REACHABILITY_BALANCED')
        self.assertEqual(profile['selected'][0]['state'], 'CANARY')
        self.assertFalse(profile['policy']['global_research_completion_required_for_entry_geometry'])

    def test_supabase_learning_budget_is_slow_and_bounded(self):
        trader = ReviewTrader()
        self.assertGreaterEqual(trader._entry_learning_refresh_seconds, 12 * 60 * 60)
        self.assertLessEqual(MAX_RESOLVED_ROWS, 800)
        # This commit reuses the existing signal/results JSON rather than adding
        # a new persistence table for every visible signal/candle.
        source = open('governed_self_calibration.py', encoding='utf-8').read()
        self.assertIn('free_plan_allows("important")', source)
        self.assertNotIn('entry_reachability_observations', source)

    def test_frontend_directional_signal_is_persistable_without_user_save(self):
        trader = ReviewTrader()
        analysis = {'symbol': 'PAXG-USDT', 'timeframe': '4h', 'source_candle_timestamp': '2026-09-01T00:00:00Z',
                    'decision': {'action': 'COMPRA_SPOT', 'confidence': 70}}
        self.assertTrue(trader.should_save_signal(analysis))


    def test_entry_learning_keeps_long_and_short_separate(self):
        rows = []
        for i, (action, entered) in enumerate([('LONG', True), ('SHORT', False)]):
            status = 'tp_hit' if entered else 'expired_no_entry'
            rows.append({
                'symbol': 'BTC-USDT', 'timeframe': '1H', 'system_type': 'futures',
                'action_normalized': action,
                'created_at': f'2026-09-0{i+1}T00:00:00+00:00',
                'signal_results': [{
                    'status': 'tp_hit' if entered else 'expired',
                    'execution_forensics': {'execution_challenger_results': {'results': [{
                        'name': 'BASELINE', 'status': status, 'entry_reached': entered,
                        'realized_r': 2.0 if entered else None, 'mfe_r': 1.0 if entered else 0.0, 'mae_r': 0.2 if entered else 0.0,
                    }]}}
                }],
            })
        summary = summarize_execution_challenger_evidence({'FUTURES_CURRENT': rows})
        actions = {row['action'] for row in summary['rows']}
        self.assertEqual(actions, {'LONG', 'SHORT'})
        self.assertEqual(summary['policy']['symbol_timeframe_action_specific'], True)


    def test_current_rc98_learning_metadata_is_preserved(self):
        source = open('review_trader.py', encoding='utf-8').read()
        self.assertIn('operational_source_v1', source)
        self.assertIn("context['market_regime']", source)
        self.assertIn("'entry_timing_mode'", source)
        self.assertIn("'entry_independent_confluence_families'", source)
        self.assertIn('RC9_7_OPPORTUNITY_CAPTURE_V2', source)


if __name__ == '__main__':
    unittest.main()
