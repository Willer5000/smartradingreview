from pathlib import Path
ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
fut=(ROOT/'static'/'futures.js').read_text(encoding='utf-8')
html=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
saved=(ROOT/'saved_signals.py').read_text(encoding='utf-8')

def test_context_allowed():
    assert "'ACTIVE_CONFIRMED'" in app
    assert "source_context: 'ACTIVE_CONFIRMED'" in fut

def test_active_guardable():
    assert 'openSaveActiveSignalFromCard' in fut
    assert 'Guardar en operación' in fut

def test_original_validity_preserved():
    assert "data['source_valid_until']" in app
    assert "expired_source_validity_no_entry" in saved
    assert "source_valid_until" in saved

def test_ui_order():
    assert html.index('Nuevas señales confirmadas') < html.index('Señales vigentes') < html.index('Señales Guardadas')

def test_live_visuals_included():
    assert 'live-indicators-visual-note' in html
    assert 'RC9-7-8-LIVE-ACTIVE-SAVE' in html
