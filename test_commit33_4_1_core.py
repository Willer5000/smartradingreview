from __future__ import annotations

from pathlib import Path

import pipeline_integrity
import publication_quality

ROOT = Path(__file__).resolve().parent


def _layers():
    return {
        "trend": {"direction":"bullish","adx":27.0,"plus_di":37.0,"minus_di":13.0},
        "momentum": {"direction":"bullish","rsi":59.0,"score":1},
        "volatility": {"atr_pct":1.2,"volatility_percentile":55},
        "volume": {"volume_ratio":1.3,"obv_trend":"bullish"},
        "structure": {"direction":"bullish","order_blocks":[{"type":"bullish"}],"pullback":True},
        "macro_context": {"risk_level":"LOW"},
    }


def test_no_live_contingency_authority_in_app():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    live=text[text.index('def analyze_full_market'):text.index('class Moderador')]
    assert 'build_contingency_playbook' not in live
    assert "structure['_execution_setup']" in live
    assert "structure['_contingency_playbook'] = contingency_playbook" not in live


def test_operational_intelligence_no_longer_imports_contingency_engine():
    text=(ROOT/'operational_intelligence.py').read_text(encoding='utf-8')
    assert 'contingency_strategy_engine' not in text
    assert 'technical_evidence' in text


def test_cache_contract_is_invalidated_for_3341():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    assert '_FUTURES_CACHE_SCHEMA_VERSION = 5' in text
    assert "COMMIT33_4_1_PUBLICATION_AUTHORITY_V1" in text
    assert "existing.get('pipeline_generation') or '') == '33.4.1'" in text
    assert 'CORE_PUBLICATION_QUALITY_33_4_1' in text


def test_compact_snapshot_preserves_canonical_candidate_contract():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    start=text.index('def _compact_futures_runtime_result')
    end=text.index('def _serialize_futures_cache', start)
    block=text[start:end]
    assert "'pipeline_generation'" in block
    assert "'candidate_source': operational.get('candidate_source')" in block
    assert "'candidate_contract': dict(operational.get('candidate_contract') or {})" in block
    assert "'core_setup_support': list(operational.get('core_setup_support') or [])" in block

def test_directional_quality_is_not_scored_twice_at_publication():
    layers=_layers()
    op={
        'thesis':{'direction':'BULLISH','action':'LONG','quality':80,'independent_support_families':['trend','momentum','structure','volume']},
        'multi_timeframe':{'conflict':False},
    }
    routed=pipeline_integrity.reconcile_operational_candidate(op,layers=layers,symbol='BTC-USDT',timeframe='30m',system_type='FUTURES')
    assert routed['candidate_ready'] is True
    assert routed['candidate_contract']['passed'] is True
    # 80 is intentionally below the old duplicate publication floor of 84.
    result={
        'analysis_mode':'CLOSED_CANDLE','source_candle_closed':True,'market_data_is_synthetic':False,
        'decision':{'action':'LONG','confidence':80},'trend':layers['trend'],'momentum':layers['momentum'],
        'volatility':layers['volatility'],'structure':layers['structure'],'operational_intelligence':routed,
        'levels':{'entry':100,'stop_loss':98,'take_profit':104,'risk_reward':2.0,'entry_score':82,
                  'entry_source':'Order Block pullback','sl_reliability':0.82,'tp_quality_score':82,'setup_family':'THESIS_CORE','risk_control':{}},
    }
    auth=publication_quality.evaluate_publication(result,symbol='BTC-USDT',timeframe='30m',quality={})
    assert auth['route_authority']['core_technical_route_live'] is True
    assert auth['eligible'] is True


def test_multi_local_snapshot_requires_current_schema():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    assert "_MULTI_LOCAL_SNAPSHOT_SCHEMA_VERSION = '33.4.1'" in text
    assert "payload.get('version')" in text


def test_execution_setup_replaces_contingency_setup_in_active_execution():
    app_text=(ROOT/'app.py').read_text(encoding='utf-8')
    fut_text=(ROOT/'futures_system.py').read_text(encoding='utf-8')
    assert "structure.get('_execution_setup')" in app_text
    assert "structure.get('_execution_setup')" in fut_text
    assert "structure['_contingency_playbook'] = contingency_playbook" not in app_text


def test_versions_are_3341():
    import market_context, safety_profiles, technical_evidence
    assert pipeline_integrity.PIPELINE_GENERATION=='33.4.1'
    assert '33_4_1' in publication_quality.VERSION
    assert '33_4_1' in safety_profiles.VERSION
    assert '33_4_1' in market_context.VERSION
    assert '33_4_1' in technical_evidence.VERSION


def test_setup_guard_is_diagnostic_only_not_a_second_publication_gate():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    start=text.index('from operational_intelligence import execution_setup_guard')
    block=text[start:start+3500]
    assert "operational_execution['diagnostic_only'] = True" in block
    assert "operational_execution['publication_hard_block'] = False" in block
    assert "accion_consenso = _guard_action" not in block
    assert "levels['publication_status'] = 'ANALYSIS_ONLY'" not in block


def test_manual_analysis_geometry_cannot_promote_a_signal():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'def _build_manual_analysis_geometry' in text
    start=text.index('def _build_manual_analysis_geometry')
    end=text.index('def _get_default_levels', start)
    block=text[start:end]
    assert "'manual_geometry_authority': 'USER_MANUAL_ANALYSIS_ONLY'" in block
    assert "'publication_status': 'ANALYSIS_ONLY'" in block
    assert "'is_executable': False" in block


def test_runtime_identity_is_single_3341_core():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'COMMIT33_4_1_CANONICAL_FLOW_V1' in text
    assert '✅ [33.4.1] núcleo canónico activo' in text
    proc=(ROOT/'Procfile').read_text(encoding='utf-8')
    render=(ROOT/'render.yaml').read_text(encoding='utf-8')
    assert 'app:app' in proc
    assert 'app:app' in render


def test_active_core_contains_no_deleted_commit_imports():
    forbidden=(
        'commit28_core', 'commit29_core', 'commit30_core',
        'premium_path_expansion_20', 'pipeline_integrity_175', 'execution_abi_175',
    )
    active=(
        'app.py','futures_system.py','multiasset_system.py','operational_intelligence.py',
        'market_context.py','technical_evidence.py','pipeline_integrity.py',
        'publication_quality.py','safety_profiles.py','worker_orchestration.py',
    )
    for name in active:
        text=(ROOT/name).read_text(encoding='utf-8')
        for token in forbidden:
            assert token not in text, f'{name} still references {token}'


def test_active_quality_labels_no_longer_claim_old_commit_authority():
    text=(ROOT/'app.py').read_text(encoding='utf-8')
    start=text.index('def _core_publication_authority')
    block=text[start:start+10000]
    assert 'CORE_SIGNAL_FUNNEL_33_4_1_V1' in block
    assert 'CORE_SPECIALISED_SAFETY_33_4_1' in block
    assert 'COMMIT28_SIGNAL_FUNNEL_V1' not in block
    assert 'COMMIT31_MULTI_SAFETY_AUTHORITY' not in block
