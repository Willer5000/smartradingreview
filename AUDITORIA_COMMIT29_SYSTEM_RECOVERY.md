# AUDITORÍA COMMIT 29 — CONSOLIDATED SYSTEM RECOVERY

## Objective

Resolve in one deployment the root causes observed after Commit 28: deployment ambiguity, primary-geometry execution failures, missing context being treated as neutral evidence, incorrect regime classification, free-plan OOM, UI/heavy contention, non-applicable traders appearing as NO_OPERAR, and validated LIVE cells being delayed behind a large Shadow/fallback universe.

## Root causes addressed

### 1. Deployment integrity
`commit29_main_entrypoint.py` imports the current core directly and verifies at boot that the native Futures/Multi execution ABI accepts `execution_observations`. `Procfile` and `render.yaml` both point to `commit29_main_entrypoint:app`. `/api/runtime/version` reports the logical version, entrypoint, source hashes, memory state and active hard contracts.

### 2. Primary geometry ABI
The full `futures_system.py` included in this release accepts and forwards `execution_observations`. This removes the production TypeError that could terminate execution before primary Entry/SL/TP existed. Because Multi inherits the Futures engine, the contract is shared consistently.

### 3. Missing context is ABSTAIN, not neutral market evidence
BTC/PAXG/ratio placeholders are marked unavailable. Correlation/rotation logic only uses them when real context is available. A missing ADX is no longer converted into `ADX=0 => lateral market`. Existing same-timeframe BTC context/snapshots are reused; no additional external request is introduced.

### 4. Regime bug
ADX >25 with conflicted DMI is now `TRANSITIONAL`, not incorrectly labelled `RANGING (20-25)`. ADX <20 remains RANGING; strongly aligned DMI remains TRENDING; extreme volatility remains HIGH_VOLATILITY. This prevents the wrong regime weights from changing committee influence.

### 5. Trader semantics
The Commit28/29 core preserves `ABSTAIN` for zero-confidence/non-applicable NO_OPERAR outcomes. A specialist outside its timeframe, neutral macro, or a model without coverage no longer appears as evidence against a trade. Evidence-backed NO_OPERAR (for example a confirmed false breakout objection) remains valid.

### 6. Render free-plan memory
Free-plan limits are tightened: soft 205 MB, hard 285 MB, heavy job start 190 MB, in-job abort 315 MB. Raw Futures cache is bounded to 4 entries, microstructure to 8, liquidation heatmaps to 8 resident objects, Multi deep analysis to 1 candidate and 6 automatic deep runs/day. Reconstructable caches/heatmaps are shed aggressively under pressure. Background permanent AI-scientist and macro watchdog threads are disabled in FREE_PLAN_LOCKDOWN; their functions remain available through scheduled/idempotent or cached/on-demand paths. Gunicorn remains 1 worker / 2 gthreads and recycles after 60±15 requests.

### 7. UI/heavy separation
When a heavy owner is active or RSS is high, `/api/futures/visuals` fails soft with HTTP 200/deferred rather than allocating another market-data DataFrame. The browser keeps the last valid chart. This is intended to avoid the observed 502/timeouts amplifying memory pressure.

### 8. Champion-first detection priority
The incremental scheduler first checks exact LIVE Champion cells whose closed candle is due, then continues through the rest of the universe. This does not add jobs, signals or authority; it reduces the probability that validated 30m/2h/4h cells are starved by Shadow/fallback cells on the single heavy slot.

### 9. Hard trading contracts unchanged
Safety Premium remains >=75, RR remains 1.8..3.5, ATR stress <=25%, real data and closed candle remain mandatory, fallback geometry remains ANALYSIS_ONLY, leverage is calculated after Entry/SL/TP and parallel Q remains diagnostic rather than a max-of-ten publication shortcut.

## What Commit 29 intentionally does NOT do

It does not manufacture four signals/day, lower Safety, promote fallback geometry, create Q11/Q12, add more traders, or promote Energy/Metals/China fast routes without clean OOS evidence. The supplied evidence does not support those promotions.

## Expected result

After deployment, validated cells should either (a) reach primary geometry and then be accepted/rejected by real economic guards, or (b) show a specific route/geometry blocker. The previous ambiguous chain `execution crash -> fallback -> fake Safety/ATR blockers` should no longer dominate. Runtime should remain materially below the 512 MB Render cgroup ceiling and the visual lane should remain usable while a heavy job runs.
