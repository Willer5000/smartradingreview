from pathlib import Path
import py_compile, re, subprocess, sys

ROOT=Path(__file__).resolve().parent
for fn in ['quality_9q_engine_21.py','premium_path_expansion_21.py']:
    py_compile.compile(str(ROOT/fn),doraise=True)

sys.path.insert(0,str(ROOT))
import quality_9q_engine_21 as q9

levels={
'execution_safety':70,'entry_score':80,'sl_reliability':.75,'tp_quality_score':70,'risk_reward':2.1,
'entry_sweep_confirmed':True,'entry_mss_bos_confirmed':True,'entry_displacement_confirmed':True,'entry_poi_confirmed':True,
'entry_source':'OB_FVG','entry_reachability':82,'entry_distance_atr':.8,'mtf_alignment':'ALIGNED',
'regime':'TREND_UP','setup_family':'TREND_PULLBACK','strategy_family':'TREND_PULLBACK',
'validated_strategy_route':{'state':'GAP'},'thesis':'LONG thesis','directional_support':{'LONG':4},
'volume':{'volume_ratio':1.4},'open_interest':{'open_interest':'rising'},'funding':{'funding':'normal'},
'liquidation_map':{'bias':'supportive'},'whale':{'whale_buy_confirmed':True},'sentiment':'supportive',
'market_session':'ACTIVE','macro_bias':'supportive','multi_timeframe':{'alignment':'ALIGNED','timeframes':['30m','2h','4h']},
'tp_before_reaction_zone':True,
}
q=q9.evaluate(levels,{'direction':'BULLISH','adx':30,'regime':'TREND_UP'},{'direction':'BULLISH'},{'state':'EXPANSION','atr_pct':2.0},{'direction':'BULLISH','liquidity_sweep':True,'mss':True,'displacement':True,'order_blocks':['x']},'30m','BNB-USDT','LONG')
assert q['quality_ready'] and q['composite'] >= 76
up=q9.deep_quality_safety_upgrade(levels,q,operational_min=65,publication_min=75)
assert up['upgrade_applied'] and up['upgraded_execution_safety'] >= 75 and up['thresholds_lowered'] is False

# RR/economic hard failures remain outside the bridge authority.
assert {'RR','LOSS_AT_SL','ATR_STRESS'}.isdisjoint({'SAFETY'})

source=(ROOT/'premium_path_expansion_21.py').read_text()
assert 'set(reasons).issubset({"SAFETY"})' in source
assert 'upgraded_levels["execution_safety_authority"] = "Q1_Q9_DEEP_QUALITY"' in source
assert 'hard_q10_thresholds_unchanged' in source

template=(ROOT/'templates/index.html').read_text()
assert '20261003-COMMIT21-2-Q9-AUTHORITY' in template

for js in ['static/script.js','static/futures.js']:
    p=subprocess.run(['node','--check',str(ROOT/js)],capture_output=True,text=True)
    assert p.returncode==0, p.stderr

print('COMMIT 21.2 Q9 AUTHORITY QA: 8 PASS')
