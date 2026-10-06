from __future__ import annotations

import champion_registry_commit19 as reg


def _base(direction="BULLISH", *, event=True, inventory=True, adx=26.0, volume=1.35, rsi=58.0):
    d = "bullish" if direction == "BULLISH" else "bearish"
    structure = {
        "direction": direction,
        "structure_direction": direction,
        "structure_score": 0.75 if direction == "BULLISH" else -0.75,
        # This mirrors analyze_price_structure_layer: there is no top-level
        # mss/bos/displacement key before Entry selection.
        "structure_reasons": (["SWEEP_REJECTION:bar=99;level=100"] if event else ["NO_STRICT_STRUCTURE_EVENT"]),
        "liquidity_sweeps": ([{"type": d, "sweep_level": 100.0, "index": 99, "strength": "strong"}] if inventory else []),
        "stop_hunts": [],
        "order_blocks": ([{"type": d, "price_range": [99.0, 100.0], "index": 95, "strength": "strong"}] if inventory else []),
        "fair_value_gaps": [],
        "supports": [99.0] if direction == "BULLISH" and inventory else [],
        "resistances": [101.0] if direction == "BEARISH" and inventory else [],
        "pivot_lows": [{"price": 99.0, "index": 90}] if direction == "BULLISH" and inventory else [],
        "pivot_highs": [{"price": 101.0, "index": 90}] if direction == "BEARISH" and inventory else [],
        "current_price": 100.5,
    }
    return {
        "trend": {"direction": d, "adx": adx},
        "momentum": {"direction": d, "rsi": rsi},
        "volume": {"volume_ratio": volume},
        "volatility": {"atr": 2.0, "atr_pct": 2.0, "state": "EXPANSION"},
        "structure": structure,
        "macro_context": {"risk_level": "NORMAL"},
    }


def _op(action="LONG"):
    return {
        "thesis": {"action": action, "direction": "BULLISH" if action == "LONG" else "BEARISH", "quality": 86},
        "context": {"regime": "TREND_UP" if action == "LONG" else "TREND_DOWN", "volatility": "EXPANSION"},
        "default_strategy": {"family": "SWEEP_MSS_POI"},
    }


def _mtf(direction="BULLISH"):
    return {"state": "ALIGNED_OR_NON_BLOCKING", "usable": True, "dominant_direction": direction,
            "conflict": False, "original_conflict": False}


def test_real_preentry_schema_can_reach_governed_30m_route():
    layers = _base("BULLISH")
    # Demonstrate the Commit-25 temporal mismatch explicitly: these fields are
    # absent from the real pre-Entry structure schema.
    assert "mss" not in layers["structure"]
    assert "bos" not in layers["structure"]
    assert "displacement" not in layers["structure"]

    route = reg.resolve_champion(
        layers=layers, operational=_op("LONG"), symbol="BTC-USDT", timeframe="30m",
        system_type="FUTURES", regime="TREND_UP", volatility="EXPANSION",
        mtf_relation=_mtf("BULLISH"),
    )
    assert route["eligible_for_execution_routing"] is True
    assert route["champion_id"] == "F30_SHARED_LIQ_SWEEP_MSS_POI_V1"
    assert route["live_context_reason"] == "F30_BACKTESTED_CONTEXT_AND_CAUSAL_PREENTRY_CONFIRMED"


def test_preentry_gate_still_requires_strict_closed_candle_structure():
    route = reg.resolve_champion(
        layers=_base("BULLISH", event=False), operational=_op("LONG"),
        symbol="ETH-USDT", timeframe="30m", system_type="FUTURES",
        regime="TREND_UP", volatility="EXPANSION", mtf_relation=_mtf("BULLISH"),
    )
    assert route["eligible_for_execution_routing"] is False
    assert route["reason"] == "F30_STRICT_CLOSED_CANDLE_EVENT_MISSING"


def test_preentry_gate_requires_reaction_inventory():
    route = reg.resolve_champion(
        layers=_base("BULLISH", inventory=False), operational=_op("LONG"),
        symbol="SOL-USDT", timeframe="30m", system_type="FUTURES",
        regime="TREND_UP", volatility="EXPANSION", mtf_relation=_mtf("BULLISH"),
    )
    assert route["eligible_for_execution_routing"] is False
    assert route["reason"] == "F30_REACTION_INVENTORY_MISSING"


def test_directional_mismatch_never_gets_promoted():
    layers = _base("BEARISH", rsi=42.0)
    # Force the operational proposal to LONG while structure is bearish.
    route = reg.resolve_champion(
        layers=layers, operational=_op("LONG"), symbol="XRP-USDT", timeframe="30m",
        system_type="FUTURES", regime="TREND_UP", volatility="EXPANSION",
        mtf_relation=_mtf("BULLISH"),
    )
    assert route["eligible_for_execution_routing"] is False


def test_structural_transition_is_visible_but_not_live_without_clean_oos():
    route = reg.resolve_champion(
        layers=_base("BULLISH"), operational=_op("LONG"), symbol="ADA-USDT", timeframe="30m",
        system_type="FUTURES", regime="TREND_UP", volatility="EXPANSION",
        mtf_relation={"state": "COUNTERTREND_VALID", "usable": True, "original_conflict": True,
                      "dominant_direction": "BEARISH"},
    )
    assert route["eligible_for_execution_routing"] is False
    assert route["reason"] == "MTF_STRUCTURAL_TRANSITION_SHADOW_ONLY"
