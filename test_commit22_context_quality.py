from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import quality_9q_engine_21 as q9


def candidate(*, action="LONG", safety=70.0, base_variant="strong"):
    if base_variant == "strong":
        levels = {
            "execution_safety": safety,
            "entry_score": 82,
            "entry_reachability": 85,
            "tp_quality_score": 70,
            "sl_reliability": 0.80,
            "risk_reward": 2.20,
            "directional_thesis": True,
            "entry_sweep_confirmed": True,
            "entry_mss_bos_confirmed": True,
            "entry_displacement_confirmed": True,
            "entry_poi_confirmed": True,
            "sl_anchor": True,
            "volume_ratio": 1.0,
            "market_session": "US_CASH",
        }
        trend = {"direction": "BULLISH", "adx": 32, "regime": "TRENDING"}
        momentum = {"direction": "BULLISH", "rsi": 57}
        volatility = {"atr_pct": 1.4, "state": "NORMAL", "volume_ratio": 1.0}
        structure = {
            "direction": "BULLISH",
            "liquidity_sweep": True,
            "mss": True,
            "displacement": True,
            "entry_poi_confirmed": True,
        }
    elif base_variant == "contradictory":
        levels = {
            "execution_safety": safety,
            "entry_score": 82,
            "entry_reachability": 85,
            "tp_quality_score": 70,
            "sl_reliability": 0.80,
            "risk_reward": 2.20,
            "directional_thesis": True,
            "entry_sweep_confirmed": True,
            "entry_mss_bos_confirmed": True,
            "entry_displacement_confirmed": True,
            "entry_poi_confirmed": True,
            "sl_anchor": True,
            "volume_ratio": 1.0,
        }
        trend = {"direction": "BEARISH", "adx": 32, "regime": "TRENDING"}
        momentum = {"direction": "BEARISH", "rsi": 57}
        volatility = {"atr_pct": 1.4, "state": "NORMAL"}
        structure = {"direction": "BEARISH", "liquidity_sweep": True, "mss": True, "displacement": True, "entry_poi_confirmed": True}
    else:
        levels = {
            "execution_safety": safety,
            "entry_score": 76,
            "entry_reachability": 70,
            "tp_quality_score": 62,
            "sl_reliability": 0.72,
            "risk_reward": 1.90,
            "directional_thesis": True,
            "volume_ratio": 0.9,
        }
        trend = {"direction": "BULLISH", "adx": 29, "regime": "TRENDING"}
        momentum = {"direction": "BULLISH", "rsi": 55}
        volatility = {"atr_pct": 1.2, "state": "NORMAL"}
        structure = {"direction": "BULLISH"}
    return levels, trend, momentum, volatility, structure


def main() -> None:
    levels, trend, momentum, volatility, structure = candidate()
    groups = q9.evaluate_context_quality_groups(levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    assert groups["primary_group"] in {"SWEEP_MSS_RECLAIM", "FAST_STABLE_CONTINUATION"}
    assert 0 < groups["group_bonus"] <= 5.0

    q = q9.evaluate(levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    assert q["composite"] >= q["base_composite"]
    assert q["context_quality_groups"]["version"].startswith("COMMIT22_CONTEXT_QUALITY_GROUPS")
    assert q["context_quality_authority"] or q["generic_quality_ready"]

    # Contradictions must suppress contextual authority.
    levels, trend, momentum, volatility, structure = candidate(base_variant="contradictory")
    groups = q9.evaluate_context_quality_groups(levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    assert groups["group_bonus"] == 0.0
    assert not groups["authority_ready"]

    # Multiasset session group can be selected without changing Q10.
    levels, trend, momentum, volatility, structure = candidate()
    levels["market_type"] = "multiasset"
    levels["market_session"] = "US_CASH"
    groups = q9.evaluate_context_quality_groups(levels, trend, momentum, volatility, structure, "1h", "QQQ-USDT", "LONG", "multiasset")
    assert "MULTIASSET_SESSION_EXECUTION" in groups["matched_groups"] or groups["primary_group"] in {"SWEEP_MSS_RECLAIM", "FAST_STABLE_CONTINUATION"}

    # Existing hard thresholds remain unchanged.
    assert q9.Q10_MIN_SAFETY == 75.0
    assert q9.Q10_MIN_TP == 55.0
    assert q9.Q10_MIN_SL == 60.0
    assert q9.Q10_MIN_RR == 1.8
    assert q9.Q10_MAX_RR == 3.5
    assert q9.MIN_COMPOSITE == 76.0

    # Deep Safety authority can only move upward and remains tied to Q1..Q9.
    levels, trend, momentum, volatility, structure = candidate()
    q = q9.evaluate(levels, trend, momentum, volatility, structure, "30m", "NEAR-USDT", "LONG", "futures")
    up = q9.deep_quality_safety_upgrade(levels, q)
    assert up["upgraded_execution_safety"] >= up["legacy_execution_safety"]
    assert up["thresholds_lowered"] is False

    proc = (ROOT / "Procfile").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert "--timeout 120" in proc
    assert "--max-requests 80" in proc
    assert "--max-requests-jitter 20" in proc
    assert "--timeout 120" in render
    assert "COMMIT22_WORKER_RESTART_POLICY" in render

    # The embedded Commit 22 quality-group engine adds no network/thread dependency.
    tree = ast.parse((ROOT / "quality_9q_engine_21.py").read_text())
    banned = {"requests", "threading", "subprocess", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned

    print("COMMIT 22 CONTEXT QUALITY QA: PASS")


if __name__ == "__main__":
    main()
