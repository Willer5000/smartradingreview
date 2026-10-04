import sys
import types
class DummyApp:
    def get(self, path):
        def deco(fn): return fn
        return deco

mod = types.ModuleType('app')
mod.app = DummyApp()

# Minimal current app contracts that 23.1 is supposed to reconcile.
def _classify_futures_analysis_result(symbol, timeframe, result, lifecycle=None, min_confidence=0):
    levels=result.get('levels') or {}
    status=str(levels.get('publication_status') or result.get('publication_status') or 'ANALYSIS_ONLY').upper()
    return {'classification': 'EXECUTABLE_SIGNAL' if status=='EXECUTABLE_SIGNAL' else 'ANALYSIS_ONLY', 'action': ((result.get('decision') or {}).get('action') or 'NO_TRADE')}

def _refresh_futures_signal_lifecycle(lifecycle, symbol, timeframe, result):
    out=dict(lifecycle or {})
    if result.get('publication_status')=='EXECUTABLE_SIGNAL':
        sid=result.get('signal_id') or 'S1'
        out[sid]={'symbol':symbol,'timeframe':timeframe,'lifecycle_status':'waiting_entry'}
    return out

def _futures_directional_hidden_candidates(visibility, source_context):
    return list((visibility or {}).get('candidates') or [])

def _get_futures_system():
    return None

mod._classify_futures_analysis_result=_classify_futures_analysis_result
mod._refresh_futures_signal_lifecycle=_refresh_futures_signal_lifecycle
mod._futures_directional_hidden_candidates=_futures_directional_hidden_candidates
mod._get_futures_system=_get_futures_system
sys.modules['app']=mod

import importlib.util
spec=importlib.util.spec_from_file_location('commit23_1_authority_runtime','/mnt/data/commit23_1_authority_runtime.py')
q=importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
q.install(mod.app)

base={
  'success': True,
  'symbol':'BTC-USDT','timeframe':'4h',
  'decision': {'action':'LONG','confidence':68},
  'levels': {
    'entry':83795.6,'stop_loss':82251.12,'take_profit':88107.87,
    'execution_safety':82,
    'risk_control':{'estimated_sl_loss_pct_margin':3.2,'estimated_atr_stress_loss_pct_margin':12.0},
    'publication_status':'ANALYSIS_ONLY','is_rejected':True,
  },
  'futures_publication_gate': {'stage':'PUBLICATION_GATE','reason_codes':['SAFETY','RR']},
  'quality_authority_version':'COMMIT23_TEN_FILTER_PARALLEL_AUTHORITY_V1',
  'quality_filter_authority':'Q4',
  'quality_filter_name':'SWEEP_MSS_RECLAIM',
  'quality_filter_score':84,
  'quality_filter_confirmed':True,
  'market_data_is_synthetic':False,
  'parallel_quality_guard_codes':[],
  'quality_filter_trace':{
      'version':'COMMIT23_TEN_FILTER_PARALLEL_AUTHORITY_V1',
      'selected_filter':'Q4','selected_filter_name':'SWEEP_MSS_RECLAIM',
      'selected_filter_score':84,'selected_filter_passed':True,
      'confirmed_one_of_ten':True,'passed_filters':['Q4','Q5'],
      'universal_guards':{'geometry_valid':True,'codes':[]},
  },
  'signal_id':'SIG1'
}

r=q.reconcile_final_quality_authority(base, symbol='BTC-USDT', timeframe='4h')
assert r['final_quality_authority']['confirmed'] is True
assert r['publication_status']=='EXECUTABLE_SIGNAL'
assert r['levels']['publication_status']=='EXECUTABLE_SIGNAL'

cls=mod._classify_futures_analysis_result('BTC-USDT','4h', dict(base), lifecycle={})
assert cls['classification']=='EXECUTABLE_SIGNAL', cls

life=mod._refresh_futures_signal_lifecycle({},'BTC-USDT','4h',dict(base))
assert life.get('SIG1',{}).get('lifecycle_status')=='waiting_entry', life

# Guard failure must never promote.
unsafe=dict(base)
unsafe['levels']=dict(base['levels'])
unsafe['levels']['risk_control']={'estimated_sl_loss_pct_margin':9.0,'estimated_atr_stress_loss_pct_margin':12.0}
r2=q.reconcile_final_quality_authority(unsafe)
assert r2['final_quality_authority']['confirmed'] is False
assert r2.get('publication_status') != 'EXECUTABLE_SIGNAL'
assert r2['final_quality_authority']['confirmed'] is False

# Dedupe must keep highest Q score for same cell.
wrapped=q._wrap_hidden_candidates(mod)
rows=mod._futures_directional_hidden_candidates({'candidates':[
    {'symbol':'BTC-USDT','timeframe':'4h','quality_filter_confirmed':True,'quality_filter_score':78,'confidence':90,'risk_reward':2.0},
    {'symbol':'BTC-USDT','timeframe':'4h','quality_filter_confirmed':True,'quality_filter_score':84,'confidence':68,'risk_reward':1.8},
    {'symbol':'ETH-USDT','timeframe':'4h','quality_filter_confirmed':False,'quality_filter_score':70,'confidence':99,'risk_reward':3.0},
]}, 'CURRENT_ANALYSIS_ONLY')
assert len(rows)==2
btc=next(x for x in rows if x['symbol']=='BTC-USDT')
assert btc['quality_filter_score']==84

print('COMMIT23.1 authority tests: PASS')
