# Backtest / validación interna Commit 19.2.4

## Importante

El repositorio no contiene un dataset fila-a-fila versionado que incluya todos los Q1–Q9 originales (estructura detallada, MTF, order-flow, divergencias, balance, macro y economía) para las 15 filas de la cohorte 17.5.10. Por eso **no es honesto presentar un IS/OOS causal completo de los nueve factores como si existiera**.

Se hicieron dos controles distintos:

### 1. Control de no-promoción sobre la cohorte histórica disponible

Fuente: `BACKTEST_ROWS_17_5_10_PROFITABILITY.csv` de Commit 17.5.10.

- IS/DEV: 11 filas.
- OOS/HOLDOUT: 4 filas.
- La representación conservadora de Q1–Q9 con solamente las columnas históricas disponibles produjo **0 promociones automáticas** en IS y **0** en OOS.
- Esto evita que el nuevo motor convierta por sí solo la cohorte genérica histórica en Premium cuando faltan evidencias Q1–Q9.

Esto no demuestra rentabilidad de CPQE; demuestra que no abre una compuerta artificial sobre la cohorte antigua.

### 2. Control positivo sobre rutas históricas ya validadas

Se probaron tres células que ya tienen evidencia IS/Selection/OOS documentada por Research:

| Ruta | Q composite | CPQE |
|---|---:|---|
| ETH 2H LONG RSI_TREND | 77.88 | PASS |
| SOL 2H SHORT SUPERTREND_PULLBACK | 78.24 | PASS |
| XRP 2H SHORT TREND_CONTINUATION | 78.77 | PASS |

La evidencia histórica documentada de esas tres células es positiva en OOS, pero se conserva como evidencia histórica; **no se interpreta como garantía futura ni como un nuevo backtest causal del CPQE**.

### Decisión

CPQE se libera como autoridad LIVE de calidad contextual porque:

- no reduce los thresholds universales;
- no genera dirección;
- exige múltiples dimensiones Q1–Q9;
- no promociona la cohorte genérica histórica sin información suficiente;
- reconoce correctamente células ya validadas como configuraciones de alta calidad.

El siguiente dataset que se acumule en producción debe registrar Q1–Q9 por señal para ejecutar un backtest causal completo del propio CPQE con split cronológico IS / Selection / OOS / walk-forward.
