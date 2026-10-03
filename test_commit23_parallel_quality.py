from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import quality_9q_engine_21 as q9


def make_candidate(rr: float = 1.25, loss_sl: float = 4.0, atr_stress: float = 10.0):
    levels = {
        "execution_safety": 70.0,
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "entry_score": 82.0,
        "entry_reachability": 85.0,
        "tp_quality_score": 70.0,
        "sl_reliability": 0.80,
        "risk_reward": rr,
        "directional_thesis": True,
        "entry_sweep_confirmed": True,
        "entry_mss_bos_confirmed": True,
        "entry_displacement_confirmed": True,
        "entry_poi_confirmed": True,
        "sl_anchor": True,
        "volume_ratio": 1.0,
        "regime": "TRENDING",
        "volatility_state": "NORMAL",
        "risk_control": {
            "estimated_sl_loss_pct_margin": loss_sl,
            "estimated_atr_stress_loss_pct_margin": atr_stress,
        },
    }
    trend = {"direction": "BULLISH", "adx": 32, "regime": "TRENDING"}
    momentum = {"direction": "BULLISH", "rsi": 57}
    volatility = {"atr_pct": 1.4, "state": "NORMAL", "volume_ratio": 1.0}
    structure = {"direction": "BULLISH", "liquidity_sweep": True, "mss": True, "displacement": True, "entry_poi_confirmed": True}
    return levels, trend, momentum, volatility, structure


def main() -> None:
    levels, trend, momentum, volatility, structure = make_candidate(rr=1.25)
    q = q9.evaluate(levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    p = q["parallel_quality_filters"]

    assert len(p["filters"]) == 10
    assert p["selected_filter"].startswith("Q")
    assert p["selected_filter_score"] >= 75.0
    assert p["confirmed_one_of_ten"] is True
    assert p["q10_required"] is False
    assert p["fast_operation_mode"] is True
    assert p["rr_role"] == "SOFT_QUALITY_INPUT"
    assert q9.PARALLEL_FILTER_MIN_SCORE == 75.0

    # A quick trade may pass even while the legacy RR 1.8 gate would reject it.
    assert 1.25 < q9.Q10_MIN_RR

    # Economic hard guards remain non-negotiable.
    bad_levels, trend, momentum, volatility, structure = make_candidate(rr=1.25, loss_sl=12.0)
    q_bad = q9.evaluate(bad_levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    assert q_bad["parallel_quality_filters"]["confirmed_one_of_ten"] is False
    assert "LOSS_AT_SL" in q_bad["parallel_quality_filters"]["universal_guards"]["codes"]

    # Directional contradiction prevents parallel publication authority.
    levels, trend, momentum, volatility, structure = make_candidate()
    trend["direction"] = "BEARISH"
    momentum["direction"] = "BEARISH"
    structure["direction"] = "BEARISH"
    q_bad_dir = q9.evaluate(levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    assert q_bad_dir["parallel_quality_filters"]["confirmed_one_of_ten"] is False

    # The new authority path can promote a candidate whose legacy gate fails
    # only on the legacy publication-quality checks (including RR) while the
    # universal economic guards and one parallel Q remain valid.
    import premium_path_expansion_21 as ppe_direct
    synthetic_q = {
        "parallel_quality_filters": {
            "confirmed_one_of_ten": True,
            "selected_filter": "Q4",
            "selected_filter_name": "ESTRATEGIA / CONTEXTO",
            "selected_filter_score": 85.0,
            "passed_filters": ["Q4", "Q8"],
            "universal_guards": {"passed": True, "codes": []},
        }
    }
    synthetic_out = {
        "futures_filter_stage": "PUBLICATION_GATE",
        "publication_status": "ANALYSIS_ONLY",
        "is_executable": False,
    }
    synthetic_gate = {
        "eligible": False,
        "reason_codes": ["RR"],
        "tier": "ANALYSIS_ONLY",
    }
    promoted, did_promote = ppe_direct._try_parallel_quality_promotion(
        synthetic_out, synthetic_q, {}, synthetic_gate,
        symbol="NEAR-USDT", timeframe="30m", action="LONG"
    )
    assert did_promote is True
    assert promoted["is_executable"] is True
    assert promoted["publication_eligible"] is True
    assert promoted["quality_authority"] == "Q4"
    assert promoted["quality_authority_score"] == 85.0
    assert promoted["q10_is_mandatory"] is False
    assert promoted["futures_publication_gate"]["legacy_q10_reason_codes"] == ["RR"]

    # No forbidden runtime dependencies were added to the pure quality engine.
    tree = ast.parse((ROOT / "quality_9q_engine_21.py").read_text())
    banned = {"requests", "threading", "subprocess", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned

    for filename in ("quality_9q_engine_21.py", "premium_path_expansion_21.py"):
        compile((ROOT / filename).read_text(), filename, "exec")

    js = ROOT / "quality_filters_frontend.js"
    subprocess.run(["node", "--check", str(js)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    js_text = js.read_text()
    assert "other_directional_signals" in js_text
    assert "Q10" in js_text
    assert "ONE_OF_TEN_QUALITY_FILTERS" not in js_text  # UI only, not decision authority.


    # Test the runtime frontend overlay without requiring Flask itself: a tiny
    # compatible stub is enough to prove that app.py/index.html are untouched.
    import types
    import premium_path_expansion_21 as ppe
    fake_flask = types.ModuleType("flask")
    fake_flask.request = types.SimpleNamespace(path="/futures")
    import sys as _sys
    _sys.modules["flask"] = fake_flask

    class _Resp:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        def __init__(self, html): self._html = html
        def get_data(self, as_text=False): return self._html if as_text else self._html.encode()
        def set_data(self, value): self._html = value

    class _App:
        def __init__(self): self.hooks=[]
        def after_request(self, fn): self.hooks.append(fn); return fn

    fake_app = _App()
    hook_status = ppe.install_frontend_quality_overlay(fake_app)
    assert hook_status["installed"] is True
    response = _Resp('<html><body><script src="/static/futures.js?v=x"></script></body></html>')
    response = fake_app.hooks[0](response)
    assert "quality_filters_frontend.js" in response.get_data(True)
    assert "futures.js" in response.get_data(True)

    # Render/process stability inherited from Commit 22 remains present.
    proc = (ROOT / "Procfile").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert "--timeout 120" in proc
    assert "--max-requests 80" in proc
    assert "--max-requests-jitter 20" in proc
    assert "COMMIT22_WORKER_RESTART_POLICY" in render

    print("COMMIT 23 PARALLEL QUALITY QA: PASS")


if __name__ == "__main__":
    main()
