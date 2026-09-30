# BACKTEST 17.5.11R.3 — Evidencia conservada de cobertura + aclaración de geometría manual

**Fecha:** 30/09/2026  
**Base estadística:** 17.5.11R.1/R.2  
**Importante:** R.3 NO reoptimiza alpha después de observar el fallo de guardado/UI. Corrige wiring, geometría manual, Multi progresivo y visualización D/G/T. Por tanto se conserva el mismo conjunto de rutas estadísticamente validadas.

## Rutas exactas con Train/Selection/OOS/WF positivos

| Celda | Familia | Train/IS | Selection | OOS final | WF+ | Autoridad |
|---|---|---:|---:|---:|---:|---|
| ETH-USDT 2H LONG · TREND_UP | RSI_TREND | N40 · +0.0866R · PF1.185 | N14 · +0.1646R · PF1.482 | N14 · +0.3331R · PF1.968 | 1.00 | routing exacto validado |
| SOL-USDT 2H SHORT · TREND_DOWN | SUPERTREND_PULLBACK | N23 · +0.1015R · PF1.138 | N8 · +0.5033R · PF1.873 | N8 · +0.3130R · PF1.416 | 1.00 | routing exacto validado |
| XRP-USDT 2H SHORT · TREND_DOWN | TREND_CONTINUATION | N52 · +0.1113R · PF1.212 | N17 · +0.3306R · PF1.826 | N18 · +0.2785R · PF1.519 | 1.00 | routing exacto validado |

## Rutas que permanecen SHADOW

- ADA-USDT 2H SHORT · SWEEP_REVERSAL: Train -0.0375R / PF0.949, aunque Selection/OOS fueron positivos.
- LINK-USDT 2H SHORT · RSI_MAVERICK_REVERSAL: Train -0.1100R / PF0.837.
- ADA-USDT 4H SHORT · BOLLINGER_SQUEEZE: Train -0.1202R / PF0.804 y OOS N6.

No se promovieron por mirar únicamente el tramo final favorable.

## Geometría LIQUIDITY_SWEEP_MSS_POI

Se conserva la única autoridad acotada adicional:

- Futures 30m IS cronológico: N11 · 7TP/4SL · +0.8592R · PF3.363.
- Futures 30m OOS cronológico: N5 · 5TP/0SL · +1.8000R.

No se generaliza:

- 1h OOS N9 · 2TP/7SL · +0.0906R · PF1.116 → SHADOW.
- 2h OOS N6 · 0TP/6SL · -1R → rechazada.
- 4h OOS N2 → muestra insuficiente.

## Screening genérico rechazado

- TREND_PULLBACK genérico: IS -0.7786R; OOS -1.0992R.
- VOLUME_PROFILE_REACTION: IS -0.8613R; OOS -0.5908R.
- FVG_RECLAIM: IS -1.1231R; OOS -1.1180R.
- TREND_BAND_CONTINUATION: IS -0.7404R; OOS +0.0584R / PF1.08 → insuficiente/inestable.

## Qué añade R.3 y por qué NO es un nuevo backtest de alpha

El usuario requiere que **toda tesis direccional real**, incluso si no es Premium, tenga Entry/SL/TP para poder guardarla bajo su propio riesgo y activar Guardian.

R.3 implementa una jerarquía de geometría:

1. geometría normal del comité;
2. recuperación estructural con POI/liquidez;
3. fallback manual técnico con Entry pendiente + invalidación/ATR + objetivo estructura/R múltiple.

El tercer nivel se marca explícitamente:

`manual_geometry_source = GUARANTEED_TECHNICAL_FALLBACK`  
`manual_geometry_authority = USER_MANUAL_ANALYSIS_ONLY`

No se le atribuye expectancy, PF ni WR histórica. No puede elevarse a Premium ni cambiar la evidencia de Research. Su función es proporcionar una operación técnicamente definida para **seguimiento manual**, no demostrar rentabilidad.

## Limitación

Ningún backtest garantiza beneficio futuro. El objetivo de R.3 es evitar pérdidas de oportunidad por wiring/geometría incompleta y restaurar el control manual solicitado, manteniendo la separación entre evidencia estadística y seguimiento bajo riesgo del usuario.
