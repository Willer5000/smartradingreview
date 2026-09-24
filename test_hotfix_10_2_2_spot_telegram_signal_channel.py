from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')


def block(start, end):
    return APP[APP.index(start):APP.index(end)]


def test_spot_confirmed_signals_ignore_guardian_preferences():
    b = block('def _confirmed_signal_preferences_allow', 'def _send_confirmed_signal_telegram')
    assert "if market == 'spot':" in b
    assert "return timeframe in ('4h', '12h', '1D', '1W')" in b
    assert '_get_spot_telegram_preferences' not in b
    assert 'spot_telegram_timeframes' in b  # documentation explicitly separates it


def test_guardian_still_uses_personal_spot_preferences():
    a = APP.index('def send_tgp_telegram_alert')
    z = APP.index('# ============================================================================\n# INICIALIZACIÓN', a)
    b = APP[a:z]
    assert '_get_spot_telegram_preferences' in b
    assert "preferences.get(\n            'spot_telegram_enabled'" in b
    assert "'spot_telegram_timeframes'" in b


def test_confirmed_signal_is_sent_immediately_per_cell():
    b = block('def _compute_previous_signals', 'def _run_previous_signals_background')
    create_pos = b.index("resultados[clave] = {")
    send_pos = b.index("_send_confirmed_signal_telegram(\n                        'spot',\n                        resultados[clave],")
    cache_pos = b.index("# ============ GUARDAR EN CACHÉ ============")
    assert create_pos < send_pos < cache_pos
    assert '_send_spot_confirmed_timeframe_alerts(resultados)' not in b


def test_spot_confirmed_all_four_production_timeframes_are_scanned():
    b = block('def _compute_previous_signals', 'def _run_previous_signals_background')
    assert "temporalidades = ['4h', '12h', '1D', '1W']" in b


def test_dedup_is_per_symbol_timeframe_action_close():
    b = block('def _confirmed_signal_event_key', 'def _confirmed_signal_recent_enough')
    assert 'spot|{symbol}|{timeframe}|{action}|{close_key}' in b


def test_delayed_worker_grace_and_deep_link_are_preserved():
    recent = block('def _confirmed_signal_recent_enough', 'def _confirmed_signal_rr')
    assert "'1D': 6 * 60 * 60" in recent
    assert "'1W': 12 * 60 * 60" in recent
    assert 'def _telegram_signal_deep_link' in APP
    assert "'signal_id': (\n                        analisis.get('signal_id')\n                        or levels.get('signal_id')" in APP


def test_learning_core_and_learning_pdf_untouched():
    assert "@app.route('/api/review/learning_pdf')" in APP
    assert 'def _run_ai_learning_daily' in APP
    assert 'def _evaluate_36s_spot_tgp_shadow' in APP
