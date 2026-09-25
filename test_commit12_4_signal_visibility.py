from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES_JS_PATH = ROOT / 'static' / 'futures.js'
FUTURES_JS = FUTURES_JS_PATH.read_text(encoding='utf-8') if FUTURES_JS_PATH.exists() else ''


def _block(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_app_parses_after_12_4_1_scope_fix():
    ast.parse(APP)


def test_one_public_official_representative_per_symbol_timeframe():
    block = _block(
        APP,
        'def _futures_frontend_representative_ids',
        'def _futures_saved_replacement_representative_ids',
    )
    assert "key = (symbol, timeframe)" in block
    assert "publication == 'EXECUTABLE_SIGNAL'" in block
    assert "row.get('system_executable') is not False" in block
    assert '_representative_signal_score(row)' in block
    assert '_signal_source_epoch(row)' in block
    # Hotfix 12.4.1: diagnostics are not part of the public main-lane arbiter.
    assert 'manual_risk_class' not in block
    assert 'manual_save_allowed' not in block


def test_public_representative_rule_is_only_confirmed_plus_vigent():
    block = _block(
        APP,
        'def _futures_frontend_representative_ids',
        'def _futures_saved_replacement_representative_ids',
    )
    assert 'Confirmadas + Vigentes' in block
    assert 'Saved signals are personal records' in block
    assert 'ANALYSIS_ONLY hypotheses' in block


def test_saved_replacement_expiry_keeps_commit_12_4_semantics_separate():
    block = _block(
        APP,
        'def _futures_saved_replacement_representative_ids',
        'def _futures_confirmed_visible_in_frontend',
    )
    assert 'manual_save_allowed' in block
    assert 'manual_risk_class' in block
    assert 'class_priority = 2 if official else 1' in block
    assert 'NOT a UI dedupe rule' in block


def test_diagnostics_are_not_filtered_by_public_representative_ids():
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
    assert 'representative_ids' not in hidden
    assert 'representative_ids' not in vigent
    assert '_dedupe_representative_signals(visible)' not in vigent


def test_frontend_does_not_revive_explicitly_empty_server_diagnostics():
    if not FUTURES_JS:
        return
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


def test_replacement_expiry_is_event_only_and_keeps_separate_saved_arbiter():
    cycle = _block(
        APP,
        'def _analyze_futures_all_parallel',
        'def _futures_combo_due_for_closed_candle',
    )
    assert 'replacement_is_new_lifecycle = bool(' in cycle
    assert 'replacement_signal_id not in lifecycle' in cycle
    assert "not r.get('_reused_closed_candle')" in cycle
    assert '_confirmed_signal_recent_enough(r, timeframe)' in cycle
    assert '_futures_saved_replacement_representative_ids(' in cycle
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
    if not FUTURES_JS:
        return
    assert FUTURES_JS.count('_isSignalSavedByCurrentUser') >= 3
    assert 'refreshUserSavedSignalRefs' in FUTURES_JS
