# BACKTEST COMMIT 29 — REGRESSION / PARITY

Commit 29 is a **system-recovery release**, not a strategy re-optimization. It does not lower Safety, RR, SL/TP quality or ATR stress limits, and it does not add a signal quota. Therefore the correct quantitative test is **parity**: previously validated LIVE routes must retain their IS/OOS evidence while the runtime/plumbing changes are applied.

## Replayed 30m cohort

The repository cohort `BACKTEST_ROWS_17_5_10_PROFITABILITY.csv` was replayed using the existing stress-net R field.

| Split | N | Net R | Expectancy | PF | MaxDD |
|---|---:|---:|---:|---:|---:|
| IS/DEV | 11 | +1.702 | +0.1547 R/trade | 1.254 | 2.236 R |
| OOS/Holdout | 4 | +3.928 | +0.9820 R/trade | 4.513 | 1.118 R |
| Combined | 15 | +5.630 | +0.3753 R/trade | 1.719 | 2.236 R |

## Interpretation

The observed sign remains positive IS and OOS. This is evidence that Commit 29 did **not** change the trading thresholds that produced the audited 30m cohort. It is not proof of future profitability: OOS N=4 is small.

Commit 29 changes detection priority so statistically validated LIVE cells are evaluated first when their candle closes. Priority does **not** create authority: a cell still has to pass the same Champion route, primary geometry, Safety, RR, ATR, real-data and closed-candle contracts.

## Coverage limitation

The supplied Research artifacts do not contain clean class-specific IS/Selection/OOS/WF evidence that would justify promoting Energy, Industrial Metals, Precious Metals or China 1h/4h directly to LIVE. Those remain Shadow/Research. Forcing them LIVE to achieve four signals/day would be rule-fitting.
