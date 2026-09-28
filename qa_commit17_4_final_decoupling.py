from pathlib import Path
from operational_intelligence import execution_setup_guard
from execution_specialist_committees import coordinate_execution_committees

checks=[]
def ok(name, cond):
    checks.append((name, bool(cond)))
    print(('OK   ' if cond else 'FAIL ')+name)

weak_levels={
    'entry':100.0,'stop_loss':99.0,'take_profit':101.0,'risk_reward':1.0,
    'entry_score':40,'entry_quality_score':40,'entry_source':'fallback',
}
r=execution_setup_guard(action='LONG', levels=weak_levels, setup_family='MOMENTUM_CONTINUATION', market='FUTURES', timeframe='1h')
ok('execution guard preserves LONG', r.get('action')=='LONG')
ok('execution guard is advisory, not a publication veto', r.get('status')=='EXECUTION_ADVISORY' and r.get('execution_ready') is True)
ok('execution guard declares direction preserved', r.get('direction_preserved') is True)
r2=execution_setup_guard(action='SHORT', levels=weak_levels, setup_family='STRUCTURE_REVERSAL', market='FUTURES', timeframe='1h')
ok('execution guard preserves SHORT', r2.get('action')=='SHORT')

structure={
 'supports':[98.0,97.5], 'resistances':[104.0,106.0],
 'pivot_lows':[{'price':97.8,'strength':3}], 'pivot_highs':[{'price':104.2,'strength':3}],
 'order_blocks':[{'type':'bullish','price_range':[97.2,98.1],'strength':'strong'}, {'type':'bearish','price_range':[104.0,105.0],'strength':'strong'}],
 'fair_value_gaps':[],
 'volume_profile':{'poc':101.0,'vah':103.0,'val':99.0,'hvn_nodes':[{'price':103.5}]},
}
combo=coordinate_execution_committees(
    baseline_entry=100.0, baseline_sl=0.0, baseline_tp=0.0,
    direction='long', current_price=101.0, atr=1.2,
    structure=structure, trend={'direction':'bullish'}, momentum={}, volatility={},
    setup_family='TREND_PULLBACK', market_type='futures', symbol='BTC-USDT', timeframe='1h',
    execution_context={'activity_score':60,'shock_score':20,'timeframe':'1h'},
    rr_floor=1.5, rr_ceiling=5.0, preferred_rr_min=2.0, preferred_rr_max=3.5,
)
ok('committees recover missing baseline geometry', combo.get('success') is True)
ok('recovered geometry is coherent', combo.get('stop_loss',0) < combo.get('entry',0) < combo.get('take_profit',0))
ok('recovered geometry has economic RR', 1.5 <= float(combo.get('risk_reward') or 0) <= 5.0)

# Sparse structure must still produce a complete execution package after signal confirmation.
sparse=coordinate_execution_committees(
    baseline_entry=0.0, baseline_sl=0.0, baseline_tp=0.0,
    direction='short', current_price=100.0, atr=1.5,
    structure={'df':{'high':[100,101,102,103], 'low':[98,99,99.5,100], 'close':[99,100,101,102]}},
    trend={'direction':'bearish'}, momentum={'direction':'bearish'}, volatility={},
    setup_family='MOMENTUM_CONTINUATION', market_type='multiasset', symbol='CL-USDT', timeframe='4h',
    execution_context={'activity_score':65,'shock_score':25,'timeframe':'4h'},
    rr_floor=1.5, rr_ceiling=4.5, preferred_rr_min=2.0, preferred_rr_max=3.2,
)
ok('sparse Multi-Asset structure still resolves geometry', sparse.get('success') is True)
ok('sparse SHORT geometry is coherent', sparse.get('take_profit',0) < sparse.get('entry',0) < sparse.get('stop_loss',0))

app=Path('app.py').read_text(encoding='utf-8')
ok('app publishes confirmed geometry as EXECUTABLE_SIGNAL', "'publication_status': 'EXECUTABLE_SIGNAL'" in app and "'execution_ready': True" in app)
ok('RC9.2 no longer rewrites consensus action from execution guard', "accion_consenso = str(operational_execution.get('action')" not in app)
ok('RC9.2 keeps guard observations advisory', "levels['execution_advisories']" in app)
ok('R4 has mandatory geometry recovery contract', 'SIGNAL => MANDATORY EXECUTION GEOMETRY' in app)

passed=sum(v for _,v in checks)
print(f'PASS {passed}/{len(checks)}')
raise SystemExit(0 if passed==len(checks) else 1)
