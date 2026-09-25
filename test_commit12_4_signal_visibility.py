from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES_JS = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')


def _block(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_one_cross_lane_representative_per_symbol_timeframe():
    block = _block(
        APP,
        'def _futures_frontend_representative_ids',
        'def _expire_saved_futures_waiting_on_replacement',
    )
    assert "key = (symbol, timeframe)" in block
    assert 'class_priority = 2 if official else 1' in block
    assert '_representative_signal_score(row)' in block
    assert '_signal_source_epoch(row)' in block
    assert "publication == 'EXECUTABLE_SIGNAL'" in block
    assert "manual_risk_class" in block


def test_official_lane_has_priority_over_diagnostic_lane():
    block = _block(
        APP,
        'def _futures_frontend_representative_ids',
        'def _expire_saved_futures_waiting_on_replacement',
    )
    rank = block[block.index('rank = ('):block.index(')', block.index('rank = (')) + 1]
    assert rank.index('class_priority') < rank.index('_representative_signal_score')


def test_diagnostics_and_main_lanes_share_representative_ids():
    assert APP.count('representative_ids=representative_ids') >= 3
    hidden = _block(
        APP,
        'def _futures_directional_hidden_candidates',
        'def _futures_vigent_manual_candidates',
    )
    vigent = _block(
        APP,
        'def _futures_vigent_manual_candidates',
        "@app.route('/api/futures/signals/active')",
    )
    assert 'signal_id not in representative_ids' in hidden
    assert 'signal_id not in representative_ids' in vigent


def test_frontend_does_not_revive_explicitly_empty_server_diagnostics():
    diagnostics = _block(
        FUTURES_JS,
        'function futRenderAnalysisDiagnostics',
        'window.openManualAnalysisSave',
    ) if 'window.openManualAnalysisSave' in FUTURES_JS[FUTURES_JS.index('function futRenderAnalysisDiagnostics'):] else FUTURES_JS[FUTURES_JS.index('function futRenderAnalysisDiagnostics'):]
    assert 'const hasServerCandidateList = Array.isArray' in diagnostics
    assert '&& !hasServerCandidateList' in diagnostics
    assert 'candidates.length === 0' not in diagnostics.split('// Backward compatibility only', 1)[1].split('candidates = json.analysis_candidates', 1)[0]


def test_saved_update_expiry_is_current_pending_same_cell_only():
    block = _block(
        APP,
        'def _expire_saved_futures_waiting_on_replacement',
        'def _spot_entry_touch_display_until',
    )
    assert ".eq('status', 'active')" in block
    assert ".eq('entry_touched', False)" in block
    assert ".eq('symbol', normalized_symbol)" in block
    assert ".eq('timeframe', normalized_timeframe)" in block
    assert "saved_source_id == replacement_signal_id" in block
    assert 'replacement_epoch <= saved_epoch' in block
    assert "'close_reason': 'expired_signal_update_no_entry'" in block


def test_saved_open_operation_is_never_expired_by_replacement():
    block = _block(
        APP,
        'def _expire_saved_futures_waiting_on_replacement',
        'def _spot_entry_touch_display_until',
    )
    assert "if bool(raw.get('entry_touched'))" in block
    assert ".eq('entry_touched', False)" in block


def test_replacement_expiry_is_event_only_and_not_backfill():
    cycle = _block(
        APP,
        'def _analyze_futures_all_parallel',
        'def _futures_combo_due_for_closed_candle',
    )
    assert 'replacement_is_new_lifecycle = bool(' in cycle
    assert 'replacement_signal_id not in lifecycle' in cycle
    assert "not r.get('_reused_closed_candle')" in cycle
    assert '_confirmed_signal_recent_enough(r, timeframe)' in cycle
    assert 'replacement_signal_id in representative_ids_now' in cycle


def test_expiry_notifier_keeps_hotfix_12_3_1_anti_history_scan():
    notifier = _block(
        APP,
        'def _send_saved_futures_lifecycle_notifications',
        'def saved_futures_lifecycle_loop',
    )
    assert 'expired_events=None' in notifier
    assert 'list_saved_signals' not in notifier
    assert "status_filter=['expired']" not in notifier
    assert "'expired_signal_update_no_entry'" in notifier
    assert "sig.get('user_name')" in notifier
    assert "sig.get('telegram_expired_notified_at')" in notifier


def test_saved_visibility_remains_personal_per_user():
    # Existing RC9.8.2 contract must remain in all user-facing Futures lanes.
    assert FUTURES_JS.count('_isSignalSavedByCurrentUser') >= 3
    assert 'refreshUserSavedSignalRefs' in FUTURES_JS
