from operational_intelligence import prepare_operational_intelligence


def layers(direction='bearish', weak=False):
    bear=direction=='bearish'
    d=direction
    out={
      'market_regime': {'regime':'TRENDING_BEAR' if bear else 'TRENDING_BULL'},
      'trend': {'direction':d,'adx':34,'plus_di':13 if bear else 32,'minus_di':32 if bear else 13},
      'momentum': {'direction':d,'rsi':38 if bear else 62,'macd_histogram':-1.2 if bear else 1.2,'divergences':[f'{d} regular']},
      'volume': {'volume_ratio':1.55,'obv_trend':d,'whale_sell_confirmed':bear,'whale_buy_confirmed':not bear},
      'structure': {'direction':d,'structure_direction':d,'order_blocks':[{'type':'bearish' if bear else 'bullish'}], 'fair_value_gaps':[{'type':'bearish' if bear else 'bullish'}]},
      'volatility': {'volatility_ratio':1.6,'bb_width':4.2,'bb_width_prev':3.4,'bb_position':0.12 if bear else .88,'squeeze_on':False,'operability':True,'atr_pct':2.1,'ftm_state':'EXPANSION'},
      'macro_context': {'bias':'neutral','risk_level':'NORMAL'}, 'liquidation': {'direction':'neutral'}
    }
    if weak:
        out['volume']={'volume_ratio':0.7,'obv_trend':'neutral'}
        out['structure']={'direction':'neutral'}
        out['volatility']={'volatility_ratio':1.0,'bb_width':2,'bb_width_prev':2,'bb_position':.5,'squeeze_on':False,'operability':True}
    return out


def mtf(desired='BEARISH', context='BULLISH', structure='BEARISH', setup='BEARISH', timing='BEARISH', conflict=True):
    def row(d, tf):
        return {'direction':d,'timeframes':[tf],'snapshots':[{'available':True,'timeframe':tf,'direction':d}]}
    return {'dominant_direction':desired,'alignment':'CONFLICT' if conflict else 'ALIGNED','conflict':conflict,'complete':not conflict,
            'public_summary':'synthetic','roles':{'context':row(context,'4H'),'structure':row(structure,'2H'),'setup':row(setup,'1H'),'timing':row(timing,'30M')}}


def run(sym='BTC-USDT', tf='1H', m=None, l=None):
    return prepare_operational_intelligence(layers=l or layers(),symbol=sym,timeframe=tf,system_type='FUTURES',mtf_context=m or mtf(),research_candidates={})

checks=[]
def check(label, cond):
    checks.append((label,bool(cond)))

x=run()
check('CORE context-only MTF lag may proceed', x['candidate_ready'] and x['candidate_action']=='SHORT')
check('transition exception is explicitly tagged', x.get('mtf_gate_mode')=='MTF_CONTEXT_LAG_TRANSITION_CONFIRMED')

x=run(m=mtf(structure='BULLISH'))
check('opposite structure still blocks', not x['candidate_ready'] and x.get('mtf_gate_mode')=='MTF_STRUCTURE_NOT_ALIGNED')

x=run(sym='SUI-USDT')
check('HIGH remains strict under MTF conflict', not x['candidate_ready'] and x.get('mtf_gate_mode')=='MTF_CONFLICT_STRICT_PROFILE')

x=run(m=mtf(context='BEARISH', conflict=False))
check('aligned crypto Futures unchanged', x['candidate_ready'] and x['candidate_action']=='SHORT')

x=run(sym='SPY-USDT',m=mtf(context='BEARISH', conflict=False))
check('Multi-Asset is a governed operational cell', x['official_cell'] and x.get('operational_segment')=='MULTIASSET')
check('aligned Multi-Asset autonomous thesis can proceed', x['candidate_ready'] and x['candidate_action']=='SHORT')
check('Multi-Asset delegates crypto playbook', (x.get('default_strategy') or {}).get('family')=='MULTIASSET_DELEGATED')

x=run(sym='SPY-USDT')
check('Multi-Asset MTF conflict remains strict', not x['candidate_ready'] and x.get('mtf_gate_mode')=='MTF_CONFLICT')

x=run(l=layers(weak=True))
check('weak evidence still cannot manufacture direction', not x['candidate_ready'])

bad=[label for label,ok in checks if not ok]
for label,ok in checks:
    print(('OK   ' if ok else 'FAIL ')+label)
print(f'PASS {len(checks)-len(bad)}/{len(checks)}')
if bad:
    raise SystemExit(1)
