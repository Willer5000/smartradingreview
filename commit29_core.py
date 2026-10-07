"""Commit 29 core helpers: deployment/runtime integrity and causal context.

Pure helpers only. No network, DB, LLM, threads or mutable global state.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

VERSION = "COMMIT29_CORE_SYSTEM_RECOVERY_V1"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        n = float(v if v is not None else default)
        return n if math.isfinite(n) else float(default)
    except Exception:
        return float(default)


def context_available(payload: Any) -> bool:
    """Missing context is not neutral market evidence."""
    if not isinstance(payload, Mapping):
        return False
    if payload.get("success") is False or payload.get("context_available") is False:
        return False
    trend = payload.get("trend") if isinstance(payload.get("trend"), Mapping) else {}
    adx = _f(trend.get("adx"), 0.0)
    direction = str(trend.get("direction") or "").strip().lower()
    return bool(adx > 0.0 or direction in {"bullish", "bearish"})


def classify_market_regime(trend: Mapping[str, Any] | None, volatility: Mapping[str, Any] | None) -> dict:
    """Classify regime without mislabeling strong-but-conflicted ADX as ranging.

    TRANSITIONAL is intentionally neutral for committee weighting: it denotes
    strong/medium trend energy without a stable directional DMI confirmation.
    """
    trend = trend or {}
    volatility = volatility or {}
    adx = _f(trend.get("adx"), 0.0)
    plus_di = _f(trend.get("plus_di"), 0.0)
    minus_di = _f(trend.get("minus_di"), 0.0)
    direction = str(trend.get("direction") or "neutral").strip().lower()
    atr_pct = _f(volatility.get("atr_pct"), 0.0)
    bb_width = _f(volatility.get("bb_width"), 0.0)
    vol_pct = _f(volatility.get("volatility_percentile"), 50.0)
    vol_ratio = _f(volatility.get("volatility_ratio"), 1.0)
    spread = abs(plus_di - minus_di)
    reasons = []

    if (vol_pct >= 93.0 and vol_ratio >= 1.5) or atr_pct > 8.0:
        confidence = min(90.0, 55.0 + max(0.0, vol_pct - 90.0) * 2.0)
        reasons.append(f"Volatilidad extrema: percentil {vol_pct:.1f}, ratio {vol_ratio:.2f}x, ATR {atr_pct:.2f}%")
        return {"regime": "HIGH_VOLATILITY", "confidence": round(confidence, 1), "reasoning": reasons, "adx": adx, "atr_pct": atr_pct}

    if adx > 25.0:
        if spread > 8.0 and plus_di > minus_di and direction == "bullish":
            confidence = min(90.0, 60.0 + (adx - 25.0) * 1.5)
            reasons += [f"ADX {adx:.1f} > 25 con +DI {plus_di:.1f} > -DI {minus_di:.1f}", "Dirección bullish confirmada"]
            return {"regime": "TRENDING_BULL", "confidence": round(confidence, 1), "reasoning": reasons, "adx": adx, "atr_pct": atr_pct}
        if spread > 8.0 and minus_di > plus_di and direction == "bearish":
            confidence = min(90.0, 60.0 + (adx - 25.0) * 1.5)
            reasons += [f"ADX {adx:.1f} > 25 con -DI {minus_di:.1f} > +DI {plus_di:.1f}", "Dirección bearish confirmada"]
            return {"regime": "TRENDING_BEAR", "confidence": round(confidence, 1), "reasoning": reasons, "adx": adx, "atr_pct": atr_pct}
        # Key Commit-29 fix: strong ADX with conflicted DMI is not a 20-25 range.
        confidence = min(78.0, 55.0 + max(0.0, adx - 25.0))
        reasons.append(f"ADX {adx:.1f} fuerte, pero DMI/dirección sin dominancia estable (spread {spread:.1f})")
        return {"regime": "TRANSITIONAL", "confidence": round(confidence, 1), "reasoning": reasons, "adx": adx, "atr_pct": atr_pct}

    if adx < 20.0:
        confidence = min(85.0, 60.0 + (20.0 - adx) * 1.5)
        reasons.append(f"ADX {adx:.1f} < 20 (sin tendencia)")
        if 0.0 < bb_width < 3.0:
            confidence = min(90.0, confidence + 10.0)
            reasons.append(f"BB width {bb_width:.2f}% (contracción)")
        return {"regime": "RANGING", "confidence": round(confidence, 1), "reasoning": reasons, "adx": adx, "atr_pct": atr_pct}

    reasons.append(f"ADX {adx:.1f} en transición 20-25; no se fuerza RANGING")
    return {"regime": "TRANSITIONAL", "confidence": 52.0, "reasoning": reasons, "adx": adx, "atr_pct": atr_pct}


def audit() -> dict:
    return {
        "version": VERSION,
        "missing_context_is_neutral": False,
        "transitional_regime_supported": True,
        "new_io": 0,
        "new_db_queries": 0,
        "new_llm_calls": 0,
        "new_threads": 0,
    }
