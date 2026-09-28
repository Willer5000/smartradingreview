import sys, types
from pathlib import Path
import pandas as pd

from operational_intelligence import prepare_operational_intelligence, _macro_reasoning
from contingency_strategy_engine import build_contingency_playbook
import ast

# Load only the pure _router_score function without importing Flask/app/futures_system.
_ma_src=Path('multiasset_system.py').read_text()
_ma_tree=ast.parse(_ma_src)
_router_node=next(n for n in _ma_tree.body if isinstance(n,ast.FunctionDef) and n.name=='_router_score')
_ns={'pd':pd,'Dict':dict}
exec(compile(ast.Module(body=[_router_node],type_ignores=[]),'multiasset_router_extract','exec'),_ns)
_router_score=_ns['_router_score']


def strong_layers(macro=None):
    d='bearish'
    return {
      'market_regime': {'regime':'TRENDING_BEAR'},
      'trend': {'direction':d,'adx':34,'plus_di':13,'minus_di':32},
      'momentum': {'direction':d,'rsi':38,'macd_histogram':-1.2,'divergences':['bearish regular']},
      'volume': {'volume_ratio':1.55,'obv_trend':d,'whale_sell_confirmed':True},
      'structure': {'direction':d,'structure_direction':d,'current_price':100.0,
                    'supports':[95,92], 'resistances':[102,105],
                    'order_blocks':[{'type':'bearish'}], 'fair_value_gaps':[{'type':'bearish'}]},
      'volatility': {'volatility_ratio':1.6,'bb_width':4.2,'bb_width_prev':3.4,'bb_position':0.12,'squeeze_on':False,'operability':True,'atr_pct':2.1,'ftm_state':'EXPANSION'},
      'macro_context': macro or {'bias':'neutral','risk_level':'NORMAL','futures_posture':'NORMAL'},
      'liquidation': {'direction':'neutral'},
      'market_hours': {'liquidity':'HIGH'},
      'sentiment': {}, 'confirmation': {}, 'time_factor': {},
    }


def mtf():
    def row(tf): return {'direction':'BEARISH','timeframes':[tf],'snapshots':[{'available':True,'timeframe':tf,'direction':'BEARISH'}]}
    return {'dominant_direction':'BEARISH','alignment':'ALIGNED','conflict':False,'complete':True,'public_summary':'qa',
            'roles':{'context':row('4H'),'structure':row('2H'),'setup':row('1H'),'timing':row('30M')}}

checks=[]
def ck(label, cond): checks.append((label, bool(cond)))

# 1) Contingency must not resurrect old blanket macro/research vetoes.
macro={'risk_level':'CRITICAL','futures_posture':'NORMAL','bias':'neutral'}
layers=strong_layers(macro)
research={'SHORT':{'state':'NEGATIVE_OOS','penalty_score':25,'best_negative':{'oos_n':3,'oos_exp_r':-0.8}}}
op=prepare_operational_intelligence(layers=layers,symbol='BTC-USDT',timeframe='1H',system_type='FUTURES',mtf_context=mtf(),research_candidates=research)
layers['operational_intelligence']=op
pb=build_contingency_playbook(layers=layers,symbol='BTC-USDT',timeframe='1H',system_type='FUTURES',committee_action='SHORT',committee_confidence=82,vote_record=[],research_prior=research['SHORT'])
ck('small-N negative + CRITICAL macro no longer downgraded by Contingency when Operational Intelligence approved', pb.get('effective_action')=='SHORT')
ck('contingency uses adaptive macro-safe semantics', (pb.get('gates') or {}).get('macro_safe') is True)
ck('contingency uses robust research semantics', (pb.get('gates') or {}).get('research_not_negative') is True)

# Robust negative evidence still blocks.
research2={'SHORT':{'state':'NEGATIVE_OOS','penalty_score':30,'best_negative':{'oos_n':25,'oos_exp_r':-0.3}}}
layers2=strong_layers()
op2=prepare_operational_intelligence(layers=layers2,symbol='BTC-USDT',timeframe='1H',system_type='FUTURES',mtf_context=mtf(),research_candidates=research2)
layers2['operational_intelligence']=op2
pb2=build_contingency_playbook(layers=layers2,symbol='BTC-USDT',timeframe='1H',system_type='FUTURES',committee_action='SHORT',committee_confidence=82,vote_record=[],research_prior=research2['SHORT'])
ck('robust negative OOS remains hard authority', pb2.get('effective_action')=='NO_OPERAR')

# 2) Multi-Asset session is contextual, not a veto.
mr=_macro_reasoning({'risk_level':'HIGH','futures_posture':'NORMAL','gate':'CAUTION','market_session':'UNDERLYING_CLOSED_OR_OFFHOURS','asset_class':'US_INDEX'}, segment='MULTIASSET')
ck('Multi-Asset offhours raises requirements', mr.get('quality_extra',0)>2 and mr.get('margin_extra',0)>0.15)
ck('Multi-Asset offhours is not a hard veto', not mr.get('hard_block_new_entry'))

# 3) Router can surface non-trend opportunity lanes using same OHLCV.
def frame(prices, vols=None):
    if vols is None: vols=[100.0]*len(prices)
    rows=[]
    for i,p in enumerate(prices):
        spread=max(0.15,abs(p)*0.002)
        rows.append({'timestamp':pd.Timestamp('2026-01-01',tz='UTC')+pd.Timedelta(hours=i),'open':p-spread*0.2,'high':p+spread,'low':p-spread,'close':p,'volume':vols[i]})
    return pd.DataFrame(rows)

trend_prices=[100+i*0.35 for i in range(72)]
trend=_router_score(frame(trend_prices,[100+i for i in range(72)]))
ck('router still recognizes trend/momentum lane', trend.get('router_lane') in {'TREND_MOMENTUM','EXPANSION_BREAKOUT'})

# Mostly balanced history followed by a sharp extension/reversal context.
mr_prices=[100 + (0.25 if i%2==0 else -0.25) for i in range(66)] + [101,103,105,107,109,108]
mr_vol=[100.0]*66+[110,120,150,180,220,260]
rev=_router_score(frame(mr_prices,mr_vol))
ck('router can prioritize a non-trend lane', rev.get('router_lane') in {'REVERSAL_MEAN_REVERSION','EXPANSION_BREAKOUT','COMPRESSION_RELEASE'})
ck('router exposes multiple lane scores for audit', len(rev.get('lane_scores') or {})==4)

# 4) Spot anti-FOMO no longer rewrites the confirmed direction.
app_text=Path('app.py').read_text()
ck('Spot anti-FOMO caller no longer assigns accion_consenso from final_action', "accion_consenso = str(\n                    spot_execution_quality.get" not in app_text)
ck('Spot anti-FOMO preserves executable signal with committee Entry', "levels['anti_fomo_advisory']" in app_text and "levels['publication_status'] = 'EXECUTABLE_SIGNAL'" in app_text)
ck('Spot freshness helper preserves final_action', "result['final_action'] = action_text" in app_text)

# 5) Multi-Asset macro context enters before layers/Operational Intelligence and Guardian reuses it.
ma_text=Path('multiasset_system.py').read_text()
ck('Multi-Asset exposes early macro override hook', 'def _market_macro_context_override' in ma_text)
ck('Multi-Asset macro packet includes session', "'market_session': _market_session(asset_class)" in ma_text)
ck('Multi-Asset Guardian requests class-specific cached macro', '_macro_context_for_asset as _ma_macro' in app_text)

bad=[x for x,ok in checks if not ok]
for label,ok in checks:
    print(('OK   ' if ok else 'FAIL ')+label)
print(f'PASS {len(checks)-len(bad)}/{len(checks)}')
if bad:
    print('FAILED:',bad)
    raise SystemExit(1)
