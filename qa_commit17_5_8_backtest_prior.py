from __future__ import annotations

import ast
import pathlib
import py_compile
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
APP_PATH = ROOT / 'app.py'
COMMITTEE_PATH = ROOT / 'execution_specialist_committees.py'
PRIOR_PATH = ROOT / 'preliminary_backtest_prior.py'
APP = APP_PATH.read_text(encoding='utf-8')
COMMITTEE = COMMITTEE_PATH.read_text(encoding='utf-8')

sys.path.insert(0, str(ROOT))
import preliminary_backtest_prior as prior
import execution_specialist_committees as committees


def load_1758_wrapper():
    tree = ast.parse(APP)
    wanted = {'_BACKTEST_LEARNING_PRIOR_VERSION', '_apply_17_5_8_preliminary_learning_prior'}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & wanted:
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
    ns = {'_apply_17_5_7_backtest_evidence_policy': lambda r, market='futures': dict(r or {})}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), 'exec'), ns)
    return ns['_apply_17_5_8_preliminary_learning_prior']


apply_1758 = load_1758_wrapper()


class Commit1758QA(unittest.TestCase):
    def test_01_files_compile(self):
        for path in (APP_PATH, COMMITTEE_PATH, PRIOR_PATH):
            py_compile.compile(str(path), doraise=True)

    def test_02_prior_version(self):
        self.assertEqual(prior.VERSION, 'COMMIT17_5_8_PRELIMINARY_BACKTEST_PRIOR_V1')
        self.assertEqual(committees.VERSION, 'COMMIT17_5_8_BACKTEST_PRIOR_V1')

    def test_03_exact_family_cell_has_bounded_positive_prior(self):
        row = prior.family_cell_prior(
            market='futures', symbol='SOL-USDT', timeframe='2h',
            action='LONG', family='RSI_TREND'
        )
        self.assertTrue(row['available'])
        self.assertGreater(row['adjustment'], 0)
        self.assertLessEqual(row['adjustment'], 4.0)

    def test_04_unknown_family_cell_is_neutral(self):
        row = prior.family_cell_prior(
            market='futures', symbol='BTC-USDT', timeframe='30m',
            action='SHORT', family='NO_SUCH_FAMILY'
        )
        self.assertFalse(row['available'])
        self.assertEqual(row['adjustment'], 0.0)
        self.assertEqual(row['score'], 50.0)

    def test_05_entry_prior_is_quality_route_not_global_relaxation(self):
        strong = prior.entry_component_prior(timeframe='30m', candidate_family='smc_poi', smc_events=2)
        weak = prior.entry_component_prior(timeframe='30m', candidate_family='baseline', smc_events=2)
        self.assertGreater(strong['adjustment'], 0)
        self.assertEqual(weak['adjustment'], 0)
        self.assertLessEqual(strong['adjustment'], 4.0)

    def test_06_sl_prior_neutral_unless_semantic_conflict(self):
        normal = prior.sl_component_prior(timeframe='1h', reaction_conflict=False)
        conflict = prior.sl_component_prior(timeframe='1h', reaction_conflict=True)
        self.assertEqual(normal['adjustment'], 0.0)
        self.assertEqual(conflict['score'], 0.0)
        self.assertEqual(conflict['authority'], 'SEMANTIC_HARD_GUARD')

    def test_07_tp_prior_does_not_authorize_global_compression(self):
        row_30 = prior.tp_component_prior(timeframe='30m', candidate_rr=2.4)
        row_1h = prior.tp_component_prior(timeframe='1h', candidate_rr=2.4)
        self.assertGreaterEqual(row_30['adjustment'], 0)
        self.assertEqual(row_1h['adjustment'], 0.0)
        bundle = prior.get_preliminary_learning_bundle(timeframe='1h')
        self.assertFalse(bundle['governance']['tp_global_compression_authorized'])
        self.assertFalse(bundle['governance']['sl_global_shift_authorized'])

    def test_08_wrapper_stamps_prior_without_changing_geometry(self):
        original = {
            'symbol': 'SOL-USDT', 'timeframe': '2h',
            'decision': {'action': 'LONG'},
            'levels': {'entry': 100.0, 'stop_loss': 98.0, 'take_profit': 104.0,
                       'leverage': 12, 'strategy_family': 'RSI_TREND'}
        }
        out = apply_1758(original, 'futures')
        self.assertEqual(out['levels']['entry'], 100.0)
        self.assertEqual(out['levels']['stop_loss'], 98.0)
        self.assertEqual(out['levels']['take_profit'], 104.0)
        self.assertEqual(out['levels']['leverage'], 12)
        self.assertIn('preliminary_backtest_prior', out['levels'])
        self.assertGreater(out['levels']['preliminary_family_prior_adjustment'], 0)

    def test_09_committee_backtest_weight_is_bounded(self):
        self.assertIn('"backtest_prior":0.35', COMMITTEE)
        self.assertIn('"backtest_prior":0.15', COMMITTEE)
        self.assertIn('"backtest_prior":0.20', COMMITTEE)
        self.assertNotIn('"backtest_prior":1.0', COMMITTEE)

    def test_10_no_core_quality_thresholds_were_lowered(self):
        for literal in ('values[4] >= 1.50', 'values[3] >= 62.0',
                        'values[5] >= 55.0', 'values[6] >= 60.0', 'values[7] >= 60.0'):
            self.assertIn(literal, APP)

    def test_11_futures_quality_first_scan_preserves_round_robin(self):
        self.assertIn('futures_scan_priority', APP)
        self.assertIn('_FUTURES_INCREMENTAL_CURSOR', APP)
        self.assertIn('_futures_combo_due_for_closed_candle', APP)
        self.assertGreater(prior.futures_scan_priority('SOL-USDT', '2h'), 0)
        self.assertEqual(prior.futures_scan_priority('NOPE-USDT', '2h'), 0)

    def test_12_multiasset_1h_uses_own_router_and_active_lane(self):
        self.assertIn("rows_1h=_multiasset_scan('1h',force=force)", APP)
        self.assertIn("@app.route('/api/multiasset/signals/active'", APP)
        active = APP.split("@app.route('/api/multiasset/signals/active'",1)[1].split("@app.route",1)[0]
        self.assertIn("'signals':signals", active.replace(' ', ''))

    def test_13_signal_funnel_and_prior_endpoint_are_cache_only(self):
        self.assertIn("@app.route('/api/diagnostics/signal-funnel'", APP)
        self.assertIn("@app.route('/api/diagnostics/backtest-prior'", APP)
        prior_ep = APP.split("@app.route('/api/diagnostics/backtest-prior'",1)[1].split("@app.route",1)[0]
        self.assertIn("'cache_only':True", prior_ep.replace(' ', ''))
        self.assertIn('_require_auth()', prior_ep)

    def test_14_no_telegram_quantity_cap_added(self):
        forbidden = ('MAX_TELEGRAM_SIGNALS', 'TELEGRAM_DAILY_SIGNAL_CAP', 'TELEGRAM_SIGNAL_LIMIT_1758')
        for token in forbidden:
            self.assertNotIn(token, APP)

    def test_15_sl_reaction_hard_guard_still_present(self):
        self.assertIn('SL_INSIDE_STRONG_REACTION_ZONE', COMMITTEE)
        self.assertIn('evaluate_sl_reaction_conflict', APP)

    def test_16_prior_cannot_create_direction_or_raise_leverage(self):
        bundle = prior.get_preliminary_learning_bundle(
            market='futures', symbol='SOL-USDT', timeframe='2h',
            action='LONG', family='RSI_TREND'
        )
        g = bundle['governance']
        self.assertFalse(g['can_create_direction'])
        self.assertFalse(g['can_bypass_safety'])
        self.assertFalse(g['can_bypass_publication'])
        self.assertFalse(g['can_raise_leverage'])

    def test_17_learning_scientist_receives_preliminary_prior(self):
        self.assertIn("'preliminary_backtest_prior_v1'", APP)
        self.assertIn('strong_family_cells', APP)
        self.assertIn('ENTRY_ROUTE_EVIDENCE', APP)
        self.assertIn('SL_FORENSIC_EVIDENCE', APP)
        self.assertIn('TP_SWEEP_EVIDENCE', APP)


if __name__ == '__main__':
    unittest.main(verbosity=2)
