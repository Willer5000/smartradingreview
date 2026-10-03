from __future__ import annotations

import pathlib
import py_compile
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent


def good(levels=None, safety=82.0, rr=2.2):
    data = {
        'execution_safety': safety,
        'entry_quality_score': 88,
        'entry_score': 88,
        'entry_reachability': 82,
        'sl_reliability': 0.78,
        'tp_quality_score': 82,
        'risk_reward': rr,
        'entry_sweep_confirmed': True,
        'entry_mss_bos_confirmed': True,
        'entry_displacement_confirmed': True,
        'entry_poi_confirmed': True,
        'entry_source': 'ORDER_BLOCK_FVG_LIQUIDITY',
        'entry_distance_atr': 0.8,
        'mtf_alignment': 'ALIGNED',
        'regime': 'TREND_UP',
        'setup_family': 'TREND_PULLBACK',
        'strategy_family': 'TREND_PULLBACK',
        'validated_strategy_route': {'state': 'LIVE_CHAMPION', 'exact_cell': True},
        'volume': {'volume_ratio': 1.35, 'open_interest': 'OPEN_INTEREST_RISING'},
        'funding': {'funding': 'NORMAL'},
        'liquidation_map': {'bias': 'SUPPORTIVE'},
        'whale': {'whale_buy_confirmed': True},
        'sentiment': 'SUPPORTIVE',
        'market_session': 'ACTIVE',
        'macro_bias': 'SUPPORTIVE',
        'thesis': 'directional thesis',
        'directional_support': {'LONG': 7},
        'multi_timeframe': {'alignment': 'ALIGNED', 'timeframes': ['30m', '2h', '4h']},
    }
    if levels:
        data.update(levels)
    return data


passed = 0

def check(name, cond):
    global passed
    if not cond:
        raise AssertionError(name)
    passed += 1
    print(f'PASS: {name}')


for fn in ('app.py', 'quality_9q_engine_21.py', 'premium_path_expansion_21.py'):
    py_compile.compile(str(ROOT / fn), doraise=True)
check('python compile', True)

sys.path.insert(0, str(ROOT))
import quality_9q_engine_21 as q9
r = q9.evaluate(good(), {'direction':'BULLISH','adx':29,'regime':'TREND_UP'}, {'direction':'BULLISH'}, {'state':'EXPANSION','atr_pct':2.0,'session':'ACTIVE'}, {'direction':'BULLISH','sweep':True,'mss':True,'displacement':True,'order_blocks':['x']}, '4h', 'BTC-USDT', 'LONG')
check('Q1-Q9 present', set(r['quality']) == {f'Q{i}' for i in range(1,10)})
check('quality model separates Q10', r['model'] == 'Q1-Q9_QUALITY_PLUS_Q10_SAFETY' and 'Q10' not in r['quality'])
check('good candidate reaches quality-ready', r['quality_ready'] is True)

unsafe = good(safety=68.0)
g = {'success': True, 'levels': unsafe, 'futures_publication_gate': {'eligible': False, 'reason_codes':['SAFETY']}}
q10 = q9.q10_safety_snapshot(g, unsafe)
check('Q10 safety hard floor retained', q10['execution_safety'] < 75 and not q10['hard_gate_eligible'])

lowrr = q9.evaluate(good(rr=1.79), {'direction':'BULLISH'}, {'direction':'BULLISH'}, {'state':'NORMAL'}, {'direction':'BULLISH'}, '4h', 'BTC-USDT', 'LONG')
check('RR below 1.8 is not economically strong', lowrr['quality']['Q7'] < r['quality']['Q7'])

highrr = q9.evaluate(good(rr=7.43), {'direction':'BULLISH'}, {'direction':'BULLISH'}, {'state':'NORMAL'}, {'direction':'BULLISH'}, '30m', 'NEAR-USDT', 'SHORT')
check('RR above 3.5 is penalized in Q7', highrr['quality']['Q7'] < r['quality']['Q7'])

neutral = q9.evaluate(good(), {'direction':'NEUTRAL'}, {'direction':'NEUTRAL'}, {'state':'NORMAL'}, {'direction':'NEUTRAL'}, '4h', 'BTC-USDT', 'NO_OPERAR')
check('Q9 cannot create direction', neutral['quality_ready'] is False and neutral['direction'] == 'NEUTRAL')

# Static contract checks.
template = (ROOT / 'templates/index.html').read_text()
app = (ROOT / 'app.py').read_text()
check('multiasset title fixed', 'CRYPTO TRADER ANALYST PRO · MULTIACTIVOS' in template)
check('futures title preserved', 'CRYPTO TRADER ANALYST PRO · FUTUROS' in template)
check('commit21 cache bust visible', '20261003-COMMIT21-9Q' in template)
check('commit21 guarded autoinstall', 'from premium_path_expansion_21 import install as _install_commit21_9q' in app)
check('base runtime remains 20.2.1', 'COMMIT20_2_1_STABILITY_FIX_V1' in (ROOT/'premium_path_expansion_21.py').read_text())
check('no new worker declarations in commit21 module', not re.search(r'--workers\s+[2-9]|workers\s*=\s*[2-9]|thread[s]?\s*=\s*[3-9]', (ROOT/'premium_path_expansion_21.py').read_text(), re.I))

for js in ('static/script.js','static/futures.js'):
    cp = subprocess.run(['node','--check',str(ROOT/js)],capture_output=True,text=True)
    check(f'node check {js}', cp.returncode == 0)

print(f'COMMIT 21 9Q QA: {passed} PASS')
