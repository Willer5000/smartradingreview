# Commit 21.2 Fix — Root-Cause Integration

## Objectives
1. Make CPQE receive the actual trend/momentum/structure context at publication time.
2. Make a Premium Strategy Bank alternative survive the subsequent setup-aware execution guard.
3. Allow a bounded alternative route under moderate RSS pressure without lowering any Premium threshold.
4. Make the indicator/candle lane independent from heavy analysis and prime it on Futures page load/change.
5. Cut macro GDELT worst-case wait from 7s to 3s; macro remains context-only.

## Hard contracts preserved
- Safety >= 75 for official Premium.
- TP >= 55.
- SL >= 60.
- RR 1.8..3.5.
- loss-at-SL and ATR-stress guards unchanged.
- No new direction from CPQE or PPE.
- No live-outcome parameter fitting.
- Max 2 alternate routes; 1 under RSS pressure.
- One worker / two threads / one heavy slot.
- No new paid APIs or workers.

## Root cause fixed
The CPQE publication wrapper previously received `levels` without the full `trend`, `momentum`, and `structure` objects. The level payload also did not reliably carry `symbol/action`, so Q1/Q2/Q6/route/direction could fall back to neutral/default values. 21.2 carries the already-computed context through a private, transient `_cpqe_context` payload and removes it before the result leaves the route.

The Strategy Route Engine then re-runs the same existing publication gate with that full context; it does not change geometry or thresholds.
