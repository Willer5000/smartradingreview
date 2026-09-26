from pathlib import Path
import execution_geometry_committee as geom
from leverage_policy import select_risk_budget_leverage

ROOT = Path(__file__).resolve().parent


def profile(market, symbol, tf='1h'):
    return geom.build_profile(
        market_type=market,
        symbol=symbol,
        timeframe=tf,
        direction='long',
        setup_family='TREND_PULLBACK',
        market_regime='TRENDING_BULL',
        trend={}, momentum={},
        volatility={'atr_pct': 1.0, 'volatility_ratio': 1.0, 'volatility_percentile': 50},
    )


def test_contextual_rr_floors_by_market_family():
    assert profile('spot','BTC-USDT','4h')['technical_rr_floor'] == 1.5
    assert profile('spot','PAXG-BTC','4h')['technical_rr_floor'] == 1.3
    assert profile('futures','BTC-USDT','1h')['technical_rr_floor'] == 1.55
    assert profile('futures','SUI-USDT','30m')['technical_rr_floor'] == 1.35


def test_multiasset_families_do_not_inherit_crypto_bucket():
    assert geom.instrument_bucket('futures','SPY-USDT') == 'MULTI_US_INDEX'
    assert geom.instrument_bucket('futures','CL-USDT') == 'MULTI_ENERGY'
    assert geom.instrument_bucket('futures','COPPER-USDT') == 'MULTI_INDUSTRIAL_METAL'
    assert geom.instrument_bucket('futures','XAG-USDT') == 'MULTI_PRECIOUS_METAL'
    assert geom.instrument_bucket('futures','KSTR-USDT') == 'MULTI_CHINA_INDEX'


def test_long_short_share_geometry_policy_without_directional_bias():
    p_long = geom.build_profile(
        market_type='futures', symbol='ADA-USDT', timeframe='2h', direction='long',
        setup_family='TREND_PULLBACK', market_regime='TRENDING_BULL',
        trend={}, momentum={}, volatility={'atr_pct': 1.0, 'volatility_ratio': 1.0, 'volatility_percentile': 50},
    )
    p_short = geom.build_profile(
        market_type='futures', symbol='ADA-USDT', timeframe='2h', direction='short',
        setup_family='TREND_PULLBACK', market_regime='TRENDING_BEAR',
        trend={}, momentum={}, volatility={'atr_pct': 1.0, 'volatility_ratio': 1.0, 'volatility_percentile': 50},
    )
    assert p_long['technical_rr_floor'] == p_short['technical_rr_floor'] == 1.5
    assert p_long['instrument_bucket'] == p_short['instrument_bucket'] == 'CORE2'


def test_review_learning_has_zero_tp_influence_before_eight_samples():
    base = profile('futures','ADA-USDT','2h')
    base['learning'] = {'sample_size': 7, 'weight': 0.0, 'avg_mfe_r': 1.2, 'tp_speed_bias': 1.0}
    with_learning = geom.tp_candidate_adjustment(base, candidate_type='resistance', rr=1.6, distance_atr=2.0)
    control = dict(base)
    control['learning'] = {'sample_size': 0, 'weight': 0.0, 'avg_mfe_r': None, 'tp_speed_bias': 0.0}
    without_learning = geom.tp_candidate_adjustment(control, candidate_type='resistance', rr=1.6, distance_atr=2.0)
    assert with_learning == without_learning


def test_mature_learning_can_only_boundedly_bias_tp_ranking():
    p = profile('futures','ADA-USDT','2h')
    p['learning'] = {'sample_size': 12, 'weight': 0.08, 'avg_mfe_r': 1.6, 'tp_speed_bias': 0.8}
    score = geom.tp_candidate_adjustment(p, candidate_type='resistance', rr=1.55, distance_atr=2.0)
    assert -18.0 <= score <= 18.0


def test_compact_target_must_fit_existing_safe_leverage_envelope():
    viable = select_risk_budget_leverage(
        minimum_required=12.0,
        sl_distance_pct=1.0,
        max_by_risk=20.0,
        max_by_atr_stress=20.0,
        safety_score=85.0,
        quality_score=85.0,
        timeframe_static_max=10.0,
        fallback_exchange_max=50.0,
        verified_exchange_max=50.0,
        max_by_liquidation_buffer=20.0,
        emergency_max_leverage=50.0,
    )
    assert viable is not None and viable['leverage'] >= 12
    rejected = select_risk_budget_leverage(
        minimum_required=24.0,
        sl_distance_pct=1.0,
        max_by_risk=20.0,
        max_by_atr_stress=20.0,
        safety_score=85.0,
        quality_score=85.0,
        timeframe_static_max=10.0,
        fallback_exchange_max=50.0,
        verified_exchange_max=50.0,
        max_by_liquidation_buffer=20.0,
        emergency_max_leverage=50.0,
    )
    assert rejected is None


def test_app_no_longer_hardcodes_18r_as_post_selection_veto():
    source = (ROOT/'app.py').read_text(encoding='utf-8')
    assert "if rr < minimum_viable_rr:" in source
    assert "min_distance_from_sl = technical_rr_floor * sl_distance_pct" in source
    assert "'minimum_viable_rr':" in source


def test_futures_q2_and_publication_use_contextual_rr():
    source = (ROOT/'futures_system.py').read_text(encoding='utf-8')
    assert "technical_rr_floor" in source
    assert "minimum_required=minimum_required_leverage" in source
    assert "compact_target = 0 < target_rr < 1.8" in source
    assert "result.get('minimum_viable_rr')" in source


def test_guardian_authority_is_preserved():
    source = (ROOT/'app.py').read_text(encoding='utf-8')
    for action in ('PROTECT','EXTEND','PROTECT_AND_EXTEND','REDUCE','EXIT'):
        assert action in source
    assert 'get_guardian_policy_adjustment' in source
    assert 'REQUIRE_MORE_CONFIRMATION' in source


def test_no_frontend_or_resource_expansion_required():
    multi = (ROOT/'multiasset_system.py').read_text(encoding='utf-8')
    assert "'auto_ai_calls':0" in multi
    assert "'scanner_supabase_writes':0" in multi
    assert "'extra_worker_threads':0" in multi
    # Commit 13 needs no additional automatic AI/DB/thread budget. Frontend
    # files and SQL schemas are intentionally outside this change.
