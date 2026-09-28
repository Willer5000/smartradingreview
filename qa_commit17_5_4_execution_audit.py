"""Offline regression audit. Run in the complete project: python this_file.py.

Uses production committees and AST-loaded app caller, with controlled legacy
selectors to isolate refinement. Synthetic fixtures are not profitability data.
No exchange, database, scheduler or Flask startup is used.
"""
import ast
import contextlib
import copy
import hashlib
import io
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import execution_specialist_committees as committee
import execution_geometry_committee as geometry

BASE_PROTECTED = {'operational_intelligence.py': '3ab1bfd66d7c3e0a4bae2d1fea253d1745dfb6b5938b445c861762e606657930', 'futures_system.py': '5dd050b00cec16e311e21cd7f786281b69c60d4c7003a2e5ec040fd1e7332eca', 'multiasset_system.py': '1a38c5e2fd756a946eed49f8473ca2d48a1f7776c5056a7db4ae1f7a73d2f370', 'default_strategy_bank.py': 'efcc923ae0ede143ef936c79f6f0c1e68e95ab53f7635e5fc97d3f248ce75ee1', 'leverage_policy.py': 'c13bb6bab647c5984bb56e861b4c00cec3fabde2d2c94f0de5684e062a64cb81', 'portfolio_guardian.py': '7e55045ec8de752ce190753ab39da4670cb31e8b990581227febd37b8c4b4a69', 'saved_signals.py': 'a101d908ae452e8df0d514ab82820b36a049d7a628518d2f395601a9254f3928', 'execution_geometry_committee.py': '9ab082b29bbea2606649187e02835cf01310bb775d1f57f46f5db43f855d8b6f', 'futures_universe.py': 'cb89f326f049a139f72fa1b4469b79dab8fe2ee5bdcaaa30697ac7617d4da8f8', 'q6_integrity.py': '45c41ace61a9c87fc6429507275b8b6ef26b6266ba3db7178503b5fa992ce998', 'entry_reaction_engine.py': '2c23e6c0dfa33058d17da0d5aacc7d9094574f740bf969f3794455a0a0baaf8a', 'execution_economics.py': 'ae3c5abee2529f167f717a6ec8ab75b599d63006d51857546914e800e1781815', 'historical_research.py': '11df1f3baeed55829db2e8184ec1300ec73b37d474ebff6b3aaa9106bd0e92a3', 'qa_commit17_5_3_structure_signal_path.py': '2d570c09c73d1918b5a3f2ba5205a2fa17869e677168c6466a93a5551a8bb8ad'}
BASE_STRUCTURE = 'c9f51ea6f29e3d3a9b4cfc670ad49e7d92aefb24f9fa16c8bceb0193854fc487'
BASE_APP_OUTSIDE_ENTRY = 'c7dd7e8d7993840fbcff785e4c4be055bc0ecf1720d79b0229163f7c421a9210'


def extract(source, name):
    node, = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name]
    node.decorator_list = []
    return node


APP = (ROOT / 'app.py').read_text(encoding='utf-8')
CALLER_NODE = extract(APP, 'calculate_entry_levels')
GATE_NODE = extract((ROOT / 'futures_system.py').read_text(encoding='utf-8'), '_futures_entry_timing_gate')
MTF_NODE = extract(APP, '_get_operational_mtf_peer_minimal')
namespace = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[CALLER_NODE, GATE_NODE], type_ignores=[])), str(ROOT / 'app.py'), 'exec'), namespace)


class RuntimeCaller:
    calculate_entry_levels = namespace['calculate_entry_levels']
    _futures_entry_timing_gate = staticmethod(namespace['_futures_entry_timing_gate'])

    def __init__(self, side='long', current=102., entry=100., atr=2., mode=None):
        self.side, self.current, self.entry, self.atr = side, current, entry, atr
        self.sl = entry - 2. if side == 'long' else entry + 2.
        self.tp = entry + 4. if side == 'long' else entry - 4.
        self.mode = mode or ('DEEP_PULLBACK_LIMIT' if abs(current-entry)/atr >= .9 else 'NEAR_REACTION')

    def _select_optimal_entry(self, *args, **kwargs):
        return self.entry, 'Order Block', 80., {
            'candidate_type': 'ob', 'entry_timing_mode': self.mode,
            'distance_atr_current': abs(self.current-self.entry)/self.atr,
            'distance_pct_current': abs(self.current-self.entry)/self.current*100,
            'smc_raw_score': 80., 'reachability_score': 80., 'market_location': 'MID_RANGE',
            '_geometry_profile_internal': {'technical_rr_floor': 1.8, 'technical_rr_ceiling': 4.5,
                                           'near_max_atr': getattr(self, 'near_max', .6), 'deep_min_atr': .9},
        }

    def _select_optimal_sl(self, *args, **kwargs): return self.sl, 'Swing SL', 80.
    def _select_optimal_tp(self, *args, **kwargs): return self.tp, 'Swing TP', 80.
    def _round_price(self, price, symbol): return round(price, 8)
    def _calculate_min_tp_distance_pct(self, *args): return 1.
    def _get_default_levels(self, *args): raise AssertionError('Unexpected runtime fallback')
    def _build_rejected_levels(self, *args): return {'is_executable': False}


def proposal(entry=99.8, side='long', **changes):
    sign = 1 if side == 'long' else -1
    result = {'success': True, 'entry': entry, 'stop_loss': entry-sign*2., 'take_profit': entry+sign*4.,
              'geometry_quality': 80., 'baseline_geometry_quality': 75., 'geometry_improvement': 5.,
              'entry_quality': 80., 'sl_quality': 80., 'tp_quality': 80.,
              'entry_committee': {'source': 'Order Block'}, 'sl_committee': {}, 'tp_committee': {}}
    return {**result, **changes}


def run_caller(analyzer=None, market='futures', fake_proposal=None, structure=None, coordinator=None, observations=None):
    analyzer = analyzer or RuntimeCaller()
    side = analyzer.side
    action = ('LONG' if side == 'long' else 'SHORT') if market != 'spot' else ('COMPRA_SPOT' if side == 'long' else 'VENTA_SPOT')
    symbol = 'CL-USDT' if market == 'multiasset' else 'BTC-USDT'
    st = {'current_price': analyzer.current, 'previous_close': analyzer.current,
          'nearest_support': 98., 'nearest_resistance': 104., **(structure or {})}
    trend = {'direction': 'bullish' if side == 'long' else 'bearish', 'adx': 35.}
    vol = {'atr': analyzer.atr, 'atr_pct': 2., 'bb_position': .5, 'suggested_leverage': 5}
    # Only the import used to identify the Multi-Asset market is isolated;
    # the application/market adapters must not start during offline QA.
    multi = SimpleNamespace(MULTIASSET_SYMBOLS={'CL-USDT': {}})
    ctx = (patch.object(committee, 'coordinate_execution_committees', return_value=fake_proposal)
           if fake_proposal is not None else
           patch.object(committee, 'coordinate_execution_committees', side_effect=coordinator)
           if coordinator is not None else contextlib.nullcontext())
    with patch.dict(sys.modules, {'multiasset_system': multi}), ctx, contextlib.redirect_stdout(io.StringIO()):
        return analyzer.calculate_entry_levels(action, trend, trend, vol, st, symbol, '1h' if market != 'spot' else '4h', execution_observations=observations)


def committee_kwargs(market='spot', side='long'):
    return dict(baseline_entry=100., baseline_sl=98. if side == 'long' else 102.,
                baseline_tp=104. if side == 'long' else 96., direction=side,
                current_price=101. if side == 'long' else 99., atr=2., market_type=market)


class ExecutionAuditQA(unittest.TestCase):
    def test_01_scope_and_structure_unchanged(self):
        self.assertTrue(BASE_PROTECTED)
        for name, expected in BASE_PROTECTED.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest(), expected, name)
        structure = ast.get_source_segment(APP, extract(APP, 'analyze_price_structure_layer'))
        self.assertEqual(hashlib.sha256(structure.encode()).hexdigest(), BASE_STRUCTURE)
        # The sole change outside these two functions is passing already-built
        # capas to the execution caller. Pin all other analyze_full_market code.
        handoff = '                        liquidation=liquidation_data,\n                        execution_observations=capas,\n'
        self.assertEqual(APP.count(handoff), 1)
        normalized = APP.replace(handoff, '                        liquidation=liquidation_data\n')
        lines = normalized.splitlines(keepends=True)
        excluded = set()
        for node in (extract(normalized, 'calculate_entry_levels'), extract(normalized, '_get_operational_mtf_peer_minimal')):
            excluded.update(range(node.lineno-1, node.end_lineno))
        outside = ''.join(line for i, line in enumerate(lines) if i not in excluded)
        self.assertEqual(hashlib.sha256(outside.encode()).hexdigest(), BASE_APP_OUTSIDE_ENTRY)

    def test_02_identical_geometry_has_zero_improvement_all_markets_and_sides(self):
        for market in ('spot', 'futures', 'multiasset'):
            for side in ('long', 'short'):
                with self.subTest(market=market, side=side):
                    result = committee.coordinate_execution_committees(**committee_kwargs(market, side))
                    self.assertTrue(result['success'])
                    self.assertEqual(result['geometry_quality'], result['baseline_geometry_quality'])
                    self.assertEqual(result['geometry_improvement'], 0.)

    def test_03_filled_fvg_is_not_sl_invalidation(self):
        for side in ('long', 'short'):
            st = {'fair_value_gaps': [{'type': 'bullish' if side == 'long' else 'bearish',
                                     'filled': True, 'gap_bottom': 99., 'gap_top': 101.}]}
            rows = committee._collect_sl_candidates(st, side, 100., 97. if side == 'long' else 103., 1., 50.)
            self.assertEqual(len(rows), 1)
            st['fair_value_gaps'][0]['filled'] = False
            self.assertEqual(len(committee._collect_sl_candidates(st, side, 100., 97. if side == 'long' else 103., 1., 50.)), 2)

    def test_04_invalidated_ob_not_reused_even_after_reclaim(self):
        for typ, closes in (('bullish', [100., 98., 100.]), ('bearish', [100., 102., 100.])):
            st = {'order_blocks': [{'type': typ, 'index': 0, 'price_range': [99., 101.]}], 'df': {'close': closes}}
            original = copy.deepcopy(st)
            self.assertEqual(committee._execution_structure(st)['order_blocks'], [])
            self.assertEqual(st, original)
            st['df']['close'] = [100., 100., 100.]
            self.assertEqual(len(committee._execution_structure(st)['order_blocks']), 1)

    def test_05_missing_legacy_index_preserves_unflagged_ob(self):
        st = {'order_blocks': [{'type': 'bullish', 'price_range': [99., 101.]}]}
        self.assertEqual(committee._execution_structure(st), st)
        for flag in ('invalidated', 'mitigated'):
            self.assertEqual(committee._execution_structure({'order_blocks': [{**st['order_blocks'][0], flag: True}]})['order_blocks'], [])

    def test_06_nonfinite_and_invalid_directions_cannot_refine(self):
        for key in ('baseline_entry', 'baseline_sl', 'baseline_tp', 'atr', 'current_price'):
            for value in (float('inf'), float('nan'), -1., 0.):
                params = {**committee_kwargs(), key: value}
                self.assertFalse(committee.coordinate_execution_committees(**params)['success'])
        for side in ('', None, 'neutral'):
            self.assertFalse(committee.coordinate_execution_committees(**{**committee_kwargs(), 'direction': side})['success'])

    def test_07_callback_rejection_or_error_preserves_baseline(self):
        def fails(_): raise ValueError('intentional')
        for guard in (lambda _: False, fails):
            result = committee.coordinate_execution_committees(**committee_kwargs(), candidate_filter=guard)
            self.assertFalse(result['success'])
            self.assertTrue(result['fallback_to_baseline'])

    def test_08_search_finds_best_admissible_runner_up(self):
        params = {**committee_kwargs(), 'structure': {'supports': [98.5, 99., 99.5], 'resistances': [103., 104., 105., 106.]}}
        proposals = []
        def collect(p): proposals.append(p); return True
        top = committee.coordinate_execution_committees(**params, candidate_filter=collect)
        self.assertGreater(len(proposals), 2)
        winner = (top['entry'], top['stop_loss'], top['take_profit'])
        def allowed(p): return (p['entry'], p['stop_loss'], p['take_profit']) != winner
        remaining = [p for p in proposals if allowed(p)]
        self.assertTrue(remaining)
        result = committee.coordinate_execution_committees(**params, candidate_filter=allowed)
        self.assertTrue(result['success'])
        self.assertNotEqual((result['entry'], result['stop_loss'], result['take_profit']), winner)
        self.assertEqual(result['geometry_quality'], max(p['geometry_quality'] for p in remaining))
        self.assertGreater(result['admissibility_rejections'], 0)

    def test_09_actual_caller_refreshes_price_metadata_all_markets(self):
        for market in ('spot', 'futures', 'multiasset'):
            result = run_caller(market=market, fake_proposal=proposal())
            self.assertTrue(result['execution_refinement_applied'], result)
            self.assertEqual(result['entry'], 99.8)
            self.assertEqual(result['entry_distance_atr'], 1.1)
            self.assertAlmostEqual(result['entry_distance_pct'], round(2.2/102*100, 4))
            self.assertEqual(result['entry_timing_mode'], 'DEEP_PULLBACK_LIMIT')
            self.assertEqual(result['entry_score'], 80.)
            self.assertEqual(result['tp_quality_score'], 80.)
            self.assertEqual(result['sl_reliability'], .8)

    def test_10_short_caller_is_symmetric(self):
        result = run_caller(RuntimeCaller(side='short', current=98.), fake_proposal=proposal(100.2, 'short'))
        self.assertTrue(result['execution_refinement_applied'])
        self.assertEqual(result['entry_distance_atr'], 1.1)
        self.assertEqual(result['entry'], 100.2)

    def test_11_moved_deep_limit_cannot_inherit_near_market_exemption(self):
        result = run_caller(fake_proposal=proposal(101.7))
        self.assertFalse(result['execution_refinement_applied'])
        self.assertEqual(result['entry'], 100.)

    def test_12_lower_tf_trigger_boundary_is_preserved(self):
        analyzer = RuntimeCaller(current=101.4, mode='STRUCTURAL_PULLBACK')
        analyzer.near_max = .4
        # Both prices are STRUCTURAL_PULLBACK, but the native lower-TF gate
        # changes at 0.60 ATR. Preserve that independent boundary as well.
        result = run_caller(analyzer, fake_proposal=proposal(100.3))
        self.assertFalse(result['execution_refinement_applied'])

    def test_13_failed_or_unknown_timing_cannot_authorize_refinement(self):
        def fails(*args): raise ValueError('intentional')
        for gate in (fails, lambda *a: {}, lambda *a: {'passed': True, 'status': 'TIMING_DIAGNOSTIC_ERROR'}):
            analyzer = RuntimeCaller()
            analyzer._futures_entry_timing_gate = gate
            result = run_caller(analyzer, fake_proposal=proposal())
            self.assertFalse(result['execution_refinement_applied'])
            self.assertEqual(result['entry'], 100.)

    def test_14_original_numeric_bounds_are_not_relaxed(self):
        bad = [proposal(97.), proposal(stop_loss=96.), proposal(stop_loss=99.6),
               proposal(take_profit=108.), proposal(geometry_improvement=1.49),
               proposal(geometry_quality=61.99), proposal(entry_quality=54.99),
               proposal(sl_quality=59.99), proposal(tp_quality=59.99),
               proposal(geometry_quality=float('inf'))]
        for p in bad:
            result = run_caller(fake_proposal=p)
            self.assertFalse(result['execution_refinement_applied'], p)
            self.assertEqual(result['entry'], 100.)

    def test_15_real_search_is_wired_into_actual_caller(self):
        original = committee.coordinate_execution_committees
        called = []
        def verify(**kwargs):
            self.assertTrue(callable(kwargs.get('candidate_filter')))
            called.append(kwargs['market_type'])
            return original(**kwargs)
        for market in ('spot', 'futures', 'multiasset'):
            result = run_caller(market=market, coordinator=verify)
            self.assertFalse(result['execution_refinement_applied'])
            self.assertEqual(result['entry'], 100.)
        self.assertEqual(called, ['spot', 'futures', 'multiasset'])

    def test_16_invalid_baseline_never_calls_refiner(self):
        analyzer = RuntimeCaller()
        analyzer.tp = 101.  # R/R 0.5: not eligible for refinement.
        calls = []
        def forbidden(**kwargs): calls.append(kwargs); return {'success': False}
        result = run_caller(analyzer, coordinator=forbidden)
        self.assertFalse(calls)
        self.assertFalse(result['is_executable'])
        self.assertFalse(result['execution_refinement_applied'])

    def mtf_runtime(self):
        ns = {'time': time, '_OPERATIONAL_MTF_MINIMAL_CACHE': {},
              '_OPERATIONAL_MTF_MINIMAL_LOCK': threading.Lock(), '_OPERATIONAL_MTF_MINIMAL_TTL': 300.}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[MTF_NODE], type_ignores=[])), str(ROOT/'app.py'), 'exec'), ns)
        return ns['_get_operational_mtf_peer_minimal'], ns['_OPERATIONAL_MTF_MINIMAL_CACHE']

    def test_17_crypto_and_multi_mtf_use_closed_provider_not_raw_data(self):
        import qa_commit17_5_3_structure_signal_path as previous
        for symbol, market in (('BTC-USDT', 'futures'), ('CL-USDT', 'futures'), ('CL-USDT', 'multiasset')):
            func, cache = self.mtf_runtime()
            df = previous.frame(81)
            df.loc[80, 'close'] = 110.  # Developing candle must never reach analysis.
            analyzed = []
            def analyze(frame, *args): analyzed.append(len(frame)); return {'close': float(frame['close'].iloc[-1])}
            def raw(*args): raise AssertionError('Raw derivative candles used')
            analyzer = SimpleNamespace(_prepare_closed_candle_analysis_data=lambda *a: {'success': True, 'closed_df': df.iloc[:-1].copy()},
                    get_kucoin_data=raw, analyze_trend_layer=analyze, analyze_momentum_layer=analyze,
                    analyze_volume_layer=analyze, analyze_price_structure_layer=analyze)
            with patch.dict(sys.modules, {'multiasset_system': SimpleNamespace(MULTIASSET_SYMBOLS={'CL-USDT': {}})}):
                result = func(analyzer, symbol, '1h', market)
            self.assertTrue(result['source_candle_closed'])
            self.assertEqual(result['structure']['close'], 100.)
            self.assertEqual(analyzed, [80]*4)
            self.assertEqual(len(cache), 1)

    def test_18_spot_closure_error_never_caches_a_closed_label(self):
        import qa_commit17_5_3_structure_signal_path as previous
        func, cache = self.mtf_runtime()
        analyzer = SimpleNamespace(get_kucoin_data=lambda *a: previous.frame(81))
        with patch.dict(sys.modules, {'multiasset_system': SimpleNamespace(MULTIASSET_SYMBOLS={})}), \
             patch('q6_integrity.prepare_spot_frame', side_effect=ValueError('stale or invalid frame')):
            self.assertIsNone(func(analyzer, 'BTC-USDT', '4h', 'spot'))
        self.assertFalse(cache)

    def test_19_mtf_missing_closed_provider_does_not_fallback_to_raw(self):
        func, cache = self.mtf_runtime()
        with patch.dict(sys.modules, {'multiasset_system': SimpleNamespace(MULTIASSET_SYMBOLS={})}):
            self.assertIsNone(func(SimpleNamespace(), 'BTC-USDT', '1h', 'futures'))
        self.assertFalse(cache)

    def test_20_real_committees_can_refine_real_caller(self):
        st = {'supports': [99.4], 'resistances': [104.2], 'pivot_lows': [{'price': 97.7}],
              'pivot_highs': [{'price': 104.2}], 'volume_profile': {'poc': 99.4},
              'order_blocks': [{'type': 'bullish', 'price_range': [97.7, 99.4], 'strength': 'strong'}],
              'bos': True, 'sweep': True, 'displacement': True}
        for market in ('spot', 'futures', 'multiasset'):
            out = run_caller(market=market, structure=st)
            self.assertTrue(out['execution_refinement_applied'], (market, out))
            self.assertLess(out['entry'], 100.)  # A better-priced long structural POI.
            self.assertLess(out['stop_loss'], 97.7)  # Behind actual invalidation.
            self.assertLessEqual(out['take_profit'], 104.2)  # At/before observed resistance.
            self.assertGreaterEqual(out['execution_geometry_improvement'], 1.5)

    def test_21_actual_observed_context_reaches_committees_for_each_market(self):
        observations = {'volume': {'volume_ratio': 2.2}, 'macro_context': {'risk_level': 'HIGH'},
                        'market_hours': {'session': 'US', 'day_type': 'WEEKDAY'},
                        'sentiment': {'current_value': 25}, 'market_regime': {'regime': 'TRENDING_BULL'}}
        original = copy.deepcopy(observations)
        captured = []
        def capture(**kw):
            captured.append(kw['execution_context'])
            return {'success': False}
        for market in ('spot', 'futures', 'multiasset'):
            run_caller(market=market, coordinator=capture, observations=observations)
        self.assertEqual(observations, original)
        for ctx in captured:
            self.assertEqual(ctx['volume_ratio'], 2.2)
            self.assertEqual(ctx['macro_risk'], 'HIGH')
            self.assertEqual(ctx['market_regime'], 'TRENDING_BULL')
            self.assertEqual(ctx['session'], 'US')
            self.assertEqual(ctx['sentiment_value'], 25)
        self.assertEqual(captured[-1]['asset_class'], 'ENERGY')

    def test_22_spot_rotation_direction_matches_asset_being_bought(self):
        from portfolio_guardian import PortfolioGuardian
        guardian = object.__new__(PortfolioGuardian)
        for action, btc_favored in (('COMPRA_SPOT', False), ('VENTA_SPOT', True)):
            analysis = {'decision': {'action': action, 'confidence': 80}, 'levels': {'execution_safety': 80}}
            score = guardian._score_ratio_for_assets(analysis)
            self.assertEqual(score > 0, btc_favored)
        self.assertEqual(guardian._score_ratio_for_assets({}), 0.)

    def test_23_distinct_asset_and_timeframe_profiles_are_preserved(self):
        neutral_learning = geometry._learning_hint('spot', 'BTC-USDT', '4h', 'long')
        with patch.object(geometry, '_learning_hint', return_value=neutral_learning):
            profiles = {}
            for market, symbol, tf in (
                    ('spot','BTC-USDT','4h'), ('spot','PAXG-USDT','1D'), ('spot','PAXG-BTC','4h'),
                    ('futures','BTC-USDT','1h'), ('futures','SUI-USDT','30m'),
                    ('futures','SPY-USDT','1h'), ('futures','CL-USDT','1h'),
                    ('futures','COPPER-USDT','4h'), ('futures','XAG-USDT','4h'), ('futures','KSTR-USDT','1D')):
                p = geometry.build_profile(market_type=market, symbol=symbol, timeframe=tf, direction='long',
                        setup_family='TREND_PULLBACK', market_regime='TRENDING_BULL', trend={}, momentum={},
                        volatility={'atr_pct': 1., 'volatility_ratio': 1., 'volatility_percentile': 50})
                profiles[symbol] = p
                self.assertGreater(p['technical_rr_floor'], 1.)
                self.assertGreater(p['technical_rr_ceiling'], p['technical_rr_floor'])
            self.assertEqual(geometry.instrument_bucket('spot','PAXG-BTC'), 'SPOT_PAXG_BTC_ROTATION')
            self.assertNotEqual(profiles['CL-USDT']['target_atr_soft_max'], profiles['SPY-USDT']['target_atr_soft_max'])
            self.assertNotEqual(profiles['PAXG-BTC']['deep_min_atr'], profiles['BTC-USDT']['deep_min_atr'])


def load_tests(loader, tests, pattern):
    # The earlier scope hash intentionally pins all of app.py to 17.5.2.
    # Replace only that historical scope check with test_01 above; keep every
    # behavioral test of strict Structure, HIGH and MTF intact (23 tests).
    import qa_commit17_5_3_structure_signal_path as previous
    for name in loader.getTestCaseNames(previous.StructureRuntimeQA):
        if not name.startswith('test_01_'):
            tests.addTest(previous.StructureRuntimeQA(name))
    return tests


if __name__ == '__main__':
    unittest.main(verbosity=2)
