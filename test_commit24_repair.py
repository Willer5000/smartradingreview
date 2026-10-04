import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "commit24_repair_runtime", ROOT / "commit24_repair_runtime.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_result(**overrides):
    result = {
        "success": True,
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "is_multiasset": False,
        "decision": {"action": "LONG", "confidence": 68},
        "levels": {
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "risk_reward": 2.0,
            "leverage": 5,
            "risk_allocation_fraction": 0.50,
            "execution_safety": 80.0,
            "execution_safety_operational_min": 65.0,
            "futures_filter_stage": "PUBLICATION_GATE",
            "futures_publication_gate": {
                "stage": "PUBLICATION_GATE",
                "reason_codes": ["SAFETY"],
                "reasons": ["Safety insuficiente en legacy Q10"],
            },
            "risk_control": {
                "estimated_sl_loss_pct_margin": 5.0,
                "estimated_atr_stress_loss_pct_margin": 10.0,
            },
            "entry_score": 80.0,
            "entry_reachability": 80.0,
            "tp_quality_score": 85.0,
            "sl_reliability": 0.85,
        },
        "trend": {"direction": "bullish", "adx": 30},
        "momentum": {"direction": "bullish"},
        "volatility": {"atr_pct": 2.0, "state": "NORMAL"},
        "structure": {"direction": "bullish"},
        "market_data_is_synthetic": False,
    }
    for k, v in overrides.items():
        result[k] = v
    return result


class FakeFutures:
    def _calculate_execution_safety(
        self, levels, trend, momentum, structure, timeframe
    ):
        return {
            "score": float(levels.get("execution_safety", 80.0)),
            "label": "ALTA",
            "components": {},
        }


class FakeApp:
    def _get_futures_system(self):
        return FakeFutures()

    def _ensure_manual_diagnostic_geometry_175114(
        self, result, action, symbol, timeframe
    ):
        # Production helper is allowed to change fallback geometry.
        result["levels"]["manual_geometry_fallback"] = True
        return result["levels"]


def install_fake_q(stage="PUBLICATION_GATE", score=84.0, passed=True, blockers=("SAFETY",)):
    class Q:
        @staticmethod
        def evaluate(**kwargs):
            return {
                "parallel_quality_filters": {
                    "selected_filter": "Q7",
                    "selected_filter_name": "SALIDA / GEOMETRÍA",
                    "selected_filter_score": score,
                    "selected_filter_passed": passed,
                    "passed_filters": ["Q7"] if passed else [],
                    "summary": "Q7 %.1f" % score,
                    "legacy_publication_blockers": list(blockers),
                    "universal_guards": {
                        "passed": stage == "PUBLICATION_GATE",
                        "codes": [],
                    },
                }
            }

    sys.modules["quality_9q_engine_21"] = Q


def test_promotes_one_of_ten_and_reconciles_gate():
    install_fake_q()
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), make_result(), "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is True
    assert auth["authority"] == "Q7"
    assert out["levels"]["publication_status"] == "EXECUTABLE_SIGNAL"
    assert out["premium_confirmation_mode"] == "ONE_OF_TEN_QUALITY_FILTERS"
    assert out["levels"]["risk_control"]["estimated_sl_loss_pct_margin"] == 5.0
    gate = out["levels"]["futures_publication_gate"]
    assert gate["eligible"] is True
    assert gate["status"] == "PREMIUM_CONTEXT_QUALITY"
    assert gate["reason_codes"] == []


def test_rejects_below_75():
    install_fake_q(score=74.9, passed=False)
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), make_result(), "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert out.get("publication_status") != "EXECUTABLE_SIGNAL"
    assert "NO_Q_GE75" in auth["universal_guard_codes"]


def test_rejects_pre_gate():
    install_fake_q(stage="CANDIDATE")
    r = make_result()
    r["levels"]["futures_filter_stage"] = "CANDIDATE"
    r["levels"]["futures_publication_gate"]["stage"] = "CANDIDATE"
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert "PRE_GATE_REJECTION" in auth["universal_guard_codes"]


def test_rejects_safety_floor():
    install_fake_q()
    r = make_result()
    r["levels"]["execution_safety"] = 64.9
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert "OPERATIONAL_SAFETY_BELOW_65" in auth["universal_guard_codes"]


def test_rejects_sl_loss_after_geometry_revaluation():
    install_fake_q()
    r = make_result()
    r["levels"]["risk_allocation_fraction"] = 1.0
    # 2% SL * 5x * 100% = 10% margin loss.
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert "LOSS_AT_SL" in auth["universal_guard_codes"]


def test_rejects_atr_stress():
    install_fake_q()
    r = make_result()
    r["volatility"]["atr_pct"] = 7.0
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert "ATR_STRESS" in auth["universal_guard_codes"]


def test_rejects_non_q10_blocker():
    install_fake_q(blockers=("LOSS_AT_SL",))
    r = make_result()
    r["levels"]["futures_publication_gate"]["reason_codes"] = ["LOSS_AT_SL"]
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert "NON_Q10_LEGACY_BLOCKER" in auth["universal_guard_codes"]


def test_rejects_unverified_market_provenance():
    install_fake_q()
    r = make_result()
    r.pop("market_data_is_synthetic", None)
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert auth["confirmed"] is False
    assert "REAL_MARKET_DATA_UNVERIFIED" in auth["universal_guard_codes"]


def test_recomputes_atr_stress_after_geometry_change():
    install_fake_q()
    r = make_result()
    # Make the fallback geometry wider: 5% SL. With 5x and 50% allocation,
    # ATR stress must be max(5%, 2%*1.5) * 5 * .5 = 12.5%.
    class GeometryApp(FakeApp):
        def _ensure_manual_diagnostic_geometry_175114(
            self, result, action, symbol, timeframe
        ):
            result["levels"]["stop_loss"] = 95.0
            result["levels"]["manual_geometry_fallback"] = True
            return result["levels"]

    out, auth = mod._normalize_quality_candidate(
        GeometryApp(), r, "BTC-USDT", "1h"
    )
    assert out["levels"]["risk_control"]["estimated_sl_loss_pct_margin"] == 12.5
    assert out["levels"]["risk_control"]["estimated_atr_stress_loss_pct_margin"] == 12.5
    assert "LOSS_AT_SL" in auth["universal_guard_codes"]


def test_native_executable_geometry_is_not_rewritten():
    install_fake_q()
    r = make_result()
    r["levels"]["publication_status"] = "EXECUTABLE_SIGNAL"
    r["levels"]["is_rejected"] = False
    original = dict(r["levels"])
    out, auth = mod._normalize_quality_candidate(
        FakeApp(), r, "BTC-USDT", "1h"
    )
    assert out["levels"]["entry"] == original["entry"]
    assert out["levels"]["stop_loss"] == original["stop_loss"]
    assert out["levels"]["take_profit"] == original["take_profit"]


def test_hidden_dedupe_keeps_best_cell():
    # Test the wrapper contract without a Flask app.
    original = lambda visibility, source_context, representative_ids=None: [
        {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "quality_filter_confirmed": False,
            "quality_filter_score": 76,
            "confidence": 70,
            "risk_reward": 2.0,
        },
        {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "quality_filter_confirmed": True,
            "quality_filter_score": 78,
            "confidence": 65,
            "risk_reward": 1.8,
        },
    ]
    class Dummy:
        _futures_directional_hidden_candidates = staticmethod(original)

    mod._ORIGINALS.clear()
    mod._wrap_hidden_candidates(Dummy)
    rows = Dummy._futures_directional_hidden_candidates({}, "futures")
    assert len(rows) == 1
    assert rows[0]["quality_filter_confirmed"] is True


def test_ui_queue_does_not_spawn_waiting_worker():
    called = {"count": 0}

    def original(symbol, timeframe, market="futures"):
        called["count"] += 1
        return "SCHEDULED"

    class Dummy:
        _start_futures_ui_analysis_async = staticmethod(original)
        _mark_futures_interactive_priority = staticmethod(lambda seconds=120: None)

    mod._ORIGINALS.clear()
    mod._PENDING_UI.clear()
    mod._HOLDER_OWNER = "futures-incremental:BTC-USDT:1h"
    mod._HOLDER_STARTED_AT = __import__("time").monotonic()
    try:
        mod._wrap_ui_start(Dummy)
        state = Dummy._start_futures_ui_analysis_async(
            "ETH-USDT", "1h", market="futures"
        )
        assert state == "DEFERRED_INTERACTIVE_QUEUE"
        assert called["count"] == 0
        assert len(mod._PENDING_UI) == 1
    finally:
        mod._PENDING_UI.clear()
        mod._HOLDER_OWNER = ""
        mod._HOLDER_STARTED_AT = 0.0


if __name__ == "__main__":
    tests = [
        test_promotes_one_of_ten_and_reconciles_gate,
        test_rejects_below_75,
        test_rejects_pre_gate,
        test_rejects_safety_floor,
        test_rejects_sl_loss_after_geometry_revaluation,
        test_rejects_atr_stress,
        test_rejects_non_q10_blocker,
        test_rejects_unverified_market_provenance,
        test_recomputes_atr_stress_after_geometry_change,
        test_native_executable_geometry_is_not_rewritten,
        test_hidden_dedupe_keeps_best_cell,
        test_ui_queue_does_not_spawn_waiting_worker,
    ]
    for fn in tests:
        fn()
        print("PASS", fn.__name__)
    print("ALL PASS")
