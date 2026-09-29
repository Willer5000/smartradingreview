"""QA Commit 17.5.10.2 — standalone acceptance checks.

Run from repository root:
    python qa/qa_commit17_5_10_2.py
"""
from __future__ import annotations

import importlib
import math
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_stubs():
    op = types.ModuleType("operational_intelligence")
    op.is_official_cell = lambda market, symbol, timeframe, action: True
    sys.modules["operational_intelligence"] = op

    bank = types.ModuleType("default_strategy_bank")
    def select_strategy(action, regime, vol_state, groups, **kwargs):
        preferred = kwargs.get("preferred_family") or "TREND_PULLBACK"
        return {
            "id": "QA_STRATEGY",
            "family": preferred,
            "quality": 84.0,
            "regime_match": True,
            "volatility_match": True,
            "confirmations": ["qa"],
            "conflicts": [],
        }
    bank.select_strategy = select_strategy
    sys.modules["default_strategy_bank"] = bank

    multi = types.ModuleType("multiasset_system")
    multi.MULTIASSET_SYMBOLS = {
        "CL-USDT": {"asset_class": "ENERGY"},
    }
    multi.MULTIASSET_STRATEGY_BANK = {
        "ENERGY": ["TREND_PULLBACK", "SWEEP_MSS_POI", "BREAKOUT_RETEST"],
    }
    sys.modules["multiasset_system"] = multi


def neutral_operational():
    return {
        "candidate_ready": False,
        "candidate_action": "NO_OPERAR",
        "official_cell": False,
        "risk_class": "CORE1",
        "context": {"regime": "TREND_UP", "volatility": "NORMAL"},
        "multi_timeframe": {
            "dominant_direction": "BULLISH",
            "alignment": "ALIGNED",
            "conflict": False,
        },
        "thesis": {
            "direction": "NEUTRAL",
            "action": "NO_OPERAR",
            "quality": 69.0,
            "macro_risk": "LOW",
            "independent_support_families": [],
        },
        "indicator_groups": {},
        "research_candidates": {},
    }


def bullish_pullback_layers():
    return {
        "trend": {
            "direction": "BULLISH",
            "adx": 31,
            "plus_di": 28,
            "minus_di": 14,
        },
        "momentum": {
            "direction": "BULLISH",
            "indicators": {"rsi": 57, "macd_histogram": 1.2},
        },
        "volume": {
            "obv_trend": "BULLISH",
            "volume_ratio": 1.35,
        },
        "volatility": {
            "atr_pct": 1.4,
            "squeeze_on": False,
        },
        "structure": {
            "direction": "BULLISH",
            "order_blocks": [{"direction": "BULLISH", "price_range": [99, 100]}],
            "fair_value_gaps": [],
            "liquidity_sweeps": [],
            "note": "bullish pullback retest into order block",
        },
        "macro_context": {"risk_level": "LOW"},
    }


def test_particular_trend_pullback_promotes():
    import pipeline_integrity_175102 as p
    out = p.reconcile_operational_candidate(
        neutral_operational(),
        layers=bullish_pullback_layers(),
        symbol="BTC-USDT",
        timeframe="2h",
        system_type="FUTURES",
    )
    assert out["candidate_ready"] is True, out
    assert out["candidate_action"] == "LONG", out
    assert out["candidate_source"] == "PARTICULAR_SETUP+STRATEGY", out
    assert out["particular_setup_family"] == "TREND_PULLBACK", out
    assert out["never_bypass_safety"] is True


def test_noise_does_not_promote():
    import pipeline_integrity_175102 as p
    op = neutral_operational()
    op["multi_timeframe"] = {
        "dominant_direction": "NEUTRAL", "alignment": "MIXED", "conflict": False
    }
    layers = {
        "trend": {"direction": "NEUTRAL", "adx": 14},
        "momentum": {"direction": "NEUTRAL", "indicators": {"rsi": 50, "macd_histogram": 0}},
        "volume": {"obv_trend": "NEUTRAL", "volume_ratio": 0.8},
        "volatility": {"atr_pct": 0.7, "squeeze_on": False},
        "structure": {"direction": "NEUTRAL"},
        "macro_context": {"risk_level": "LOW"},
    }
    out = p.reconcile_operational_candidate(
        op, layers=layers, symbol="BTC-USDT", timeframe="2h", system_type="FUTURES"
    )
    assert out["candidate_ready"] is False
    assert out["candidate_action"] == "NO_OPERAR"


def test_existing_candidate_preserved():
    import pipeline_integrity_175102 as p
    op = neutral_operational()
    op.update({
        "candidate_ready": True,
        "candidate_action": "LONG",
        "official_cell": True,
    })
    op["thesis"].update({"direction": "BULLISH", "action": "LONG", "quality": 86})
    out = p.reconcile_operational_candidate(
        op, layers=bullish_pullback_layers(),
        symbol="BTC-USDT", timeframe="2h", system_type="FUTURES"
    )
    assert out["candidate_ready"] is True
    assert out["candidate_action"] == "LONG"


def test_greeks_math_no_direction_authority():
    from market_maker_math import aggregate_gamma_exposure
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=12)
    rows = []
    for strike, c_oi, p_oi in [
        (90000, 120, 30),
        (95000, 180, 70),
        (100000, 250, 220),
        (105000, 90, 260),
        (110000, 40, 180),
    ]:
        rows.append({
            "strike": strike, "open_interest": c_oi, "iv": 0.55,
            "option_type": "CALL", "expiry": expiry,
        })
        rows.append({
            "strike": strike, "open_interest": p_oi, "iv": 0.58,
            "option_type": "PUT", "expiry": expiry,
        })
    out = aggregate_gamma_exposure(rows, spot=100000, as_of=now)
    assert out["available"] is True
    assert out["can_create_direction"] is False
    assert out["production_score_adjustment"] == 0.0
    assert out["specialist_shadow_context"]["authority"] == "SHADOW_CONTEXT_ONLY"
    assert out["specialist_shadow_context"]["can_modify_entry"] is False
    # Delta curve should be finite and not be produced by an extra PUT sign flip.
    vals = [float(x[1]) for x in out["delta_curve"]]
    assert all(math.isfinite(x) for x in vals)
    assert len(set(round(x, 4) for x in vals)) > 3


def test_altcoin_option_chain_is_not_projected():
    import options_market_context as o
    out = o.get_crypto_option_chain("SOL-USDT")
    assert out["available"] is False
    assert out["direct_underlying_match"] is False
    assert out["reason"] == "NO_DIRECT_OPTION_UNDERLYING_FOR_SYMBOL"


def main():
    install_stubs()
    tests = [
        test_particular_trend_pullback_promotes,
        test_noise_does_not_promote,
        test_existing_candidate_preserved,
        test_greeks_math_no_direction_authority,
        test_altcoin_option_chain_is_not_projected,
    ]
    failed = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed.append((fn.__name__, repr(exc)))
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"\n{len(tests)-len(failed)}/{len(tests)} PASS")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
