from contextual_quality_commit27 import evaluate_publication
from champion_registry_commit19 import resolve_champion


def quality(ready=True,score=80):
    return {'quality_ready':ready,'quality':{f'Q{i}':score for i in range(1,10)},'composite':score,'base_composite':score}

def base(symbol='BTC-USDT',action='LONG',route='F30_SHARED_LIQ_SWEEP_MSS_POI_V1',tf='30m'):
    return {
      'success':True,'analysis_mode':'CLOSED_CANDLE','source_candle_closed':True,'market_data_is_synthetic':False,
      'symbol':symbol,'timeframe':tf,'decision':{'action':action},
      'levels':{
        'entry':100,'stop_loss':99 if action=='LONG' else 101,'take_profit':102 if action=='LONG' else 98,
        'risk_reward':2.0,'execution_safety':80,
        'risk_control':{'estimated_sl_loss_pct_margin':4,'estimated_atr_stress_loss_pct_margin':12},
        'entry_quality_score':75,'sl_reliability':0.8,'tp_quality_score':75,
        'entry_sweep_confirmed':True,'entry_mss_bos_confirmed':True,'entry_source':'Order Block POI reaction',
        'commit19_champion':{'champion_id':route,'eligible_for_execution_routing':True,'source_type':'TEST'},
      }
    }

def test_f30_primary_validated_can_publish():
    a=evaluate_publication(base(),symbol='BTC-USDT',timeframe='30m',quality=quality())
    assert a['eligible'] is True
    assert a['movement_profile']['name']=='FUTURES_FAST_SWEEP_MSS_REACTION'

def test_fallback_never_publishes_even_with_perfect_q():
    r=base(); r['levels']['manual_geometry_fallback']=True
    a=evaluate_publication(r,symbol='BTC-USDT',timeframe='30m',quality=quality(score=100))
    assert a['eligible'] is False
    assert 'FALLBACK_GEOMETRY_NOT_PUBLISHABLE' in a['reason_codes']

def test_max_parallel_like_quality_cannot_rescue_native_quality_not_ready():
    a=evaluate_publication(base(),symbol='BTC-USDT',timeframe='30m',quality=quality(ready=False,score=100))
    assert a['eligible'] is False
    assert 'CONTEXTUAL_Q1_Q9_QUALITY_NOT_READY' in a['reason_codes']

def test_f30_structure_is_post_geometry_mandatory():
    r=base(); r['levels']['entry_sweep_confirmed']=False; r['levels']['entry_mss_bos_confirmed']=False; r['levels']['entry_displacement_confirmed']=False
    a=evaluate_publication(r,symbol='BTC-USDT',timeframe='30m',quality=quality())
    assert a['eligible'] is False
    assert 'F30_POST_GEOMETRY_STRUCTURE_MISSING' in a['reason_codes']

def test_multi_fast_quality_is_shadow_without_oos_route():
    r=base(symbol='CL-USDT',action='SHORT',route='',tf='4h')
    r['asset_class']='ENERGY'; r['is_multiasset']=True; r['market']='multiasset'
    r['levels'].pop('commit19_champion',None)
    a=evaluate_publication(r,symbol='CL-USDT',timeframe='4h',quality=quality())
    assert a['eligible'] is False
    assert a['publication_status']=='SHADOW_QUALITY_CANDIDATE'
    assert 'ENERGY_FAST_ROUTE_REQUIRES_OOS' in a['reason_codes']

def test_us_index_1d_exact_route_can_publish():
    r=base(symbol='QQQ-USDT',route='US_INDEX_1D_TREND_PULLBACK_RR18_V1',tf='1D')
    r['asset_class']='US_INDEX'; r['is_multiasset']=True; r['market']='multiasset'
    r['levels']['strategy_family']='TREND_PULLBACK'
    a=evaluate_publication(r,symbol='QQQ-USDT',timeframe='1D',quality=quality())
    assert a['eligible'] is True
    assert a['movement_profile']['name'].startswith('MULTI_US_INDEX')

def test_safety_75_is_not_lowered():
    r=base(); r['levels']['execution_safety']=74.99
    a=evaluate_publication(r,symbol='BTC-USDT',timeframe='30m',quality=quality())
    assert a['eligible'] is False
    assert 'PREMIUM_SAFETY_BELOW_75' in a['reason_codes']

def test_f30_preentry_router_no_longer_demands_postentry_structure():
    layers={
      'trend':{'direction':'bullish','adx':28},
      'momentum':{'direction':'bearish','rsi':55},  # opposite momentum no longer kills pooled 30m pre-entry
      'volume':{'volume_ratio':1.35},
      'structure':{},
    }
    op={'candidate_action':'LONG','thesis':{'action':'LONG'},'context':{'regime':'TREND_UP','volatility':'HIGH'}}
    route=resolve_champion(layers=layers,symbol='BTC-USDT',timeframe='30m',system_type='FUTURES',regime='TREND_UP',volatility='HIGH',mtf_relation={'usable':True,'state':'ALIGNED','dominant_direction':'bullish'},operational=op)
    assert route['eligible_for_execution_routing'] is True
    assert route['champion_id']=='F30_SHARED_LIQ_SWEEP_MSS_POI_V1'

def test_commit27_separates_q9_from_route_authority_without_lowering_quality_floor():
    q = quality(ready=False, score=80)
    q['quality']['Q9'] = 20
    q['commit27_nonstat_composite'] = 80
    q['commit27_quality_ready'] = True
    q['commit27_q9_role'] = 'STATISTICAL_GOVERNANCE_DIAGNOSTIC_ONLY'
    a = evaluate_publication(base(), symbol='BTC-USDT', timeframe='30m', quality=q)
    assert a['eligible'] is True
    assert a['quality_domains']['statistical_q9_diagnostic'] == 20
    assert a['quality_domains']['quality_ready'] is True
    assert a['route_authority']['live'] is True
