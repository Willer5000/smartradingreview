import ast
from pathlib import Path

APP = Path(__file__).with_name('app.py')


def _helpers():
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    names = {
        '_tgp_public_reason',
        '_tgp_public_target_pct',
        '_tgp_public_alert_family',
        '_tgp_public_subject',
        '_tgp_public_allocation_lines',
    }
    nodes = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name in names
    ]
    ns = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<helpers>', 'exec'), ns)
    return ns


def test_guardian_public_reason_hides_internal_codes():
    ns = _helpers()
    reason = (
        'Best TF=4h. Q4B: todavía no existe evidencia Q1 suficiente; '
        'se conserva la decisión previa del TGP. '
        'Fase de retorno gradual BTC=1/3: el tamaño original era 8.0% '
        'del activo fuente y el límite actual es 8.0%. Confirmación BTC=2/4 TF, '
        '1D/1W directos=1/2, edge=28.5. El retorno se hace por tramos para evitar '
        'abandonar la defensa de una sola vez.'
    )
    out = ns['_tgp_public_reason'](reason)
    assert 'Q4B' not in out
    assert 'Q1' not in out
    assert 'edge=' not in out
    assert 'Best TF=' not in out


def test_guardian_dedup_groups_same_btc_goal_across_sources():
    ns = _helpers()
    paxg = {
        'action': 'SWAP_PAXG_TO_BTC',
        'source_asset': 'PAXG',
        'target_asset': 'BTC',
        'portfolio_after': {'pct_btc': 0.216},
    }
    usdt = {
        'action': 'BUY_BTC',
        'source_asset': 'USDT',
        'target_asset': 'BTC',
        'portfolio_after': {'pct_btc': 0.208},
    }
    assert ns['_tgp_public_subject'](paxg, 'BALANCED', False) == ns['_tgp_public_subject'](usdt, 'BALANCED', False)


def test_guardian_shared_message_allocation_uses_percentages_not_amounts():
    ns = _helpers()
    result = {
        'target_asset': 'BTC',
        'portfolio_before': {'pct_btc': 0.182},
        'portfolio_after': {'pct_btc': 0.216},
        'amount_crypto': 0.00919344,
        'amount_usd': 40.04,
    }
    text = ' '.join(ns['_tgp_public_allocation_lines'](result))
    assert '18.2%' in text and '21.6%' in text
    assert '0.00919344' not in text
    assert '40.04' not in text
    assert '$' not in text
