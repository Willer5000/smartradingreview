# Commit 21.2 Deep Root-Cause Audit

## Finding A — CPQE context starvation
The log shows directional votes, but RC9.2 reports `sin candidato ejecutable → PRECAUCION`. The existing CPQE implementation reads trend/momentum/structure from the `levels` result, while these structures are actually available in `calculate_entry_levels(...)` arguments. This creates a data-plumbing failure: Q1/Q2/Q6 and route selection can be evaluated from defaults/empty dictionaries. The direction can also become NEUTRAL in the safety wrapper when `levels['action']` is absent.

**Effect:** Q1-Q9 exists, but several dimensions are starved of the evidence they were designed to measure. A higher-quality candidate can therefore fail CPQE without violating any hard risk rule.

## Finding B — route engine memory stop
Commit 21.1 used route hard RSS=220 MB. The runtime log has `rss=222.6MB`, so the alternative Strategy Bank route is skipped before evaluation. 21.2 allows one bounded route after a non-aggressive cache shed and only when post-shed RSS <=222 MB; above that it preserves the baseline and skips alternatives.

## Finding C — route promotion could be re-blocked by stale setup family
After a promoted alternative, RC9.2 still read the original `contingency_playbook.setup_family`. 21.2 makes the promoted route family authoritative for that guard only. This does not bypass the guard; it makes the guard evaluate the route actually tested.

## Finding D — indicator charts were not actually independent
The 21.1 `changeToSignal` path waited for the light visual request to finish before starting heavy analysis. The Futures page itself did not issue an initial `/api/futures/visuals` call; the log therefore showed analysis calls but no visuals request. 21.2 fires the light visual route independently at page boot, on symbol/TF changes, and from signal navigation. Heavy analysis no longer waits for the chart request.

## Finding E — macro timeout adds avoidable latency
GDELT timeout is logged at 7s. Macro is context-only. 21.2 reduces the default/env cap to 3s to reduce worst-case page latency without changing trading authority.
