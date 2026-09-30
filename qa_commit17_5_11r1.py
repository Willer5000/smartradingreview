#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validated_strategy_routes_175111r1 import resolve_validated_route, coverage_summary, route_registry
from execution_specialist_committees import _strategy_family


def prior(family, n=12, exp=0.5, pf=1.8, stage='SHADOW_READY_FAST', state='OOS_VALIDATED', recycle=False):
    return {
        'state': state,
        'recycle_required': recycle,
        'best_positive': {
            'stage': stage,
            'strategy_family': family,
            'oos_n': n,
            'oos_exp_r': exp,
            'oos_pf': pf,
            'runtime_trackable': True,
            'recycle_required': recycle,
        },
    }


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print('PASS:', name)


summary = coverage_summary()
check('registry has 6 exact audited routes', summary['exact_routes'] == 6)
check('only 3 routes are profitable in train+selection+OOS and receive routing authority', summary['execution_routing_routes'] == 3)
check('three routes remain shadow-only after train/OOS audit', summary['shadow_only_routes'] == 3)

r = resolve_validated_route(
    prior=prior('SWEEP_REVERSAL', n=12, exp=.5596, pf=2.1422),
    symbol='ADA-USDT', timeframe='2h', action='SHORT', regime='BALANCE', volatility='NORMAL')
check('ADA 2H stays shadow because IS/train was not profitable', r['matched'] and not r['eligible_for_execution_routing'])

r = resolve_validated_route(
    prior=prior('RSI_TREND', n=14, exp=.333, pf=1.9675),
    symbol='ETH-USDT', timeframe='2h', action='LONG', regime='TREND_DOWN', volatility='NORMAL')
check('wrong regime cannot activate ETH trend route', not r['eligible_for_execution_routing'] and 'REGIME' in r['reason'])

r = resolve_validated_route(
    prior=prior('RSI_TREND', n=14, exp=.333, pf=1.9675, recycle=True),
    symbol='ETH-USDT', timeframe='2h', action='LONG', regime='TREND_UP', volatility='NORMAL')
check('alpha-decay/recycle blocks validated route', not r['eligible_for_execution_routing'])

r = resolve_validated_route(
    prior=prior('BOLLINGER_SQUEEZE', n=6, exp=.965, pf=6.618, stage='SHADOW_READY'),
    symbol='ADA-USDT', timeframe='4h', action='SHORT', regime='BALANCE', volatility='EXPANSION')
check('positive ADA 4H squeeze is still shadow-only', r['matched'] and not r['eligible_for_execution_routing'] and r['reason'] == 'POSITIVE_BUT_SMALL_OOS_SHADOW_ONLY')

r = resolve_validated_route(
    prior=prior('TREND_CONTINUATION', n=18, exp=.279, pf=1.519),
    symbol='XRP-USDT', timeframe='2h', action='SHORT', regime='TREND_DOWN', volatility='LOW')
check('validated route is not vetoed merely by LOW volatility when research spec was ANY', r['eligible_for_execution_routing'])

r = resolve_validated_route(
    prior=prior('TREND_CONTINUATION', n=18, exp=.279, pf=1.519),
    symbol='BTC-USDT', timeframe='2h', action='SHORT', regime='TREND_DOWN', volatility='NORMAL')
check('unknown cell remains research gap, no family is fabricated', not r['matched'] and not r['eligible_for_execution_routing'])

check('RSI_TREND maps to momentum-continuation geometry', _strategy_family('RSI_TREND') == 'MOMENTUM_CONTINUATION')
check('RSI Maverick reversal maps to mean-reversion geometry', _strategy_family('RSI_MAVERICK_REVERSAL') == 'MEAN_REVERSION')
check('Bollinger squeeze maps to compression/expansion geometry', _strategy_family('BOLLINGER_SQUEEZE') == 'COMPRESSION_EXPANSION')
check('Supertrend pullback maps to pullback geometry', _strategy_family('SUPERTREND_PULLBACK') == 'TREND_PULLBACK')

op = (ROOT / 'operational_intelligence.py').read_text(encoding='utf-8')
ct = (ROOT / 'contingency_strategy_engine.py').read_text(encoding='utf-8')
ex = (ROOT / 'execution_specialist_committees.py').read_text(encoding='utf-8')
check('operational routing prefers exact validated local family over group prior', '_validated_bank_family or _group_prior_family' in op)
check('contingency aligns setup family only when route action matches live action', '_u(validated_route.get("action")) == _u(target_action)' in ct)
check('30m backtested liquidity entry route from 17.5.11R is preserved', 'validated_liquidity_route' in ex and 'and _tf == "30m"' in ex)
app = (ROOT / 'app.py').read_text(encoding='utf-8')
check('validated exact route may softly align preferred RR without changing technical floor', '_route_rr_min' in app and '_target_rr - 0.35' in app and 'minimum_viable_rr' in app)
check('backtest prior remains non-authoritative in execution consensus', '"backtest_prior":0.0' in ex)

print('R1 QA: 18/18 PASS')
