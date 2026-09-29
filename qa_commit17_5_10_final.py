from __future__ import annotations

import ast
import hashlib
import importlib
import os
from pathlib import Path
import sys
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app.py'
SOURCE = APP.read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
sys.path.insert(0, str(ROOT))

PASS = []

def ok(name, cond=True):
    assert cond, name
    PASS.append(name)
    print(f'PASS {len(PASS):02d} - {name}')


def load_functions(names, env=None):
    ns = dict(env or {})
    wanted = set(names)
    nodes = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
    missing = wanted - {n.name for n in nodes}
    assert not missing, missing
    for n in nodes:
        n.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), 'exec'), ns)
    return ns


def constant(name):
    for node in TREE.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)

# 1-2 compile / lineage
import py_compile
for name in ('app.py','execution_specialist_committees.py','preliminary_backtest_prior.py','worker_orchestration.py','market_maker_math.py','options_market_context.py','profitability_qualification.py','backtest_commit17_5_10_profitability.py'):
    py_compile.compile(str(ROOT/name), doraise=True)
ok('py_compile functional files')

worker_source=(ROOT/'worker_orchestration.py').read_text(encoding='utf-8')
ok('worker orchestration remains non-voting and now exposes MM math as a tool',
   'WORK_PRODUCT_ONLY' in worker_source and 'market_maker_math_is_tool_not_vote' in worker_source
   and 'options_gex_cannot_create_direction' in worker_source)

# 3-5 MTF provider boundary
ns = load_functions({'_operational_mtf_provider_timeframe'})
maptf = ns['_operational_mtf_provider_timeframe']
ok('MTF aliases intraday canonicalized', [maptf(x) for x in ('30M','1H','2H','4H','12H')] == ['30m','1h','2h','4h','12h'])
ok('MTF daily/weekly labels preserved', [maptf(x) for x in ('1D','1W')] == ['1D','1W'])
requested=[]
class FakeAnalyzer:
    def _prepare_closed_candle_analysis_data(self,symbol,tf):
        requested.append(tf); return {'success':True,'closed_df':[0]*100}
    def analyze_trend_layer(self,df): return {'direction':'bullish'}
    def analyze_momentum_layer(self,df): return {'direction':'bullish'}
    def analyze_volume_layer(self,df,tf): return {'volume_ratio':1.2}
    def analyze_price_structure_layer(self,df,tf,symbol): return {'direction':'bullish'}
ns = load_functions({'_operational_mtf_provider_timeframe','_get_operational_mtf_peer_minimal'}, {
    'time':time,'threading':threading,'_OPERATIONAL_MTF_MINIMAL_CACHE':{},
    '_OPERATIONAL_MTF_MINIMAL_LOCK':threading.Lock(),'_OPERATIONAL_MTF_MINIMAL_TTL':300.0,
})
with patch.dict(sys.modules, {'multiasset_system':SimpleNamespace(MULTIASSET_SYMBOLS={})}):
    row=ns['_get_operational_mtf_peer_minimal'](FakeAnalyzer(),'BTC-USDT','4H','futures')
ok('MTF provider receives 4h while internal row remains 4H', requested==['4h'] and row and row['timeframe']=='4H')

# 6-9 leverage is diagnostic, never standalone publication veto
ns = load_functions({'_derivative_premium_leverage_ok','_entry_evidence_class','_apply_17_5_7_backtest_evidence_policy'}, {
    '_DERIVATIVE_PREMIUM_MIN_LEVERAGE': constant('_DERIVATIVE_PREMIUM_MIN_LEVERAGE'),
    '_BACKTEST_EVIDENCE_POLICY_VERSION': constant('_BACKTEST_EVIDENCE_POLICY_VERSION'),
})
for lev in (1,2,3,4,8,31):
    sig={'success':True,'decision':{'action':'LONG','confidence':82},'publication_status':'EXECUTABLE_SIGNAL','publication_eligible':True,
         'levels':{'entry':100.0,'stop_loss':98.0,'take_profit':104.0,'leverage':lev,'publication_status':'EXECUTABLE_SIGNAL','is_executable':True},
         'futures_publication_gate':{'eligible':True,'tier':'PREMIUM','reasons':[],'reason_codes':[]}}
    out=ns['_apply_17_5_7_backtest_evidence_policy'](sig,'futures')
    assert out['levels']['publication_status']=='EXECUTABLE_SIGNAL'
    assert out['levels']['entry']==100.0 and out['levels']['stop_loss']==98.0 and out['levels']['take_profit']==104.0 and out['levels']['leverage']==lev
ok('x1-x3 and higher leverage preserve otherwise executable publication')
ok('leverage never raised to pass publication', '_DERIVATIVE_PREMIUM_MIN_LEVERAGE = int' not in SOURCE and "levels['leverage'] = int(_DERIVATIVE_PREMIUM_MIN_LEVERAGE)" not in SOURCE)
legacy={'decision':{'action':'LONG','confidence':80},'publication_status':'ANALYSIS_ONLY','publication_eligible':False,
        'levels':{'entry':100,'stop_loss':98,'take_profit':104,'leverage':2,'publication_status':'ANALYSIS_ONLY','is_rejected':True,'low_leverage_product_fit_gate':True},
        'futures_publication_gate':{'eligible':False,'tier':'ANALYSIS_ONLY','reasons':['low leverage'],'reason_codes':['LOW_LEVERAGE_PRODUCT_FIT'],'backtest_evidence_policy_version':'17.5.7_BACKTEST_EVIDENCE_V1'}}
healed=ns['_apply_17_5_7_backtest_evidence_policy'](legacy,'futures')
ok('legacy low-leverage-only rejection can be healed', healed['levels']['publication_status']=='EXECUTABLE_SIGNAL' and healed['publication_eligible'] is True)
safety={'decision':{'action':'LONG','confidence':80},'publication_status':'ANALYSIS_ONLY','publication_eligible':False,
        'levels':{'entry':100,'stop_loss':98,'take_profit':104,'leverage':2,'publication_status':'ANALYSIS_ONLY','is_rejected':True},
        'futures_publication_gate':{'eligible':False,'tier':'ANALYSIS_ONLY','reasons':['Safety'],'reason_codes':['SAFETY','LOW_LEVERAGE_PRODUCT_FIT'],'backtest_evidence_policy_version':'17.5.7_BACKTEST_EVIDENCE_V1'}}
not_healed=ns['_apply_17_5_7_backtest_evidence_policy'](safety,'futures')
ok('Safety/TP/SL/RR rejection cannot be healed by leverage policy', not_healed['levels']['publication_status']=='ANALYSIS_ONLY' and not_healed['publication_eligible'] is False)

# 10-13 SL locality regression
committees=importlib.import_module('execution_specialist_committees')
for direction,sl,level in (('long',98.0,50.0),('short',102.0,150.0)):
    st={'pivot_lows' if direction=='long' else 'pivot_highs':[{'price':level,'strength':3}]}
    out=committees.evaluate_sl_reaction_conflict(structure=st,direction=direction,entry=100.0,stop_loss=sl,atr=1.0)
    assert out['conflict'] is False
ok('distant 48 ATR structure no longer vetoes LONG/SHORT SL')
for direction,sl,level in (('long',98.0,97.8),('short',102.0,102.2)):
    st={'pivot_lows' if direction=='long' else 'pivot_highs':[{'price':level,'strength':3}]}
    out=committees.evaluate_sl_reaction_conflict(structure=st,direction=direction,entry=100.0,stop_loss=sl,atr=1.0)
    assert out['conflict'] is True and out['distance_atr'] < 0.3
ok('near strong reaction still vetoes LONG/SHORT SL')
probe=committees.evaluate_sl_reaction_conflict(structure={'pivot_lows':[{'price':97.8,'strength':3}]},direction='long',entry=100.0,stop_loss=98.0,atr=1.0)
ok('SL guard only diagnoses and proposes no replacement stop', not any(k in probe for k in ('new_stop','replacement_stop','adjusted_stop_loss')))
ok('recovery geometry engine still present', 'def recover_execution_geometry_from_structure' in (ROOT/'execution_specialist_committees.py').read_text())

# 14-17 priors are shadow-only and Spot action contract fixed
prior=importlib.import_module('preliminary_backtest_prior')
p1=prior.family_cell_prior(market='spot',symbol='PAXG-USDT',timeframe='1D',action='LONG',family='RSI_TREND')
ok('Spot LONG maps to COMPRA_SPOT historical key', p1['available'] is True and p1['adjustment']==0.0 and p1['shadow_adjustment']>0)
p2=prior.family_cell_prior(market='futures',symbol='SOL-USDT',timeframe='1H',action='SHORT',family='RSI_TREND')
ok('Futures selected family prior is neutral LIVE but visible SHADOW', p2['available'] and p2['adjustment']==0.0 and p2['shadow_adjustment']>0)
ep=prior.entry_component_prior(timeframe='30m',candidate_family='liquidity',smc_events=2,market='futures',symbol='BTC-USDT')
tp=prior.tp_component_prior(timeframe='30m',candidate_rr=2.5)
ok('Entry/TP historical boosts are shadow-only', ep['adjustment']==0.0 and ep['shadow_adjustment']>0 and tp['adjustment']==0.0 and tp['shadow_adjustment']>0)
ok('selected historical priors cannot reorder LIVE Futures scanning', prior.futures_scan_priority('SOL-USDT','1H')==0.0 and 'futures_scan_priority' not in SOURCE)

# 18-20 Multi-Asset fair queue and resource deferral
queue_names={'_multiasset_bucket','_multiasset_queue_ttl_seconds','_multiasset_enqueue_due','_multiasset_prune_pending','_multiasset_pop_completed_pending','_multiasset_background_tick'}
base_env={
    'os':os,'datetime':datetime,'timezone':timezone,'time':time,'threading':threading,
    '_MULTI_AUTO_LOCK':threading.Lock(),'_MULTI_ROUTER_STATE_LOCK':threading.Lock(),
    '_MULTI_AUTO_DAILY':{},'_MULTI_AUTO_DONE':set(),'_MULTI_DEEP_RETRY':{},'_MULTI_CLOSE_REFRESHED':set(),
    '_MULTI_ROUTER_STATE':{},'_MULTI_FAST_LANE_MIN_SCORE':82.0,'_MULTI_DAILY_CONTEXT_EXTRA_MAX':2,
    '_MULTI_PENDING_QUEUE':[],'_MULTI_PENDING_KEYS':set(),'_MULTI_PENDING_EXPIRED':0,'_MULTI_PENDING_RESOURCE_DEFERRALS':0,
    '_multiasset_close_plan':lambda now:{tf:{'due':tf=='1h','key':tf} for tf in ('1h','4h','1D')},
    '_multiasset_close_refresh_done':lambda key:False,'_multiasset_mark_close_refresh':lambda key:None,
    '_multiasset_retry_ready':lambda *a:True,'_multiasset_is_executable':lambda r:False,
    '_multiasset_compact_telegram':lambda r:False,
}
scan_rows=[{'symbol':'CL-USDT','router_score':90.0,'deep_candidate':True},{'symbol':'XAG-USDT','router_score':89.0,'deep_candidate':True}]
analyses=[]
env=dict(base_env)
env['_multiasset_scan']=lambda tf,force=False: scan_rows if tf=='1h' else []
env['_multiasset_run_analysis']=lambda symbol,tf,owner: (analyses.append((symbol,tf)) or {'success':True,'symbol':symbol,'timeframe':tf})
ns=load_functions(queue_names,env)
with patch.dict(sys.modules, {'multiasset_system':SimpleNamespace(MULTIASSET_DEEP_LIMIT=2,MULTIASSET_AUTO_DEEP_DAILY_MAX=12)}), patch.dict(os.environ, {'MULTIASSET_ENABLED':'1'}):
    ns['_multiasset_background_tick'](); ns['_multiasset_background_tick']()
ok('Multi 1h fair queue gives second high-quality candidate a turn', analyses==[('CL-USDT','1h'),('XAG-USDT','1h')])
ok('Multi remains sequential one-deep-analysis per scheduler tick', len(analyses)==2)
# resource cap: queue must remain pending, not marked done
analyses2=[]; env=dict(base_env); env.update({
    '_MULTI_AUTO_LOCK':threading.Lock(), '_MULTI_ROUTER_STATE_LOCK':threading.Lock(),
    '_MULTI_AUTO_DAILY':{'day':datetime.now(timezone.utc).strftime('%Y-%m-%d'),'count':12,'context_count':0,'fast_count':0},
    '_MULTI_AUTO_DONE':set(), '_MULTI_DEEP_RETRY':{}, '_MULTI_CLOSE_REFRESHED':set(),
    '_MULTI_ROUTER_STATE':{}, '_MULTI_PENDING_QUEUE':[], '_MULTI_PENDING_KEYS':set(),
    '_MULTI_PENDING_EXPIRED':0, '_MULTI_PENDING_RESOURCE_DEFERRALS':0,
})
env['_multiasset_scan']=lambda tf,force=False: scan_rows if tf=='1h' else []
env['_multiasset_run_analysis']=lambda symbol,tf,owner: (analyses2.append((symbol,tf)) or {'success':True})
ns2=load_functions(queue_names,env)
with patch.dict(sys.modules, {'multiasset_system':SimpleNamespace(MULTIASSET_DEEP_LIMIT=2,MULTIASSET_AUTO_DEEP_DAILY_MAX=12)}), patch.dict(os.environ, {'MULTIASSET_ENABLED':'1'}):
    ns2['_multiasset_background_tick']()
ok('Multi resource cap defers rather than silently consuming candidate', not analyses2 and len(ns2['_MULTI_PENDING_QUEUE'])==2 and len(ns2['_MULTI_AUTO_DONE'])==0 and ns2['_MULTI_PENDING_RESOURCE_DEFERRALS']>=1)

# 21-24 durable Telegram outbox retry/dedup
outbox_names={'_compact_confirmed_outbox_signal','_confirmed_outbox_enqueue','_attempt_confirmed_outbox_event','_retry_confirmed_signal_outbox'}
sends=[]
class Expert:
    def __init__(self): self.result=False
    def send_telegram_alert(self,*a,**k): sends.append(1); return self.result
expert=Expert()
out_env={
    'time':time,'threading':threading,'_CONFIRMED_SIGNAL_OUTBOX_RETENTION':172800,
    '_confirmed_signal_outbox':{},'_confirmed_signal_outbox_lock':threading.Lock(),
    '_confirmed_signal_alerts_sent':{},'_confirmed_signal_alerts_lock':threading.Lock(),
    '_save_confirmed_signal_outbox_to_disk':lambda:True,'_save_confirmed_signal_alerts_to_disk':lambda:True,
    '_confirmed_signal_preferences_allow':lambda m,t:True,'_confirmed_signal_recent_enough':lambda s,t:True,
    '_build_confirmed_signal_telegram_message':lambda m,s:'msg','expert_system':expert,
}
ns=load_functions(outbox_names,out_env)
sig={'symbol':'BTC-USDT','timeframe':'1h','decision':{'action':'LONG','confidence':80},'levels':{'entry':100,'stop_loss':98,'take_profit':104,'leverage':2,'publication_status':'EXECUTABLE_SIGNAL'},'publication_status':'EXECUTABLE_SIGNAL','source_candle_timestamp':'2026-09-29T00:00:00Z'}
ns['_confirmed_outbox_enqueue']('futures',sig,'k1')
assert ns['_attempt_confirmed_outbox_event']('k1') is False
ok('Telegram transport failure remains FAILED_RETRYABLE', ns['_confirmed_signal_outbox']['k1']['state']=='FAILED_RETRYABLE' and len(sends)==1)
ns['_confirmed_signal_outbox']['k1']['next_retry_at']=0; expert.result=True
ok('Telegram pending confirmation retries and reaches SENT', ns['_attempt_confirmed_outbox_event']('k1') is True and ns['_confirmed_signal_outbox']['k1']['state']=='SENT' and len(sends)==2)
ns['_attempt_confirmed_outbox_event']('k1')
ok('Telegram SENT outbox is deduplicated', len(sends)==2)
# stale authorization/freshness fails closed
ns['_confirmed_signal_outbox']['k2']={'key':'k2','market':'futures','signal':sig,'state':'PENDING','attempts':0,'created_at':time.time(),'updated_at':time.time(),'next_retry_at':0,'last_error':None}
ns['_confirmed_signal_recent_enough']=lambda s,t:False
assert ns['_attempt_confirmed_outbox_event']('k2') is False
ok('stale Telegram event expires instead of backfilling', ns['_confirmed_signal_outbox']['k2']['state']=='EXPIRED_OR_SUPERSEDED' and len(sends)==2)

# 25-27 quality gates were not retuned in this patch
ok('17.5.10 does not ship futures_system threshold changes', not (ROOT/'futures_system.py').exists())
ok('no new daily signal quota introduced', 'SIGNAL_DAILY_MAX' not in SOURCE and 'TELEGRAM_DAILY_MAX' not in SOURCE)
ok('worker evidence remains worker-product architecture', 'WORK_PRODUCT_ONLY' in (ROOT/'worker_orchestration.py').read_text())



# 28-31 profitability qualification: incremental scope only
pq=importlib.import_module('profitability_qualification')
qualified={
    'system_type':'futures','timeframe':'30m','symbol':'BTC-USDT',
    'decision':{'action':'LONG','confidence':82},
    'indicators':{'adx':24,'volume_ratio':1.5,'rsi':60,'trend_direction':'bullish'},
    'levels':{'entry':100,'stop_loss':98,'take_profit':104,'leverage':2,
              'publication_status':'EXECUTABLE_SIGNAL','is_executable':True,
              'entry_sweep_confirmed':True,'entry_mss_bos_confirmed':True,
              'entry_liquidity_pool_near':True,'entry_source':'Liquidity POI'},
    'publication_status':'EXECUTABLE_SIGNAL','is_executable':True,
}
q=pq.qualify_result(qualified,market='futures')
ok('profitability qualifier recognizes frozen profitable 30m route', q['qualified'] is True and q['checks']['volume_ratio_gte_1_2'])
weak={**qualified,'indicators':{'adx':24,'volume_ratio':0.8,'rsi':60,'trend_direction':'bullish'}}
ok('profitability qualifier rejects weak-volume incremental scope', pq.qualify_result(weak,market='futures')['qualified'] is False)
nsq=load_functions({'_estimate_mm_volatility','_apply_17_5_10_profitability_market_maker_context'}, {
    '_PROFITABILITY_QUALIFIER_VERSION':'17.5.10_PROFITABILITY_QUALIFIED_V1',
    '_MM_CONTEXT_VERSION':'17.5.10_MM_MATH_V1',
    '_DERIVATIVE_PREMIUM_MIN_LEVERAGE':4,
})
qout=nsq['_apply_17_5_10_profitability_market_maker_context'](qualified,'futures')
ok('qualified low-leverage signal is not blocked solely by leverage', qout['levels']['publication_status']=='EXECUTABLE_SIGNAL')
wout=nsq['_apply_17_5_10_profitability_market_maker_context'](weak,'futures')
ok('profitability evidence is diagnostic and cannot re-veto an executable signal',
   wout['levels']['publication_status']=='EXECUTABLE_SIGNAL'
   and wout['levels']['profitability_qualification_is_publication_gate'] is False
   and wout['levels']['profitability_qualification_authority']=='DIAGNOSTIC_SHADOW_ONLY')

# 32-36 Black-Scholes / Greeks / GEX model invariants
mm=importlib.import_module('market_maker_math')
call=mm.black_scholes_greeks(spot=100,strike=100,t_years=1/365,volatility=.50,option_type='CALL')
put=mm.black_scholes_greeks(spot=100,strike=100,t_years=1/365,volatility=.50,option_type='PUT')
ok('Black-Scholes deltas have correct signs and gamma is positive', 0<call['delta']<1 and -1<put['delta']<0 and call['gamma']>0 and abs(call['gamma']-put['gamma'])<1e-12)
# simple 0DTE-ish observed chain
asof=datetime(2026,9,29,6,0,tzinfo=timezone.utc)
chain=[
 {'strike':98,'expiry':'2026-09-29T08:00:00+00:00','option_type':'PUT','iv':55,'open_interest':150},
 {'strike':100,'expiry':'2026-09-29T08:00:00+00:00','option_type':'CALL','iv':50,'open_interest':200},
 {'strike':100,'expiry':'2026-09-29T08:00:00+00:00','option_type':'PUT','iv':50,'open_interest':180},
 {'strike':102,'expiry':'2026-09-29T08:00:00+00:00','option_type':'CALL','iv':55,'open_interest':170},
]*3
ctx=mm.aggregate_gamma_exposure(chain,spot=100,as_of=asof)
ok('observed option chain produces finite gamma walls, 0DTE share and compact curves',
   ctx['available'] and ctx['zero_dte_gamma_share']>0.99 and ctx['gamma_wall'] is not None
   and len(ctx.get('gex_curve') or [])>=11 and len(ctx.get('delta_curve') or [])>=11)
ok('GEX context cannot create direction or bypass Safety', ctx['can_create_direction'] is False and ctx['can_bypass_safety'] is False and ctx['production_score_adjustment']==0)
theo=mm.build_market_maker_context(spot=100,option_chain=[],realized_or_implied_volatility=.5,as_of=asof)
ok('no observed chain falls back to theoretical shadow only', theo['observed_option_chain'] is False and theo['authority']=='SHADOW_THEORETICAL_ONLY')
opt=importlib.import_module('options_market_context')
parsed=opt._normalize_summary_rows([
 {'instrument_name':'BTC-29SEP26-100-C','open_interest':100,'mark_iv':50,'volume':2},
 {'instrument_name':'BTC-29SEP26-100-P','open_interest':120,'mark_iv':52,'volume':3},
],now=asof)
ok('Deribit summary parser extracts near-expiry OI/IV without ticker fanout', len(parsed)==2 and all(r['open_interest']>0 for r in parsed))

# 37-39 execution desk carries MM context but does not score it
ctx2=committees.build_execution_context(structure={},volume={'volume_ratio':1.2},volatility={'atr':1},market_maker_context=ctx,symbol='BTC-USDT',timeframe='30m',market_type='futures')
ok('execution context carries market-maker math as worker tool', ctx2['market_maker_context'].get('gamma_regime')==ctx.get('gamma_regime'))
entry_weights=committees._weights_for('entry','futures')
ok('market-maker context has zero direct committee weight in 17.5.10', 'market_maker' not in entry_weights)

# 40-42 offline row-level backtest must remain profitable under stress in both periods
import subprocess, json
raw=subprocess.check_output([sys.executable,str(ROOT/'backtest_commit17_5_10_profitability.py')],text=True)
bt=json.loads(raw)
ok('development cohort is positive after unresolved=-1R and modeled cost stress', bt['IN_SAMPLE_DEVELOPMENT']['net_stress_r']>0 and bt['IN_SAMPLE_DEVELOPMENT']['profit_factor_stress']>1)
ok('chronological holdout is positive after same stress', bt['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['net_stress_r']>0 and bt['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['profit_factor_stress']>1)
ok('combined stressed backtest is profitable', bt['COMBINED']['net_stress_r']>0)


# 43-50 FINAL frontend / direct-underlying / anti-overfit / policy integrity
frontend_path=(ROOT/'static'/'market_maker_frontend.js') if (ROOT/'static'/'market_maker_frontend.js').exists() else (ROOT/'market_maker_frontend.js')
index_path=(ROOT/'templates'/'index.html') if (ROOT/'templates'/'index.html').exists() else (ROOT/'index.html')
frontend=frontend_path.read_text(encoding='utf-8')
index=index_path.read_text(encoding='utf-8')
ok('frontend adds conventional Black-Scholes/Gamma/Delta/0DTE indicator card',
   'mm-options-chart' in index and 'Opciones · Gamma / Delta / 0DTE' in index and 'market_maker_frontend.js' in index)
ok('frontend indicator is display-only and hooks existing analysis payload',
   'updateAllCharts' in frontend and 'fetch(' not in frontend and 'runCompleteAnalysis' not in frontend)

import subprocess
subprocess.check_call(['node','--check',str(frontend_path)])
ok('market_maker_frontend.js passes node syntax check')
try:
    from jinja2 import Environment
    Environment().parse(index)
    _jinja_ok=True
except Exception:
    _jinja_ok=False
ok('modified index.html parses as Jinja template', _jinja_ok)

opt=importlib.import_module('options_market_context')
ok('observed Deribit option chain is used only for directly matching BTC/ETH underlyings',
   opt._currency_for_symbol('BTC-USDT')=='BTC' and opt._currency_for_symbol('ETH-USDT')=='ETH'
   and opt._currency_for_symbol('SOL-USDT') is None and opt._currency_for_symbol('XRP-USDT') is None)
alt=opt.get_crypto_option_chain('SOL-USDT')
ok('altcoin does not receive false BTC strike/GEX projection',
   alt.get('available') is False and alt.get('direct_underlying_match') is False
   and alt.get('reason')=='NO_DIRECT_OPTION_UNDERLYING_FOR_SYMBOL')

app_source=SOURCE
ok('profitability backtest remains evidence, not a quantity/publication quota',
   "profitability_qualification_is_publication_gate'] = False" in app_source
   and 'SIGNAL_DAILY_MAX' not in app_source and 'TELEGRAM_DAILY_MAX' not in app_source)

# V6 remains a baseline dependency rather than being rewritten in this commit.
import json
base=json.loads((ROOT/'BASELINE_DEPENDENCIES_17_5_10.json').read_text(encoding='utf-8'))
ok('leverage V6 baseline is frozen and expected to select technical maximum',
   base['leverage_policy.py']['modified_by_17_5_10'] is False
   and base['leverage_policy.py']['expected_policy_version']=='RC9_7_14_STANDARD_TECHNICAL_MAX_LEVERAGE_V6'
   and base['leverage_policy.py']['selection_policy']=='STANDARD_TECHNICAL_MAX_V6')

# 51-54 backtest anti-overfit diagnostics
raw=subprocess.check_output([sys.executable,str(ROOT/'backtest_commit17_5_10_profitability.py')],text=True)
bt=json.loads(raw)
ok('IN-SAMPLE development is profitable under -1R unresolved + 0.118R cost stress',
   bt['IN_SAMPLE_DEVELOPMENT']['net_stress_r']>0 and bt['IN_SAMPLE_DEVELOPMENT']['profit_factor_stress']>1)
ok('OUT-OF-SAMPLE chronological holdout is profitable under identical stress',
   bt['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['net_stress_r']>0
   and bt['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['profit_factor_stress']>1)
ok('backtest explicitly refuses a profitability guarantee and marks OOS as non-prospective',
   bt['release_acceptance']['profitability_guarantee'] is False
   and bt['method']['oos_type']=='CHRONOLOGICAL_HOLDOUT_NOT_PROSPECTIVE_LIVE')

stability=json.loads((ROOT/'BACKTEST_PARAMETER_STABILITY_17_5_10.json').read_text(encoding='utf-8'))
positive_both=sum(1 for row in stability if float(row.get('dev_net_stress_r') or 0)>0 and float(row.get('holdout_net_stress_r') or 0)>0)
ok('parameter-neighbourhood test is disclosed instead of hiding unstable neighbours',
   len(stability)>=7 and positive_both>=4 and any(float(row.get('dev_net_stress_r') or 0)<0 for row in stability))

print(f'QA_17_5_10_FINAL: {len(PASS)}/{len(PASS)} PASS')

