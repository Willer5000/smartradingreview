# SmartradingReview — Commit 17.5.10 FINAL
## Backtest de aceptación · In-sample + Out-of-sample cronológico

### Objetivo

El backtest de aceptación de 17.5.10 NO se usa para bajar Safety, fabricar frecuencia ni fijar una cuota de señales. Se usa para comprobar que una ruta concreta que el sistema ya estudia (`LIQUIDITY_SWEEP_MSS_POI`, Futures 30m) tiene evidencia histórica positiva bajo un tratamiento deliberadamente conservador, y para impedir que los cambios de cobertura se conviertan en una excusa para sobreajustar parámetros.

### Cohorte congelada

Mercado: FUTURES  
TF: 30m  
Ruta: `LIQUIDITY_SWEEP_MSS_POI`  
Condiciones: tendencia alineada; ADX >= 20; volumen relativo >= 1.20; RSI LONG <= 80 / SHORT >= 20.

No se seleccionó el punto con mayor retorno de la rejilla. La vecindad de parámetros se conserva en `BACKTEST_PARAMETER_STABILITY_17_5_10.json`, incluidas configuraciones negativas.

### Tratamiento conservador

- TP histórico resuelto: R observado por el challenger.
- SL histórico resuelto: R observado.
- Toda entrada no resuelta / expirada después de Entry: **-1R completo**.
- Cada entrada: **-0.118R** adicionales de stress de fees/slippage.
- 0.118R corresponde a la mediana histórica del proxy modelado de fees+slippage de Futures 30m (N=46 en la cohorte disponible).

### Separación temporal

**IN-SAMPLE / Development:** 2026-09-10 a 2026-09-13.  
**OUT-OF-SAMPLE cronológico / Holdout:** 2026-09-14 a 2026-09-16.

El holdout es posterior en el tiempo al development y se calcula con exactamente las mismas reglas. Sin embargo, no debe llamarse OOS prospectivo limpio de 17.5.10: el histórico antecede a esta versión y el holdout fue inspeccionado durante este trabajo. La validación realmente prospectiva comienza después del deploy.

### Resultados

| Período | N | TP | SL | No resueltas penalizadas | Net R stress | Expectancy | PF stress | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| In-sample | 11 | 5 | 1 | 5 | **+1.702R** | **+0.1547R** | **1.254** | 2.236R |
| OOS cronológico | 4 | 3 | 0 | 1 | **+3.928R** | **+0.9820R** | **4.513** | 1.118R |
| Combinado | 15 | 8 | 1 | 6 | **+5.630R** | **+0.3753R** | **1.719** | 2.236R |

Tasa conservadora de TP combinada: 53.33%. Esta tasa NO equivale a probabilidad calibrada de éxito.

### Folds diarios

- 2026-09-10: +1.692R
- 2026-09-11: +1.128R
- 2026-09-13: -1.118R
- 2026-09-14: +2.246R
- 2026-09-15: +1.682R

La existencia de un fold negativo se conserva expresamente; no se eliminó para mejorar la presentación.

### Bootstrap de incertidumbre

100,000 remuestreos, seed 17510:

- P(media > 0) ~= 0.9026
- IC 95% de media R: **[-0.3713, +1.1220]R**

El intervalo incluye cero. Por tanto, el backtest es positivo como evidencia de aceptación preliminar, pero el tamaño de muestra NO permite certificar rentabilidad futura ni afirmar ausencia de overfitting.

### Estabilidad de parámetros

Se probaron siete puntos vecinos. Cuatro fueron positivos tanto en development como en holdout. Algunos vecinos son negativos. El punto final `ADX20 / Vol1.20 / RSI80` no es el punto de máximo retorno; se eligió por ser amplio e interpretable y por evitar optimización extrema.

### Qué valida y qué NO valida

**Valida de forma preliminar:** que esta ruta 30m concreta tiene resultado histórico stressed positivo en development y holdout cronológico; que no fue necesario bajar Safety ni alterar Entry/SL/TP para obtenerlo.

**No valida:** todo SmartradingReview, todo Futures, Multi-Activo, las señales futuras de 17.5.10, ni los modelos Gamma/0DTE. Multi-Activo todavía no dispone de una cohorte de producción equivalente. Black-Scholes/GEX entra en 17.5.10 como contexto/SHADOW hasta acumular observaciones point-in-time.

### Archivos reproducibles

- `BACKTEST_ROWS_17_5_10_PROFITABILITY.csv`: las 15 observaciones exactas.
- `backtest_commit17_5_10_profitability.py`: replay offline.
- `BACKTEST_17_5_10_FINAL_RESULT.json`: salida congelada.
- `BACKTEST_PARAMETER_STABILITY_17_5_10.json`: vecindad de parámetros.
- `BACKTEST_SQL_17_5_10.sql`: consultas de extracción/auditoría.
