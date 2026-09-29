"""Commit 17.5.10 — historical backtest evidence in SHADOW.

This module preserves the historical Research OOS and execution-forensics
cohorts available on 2026-09-28, but 17.5.10 removes their production ranking
authority until an independent, point-in-time validation cohort exists.

Important:
- It never creates LONG/SHORT direction.
- It never bypasses Safety, MTF, publication or execution guards.
- It never changes leverage directly.
- Family evidence remains cell-specific (market × symbol × timeframe × action).
- Production score/adjustment is neutral: historical evidence is SHADOW only.
- Entry/SL/TP historical evidence is diagnostic because the cohorts are not a
  version-matched replay of 17.5.10. Current technical guards remain separate.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

VERSION = "COMMIT17_5_10_BACKTEST_SHADOW_V1"
PRODUCTION_AUTHORITY = "SHADOW_ONLY_UNTIL_INDEPENDENT_VALIDATION"
EVIDENCE_ASOF = "2026-09-28"


def _norm_market(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"FUTURES", "CRYPTO_FUTURES"}:
        return "FUTURES"
    if text in {"SPOT", "CRYPTO_SPOT", "PAXG_USDT", "PAXG_BTC"}:
        return "SPOT"
    if text in {"MULTIASSET", "MULTI-ASSET", "MULTI_ASSET"}:
        return "MULTIASSET"
    return text or "UNKNOWN"


def _norm_tf(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"30MIN": "30M", "60M": "1H", "120M": "2H", "240M": "4H", "1DAY": "1D"}
    return aliases.get(text, text)


def _norm_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text == "COMPRA_SPOT":
        return "COMPRA_SPOT"
    if text == "VENTA_SPOT":
        return "VENTA_SPOT"
    if text in {"LONG", "BUY", "COMPRA"}:
        return "LONG"
    if text in {"SHORT", "SELL", "VENTA"}:
        return "SHORT"
    return text


def _norm_family(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


# Selected positive OOS cells with n>=10, expectancy >= +0.12R,
# PF>=1.25 and max drawdown <=6R. Duplicates from prior candidate variants are
# collapsed to one representative record per exact family/cell.
FAMILY_CELL_EVIDENCE: Dict[Tuple[str, str, str, str, str], Dict[str, float]] = {
    # FUTURES
    ("FUTURES", "SOL-USDT", "1H", "SHORT", "RSI_TREND"): {"n": 10, "exp_r": 0.7652, "pf": 4.343, "maxdd_r": 1.229},
    ("FUTURES", "BNB-USDT", "2H", "LONG", "MFI_OBV_FLOW"): {"n": 17, "exp_r": 0.7258, "pf": 2.743, "maxdd_r": 3.438},
    ("FUTURES", "XRP-USDT", "30M", "LONG", "HIDDEN_DIVERGENCE_TREND"): {"n": 12, "exp_r": 0.6030, "pf": 1.993, "maxdd_r": 3.684},
    ("FUTURES", "SOL-USDT", "2H", "LONG", "RSI_TREND"): {"n": 20, "exp_r": 0.4498, "pf": 2.287, "maxdd_r": 3.630},
    ("FUTURES", "LINK-USDT", "30M", "LONG", "SUPERTREND_PULLBACK"): {"n": 12, "exp_r": 0.3150, "pf": 1.549, "maxdd_r": 4.592},
    ("FUTURES", "ETH-USDT", "1D", "LONG", "VOLUME_PROFILE_NODE_REACTION"): {"n": 11, "exp_r": 0.6043, "pf": 2.992, "maxdd_r": 1.061},
    ("FUTURES", "BNB-USDT", "2H", "LONG", "SUPERTREND_PULLBACK"): {"n": 13, "exp_r": 0.5235, "pf": 1.730, "maxdd_r": 5.622},
    ("FUTURES", "ETH-USDT", "4H", "SHORT", "SWEEP_REVERSAL"): {"n": 16, "exp_r": 0.4058, "pf": 1.973, "maxdd_r": 2.924},
    ("FUTURES", "SOL-USDT", "30M", "SHORT", "EMA_RECLAIM"): {"n": 11, "exp_r": 0.3568, "pf": 1.746, "maxdd_r": 1.384},
    ("FUTURES", "BNB-USDT", "2H", "LONG", "VOLUME_PROFILE_NODE_REACTION"): {"n": 24, "exp_r": 0.3567, "pf": 1.711, "maxdd_r": 4.525},
    ("FUTURES", "XRP-USDT", "2H", "LONG", "VOLUME_PROFILE_NODE_REACTION"): {"n": 19, "exp_r": 0.3510, "pf": 1.651, "maxdd_r": 4.487},
    ("FUTURES", "SOL-USDT", "1D", "LONG", "ADX_DI_TREND"): {"n": 11, "exp_r": 0.3274, "pf": 1.901, "maxdd_r": 1.735},
    ("FUTURES", "SOL-USDT", "12H", "SHORT", "RSI_TREND"): {"n": 13, "exp_r": 0.3122, "pf": 1.648, "maxdd_r": 4.566},
    ("FUTURES", "LINK-USDT", "30M", "LONG", "HIDDEN_DIVERGENCE_TREND"): {"n": 10, "exp_r": 0.3110, "pf": 1.667, "maxdd_r": 2.189},
    ("FUTURES", "ETH-USDT", "12H", "LONG", "MULTI_RSI_TREND"): {"n": 14, "exp_r": 0.2851, "pf": 1.624, "maxdd_r": 2.441},
    ("FUTURES", "BTC-USDT", "1D", "LONG", "PSAR_TREND"): {"n": 13, "exp_r": 0.2806, "pf": 2.049, "maxdd_r": 2.178},
    ("FUTURES", "ETH-USDT", "2H", "SHORT", "FVG_RECLAIM"): {"n": 11, "exp_r": 0.2748, "pf": 1.679, "maxdd_r": 2.304},
    ("FUTURES", "XRP-USDT", "30M", "SHORT", "SUPERTREND_PULLBACK"): {"n": 11, "exp_r": 0.2718, "pf": 1.459, "maxdd_r": 4.668},
    ("FUTURES", "ETH-USDT", "30M", "LONG", "SUPERTREND_PULLBACK"): {"n": 10, "exp_r": 0.2645, "pf": 1.427, "maxdd_r": 4.230},
    ("FUTURES", "LINK-USDT", "30M", "LONG", "MFI_OBV_FLOW"): {"n": 21, "exp_r": 0.2560, "pf": 1.416, "maxdd_r": 3.568},
    ("FUTURES", "BNB-USDT", "1H", "LONG", "HIDDEN_DIVERGENCE_TREND"): {"n": 10, "exp_r": 0.2503, "pf": 1.361, "maxdd_r": 4.040},
    ("FUTURES", "ADA-USDT", "30M", "SHORT", "SWEEP_REVERSAL"): {"n": 11, "exp_r": 0.2495, "pf": 1.453, "maxdd_r": 4.489},
    ("FUTURES", "SOL-USDT", "1H", "LONG", "VOLUME_PROFILE_NODE_REACTION"): {"n": 23, "exp_r": 0.2359, "pf": 1.466, "maxdd_r": 4.754},
    ("FUTURES", "ADA-USDT", "2H", "SHORT", "MFI_OBV_FLOW"): {"n": 18, "exp_r": 0.2294, "pf": 1.602, "maxdd_r": 4.523},
    ("FUTURES", "SOL-USDT", "2H", "LONG", "VOLUME_PROFILE_NODE_REACTION"): {"n": 18, "exp_r": 0.2058, "pf": 1.392, "maxdd_r": 5.422},
    ("FUTURES", "BTC-USDT", "12H", "LONG", "RSI_TREND"): {"n": 12, "exp_r": 0.1712, "pf": 1.445, "maxdd_r": 2.884},
    ("FUTURES", "ETH-USDT", "4H", "SHORT", "MFI_OBV_FLOW"): {"n": 14, "exp_r": 0.1554, "pf": 1.344, "maxdd_r": 3.364},
    ("FUTURES", "ETH-USDT", "4H", "SHORT", "HIDDEN_DIVERGENCE_TREND"): {"n": 13, "exp_r": 0.1531, "pf": 1.274, "maxdd_r": 2.897},
    ("FUTURES", "LINK-USDT", "30M", "LONG", "TREND_CONTINUATION"): {"n": 25, "exp_r": 0.1479, "pf": 1.383, "maxdd_r": 3.625},
    ("FUTURES", "SOL-USDT", "12H", "LONG", "ICHIMOKU_TREND"): {"n": 12, "exp_r": 0.1204, "pf": 1.251, "maxdd_r": 3.842},
    # SPOT
    ("SPOT", "PAXG-USDT", "1D", "COMPRA_SPOT", "RSI_TREND"): {"n": 14, "exp_r": 1.2538, "pf": 4.031, "maxdd_r": 2.147},
    ("SPOT", "PAXG-USDT", "1D", "COMPRA_SPOT", "MULTI_RSI_TREND"): {"n": 17, "exp_r": 0.8780, "pf": 2.838, "maxdd_r": 2.546},
    ("SPOT", "PAXG-BTC", "1D", "COMPRA_SPOT", "MFI_OBV_FLOW"): {"n": 15, "exp_r": 0.7922, "pf": 3.942, "maxdd_r": 1.828},
    ("SPOT", "PAXG-BTC", "1D", "COMPRA_SPOT", "TREND_CONTINUATION"): {"n": 17, "exp_r": 0.5298, "pf": 2.895, "maxdd_r": 2.144},
    ("SPOT", "BTC-USDT", "1D", "VENTA_SPOT", "SWEEP_REVERSAL"): {"n": 11, "exp_r": 0.5067, "pf": 3.404, "maxdd_r": 1.265},
    ("SPOT", "BTC-USDT", "1D", "VENTA_SPOT", "MACD_TREND"): {"n": 10, "exp_r": 0.4796, "pf": 2.146, "maxdd_r": 2.094},
    ("SPOT", "BTC-USDT", "1D", "VENTA_SPOT", "ADX_DI_TREND"): {"n": 18, "exp_r": 0.3136, "pf": 1.844, "maxdd_r": 3.261},
    ("SPOT", "PAXG-USDT", "1D", "COMPRA_SPOT", "TREND_CONTINUATION"): {"n": 24, "exp_r": 0.2934, "pf": 1.793, "maxdd_r": 2.835},
    ("SPOT", "PAXG-BTC", "1D", "COMPRA_SPOT", "RSI_TREND"): {"n": 17, "exp_r": 0.2599, "pf": 1.646, "maxdd_r": 2.135},
    ("SPOT", "BTC-USDT", "1D", "VENTA_SPOT", "VOLUME_PROFILE_NODE_REACTION"): {"n": 20, "exp_r": 0.2381, "pf": 1.731, "maxdd_r": 3.880},
    ("SPOT", "PAXG-USDT", "12H", "VENTA_SPOT", "TREND_PULLBACK"): {"n": 11, "exp_r": 0.2168, "pf": 1.527, "maxdd_r": 2.597},
    ("SPOT", "PAXG-USDT", "12H", "VENTA_SPOT", "MFI_OBV_FLOW"): {"n": 13, "exp_r": 0.1877, "pf": 1.362, "maxdd_r": 2.296},
}

# Component studies from production historical forensics. These are not
# version-matched 17.5.8 results; therefore they are used as priors, never hard
# outcome probabilities.
ENTRY_ROUTE_EVIDENCE = {
    "30M": {"route": "LIQUIDITY_SWEEP_MSS_POI", "resolved_n": 16, "wr_pct": 75.00, "exp_r": 1.153, "pf": 5.613},
    "1H": {"route": "LIQUIDITY_SWEEP_MSS_POI", "resolved_n": 27, "wr_pct": 33.33, "exp_r": 0.089, "pf": 1.134},
    "2H": {"route": "LIQUIDITY_SWEEP_MSS_POI", "resolved_n": 17, "wr_pct": 47.06, "exp_r": 0.318, "pf": 1.600},
}

SL_FORENSIC_EVIDENCE = {
    "30M": {"sl_hits": 81, "wick_out": 4, "reclaimed": 4, "tp_after_stop": 1, "possibly_tight": 3, "avg_mfe_before_sl": 0.565},
    "1H": {"sl_hits": 109, "wick_out": 8, "reclaimed": 13, "tp_after_stop": 0, "possibly_tight": 2, "avg_mfe_before_sl": 0.807},
    "2H": {"sl_hits": 62, "wick_out": 6, "reclaimed": 9, "tp_after_stop": 1, "possibly_tight": 4, "avg_mfe_before_sl": 0.451},
    "4H": {"sl_hits": 17, "wick_out": 2, "reclaimed": 2, "tp_after_stop": 1, "possibly_tight": 2, "avg_mfe_before_sl": 0.634},
}

# Highest expectancy observed in the same-entry/same-SL target-compression sweep.
# Negative values mean target compression did NOT rescue that timeframe cohort.
TP_SWEEP_EVIDENCE = {
    "30M": {"best_multiplier": 1.00, "n": 120, "exp_r": 0.208, "pf_proxy": 1.311},
    "1H": {"best_multiplier": 0.50, "n": 114, "exp_r": -0.464, "pf_proxy": 0.392},
    "2H": {"best_multiplier": 1.00, "n": 74, "exp_r": -0.376, "pf_proxy": 0.544},
    "4H": {"best_multiplier": 0.50, "n": 18, "exp_r": -0.438, "pf_proxy": 0.475},
}


def family_cell_prior(*, market: Any, symbol: Any, timeframe: Any, action: Any, family: Any) -> Dict[str, Any]:
    market_n = _norm_market(market)
    action_n = _norm_action(action)
    # 17.5.10 fixes the Spot contract even while evidence remains shadow-only.
    if market_n == "SPOT":
        if action_n == "LONG":
            action_n = "COMPRA_SPOT"
        elif action_n == "SHORT":
            action_n = "VENTA_SPOT"
    key = (market_n, str(symbol or "").strip().upper(), _norm_tf(timeframe), action_n, _norm_family(family))
    row = FAMILY_CELL_EVIDENCE.get(key)
    if not row:
        return {
            "available": False, "score": 50.0, "adjustment": 0.0,
            "shadow_score": 50.0, "shadow_adjustment": 0.0,
            "authority": PRODUCTION_AUTHORITY, "key": "|".join(key),
        }
    n = float(row["n"])
    exp_r = float(row["exp_r"])
    pf = float(row["pf"])
    evidence = min(1.0, max(0.0, (n - 8.0) / 24.0) * 0.35 + min(exp_r, 0.80) / 0.80 * 0.40 + min(max(pf - 1.0, 0.0), 2.5) / 2.5 * 0.25)
    shadow_adjustment = round(min(4.0, 0.75 + 3.25 * evidence), 3)
    return {
        "available": True,
        # LIVE stays neutral. The old bounded value remains visible for shadow comparison.
        "score": 50.0,
        "adjustment": 0.0,
        "shadow_score": round(50.0 + shadow_adjustment * 5.0, 2),
        "shadow_adjustment": shadow_adjustment,
        "authority": PRODUCTION_AUTHORITY,
        "key": "|".join(key),
        **row,
    }

def entry_component_prior(*, timeframe: Any, candidate_family: Any, smc_events: int = 0, market: Any = None, symbol: Any = None, regime: Any = None) -> Dict[str, Any]:
    tf = _norm_tf(timeframe)
    ev = ENTRY_ROUTE_EVIDENCE.get(tf)
    fam = _norm_family(candidate_family).lower()
    route_like = fam in {"smc_poi", "liquidity", "swing", "structure", "fib", "recent_reaction", "volatility_reaction"}
    shadow_adj = 0.0
    if ev and route_like and int(smc_events or 0) > 0:
        if float(ev["exp_r"]) >= 0.75 and float(ev["pf"]) >= 2.0:
            shadow_adj = 4.0
        elif float(ev["exp_r"]) >= 0.20 and float(ev["pf"]) >= 1.40:
            shadow_adj = 2.5
        elif float(ev["exp_r"]) > 0 and float(ev["pf"]) > 1.0:
            shadow_adj = 1.0
    return {
        "available": bool(ev), "score": 50.0, "adjustment": 0.0,
        "shadow_score": round(50.0 + shadow_adj * 5.0, 2),
        "shadow_adjustment": shadow_adj,
        "authority": PRODUCTION_AUTHORITY, "timeframe": tf,
        "market": _norm_market(market) if market is not None else None,
        "symbol": str(symbol or "").upper() or None,
        **(ev or {}),
    }

def sl_component_prior(*, timeframe: Any, reaction_conflict: bool = False) -> Dict[str, Any]:
    tf = _norm_tf(timeframe)
    ev = SL_FORENSIC_EVIDENCE.get(tf)
    # Historical SL evidence is neutral in LIVE. The actual reaction-conflict
    # hard guard is computed from current structure in execution_specialist_committees.py.
    return {
        "available": bool(ev), "score": 50.0, "adjustment": 0.0,
        "shadow_score": 50.0, "shadow_adjustment": 0.0,
        "shadow_reaction_conflict": bool(reaction_conflict),
        "authority": PRODUCTION_AUTHORITY, "timeframe": tf,
        **(ev or {}),
    }

def tp_component_prior(*, timeframe: Any, candidate_rr: float = 0.0) -> Dict[str, Any]:
    tf = _norm_tf(timeframe)
    ev = TP_SWEEP_EVIDENCE.get(tf)
    rr = float(candidate_rr or 0.0)
    shadow_adj = 1.5 if ev and tf == "30M" and 1.8 <= rr <= 3.5 and float(ev["exp_r"]) > 0 else 0.0
    return {
        "available": bool(ev), "score": 50.0, "adjustment": 0.0,
        "shadow_score": round(50.0 + shadow_adj * 5.0, 2),
        "shadow_adjustment": shadow_adj,
        "authority": PRODUCTION_AUTHORITY, "timeframe": tf,
        **(ev or {}),
    }

def get_preliminary_learning_bundle(*, market: Any = "", symbol: Any = "", timeframe: Any = "", action: Any = "", family: Any = "") -> Dict[str, Any]:
    return {
        "version": VERSION,
        "evidence_asof": EVIDENCE_ASOF,
        "probability_status": "HISTORICAL_PRIOR_NOT_CALIBRATED_PROBABILITY",
        "family": family_cell_prior(market=market, symbol=symbol, timeframe=timeframe, action=action, family=family),
        "entry": ENTRY_ROUTE_EVIDENCE.get(_norm_tf(timeframe), {}),
        "sl": SL_FORENSIC_EVIDENCE.get(_norm_tf(timeframe), {}),
        "tp": TP_SWEEP_EVIDENCE.get(_norm_tf(timeframe), {}),
        "governance": {
            "can_create_direction": False,
            "can_bypass_safety": False,
            "can_bypass_publication": False,
            "can_raise_leverage": False,
            "family_prior_max_adjustment": 0.0,
            "entry_prior_max_adjustment": 0.0,
            "production_authority": PRODUCTION_AUTHORITY,
            "shadow_family_max_adjustment": 4.0,
            "shadow_entry_max_adjustment": 4.0,
            "sl_global_shift_authorized": False,
            "tp_global_compression_authorized": False,
        },
    }


def futures_scan_priority(symbol: Any, timeframe: Any) -> float:
    """17.5.10: historical selected priors do not reorder LIVE scan coverage."""
    return 0.0


def shadow_futures_scan_priority(symbol: Any, timeframe: Any) -> float:
    """Diagnostic-only copy of the old research-priority score."""
    sym = str(symbol or "").strip().upper()
    tf = _norm_tf(timeframe)
    best = 0.0
    for (market, cell_symbol, cell_tf, _action, _family), row in FAMILY_CELL_EVIDENCE.items():
        if market != "FUTURES" or cell_symbol != sym or cell_tf != tf:
            continue
        n = float(row.get("n") or 0.0)
        exp_r = max(0.0, float(row.get("exp_r") or 0.0))
        pf = max(1.0, float(row.get("pf") or 1.0))
        score = exp_r * 100.0 + min(n, 30.0) * 1.5 + min(pf - 1.0, 3.0) * 12.0
        best = max(best, score)
    return round(best, 3)
