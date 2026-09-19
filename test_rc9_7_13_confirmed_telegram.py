from pathlib import Path

ROOT = Path(__file__).resolve().parent
app = (ROOT / 'app.py').read_text(encoding='utf-8')


def test_confirmed_telegram_has_durable_dedup_and_boot_restore():
    assert "'confirmed_signal_alerts_dedup'" in app
    assert 'def _load_confirmed_signal_alerts_from_disk()' in app
    assert "('telegram-confirmed-dedup', _load_confirmed_signal_alerts_from_disk)" in app


def test_confirmed_telegram_is_anti_backfill_after_deploy():
    assert '_CONFIRMED_SIGNAL_PROCESS_STARTED_AT = time.time()' in app
    assert 'def _confirmed_signal_recent_enough(signal, timeframe):' in app
    assert '_CONFIRMED_SIGNAL_PROCESS_STARTED_AT - 120.0' in app


def test_futures_closed_candle_path_emits_confirmed_event():
    start = app.index('def _analyze_futures_all_parallel')
    end = app.index('def _next_futures_incremental_combo', start)
    scope = app[start:end]
    assert "_send_confirmed_signal_telegram(\n                    'futures',\n                    r," in scope
    assert 'closed_candle_only=True' in scope


def test_futures_confirmed_only_allows_executable_long_short():
    start = app.index('def _send_confirmed_signal_telegram')
    end = app.index('# Deduplicación ENTRY', start)
    scope = app[start:end]
    assert "if action not in ('LONG', 'SHORT'):" in scope
    assert "if publication_status != 'EXECUTABLE_SIGNAL':" in scope


def test_spot_closed_confirmation_emits_confirmed_event():
    start = app.index('def _compute_previous_signals')
    end = app.index('def _run_previous_signals_background', start)
    scope = app[start:end]
    assert "'ui_context': 'CONFIRMED'" in scope
    assert "_send_confirmed_signal_telegram(\n                        'spot',\n                        resultados[clave]," in scope


def test_intrabar_paths_do_not_emit_confirmed_telegram():
    fut_start = app.index('def _start_futures_ui_analysis_async')
    fut_end = app.index('def _serialize_futures_cache', fut_start)
    assert '_send_confirmed_signal_telegram' not in app[fut_start:fut_end]

    spot_start = app.index('def _run_spot_intrabar_preview')
    spot_end = app.index('def _start_spot_intrabar_refresh_async', spot_start)
    assert '_send_confirmed_signal_telegram' not in app[spot_start:spot_end]


def test_confirmed_message_separates_confirmation_from_entry_event():
    start = app.index('def _build_confirmed_signal_telegram_message')
    end = app.index('def _confirmed_signal_preferences_allow', start)
    scope = app[start:end]
    assert 'NUEVA SEÑAL CONFIRMADA' in scope
    assert 'La alerta de Entry se enviará aparte' in scope
    assert 'Apalancamiento' in scope
    assert 'R/R' in scope


def test_spot_confirmation_respects_spot_telegram_timeframe_preferences():
    start = app.index('def _confirmed_signal_preferences_allow')
    end = app.index('def _send_confirmed_signal_telegram', start)
    scope = app[start:end]
    assert '_get_spot_telegram_preferences(user)' in scope
    assert "prefs.get('spot_telegram_enabled', True)" in scope
    assert "prefs.get('spot_telegram_timeframes')" in scope
