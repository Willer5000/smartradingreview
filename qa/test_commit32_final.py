from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commit32_spot_market_authority import (
    VERSION as SPOT_VERSION,
    evaluate_spot_market_signal,
    normalize_divergences,
    apply_market_signal_to_pipeline,
)
from commit32_execution_policy import TEMPO_OVERRIDES, MULTIASSET_TEMPO, annotate_multiasset_result
from commit32_runtime_patch import _CompactStructureDict, PUBLICATION_POLICY_VERSION, _ram_checkpoint


def bullish_layers():
    return {
        "trend": {"direction": "BULLISH", "confidence": 82, "adx": 26},
        "momentum": {"direction": "BULLISH", "confidence": 78, "divergences": ["rsi_bull_divergence"]},
        "volume": {"accumulation_score": 3, "obv_trend": "BULLISH"},
        "structure": {
            "current_price": 100.0, "nearest_support": 99.0, "nearest_resistance": 108.0,
            "pivot_lows": [{"price": 98.8}, {"price": 99.1}, {"price": 99.0}],
            "patterns": ["double_bottom"],
        },
        "macro_context": {"risk_level": "LOW"},
        "ratio_analysis": {"direction": "BEARISH", "confidence": 70},
    }


def bearish_exhaustion_layers():
    return {
        "trend": {"direction": "BULLISH", "confidence": 55, "adx": 20},
        "momentum": {"direction": "BEARISH", "confidence": 80, "divergences": ["rsi_bear_divergence"]},
        "volume": {"distribution_score": 3, "obv_trend": "BEARISH"},
        "structure": {
            "current_price": 85.15, "nearest_resistance": 87.0, "nearest_support": 82.2,
            "pivot_highs": [{"price": 86.9}, {"price": 87.1}, {"price": 87.0}],
            "patterns": ["double_top"],
        },
        "macro_context": {"risk_level": "HIGH"},
        "ratio_analysis": {"direction": "BULLISH", "confidence": 75},
    }


def test_divergence_aliases():
    a = normalize_divergences({"divergences": ["rsi_bear_divergence"]})
    b = normalize_divergences({"divergences": ["rsi_divergence_bear"]})
    assert a["regular_bearish"] and b["regular_bearish"]


def test_btc_exhaustion_is_not_buy():
    x = evaluate_spot_market_signal(symbol="BTC-USDT", timeframe="4h", layers=bearish_exhaustion_layers())
    assert x["action"] == "VENTA_SPOT", x
    assert x["ready"] and x["family_count"] >= 3


def test_btc_bullish_accumulation_is_buy():
    x = evaluate_spot_market_signal(symbol="BTC-USDT", timeframe="4h", layers=bullish_layers())
    assert x["action"] == "COMPRA_SPOT", x


def test_spot_is_portfolio_independent():
    x = evaluate_spot_market_signal(symbol="BTC-USDT", timeframe="4h", layers=bullish_layers())
    assert x["portfolio_independent"] is True
    assert x["reads_user_holdings"] is False
    assert x["guardian_authority"] == "UNCHANGED_DOWNSTREAM_PER_USER"


def test_paxgbtc_rotation_semantics_buy():
    layers = bullish_layers()
    layers["ratio_analysis"] = {"direction": "BULLISH", "confidence": 95}
    layers["macro_context"] = {"risk_level": "HIGH"}
    x = evaluate_spot_market_signal(symbol="PAXG-BTC", timeframe="4h", layers=layers)
    if x["ready"]:
        assert x["market_rotation_signal"] == "ROTACION_BTC_A_PAXG"


def test_paxgbtc_rotation_semantics_sell():
    layers = bearish_exhaustion_layers()
    layers["ratio_analysis"] = {"direction": "BEARISH", "confidence": 95}
    layers["macro_context"] = {"risk_level": "LOW"}
    x = evaluate_spot_market_signal(symbol="PAXG-BTC", timeframe="4h", layers=layers)
    if x["ready"]:
        assert x["market_rotation_signal"] == "ROTACION_PAXG_A_BTC"


def test_market_score_not_probability():
    x = evaluate_spot_market_signal(symbol="BTC-USDT", timeframe="4h", layers=bullish_layers())
    assert "NOT_CALIBRATED" in x["score_semantics"]


def test_pipeline_can_flip_only_through_existing_strategy_gate():
    def original(op, *, layers, symbol, timeframe, system_type):
        out = dict(op)
        out.update({"candidate_ready": True, "candidate_action": "COMPRA_SPOT", "official_cell": True, "multi_timeframe": {"conflict": False}})
        return out
    fake = SimpleNamespace(
        _select_default_strategy=lambda *a, **k: {"quality": 80, "regime_match": True, "volatility_match": True},
        _official_cell=lambda *a, **k: True,
    )
    out = apply_market_signal_to_pipeline(original, fake, {"thesis": {}}, layers=bearish_exhaustion_layers(), symbol="BTC-USDT", timeframe="4h", system_type="SPOT")
    assert out["candidate_action"] == "VENTA_SPOT", out
    assert out["never_bypass_safety"] is True


def test_pipeline_does_not_force_when_strategy_fails():
    def original(op, *, layers, symbol, timeframe, system_type):
        return {"candidate_ready": True, "candidate_action": "COMPRA_SPOT", "official_cell": True, "multi_timeframe": {"conflict": False}, "thesis": {}}
    fake = SimpleNamespace(
        _select_default_strategy=lambda *a, **k: {"quality": 50, "regime_match": True, "volatility_match": True},
        _official_cell=lambda *a, **k: True,
    )
    out = apply_market_signal_to_pipeline(original, fake, {}, layers=bearish_exhaustion_layers(), symbol="BTC-USDT", timeframe="4h", system_type="SPOT")
    assert out["candidate_action"] != "VENTA_SPOT"
    assert not out["candidate_ready"] or out.get("candidate_action") == "NO_OPERAR"


def test_futures_unchanged_by_spot_wrapper():
    calls = []
    def original(op, *, layers, symbol, timeframe, system_type):
        calls.append(system_type); return {"ok": True}
    fake = SimpleNamespace()
    out = apply_market_signal_to_pipeline(original, fake, {}, layers={}, symbol="BTC-USDT", timeframe="1h", system_type="FUTURES")
    assert out == {"ok": True} and calls == ["FUTURES"]


def test_structure_df_is_compacted():
    d = _CompactStructureDict()
    d["df"] = {"time": list(range(500)), "open": list(range(500)), "high": list(range(500)), "low": list(range(500)), "close": list(range(500)), "volume": list(range(500))}
    assert len(d["df"]["time"]) == 500
    assert set(d["df"].keys()) == {"time", "_commit32_compacted"}


def test_futures_tempo_ordering():
    assert TEMPO_OVERRIDES["HIGH"]["max_entry_wait_bars"] < TEMPO_OVERRIDES["MEDIUM"]["max_entry_wait_bars"] < TEMPO_OVERRIDES["CORE1"]["max_entry_wait_bars"]
    assert TEMPO_OVERRIDES["HIGH"]["entry_zone_pct"] < TEMPO_OVERRIDES["MEDIUM"]["entry_zone_pct"] < TEMPO_OVERRIDES["CORE1"]["entry_zone_pct"]


def test_multi_tempo_does_not_move_levels():
    r = {"levels": {"entry": 100, "sl": 98, "tp": 104, "entry_zone_pct": 0.2, "max_entry_wait_bars": 5}}
    out = annotate_multiasset_result(r, "1h")
    assert out["levels"]["entry"] == 100 and out["levels"]["sl"] == 98 and out["levels"]["tp"] == 104
    assert out["levels"]["entry_zone_pct"] <= 0.08 and out["levels"]["max_entry_wait_bars"] == 1


def test_publication_policy_is_new_generation():
    assert PUBLICATION_POLICY_VERSION == "COMMIT32_PUBLICATION_AUDIT_V2"
    assert "30_1" not in PUBLICATION_POLICY_VERSION


def test_runtime_does_not_patch_legacy_vote():
    text = (ROOT / "commit32_runtime_patch.py").read_text(encoding="utf-8")
    assert "_install_spot_authority" not in text
    assert "pipeline_integrity_175101" in text
    assert "reconcile_operational_candidate" in text


def test_guardian_not_in_package():
    assert not (ROOT / "portfolio_guardian.py").exists()


def test_render_ram_limits_and_heatmap():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert 'COMMIT32_RAM_ABORT_MB' in text and 'value: "285"' in text
    assert 'LIQUIDATION_HEATMAP_MAX_RESIDENT' in text



def test_ram_checkpoint_sheds_before_abort():
    state = {"rss": 260.0, "shed": 0}
    class Fake:
        @staticmethod
        def _process_rss_mb(): return state["rss"]
        @staticmethod
        def _shed_recreatable_memory(reason="", aggressive=False):
            state["shed"] += 1; state["rss"] = 220.0; return {}
    out = _ram_checkpoint(Fake, "unit")
    assert state["shed"] == 1 and out == 220.0


def test_ram_checkpoint_aborts_persistent_pressure():
    class Fake:
        @staticmethod
        def _process_rss_mb(): return 300.0
        @staticmethod
        def _shed_recreatable_memory(reason="", aggressive=False): return {}
    try:
        _ram_checkpoint(Fake, "unit_abort")
    except RuntimeError as exc:
        assert "RESOURCE_PRESSURE_ABORT_COMMIT32" in str(exc)
    else:
        raise AssertionError("persistent high RSS must abort")

def test_entrypoint_is_commit32():
    assert "commit32_main_entrypoint:app" in (ROOT / "Procfile").read_text(encoding="utf-8")
    assert "commit32_main_entrypoint:app" in (ROOT / "render.yaml").read_text(encoding="utf-8")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn(); print("PASS", fn.__name__)
        except Exception as exc:
            failed.append((fn.__name__, repr(exc))); print("FAIL", fn.__name__, repr(exc))
    print(f"RESULT {len(tests)-len(failed)} PASS / {len(failed)} FAIL")
    if failed:
        raise SystemExit(1)
