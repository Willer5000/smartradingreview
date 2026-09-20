from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
REVIEW = (ROOT / 'review_trader.py').read_text(encoding='utf-8')
SAVED = (ROOT / 'saved_signals.py').read_text(encoding='utf-8')
SUPA = (ROOT / 'supabase_client.py').read_text(encoding='utf-8')
FUT = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
RENDER = (ROOT / 'render.yaml').read_text(encoding='utf-8')
FUTSYS = (ROOT / 'futures_system.py').read_text(encoding='utf-8')

spec = importlib.util.spec_from_file_location('uel', ROOT / 'user_execution_learning.py')
uel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uel)


def row(sid, status='sl_hit', rr=2.0, mfe=0.1, cmae=1, symbol='BNB-USDT', tf='1h', action='LONG'):
    return {
        'source_signal_id': sid,
        'symbol': symbol,
        'timeframe': tf,
        'action': action,
        'status': status,
        'entry_touched': True,
        'entry': 100.0,
        'stop_loss': 98.0,
        'take_profit': 104.0,
        'original_entry': 100.0,
        'original_stop_loss': 98.0,
        'original_take_profit': 104.0,
        'original_risk_reward': rr,
        'execution_origin': 'SYSTEM_EXECUTABLE',
        'system_executable': True,
        'mfe_r': mfe,
        'mae_r': 1.0 if status == 'sl_hit' else 0.2,
        'candles_to_mae': cmae,
    }


def test_one_loss_is_learned_but_has_zero_authority():
    p = uel._profile([row('one')], 'BNB-USDT', '1h', 'LONG')
    assert p['sample_size'] == 1
    assert p['authority'] == 'OBSERVE_ONLY'
    assert p['score_adjustment'] == 0.0


def test_duplicate_users_do_not_multiply_one_system_signal():
    rows = [row('same'), row('same'), row('other', status='tp_hit', mfe=1.5)]
    deduped = uel._dedupe_canonical(rows)
    assert len(deduped) == 2


def test_manual_modified_geometry_has_no_review_authority():
    r = row('manual')
    r['entry'] = 101.0
    assert uel._canonical_system_execution(r) is False


def test_repeated_bad_execution_can_apply_only_bounded_penalty():
    rows = [row(f'sl{i}') for i in range(10)]
    p = uel._profile(rows, 'BNB-USDT', '1h', 'LONG')
    assert p['authority'] == 'BOUNDED_CONTINUITY'
    assert -8.0 <= p['score_adjustment'] < 0.0


def test_post_trade_forensics_flags_bad_entry_and_rr_without_claiming_causality():
    r = row('loss', rr=0.84, mfe=0.05, cmae=1)
    f = uel.get_saved_trade_forensics(r)
    assert 'WEAK_RR_GEOMETRY' in f['diagnostic_tags']
    assert 'ENTRY_TIMING_SUSPECTED' in f['diagnostic_tags']
    assert f['single_trade_changes_policy'] is False


def test_reviewtrader_observes_global_execution_without_rewriting_direction_score():
    assert 'get_global_execution_profile' in REVIEW
    assert "explicit_market == 'futures'" in REVIEW
    assert 'mínimo N=8' in REVIEW
    assert 'GLOBAL_EXECUTION_ENTRY_CAUTION_' in REVIEW
    assert 'adjust_review_score' not in REVIEW


def test_global_execution_gate_targets_entry_not_direction(monkeypatch):
    monkeypatch.setattr(uel, 'get_global_execution_profile', lambda *args, **kwargs: {
        'authority': 'BOUNDED_CONTINUITY', 'sample_size': 10, 'expectancy_r': -0.3,
        'fast_sl_rate': 0.4, 'weak_progress_sl_rate': 0.5,
    })
    review = uel.get_execution_publication_review(
        'BNB-USDT', '1h', 'LONG',
        {'entry_defensibility_score': 50, 'entry_reachability_score': 48},
    )
    assert review['block_publication'] is True
    assert review['changes_direction'] is False
    assert review['changes_levels'] is False



def test_futures_publication_consumes_entry_continuity_gate_after_standard_geometry():
    assert 'get_execution_publication_review' in FUTSYS
    assert "'GLOBAL_EXECUTION_ENTRY'" in FUTSYS
    assert "action=decision" in FUTSYS

def test_saved_detail_exposes_configuration_forensics_and_global_profile():
    assert "'signal_configuration': learning_bundle.get('configuration')" in APP
    assert "'trade_forensics': learning_bundle.get('forensics')" in APP
    assert "'global_execution_learning': learning_bundle.get('global_profile')" in APP
    assert 'Configuración original de la señal' in FUT
    assert 'ReviewTrader · revisión post-trade' in FUT
    assert 'Ejecución real agregada · todos los usuarios' in FUT


def test_all_user_learning_is_deidentified_and_deduped():
    code = (ROOT / 'user_execution_learning.py').read_text(encoding='utf-8')
    fetch_section = code[code.index('def _fetch_closed_rows'):code.index('def _dedupe_canonical')]
    assert 'user_name' not in fetch_section
    assert 'source_signal_id' in fetch_section
    assert 'deduped_by_source_signal' in code


def test_save_endpoint_is_read_only_and_never_forces_heavy_refresh():
    start = APP.index("@app.route('/api/saved_signals', methods=['POST'])")
    end = APP.index("@app.route('/api/saved_signals/<signal_id>', methods=['GET'])", start)
    block = APP[start:end]
    assert '_get_futures_analysis_snapshot_read_only()' in block
    assert '_get_or_refresh_futures_analysis()' not in block


def test_free_runtime_removes_rc13_auto_heavy_intrabar_pollers():
    assert "@app.route('/api/futures/opportunities/refresh'" not in APP
    assert "@app.route('/api/spot/signals/active/refresh'" not in APP
    assert '_futScheduleSelectedIntrabarRefresh' not in FUT
    script = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
    assert '_scheduleSpotIntrabarRefresh' not in script


def test_free_runtime_bounds_waiting_threads_and_native_math_threads():
    assert 'FREE_RUNTIME_MAX_THREADS' in APP
    assert '_FREE_RUNTIME_BACKGROUND_LOCK_WAIT_SECONDS' in APP
    assert 'threading.active_count() >= _FREE_RUNTIME_MAX_THREADS' in APP
    assert 'OMP_NUM_THREADS' in RENDER
    assert 'OPENBLAS_NUM_THREADS' in RENDER
    assert 'LOW_MEMORY_MODE' in (ROOT / 'sitecustomize.py').read_text(encoding='utf-8')


def test_low_memory_signal_indicator_persistence_does_not_spawn_thread_per_signal():
    assert "if low_memory:" in SUPA
    assert 'self._insert_signal_indicators(signal_id, strategies, snapshot)' in SUPA
