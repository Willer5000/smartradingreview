from datetime import datetime, timedelta, timezone

import pandas as pd

from portfolio_guardian import PortfolioGuardian
from saved_signals import _guardian_exit_hold_counterfactual


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _signal(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        'id': 'sig-rc3',
        'symbol': 'XRP-USDT',
        'timeframe': '4h',
        'action': 'LONG',
        'entry': 1.3504,
        'stop_loss': 1.3268,
        'take_profit': 1.3823,
        'status': 'entry_touched',
        'entry_touched': True,
        'created_at': _iso(now - timedelta(hours=30)),
        'entry_at': _iso(now - timedelta(hours=24)),
        'entry_touched_at': _iso(now - timedelta(hours=2)),
        'risk_class': 'HIGH',
        'investment_usdt': 24.0,
        'leverage': 2,
    }
    base.update(overrides)
    return base


def _candles_after(start, closes, *, width=0.002):
    times = []
    highs = []
    lows = []
    for i, c in enumerate(closes, start=1):
        times.append(_iso(start + timedelta(hours=4 * i)))
        highs.append(c + width)
        lows.append(c - width)
    return {'time': times, 'close': closes, 'high': highs, 'low': lows}


def test_guardian_clock_starts_at_entry_touch_not_signal_creation():
    g = PortfolioGuardian()
    now = datetime.now(timezone.utc)
    touch = now - timedelta(hours=2)
    sig = _signal(
        created_at=_iso(now - timedelta(days=2)),
        entry_at=_iso(now - timedelta(hours=20)),
        entry_touched_at=_iso(touch),
    )
    candles = _candles_after(touch, [1.3510, 1.3520, 1.3530])
    out = g.evaluate_futures_position(sig, 1.3530, candles)
    assert out['analysis_version'] == 'RC3_GUARDIAN_TRADER_V2'
    assert out['entry_clock_source'] == 'entry_touched_at'
    assert 60 <= out['elapsed_minutes'] <= 180


def test_guardian_does_not_use_pre_entry_candles_for_mae_or_structure():
    g = PortfolioGuardian()
    now = datetime.now(timezone.utc)
    touch = now - timedelta(hours=12)
    sig = _signal(entry_touched_at=_iso(touch), entry_at=_iso(now - timedelta(days=1)))

    # Dos velas anteriores al Entry contienen una caída extrema que no debe
    # contaminar MAE ni la estructura de la posición realmente abierta.
    times = [
        _iso(touch - timedelta(hours=8)),
        _iso(touch - timedelta(hours=4)),
        _iso(touch + timedelta(hours=4)),
        _iso(touch + timedelta(hours=8)),
    ]
    candles = {
        'time': times,
        'close': [1.20, 1.25, 1.3510, 1.3560],
        'high': [1.23, 1.27, 1.3570, 1.3600],
        'low': [1.10, 1.18, 1.3470, 1.3510],
    }
    out = g.evaluate_futures_position(sig, 1.3560, candles)
    assert out['post_entry_closed_candles'] == 2
    assert out['mae_pct'] < 1.0
    assert out['structure_deteriorated'] is False
    assert out['action'] != 'EXIT'


def test_stagnation_alone_never_forces_exit_on_4h_trade():
    g = PortfolioGuardian()
    now = datetime.now(timezone.utc)
    touch = now - timedelta(hours=20)
    sig = _signal(entry_touched_at=_iso(touch), risk_class='HIGH')
    # Mercado lateral post-entry, sin ruptura estructural confirmada.
    closes = [1.3508, 1.3512, 1.3509, 1.3510, 1.3507, 1.3509]
    candles = _candles_after(touch, closes, width=0.0009)
    out = g.evaluate_futures_position(sig, 1.3509, candles)
    assert out['stagnant'] is True
    assert out['thesis_invalidated'] is False
    assert out['action'] == 'HOLD'


def test_high_risk_trade_is_not_scaled_in():
    g = PortfolioGuardian()
    plan = g._build_futures_management_plan(
        action='LONG',
        entry=100.0,
        sl=95.0,
        tp=115.0,
        current_price=106.0,
        highs=[102.0, 104.0, 106.5],
        lows=[100.5, 102.0, 104.5],
        recent_change_pct=0.8,
        fast_avg=105.0,
        slow_avg=103.0,
        structure_deteriorated=False,
        deterioration_score=0,
        timeframe='4h',
        risk_class='HIGH',
        investment_usdt=100.0,
        leverage=2,
    )
    assert plan['suggested_add_position_pct'] is None
    assert 'ADD' not in plan['management_action']


def test_profitable_protected_trade_can_receive_small_scale_in_recommendation():
    g = PortfolioGuardian()
    plan = g._build_futures_management_plan(
        action='LONG',
        entry=100.0,
        sl=95.0,
        tp=115.0,
        current_price=106.0,
        highs=[102.0, 104.0, 106.5],
        lows=[100.5, 102.0, 104.5],
        recent_change_pct=0.8,
        fast_avg=105.0,
        slow_avg=103.0,
        structure_deteriorated=False,
        deterioration_score=0,
        timeframe='4h',
        risk_class='MEDIUM',
        investment_usdt=100.0,
        leverage=2,
    )
    assert plan['suggested_stop_loss'] is not None
    assert plan['suggested_add_position_pct'] is not None
    assert 0 < plan['suggested_add_position_pct'] <= 15
    assert plan['scale_in_rr'] >= 1.5
    assert 'ADD' in plan['management_action']


def test_exit_learning_keeps_original_trade_alive_and_detects_cut_winner():
    now = pd.Timestamp.now(tz='UTC')
    observed = now - pd.Timedelta(hours=12)
    touch = observed - pd.Timedelta(hours=8)
    sig = _signal(
        entry=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        timeframe='4h',
        entry_touched_at=touch.isoformat(),
        entry_at=touch.isoformat(),
        created_at=(touch - pd.Timedelta(hours=4)).isoformat(),
        action='LONG',
        status='closed_manual',
        closed_price=102.0,
    )
    event = {
        'observed_at': observed.isoformat(),
        'observed_price': 102.0,
        'observed_r': 0.4,
        'original_stop_loss': 95.0,
        'original_take_profit': 110.0,
        'direction': 'LONG',
    }

    def fetcher(symbol, timeframe):
        return pd.DataFrame({
            'time': [
                (observed + pd.Timedelta(hours=1)).isoformat(),
                (observed + pd.Timedelta(hours=5)).isoformat(),
            ],
            'open': [102.0, 105.0],
            'high': [106.0, 111.0],
            'low': [101.0, 104.0],
            'close': [105.0, 110.5],
        })

    result = _guardian_exit_hold_counterfactual(event, sig, fetcher)
    assert result['counterfactual_status'] == 'EVALUATED_HOLD_TP'
    assert result['counterfactual_r'] == 2.0
    assert result['delta_r'] < 0
    assert result['would_help'] is False


def test_tp_extension_can_use_pre_entry_closed_structural_target():
    g = PortfolioGuardian()
    plan = g._build_futures_management_plan(
        action='LONG',
        entry=100.0,
        sl=95.0,
        tp=110.0,
        current_price=108.0,
        highs=[103.0, 106.0, 108.2],
        lows=[100.0, 102.0, 105.0],
        context_highs=[104.0, 111.5, 109.0, 108.2],
        context_lows=[96.0, 98.0, 100.0, 105.0],
        recent_change_pct=0.8,
        fast_avg=107.0,
        slow_avg=105.0,
        structure_deteriorated=False,
        deterioration_score=0,
        timeframe='4h',
        risk_class='MEDIUM',
        investment_usdt=100.0,
        leverage=2,
    )
    assert plan['suggested_take_profit'] == 111.5
    assert 'EXTEND' in plan['management_action']
