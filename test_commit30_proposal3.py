from pathlib import Path

import commit30_core as c30
from operational_intelligence import build_independent_thesis, canonical_regime
from champion_registry_commit19 import route_registry


def btc_crash_layers():
    return {
        'trend': {'direction':'bearish','adx':17.7,'plus_di':9.5,'minus_di':42.2},
        'momentum': {'direction':'bearish','score':-4.0,'indicators':{'rsi':23.9,'macd_histogram':-1.0}},
        'volume': {'volume_ratio':2.82,'obv_direction':'bearish'},
        'structure': {
            'structure_direction':'bearish',
            'order_blocks':[{'direction':'bearish'}],
            'fair_value_gaps':[{'direction':'bearish'}],
            'liquidity_sweeps':[{'direction':'bearish'}],
        },
        'volatility': {'bb_width':2.81,'atr_pct':1.0},
        'macro_context': {'risk_level':'NORMAL'},
        'liquidation': {'direction':'bearish'},
    }


def test_observed_btc_1h_crash_is_directional_impulse_not_range():
    l=btc_crash_layers()
    impulse=c30.detect_directional_impulse(l['trend'],l['momentum'],l['volume'],l['structure'])
    assert impulse['active'] is True
    assert impulse['direction']=='bearish'
    regime=c30.classify_market_regime(l['trend'],l['volatility'],l['momentum'],l['volume'],l['structure'])
    assert regime['regime']=='DIRECTIONAL_IMPULSE_BEAR'


def test_low_adx_without_dmi_dominance_stays_range():
    impulse=c30.detect_directional_impulse(
        {'direction':'bearish','adx':16,'plus_di':18,'minus_di':21},
        {'direction':'bearish','indicators':{'rsi':42}},
        {'volume_ratio':1.5},
        {'structure_direction':'bearish','order_blocks':[{}]},
    )
    assert impulse['active'] is False
    regime=c30.classify_market_regime(
        {'direction':'bearish','adx':16,'plus_di':18,'minus_di':21},
        {'bb_width':2.0},
        {'direction':'bearish','indicators':{'rsi':42}},
        {'volume_ratio':1.5},
        {'structure_direction':'bearish','order_blocks':[{}]},
    )
    assert regime['regime']=='RANGING'


def test_impulse_strengthens_existing_trend_family_without_new_family():
    l=btc_crash_layers()
    thesis=build_independent_thesis(
        layers=l,
        mtf_context={
            'dominant_direction':'bearish','alignment':'ALIGNED','conflict':False,
            'public_summary':'1h→2h bearish aligned'
        },
        market='FUTURES', symbol='BTC-USDT', timeframe='1h',
    )
    assert thesis['action']=='SHORT'
    assert 'trend' in thesis['short_families']
    assert 'multiframe' in thesis['short_families']
    assert 'directional_impulse' not in thesis['families']


def test_impulse_regime_maps_to_trend_context_not_new_alpha_family():
    assert canonical_regime('DIRECTIONAL_IMPULSE_BEAR')=='TREND_DOWN'
    assert canonical_regime('DIRECTIONAL_IMPULSE_BULL')=='TREND_UP'


def test_no_direct_1h_champion_is_invented():
    specs=list(route_registry().values())
    btc_1h=[s for s in specs if str(s.get('market')).upper()=='FUTURES' and str(s.get('timeframe')).upper()=='1H' and 'BTC-USDT' in set(s.get('symbols') or [])]
    assert btc_1h == []


def test_commit30_routes_impulse_only_to_existing_validated_30m_lane():
    text=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert '_commit30_enqueue_impulse_priority' in text
    assert "(target, '30m', _now)" in text
    assert 'no publica por sí solo' in text


def test_deploy_files_target_commit30():
    root=Path(__file__).resolve().parent
    assert 'commit30_main_entrypoint:app' in (root/'Procfile').read_text(encoding='utf-8')
    assert 'commit30_main_entrypoint:app' in (root/'render.yaml').read_text(encoding='utf-8')


def test_hard_safety_contract_unchanged():
    text=Path(__file__).with_name('contextual_quality_commit28.py').read_text(encoding='utf-8')
    assert 'PREMIUM_SAFETY_MIN = 75.0' in text
    assert 'RR_MIN = 1.8' in text and 'RR_MAX = 3.5' in text
    assert 'MAX_ATR_STRESS_PCT = 25.0' in text


def test_particular_setup_recognizes_impulse_but_remains_separate_from_route_authority():
    from pipeline_integrity_175102 import _live_evidence, _evaluate_particular_side
    l=btc_crash_layers()
    op={'multi_timeframe':{'dominant_direction':'bearish','alignment':'ALIGNED','conflict':False}}
    ev=_live_evidence(l,op,'BEARISH')
    assert ev['dmi_impulse'] is True
    best=_evaluate_particular_side(l,op,'BEARISH')['best']
    assert best and best['setup']=='DIRECTIONAL_IMPULSE_CONTINUATION'
    assert best['passed'] is True


def test_technical_and_multiframe_specialists_are_impulse_aware():
    text=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert 'IMPULSO_DMI_BAJISTA' in text and 'IMPULSO_DMI_ALCISTA' in text
    assert 'IMPULSO_MTF_BEARISH' in text and 'IMPULSO_MTF_BULLISH' in text


def test_impulse_priority_queue_preserves_not_due_cells():
    text=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert '_keep_impulse.append((_sym, _tf, _created))' in text
    assert '5400.0' in text
    assert '_chosen_impulse' in text

def test_observed_btc_1h_impulse_survives_when_mtf_context_is_temporarily_unavailable():
    # Exact causal class observed in production: the independent thesis arrived
    # before a usable higher-TF context object. C29 had only three strong
    # families and returned PRECAUCION/56; C30 strengthens the existing trend
    # family from DMI+momentum rather than inventing a new independent vote.
    l=btc_crash_layers()
    thesis=build_independent_thesis(
        layers=l, mtf_context={}, market='FUTURES', symbol='BTC-USDT', timeframe='1h'
    )
    assert thesis['action']=='SHORT'
    assert thesis['quality'] >= 82.0
    assert set(thesis['short_families']) >= {'trend','structure','momentum','volume'}
    assert 'multiframe' not in thesis['short_families']
