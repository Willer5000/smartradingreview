# Commit 21 — Anti-Overfitting Policy

1. No live parameter fitting.
2. No threshold tuning from the latest candle/window.
3. No route selection from realized PnL.
4. No route creation during inference.
5. Route candidates must already exist in the frozen Strategy Bank.
6. Exact-cell market/symbol/timeframe/action scope is mandatory.
7. Regime and volatility must match the current snapshot.
8. Independent functional-family minimum remains the Strategy Bank contract.
9. Publication still depends on the unchanged production gate + CPQE.
10. A fallback geometry can never become Premium merely because a route was tried.
11. Two-alternative cap is fixed and independent of recent success rate.
12. Route statistics are collected for Research; they do not feed an online optimizer.
