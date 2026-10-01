# BACKTEST / AUTHORITY MATRIX — COMMIT 18

Base histórica auditada: Supabase SmarTradingReview hasta el último outcome persistido disponible (18/09/2026).  
Commit Main base: 17.5.11R4. Research base: 12.1.

## Regla de aceptación

Commit 18 **no concede nueva autoridad de producción a un componente por tener una buena narrativa o una buena muestra final**. Una ruta estadística sólo puede recibir autoridad si mantiene signo positivo en Discovery/Train, Selection holdout y OOS final, con walk-forward compatible. La geometría live debe además conservar paridad con lo realmente probado.

Esta regla implica algo importante: no es correcto exigir que *Macro, IA Científica, Guardian o cada trader* tengan PnL positivo standalone. Esos componentes no son estrategias autónomas. Se validan por su contrato de rol y sólo una estrategia/ejecución que sí toma riesgo necesita demostrar rentabilidad IS/OOS.

## Estrategias exactas con evidencia positiva consistente

| Mercado | Celda | Familia | Train/IS | Selection | OOS final | WF+ | Autoridad Commit 18 |
|---|---|---|---:|---:|---:|---:|---|
| Futures | ETH-USDT 2H LONG TREND_UP | RSI_TREND | N40 +0.0866R PF1.185 | N14 +0.1646R PF1.482 | N14 +0.3331R PF1.968 | 1.00 | routing contextual; no bypass |
| Futures | SOL-USDT 2H SHORT TREND_DOWN | SUPERTREND_PULLBACK | N23 +0.1015R PF1.138 | N8 +0.5033R PF1.873 | N8 +0.3130R PF1.416 | 1.00 | routing contextual; no bypass |
| Futures | XRP-USDT 2H SHORT TREND_DOWN | TREND_CONTINUATION | N52 +0.1113R PF1.212 | N17 +0.3306R PF1.826 | N18 +0.2785R PF1.519 | 1.00 | routing contextual; no bypass |
| Spot | PAXG-USDT 12H COMPRA TREND_UP | MULTI_RSI_TREND | N69 +0.1823R PF1.715 | N23 +0.5543R PF2.539 | N24 +0.1955R PF1.498 | 1.00 | Research-positive; production parity still required |

## Rutas que NO se promocionan

- ADA 2H SHORT / SWEEP_REVERSAL: Train/IS -0.0375R, aunque Selection/OOS sean positivos.
- ADA 4H SHORT / BOLLINGER_SQUEEZE: Train/IS -0.1202R y OOS N6.
- LINK 2H SHORT / RSI_MAVERICK_REVERSAL: Train/IS -0.1100R.
- BTC Spot 12H VENTA / MOMENTUM_BREAKOUT: Train/IS -0.3006R.
- PAXG-BTC 12H COMPRA / VWAP_REVERSION: Train/IS -0.3933R.

Esto evita seleccionar sólo por el tramo OOS más atractivo.

## Traders internos

Proxy cronológico 70/30 contra outcomes persistidos:

| Trader | IS utility | OOS utility | Decisión de autoridad |
|---|---:|---:|---|
| Chartista | -0.746 | -0.677 | rol especializado; sin voto alpha |
| Multiframe | -0.564 | -0.591 | contexto temporal; sin voto alpha |
| Pullback | +0.143 | -1.000 | timing Entry; sin voto alpha |
| Smart Money | -0.171 | -0.259 | estructura/liquidez; sin voto alpha |
| Técnico Puro | -0.600 | -0.385 | setup técnico; sin voto alpha |

Limitación: no es PnL standalone puro porque varias tesis de trader no tenían geometría propia. Precisamente por eso Commit 18 **no los convierte en estrategias ni en mayoría de votos**.

## Execution / Entry-SL-TP

Challengers cronológicos globales:

| Ruta | IS | OOS | Estado |
|---|---:|---:|---|
| BASELINE | -0.4303R PF0.472 | +0.1540R PF1.240 | no promotion |
| DEFENSIBILITY | -0.4503R PF0.458 | +0.0370R PF1.057 | no promotion |
| LIQUIDITY_SWEEP_MSS_POI global | +0.6927R PF2.593 | -0.0200R PF0.969 | no generalizar |
| MICROSTRUCTURE_CONFIRMED_ENTRY | -0.5617R PF0.314 | -0.4503R PF0.460 | rechazado |
| SPECIALIST_COMMITTEE global | -0.2714R PF0.674 | +0.6177R PF2.132 (N11) | no promotion: Train negativo |
| TRENDLINE_RETEST | negativo | negativo | rechazado |

Subruta contextual que ya estaba permitida de forma acotada:

**Futures 30m LIQUIDITY_SWEEP_MSS_POI**  
IS N11: 7 TP / 4 SL, +0.8592R, PF3.363.  
OOS N5: 5 TP / 0 SL, +1.8000R.  

OOS es pequeño; se conserva sólo con autoridad acotada y todos los gates posteriores. No se extrapola a 1h/2h/4h.

## Entry/SL de Commit 18

Commit 18 no introduce una geometría global nueva que no haya demostrado edge. Corrige un defecto semántico de la lane manual: si Entry/SL/TP están ordenados matemáticamente pero el SL cae dentro de una zona de reacción todavía válida, intenta **una recuperación estructural sobre la misma tesis**. Si no logra una geometría coherente, no recibe autoridad oficial.

Esto ataca el caso observado: el precio toca el antiguo SL y recién allí reacciona. La zona de reacción debe competir por Entry; la invalidación real debe quedar detrás.

## Leverage

**No se recalibra ni reemplaza.** `leverage_policy.py` y `execution_specialist_committees.py` no son modificados por Commit 18. El contexto de leverage actual sigue ejecutándose **después** de la geometría Entry/SL/TP y declara explícitamente `does_not_force_low_leverage=True`.

Al corregir un SL demasiado cercano, el leverage final puede cambiar como consecuencia matemática de una distancia de riesgo distinta. Eso no es un nuevo modelo de leverage: es el mismo modelo recibiendo una geometría más correcta.

## Macro / Noticias

No son una estrategia standalone; por diseño no convierten un titular en LONG/SHORT. Validación de rol:
- contexto/régimen/event risk;
- relevancia por mercado/activo;
- cache/fail-open;
- no Entry/SL/TP/leverage/publication authority directa.

Fuentes actuales: GDELT, calendario BLS, calendario FOMC, RSS Federal Reserve, CFTC y SEC.

## IA Científica

No es un trader de producción. Su salida permitida es `SHADOW_PROPOSAL` testable. Research sólo acepta propuestas con filtros reproducibles y las somete a la misma cadena causal/OOS. Una propuesta LLM nunca obtiene autoridad directamente.

## Multi-Activo

Al momento de esta auditoría Supabase todavía no contenía filas de `MULTIASSET_CAUSAL_OOS_V1`. Por tanto **no se declara ninguna estrategia Multi nueva como rentable**. Commit 18-R repara Research para que el laboratorio Multi 12.1 pueda ejecutarse; Commit 18 Main repara el Display Lane, pero no inventa alpha Multi.

## Conclusión estadística

Lo que se valida positivamente recibe autoridad acotada. Lo que no tiene IS/OOS positivo se mantiene como contexto, Shadow o diagnóstico. No se garantiza beneficio futuro y no se fabrica una tasa diaria de señales bajando filtros.
