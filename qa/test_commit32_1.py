from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commit32_1_candidate_recovery import _score_contract, recover_candidate, VERSION as RECOVERY_VERSION
from commit32_1_research_registry import snapshot, assert_no_live_authority


def test_research_registry_shadow_only():
    data = snapshot()
    assert data["authority"] == "RESEARCH_ONLY"
    assert assert_no_live_authority()
    assert "CRT_LIQUIDITY_RANGE_RECLAIM" in data["strategies"]
    assert "TRIPLE_RSI_MOMENTUM_TIMING" in data["strategies"]
    assert all(not x["production_authority"] for x in data["strategies"].values())


def test_directional_impulse_mtf_is_context_not_universal_veto():
    spec = {
        "setup":"DIRECTIONAL_IMPULSE_CONTINUATION", "preferred_family":"BREAKOUT_RETEST",
        "mandatory":("dmi_impulse",), "alternatives":(("direction_anchor","momentum"),),
        "support":("structure","volume","displacement","breakout","mtf"), "min_support":1, "mtf_mode":"CONTEXT"
    }
    ev = {"dmi_impulse":True, "momentum":True, "structure":True, "volume":True,
          "mtf_conflict":True, "mtf_opposite":False, "mtf":False, "volume_ratio":1.3}
    out = _score_contract(ev, spec)
    assert out["passed"] is True  # conflict requires the second support, which exists


def test_trend_pullback_keeps_strict_mtf():
    spec = {
        "setup":"TREND_PULLBACK", "preferred_family":"TREND_PULLBACK",
        "mandatory":("trend","pullback","mtf"), "alternatives":(),
        "support":("momentum","volume","poi","structure"), "min_support":1, "mtf_mode":"STRICT"
    }
    ev = {"trend":True, "pullback":True, "mtf":True, "momentum":True,
          "mtf_conflict":True, "mtf_opposite":False, "volume_ratio":1.0}
    assert _score_contract(ev, spec)["passed"] is False


class FakeImpl:
    def _is_multiasset(self, symbol):
        return str(symbol).startswith("CL-")
    def _action(self, direction, market):
        return "LONG" if direction == "BULLISH" else "SHORT"
    def _official_cell(self, market, symbol, timeframe, action, fallback=False):
        return True
    def _select_default_strategy(self, *args, **kwargs):
        return {"id":"TEST", "family":kwargs.get("preferred_family"), "quality":82.0,
                "regime_match":True, "volatility_match":True}
    def _live_evidence(self, layers, operational, direction):
        if direction == "BULLISH":
            return {
                "dmi_impulse":True, "direction_anchor":True, "momentum":True,
                "structure":True, "volume":True, "displacement":True, "breakout":False,
                "mtf":False, "mtf_conflict":False, "mtf_opposite":False,
                "sweep":False, "mss":False, "poi":True, "pullback":False,
                "breakout_retest":False, "squeeze":False, "expansion":True,
                "range":False, "extreme":False, "mean_reversion_location":False,
                "volume_ratio":1.3, "adx":24, "rsi":57,
                "trend_direction":"BULLISH", "structure_direction":"BULLISH", "mtf_direction":"NEUTRAL",
            }
        return {
            "dmi_impulse":False, "direction_anchor":False, "momentum":False,
            "structure":False, "volume":False, "displacement":False, "breakout":False,
            "mtf":False, "mtf_conflict":False, "mtf_opposite":False,
            "sweep":False, "mss":False, "poi":False, "pullback":False,
            "breakout_retest":False, "squeeze":False, "expansion":False,
            "range":False, "extreme":False, "mean_reversion_location":False,
            "volume_ratio":1.0, "adx":24, "rsi":50,
            "trend_direction":"NEUTRAL", "structure_direction":"NEUTRAL", "mtf_direction":"NEUTRAL",
        }


def test_recovery_creates_candidate_but_never_bypasses_safety_route():
    impl = FakeImpl()
    op = {"candidate_ready":False, "official_cell":True, "risk_class":"HIGH", "thesis":{"macro_risk":"LOW"}}
    out = recover_candidate(impl, op, layers={"macro_context":{"risk_level":"LOW"}}, symbol="BTC-USDT", timeframe="30m", system_type="FUTURES")
    assert out["candidate_ready"] is True
    assert out["candidate_source"] == "COMMIT32_1_GRADED_SETUP+STRATEGY"
    assert out["never_bypass_safety"] is True
    assert out["requires_validated_live_route"] is True
    assert out["no_signal_quota"] is True
    assert out["commit32_1_candidate_quality"] >= 82


def test_high_risk_does_not_need_a_higher_pre_candidate_floor_than_core():
    impl = FakeImpl()
    for risk in ("CORE1", "MEDIUM", "HIGH"):
        op = {"candidate_ready":False, "official_cell":True, "risk_class":risk, "thesis":{"macro_risk":"LOW"}}
        out = recover_candidate(impl, op, layers={"macro_context":{"risk_level":"LOW"}}, symbol="BTC-USDT", timeframe="30m", system_type="FUTURES")
        assert out.get("candidate_ready") is True
        assert out["thesis"]["commit32_1_graded_contract"]["candidate_floor"] == 82.0


def test_multi_keeps_slightly_higher_candidate_floor():
    impl = FakeImpl()
    op = {"candidate_ready":False, "official_cell":True, "risk_class":"MULTI", "thesis":{"macro_risk":"LOW"}}
    out = recover_candidate(impl, op, layers={"macro_context":{"risk_level":"LOW"}}, symbol="CL-USDT", timeframe="1h", system_type="FUTURES")
    assert out.get("candidate_ready") is True
    assert out["thesis"]["commit32_1_graded_contract"]["candidate_floor"] == 84.0


def test_procfile_and_render_authority():
    assert "commit32_1_main_entrypoint:app" in (ROOT / "Procfile").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert "commit32_1_main_entrypoint:app" in render
    assert 'key: COMMIT32_1_RECOVERY_ENABLED' in render
    assert 'key: MEMORY_JOB_START_LIMIT_MB\n        value: "240"' in render
    assert 'key: MEMORY_HARD_LIMIT_MB\n        value: "350"' in render


def test_entrypoint_guards_multi_and_futures_abi_textually():
    text = (ROOT / "commit32_1_main_entrypoint.py").read_text()
    assert "Multi class ABI missing execution_observations" in text
    assert "Multi singleton ABI missing execution_observations" in text
    assert "Futures ABI missing execution_observations" in text


def test_runtime_patch_contains_independent_visual_lane_and_actual_geometry_guard():
    text = (ROOT / "commit32_1_runtime_patch.py").read_text()
    assert "COMMIT32_1_OHLC_ONLY_VISUAL_LANE" in text
    assert "fs_cls.calculate_entry_levels = fs_wrapped" in text
    assert "multi_cls.calculate_entry_levels = multi_wrapped" in text
    assert "candidate_second_chance_recovered" in text


def test_no_patch_modifies_guardian():
    for name in ("commit32_1_runtime_patch.py", "commit32_1_candidate_recovery.py", "commit32_1_research_registry.py"):
        text = (ROOT / name).read_text().lower()
        assert "portfolio_guardian.py" not in text

