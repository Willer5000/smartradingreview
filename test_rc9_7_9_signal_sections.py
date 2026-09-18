from pathlib import Path
ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
fut=(ROOT/'static'/'futures.js').read_text(encoding='utf-8')
html=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
saved=(ROOT/'saved_signals.py').read_text(encoding='utf-8')

def test_three_signal_lanes_and_order():
    a=html.index('Señales activas')
    c=html.index('Señales confirmadas')
    v=html.index('Señales vigentes')
    s=html.index('Señales Guardadas')
    assert a < c < v < s

def test_active_lane_navigation_only():
    assert 'current-active-signals-list' in html
    assert 'current-active-signals-count' in html
    assert "window.changeToSignal" in fut
    assert '/api/futures/opportunities?limit=63' in fut
    assert 'Esta lista es de navegación y no guarda operaciones.' in html

def test_colors_explicit():
    assert 'bg-success bg-opacity-25' in html
    assert 'bg-danger bg-opacity-25' in html

def test_confirmed_and_vigent_guardable():
    assert 'openSaveSignalFromCard' in fut
    assert 'openSaveActiveSignalFromCard' in fut
    assert "source_context: 'ACTIVE_CONFIRMED'" in fut

def test_original_validity_and_guardian_contract_preserved():
    assert "data['source_valid_until']" in app
    assert 'source_valid_until' in saved
    assert 'expired_source_validity_no_entry' in saved

def test_current_diagnostics_not_mixed_into_vigentes():
    assert "document.getElementById('current-active-diagnostics')" in fut
    assert 'signalsList.innerHTML = html;' in fut

def test_live_visuals_still_included():
    assert 'live-indicators-visual-note' in html
    assert 'RC9-7-9-THREE-SIGNAL-LANES' in html
