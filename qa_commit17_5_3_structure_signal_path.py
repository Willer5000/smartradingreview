"""17.5.3: deterministic runtime signal-path QA; no network or app startup.

Run beside the complete 17.5.2 project after replacing app.py:
    python qa_commit17_5_3_structure_signal_path.py
Requires numpy/pandas (already application dependencies). This is NOT a PnL backtest.
Real production method bodies are loaded by AST to avoid Flask/background jobs.
No Structure direction, detector result or scoring logic is substituted in fixtures.
"""
import ast
import contextlib
import hashlib
import io
from pathlib import Path
import sys
import unittest
import warnings

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import operational_intelligence as oi

APP = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(APP)
METHOD = 'analyze_price_structure_layer'
FIELDS = {'direction', 'structure_direction', 'structure_score', 'structure_reasons'}

# SHA256 of normalized text at d0a8470; populated from the verified base.
BASE_PROTECTED = {'default_strategy_bank.py': 'efcc923ae0ede143ef936c79f6f0c1e68e95ab53f7635e5fc97d3f248ce75ee1', 'execution_geometry_committee.py': '9ab082b29bbea2606649187e02835cf01310bb775d1f57f46f5db43f855d8b6f', 'execution_specialist_committees.py': '6ceed9bfc933413fcbe4f4c5eb9d74a108c2cde32e809c6fe4695477506ecf4f', 'futures_system.py': '5dd050b00cec16e311e21cd7f786281b69c60d4c7003a2e5ec040fd1e7332eca', 'futures_universe.py': 'cb89f326f049a139f72fa1b4469b79dab8fe2ee5bdcaaa30697ac7617d4da8f8', 'leverage_policy.py': 'c13bb6bab647c5984bb56e861b4c00cec3fabde2d2c94f0de5684e062a64cb81', 'multiasset_system.py': '1a38c5e2fd756a946eed49f8473ca2d48a1f7776c5056a7db4ae1f7a73d2f370', 'operational_intelligence.py': '3ab1bfd66d7c3e0a4bae2d1fea253d1745dfb6b5938b445c861762e606657930', 'portfolio_guardian.py': '7e55045ec8de752ce190753ab39da4670cb31e8b990581227febd37b8c4b4a69', 'q6_integrity.py': '45c41ace61a9c87fc6429507275b8b6ef26b6266ba3db7178503b5fa992ce998', 'saved_signals.py': 'a101d908ae452e8df0d514ab82820b36a049d7a628518d2f395601a9254f3928', 'templates/login.html': 'd5bb5b3e79a0e3599a673a9b09d9ad7e1cbbd73b28f71e409a65809d55421fb4', 'test_commit14_liquidation_heatmap.py': '066dd9178c54b45745318d80544f4438c54676470fa6dbfac41e958938bc7b4e'}
BASE_APP_OUTSIDE_METHOD = 'b4967a1eb3654d1f9864bade28c85d9c22cdc2fa417e80d9190cad452bf2c54b'


def outside_method(source):
    tree = ast.parse(source)
    node, = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == METHOD]
    lines = source.splitlines(keepends=True)
    return ''.join(lines[:node.lineno - 1] + lines[node.end_lineno:])


def runtime_analyzer():
    names = {METHOD, 'calculate_support_resistance_channels', 'detect_candle_patterns',
             '_initialize_pattern_database', 'analyze_volume_profile'}
    owner, = [n for n in ast.walk(TREE) if isinstance(n, ast.ClassDef)
              and any(isinstance(m, ast.FunctionDef) and m.name == METHOD for m in n.body)]
    available = {n.name: n for n in owner.body if isinstance(n, ast.FunctionDef)}
    while True:
        dependencies = {n.attr for name in names for n in ast.walk(available[name])
                        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                        and n.value.id == 'self' and n.attr in available}
        if dependencies <= names:
            break
        names |= dependencies
    nodes = [available[name] for name in sorted(names)]
    assert len(nodes) == len(names), 'Production methods must be unique'
    cls = ast.ClassDef(name='RuntimeSlice', bases=[], keywords=[], body=nodes, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    namespace = {'np': np, 'pd': pd}
    exec(compile(module, str(ROOT / 'app.py'), 'exec'), namespace)
    analyzer = namespace['RuntimeSlice']()
    analyzer.pattern_database = analyzer._initialize_pattern_database()
    return analyzer


def frame(n=80):
    return pd.DataFrame({'time': pd.date_range('2026-01-01', periods=n, freq='h'),
                         'open': np.full(n, 100.), 'high': np.full(n, 101.),
                         'low': np.full(n, 99.), 'close': np.full(n, 100.),
                         'volume': np.full(n, 100.)})


def candle(df, i, o, h, l, c, v=100.):
    df.loc[df.index[i], ['open', 'high', 'low', 'close', 'volume']] = [o, h, l, c, v]
    return df


def mirror(df):
    out = df.copy()
    out['open'], out['close'] = 200. - df['open'], 200. - df['close']
    out['high'], out['low'] = 200. - df['low'], 200. - df['high']
    return out


def event_frame(kind='sweep'):
    df = frame()
    if kind == 'sweep':
        return candle(df, -1, 99.5, 100.8, 97., 100.2)
    if kind == 'hunt':
        return candle(df, -1, 99.5, 101., 98.3, 100.2)
    if kind == 'bos':
        # Distinct swing at bar 65, confirmed at 70, broken by close at 79.
        candle(df, 65, 100., 102., 99., 100.)
        return candle(df, -1, 100., 102.5, 99.5, 102.2)
    raise ValueError(kind)


def broad_frame():
    df = frame(96)
    center = 100. + .002 * np.arange(96) + .1 * np.sin(np.arange(96) * np.pi / 8.)
    df['open'] = df['close'] = center
    df['high'], df['low'] = center + 1., center - 1.
    return df


def layers(structure, side='BULLISH'):
    bull = side == 'BULLISH'
    return {
        'trend': {'direction': side, 'adx': 35, 'plus_di': 35 if bull else 10, 'minus_di': 10 if bull else 35},
        'momentum': {'direction': side, 'rsi': 60 if bull else 40, 'macd_histogram': 1 if bull else -1},
        'volume': {'volume_ratio': 1.4, 'obv_trend': side},
        'structure': structure, 'macro_context': {'risk_level': 'NORMAL'}, 'liquidation': {},
        'volatility': {'atr': 2., 'atr_pct': 2., 'bb_width': 3.},
        'market_regime': {'regime': 'TRENDING_BULL' if bull else 'TRENDING_BEAR'},
    }


def mtf(side='BULLISH'):
    return {'dominant_direction': side, 'alignment': 'ALIGNED', 'conflict': False,
            'complete': True, 'public_summary': 'QA aligned closed frames'}


class StructureRuntimeQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = runtime_analyzer()

    def run_structure(self, df):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            result = self.analyzer.analyze_price_structure_layer(df, '1h', 'SUI-USDT')
        self.assertNotIn('analysis_error', result)
        self.assertTrue(FIELDS <= result.keys())
        self.assertEqual(result['direction'], result['structure_direction'])
        self.assertTrue(result['structure_reasons'])
        return result

    def assert_neutral(self, result):
        self.assertEqual(result['direction'], 'NEUTRAL')
        self.assertEqual(result['structure_score'], 0.)

    def test_01_protected_files_and_entire_app_outside_method_unchanged(self):
        self.assertTrue(BASE_PROTECTED)
        for name, expected in BASE_PROTECTED.items():
            with self.subTest(file=name):
                actual = hashlib.sha256((ROOT / name).read_text(encoding='utf-8').encode()).hexdigest()
                self.assertEqual(actual, expected, 'Protected baseline changed')
        self.assertEqual(hashlib.sha256(outside_method(APP).encode()).hexdigest(), BASE_APP_OUTSIDE_METHOD)

    def test_02_real_sweep_rejection_both_directions(self):
        for df, side in ((event_frame(), 'BULLISH'), (mirror(event_frame()), 'BEARISH')):
            with self.subTest(side=side):
                result = self.run_structure(df)
                self.assertEqual(result['direction'], side)
                self.assertTrue(any(r.startswith('SWEEP_REJECTION:') for r in result['structure_reasons']))
                self.assertGreaterEqual(abs(result['structure_score']), .65)
                self.assertEqual(result['structure_score'] > 0, side == 'BULLISH')

    def test_03_stop_hunt_recovery_both_directions(self):
        for df, side in ((event_frame('hunt'), 'BULLISH'), (mirror(event_frame('hunt')), 'BEARISH')):
            with self.subTest(side=side):
                result = self.run_structure(df)
                self.assertEqual(result['direction'], side)
                self.assertFalse(result['liquidity_sweeps'])
                self.assertTrue(any(r.startswith('STOP_HUNT_RECOVERY:') for r in result['structure_reasons']))

    def test_04_bos_close_both_directions(self):
        for df, side in ((event_frame('bos'), 'BULLISH'), (mirror(event_frame('bos')), 'BEARISH')):
            with self.subTest(side=side):
                result = self.run_structure(df)
                self.assertEqual(result['direction'], side)
                self.assertTrue(any('BOS_CLOSE:bar=79;pivot=65;' in r for r in result['structure_reasons']))

    def test_05_wick_does_not_confirm_bos(self):
        df = candle(frame(), -1, 100., 101.2, 99.5, 100.5)
        for candidate in (df, mirror(df)):
            self.assert_neutral(self.run_structure(candidate))

    def test_06_no_recovery_cannot_create_reversal_family(self):
        df = candle(frame(), -1, 98., 99.4, 97., 98.8)
        for candidate, forbidden in ((df, 'BULLISH'), (mirror(df), 'BEARISH')):
            result = self.run_structure(candidate)
            self.assertNotEqual(result['direction'], forbidden)
            self.assertFalse(any(r.startswith(('SWEEP_REJECTION:', 'STOP_HUNT_RECOVERY:')) for r in result['structure_reasons']))

    def test_07_events_expire_after_three_bars(self):
        for kind in ('sweep', 'hunt', 'bos'):
            df = event_frame(kind)
            tail = frame(3)
            if kind == 'bos':
                for i in range(3):
                    candle(tail, i, 102.2, 102.6, 101.8, 102.2)
            self.assert_neutral(self.run_structure(pd.concat([df, tail], ignore_index=True)))

    def test_08_invalidation_prevents_reuse(self):
        df = event_frame()
        tail = candle(frame(1), 0, 98.9, 99.2, 98.5, 98.8)
        result = self.run_structure(pd.concat([df, tail], ignore_index=True))
        self.assertNotEqual(result['direction'], 'BULLISH')
        self.assertFalse(any(r.startswith('SWEEP_REJECTION:') for r in result['structure_reasons']))

    def test_09_higher_highs_higher_lows_are_not_a_family(self):
        for df in (broad_frame(), mirror(broad_frame())):
            result = self.run_structure(df)
            self.assertEqual(len(result['pivot_highs']), 3)
            self.assertEqual(len(result['pivot_lows']), 3)
            highs = [p['price'] for p in result['pivot_highs']]
            lows = [p['price'] for p in result['pivot_lows']]
            self.assertTrue((highs[0] < highs[1] < highs[2] and lows[0] < lows[1] < lows[2]) or
                            (highs[0] > highs[1] > highs[2] and lows[0] > lows[1] > lows[2]))
            self.assert_neutral(result)
            thesis = oi.build_independent_thesis(layers=layers(result), mtf_context=mtf(), market='FUTURES', symbol='SUI-USDT', timeframe='1H')
            self.assertNotIn('structure', thesis['long_families'])
            self.assertEqual(thesis['direction'], 'NEUTRAL')

    def test_10_ob_alone_does_not_create_direction(self):
        df = candle(frame(), 70, 99., 101.4, 98.7, 101.2, 400.)
        for candidate in (df, mirror(df)):
            result = self.run_structure(candidate)
            self.assertTrue(result['order_blocks'])
            self.assert_neutral(result)

    def test_11_unfilled_fvg_alone_does_not_create_direction(self):
        df = frame()
        candle(df, 69, 100., 103., 99., 102.5)
        for i in range(70, 80):
            candle(df, i, 102., 103., 101.5, 102.)
        for candidate in (df, mirror(df)):
            result = self.run_structure(candidate)
            self.assertTrue(any(not f['filled'] for f in result['fair_value_gaps']))
            self.assert_neutral(result)

    def test_12_insufficient_history_and_flat_market(self):
        for n in (0, 1, 10, 20, 80):
            self.assert_neutral(self.run_structure(frame(n)))

    def test_13_invalid_ohlc_fails_closed(self):
        for value in (float('nan'), float('inf'), -1.):
            df = event_frame()
            df.loc[79, 'close'] = value
            self.assert_neutral(self.run_structure(df))
        df = event_frame()
        df.loc[79, 'high'] = 96.
        self.assert_neutral(self.run_structure(df))

    def test_14_exception_return_exposes_neutral_contract(self):
        class FailingRuntime(type(self.analyzer)):
            def calculate_support_resistance_channels(self, *args):
                raise RuntimeError('QA intentional downstream failure')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = FailingRuntime().analyze_price_structure_layer(event_frame(), '1h', 'SUI-USDT')
        self.assertIn('analysis_error', result)
        self.assertEqual(result['structure_reasons'], ['STRUCTURE_ANALYSIS_ERROR'])
        self.assert_neutral(result)

    def test_15_high_reachable_using_real_structure_and_unchanged_thresholds(self):
        for df, side in ((event_frame(), 'BULLISH'), (mirror(event_frame()), 'BEARISH')):
            structure = self.run_structure(df)
            for symbol in ('SUI-USDT', 'HYPE-USDT', 'APT-USDT', 'INJ-USDT', 'SEI-USDT'):
                for tf in ('30M', '1H', '2H'):
                    with self.subTest(side=side, symbol=symbol, tf=tf):
                        thesis = oi.build_independent_thesis(layers=layers(structure, side), mtf_context=mtf(side), market='FUTURES', symbol=symbol, timeframe=tf)
                        self.assertEqual(thesis['risk_class'], 'HIGH')
                        self.assertEqual(thesis['required_independent_families'], 5)
                        self.assertEqual(thesis['required_direction_margin'], 1.45)
                        self.assertEqual(thesis['direction'], side)
                        self.assertEqual(len(thesis['independent_support_families']), 5)
                        candidate = oi.prepare_operational_intelligence(layers=layers(structure, side), mtf_context=mtf(side),
                                    symbol=symbol, timeframe=tf, system_type='futures', research_candidates={})
                        self.assertTrue(candidate['candidate_ready'])
                        self.assertEqual(candidate['candidate_action'], 'LONG' if side == 'BULLISH' else 'SHORT')
                        # Reproduce the exact old omission, not an invented old scorer.
                        legacy_structure = {k: v for k, v in structure.items() if k not in FIELDS}
                        old = oi.build_independent_thesis(layers=layers(legacy_structure, side), mtf_context=mtf(side), market='FUTURES', symbol=symbol, timeframe=tf)
                        self.assertEqual(old['families']['structure']['score'], 0.)
                        self.assertEqual(old['direction'], 'NEUTRAL')
                        self.assertEqual(len(old['independent_support_families']), 4)

    def test_16_structure_does_not_replace_other_families(self):
        structure = self.run_structure(event_frame())
        for missing in ('trend', 'momentum', 'volume', 'multiframe'):
            ls, context = layers(structure), mtf()
            if missing == 'multiframe':
                context = {'alignment': 'INCOMPLETE'}
            else:
                ls[missing] = {}
            thesis = oi.build_independent_thesis(layers=ls, mtf_context=context, market='FUTURES', symbol='SUI-USDT', timeframe='1H')
            self.assertEqual(thesis['direction'], 'NEUTRAL')

    def test_17_multiasset_and_core_four_family_requirement_preserved(self):
        for symbol in ('BTC-USDT', 'CL-USDT'):
            ls = layers(self.run_structure(event_frame()))
            ls['volume'] = {}
            thesis = oi.build_independent_thesis(layers=ls, mtf_context=mtf(), market='FUTURES', symbol=symbol, timeframe='1H')
            self.assertEqual(thesis['required_independent_families'], 4)
            self.assertEqual(thesis['direction'], 'BULLISH')
            ls['structure'] = self.run_structure(frame())
            thesis = oi.build_independent_thesis(layers=ls, mtf_context=mtf(), market='FUTURES', symbol=symbol, timeframe='1H')
            self.assertEqual(thesis['direction'], 'NEUTRAL')

    def test_18_mtf_conflict_still_blocks_candidate(self):
        context = mtf()
        context.update(conflict=True, alignment='CONFLICT')
        result = oi.prepare_operational_intelligence(layers=layers(self.run_structure(event_frame())),
                    mtf_context=context, symbol='SUI-USDT', timeframe='1H', system_type='futures', research_candidates={})
        self.assertFalse(result['candidate_ready'])

    def test_19_prefix_is_causal_and_input_not_mutated(self):
        df = event_frame('bos')
        original = df.copy(deep=True)
        self.assert_neutral(self.run_structure(df.iloc[:-1].copy()))
        result = self.run_structure(df)
        self.assertEqual(result['direction'], 'BULLISH')
        pd.testing.assert_frame_equal(df, original)
        extended = pd.concat([df, candle(frame(1), 0, 102., 110., 95., 96.)], ignore_index=True)
        self.assertEqual(self.run_structure(extended.iloc[:80].copy())['structure_reasons'], result['structure_reasons'])

    def test_20_opposing_valid_events_remain_neutral(self):
        df = candle(frame(), -2, 99.5, 100.8, 97., 100.2)
        candle(df, -1, 100.5, 103., 99.2, 99.8)
        result = self.run_structure(df)
        self.assert_neutral(result)
        self.assertEqual(result['structure_reasons'][0], 'CONFLICTING_STRICT_STRUCTURE_EVENTS')

    def test_21_unconfirmed_pivot_cannot_supply_bos(self):
        df = candle(frame(), 75, 100., 102., 99., 100.)
        candle(df, -1, 100., 102.2, 99.5, 101.8)
        for candidate in (df, mirror(df)):
            self.assert_neutral(self.run_structure(candidate))

    def test_22_broken_then_lost_level_is_not_a_fresh_bos(self):
        df = event_frame('bos')
        tail = frame(2)
        candle(tail, 0, 102.2, 102.5, 101.5, 101.8)
        candle(tail, 1, 101.8, 102.5, 101.5, 102.2)
        df = pd.concat([df, tail], ignore_index=True)
        for candidate in (df, mirror(df)):
            self.assert_neutral(self.run_structure(candidate))

    def test_23_ob_only_reinforces_an_existing_strict_event(self):
        df = candle(event_frame(), 70, 99., 101.4, 98.7, 101.2, 400.)
        for candidate in (df, mirror(df)):
            result = self.run_structure(candidate)
            self.assertIn('OB_REINFORCEMENT', result['structure_reasons'])
            self.assertGreater(abs(result['structure_score']), .65)
            self.assertLessEqual(abs(result['structure_score']), .85)
            self.assertTrue(any(r.startswith('SWEEP_REJECTION:') for r in result['structure_reasons']))

    def test_24_fvg_only_reinforces_an_existing_strict_event(self):
        df = candle(event_frame('bos'), -1, 102.6, 104., 102.5, 103.)
        for candidate in (df, mirror(df)):
            result = self.run_structure(candidate)
            self.assertIn('FVG_REINFORCEMENT', result['structure_reasons'])
            self.assertGreater(abs(result['structure_score']), .65)
            self.assertLessEqual(abs(result['structure_score']), .85)
            self.assertTrue(any(r.startswith('BOS_CLOSE:') for r in result['structure_reasons']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
