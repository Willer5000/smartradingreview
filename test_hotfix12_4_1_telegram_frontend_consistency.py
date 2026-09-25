from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SAVED_PATH = ROOT / 'saved_signals.py'


def _block(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_confirmed_telegram_is_subset_of_public_frontend_projection():
    cycle = _block(
        APP,
        'def _analyze_futures_all_parallel',
        'def _futures_combo_due_for_closed_candle',
    )
    gate = cycle.index('_futures_confirmed_visible_in_frontend(')
    send = cycle.index("_send_confirmed_signal_telegram(\n                        'futures'", gate)
    assert gate < send
    assert 'no es el representante oficial visible' in cycle


def test_telegram_visibility_gate_reuses_exact_public_representative():
    helper = _block(
        APP,
        'def _futures_confirmed_visible_in_frontend',
        'def _expire_saved_futures_waiting_on_replacement',
    )
    assert 'signal_id in _futures_frontend_representative_ids(cache)' in helper
    assert "publication != 'EXECUTABLE_SIGNAL'" in helper
    assert "action not in ('LONG', 'SHORT')" in helper
    assert "'waiting_entry'" in helper and "'entry_touched'" in helper
    assert '_leverage_in_valid_range' in helper
    assert 'entry <= 0 or stop_loss <= 0 or take_profit <= 0' in helper


def test_confirmadas_and_vigentes_share_same_official_cell_arbiter():
    active = _block(
        APP,
        'def api_futures_signals_active',
        "@app.route('/api/futures/debug')",
    )
    previous = _block(
        APP,
        'def api_futures_signals_previous',
        "@app.route('/api/futures/correlation')",
    )
    assert '_futures_frontend_representative_ids(cache)' in active
    assert '_futures_frontend_representative_ids(cache)' in previous
    assert 'str(signal_id) not in representative_ids' in active
    assert 'signal_id not in representative_ids' in previous


def test_different_timeframes_are_different_public_cells():
    helper = _block(
        APP,
        'def _futures_frontend_representative_ids',
        'def _futures_saved_replacement_representative_ids',
    )
    assert "key = (symbol, timeframe)" in helper
    # The key must not be symbol-only, so DOT 30m cannot hide DOT 1h.
    assert 'key = symbol' not in helper


def test_saved_list_is_not_collapsed_by_symbol_timeframe():
    if not SAVED_PATH.exists():
        return
    saved = SAVED_PATH.read_text(encoding='utf-8')
    block = _block(saved, 'def list_saved_signals', 'def get_saved_signal')
    assert "order('created_at', desc=True)" in block
    assert '_dedupe_representative_signals' not in block
    assert 'group_by' not in block
    assert 'distinct(' not in block


def test_hotfix_does_not_touch_trading_geometry_or_safety_contract():
    helper = _block(
        APP,
        'def _futures_confirmed_visible_in_frontend',
        'def _expire_saved_futures_waiting_on_replacement',
    )
    # It validates existing levels; it never recalculates them.
    forbidden = [
        '_calculate_futures_entry',
        '_calculate_futures_stop',
        '_calculate_futures_take_profit',
        'minimum_execution_safety =',
        'minimum_publication_execution_safety =',
    ]
    for token in forbidden:
        assert token not in helper
