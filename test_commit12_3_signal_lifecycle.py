from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES_JS = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
SCRIPT_JS = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def _block(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_confirmed_telegram_is_after_frontend_cache_publication():
    cycle = _block(APP, 'def _analyze_futures_all_parallel', 'def _futures_combo_due_for_closed_candle')
    published = cycle.index("cache['data'] = partial_data")
    visible_gate = cycle.index('_futures_confirmed_visible_in_frontend(', published)
    telegram_send = cycle.index('_send_confirmed_signal_telegram(', visible_gate)
    assert published < visible_gate < telegram_send


def test_futures_vigentes_keep_entry_touched_until_terminal_or_validity():
    active = _block(APP, 'def api_futures_signals_active', "@app.route('/api/futures/debug')")
    assert "lifecycle_status not in ('waiting_entry', 'entry_touched')" in active
    assert "tiempo_restante <= 0" in active
    assert "signal_id) not in representative_ids" in active


def test_futures_public_lifecycle_has_requested_terminal_states():
    lifecycle = _block(APP, 'def _refresh_futures_signal_lifecycle', '# ============================================================================\n# COMMIT H')
    assert "missed_target_before_entry" in lifecycle
    assert "expired_after_entry_unsaved" in lifecycle
    assert "record['lifecycle_status'] = 'tp_hit'" in lifecycle
    assert "record['lifecycle_status'] = 'sl_hit'" in lifecycle


def test_cross_lane_dedupe_is_shared_by_confirmed_and_vigent():
    assert 'def _futures_frontend_representative_ids' in APP
    active = _block(APP, 'def api_futures_signals_active', "@app.route('/api/futures/debug')")
    previous = _block(APP, 'def api_futures_signals_previous', '# ============================================================================\n# FUTURES ANALYSIS') if '# ============================================================================\n# FUTURES ANALYSIS' in APP[APP.index('def api_futures_signals_previous'):] else APP[APP.index('def api_futures_signals_previous'):]
    assert '_futures_frontend_representative_ids(cache)' in active
    assert '_futures_frontend_representative_ids(cache)' in previous
    assert 'def _spot_frontend_representative_identities' in APP


def test_saved_expiration_telegram_is_simple_and_only_for_no_entry_expiry():
    notifier = _block(APP, 'def _saved_expiry_short_message', 'def saved_futures_lifecycle_loop')
    assert 'SEÑAL EXPIRADA' in notifier
    assert "'expired_source_validity_no_entry'" in notifier
    assert "'expired_tp_before_entry_no_entry'" in notifier
    assert "if bool(sig.get('entry_touched'))" in notifier
    assert "category='SAVED_SIGNAL_EXPIRED'" in notifier


def test_saved_signals_repo_file_has_tp_before_entry_rule_when_applied():
    saved = ROOT / 'saved_signals.py'
    if not saved.exists():
        # The delivery keeps this large current file as a surgical GitHub-Web
        # edit to avoid overwriting it with a stale full copy.
        return
    text = saved.read_text(encoding='utf-8')
    assert 'expired_tp_before_entry_no_entry' in text
    assert 'target_before_entry' in text


def test_frontend_does_not_expose_resource_or_internal_architecture_copy():
    public = '\n'.join([FUTURES_JS, SCRIPT_JS, INDEX])
    forbidden = [
        'Scanner determinístico sin IA ni escrituras DB',
        'La cabecera no consulta Supabase',
        'Microestructura en modo protegido',
        'Modo protegido de recursos',
        'control interno aplicado',
        'Router de oportunidades · Multi-Activo',
    ]
    for phrase in forbidden:
        assert phrase not in public


def test_entry_touched_frontend_has_only_save_in_operation_button():
    assert "const saveButtons = sig.lifecycle_status === 'entry_touched'" in FUTURES_JS
    touched_branch = FUTURES_JS.split("const saveButtons = sig.lifecycle_status === 'entry_touched'", 1)[1].split("html +=", 1)[0]
    first_branch = touched_branch.split(': `', 1)[0]
    assert 'Guardar en operación' in first_branch
    assert '🔖 Guardar' not in first_branch
