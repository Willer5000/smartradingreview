from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUT = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
SCRIPT = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def test_active_is_intrabar_and_not_persisted():
    assert "analysis_mode'] = 'INTRABAR_PREVIEW'" in APP
    assert "source_candle_closed'] = False" in APP
    assert "if str(result.get('analysis_mode') or '').upper() != 'INTRABAR_PREVIEW'" in APP
    assert "Activas son efímeras por definición" in APP
    assert "'active': None" in APP


def test_spot_confirmed_is_latest_closed_candle():
    assert "prepare_spot_frame(df, timeframe, previous=False)" in APP
    assert "prepare_spot_frame(df, timeframe, previous=True)" not in APP


def test_futures_current_ui_uses_intrabar_preview_but_closed_cache_survives():
    worker = APP[APP.index('def _start_futures_ui_analysis_async'):APP.index('def _serialize_futures_cache')]
    assert 'closed_candle_only=False' in worker
    assert 'intrabar_preview=True' in worker
    assert '_store_futures_intrabar_preview' in worker
    assert "_futures_analysis_cache['data'] = current_data" not in worker


def test_futures_active_list_reads_preview_cache_not_closed_analysis():
    route = APP[APP.index("@app.route('/api/futures/opportunities'"):APP.index('# COMMIT 15B', APP.index("@app.route('/api/futures/opportunities'"))]
    assert '_list_futures_intrabar_active()' in route
    assert "cache.get('analysis')" not in route
    assert "'intrabar': True" in route


def test_futures_preview_never_registers_reviewtrader():
    assert 'intrabar_preview: bool = False' in FUT
    assert "result['analysis_mode'] = 'INTRABAR_PREVIEW'" in FUT
    assert 'if intrabar_preview:' in FUT
    assert 'Preview efímero: jamás persiste ni alimenta ReviewTrader.' in FUT


def test_visual_noise_removed_and_adaptive_preview_refresh_present():
    assert 'Actual · vela en formación · sólo visual' not in SCRIPT
    assert 'Los gráficos e indicadores incorporan provisionalmente' not in TEMPLATE
    assert 'señales basadas en velas cerradas' not in TEMPLATE
    assert "'30m': 90000" in TEMPLATE
    assert "'1h': 120000" in TEMPLATE
    assert 'scheduleIntrabarAnalysis' in TEMPLATE
