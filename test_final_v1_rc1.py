from pathlib import Path

ROOT = Path(__file__).resolve().parent


def txt(name):
    return (ROOT / name).read_text(encoding='utf-8')


def test_canonical_40_cell_contract_and_no_pooled_counting():
    src = txt('research_evidence_fusion.py')
    assert '_COVERAGE_TARGET = 40' in src
    assert '_canonical_cell_key' in src
    assert 'if sym in _FUTURES_SYMBOLS and tf in _FUTURES_TFS' in src
    assert 'return None' in src
    assert 'shadow_live_candidates' in src
    assert 'oos_wr_weighted' in src and 'oos_total_r' in src


def test_simple_analytics_default_and_heavy_diagnostics_on_demand():
    html = txt('templates/analytics.html')
    js = txt('static/analytics.js')
    assert 'Estado V1 · lectura rápida' in html
    assert 'v1-spot-live' in html and 'v1-futures-live' in html
    assert 'v1-spot-oos' in html and 'v1-futures-oos' in html
    assert 'id="q5-v2-section"' in html and 'chart-container mb-4 v1-advanced' in html
    assert 'legacy-analytics-section' in html and 'v1-advanced' in html
    assert 'Resultado OOS / PnL' in js and 'WR ${wr}' in js
    assert 'window.__V1_ADVANCED_ANALYTICS__ = false' in js
    # Heavy legacy calls exist only in the advanced-mode loader, not coreTasks.
    core = js.split('const coreTasks = [',1)[1].split('];',1)[0]
    assert 'loadQualityV2' in core and 'loadLearningGovernanceStatus' in core and 'loadResearchFederationAnalytics' in core
    assert 'loadSummary' not in core and 'loadHeatmap' not in core and 'loadPnLDistribution' not in core


def test_macro_current_vs_next_event_and_cex_context_preserved():
    macro = txt('macro_context.py')
    script = txt('static/script.js')
    assert 'FOMC current-year block not found' in macro
    assert 'current_risk_level' in macro
    assert 'next_event_risk_level' in macro and 'next_event_hours' in macro
    assert 'exchange_flow' in macro and 'fundamental_signal_context' in macro
    assert 'MACRO AHORA' in script and 'PRÓXIMO' in script


def test_scientist_has_observable_attempt_and_read_only_status_path():
    app = txt('app.py')
    assert 'thread_started_at' in app and 'last_watchdog_heartbeat_at' in app
    assert '_ensure_ai_learning_scientist_thread' in app
    start=app.index('def api_ai_gemini_activity')
    endpoint=app[start:start+4200]
    assert "_kick_ai_learning_scientist_async('status-self-heal')" not in endpoint
