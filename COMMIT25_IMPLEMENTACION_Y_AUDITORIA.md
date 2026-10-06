# COMMIT 25 — Contextual Champion Recovery + Anti-Overfit Authority

## 1. Objetivo

Aumentar la frecuencia de **señales de calidad** sin bajar Safety, R/R, SL/TP quality, pérdida máxima, ATR stress ni closed-candle authority. El cambio no crea una cuota de señales y no copia una estrategia ganadora a otra clase de activo.

## 2. Causa raíz corregida

El runtime `commit19_runtime.py` ya contenía el carril de Champions, pero importaba `champion_registry_commit19` y `champion_decay_commit19`. Esos módulos no estaban presentes en el Main entregado. La excepción era capturada y el motor hacía `COMMIT19_FAIL_SAFE_TO_BASE_18_2`, por lo que la autoridad de rutas con backtest positivo podía quedar silenciosamente inactiva.

`commit19_1_runtime.py` tenía el mismo problema con `synthesis_decay_commit19_1`.

Además, Commit 23/24 permitía que `max(Q1..Q10)` funcionara como autoridad de publicación. Ese diseño selecciona la mejor de varias transformaciones correlacionadas de la misma evidencia y podía rescatar fallos legacy de `RR`, `SAFETY`, `TP_QUALITY` y `SL_QUALITY`. Commit 25 elimina esa ruta de publicación; los diez Q siguen visibles como diagnóstico.

## 3. Mejora implementada

### 3.1 Registry de Champions contextuales restaurado

Nuevo `champion_registry_commit19.py` sin I/O, sin DataFrames y sin red. Sólo activa rutas que aparecen como `LIVE_CHAMPION` con evidencia positiva en `BACKTEST_COMMIT19_RESULT.json`:

- Futures 30m `LIQUIDITY_SWEEP_MSS_POI`: BTC, ETH, SOL, XRP, ADA y LINK.
- ETH 2h LONG `RSI_TREND`.
- SOL 2h SHORT `SUPERTREND_PULLBACK`.
- XRP 2h SHORT `TREND_CONTINUATION`.
- LINK 4h SHORT `RSI_TREND`.
- SPY/QQQ 1D `TREND_PULLBACK_RR18` para `US_INDEX`.

No existe extrapolación por similitud. Un Champion de ETH no se aplica a BNB/SUI; el Champion de índices no se aplica a CL/XAG/KSTR.

### 3.2 Contexto live obligatorio

Una ruta histórica sólo abre un **candidato** si el contexto actual es compatible:

- dirección live no ambigua;
- tendencia coherente;
- momentum no contrario;
- MTF sin conflicto duro y, cuando existe dirección dominante, alineado;
- régimen requerido para rutas exactas;
- macro `CRITICAL` bloquea;
- 30m mantiene el contrato del replay: ADX >= 20, volume ratio >= 1.20, RSI anti-chase y trigger estructural Sweep+MSS o Displacement+POI;
- US_INDEX 1D requiere evidencia de pullback/retest/POI.

Después de esto, el candidato sigue pasando por Entry/SL/TP, rescore geométrico, Safety, RR, leverage y publication gate. El registry no publica por sí solo.

### 3.3 Particularización por clase

| Segmento | Commit 25 | Motivo |
|---|---|---|
| CORE1/CORE2 | Champions exactos 30m + ETH/SOL/XRP 2h cuando corresponde | Evidencia IS/OOS disponible |
| MEDIUM | LINK 30m y LINK 4h SHORT | Evidencia IS/OOS disponible |
| HIGH | Research/Shadow | No hay ruta limpia IS/OOS suficiente en el bundle |
| US_INDEX | SPY/QQQ 1D Trend Pullback | Evidencia IS/Selection/OOS independiente |
| ENERGY | Research/Shadow | No se extrapola US_INDEX/crypto |
| INDUSTRIAL_METAL | Research/Shadow | Sin Champion OOS propio |
| PRECIOUS_METAL | Research/Shadow | Sin Champion OOS propio |
| CHINA_INDEX | Research/Shadow | Sin Champion OOS propio |

Esto es intencional: “analizar cada caso” no significa inventar una regla distinta para cada símbolo; significa que sólo una celda con evidencia propia recibe autoridad.

### 3.4 Q1..Q10 dejan de ser una máquina de selección optimista

Cambios:

- `parallel_quality_filters` permanece en metadata/UI para diagnóstico.
- `max(Q1..Q10) >= 75` **no** convierte un `ANALYSIS_ONLY` en Premium.
- R/R vuelve a ser hard check 1.8..3.5 para el paquete Premium.
- Safety Premium 75, TP >=55 y SL >=60 se comprueban en la lectura diagnóstica paralela.
- se corrige Q6: un `entry_reachability` ausente ya no pasa porque el default `0 >= 0` sea verdadero.
- `quality_ready` ya no recibe autoridad sólo porque un Q paralelo haya ganado.

### 3.5 Q9/evidencia deja de perder al Champion durante la geometría

`commit19_runtime.py` conserva en `levels` el objeto compacto `commit19_champion` y `validated_strategy_route`. De esta forma Q9 no ve `GAP` sólo porque el snapshot perdió provenance entre routing y Entry/SL/TP.

### 3.6 Quant Synthesis queda Shadow por defecto

Se restaura el módulo faltante `synthesis_decay_commit19_1.py`, pero un fingerprint nuevo no obtiene autoridad live automáticamente. Permanece `SHADOW_DECAY` hasta que governance lo marque como validado. Se preserva el contrato 8 pérdidas LIVE -> Shadow; 8 Shadow -> Retired para fingerprints que sí hayan sido promovidos por evidencia.

## 4. Backtest de release

### 4.1 Replay físico disponible — Futures 30m

Fuente: `BACKTEST_ROWS_17_5_10_PROFITABILITY.csv` incluida en el ZIP entregado.

| Split | N | Net R | Expectancy | PF | MaxDD |
|---|---:|---:|---:|---:|---:|
| IS / DEV | 11 | +1.702R | +0.15473R | 1.2537 | 2.236R |
| OOS cronológico | 4 | +3.928R | +0.98200R | 4.5134 | 1.118R |

**PASS de release**, con advertencia estadística: OOS N=4 es muy pequeño y no demuestra por sí solo rentabilidad futura.

### 4.2 Rutas causales gobernadas

Las métricas siguientes están congeladas en `BACKTEST_COMMIT19_RESULT.json`. Sus candles raw no están en el ZIP recibido, por lo que Commit 25 no las “recalcula” artificialmente.

| Ruta | IS | Selection | OOS |
|---|---:|---:|---:|
| ETH 2h LONG RSI_TREND | N40 E +0.0866R PF 1.185 | N14 E +0.1646R PF 1.482 | N14 E +0.3331R PF 1.968 |
| SOL 2h SHORT SUPERTREND_PULLBACK | N23 E +0.1015R PF 1.138 | N8 E +0.5033R PF 1.873 | N8 E +0.3130R PF 1.416 |
| XRP 2h SHORT TREND_CONTINUATION | N52 E +0.1113R PF 1.212 | N17 E +0.3306R PF 1.826 | N18 E +0.2785R PF 1.519 |
| LINK 4h SHORT RSI_TREND | N49 E +0.0071R PF 1.016 | N16 E +0.5422R PF 3.633 | N17 E +0.2754R PF 1.853 |
| US_INDEX 1D TREND_PULLBACK_RR18 | N213 E +0.0211R PF 1.043 | N71 E +0.0130R PF 1.030 | N72 E +0.5055R PF 2.912 |

Todos mantienen signo positivo en los splits disponibles. LINK 4h y US_INDEX tienen edge IS débil; por eso Alpha Decay/ReviewTrader siguen siendo importantes.

### 4.3 Resumen agregado de evidencia (NO cartera sincronizada)

- Crypto exact 4 rutas: IS N164 E ponderada +0.072763R, PF proxy 1.14126.
- Crypto exact 4 rutas: Selection N55 E +0.375007R, PF proxy 2.05801.
- Crypto exact 4 rutas: OOS N57 E +0.295821R, PF proxy 1.64871.
- Crypto + replay 30m: OOS N61 E +0.340816R, PF proxy 1.76684.
- US_INDEX 1D: OOS N72 E +0.5055R, PF 2.912.
- Resumen de toda evidencia OOS disponible: N133, E ponderada +0.429968R, PF proxy 2.23922.

Estos agregados combinan backtests distintos y sólo resumen evidencia; no son un equity curve de cartera.

## 5. Frecuencia

La mejora no promete “X señales por día”. Cambia la **cobertura gobernada**:

- Main previo: 3 celdas positivas exactas conectadas en `validated_strategy_routes_175111r1.py`.
- Commit 25: 12 celdas símbolo×TF cubiertas por Champions gobernados.
- Incremento de cobertura potencial: **4.0x**.

Una celda cubierta puede producir 0 señales si el contexto actual no cumple el setup. Eso es correcto. La frecuencia aumenta sólo porque más rutas históricamente defendibles vuelven a poder competir; no porque los gates se hagan más fáciles.

## 6. Control de overfitting

Commit 25 aplica cinco barreras:

1. no hay búsqueda de parámetros nueva;
2. no se usa OOS para ajustar thresholds del Commit 25;
3. no se extrapolan Champions por clase/símbolo;
4. max(Q1..Q10) no tiene autoridad de publicación;
5. las clases sin OOS propio continúan Research/Shadow.

## 7. Recursos Free Tier

El cambio caliente es deliberadamente puro:

- nuevos market-data requests: **0**;
- nuevas consultas Supabase: **0**;
- nuevos writes Supabase: **0**;
- nuevos LLM calls: **0**;
- nuevos background threads: **0**;
- nuevas dependencias Python: **0**;
- nuevas tablas SQL: **0**.

Se conserva 1 Gunicorn worker + 2 gthreads. `MAIN_SUPABASE_DAILY_BUDGET_MB=12` no cambia (aprox. 372 MB/mes a 31 días, muy por debajo de 5 GB). El budget Groq se reduce de 160k a **140k tokens/día** para aumentar margen. No se añaden DataFrames ni OHLCV persistente.

No fue posible hacer un boot Flask completo dentro del contenedor de auditoría porque este entorno no tiene instalado `Flask`; Render sí instalará `requirements.txt` durante build. Por ello la validación de runtime local de esta entrega es de compilación, unit/integration tests puros y backtests incluidos, no un despliegue Render real.

## 8. QA ejecutado

- compilación de 257 módulos Python top-level: PASS;
- `test_commit25_contextual_authority.py` + regresión segura de Q23: 10/10 PASS;
- `qa_commit19_1.py`: 13/13 PASS;
- `backtest_commit25_contextual_authority.py`: PASS;
- suite completa: conserva 5 errores de colección que ya existen exactamente en el baseline recibido;
- `test_commit24_repair.py`: 6 fallos / 6 pass, exactamente el mismo resultado que el baseline original recibido. No son regresiones introducidas por Commit 25.

## 9. Criterio de éxito en producción

No considerar el cambio exitoso sólo porque aparezca una señal. Medir durante producción:

- Champion matched -> candidate generated -> primary geometry -> native quality -> hard guards -> published;
- señales/semana por route/symbol/TF/direction/regime/volatility;
- expectancy y PF live/shadow por Champion;
- 8-loss Alpha Decay;
- RSS idle/normal/heavy y OOM;
- Supabase egress/storage;
- Q parallel “would confirm” vs native publication, para observar cuánto optimismo eliminó la política anti-overfit.

## 10. Conclusión

Commit 25 ataca la frecuencia en el punto correcto: **recupera cobertura de rutas que ya tenían evidencia positiva y que estaban desconectadas del runtime**. No baja calidad. En paralelo elimina una fuente de overfitting de autoridad: seleccionar el mejor Q correlacionado para rescatar un trade económicamente rechazado.
