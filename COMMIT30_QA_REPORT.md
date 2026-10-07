# Commit 30 QA Report

## Behavioral tests
- Current governed regression selection (Commit22/23/25/27/28/29/30): **43 PASS**.
- **2 deselected** because they assert that deploy files must still point to Commit28/Commit29; Commit30 intentionally replaces those deployment contracts.
- Commit24.3 queue/safety/runtime regression script: **23 PASS / ALL PASS**.
- Commit30 dedicated suite: **12 PASS** (included in the 43 current tests).
- Deterministic BTC 1h incident replay: **PASS** (`DIRECTIONAL_IMPULSE_BEAR`, thesis `SHORT`, quality 98.5).

## Static validation
- Top-level Python modules compiled: **272**.
- Syntax errors: **0**.
- `node --check` PASS for:
  - `static/script.js`
  - `static/futures.js`
  - `static/chart_workspace.js`
  - `static/market_maker_frontend.js`

## Intentionally obsolete tests
`test_commit24_repair.py` contains the old `one-of-ten Q may promote` contract and is not a valid Commit30 acceptance test. The current architecture deliberately makes parallel Q diagnostic-only. Similarly, the old Commit28/29 deployment assertions must fail once Procfile/render point to Commit30.

## Boot limitation of audit container
The audit container does not have Flask installed, so a complete Gunicorn import cannot be executed locally. `commit30_main_entrypoint.py` therefore includes fail-fast boot guards for:
- native `execution_observations` ABI;
- Procfile/render target;
- deterministic reproduction of the BTC 1h impulse class.

## Resource impact
Commit30 adds:
- 0 permanent threads;
- 0 polling loops;
- 0 new data providers;
- 0 Supabase queries/writes;
- 0 Groq calls;
- one bounded in-process impulse-priority queue (max 12 entries, TTL 90 min).

Commit29 memory protections remain unchanged: one worker/two gthreads, 205 MB soft, 285 MB internal hard, 190 MB prestart, 315 MB in-job abort, reduced caches.
