from pathlib import Path
import ast, types, numpy as np

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app.py'
SRC = APP.read_text(encoding='utf-8')


def load_geometry_helper():
    tree = ast.parse(SRC)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == '_signal_execution_geometry_status'
    )
    module = ast.Module(body=[node], type_ignores=[])
    code = compile(module, str(APP), 'exec')
    ns = {'np': np}
    exec(code, ns)
    return ns['_signal_execution_geometry_status']


def test_missing_levels_blocked(fn):
    out = fn('spot', {'decision':'VENTA_SPOT','entry':None,'stop_loss':None,'take_profit':None})
    assert out['ok'] is False and out['reason']=='MISSING_EXECUTION_LEVELS', out


def test_spot_short_geometry_accepted(fn):
    out = fn('spot', {
        'decision':'VENTA_SPOT','entry':100,'stop_loss':103,'take_profit':94,
        'is_rejected':False,'is_executable':True,'publication_status':'EXECUTABLE_SIGNAL'
    })
    assert out['ok'] is True and abs(out['risk_reward']-2.0) < 1e-9, out


def test_spot_long_geometry_accepted(fn):
    out = fn('spot', {
        'decision':'COMPRA_SPOT','entry':100,'stop_loss':96,'take_profit':108,
        'is_rejected':False,'is_executable':True,'publication_status':'EXECUTABLE_SIGNAL'
    })
    assert out['ok'] is True and abs(out['risk_reward']-2.0) < 1e-9, out


def test_invalid_geometry_blocked(fn):
    out = fn('spot', {'decision':'VENTA_SPOT','entry':100,'stop_loss':97,'take_profit':105})
    assert out['ok'] is False and out['reason']=='INVALID_EXECUTION_GEOMETRY', out


def test_rejected_blocked(fn):
    out = fn('spot', {
        'decision':'VENTA_SPOT','entry':100,'stop_loss':103,'take_profit':94,
        'is_rejected':True
    })
    assert out['ok'] is False and out['reason']=='LEVELS_REJECTED', out


def test_analysis_only_blocked(fn):
    out = fn('futures', {
        'decision':'SHORT','entry':100,'stop_loss':103,'take_profit':94,
        'publication_status':'ANALYSIS_ONLY'
    })
    assert out['ok'] is False and out['reason']=='PUBLICATION_NOT_EXECUTABLE', out


def test_source_contracts_present():
    assert 'SPOT_RECOVERY_NOT_ENABLED' not in SRC
    assert "_recovery_market_type = 'futures' if is_futures else 'spot'" in SRC
    assert "market=('FUTURES' if is_futures else 'SPOT')" in SRC
    assert "_geometry = _signal_execution_geometry_status(market, signal)" in SRC
    assert "no se publica como CONFIRMADA" in SRC
    assert "publication_status': 'ANALYSIS_ONLY'" in SRC


def main():
    fn = load_geometry_helper()
    tests = [
        lambda: test_missing_levels_blocked(fn),
        lambda: test_spot_short_geometry_accepted(fn),
        lambda: test_spot_long_geometry_accepted(fn),
        lambda: test_invalid_geometry_blocked(fn),
        lambda: test_rejected_blocked(fn),
        lambda: test_analysis_only_blocked(fn),
        test_source_contracts_present,
    ]
    for i, test in enumerate(tests,1):
        test()
        print(f'PASS {i}: {getattr(test,"__name__", "geometry_case")}')
    print(f'\n{len(tests)}/{len(tests)} PASS')


if __name__ == '__main__':
    main()
