from __future__ import annotations

import ast
import importlib
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app.py'
SRC = APP.read_text(encoding='utf-8')
sys.path.insert(0, str(ROOT))

checks = []

def check(name, cond, detail=''):
    ok = bool(cond)
    checks.append((name, ok, detail))
    if not ok:
        raise AssertionError(f'{name}: {detail}')

# ---------------------------------------------------------------------------
# 1) Syntax / static contract
# ---------------------------------------------------------------------------
for py in [
    'app.py', 'default_strategy_bank.py', 'operational_intelligence.py',
    'execution_specialist_committees.py', 'multiasset_system.py',
    'portfolio_guardian.py'
]:
    ast.parse((ROOT / py).read_text(encoding='utf-8'))
    check(f'parse {py}', True)

for legacy in ['50_000_000', '100_000_000', '200_000_000']:
    check(f'no legacy liquidation threshold {legacy}', legacy not in SRC)

for marker in [
    "'weight_unit': 'relative_participation'",
    "'interpretation_version': 'RELATIVE_PARTICIPATION_CONSUMERS_V1'",
    "liquidation.get('weight_unit') != 'relative_participation'",
    "'liquidity_intensity': intensity",
    "liquidity_public_calibrated",
    "liquidity_calibration_quality",
]:
    check(f'liquidation contract marker {marker}', marker in SRC)

check('no false M-dollar liquidation template', 'total_short_below:.1f}M' not in SRC and 'total_long_above:.1f}M' not in SRC)
check('legacy Liquidation voter delegates', 'return self.votar(capas, symbol, timeframe)' in SRC)

# ---------------------------------------------------------------------------
# 2) Strategy Bank 17.3 remains valid / broad but selective
# ---------------------------------------------------------------------------
bank = importlib.import_module('default_strategy_bank')
validation = bank.validate_bank()
coverage = bank.coverage_matrix()
check('strategy bank validation', validation.get('ok'), json.dumps(validation)[:600])
check('official cell coverage', coverage.get('ok'), json.dumps(coverage)[:600])
check('minimum 7 playbooks per cell', coverage.get('minimum_strategies_per_cell', 0) >= 7, str(coverage))

families = {str(x.get('family')) for x in bank.ARCHETYPES}
for fam in ['MOMENTUM_CONTINUATION', 'COMPRESSION_EXPANSION', 'STRUCTURE_REVERSAL']:
    check(f'family exists {fam}', fam in families)
    for action in ['LONG', 'SHORT', 'COMPRA_SPOT', 'VENTA_SPOT']:
        check(
            f'{fam} covers {action}',
            any(x.get('family') == fam and action in (x.get('actions') or []) for x in bank.ARCHETYPES)
        )

# ---------------------------------------------------------------------------
# 3) Independent thesis: HIGH is not relaxed; expansion only widens evidence
# ---------------------------------------------------------------------------
op = importlib.import_module('operational_intelligence')
layers = {
    'trend': {'direction': 'bullish', 'adx': 34, 'plus_di': 36, 'minus_di': 14},
    'momentum': {
        'direction': 'bullish',
        'indicators': {'rsi': 63, 'macd_histogram': 1.5},
        'divergences': [], 'hidden_divergences': []
    },
    'volume': {'volume_ratio': 1.5, 'obv_trend': 'bullish'},
    'structure': {
        'direction': 'neutral', 'order_blocks': [], 'fair_value_gaps': [],
        'liquidity_sweeps': [], 'stop_hunts': []
    },
    'volatility': {
        'volatility_ratio': 1.65, 'bb_width': 6.2, 'bb_width_prev': 4.2,
        'bb_position': 0.86, 'squeeze_on': False, 'operability': True
    },
    'macro_context': {'risk_level': 'LOW'},
    'liquidation': {},
}
mtf = {'dominant_direction': 'bullish', 'alignment': 'ALIGNED', 'conflict': False, 'public_summary': '3 TF alcistas'}
thesis = op.build_independent_thesis(
    layers=layers, mtf_context=mtf, market='FUTURES', symbol='SUI-USDT', timeframe='1H'
)
check('HIGH still requires 5 independent families', thesis.get('required_independent_families') == 5, str(thesis))
check('expansion can be independent support', 'expansion' in (thesis.get('independent_support_families') or []), str(thesis))

only = {
    'trend': {}, 'momentum': {}, 'volume': {}, 'structure': {},
    'volatility': layers['volatility'], 'macro_context': {}, 'liquidation': {}
}
neutral = op.build_independent_thesis(
    layers=only,
    mtf_context={'dominant_direction': 'NEUTRAL', 'alignment': 'INCOMPLETE', 'conflict': False, 'public_summary': 'incompleto'},
    market='FUTURES', symbol='SUI-USDT', timeframe='1H'
)
check('expansion alone cannot create direction', neutral.get('direction') == 'NEUTRAL', str(neutral))

# ---------------------------------------------------------------------------
# 4) Entry no-chase remains intact
# ---------------------------------------------------------------------------
esc = importlib.import_module('execution_specialist_committees')
check('LONG no-chase', esc._is_correct_side(99, 100, 'long', 'entry') and not esc._is_correct_side(101, 100, 'long', 'entry'))
check('SHORT no-chase', esc._is_correct_side(101, 100, 'short', 'entry') and not esc._is_correct_side(99, 100, 'short', 'entry'))

# ---------------------------------------------------------------------------
# Helpers to execute selected app.py methods WITHOUT importing Flask app.py.
# ---------------------------------------------------------------------------
tree = ast.parse(SRC)

def method_source(class_name, method_name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    segment = ast.get_source_segment(SRC, item)
                    return textwrap.dedent(segment)
    raise RuntimeError(f'{class_name}.{method_name} not found')

# ---------------------------------------------------------------------------
# 5) TP scoring uses relative intensity + confidence/calibration, not dollars.
# ---------------------------------------------------------------------------
ns = {}
exec(method_source('TradingExpertSystem', '_score_tp_candidate'), ns)
score_tp = ns['_score_tp_candidate']

def liq_candidate(intensity, calibrated=True, quality=100, model_conf=70):
    return {
        'price': 103.0,
        'source': 'synthetic liquidity target',
        'strength': 3,
        'volume_ratio': 1.0,
        'type': 'liquidity',
        'liquidity_intensity': intensity,
        'liquidity_model_confidence': model_conf,
        'liquidity_public_calibrated': calibrated,
        'liquidity_calibration_quality': quality,
    }

weak = liq_candidate(20)
strong = liq_candidate(90)
fallback = liq_candidate(90, calibrated=False, quality=0)
weak_score = score_tp(object(), weak, 100.0, 'long', [weak], 0.2, sl_distance_pct=1.2, geometry_profile=None)
strong_score = score_tp(object(), strong, 100.0, 'long', [strong], 0.2, sl_distance_pct=1.2, geometry_profile=None)
fallback_score = score_tp(object(), fallback, 100.0, 'long', [fallback], 0.2, sl_distance_pct=1.2, geometry_profile=None)
check('strong liquidity pool outranks weak pool', strong_score > weak_score + 10, f'{strong_score=} {weak_score=}')
check('public calibration has more TP authority than OHLCV-only fallback', strong_score > fallback_score, f'{strong_score=} {fallback_score=}')
check('TP scores bounded 0..100', all(0 <= x <= 100 for x in [weak_score, strong_score, fallback_score]))

# ---------------------------------------------------------------------------
# 6) Active TraderLiquidation respects relative contract and confirmations.
# ---------------------------------------------------------------------------
ns = {}
exec(method_source('TraderLiquidation', 'votar'), ns)
liq_vote = ns['votar']
base_bins = [
    {'side': 'long'}, {'side': 'long'}, {'side': 'long'},
    {'side': 'short'}, {'side': 'short'}, {'side': 'short'},
]
base_liq = {
    'data_type': 'MODEL_ESTIMATE_NOT_OBSERVED',
    'weight_unit': 'relative_participation',
    'active_bins': base_bins,
    'frozen_bins': [],
    'total_spikes': 6,
    'model_confidence': 60,
}

bear = dict(base_liq, total_long_weight=2.0, total_short_weight=1.0)
action, confidence, strategies, reasons = liq_vote(
    object(),
    {'system_type': 'futures', 'liquidation': bear, 'trend': {'direction': 'bearish'}, 'momentum': {'direction': 'neutral'}},
    'BTC-USDT', '1h'
)
check('relative LONG exposure + bearish confirmation can support SHORT', action == 'SHORT', str((action, confidence, strategies, reasons)))
check('liquidator confidence capped <=68', confidence <= 68, str(confidence))

bull = dict(base_liq, total_long_weight=1.0, total_short_weight=2.0)
action, confidence, strategies, reasons = liq_vote(
    object(),
    {'system_type': 'futures', 'liquidation': bull, 'trend': {'direction': 'bullish'}, 'momentum': {'direction': 'neutral'}},
    'BTC-USDT', '1h'
)
check('relative SHORT exposure + bullish confirmation can support LONG', action == 'LONG', str((action, confidence, strategies, reasons)))

bad_contract = dict(bear)
bad_contract.pop('weight_unit')
action, confidence, strategies, reasons = liq_vote(
    object(),
    {'system_type': 'futures', 'liquidation': bad_contract, 'trend': {'direction': 'bearish'}, 'momentum': {'direction': 'neutral'}},
    'BTC-USDT', '1h'
)
check('missing relative unit fails closed', action == 'NO_OPERAR' and confidence == 0, str((action, confidence, reasons)))

# ---------------------------------------------------------------------------
# 7) Guardian 17.3 protection remains present.
# ---------------------------------------------------------------------------
from portfolio_guardian import PortfolioGuardian
g = PortfolioGuardian()
plan = g._build_futures_management_plan(
    action='LONG', entry=100, sl=95, tp=112, current_price=102,
    highs=[104, 106, 103], lows=[101.5, 102.2, 101.7], recent_change_pct=-0.2,
    fast_avg=102, slow_avg=101.5, structure_deteriorated=False,
    deterioration_score=10, timeframe='1h', risk_class='CORE1',
    investment_usdt=24, leverage=5, mfe_pct=6.0, mae_pct=1.0,
    thesis_invalidated=False, reduce_recommended=False,
    context_highs=[106, 110, 114], context_lows=[96, 98, 100]
)
check('Guardian MFE profit lock remains active', plan.get('profit_lock_triggered') is True, str(plan))
check('Guardian suggested stop improves original risk', 95 < float(plan.get('suggested_stop_loss')) < 102, str(plan))

# ---------------------------------------------------------------------------
# 8) Accepted visual heatmap remains the same JS implementation markers.
# ---------------------------------------------------------------------------
script = (ROOT / 'static/script.js').read_text(encoding='utf-8')
for marker in ['xgap: 1.15', 'ygap: 1.05', 'zsmooth: false', 'Mayor concentración', 'Menor intensidad']:
    check(f'heatmap visual marker {marker}', marker in script)

print(f'PASS {sum(1 for _, ok, _ in checks if ok)}/{len(checks)}')
for name, ok, detail in checks:
    print(('OK   ' if ok else 'FAIL ') + name + (f' :: {detail}' if detail and not ok else ''))
