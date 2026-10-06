from __future__ import annotations

"""Commit 25 regression of the historical Commit-23 parallel-Q lane.

The ten filters remain observable but are no longer publication authority.
"""
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import quality_9q_engine_21 as q9
import premium_path_expansion_21 as ppe


def make_candidate(rr: float = 2.0, safety: float = 80.0, loss_sl: float = 4.0, atr_stress: float = 10.0):
    levels = {
        "execution_safety": safety,
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "entry_score": 82.0,
        "entry_reachability": 85.0,
        "entry_source": "STRUCTURAL_POI",
        "tp_quality_score": 70.0,
        "sl_reliability": 0.80,
        "risk_reward": rr,
        "directional_thesis": True,
        "entry_sweep_confirmed": True,
        "entry_mss_bos_confirmed": True,
        "entry_displacement_confirmed": True,
        "entry_poi_confirmed": True,
        "sl_anchor": True,
        "volume_ratio": 1.2,
        "regime": "TRENDING",
        "volatility_state": "NORMAL",
        "risk_control": {
            "estimated_sl_loss_pct_margin": loss_sl,
            "estimated_atr_stress_loss_pct_margin": atr_stress,
        },
    }
    trend = {"direction": "BULLISH", "adx": 32, "regime": "TRENDING"}
    momentum = {"direction": "BULLISH", "rsi": 57}
    volatility = {"atr_pct": 1.4, "state": "NORMAL", "volume_ratio": 1.2}
    structure = {"direction": "BULLISH", "liquidity_sweep": True, "mss": True, "displacement": True, "entry_poi_confirmed": True}
    return levels, trend, momentum, volatility, structure


def test_parallel_filters_diagnostic_and_hard_economics():
    levels, trend, momentum, volatility, structure = make_candidate(rr=2.0)
    q = q9.evaluate(levels, trend, momentum, volatility, structure, "30m", "BTC-USDT", "LONG", "futures")
    p = q["parallel_quality_filters"]
    assert len(p["filters"]) == 10
    assert p["q10_required"] is True
    assert p["rr_role"] == "DIAGNOSTIC_INPUT_HARD_NATIVE_PUBLICATION_GATE"
    assert p["universal_guards"]["passed"] is True

    bad, trend, momentum, volatility, structure = make_candidate(rr=1.25)
    qb = q9.evaluate(bad, trend, momentum, volatility, structure, "30m", "BTC-USDT", "LONG", "futures")
    assert qb["parallel_quality_filters"]["confirmed_one_of_ten"] is False
    assert "RR_OUTSIDE_1_8_3_5" in qb["parallel_quality_filters"]["universal_guards"]["codes"]

    low_safety, trend, momentum, volatility, structure = make_candidate(rr=2.0, safety=70.0)
    qs = q9.evaluate(low_safety, trend, momentum, volatility, structure, "30m", "BTC-USDT", "LONG", "futures")
    assert "PREMIUM_SAFETY_BELOW_75" in qs["parallel_quality_filters"]["universal_guards"]["codes"]


def test_parallel_cannot_promote_legacy_rr_failure():
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
    out, promoted = ppe._try_parallel_quality_promotion(
        {"futures_filter_stage": "PUBLICATION_GATE", "publication_status": "ANALYSIS_ONLY", "is_executable": False},
        synthetic_q, {}, {"eligible": False, "reason_codes": ["RR"]},
        symbol="BTC-USDT", timeframe="30m", action="LONG",
    )
    assert promoted is False
    assert out["is_executable"] is False
    assert out["q10_is_mandatory"] is True
    assert out["commit25_parallel_quality_diagnostic_only"] is True


def test_q6_missing_reachability_does_not_pass_on_zero_default():
    levels, trend, momentum, volatility, structure = make_candidate()
    levels.pop("entry_reachability", None)
    levels.pop("entry_source", None)
    levels["entry_score"] = 65.0
    q = q9.evaluate(levels, trend, momentum, volatility, structure, "30m", "BTC-USDT", "LONG", "futures")
    rows = {r["filter"]: r for r in q["parallel_quality_filters"]["filters"]}
    assert rows["Q6"]["evidence"] is False


def test_no_forbidden_dependencies():
    tree = ast.parse((ROOT / "quality_9q_engine_21.py").read_text())
    banned = {"requests", "threading", "subprocess", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned
