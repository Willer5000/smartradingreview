# Propuesta general — Commit 33.3 CURRENT CORE REPAIR

## Objetivo

Recuperar señales de calidad y estabilidad UI sin retroceder a la arquitectura antigua.

## Arquitectura objetivo

`Datos -> Operational Intelligence -> Core Candidate Router 33.3 -> 9 especialistas -> Strategy/Execution -> Comité Entry -> Comité SL -> Comité TP -> Safety especializado -> hard risk/RR -> OOS/Publicación`

Guardian queda después y separado por usuario.

## Principio de frecuencia

La frecuencia NO se aumenta rebajando el filtro final. Se aumenta evitando que una hipótesis técnicamente coherente muera antes de Geometry por filtros redundantes o incompatibles con su setup.

Ejemplo:

- Trend Pullback debe respetar MTF.
- Un impulso nuevo puede aparecer antes de que el HTF reaccione. Si MTF va en contra, se exige una confirmación independiente adicional, pero no se elimina automáticamente la hipótesis.
- Un sweep/reversal necesita barrido + evidencia estructural real; MTF contrario al inicio de una reversión es contraevidencia, no necesariamente veto absoluto.

## Risk class

CORE / MEDIUM / HIGH comparten el mismo piso de existencia de hipótesis.

La clase de riesgo seguirá modificando aquello que realmente debe modificar:

- velocidad/tempo;
- vigencia de Entry;
- sizing/leverage;
- hard risk;
- Safety contextual.

No se utiliza como requisito de sumar más indicadores correlacionados antes de Geometry.

## Geometría

Commit33.3 NO cambia la investigación ya realizada sobre Entry/SL/TP.

El TP sigue siendo una meta **realista y probable**, no el TP más lejano que maximice RR. Debe continuar usando la geometría actual: liquidity targets, Fibonacci, imbalances/FVG, OB, POC/HVN/LVN, soporte/resistencia y reacción esperada.

El SL sigue siendo estructural y no vuelve al comportamiento del main antiguo.

## Recursos Render

- 1 worker / 2 gthreads.
- BLAS single-thread.
- un heavy slot.
- native app memory policy 255 start / 270 soft / 335 hard / 315 in-job abort.
- Commit21.1 ya no pisa estos números.
- Visuals OHLC no compiten con heavy analysis.

## Criterio de éxito del deploy

1. `/api/runtime/version` => `COMMIT33_3_CORE_REPAIR_V1` y `entrypoint=app:app`.
2. `/health` => `geometry_abi_ok=true`.
3. No vuelve a aparecer `unexpected keyword argument execution_observations`.
4. `/api/futures/visuals` devuelve `df` incluso cuando otro heavy job está corriendo, salvo presión crítica.
5. Desaparece el log `COMMIT21.1 overlay activo` con policy 215/235/300; en su lugar debe aparecer `legacy Commit21.1 trading/memory overlay neutralized`.
6. Funnel operativo debe empezar a mostrar candidatos que llegan a geometría primaria, no sólo fallbacks.

## Estrategias nuevas

CRT, Failed Auction, Opening Range+VWAP, Triple RSI, Efficiency Ratio y Compression Release quedan fuera de la autoridad productiva de 33.3. Se evaluarán en 30m con split cronológico IS/OOS y costes. Una estrategia sólo puede incorporarse si demuestra edge incremental; no se añade para cumplir una cuota diaria de señales.


## Contratos preservados al retirar 32.x

- Autoridad SPOT global preservada como llamada nativa del router; Guardian no se toca.
- Tempo Futures migrado a `futures_universe.py`: CORE1 0.12%/3 velas, CORE2 0.11%/3, MEDIUM 0.08%/2, HIGH 0.05%/1.
- 30m sigue siendo la menor temporalidad.
- Entry/SL/TP committees y Safety especializado permanecen downstream.
