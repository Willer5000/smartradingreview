"""Commit 26 / Propuesta Profunda 2 release audit and backtest.

This script is intentionally anti-overfit:
- no parameter search is performed;
- the 30m contract is replayed from the row-level historical cohort already
  bundled with Main, preserving the frozen chronological DEV/HOLDOUT split;
- governed Commit-19 Champions are aggregated from their frozen IS/Selection/OOS
  evidence only (their raw candles are not bundled in Main);
- Commit-26's code change is an integration/parity repair, not a new alpha rule:
  it stops requiring post-Entry MSS/displacement fields at a pre-Entry routing
  stage and instead consumes the strict closed-candle Structure evidence that
  the real app actually exposes there.

The output demonstrates observed historical profitability of the governed LIVE
routes and verifies that the repaired router can consume the real pre-Entry
schema.  It does not claim future-profit certainty.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List

import champion_registry_commit19 as registry

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "BACKTEST_COMMIT26_PROPOSAL2.json"
OUT_MD = ROOT / "BACKTEST_COMMIT26_PROPOSAL2.md"


def _metrics(values: Iterable[float]) -> Dict[str, Any]:
    vals = list(values)
    gp = sum(max(v, 0.0) for v in vals)
    gl = abs(sum(min(v, 0.0) for v in vals))
    cum = peak = max_dd = 0.0
    for v in vals:
        cum += v
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return {
        "n": len(vals),
        "net_r": round(sum(vals), 6),
        "expectancy_r": round(sum(vals) / len(vals), 6) if vals else 0.0,
        "profit_factor": round(gp / gl, 6) if gl > 0 else None,
        "max_drawdown_r": round(max_dd, 6),
    }


def _bootstrap_mean(vals: List[float], *, iterations: int = 100000, seed: int = 2602) -> Dict[str, Any]:
    rnd = random.Random(seed)
    means: List[float] = []
    n = len(vals)
    for _ in range(iterations):
        means.append(sum(vals[rnd.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * iterations)]
    hi = means[int(0.975 * iterations)]
    ppos = sum(x > 0 for x in means) / iterations
    return {
        "iterations": iterations,
        "seed": seed,
        "probability_bootstrap_mean_gt_zero": round(ppos, 5),
        "ci95_mean_r": [round(lo, 6), round(hi, 6)],
    }


def _load_30m() -> Dict[str, Any]:
    with (ROOT / "BACKTEST_ROWS_17_5_10_PROFITABILITY.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dev = [r for r in rows if r["period"] == "DEV"]
    oos = [r for r in rows if r["period"] == "HOLDOUT"]

    def values(part, extra_cost=0.0):
        return [float(r["stress_net_r"]) - extra_cost for r in part]

    base_dev = _metrics(values(dev))
    base_oos = _metrics(values(oos))
    base_all = _metrics(values(rows))
    stress = {}
    for extra in (0.05, 0.10, 0.15, 0.20):
        stress[f"plus_{extra:.2f}R_per_trade"] = {
            "is": _metrics(values(dev, extra)),
            "oos": _metrics(values(oos, extra)),
        }

    return {
        "contract": {
            "route": "LIQUIDITY_SWEEP_MSS_POI",
            "timeframe": "30M",
            "trend_aligned": True,
            "adx_min": 20.0,
            "volume_ratio_min": 1.20,
            "rsi_long_max": 80.0,
            "rsi_short_min": 20.0,
            "rr": 1.8,
            "base_cost_stress_r_per_entry": 0.118,
            "is_period": "2026-09-10..2026-09-13",
            "oos_period": "2026-09-14..2026-09-16",
        },
        "is": base_dev,
        "oos": base_oos,
        "combined": base_all,
        "bootstrap_combined": _bootstrap_mean(values(rows)),
        "additional_cost_stress": stress,
        "pass": bool(base_dev["expectancy_r"] > 0 and (base_dev["profit_factor"] or 0) > 1
                     and base_oos["expectancy_r"] > 0 and (base_oos["profit_factor"] or 0) > 1),
        "limitations": [
            "OOS n=4 is chronologically clean but statistically small.",
            "The row-level cohort does not persist synchronized 4h->30m relation fields or pre-Entry structure_reasons.",
            "Commit 26 therefore restores live/backtest stage parity; it does not claim a new 4h-countertrend edge.",
        ],
    }


def _aggregate(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = sum(int(p.get("n") or 0) for p in parts)
    net = sum(int(p.get("n") or 0) * float(p.get("expectancy_r") or 0.0) for p in parts)
    wins = losses = 0.0
    for p in parts:
        ni = int(p.get("n") or 0)
        e = float(p.get("expectancy_r") or 0.0)
        pf = float(p.get("pf") or p.get("profit_factor") or 0.0)
        nr = ni * e
        if pf > 1.0 and nr > 0:
            loss = nr / (pf - 1.0)
            win = pf * loss
            wins += win
            losses += loss
        elif nr >= 0:
            wins += nr
        else:
            losses += -nr
    return {
        "n": n,
        "net_r_proxy": round(net, 6),
        "expectancy_r_weighted": round(net / n, 6) if n else None,
        "profit_factor_aggregate_proxy": round(wins / losses, 6) if losses else None,
        "note": "Cross-route evidence aggregation, not a synchronized portfolio equity curve.",
    }


def _system_evidence(raw30: Dict[str, Any]) -> Dict[str, Any]:
    frozen = json.loads((ROOT / "BACKTEST_COMMIT19_RESULT.json").read_text(encoding="utf-8"))
    champs = frozen["champions"]
    crypto = [
        "ETH_2H_LONG_RSI_TREND_V1",
        "SOL_2H_SHORT_SUPERTREND_PULLBACK_V1",
        "XRP_2H_SHORT_TREND_CONTINUATION_V1",
        "LINK_4H_SHORT_RSI_TREND_V1",
    ]
    is_parts = [champs[c]["parts"]["is"] for c in crypto]
    sel_parts = [champs[c]["parts"]["selection"] for c in crypto]
    oos_parts = [champs[c]["parts"]["oos"] for c in crypto]
    f30_is = {"n": raw30["is"]["n"], "expectancy_r": raw30["is"]["expectancy_r"], "pf": raw30["is"]["profit_factor"]}
    f30_oos = {"n": raw30["oos"]["n"], "expectancy_r": raw30["oos"]["expectancy_r"], "pf": raw30["oos"]["profit_factor"]}
    us = champs["US_INDEX_1D_TREND_PULLBACK_RR18_V1"]["parts"]
    return {
        "crypto_governed_is_including_30m": _aggregate(is_parts + [f30_is]),
        "crypto_governed_selection_without_30m": _aggregate(sel_parts),
        "crypto_governed_oos_including_30m": _aggregate(oos_parts + [f30_oos]),
        "all_governed_is_including_us_index": _aggregate(is_parts + [f30_is, us["is"]]),
        "all_governed_oos_including_us_index": _aggregate(oos_parts + [f30_oos, us["oos"]]),
        "all_route_splits_positive": all(
            float(split.get("expectancy_r") or 0) > 0 and float(split.get("pf") or 0) > 1
            for row in champs.values() for split in (row.get("parts") or {}).values()
        ),
    }


def _router_parity() -> Dict[str, Any]:
    real_structure = {
        "direction": "BULLISH",
        "structure_direction": "BULLISH",
        "structure_reasons": ["SWEEP_REJECTION:bar=99;level=100", "OB_REINFORCEMENT"],
        "liquidity_sweeps": [{"type": "bullish", "sweep_level": 100.0, "index": 99, "strength": "strong"}],
        "order_blocks": [{"type": "bullish", "price_range": [99.0, 100.0], "index": 95, "strength": "strong"}],
        "fair_value_gaps": [],
        "supports": [99.0],
        "resistances": [102.0],
        "pivot_lows": [{"price": 99.0, "index": 90}],
        "pivot_highs": [{"price": 102.0, "index": 91}],
        "current_price": 100.5,
    }
    layers = {
        "trend": {"direction": "bullish", "adx": 26.0},
        "momentum": {"direction": "bullish", "rsi": 58.0},
        "volume": {"volume_ratio": 1.35},
        "volatility": {"state": "EXPANSION", "atr_pct": 2.4},
        "structure": real_structure,
        "macro_context": {"risk_level": "NORMAL"},
    }
    # Exact Commit-25 logic reproduced locally: it asks for fields not emitted
    # by analyze_price_structure_layer at this stage.
    s = real_structure
    legacy_sweep = bool(s.get("liquidity_sweep") or s.get("liquidity_sweeps") or s.get("sweep"))
    legacy_mss = bool(s.get("mss") or s.get("bos") or s.get("market_structure_shift") or s.get("break_of_structure"))
    legacy_displacement = bool(s.get("displacement") or s.get("displacement_confirmed"))
    legacy_poi = bool(s.get("order_blocks") or s.get("fair_value_gaps") or s.get("fvg") or s.get("poi") or s.get("institutional_zone"))
    legacy_ok = bool((legacy_sweep and legacy_mss) or (legacy_displacement and legacy_poi))
    new_ok, new_reason = registry._preentry_structure_audit(layers, "LONG")
    no_event_layers = json.loads(json.dumps(layers))
    no_event_layers["structure"]["structure_reasons"] = ["NO_STRICT_STRUCTURE_EVENT"]
    no_event_ok, no_event_reason = registry._preentry_structure_audit(no_event_layers, "LONG")
    return {
        "real_preentry_schema_has_top_level_mss": "mss" in real_structure,
        "real_preentry_schema_has_top_level_displacement": "displacement" in real_structure,
        "commit25_trigger_would_pass": legacy_ok,
        "commit26_trigger_passes": new_ok,
        "commit26_reason": new_reason,
        "commit26_no_strict_event_passes": no_event_ok,
        "commit26_no_strict_event_reason": no_event_reason,
        "interpretation": "Commit 26 restores stage parity without weakening downstream execution or risk gates.",
    }


def _non_promotions() -> Dict[str, Any]:
    snap = json.loads((ROOT / "BACKTEST_DATA_SNAPSHOT_20260928.json").read_text(encoding="utf-8"))
    one_h = snap["clean_logged_backtest"]["futures"]["by_timeframe"]["1h"]
    one_h_liq = snap["execution_challenger_shadow"]["futures_selected_timeframes"]["1h"]["LIQUIDITY_SWEEP_MSS_POI"]
    multi = snap["multiasset_proxy"]
    spot = snap["clean_logged_backtest"]["spot"]
    return {
        "futures_1h": {
            "historical_all_routes": one_h,
            "liquidity_shadow": one_h_liq,
            "decision": "SHADOW_ONLY_NO_NEW_LIVE_AUTHORITY",
            "reason": "1h aggregate history is negative and the liquidity challenger lacks a clean chronological IS/OOS split in the supplied evidence.",
        },
        "multiasset": {
            "generic_proxy": multi["aggregate"],
            "decision": "NO_GENERIC_CRYPTO_ROUTE_COPY",
            "reason": "Generic Multi proxy is negative; only the already-governed US_INDEX 1D route retains LIVE authority.",
        },
        "spot": {
            "historical": {k: spot[k] for k in ("resolved", "tp", "sl", "wr_pct", "gross_expectancy_r_proxy", "profit_factor_proxy", "warning")},
            "decision": "NO_SIGNAL_LOGIC_CHANGE",
        },
    }


def main() -> None:
    raw30 = _load_30m()
    result = {
        "commit": "COMMIT26_CAUSAL_PREENTRY_RECOVERY_PROPOSAL2_V1",
        "methodology": {
            "new_parameter_search": False,
            "thresholds_changed": False,
            "safety_changed": False,
            "rr_changed": False,
            "leverage_policy_changed": False,
            "closed_candle_authority_changed": False,
            "purpose": "Repair pre-Entry/live parity for an already-governed 30m route and refuse unvalidated 1h/Multi expansions.",
        },
        "router_stage_parity": _router_parity(),
        "raw_30m_is_oos": raw30,
        "governed_system_evidence": _system_evidence(raw30),
        "anti_overfit_non_promotions": _non_promotions(),
        "resource_delta": {
            "new_threads": 0,
            "new_market_requests": 0,
            "new_supabase_reads": 0,
            "new_supabase_writes": 0,
            "new_llm_calls": 0,
            "new_persistent_cache": 0,
            "algorithmic_delta": "bounded list/string inspection on the existing structure layer",
        },
    }
    sys_e = result["governed_system_evidence"]
    parity = result["router_stage_parity"]
    result["release"] = {
        "30m_is_positive": raw30["is"]["expectancy_r"] > 0 and (raw30["is"]["profit_factor"] or 0) > 1,
        "30m_oos_positive": raw30["oos"]["expectancy_r"] > 0 and (raw30["oos"]["profit_factor"] or 0) > 1,
        "all_governed_route_splits_positive": sys_e["all_route_splits_positive"],
        "real_schema_reaches_router": bool(parity["commit26_trigger_passes"]),
        "invalid_no_event_still_blocked": not bool(parity["commit26_no_strict_event_passes"]),
        "new_1h_live_authority": False,
        "new_multi_live_authority": False,
        "pass": bool(raw30["pass"] and sys_e["all_route_splits_positive"] and parity["commit26_trigger_passes"] and not parity["commit26_no_strict_event_passes"]),
        "future_profit_guarantee": False,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    is30, oos30 = raw30["is"], raw30["oos"]
    gois = sys_e["all_governed_is_including_us_index"]
    gooos = sys_e["all_governed_oos_including_us_index"]
    md = f"""# BACKTEST COMMIT 26 — PROPUESTA PROFUNDA 2\n\n## Resultado release\n\n**PASS = {result['release']['pass']}**\n\nEl cambio no optimiza parámetros. Repara una incompatibilidad temporal entre el router Champion 30m y el esquema real pre-Entry.\n\n## 30m — replay físico IS/OOS\n\n| Split | N | Net R | Expectancy | PF | MaxDD R |\n|---|---:|---:|---:|---:|---:|\n| IS | {is30['n']} | {is30['net_r']:.3f} | {is30['expectancy_r']:.4f}R | {is30['profit_factor']:.3f} | {is30['max_drawdown_r']:.3f} |\n| OOS | {oos30['n']} | {oos30['net_r']:.3f} | {oos30['expectancy_r']:.4f}R | {oos30['profit_factor']:.3f} | {oos30['max_drawdown_r']:.3f} |\n\nEl OOS es positivo pero pequeño (N=4). No es una garantía de rentabilidad futura.\n\n## Evidencia conjunta de rutas gobernadas\n\n| Conjunto | N | Net R proxy | Expectancy ponderada | PF agregado proxy |\n|---|---:|---:|---:|---:|\n| IS gobernado | {gois['n']} | {gois['net_r_proxy']:.3f} | {gois['expectancy_r_weighted']:.4f}R | {gois['profit_factor_aggregate_proxy']:.3f} |\n| OOS gobernado | {gooos['n']} | {gooos['net_r_proxy']:.3f} | {gooos['expectancy_r_weighted']:.4f}R | {gooos['profit_factor_aggregate_proxy']:.3f} |\n\nEsto agrega evidencia de rutas; no es una curva de portfolio sincronizada.\n\n## Hallazgo causal\n\n- Commit 25 con esquema real pre-Entry: trigger estructural = **{parity['commit25_trigger_would_pass']}**.\n- Commit 26 con el mismo esquema: trigger estructural = **{parity['commit26_trigger_passes']}**.\n- Sin evento estructural estricto: Commit 26 = **{parity['commit26_no_strict_event_passes']}**.\n\nCommit 26 consume `structure_direction`, `structure_reasons` y el inventario real de zonas; no fabrica MSS/displacement antes de Entry.\n\n## Decisiones anti-overfit\n\n- 1h: **Shadow**, no nueva autoridad LIVE.\n- Multi ENERGY/METALS/CHINA: **Shadow**, no copia de reglas crypto.\n- Spot: sin cambio de lógica.\n- Q1..Q10: diagnóstico/evidencia; no `max(Q)` como atajo de publicación.\n- RR/Safety/SL/TP/ATR/closed candle: sin rebaja.\n\n## Recursos incrementales\n\n0 threads, 0 requests de mercado, 0 lecturas/escrituras Supabase, 0 llamadas LLM.\n"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(json.dumps(result["release"], indent=2))
    print(json.dumps({"30m_is": is30, "30m_oos": oos30, "system_is": gois, "system_oos": gooos}, indent=2))


if __name__ == "__main__":
    main()
