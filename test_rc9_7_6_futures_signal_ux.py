from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES_JS = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def test_futures_ui_has_no_separate_market_status_card():
    assert 'futures-market-status-card' not in INDEX
    assert '>Estado del mercado<' not in INDEX


def test_signal_lists_only_surface_directional_medium_high_diagnostics():
    assert "risk_class not in ('MEDIUM', 'HIGH')" in APP
    assert "classification != 'ANALYSIS_ONLY'" in APP
    assert "action not in ('LONG', 'SHORT')" in APP
    assert "'other_directional_signals':" in APP
    assert 'No hubo otras hipótesis LONG/SHORT de riesgo medio o alto' in FUTURES_JS


def test_previous_manual_save_stays_previous_only():
    assert "'PREVIOUS_ANALYSIS_ONLY'" in APP
    assert "'CURRENT_ANALYSIS_ONLY'" in APP
    assert "context === 'previous'" in FUTURES_JS
    assert "source_context: 'PREVIOUS_ANALYSIS_ONLY'" in FUTURES_JS


def test_hidden_directional_section_is_embedded_in_both_signal_lists():
    assert FUTURES_JS.count('signalsList.innerHTML = html + diagnosticsHtml;') >= 2
    assert FUTURES_JS.count('${diagnosticsHtml}') >= 2
    assert 'Por qué no aparecen otras señales' in FUTURES_JS


def test_cache_buster_updated():
    assert '20260918-RC9-7-6-FUTURES-SIGNALS' in INDEX
