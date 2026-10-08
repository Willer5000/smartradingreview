# Commit 33.4.3 — Execution Economics + Saved Detail Core

## Scope
This commit is a direct core correction over 33.4.2. It does not install an overlay,
monkeypatch or historical runtime authority.

### 1. Saved Multi-Asset detail is market-aware
`/api/saved_signals/<id>/chart_data` now chooses `multiasset_system` for logical
Multi-Asset symbols instead of forcing the crypto Futures symbol map. The saved
trade record, technical sheet and learning review are returned even if the candle
provider is temporarily unavailable; chart availability is independent metadata.

### 2. Leverage restores the maximum technically permissible model
Leverage and position size again have separate responsibilities. For a publication-
grade setup (Safety >=75 and aggregate execution quality >=75), leverage uses the
full technical headroom constrained by contract maximum, structural SL/ATR,
liquidation buffer and the emergency cap. Monetary risk is controlled afterwards
with the recommended allocation fraction. Lower-quality setups remain reduced.

No confidence percentage is treated as a probability of TP. A closer TP by itself
cannot justify more leverage; the relevant risk variables are SL distance, ATR,
liquidation buffer, contract limit and execution quality. A high-quality fast setup
therefore no longer lands at 3x/5x merely because of a quality multiplier when its
true technical ceiling is materially higher.

### 3. Stale source/bytecode hygiene
`build.sh` removes `__pycache__`, `.pytest_cache`, `.pyc` and `.pyo` before compiling.
These directories are not application state and must also be deleted locally when
replacing one full commit tree with another.

### 4. Generation invalidation
Futures cache schema is 7 and pipeline generation is `33.4.3`, so malformed/stale
33.4.2 snapshots cannot masquerade as new confirmed signals.

## Deployment identity
`/api/runtime/version` must report:
`COMMIT33_4_3_EXECUTION_ECONOMICS_DETAIL_CORE_V1`

Boot log must contain:
`✅ [33.4.3] núcleo canónico activo`
