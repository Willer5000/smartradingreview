"""QA 17.5.10.5.
Run: python qa/qa_commit17_5_10_5.py
"""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(name):
    return (ROOT / name).read_text(encoding="utf-8")

def test_compile():
    for name in (
        "execution_abi_175104.py",
        "strategy_quality_extension_175105.py",
        "macro_backoff_175105.py",
    ):
        ast.parse(read(name), filename=name)

def test_no_signal_quota():
    blob = read("execution_abi_175104.py") + read("strategy_quality_extension_175105.py")
    bad = ["max_signals", "signal_quota", "minimum_signals", "force_signal"]
    assert all(x not in blob.lower() for x in bad)

def test_recovery_only_existing_direction():
    blob = read("execution_abi_175104.py")
    assert 'str(decision or "").upper() not in {"LONG", "SHORT"}' in blob
    assert "R/R desfavorable" in blob
    assert "SL no defendible" in blob
    assert "recover_execution_geometry_from_structure" in blob

def test_quality_unchanged():
    blob = read("execution_abi_175104.py")
    for needle in (
        'floor = max(1.0, _f(levels.get("minimum_viable_rr"), 1.8))',
        '_f(candidate.get("geometry_quality")) < 62.0',
        '_f(candidate.get("entry_quality")) < 55.0',
        '_f(candidate.get("sl_quality")) < 60.0',
        '_f(candidate.get("tp_quality")) < 60.0',
    ):
        assert needle in blob

def test_downstream_safety_preserved():
    blob = read("execution_abi_175104.py")
    assert "BASE_GEOMETRY_ONLY_DOWNSTREAM_SAFETY_UNCHANGED" in blob
    assert "base_cls.calculate_entry_levels = _base_wrapped" in blob

def test_temporal_scope_enforced():
    blob = read("strategy_quality_extension_175105.py")
    assert "out_of_scope_specializations_removed" in blob
    assert "family_tf" in blob and "allowed" in blob

def test_continuation_shadow_only():
    blob = read("strategy_quality_extension_175105.py")
    assert '"authority": "SHADOW_ONLY"' in blob
    assert '"can_select_live_strategy": False' in blob
    assert "NOT_PROMOTED_DIRECTIONAL_ASYMMETRY_AND_N_TOO_SMALL" in blob

def test_backtest_embedded():
    blob = read("strategy_quality_extension_175105.py")
    assert '"expectancy_r": 0.0655' in blob
    assert '"expectancy_r": 1.4797' in blob
    assert '"profit_factor": 6.294' in blob

def test_macro_no_extra_requests():
    blob = read("macro_backoff_175105.py")
    assert "original(*args, **kwargs)" in blob
    assert "requests.get" not in blob
    assert "threading.Thread" not in blob

def main():
    tests = [v for k,v in globals().items() if k.startswith("test_") and callable(v)]
    failures = []
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:
            failures.append((fn.__name__, repr(exc)))
            print("FAIL", fn.__name__, repr(exc))
    print(f"{len(tests)-len(failures)}/{len(tests)} PASS")
    if failures:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
