# BACKTEST COMMIT 27 — autoridad contextual unificada

## Alcance

Este backtest usa únicamente evidencia incluida en el repositorio. No reconstruye Q, estructura, orderflow, macro o Multi cuando esas columnas históricas no existen. Por eso valida **el conjunto de rutas que Commit 27 permite LIVE**, no inventa una prueba causal de variables ausentes.

## Futures 30m — cohorte raw con coste stress 0.118R/trade

| Split | N | Net R | E[R]/trade | PF | MaxDD R |
|---|---:|---:|---:|---:|---:|
| IS | 11 | 1.702 | 0.1547 | 1.2537 | 2.236 |
| OOS | 4 | 3.928 | 0.9820 | 4.5134 | 1.118 |
| COMBINED | 15 | 5.630 | 0.3753 | 1.7194 | 2.236 |

Bootstrap IS P(E>0): **61.5%**, IC95% [-0.6089, 0.9184]
Bootstrap OOS P(E>0): **94.9%**, IC95% [-0.418, 1.682]

No se crean reglas por símbolo o dirección a partir de los subgrupos pequeños; hacerlo sería sobreajuste.

## Futures 30m — trigger estructural post-geometría

Ruta `LIQUIDITY_SWEEP_MSS_POI`: IS N=11, E=+0.8592R, PF=3.363; OOS N=5, E=+1.8000R. Condición: `sweep + MSS/BOS or displacement + structural POI`.

Commit 27 usa esta estructura **después** de que Entry exista. Ya no la exige en el router pre-Entry.

## Separación anti-double-counting Q / autoridad estadística

Commit 27 no utiliza `max(Q1..Q10)` como autoridad. Q1..Q8 forman la capa de calidad de tesis/ejecución con los mismos pisos existentes (composite 76, structural floor 64, execution floor 70), mientras Q9 queda como diagnóstico de evidencia. La evidencia estadística se exige una sola vez mediante la ruta Champion/OOS congelada + governance. Esto evita penalizar o premiar dos veces la misma evidencia.

## Champions gobernados

| Ruta | Mercado | TF | IS E | Selection E | OOS E | Release |
|---|---|---:|---:|---:|---:|---|
| F30_SHARED_LIQ_SWEEP_MSS_POI_V1 | FUTURES | 30M | +0.1547 | +0.0000 | +0.9820 | PASS |
| ETH_2H_LONG_RSI_TREND_V1 | FUTURES | 2H | +0.0866 | +0.1646 | +0.3331 | PASS |
| SOL_2H_SHORT_SUPERTREND_PULLBACK_V1 | FUTURES | 2H | +0.1015 | +0.5033 | +0.3130 | PASS |
| XRP_2H_SHORT_TREND_CONTINUATION_V1 | FUTURES | 2H | +0.1113 | +0.3306 | +0.2785 | PASS |
| LINK_4H_SHORT_RSI_TREND_V1 | FUTURES | 4H | +0.0071 | +0.5422 | +0.2754 | PASS |
| US_INDEX_1D_TREND_PULLBACK_RR18_V1 | MULTIASSET | 1D | +0.0211 | +0.0130 | +0.5055 | PASS |

## Multi-Activo rápido 1h/4h

**No se promueve una ruta rápida nueva a LIVE.** El repositorio no contiene un cohort IS/Selection/OOS class-specific de 1h/4h para Energy, Metals o China. El proxy genérico disponible es precisamente evidencia contra copiar una receta universal:

- señales=74; resueltas=59; expectancy=-0.3714R; PF=0.553; MaxDD=24.761R.

Commit 27 sí aplica filtros contextuales por clase a esos candidatos y los conserva como Shadow con blocker explícito, de modo que ReviewTrader/Research puedan construir la muestra que falta sin arriesgar capital LIVE.

## Conclusión de release

- Futures 30m: **PASS** para mantener/recuperar la ruta gobernada; la evidencia es positiva IS y OOS, pero la muestra OOS sigue siendo pequeña.
- Exact Champions Futures: **PASS** sólo en sus celdas exactas.
- US Index 1D: **PASS** según su evidencia IS/Selection/OOS.
- Multi 1h/4h nuevo: **NO LIVE** todavía; falta OOS causal por clase.
- Spot: no se modifica el motor de señales en Commit 27.
- Esto demuestra rentabilidad histórica de las rutas promovidas, **no garantiza rentabilidad futura**.
