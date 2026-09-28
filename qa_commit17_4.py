from operational_intelligence import (
    prepare_operational_intelligence, moderator_candidate, volatility_reasoning,
    market_objective_for, is_multiasset_cell, MULTIASSET_EXECUTION_TFS,
)
from default_strategy_bank import validate_bank


def layers(direction='bearish', weak=False, macro=None, vol=None):
    bear=direction=='bearish'; d=direction
    out={
      'market_regime': {'regime':'TRENDING_BEAR' if bear else 'TRENDING_BULL'},
      'trend': {'direction':d,'adx':34,'plus_di':13 if bear else 32,'minus_di':32 if bear else 13},
      'momentum': {'direction':d,'rsi':38 if bear else 62,'macd_histogram':-1.2 if bear else 1.2,'divergences':[f'{d} regular']},
      'volume': {'volume_ratio':1.55,'obv_trend':d,'whale_sell_confirmed':bear,'whale_buy_confirmed':not bear},
      'structure': {'direction':d,'structure_direction':d,'order_blocks':[{'type':'bearish' if bear else 'bullish'}], 'fair_value_gaps':[{'type':'bearish' if bear else 'bullish'}]},
      'volatility': vol or {'volatility_ratio':1.6,'bb_width':4.2,'bb_width_prev':3.4,'bb_position':0.12 if bear else .88,'squeeze_on':False,'operability':True,'atr_pct':2.1,'ftm_state':'EXPANSION'},
      'macro_context': macro or {'bias':'neutral','risk_level':'NORMAL','futures_posture':'NORMAL'},
      'liquidation': {'direction':'neutral'},
    }
    if weak:
        out['trend']={'direction':'neutral','adx':14,'plus_di':19,'minus_di':18}
        out['momentum']={'direction':'neutral','rsi':50,'macd_histogram':0,'divergences':[]}
        out['volume']={'volume_ratio':0.7,'obv_trend':'neutral'}
        out['structure']={'direction':'neutral'}
        out['volatility']={'volatility_ratio':1.0,'bb_width':2,'bb_width_prev':2,'bb_position':.5,'squeeze_on':False,'operability':True}
    return out


def mtf_crypto(desired='BEARISH', context=None, structure=None, setup=None, timing=None, conflict=False):
    context=context or desired; structure=structure or desired; setup=setup or desired; timing=timing or desired
    def row(d,tf): return {'direction':d,'timeframes':[tf],'snapshots':[{'available':True,'timeframe':tf,'direction':d}]}
    return {'dominant_direction':desired,'alignment':'CONFLICT' if conflict else 'ALIGNED','conflict':conflict,'complete':not conflict,
            'public_summary':'synthetic crypto','roles':{'context':row(context,'4H'),'structure':row(structure,'2H'),'setup':row(setup,'1H'),'timing':row(timing,'30M')}}


def mtf_multi(desired='BEARISH', conflict=False):
    def row(d,tf): return {'direction':d,'timeframes':[tf],'snapshots':[{'available':True,'timeframe':tf,'direction':d}]}
    return {'dominant_direction':desired,'alignment':'CONFLICT' if conflict else 'ALIGNED','conflict':conflict,'complete':not conflict,
            'public_summary':'synthetic multi','roles':{'context':row(desired,'1D'),'structure':row(desired,'4H'),'setup':row(desired,'1H'),'timing':row(desired,'1H')}}


def run(sym='BTC-USDT',tf='1H',m=None,l=None,research=None):
    return prepare_operational_intelligence(layers=l or layers(),symbol=sym,timeframe=tf,system_type='FUTURES',mtf_context=m or mtf_crypto(),research_candidates=research or {})

checks=[]
def ck(label,cond): checks.append((label,bool(cond)))

# 1) Existing strategy/indicator contract remains valid.
va=validate_bank()
ck('39/39 strategy bank remains valid', va.get('ok') is True)

# 2) Multi-Asset is truly first-class and timeframe contract matches runtime.
ck('Multi-Asset governed TF contract is exactly 1H/4H/1D', MULTIASSET_EXECUTION_TFS=={'1H','4H','1D'})
ck('SPY 1H is governed Multi-Asset cell', is_multiasset_cell('FUTURES','SPY-USDT','1H','SHORT'))
ck('SPY 30M is not falsely governed', not is_multiasset_cell('FUTURES','SPY-USDT','30M','SHORT'))

# 3) Strong crypto and Multi-Asset directional states can reach candidate stage.
for sym,tf in [('BTC-USDT','1H'),('LINK-USDT','1H'),('SUI-USDT','1H')]:
    x=run(sym=sym,tf=tf)
    ck(f'{sym} strong bearish thesis remains executable candidate', x['candidate_ready'] and x['candidate_action']=='SHORT')
for sym,tf in [('SPY-USDT','1H'),('CL-USDT','4H'),('XAG-USDT','1D')]:
    x=run(sym=sym,tf=tf,m=mtf_multi())
    ck(f'{sym} early Multi-Asset strategy exists', x['candidate_ready'] and x['candidate_action']=='SHORT' and x['default_strategy']['family'] not in {'NONE','MULTIASSET_DELEGATED'})
    ck(f'{sym} market segment is Multi-Asset', x['operational_segment']=='MULTIASSET')

# 4) Weak evidence still cannot manufacture direction.
x=run(l=layers(weak=True))
ck('weak evidence still produces no candidate', not x['candidate_ready'])

# 5) Macro critical becomes higher bar, not blanket veto; imminent event remains hard hold.
critical=layers(macro={'risk_level':'CRITICAL','futures_posture':'NORMAL','bias':'neutral'})
x=run(l=critical)
ck('generic CRITICAL macro does not erase strong thesis', x['candidate_ready'] and not x['context']['macro_reasoning']['hard_block_new_entry'])
ck('generic CRITICAL macro raises quality requirement', x['adaptive_quality_min'] > x['autonomous_thesis_min_quality'])
event=layers(macro={'risk_level':'CRITICAL','futures_posture':'NO_NEW_TRADES','bias':'neutral'})
x=run(l=event)
ck('imminent macro event still blocks new entry', (not x['candidate_ready']) and 'IMMINENT_UNMODELLED_MACRO_EVENT' in x['candidate_blockers'])

# 6) Research negative evidence needs enough N to be hard authority.
small_neg={'SHORT':{'state':'NEGATIVE_OOS','penalty_score':25,'best_negative':{'oos_n':3,'oos_exp_r':-0.8}}}
x=run(research=small_neg)
ck('small-N negative research is advisory not hard block', x['candidate_ready'] and not x['research_blocks_selected_action'])
robust_neg={'SHORT':{'state':'NEGATIVE_OOS','penalty_score':30,'best_negative':{'oos_n':25,'oos_exp_r':-0.3}}}
x=run(research=robust_neg)
ck('robust negative OOS can hard block exact action', (not x['candidate_ready']) and x['research_blocks_selected_action'])

# 7) Specialist committee is evidence, not a mandatory directional permission.
x=run()
empty_votes=[{'accion':'NO_OPERAR','confianza':72},{'accion':'PRECAUCION','confianza':71}]
mod=moderator_candidate(x,empty_votes,'FUTURES')
ck('exceptionally strong thesis can proceed with non-directional specialists', mod.get('use') is True and mod.get('action')=='SHORT')
# Opposing specialists still challenge materially.
opp=[{'accion':'LONG','confianza':90},{'accion':'LONG','confianza':88},{'accion':'LONG','confianza':86}]
mod=moderator_candidate(x,opp,'FUTURES')
ck('three strong opposite specialists force precaution', (not mod.get('use')) and mod.get('action')=='PRECAUCION')

# 8) Relative volatility beats one-size-fits-all absolute thresholds.
vr_us=volatility_reasoning({'atr_pct':1.5,'volatility_ratio':1.0,'bb_width':2,'bb_width_prev':2},market='FUTURES',symbol='SPY-USDT',timeframe='1H')
vr_energy=volatility_reasoning({'atr_pct':1.5,'volatility_ratio':1.0,'bb_width':2,'bb_width_prev':2},market='FUTURES',symbol='NATGAS-USDT',timeframe='1H')
ck('same ATR% can mean different volatility by asset class', vr_us['state'] != vr_energy['state'])
vr_rel=volatility_reasoning({'atr_pct':0.5,'volatility_ratio':1.45,'bb_width':1.8,'bb_width_prev':1.4},market='FUTURES',symbol='BTC-USDT',timeframe='1H')
ck('relative expansion can override low absolute ATR', vr_rel['state']=='EXPANSION')

# 9) Spot objective is explicit before strategy/execution.
ck('BTC Spot objective is snowball satoshis+USDT', 'SATOSHIS_AND_USDT' in market_objective_for('SPOT','BTC-USDT'))
ck('PAXG/BTC Spot objective is relative rotation', 'ROTATE_BTC_GOLD' in market_objective_for('SPOT','PAXG-BTC'))

# 10) Resource contract: reasoning adds no external work.
x=run(sym='SPY-USDT',tf='1H',m=mtf_multi())
rp=x.get('resource_policy') or {}
ck('17.4 reasoning adds zero network calls', rp.get('extra_network_calls')==0)
ck('17.4 reasoning adds zero DB writes', rp.get('extra_db_writes')==0)
ck('17.4 reasoning adds zero LLM calls', rp.get('extra_llm_calls')==0)
ck('17.4 reasoning adds zero workers', rp.get('extra_workers')==0)

bad=[label for label,ok in checks if not ok]
for label,ok in checks: print(('OK   ' if ok else 'FAIL ')+label)
print(f'PASS {len(checks)-len(bad)}/{len(checks)}')
if bad:
    print('FAILED:',bad)
    raise SystemExit(1)
