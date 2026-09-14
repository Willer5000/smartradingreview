from pathlib import Path

ROOT = Path(__file__).resolve().parent


def txt(name):
    return (ROOT / name).read_text(encoding='utf-8')


def test_scientist_timezone_and_status_read_only():
    app = txt('app.py')
    assert 'from datetime import datetime, timedelta, timezone' in app
    start = app.index('def api_ai_gemini_activity')
    tail = app[start:start + 4200]
    assert "_kick_ai_learning_scientist_async('status-self-heal')" not in tail
    assert 'this status endpoint is strictly READ ONLY' in tail


def test_active_futures_contract_retires_5m_15m():
    fut = txt('futures_system.py')
    start = fut.index('FUTURES_TIMEFRAMES = {')
    end = fut.index('FUTURES_CONTRACT_SYMBOLS', start)
    block = fut[start:end]
    assert "'30m'" in block and "'1h'" in block and "'2h'" in block and "'4h'" in block
    assert "'5m'" not in block and "'15m'" not in block
    idx = txt('templates/index.html')
    # Active selector no longer offers retired trading TFs.
    selector_start = idx.index('id="interval-select"') if 'id="interval-select"' in idx else 0
    selector = idx[selector_start:selector_start+1800]
    assert '>5m<' not in selector and '>15m<' not in selector


def test_research_fusion_uses_40_cells_and_latest_cell_state():
    fusion = txt('research_evidence_fusion.py')
    assert '_COVERAGE_TARGET = 40' in fusion
    assert '_FUTURES_TFS = ("30M","1H","2H","4H")' in fusion
    assert 'Current cell state must win over an older SHADOW_READY' in fusion


def test_analytics_is_bounded_and_middle_ground():
    js = txt('static/analytics.js')
    html = txt('templates/analytics.html')
    assert 'async function v1FetchJson' in js
    assert 'AbortController' in js
    assert 'Promise.allSettled(coreTasks)' in js
    assert 'Monitoreo de rentabilidad y continuidad' in html
    assert 'v1-validated-live-body' in html
    assert 'v1-coverage-matrix-body' in html
    assert '40 celdas activas' in html
    assert '20260914-FINAL-V1-RC2' in html


def test_live_kpis_ignore_retired_futures_without_deleting_history():
    svc = txt('analytics_service.py')
    assert "if active_tf not in {'30m', '1h', '2h', '4h'}" in svc
    assert 'Historical rows remain in Supabase for audit/learning' in svc


def test_memory_logs_are_telemetry_not_an_active_spam_source():
    app = txt('app.py')
    assert "MEMORY_DEBUG_LOGS" in app
    assert 'under_pressure' in app
    assert 'return state' in app
