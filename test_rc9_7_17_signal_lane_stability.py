from pathlib import Path

ROOT = Path(__file__).parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SPOT = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
FUT = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')


def test_spot_active_endpoint_can_schedule_selected_intrabar_without_closed_fallback():
    assert 'def _schedule_spot_intrabar_preview_async' in APP
    assert "request.args.get('symbol')" in APP
    assert "request.args.get('timeframe')" in APP
    assert "Activas = señal provisional de la vela en formación" in APP
    assert "_spot_intrabar_preview_cached(requested_symbol, requested_tf)" in APP


def test_spot_frontend_requests_selected_intrabar_and_prioritizes_lanes():
    assert "URLSearchParams" in SPOT
    assert "'/api/spot/signals/active'" not in SPOT or "`/api/spot/signals/active?${activeParams.toString()}`" in SPOT
    assert 'Vigentes > Confirmadas > Activas' in SPOT
    assert 'window.prioritizeSpotSignalLanes' in SPOT


def test_futures_opportunities_warms_only_selected_cell_not_full_universe():
    assert "selected_symbol = str(request.args.get('symbol')" in APP
    assert "_start_futures_ui_analysis_async(selected_symbol, selected_tf)" in APP
    assert "No se escanean 63 celdas intrabar en Render Free" in APP
    assert "processing_selected" in APP


def test_futures_frontend_prioritizes_vigent_then_confirmed_then_active():
    assert 'Vigentes > Confirmadas > Activas' in FUT
    assert 'window.prioritizeFuturesSignalLanes' in FUT
    assert "cargando Vigentes (prioridad 1)" in FUT
    assert "cargando Confirmadas (prioridad 2)" in FUT
    assert "cargando Activas intrabar (prioridad 3)" in FUT


def test_internal_review_panels_are_removed_from_frontend_but_backend_not_deleted():
    assert "document.getElementById('review-trader-panel-container')?.remove()" in FUT
    assert "document.getElementById('review-global-panel-container')?.remove()" in FUT
    assert 'ReviewTrader/Strategy Bank siguen activos en backend' in FUT
