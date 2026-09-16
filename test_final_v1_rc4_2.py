from pathlib import Path

from hierarchical_committee import build_hierarchical_assessment
from dynamic_expert_committee import install_governed_profile, get_governed_multiplier
from execution_challenger_lab import summarize_execution_challenger_evidence


def test_research_fusion_reads_only_final_rc42_generation():
    src = Path('research_evidence_fusion.py').read_text(encoding='utf-8')
    assert 'RFV1_12_RC5_ITERATIVE_EDGE_46CELL' in src
    assert 'RFV1_10_RC4_46CELL' not in src


def test_high_tf_context_is_required_not_assumed_neutral():
    votes = [
        {'trader': 'Smart Money', 'accion': 'LONG', 'confianza': 80},
        {'trader': 'Chartista', 'accion': 'LONG', 'confianza': 75},
    ]
    out = build_hierarchical_assessment(
        votes, baseline_action='LONG', market='FUTURES', timeframe='1D', symbol='BTC-USDT'
    )
    assert out['quality_gate_passed'] is False
    assert 'HIGH_TF_CONTEXT' in out['reason']
    assert out['policy']['required_context_fails_closed'] is True


def test_governed_trader_weight_is_symbol_specific():
    install_governed_profile({'rows': [
        {'trader': 'Smart Money', 'market': 'FUTURES', 'symbol': 'BTC-USDT', 'timeframe': '4H',
         'direction': 'SHORT', 'regime': 'TREND_DOWN', 'relation': 'SUPPORT', 'state': 'ACTIVE',
         'production_multiplier': 1.18, 'validation_n': 20},
        {'trader': 'Smart Money', 'market': 'FUTURES', 'symbol': 'XRP-USDT', 'timeframe': '4H',
         'direction': 'SHORT', 'regime': 'TREND_DOWN', 'relation': 'SUPPORT', 'state': 'PROTECT',
         'production_multiplier': 0.90, 'validation_n': 20},
    ]})
    btc, btc_state = get_governed_multiplier('Smart Money', 'FUTURES', '4H', 'SHORT', 'TREND_DOWN', symbol='BTC-USDT')
    xrp, xrp_state = get_governed_multiplier('Smart Money', 'FUTURES', '4H', 'SHORT', 'TREND_DOWN', symbol='XRP-USDT')
    assert btc_state == 'ACTIVE' and btc > 1.0
    assert xrp_state == 'PROTECT' and xrp < 1.0


def _challenger_row(symbol, timeframe, cid):
    return {
        'id': cid, 'system_type': 'futures', 'symbol': symbol, 'timeframe': timeframe,
        'created_at': '2026-09-14T00:00:00+00:00',
        'signal_results': {
            'status': 'tp_hit', 'gross_r': 1.0, 'modeled_net_r': 0.8,
            'execution_forensics': {'execution_challenger_results': {'results': [
                {'name': 'BASELINE', 'status': 'tp_hit', 'entry_reached': True, 'realized_r': 0.5, 'mfe_r': 0.8, 'mae_r': 0.2},
                {'name': 'DEFENSIBILITY', 'status': 'tp_hit', 'entry_reached': True, 'realized_r': 1.0, 'mfe_r': 1.2, 'mae_r': 0.15},
            ]}},
        },
    }


def test_execution_challenger_isolated_by_symbol_and_timeframe():
    rows = [_challenger_row('SOL-USDT', '2h', 'a'), _challenger_row('XRP-USDT', '30m', 'b')]
    out = summarize_execution_challenger_evidence({'FUTURES_CURRENT': rows})
    cells = {(r.get('symbol'), r.get('timeframe')) for r in out['rows'] if r.get('candidate') == 'DEFENSIBILITY'}
    assert ('SOL-USDT', '2H') in cells
    assert ('XRP-USDT', '30M') in cells
    assert out['policy']['symbol_timeframe_specific'] is True


def test_futures_ui_uses_intermarket_context_not_spot_rotation_placeholder():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    assert 'Contexto intermercado Futures' in html
    assert 'No representa una rotación BTC/PAXG' in html
    assert '20260916-RC7-PREAUDIT' in html


def test_link_bnb_and_high_tf_entry_contract_are_final_v1():
    src = Path('futures_system.py').read_text(encoding='utf-8')
    assert 'research_only_symbol = False' in src
    assert "'LINK-USDT'" in src and "'BNB-USDT'" in src
    assert '_confirm_high_tf_entry_trigger' in src
    assert "'12h': '2h'" in src and "'1D': '4h'" in src
    assert 'HIGH_TF_LOWER_TRIGGER_REQUIRED' in src


def test_public_analytics_hides_release_codes():
    html = Path('templates/analytics.html').read_text(encoding='utf-8')
    assert 'V1 RC4.1 · 46 celdas activas' not in html
    assert 'RC4 · Entry Reaction' not in html
    assert 'Estado del sistema · lectura rápida' in html
