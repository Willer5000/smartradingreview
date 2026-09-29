# Backtest de familias + Entry + SL + TP — Commit 17.5.8

Fecha de evidencia: 28/09/2026.

## Alcance

Este estudio usa dos fuentes distintas:

1. **Research OOS de Supabase** para familias de estrategia por celda mercado × símbolo × temporalidad × dirección.
2. **Forensics históricos de señales** para Entry, SL y TP.

No se presenta como backtest version-matched de 17.5.8: el historial fue generado por versiones anteriores del motor. Por eso 17.5.8 lo incorpora como **prior preliminar acotado**, no como autoridad para fabricar señales ni para saltar Safety/MTF/publicación.

## 1. Estado económico de referencia

Cohorte limpia de temporalidades operativas con geometría válida y R/R 1.8–6:

| Mercado | Resueltas | TP | SL | WR | Expectancy R | PF proxy |
|---|---:|---:|---:|---:|---:|---:|
| Futures | 346 | 77 | 269 | 22.25% | -0.1324R | 0.830 |
| Spot | 16 | 9 | 7 | 56.25% | +1.3656R | 4.121 |
| Multi-Activo proxy diario | 59 | 10 | 49 | 16.95% | -0.3714R | 0.553 |

El proxy Multi-Activo usa SPY/QQQ/USO/GLD 2022–2026 con una receta estructural genérica; **no reproduce** el motor Multi-Activo productivo ni su Strategy Bank, macro, sesiones ni Liquidation Map. Su lectura útil es negativa: no conviene copiar una receta universal a todos los activos.

## 2. Backtest por familias — celdas OOS positivas

Sólo se incorporan como prior las celdas con **N>=10, expectancy >= +0.12R, PF>=1.25 y max drawdown <=6R**. Ejemplos representativos:

| Celda | Familia | N OOS | Exp. R | PF | MaxDD R |
|---|---|---:|---:|---:|---:|
| SOL 1H SHORT | RSI_TREND | 10 | +0.7652 | 4.343 | 1.229 |
| BNB 2H LONG | MFI_OBV_FLOW | 17 | +0.7258 | 2.743 | 3.438 |
| XRP 30M LONG | HIDDEN_DIVERGENCE_TREND | 12 | +0.6030 | 1.993 | 3.684 |
| ETH 1D LONG | VOLUME_PROFILE_NODE_REACTION | 11 | +0.6043 | 2.992 | 1.061 |
| SOL 2H LONG | RSI_TREND | 20 | +0.4498 | 2.287 | 3.630 |
| ETH 4H SHORT | SWEEP_REVERSAL | 16 | +0.4058 | 1.973 | 2.924 |
| BNB 2H LONG | VOLUME_PROFILE_NODE_REACTION | 24 | +0.3567 | 1.711 | 4.525 |
| XRP 2H LONG | VOLUME_PROFILE_NODE_REACTION | 19 | +0.3510 | 1.651 | 4.487 |
| SOL 30M SHORT | EMA_RECLAIM | 11 | +0.3568 | 1.746 | 1.384 |
| ETH 2H SHORT | FVG_RECLAIM | 11 | +0.2748 | 1.679 | 2.304 |
| ADA 2H SHORT | MFI_OBV_FLOW | 18 | +0.2294 | 1.602 | 4.523 |
| LINK 30M LONG | TREND_CONTINUATION | 25 | +0.1479 | 1.383 | 3.625 |

Spot también mostró celdas prometedoras, especialmente:

- PAXG-USDT 1D COMPRA_SPOT · RSI_TREND: N=14, +1.2538R, PF 4.031.
- PAXG-BTC 1D COMPRA_SPOT · MFI_OBV_FLOW: N=15, +0.7922R, PF 3.942.
- BTC-USDT 1D VENTA_SPOT · SWEEP_REVERSAL: N=11, +0.5067R, PF 3.404.
- BTC-USDT 1D VENTA_SPOT · ADX_DI_TREND: N=18, +0.3136R, PF 1.844.

**Conclusión:** la evidencia es específica por celda. Una familia buena en un activo/TF/dirección no se promueve globalmente.

## 3. Backtest de Entry

Se compararon rutas contrafactuales ya guardadas por el laboratorio de ejecución.

### 30M

| Ruta | Resueltas | WR | Exp. R | PF |
|---|---:|---:|---:|---:|
| Baseline | 35 | 40.00% | +0.220 | 1.366 |
| Liquidity/Sweep/MSS/POI | 16 | 75.00% | +1.153 | 5.613 |
| Specialist Committee | 9 | 55.56% | +0.756 | 2.701 |

### 1H

| Ruta | Resueltas | WR | Exp. R | PF |
|---|---:|---:|---:|---:|
| Baseline | 31 | 9.68% | -0.740 | 0.180 |
| Liquidity/Sweep/MSS/POI | 27 | 33.33% | +0.089 | 1.134 |
| Specialist Committee | 11 | 9.09% | -0.645 | 0.290 |

### 2H

| Ruta | Resueltas | WR | Exp. R | PF |
|---|---:|---:|---:|---:|
| Baseline | 21 | 9.52% | -0.596 | 0.342 |
| Liquidity/Sweep/MSS/POI | 17 | 47.06% | +0.318 | 1.600 |
| Specialist Committee | 11 | 18.18% | +0.001 | 1.001 |

La señal más clara del estudio es que **Entry basado en reacción estructural + liquidez + sweep/MSS/POI** merece más peso relativo en 30M/1H/2H, pero sólo como prior suave porque los challengers también cambian parte de la geometría y la muestra no es version-matched.

## 4. Backtest / forensics de SL

| TF | SL hits | Wick-out | Recuperó Entry tras SL | Llegó a TP tras SL | Marcado tight |
|---|---:|---:|---:|---:|---:|
| 30M | 81 | 4 | 4 | 1 | 3 |
| 1H | 109 | 8 | 13 | 0 | 2 |
| 2H | 62 | 6 | 9 | 1 | 4 |
| 4H | 17 | 2 | 2 | 1 | 2 |

Sobre 269 SL de estas temporalidades, sólo una fracción pequeña terminó demostrando falsa invalidación útil. Por eso **no se autoriza ensanchar todos los SL**.

17.5.8 mantiene el hard guard de 17.5.6: si un SL cae dentro de una zona fuerte que el propio motor todavía considera reacción favorable, esa geometría es contradictoria y se rechaza/recalcula. Fuera de ese caso, el backtest prior de SL queda neutral.

## 5. Backtest de TP — compresión de objetivo

Se mantuvo Entry y SL y se simuló alcanzar un porcentaje del TP planificado usando el progreso favorable registrado antes del resultado.

### 30M

| TP relativo | Exp. R | PF proxy |
|---|---:|---:|
| 50% | -0.026 | 0.956 |
| 60% | +0.065 | 1.109 |
| 70% | +0.121 | 1.199 |
| 80% | +0.116 | 1.181 |
| 90% | +0.148 | 1.225 |
| 100% | **+0.208** | **1.311** |

En 30M el TP completo fue mejor que comprimirlo sistemáticamente.

### 1H / 2H / 4H

Incluso el mejor multiplicador siguió con expectancy negativa:

- 1H: mejor observado 50% TP = -0.464R, PF 0.392.
- 2H: mejor observado 100% TP = -0.376R, PF 0.544.
- 4H: mejor observado 50% TP = -0.438R, PF 0.475; N pequeño.

**Conclusión:** acortar TP no arregla el problema de 1H/2H. El ajuste debe venir antes: selección de familia, contexto y Entry.

## 6. Liquidation Map

Se preserva el modelo posterior a Commit 16/17.3: `MODEL_ESTIMATE_NOT_OBSERVED`, unidad `relative_participation`, calibración con datos públicos de derivados cuando están disponibles y fallback protegido.

No se creó un backtest histórico de Liquidation Map V3 porque el sistema no conserva una serie point-in-time completa de OI + long/short ratio + taker flow para cada fecha del histórico. Reusar datos actuales sobre velas antiguas introduciría look-ahead leakage. Por tanto, 17.5.8 no fabrica una ventaja histórica del mapa; continúa usándolo como contexto live para Entry/TP y como variable a registrar para cohortes futuras.

## 7. Ajustes que sí entran en 17.5.8

1. **Prior preliminar por familia/celda**: máximo +4 puntos en la lente de estrategia; nunca crea dirección.
2. **Prior de Entry**: máximo +4 puntos para candidatos de reacción/liquidez alineados con evidencia 30M/1H/2H.
3. **SL**: sin widening global; hard guard de conflicto reacción↔SL permanece.
4. **TP**: sin compresión global; sólo 30M recibe una preferencia muy pequeña por RR técnico normal.
5. **Learning Scientist / ReviewTrader context** recibe las celdas fuertes y los estudios Entry/SL/TP como evidencia explícita.
6. **Futures quality-first refresh order**: las celdas históricamente prometedoras se analizan antes en el round-robin, sin excluir ninguna celda y sin bajar filtros.
7. **Multi-Activo** conserva su 1H router independiente, active lane, Strategy Bank específico y límites de recursos existentes. No se aplican priors crypto a Multi-Activo sin evidencia propia.
8. Telegram continúa sin cupo diario de señales: la cantidad depende de pasar los filtros técnicos.

## 8. Qué NO cambia

- No se baja 1.50 de mejora mínima, quality 62, Entry 55, SL 60, TP 60.
- No se reduce Safety/MTF/Publicación.
- No se aumenta leverage para aprobar una señal.
- No se obliga x2/x3; la política 17.5.7 de product-fit continúa.
- No se cambia dirección por un backtest prior.
- No se fuerza señal si el mercado no ofrece geometría válida.

## Lectura final

La falta actual de señales no justifica relajar calidad. 17.5.8 intenta recuperar **latencia hacia oportunidades de mayor calidad** y mejorar el ranking de Entry/familia con evidencia histórica, mientras mantiene intactos los gates que evitan lluvia de señales.
