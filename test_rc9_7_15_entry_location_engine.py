from pathlib import Path

from entry_reaction_engine import evaluate_entry_reaction

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUT = (ROOT / 'futures_system.py').read_text(encoding='utf-8')


def _levels(distance_atr):
    return {
        'entry_smc_raw_score': 84,
        'entry_reachability_score': 88,
        'entry_defensibility_score': 80,
        'entry_distance_atr': distance_atr,
        'entry_source': 'Order Block alcista + Soporte',
        'entry_liquidity_pool_near': True,
        'entry_sweep_confirmed': True,
        'entry_mss_bos_confirmed': True,
        'entry_displacement_confirmed': True,
        'entry_market_location': 'FLOOR_DEMAND',
    }


def test_location_is_structural_first_not_atr_generated():
    assert "NEAREST_SUPPORT_RESISTANCE_RANGE" in APP
    assert "ATR_NORMALIZED_FALLBACK" in APP
    assert "NORMALIZER_NOT_ENTRY_SOURCE" in APP
    assert "market_location = 'FLOOR_DEMAND'" in APP
    assert "market_location = 'CEILING_SUPPLY'" in APP


def test_long_and_short_location_logic_is_symmetric():
    assert "LONG_EXTENDED_OR_AT_CEILING" in APP
    assert "LONG_AT_FLOOR_DEMAND" in APP
    assert "SHORT_EXTENDED_OR_AT_FLOOR" in APP
    assert "SHORT_AT_CEILING_SUPPLY" in APP


def test_correct_side_floor_or_ceiling_can_use_close_reaction_without_forced_deep_pullback():
    assert "correct_side_near_reaction" in APP
    assert "max(0.03, 0.10 * atr_pct)" in APP


def test_ema_is_confluence_not_entry_creator():
    assert "EMAs do not create an Entry by themselves" in APP
    assert "ema_confluence_bonus" in APP
    assert "ema21" in APP and "ema50" in APP and "ema200" in APP


def test_structural_poi_stays_primary_and_atr_fallback_low_score():
    assert "'ob': 28" in APP
    assert "'fvg': 22" in APP
    assert "'support': 18" in APP
    assert "'resistance': 18" in APP
    assert "'atr': 5" in APP


def test_near_market_2h_and_4h_futures_require_lower_tf_confirmation():
    out2 = evaluate_entry_reaction(_levels(0.40), timeframe='2h', market_type='futures')
    out4 = evaluate_entry_reaction(_levels(0.40), timeframe='4h', market_type='futures')
    assert out2['lower_tf_confirmation_required'] is True
    assert out4['lower_tf_confirmation_required'] is True


def test_deeper_2h_and_4h_structural_limit_does_not_require_pre_touch_trigger():
    out2 = evaluate_entry_reaction(_levels(0.90), timeframe='2h', market_type='futures')
    out4 = evaluate_entry_reaction(_levels(0.90), timeframe='4h', market_type='futures')
    assert out2['lower_tf_confirmation_required'] is False
    assert out4['lower_tf_confirmation_required'] is False


def test_lower_tf_map_covers_governed_execution_timeframes():
    assert "'1h': '30m'" in FUT
    assert "'2h': '30m'" in FUT
    assert "'4h': '1h'" in FUT
    assert "'12h': '2h'" in FUT
    assert "'1D': '4h'" in FUT


def test_orderflow_is_not_promoted_without_oos_calibration():
    assert "SHADOW_CONFLUENCE_NOT_AUTHORITY" in FUT
    assert "unvalidated order-book snapshot create or veto" in FUT


def test_ceiling_long_and_floor_short_are_explicit_wait_states():
    assert "WAIT_PULLBACK_LONG_EXTENDED" in FUT
    assert "WAIT_REBOUND_SHORT_EXTENDED" in FUT
    assert "Esperar retroceso hacia POI de reacción" in FUT
    assert "Esperar rebote hacia POI de reacción" in FUT


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
    return dummy


def test_long_at_floor_accepts_near_structural_reaction_and_records_location():
    dummy = _selector_dummy()
    entry, _, _, diag = dummy._select_optimal_entry(
        'long',
        {
            'supports': [100.0],
            'resistances': [120.0],
            'order_blocks': [{'type': 'bullish', 'price_range': [100.2, 100.8], 'strength': 'strong'}],
            'fair_value_gaps': [],
            'fib_retracements': {},
            'volume_profile': {},
        },
        101.0,
        101.0,
        {'atr': 2.0, 'bb_position': 0.20},
        '4h',
        market_type='futures',
        trend={'indicators': {'ema21': 100.6, 'ema50': 99.8}},
    )
    assert diag['market_location'] == 'FLOOR_DEMAND'
    assert diag['location_context'] == 'LONG_AT_FLOOR_DEMAND'
    assert entry <= 101.0
    assert diag['location_adjustment'] > 0


def test_short_at_floor_prefers_rebound_zone_not_floor_chase():
    dummy = _selector_dummy()
    entry, _, _, diag = dummy._select_optimal_entry(
        'short',
        {
            'supports': [100.0],
            'resistances': [108.0],
            'order_blocks': [{'type': 'bearish', 'price_range': [104.0, 105.0], 'strength': 'strong'}],
            'fair_value_gaps': [],
            'fib_retracements': {},
            'volume_profile': {},
        },
        101.0,
        101.0,
        {'atr': 3.0, 'bb_position': 0.10},
        '4h',
        market_type='futures',
        trend={'indicators': {'ema21': 104.5, 'ema50': 106.0}},
    )
    assert diag['market_location'] == 'FLOOR_DEMAND'
    assert diag['location_context'] == 'SHORT_EXTENDED_OR_AT_FLOOR'
    assert entry > 101.0
    assert diag['location_adjustment'] > 0


def test_long_at_ceiling_near_market_zone_is_penalized_before_timing_gate():
    dummy = _selector_dummy()
    entry, _, _, diag = dummy._select_optimal_entry(
        'long',
        {
            'supports': [112.0],
            'resistances': [121.0],
            'order_blocks': [{'type': 'bullish', 'price_range': [118.0, 118.5], 'strength': 'strong'}],
            'fair_value_gaps': [],
            'fib_retracements': {},
            'volume_profile': {},
        },
        120.0,
        120.0,
        {'atr': 5.0, 'bb_position': 0.85},
        '4h',
        market_type='futures',
        trend={'indicators': {'ema21': 112.1, 'ema50': 111.8}},
    )
    assert diag['market_location'] == 'CEILING_SUPPLY'
    assert diag['location_context'] == 'LONG_EXTENDED_OR_AT_CEILING'
    assert entry < 120.0
    assert diag['location_adjustment'] < 0
