from __future__ import annotations

from pathlib import Path

import market_context
import pipeline_integrity
import publication_quality
import safety_profiles

ROOT = Path(__file__).resolve().parent


def _layers(direction="bullish"):
    bull = direction == "bullish"
    trend = {
        "direction": direction,
        "adx": 28.0,
        "plus_di": 38.0 if bull else 12.0,
        "minus_di": 12.0 if bull else 38.0,
    }
    momentum = {"direction": direction, "rsi": 61.0 if bull else 39.0, "score": 1 if bull else -1}
    structure = {
        "direction": direction,
        "order_blocks": [{"type": "bullish" if bull else "bearish"}],
        "fair_value_gaps": [{"direction": direction}],
        "liquidity_sweeps": [{"direction": direction}],
        "mss": True,
        "pullback": True,
    }
    return {
        "trend": trend,
        "momentum": momentum,
        "volatility": {"atr_pct": 1.3, "volatility_percentile": 55},
        "volume": {"volume_ratio": 1.35, "obv_trend": direction},
        "structure": structure,
        "macro_context": {"risk_level": "LOW"},
    }


def test_runtime_has_no_deleted_core_imports():
    forbidden = (
        "commit28_core", "commit29_core", "commit30_core",
        "pipeline_integrity_175101", "execution_abi_175104",
        "safety_profiles_commit31", "contextual_quality_commit28",
        "quality_9q_engine_21", "premium_path_expansion_20",
        "strategy_quality_extension_175105", "commit24_repair_runtime",
    )
    for name in ("app.py", "futures_system.py", "operational_intelligence.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, (name, token)


def test_market_context_impulse_is_context_not_signal():
    layers = _layers("bearish")
    out = market_context.detect_directional_impulse(
        layers["trend"], layers["momentum"], layers["volume"], layers["structure"]
    )
    assert out["active"] is True
    assert out["direction"] == "bearish"
    assert out["can_publish"] is False


def test_candidate_router_does_not_require_historical_route_pre_geometry():
    layers = _layers("bullish")
    op = {
        "thesis": {
            "direction": "BULLISH", "action": "LONG", "quality": 84,
            "independent_support_families": ["trend", "momentum", "structure", "volume"],
        },
        "multi_timeframe": {"conflict": False},
        "candidate_ready": False,
    }
    out = pipeline_integrity.reconcile_operational_candidate(
        op, layers=layers, symbol="BTC-USDT", timeframe="30m", system_type="FUTURES"
    )
    assert out["candidate_ready"] is True
    assert out["candidate_action"] == "LONG"
    assert out["candidate_router_contract"]["route_authority_is_pre_candidate_veto"] is False
    assert out["never_bypass_safety"] is True


def _publishable_result():
    layers = _layers("bullish")
    return {
        "symbol": "BTC-USDT",
        "timeframe": "30m",
        "analysis_mode": "CLOSED_CANDLE",
        "source_candle_closed": True,
        "market_data_is_synthetic": False,
        "decision": {"action": "LONG", "confidence": 84},
        "trend": layers["trend"],
        "momentum": layers["momentum"],
        "volatility": layers["volatility"],
        "structure": layers["structure"],
        "operational_intelligence": {
            "candidate_ready": True,
            "candidate_action": "LONG",
            "candidate_source": "CORE_SETUP",
            "candidate_quality": 88,
            "candidate_contract": {
                "version": "33.4.2_PIPELINE_INTEGRITY_V6", "passed": True,
                "action": "LONG", "source": "CORE_SETUP",
                "quality": 88, "quality_floor": 82,
                "support": ["trend", "mtf", "pullback", "momentum", "volume"],
                "support_count": 5, "support_floor": 3,
                "setup_family": "TREND_PULLBACK", "ambiguous": False,
            },
            "core_setup_quality": 88,
            "core_setup_family": "TREND_PULLBACK",
            "core_setup_support": ["trend", "mtf", "pullback", "momentum", "volume"],
            "particular_setup_diagnostic": {"ambiguous": False, "winner": {"setup": "TREND_PULLBACK", "quality": 88, "core_hits": ["trend", "mtf", "pullback"], "support_hits": ["momentum", "volume"]}},
            "thesis": {"independent_support_families": ["trend", "momentum", "structure", "volume"]},
        },
        "levels": {
            "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
            "risk_reward": 2.0,
            "entry_score": 82.0,
            "entry_source": "Order Block + pullback",
            "sl_reliability": 0.82,
            "tp_quality_score": 82.0,
            "setup_family": "TREND_PULLBACK",
            "risk_control": {},
        },
    }


def test_missing_atr_stress_is_not_a_fake_hard_failure():
    result = _publishable_result()
    auth = publication_quality.evaluate_publication(result, symbol="BTC-USDT", timeframe="30m", quality={})
    assert "ATR_STRESS" not in auth["hard_reason_codes"]


def test_core_technical_route_can_publish_only_after_safety_and_geometry():
    result = _publishable_result()
    auth = publication_quality.evaluate_publication(result, symbol="BTC-USDT", timeframe="30m", quality={})
    assert auth["route_authority"]["core_technical_route_live"] is True
    assert auth["hard_guards"]["primary_geometry"] is True
    assert auth["hard_guards"]["selected_safety_ready"] is True
    assert auth["eligible"] is True


def test_fallback_geometry_stays_non_publishable():
    result = _publishable_result()
    result["levels"]["manual_geometry_fallback"] = True
    auth = publication_quality.evaluate_publication(result, symbol="BTC-USDT", timeframe="30m", quality={})
    assert auth["eligible"] is False
    assert "FALLBACK_GEOMETRY_NOT_PUBLISHABLE" in auth["hard_reason_codes"]


def test_multi_display_lane_does_not_launch_heavy_15s_fetch():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    start = text.index("def _multiasset_light_chart_snapshot_33_4")
    end = text.index("# 17.5.11 — cache-only Multi-Asset diagnostic lane", start)
    block = text[start:end]
    assert "_get_cached_futures_data" in block
    assert "_router_fetch" in block
    assert "engine.get_kucoin_data" not in block


def test_native_execution_market_type_is_defined_before_committee_gate():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    anchor = text.index("execution_market_type = 'futures' if is_futures else 'spot'")
    gate = text.index("if baseline_geometry_valid:", anchor)
    assert anchor < gate


def test_boot_is_app_native_and_overlay_free():
    assert "gunicorn app:app" in (ROOT / "Procfile").read_text()
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _bootstrap_core_33_4" in text
    assert "runtime_overlays':False" in text or "runtime_overlays': False" in text
