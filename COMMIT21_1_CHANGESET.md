# Commit 21.1 — Fix: performance, visual-first charts and Premium thesis recovery

## Root causes addressed

1. Commit 20/21 changed Flask app attributes but the real Render memory guards read module globals. LOW_MEMORY_MODE still clamped the true start limit to 200 MB. 21.1 synchronizes the real module globals and uses a conservative 225 MB job-start budget with 235 MB soft / 300 MB hard.
2. Commit 21's route engine expected nested `strategy.alternatives`, while the production contingency playbook stores strategy/family metadata at the top level. 21.1 resolves alternatives directly from the frozen Default Strategy Bank for the exact Futures cell.
3. A `PRECAUCION` directional thesis could be routed through manual geometry and then forcibly overwritten as ANALYSIS_ONLY even when the underlying real execution pipeline had produced a genuine Premium result. 21.1 preserves and promotes only such a result when its existing publication gate is already PREMIUM.
4. Clicking a directional opportunity waited for heavy 9-trader analysis before visual charts rendered. 21.1 adds a lightweight OHLCV visual endpoint and renders candle/indicator charts first, then runs the heavy analysis exactly once.

## Safety / anti-overfitting contract

- No Premium threshold is lowered.
- No R/R 1.8–3.5 change.
- No Safety/SL/TP/ATR stress relaxation.
- No new direction is created.
- Route candidates come only from the existing frozen Strategy Bank and exact cell.
- No live outcome/PnL parameter fitting.
- Fallback geometry never becomes Premium.
- A route can reach Premium only when the existing execution/publication gate itself returns PREMIUM.
- At most one alternative route is tested for a fallback geometry; at most two for a near-Premium baseline, sequentially.
- No new worker, thread, paid API or options provider is added.

## Visuals

`/api/futures/visuals` returns up to 120 existing provider candles without running the heavy analysis. The browser immediately renders the candle/indicator workspace from that payload.

## Multi-Asset

The Commit 20.2 Saved Signals Multi-Activo contract is preserved unchanged.
