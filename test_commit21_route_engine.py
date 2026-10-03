from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name("premium_path_expansion_20.py")
spec = importlib.util.spec_from_file_location("p21", MODULE)
p21 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p21)


def test_contract_unchanged():
    a = p21.audit()
    assert a["premium_thresholds"] == {
        "safety": 75.0,
        "tp": 55.0,
        "sl": 60.0,
        "rr_min": 1.8,
        "rr_max": 3.5,
    }
    assert a["adds_threads"] is False
    assert a["adds_network_calls"] is False
    assert a["promotes_fallback"] is False
    assert a["live_parameter_fitting"] is False


def test_candidate_is_contextual_and_bounded():
    calls = []

    def fake_select_strategy(action, regime, vol_state, groups, **kwargs):
        calls.append(kwargs.get("preferred_family"))
        family = kwargs.get("preferred_family")
        if family == "GOOD_ROUTE":
            return {
                "id": "FUT_LONG_GOOD",
                "family": "GOOD_ROUTE",
                "quality": 72.0,
                "regime_match": True,
                "volatility_match": True,
                "positive_functional_families": 4,
                "required_independent_families": 4,
            }
        return {
            "id": "FUT_LONG_BAD",
            "family": family,
            "quality": 40.0,
            "regime_match": True,
            "volatility_match": True,
            "positive_functional_families": 4,
            "required_independent_families": 4,
        }

    import sys
    original = sys.modules.get("default_strategy_bank")
    fake = type("M", (), {"select_strategy": staticmethod(fake_select_strategy)})
    sys.modules["default_strategy_bank"] = fake
    try:
        structure = {
            "_contingency_playbook": {
                "market": "FUTURES",
                "research_state": "UNAVAILABLE",
                "setup_family": "BASE",
                "context": {"regime": "TREND_UP", "volatility": "NORMAL"},
                "volatility": {"state": "NORMAL"},
                "indicator_groups": {},
                "strategy": {
                    "family": "BASE",
                    "alternatives": [
                        {"id": "FUT_LONG_GOOD", "family": "GOOD_ROUTE", "quality": 70.0},
                        {"id": "FUT_LONG_BAD", "family": "BAD_ROUTE", "quality": 40.0},
                    ],
                },
            }
        }
        got = p21._strategy_alternatives(structure=structure, decision="LONG", symbol="BTC-USDT", timeframe="1h")
        assert [x["family"] for x in got] == ["GOOD_ROUTE"]
        assert calls == ["GOOD_ROUTE", "BAD_ROUTE"]
    finally:
        if original is not None:
            sys.modules["default_strategy_bank"] = original
        else:
            sys.modules.pop("default_strategy_bank", None)


def test_no_route_on_negative_research():
    structure = {
        "_contingency_playbook": {
            "market": "FUTURES",
            "research_state": "NEGATIVE_OOS",
            "setup_family": "BASE",
            "strategy": {"alternatives": [{"family": "GOOD_ROUTE"}]},
        }
    }
    assert p21._strategy_alternatives(structure=structure, decision="LONG", symbol="BTC-USDT", timeframe="1h") == []


def test_premium_gate_passthrough():
    assert p21._premium_gate({"publication_eligible": True}) is True
    assert p21._premium_gate({"futures_signal_tier": "PREMIUM"}) is True
    assert p21._premium_gate({"futures_publication_gate": {"tier": "PREMIUM"}}) is True
    assert p21._premium_gate({"publication_eligible": False}) is False


if __name__ == "__main__":
    test_contract_unchanged()
    test_candidate_is_contextual_and_bounded()
    test_no_route_on_negative_research()
    test_premium_gate_passthrough()
    print("Commit 21 tests passed")


def test_installed_engine_can_promote_only_after_existing_gate():
    import sys, types

    class FakeAnalysis:
        def calculate_entry_levels(self, decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation=None):
            family = str(((structure.get("_contingency_playbook") or {}).get("setup_family")) or "BASE").upper()
            if family == "GOOD_ROUTE":
                return {
                    "publication_eligible": True,
                    "futures_signal_tier": "PREMIUM",
                    "levels": {"execution_safety": 82, "tp_touch_quality_score": 70, "sl_avoidance_quality_score": 70, "risk_reward": 2.1},
                    "futures_publication_gate": {"eligible": True, "tier": "PREMIUM", "reason_codes": []},
                }
            return {
                "publication_eligible": False,
                "futures_signal_tier": "ANALYSIS_ONLY",
                "levels": {"execution_safety": 72, "tp_touch_quality_score": 60, "sl_avoidance_quality_score": 58, "risk_reward": 2.1},
                "futures_publication_gate": {"eligible": False, "tier": "ANALYSIS_ONLY", "reason_codes": ["SAFETY", "SL_QUALITY"]},
            }

    fake_fs = types.SimpleNamespace(FuturesAnalysis=FakeAnalysis)
    old_fs = sys.modules.get("futures_system")
    sys.modules["futures_system"] = fake_fs
    try:
        status = p21.install_strategy_route_engine()
        assert status["installed"] is True
        obj = FakeAnalysis()
        structure = {
            "_contingency_playbook": {
                "market": "FUTURES", "research_state": "UNAVAILABLE", "setup_family": "BASE",
                "context": {"regime": "TREND_UP", "volatility": "NORMAL"},
                "volatility": {"state": "NORMAL"},
                "indicator_groups": {},
                "strategy": {"id": "BASE", "family": "BASE", "alternatives": [{"id": "FUT_LONG_GOOD", "family": "GOOD_ROUTE", "quality": 70}]},
            }
        }
        # Make select_strategy return the eligible route.
        fake_bank = types.SimpleNamespace(select_strategy=lambda action, regime, vol_state, groups, **kwargs: {
            "id": "FUT_LONG_GOOD", "family": kwargs.get("preferred_family"), "quality": 70,
            "regime_match": True, "volatility_match": True, "positive_functional_families": 4, "required_independent_families": 4,
        })
        old_bank = sys.modules.get("default_strategy_bank")
        sys.modules["default_strategy_bank"] = fake_bank
        try:
            result = obj.calculate_entry_levels("LONG", {}, {}, {}, structure, "BTC-USDT", "1h")
        finally:
            if old_bank is not None:
                sys.modules["default_strategy_bank"] = old_bank
            else:
                sys.modules.pop("default_strategy_bank", None)
        assert result.get("premium_route_promoted") is True
        assert result.get("publication_eligible") is True
    finally:
        if old_fs is not None:
            sys.modules["futures_system"] = old_fs
        else:
            sys.modules.pop("futures_system", None)

