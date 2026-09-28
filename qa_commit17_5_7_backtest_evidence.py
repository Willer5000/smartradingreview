from __future__ import annotations

import ast
import hashlib
import pathlib
import py_compile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
APP_PATH = ROOT / 'app.py'
COMMITTEE_PATH = ROOT / 'execution_specialist_committees.py'
APP = APP_PATH.read_text(encoding='utf-8')
COMMITTEE = COMMITTEE_PATH.read_text(encoding='utf-8')
BASE_1756_COMMITTEE_SHA256 = '220672216e24d938958863eb0bfd4b801738cc58f96c71838dc45cad5ba795e5'


def _load_policy_namespace():
    tree = ast.parse(APP)
    names = {
        '_BACKTEST_EVIDENCE_POLICY_VERSION',
        '_DERIVATIVE_PREMIUM_MIN_LEVERAGE',
        '_derivative_premium_leverage_ok',
        '_entry_evidence_class',
        '_apply_17_5_7_backtest_evidence_policy',
    }
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target_names = set()
            targets = getattr(node, 'targets', []) or []
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    target_names.add(t.id)
            if target_names & names:
                selected.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            selected.append(node)
    ns = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APP_PATH), 'exec'), ns)
    return ns


POLICY = _load_policy_namespace()
apply_policy = POLICY['_apply_17_5_7_backtest_evidence_policy']
entry_class = POLICY['_entry_evidence_class']
lev_ok = POLICY['_derivative_premium_leverage_ok']


def sample(leverage=8, market='futures', **level_updates):
    levels = {
        'entry': 100.0,
        'stop_loss': 98.0,
        'take_profit': 104.0,
        'risk_reward': 2.0,
        'leverage': leverage,
        'publication_status': 'EXECUTABLE_SIGNAL',
        'is_executable': True,
        'is_rejected': False,
        'entry_source': 'Order Block',
        'entry_independent_confluence_families': 2,
        'entry_sweep_confirmed': True,
        'entry_mss_bos_confirmed': True,
        'entry_displacement_confirmed': True,
        'entry_liquidity_pool_near': True,
    }
    levels.update(level_updates)
    return {
        'success': True,
        'is_multiasset': market == 'multiasset',
        'decision': {'action': 'LONG', 'confidence': 80},
        'levels': levels,
        'futures_publication_gate': {'eligible': True, 'tier': 'PREMIUM', 'reasons': [], 'reason_codes': []},
    }


class Commit1757QA(unittest.TestCase):
    def test_01_files_compile(self):
        py_compile.compile(str(APP_PATH), doraise=True)
        py_compile.compile(str(COMMITTEE_PATH), doraise=True)

    def test_02_committee_is_exact_1756_execution_engine(self):
        sha = hashlib.sha256(COMMITTEE_PATH.read_bytes()).hexdigest()
        self.assertEqual(sha, BASE_1756_COMMITTEE_SHA256)
        self.assertIn('SL_INSIDE_STRONG_REACTION_ZONE', COMMITTEE)

    def test_03_spot_is_untouched(self):
        raw = sample(2, market='spot')
        out = apply_policy(raw, 'spot')
        self.assertIs(out, raw)
        self.assertEqual(out['levels']['leverage'], 2)
        self.assertEqual(out['levels']['publication_status'], 'EXECUTABLE_SIGNAL')

    def test_04_x2_futures_becomes_analysis_only_without_inflation(self):
        raw = sample(2)
        out = apply_policy(raw, 'futures')
        self.assertEqual(out['levels']['leverage'], 2)
        self.assertEqual(out['levels']['entry'], 100.0)
        self.assertEqual(out['levels']['stop_loss'], 98.0)
        self.assertEqual(out['levels']['take_profit'], 104.0)
        self.assertFalse(out['levels']['is_executable'])
        self.assertEqual(out['levels']['publication_status'], 'ANALYSIS_ONLY')
        self.assertIn('LOW_LEVERAGE_PRODUCT_FIT', out['futures_publication_gate']['reason_codes'])
        self.assertTrue(out['futures_publication_gate']['leverage_was_not_increased'])

    def test_05_x3_multiasset_becomes_analysis_only(self):
        out = apply_policy(sample(3, market='multiasset'), 'multiasset')
        self.assertEqual(out['levels']['leverage'], 3)
        self.assertEqual(out['levels']['publication_status'], 'ANALYSIS_ONLY')
        self.assertFalse(out['publication_eligible'])

    def test_06_x4_plus_is_not_downgraded(self):
        for lev in (4, 8, 15, 31):
            with self.subTest(lev=lev):
                out = apply_policy(sample(lev), 'futures')
                self.assertEqual(out['levels']['leverage'], lev)
                self.assertEqual(out['levels']['publication_status'], 'EXECUTABLE_SIGNAL')
                self.assertTrue(out['levels']['leverage_product_fit'])

    def test_07_entry_evidence_class_full_sequence(self):
        levels = sample(8)['levels']
        self.assertEqual(entry_class(levels), 'LIQUIDITY_SWEEP_STRUCTURE_POI')

    def test_08_entry_evidence_class_is_diagnostic_not_veto(self):
        levels = {
            'entry_source': 'fallback',
            'entry_independent_confluence_families': 1,
            'entry_sweep_confirmed': False,
            'entry_mss_bos_confirmed': False,
            'entry_displacement_confirmed': False,
            'entry_liquidity_pool_near': False,
        }
        self.assertEqual(entry_class(levels), 'BASIC_TECHNICAL_EVIDENCE')
        raw = sample(8, **levels)
        out = apply_policy(raw, 'futures')
        self.assertEqual(out['levels']['publication_status'], 'EXECUTABLE_SIGNAL')
        self.assertEqual(out['levels']['entry_evidence_probability_status'], 'DIAGNOSTIC_NOT_CALIBRATED')

    def test_09_product_floor_is_exactly_four_not_a_leverage_rewrite(self):
        self.assertFalse(lev_ok(1))
        self.assertFalse(lev_ok(2))
        self.assertFalse(lev_ok(3))
        self.assertTrue(lev_ok(4))
        self.assertIn("_DERIVATIVE_PREMIUM_MIN_LEVERAGE = 4", APP)
        self.assertNotIn("levels['leverage'] = 4", APP)

    def test_10_policy_is_wired_after_final_futures_risk_layer(self):
        self.assertIn("result = _apply_17_5_7_backtest_evidence_policy(result, 'futures')", APP)
        self.assertIn("r = _apply_17_5_7_backtest_evidence_policy(r, 'futures')", APP)
        self.assertGreaterEqual(APP.count("_apply_17_5_7_backtest_evidence_policy"), 7)

    def test_11_multiasset_policy_runs_before_cache_and_telegram(self):
        fragment = "result=_apply_17_5_7_backtest_evidence_policy(result,'multiasset')\n            if result.get('success') is not False:\n                _multiasset_cache_result"
        self.assertIn(fragment, APP)
        self.assertIn("signal = _apply_17_5_7_backtest_evidence_policy(signal, market)", APP)

    def test_12_no_signal_quantity_quota_added(self):
        forbidden = ('MAX_TELEGRAM_SIGNALS_PER_DAY', 'TELEGRAM_DAILY_SIGNAL_CAP', 'SIGNAL_DAILY_QUOTA_17_5_7')
        for token in forbidden:
            self.assertNotIn(token, APP)

    def test_13_1756_sl_semantic_guard_is_preserved(self):
        self.assertIn('def evaluate_sl_reaction_conflict', COMMITTEE)
        self.assertIn("if is_futures and sl_reaction_guard.get('conflict')", APP)

    def test_14_policy_does_not_change_core_entry_sl_tp_thresholds(self):
        # 17.5.4/17.5.6 invariants remain visible in the execution refiner.
        for token in ('geometry_improvement', 'entry_quality', 'sl_quality', 'tp_quality'):
            self.assertIn(token, APP)
        self.assertNotIn('BACKTEST_TUNED_ENTRY_THRESHOLD', APP)
        self.assertNotIn('BACKTEST_TUNED_SL_THRESHOLD', APP)
        self.assertNotIn('BACKTEST_TUNED_TP_THRESHOLD', APP)


if __name__ == '__main__':
    unittest.main(verbosity=2)
