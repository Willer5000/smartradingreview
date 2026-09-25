from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
SAVED = (ROOT / 'saved_signals.py').read_text(encoding='utf-8')


def _block(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_notifier_never_scans_expired_history():
    notifier = _block(
        APP,
        'def _send_saved_futures_lifecycle_notifications',
        'def saved_futures_lifecycle_loop',
    )
    assert "list_saved_signals" not in notifier
    assert "status_filter=['expired']" not in notifier
    assert 'expired_events=None' in notifier
    assert "sig.get('user_name')" in notifier
    assert "sig.get('telegram_expired_notified_at')" in notifier
    assert "sig.get('entry_touched')" in notifier


def test_lifecycle_sends_only_current_cycle_expired_events():
    lifecycle = _block(
        APP,
        'def saved_futures_lifecycle_loop',
        '_Q6_DAILY_LOCK',
    )
    assert "stats.get('expired_events') or []" in lifecycle
    assert '_send_saved_futures_lifecycle_notifications(' in lifecycle


def test_saved_evaluator_emits_transition_events_without_extra_history_query():
    evaluator = SAVED[SAVED.index('def evaluate_saved_signals(price_fetcher) -> Dict:'):]
    assert "'expired_events': []" in evaluator
    assert "stats['expired_events'].append(expired_event)" in evaluator
    assert "list_saved_signals(status_filter=['active', 'entry_touched']" in evaluator


def test_expiry_event_is_created_only_after_persisting_expiration():
    evaluator = SAVED[SAVED.index('def evaluate_saved_signals(price_fetcher) -> Dict:'):]
    first_reason = evaluator.index("'expired_source_validity_no_entry'")
    first_append = evaluator.index("stats['expired_events'].append(expired_event)", first_reason)
    assert first_append > first_reason

    second_reason = evaluator.index("'expired_no_entry'", first_append)
    second_append = evaluator.index("stats['expired_events'].append(expired_event)", second_reason)
    assert second_append > second_reason
