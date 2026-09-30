# BACKTEST 17.5.11R.2 — Evidencia de cobertura y geometría

**Fecha:** 30/09/2026  
**Base:** 17.5.10.9  
**Nota:** R.2 no cambió las estrategias/alpha aprobadas en R.1; corrigió el flujo manual, el uso del comité Entry/SL/TP para hipótesis no publicadas, Multi UI y Delta/Gamma/Theta. Por tanto la evidencia estadística de R.1 se conserva sin reoptimización posterior a los nuevos bugs visuales.

## Rutas exactas con Train/Selection/OOS/WF positivos

| Celda | Familia | Train/IS | Selection | OOS final | WF+ | Estado R.2 |
|---|---|---:|---:|---:|---:|---|
| ETH-USDT 2H LONG · TREND_UP | RSI_TREND | N40 · +0.0866R · PF1.185 | N14 · +0.1646R · PF1.482 | N14 · +0.3331R · PF1.968 | 1.00 | Routing exacto validado |
| SOL-USDT 2H SHORT · TREND_DOWN | SUPERTREND_PULLBACK | N23 · +0.1015R · PF1.138 | N8 · +0.5033R · PF1.873 | N8 · +0.3130R · PF1.416 | 1.00 | Routing exacto validado |
| XRP-USDT 2H SHORT · TREND_DOWN | TREND_CONTINUATION | N52 · +0.1113R · PF1.212 | N17 · +0.3306R · PF1.826 | N18 · +0.2785R · PF1.519 | 1.00 | Routing exacto validado |

## Rutas que permanecen SHADOW

- ADA-USDT 2H SHORT · SWEEP_REVERSAL: Train -0.0375R / PF0.949 aunque Selection/OOS fueron positivos.
- LINK-USDT 2H SHORT · RSI_MAVERICK_REVERSAL: Train -0.1100R / PF0.837.
- ADA-USDT 4H SHORT · BOLLINGER_SQUEEZE: Train -0.1202R / PF0.804 y OOS sólo N6.

No se promovieron por mirar únicamente el tramo final favorable.

## Geometría LIQUIDITY_SWEEP_MSS_POI

Única autoridad acotada adicional que se conserva:

- Futures 30m IS cronológico: N11 · 7TP/4SL · +0.8592R · PF3.363.
- Futures 30m OOS cronológico: N5 · 5TP/0SL · +1.8000R.

No se generaliza:

- 1h OOS N9 · 2TP/7SL · +0.0906R · PF1.116 → SHADOW.
- 2h OOS N6 · 0TP/6SL · -1R → rechazada.
- 4h OOS N2 → muestra insuficiente.

## Screening de nuevas familias genéricas

Se mantienen rechazadas:

- TREND_PULLBACK genérico: IS -0.7786R; OOS -1.0992R.
- VOLUME_PROFILE_REACTION: IS -0.8613R; OOS -0.5908R.
- FVG_RECLAIM: IS -1.1231R; OOS -1.1180R.
- TREND_BAND_CONTINUATION: IS -0.7404R; OOS +0.0584R / PF1.08 → insuficiente/inestable.

## Qué cambia R.2 respecto al backtest

R.2 no reoptimiza parámetros después de observar las capturas. En vez de eso corrige una discrepancia de producción:

`tesis direccional no publicada -> antes niveles por defecto/NO_EXECUTABLE_LEVELS`

pasa a:

`tesis direccional gobernada -> mismo calculate_entry_levels de la señal oficial -> validación -> ANALYSIS_ONLY manual`

La geometría manual sigue sometida a Entry/SL/TP completos, R/R, Safety observable, vela cerrada y guardado server-side. No se le atribuye rentabilidad histórica nueva sólo por existir.

## Limitación

Ningún backtest garantiza beneficio futuro. Las rutas exactas siguen necesitando validación prospectiva. R.2 busca que el runtime deje de perder oportunidades por wiring/UX/geometría incompleta; no declara rentable una celda que Research no haya validado.
