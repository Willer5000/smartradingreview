from execution_specialist_committees import _tp_specialists, _sl_specialists
from portfolio_guardian import PortfolioGuardian

checks=[]
def ok(name, cond):
    if not cond:
        raise AssertionError(name)
    print('OK  ', name)
    checks.append(name)

# TP: same technical candidate becomes more economically meaningful at higher
# indicative leverage, without changing direction or inventing a farther target.
cand={'price':100.5,'family':'structure_target','strength':3.0,'families':{'structure_target'}}
universe=[cand]
base=dict(direction='long',entry=100.0,sl=99.8,atr=1.0,structure={},trend={'direction':'bullish'},momentum={'direction':'bullish'},volatility={},setup_family='MOMENTUM_CONTINUATION',context={'activity_score':65,'shock_score':10,'market_regime':'TREND'},market_type='futures',liquidation=None)
low=_tp_specialists(cand,universe,leverage_hint=2,**base)
high=_tp_specialists(cand,universe,leverage_hint=20,**base)
ok('TP economics uses indicative leverage', high['economics'] > low['economics'])

# SL: an identical price-distance that becomes too expensive on margin at high
# leverage is ranked lower, but remains a candidate (no thesis veto).
slcand={'price':98.5,'family':'structural_invalidation','strength':3.0,'families':{'structural_invalidation'},'anchor':98.7}
sluni=[slcand]
slbase=dict(direction='long',entry=100.0,tp_hint=103.0,atr=1.0,structure={},setup_family='TREND_PULLBACK',context={'activity_score':50,'shock_score':0},market_type='futures')
sl5=_sl_specialists(slcand,sluni,leverage_hint=5,**slbase)
sl20=_sl_specialists(slcand,sluni,leverage_hint=20,**slbase)
ok('SL ranks excessive leveraged loss lower', sl5['risk'] > sl20['risk'])
ok('SL high-leverage candidate is not hard-vetoed', sl20['risk'] > 0)

# Guardian: extension is placed before the next reaction swing, not exactly on
# it, and only when the extension is economically meaningful.
g=PortfolioGuardian()
plan=g._build_futures_management_plan(
    action='LONG',entry=100,sl=99,tp=103,current_price=102.4,
    highs=[102.0,102.3,102.5],lows=[101.7,101.9,102.0],
    recent_change_pct=1.0,fast_avg=102.2,slow_avg=101.8,
    structure_deteriorated=False,deterioration_score=0,timeframe='1h',risk_class='CORE',
    investment_usdt=24,leverage=10,mfe_pct=2.6,mae_pct=0.2,
    context_highs=[102.5,104.0,105.0],context_lows=[101.5,101.8,102.0]
)
tp=plan['suggested_take_profit']
ok('Guardian can extend healthy winner', tp is not None)
ok('Guardian TP extension captures before reaction swing', 103 < tp < 104.0)
ok('Guardian extension keeps original TP direction', tp > 103)

print(f'PASS {len(checks)}/{len(checks)}')
