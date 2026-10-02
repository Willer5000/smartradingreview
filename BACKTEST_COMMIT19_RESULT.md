# Commit 19 — Backtest / evidence report

## Release decision
- All release checks: **PASS**
- Future-profit guarantee: **NO** (historical evidence only).

## 30m raw replay from bundled cohort
- IS: N=11 · Net=+1.702R · Expectancy=+0.1547R · PF=1.254
- OOS: N=4 · Net=+3.928R · Expectancy=+0.9820R · PF=4.513
- Combined: N=15 · Net=+5.630R · Expectancy=+0.3753R · PF=1.719

## Registry evidence

| Champion | Evidence | IS | Selection | OOS | Release |
|---|---|---:|---:|---:|---|
| F30_SHARED_LIQ_SWEEP_MSS_POI_V1 | RAW_COHORT_REPLAY_IN_ZIP | N11 · E +0.1547R · PF 1.254 | — | N4 · E +0.9820R · PF 4.513 | PASS |
| ETH_2H_LONG_RSI_TREND_V1 | GOVERNED_RESEARCH_CAUSAL_EVIDENCE | N40 · E +0.0866R · PF 1.185 | N14 · E +0.1646R · PF 1.482 | N14 · E +0.3331R · PF 1.968 | PASS |
| SOL_2H_SHORT_SUPERTREND_PULLBACK_V1 | GOVERNED_RESEARCH_CAUSAL_EVIDENCE | N23 · E +0.1015R · PF 1.138 | N8 · E +0.5033R · PF 1.873 | N8 · E +0.3130R · PF 1.416 | PASS |
| XRP_2H_SHORT_TREND_CONTINUATION_V1 | GOVERNED_RESEARCH_CAUSAL_EVIDENCE | N52 · E +0.1113R · PF 1.212 | N17 · E +0.3306R · PF 1.826 | N18 · E +0.2785R · PF 1.519 | PASS |
| LINK_4H_SHORT_RSI_TREND_V1 | GOVERNED_RESEARCH_CAUSAL_EVIDENCE_PARITY_REPAIRED_IN_C19 | N49 · E +0.0071R · PF 1.016 | N16 · E +0.5422R · PF 3.633 | N17 · E +0.2754R · PF 1.853 | PASS |
| US_INDEX_1D_TREND_PULLBACK_RR18_V1 | PRIOR_INDEPENDENT_PUBLIC_HISTORY_BACKTEST_EVIDENCE | N213 · E +0.0211R · PF 1.043 | N71 · E +0.0130R · PF 1.030 | N72 · E +0.5055R · PF 2.912 | PASS |

## Limitations

- 30m is the only route whose row-level cohort is physically present in the attached Main ZIP and is re-executed here.
- ETH/SOL/XRP/LINK use governed causal IS/Selection/OOS metrics audited from Research/Supabase; their raw candle datasets are not in the attached Main ZIP.
- US_INDEX 1D uses the independent public-history IS/Selection/OOS result recorded by the Commit-19 audit; the external raw price dataset is not bundled here.
- Positive historical IS/OOS evidence is a release criterion, not a guarantee of future profitability.
