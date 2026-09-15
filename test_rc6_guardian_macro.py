from datetime import datetime, timezone, timedelta

from portfolio_guardian import PortfolioGuardian
from macro_context import classify_macro_headline


def _snap(trend='neutral', momentum='neutral', adx=20, close=0.0, body=0.0, two=0.0, atr=1.0, ratio=1.0):
    return {
        'success': True,
        'decision': {'action': 'NO_OPERAR', 'confidence': 0},
        'levels': {'execution_safety': 70},
        'trend': {'direction': trend, 'adx': adx},
        'momentum': {'direction': momentum},
        'structure': {},
        'closed_candle': {
            'close_change_pct': close,
            'body_change_pct': body,
            'two_bar_change_pct': two,
            'closed': True,
        },
        'volatility': {
            'atr_pct': atr,
            'volatility_ratio': ratio,
            'volatility_percentile': 70,
        },
    }


def _market(btc4, btc12=None, btc1d=None, paxg4=None, ratio4=None):
    out = {}
    for tf, b in [('4h', btc4), ('12h', btc12 or _snap()), ('1D', btc1d or _snap()), ('1W', _snap())]:
        out[tf] = {
            'BTC-USDT': b,
            'PAXG-USDT': paxg4 if tf == '4h' and paxg4 else _snap(),
            'PAXG-BTC': ratio4 if tf == '4h' and ratio4 else _snap(),
        }
    return out


def test_no_operar_can_still_express_bearish_portfolio_context():
    g = PortfolioGuardian()
    score = g._score_market_snapshot(_snap('bearish', 'bearish', 31, close=-1.1), 'BTC')
    assert score < 0
    assert abs(score) <= 62.0


def test_macro_alone_does_not_sell_btc():
    g = PortfolioGuardian()
    market = _market(_snap('neutral', 'neutral', 18))
    risk = g._build_spot_market_risk_watch(
        market,
        {'current_risk_level': 'CRITICAL', 'directional_bias': 'RISK_OFF'},
        pct_btc=0.50,
        pct_paxg=0.30,
        pct_usdt=0.20,
    )
    assert risk['alert'] is True
    assert risk['technical_confirmed'] is False
    assert risk['defensive_action_eligible'] is False


def test_closed_btc_deterioration_plus_context_enables_partial_defense():
    g = PortfolioGuardian()
    market = _market(
        _snap('bearish', 'bearish', 32, close=-1.8, body=-1.6, two=-2.7, atr=1.4, ratio=1.7),
        btc12=_snap('bearish', 'bearish', 27),
        btc1d=_snap('bearish', 'neutral', 24),
        paxg4=_snap('bullish', 'bullish', 25),
        ratio4=_snap('bullish', 'bullish', 25),
    )
    risk = g._build_spot_market_risk_watch(
        market,
        {'current_risk_level': 'HIGH', 'directional_bias': 'RISK_OFF'},
        pct_btc=0.55,
        pct_paxg=0.30,
        pct_usdt=0.15,
    )
    assert risk['level'] in {'HIGH', 'CRITICAL'}
    assert risk['technical_confirmed'] is True
    assert risk['defensive_action_eligible'] is True


def test_recovered_close_does_not_treat_lower_wick_as_defense_trigger():
    g = PortfolioGuardian()
    market = _market(
        _snap('bullish', 'bullish', 26, close=0.25, body=0.35, two=0.4, atr=1.6, ratio=1.8),
        btc12=_snap('bullish', 'neutral', 22),
        btc1d=_snap('neutral', 'neutral', 18),
    )
    risk = g._build_spot_market_risk_watch(
        market,
        {'current_risk_level': 'HIGH', 'directional_bias': 'RISK_OFF'},
        pct_btc=0.55,
        pct_paxg=0.30,
        pct_usdt=0.15,
    )
    assert risk['closed_shock'] is False
    assert risk['technical_confirmed'] is False
    assert risk['defensive_action_eligible'] is False


def test_macro_classifier_understands_oil_yields_and_rate_hike_as_risk_off():
    result = classify_macro_headline(
        'Oil surges as Treasury yields breach 5% and Fed rate hike bets rise',
        'test',
    )
    assert result['risk_level'] in {'HIGH', 'CRITICAL'}
    assert result['risk_bias'] == 'RISK_OFF'
    codes = {row['code'] for row in result['categories']}
    assert 'ENERGY_INFLATION' in codes
    assert 'RATES_BONDS' in codes


def test_clarity_act_is_crypto_legislation_context_not_trade_signal():
    result = classify_macro_headline(
        'US Senate to vote on advancing Clarity Act crypto bill',
        'test',
    )
    codes = {row['code'] for row in result['categories']}
    assert 'CRYPTO_LEGISLATION' in codes
    assert result['method'] == 'RULE_BASED_CONTEXT_ONLY'


def test_futures_macro_high_blocks_add_extend_but_does_not_create_exit(monkeypatch):
    g = PortfolioGuardian()
    def fake_plan(**kwargs):
        return {
            'management_action': 'ADD_AND_EXTEND',
            'suggested_stop_loss': None,
            'suggested_take_profit': 114.0,
            'suggested_add_entry': 103.0,
            'suggested_add_position_pct': 10.0,
            'suggested_add_position_usdt': 10.0,
            'scale_in_rr': 2.0,
            'progress_r': 0.8,
            'tp_progress_ratio': 0.4,
            'momentum_with_position': True,
            'trade_state': 'OPPORTUNITY',
            'management_reason': 'setup técnico permite add/extend',
        }
    monkeypatch.setattr(g, '_build_futures_management_plan', fake_plan)
    signal = {
        'status': 'entry_touched', 'action': 'LONG', 'entry': 100.0,
        'stop_loss': 95.0, 'take_profit': 110.0, 'leverage': 3,
        'timeframe': '1h', 'entry_touched_at': (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
    }
    # Import local here so the top of the test stays lightweight.
    candles = {
        'close': [100, 101, 102, 103, 104, 104.2, 104.3, 104.0],
        'high': [101, 102, 103, 104, 105, 105, 105, 105],
        'low': [99, 100, 101, 102, 103, 103, 103, 103],
    }
    advice = g.evaluate_futures_position(
        signal, 104.0, candles,
        macro_context={'current_risk_level': 'HIGH', 'directional_bias': 'RISK_OFF'},
    )
    assert advice['action'] == 'HOLD'
    assert advice['management_action'] == 'HOLD'
    assert advice['macro_overlay_applied'] is True
    assert advice['suggested_add_position_pct'] is None
    assert advice['suggested_take_profit'] is None
    assert advice['action'] not in {'EXIT', 'REDUCE'}
