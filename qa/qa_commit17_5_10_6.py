"""QA 17.5.10.6 — gate-aware recovery + Multi-Asset pre-execution routing.

Run from repository root:
    python qa/qa_commit17_5_10_6.py

This QA intentionally distinguishes static policy checks from local integration
contract tests. It does not claim a live-market backtest or a production deploy.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "execution_abi_175104.py"


def read(name):
    primary = ROOT / name
    if primary.exists():
        return primary.read_text(encoding="utf-8")
    support = ROOT / "UNCHANGED_17_5_10_5_SUPPORT" / name
    return support.read_text(encoding="utf-8")


def load_exec_module():
    spec = importlib.util.spec_from_file_location("exec175106_under_test", EXEC)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_compile_all_runtime_modules():
    for name in (
        "execution_abi_175104.py",
        "strategy_quality_extension_175105.py",
        "macro_backoff_175105.py",
    ):
        ast.parse(read(name), filename=name)


def test_no_signal_quota_or_threshold_relaxation():
    blob = read("execution_abi_175104.py") + read("strategy_quality_extension_175105.py")
    for bad in ("signal_quota", "minimum_signals", "force_signal", "target_signal_count"):
        assert bad not in blob.lower()
    for needle in (
        'floor = max(1.0, _f(levels.get("minimum_viable_rr"), 1.8))',
        '_f(candidate.get("geometry_quality")) < 62.0',
        '_f(candidate.get("entry_quality")) < 55.0',
        '_f(candidate.get("sl_quality")) < 60.0',
        '_f(candidate.get("tp_quality")) < 60.0',
    ):
        assert needle in blob


def test_recovery_only_for_existing_direction_and_existing_reasons():
    blob = read("execution_abi_175104.py")
    assert 'str(decision or "").upper() not in {"LONG", "SHORT"}' in blob
    assert 'reason.startswith("R/R desfavorable")' in blob
    assert 'reason.startswith("SL no defendible")' in blob



def test_contextual_rr_guard_replaces_legacy_global_150_floor():
    mod = load_exec_module()
    oi = types.ModuleType("operational_intelligence")

    seen = {}
    def legacy_guard(*, action, levels, setup_family, market, timeframe):
        seen["setup_family"] = setup_family
        rr = float((levels or {}).get("risk_reward") or 0)
        reasons = []
        if str(market).upper() == "FUTURES" and rr < 1.50:
            reasons.append(f"la relación riesgo/beneficio disponible es 1:{rr:.2f}")
        if reasons:
            return {"applied": True, "action": "PRECAUCION", "status": "SETUP_NOT_EXECUTABLE", "reasons": reasons, "original_action": action}
        return {"applied": False, "action": action, "status": "SETUP_EXECUTABLE", "reasons": []}

    oi.execution_setup_guard = legacy_guard
    sys.modules["operational_intelligence"] = oi
    assert mod._install_contextual_execution_setup_guard() is True

    # Multi-Energy style cell: 1.42 is valid against its contextual 1.40 floor.
    ok = oi.execution_setup_guard(
        action="SHORT", levels={"risk_reward": 1.42, "minimum_viable_rr": 1.40},
        setup_family="TREND_PULLBACK", market="FUTURES", timeframe="1h",
    )
    assert ok["applied"] is False
    assert ok["rr_floor"] == 1.4

    routed = oi.execution_setup_guard(
        action="SHORT",
        levels={"risk_reward": 1.60, "minimum_viable_rr": 1.40, "_execution_setup_family_175106": "BREAKOUT_RETEST"},
        setup_family="SWEEP_REVERSAL", market="FUTURES", timeframe="1h",
    )
    assert routed["applied"] is False
    assert seen["setup_family"] == "BREAKOUT_RETEST"

    # Same cell below its actual floor must still be rejected.
    bad = oi.execution_setup_guard(
        action="SHORT", levels={"risk_reward": 1.35, "minimum_viable_rr": 1.40},
        setup_family="TREND_PULLBACK", market="FUTURES", timeframe="1h",
    )
    assert bad["applied"] is True
    assert any("piso técnico 1:1.40" in r for r in bad["reasons"])

    # A stricter CORE-style cell is not relaxed: 1.52 fails a 1.55 contextual floor.
    strict = oi.execution_setup_guard(
        action="LONG", levels={"risk_reward": 1.52, "minimum_viable_rr": 1.55},
        setup_family="TREND_PULLBACK", market="FUTURES", timeframe="1h",
    )
    assert strict["applied"] is True
    assert any("piso técnico 1:1.55" in r for r in strict["reasons"])


def test_gate_aware_preflight_is_present():
    blob = read("execution_abi_175104.py")
    for needle in (
        "_futures_entry_timing_gate",
        "evaluate_entry_reaction",
        "execution_setup_guard",
        "_install_contextual_execution_setup_guard",
        "downstream_preflight_rejections",
    ):
        assert needle in blob


def test_recovered_entry_metadata_is_rebuilt():
    blob = read("execution_abi_175104.py")
    for needle in (
        '"entry_timing_mode": timing_mode',
        '"entry_reachability_score"',
        '"entry_defensibility_score"',
        '"entry_sweep_confirmed"',
        '"entry_mss_bos_confirmed"',
        '"recovery_metadata_rebuilt": True',
    ):
        assert needle in blob


def test_recovery_does_not_claim_publication_before_gates():
    blob = read("execution_abi_175104.py")
    assert '"publication_status": "RECOVERED_BASE_PENDING_GATES"' in blob
    assert '"publication_status": "EXECUTABLE_SIGNAL"' not in blob
    assert "BASE_GEOMETRY_ONLY_DOWNSTREAM_SAFETY_UNCHANGED" in blob


def test_multiasset_route_is_pre_execution_and_direction_neutral():
    blob = read("execution_abi_175104.py")
    assert "_multiasset_pre_execution_route" in blob
    assert 'playbook["setup_family"] = route["engine_family"]' in blob
    assert 'result["_execution_setup_family_175106"] = route["engine_family"]' in blob
    assert 'if "soporte" in source_l' in blob
    assert 'if "resistencia" in source_l' in blob
    assert '"creates_direction": False' in blob
    assert 'route = _multiasset_pre_execution_route(' in blob


def test_no_new_io_in_execution_patch():
    blob = read("execution_abi_175104.py")
    for forbidden in ("requests.get", "requests.post", "supabase", "threading.Thread", "groq", "openai"):
        assert forbidden not in blob.lower()


def _install_gate_stubs():
    geom = types.ModuleType("execution_geometry_committee")
    geom.build_profile = lambda **kwargs: {
        "near_max_atr": 0.55, "deep_min_atr": 0.85, "setup_family": kwargs.get("setup_family")
    }
    geom.entry_candidate_adjustment = lambda profile, **kwargs: {
        "timing_mode": "DEEP_PULLBACK_LIMIT" if float(kwargs.get("distance_atr") or 0) >= 0.85 else "NEAR_REACTION"
    }
    sys.modules["execution_geometry_committee"] = geom

    reaction = types.ModuleType("entry_reaction_engine")
    reaction.evaluate_entry_reaction = lambda levels, **kwargs: {
        "passed": bool(levels.get("recovery_metadata_rebuilt")), "status": "ENTRY_CONFIRMED"
    }
    sys.modules["entry_reaction_engine"] = reaction

    op = types.ModuleType("operational_intelligence")
    op.execution_setup_guard = lambda **kwargs: {
        "applied": False, "status": "SETUP_EXECUTABLE", "action": kwargs.get("action")
    }
    sys.modules["operational_intelligence"] = op


def test_dynamic_recovery_rejects_candidate_that_fails_next_gate():
    mod = load_exec_module()
    _install_gate_stubs()

    committee = types.ModuleType("execution_specialist_committees")
    committee.evaluate_sl_reaction_conflict = lambda **kwargs: {"conflict": False}

    bad = {
        "success": True, "entry": 99.0, "stop_loss": 98.0, "take_profit": 101.0,
        "risk_reward": 2.0, "geometry_quality": 80, "entry_quality": 80,
        "sl_quality": 80, "tp_quality": 80,
        "entry_committee": {"source": "Swing @ 99", "family": "swing", "specialist_scores": {"reachability": 80, "smc": 80}},
        "sl_committee": {"source": "Swing invalidation", "family": "structural_invalidation"},
        "tp_committee": {"source": "Liquidity", "family": "liquidity"},
    }
    good = {
        **bad, "entry": 98.0, "stop_loss": 97.0, "take_profit": 100.0,
        "entry_committee": {"source": "Swing @ 98", "family": "swing", "specialist_scores": {"reachability": 82, "smc": 82}},
    }

    def fake_recover(**kwargs):
        filt = kwargs["candidate_filter"]
        assert filt(bad) is False
        assert filt(good) is True
        return dict(good)

    committee.recover_execution_geometry_from_structure = fake_recover
    sys.modules["execution_specialist_committees"] = committee

    class Fake:
        def _market_label(self): return "FUTUROS"
        def _futures_entry_timing_gate(self, decision, trend, momentum, volatility, structure, levels):
            return {"passed": float(levels.get("entry") or 0) <= 98.0, "status": "OK"}
        def detect_market_regime(self, trend, momentum, volatility, structure):
            return {"regime": "RANGING"}

    out = mod._structural_recovery_candidate(
        Fake(), decision="LONG", trend={}, momentum={}, volatility={"atr": 2.0},
        structure={"current_price": 100.0, "sweep": True, "mss": True},
        symbol="BTC-USDT", timeframe="1h", liquidation=None,
        levels={"entry": 99.0, "minimum_viable_rr": 1.5, "maximum_technical_rr": 4.5},
    )
    assert out.get("success") is True
    assert out.get("entry") == 98.0
    assert int((out.get("downstream_preflight_rejections") or {}).get("ENTRY_TIMING") or 0) == 1


def test_dynamic_recovered_price_gets_new_timing_metadata():
    mod = load_exec_module()
    _install_gate_stubs()

    class Fake:
        def _market_label(self): return "FUTUROS"
        def detect_market_regime(self, *args): return {"regime": "RANGING"}
        def _round_price(self, value, symbol): return float(value)

    recovery = {
        "entry": 98.0, "stop_loss": 97.0, "take_profit": 100.0, "risk_reward": 2.0,
        "entry_quality": 80, "sl_quality": 82, "tp_quality": 85, "geometry_quality": 83,
        "entry_committee": {"source": "Swing @ 98", "family": "swing", "specialist_scores": {"reachability": 84, "smc": 79}},
        "sl_committee": {"source": "Swing invalidation", "family": "structural_invalidation"},
        "tp_committee": {"source": "Liquidity", "family": "liquidity"},
    }
    out = mod._apply_recovered_base_geometry(
        Fake(), {"entry_timing_mode": "NEAR_REACTION"}, recovery,
        decision="LONG", trend={}, momentum={}, structure={"current_price": 100.0},
        volatility={"atr": 2.0}, symbol="BTC-USDT", timeframe="1h",
    )
    assert out["entry"] == 98.0
    assert out["entry_timing_mode"] == "DEEP_PULLBACK_LIMIT"
    assert out["entry_reachability_score"] == 84.0
    assert out["publication_status"] == "RECOVERED_BASE_PENDING_GATES"
    assert out["recovery_metadata_rebuilt"] is True


def test_dynamic_multiasset_route_avoids_unconfirmed_sweep_family():
    mod = load_exec_module()
    ma = types.ModuleType("multiasset_system")
    ma.MULTIASSET_SYMBOLS = {"CL-USDT": {"asset_class": "ENERGY", "code": "CL"}}
    ma._strategy_context = lambda meta, tf, result: {
        "families": ["SWEEP_MSS_POI", "TREND_PULLBACK", "BREAKOUT_RETEST", "COMPRESSION_EXPANSION"],
        "preferred_for_context": ["TREND_PULLBACK", "SWEEP_MSS_POI", "BREAKOUT_RETEST"],
        "regime": "TRENDING", "volatility_regime": "NORMAL",
    }
    ma._route_strategy_family = lambda result, strategy, macro: {"selected_family": "SWEEP_MSS_POI"}
    sys.modules["multiasset_system"] = ma

    class Fake:
        def _market_label(self): return "MULTI-ACTIVO"

    route = mod._multiasset_pre_execution_route(
        Fake(), decision="SHORT", trend={"adx": 32}, momentum={}, volatility={"atr_pct": 1.4},
        structure={"current_price": 90.0}, symbol="CL-USDT", timeframe="1h",
    )
    assert route["engine_family"] == "TREND_PULLBACK"
    assert route["creates_direction"] is False


def test_existing_175105_scope_and_shadow_contract_still_present():
    blob = read("strategy_quality_extension_175105.py")
    assert "out_of_scope_specializations_removed" in blob
    assert '"authority": "SHADOW_ONLY"' in blob
    assert '"can_select_live_strategy": False' in blob
    assert "NOT_PROMOTED_DIRECTIONAL_ASYMMETRY_AND_N_TOO_SMALL" in blob


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
