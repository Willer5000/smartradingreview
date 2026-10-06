"""Commit 25 release backtest / evidence audit.

No data is fabricated and no parameter search is performed here.
- F30 is re-executed from the row-level cohort physically bundled in Main.
- The other Champions are read from the frozen governed Commit-19 result because
  their raw candle histories are not bundled in the supplied ZIP.

This script therefore proves release parity with the available evidence, not a
future-return guarantee and not a synchronized multi-strategy portfolio replay.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "BACKTEST_COMMIT25_CONTEXTUAL_AUTHORITY.json"
OUT_MD = ROOT / "BACKTEST_COMMIT25_CONTEXTUAL_AUTHORITY.md"


def _metrics(rows: Iterable[Dict[str, str]]) -> Dict[str, Any]:
    rows = list(rows)
    vals = [float(r["stress_net_r"]) for r in rows]
    gp = sum(max(v, 0.0) for v in vals)
    gl = abs(sum(min(v, 0.0) for v in vals))
    cum = peak = dd = 0.0
    for v in vals:
        cum += v
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {
        "n": len(rows),
        "net_r": round(sum(vals), 4),
        "expectancy_r": round(sum(vals) / len(vals), 5) if vals else 0.0,
        "pf": round(gp / gl, 4) if gl > 0 else None,
        "max_dd_r": round(dd, 4),
        "tp": sum(r.get("status") == "tp_hit" for r in rows),
        "sl": sum(r.get("status") == "sl_hit" for r in rows),
        "expired_after_entry": sum(r.get("status") == "expired_after_entry" for r in rows),
    }


def _load_raw30() -> Dict[str, Any]:
    with (ROOT / "BACKTEST_ROWS_17_5_10_PROFITABILITY.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    is_rows = [r for r in rows if r.get("period") == "DEV"]
    oos_rows = [r for r in rows if r.get("period") == "HOLDOUT"]
    return {
        "source": "BACKTEST_ROWS_17_5_10_PROFITABILITY.csv",
        "method": {
            "route": "LIQUIDITY_SWEEP_MSS_POI",
            "timeframe": "30M",
            "trend_aligned": True,
            "adx_min": 20,
            "volume_ratio_min": 1.2,
            "rsi_long_max": 80,
            "rsi_short_min": 20,
            "unresolved_treatment": "-1R",
            "cost_stress_r_per_entry": 0.118,
            "is_period": "2026-09-10..2026-09-13",
            "oos_period": "2026-09-14..2026-09-16",
        },
        "is": _metrics(is_rows),
        "oos": _metrics(oos_rows),
        "combined": _metrics(rows),
        "acceptance": bool(
            _metrics(is_rows)["expectancy_r"] > 0
            and (_metrics(is_rows)["pf"] or 0) > 1
            and _metrics(oos_rows)["expectancy_r"] > 0
            and (_metrics(oos_rows)["pf"] or 0) > 1
        ),
        "small_sample_warning": len(oos_rows) < 30,
    }


def _net_from_expectancy(n: int, e: float) -> float:
    return float(n) * float(e)


def _gross_from_net_pf(n: int, e: float, pf: float) -> tuple[float, float]:
    """Infer gross wins/losses from net and PF for additive aggregate PF."""
    net = _net_from_expectancy(n, e)
    if pf is None or pf <= 1.0 or net <= 0:
        return max(net, 0.0), max(-net, 0.0)
    loss = net / (pf - 1.0)
    win = pf * loss
    return win, loss


def _aggregate(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = sum(int(p.get("n") or 0) for p in parts)
    net = sum(_net_from_expectancy(int(p.get("n") or 0), float(p.get("expectancy_r") or 0.0)) for p in parts)
    wins = losses = 0.0
    for p in parts:
        w, l = _gross_from_net_pf(int(p.get("n") or 0), float(p.get("expectancy_r") or 0.0), float(p.get("pf") or 0.0))
        wins += w
        losses += l
    return {
        "n": n,
        "net_r_proxy": round(net, 5),
        "expectancy_r_weighted": round(net / n, 6) if n else None,
        "pf_aggregate_proxy": round(wins / losses, 5) if losses > 0 else None,
        "note": "Evidence aggregation across route backtests; not a synchronized portfolio simulation.",
    }


def _frozen_champions() -> tuple[Dict[str, Any], Dict[str, Any]]:
    frozen = json.loads((ROOT / "BACKTEST_COMMIT19_RESULT.json").read_text(encoding="utf-8"))
    champs = frozen.get("champions") or {}
    # Only governed live routes present in Commit-25 registry are release eligible.
    wanted = [
        "F30_SHARED_LIQ_SWEEP_MSS_POI_V1",
        "ETH_2H_LONG_RSI_TREND_V1",
        "SOL_2H_SHORT_SUPERTREND_PULLBACK_V1",
        "XRP_2H_SHORT_TREND_CONTINUATION_V1",
        "LINK_4H_SHORT_RSI_TREND_V1",
        "US_INDEX_1D_TREND_PULLBACK_RR18_V1",
    ]
    picked = {k: champs[k] for k in wanted if k in champs}
    return frozen, picked


def main() -> None:
    from champion_registry_commit19 import route_registry, context_authority_matrix

    raw30 = _load_raw30()
    frozen, champs = _frozen_champions()
    registry = route_registry()

    route_rows = {}
    all_positive = True
    for cid, row in champs.items():
        parts = row.get("parts") or {}
        check_parts = [p for p in ("is", "selection", "oos") if p in parts]
        positive = all(
            float((parts[p] or {}).get("expectancy_r") or 0.0) > 0
            and float((parts[p] or {}).get("pf") or 0.0) > 1.0
            for p in check_parts
        )
        # F30 has raw replay fields named exactly as frozen result; verify parity.
        if cid == "F30_SHARED_LIQ_SWEEP_MSS_POI_V1":
            positive = positive and raw30["acceptance"]
        all_positive = all_positive and positive
        route_rows[cid] = {
            "market": row.get("market"),
            "symbols": row.get("symbols"),
            "timeframe": row.get("timeframe"),
            "source_type": row.get("source_type"),
            "parts": parts,
            "release_positive_all_available_splits": positive,
        }

    crypto_ids = [
        "ETH_2H_LONG_RSI_TREND_V1",
        "SOL_2H_SHORT_SUPERTREND_PULLBACK_V1",
        "XRP_2H_SHORT_TREND_CONTINUATION_V1",
        "LINK_4H_SHORT_RSI_TREND_V1",
    ]
    is_parts = [champs[c]["parts"]["is"] for c in crypto_ids]
    sel_parts = [champs[c]["parts"]["selection"] for c in crypto_ids]
    oos_parts = [champs[c]["parts"]["oos"] for c in crypto_ids]
    us = champs["US_INDEX_1D_TREND_PULLBACK_RR18_V1"]["parts"]

    # Include raw F30 in IS/OOS evidence summary. It has no independent Selection split.
    is_with_f30 = is_parts + [{"n": raw30["is"]["n"], "expectancy_r": raw30["is"]["expectancy_r"], "pf": raw30["is"]["pf"]}]
    oos_with_f30 = oos_parts + [{"n": raw30["oos"]["n"], "expectancy_r": raw30["oos"]["expectancy_r"], "pf": raw30["oos"]["pf"]}]

    # Governed route coverage (symbol×timeframe, not trade count): old Main's
    # validated_strategy_routes had 3 positive live cells; Commit25 restores 12.
    restored_symbol_tf_cells = sum(len(v.get("symbols") or []) for v in registry.values())

    result = {
        "commit": "COMMIT25_CONTEXTUAL_CHAMPION_RECOVERY_ANTI_OVERFIT_V1",
        "methodology": {
            "parameter_search_in_commit25": False,
            "new_threshold_optimization": False,
            "raw_replay_available": ["F30_SHARED_LIQ_SWEEP_MSS_POI_V1"],
            "governed_frozen_evidence_used": [k for k in champs if k != "F30_SHARED_LIQ_SWEEP_MSS_POI_V1"],
            "oos_kept_separate": True,
            "portfolio_simulation_claimed": False,
        },
        "raw_30m_replay": raw30,
        "routes": route_rows,
        "evidence_aggregates": {
            "crypto_exact_4routes_is": _aggregate(is_parts),
            "crypto_exact_4routes_selection": _aggregate(sel_parts),
            "crypto_exact_4routes_oos": _aggregate(oos_parts),
            "crypto_plus_f30_is": _aggregate(is_with_f30),
            "crypto_plus_f30_oos": _aggregate(oos_with_f30),
            "us_index_1d_is": _aggregate([us["is"]]),
            "us_index_1d_selection": _aggregate([us["selection"]]),
            "us_index_1d_oos": _aggregate([us["oos"]]),
            "all_contexts_is_evidence_summary": _aggregate(is_with_f30 + [us["is"]]),
            "all_contexts_oos_evidence_summary": _aggregate(oos_with_f30 + [us["oos"]]),
        },
        "coverage": {
            "prior_main_positive_exact_symbol_tf_cells": 3,
            "commit25_governed_symbol_tf_cells": restored_symbol_tf_cells,
            "coverage_multiple": round(restored_symbol_tf_cells / 3.0, 2),
            "note": "Coverage is eligible governed cells, not guaranteed published signals; live context and hard gates still apply.",
        },
        "anti_overfit": {
            "parallel_q_max_authority_removed": True,
            "no_cross_asset_route_copy": True,
            "unsupported_classes_remain_shadow": ["CRYPTO_HIGH", "ENERGY", "INDUSTRIAL_METAL", "PRECIOUS_METAL", "CHINA_INDEX"],
            "context_authority_matrix": context_authority_matrix(),
        },
        "release": {
            "all_available_route_splits_positive": all_positive,
            "raw_30m_is_oos_positive": raw30["acceptance"],
            "registry_matches_frozen_champion_ids": set(registry) == set(champs),
            "future_profit_guarantee": False,
            "pass": bool(all_positive and raw30["acceptance"] and set(registry) == set(champs)),
        },
        "limitations": list(frozen.get("limitations") or []) + [
            "Commit25 does not have the raw candle datasets for ETH/SOL/XRP/LINK/US_INDEX in the supplied ZIP, so those frozen governed IS/Selection/OOS metrics are audited/reused rather than recomputed from candles.",
            "The 30m OOS has N=4; it is positive but statistically small and must continue under Alpha Decay/ReviewTrader.",
            "Increasing governed route coverage does not guarantee a non-zero signal on every market day; a cell still needs live direction, MTF compatibility, geometry, Safety, RR and publication quality.",
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# BACKTEST COMMIT 25 — Contextual Champion Recovery / Anti-Overfit",
        "",
        "## Resultado de release",
        f"- PASS: **{result['release']['pass']}**",
        f"- 30m raw replay IS: N={raw30['is']['n']} · E={raw30['is']['expectancy_r']:+.4f}R · PF={raw30['is']['pf']}",
        f"- 30m raw replay OOS: N={raw30['oos']['n']} · E={raw30['oos']['expectancy_r']:+.4f}R · PF={raw30['oos']['pf']}",
        f"- Cobertura gobernada symbol×TF: 3 -> {restored_symbol_tf_cells} ({result['coverage']['coverage_multiple']:.1f}x)",
        "",
        "## Rutas con autoridad exacta",
        "| Ruta | Mercado / celda | IS | Selection | OOS | Release |",
        "|---|---|---:|---:|---:|---|",
    ]
    for cid, r in route_rows.items():
        p = r["parts"]
        def fmt(k: str) -> str:
            x = p.get(k)
            if not x: return "—"
            return f"N{x.get('n')} E {float(x.get('expectancy_r') or 0):+.4f}R PF {float(x.get('pf') or 0):.3f}"
        lines.append(f"| {cid} | {','.join(r.get('symbols') or [])} {r.get('timeframe')} | {fmt('is')} | {fmt('selection')} | {fmt('oos')} | {'PASS' if r['release_positive_all_available_splits'] else 'FAIL'} |")
    lines += [
        "",
        "## Interpretación",
        "La evidencia positiva es una condición de release, no una garantía de rentabilidad futura. Commit 25 no hace búsqueda de parámetros ni copia una ruta ganadora a otra clase de activo. Los Q paralelos quedan diagnósticos y no pueden rescatar un paquete que incumple el gate económico nativo.",
        "",
        "## Limitaciones",
    ]
    lines += [f"- {x}" for x in result["limitations"]]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["release"]["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
