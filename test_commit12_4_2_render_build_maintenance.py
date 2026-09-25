from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = (ROOT / 'build.sh').read_text(encoding='utf-8')


def test_build_keeps_existing_dependency_contract():
    assert 'requirements.txt' in BUILD
    assert 'pip install' in BUILD
    assert '--no-cache-dir' in BUILD
    assert '--no-compile' in BUILD


def test_build_does_not_change_runtime_or_trading_code():
    forbidden = (
        'app.py =',
        'futures_system.py =',
        'saved_signals.py =',
        'minimum_execution_safety',
        'leverage',
        'take_profit',
        'stop_loss',
        'entry =',
    )
    for token in forbidden:
        assert token not in BUILD


def test_build_removes_stale_repository_bytecode():
    assert "-name '__pycache__'" in BUILD
    assert "-name '*.pyc'" in BUILD
    assert "-name '*.pyo'" in BUILD


def test_build_precompiles_only_flask_entrypoint():
    assert 'python -m py_compile app.py' in BUILD
    assert 'compileall' not in BUILD


def test_build_is_fail_fast():
    assert 'set -euo pipefail' in BUILD
