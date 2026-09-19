from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
AI = (ROOT / 'ai_advisor.py').read_text(encoding='utf-8')


def _load_resolver():
    mod = ast.parse(APP)
    node = next(
        n for n in mod.body
        if isinstance(n, ast.FunctionDef)
        and n.name == '_resolve_ai_question_target'
    )
    ns = {}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
            '<resolver>',
            'exec'
        ),
        ns
    )
    return ns['_resolve_ai_question_target']


def test_all_futures_symbols_are_recognized_by_manual_chat_gate():
    for token in (
        'btc', 'eth', 'sol', 'xrp', 'ada', 'bnb', 'link', 'avax',
        'near', 'dot', 'sui', 'hype', 'apt', 'inj', 'sei', 'usdt'
    ):
        assert f'"{token}"' in AI


def test_link_avax_comparison_is_resolved_as_futures_multi_symbol():
    resolver = _load_resolver()
    result = resolver(
        'Conviene entrar a LINK-USDT y a AVAX-USDT o cual aconsejas?',
        'FUTURES',
        'LINK-USDT',
        '30m'
    )
    assert result['market'] == 'FUTURES'
    assert result['symbol'] == 'LINK-USDT'
    assert result['mentioned_symbols'] == ['LINK-USDT', 'AVAX-USDT']
    assert result['timeframe_explicit'] is False


def test_order_of_symbols_and_explicit_timeframe_are_preserved():
    resolver = _load_resolver()
    result = resolver(
        '¿AVAX o LINK en 4h?',
        'FUTURES',
        'BTC-USDT',
        '1h'
    )
    assert result['symbol'] == 'AVAX-USDT'
    assert result['mentioned_symbols'] == ['AVAX-USDT', 'LINK-USDT']
    assert result['timeframe'] == '4h'
    assert result['timeframe_explicit'] is True


def test_current_futures_timeframe_universe_is_supported():
    resolver = _load_resolver()
    assert resolver('BTC 1D', 'FUTURES', 'ETH-USDT', '1h')['timeframe'] == '1D'
    assert resolver('XRP 12h', 'FUTURES', 'BTC-USDT', '1h')['timeframe'] == '12h'
    assert resolver('SUI 4h', 'FUTURES', 'BTC-USDT', '1h')['timeframe'] == '1h'


def test_manual_comparison_context_and_prompt_contract_exist():
    assert 'def _build_ai_manual_comparison' in APP
    assert "context[\n                'manual_comparison'\n            ]" in APP
    assert 'Si manual_comparison existe' in AI
    assert 'no elegir' in APP.lower()
