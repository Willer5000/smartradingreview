from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SCRIPT = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
FUTURES = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def test_python_syntax_and_spot_singleflight_present():
    ast.parse(APP)
    assert 'def _run_spot_analysis_singleflight' in APP
    assert APP.count('_run_spot_analysis_singleflight(') >= 3  # helper + two UI callers
    assert '[H3 SINGLEFLIGHT]' in APP
    assert '_SPOT_ANALYSIS_SINGLEFLIGHT_STALE_SECONDS = 120.0' in APP


def test_previous_signals_refresh_on_closed_4h_bucket_not_fixed_10_min_loop():
    assert '_SPOT_PREVIOUS_FASTEST_SECONDS = 4 * 60 * 60' in APP
    assert 'def _spot_previous_refresh_due' in APP
    assert 'cache_duration = 600' not in APP
    assert "time.sleep(5 * 60)" in APP
    assert "'processing_age_seconds': _spot_previous_processing_age()" in APP
    assert "'previous_ts': previous_ts" in APP
    assert "'active_ts': active_ts" in APP


def test_frontend_global_analysis_lock_always_has_expiry_and_finally_release():
    assert 'function _h3AcquireAnalysisLock' in SCRIPT
    assert '(now - startedAt) > 90000' in SCRIPT
    assert "_h3ReleaseAnalysisLock('runCompleteAnalysis')" in SCRIPT
    assert "_h3ReleaseAnalysisLock('getInstantRecommendation')" in SCRIPT
    auth_pos = SCRIPT.index("function getInstantRecommendation(attempt = 1)")
    auth_block = SCRIPT[auth_pos:auth_pos + 900]
    assert auth_block.index('if (!isAuthenticated())') < auth_block.index("_h3AcquireAnalysisLock('getInstantRecommendation')")


def test_spot_signal_polling_is_bounded_and_http_has_timeout():
    assert 'function _h3SpotPollSchedule' in SCRIPT
    assert 'elapsed >= 30000 || state.retries >= 6' in SCRIPT
    assert 'function _h3FetchJson' in SCRIPT
    assert "_h3FetchJson('/api/spot/signals/active', 10000" in SCRIPT
    assert "_h3FetchJson('/api/previous_signals', 10000" in SCRIPT
    assert 'la espera automática terminó para evitar carga infinita' in SCRIPT.lower()


def test_futures_keeps_snapshot_and_bounds_warmup_wait():
    assert 'function _futSignalSchedule' in FUTURES
    assert 'elapsed >= 30000 || retries >= 6' in FUTURES
    assert 'async function _futFetchJsonTimeout' in FUTURES
    assert 'const blockingWarmup = Boolean(running && !json.cache_ready && signals.length === 0);' in FUTURES
    assert 'if (!window.futuresActiveLoaded)' in FUTURES
    assert 'if (!window.futuresPrevLoaded)' in FUTURES
    assert 'petición anterior todavía en curso; no se duplica' in FUTURES


def test_h3_cache_bust_is_installed():
    assert '20260913-H3-NO-INFINITE-LOADING' in INDEX
