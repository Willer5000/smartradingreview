# Leverage preservation — Commit 18

Commit 18 **does not replace or tune** `leverage_policy.py`.

The current policy in the audited HEAD is `RC9_7_14_STANDARD_TECHNICAL_MAX_LEVERAGE_V6`. Its design intentionally avoids the older behaviour where a wide structural SL forced 2x/3x solely because of a money-risk target:

- leverage is selected from technical/contract constraints;
- hard ceilings are exchange max, liquidation buffer, technical risk/ATR caps and emergency cap;
- quality controls how much technical headroom is used;
- the monetary loss budget is managed mainly by `recommended_risk_allocation_fraction`, separately from leverage;
- timeframe max is a reference, not an arbitrary hard ceiling;
- uncalibrated confidence is not treated as literal TP probability.

Commit 18 only improves the geometry supplied **before** leverage. In the regression fixture, Entry/SL changes from an SL inside the reaction block to an Entry at the block and SL beyond invalidation, while the pre-existing leverage field remains unchanged.

If the existing leverage engine later computes a different leverage because the corrected geometry changes a genuine technical/liquidation cap, that is expected behaviour of the existing V6 policy, not a reintroduction of x1/x2 caps.
