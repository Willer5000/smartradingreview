from pathlib import Path

FUT = (Path(__file__).parent / 'static' / 'futures.js').read_text(encoding='utf-8')


def test_user_card_hides_internal_strategy_id_and_source():
    assert '_futUserStrategyLabel(cfgStrategy.family, sig.action)' in FUT
    assert 'cfgStrategy.id || cfgStrategy.family' not in FUT
    assert 'strategySource = cfgStrategy.source' not in FUT
    assert 'Familia:</span>' not in FUT
    assert 'Fuente:</span>' not in FUT


def test_user_card_uses_clear_labels():
    assert '🧩 Ficha técnica de la señal' in FUT
    assert 'Contexto:</span>' in FUT
    assert 'Alineación temporal:</span>' in FUT
    assert 'Seguridad técnica:</span>' in FUT
    assert 'Calidad de entrada:</span>' in FUT
    assert 'Zona alcanzable:</span>' in FUT
    assert 'Protección estructural del Entry:</span>' in FUT
    assert 'Evidencias técnicas:' in FUT


def test_internal_review_language_is_translated_for_ui_only():
    assert '🔬 Revisión técnica de la operación' in FUT
    assert '🔬 ReviewTrader · revisión post-trade' not in FUT
    assert '_futUserReviewState' in FUT
    assert '_futUserLearningAuthority' in FUT
    assert 'Solo observación' in FUT


def test_real_indicators_are_explained_when_present():
    for token in ('ADX ', 'DMI:', 'RSI ', 'MACD:', 'Volumen ', 'Volatilidad observada (ATR):'):
        assert token in FUT
    assert 'cfg.key_indicators' in FUT


def test_score_is_not_presented_as_tp_probability():
    assert 'no representan una probabilidad garantizada de tocar TP' in FUT
