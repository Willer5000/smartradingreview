from pathlib import Path

def test_strategy_bank_covers_every_indicator_twice():
    from default_strategy_bank import validate_bank, STRATEGIES, INDICATOR_UNIVERSE
    v=validate_bank()
    assert v['ok'], v
    assert min(v['counts'].values()) >= 2
    assert all(len(set(s['indicators'])) < len(INDICATOR_UNIVERSE) for s in STRATEGIES)

def test_internal_committee_language_never_public():
    from reason_presenter import public_reason
    assert public_reason('Veto único de Escéptico (100%) sin réplica del comité') == ''
    assert public_reason('Veto por consenso (2 traders): Smart Money, Chartista') == ''
    assert public_reason('ADX 31 confirma fuerza bajista')
    assert public_reason('Pullback a EMA21 con rechazo de resistencia')
    assert public_reason('Smart Money (95%): Order Block bajista con volumen 1.8x') == 'Order Block bajista con volumen 1.8x.'

def test_scalping_is_only_5m_15m_and_standard_is_separate():
    text=Path('app.py').read_text(encoding='utf-8')
    assert "_FUTURES_SCALPING_TFS = (\n    '5m',\n    '15m',\n)" in text
    assert "_FUTURES_STANDARD_ALERT_TFS = ('30m','1h','2h','4h','12h','1D')" in text
    assert "publication_status!='EXECUTABLE_SIGNAL'" in text

def test_public_message_does_not_insert_committee_reasons():
    text=Path('app.py').read_text(encoding='utf-8')
    block=text[text.index('def generate_professional_message_with_consenso'):text.index('# ============ EXTRACCIÓN MASIVA', text.index('def generate_professional_message_with_consenso'))]
    assert 'Bloqueo principal' not in block
    assert 'Motivo del LONG Futures' not in block


def test_main_free_plan_default_budget_is_conservative():
    text=Path('supabase_client.py').read_text(encoding='utf-8')
    assert "MAIN_SUPABASE_DAILY_BUDGET_MB', '60'" in text
