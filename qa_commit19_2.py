from __future__ import annotations
import os, sys, re
ROOT=os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path: sys.path.insert(0,ROOT)

from live_quant_synthesis_commit19_1 import synthesize_live_candidate
from execution_specialist_committees import build_execution_context, score_execution_geometry
from synthesis_decay_commit19_1 import evaluate_decay
import qa_commit19_1 as q19_1


def _check(name, value, checks):
    checks[name]=bool(value)
    print(('PASS' if value else 'FAIL'), name)


def main():
    checks={}

    # 1) Concrete multi-source pattern is allowed even when the old generic
    # thesis-family label count is incomplete. This is not a quality-threshold
    # reduction: the setup still needs Sweep+MSS/Displacement+POI, coherent
    # independent desks and the unchanged >=0.66 synthesis quality floor.
    c,r=q19_1._case('BULLISH')
    c['operational_intelligence']['thesis']['long_families']=['trend']
    x=synthesize_live_candidate(capas=c,vote_record=r,symbol='BTC-USDT',timeframe='1H',system_type='futures',review_trader=q19_1.Review())
    _check('pattern_contract_replaces_generic_family_quota', x.get('use') and x.get('pattern_contract')=='SWEEP_MSS_POI_CONTRACT', checks)

    # 2) A real single-indicator situation remains blocked.
    c,r=q19_1._case('BULLISH')
    c['operational_intelligence']['thesis']['long_families']=['trend']
    c['structure']={'current_price':100}
    c['momentum']={'direction':'neutral','rsi':50,'macd_histogram':0}
    c['volume']={'volume_ratio':0.6}
    c['trend']={'direction':'bullish','adx':12}
    for w in r['worker_desk_17_5_9']['workers']:
        w['strategies_observed']=['RSI']; w['work_notes']=[]
    x=synthesize_live_candidate(capas=c,vote_record=r,symbol='BTC-USDT',timeframe='1H',system_type='futures',review_trader=q19_1.Review())
    _check('true_single_indicator_still_blocked', not x.get('use'), checks)

    # 3) Multi-Asset can create a native quality thesis from concrete market
    # evidence without waiting for crypto-style family labels.
    c,r=q19_1._case('BULLISH')
    c['operational_intelligence']['thesis']['long_families']=[]
    x=synthesize_live_candidate(capas=c,vote_record=r,symbol='SPY-USDT',timeframe='4H',system_type='futures',review_trader=q19_1.Review())
    _check('multiasset_native_pattern_lane', x.get('use') and x.get('action')=='LONG', checks)

    # 4) Exact final geometry is independently scored without moving prices.
    structure={
        'current_price':100.0,'supports':[98.0,96.0],'resistances':[104.0,107.0],
        'order_blocks':[{'price':98.5,'type':'bullish','strength':3}],
        'fair_value_gaps':[{'price':99.0}], 'nearest_support':98.0,'nearest_resistance':104.0,
        'poc':99.0, 'liquidity_sweeps':[{'price':98.0}],
    }
    vol={'atr':2.0,'atr_pct':2.0,'state':'NORMAL'}
    trend={'direction':'bullish','adx':28}
    mom={'direction':'bullish','rsi':56,'macd_histogram':0.2}
    ctx=build_execution_context(structure=structure,volume={'volume_ratio':1.3},volatility=vol,
        market_hours={},sentiment={},macro_context={'risk_level':'NORMAL'},market_regime={'regime':'TREND_UP'},
        symbol='BTC-USDT',timeframe='1h',market_type='futures')
    score=score_execution_geometry(entry=98.5,stop_loss=96.0,take_profit=104.0,direction='long',current_price=100.0,
        atr=2.0,structure=structure,trend=trend,momentum=mom,volatility=vol,setup_family='TREND_PULLBACK',
        market_type='futures',symbol='BTC-USDT',timeframe='1h',execution_context=ctx,rr_floor=1.8,rr_ceiling=4.5)
    _check('final_geometry_rescore_succeeds', score.get('success') and score.get('prices_changed') is False, checks)
    _check('final_geometry_rescore_has_real_component_scores', score.get('entry_quality',0)>0 and score.get('sl_quality',0)>0 and score.get('tp_quality',0)>0, checks)

    # 5) Static guard regression checks: old parity shackles are removed, while
    # refined geometry is held to stricter local component floors and must pass
    # the actual downstream timing/setup guard.
    app=open(os.path.join(ROOT,'app.py'),encoding='utf-8').read()
    _check('same_rr_bucket_shackle_removed', '_rr_safety_bucket(rr_candidate) == _rr_safety_bucket(baseline_rr)' not in app, checks)
    _check('same_timing_class_shackle_removed', "metadata['entry_timing_mode'] != entry_quality.get('entry_timing_mode')" not in app, checks)
    _check('same_060atr_shackle_removed', "<= 0.60) != (abs(current_price - baseline_entry)" not in app, checks)
    _check('refined_geometry_quality_floors_not_lowered', '_entry_q >= 65.0 and _sl_q >= 60.0 and _tp_q >= 60.0' in app and '_candidate_gq >= 68.0' in app, checks)
    _check('refined_entry_must_pass_real_timing_gate', 'if refined_passed is not True:' in app, checks)
    _check('selected_geometry_scores_follow_selected_prices', "entry_score = float(committee_result.get('entry_quality')" in app and "sl_score = float(committee_result.get('sl_quality')" in app and "tp_score = float(committee_result.get('tp_quality')" in app, checks)

    # 6) Publication thresholds are untouched.
    fs=open(os.path.join(ROOT,'futures_system.py'),encoding='utf-8').read()
    _check('publication_safety_still_75', re.search(r"'minimum_publication_execution_safety'\s*:\s*75\.0",fs) is not None, checks)
    _check('publication_rr_still_1_8', re.search(r"'minimum_publication_rr'\s*:\s*1\.8",fs) is not None, checks)
    _check('publication_tp_quality_still_55', re.search(r"'minimum_publication_tp_quality'\s*:\s*55\.0",fs) is not None, checks)
    _check('publication_sl_quality_still_60', re.search(r"'minimum_publication_sl_avoidance_quality'\s*:\s*60\.0",fs) is not None, checks)

    # 7) Runtime rescoring happens after Champion/Synthesis geometry and does not
    # alter prices or add I/O.
    rt=open(os.path.join(ROOT,'commit19_1_runtime.py'),encoding='utf-8').read()
    _check('runtime_scores_actual_final_geometry', 'COMMIT19_2_FINAL_GEOMETRY_SCORE_V1' in rt and 'final_geometry_quality_rescored' in rt, checks)
    _check('runtime_does_not_lower_safety_rr', 'changes_safety_thresholds":False' in rt and 'changes_rr_floor":False' in rt, checks)
    _check('alpha_decay_8_plus_8_preserved', evaluate_decay(live_consecutive_losses=8)=='SHADOW_DECAY' and evaluate_decay(live_consecutive_losses=8,shadow_consecutive_losses=8)=='RETIRED_ALPHA_DECAY', checks)

    # 8) Greeks blank-card repair reuses visible candle data before network.
    js=open(os.path.join(ROOT,'static','market_maker_frontend.js'),encoding='utf-8').read()
    _check('greeks_reuses_visible_candle_price', 'function visibleCandlePrice()' in js and "$('candle-chart')" in js, checks)
    _check('greeks_no_polling_added', 'setInterval(' not in js, checks)

    # 9) Resource contract remains the same or stricter.
    proc=open(os.path.join(ROOT,'Procfile'),encoding='utf-8').read()
    render=open(os.path.join(ROOT,'render.yaml'),encoding='utf-8').read()
    _check('one_worker_two_threads', '--workers 1 --threads 2' in proc and '--workers 1 --threads 2' in render, checks)
    _check('memory_hard_guard_300mb', 'MEMORY_HARD_LIMIT_MB' in render and 'value: "300"' in render, checks)
    _check('options_provider_budget_12mb_day', 'OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB' in render and 'value: "12"' in render, checks)
    _check('multi_deep_limit_2', 'MULTIASSET_DEEP_LIMIT' in render and 'value: "2"' in render, checks)
    _check('new_entrypoint_commit19_2', (('commit19_2_main_entrypoint:app' in proc and 'commit19_2_main_entrypoint:app' in render) or ('commit19_2_1_main_entrypoint:app' in proc and 'commit19_2_1_main_entrypoint:app' in render)), checks)

    # 10) Manual diagnostics show the exact Premium blocker instead of only a
    # generic explanation, so remaining analysis-only rows are auditable.
    _check('manual_lane_surfaces_exact_gate_reason', 'Motivo exacto:' in app and "_publication_gate.get('reasons')" in app, checks)
    _check('multi_lane_surfaces_exact_gate_reason', "_multi_gate.get('reasons')" in app and "_multi_gate_reasons" in app, checks)
    _check('theoretical_greeks_marks_oi_metrics_na', "Call Wall (por OI)" in js and "Gamma Wall (por OI)" in js and "text('mm-call-wall', 'Requiere OI')" in js and "text('mm-gamma-wall', 'Requiere OI')" in js, checks)

    failed=[k for k,v in checks.items() if not v]
    print(f'\nSUMMARY {len(checks)-len(failed)}/{len(checks)} PASS')
    if failed:
        print('FAILED',failed)
        raise SystemExit(1)

if __name__=='__main__': main()
