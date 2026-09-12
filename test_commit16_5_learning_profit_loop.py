from pathlib import Path


def test_learning_proposals_get_machine_testable_filters():
    import ai_advisor
    rows = ai_advisor._normalize_strategy_proposals([{
        'name': 'Short 30m en tendencia bajista',
        'market': 'FUTURES',
        'thesis': 'Probar edge neto en tendencia bajista.',
        'entry_conditions': ['TREND_DOWN', 'SHORT', '30m'],
        'research_filters': {
            'timeframe': '30m',
            'direction': 'short',
            'regime': 'trend_down',
            'micro_alignment': 'aligned',
        },
    }])
    assert len(rows) == 1
    proposal = rows[0]
    assert proposal['status'] == 'SHADOW_PROPOSAL'
    assert proposal['runtime_testable'] is True
    assert proposal['research_filters']['market_family'] == 'CRYPTO_FUTURES'
    assert proposal['research_filters']['timeframe'] == '30M'
    assert proposal['research_filters']['direction'] == 'SHORT'
    assert proposal['proposal_id'].startswith('AI_')


def test_learning_scientist_receives_external_research_summary():
    root = Path(__file__).resolve().parent
    app = (root / 'app.py').read_text(encoding='utf-8')
    assert "'research_federation_v13'" in app
    assert '_research_compact(force=False)' in app


def test_activity_label_is_provider_aware_not_hardcoded_gemini():
    root = Path(__file__).resolve().parent
    text = (root / 'ai_advisor.py').read_text(encoding='utf-8')
    assert 'f"✅ {provider_short} activo"' in text
    assert 'if configured_provider == "GROQ_LEARNING"' in text


def test_learning_pdf_uses_exact_count_without_downloading_full_cohort():
    root = Path(__file__).resolve().parent
    text = (root / 'pdf_learning_report.py').read_text(encoding='utf-8')
    assert ".select('id', count='exact')" in text
    assert "count_proves_complete" in text
    assert "diagnostics['expected_rows'] = expected_rows" in text
