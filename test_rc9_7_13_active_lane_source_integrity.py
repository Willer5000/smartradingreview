from pathlib import Path

ROOT = Path(__file__).resolve().parent
app = (ROOT / 'app.py').read_text(encoding='utf-8')
fut = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
spot = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')


def test_futures_active_diagnostics_are_intrabar_only():
    assert '_FUTURES_INTRABAR_DIAGNOSTIC_CACHE = {}' in app
    assert "'source_context': 'INTRABAR_ANALYSIS_ONLY'" in app
    assert "'manual_save_allowed': False" in app
    assert "'other_directional_signals': diagnostics[:limit]" in app


def test_futures_frontend_reads_active_diagnostics_from_opportunities():
    assert "futRenderAnalysisDiagnostics(data, 'active')" in fut
    active_route_pos = fut.index("'/api/futures/signals/active?min_confidence=55")
    next_chunk = fut[active_route_pos:active_route_pos + 12000]
    assert "json,\n                'active'" not in next_chunk


def test_confirmed_and_vigent_sources_remain_closed_lifecycle():
    assert "@app.route('/api/futures/signals/previous')" in app
    assert "'source_context': 'PREVIOUS_CONFIRMED'" in app
    assert "@app.route('/api/futures/signals/active')" in app
    assert "'source_context': 'ACTIVE_CONFIRMED'" in app


def test_selected_futures_intrabar_refresh_is_scheduled_without_universe_scan():
    assert "@app.route('/api/futures/opportunities/refresh', methods=['POST'])" in app
    assert '_FUTURES_INTRABAR_REFRESH_SECONDS' in app
    assert '_futScheduleSelectedIntrabarRefresh' in fut
    assert "'/api/futures/opportunities/refresh'" in fut
    assert "'30m': 90000" in fut
    assert "'1h': 120000" in fut


def test_futures_stale_intrabar_preview_expires_quickly():
    assert 'def _futures_intrabar_ttl_seconds(timeframe):' in app
    assert 'cadence * 2' in app


def test_spot_selected_intrabar_refresh_is_real_and_separate():
    assert "@app.route('/api/spot/signals/active/refresh', methods=['POST'])" in app
    assert '_start_spot_intrabar_refresh_async' in app
    assert '_scheduleSpotIntrabarRefresh' in spot
    assert "'/api/spot/signals/active/refresh'" in spot
    assert "'4h': 90000" in spot
