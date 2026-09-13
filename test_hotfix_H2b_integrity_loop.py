from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SCRIPT = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
PDF = (ROOT / 'pdf_learning_report.py').read_text(encoding='utf-8')


def test_spot_current_recommendation_syncs_active_panel_without_extra_market_analysis():
    assert 'def _sync_spot_active_signal_from_result' in APP
    assert APP.count('_sync_spot_active_signal_from_result(result)') >= 2
    assert "snapshot_origin': 'INTERACTIVE_CURRENT_ANALYSIS'" in APP
    assert "cache.pop(key, None)" in APP
    assert 'setTimeout(() => window.updateActiveSignals(), 50)' in SCRIPT


def test_learning_pdf_reads_scoped_statistical_cohorts_not_all_19k_rows():
    assert "'result_mode': 'SCOPED_STATISTICAL_COHORT_H2'" in PDF
    assert "'spot_verified'" in PDF
    assert "'futures_clean'" in PDF
    assert "('context->learning->>statistically_eligible', 'true')" in PDF
    assert "('context->learning->>cohort', FUTURES_REAL_COHORT)" in PDF
    assert "'inventory_expected_rows'" in PDF
    assert 'Cobertura cohorte estadística relevante' in PDF
    assert 'PAGINACIÓN SCOPED (Spot Q6 + Futures real)' in PDF


def test_learning_scientist_has_independent_six_hour_recovery_watchdog():
    assert "AI_LEARNING_SLOT_HOURS', '6'" in APP
    assert "'AI_LEARNING_V2'" in APP
    assert "event_type='RESEARCH_CYCLE_6H'" in APP
    assert 'def ai_learning_scientist_watchdog_loop' in APP
    assert "name='ai-learning-scientist'" in APP
    assert '_AI_LEARNING_WATCHDOG_SECONDS' in APP


def test_bank_justifications_do_not_claim_zero_squeeze_or_value_area_confirmation():
    assert 'máxima contracción (squeeze) de {squeeze_length} velas con ruptura alcista' not in APP
    assert 'Precio fuera de Value Area ({price_position}) con volumen creciente, confirmando dirección.' not in APP
    assert 'La ubicación por sí sola no confirma dirección' in APP
    assert 'Si existe squeeze real, su duración es {squeeze_length} velas' in APP


def test_cache_bust_for_updated_h2_bundle():
    assert '20260913-H3-NO-INFINITE-LOADING' in INDEX
