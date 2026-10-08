# QA Commit 33.4.3

## Current-core validation

Command:

`pytest -q test_commit33_4_3.py test_commit33_4_core.py test_execution_learning.py test_commit13_execution_geometry_v2.py test_commit17_5_execution_hardening.py test_rc9_8_execution_geometry.py`

Result:

**55 passed, 0 failed**

Python syntax/bytecode validation also passed for:
`app.py`, `futures_system.py`, `leverage_policy.py`, `review_trader.py`,
`multiasset_system.py`, `market_context.py`, `pipeline_integrity.py`,
`safety_profiles.py`, `publication_quality.py`.

## Verified contracts

- no live `_commit28_preexec_route` reference in `futures_system.py`;
- ReviewTrader imports `uuid` explicitly;
- Multi-Asset saved detail routes through `multiasset_system` by symbol/market;
- saved trade details remain available even if candle download fails;
- publication-grade leverage reaches full technical headroom;
- position size remains the monetary-risk control after leverage selection;
- lower-quality setups do not receive full leverage headroom;
- build removes Python/pytest caches before compilation;
- Futures snapshot schema = 7;
- pipeline generation = `33.4.3`;
- runtime identity = `COMMIT33_4_3_EXECUTION_ECONOMICS_DETAIL_CORE_V1`.

## Historical-version tests

Tests whose sole contract is that the runtime must still identify itself as
33.4.2/schema 6 are intentionally superseded and are not part of current-core QA.
No trading/geometry test was changed to manufacture a pass.
