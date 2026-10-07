from safety_profiles_commit31 import evaluate_safety, select_profile, audit


def base_levels(rr=2.0):
    return {
        'entry_score': 82,
        'sl_reliability': 0.78,
        'tp_quality_score': 72,
        'risk_reward': rr,
        'minimum_viable_rr': 1.5,
        'maximum_technical_rr': 4.5,
    }


def test_architecture_has_exactly_eight_safeties_and_no_universal_score_gate():
    a = audit()
    assert a['profile_count'] == 8
    assert a['universal_score_threshold'] is None
    assert a['highest_score_selection_forbidden'] is True


def test_directional_impulse_selected_before_score_and_adx_does_not_veto():
    r = evaluate_safety(
        levels=base_levels(1.8),
        trend={'direction':'bearish','adx':17.7,'plus_di':9.5,'minus_di':42.2},
        momentum={'direction':'bearish','rsi':23.9},
        volatility={'volume_ratio':2.82,'volatility_state':'HIGH'},
        structure={'structure_direction':'bearish','order_blocks':[1],'fair_value_gaps':[1],'liquidity_sweeps':[1]},
        action='SHORT', symbol='BTC-USDT', timeframe='30m', market_type='futures',
    )
    assert r['profile'] == 'DIRECTIONAL_IMPULSE'
    assert r['score_is_hard_gate'] is False
    assert r['ready'] is True
    assert r['components']['trend'] >= 60


def test_liquidity_reversal_selected_for_sweep_mss_poi():
    levels=base_levels()
    levels['setup_family']='LIQUIDITY_SWEEP_MSS_POI'
    r=select_profile(
        levels=levels, trend={'direction':'bullish','adx':22}, momentum={'direction':'bullish'}, volatility={},
        structure={'liquidity_sweeps':[1], 'mss':True, 'order_blocks':[1]}, action='LONG', symbol='ETH-USDT', timeframe='30m', market_type='futures')
    assert r['profile']=='LIQUIDITY_REVERSAL'


def test_pullback_and_breakout_are_distinct_profiles():
    p=select_profile(levels={**base_levels(),'setup_family':'TREND_PULLBACK'}, trend={'direction':'bullish','adx':27}, momentum={'direction':'bullish'}, volatility={}, structure={}, action='LONG', symbol='ETH-USDT', timeframe='2h', market_type='futures')
    b=select_profile(levels={**base_levels(),'setup_family':'BREAKOUT_RETEST'}, trend={'direction':'bullish','adx':27}, momentum={'direction':'bullish'}, volatility={'squeeze_on':True}, structure={'displacement':True}, action='LONG', symbol='ETH-USDT', timeframe='2h', market_type='futures')
    assert p['profile']=='TREND_PULLBACK'
    assert b['profile']=='BREAKOUT_EXPANSION'


def test_multiasset_asset_class_is_modifier_not_automatic_safety():
    # QQQ in a normal trend should use the trend profile; being Multi-Asset alone
    # must not force EVENT_SESSION.
    r=select_profile(levels=base_levels(), trend={'direction':'bullish','adx':28}, momentum={'direction':'bullish'}, volatility={'session':'US'}, structure={}, action='LONG', symbol='QQQ-USDT', timeframe='4h', market_type='multiasset')
    assert r['profile']=='TREND_CONTINUATION'
    assert r['bucket']=='US_INDEX'


def test_explicit_multiasset_event_uses_event_session_safety():
    r=select_profile(levels={**base_levels(),'setup_family':'POST_EVENT_TREND'}, trend={'direction':'bearish','adx':23}, momentum={'direction':'bearish'}, volatility={'session':'US'}, structure={}, action='SHORT', symbol='CL-USDT', timeframe='1h', market_type='multiasset')
    assert r['profile']=='EVENT_SESSION'
    assert r['bucket']=='ENERGY'


def test_missing_optional_evidence_is_reweighted_not_zeroed():
    r=evaluate_safety(levels=base_levels(), trend={'direction':'bullish','adx':28}, momentum={'direction':'bullish'}, volatility={}, structure={'order_blocks':[1], 'structure_direction':'bullish'}, action='LONG', symbol='ETH-USDT', timeframe='2h', market_type='futures')
    assert r['components']['flow'] is None
    assert r['components']['mtf'] is None
    assert r['evidence_coverage'] < 1.0
    assert r['score'] > 0


def test_bad_sl_is_non_compensatory_even_with_good_other_components():
    lv=base_levels(); lv['sl_reliability']=0.35
    r=evaluate_safety(levels=lv, trend={'direction':'bullish','adx':30}, momentum={'direction':'bullish'}, volatility={}, structure={'order_blocks':[1], 'fair_value_gaps':[1], 'structure_direction':'bullish'}, action='LONG', symbol='ETH-USDT', timeframe='2h', market_type='futures')
    assert r['ready'] is False
    assert any(x.startswith('SL_BELOW') for x in r['critical_failures'])


def test_score_can_be_below_old_75_without_being_a_magic_gate():
    lv={'entry_score':66,'sl_reliability':0.62,'tp_quality_score':56,'risk_reward':1.8,'minimum_viable_rr':1.5,'maximum_technical_rr':4.5,'setup_family':'TREND_PULLBACK'}
    r=evaluate_safety(levels=lv, trend={'direction':'bullish','adx':22}, momentum={'direction':'bullish'}, volatility={}, structure={'order_blocks':[1], 'structure_direction':'bullish'}, action='LONG', symbol='ETH-USDT', timeframe='2h', market_type='futures')
    assert r['publication_score_threshold'] is None
    assert r['score_is_hard_gate'] is False


def _publication_result(*, legacy_safety=60.0, route=True, fallback=False, sl_loss=4.0, atr_stress=10.0):
    levels={
        'entry':100.0,'stop_loss':98.0,'take_profit':104.0,'risk_reward':2.0,
        'entry_score':82.0,'sl_reliability':0.78,'tp_quality_score':72.0,
        'execution_safety':legacy_safety,'minimum_viable_rr':1.6,'maximum_technical_rr':4.5,
        'risk_control':{'estimated_sl_loss_pct_margin':sl_loss,'estimated_atr_stress_loss_pct_margin':atr_stress},
        'manual_geometry_fallback':fallback,
    }
    if route:
        levels['commit19_champion']={'champion_id':'ETH_2H_LONG_RSI_TREND_V1','eligible_for_execution_routing':True}
    return {
        'analysis_mode':'CLOSED_CANDLE','source_candle_closed':True,'market_data_is_synthetic':False,
        'decision':{'action':'LONG'},'levels':levels,
        'trend':{'direction':'bullish','adx':28,'plus_di':30,'minus_di':12},
        'momentum':{'direction':'bullish','rsi':58},
        'volatility':{'atr_pct':1.2,'state':'NORMAL'},
        'structure':{'direction':'bullish','order_blocks':[1],'fair_value_gaps':[1]},
    }


def test_publication_no_longer_requires_legacy_safety_75_or_q_ready():
    from contextual_quality_commit28 import evaluate_publication
    out=evaluate_publication(_publication_result(legacy_safety=60.0),symbol='ETH-USDT',timeframe='2h',quality={'quality_ready':False,'quality':{}})
    assert 'PREMIUM_SAFETY_BELOW_75' not in out['reason_codes']
    assert 'CONTEXTUAL_Q1_Q9_QUALITY_NOT_READY' not in out['reason_codes']
    assert out['legacy_safety_75_is_gate'] is False
    assert out['q1_q10_are_gates'] is False
    assert out['eligible'] is True


def test_hard_risk_and_route_authority_remain_mandatory():
    from contextual_quality_commit28 import evaluate_publication
    badrisk=evaluate_publication(_publication_result(sl_loss=12.0),symbol='ETH-USDT',timeframe='2h',quality={})
    assert badrisk['eligible'] is False and 'LOSS_AT_SL' in badrisk['reason_codes']
    noroute=evaluate_publication(_publication_result(route=False),symbol='ETH-USDT',timeframe='2h',quality={})
    assert noroute['eligible'] is False and 'NO_VALIDATED_LIVE_ROUTE' in noroute['reason_codes']
    fallback=evaluate_publication(_publication_result(fallback=True),symbol='ETH-USDT',timeframe='2h',quality={})
    assert fallback['eligible'] is False and 'FALLBACK_GEOMETRY_NOT_PUBLISHABLE' in fallback['reason_codes']


def test_deploy_targets_commit31_and_legacy_safety_gate_removed():
    from pathlib import Path
    root=Path(__file__).resolve().parent
    assert 'commit31_main_entrypoint:app' in (root/'Procfile').read_text(encoding='utf-8')
    assert 'commit31_main_entrypoint:app' in (root/'render.yaml').read_text(encoding='utf-8')
    fs=(root/'futures_system.py').read_text(encoding='utf-8')
    assert 'legacy_safety_gate_bypassed_by_commit31' in fs
    assert 'COMMIT 31 — LEGACY SAFETY YA NO ES VETO DE PUBLICACIÓN' in fs
    cq=(root/'contextual_quality_commit28.py').read_text(encoding='utf-8')
    assert 'SAFETY_PROFILE_NOT_READY' in cq
    assert 'CONTEXTUAL_Q1_Q9_QUALITY_NOT_READY' not in cq.split('def evaluate_publication',1)[1]


def test_new_safety_module_has_no_network_threads_or_db_dependencies():
    import ast
    from pathlib import Path
    root=Path(__file__).resolve().parent
    tree=ast.parse((root/'safety_profiles_commit31.py').read_text(encoding='utf-8'))
    banned={'requests','threading','subprocess','socket','supabase','flask'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for alias in node.names:
                assert alias.name.split('.')[0] not in banned
        elif isinstance(node,ast.ImportFrom):
            assert (node.module or '').split('.')[0] not in banned
