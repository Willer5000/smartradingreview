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


def test_free_runtime_does_not_auto_schedule_heavy_futures_intrabar_refresh():
    assert "@app.route('/api/futures/opportunities/refresh', methods=['POST'])" not in app
    assert '_futScheduleSelectedIntrabarRefresh' not in fut
    assert "'/api/futures/opportunities/refresh'" not in fut
    # Selected analysis can still populate INTRABAR preview; there is simply no
    # autonomous heavy polling loop on the 512 MB worker.
    assert '_FUTURES_INTRABAR_DIAGNOSTIC_CACHE = {}' in app


def test_futures_stale_intrabar_preview_expires_quickly():
    assert 'def _futures_intrabar_ttl_seconds(timeframe):' in app
    assert 'cadence * 2' in app


def test_spot_intrabar_preview_is_separate_but_not_auto_polled_on_free_runtime():
    assert 'def _run_spot_intrabar_preview' in app
    assert "@app.route('/api/spot/signals/active/refresh', methods=['POST'])" not in app
    assert '_start_spot_intrabar_refresh_async' not in app
    assert '_scheduleSpotIntrabarRefresh' not in spot
    assert "'/api/spot/signals/active/refresh'" not in spot
