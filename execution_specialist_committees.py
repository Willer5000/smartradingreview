"""Commit 17.1 - Specialist Execution Committees · Joint Geometry Reconciliation.

Deterministic, local-only specialist deliberation for Entry, Stop Loss and
Take Profit.  No network, database or LLM calls.  The committees do not create
a LONG/SHORT thesis; they evaluate the execution geometry of an already
selected thesis using evidence that the analysis has already loaded.

Design principle:
    * no "near is good" / "deep is safe" rule;
    * distance is only one item of evidence (fill probability / noise);
    * every candidate is evaluated by several independent specialist lenses;
    * market, strategy, regime, volatility and live context change relevance;
    * Spot, Futures and Multi-Asset have different execution strictness;
    * a specialist abstains when its evidence is unavailable instead of
      fabricating a score.
"""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "COMMIT17_5_11R_1_CONTEXT_ALIGNED_EXECUTION_V1"

try:
    from preliminary_backtest_prior import (
        entry_component_prior as _bt_entry_component_prior,
        sl_component_prior as _bt_sl_component_prior,
        tp_component_prior as _bt_tp_component_prior,
        family_cell_prior as _bt_family_cell_prior,
    )
except Exception:  # fail-open: priors can never break execution geometry
    _bt_entry_component_prior = _bt_sl_component_prior = None
    _bt_tp_component_prior = _bt_family_cell_prior = None


MULTI_ASSET_CLASS = {
    "SPY-USDT": "US_INDEX", "QQQ-USDT": "US_INDEX",
    "CL-USDT": "ENERGY", "NATGAS-USDT": "ENERGY",
    "COPPER-USDT": "INDUSTRIAL_METAL", "XAG-USDT": "PRECIOUS_METAL",
    "KSTR-USDT": "CHINA_INDEX",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if isfinite(out) else default
    except Exception:
        return default


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _seq(mapping: Dict[str, Any], key: str) -> List[float]:
    out: List[float] = []
    for item in (mapping.get(key) or []):
        try:
            out.append(float(item))
        except Exception:
            pass
    return out


def _weighted_mean(items: Iterable[Tuple[float, float]]) -> Optional[float]:
    vals = [(float(v), max(0.0, float(w))) for v, w in items if v is not None and w > 0]
    if not vals:
        return None
    den = sum(w for _, w in vals)
    return sum(v * w for v, w in vals) / den if den > 0 else None


def _consensus(scores: List[float]) -> float:
    if len(scores) < 2:
        return 50.0
    mean = sum(scores) / len(scores)
    var = sum((s - mean) ** 2 for s in scores) / len(scores)
    # Low dispersion => stronger agreement.  A disagreement is information,
    # not an automatic veto.
    return _clip(100.0 - sqrt(var) * 2.15)


def _activity_ratio_score(ratio: float) -> float:
    ratio = max(0.0, ratio)
    if ratio <= 0.45:
        return 18.0
    if ratio <= 1.0:
        return 18.0 + 37.0 * (ratio - 0.45) / 0.55
    if ratio <= 2.0:
        return 55.0 + 45.0 * (ratio - 1.0)
    return 100.0


def build_execution_context(*, structure=None, volume=None, volatility=None,
                            market_hours=None, sentiment=None, macro_context=None,
                            market_regime=None, market_maker_context=None,
                            symbol=None, timeframe=None, market_type=None) -> Dict[str, Any]:
    """Observed execution context; calendar labels are tags, not fixed alpha.

    It deliberately uses only data already loaded in the current analysis.
    Therefore a weekend/Asian-session prior cannot override an actual shock in
    volume/range/macro conditions, and this function adds zero bandwidth.
    """
    structure, volume, volatility = _d(structure), _d(volume), _d(volatility)
    market_hours, sentiment = _d(market_hours), _d(sentiment)
    macro_context, market_regime = _d(macro_context), _d(market_regime)
    market_maker_context = _d(market_maker_context)
    df = _d(structure.get("df"))

    highs, lows, vols = _seq(df, "high"), _seq(df, "low"), _seq(df, "volume")
    n = min(len(highs), len(lows))
    ranges = [max(0.0, highs[i] - lows[i]) for i in range(n)]
    recent_n = min(4, n)
    recent_ranges = [x for x in ranges[-recent_n:] if x > 0] if recent_n else []
    base_ranges = [x for x in ranges[max(0, n-36):max(0, n-recent_n)] if x > 0]
    atr = _f(volatility.get("atr"), 0.0)
    live_range = median(recent_ranges) if recent_ranges else atr
    base_range = median(base_ranges) if base_ranges else atr
    range_ratio = live_range / base_range if base_range > 0 else 1.0

    volume_ratio = _f(volume.get("volume_ratio"), 0.0)
    if volume_ratio <= 0 and vols:
        rv = [x for x in vols[-min(4, len(vols)):] if x >= 0]
        bv = [x for x in vols[max(0, len(vols)-36):max(0, len(vols)-len(rv))] if x > 0]
        if rv and bv:
            volume_ratio = median(rv) / max(median(bv), 1e-12)
    if volume_ratio <= 0:
        volume_ratio = 1.0

    activity = _clip(0.55 * _activity_ratio_score(volume_ratio) + 0.45 * _activity_ratio_score(range_ratio))
    shock = _clip(max(0.0, volume_ratio - 1.25) * 52.0 + max(0.0, range_ratio - 1.25) * 52.0)

    macro_risk = str(macro_context.get("risk_level") or "UNKNOWN").upper()
    posture = str(macro_context.get("futures_posture") or macro_context.get("posture") or "NORMAL").upper()
    if macro_risk == "CRITICAL" or posture == "NO_NEW_TRADES":
        shock = max(shock, 95.0)
    elif macro_risk == "HIGH" or posture in {"CAUTION", "WAIT_EVENT"}:
        shock = max(shock, 72.0)

    sentiment_value = _f(sentiment.get("current_value"), 50.0)
    market = str(market_type or "").lower()
    sym = str(symbol or "").upper()
    asset_class = MULTI_ASSET_CLASS.get(sym, "CRYPTO" if market != "multiasset" else "OTHER")

    return {
        "version": VERSION,
        "market_type": market,
        "symbol": sym,
        "timeframe": str(timeframe or ""),
        "asset_class": asset_class,
        "session": str(market_hours.get("session") or "UNKNOWN"),
        "day_type": str(market_hours.get("day_type") or "UNKNOWN"),
        "calendar_authority": "CONTEXT_TAG_ONLY",
        "volume_ratio": round(volume_ratio, 4),
        "range_ratio": round(range_ratio, 4),
        "activity_score": round(activity, 2),
        "shock_score": round(shock, 2),
        "macro_risk": macro_risk,
        "macro_posture": posture,
        "sentiment_value": round(sentiment_value, 2),
        "sentiment_bias": str(sentiment.get("sentiment_bias") or "neutral"),
        "market_regime": str(market_regime.get("regime") or market_regime.get("state") or "UNKNOWN"),
        # 17.5.10: Black-Scholes/Greeks/GEX context is carried into the
        # execution desk, but has zero production score authority until a
        # point-in-time options replay validates it.  Workers can reason about
        # gamma walls/delta-neutral levels without turning them into votes.
        "market_maker_context": market_maker_context,
        "market_maker_authority": str(market_maker_context.get("authority") or "UNAVAILABLE"),
    }




def _extract_price_levels(payload: Any, limit: int = 24) -> List[float]:
    """Best-effort extraction from already-loaded liquidation/microstructure payloads.

    The function is intentionally conservative and never opens a network call.
    """
    out: List[float] = []
    stack = [payload]
    seen = 0
    while stack and len(out) < limit and seen < 120:
        seen += 1
        item = stack.pop()
        if isinstance(item, dict):
            for key in ("price", "level", "center", "price_level", "liq_price"):
                value = _f(item.get(key), 0.0)
                if value > 0:
                    out.append(value)
            for key, value in item.items():
                if key in {"price","level","center","price_level","liq_price"}:
                    continue
                if isinstance(value, (dict, list, tuple)):
                    stack.append(value)
        elif isinstance(item, (list, tuple)):
            stack.extend(list(item)[:40])
    # preserve order, deduplicate
    clean=[]
    for x in out:
        if not any(abs(x-y) <= max(abs(x)*1e-7,1e-10) for y in clean):
            clean.append(x)
    return clean[:limit]

def _append_candidate(out: List[Dict[str, Any]], price: Any, family: str,
                      source: str, strength: Any = 2.0, anchor: Optional[float] = None) -> None:
    p = _f(price, 0.0)
    if p <= 0:
        return
    # Deduplicate nearby representations without erasing independent evidence.
    for row in out:
        if abs(_f(row.get("price")) - p) <= max(abs(p) * 1e-7, 1e-10):
            fams = row.setdefault("families", set())
            fams.add(family)
            row["strength"] = max(_f(row.get("strength"), 1.0), _f(strength, 2.0))
            if source and source not in row.setdefault("sources", []):
                row["sources"].append(source)
            return
    out.append({
        "price": p, "family": family, "families": {family},
        "source": source, "sources": [source] if source else [],
        "strength": max(1.0, min(3.0, _f(strength, 2.0))),
        "anchor": anchor,
    })


def _iter_swing_prices(structure: Dict[str, Any], key: str):
    for item in structure.get(key, []) or []:
        if isinstance(item, dict):
            p = _f(item.get("price"), 0.0)
            s = _f(item.get("strength"), 3.0)
        else:
            p, s = _f(item, 0.0), 2.0
        if p > 0:
            yield p, s


def _volume_profile(structure: Dict[str, Any]) -> Dict[str, Any]:
    return _d(structure.get("volume_profile") or structure.get("vp") or {})


def _execution_structure(structure: Dict[str, Any]) -> Dict[str, Any]:
    """Private committee view; never mutate the signal's Structure evidence.

    A closed candle through an OB's invalidation edge retires that original
    OB. A potential role reversal would require separate evidence. Missing
    legacy indices retain compatibility; explicit invalidation is authoritative.
    """
    result = dict(structure)
    closes = _d(structure.get("df")).get("close") or []
    usable = []
    for ob in structure.get("order_blocks") or []:
        if not isinstance(ob, dict) or ob.get("invalidated") or ob.get("mitigated"):
            continue
        bounds = ob.get("price_range") or []
        if len(bounds) < 2:
            continue
        bottom, top = _f(bounds[0]), _f(bounds[1])
        if not 0 < bottom < top:
            continue
        index = ob.get("index")
        if isinstance(index, int) and not isinstance(index, bool) and closes:
            if not 0 <= index < len(closes):
                continue
            observed = [_f(c, -1.) for c in closes[index + 1:]]
            if any(c <= 0 for c in observed):
                continue
            bull = str(ob.get("type") or "").lower() == "bullish"
            if any(c <= bottom if bull else c >= top for c in observed):
                continue
        usable.append(ob)
    result["order_blocks"] = usable
    return result


def _recent_candle_reaction_levels(structure: Dict[str, Any], direction: str) -> List[Tuple[float, str, float]]:
    """Low-cost reaction anchors from already-loaded candles.

    Used only as a recovery universe when explicit S/R, OB, FVG or profile
    levels are sparse.  It adds zero I/O and does not create the trading thesis.
    """
    df = _d(_d(structure).get("df"))
    highs, lows, closes = _seq(df, "high"), _seq(df, "low"), _seq(df, "close")
    n = min(len(highs), len(lows))
    if n <= 0:
        return []
    look = min(20, n)
    hi = highs[-look:]
    lo = lows[-look:]
    out: List[Tuple[float, str, float]] = []
    if direction == "long":
        recent = lo[-min(5, len(lo)):]
        if recent:
            out.append((median(recent), "Micro soporte reciente", 2.0))
        out.append((min(lo), "Extremo estructural reciente", 2.6))
    else:
        recent = hi[-min(5, len(hi)):]
        if recent:
            out.append((median(recent), "Micro resistencia reciente", 2.0))
        out.append((max(hi), "Extremo estructural reciente", 2.6))
    if closes:
        out.append((closes[-1], "Último cierre", 1.4))
    clean=[]
    for price, src, strength in out:
        if price > 0 and not any(abs(price-x[0]) <= max(abs(price)*1e-7,1e-10) for x in clean):
            clean.append((price,src,strength))
    return clean


def _add_execution_recovery_entry_candidates(out: List[Dict[str, Any]], *,
                                             structure: Dict[str, Any], direction: str,
                                             current_price: float, atr: float) -> None:
    # 17.5.2: recovery means "look harder at observed reaction structure", not
    # "manufacture a price by ATR".  Recent swing/reaction levels are genuine
    # market evidence already present in the loaded candles and therefore safe
    # to add as alternatives.  If they are insufficient, the caller preserves
    # the audited 17.5.1 baseline geometry.
    for price, src, strength in _recent_candle_reaction_levels(structure, direction):
        _append_candidate(out, price, "recent_reaction", src, strength)


def _add_execution_recovery_sl_candidates(out: List[Dict[str, Any]], *,
                                          structure: Dict[str, Any], direction: str,
                                          entry: float, atr: float, activity: float) -> None:
    # 17.5.2: SL recovery only extends REAL invalidation anchors.  ATR is used
    # as a noise buffer behind observed structure, never as a stand-alone stop
    # source.  This prevents the committee from recreating the old fixed-ATR SL.
    noise_mult = 0.16 + 0.20 * _clip(activity,0,100)/100.0
    buffer_abs = max(atr*noise_mult, abs(entry)*0.0004)
    for anchor, src, strength in _recent_candle_reaction_levels(structure, direction):
        if direction == "long" and anchor < entry:
            _append_candidate(out, anchor-buffer_abs, "recent_invalidation", f"Invalidación detrás de {src}", strength, anchor=anchor)
        elif direction == "short" and anchor > entry:
            _append_candidate(out, anchor+buffer_abs, "recent_invalidation", f"Invalidación detrás de {src}", strength, anchor=anchor)


def _add_execution_recovery_tp_candidates(out: List[Dict[str, Any]], *,
                                          direction: str, entry: float, sl: float, atr: float,
                                          rr_floor: float, preferred_rr_min: float,
                                          preferred_rr_max: float) -> None:
    # 17.5.2 intentionally does NOT invent TP levels from R/R or ATR.  A target
    # must come from structure/value/liquidity already observed by the system.
    # If no such target improves the baseline, the baseline TP is preserved.
    return


def _collect_entry_candidates(structure: Dict[str, Any], direction: str,
                              baseline: float, liquidation=None) -> List[Dict[str, Any]]:
    s = _d(structure)
    long_side = direction == "long"
    out: List[Dict[str, Any]] = []
    _append_candidate(out, baseline, "baseline", "Entry base", 2.0)

    for p in s.get("supports" if long_side else "resistances", []) or []:
        _append_candidate(out, p, "structure", "Soporte" if long_side else "Resistencia", 2.0)
    for p, st in _iter_swing_prices(s, "pivot_lows" if long_side else "pivot_highs"):
        _append_candidate(out, p, "swing", "Swing", st)

    for ob in s.get("order_blocks", []) or []:
        if not isinstance(ob, dict):
            continue
        if str(ob.get("type") or "").lower() != ("bullish" if long_side else "bearish"):
            continue
        pr = ob.get("price_range") or []
        if len(pr) >= 2:
            _append_candidate(out, pr[1] if long_side else pr[0], "smc_poi", "Order Block", 3 if ob.get("strength") == "strong" else 2)

    for fvg in s.get("fair_value_gaps", []) or []:
        if not isinstance(fvg, dict) or fvg.get("filled", True):
            continue
        if str(fvg.get("type") or "").lower() != ("bullish" if long_side else "bearish"):
            continue
        _append_candidate(out, fvg.get("gap_top" if long_side else "gap_bottom"), "smc_poi", "FVG", 2)

    fib = _d(s.get("fib_retracements") or s.get("fibonacci") or s.get("fib_levels"))
    for name, value in fib.items():
        if str(name) in {"0.382", "0.5", "0.50", "0.618", "0.786"}:
            _append_candidate(out, value, "fib", f"Fib {name}", 3 if str(name) in {"0.618", "0.786"} else 2)

    vp = _volume_profile(s)
    _append_candidate(out, vp.get("poc"), "value", "POC", 3)
    _append_candidate(out, vp.get("val" if long_side else "vah"), "value", "Value Area", 2)
    for node in vp.get("hvn_nodes", []) or []:
        if isinstance(node, dict):
            _append_candidate(out, node.get("price"), "value", "HVN", 3)

    indicators = _d(s.get("indicators"))
    for key, label in (("ema20", "EMA20"), ("ema50", "EMA50"), ("ema200", "EMA200"), ("vwap", "VWAP")):
        _append_candidate(out, indicators.get(key) or s.get(key), "dynamic_value", label, 2)

    for key in ("liquidity_pools", "liquidity_zones"):
        for item in s.get(key, []) or []:
            if isinstance(item, dict):
                side = str(item.get("side") or item.get("type") or "").lower()
                # Entry wants sell-side liquidity for longs and buy-side for shorts.
                wanted = ("sell" in side or "low" in side) if long_side else ("buy" in side or "high" in side)
                if wanted or not side:
                    _append_candidate(out, item.get("price") or item.get("level"), "liquidity", "Liquidity", _f(item.get("strength"), 2))
    for lp in _extract_price_levels(liquidation):
        if (long_side and lp <= baseline) or ((not long_side) and lp >= baseline):
            _append_candidate(out, lp, "liquidation", "Liquidation / liquidity map", 2)
    return out


def _collect_sl_candidates(structure: Dict[str, Any], direction: str, entry: float,
                           baseline: float, atr: float, activity: float) -> List[Dict[str, Any]]:
    s = _d(structure)
    long_side = direction == "long"
    out: List[Dict[str, Any]] = []
    _append_candidate(out, baseline, "baseline", "SL base", 2.0)

    # Noise buffer follows observed activity. It is a buffer behind a real
    # invalidation anchor, never a free-standing ATR stop.
    noise_mult = 0.14 + 0.18 * _clip(activity, 0, 100) / 100.0
    buffer_abs = max(atr * noise_mult, abs(entry) * 0.0004)

    anchors: List[Tuple[float, str, float]] = []
    for p in s.get("supports" if long_side else "resistances", []) or []:
        v = _f(p, 0.0)
        if v > 0: anchors.append((v, "Estructura", 2.0))
    for p, st in _iter_swing_prices(s, "pivot_lows" if long_side else "pivot_highs"):
        anchors.append((p, "Swing", max(2.0, st)))
    for ob in s.get("order_blocks", []) or []:
        if not isinstance(ob, dict): continue
        if str(ob.get("type") or "").lower() != ("bullish" if long_side else "bearish"): continue
        pr = ob.get("price_range") or []
        if len(pr) >= 2:
            anchors.append((_f(pr[0] if long_side else pr[1], 0.0), "Order Block", 3.0))
    for fvg in s.get("fair_value_gaps", []) or []:
        if not isinstance(fvg, dict) or fvg.get("filled", True): continue
        if str(fvg.get("type") or "").lower() != ("bullish" if long_side else "bearish"): continue
        p = _f(fvg.get("gap_bottom" if long_side else "gap_top"), 0.0)
        if p > 0: anchors.append((p, "FVG", 2.0))

    for anchor, source, strength in anchors:
        if anchor <= 0: continue
        # Only structural anchors located beyond Entry in the invalidation side.
        if (long_side and anchor >= entry) or ((not long_side) and anchor <= entry):
            continue
        stop = anchor - buffer_abs if long_side else anchor + buffer_abs
        _append_candidate(out, stop, "structural_invalidation", f"Detrás de {source}", strength, anchor=anchor)
    return out


def _collect_tp_candidates(structure: Dict[str, Any], direction: str, entry: float,
                           baseline: float, atr: float, liquidation=None) -> List[Dict[str, Any]]:
    s = _d(structure)
    long_side = direction == "long"
    out: List[Dict[str, Any]] = []
    _append_candidate(out, baseline, "baseline", "TP base", 2.0)

    for p in s.get("resistances" if long_side else "supports", []) or []:
        _append_candidate(out, p, "structure_target", "Resistencia" if long_side else "Soporte", 2.0)
    for p, st in _iter_swing_prices(s, "pivot_highs" if long_side else "pivot_lows"):
        _append_candidate(out, p, "swing_target", "Swing target", st)

    for ob in s.get("order_blocks", []) or []:
        if not isinstance(ob, dict): continue
        if str(ob.get("type") or "").lower() != ("bearish" if long_side else "bullish"): continue
        pr = ob.get("price_range") or []
        if len(pr) >= 2:
            _append_candidate(out, pr[0] if long_side else pr[1], "opposing_poi", "Order Block contrario", 3 if ob.get("strength") == "strong" else 2)
    for fvg in s.get("fair_value_gaps", []) or []:
        if not isinstance(fvg, dict) or fvg.get("filled", True): continue
        if str(fvg.get("type") or "").lower() != ("bearish" if long_side else "bullish"): continue
        _append_candidate(out, fvg.get("gap_bottom" if long_side else "gap_top"), "opposing_poi", "FVG contrario", 2)

    vp = _volume_profile(s)
    _append_candidate(out, vp.get("poc"), "value_target", "POC", 2)
    _append_candidate(out, vp.get("vah" if long_side else "val"), "value_target", "Value Area", 2)
    for node in vp.get("hvn_nodes", []) or []:
        if isinstance(node, dict): _append_candidate(out, node.get("price"), "value_target", "HVN", 3)

    fib = _d(s.get("fib_extensions") or s.get("fib_levels") or s.get("fibonacci"))
    for name, value in fib.items():
        if str(name) in {"1.0", "1", "1.272", "1.414", "1.618", "2.0", "2"}:
            _append_candidate(out, value, "fib_target", f"Fib ext {name}", 2 if str(name) != "1.618" else 3)

    for key in ("liquidity_pools", "liquidity_zones"):
        for item in s.get(key, []) or []:
            if not isinstance(item, dict): continue
            side = str(item.get("side") or item.get("type") or "").lower()
            wanted = ("buy" in side or "high" in side) if long_side else ("sell" in side or "low" in side)
            if wanted or not side:
                _append_candidate(out, item.get("price") or item.get("level"), "liquidity_target", "Liquidity target", _f(item.get("strength"), 2))

    for lp in _extract_price_levels(liquidation):
        if (long_side and lp > entry) or ((not long_side) and lp < entry):
            _append_candidate(out, lp, "liquidation_target", "Liquidation / liquidity target", 2)

    # Front-edge candidates are alternatives considered by the TP committee,
    # not mandatory cuts. A strong opposing zone may be approached from the
    # safer side when that alternative has better expected utility.
    buffer_abs = max(atr * 0.12, abs(entry) * 0.00035)
    snapshot = list(out)
    for row in snapshot:
        if row.get("family") in {"structure_target", "swing_target", "opposing_poi", "value_target", "liquidity_target"}:
            p = _f(row.get("price"), 0.0)
            if p <= 0: continue
            capture = p - buffer_abs if long_side else p + buffer_abs
            _append_candidate(out, capture, "capture_before_reaction", f"Captura antes de {row.get('source')}", _f(row.get("strength"), 2), anchor=p)
    return out


def _is_correct_side(price: float, reference: float, direction: str, role: str) -> bool:
    if role == "entry":
        return price <= reference if direction == "long" else price >= reference
    if role == "sl":
        return price < reference if direction == "long" else price > reference
    return price > reference if direction == "long" else price < reference


def _cluster_evidence(candidate: Dict[str, Any], universe: List[Dict[str, Any]], atr: float) -> Tuple[int, float]:
    p = _f(candidate.get("price"), 0.0)
    radius = max(atr * 0.30, abs(p) * 0.0012)
    families = set(candidate.get("families") or {candidate.get("family")})
    strength = _f(candidate.get("strength"), 1.0)
    for other in universe:
        if other is candidate: continue
        if abs(_f(other.get("price")) - p) <= radius:
            families.update(other.get("families") or {other.get("family")})
            strength += min(2.0, _f(other.get("strength"), 1.0)) * 0.45
    return len({f for f in families if f}), min(6.0, strength)


def evaluate_sl_reaction_conflict(*, structure: Dict[str, Any], direction: str,
                                  entry: float, stop_loss: float, atr: float) -> Dict[str, Any]:
    """Fail closed on invalid input and reject only local, still-valid reaction collisions.

    17.5.11 also protects the *full width* of a valid Order Block. A stop inside
    the body of a reaction zone is not an invalidation; it is precisely where a
    reaction may occur. Far historical levels remain irrelevant.
    """
    direction = str(direction or "").lower()
    try:
        raw_entry, raw_stop, raw_atr = float(entry), float(stop_loss), float(atr)
    except Exception:
        raw_entry = raw_stop = raw_atr = float("nan")
    if (
        direction not in {"long", "short"}
        or not isfinite(raw_entry) or raw_entry <= 0
        or not isfinite(raw_stop) or raw_stop <= 0
        or not isfinite(raw_atr) or raw_atr <= 0
    ):
        return {"conflict": True, "reason": "INVALID_SL_GUARD_INPUT",
                "source": "Execution input", "level": None}
    entry, stop_loss, atr = raw_entry, raw_stop, raw_atr
    if not _is_correct_side(stop_loss, entry, direction, "sl"):
        return {"conflict": True, "reason": "SL_WRONG_SIDE", "level": entry,
                "source": "Entry", "distance_atr": 0.0}

    clean_structure = _execution_structure(_d(structure))
    # Full-zone semantic guard for active Order Blocks. The invalidation edge is
    # the far edge of the block, not merely the candidate edge used for Entry.
    for ob in clean_structure.get("order_blocks") or []:
        if not isinstance(ob, dict) or ob.get("invalidated") or ob.get("mitigated"):
            continue
        wanted = "bullish" if direction == "long" else "bearish"
        if str(ob.get("type") or "").lower() != wanted:
            continue
        band = ob.get("price_range") or []
        if len(band) < 2:
            continue
        lo, hi = sorted((_f(band[0], 0.0), _f(band[1], 0.0)))
        if not (0 < lo < hi):
            continue
        if direction == "long" and hi >= entry:
            continue
        if direction == "short" and lo <= entry:
            continue
        risk_distance = abs(entry - stop_loss)
        nearest = hi if direction == "long" else lo
        if abs(entry - nearest) > max(risk_distance * 1.75, atr * 4.0):
            continue
        edge = lo if direction == "long" else hi
        clearance = max(atr * 0.16, abs(edge) * 0.0006)
        inside = (stop_loss >= edge - clearance) if direction == "long" else (stop_loss <= edge + clearance)
        if inside:
            return {
                "conflict": True, "reason": "SL_INSIDE_STRONG_REACTION_ZONE",
                "level": round(edge, 12), "source": "Order Block",
                "families": 1, "strength": 4.5,
                "distance_atr": round(abs(stop_loss-edge)/atr, 4),
                "required_clearance_atr": round(clearance/atr, 4),
                "setup_risk_distance_atr": round(risk_distance/atr, 4),
            }

    reaction_universe = _collect_entry_candidates(clean_structure, direction, entry)
    risk_distance = abs(entry - stop_loss)
    best = None
    for lvl in reaction_universe:
        lp = _f(lvl.get("price"), 0.0)
        if lp <= 0:
            continue
        if direction == "long" and lp >= entry:
            continue
        if direction == "short" and lp <= entry:
            continue
        fams, strength = _cluster_evidence(lvl, reaction_universe, atr)
        family = str(lvl.get("family") or "")
        explicit_poi = family in {"smc_poi", "swing", "structure", "value", "dynamic_value", "liquidity"}
        strong = (fams >= 2 and strength >= 3.0) or strength >= 4.5 or (explicit_poi and strength >= 3.0)
        if not strong:
            continue

        clearance = max(atr * (0.12 + 0.02 * min(fams, 4)), abs(lp) * 0.0006)
        stop_to_level = abs(stop_loss - lp)
        entry_to_level = abs(entry - lp)

        # Relevance comes from the setup's own planned risk corridor. A level
        # far deeper than the current invalidation cannot veto this SL merely
        # because it is on the same side of Entry.
        local_stop_radius = max(risk_distance * 0.75, clearance * 2.0)
        local_entry_depth = risk_distance + local_stop_radius
        if stop_to_level > local_stop_radius or entry_to_level > local_entry_depth:
            continue

        if direction == "long":
            inside = stop_loss >= (lp - clearance)
            signed_clearance = (lp - stop_loss) / max(atr, 1e-12)
        else:
            inside = stop_loss <= (lp + clearance)
            signed_clearance = (stop_loss - lp) / max(atr, 1e-12)
        if not inside:
            continue

        distance_atr = stop_to_level / max(atr, 1e-12)
        row = {
            "conflict": True,
            "reason": "SL_INSIDE_STRONG_REACTION_ZONE",
            "level": round(lp, 12),
            "source": str(lvl.get("source") or family or "reaction"),
            "families": int(fams),
            "strength": round(float(strength), 3),
            "distance_atr": round(distance_atr, 4),
            "required_clearance_atr": round(clearance / max(atr, 1e-12), 4),
            "signed_clearance_atr": round(signed_clearance, 4),
            "setup_risk_distance_atr": round(risk_distance / max(atr, 1e-12), 4),
            "local_relevance_radius_atr": round(local_stop_radius / max(atr, 1e-12), 4),
        }
        if best is None or row["distance_atr"] < best["distance_atr"]:
            best = row
    return best or {"conflict": False, "reason": "CLEAR_INVALIDATION"}

def _strategy_family(setup_family: Any) -> str:
    text = str(setup_family or "").upper()
    # Commit 17.3: explicit generic families first so a structure reversal is
    # not accidentally classified as SWEEP and expansion is not forced into
    # BREAKOUT_RETEST.  This changes only price-level specialization.
    if "RSI_TREND" in text or "TREND_CONTINUATION" in text: return "MOMENTUM_CONTINUATION"
    if "MOMENTUM_CONTINUATION" in text or ("MOMENTUM" in text and "CONTINU" in text): return "MOMENTUM_CONTINUATION"
    if "BOLLINGER_SQUEEZE" in text or "COMPRESSION_EXPANSION" in text or "SQUEEZE_EXPANSION" in text: return "COMPRESSION_EXPANSION"
    if "RSI_MAVERICK_REVERSAL" in text: return "MEAN_REVERSION"
    if "SUPERTREND_PULLBACK" in text: return "TREND_PULLBACK"
    if "STRUCTURE_REVERSAL" in text or "TREND_REVERSAL" in text: return "STRUCTURE_REVERSAL"
    if "SWEEP" in text: return "SWEEP_REVERSAL"
    if "BREAK" in text or "RETEST" in text: return "BREAKOUT_RETEST"
    if "MEAN" in text or "VALUE" in text: return "MEAN_REVERSION"
    if "TREND" in text or "PULLBACK" in text: return "TREND_PULLBACK"
    if "REVERS" in text: return "STRUCTURE_REVERSAL"
    if "ROTATION" in text: return "ROTATION"
    return text or "UNSPECIFIED"


def _entry_specialists(candidate, universe, *, direction, current_price, atr,
                       structure, trend, momentum, volatility, setup_family,
                       context, market_type) -> Dict[str, float]:
    p = _f(candidate.get("price"), 0.0)
    if p <= 0 or atr <= 0: return {}
    fam = str(candidate.get("family") or "")
    independent, strength = _cluster_evidence(candidate, universe, atr)

    # 1) Reaction / structure specialist.
    reaction = _clip(32 + strength * 9 + max(0, independent - 1) * 8)
    if fam == "baseline": reaction = max(reaction, 50.0)

    # 2) Smart-money / liquidity specialist.
    smc_ctx = _d(structure.get("smc") or structure.get("smart_money"))
    smc_events = sum(bool(smc_ctx.get(k) or structure.get(k)) for k in ("liquidity_sweep", "sweep", "mss", "bos", "displacement"))
    smc = 45.0 + smc_events * 8.0
    if fam in {"smc_poi", "liquidity", "swing"}: smc += 12.0
    smc = _clip(smc)

    # 3) Strategy specialist: relevance depends on the active setup, not distance.
    setup = _strategy_family(setup_family)
    compat = {
        "SWEEP_REVERSAL": {"smc_poi", "liquidity", "swing", "structure", "fib"},
        "BREAKOUT_RETEST": {"structure", "smc_poi", "dynamic_value", "value"},
        "TREND_PULLBACK": {"smc_poi", "fib", "dynamic_value", "structure", "value"},
        "MEAN_REVERSION": {"value", "dynamic_value", "structure", "fib", "swing"},
        "ROTATION": {"value", "structure", "dynamic_value"},
        "MOMENTUM_CONTINUATION": {"dynamic_value", "structure", "smc_poi", "swing", "value", "recent_reaction", "volatility_reaction"},
        "COMPRESSION_EXPANSION": {"structure", "smc_poi", "dynamic_value", "value", "swing", "recent_reaction", "volatility_reaction"},
        "STRUCTURE_REVERSAL": {"smc_poi", "structure", "swing", "fib", "liquidity", "dynamic_value", "recent_reaction"},
    }
    strategy = 62.0 if fam in compat.get(setup, set()) else 50.0
    if fam == "baseline": strategy = 54.0

    # 4) Reachability/timing specialist. It estimates fill probability only;
    # it does not say that near or deep is intrinsically better.
    d_atr = abs(current_price - p) / max(atr, 1e-12)
    activity = _f(context.get("activity_score"), 50.0)
    tf = str(context.get("timeframe") or "")
    horizon = {"30m":1.35,"1h":1.55,"2h":1.75,"4h":2.05,"12h":2.5,"1D":3.0,"1W":3.4}.get(tf, 2.0)
    horizon *= 0.80 + activity / 250.0
    reach = _clip(100.0 - max(0.0, d_atr - 0.15) / max(horizon, 0.25) * 58.0)
    # A chased/extended current price can make an immediate entry less safe.
    extension = str(_d(trend).get("direction") or "").lower()
    if d_atr < 0.18 and setup in {"TREND_PULLBACK", "MEAN_REVERSION", "SWEEP_REVERSAL"}:
        reach = min(reach, 78.0)

    # 5) Volatility/noise specialist.
    shock = _f(context.get("shock_score"), 0.0)
    noise = 76.0
    if d_atr < 0.18 and shock >= 65: noise -= 24.0
    if d_atr > horizon * 1.15: noise -= 18.0
    noise = _clip(noise)

    # 6) Flow/value specialist. Abstains softly when unavailable.
    flow = 50.0
    if fam in {"value", "dynamic_value"}: flow += 20.0
    if fam in {"liquidation", "liquidity"}: flow += 12.0
    volume = _d(structure.get("volume_profile"))
    if volume: flow += 6.0
    if _d(structure.get("order_flow") or structure.get("orderflow") or structure.get("microstructure")): flow += 8.0
    flow = _clip(flow)

    # 7) Context/market specialist: dynamic activity/macro modifies confidence,
    # never selects a price only because of weekday/session.
    context_score = 68.0
    macro = str(context.get("macro_risk") or "UNKNOWN")
    if macro == "CRITICAL": context_score -= 28.0
    elif macro == "HIGH": context_score -= 12.0
    if shock >= 85 and d_atr < 0.20: context_score -= 10.0
    if market_type == "spot": context_score += 3.0
    context_score = _clip(context_score)

    # 17.5.8 — historical priors are a small ranking lens, never authority.
    # Exact family/cell evidence and the execution-route study can add only a
    # bounded soft contribution. Missing/stale evidence is neutral (50).
    backtest_score = 50.0
    try:
        if callable(_bt_entry_component_prior):
            ep = _bt_entry_component_prior(
                timeframe=context.get("timeframe"), candidate_family=fam,
                smc_events=smc_events,
            ) or {}
            backtest_score = float(ep.get("score") or 50.0)
        if callable(_bt_family_cell_prior):
            fp = _bt_family_cell_prior(
                market=market_type, symbol=context.get("symbol"),
                timeframe=context.get("timeframe"),
                action="LONG" if direction == "long" else "SHORT",
                family=setup_family,
            ) or {}
            strategy = _clip(strategy + float(fp.get("adjustment") or 0.0))
            backtest_score = max(backtest_score, float(fp.get("score") or 50.0))
    except Exception:
        backtest_score = 50.0

    scores = {
        "reaction": reaction, "smc": smc, "strategy": strategy,
        "reachability": reach, "volatility": noise, "flow": flow,
        "context": context_score, "backtest_prior": _clip(backtest_score),
    }

    # COMMIT 17.5.11R — validated execution route (ranker only).
    # Historical execution-forensics were split chronologically 70/30 before
    # promotion. LIQUIDITY_SWEEP_MSS_POI passed the stricter hit-efficiency +
    # expectancy test only on 30m: IS +0.859R (7 TP / 4 SL) and OOS +1.800R
    # (5 TP / 0 SL). 1h kept slightly positive expectancy but failed the user's
    # TP-vs-SL efficiency objective (OOS 2 TP / 7 SL), 2h failed OOS, and 4h
    # has N too small. Those timeframes receive NO production ranking lift.
    # This specialist never creates direction, never changes Safety/RR gates,
    # and is omitted (not scored neutral) when the exact observed route is
    # absent or the market/timeframe is outside validated scope.
    _tf = str(context.get("timeframe") or "").lower()
    _market = str(market_type or "").lower()
    _has_sweep = bool(
        smc_ctx.get("liquidity_sweep") or smc_ctx.get("sweep")
        or structure.get("liquidity_sweep") or structure.get("sweep")
    )
    _has_shift = bool(
        smc_ctx.get("mss") or smc_ctx.get("bos")
        or structure.get("mss") or structure.get("bos")
    )
    _has_displacement = bool(
        smc_ctx.get("displacement") or structure.get("displacement")
    )
    _poi_candidate = fam in {"smc_poi", "liquidity", "swing", "structure"}
    if (
        _market == "futures"
        and _tf == "30m"
        and _has_sweep
        and (_has_shift or _has_displacement)
        and _poi_candidate
    ):
        scores["validated_liquidity_route"] = 88.0

    return scores


def _sl_specialists(candidate, universe, *, direction, entry, tp_hint, atr,
                    structure, setup_family, context, market_type,
                    leverage_hint: float = 1.0) -> Dict[str, float]:
    p = _f(candidate.get("price"), 0.0)
    if p <= 0 or atr <= 0: return {}
    d_atr = abs(entry - p) / max(atr, 1e-12)
    independent, strength = _cluster_evidence(candidate, universe, atr)
    anchor = _f(candidate.get("anchor"), 0.0)

    # Invalidation specialist: candidate created behind a real anchor receives
    # stronger evidence than a distance-only baseline.
    invalidation = 48.0 + strength * 8.0 + max(0, independent - 1) * 5.0
    if candidate.get("family") in {"structural_invalidation","recent_invalidation","volatility_invalidation"}: invalidation += 12.0
    if anchor > 0: invalidation += 7.0
    invalidation = _clip(invalidation)

    # Noise specialist: derives from observed activity instead of fixed TF sweet spots.
    activity = _f(context.get("activity_score"), 50.0)
    shock = _f(context.get("shock_score"), 0.0)
    expected_noise = 0.65 + activity / 140.0 + shock / 260.0
    noise = _clip(82.0 - abs(d_atr - expected_noise) * 27.0)
    # Too tight is more dangerous than somewhat wide; risk specialist handles width.
    if d_atr < expected_noise * 0.65: noise -= 22.0
    noise = _clip(noise)

    # Reaction-collision specialist checks whether SL lies inside another strong
    # reaction cluster rather than merely "how far" it is.
    reaction_universe = _collect_entry_candidates(structure, direction, entry)
    collision = 92.0
    for lvl in reaction_universe:
        lp = _f(lvl.get("price"), 0.0)
        if lp <= 0: continue
        fams, st = _cluster_evidence(lvl, reaction_universe, atr)
        radius = max(atr * (0.18 + 0.04 * min(fams, 3)), abs(lp) * 0.0008)
        if abs(p - lp) <= radius and st >= 3.0:
            collision -= min(62.0, 16.0 + st * 7.0 + fams * 5.0)
    collision = _clip(collision)
    hard_conflict = evaluate_sl_reaction_conflict(
        structure=structure, direction=direction, entry=entry, stop_loss=p, atr=atr
    )
    if hard_conflict.get("conflict"):
        collision = 0.0

    # Liquidity/stop-hunt specialist: just beyond swing/liquidity is preferred
    # over exactly on it, but does not demand a universal distance.
    liquidity = 62.0
    if candidate.get("family") in {"structural_invalidation","recent_invalidation","volatility_invalidation"}: liquidity += 15.0
    if anchor > 0 and abs(p - anchor) >= atr * 0.10: liquidity += 8.0
    liquidity = _clip(liquidity)

    # Risk/economics specialist.  For derivatives the SL is also ranked by
    # the approximate margin impact at the leverage that the volatility engine
    # is currently considering.  This is a ranking input only: it cannot veto
    # the LONG/SHORT thesis and the canonical leverage engine still runs later.
    risk = 78.0
    if tp_hint and _f(tp_hint) > 0:
        rr = abs(_f(tp_hint) - entry) / max(abs(entry - p), 1e-12)
        if rr < 1.4: risk -= 45.0
        elif rr < 1.8: risk -= 24.0
        elif rr <= 3.5: risk += 8.0
        elif rr > 5.0: risk -= 10.0
    if d_atr > 4.0: risk -= 28.0
    lev = 1.0 if str(market_type).lower() == "spot" else max(1.0, min(100.0, _f(leverage_hint, 1.0)))
    risk_move_pct = abs(entry - p) / max(abs(entry), 1e-12) * 100.0
    margin_loss_pct = risk_move_pct * lev
    # Prefer a technically valid invalidation whose leveraged loss is material
    # but not excessive.  Position sizing remains responsible for account risk.
    if str(market_type).lower() in {"futures", "multiasset"}:
        if margin_loss_pct <= 12.0:
            risk += 8.0
        elif margin_loss_pct <= 18.0:
            risk += 2.0
        elif margin_loss_pct <= 25.0:
            risk -= 12.0
        else:
            risk -= min(38.0, 16.0 + (margin_loss_pct - 25.0) * 0.8)
    risk = _clip(risk)

    # Strategy specialist: reversals need invalidation beyond the extreme;
    # breakouts need the reclaimed/broken structure to fail.
    setup = _strategy_family(setup_family)
    strategy = 68.0
    if setup in {"SWEEP_REVERSAL", "MEAN_REVERSION"} and anchor > 0: strategy += 8.0
    if setup in {"BREAKOUT_RETEST", "TREND_PULLBACK", "MOMENTUM_CONTINUATION", "COMPRESSION_EXPANSION"} and candidate.get("family") in {"structural_invalidation","recent_invalidation","volatility_invalidation"}: strategy += 8.0
    if setup == "STRUCTURE_REVERSAL" and candidate.get("family") in {"structural_invalidation","recent_invalidation"} and anchor > 0: strategy += 10.0
    strategy = _clip(strategy)

    backtest_score = 50.0
    try:
        if callable(_bt_sl_component_prior):
            sp = _bt_sl_component_prior(
                timeframe=context.get("timeframe"),
                reaction_conflict=bool(hard_conflict.get("conflict")),
            ) or {}
            backtest_score = float(sp.get("score") or 50.0)
    except Exception:
        backtest_score = 50.0

    return {"invalidation":invalidation,"noise":noise,"reaction_collision":collision,
            "liquidity":liquidity,"risk":risk,"strategy":strategy,
            "backtest_prior":_clip(backtest_score)}


def _path_barrier_score(tp: float, entry: float, direction: str, structure: Dict[str, Any], atr: float, liquidation=None) -> float:
    targets = _collect_tp_candidates(structure, direction, entry, tp, atr, liquidation=liquidation)
    penalty = 0.0
    for row in targets:
        p = _f(row.get("price"), 0.0)
        if p <= 0 or abs(p - tp) <= atr * 0.12: continue
        between = entry < p < tp if direction == "long" else entry > p > tp
        if not between: continue
        fams, st = _cluster_evidence(row, targets, atr)
        if st >= 3.0 and fams >= 2:
            penalty += min(24.0, 5.0 + st * 2.5 + fams * 3.0)
    return _clip(100.0 - min(75.0, penalty))


def _tp_specialists(candidate, universe, *, direction, entry, sl, atr, structure,
                    trend, momentum, volatility, setup_family, context, market_type,
                    liquidation=None, leverage_hint: float = 1.0) -> Dict[str, float]:
    p = _f(candidate.get("price"), 0.0)
    if p <= 0 or atr <= 0: return {}
    d_atr = abs(p - entry) / max(atr, 1e-12)
    independent, strength = _cluster_evidence(candidate, universe, atr)

    target = _clip(34.0 + strength * 8.5 + max(0, independent-1) * 7.0)
    if candidate.get("family") in {"liquidity_target", "swing_target", "opposing_poi", "structure_target", "projected_target", "volatility_target"}: target += 8.0
    target = _clip(target)

    path = _path_barrier_score(p, entry, direction, structure, atr, liquidation=liquidation)

    # Touch probability specialist combines distance with actual market state.
    activity = _f(context.get("activity_score"), 50.0)
    shock = _f(context.get("shock_score"), 0.0)
    regime = str(context.get("market_regime") or "").upper()
    trend_dir = str(_d(trend).get("direction") or "").lower()
    aligned = (direction == "long" and "bull" in trend_dir) or (direction == "short" and "bear" in trend_dir)
    capacity = 1.5 + activity / 90.0 + (0.35 if aligned else 0.0)
    if "TREND" in regime: capacity += 0.35
    if shock >= 80: capacity += 0.25
    touch = _clip(100.0 - max(0.0, d_atr - 0.35) / max(capacity, 0.5) * 72.0)

    # Momentum continuation specialist can support a farther TP when the path is
    # clean; exhaustion can prefer a nearer capture. It never hardcodes distance.
    mom_dir = str(_d(momentum).get("direction") or "").lower()
    mom_aligned = (direction == "long" and "bull" in mom_dir) or (direction == "short" and "bear" in mom_dir)
    continuation = 68.0 + (14.0 if mom_aligned else -6.0)
    if path < 55: continuation -= 14.0
    continuation = _clip(continuation)

    # Economics specialist: profitable AND realistic.  For derivatives the
    # committee also asks whether the expected price move is economically
    # meaningful at the *indicative* leverage already produced by volatility.
    # This does not force leverage and cannot create/veto a directional signal.
    rr = abs(p - entry) / max(abs(entry - sl), 1e-12)
    economics = 88.0
    if rr < 1.3: economics = 20.0
    elif rr < 1.8: economics = 48.0
    elif rr <= 3.5: economics = 92.0
    elif rr <= 4.5: economics = 80.0
    else: economics = 55.0
    lev = 1.0 if str(market_type).lower() == "spot" else max(1.0, min(100.0, _f(leverage_hint, 1.0)))
    reward_move_pct = abs(p - entry) / max(abs(entry), 1e-12) * 100.0
    risk_move_pct = abs(entry - sl) / max(abs(entry), 1e-12) * 100.0
    margin_reward_pct = reward_move_pct * lev
    margin_risk_pct = risk_move_pct * lev
    if str(market_type).lower() in {"futures", "multiasset"}:
        min_margin_roi = max(3.0, _f(context.get("min_margin_roi_pct"), 5.0))
        if margin_reward_pct < min_margin_roi:
            economics -= min(36.0, 12.0 + (min_margin_roi - margin_reward_pct) * 5.0)
        elif margin_reward_pct <= 18.0:
            economics += 6.0
        elif margin_reward_pct > 45.0:
            # Very distant targets can look attractive only because leverage
            # magnifies ROI; touch/path specialists must remain dominant.
            economics -= 8.0
        if margin_risk_pct > 25.0:
            economics -= min(20.0, 6.0 + (margin_risk_pct - 25.0) * 0.5)
        economics = _clip(economics)

    setup = _strategy_family(setup_family)
    strategy = 68.0
    if setup in {"BREAKOUT_RETEST", "TREND_PULLBACK", "MOMENTUM_CONTINUATION", "COMPRESSION_EXPANSION"} and candidate.get("family") in {"liquidity_target","swing_target","fib_target"}: strategy += 8.0
    if setup in {"SWEEP_REVERSAL", "MEAN_REVERSION", "STRUCTURE_REVERSAL"} and candidate.get("family") in {"value_target","structure_target","capture_before_reaction","opposing_poi"}: strategy += 8.0
    strategy = _clip(strategy)

    context_score = 72.0
    if str(context.get("macro_risk") or "") == "CRITICAL": context_score -= 24.0
    if shock >= 85 and path < 60: context_score -= 10.0
    context_score = _clip(context_score)

    backtest_score = 50.0
    try:
        if callable(_bt_tp_component_prior):
            tp_prior = _bt_tp_component_prior(
                timeframe=context.get("timeframe"), candidate_rr=rr,
            ) or {}
            backtest_score = float(tp_prior.get("score") or 50.0)
    except Exception:
        backtest_score = 50.0

    return {"target":target,"path":path,"touch_probability":touch,
            "continuation":continuation,"economics":economics,
            "strategy":strategy,"context":context_score,
            "backtest_prior":_clip(backtest_score)}


def _weights_for(role: str, market_type: str) -> Dict[str, float]:
    market = str(market_type or "spot").lower()
    if role == "entry":
        # Spot is slightly more tolerant; derivatives demand reaction + fill quality.
        base = {"reaction":1.25,"smc":1.20,"strategy":1.05,"reachability":1.15,
                "volatility":0.85,"flow":0.85,"context":0.75,"backtest_prior":0.0,
                "validated_liquidity_route":0.90}
        if market in {"futures","multiasset"}:
            base.update({"reaction":1.35,"smc":1.30,"reachability":1.25,"volatility":1.0})
        return base
    if role == "sl":
        base = {"invalidation":1.35,"noise":1.05,"reaction_collision":1.25,
                "liquidity":1.0,"risk":1.15,"strategy":0.9,"backtest_prior":0.0}
        if market == "spot": base["risk"] = 1.0
        return base
    return {"target":1.20,"path":1.25,"touch_probability":1.25,
            "continuation":0.95,"economics":1.25,"strategy":0.9,"context":0.7,
            "backtest_prior":0.0}


def _harmonic(values: Iterable[float]) -> Optional[float]:
    vals=[max(1.0, min(100.0, float(v))) for v in values if v is not None]
    if not vals:
        return None
    return len(vals) / sum(1.0/v for v in vals)


def _score_candidate(scores: Dict[str, float], weights: Dict[str, float], role: str = "") -> Tuple[float, float]:
    pairs = [(scores[k], weights.get(k, 1.0)) for k in scores if k in weights]
    agg = _weighted_mean(pairs)
    if agg is None: return 0.0, 0.0
    # 17.5.11: a zero-authority/shadow specialist must not affect either the
    # weighted mean OR the agreement term. This prevents N-small historical
    # priors from silently changing live Entry/SL/TP ranking.
    agreement_values = [scores[k] for k in scores if float(weights.get(k, 0.0)) > 0.0]
    agree = _consensus(agreement_values)

    # Each committee has a small set of indispensable specialist dimensions.
    # Harmonic synthesis prevents one excellent opinion from hiding a very weak
    # one, without introducing a near/deep/close/far price rule.
    if role == "entry":
        core = _harmonic([scores.get("reaction"), scores.get("reachability"), scores.get("strategy")])
        final = (core or agg) * 0.62 + agg * 0.28 + agree * 0.10
    elif role == "sl":
        core = _harmonic([scores.get("invalidation"), scores.get("noise"), scores.get("reaction_collision"), scores.get("risk")])
        final = (core or agg) * 0.68 + agg * 0.24 + agree * 0.08
    elif role == "tp":
        core = _harmonic([scores.get("target"), scores.get("path"), scores.get("touch_probability"), scores.get("economics")])
        final = (core or agg) * 0.72 + agg * 0.22 + agree * 0.06
    else:
        final = agg * 0.88 + agree * 0.12
    return _clip(final), agree


def _rank_candidates(candidates: List[Dict[str, Any]], scorer,
                     weights: Dict[str, float], predicate,
                     role: str = "") -> List[Dict[str, Any]]:
    """Rank all admissible candidates for one execution role.

    Commit 17.1 keeps the specialist committees as *price selectors*.  The
    ranking is internal and does not change LONG/SHORT thesis, Safety or
    publication thresholds.
    """
    ranked: List[Dict[str, Any]] = []
    for c in candidates:
        p = _f(c.get("price"), 0.0)
        if p <= 0 or not predicate(p):
            continue
        scores = scorer(c)
        total, consensus = _score_candidate(scores, weights, role=role)
        row = dict(c)
        row["committee_score"] = round(total, 2)
        row["consensus"] = round(consensus, 2)
        row["specialist_scores"] = {k: round(v, 2) for k, v in scores.items()}
        ranked.append(row)
    ranked.sort(key=lambda r: (r["committee_score"], r["consensus"]), reverse=True)
    return ranked


def _choose(candidates: List[Dict[str, Any]], scorer,
            weights: Dict[str, float], predicate,
            role: str = "") -> Optional[Dict[str, Any]]:
    ranked = _rank_candidates(candidates, scorer, weights, predicate, role=role)
    return ranked[0] if ranked else None


def _rr_quality(rr: float, floor: float, ceiling: float,
                preferred_min: float, preferred_max: float) -> float:
    """Describe economic fit without fabricating levels.

    Only combinations already inside the existing technical R/R interval reach
    this function.  It merely prefers the central working band; it never lowers
    the deployed floor/ceiling.
    """
    rr = _f(rr, 0.0)
    floor = max(0.01, _f(floor, 1.8))
    ceiling = max(floor, _f(ceiling, 4.5))
    preferred_min = max(floor, _f(preferred_min, 2.0))
    preferred_max = min(ceiling, max(preferred_min, _f(preferred_max, 3.2)))
    if rr < floor or rr > ceiling:
        return 0.0
    if preferred_min <= rr <= preferred_max:
        return 100.0
    if rr < preferred_min:
        span = max(0.01, preferred_min - floor)
        return _clip(62.0 + 38.0 * (rr - floor) / span)
    span = max(0.01, ceiling - preferred_max)
    return _clip(62.0 + 38.0 * (ceiling - rr) / span)


def _joint_geometry_score(entry_row: Dict[str, Any], sl_row: Dict[str, Any],
                          tp_row: Dict[str, Any], rr: float,
                          rr_floor: float, rr_ceiling: float,
                          preferred_rr_min: float,
                          preferred_rr_max: float) -> float:
    """Score the *combination*, not another trading thesis.

    A high Entry score cannot hide a poor SL/TP and vice versa.  The harmonic
    core keeps all three roles relevant, while the existing R/R interval acts
    only as an economic compatibility check.
    """
    role_scores = [
        _f(entry_row.get("committee_score"), 0.0),
        _f(sl_row.get("committee_score"), 0.0),
        _f(tp_row.get("committee_score"), 0.0),
    ]
    core = _harmonic(role_scores) or 0.0
    mean = sum(role_scores) / 3.0 if role_scores else 0.0
    rr_score = _rr_quality(
        rr, rr_floor, rr_ceiling, preferred_rr_min, preferred_rr_max
    )
    return _clip(core * 0.56 + mean * 0.31 + rr_score * 0.13)


def coordinate_execution_committees(*, baseline_entry: float, baseline_sl: float,
                                    baseline_tp: float, direction: str,
                                    current_price: float, atr: float,
                                    structure=None, trend=None, momentum=None,
                                    volatility=None, setup_family=None, liquidation=None,
                                    market_type="spot", symbol=None, timeframe=None,
                                    execution_context=None,
                                    rr_floor: float = 1.8,
                                    rr_ceiling: float = 4.5,
                                    preferred_rr_min: float = 2.0,
                                    preferred_rr_max: float = 3.2,
                                    leverage_hint: float = 1.0,
                                    candidate_filter=None) -> Dict[str, Any]:
    """Coordinate Entry, SL and TP without becoming a second signal committee.

    Commit 17.1 responsibilities are intentionally narrow:
      * the trading thesis/direction already exists before this function;
      * Entry committee ranks prices for that thesis;
      * SL committee ranks invalidation prices for each viable Entry;
      * TP committee ranks structural targets for each Entry+SL pair;
      * a bounded reconciliation pass chooses the best *joint* geometry that
        already respects the deployed technical R/R interval.

    If no improved/coherent combination exists, the caller MUST preserve the
    audited 17.5.1 baseline instead of treating this helper as a veto.  This
    function is a bounded execution refiner, never a signal generator.
    """
    structure, trend, momentum, volatility = (
        _d(structure), _d(trend), _d(momentum), _d(volatility)
    )
    structure = _execution_structure(structure)
    context = dict(_d(execution_context))
    context.setdefault("market_type", str(market_type or "spot").lower())
    context.setdefault("symbol", str(symbol or ""))
    context.setdefault("timeframe", str(timeframe or ""))
    market = str(market_type or "spot").lower()
    direction = str(direction or "").lower()
    if direction not in {"long", "short"} or not all(
            _f(value) > 0 for value in (baseline_entry, baseline_sl, baseline_tp, current_price, atr)):
        return {"success": False, "reason": "INVALID_REFINEMENT_INPUT",
                "version": VERSION, "fallback_to_baseline": True}
    leverage_hint = 1.0 if market == "spot" else max(1.0, min(100.0, _f(leverage_hint, 1.0)))
    context.setdefault("leverage_hint", round(leverage_hint, 4))
    current_price = _f(current_price, 0.0)
    atr = max(_f(atr, 0.0), abs(current_price) * 1e-6, 1e-12)

    rr_floor = max(1.0, _f(rr_floor, 1.8))
    rr_ceiling = max(rr_floor, _f(rr_ceiling, 4.5))
    preferred_rr_min = max(rr_floor, _f(preferred_rr_min, 2.0))
    preferred_rr_max = min(
        rr_ceiling,
        max(preferred_rr_min, _f(preferred_rr_max, 3.2)),
    )

    # ENTRY ---------------------------------------------------------------
    # The existing anti-chase contract is retained: LONG entry is at/below
    # current price; SHORT entry is at/above current price.  Breakout setups
    # are expected to arrive here *after* confirmation, so Entry searches the
    # retest/reaction zone and never acts as a breakout trigger.
    entry_candidates = _collect_entry_candidates(
        structure, direction, _f(baseline_entry), liquidation=liquidation
    )
    _add_execution_recovery_entry_candidates(
        entry_candidates, structure=structure, direction=direction,
        current_price=current_price, atr=atr,
    )
    entry_ranked = _rank_candidates(
        entry_candidates,
        lambda c: _entry_specialists(
            c, entry_candidates, direction=direction,
            current_price=current_price, atr=atr, structure=structure,
            trend=trend, momentum=momentum, volatility=volatility,
            setup_family=setup_family, context=context, market_type=market,
        ),
        _weights_for("entry", market),
        lambda p: _is_correct_side(p, current_price, direction, "entry"),
        role="entry",
    )
    if not entry_ranked:
        return {
            "success": False,
            "reason": "NO_STRUCTURAL_ENTRY_IMPROVEMENT",
            "version": VERSION,
            "fallback_to_baseline": True,
        }

    # 17.5.2 baseline benchmark.  The committee is allowed to replace the
    # deployed geometry only when it can score the complete alternative against
    # the same specialist roles.  The baseline remains authoritative if the
    # comparison cannot be made.
    baseline_geometry_quality = None
    try:
        be = _f(baseline_entry, 0.0)
        bs = _f(baseline_sl, 0.0)
        bt = _f(baseline_tp, 0.0)
        baseline_risk = abs(be - bs)
        baseline_rr = abs(bt - be) / max(baseline_risk, 1e-12)
        if (
            be > 0 and bs > 0 and bt > 0 and baseline_risk > 0
            and rr_floor <= baseline_rr <= rr_ceiling
            and _is_correct_side(be, current_price, direction, "entry")
            and _is_correct_side(bs, be, direction, "sl")
            and _is_correct_side(bt, be, direction, "tp")
        ):
            # Score the same object as the candidate search: same family,
            # merged confluences and exclusion of itself from its cluster.
            be_row = next(row for row in entry_candidates if row['price'] == be)
            be_scores = _entry_specialists(
                be_row, entry_candidates, direction=direction,
                current_price=current_price, atr=atr, structure=structure,
                trend=trend, momentum=momentum, volatility=volatility,
                setup_family=setup_family, context=context, market_type=market,
            )
            be_score, be_consensus = _score_candidate(be_scores, _weights_for("entry", market), role="entry")
            be_row.update({"scores": be_scores, "committee_score": round(be_score, 2), "consensus": be_consensus})

            base_sl_candidates = _collect_sl_candidates(
                structure, direction, be, bs, atr, _f(context.get("activity_score"), 50.0)
            )
            _add_execution_recovery_sl_candidates(
                base_sl_candidates, structure=structure, direction=direction,
                entry=be, atr=atr, activity=_f(context.get("activity_score"), 50.0),
            )
            bs_row = next(row for row in base_sl_candidates if row['price'] == bs)
            bs_scores = _sl_specialists(
                bs_row, base_sl_candidates, direction=direction, entry=be,
                tp_hint=bt, atr=atr, structure=structure, setup_family=setup_family,
                context=context, market_type=market, leverage_hint=leverage_hint,
            )
            bs_score, bs_consensus = _score_candidate(bs_scores, _weights_for("sl", market), role="sl")
            bs_row.update({"scores": bs_scores, "committee_score": round(bs_score, 2), "consensus": bs_consensus})

            base_tp_candidates = _collect_tp_candidates(
                structure, direction, be, bt, atr, liquidation=liquidation
            )
            bt_row = next(row for row in base_tp_candidates if row['price'] == bt)
            bt_scores = _tp_specialists(
                bt_row, base_tp_candidates, direction=direction, entry=be, sl=bs,
                atr=atr, structure=structure, trend=trend, momentum=momentum,
                volatility=volatility, setup_family=setup_family, context=context,
                market_type=market, liquidation=liquidation, leverage_hint=leverage_hint,
            )
            bt_score, bt_consensus = _score_candidate(bt_scores, _weights_for("tp", market), role="tp")
            bt_row.update({"scores": bt_scores, "committee_score": round(bt_score, 2), "consensus": bt_consensus})
            baseline_geometry_quality = round(_joint_geometry_score(
                be_row, bs_row, bt_row, baseline_rr, rr_floor, rr_ceiling,
                preferred_rr_min, preferred_rr_max,
            ), 2)
    except Exception:
        baseline_geometry_quality = None

    # Bounded search: enough alternatives to reconcile geometry while keeping
    # CPU/RAM deterministic and tiny.  No I/O is introduced.
    best_combo: Optional[Dict[str, Any]] = None
    admissibility_rejections = 0
    sl_reaction_rejections = 0
    entry_limit = min(7, len(entry_ranked))

    for entry_rank, entry_row in enumerate(entry_ranked[:entry_limit]):
        entry_price = _f(entry_row.get("price"), 0.0)
        if entry_price <= 0:
            continue

        _activity = _f(context.get("activity_score"), 50.0)
        sl_candidates = _collect_sl_candidates(
            structure, direction, entry_price, _f(baseline_sl), atr, _activity,
        )
        _add_execution_recovery_sl_candidates(
            sl_candidates, structure=structure, direction=direction, entry=entry_price,
            atr=atr, activity=_activity,
        )
        # 17.5.6: score cannot compensate a semantic contradiction.  A stop
        # that still sits inside a strong reaction zone for the thesis is not
        # a valid invalidation candidate.  Keep the baseline benchmark for
        # comparison, but never select a conflicting SL as the refined winner.
        filtered_sl_candidates = []
        for _sl_row in sl_candidates:
            _sl_check = evaluate_sl_reaction_conflict(
                structure=structure, direction=direction, entry=entry_price,
                stop_loss=_f(_sl_row.get("price"), 0.0), atr=atr,
            )
            if _sl_check.get("conflict"):
                sl_reaction_rejections += 1
                continue
            filtered_sl_candidates.append(_sl_row)
        sl_candidates = filtered_sl_candidates
        sl_ranked = _rank_candidates(
            sl_candidates,
            lambda c: _sl_specialists(
                c, sl_candidates, direction=direction, entry=entry_price,
                tp_hint=_f(baseline_tp), atr=atr, structure=structure,
                setup_family=setup_family, context=context, market_type=market,
                leverage_hint=leverage_hint,
            ),
            _weights_for("sl", market),
            lambda p: _is_correct_side(p, entry_price, direction, "sl"),
            role="sl",
        )
        if not sl_ranked:
            continue

        for sl_rank, sl_row in enumerate(sl_ranked[:min(8, len(sl_ranked))]):
            sl_price = _f(sl_row.get("price"), 0.0)
            risk = abs(entry_price - sl_price)
            if risk <= 0:
                continue

            tp_candidates = _collect_tp_candidates(
                structure, direction, entry_price, _f(baseline_tp), atr,
                liquidation=liquidation,
            )
            _add_execution_recovery_tp_candidates(
                tp_candidates, direction=direction, entry=entry_price, sl=sl_price, atr=atr,
                rr_floor=rr_floor, preferred_rr_min=preferred_rr_min,
                preferred_rr_max=preferred_rr_max,
            )
            tp_ranked = _rank_candidates(
                tp_candidates,
                lambda c: _tp_specialists(
                    c, tp_candidates, direction=direction, entry=entry_price,
                    sl=sl_price, atr=atr, structure=structure, trend=trend,
                    momentum=momentum, volatility=volatility,
                    setup_family=setup_family, context=context,
                    market_type=market, liquidation=liquidation,
                    leverage_hint=leverage_hint,
                ),
                _weights_for("tp", market),
                lambda p: _is_correct_side(p, entry_price, direction, "tp"),
                role="tp",
            )
            if not tp_ranked:
                continue

            for tp_rank, tp_row in enumerate(tp_ranked[:min(12, len(tp_ranked))]):
                tp_price = _f(tp_row.get("price"), 0.0)
                reward = abs(tp_price - entry_price)
                rr = reward / max(risk, 1e-12)

                # Existing economics are preserved exactly: committees may
                # search alternatives, but never lower the deployed R/R floor
                # or raise its technical ceiling to force a signal.
                if rr < rr_floor or rr > rr_ceiling:
                    continue

                joint = _joint_geometry_score(
                    entry_row, sl_row, tp_row, rr,
                    rr_floor, rr_ceiling,
                    preferred_rr_min, preferred_rr_max,
                )

                combo = {
                    "joint_score": round(joint, 2),
                    "risk_reward": round(rr, 4),
                    "entry": entry_price,
                    "stop_loss": sl_price,
                    "take_profit": tp_price,
                    "entry_committee": entry_row,
                    "sl_committee": sl_row,
                    "tp_committee": tp_row,
                    "ranks": {
                        "entry": entry_rank + 1,
                        "sl": sl_rank + 1,
                        "tp": tp_rank + 1,
                    },
                }
                # Search among admissible alternatives, instead of selecting
                # an out-of-bounds winner and discarding all runners-up later.
                # The caller owns these unchanged policy limits and rechecks
                # the winner before replacing its baseline.
                if candidate_filter is not None:
                    proposal = {
                        **combo, "geometry_quality": combo["joint_score"],
                        "baseline_geometry_quality": baseline_geometry_quality,
                        "geometry_improvement": (round(combo["joint_score"] - baseline_geometry_quality, 2)
                                                 if baseline_geometry_quality is not None else None),
                        "entry_quality": entry_row["committee_score"],
                        "sl_quality": sl_row["committee_score"],
                        "tp_quality": tp_row["committee_score"],
                    }
                    try:
                        admissible = candidate_filter(proposal) is True
                    except Exception:
                        return {"success": False, "reason": "REFINEMENT_GUARD_ERROR",
                                "version": VERSION, "fallback_to_baseline": True}
                    if not admissible:
                        admissibility_rejections += 1
                        continue
                if (
                    best_combo is None
                    or combo["joint_score"] > best_combo["joint_score"]
                    or (
                        combo["joint_score"] == best_combo["joint_score"]
                        and abs(combo["risk_reward"] - 2.6)
                        < abs(best_combo["risk_reward"] - 2.6)
                    )
                ):
                    best_combo = combo

    if best_combo is None:
        return {
            "success": False,
            "reason": "NO_COHERENT_STRUCTURAL_GEOMETRY_IMPROVEMENT",
            "version": VERSION,
            "fallback_to_baseline": True,
            "admissibility_rejections": admissibility_rejections,
            "sl_reaction_rejections": sl_reaction_rejections,
        }

    entry_row = best_combo["entry_committee"]
    sl_row = best_combo["sl_committee"]
    tp_row = best_combo["tp_committee"]

    # Committee scores remain internal selection diagnostics.  The caller keeps
    # the established legacy Entry/SL/TP quality scale for Safety/ReviewTrader/
    # Publication, preventing Commit 16 from silently changing those thresholds.
    return {
        "success": True,
        "admissibility_rejections": admissibility_rejections,
        "sl_reaction_rejections": sl_reaction_rejections,
        "version": VERSION,
        "market_type": market,
        "entry": best_combo["entry"],
        "stop_loss": best_combo["stop_loss"],
        "take_profit": best_combo["take_profit"],
        "risk_reward": best_combo["risk_reward"],
        "indicative_leverage": round(leverage_hint, 2),
        "geometry_quality": best_combo["joint_score"],
        "baseline_geometry_quality": baseline_geometry_quality,
        "geometry_improvement": (
            round(best_combo["joint_score"] - baseline_geometry_quality, 2)
            if baseline_geometry_quality is not None else None
        ),
        "entry_quality": round(_f(entry_row.get("committee_score")), 2),
        "sl_quality": round(_f(sl_row.get("committee_score")), 2),
        "tp_quality": round(_f(tp_row.get("committee_score")), 2),
        "reconciled": True,
        "ranks": best_combo["ranks"],
        "entry_committee": entry_row,
        "sl_committee": sl_row,
        "tp_committee": tp_row,
        "recovery_mode": best_combo.get("recovery_mode", "STRUCTURAL_COMMITTEE_SELECTION"),
    }


def recover_execution_geometry_from_structure(*, direction: str, current_price: float,
                                               atr: float, structure=None, trend=None,
                                               momentum=None, volatility=None,
                                               setup_family=None, liquidation=None,
                                               market_type="futures", symbol=None,
                                               timeframe=None, execution_context=None,
                                               entry_hint: float = 0.0,
                                               rr_floor: float = 1.8,
                                               rr_ceiling: float = 4.5,
                                               preferred_rr_min: float = 2.0,
                                               preferred_rr_max: float = 3.2,
                                               leverage_hint: float = 1.0,
                                               candidate_filter=None) -> Dict[str, Any]:
    """17.5.9 structural opportunity recovery when baseline geometry is missing/bad.

    This is intentionally *not* a looser execution path.  It searches only
    observed structure/value/liquidity/reaction candidates already loaded by the
    analysis and applies the same specialist quality floors used by the normal
    refinement path.  ATR is only a buffer behind observed invalidation anchors;
    TP is never manufactured from an ATR/RR projection.

    The function cannot create direction.  The caller must already own a valid
    thesis/candidate and downstream Safety/Publication remain authoritative.
    """
    structure, trend, momentum, volatility = (
        _d(structure), _d(trend), _d(momentum), _d(volatility)
    )
    structure = _execution_structure(structure)
    context = dict(_d(execution_context))
    context.setdefault("market_type", str(market_type or "futures").lower())
    context.setdefault("symbol", str(symbol or ""))
    context.setdefault("timeframe", str(timeframe or ""))
    market = str(market_type or "futures").lower()
    direction = str(direction or "").lower()
    try:
        raw_current_price = float(current_price)
        raw_atr = float(atr)
    except Exception:
        raw_current_price = raw_atr = float("nan")
    if (
        direction not in {"long", "short"}
        or not isfinite(raw_current_price) or raw_current_price <= 0
        or not isfinite(raw_atr) or raw_atr <= 0
    ):
        return {"success": False, "reason": "INVALID_RECOVERY_INPUT", "version": VERSION}
    current_price = raw_current_price
    atr = raw_atr

    rr_floor = max(1.0, _f(rr_floor, 1.8))
    rr_ceiling = max(rr_floor, _f(rr_ceiling, 4.5))
    preferred_rr_min = max(rr_floor, _f(preferred_rr_min, 2.0))
    preferred_rr_max = min(rr_ceiling, max(preferred_rr_min, _f(preferred_rr_max, 3.2)))
    leverage_hint = 1.0 if market == "spot" else max(1.0, min(100.0, _f(leverage_hint, 1.0)))
    context.setdefault("leverage_hint", round(leverage_hint, 4))

    # Use current price only as a reference for liquidation-side filtering, then
    # remove the synthetic baseline row.  No current-price Entry is invented.
    entry_candidates = _collect_entry_candidates(
        structure, direction, current_price, liquidation=liquidation
    )
    entry_candidates = [r for r in entry_candidates if str(r.get("family")) != "baseline"]
    _add_execution_recovery_entry_candidates(
        entry_candidates, structure=structure, direction=direction,
        current_price=current_price, atr=atr,
    )
    if _f(entry_hint, 0.0) > 0:
        _append_candidate(
            entry_candidates, entry_hint, "existing_entry",
            "Entry técnico ya seleccionado", 2.0,
        )

    entry_ranked = _rank_candidates(
        entry_candidates,
        lambda c: _entry_specialists(
            c, entry_candidates, direction=direction,
            current_price=current_price, atr=atr, structure=structure,
            trend=trend, momentum=momentum, volatility=volatility,
            setup_family=setup_family, context=context, market_type=market,
        ),
        _weights_for("entry", market),
        lambda p: _is_correct_side(p, current_price, direction, "entry"),
        role="entry",
    )
    if not entry_ranked:
        return {"success": False, "reason": "NO_STRUCTURAL_ENTRY_FOR_RECOVERY", "version": VERSION}

    best_combo = None
    sl_reaction_rejections = 0
    admissibility_rejections = 0
    tested_combinations = 0
    activity = _f(context.get("activity_score"), 50.0)

    for entry_rank, entry_row in enumerate(entry_ranked[:min(8, len(entry_ranked))]):
        entry = _f(entry_row.get("price"), 0.0)
        if entry <= 0:
            continue
        sl_candidates = _collect_sl_candidates(
            structure, direction, entry, 0.0, atr, activity,
        )
        _add_execution_recovery_sl_candidates(
            sl_candidates, structure=structure, direction=direction,
            entry=entry, atr=atr, activity=activity,
        )
        filtered = []
        for row in sl_candidates:
            check = evaluate_sl_reaction_conflict(
                structure=structure, direction=direction, entry=entry,
                stop_loss=_f(row.get("price"), 0.0), atr=atr,
            )
            if check.get("conflict"):
                sl_reaction_rejections += 1
                continue
            filtered.append(row)
        sl_candidates = filtered
        sl_ranked = _rank_candidates(
            sl_candidates,
            lambda c: _sl_specialists(
                c, sl_candidates, direction=direction, entry=entry,
                tp_hint=0.0, atr=atr, structure=structure,
                setup_family=setup_family, context=context, market_type=market,
                leverage_hint=leverage_hint,
            ),
            _weights_for("sl", market),
            lambda p: _is_correct_side(p, entry, direction, "sl"),
            role="sl",
        )
        if not sl_ranked:
            continue

        for sl_rank, sl_row in enumerate(sl_ranked[:min(8, len(sl_ranked))]):
            sl = _f(sl_row.get("price"), 0.0)
            risk = abs(entry - sl)
            if risk <= 0:
                continue
            tp_candidates = _collect_tp_candidates(
                structure, direction, entry, 0.0, atr, liquidation=liquidation,
            )
            # Deliberately no RR/ATR TP fabrication.
            tp_ranked = _rank_candidates(
                tp_candidates,
                lambda c: _tp_specialists(
                    c, tp_candidates, direction=direction, entry=entry, sl=sl,
                    atr=atr, structure=structure, trend=trend, momentum=momentum,
                    volatility=volatility, setup_family=setup_family,
                    context=context, market_type=market, liquidation=liquidation,
                    leverage_hint=leverage_hint,
                ),
                _weights_for("tp", market),
                lambda p: _is_correct_side(p, entry, direction, "tp"),
                role="tp",
            )
            if not tp_ranked:
                continue

            for tp_rank, tp_row in enumerate(tp_ranked[:min(12, len(tp_ranked))]):
                tested_combinations += 1
                tp = _f(tp_row.get("price"), 0.0)
                reward = abs(tp - entry)
                rr = reward / max(risk, 1e-12)
                if rr < rr_floor or rr > rr_ceiling:
                    continue
                joint = _joint_geometry_score(
                    entry_row, sl_row, tp_row, rr,
                    rr_floor, rr_ceiling, preferred_rr_min, preferred_rr_max,
                )
                proposal = {
                    "entry": entry, "stop_loss": sl, "take_profit": tp,
                    "risk_reward": round(rr, 4),
                    "geometry_quality": round(joint, 2),
                    "entry_quality": round(_f(entry_row.get("committee_score")), 2),
                    "sl_quality": round(_f(sl_row.get("committee_score")), 2),
                    "tp_quality": round(_f(tp_row.get("committee_score")), 2),
                    "entry_committee": entry_row,
                    "sl_committee": sl_row,
                    "tp_committee": tp_row,
                    "ranks": {"entry": entry_rank + 1, "sl": sl_rank + 1, "tp": tp_rank + 1},
                    "recovery_mode": "STRUCTURAL_OPPORTUNITY_RECOVERY",
                }
                # Same legacy execution quality floors. Recovery cannot be used
                # to sneak a weaker geometry into publication.
                if not (
                    proposal["geometry_quality"] >= 62.0
                    and proposal["entry_quality"] >= 55.0
                    and proposal["sl_quality"] >= 60.0
                    and proposal["tp_quality"] >= 60.0
                ):
                    continue
                if candidate_filter is not None:
                    try:
                        if candidate_filter(proposal) is not True:
                            admissibility_rejections += 1
                            continue
                    except Exception:
                        return {
                            "success": False, "reason": "RECOVERY_GUARD_ERROR",
                            "version": VERSION,
                        }
                if (
                    best_combo is None
                    or proposal["geometry_quality"] > best_combo["geometry_quality"]
                    or (
                        proposal["geometry_quality"] == best_combo["geometry_quality"]
                        and abs(proposal["risk_reward"] - 2.6) < abs(best_combo["risk_reward"] - 2.6)
                    )
                ):
                    best_combo = proposal

    if best_combo is None:
        return {
            "success": False,
            "reason": "NO_COHERENT_STRUCTURAL_RECOVERY_GEOMETRY",
            "version": VERSION,
            "tested_combinations": tested_combinations,
            "admissibility_rejections": admissibility_rejections,
            "sl_reaction_rejections": sl_reaction_rejections,
        }

    return {
        "success": True,
        "version": VERSION,
        "market_type": market,
        **best_combo,
        "tested_combinations": tested_combinations,
        "admissibility_rejections": admissibility_rejections,
        "sl_reaction_rejections": sl_reaction_rejections,
        "authority": "RECOVER_GEOMETRY_ONLY_EXISTING_THESIS",
        "safety_unchanged": True,
    }

def leverage_committee_context(*, entry: float, stop_loss: float, take_profit: float,
                               atr: float, execution_safety: float = 0.0,
                               market_type: str = "futures",
                               execution_context=None) -> Dict[str, Any]:
    """Context packet for the existing leverage engine.

    Commit 17.1 deliberately does not replace the already deployed risk-budget
    leverage policy.  It ensures that leverage is assessed only *after* the
    specialist committees have finalized geometry and provides descriptive
    quality/risk context without forcing x1/x2 or inflating leverage.
    """
    ctx = _d(execution_context)
    e, s, t = _f(entry), _f(stop_loss), _f(take_profit)
    risk_pct = abs(e-s)/max(abs(e),1e-12)*100.0
    reward_pct = abs(t-e)/max(abs(e),1e-12)*100.0
    atr_pct = abs(_f(atr))/max(abs(e),1e-12)*100.0
    return {
        "version": VERSION,
        "market_type": str(market_type or "futures").lower(),
        "risk_pct": round(risk_pct,4),
        "reward_pct": round(reward_pct,4),
        "atr_pct": round(atr_pct,4),
        "risk_reward": round(reward_pct/max(risk_pct,1e-12),4),
        "execution_safety": round(_clip(execution_safety),2),
        "activity_score": round(_f(ctx.get("activity_score"),50.0),2),
        "shock_score": round(_f(ctx.get("shock_score"),0.0),2),
        "authority": "CONTEXT_FOR_EXISTING_LEVERAGE_POLICY",
        "does_not_force_low_leverage": True,
    }
