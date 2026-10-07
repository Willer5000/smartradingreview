"""Commit 30.1 offline acceptance/regression evidence.

No market/API/DB calls. Reads the frozen pre-incident parameter stability file
and reports the old live point (Vol1.20) versus the broader frozen point
(Vol1.00). This does NOT claim a new 1h alpha or prove future profitability.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "BACKTEST_PARAMETER_STABILITY_17_5_10.json"
OUT = ROOT / "BACKTEST_COMMIT30_1_RESULT.json"

def point(rows, adx, volume, rsi):
    for row in rows:
        if row.get("adx_min") == adx and float(row.get("volume_min")) == float(volume) and row.get("rsi_cap") == rsi:
            return dict(row)
    raise KeyError((adx, volume, rsi))

def enrich(row):
    out=dict(row)
    out["dev_expectancy_r"] = round(float(row["dev_net_stress_r"])/int(row["dev_n"]), 6) if row.get("dev_n") else None
    out["holdout_expectancy_r"] = round(float(row["holdout_net_stress_r"])/int(row["holdout_n"]), 6) if row.get("holdout_n") else None
    n=int(row.get("dev_n") or 0)+int(row.get("holdout_n") or 0)
    net=float(row.get("dev_net_stress_r") or 0)+float(row.get("holdout_net_stress_r") or 0)
    out["combined_n"] = n
    out["combined_net_stress_r"] = round(net, 6)
    out["combined_expectancy_r"] = round(net/n, 6) if n else None
    return out

def main():
    rows=json.loads(SRC.read_text(encoding="utf-8"))
    old=enrich(point(rows,20,1.2,80))
    broad=enrich(point(rows,20,1.0,80))
    result={
      "version":"COMMIT30_1_PROPOSAL3_FAST_LANE_BRIDGE_V1",
      "source":SRC.name,
      "source_frozen_before_2026_10_06_incident":True,
      "old_live_point":old,
      "broader_frozen_point":broad,
      "acceptance":{
        "same_adx_floor": broad["adx_min"] == old["adx_min"] == 20,
        "same_rsi_cap": broad["rsi_cap"] == old["rsi_cap"] == 80,
        "broader_has_more_dev_samples": broad["dev_n"] > old["dev_n"],
        "broader_has_more_holdout_samples": broad["holdout_n"] > old["holdout_n"],
        "broader_dev_positive": broad["dev_net_stress_r"] > 0,
        "broader_holdout_positive": broad["holdout_net_stress_r"] > 0,
        "profit_factor_available_for_broader_point": False,
        "direct_1h_live_authority_added": False,
        "multiasset_fast_live_authority_added": False,
        "future_profit_guarantee": False,
      },
      "methodology_note": (
        "Vol1.00 is a pre-existing frozen neighboring point, but it also has higher net R than the old selected point. "
        "Commit30.1 therefore uses it only as a broader PRE-ENTRY routing eligibility contract; hard geometry/Safety/RR gates remain unchanged. "
        "Prospective monitoring remains required and this is not clean new OOS."
      ),
    }
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__ == '__main__':
    main()
