from pathlib import Path
import ast
import pytest

ROOT=Path(__file__).resolve().parent

def read(path):
    target = ROOT / path
    if not target.exists():
        pytest.skip(f'Archivo de soporte no incluido en este paquete incremental: {path}')
    return target.read_text(encoding='utf-8')


def test_multiasset_price_uses_multiasset_engine_not_spot():
    app=read('app.py')
    block=app[app.index("@app.route('/api/price')"):app.index("@app.route('/api/telegram", app.index("@app.route('/api/price')"))]
    assert "if market == 'multiasset':" in block
    assert "multi_market.get_kucoin_data(symbol, interval)" in block
    assert "elif market == 'futures':" in block


def test_multiasset_navigation_gets_interactive_priority_and_background_cooldown():
    app=read('app.py')
    assert "'/multiasset',\n    '/analytics'" in app
    assert "'multi-background:'," in app
    assert "_mark_system_interactive_priority(seconds=120)" in app
    multi=app[app.index('def _multiasset_run_analysis'):app.index('def _multiasset_compact_telegram')]
    assert "timeout=6.0 if is_ui else 0.0" in multi
    assert "'partial':True" in multi
    assert "'retry_after_ms':7000" in multi


def test_microstructure_uses_deriv_api_base_and_cache_only_multi_endpoint():
    app=read('app.py')
    script=read('static/script.js')
    endpoint=app[app.index("@app.route('/api/multiasset/microstructure'"):app.index("@app.route('/api/multiasset/position-guardian'")]
    assert 'does not call another exchange endpoint' in endpoint
    assert "RESOURCE_GUARDED_PROXY" in endpoint
    fetch=script[script.index('async function _fetchOrderFlowUi'):script.index('function updateOrderFlowChart')]
    assert "window.DERIV_API_BASE || '/api/futures'" in fetch
    assert '/api/futures/microstructure?symbol=' not in fetch
    assert 'timeframe=${encodeURIComponent(tf)}' in fetch


def test_multiasset_busy_polling_is_bounded_and_not_infinite():
    script=read('static/script.js')
    assert 'const maxBusyMs = isMulti ? 30000 : 90000;' in script
    assert 'const maxBusyRetries = isMulti ? 3 : 8;' in script
    assert 'No se seguirá haciendo polling' in script


def test_frontend_humanizes_multiasset_and_protected_microstructure():
    template=read('templates/index.html')
    multi=read('multiasset_system.py')
    assert "'CL-USDT': 'CL (Petróleo WTI)'" in template
    assert 'Microestructura Multi-Activo' in template
    assert 'Mapa de Liquidez / Barridos (proxy)' in template
    assert 'Profundidad y presión de compra/venta disponibles para este mercado.' in template
    assert 'no descarga Order Book/OI/funding extra' not in template
    assert '_humanize_multiasset_message' in multi
    assert 'ast.literal_eval' in multi
    assert "text.replace(str(symbol), display)" in multi


def test_analysis_pdf_is_physically_removed_but_learning_pdf_stays():
    template=read('templates/index.html')
    app=read('app.py')
    assert 'downloadAnalysisReport' not in template
    assert '/api/generate_report' not in template
    assert "@app.route('/api/review/learning_pdf')" in app
    assert 'window.downloadLearningReport' in template


def test_analytics_navigation_and_filter_patch_include_multiasset():
    app=read('app.py')
    assert 'id="rc12-1-analytics-ui-patch"' in app
    assert "a.href='/multiasset'" in app
    assert "opt.value='multiasset'" in app
    assert "'CL-USDT':'CL (Petróleo WTI)'" in app
    assert "q5.style.display=isMulti?'none':''" in app


def test_analytics_separates_multiasset_from_futures_without_schema_change():
    analytics=read('analytics_service.py')
    assert 'MULTIASSET_ANALYTICS_SYMBOLS' in analytics
    assert "requested == 'multiasset'" in analytics
    assert "requested == 'futures'" in analytics
    assert 'not _analytics_is_multiasset_signal(r)' in analytics
    assert "'OFFICIAL_CURRENT_MULTI_ASSET'" in analytics
    assert "'multiasset':\n                self._q5_aggregate" in analytics


def test_multiasset_header_kpi_is_cache_only_no_supabase_read():
    app=read('app.py')
    start=app.index("if market_filter == 'multiasset':")
    end=app.index("signals = [s for s in _collect_frontend_signals()", start)
    block=app[start:end]
    assert "_MULTI_ASSET_CACHE" in block
    assert 'from supabase_client' not in block
    assert ".table('signals')" not in block
    assert "'source': 'multiasset_local_cache_no_db'" in block


def test_info_widget_now_documents_multiasset_and_resource_policy():
    app=read('app.py')
    block=app[app.index('def _rc9_system_info_widget_html'):app.index('def _rc12_1_analytics_ui_patch_html')]
    assert '<h4>Multi-Activo</h4>' in block
    assert '<h4>Análisis</h4>' in block
    assert 'scanner no escribe en Supabase ni llama IA' in block
    inject=app[app.index('def _memory_cleanup_after_analytics'):app.index("@app.route('/api/system/bandwidth-stats'")]
    assert "'/', '/futures', '/multiasset', '/analytics'" in inject


def test_no_resource_budget_expansion_or_new_sql():
    # Commit 12.1 does not touch render.yaml or create migrations.
    if (ROOT/'render.yaml').exists():
        y=read('render.yaml')
        assert 'MAIN_SUPABASE_DAILY_BUDGET_MB' in y and 'value: "12"' in y
        assert 'workers 1 --threads 2' in y
    assert not any(ROOT.glob('*.sql'))
    app=read('app.py')
    assert "multi-background:" in app
    assert 'threading.Thread' not in app[app.index('# COMMIT 12 — MULTI-ACTIVO RESOURCE-GOVERNED RUNTIME'):app.index('# COMMIT 12 — MULTI-ACTIVO API')]


def test_modified_python_parses():
    for name in ('app.py','multiasset_system.py','analytics_service.py'):
        ast.parse(read(name), filename=name)
