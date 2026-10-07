# Commit 30.1 — Evidencia de estabilidad y regresión

Fuente congelada: `BACKTEST_PARAMETER_STABILITY_17_5_10.json`, creada antes del incidente del 6–7 de octubre de 2026.

| Contrato F30 | Dev N | Dev net stressed R | Dev E/R | Holdout N | Holdout net stressed R | Holdout E/R | Total N | Total net stressed R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| anterior: ADX20 / Vol1.20 / RSI80 | 11 | +1.702 | +0.1547 | 4 | +3.928 | +0.9820 | 15 | +5.630 |
| 30.1: ADX20 / Vol1.00 / RSI80 | 16 | +2.563 | +0.1602 | 5 | +5.610 | +1.1220 | 21 | +8.173 |

El archivo de estabilidad no conserva PF para el punto Vol1.00, por lo que **no se inventa**. Tampoco constituye un nuevo OOS limpio: el histórico ya era conocido antes de Commit30.1.

### Interpretación

El punto Vol1.00 es más amplio, tiene mayor N y permanece positivo en Development y holdout. Sin embargo, también tiene mayor net R que el punto originalmente seleccionado, lo que introduce riesgo de selección si se lo tratara como una nueva estrategia ganadora. Commit30.1 lo usa sólo como **routing pre-Entry**, manteniendo intactos los hard guards de publicación.

### Lo que sigue sin validarse

- `DIRECTIONAL_IMPULSE` 1h como estrategia LIVE independiente: **NO**.
- Fast Multi-Activo 1h/4h: **NO**.
- Rentabilidad futura: **NO garantizada**.
- PF del punto Vol1.00: **no disponible en el artefacto congelado**.

La ruta general Futures 1h histórica sigue siendo débil; por eso el 1h sólo despierta/prioriza 30m.
