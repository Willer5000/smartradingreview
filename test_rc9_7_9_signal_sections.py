from pathlib import Path

ROOT = Path(__file__).resolve().parent
app = (ROOT / 'app.py').read_text(encoding='utf-8')
fut = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
saved = (ROOT / 'saved_signals.py').read_text(encoding='utf-8')


def test_three_signal_lanes_and_order():
    a = html.index('Señales activas')
    c = html.index('Señales confirmadas')
    v = html.index('Señales vigentes')
    s = html.index('Señales Guardadas')
    assert a < c < v < s


def test_active_lane_navigation_only():
    assert 'current-active-signals-list' in html
    assert 'current-active-signals-count' in html
    assert 'window.changeToSignal' in fut
    assert '/api/futures/opportunities?limit=63' in fut
    assert 'Esta lista es de navegación y no guarda operaciones.' in html


def test_colors_explicit():
    assert 'bg-success bg-opacity-25' in html
    assert 'bg-danger bg-opacity-25' in html


def test_confirmed_and_vigent_official_guardable():
    assert 'openSaveSignalFromCard' in fut
    assert 'openSaveActiveSignalFromCard' in fut
    assert "source_context: 'ACTIVE_CONFIRMED'" in fut


def test_vigent_medium_high_have_own_diagnostics_lane():
    assert 'vigent-signals-diagnostics' in html
    assert 'vigent_other_directional_signals' in app
    assert "futRenderAnalysisDiagnostics(\n                json,\n                'vigent'" in fut
    assert "'ACTIVE_ANALYSIS_ONLY'" in app
    assert "'ACTIVE_ANALYSIS_ONLY'" in fut


def test_manual_medium_high_are_persisted_in_canonical_lifecycle():
    assert 'manual_candidate = (' in app
    assert "manual_profile = _futures_manual_risk_profile(result)" in app
    assert "'manual_save_allowed': bool(manual_candidate)" in app
    assert "'manual_risk_class': (" in app
    assert "publication_status != 'EXECUTABLE_SIGNAL'" in app


def test_vigent_manual_save_keeps_original_validity_and_can_arm_guardian():
    assert "source_context == 'ACTIVE_ANALYSIS_ONLY'" in app
    assert "data['source_valid_until'] = source_valid_until" in app
    assert "if lifecycle_status == 'entry_touched':" in app
    assert "data['already_in_position'] = True" in app
    assert 'source_valid_until' in saved
    assert 'expired_source_validity_no_entry' in saved


def test_vigent_hidden_list_excludes_noise_and_expired():
    assert 'def _futures_vigent_manual_candidates' in app
    assert "risk_class not in ('MEDIUM', 'HIGH')" in app
    assert "lifecycle_status not in ('waiting_entry', 'entry_touched')" in app
    assert 'if remaining_seconds <= 0:' in app


def test_official_vigent_list_does_not_mix_analysis_only_cards():
    assert "record_publication != 'EXECUTABLE_SIGNAL'" in app
    assert "record.get('system_executable') is False" in app


def test_original_validity_and_guardian_contract_preserved():
    assert "data['source_valid_until']" in app
    assert 'source_valid_until' in saved
    assert 'expired_source_validity_no_entry' in saved


def test_current_diagnostics_remain_attached_to_active_lane():
    assert "document.getElementById('current-active-diagnostics')" in fut
    assert "context !== 'vigent'" in fut


def test_live_visuals_still_included():
    assert 'live-indicators-visual-note' in html
    assert 'RC9-7-10-FINALIZATION' in html
