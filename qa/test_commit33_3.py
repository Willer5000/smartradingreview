from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module_with_stub(evidence):
    base = types.ModuleType("pipeline_integrity_175102")
    base.VERSION = "BASE_TEST"
    base.PIPELINE_GENERATION = "BASE"
    base.RELEASED_AT_UTC = "2026-01-01T00:00:00+00:00"
    base._live_evidence = lambda layers, operational, direction: dict(evidence.get(direction, {}))
    base._select_default_strategy = lambda *a, **k: {
        "id": "TEST", "family": k.get("preferred_family"), "quality": 82.0,
        "regime_match": True, "volatility_match": True,
    }
    base._official_cell = lambda *a, **k: True
    base._is_multiasset = lambda symbol: False
    base._multiasset_strategy_from_live_layers = lambda *a, **k: {"quality": 82.0}
    base.reconcile_operational_candidate = lambda operational, **kwargs: dict(operational or {})
    base.profitability_hard_block_authority = lambda route: {"allowed": False, "reason": "TEST"}
    base.stamp_pipeline_generation = lambda result: dict(result)
    sys.modules["pipeline_integrity_175102"] = base

    name = "pipeline_integrity_175103_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "pipeline_integrity_175103.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def neutral_ev(**overrides):
    base = {
        "trend": False, "mtf": False, "mtf_conflict": False, "mtf_opposite": False,
        "momentum": False, "volume": False, "structure": False, "sweep": False,
        "mss": False, "poi": False, "pullback": False, "breakout": False,
        "breakout_retest": False, "displacement": False, "squeeze": False,
        "expansion": False, "range": False, "extreme": False,
        "mean_reversion_location": False, "direction_anchor": False,
        "dmi_impulse": False, "volume_ratio": 1.0, "adx": 20, "rsi": 50,
        "trend_direction": "NEUTRAL", "structure_direction": "NEUTRAL",
        "mtf_direction": "NEUTRAL",
    }
    base.update(overrides)
    return base


def test_files_and_boot_contract():
    proc = (ROOT / "Procfile").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert "gunicorn app:app" in proc
    assert "gunicorn app:app" in render
    assert "commit32_2_main_entrypoint:app" not in render
    assert "COMMIT32_2_RECOVERY_ENABLED" not in render
    assert 'MEMORY_JOB_START_LIMIT_MB\n        value: "255"' in render
    assert 'LOW_MEMORY_MODE\n        value: "1"' in render
    assert "15m" not in render



def test_retired_runtime_patches_are_noop():
    for filename in (
        "commit32_runtime_patch.py", "commit32_1_runtime_patch.py",
        "commit32_2_runtime_patch.py",
    ):
        path = ROOT / filename
        spec = importlib.util.spec_from_file_location("retired_" + filename.replace(".", "_"), path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        out = mod.install(object())
        assert out["installed"] is False
        assert out["retired"] is True

def test_historical_entrypoints_are_inert():
    for name in (
        "commit31_main_entrypoint.py", "commit32_main_entrypoint.py",
        "commit32_1_main_entrypoint.py", "commit32_2_main_entrypoint.py",
    ):
        text = (ROOT / name).read_text()
        assert "from app import app" in text
        assert "runtime_patch import" not in text
        assert "install(" not in text


def test_legacy_overlay_cannot_change_trading_or_memory():
    path = ROOT / "premium_path_expansion_20.py"
    text = path.read_text()
    spec = importlib.util.spec_from_file_location("premium_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    a = mod.audit()
    assert a["memory_policy_mutation"] is False
    assert a["trading_authority"] is False
    assert a["publication_authority"] is False
    assert a["safety_authority"] is False
    assert "COMMIT33_3_OHLC_ONLY_VISUAL_LANE" in text
    assert "COMMIT33_3_PUBLICATION_AUDIT_V1" in text


def test_impulse_can_reach_geometry_without_mtf_veto():
    evidence = {
        "BULLISH": neutral_ev(
            dmi_impulse=True, direction_anchor=True, momentum=True,
            structure=True, displacement=True, mtf_opposite=True,
            volume_ratio=1.3,
        ),
        "BEARISH": neutral_ev(),
    }
    mod = load_module_with_stub(evidence)
    op = {
        "candidate_ready": False,
        "thesis": {"direction": "BULLISH", "action": "LONG", "risk_class": "HIGH"},
        "multi_timeframe": {"conflict": False},
        "official_cell": True,
    }
    out = mod.reconcile_operational_candidate(
        op, layers={"macro_context": {}}, symbol="BTC-USDT", timeframe="30m", system_type="FUTURES"
    )
    assert out["candidate_ready"] is True
    assert out["candidate_action"] == "LONG"
    assert out["commit33_3_recovered"] is True
    assert out["never_bypass_safety"] is True
    assert out["never_bypass_execution_committees"] is True


def test_sweep_reversal_needs_real_independent_confirmation():
    evidence = {
        "BULLISH": neutral_ev(sweep=True, structure=True, momentum=True, poi=True),
        "BEARISH": neutral_ev(),
    }
    mod = load_module_with_stub(evidence)
    diag = mod.particular_setup_diagnostic(
        {}, layers={}, symbol="BTC-USDT", timeframe="30m", system_type="FUTURES"
    )
    assert diag["winner"] is not None
    assert diag["winner"]["setup"] == "SWEEP_REVERSAL"


def test_trend_pullback_keeps_strict_mtf():
    evidence = {
        "BULLISH": neutral_ev(
            trend=True, mtf=True, pullback=True, momentum=True,
            mtf_conflict=True, mtf_opposite=True,
        ),
        "BEARISH": neutral_ev(),
    }
    mod = load_module_with_stub(evidence)
    diag = mod.particular_setup_diagnostic(
        {}, layers={}, symbol="BTC-USDT", timeframe="30m", system_type="FUTURES"
    )
    contracts = diag["long"]["contracts"]
    trend = next(c for c in contracts if c["setup"] == "TREND_PULLBACK")
    assert trend["passed"] is False
    assert trend["mtf_policy"] == "STRICT"


def test_minimum_timeframe_contract_is_30m():
    text = (ROOT / "pipeline_integrity_175103.py").read_text()
    assert '"minimum_operational_timeframe": "30m"' in text
    assert "15m" not in text



def test_futures_tempo_is_native_and_minimum_tf_is_30m():
    spec = importlib.util.spec_from_file_location("fu33", ROOT / "futures_universe.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.universe_audit()["ok"] is True
    assert all("15m" not in rows for rows in mod.RISK_CLASS_TIMEFRAMES.values())
    assert min(float(v["entry_zone_pct"]) for v in mod.EXIT_PROFILES.values()) == 0.05
    assert mod.EXIT_PROFILES["CORE1"]["entry_zone_pct"] == 0.12
    assert mod.EXIT_PROFILES["MEDIUM"]["max_entry_wait_bars"] == 2
    assert mod.EXIT_PROFILES["HIGH"]["max_entry_wait_bars"] == 1


def test_spot_market_authority_is_static_not_wsgi_patch():
    evidence = {"BULLISH": neutral_ev(), "BEARISH": neutral_ev()}
    mod = load_module_with_stub(evidence)
    spot = types.ModuleType("commit32_spot_market_authority")
    spot.SUPPORTED_SYMBOLS = {"BTC-USDT", "PAXG-USDT", "PAXG-BTC"}
    def apply(original, pipeline_module, operational, **kwargs):
        out = original(operational, **kwargs)
        out["spot_static_authority_called"] = True
        out["guardian_untouched"] = True
        return out
    spot.apply_market_signal_to_pipeline = apply
    sys.modules["commit32_spot_market_authority"] = spot
    out = mod.reconcile_operational_candidate(
        {"candidate_ready": False, "thesis": {}},
        layers={}, symbol="BTC-USDT", timeframe="4h", system_type="SPOT"
    )
    assert out["spot_static_authority_called"] is True
    assert out["guardian_untouched"] is True


def test_research_backtester_is_30m_only_and_not_live_authority():
    strat = (ROOT / "strategies_commit33_3.py").read_text()
    bt = (ROOT / "backtest_commit33_3.py").read_text()
    status = (ROOT / "BACKTEST_COMMIT33_3_STATUS.json").read_text()
    assert "30m research strategies" in strat
    assert "15m" not in strat
    assert "COMMIT33_3_BACKTEST_30M_V2" in bt
    assert '"real_market_backtest_executed": false' in status
    assert '"production_authority_granted": false' in status

def test_committees_and_safety_are_not_replaced_by_package():
    names = {p.name for p in ROOT.iterdir() if p.is_file()}
    assert "execution_specialist_committees.py" not in names
    assert "safety_profiles_commit31.py" not in names
    assert "futures_system.py" not in names
    assert "multiasset_system.py" not in names
    assert "portfolio_guardian.py" not in names


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for test in tests:
        try:
            test()
            print("PASS", test.__name__)
        except Exception as exc:
            failed.append((test.__name__, exc))
            print("FAIL", test.__name__, repr(exc))
    print(f"RESULT {len(tests)-len(failed)}/{len(tests)} PASS")
    if failed:
        raise SystemExit(1)
