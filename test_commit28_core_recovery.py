from __future__ import annotations

import ast
from pathlib import Path

import commit28_core
import contextual_quality_commit28 as cq

ROOT = Path(__file__).resolve().parent


def test_zero_confidence_no_operar_becomes_abstain():
    action, legacy, abstain = commit28_core.normalize_specialist_action('NO_OPERAR', 0)
    assert action == 'ABSTAIN'
    assert legacy == 'NO_OPERAR'
    assert abstain is True


def test_real_no_operar_objection_is_preserved():
    action, legacy, abstain = commit28_core.normalize_specialist_action('NO_OPERAR', 100)
    assert action == 'NO_OPERAR'
    assert legacy == 'NO_OPERAR'
    assert abstain is False


def test_btc_context_reuses_current_then_previous_without_io():
    current = {('BTC-USDT', '1h'): {'success': True, 'trend': {'adx': 36.3}}}
    previous = {('BTC-USDT', '1h'): {'success': True, 'trend': {'adx': 25.0}}}
    row, source = commit28_core.select_cached_btc_context(current, previous, '1h')
    assert row is current[('BTC-USDT', '1h')]
    assert source == 'CURRENT_REFRESH'
    row, source = commit28_core.select_cached_btc_context({}, previous, '1h')
    assert row is previous[('BTC-USDT', '1h')]
    assert source == 'PREVIOUS_CACHE'


def test_futures_native_abi_signature_accepts_execution_observations():
    tree = ast.parse((ROOT / 'futures_system.py').read_text(encoding='utf-8'))
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'calculate_entry_levels']
    assert funcs
    target = max(funcs, key=lambda n: n.end_lineno or 0)
    names = [a.arg for a in target.args.args]
    assert 'execution_observations' in names
    segment = ast.get_source_segment((ROOT / 'futures_system.py').read_text(encoding='utf-8'), target) or ''
    assert 'execution_observations=execution_observations' in segment
    assert '_multiasset_pre_execution_route' in segment


def _base_result(*, fallback: bool, safety: float, atr: float):
    return {
        'system_type': 'futures',
        'analysis_mode': 'CLOSED_CANDLE',
        'source_candle_closed': True,
        'market_data_is_synthetic': False,
        'decision': {'action': 'LONG'},
        'trend': {'direction': 'bullish'},
        'momentum': {'direction': 'bullish'},
        'volatility': {'atr_pct': 1.5},
        'structure': {'order_blocks': [1]},
        'levels': {
            'entry': 100.0,
            'stop_loss': 98.0,
            'take_profit': 104.0,
            'risk_reward': 2.0,
            'manual_geometry_fallback': fallback,
            'execution_safety': safety,
            'entry_quality_score': 80.0,
            'sl_quality_score': 80.0,
            'tp_quality_score': 80.0,
            'risk_control': {
                'estimated_sl_loss_pct_margin': 2.0,
                'estimated_atr_stress_loss_pct_margin': atr,
            },
        },
        'operational_intelligence': {
            'commit19_champion': {
                'champion_id': 'F30_SHARED_LIQ_SWEEP_MSS_POI_V1',
                'eligible_for_execution_routing': True,
                'authority': 'LIVE_CHAMPION_COMMIT19',
                'state': 'LIVE_CHAMPION',
                'live_context_reason': 'TEST_ROUTE',
            }
        },
    }


def test_fallback_reports_root_cause_not_fake_safety_atr():
    result = _base_result(fallback=True, safety=0.0, atr=0.0)
    out = cq.evaluate_publication(
        result, symbol='BTC-USDT', timeframe='30m',
        quality={'commit27_quality_ready': True, 'quality': {'Q1': 80, 'Q2': 80, 'Q3': 80, 'Q4': 80, 'Q5': 80, 'Q6': 80, 'Q7': 80, 'Q8': 80, 'Q9': 80}},
    )
    assert 'FALLBACK_GEOMETRY_NOT_PUBLISHABLE' in out['hard_reason_codes']
    assert 'PREMIUM_SAFETY_BELOW_75' not in out['hard_reason_codes']
    assert 'ATR_STRESS' not in out['hard_reason_codes']
    assert out['diagnostics']['fallback_secondary_guards_evaluated'] is False


def test_primary_geometry_still_enforces_safety_and_atr():
    result = _base_result(fallback=False, safety=74.0, atr=0.0)
    out = cq.evaluate_publication(
        result, symbol='BTC-USDT', timeframe='30m',
        quality={'commit27_quality_ready': True, 'quality': {'Q1': 80, 'Q2': 80, 'Q3': 80, 'Q4': 80, 'Q5': 80, 'Q6': 80, 'Q7': 80, 'Q8': 80, 'Q9': 80}},
    )
    assert 'PREMIUM_SAFETY_BELOW_75' in out['hard_reason_codes']
    assert 'ATR_STRESS' in out['hard_reason_codes']


def test_deploy_points_to_commit28():
    proc = (ROOT / 'Procfile').read_text(encoding='utf-8')
    render = (ROOT / 'render.yaml').read_text(encoding='utf-8')
    assert 'commit28_main_entrypoint:app' in proc
    assert 'commit28_main_entrypoint:app' in render
    assert 'commit27_main_entrypoint:app' not in proc
