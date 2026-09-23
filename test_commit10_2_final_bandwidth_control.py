from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return (ROOT / name).read_text(encoding='utf-8')


def function_block(text, start, next_start):
    a = text.index(start)
    b = text.index(next_start, a + len(start))
    return text[a:b]


def test_analysis_pdf_and_telegram_media_are_retired_but_learning_pdf_remains():
    app = read('app.py')
    assert "@app.route('/api/generate_report')" not in app
    assert 'sendPhoto' not in app
    assert 'sendDocument' not in app
    assert 'from pdf_report' not in app
    assert "@app.route('/api/review/learning_pdf')" in app
    assert 'pdf_learning_report' in app
    assert 'generate_learning_pdf' in app


def test_telegram_transport_is_text_only_and_direct_signal_links_exist():
    app = read('app.py')
    block = function_block(app, '    def send_telegram_alert(', '    def should_send_telegram_alert(')
    assert 'sendMessage' in block
    assert 'sendPhoto' not in block
    assert 'sendDocument' not in block
    assert "@app.route('/signal/<signal_id>')" in app
    assert 'def _telegram_signal_deep_link' in app
    assert 'Abrir esta señal' in app
    assert "return _telegram_signal_deep_link('futures', result)" in app


def test_frontend_has_no_operational_analysis_pdf_control_and_supports_deep_links():
    script = read('static/script.js')
    futures = read('static/futures.js')
    assert 'removeAnalysisPdfControls' in script
    assert '[onclick*="downloadAnalysisReport"]' in script
    assert 'applySignalDeepLink' in script
    assert 'data-signal-id' in script
    assert 'applyFuturesSignalDeepLink' in futures
    assert 'data-signal-id' in futures


def test_supabase_dedupe_is_only_for_derived_material():
    db = read('supabase_client.py')
    assert 'def _derived_write_changed' in db
    assert 'def _mark_derived_write_persisted' in db
    assert 'def _meter_outbound_payload' in db
    assert 'def outbound_payload_status' in db

    insert_signal = function_block(db, '    def insert_signal(', '    def _insert_signal_indicators(')
    update_result = function_block(db, '    def update_signal_result(', '    def insert_missed_opportunity(')
    recommendations = function_block(db, '    def upsert_recommendation(', '    def upsert_strategy_stats(')
    stats = function_block(db, '    def upsert_strategy_stats(', '    def get_signals_for_stats(')

    assert '_derived_write_changed' not in insert_signal
    assert '_derived_write_changed' not in update_result
    assert '_derived_write_changed' in recommendations
    assert '_mark_derived_write_persisted' in recommendations
    assert '_derived_write_changed' in stats
    assert '_mark_derived_write_persisted' in stats


def test_approved_ai_bandwidth_contract_is_preserved():
    ai = read('ai_advisor.py')
    ui = read('static/ai_assistant.js')
    assert 'AI_MANUAL_MIN_INTERVAL_MINUTES' in ai
    assert '"20"' in ai
    assert 'manual_futures_cooldown' in ai
    assert '1 pregunta cada 20 min' in ui
    assert '30 min' in ui
