from pathlib import Path
import sys
import types

ROOT = Path(__file__).parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
SPOT_JS_PATH = ROOT / 'static' / 'script.js'
FUT_JS_PATH = ROOT / 'static' / 'futures.js'
SPOT_JS = SPOT_JS_PATH.read_text(encoding='utf-8') if SPOT_JS_PATH.exists() else ''
FUT_JS = FUT_JS_PATH.read_text(encoding='utf-8') if FUT_JS_PATH.exists() else ''

from execution_geometry_committee import (
    build_profile,
    entry_candidate_adjustment,
    instrument_bucket,
)
from entry_reaction_engine import evaluate_entry_reaction
import user_execution_learning as uel


def test_market_and_instrument_specialization():
    assert instrument_bucket('spot', 'BTC/USDT') == 'SPOT_BTC_USDT'
    assert instrument_bucket('spot', 'PAXG-USDT') == 'SPOT_PAXG_USDT'
    assert instrument_bucket('spot', 'PAXG/BTC') == 'SPOT_PAXG_BTC_ROTATION'
    assert instrument_bucket('futures', 'BTC-USDT') == 'CORE1'
    assert instrument_bucket('futures', 'XRP-USDT') == 'CORE2'
    assert instrument_bucket('futures', 'LINK-USDT') == 'MEDIUM'
    assert instrument_bucket('futures', 'SUI-USDT') == 'HIGH'


def test_spot_and_futures_have_different_missions_and_speed():
    spot = build_profile(
        market_type='spot', symbol='PAXG-BTC', timeframe='12h', direction='long',
        market_regime='RANGING', volatility={'atr_pct': 1.2}
    )
    core = build_profile(
        market_type='futures', symbol='BTC-USDT', timeframe='1h', direction='long',
        market_regime='TRENDING_BULL', volatility={'atr_pct': 0.8}
    )
    medium = build_profile(
        market_type='futures', symbol='LINK-USDT', timeframe='1h', direction='long',
        market_regime='TRENDING_BULL', volatility={'atr_pct': 1.0}
    )
    high = build_profile(
        market_type='futures', symbol='SUI-USDT', timeframe='1h', direction='long',
        market_regime='HIGH_VOLATILITY', volatility={'atr_pct': 1.7, 'volatility_percentile': 88}
    )
    assert spot['mission'] == 'ACCUMULATION_ROTATION'
    assert spot['speed'] == 'POSITIONAL'
    core2 = build_profile(
        market_type='futures', symbol='XRP-USDT', timeframe='1h', direction='long',
        market_regime='TRENDING_BULL', volatility={'atr_pct': 0.8}
    )
    assert core['speed'] == 'FAST'
    assert core2['speed'] == 'FAST'
    assert core2['target_atr_soft_max'] != core['target_atr_soft_max']
    assert core2['specialization_key'] != core['specialization_key']
    assert medium['speed'] == 'FASTER'
    assert high['speed'] == 'VERY_FAST'
    assert high['target_atr_soft_max'] < medium['target_atr_soft_max'] < core['target_atr_soft_max']


def test_context_volatility_and_timeframe_change_geometry():
    base = build_profile(
        market_type='futures', symbol='BTC-USDT', timeframe='1h', direction='long',
        market_regime='TRENDING_BULL', setup_family='PULLBACK',
        volatility={'atr_pct': 0.8, 'volatility_percentile': 50, 'volatility_ratio': 1.0}
    )
    volatile = build_profile(
        market_type='futures', symbol='BTC-USDT', timeframe='1h', direction='long',
        market_regime='HIGH_VOLATILITY', setup_family='PULLBACK',
        volatility={'atr_pct': 2.0, 'volatility_percentile': 92, 'volatility_ratio': 1.8}
    )
    tf4h = build_profile(
        market_type='futures', symbol='BTC-USDT', timeframe='4h', direction='long',
        market_regime='TRENDING_BULL', setup_family='PULLBACK',
        volatility={'atr_pct': 1.4, 'volatility_percentile': 50, 'volatility_ratio': 1.0}
    )
    assert volatile['hard_max_reach_atr'] > base['hard_max_reach_atr']
    assert volatile['sl_buffer_atr'] > base['sl_buffer_atr']
    assert tf4h['hard_max_reach_atr'] != base['hard_max_reach_atr']


def test_entry_can_choose_near_reaction_or_deep_probable_pullback():
    profile = build_profile(
        market_type='futures', symbol='LINK-USDT', timeframe='4h', direction='long',
        market_regime='TRENDING_BULL', setup_family='PULLBACK',
        volatility={'atr_pct': 1.5}
    )
    near_at_ceiling = entry_candidate_adjustment(
        profile, candidate_type='ob', distance_atr=0.25,
        market_location='CEILING_SUPPLY', directional_extension=True,
        correct_side_near_reaction=False, independent_family_count=2,
    )
    deep_at_ceiling = entry_candidate_adjustment(
        profile, candidate_type='ob', distance_atr=1.20,
        market_location='CEILING_SUPPLY', directional_extension=True,
        correct_side_near_reaction=False, independent_family_count=2,
    )
    near_at_floor = entry_candidate_adjustment(
        profile, candidate_type='support', distance_atr=0.25,
        market_location='FLOOR_DEMAND', directional_extension=False,
        correct_side_near_reaction=True, independent_family_count=2,
    )
    assert near_at_ceiling['timing_mode'] == 'NEAR_REACTION'
    assert deep_at_ceiling['timing_mode'] == 'DEEP_PULLBACK_LIMIT'
    assert deep_at_ceiling['adjustment'] > near_at_ceiling['adjustment']
    assert near_at_floor['adjustment'] > near_at_ceiling['adjustment']


def test_reviewtrader_is_zero_authority_below_8_and_bounded_after(monkeypatch):
    fake = types.ModuleType('user_execution_learning')
    fake.get_global_execution_profile = lambda *args, **kwargs: {
        'authority': 'OBSERVE_ONLY', 'sample_size': 3, 'expectancy_r': -1.0,
        'fast_sl_rate': 0.9, 'weak_progress_sl_rate': 0.9,
    }
    monkeypatch.setitem(sys.modules, 'user_execution_learning', fake)
    small = build_profile(
        market_type='futures', symbol='LINK-USDT', timeframe='4h', direction='long',
        market_regime='RANGING', volatility={'atr_pct': 1.4}
    )
    assert small['learning']['weight'] == 0.0
    assert small['learning']['deep_bias'] == 0.0

    fake.get_global_execution_profile = lambda *args, **kwargs: {
        'authority': 'BOUNDED_CONTINUITY', 'sample_size': 16, 'expectancy_r': -0.4,
        'fast_sl_rate': 0.45, 'weak_progress_sl_rate': 0.50,
    }
    mature = build_profile(
        market_type='futures', symbol='LINK-USDT', timeframe='4h', direction='long',
        market_regime='RANGING', volatility={'atr_pct': 1.4}
    )
    assert 0.0 < mature['learning']['weight'] <= 0.16
    assert mature['learning']['deep_bias'] > 0.0


def test_deep_futures_limit_does_not_require_prearrival_reaction():
    levels = {
        'entry_source': 'Order Block alcista + FVG',
        'entry_smc_raw_score': 55,
        'entry_reachability_score': 25,
        'entry_defensibility_score': 70,
        'entry_distance_atr': 1.35,
        'entry_timing_mode': 'DEEP_PULLBACK_LIMIT',
        'entry_liquidity_pool_near': False,
        'entry_sweep_confirmed': False,
        'entry_mss_bos_confirmed': False,
        'entry_displacement_confirmed': False,
    }
    out = evaluate_entry_reaction(levels, timeframe='4h', market_type='futures')
    assert out['passed'] is True
    assert out['lower_tf_confirmation_required'] is False
    assert out['status'] == 'STRUCTURAL_LIMIT_WAITING_PRICE'


def test_near_futures_entry_still_requires_precision():
    levels = {
        'entry_source': 'Soporte',
        'entry_smc_raw_score': 75,
        'entry_reachability_score': 95,
        'entry_defensibility_score': 80,
        'entry_distance_atr': 0.30,
        'entry_timing_mode': 'NEAR_REACTION',
        'entry_liquidity_pool_near': True,
        'entry_sweep_confirmed': True,
        'entry_mss_bos_confirmed': True,
        'entry_displacement_confirmed': True,
    }
    out = evaluate_entry_reaction(levels, timeframe='4h', market_type='futures')
    assert out['passed'] is True
    assert out['lower_tf_confirmation_required'] is True
    assert out['status'] == 'ZONE_VALID_LOWER_TF_TRIGGER_REQUIRED'


def test_reviewtrader_publication_review_is_advisory_not_veto(monkeypatch):
    monkeypatch.setattr(uel, 'get_global_execution_profile', lambda *args, **kwargs: {
        'authority': 'BOUNDED_CONTINUITY', 'sample_size': 20, 'expectancy_r': -0.7,
        'fast_sl_rate': 0.55, 'weak_progress_sl_rate': 0.60,
    })
    review = uel.get_execution_publication_review(
        'LINK-USDT', '4h', 'LONG',
        {'entry_defensibility_score': 40, 'entry_reachability_score': 35}
    )
    assert review['block_publication'] is False
    assert review['publication_veto_disabled'] is True
    assert review['geometry_advice'] == 'PREFER_BETTER_PROTECTED_ENTRY_GEOMETRY'


def test_internal_committee_metadata_is_not_sent_to_frontend():
    # The profile is explicitly private and removed before API level construction.
    assert "entry_quality.pop(\n                '_geometry_profile_internal'" in APP
    assert 'specialist_weights' not in SPOT_JS
    assert 'specialist_weights' not in FUT_JS
    assert 'execution_geometry_committee' not in SPOT_JS
    assert 'execution_geometry_committee' not in FUT_JS
    # Frontend receives technical geometry labels only.
    assert "'entry_timing_mode':" in APP
    assert "'entry_independent_confluence_families':" in APP


def test_futures_q2_uses_same_internal_geometry_and_deep_mode_is_preserved():
    assert 'geometry_profile=geometry_profile' in FUTURES
    assert "timing_mode == 'DEEP_PULLBACK_LIMIT'" in FUTURES
    assert "'version': 'RC9_8_FUTURES_ENTRY_TIMING_V1'" in FUTURES
    learning_source = (ROOT / 'user_execution_learning.py').read_text(encoding='utf-8')
    assert 'publication_veto_disabled' in learning_source
    assert "'publication_veto': False" in FUTURES
    assert 'entry_defensibility_learning_advisory' in FUTURES


def _selector_dummy():
    lines = APP.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('    def _select_optimal_entry('))
    end = next(i for i, line in enumerate(lines[start + 1:], start + 1) if line.startswith('    def calculate_entry_levels('))
    ns = {}
    exec('class Dummy:\n' + '\n'.join(lines[start:end]), ns)
    dummy = ns['Dummy']()
    dummy._build_smc_entry_context = lambda *args, **kwargs: {
        'sweep': False,
        'mss': False,
        'displacement': False,
        'liquidity_pool_near': False,
        'liquidity_pool_price': None,
        'liquidity_pool_distance': None,
        'liquidity_pool_weight': 0,
    }
    dummy.detect_market_regime = lambda *args, **kwargs: {'regime': 'RANGING'}
    return dummy


def test_actual_entry_selector_prefers_deep_structure_when_long_is_extended():
    dummy = _selector_dummy()
    entry, _, _, diag = dummy._select_optimal_entry(
        'long',
        {
            'supports': [112.0],
            'resistances': [121.0],
            'order_blocks': [
                {'type': 'bullish', 'price_range': [118.0, 118.5], 'strength': 'strong'},
            ],
            'fair_value_gaps': [],
            'fib_retracements': {},
            'volume_profile': {},
        },
        120.0, 120.0,
        {'atr': 5.0, 'bb_position': 0.85},
        '4h', market_type='futures', symbol='BTC-USDT',
        trend={'indicators': {'ema21': 112.1, 'ema50': 111.8}},
    )
    assert diag['market_location'] == 'CEILING_SUPPLY'
    assert entry == 112.0
    assert diag['entry_timing_mode'] == 'DEEP_PULLBACK_LIMIT'


def test_actual_entry_selector_keeps_near_entry_when_reacting_at_demand():
    dummy = _selector_dummy()
    entry, _, _, diag = dummy._select_optimal_entry(
        'long',
        {
            'supports': [100.0],
            'resistances': [120.0],
            'order_blocks': [
                {'type': 'bullish', 'price_range': [100.2, 100.8], 'strength': 'strong'},
            ],
            'fair_value_gaps': [],
            'fib_retracements': {},
            'volume_profile': {},
        },
        101.0, 101.0,
        {'atr': 2.0, 'bb_position': 0.20},
        '4h', market_type='futures', symbol='BTC-USDT',
        trend={'indicators': {'ema21': 100.6, 'ema50': 99.8}},
    )
    assert diag['market_location'] == 'FLOOR_DEMAND'
    assert 100.0 <= entry <= 101.0
    assert diag['entry_timing_mode'] in {'NEAR_REACTION', 'STRUCTURAL_PULLBACK'}


def test_actual_entry_selector_can_keep_probable_pullback_beyond_old_preferred_band():
    dummy = _selector_dummy()
    # 3.0 ATR away: beyond legacy preferred max (2.5 ATR) but inside RC9.8
    # CORE1 4h hard cap (3.2 ATR). The structural support must remain eligible.
    entry, _, _, diag = dummy._select_optimal_entry(
        'long',
        {
            'supports': [105.0],
            'resistances': [121.0],
            'order_blocks': [],
            'fair_value_gaps': [],
            'fib_retracements': {},
            'volume_profile': {},
        },
        120.0, 120.0,
        {'atr': 5.0, 'bb_position': 0.90},
        '4h', market_type='futures', symbol='BTC-USDT',
        trend={'indicators': {}},
    )
    assert entry == 105.0
    assert diag['distance_atr_current'] == 3.0
    assert diag['hard_max_reach_atr'] >= 3.0
    assert diag['entry_timing_mode'] == 'DEEP_PULLBACK_LIMIT'


def _method_dummy(method_name, next_method_name=None):
    lines = APP.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f'    def {method_name}('))
    if next_method_name:
        end = next(i for i, line in enumerate(lines[start + 1:], start + 1) if line.startswith(f'    def {next_method_name}('))
    else:
        end = next(i for i, line in enumerate(lines[start + 1:], start + 1) if line.startswith('    def '))
    ns = {}
    exec('class Dummy:\n' + '\n'.join(lines[start:end]), ns)
    return ns['Dummy']()


def test_deep_pending_entry_can_keep_tp_between_entry_and_current_market():
    dummy = _method_dummy('_collect_tp_candidates', '_collect_sl_candidates')
    candidates = dummy._collect_tp_candidates(
        'long',
        {
            'resistances': [115.0],
            'order_blocks': [], 'fair_value_gaps': [], 'pivot_highs': [],
            'fib_extensions': {}, 'volume_profile': {},
        },
        current_price=120.0,
        volatility={'atr': 5.0},
        timeframe='4h',
        entry_reference=100.0,
    )
    assert any(abs(float(x.get('price') or 0) - 115.0) < 1e-9 for x in candidates)


def test_sl_hard_floor_is_atr_normalized_not_universal_point_six_percent():
    dummy = _method_dummy('_score_sl_candidate', '_select_optimal_tp')
    dummy._get_expected_sl_band = lambda timeframe: (0.3, 1.0)
    score = dummy._score_sl_candidate(
        {'price': 99.5, 'strength': 3, 'type': 'swing'},
        entry=100.0, direction='long', timeframe='1h',
        max_distance_pct=5.0, atr=0.5,
        geometry_profile={'sl_hard_min_atr': 0.65, 'sl_ideal_min_atr': 1.0, 'sl_ideal_max_atr': 3.0},
    )
    assert score >= 0


def test_structural_poi_is_not_rewritten_to_previous_close_by_anti_chase():
    assert "structural_entry = candidate_type in" in APP
    assert "if not structural_entry:" in APP
    assert "structural_entry_preserved_by_anti_chase" in APP
    assert "Cierre anterior (anti-FOMO pullback/reversión)" not in APP


def test_fixed_roi_and_profit_targets_are_diagnostics_not_publication_vetoes():
    assert "'publication_veto': False" in FUTURES
    gate = FUTURES[FUTURES.index('    def _apply_futures_publication_gate('):FUTURES.index('    def calculate_roi_futures(', FUTURES.index('    def _apply_futures_publication_gate('))]
    assert "require(\n            roi_tp" not in gate
    assert "require(\n            net_profit" not in gate
    assert "economic_diagnostics" in gate
    assert "economic_roi_reference" in FUTURES
    assert "economic_profit_reference" in FUTURES


def test_reviewtrader_persists_technical_geometry_without_internal_weights():
    review_source = (ROOT / 'review_trader.py').read_text(encoding='utf-8')
    assert "'entry_timing_mode'" in review_source
    assert "'entry_independent_confluence_families'" in review_source
    assert 'specialist_weights' not in review_source
