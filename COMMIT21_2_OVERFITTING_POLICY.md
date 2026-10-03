# Commit 21.2 — Anti-Overfitting Contract

- No parameters are fitted from current/last-close PnL.
- No threshold is lowered.
- The Strategy Bank is frozen; alternatives are exact-cell routes already declared for the same symbol/TF/action.
- CPQE gets more **context**, not more permissive thresholds.
- Route promotion requires the same publication gate and hard economic constraints.
- Fallback geometry remains non-Premium.
- Research/Champion evidence remains observational; no live result can mutate a route parameter during the signal cycle.
- Maximum two alternatives; one under RSS pressure.
- A route that only wins because a threshold was weakened is invalid by construction; this patch contains no such path.
