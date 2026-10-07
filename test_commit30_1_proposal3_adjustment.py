from pathlib import Path

import commit30_1_core as c301
import champion_registry_commit19 as reg
import contextual_quality_commit28 as cq


def layers(direction='BULLISH', *, adx=24.0, volume=1.05, rsi=55.0):
    d = 'bullish' if direction == 'BULLISH' else 'bearish'
    return {
        'trend': {'direction': d, 'adx': adx},
        'momentum': {'direction': d, 'rsi': rsi},
        'volume': {'volume_ratio': volume},
        'volatility': {'atr': 2.0},
        'structure': {'direction': d, 'liquidity_sweeps':[{'direction':d}], 'order_blocks':[{'direction':d}]},
        'macro_context': {'risk_level':'NORMAL'},
    }


def op(action):
    d = 'BULLISH' if action == 'LONG' else 'BEARISH'
    return {'thesis': {'action':action,'direction':d,'quality':90}, 'context': {'regime':'TREND_UP' if action=='LONG' else 'TREND_DOWN','volatility':'NORMAL'}}


def mtf(direction):
    return {'state':'ALIGNED','usable':True,'dominant_direction':direction,'conflict':False}


def test_frozen_broader_volume_contract_is_preexisting_and_positive():
    c = c301.F30_FROZEN_STABILITY_CONTRACT
    assert c['volume_ratio_min'] == 1.0
    assert c['adx_min'] == 20.0
    assert c['development']['n'] == 16 and c['development']['net_stress_r'] > 0
    assert c['holdout']['n'] == 5 and c['holdout']['net_stress_r'] > 0
    assert c['frozen_before_current_incident'] is True


def test_f30_volume_105_passes_but_099_fails_without_lowering_adx():
    ok = reg.resolve_champion(layers=layers(volume=1.05), operational=op('LONG'), symbol='BTC-USDT', timeframe='30m', system_type='FUTURES', regime='TREND_UP', volatility='NORMAL', mtf_relation=mtf('BULLISH'))
    assert ok['eligible_for_execution_routing'] is True
    bad = reg.resolve_champion(layers=layers(volume=0.99), operational=op('LONG'), symbol='BTC-USDT', timeframe='30m', system_type='FUTURES', regime='TREND_UP', volatility='NORMAL', mtf_relation=mtf('BULLISH'))
    assert bad['eligible_for_execution_routing'] is False
    assert bad['reason'] == 'F30_VOLUME_BELOW_FROZEN_STABILITY_CONTRACT'
    weak_adx = reg.resolve_champion(layers=layers(adx=19.9, volume=2.0), operational=op('LONG'), symbol='BTC-USDT', timeframe='30m', system_type='FUTURES', regime='TREND_UP', volatility='NORMAL', mtf_relation=mtf('BULLISH'))
    assert weak_adx['eligible_for_execution_routing'] is False
    assert 'ADX' in weak_adx['reason']


def test_route_reason_survives_compact_route_shape_and_precedes_generic_reason():
    route = {'matched':False,'eligible_for_execution_routing':False,'reason':'F30_ADX_BELOW_FROZEN_STABILITY_CONTRACT'}
    result = {'operational_intelligence': {'commit19_champion': route}}
    assert cq._route_block(result)['reason'] == route['reason']
    text = Path(__file__).with_name('contextual_quality_commit28.py').read_text(encoding='utf-8')
    assert 'ROUTE_CONTEXT:{_route_reason}' in text
    assert text.index('shadow_reasons.append(f"ROUTE_CONTEXT:{_route_reason}"') < text.index('shadow_reasons.append("NO_VALIDATED_LIVE_ROUTE")')


def test_proposal3_event_lane_is_not_dropped_on_heavy_lock_or_ui_cooldown():
    text = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert '_commit30_1_release_priority_attempt(symbol, timeframe)' in text
    assert '_commit30_1_ack_priority(symbol, timeframe)' in text
    assert 'and not _c30_1_priority_pending' in text
    assert 'Memory backoff is NEVER bypassed' in text
    # The trigger AND the heavy-lock gate must both recognize a persisted
    # impulse owner; otherwise the old UI/background cooldown still starves it.
    assert "commit30_1_priority_owner = bool(_c30_priority_fn(owner))" in text
    assert 'priority_active and not commit30_1_priority_owner' in text
    assert '_background_heavy_cooldown_active() and not commit30_1_priority_owner' in text
    assert 'heavy-lock y memoria siguen siendo obligatorios' in text


def test_same_symbol_30m_rechecks_same_closed_candle_once_after_1h_context():
    text = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert "'force_same_candle_once': bool(target == source_symbol)" in text
    assert 'and not _c30_1_force_context_recompute' in text
    assert 'reevalúa la misma vela 30m una sola vez' in text


def test_regime_detector_now_receives_real_volume_on_main_analysis_path():
    text = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert 'def detect_market_regime(self, trend, momentum, volatility, structure, volume=None):' in text
    assert 'volume=(volume or {})' in text
    assert 'self.detect_market_regime(trend, momentum, volatility, structure, volume=volume)' in text


def test_hard_guards_are_unchanged():
    text = Path(__file__).with_name('contextual_quality_commit28.py').read_text(encoding='utf-8')
    assert 'PREMIUM_SAFETY_MIN = 75.0' in text
    assert 'RR_MIN = 1.8' in text and 'RR_MAX = 3.5' in text
    assert 'MAX_ATR_STRESS_PCT = 25.0' in text
    audit = c301.audit()
    assert audit['adx_lowered'] is False
    assert audit['rr_lowered'] is False
    assert audit['safety_lowered'] is False
    assert audit['new_live_1h_route'] is False
    assert audit['new_multiasset_live_route'] is False


def test_deploy_targets_commit30_1():
    root = Path(__file__).resolve().parent
    assert 'commit30_1_main_entrypoint:app' in (root/'Procfile').read_text(encoding='utf-8')
    assert 'commit30_1_main_entrypoint:app' in (root/'render.yaml').read_text(encoding='utf-8')
