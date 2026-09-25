from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')


def _block(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_app_parses():
    ast.parse(APP)


def test_telegram_uses_existing_12_4_representative_selector():
    cycle = _block(
        APP,
        'def _analyze_futures_all_parallel',
        'def _futures_combo_due_for_closed_candle',
    )
    gate = cycle.index('_futures_frontend_representative_ids(partial_data)')
    send = cycle.index("_send_confirmed_signal_telegram(\n                        'futures'", gate)
    assert gate < send
    assert "telegram_signal_id in telegram_representative_ids" in cycle


def test_12_4_public_selector_itself_was_not_rewritten():
    helper = _block(
        APP,
        'def _futures_frontend_representative_ids',
        'def _expire_saved_futures_waiting_on_replacement',
    )
    assert "key = (symbol, timeframe)" in helper
    assert 'class_priority = 2 if official else 1' in helper
    assert 'manual_risk_class' in helper


def test_trading_geometry_not_changed_by_minimal_gate():
    cycle = _block(
        APP,
        'def _analyze_futures_all_parallel',
        'def _futures_combo_due_for_closed_candle',
    )
    gate = cycle[cycle.index('# Commit 12.4.1 FINAL'):cycle.index('print(\n                f"✅ [FUT', cycle.index('# Commit 12.4.1 FINAL'))]
    for forbidden in (
        '_calculate_futures_entry',
        '_calculate_futures_stop',
        '_calculate_futures_take_profit',
        'minimum_execution_safety =',
        'minimum_publication_execution_safety =',
    ):
        assert forbidden not in gate
