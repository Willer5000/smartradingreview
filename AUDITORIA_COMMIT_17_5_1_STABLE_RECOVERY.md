# Auditoría técnica — Commit 17.5.1 Stable Recovery

## Evidencia histórica GitHub
- Commit `718f4af2ae713596c4eec4cbcb1dacff5d8683e0`: `commit 13 comites de SL, TP y Apalancamiento`, 26/09/2026 02:15 -03.
- Commit `b7892f4baea4aaa51c9cea09e7714b35bb867fe7`: `Commit 14. Mapa de liquidaciones`, 26/09/2026 11:06 -03.
- Commit `467834171ce145d019aa5611add4061724770516`: `Commit 17.2 - Multi-Asset runtime reliability and close-aware scheduler`, 27/09/2026 10:45 -03.

El `leverage_policy.py` del ZIP 17.5 tiene el mismo git blob que Commit 13: `9e85a7fc8628799e9590a8a1d0be990c8ef30486`.

## Causa raíz Multi-Activo
El ZIP 17.5 heredaba Multi-Activo de Commit 12.1, pero `operational_intelligence.py` sólo declaraba celdas oficiales para Spot y Crypto Futures. Como `MultiAssetAnalysis` hereda `FuturesAnalysis`, CL/SPY/QQQ/etc. llegaban como `FUTURES`, pero fallaban `official_cell` porque no pertenecen a `futures_universe.py`.

A eso se sumaban dos fallos operativos:
- el router podía usar la vela todavía abierta;
- el shortlist 4h se reutilizaba para decidir qué analizar en 1D y 1h.

17.5.1 corrige solamente estos problemas para los siete Multi-Activos. No introduce las excepciones MTF ni el razonador global de 17.4.

## Aislamiento de Crypto Futures
Se compararon cinco fingerprints deterministas de `operational_intelligence` (BTC 1h/2h, LINK 1h, SUI 30m y evidencia débil) entre el ZIP 17.5 original y 17.5.1: salida idéntica para Crypto Futures.

La auditoría oficial continúa en 150 celdas Spot/Crypto Futures. Las celdas Multi-Activo se reconocen de forma adicional y aislada.

## Multi-Activo final
Celdas permitidas:
- SPY-USDT, QQQ-USDT, CL-USDT, NATGAS-USDT, COPPER-USDT, XAG-USDT, KSTR-USDT.
- 1h, 4h, 1D.
- LONG/SHORT.

MTF:
- 1h: contexto/estructura 4h; setup/timing 1h.
- 4h: contexto/estructura 1D; setup/timing 4h.
- 1D: contexto/estructura/setup 1D; timing 4h.

No se relaja un conflicto real. Para evitar mezclar estrategias crypto con petróleo/índices/metales, la estrategia común se marca como delegada y la señal sólo puede avanzar por una tesis autónoma fuerte + MTF + especialistas + gates comunes; después `multiasset_system.py` añade contexto de clase de activo.

## Leverage
No se cambió. Esto es deliberado.

La investigación del historial muestra que el motor actual ya es el motor pre-heatmap que buscabas. Forzar un mínimo alto sería peligroso: si contrato, ATR y SL sólo soportan poco leverage, el sistema debe reducirlo o rechazar económicamente la operación, no falsificar 15x.

En escenarios técnicos sintéticos con Safety/quality 80, la política conserva leverage claramente superior a 2x:
- SL 1%, ATR 1%: ~23x.
- SL 2%, ATR 2%: ~13x.
- SL 3%, ATR 3%: ~9x.

Son pruebas de la política, no recomendaciones de operación.

## Recursos
No se portó la persistencia compacta Supabase que 17.2 había agregado. Por tanto el arreglo Multi-Activo no agrega DB writes. Se mantiene el cache RAM acotado y una sola celda profunda por tick.
