from pathlib import Path

import leverage_policy as lev

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUT = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
BUILD = (ROOT / 'build.sh').read_text(encoding='utf-8')
REVIEW = (ROOT / 'review_trader.py').read_text(encoding='utf-8')


def test_runtime_identity_and_pipeline_generation_are_3343():
    assert 'COMMIT33_4_3_EXECUTION_ECONOMICS_DETAIL_CORE_V1' in APP
    assert "PIPELINE_GENERATION = \"33.4.3\"" in (ROOT / 'pipeline_integrity.py').read_text(encoding='utf-8')
    assert "_FUTURES_CACHE_SCHEMA_VERSION = 7" in APP


def test_removed_commit28_preexec_symbol_is_not_in_live_futures_source():
    assert '_commit28_preexec_route' not in FUT
    assert 'commit28_core' not in FUT
    assert 'commit29_core' not in FUT
    assert 'commit30_core' not in FUT


def test_review_trader_uuid_dependency_is_explicit():
    assert '\nimport uuid\n' in REVIEW
    assert 'uuid.uuid5(' in REVIEW


def test_saved_signal_detail_routes_multiasset_and_never_hides_record_when_chart_missing():
    block = APP[APP.index("@app.route('/api/saved_signals/<signal_id>/chart_data'"):APP.index("@app.route('/api/kpis/frontend_signals')")]
    assert 'from multiasset_system import MULTIASSET_SYMBOLS, multiasset_system' in block
    assert "chart_market = 'multiasset'" in block
    assert "'signal': sig" in block
    assert "'chart_available': bool(candles.get('time'))" in block
    assert "'success': True" in block
    # Previous behavior returned before the technical sheet could render.
    assert "'error': 'Sin datos de velas Futures perpetuos'" not in block


def test_publication_grade_uses_full_technical_headroom_and_size_controls_money_risk():
    result = lev.select_risk_budget_leverage(
        minimum_required=1,
        sl_distance_pct=0.8,
        max_by_risk=30,
        max_by_atr_stress=30,
        safety_score=82,
        timeframe_static_max=30,
        fallback_exchange_max=50,
        verified_exchange_max=50,
        max_by_liquidation_buffer=30,
        risk_allocation_fraction=1.0,
        emergency_max_leverage=50,
        quality_score=86,
    )
    assert result is not None
    assert result['leverage'] == 30
    assert result['publication_grade_full_headroom'] is True
    assert result['recommended_risk_allocation_fraction'] < 1.0


def test_lower_quality_does_not_receive_full_headroom():
    result = lev.select_risk_budget_leverage(
        minimum_required=1,
        sl_distance_pct=1.0,
        max_by_risk=30,
        max_by_atr_stress=30,
        safety_score=68,
        timeframe_static_max=30,
        fallback_exchange_max=50,
        verified_exchange_max=50,
        max_by_liquidation_buffer=30,
        emergency_max_leverage=50,
        quality_score=68,
    )
    assert result is not None
    assert result['leverage'] == 24
    assert result['publication_grade_full_headroom'] is False


def test_build_destroys_python_and_pytest_caches_before_compile():
    assert "-name '__pycache__'" in BUILD
    assert "-name '.pytest_cache'" in BUILD
    assert "-name '*.pyc'" in BUILD
    assert 'python -m compileall -q -j 1 .' in BUILD
