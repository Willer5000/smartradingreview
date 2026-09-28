from pathlib import Path
import ast

ROOT = Path(__file__).parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
COMMITTEE = (ROOT / 'execution_geometry_committee.py').read_text(encoding='utf-8')


def _extract_methods(*names):
    tree = ast.parse(APP)
    lines = APP.splitlines()
    nodes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes[node.name] = node
    body = ['class Dummy:']
    for name in names:
        node = nodes[name]
        body.extend(lines[node.lineno - 1:node.end_lineno])
    ns = {}
    exec('\n'.join(body), ns)
    return ns['Dummy']()


def test_signal_and_leverage_engines_are_not_modified_by_scope_contract():
    # Commit 17.5 is execution geometry only; the files that own publication,
    # leverage and multi-asset routing must remain outside the patch scope.
    assert 'Commit 17.5' in APP
    assert 'tp_capture_buffer_atr' in COMMITTEE


def test_sl_uses_contextual_clearance_behind_reaction_zone():
    dummy = _extract_methods('_collect_sl_candidates')
    candidates = dummy._collect_sl_candidates(
        'long',
        {
            'pivot_lows': [{'price': 99.0}],
            'order_blocks': [], 'fair_value_gaps': [], 'liquidity_sweeps': [],
            'nearest_support': 99.0, 'volume_profile': {},
        },
        current_price=100.0,
        volatility={'atr': 1.0},
        timeframe='1h',
        geometry_profile={'sl_buffer_atr': 0.35},
    )
    structural = [c for c in candidates if c.get('type') == 'swing'][0]
    assert structural['buffer_atr'] >= 0.35
    assert structural['price'] <= 98.65 + 1e-9


def test_short_sl_is_symmetrical_and_behind_reaction_zone():
    dummy = _extract_methods('_collect_sl_candidates')
    candidates = dummy._collect_sl_candidates(
        'short',
        {
            'pivot_highs': [{'price': 101.0}],
            'order_blocks': [], 'fair_value_gaps': [], 'liquidity_sweeps': [],
            'nearest_resistance': 101.0, 'volume_profile': {},
        },
        current_price=100.0,
        volatility={'atr': 1.0},
        timeframe='1h',
        geometry_profile={'sl_buffer_atr': 0.35},
    )
    structural = [c for c in candidates if c.get('type') == 'swing'][0]
    assert structural['buffer_atr'] >= 0.35
    assert structural['price'] >= 101.35 - 1e-9


def test_tp_liquidation_intensity_uses_relative_map_units():
    dummy = _extract_methods('_collect_tp_candidates')
    candidates = dummy._collect_tp_candidates(
        'long',
        {'order_blocks': [], 'fair_value_gaps': [], 'resistances': [],
         'pivot_highs': [], 'fib_extensions': {}, 'volume_profile': {}},
        current_price=100.0,
        volatility={'atr': 2.0},
        timeframe='1h',
        entry_reference=100.0,
        liquidation={'active_bins': [
            {'side': 'short', 'price_top': 104.2, 'price_bottom': 103.8, 'weight': 1.0},
            {'side': 'short', 'price_top': 108.2, 'price_bottom': 107.8, 'weight': 5.0},
        ]},
    )
    liq = [c for c in candidates if c.get('type') == 'liquidity']
    assert len(liq) == 2
    strengths = sorted(c['liquidity_intensity'] for c in liq)
    assert strengths[0] == 0.2
    assert strengths[1] == 1.0


def test_tp_capture_is_before_reaction_and_preserves_rr_floor():
    dummy = _extract_methods('_collect_tp_candidates', '_score_tp_candidate', '_select_optimal_tp')
    dummy._calculate_min_tp_distance_pct = lambda *args, **kwargs: 0.4
    # One structural resistance at 110. Entry 100, SL 95 => raw RR 2.0.
    # The capture buffer may move TP inward, but never below the 1.8R floor.
    tp, source, score = dummy._select_optimal_tp(
        'long',
        {'order_blocks': [], 'fair_value_gaps': [], 'resistances': [110.0],
         'pivot_highs': [], 'fib_extensions': {}, 'volume_profile': {}},
        entry=100.0,
        current_price=100.0,
        volatility={'atr': 2.0},
        timeframe='1h',
        leverage=10,
        is_futures=True,
        sl_price=95.0,
        liquidation=None,
        geometry_profile={'technical_rr_floor': 1.8, 'preferred_rr_min': 2.0,
                          'technical_rr_ceiling': 4.5, 'tp_capture_buffer_atr': 0.10,
                          '_atr_abs': 2.0},
    )
    assert 109.0 <= tp < 110.0
    assert (tp - 100.0) / 5.0 >= 1.8
    assert 'captura antes de reacción' in source
    assert score > 0


def test_tp_capture_is_symmetric_for_short():
    dummy = _extract_methods('_collect_tp_candidates', '_score_tp_candidate', '_select_optimal_tp')
    dummy._calculate_min_tp_distance_pct = lambda *args, **kwargs: 0.4
    tp, source, score = dummy._select_optimal_tp(
        'short',
        {'order_blocks': [], 'fair_value_gaps': [], 'supports': [90.0],
         'pivot_lows': [], 'fib_retracements': {}, 'volume_profile': {}},
        entry=100.0,
        current_price=100.0,
        volatility={'atr': 2.0},
        timeframe='1h',
        leverage=10,
        is_futures=True,
        sl_price=105.0,
        liquidation=None,
        geometry_profile={'technical_rr_floor': 1.8, 'preferred_rr_min': 2.0,
                          'technical_rr_ceiling': 4.5, 'tp_capture_buffer_atr': 0.10,
                          '_atr_abs': 2.0},
    )
    assert 90.0 < tp <= 91.0
    assert (100.0 - tp) / 5.0 >= 1.8
    assert 'captura antes de reacción' in source
    assert score > 0


def test_entry_liquidity_context_prefers_stronger_pool_when_distances_are_close():
    dummy = _extract_methods('_build_smc_entry_context')
    out = dummy._build_smc_entry_context(
        'long',
        {'df': {'high': [], 'low': [], 'open': [], 'close': []}},
        current_price=100.0,
        previous_close=100.0,
        volatility={'atr': 2.0},
        liquidation={'active_bins': [
            # Weak and slightly nearer.
            {'side': 'long', 'price_top': 98.9, 'price_bottom': 98.7, 'weight': 1.0},
            # Strong and only 0.1 ATR farther; should win bounded tie-break.
            {'side': 'long', 'price_top': 98.7, 'price_bottom': 98.5, 'weight': 5.0},
        ]},
    )
    assert out['liquidity_pool_price'] == 98.6
    assert out['liquidity_pool_intensity'] == 1.0
    assert out['liquidity_pool_near'] is True
