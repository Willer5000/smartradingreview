# COMMIT 29 — QA REPORT

## Current-generation regression suite

Command: `pytest test_commit29_system_recovery.py test_commit28_core_recovery.py test_commit27_contextual_core.py test_commit25_contextual_authority.py test_commit23_parallel_quality.py test_commit22_context_quality.py -k "not deploy_points_to_commit28"`

Result: **32 passed, 1 deselected**.

The deselected test is intentionally obsolete: it asserts that deploy files must still point to Commit 28. Commit 29 must point to Commit 29.

## Static compilation

- Python modules compiled: **274**
- Syntax failures: **0**
- `node --check static/futures.js`: PASS
- `node --check static/script.js`: PASS
- `node --check static/chart_workspace.js`: PASS

## Contracts explicitly tested

- strong ADX + directional conflict => TRANSITIONAL, not RANGING;
- missing/default context is unavailable, not neutral evidence;
- Procfile/render target Commit29;
- runtime version endpoint and pressure-safe visual lane are present;
- bounded liquidation heatmap cache and in-job resource abort are present;
- Champion-first detection priority is present;
- Safety 75 / RR 1.8..3.5 / ATR stress 25 remain unchanged;
- native `execution_observations` ABI exists in Futures.

## Legacy-test note

A broad set of historical tests contains assertions for superseded Commit24/25/28 behavior (including older deployment strings and older Q/publication semantics). They are not reported as passing. Release acceptance is based on the current-generation contract suite plus compilation and the unchanged trading backtest.
