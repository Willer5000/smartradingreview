from pathlib import Path

from entry_reaction_engine import evaluate_entry_reaction

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUT = (ROOT / 'futures_system.py').read_text(encoding='utf-8')


def _levels(distance_atr):
    return {
        'entry_smc_raw_score': 82,
        'entry_reachability_score': 88,
        'entry_defensibility_score': 78,
        'entry_distance_atr': distance_atr,
        'entry_source': 'Order Block alcista',
        'entry_liquidity_pool_near': True,
        'entry_sweep_confirmed': True,
        'entry_mss_bos_confirmed': True,
        'entry_displacement_confirmed': True,
    }


def test_one_hour_near_market_entry_requires_30m_trigger():
    out = evaluate_entry_reaction(_levels(0.25), timeframe='1h', market_type='futures')
    assert out['lower_tf_confirmation_required'] is True


def test_one_hour_limit_pullback_does_not_wait_for_touch_before_publication():
    out = evaluate_entry_reaction(_levels(0.90), timeframe='1h', market_type='futures')
    assert out['lower_tf_confirmation_required'] is False


def test_futures_lower_tf_map_supports_1h_to_30m():
    assert "'1h': '30m'" in FUT
    assert "decision.get('action')" not in FUT


def test_entry_reaction_failure_is_publication_block_not_only_extreme_hard_block():
    assert "if (not entry_reaction.get('passed', False))" in FUT
    assert "RC9_7_14_ENTRY_REACTION_NOT_CONFIRMED" in FUT


def test_futures_has_atr_aware_anti_chase_timing_gate():
    assert ("RC9_7_14_FUTURES_TIMING_GATE_V1" in FUT or "RC9_7_15_FUTURES_LOCATION_TIMING_V2" in FUT)
    assert "WAIT_PULLBACK_LONG_EXTENDED" in FUT
    assert "FUTURES_ENTRY_TIMING_WAIT" in FUT
    assert "waits_for_pullback" in FUT


def test_spot_reachability_is_stronger_but_still_structure_first():
    assert "smc_weight, reach_weight = 0.82, 0.18" in APP


def test_poi_confluence_recomputes_actual_ranking_score():
    marker = "Confluence is part of the causal POI quality"
    assert marker in APP
    block = APP[APP.index(marker):APP.index(marker)+700]
    assert "candidate['_entry_quality_score']" in block
    assert "candidate['_smc_score'] * smc_weight" in block


def test_antichase_price_change_regrades_entry_instead_of_reusing_old_poi_score():
    assert "price_adjusted_by_anti_chase" in APP
    assert "original_selected_entry" in APP
    assert "smc_raw = min(60.0" in APP
