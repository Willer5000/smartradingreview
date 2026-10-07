"""Commit 32 SPOT Market Signal Authority.

Global market signal logic only. It never reads a user's holdings and never
modifies Portfolio Guardian. Its job is to decide whether the market evidence
supports COMPRA_SPOT, VENTA_SPOT or ESPERAR and to expose relative BTC/PAXG
rotation context. Existing Strategy Bank, geometry, Safety, publication/OOS and
Guardian remain downstream authorities.
"""
from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Tuple

VERSION = "COMMIT32_SPOT_MARKET_SIGNAL_AUTHORITY_V2"
SUPPORTED_SYMBOLS = {"BTC-USDT", "PAXG-USDT", "PAXG-BTC"}
_DIRECTIONAL = {"COMPRA_SPOT", "VENTA_SPOT"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else float(default)
    except Exception:
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _sym(value: Any) -> str:
    return _u(value).replace("/", "-")


def _direction(value: Any) -> str:
    raw = _u(value)
    if raw in {"LONG", "BUY", "BULL", "BULLISH", "ALCISTA", "UP", "COMPRA_SPOT"}:
        return "BULLISH"
    if raw in {"SHORT", "SELL", "BEAR", "BEARISH", "BAJISTA", "DOWN", "VENTA_SPOT"}:
        return "BEARISH"
    return "NEUTRAL"


def _confidence(container: Mapping[str, Any] | None) -> float:
    c = container or {}
    value = _f(c.get("confidence") or c.get("quality") or c.get("score") or c.get("strength_score"), 0.0)
    if 0 < value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _rec_tokens(value: Any, depth: int = 0) -> Iterable[str]:
    if depth > 5:
        return
    if isinstance(value, Mapping):
        for key, val in value.items():
            yield str(key)
            yield from _rec_tokens(val, depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _rec_tokens(item, depth + 1)
    elif value is not None:
        yield str(value)


def _blob(*values: Any) -> str:
    text = " ".join(_rec_tokens(values)).lower()
    text = re.sub(r"[^a-z0-9áéíóúñ_\- ]+", " ", text)
    return re.sub(r"\s+", " ", text)


def normalize_divergences(momentum: Mapping[str, Any] | None) -> Dict[str, bool]:
    """Normalize historical aliases, including the RSI producer/consumer mismatch."""
    m = momentum or {}
    text = _blob(
        m.get("divergences"), m.get("hidden_divergences"), m.get("divergence"),
        m.get("rsi_divergence"), m.get("macd_divergence"), m,
    )
    regular_bear = any(t in text for t in (
        "rsi_bear_divergence", "rsi_divergence_bear", "macd_bear_divergence",
        "macd_divergence_bear", "bearish divergence", "divergencia bajista",
        "regular_bearish", "regular bearish",
    )) and "hidden" not in text
    regular_bull = any(t in text for t in (
        "rsi_bull_divergence", "rsi_divergence_bull", "macd_bull_divergence",
        "macd_divergence_bull", "bullish divergence", "divergencia alcista",
        "regular_bullish", "regular bullish",
    )) and "hidden" not in text
    hidden_bear = any(t in text for t in (
        "hidden_bear", "bearish_hidden", "divergencia oculta bajista", "hidden bearish",
    ))
    hidden_bull = any(t in text for t in (
        "hidden_bull", "bullish_hidden", "divergencia oculta alcista", "hidden bullish",
    ))
    # Lists can contain both regular and hidden items. Inspect entries individually
    # so a hidden token elsewhere does not erase a genuine regular divergence.
    for item in list(m.get("divergences") or []):
        t = _blob(item)
        if "hidden" not in t and any(x in t for x in ("bear", "bajist")):
            regular_bear = True
        if "hidden" not in t and any(x in t for x in ("bull", "alcist")):
            regular_bull = True
    for item in list(m.get("hidden_divergences") or []):
        t = _blob(item)
        hidden_bear |= any(x in t for x in ("bear", "bajist"))
        hidden_bull |= any(x in t for x in ("bull", "alcist"))
    return {
        "regular_bearish": bool(regular_bear),
        "regular_bullish": bool(regular_bull),
        "hidden_bearish": bool(hidden_bear),
        "hidden_bullish": bool(hidden_bull),
    }


def _strong_patterns(structure: Mapping[str, Any] | None) -> Dict[str, bool]:
    text = _blob(structure or {})
    bearish = any(t in text for t in (
        "double_top", "doble techo", "doble_techo", "triple_top", "triple techo",
        "head_and_shoulders", "hombro cabeza hombro", "distribution_top",
        "bearish_engulf", "envolvente bajista", "evening_star", "estrella vespertina",
    ))
    bullish = any(t in text for t in (
        "double_bottom", "doble suelo", "doble_suelo", "triple_bottom", "triple suelo",
        "inverse_head_and_shoulders", "hombro cabeza hombro invertido", "accumulation_bottom",
        "bullish_engulf", "envolvente alcista", "morning_star", "estrella matutina",
    ))
    return {"bearish": bearish, "bullish": bullish}


def _cluster(prices: List[float], *, tolerance_pct: float = 1.4) -> Tuple[int, float | None]:
    values = sorted(x for x in prices if x > 0)
    if len(values) < 2:
        return 0, None
    best_count, best_center = 1, values[0]
    for anchor in values:
        band = max(anchor * tolerance_pct / 100.0, 1e-12)
        group = [x for x in values if abs(x - anchor) <= band]
        if len(group) > best_count:
            best_count = len(group)
            best_center = sum(group) / len(group)
    return best_count, best_center


def _rejection_context(structure: Mapping[str, Any] | None, price: float) -> Dict[str, Any]:
    s = structure or {}
    highs: List[float] = []
    lows: List[float] = []
    for row in list(s.get("pivot_highs") or [])[-20:]:
        if isinstance(row, Mapping):
            highs.append(_f(row.get("price"), 0.0))
        else:
            highs.append(_f(row, 0.0))
    for row in list(s.get("pivot_lows") or [])[-20:]:
        if isinstance(row, Mapping):
            lows.append(_f(row.get("price"), 0.0))
        else:
            lows.append(_f(row, 0.0))
    high_count, high_center = _cluster(highs)
    low_count, low_center = _cluster(lows)
    resistance = _f(s.get("nearest_resistance"), 0.0) or _f(high_center, 0.0)
    support = _f(s.get("nearest_support"), 0.0) or _f(low_center, 0.0)
    res_dist = ((resistance - price) / price * 100.0) if price > 0 and resistance > 0 else None
    sup_dist = ((price - support) / price * 100.0) if price > 0 and support > 0 else None
    return {
        "pivot_high_cluster": int(high_count),
        "pivot_low_cluster": int(low_count),
        "cluster_resistance": high_center,
        "cluster_support": low_center,
        "nearest_resistance": resistance or None,
        "nearest_support": support or None,
        "resistance_distance_pct": res_dist,
        "support_distance_pct": sup_dist,
        "repeated_rejection": bool(high_count >= 2 and res_dist is not None and -1.0 <= res_dist <= 5.0),
        "repeated_support": bool(low_count >= 2 and sup_dist is not None and -1.0 <= sup_dist <= 5.0),
    }


def _analysis_direction(obj: Any) -> Tuple[str, float]:
    if not isinstance(obj, Mapping):
        return "NEUTRAL", 0.0
    raw = obj.get("action") or obj.get("direction") or obj.get("signal") or obj.get("bias") or obj.get("trend")
    return _direction(raw), _confidence(obj)


def _relative_context(symbol: str, layers: Mapping[str, Any]) -> Dict[str, Any]:
    btc_dir, btc_conf = _analysis_direction(layers.get("btc_analysis") or {})
    gold_dir, gold_conf = _analysis_direction(layers.get("paxg_analysis") or layers.get("gold_analysis") or {})
    ratio_dir, ratio_conf = _analysis_direction(layers.get("ratio_analysis") or layers.get("paxg_btc_analysis") or {})
    buy = sell = 0.0
    reasons: List[str] = []
    rotation = "NEUTRAL"

    # PAXG/BTC rising means gold is outperforming BTC; falling means BTC is
    # outperforming gold. This is relative market evidence, not a portfolio act.
    if symbol == "BTC-USDT":
        if ratio_dir == "BULLISH":
            sell += 12 + min(ratio_conf, 100) * 0.05; reasons.append("PAXG_BTC_OUTPERFORMS_BTC"); rotation = "BTC_TO_PAXG_CONTEXT"
        elif ratio_dir == "BEARISH":
            buy += 12 + min(ratio_conf, 100) * 0.05; reasons.append("BTC_OUTPERFORMS_PAXG"); rotation = "PAXG_TO_BTC_CONTEXT"
        if btc_dir == "BULLISH" and gold_dir == "BEARISH": buy += 8
        if btc_dir == "BEARISH" and gold_dir == "BULLISH": sell += 8
    elif symbol == "PAXG-USDT":
        if ratio_dir == "BULLISH":
            buy += 12 + min(ratio_conf, 100) * 0.05; reasons.append("PAXG_OUTPERFORMS_BTC"); rotation = "BTC_TO_PAXG_CONTEXT"
        elif ratio_dir == "BEARISH":
            sell += 12 + min(ratio_conf, 100) * 0.05; reasons.append("BTC_OUTPERFORMS_PAXG"); rotation = "PAXG_TO_BTC_CONTEXT"
        if gold_dir == "BULLISH" and btc_dir == "BEARISH": buy += 8
        if gold_dir == "BEARISH" and btc_dir == "BULLISH": sell += 8
    elif symbol == "PAXG-BTC":
        if ratio_dir == "BULLISH":
            buy += 18 + min(ratio_conf, 100) * 0.05; reasons.append("ROTATION_BTC_TO_PAXG"); rotation = "ROTACION_BTC_A_PAXG"
        elif ratio_dir == "BEARISH":
            sell += 18 + min(ratio_conf, 100) * 0.05; reasons.append("ROTATION_PAXG_TO_BTC"); rotation = "ROTACION_PAXG_A_BTC"
    return {
        "buy": round(buy, 2), "sell": round(sell, 2), "reasons": reasons,
        "rotation": rotation, "btc_direction": btc_dir, "paxg_direction": gold_dir,
        "ratio_direction": ratio_dir,
    }


def evaluate_spot_market_signal(
    *, symbol: Any, timeframe: Any, layers: Mapping[str, Any], operational: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Evaluate a global SPOT market signal without user holdings.

    The score is a deterministic policy-quality score, NOT a calibrated win
    probability. Publication still needs the existing Strategy/geometry/Safety/
    OOS gates after this layer.
    """
    symbol = _sym(symbol)
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"unsupported SPOT symbol {symbol}")
    layers = dict(layers or {})
    trend = dict(layers.get("trend") or {})
    momentum = dict(layers.get("momentum") or {})
    volume = dict(layers.get("volume") or {})
    structure = dict(layers.get("structure") or {})
    macro = dict(layers.get("macro_context") or {})
    volatility = dict(layers.get("volatility") or {})
    price = _f(structure.get("current_price") or trend.get("current_price"), 0.0)

    scores = {"COMPRA_SPOT": 35.0, "VENTA_SPOT": 35.0}
    families = {"COMPRA_SPOT": set(), "VENTA_SPOT": set()}
    reasons = {"COMPRA_SPOT": [], "VENTA_SPOT": []}

    # Trend: context, never an automatic veto.
    trend_dir = _direction(trend.get("direction") or trend.get("trend_direction"))
    tconf = _confidence(trend)
    if trend_dir == "BULLISH":
        scores["COMPRA_SPOT"] += 12 + 0.08 * tconf; families["COMPRA_SPOT"].add("trend"); reasons["COMPRA_SPOT"].append("trend_bullish")
    elif trend_dir == "BEARISH":
        scores["VENTA_SPOT"] += 12 + 0.08 * tconf; families["VENTA_SPOT"].add("trend"); reasons["VENTA_SPOT"].append("trend_bearish")

    adx = _f(trend.get("adx") or volatility.get("adx"), 0.0)
    if 0 < adx < 18:
        # Low ADX lowers conviction but does not create the opposite signal.
        scores["COMPRA_SPOT"] -= 3; scores["VENTA_SPOT"] -= 3

    # Momentum + correctly-normalized divergences.
    mom_dir = _direction(momentum.get("direction") or momentum.get("signal") or momentum.get("bias"))
    mconf = _confidence(momentum)
    if mom_dir == "BULLISH":
        scores["COMPRA_SPOT"] += 8 + 0.07 * mconf; families["COMPRA_SPOT"].add("momentum"); reasons["COMPRA_SPOT"].append("momentum_bullish")
    elif mom_dir == "BEARISH":
        scores["VENTA_SPOT"] += 8 + 0.07 * mconf; families["VENTA_SPOT"].add("momentum"); reasons["VENTA_SPOT"].append("momentum_bearish")
    div = normalize_divergences(momentum)
    if div["regular_bearish"]:
        scores["VENTA_SPOT"] += 22; families["VENTA_SPOT"].add("momentum"); reasons["VENTA_SPOT"].append("regular_bearish_divergence")
    if div["regular_bullish"]:
        scores["COMPRA_SPOT"] += 22; families["COMPRA_SPOT"].add("momentum"); reasons["COMPRA_SPOT"].append("regular_bullish_divergence")
    if div["hidden_bearish"]:
        scores["VENTA_SPOT"] += 12; families["VENTA_SPOT"].add("momentum"); reasons["VENTA_SPOT"].append("hidden_bearish_continuation")
    if div["hidden_bullish"]:
        scores["COMPRA_SPOT"] += 12; families["COMPRA_SPOT"].add("momentum"); reasons["COMPRA_SPOT"].append("hidden_bullish_continuation")

    # Structure: strong patterns and multi-pivot rejection/support clusters.
    patt = _strong_patterns(structure)
    reject = _rejection_context(structure, price)
    if patt["bearish"]:
        scores["VENTA_SPOT"] += 20; families["VENTA_SPOT"].add("structure"); reasons["VENTA_SPOT"].append("strong_bearish_pattern")
    if patt["bullish"]:
        scores["COMPRA_SPOT"] += 20; families["COMPRA_SPOT"].add("structure"); reasons["COMPRA_SPOT"].append("strong_bullish_pattern")
    if reject["repeated_rejection"]:
        scores["VENTA_SPOT"] += 18; families["VENTA_SPOT"].add("structure"); reasons["VENTA_SPOT"].append("repeated_resistance_rejection")
    elif reject.get("resistance_distance_pct") is not None and 0 <= float(reject["resistance_distance_pct"]) <= 2.0:
        scores["VENTA_SPOT"] += 9; families["VENTA_SPOT"].add("structure"); reasons["VENTA_SPOT"].append("near_resistance")
    if reject["repeated_support"]:
        scores["COMPRA_SPOT"] += 18; families["COMPRA_SPOT"].add("structure"); reasons["COMPRA_SPOT"].append("repeated_support_hold")
    elif reject.get("support_distance_pct") is not None and 0 <= float(reject["support_distance_pct"]) <= 2.0:
        scores["COMPRA_SPOT"] += 9; families["COMPRA_SPOT"].add("structure"); reasons["COMPRA_SPOT"].append("near_support")

    # Volume / accumulation-distribution.
    acc = _f(volume.get("accumulation_score") or volume.get("accumulation"), 0.0)
    dist = _f(volume.get("distribution_score") or volume.get("distribution"), 0.0)
    obv = _direction(volume.get("obv_trend") or volume.get("obv_direction"))
    whale_buy = bool(volume.get("whale_buy_confirmed") or volume.get("whale_buy") or volume.get("iceberg_buy"))
    whale_sell = bool(volume.get("whale_sell_confirmed") or volume.get("whale_sell") or volume.get("iceberg_sell"))
    if acc >= 2 or obv == "BULLISH" or whale_buy:
        scores["COMPRA_SPOT"] += 13; families["COMPRA_SPOT"].add("volume"); reasons["COMPRA_SPOT"].append("accumulation_or_buying_pressure")
    if dist >= 2 or obv == "BEARISH" or whale_sell:
        scores["VENTA_SPOT"] += 13; families["VENTA_SPOT"].add("volume"); reasons["VENTA_SPOT"].append("distribution_or_selling_pressure")

    # Macro is context and symmetric across BTC/gold. It does not manufacture a
    # signal alone because ready still requires >=3 independent families.
    risk = _u(macro.get("risk_level") or macro.get("current_risk_level") or macro.get("risk"))
    if symbol == "BTC-USDT":
        if risk in {"HIGH", "VERY_HIGH", "CRITICAL", "RISK_OFF"}:
            scores["VENTA_SPOT"] += 9; families["VENTA_SPOT"].add("macro"); reasons["VENTA_SPOT"].append("macro_risk_off")
        elif risk in {"LOW", "RISK_ON"}:
            scores["COMPRA_SPOT"] += 7; families["COMPRA_SPOT"].add("macro"); reasons["COMPRA_SPOT"].append("macro_risk_on")
    elif symbol in {"PAXG-USDT", "PAXG-BTC"}:
        if risk in {"HIGH", "VERY_HIGH", "CRITICAL", "RISK_OFF"}:
            scores["COMPRA_SPOT"] += 9; families["COMPRA_SPOT"].add("macro"); reasons["COMPRA_SPOT"].append("defensive_gold_context")
        elif risk in {"LOW", "RISK_ON"}:
            scores["VENTA_SPOT"] += 5; families["VENTA_SPOT"].add("macro"); reasons["VENTA_SPOT"].append("risk_on_gold_headwind")

    rel = _relative_context(symbol, layers)
    if rel["buy"] > 0:
        scores["COMPRA_SPOT"] += rel["buy"]; families["COMPRA_SPOT"].add("relative"); reasons["COMPRA_SPOT"].extend(rel["reasons"])
    if rel["sell"] > 0:
        scores["VENTA_SPOT"] += rel["sell"]; families["VENTA_SPOT"].add("relative"); reasons["VENTA_SPOT"].extend(rel["reasons"])

    for key in scores:
        scores[key] = max(0.0, min(100.0, scores[key]))
    ordered = sorted(scores, key=lambda a: scores[a], reverse=True)
    winner, runner = ordered[0], ordered[1]
    margin = scores[winner] - scores[runner]
    family_count = len(families[winner])
    ready = bool(scores[winner] >= 78.0 and margin >= 12.0 and family_count >= 3)
    action = winner if ready else "ESPERAR"

    rotation = rel["rotation"]
    if symbol == "PAXG-BTC" and ready:
        rotation = "ROTACION_BTC_A_PAXG" if winner == "COMPRA_SPOT" else "ROTACION_PAXG_A_BTC"
    elif ready and winner == "VENTA_SPOT" and rotation == "NEUTRAL":
        rotation = "USDT_PRESERVATION_CONTEXT"

    # Strong opposite evidence may suppress a stale/generic opposite candidate,
    # but this layer still cannot bypass Strategy/geometry/Safety/OOS.
    block_opposite = bool(ready and scores[winner] >= 84.0 and margin >= 18.0 and family_count >= 3)
    preferred_family = "ROTATION" if "ROTACION_" in rotation or "_TO_PAXG" in rotation or "_TO_BTC" in rotation else (
        "MEAN_REVERSION" if any("divergence" in x or "rejection" in x or "pattern" in x for x in reasons[winner]) else "TREND_PULLBACK"
    )

    return {
        "version": VERSION,
        "symbol": symbol,
        "timeframe": str(timeframe or ""),
        "action": action,
        "direction": "BULLISH" if winner == "COMPRA_SPOT" else "BEARISH",
        "winning_action": winner,
        "quality": round(scores[winner], 2),
        "runner_quality": round(scores[runner], 2),
        "margin": round(margin, 2),
        "ready": ready,
        "block_opposite": block_opposite,
        "independent_support_families": sorted(families[winner]),
        "family_count": family_count,
        "reasons": reasons[winner][:12],
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "divergences": div,
        "structure_context": reject,
        "relative_context": rel,
        "market_rotation_signal": rotation,
        "preferred_family": preferred_family,
        "portfolio_independent": True,
        "reads_user_holdings": False,
        "guardian_authority": "UNCHANGED_DOWNSTREAM_PER_USER",
        "creates_publication_authority": False,
        "never_bypass_strategy": True,
        "never_bypass_geometry": True,
        "never_bypass_safety": True,
        "never_bypass_oos_route": True,
        "score_semantics": "POLICY_QUALITY_NOT_CALIBRATED_WIN_PROBABILITY",
    }


def apply_market_signal_to_pipeline(
    original_reconcile: Any, pipeline_module: Any, operational: Mapping[str, Any], *,
    layers: Mapping[str, Any], symbol: str, timeframe: str, system_type: str,
) -> Dict[str, Any]:
    """Reconcile the global SPOT signal through the existing production gates."""
    market = _u(system_type)
    sym = _sym(symbol)
    if market != "SPOT" or sym not in SUPPORTED_SYMBOLS:
        return original_reconcile(operational, layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type)

    assessment = evaluate_spot_market_signal(symbol=sym, timeframe=timeframe, layers=layers, operational=operational)
    result = original_reconcile(operational, layers=layers, symbol=symbol, timeframe=timeframe, system_type=system_type)
    if not isinstance(result, dict):
        result = dict(operational or {})
    result = deepcopy(result)
    result["commit32_spot_market_signal"] = assessment

    target = assessment.get("winning_action") if assessment.get("ready") else None
    current = _u(result.get("candidate_action")) if result.get("candidate_ready") else "NO_OPERAR"
    if target not in _DIRECTIONAL:
        return result
    if current == target:
        result["candidate_source"] = str(result.get("candidate_source") or "") + "+C32_SPOT_MARKET_CONFIRM"
        return result

    # Try to route the new market direction through exactly the existing SPOT
    # Strategy Bank thresholds and official-cell rules. No threshold is lowered.
    selector = getattr(pipeline_module, "_select_default_strategy", None)
    official_fn = getattr(pipeline_module, "_official_cell", None)
    if callable(selector) and callable(official_fn):
        try:
            strategy = selector(
                result, layers=layers, symbol=sym, timeframe=timeframe, market="SPOT",
                action=target, preferred_family=str(assessment.get("preferred_family") or ""), is_multi=False,
            )
        except Exception as exc:
            strategy = {"quality": 0.0, "regime_match": False, "volatility_match": False, "error": type(exc).__name__}
        strategy_quality = _f(strategy.get("quality"), 0.0)
        strategy_ok = bool(strategy_quality >= 70.0 and strategy.get("regime_match", True) and strategy.get("volatility_match", True))
        try:
            official = bool(official_fn("SPOT", sym, timeframe, target, fallback=bool(result.get("official_cell"))))
        except Exception:
            official = bool(result.get("official_cell", True))
        mtf = result.get("multi_timeframe") or {}
        mtf_usable = not bool(mtf.get("conflict")) if isinstance(mtf, Mapping) else True
        macro = layers.get("macro_context") or {}
        macro_risk = _u((result.get("thesis") or {}).get("macro_risk") or macro.get("risk_level") or macro.get("risk"))
        route_ready = bool(official and mtf_usable and macro_risk != "CRITICAL" and strategy_ok)
        result["commit32_spot_strategy_recheck"] = {
            "quality": round(strategy_quality, 2), "strategy_ok": strategy_ok,
            "official_cell": official, "mtf_usable": mtf_usable, "macro_risk": macro_risk or "UNKNOWN",
            "ready": route_ready,
        }
        if route_ready:
            thesis = dict(result.get("thesis") or {})
            thesis.update({
                "action": target,
                "direction": "BULLISH" if target == "COMPRA_SPOT" else "BEARISH",
                "quality": round(float(assessment.get("quality") or 0.0), 2),
                "source": "COMMIT32_SPOT_MARKET_SIGNAL_AUTHORITY",
                "market_rotation_signal": assessment.get("market_rotation_signal"),
            })
            result["thesis"] = thesis
            result["candidate_ready"] = True
            result["candidate_action"] = target
            result["candidate_source"] = "COMMIT32_SPOT_MARKET_SIGNAL+EXISTING_STRATEGY_BANK"
            result["default_strategy"] = strategy
            result["particular_strategy_quality"] = round(strategy_quality, 2)
            result["independent_support_families"] = list(assessment.get("independent_support_families") or [])
            result["never_bypass_safety"] = True
            result["commit32_spot_direction_changed"] = current not in {"NO_OPERAR", target}
            return result

    # If strong market evidence contradicts a generic opposite candidate but
    # the replacement cannot pass existing Strategy/official-cell gates, do not
    # publish the opposite stale thesis. Wait instead. This is a false-positive
    # guard, not a promotion bypass.
    if current in _DIRECTIONAL and current != target and assessment.get("block_opposite"):
        result["candidate_ready"] = False
        result["candidate_action"] = "NO_OPERAR"
        result["candidate_source"] = "COMMIT32_SPOT_MARKET_CONFLICT_WAIT"
        result["commit32_spot_suppressed_opposite"] = current
    return result
