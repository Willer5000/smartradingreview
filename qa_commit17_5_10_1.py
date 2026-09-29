from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
BASE = (Path('/mnt/data/c175101') / 'app.py').read_text(encoding='utf-8') if Path('/mnt/data/c175101/app.py').exists() else ''
MMJS = (ROOT / 'static' / 'market_maker_frontend.js').read_text(encoding='utf-8')
HTML = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
OPT = (ROOT / 'options_market_context.py').read_text(encoding='utf-8')

passed=[]

def check(name, cond, detail=''):
    if not cond:
        raise AssertionError(f'{name}: {detail}')
    passed.append(name)

# --- pure helper tests with a stub Multi-Asset bank ---
stub = types.ModuleType('multiasset_system')
stub.MULTIASSET_SYMBOLS = {
    'CL-USDT': {'asset_class':'ENERGY'},
    'SPY-USDT': {'asset_class':'US_INDEX'},
}
stub.MULTIASSET_STRATEGY_BANK = {
    'ENERGY':['SWEEP_MSS_POI','TREND_PULLBACK','BREAKOUT_RETEST','COMPRESSION_EXPANSION','POST_EVENT_CONFIRMATION','VOLATILITY_RETEST'],
    'US_INDEX':['SWEEP_MSS_POI','VWAP_SESSION_PULLBACK','BREAKOUT_RETEST','COMPRESSION_EXPANSION','TREND_PULLBACK','POST_MACRO_CONFIRMATION','MEAN_REVERSION_SELECTIVE'],
}
sys.modules['multiasset_system'] = stub
from pipeline_integrity_175101 import (
    PIPELINE_GENERATION, VERSION, reconcile_operational_candidate,
    profitability_hard_block_authority, stamp_pipeline_generation,
)

layers = {
    'trend': {'direction':'bullish','adx':34},
    'momentum': {'rsi':58},
    'volatility': {'atr_pct':1.4},
    'volume': {'volume_ratio':1.45},
    'structure': {
        'events':['liquidity_sweep','MSS','displacement','order_block'],
        'order_blocks':[{'type':'bullish'}],
    },
    'confirmation': {'retest':True},
    'macro_context': {'risk_level':'LOW'},
}
base_multi = {
    'thesis': {
        'direction':'BULLISH','action':'LONG','quality':86,
        'independent_support_families':['trend','structure','momentum','volume'],
        'required_independent_families':4,'macro_risk':'LOW',
    },
    'default_strategy': {'id':'MULTIASSET_DELEGATED_PLAYBOOK','family':'MULTIASSET_DELEGATED','quality':0},
    'multi_timeframe': {'conflict':False}, 'mtf_usable':True,
    'candidate_ready':False,'candidate_action':'NO_OPERAR','candidate_source':'NONE',
    'official_cell':True,'autonomous_thesis_min_quality':82,
    'research_blocks_selected_action':False,
}
rec = reconcile_operational_candidate(base_multi,layers=layers,symbol='CL-USDT',timeframe='4h',system_type='futures')
check('multi strategy participates pre-candidate', rec['default_strategy']['family'] != 'MULTIASSET_DELEGATED')
check('multi strategy has live quality', float(rec['default_strategy']['quality']) >= 78, rec['default_strategy'])
check('multi candidate can be built without lowering threshold', rec['candidate_ready'] is True)
check('multi strategy threshold remains 78', float(rec['multiasset_strategy_threshold_unchanged']) == 78.0)

neutral = dict(base_multi)
neutral['thesis'] = dict(base_multi['thesis'], direction='NEUTRAL', action='NO_OPERAR', quality=68)
rec_neutral = reconcile_operational_candidate(neutral,layers=layers,symbol='CL-USDT',timeframe='4h',system_type='futures')
check('multi strategy never creates direction from neutral thesis', rec_neutral['candidate_ready'] is False)

# Crypto stale research: same technical thresholds, no early historical veto.
crypto = {
    'thesis': {
        'direction':'BULLISH','action':'LONG','quality':84,
        'independent_support_families':['trend','structure','momentum','volume'],
        'required_independent_families':4,'macro_risk':'LOW',
    },
    'default_strategy': {'id':'X','family':'TREND_PULLBACK','quality':83,'regime_match':True,'volatility_match':True},
    'multi_timeframe': {'conflict':False}, 'mtf_usable':True,
    'candidate_ready':False,'candidate_action':'NO_OPERAR','candidate_source':'NONE',
    'official_cell':True,'autonomous_thesis_min_quality':82,
    'research_blocks_selected_action':True,
    'research_candidates': {'LONG': {'state':'REJECTED_OOS'}},
    'selected_specialist_source':'THESIS',
}
rec_crypto = reconcile_operational_candidate(crypto,layers=layers,symbol='BTC-USDT',timeframe='30m',system_type='futures')
check('old research is counter evidence pre-candidate', rec_crypto.get('stale_research_softened') is True)
check('old research no longer erases otherwise-valid crypto candidate', rec_crypto.get('candidate_ready') is True)

# Generation-aware alpha decay authority.
check('old negative OOS cannot hard-veto new generation', profitability_hard_block_authority({'state':'NEGATIVE_EDGE_VETO','block_new_signal':True})['allowed'] is False)
check('old alpha decay cannot hard-veto without current forward cohort', profitability_hard_block_authority({'state':'ALPHA_DECAY_VETO','block_new_signal':True,'best_diverged':{'recent8_n':8,'shadow_updated_at':'2026-09-18T00:00:00+00:00'}})['allowed'] is False)
check('current forward alpha decay can regain hard authority', profitability_hard_block_authority({'state':'ALPHA_DECAY_VETO','block_new_signal':True,'best_diverged':{'recent8_n':8,'shadow_updated_at':'2026-09-29T12:45:00+00:00'}})['allowed'] is True)

stamped=stamp_pipeline_generation({'levels':{},'context':{}})
check('pipeline generation stamped top-level', stamped['pipeline_generation']==PIPELINE_GENERATION)
check('pipeline generation stamped learning context', stamped['context']['learning']['pipeline_generation']==PIPELINE_GENERATION)

# --- source-level invariants in app.py ---
def func_text(name, next_marker='\ndef '):
    start=APP.index(f'def {name}')
    end=APP.find(next_marker,start+5)
    return APP[start:] if end<0 else APP[start:end]

bg=func_text('_multiasset_background_tick()')
retry=func_text('_multiasset_record_retry(bucket, error)')
risk=func_text('_apply_96_futures_risk_policy(result, symbol, timeframe)')
edge=func_text('_apply_profitability_router(result, symbol, timeframe)')
mmapply=func_text("_apply_17_5_10_profitability_market_maker_context(result, market='futures')")

check('Multi all 1h router rows enter due queue', "for r in rows_1h" in bg and "r.get('deep_candidate')" not in bg)
check('Multi 1h score >=82 removed as eligibility', '_MULTI_FAST_LANE_MIN_SCORE' not in bg)
check('Multi top2 deep limit removed from scheduler', 'MULTIASSET_DEEP_LIMIT' not in bg)
check('Multi 12/day hard budget removed from scheduler', 'MULTIASSET_AUTO_DEEP_DAILY_MAX' not in bg)
check('Multi has RAM/network backpressure', '_multiasset_resource_backpressure' in bg)
check('Multi failures are never marked DONE', '_MULTI_AUTO_DONE.add' not in retry)
check('Multi retry state is explicit runtime failure', "'state': 'RUNTIME_FAILED'" in retry)
check('HIGH no-data is not bad-liquidity veto', 'HIGH_REQUIRES_MICROSTRUCTURE' not in risk and 'NO_DATA_IS_NOT_NEGATIVE_EVIDENCE' in risk)
check('objective poor microstructure still blocks', 'LIQUIDITY_EXECUTION_RISK' in risk)
check('stale edge veto becomes counter evidence', 'edge_counter_evidence' in edge and 'block_new_signal_effective' in edge)
check('profitability router cache minimum raised', 'PROFITABILITY_ROUTER_MIN_CACHE_SECONDS' in edge and "'1800'" in edge)
check('automatic options fetch requires directional candidate', '_directional_candidate' in mmapply and "and _directional_candidate" in mmapply)
check('pipeline-integrity diagnostics endpoint exists', "/api/diagnostics/pipeline-integrity" in APP)
check('market-maker lightweight endpoint exists', "/api/futures/market-maker-context" in APP)
check('runtime snapshot readback health exists', '_RUNTIME_PERSISTENCE_VERIFY_STATE' in APP and 'READBACK_OK' in APP)
check('template exclusion spam is opt-in', 'TRADING_VERBOSE_TEMPLATE_DIAGNOSTICS' in APP)
check('stack extraction remains diagnostic-only', '_verbose_template_diag' in APP and 'traceback.extract_stack()' in APP)

# No extra background thread added versus exact 17.5.10 baseline.
if BASE:
    check('no additional threads introduced', APP.count('threading.Thread(') == BASE.count('threading.Thread('), (APP.count('threading.Thread('),BASE.count('threading.Thread(')))

# --- Market-maker math / frontend ---
from market_maker_math import black_scholes_greeks, build_market_maker_context
c=black_scholes_greeks(spot=100,strike=100,t_years=1/365,volatility=.6,option_type='CALL')
p=black_scholes_greeks(spot=100,strike=100,t_years=1/365,volatility=.6,option_type='PUT')
check('Black-Scholes call delta positive', c['delta']>0)
check('Black-Scholes put delta negative', p['delta']<0)
check('Black-Scholes gamma positive', c['gamma']>0 and p['gamma']>0)
check('Black-Scholes vega available', c['vega']>0)
check('Black-Scholes theta available', 'theta_per_day' in c)
ctx=build_market_maker_context(spot=100,option_chain=[],realized_or_implied_volatility=.6)
check('MM aggregate exposes Vega', 'aggregate_vega_per_iv_point' in ctx)
check('MM aggregate exposes Theta', 'aggregate_theta_per_day' in ctx)
check('MM aggregate exposes ATM Greeks', 'representative_atm_greeks' in ctx)
check('MM context remains non-directional', ctx.get('can_create_direction') is False)

for field in ['mm-delta-dollar','mm-gex-total','mm-vega','mm-theta','mm-atm-call','mm-atm-put']:
    check(f'frontend field {field}', field in HTML and field in MMJS)
check('frontend directly reads lightweight context endpoint', '/api/futures/market-maker-context' in MMJS)
check('frontend has no polling interval', 'setInterval(' not in MMJS)
check('options provider cache default one hour', '"3600"' in OPT)

# Critical untouched domains are not shipped/replaced by this commit.
check('futures_system not in ready-change source set', not (ROOT/'futures_system.py').exists())
check('leverage_policy not in ready-change source set', not (ROOT/'leverage_policy.py').exists())

# 17.5.10 profitability evidence remains unchanged and positive IS/OOS.
res=json.loads((ROOT/'BACKTEST_17_5_10_1_RECHECK.json').read_text())
check('IS remains profitable', res['IN_SAMPLE_DEVELOPMENT']['net_stress_r']>0)
check('OOS chronological holdout remains profitable', res['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['net_stress_r']>0)
check('backtest still declares no guarantee', res['release_acceptance']['profitability_guarantee'] is False)

print(f'PASS {len(passed)}/{len(passed)}')
for i,name in enumerate(passed,1): print(f'{i:02d}. PASS — {name}')
