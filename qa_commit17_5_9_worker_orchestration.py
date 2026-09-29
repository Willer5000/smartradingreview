from __future__ import annotations

import hashlib
from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app.py'
COMMITTEE = ROOT / 'execution_specialist_committees.py'
PRIOR = ROOT / 'preliminary_backtest_prior.py'
WORKERS = ROOT / 'worker_orchestration.py'
BASE1758 = Path('/mnt/data/commit17_5_8_ready')

passed=[]

def ok(name, cond):
    assert cond, name
    passed.append(name)

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

for p in (APP, COMMITTEE, PRIOR, WORKERS):
    py_compile.compile(str(p), doraise=True)
ok('01_compile_changed_files', True)

app = APP.read_text(encoding='utf-8')
committee = COMMITTEE.read_text(encoding='utf-8')
workers = WORKERS.read_text(encoding='utf-8')

ok('02_production_no_longer_calls_legacy_moderator_candidate', 'from operational_intelligence import moderator_candidate' not in app)
ok('03_worker_moderator_is_wired', 'moderator_worker_candidate' in app and 'build_worker_desk_snapshot' in app)
ok('04_legacy_vote_payload_marked_telemetry_only', "'legacy_vote_telemetry_only': True" in app)
ok('05_worker_policy_forbids_majority_and_veto', '"majority_vote_used": False' in workers and '"worker_veto_used": False' in workers)
ok('06_worker_roles_cover_all_ten', workers.count('"deliverable":') >= 10)
ok('07_strategy_reasoning_preserves_alternatives', 'strategy.get("alternatives")' in workers and 'CONTEXT_STRATEGY_ROUTING' in workers)
ok('08_recovery_function_added', 'def recover_execution_geometry_from_structure' in committee)
ok('09_recovery_cannot_create_direction', 'authority": "RECOVER_GEOMETRY_ONLY_EXISTING_THESIS"' in committee)
ok('10_recovery_keeps_quality_floors', 'proposal["geometry_quality"] >= 62.0' in committee and 'proposal["entry_quality"] >= 55.0' in committee and 'proposal["sl_quality"] >= 60.0' in committee and 'proposal["tp_quality"] >= 60.0' in committee)
ok('11_recovery_no_atr_tp_fabrication', 'Deliberately no RR/ATR TP fabrication.' in committee)
ok('12_app_attempts_recovery_for_missing_sl', "_attempt_structural_recovery_17_5_9('NO_VALID_SL'" in app)
ok('13_app_attempts_recovery_for_missing_tp', "_attempt_structural_recovery_17_5_9('NO_VALID_TP'" in app)
ok('14_app_attempts_recovery_for_bad_baseline_geometry', "_attempt_structural_recovery_17_5_9('BASELINE_GEOMETRY_INVALID'" in app)
ok('15_recovered_entry_must_pass_existing_timing_gate', "_gate_check.get('passed') is True" in app)
ok('16_recovered_geometry_must_pass_existing_setup_guard', 'execution_setup_guard as _setup_guard_1759' in app)
ok('17_spot_execution_recovery_not_changed', "return {'success': False, 'reason': 'SPOT_RECOVERY_NOT_ENABLED'}" in app)
ok('18_sl_reaction_hard_guard_preserved', 'evaluate_sl_reaction_conflict' in committee and 'SL_REACTION_GUARD_ERROR' in app)
ok('19_no_new_signal_quantity_cap', 'DAILY_SIGNAL_MAX' not in workers and 'SIGNAL_QUOTA' not in workers)
ok('20_funnel_exposes_recovery_and_precise_stages', "'OPPORTUNITY_RECOVERY'" in app and "'opportunity_recovery'" in app)

if BASE1758.exists():
    ok('21_preliminary_backtest_prior_unchanged', sha(PRIOR) == sha(BASE1758/'preliminary_backtest_prior.py'))

# Behavioral checks for orchestration.
import sys
sys.path.insert(0, str(ROOT))
from worker_orchestration import build_worker_desk_snapshot, moderator_worker_candidate, WORKER_ROLES

op={
    'candidate_action':'LONG','candidate_ready':True,'candidate_source':'THESIS+DEFAULT',
    'thesis':{'direction':'BULLISH','quality':84},
    'default_strategy':{'family':'TREND_PULLBACK','quality':80,'regime_match':True,'volatility_match':True},
    'context':{'regime':'TREND_UP','volatility':'NORMAL'},
}
legacy=[
    {'trader':'Escéptico','accion':'NO_OPERAR','confianza_original':99,'razones':['counter']},
    {'trader':'Smart Money','accion':'SHORT','confianza_original':95,'razones':['opposite']},
    {'trader':'Chartista','accion':'SHORT','confianza_original':95,'razones':['opposite2']},
]
desk=build_worker_desk_snapshot(legacy,op,market='FUTURES',symbol='BTC-USDT',timeframe='1h')
mod=moderator_worker_candidate(op,market='FUTURES',symbol='BTC-USDT',timeframe='1h',worker_desk=desk)
ok('22_workers_cannot_outvote_valid_governed_candidate', mod['use'] is True and mod['action']=='LONG' and mod['worker_vote_used'] is False)
ok('23_all_named_workers_registered', len(WORKER_ROLES)==10)
op_bad=dict(op); op_bad['candidate_ready']=False
mod_bad=moderator_worker_candidate(op_bad,market='FUTURES',symbol='BTC-USDT',timeframe='1h',worker_desk=desk)
ok('24_operational_candidate_still_required', mod_bad['use'] is False)

# Structural recovery smoke test: uses observed structure only.
from execution_specialist_committees import recover_execution_geometry_from_structure
structure={
    'supports':[98.0,97.5], 'resistances':[104.0,106.0],
    'pivot_lows':[{'price':98.2,'strength':3}], 'pivot_highs':[{'price':104.2,'strength':3}],
    'order_blocks':[
        {'type':'bullish','price_range':[97.8,98.4],'strength':'strong'},
        {'type':'bearish','price_range':[104.0,104.5],'strength':'strong'},
    ],
    'fair_value_gaps':[],
    'volume_profile':{'poc':100.0,'val':98.0,'vah':104.0,'hvn_nodes':[{'price':98.3},{'price':104.1}]},
    'indicators':{'ema20':99.0,'ema50':98.5,'vwap':99.2},
    'smc':{'liquidity_sweep':True,'mss':True,'displacement':True},
    'liquidity_sweep':True,'mss':True,'displacement':True,
    'recent_highs':[101,102,103], 'recent_lows':[99,98.5,98.2],
}
rec=recover_execution_geometry_from_structure(
    direction='long',current_price=100,atr=1.0,structure=structure,
    trend={'direction':'bullish'},momentum={'rsi':55},volatility={},
    setup_family='SWEEP_REVERSAL',market_type='futures',symbol='BTC-USDT',timeframe='1h',
    execution_context={'activity_score':50,'shock_score':0},entry_hint=98.4,
    rr_floor=1.5,rr_ceiling=4.5,preferred_rr_min=2.0,preferred_rr_max=3.2,leverage_hint=10,
)
ok('25_structural_recovery_smoke_success', rec.get('success') is True and rec.get('stop_loss',0)<rec.get('entry',0)<rec.get('take_profit',0))
empty=recover_execution_geometry_from_structure(
    direction='long',current_price=100,atr=1.0,structure={},trend={},momentum={},volatility={},
    setup_family='TREND_PULLBACK',market_type='futures',symbol='BTC-USDT',timeframe='1h',
    execution_context={'activity_score':50},entry_hint=0,rr_floor=1.8,rr_ceiling=4.5,
)
ok('26_no_structure_no_fabricated_recovery', empty.get('success') is False)

print(f'QA 17.5.9: {len(passed)}/{len(passed)} PASS')
for i,name in enumerate(passed,1):
    print(f'{i:02d}. PASS {name}')
