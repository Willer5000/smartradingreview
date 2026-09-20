from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTSYS = (ROOT / 'futures_system.py').read_text(encoding='utf-8')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

uel = _load('uel_v2', ROOT / 'user_execution_learning.py')
lev = _load('lev_v6', ROOT / 'leverage_policy.py')


def base_trade(**kw):
    row = {
        'id': 'saved-1',
        'source_signal_id': 'signal-1',
        'symbol': 'BNB-USDT', 'timeframe': '1h', 'action': 'LONG',
        'status': 'sl_hit', 'entry_touched': True,
        'entry': 100.0, 'stop_loss': 101.0, 'take_profit': 104.0,
        'original_entry': 100.0, 'original_stop_loss': 98.0,
        'original_take_profit': 104.0, 'original_risk_reward': 2.0,
        'execution_origin': 'SYSTEM_EXECUTABLE', 'system_executable': True,
        'closed_price': 101.0, 'mfe_r': 0.8, 'mae_r': 0.2,
        'candles_to_mae': 2,
    }
    row.update(kw)
    return row


def test_protected_stop_above_entry_is_positive_trade_even_when_status_sl_hit(monkeypatch):
    row = base_trade()
    assert uel._outcome_r(row) == 0.5
    monkeypatch.setattr(uel, 'get_guardian_trade_review', lambda _signal: {
        'learning_interpretation': 'HELPFUL', 'evaluated': 1, 'avg_delta_r': 0.3,
    })
    f = uel.get_saved_trade_forensics(row)
    assert f['economic_outcome'] == 'WIN'
    assert 'PROTECTED_STOP_WIN' in f['diagnostic_tags']
    assert 'ENTRY_TIMING_SUSPECTED' not in f['diagnostic_tags']
    assert f['one_trade_equals_one_market_sample'] is True


def test_negative_fast_stop_can_flag_entry_without_calling_direction_wrong(monkeypatch):
    row = base_trade(
        stop_loss=98.0, closed_price=98.0, mfe_r=0.05, mae_r=1.0, candles_to_mae=1
    )
    monkeypatch.setattr(uel, 'get_guardian_trade_review', lambda _signal: {
        'learning_interpretation': 'PENDING_OR_NEUTRAL', 'evaluated': 0, 'avg_delta_r': None,
    })
    f = uel.get_saved_trade_forensics(row)
    assert f['economic_outcome'] == 'LOSS'
    assert 'ENTRY_TIMING_SUSPECTED' in f['diagnostic_tags']
    assert f['component_assessment']['direction']['state'] == 'SEPARATE_FROM_ENTRY'


def test_guardian_harmful_exit_becomes_more_patient_only_after_eight(monkeypatch):
    key = ('BNB-USDT', '1h', 'LONG', 'EXIT')
    monkeypatch.setattr(uel, '_build_guardian_policy_profiles', lambda: {
        key: {'sample_size': 8, 'avg_delta_r': -0.35, 'helpful_rate': 0.2, 'harmful_rate': 0.75}
    })
    result = uel.get_guardian_policy_adjustment('BNB-USDT', '1h', 'LONG')
    assert result['exit_threshold_delta'] > 0
    assert result['sample_size'] == 8


def test_guardian_harmful_protect_requires_more_confirmation_after_eight(monkeypatch):
    key = ('BNB-USDT', '1h', 'LONG', 'PROTECT')
    monkeypatch.setattr(uel, '_build_guardian_policy_profiles', lambda: {
        key: {'sample_size': 9, 'avg_delta_r': -0.22, 'helpful_rate': 0.22, 'harmful_rate': 0.67}
    })
    result = uel.get_guardian_policy_adjustment('BNB-USDT', '1h', 'LONG')
    assert result['protect_policy'] == 'REQUIRE_MORE_CONFIRMATION'
    assert result['protect_sample_size'] == 9


def test_v6_timeframe_reference_is_not_a_hard_cap_and_quality_100_reaches_technical_cap():
    result = lev.select_risk_budget_leverage(
        minimum_required=1,
        sl_distance_pct=2.0,
        max_by_risk=30,
        max_by_atr_stress=30,
        safety_score=100,
        timeframe_static_max=10,  # old 4h ceiling: diagnostics only
        fallback_exchange_max=50,
        verified_exchange_max=50,
        max_by_liquidation_buffer=30,
        risk_allocation_fraction=0.20,
        emergency_max_leverage=50,
        quality_score=100,
    )
    assert result['leverage'] == 30
    assert result['timeframe_cap_mode'] == 'REFERENCE_ONLY_NOT_HARD_CAP'
    assert result['quality_is_probability'] is False


def test_v6_leverage_does_not_depend_on_user_size_fraction():
    common = dict(
        minimum_required=1, sl_distance_pct=3.0,
        max_by_risk=25, max_by_atr_stress=25, safety_score=82,
        timeframe_static_max=10, fallback_exchange_max=50,
        verified_exchange_max=50, max_by_liquidation_buffer=25,
        emergency_max_leverage=50, quality_score=82,
    )
    a = lev.select_risk_budget_leverage(**common, risk_allocation_fraction=1.0)
    b = lev.select_risk_budget_leverage(**common, risk_allocation_fraction=0.10)
    assert a['leverage'] == b['leverage']
    assert a['selection_policy'] == 'STANDARD_TECHNICAL_MAX_V6'


def test_futures_system_no_longer_reapplies_timeframe_hard_cap_or_user_size_to_economic_gate():
    assert 'STANDARD_TECHNICAL_MAX (contract/liquidation/SL/ATR)' in FUTSYS
    assert 'economic_reference_margin_usdt' in FUTSYS
    assert 'timeframe_cap_mode' in FUTSYS
    helper = FUTSYS[FUTSYS.index('def _leverage_in_valid_range'):FUTSYS.index('# ============================================================================\n# CLASE PRINCIPAL', FUTSYS.index('def _leverage_in_valid_range'))]
    assert 'LEVERAGE_RANGES.get' not in helper


def test_signal_validity_is_multi_candle_technical_and_source_anchored():
    assert "RC9_7_14_TECHNICAL_VALIDITY_V3" in APP
    assert "RC9_7_14_SPOT_TECHNICAL_VALIDITY_V3" in APP
    assert "'4h': 12" in APP  # Futures max horizon guardrail
    assert "'4h': 18" in APP  # Spot patient horizon guardrail
    assert 'ENTRY_DISTANCE_ATR' in APP
    assert 'STRUCTURAL_INVALIDATION' in APP
    assert 'source + pd.Timedelta' in APP


def test_official_confirmed_vigent_shadow_monitor_is_lightweight_and_user_independent():
    assert '_SPOT_OFFICIAL_SHADOW' in APP
    assert 'shadow_live_monitored' in APP
    assert 'mark-price shadow monitor for ALL Confirmed/Vigent' in APP
    # Telegram monitor may consume the event, but is not what enables shadow tracking.
    assert 'Shadow-live runs for every official signal, independent of users.' in APP
    # Background Entry Telegram must never re-run a heavy full analysis on cache miss.
    monitor = APP[APP.index('def monitor_entries_loop'):APP.index('# ============================================================================\n# COMMIT 36N', APP.index('def monitor_entries_loop'))]
    assert 'expert_system.analyze_full_market(symbol, tf)' not in monitor
    assert 'analyze_futures_market(symbol, tf)' not in monitor


def test_guardian_runtime_can_delay_repeated_harmful_protect_without_rewriting_levels():
    block = APP[APP.index('def _apply_96_guardian_risk_policy'):APP.index('# ============================================================================\n# MENSAJE FUTURES GUARDIAN', APP.index('def _apply_96_guardian_risk_policy'))]
    assert "protect_policy') or '') == 'REQUIRE_MORE_CONFIRMATION'" in block
    assert "action = 'HOLD'" in block
    assert 'suggested_stop_loss' not in block[block.index("protect_policy"):]


def test_saved_signal_r_uses_original_risk_even_after_guardian_moves_stop():
    saved = (ROOT / 'saved_signals.py').read_text(encoding='utf-8')
    start = saved.index('def _calculate_trade_r(')
    end = saved.index('def _build_early_exit_comparison', start)
    block = saved[start:end]
    assert "signal.get('original_entry')" in block
    assert "signal.get('original_stop_loss')" in block
    assert 'riesgo ORIGINAL' in block


def test_guardian_market_snapshot_is_shared_and_defers_under_memory_pressure():
    assert '_GUARDIAN_MARKET_CACHE' in APP
    assert '_GUARDIAN_MARKET_CACHE_TTL_SECONDS = 90' in APP
    block = APP[APP.index('def _guardian_prepare_futures_market_data'):APP.index('def _guardian_telegram_cooldown')]
    assert '_MEMORY_JOB_START_LIMIT_MB' in block
    assert 'ciclo diferido por RSS' in block
