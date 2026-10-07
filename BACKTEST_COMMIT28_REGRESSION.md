# Commit 28 — Backtest / regression evidence

Commit 28 no cambia reglas de selección histórica, thresholds ni geometrías objetivo. Por tanto no se reoptimiza el PnL: se reejecutó el backtest gobernado ya incluido en el repositorio y se exige paridad con Commit 27.

## Futures 30m pooled route

Con stress de coste histórico 0.118R por entrada:

- IS: N=11 · Net +1.702R · E +0.1547R · PF 1.2537 · MaxDD 2.236R
- OOS: N=4 · Net +3.928R · E +0.9820R · PF 4.5134 · MaxDD 1.118R
- Combined: N=15 · Net +5.630R · E +0.3753R · PF 1.7194

La muestra OOS es pequeña y no garantiza beneficio futuro.

## Post-geometry execution evidence

`LIQUIDITY_SWEEP_MSS_POI`:

- IS: N=11 · E +0.8592R · PF 3.363
- OOS: N=5 · E +1.8000R · 5 TP / 0 SL

La condición se mantiene post-geometría: sweep+MSS/BOS o displacement+POI.

## Multi fast lanes

No se promueve ninguna nueva ruta 1h/4h de Energy/Metals/China/US Index. La evidencia limpia class-specific IS/Selection/OOS no está disponible en el material suministrado.

## Conclusión estadística

Commit 28 es una reparación de integración. Al no cambiar el contrato de selección/backtest, conserva la evidencia histórica existente y evita crear un nuevo grado de libertad susceptible de overfitting.
