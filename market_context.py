"""SmartTradingReview core market context utilities — Commit 33.4.1.

Single, neutral implementation for specialist abstention semantics, cached BTC
context reuse, regime classification and early directional impulse detection.
No commit-number modules, network I/O, DB, LLMs, threads or runtime patching.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Tuple

VERSION = "CORE_MARKET_CONTEXT_33_4_1_V2"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        n = float(v if v is not None else default)
        return n if math.isfinite(n) else float(default)
    except Exception:
        return float(default)


def _nested(mapping: Mapping[str, Any] | None, *names: str, default: Any = None) -> Any:
    m = mapping or {}
    indicators = m.get("indicators") if isinstance(m.get("indicators"), Mapping) else {}
    for name in names:
        if name in m and m.get(name) is not None:
            return m.get(name)
        if name in indicators and indicators.get(name) is not None:
            return indicators.get(name)
    return default


def normalize_specialist_action(action: Any, confidence: Any) -> Tuple[str, str, bool]:
    """Normalize empty specialist votes to ABSTAIN, not bearish/negative evidence."""
    legacy = str(action or "NO_OPERAR").strip().upper()
    conf = _f(confidence, 0.0)
    if legacy == "NO_OPERAR" and conf <= 0.0:
        return "ABSTAIN", legacy, True
    if legacy in {"ABSTAIN", "NO_APLICA"}:
        return "ABSTAIN", legacy, True
    return legacy, legacy, False


def select_cached_btc_context(current_results: Mapping[Any, Any] | None, previous_results: Mapping[Any, Any] | None, timeframe: Any) -> Tuple[dict | None, str]:
    """Reuse a valid same-timeframe BTC snapshot without new I/O."""
    tf = str(timeframe or "")
    for source_name, source in (("CURRENT_REFRESH", current_results or {}), ("PREVIOUS_CACHE", previous_results or {})):
        try:
            row = source.get(("BTC-USDT", tf))
        except Exception:
            row = None
        if not isinstance(row, dict) or row.get("success") is False:
            continue
        trend = row.get("trend") or {}
        if not isinstance(trend, dict):
            continue
        adx = _f(trend.get("adx"), 0.0)
        direction = str(trend.get("direction") or "").strip().lower()
        if adx > 0.0 or direction in {"bullish", "bearish"}:
            return row, source_name
    return None, "NONE"


def context_available(payload: Any) -> bool:
    """Missing context is unknown; it must never be converted to neutral market evidence."""
    if not isinstance(payload, Mapping):
        return False
    if payload.get("success") is False or payload.get("context_available") is False:
        return False
    trend = payload.get("trend") if isinstance(payload.get("trend"), Mapping) else {}
    adx = _f(trend.get("adx"), 0.0)
    direction = str(trend.get("direction") or "").strip().lower()
    return bool(adx > 0.0 or direction in {"bullish", "bearish"})


def detect_directional_impulse(trend: Mapping[str, Any] | None, momentum: Mapping[str, Any] | None = None, volume: Mapping[str, Any] | None = None, structure: Mapping[str, Any] | None = None) -> dict:
    """Detect an early directional context event. It never publishes by itself."""
    trend, momentum, volume, structure = trend or {}, momentum or {}, volume or {}, structure or {}
    direction = str(trend.get("direction") or "neutral").strip().lower()
    adx = _f(_nested(trend, "adx", default=0.0))
    plus_di = _f(_nested(trend, "plus_di", default=0.0))
    minus_di = _f(_nested(trend, "minus_di", default=0.0))
    rsi = _f(_nested(momentum, "rsi", default=50.0), 50.0)
    macd = _f(_nested(momentum, "macd_histogram", "macd_hist", default=0.0))
    mom_dir = str(momentum.get("direction") or "neutral").strip().lower()
    mom_score = _f(momentum.get("score"), 0.0)
    vol_ratio = _f(_nested(volume, "volume_ratio", "relative_volume", default=1.0), 1.0)
    obv = str(_nested(volume, "obv_trend", "obv_direction", default="") or "").strip().lower()
    struct_dir = str(structure.get("direction") or structure.get("structure_direction") or "neutral").strip().lower()
    structural_inventory = bool(structure.get("order_blocks") or structure.get("fair_value_gaps") or structure.get("fvgs") or structure.get("liquidity_sweeps") or structure.get("stop_hunts"))

    if direction == "bearish":
        dominant, opposite = minus_di, plus_di
        momentum_ok = bool(mom_dir == "bearish" or rsi <= 45.0 or macd < 0.0 or mom_score < 0.0)
        structure_ok = bool(struct_dir == "bearish" and structural_inventory)
        volume_ok = bool(vol_ratio >= 1.20 or obv == "bearish")
    elif direction == "bullish":
        dominant, opposite = plus_di, minus_di
        momentum_ok = bool(mom_dir == "bullish" or rsi >= 55.0 or macd > 0.0 or mom_score > 0.0)
        structure_ok = bool(struct_dir == "bullish" and structural_inventory)
        volume_ok = bool(vol_ratio >= 1.20 or obv == "bullish")
    else:
        return {"active": False, "direction": "neutral", "strength": 0.0, "reason": "TREND_DIRECTION_NEUTRAL", "adx": round(adx,3), "plus_di": round(plus_di,3), "minus_di": round(minus_di,3), "can_publish": False}

    spread = max(0.0, dominant - opposite)
    ratio = dominant / max(opposite, 1.0)
    dmi_dominant = bool(dominant >= 25.0 and (spread >= 15.0 or ratio >= 2.0))
    corroborations = int(momentum_ok) + int(volume_ok) + int(structure_ok)
    active = bool(dmi_dominant and momentum_ok and (volume_ok or structure_ok))
    dominance = min(1.0, max(spread / 35.0, (ratio - 1.0) / 3.0))
    support = min(1.0, corroborations / 3.0)
    strength = min(1.0, 0.62 * dominance + 0.38 * support) if active else 0.0
    reasons=[]
    if dmi_dominant: reasons.append(f"DMI dominante {dominant:.1f} vs {opposite:.1f} (spread {spread:.1f}, ratio {ratio:.2f}x)")
    if momentum_ok: reasons.append(f"momentum confirma ({mom_dir}, RSI {rsi:.1f})")
    if volume_ok: reasons.append(f"actividad/volumen confirma ({vol_ratio:.2f}x, OBV {obv or 'n/a'})")
    if structure_ok: reasons.append("estructura institucional alineada")
    if active and adx < 20.0: reasons.append(f"ADX {adx:.1f} rezagado: no veta el impulso")
    return {"active":active,"direction":direction if active else "neutral","strength":round(strength,3),"adx":round(adx,3),"plus_di":round(plus_di,3),"minus_di":round(minus_di,3),"dmi_spread":round(spread,3),"dmi_ratio":round(ratio,3),"rsi":round(rsi,3),"volume_ratio":round(vol_ratio,3),"momentum_ok":momentum_ok,"volume_ok":volume_ok,"structure_ok":structure_ok,"corroborations":corroborations,"reasoning":reasons,"role":"CONTEXT_EVENT_ONLY","can_publish":False}


def classify_market_regime(trend: Mapping[str, Any] | None, volatility: Mapping[str, Any] | None, momentum: Mapping[str, Any] | None = None, volume: Mapping[str, Any] | None = None, structure: Mapping[str, Any] | None = None) -> dict:
    trend, volatility = trend or {}, volatility or {}
    adx=_f(trend.get("adx")); plus_di=_f(trend.get("plus_di")); minus_di=_f(trend.get("minus_di")); direction=str(trend.get("direction") or "neutral").strip().lower()
    atr_pct=_f(volatility.get("atr_pct")); bb_width=_f(volatility.get("bb_width")); vol_pct=_f(volatility.get("volatility_percentile"),50.0); vol_ratio=_f(volatility.get("volatility_ratio"),1.0); spread=abs(plus_di-minus_di)
    if (vol_pct >= 93.0 and vol_ratio >= 1.5) or atr_pct > 8.0:
        return {"regime":"HIGH_VOLATILITY","confidence":round(min(90.0,55.0+max(0.0,vol_pct-90.0)*2.0),1),"reasoning":[f"Volatilidad extrema: percentil {vol_pct:.1f}, ratio {vol_ratio:.2f}x, ATR {atr_pct:.2f}%"],"adx":adx,"atr_pct":atr_pct}
    impulse=detect_directional_impulse(trend,momentum or {},volume or {},structure or {})
    if impulse.get("active"):
        regime="DIRECTIONAL_IMPULSE_BEAR" if impulse.get("direction")=="bearish" else "DIRECTIONAL_IMPULSE_BULL"
        return {"regime":regime,"confidence":round(min(90.0,62.0+25.0*_f(impulse.get("strength"))),1),"reasoning":list(impulse.get("reasoning") or []),"adx":adx,"atr_pct":atr_pct,"directional_impulse":impulse}
    if adx > 25.0:
        if spread > 8.0 and plus_di > minus_di and direction == "bullish": return {"regime":"TRENDING_BULL","confidence":round(min(90.0,60.0+(adx-25.0)*1.5),1),"reasoning":[f"ADX {adx:.1f} > 25 con +DI dominante"],"adx":adx,"atr_pct":atr_pct}
        if spread > 8.0 and minus_di > plus_di and direction == "bearish": return {"regime":"TRENDING_BEAR","confidence":round(min(90.0,60.0+(adx-25.0)*1.5),1),"reasoning":[f"ADX {adx:.1f} > 25 con -DI dominante"],"adx":adx,"atr_pct":atr_pct}
        return {"regime":"TRANSITIONAL","confidence":round(min(78.0,55.0+max(0.0,adx-25.0)),1),"reasoning":[f"ADX {adx:.1f} fuerte, DMI sin dominancia estable"],"adx":adx,"atr_pct":atr_pct}
    if adx < 20.0:
        conf=min(85.0,60.0+(20.0-adx)*1.5); reasons=[f"ADX {adx:.1f} < 20 sin impulso DMI confirmado"]
        if 0.0 < bb_width < 3.0: conf=min(90.0,conf+10.0); reasons.append(f"BB width {bb_width:.2f}% (contracción)")
        return {"regime":"RANGING","confidence":round(conf,1),"reasoning":reasons,"adx":adx,"atr_pct":atr_pct}
    return {"regime":"TRANSITIONAL","confidence":52.0,"reasoning":[f"ADX {adx:.1f} en transición 20-25"],"adx":adx,"atr_pct":atr_pct}


def audit() -> dict:
    return {"version":VERSION,"single_core_module":True,"missing_context_is_neutral":False,"directional_impulse_can_publish":False,"new_io":0,"new_threads":0,"new_db_queries":0,"new_llm_calls":0}
