from cohort_integrity import classify_quality_signal, futures_cell_active
from entry_reaction_engine import evaluate_entry_reaction
from hierarchical_committee import build_hierarchical_assessment
import research_evidence_fusion as ref


def vote(trader, action, conf=75):
    return {'trader': trader, 'accion': action, 'confianza': conf}


def test_rc4_high_tf_contract_is_only_btc_eth_sol():
    assert futures_cell_active('BTC-USDT', '12h')
    assert futures_cell_active('ETH-USDT', '1D')
    assert futures_cell_active('SOL-USDT', '12h')
    assert not futures_cell_active('XRP-USDT', '12h')
    assert not futures_cell_active('LINK-USDT', '1D')


def test_hierarchy_context_alone_cannot_make_trade_executable():
    result = build_hierarchical_assessment([
        vote('Macroeconomista', 'LONG', 90),
        vote('Multiframe', 'LONG', 85),
        vote('Cazador de Ballenas', 'LONG', 80),
    ], baseline_action='LONG', market='futures', timeframe='4h', symbol='BTC-USDT')
    assert result['quality_gate_passed'] is False
    assert result['recommended_action'] == 'ESPERAR'


def test_hierarchy_independent_setup_execution_can_confirm():
    result = build_hierarchical_assessment([
        vote('Técnico Puro', 'LONG', 75),
        vote('Smart Money', 'LONG', 82),
        vote('Multiframe', 'LONG', 65),
        vote('Escéptico', 'ESPERAR', 40),
    ], baseline_action='LONG', market='futures', timeframe='4h', symbol='ETH-USDT')
    assert result['quality_gate_passed'] is True
    assert result['recommended_action'] == 'LONG'


def test_entry_reaction_futures_is_stricter_and_high_tf_requires_trigger():
    levels = {
        'entry_source': 'Order Block alcista', 'entry_smc_raw_score': 80,
        'entry_reachability_score': 90, 'entry_defensibility_score': 78,
        'entry_liquidity_pool_near': True, 'entry_sweep_confirmed': True,
        'entry_mss_bos_confirmed': True, 'entry_displacement_confirmed': True,
        'entry_distance_atr': 0.8,
    }
    fut = evaluate_entry_reaction(levels, timeframe='12h', market_type='futures')
    spot = evaluate_entry_reaction(levels, timeframe='12h', market_type='spot')
    assert fut['passed'] is True
    assert fut['lower_tf_confirmation_required'] is True
    assert fut['status'] == 'ZONE_VALID_LOWER_TF_TRIGGER_REQUIRED'
    assert fut['threshold'] > spot['threshold']


def test_cohort_integrity_separates_unverified_futures():
    base = {'system_type':'futures','symbol':'BTC-USDT','timeframe':'4h','context':{'learning':{}}}
    assert classify_quality_signal(base)['official'] is False
    clean = {'system_type':'futures','symbol':'BTC-USDT','timeframe':'4h','context':{'learning':{
        'cohort':'FUTURES_PERPETUAL_REAL_CLOSED_V1',
        'market_data_source':'KUCOIN_FUTURES_PERPETUAL_REST',
        'market_data_is_synthetic':False,'source_candle_closed':True,
        'evaluation_role':'EXECUTABLE_SIGNAL','statistically_eligible':True,
    }}}
    assert classify_quality_signal(clean)['cohort'] == 'OFFICIAL_CURRENT_FUTURES'


def test_research_fusion_accepts_only_valid_high_tf_cells():
    row = {'scope': {'market_family':'CRYPTO_FUTURES','symbol':'BTC-USDT','timeframe':'12H'}}
    bad = {'scope': {'market_family':'CRYPTO_FUTURES','symbol':'XRP-USDT','timeframe':'12H'}}
    assert ref._canonical_cell_key(row) == 'FUTURES|BTC-USDT|12H'
    assert ref._canonical_cell_key(bad) is None
    assert ref._COVERAGE_TARGET == 46
