from pathlib import Path

APP = Path('app.py').read_text(encoding='utf-8')
JS = Path('static/script.js').read_text(encoding='utf-8')


def test_spot_has_global_interactive_priority():
    assert 'def _mark_system_interactive_priority' in APP
    assert "owner.startswith(('futures-ui:', 'spot-ui:'))" in APP
    assert "spot-ui:tgp:" in APP
    assert "spot-ui:analyze:" in APP


def test_tgp_reuses_single_expert_system():
    assert 'trading_system = expert_system' in APP
    assert 'api_analyze_with_portfolio._trading_system = (' not in APP


def test_background_is_throttled_not_disabled():
    assert "FUTURES_SNAPSHOT_MIN_INTERVAL_SECONDS', '120'" in APP
    assert "FUTURES_INCREMENTAL_INTERVAL_SECONDS', '30'" in APP
    assert "LEARNING_MICROBATCH_ROWS', '8'" in APP
    assert "LEARNING_MICROBATCHES_PER_CYCLE', '1'" in APP


def test_spot_frontend_does_not_launch_two_extra_analyses():
    assert 'SPOT: CORRELACIÓN SIN ANÁLISIS EXTRA' in JS
    marker = JS.index('SPOT: CORRELACIÓN SIN ANÁLISIS EXTRA')
    tail = JS[marker: marker + 1500]
    assert 'otrosPares.map' not in tail
    assert 'updateCorrelationInfo' in tail


def test_busy_retry_applies_to_spot_and_futures():
    assert 'if (error?.busy)' in JS
    assert "const analysisHttpTimeoutMs = window.IS_FUTURES_PAGE ? 12000 : 45000;" in JS
