from pathlib import Path

ROOT = Path(__file__).resolve().parent
app = (ROOT / 'app.py').read_text(encoding='utf-8')


def test_spot_entry_monitor_reads_confirmed_and_vigent_caches():
    start = app.index('def _get_signals_for_entry_monitor')
    end = app.index('def _spot_live_market_price', start)
    scope = app[start:end]
    assert "('CONFIRMED', getattr(expert_system, 'prev_signals_cache'" in scope
    assert "('VIGENT', getattr(expert_system, 'spot_vigent_signals_cache'" in scope
    assert "'ui_context': ui_context" in scope


def test_spot_entry_uses_live_price_and_same_telegram_preferences():
    assert 'def _spot_live_market_price(symbol):' in app
    assert "https://api.kucoin.com/api/v1/market/orderbook/level1" in app
    assert "_confirmed_signal_preferences_allow('spot', timeframe)" in app
    start = app.index('def monitor_entries_loop')
    end = app.index('# ============================================================================\n# COMMIT 36N', start)
    scope = app[start:end]
    assert '_spot_live_market_price(symbol)' in scope
    assert '_spot_entry_alert_allowed(tf)' in scope
    assert '_price_touches_entry(current, entry' in scope


def test_spot_old_intermediate_setup_telegram_is_removed():
    assert 'def _spot_preentry_key' not in app
    assert 'SPOT · SEÑAL VIGENTE (VELA CERRADA)' not in app
    assert 'SETUP Spot vela cerrada enviado' not in app


def test_futures_entry_monitor_reads_official_lifecycle_not_only_latest_analysis():
    start = app.index('def futures_standard_alert_loop():')
    end = app.index('# ============================================================================\n# LEGACY 36K', start)
    scope = app[start:end]
    assert "lifecycle = dict(raw.get('lifecycle') or {})" in scope
    assert 'for signal_id, record in lifecycle.items():' in scope
    assert "status not in ('waiting_entry', 'entry_touched')" in scope
    assert "publication != 'EXECUTABLE_SIGNAL'" in scope
    assert "record.get('system_executable') is False" in scope


def test_futures_entry_alert_survives_move_from_confirmed_to_vigent():
    start = app.index('def futures_standard_alert_loop():')
    end = app.index('# ============================================================================\n# LEGACY 36K', start)
    scope = app[start:end]
    assert "if status == 'entry_touched':" in scope
    assert "else '📌 Origen: <b>VIGENTE</b>'" in scope
    assert '_futures_official_entry_already_sent(user, record)' in scope
    assert '_mark_futures_official_entry_sent(user, record)' in scope


def test_futures_official_entry_dedup_is_durable():
    start = app.index('def _futures_official_entry_event_key')
    end = app.index('def futures_standard_alert_loop():', start)
    scope = app[start:end]
    assert '_entry_alerts_sent' in scope
    assert '_save_entry_alerts_to_disk()' in scope
    assert "FUTURES_ENTRY|" in scope


def test_saved_futures_does_not_duplicate_official_entry_event():
    start = app.index('def _send_saved_futures_lifecycle_notifications')
    end = app.index('def saved_futures_lifecycle_loop', start)
    scope = app[start:end]
    assert "source_signal_id = str(sig.get('source_signal_id')" in scope
    assert '_futures_official_entry_already_sent(' in scope
    assert 'Saved Futures ENTRY deduplicado contra señal oficial' in scope
