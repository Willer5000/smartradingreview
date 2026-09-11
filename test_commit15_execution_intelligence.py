import ast
import unittest
from pathlib import Path

from execution_intelligence_v2 import (
    build_uncertainty_shadow_gate,
    attach_microstructure_entry_challenger,
)
from execution_learning import build_execution_forensics

ROOT = Path(__file__).resolve().parent


def literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f'{name} not found in {path}')


class Commit15ExecutionIntelligenceTests(unittest.TestCase):
    def _analysis(self):
        return {
            'decision': {
                'action': 'SHORT',
                'confidence': 90,
                'registro_votacion': {
                    'todos_los_votos': [
                        {'accion': 'SHORT', 'confianza': 90, 'peso': 1.0}
                        for _ in range(8)
                    ] + [
                        {'accion': 'NO_OPERAR', 'confianza': 60, 'peso': 1.0}
                    ]
                },
            },
            'levels': {
                'entry': 100.0,
                'stop_loss': 105.0,
                'take_profit': 90.0,
                'entry_defensibility_score': 85,
                'entry_reachability_score': 80,
                'tp_quality_score': 75,
                'execution_safety': 80,
                'sl_reliability': 0.90,
            },
            'market_regime': {'confidence': 85},
            'execution_challenger_lab': {
                'authority': 'SHADOW_ONLY',
                'production_change': False,
                'version': 'C13_EXECUTION_CHALLENGER_LAB_V1',
                'policy': {'max_candidates_per_signal': 4},
                'candidates': [{
                    'name': 'BASELINE',
                    'geometry_valid': True,
                    'action': 'SHORT',
                    'entry': 100.0,
                    'stop_loss': 105.0,
                    'take_profit': 90.0,
                    'risk_reward': 2.0,
                    'affects_production': False,
                }],
            },
        }

    def test_uncertainty_is_low_when_committee_execution_and_microstructure_agree(self):
        analysis = self._analysis()
        micro = {
            'available': True,
            'alignment': 'ALIGNED',
            'alignment_score': 85.0,
            'metrics': {'source_count': 4},
        }
        out = build_uncertainty_shadow_gate(analysis, micro)
        self.assertEqual(out['authority'], 'SHADOW_ONLY')
        self.assertFalse(out['production_change'])
        self.assertEqual(out['conformal_status'], 'NOT_CALIBRATED_WAITING_OOS')
        self.assertEqual(out['uncertainty_bucket'], 'LOW')
        self.assertFalse(out['affects_entry'])
        self.assertFalse(out['affects_safety'])
        self.assertFalse(out['affects_publication'])
        self.assertFalse(out['affects_leverage'])

    def test_uncertainty_becomes_high_for_disagreement_and_missing_microstructure(self):
        analysis = {
            'decision': {
                'action': 'LONG', 'confidence': 40,
                'registro_votacion': {'todos_los_votos': [
                    {'accion': 'LONG', 'confianza': 60, 'peso': 1.0},
                    {'accion': 'SHORT', 'confianza': 60, 'peso': 1.0},
                    {'accion': 'NO_OPERAR', 'confianza': 60, 'peso': 1.0},
                ]},
            },
            'levels': {},
            'market_regime': {'confidence': 30},
        }
        out = build_uncertainty_shadow_gate(analysis, {})
        self.assertEqual(out['uncertainty_bucket'], 'HIGH')
        self.assertEqual(out['shadow_gate'], 'ABSTAIN_CANDIDATE')
        self.assertGreaterEqual(out['uncertainty_score'], 70)

    def test_microstructure_entry_challenger_preserves_production_geometry(self):
        analysis = self._analysis()
        before = dict(analysis['levels'])
        out = attach_microstructure_entry_challenger(
            analysis,
            {'available': True, 'alignment': 'ALIGNED', 'alignment_score': 78.0},
        )
        self.assertEqual(out['levels'], before)
        candidates = out['execution_challenger_lab']['candidates']
        candidate = next(c for c in candidates if c['name'] == 'MICROSTRUCTURE_CONFIRMED_ENTRY')
        self.assertTrue(candidate['condition_met_at_signal'])
        self.assertEqual(candidate['entry'], before['entry'])
        self.assertEqual(candidate['stop_loss'], before['stop_loss'])
        self.assertEqual(candidate['take_profit'], before['take_profit'])
        self.assertFalse(candidate['affects_production'])
        self.assertLessEqual(len(candidates), 5)

    def test_wick_out_is_diagnostic_and_sl_stays_a_loss(self):
        signal = {
            'action_normalized': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 110.0,
        }
        result = {
            'status': 'sl_hit',
            'mfe_r': 0.30,
            'mae_r': 1.0,
        }
        out = build_execution_forensics(
            signal,
            result,
            entry_touched=True,
            post_stop_recovery={
                'reclaimed_entry': True,
                'best_favorable_r_after_stop': 1.2,
                'tp_reached_after_stop': True,
            },
        )
        self.assertEqual(out['status'], 'sl_hit')
        self.assertTrue(out['wick_out'])
        self.assertTrue(out['false_invalidation_to_target'])
        self.assertEqual(out['wick_classification'], 'FALSE_INVALIDATION_TO_TARGET')

    def test_link_and_bnb_are_separate_research_universe(self):
        futures_path = ROOT / 'futures_system.py'
        production = literal_assignment(futures_path, 'FUTURES_SYMBOLS')
        research = literal_assignment(futures_path, 'FUTURES_RESEARCH_SYMBOLS')
        contracts = literal_assignment(futures_path, 'FUTURES_CONTRACT_SYMBOLS')
        self.assertNotIn('LINK-USDT', production)
        self.assertNotIn('BNB-USDT', production)
        self.assertIn('LINK-USDT', research)
        self.assertIn('BNB-USDT', research)
        self.assertEqual(contracts['LINK-USDT'], 'LINKUSDTM')
        self.assertEqual(contracts['BNB-USDT'], 'BNBUSDTM')
        source = futures_path.read_text(encoding='utf-8')
        self.assertIn("FUTURES_RESEARCH_TIMEFRAMES = ('15m', '30m', '1h')", source)
        self.assertIn("result['publication_status'] = 'RESEARCH_ONLY_SHADOW'", source)
        self.assertIn("result['publication_eligible'] = False", source)

    def test_order_flow_graph_is_futures_only_and_client_side(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        js = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        workspace = (ROOT / 'static' / 'chart_workspace.js').read_text(encoding='utf-8')
        self.assertIn('COMMIT 15B — ORDER BOOK / ORDER FLOW MICROSTRUCTURE', html)
        self.assertIn('id="order-flow-chart"', html)
        self.assertIn('{% if is_futures %}', html)
        self.assertIn('/api/futures/microstructure?symbol=', js)
        self.assertIn("type: 'bar', orientation: 'h', name: 'BID'", js)
        self.assertIn("type: 'bar', orientation: 'h', name: 'ASK'", js)
        self.assertIn("'order-flow': updateOrderFlowChart", js)
        self.assertIn("'order-flow': { label: 'Order Book / Order Flow'", workspace)
        # Rendering happens in the browser with the already loaded Plotly.
        self.assertNotIn('matplotlib', js.lower())

    def test_microstructure_api_and_memory_caps_are_compact(self):
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        futures_source = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
        self.assertIn("@app.route('/api/futures/microstructure', methods=['GET'])", app_source)
        self.assertIn("'bid_profile': list(orderbook.get('bid_profile') or [])[:10]", app_source)
        self.assertIn("'ask_profile': list(orderbook.get('ask_profile') or [])[:10]", app_source)
        self.assertIn("'trade_count': trades.get('sample_size')", app_source)
        self.assertIn("('BID', bids[:10], bid_size, bid_profile)", futures_source)
        self.assertIn("('ASK', asks[:10], ask_size, ask_profile)", futures_source)
        self.assertIn("FUTURES_MICROSTRUCTURE_TTL_SECONDS", futures_source)

    def test_analytics_and_sql_keep_commit15_research_only(self):
        html = (ROOT / 'templates' / 'analytics.html').read_text(encoding='utf-8')
        js = (ROOT / 'static' / 'analytics.js').read_text(encoding='utf-8')
        sql = (ROOT / 'schema_commit15_execution_intelligence.sql').read_text(encoding='utf-8')
        self.assertIn('Execution Intelligence V2 · Observación', html)
        self.assertIn('El filtro de incertidumbre permanece sin calibrar', html)
        self.assertIn('renderExecutionIntelligenceV2(data)', js)
        self.assertIn("'{learning,uncertainty_shadow}'", sql)
        self.assertIn("'{learning,research_only_universe}'", sql)
        self.assertNotIn('DELETE FROM public.signals', sql)
        self.assertNotIn('DELETE FROM public.signal_results', sql)
        review = (ROOT / 'review_trader.py').read_text(encoding='utf-8')
        self.assertIn("context['learning']['uncertainty_shadow']", review)
        self.assertIn("context['learning']['research_only_universe']", review)


if __name__ == '__main__':
    unittest.main()
