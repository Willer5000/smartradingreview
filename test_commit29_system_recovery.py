import inspect
from pathlib import Path

import commit29_core as c29


def test_regime_strong_adx_conflict_is_transitional_not_ranging():
    r = c29.classify_market_regime(
        {'adx': 27.5, 'plus_di': 17.3, 'minus_di': 19.2, 'direction': 'bearish'},
        {'atr_pct': 2.0, 'bb_width': 3.0, 'volatility_percentile': 60, 'volatility_ratio': 1.1},
    )
    assert r['regime'] == 'TRANSITIONAL'


def test_missing_context_not_neutral_evidence():
    assert not c29.context_available({'success': False, 'trend': {'direction': 'neutral', 'adx': 0}})
    assert not c29.context_available({'success': True, 'context_available': False, 'trend': {'direction': 'neutral', 'adx': 0}})
    assert c29.context_available({'success': True, 'trend': {'direction': 'bullish', 'adx': 21.0}})


def test_deploy_files_target_commit29():
    root = Path(__file__).resolve().parent
    assert 'commit29_main_entrypoint:app' in (root / 'Procfile').read_text(encoding='utf-8')
    assert 'commit29_main_entrypoint:app' in (root / 'render.yaml').read_text(encoding='utf-8')


def test_app_has_runtime_version_and_visual_pressure_lane():
    text = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert "@app.route('/api/runtime/version')" in text
    assert 'COMMIT29_CACHE_ONLY_PRESSURE' in text
    assert 'LIQUIDATION_HEATMAP_MAX_RESIDENT' in text
    assert 'RESOURCE_PRESSURE_ABORT' in text


def test_champion_detection_priority_present():
    text = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert 'detection priority follows LIVE statistical authority' in text
    assert '_c29_route_registry' in text


def test_safety_contract_not_lowered():
    text = Path(__file__).with_name('contextual_quality_commit28.py').read_text(encoding='utf-8')
    assert 'PREMIUM_SAFETY_MIN = 75.0' in text
    assert 'RR_MIN = 1.8' in text and 'RR_MAX = 3.5' in text
    assert 'MAX_ATR_STRESS_PCT = 25.0' in text


def test_native_execution_abi_supports_execution_observations():
    # Static text check avoids importing the full Flask system in lightweight CI.
    text = Path(__file__).with_name('futures_system.py').read_text(encoding='utf-8')
    assert 'execution_observations=None' in text
