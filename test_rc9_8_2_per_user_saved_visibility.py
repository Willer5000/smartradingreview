from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')


def test_personal_saved_reference_index_exists():
    assert 'window._userSavedSignalRefs' in JS
    assert "fetch('/api/saved_signals?limit=500'" in JS
    assert "credentials: 'same-origin'" in JS
    assert 'row?.source_signal_id' in JS
    assert '_savedSignalFingerprint' in JS


def test_cache_is_scoped_to_current_authenticated_user():
    assert 'userKey: null' in JS
    assert '_currentSavedSignalUserKey' in JS
    assert 'if (state.userKey !== currentUserKey)' in JS
    assert 'state.sourceIds = new Set();' in JS
    assert 'state.fingerprints = new Set();' in JS


def test_confirmed_and_vigent_lanes_hide_only_personally_saved_rows():
    assert JS.count('allSignals.filter(sig => !_isSignalSavedByCurrentUser(sig))') >= 2
    assert 'candidates = candidates.filter(candidate => !_isSignalSavedByCurrentUser(candidate));' in JS
    assert "'/api/futures/signals/active?min_confidence=55" in JS
    assert "'/api/futures/signals/previous?min_confidence=55" in JS


def test_save_moves_visual_card_to_saved_without_touching_global_signal():
    start = JS.index('window.confirmSaveSignal = async function()')
    end = JS.index('// ============================================================================\n// FASE 7G.1', start)
    block = JS[start:end]
    assert "fetch('/api/saved_signals'" in block
    assert 'await window.updateSavedSignalsList();' in block
    assert 'await window.refreshSignalLanesAfterSavedChange();' in block


def test_delete_restores_card_when_global_signal_is_still_alive():
    start = JS.index('window.deleteSavedSignal = async function()')
    end = JS.index('// ============ Auto-refresh', start)
    block = JS[start:end]
    assert "method: 'DELETE'" in block
    assert 'await window.updateSavedSignalsList();' in block
    assert 'await window.refreshSignalLanesAfterSavedChange();' in block


def test_visual_layer_does_not_mutate_global_lifecycle():
    start = JS.index('// RC9.8.2 — VISIBILIDAD PERSONAL DE SEÑALES GUARDADAS')
    end = JS.index('function futPublicAnalysisRole', start)
    block = JS[start:end]
    for forbidden in (
        '/api/futures/signals/active',
        '/api/futures/signals/previous',
        'valid_until =',
        'source_valid_until =',
        'lifecycle_status =',
    ):
        assert forbidden not in block
