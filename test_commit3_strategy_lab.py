import unittest
import numpy as np
import pandas as pd
from trendline_strategy_lab import analyze_trendline_strategy_lab
from strategy_registry import default_registry_snapshot
from historical_research import run_historical_strategy_research

class Commit3Tests(unittest.TestCase):
    def _df(self, n=140):
        x=np.arange(n,dtype=float); base=100+x*0.08+np.sin(x/4)*0.5
        return pd.DataFrame({"time":pd.date_range("2026-01-01",periods=n,freq="h"),"open":base-0.1,"high":base+0.5,"low":base-0.5,"close":base,"volume":np.full(n,1000.0)})
    def test_registry_shadow(self):
        snap=default_registry_snapshot(); self.assertFalse(snap["production_authority"]); self.assertTrue(all(v["state"]=="SHADOW" for v in snap["strategies"].values()))
    def test_trendline_guardrails(self):
        r=analyze_trendline_strategy_lab(self._df(),"BTC-USDT","1h","futures")
        self.assertTrue(r["shadow_only"]); self.assertFalse(r["affects_vote"]); self.assertFalse(r["affects_levels"])
    def test_research_is_separate(self):
        r=run_historical_strategy_research(self._df(),"BTC-USDT","1h",40)
        self.assertEqual(r["cohort"],"HISTORICAL_RESEARCH"); self.assertFalse(r["production_authority"])

if __name__ == "__main__": unittest.main()
