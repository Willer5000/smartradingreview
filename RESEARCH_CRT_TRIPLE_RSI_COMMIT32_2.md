# CRT / Triple RSI — Commit 32.2

## Estado actual
`PENDING_BACKTEST_DATA`. No existe en este paquete una declaración de rentabilidad no ejecutada.

## CRT_LIQUIDITY_RANGE_RECLAIM_V1
Hipótesis: sweep de un extremo del rango previo + cierre/reclaim dentro del rango; entrada en la siguiente vela, stop ATR y target parametrizado en R. Debe compararse contra el Sweep/MSS actual para demostrar valor incremental.

## TRIPLE_RSI_MOMENTUM_TIMING_V1
Hipótesis: alineación RSI corto/medio/largo con filtro EMA50 y trigger únicamente al inicio de una nueva alineación. Debe demostrar valor incremental frente al momentum/RSI existente.

## Protocolo
Split cronológico 70/30; parámetros congelados antes de OOS; costes; métricas N, expectancy R, PF, win rate, net R y max DD. PASS exige OOS >=30 operaciones, expectancy positiva y PF >=1.05 en IS y OOS.

## Gobierno LIVE
PASS -> LIVE directo. Ocho pérdidas LIVE consecutivas -> SHADOW. TP/WIN reinicia la racha. No se usa una cuota diaria como criterio de promoción.
