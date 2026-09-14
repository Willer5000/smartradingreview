"""FINAL V1 RC4 — Entry Reaction Engine.

The engine does not invent a new trade. It grades the Entry already selected by
SmartradingReview and decides whether the execution is precise enough for the
market/timeframe. Futures is deliberately stricter than Spot.

Core idea:
    POI/zone -> liquidity -> sweep -> MSS/BOS -> displacement/retest -> Entry

A high score means the entry is placed in a technically defendable reaction
area with enough confirmation for that timeframe. It is not a promise of TP.
"""
from __future__ import annotations

from typing import Any, Dict

RC4_ENTRY_REACTION_VERSION = "RC4_ENTRY_REACTION_V1"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _tf(timeframe: Any) -> str:
    raw = str(timeframe or "").strip().upper()
    return {"30MIN": "30M", "1DAY": "1D"}.get(raw, raw)


def evaluate_entry_reaction(
    levels: Dict[str, Any],
    *,
    structure: Dict[str, Any] | None = None,
    volatility: Dict[str, Any] | None = None,
    timeframe: Any = None,
    market_type: str = "spot",
) -> Dict[str, Any]:
    levels = levels or {}
    structure = structure or {}
    volatility = volatility or {}
    market = "FUTURES" if str(market_type or "").lower() == "futures" else "SPOT"
    tf = _tf(timeframe)

    smc = _f(levels.get("entry_smc_raw_score"), _f(levels.get("entry_score")))
    reach = _f(levels.get("entry_reachability_score"))
    defensibility = _f(levels.get("entry_defensibility_score"), _f(levels.get("sl_reliability")) * 100.0)
    distance_atr = levels.get("entry_distance_atr")
    try:
        distance_atr = float(distance_atr) if distance_atr is not None else None
    except Exception:
        distance_atr = None

    # Exposed by RC4 from the same causal SMC context used by entry selection.
    liquidity = bool(levels.get("entry_liquidity_pool_near"))
    sweep = bool(levels.get("entry_sweep_confirmed"))
    mss = bool(levels.get("entry_mss_bos_confirmed"))
    displacement = bool(levels.get("entry_displacement_confirmed"))
    source = str(levels.get("entry_source") or "").upper()
    structural_poi = any(token in source for token in ("ORDER BLOCK", "FVG", "POC", "SOPORTE", "RESIST", "SWING", "LIQUID"))

    # Reaction confirmation deliberately rewards *independent* evidence, not
    # number of indicators. A single RSI/EMA family cannot manufacture 90/100.
    reaction = 0.0
    reaction += 18.0 if structural_poi else 4.0
    reaction += 12.0 if liquidity else 0.0
    reaction += 24.0 if sweep else 0.0
    reaction += 22.0 if mss else 0.0
    reaction += 14.0 if displacement else 0.0
    reaction += min(10.0, max(0.0, smc - 60.0) * 0.25)
    reaction = max(0.0, min(100.0, reaction))

    # Existing SMC quality remains the dominant input. Reaction confirmation is
    # intentionally stronger in Futures because leverage punishes imprecision.
    if market == "FUTURES":
        quality = 0.42 * smc + 0.20 * reach + 0.18 * defensibility + 0.20 * reaction
    else:
        quality = 0.50 * smc + 0.24 * reach + 0.16 * defensibility + 0.10 * reaction
    quality = max(0.0, min(100.0, quality))

    if market == "FUTURES":
        threshold = {
            "30M": 62.0,
            "1H": 60.0,
            "2H": 58.0,
            "4H": 56.0,
            "12H": 54.0,
            "1D": 54.0,
        }.get(tf, 58.0)
        # High TF defines the thesis; a lower TF should refine the actual fill.
        lower_tf_confirmation_required = tf in {"12H", "1D"}
        weak_reaction_hard_block = (
            tf in {"30M", "1H", "2H", "4H"}
            and reaction < 32.0
            and smc < 62.0
        )
    else:
        threshold = {"4H": 48.0, "12H": 46.0, "1D": 44.0, "1W": 42.0}.get(tf, 46.0)
        lower_tf_confirmation_required = False
        weak_reaction_hard_block = False

    passed = quality >= threshold and not weak_reaction_hard_block

    if market == "FUTURES" and lower_tf_confirmation_required:
        status = "ZONE_VALID_LOWER_TF_TRIGGER_REQUIRED" if passed else "ENTRY_ZONE_WEAK"
    elif passed:
        status = "ENTRY_CONFIRMED"
    elif weak_reaction_hard_block:
        status = "ENTRY_REACTION_NOT_CONFIRMED"
    else:
        status = "ENTRY_QUALITY_BELOW_THRESHOLD"

    return {
        "version": RC4_ENTRY_REACTION_VERSION,
        "market": market,
        "timeframe": tf,
        "score": round(quality, 2),
        "threshold": threshold,
        "passed": bool(passed),
        "status": status,
        "lower_tf_confirmation_required": lower_tf_confirmation_required,
        "hard_block": bool(weak_reaction_hard_block),
        "components": {
            "smc": round(smc, 2),
            "reachability": round(reach, 2),
            "defensibility": round(defensibility, 2),
            "reaction": round(reaction, 2),
            "distance_atr": round(distance_atr, 4) if distance_atr is not None else None,
        },
        "reaction_evidence": {
            "structural_poi": structural_poi,
            "liquidity_pool_near": liquidity,
            "sweep": sweep,
            "mss_bos": mss,
            "displacement": displacement,
        },
        "policy": {
            "futures_stricter_than_spot": True,
            "entry_quality_not_win_probability": True,
            "high_tf_uses_lower_tf_trigger": bool(lower_tf_confirmation_required),
            "does_not_change_direction": True,
            "does_not_change_leverage": True,
        },
    }
