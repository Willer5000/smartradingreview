from __future__ import annotations

import json
from pathlib import Path

import champion_registry_commit19 as reg
from champion_decay_commit19 import evaluate_decay as champion_decay
from synthesis_decay_commit19_1 import evaluate_decay as synth_decay, get_decay_state as synth_state

ROOT = Path(__file__).resolve().parent


def layers(direction="BULLISH", *, adx=30, volume=1.3, rsi=58, structural=True, pullback=False):
    trend_name = "bullish" if direction == "BULLISH" else "bearish"
    s = {"direction": trend_name, "current_price": 100.0}
    if structural:
        s.update({"liquidity_sweep": True, "mss": True, "order_blocks": [{"price": 99.0}]})
    if pullback:
        s["setup"] = "TREND_PULLBACK_RETEST_POI"
    return {
        "trend": {"direction": trend_name, "adx": adx},
        "momentum": {"direction": trend_name, "rsi": rsi},
        "volume": {"volume_ratio": volume},
        "volatility": {"atr": 2.0, "atr_pct": 2.0, "state": "NORMAL"},
        "structure": s,
        "macro_context": {"risk_level": "NORMAL"},
    }


def op(action, regime):
    return {
        "thesis": {"action": action, "direction": "BULLISH" if action == "LONG" else "BEARISH", "quality": 86},
        "context": {"regime": regime, "volatility": "NORMAL"},
        "default_strategy": {"family": "TREND_PULLBACK"},
    }


def mtf(direction):
    return {"state": "ALIGNED", "usable": True, "dominant_direction": direction, "conflict": False}


def test_f30_exact_context_and_no_cross_symbol_copy():
    r = reg.resolve_champion(layers=layers("BULLISH"), operational=op("LONG", "TREND_UP"), symbol="BTC-USDT", timeframe="30m", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert r["eligible_for_execution_routing"] is True
    assert r["champion_id"] == "F30_SHARED_LIQ_SWEEP_MSS_POI_V1"
    assert r["risk_class"] == "CORE1"

    bnb = reg.resolve_champion(layers=layers("BULLISH"), operational=op("LONG", "TREND_UP"), symbol="BNB-USDT", timeframe="30m", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert bnb["eligible_for_execution_routing"] is False
    assert bnb["risk_class"] == "MEDIUM"

    high = reg.resolve_champion(layers=layers("BULLISH"), operational=op("LONG", "TREND_UP"), symbol="SUI-USDT", timeframe="30m", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert high["eligible_for_execution_routing"] is False
    assert high["risk_class"] == "HIGH"


def test_f30_backtest_contract_is_not_weakened():
    weak_adx = reg.resolve_champion(layers=layers("BULLISH", adx=18), operational=op("LONG", "TREND_UP"), symbol="ETH-USDT", timeframe="30m", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert weak_adx["eligible_for_execution_routing"] is False
    assert "ADX" in weak_adx["reason"]
    no_structure = reg.resolve_champion(layers=layers("BULLISH", structural=False), operational=op("LONG", "TREND_UP"), symbol="ETH-USDT", timeframe="30m", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert no_structure["eligible_for_execution_routing"] is False


def test_exact_2h_and_4h_champions():
    eth = reg.resolve_champion(layers=layers("BULLISH", rsi=58), operational=op("LONG", "TREND_UP"), symbol="ETH-USDT", timeframe="2h", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert eth["champion_id"] == "ETH_2H_LONG_RSI_TREND_V1"
    sol = reg.resolve_champion(layers=layers("BEARISH", rsi=44), operational=op("SHORT", "TREND_DOWN"), symbol="SOL-USDT", timeframe="2h", system_type="FUTURES", regime="TREND_DOWN", volatility="EXPANSION", mtf_relation=mtf("BEARISH"))
    assert sol["champion_id"] == "SOL_2H_SHORT_SUPERTREND_PULLBACK_V1"
    xrp = reg.resolve_champion(layers=layers("BEARISH", rsi=45), operational=op("SHORT", "TREND_DOWN"), symbol="XRP-USDT", timeframe="2h", system_type="FUTURES", regime="TREND_DOWN", volatility="NORMAL", mtf_relation=mtf("BEARISH"))
    assert xrp["champion_id"] == "XRP_2H_SHORT_TREND_CONTINUATION_V1"
    link = reg.resolve_champion(layers=layers("BEARISH", rsi=45), operational=op("SHORT", "TREND_DOWN"), symbol="LINK-USDT", timeframe="4h", system_type="FUTURES", regime="TREND_DOWN", volatility="NORMAL", mtf_relation=mtf("BEARISH"))
    assert link["champion_id"] == "LINK_4H_SHORT_RSI_TREND_V1"


def test_mtf_conflict_blocks_and_us_index_is_asset_specific():
    eth = reg.resolve_champion(layers=layers("BULLISH"), operational=op("LONG", "TREND_UP"), symbol="ETH-USDT", timeframe="2h", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation={"state": "HARD_CONFLICT", "usable": False})
    assert eth["eligible_for_execution_routing"] is False

    spy = reg.resolve_champion(layers=layers("BULLISH", pullback=True), operational=op("LONG", "TREND_UP"), symbol="SPY-USDT", timeframe="1D", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert spy["eligible_for_execution_routing"] is True
    assert spy["asset_class"] == "US_INDEX"

    energy = reg.resolve_champion(layers=layers("BULLISH", pullback=True), operational=op("LONG", "TREND_UP"), symbol="CL-USDT", timeframe="1D", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert energy["eligible_for_execution_routing"] is False
    assert energy["asset_class"] == "ENERGY"

    metal = reg.resolve_champion(layers=layers("BULLISH", pullback=True), operational=op("LONG", "TREND_UP"), symbol="XAG-USDT", timeframe="1D", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert metal["eligible_for_execution_routing"] is False
    assert metal["asset_class"] == "PRECIOUS_METAL"

    china = reg.resolve_champion(layers=layers("BULLISH", pullback=True), operational=op("LONG", "TREND_UP"), symbol="KSTR-USDT", timeframe="1D", system_type="FUTURES", regime="TREND_UP", volatility="NORMAL", mtf_relation=mtf("BULLISH"))
    assert china["eligible_for_execution_routing"] is False
    assert china["asset_class"] == "CHINA_INDEX"


def test_decay_contracts_and_synthesis_shadow_default():
    assert champion_decay(live_consecutive_losses=7) == "LIVE_CHAMPION"
    assert champion_decay(live_consecutive_losses=8) == "SHADOW_DECAY"
    assert champion_decay(live_consecutive_losses=8, shadow_consecutive_losses=8) == "RETIRED_ALPHA_DECAY"
    assert synth_decay(live_consecutive_losses=7) == "LIVE_SYNTHESIS"
    assert synth_decay(live_consecutive_losses=8) == "SHADOW_DECAY"
    assert synth_state(synthesis_id="UNVALIDATED")["state"] == "SHADOW_DECAY"


def test_registry_matches_frozen_release_evidence():
    frozen = json.loads((ROOT / "BACKTEST_COMMIT19_RESULT.json").read_text())
    assert set(reg.route_registry()) == set(frozen["champions"])
    for cid, row in frozen["champions"].items():
        for split in (row.get("parts") or {}).values():
            assert float(split.get("expectancy_r") or 0.0) > 0.0
            assert float(split.get("pf") or 0.0) > 1.0
