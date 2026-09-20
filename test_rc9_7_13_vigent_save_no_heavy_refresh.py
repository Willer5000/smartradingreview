from pathlib import Path

ROOT = Path(__file__).resolve().parent
app = (ROOT / 'app.py').read_text(encoding='utf-8')


def _save_route_scope():
    start = app.index("@app.route('/api/saved_signals', methods=['POST'])")
    end = app.index("@app.route('/api/saved_signals/<signal_id>', methods=['GET'])", start)
    return app[start:end]


def test_saved_signal_validation_uses_read_only_futures_snapshot():
    scope = _save_route_scope()
    assert scope.count('_get_futures_analysis_snapshot_read_only()') >= 2
    assert '_get_or_refresh_futures_analysis()' not in scope


def test_read_only_snapshot_never_starts_analysis_or_restore():
    start = app.index('def _get_futures_analysis_snapshot_read_only():')
    end = app.index('def _get_or_refresh_futures_analysis(', start)
    scope = app[start:end]
    assert "with cache['lock']" in scope
    assert "cache.get('data')" in scope
    assert '_trigger_futures_' not in scope
    assert '_get_or_refresh_futures_analysis' not in scope


def test_save_fails_closed_with_http_409_when_snapshot_missing():
    scope = _save_route_scope()
    assert "current_cache.get('snapshot_available') is not True" in scope
    assert 'El snapshot de Futuros todavía no está disponible.' in scope
    assert 'Actualiza Futuros y vuelve a intentarlo.' in scope
    assert '}), 409' in scope
