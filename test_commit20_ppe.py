from premium_path_expansion_20 import (
    VERSION,
    PREMIUM_MIN_SAFETY,
    PREMIUM_MIN_TP,
    PREMIUM_MIN_SL,
    PREMIUM_MIN_RR,
    PREMIUM_MAX_RR,
    _geometry_score,
    _route_families,
)


def test_contract_values_unchanged():
    assert VERSION == "COMMIT20_PREMIUM_PATH_EXPANSION_V1"
    assert PREMIUM_MIN_SAFETY == 75.0
    assert PREMIUM_MIN_TP == 55.0
    assert PREMIUM_MIN_SL == 60.0
    assert PREMIUM_MIN_RR == 1.8
    assert PREMIUM_MAX_RR == 3.5


def test_route_router_is_contextual_and_bounded():
    routes = _route_families(
        setup_family="TREND_PULLBACK",
        trend={"adx": 31, "regime": "TRENDING_BULL", "direction": "BULLISH"},
        momentum={"rsi": 61},
        volatility={"state": "NORMAL", "atr_pct": 1.2},
        structure={
            "order_blocks": [{"type": "bullish"}],
            "fair_value_gaps": [{"type": "bullish"}],
            "liquidity_sweeps": [],
        },
        symbol="BTC-USDT",
        timeframe="1h",
        market_type="futures",
    )
    assert 0 < len(routes) <= 2
    assert "TREND_PULLBACK" not in routes


def test_geometry_score_prefers_coherent_package():
    strong = {
        "entry_score": 88,
        "sl_reliability": 0.84,
        "tp_quality_score": 82,
        "risk_reward": 2.3,
        "execution_geometry_quality": 86,
    }
    weak = {
        "entry_score": 66,
        "sl_reliability": 0.54,
        "tp_quality_score": 58,
        "risk_reward": 1.7,
        "execution_geometry_quality": 60,
    }
    assert _geometry_score(strong) > _geometry_score(weak)
