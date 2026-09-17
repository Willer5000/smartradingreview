from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent


def test_public_reason_drops_internal_contingency_codes():
    from reason_presenter import public_reason, contingency_public_reason
    assert public_reason('ACTION_CELL_NOT_YET_VALIDATED') == ''
    assert public_reason('STRUCTURE_RETEST') == ''
    assert public_reason('RC8.2 contingencia: ACTION_CELL_NOT_YET_VALIDATED · STRUCTURE_RETEST') == ''
    assert contingency_public_reason('ACTION_CELL_NOT_YET_VALIDATED', 'STRUCTURE_RETEST') == ''
    natural = 'ADX en 31.2 confirma una tendencia bajista con presión vendedora.'
    assert public_reason(natural) == natural


def test_contingency_codes_do_not_enter_public_consensus():
    text = (ROOT / 'app.py').read_text(encoding='utf-8')
    block = text[text.index('# RC8.2 — CONTINGENCY PLAYBOOK'):text.index('# Q7 — ADAPTIVE INTRADAY STRATEGY LAB')]
    assert 'estrategias_consenso.append(strategy_name)' not in block
    assert 'contingency_public_reason(' not in block
    assert "contingency_playbook.get('downgrade_reason')" in block


def test_reviewtrader_futures_obeys_active_cell_contract():
    text = (ROOT / 'review_trader.py').read_text(encoding='utf-8')
    start = text.index('def _is_signal_eligible_for_profit_stats')
    block = text[start:start+1800]
    assert 'futures_cell_active' in block


def test_learning_pdf_fetches_executable_futures_separately_from_shadow():
    text = (ROOT / 'pdf_learning_report.py').read_text(encoding='utf-8')
    start = text.index('def _fetch_all_signals_with_indicators')
    block = text[start:text.index('def _calc_stats_general', start)]
    assert "('context->learning->>evaluation_role', 'EXECUTABLE_SIGNAL')" in block
    assert "('context->learning->>statistically_eligible', 'true')" in block
    assert "('context->learning->>evaluation_role', 'SHADOW_ANALYSIS')" in block
    assert 'REPORT_SHADOW_SAMPLE_MAX_ROWS' in block
    assert "'shadow_sample_complete'" in block


def test_analytics_contract_exposes_all_action_types_and_92_cells():
    html = (ROOT / 'templates' / 'analytics.html').read_text(encoding='utf-8')
    js = (ROOT / 'static' / 'analytics.js').read_text(encoding='utf-8')
    assert 'COMPRA_SPOT' in html and 'VENTA_SPOT' in html
    assert '92 celdas objetivo' in html
    assert ' investigadas · ' not in js
    assert ' con Champion · ' in js


def test_changed_python_files_parse():
    for name in ('app.py','contingency_strategy_engine.py','reason_presenter.py','review_trader.py','supabase_client.py','pdf_learning_report.py'):
        ast.parse((ROOT/name).read_text(encoding='utf-8'), filename=name)
