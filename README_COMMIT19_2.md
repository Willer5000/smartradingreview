# Commit 19.2 — QUALITY SIGNAL RECOVERY

Fecha: 2026-10-01

## Objetivo

Commit 19.1 ya encontraba tesis direccionales y podía construir Entry/SL/TP, pero en producción todavía aparecían muchas filas como **ANÁLISIS, NO SEÑAL** y ninguna señal Premium. Commit 19.2 corrige la causa sin reducir Safety, R/R, TP Quality, SL Quality, Leverage V6 ni los controles de reacción/timing.

Este release se instala **encima del Commit 19.1 FINAL Greeks** ya desplegado.

## Diagnóstico resumido

La evidencia de producción mostrada por el frontend es consistente con un falso negativo de autoridad/calidad, no con ausencia de análisis: había tesis LONG/SHORT con geometría completa, pero la publicación seguía cerrada.

Se encontraron cuatro defectos principales:

1. La síntesis nativa exigía una cuota genérica de familias de estrategia, incluso cuando existía un patrón concreto y multifuente suficientemente definido. Esto castigaba especialmente Multi-Activo.
2. El refinamiento Entry/SL/TP estaba atado a restricciones de **paridad con la geometría baseline** (mismo bucket R/R, misma clase de timing y límites muy estrechos), impidiendo que los comités sustituyeran una geometría mediocre por otra de mayor calidad.
3. Cuando los comités cambiaban Entry/SL/TP, algunos scores de Entry/SL/TP podían seguir perteneciendo a la geometría anterior. Safety podía terminar evaluando una geometría nueva con puntuaciones viejas.
4. Los niveles finales de Champion/Quant podían cambiar después del scoring previo. Faltaba un scoring explícito de la geometría final que realmente llega a Futures/Multi publication.

El 68% que aparece repetidamente en las filas manuales **no es el umbral Premium**. Es un cap diagnóstico aplicado después de que la operación ya fue degradada a ANALYSIS_ONLY. No se cambió para fabricar señales.

## Solución

### 1. Pattern-specific LIVE synthesis

La vía de los 9 especialistas + ReviewTrader ya no depende de una cuota arbitraria de etiquetas de familias. Cada setup debe demostrar su propio contrato de evidencia:

- SWEEP_REVERSAL: sweep + MSS/displacement + POI + coherencia Setup/Execution.
- TREND_PULLBACK: tendencia + POI + ADX + Setup/Execution + MTF/contexto/volumen.
- BREAKOUT_RETEST: ruptura + retest + confirmación estructural/volumen/MTF.
- COMPRESSION_EXPANSION: squeeze + tendencia + momentum + volumen.
- MOMENTUM_CONTINUATION: tendencia + momentum + ADX + volumen + contexto/MTF.
- STRUCTURE_RETEST: POI + estructura + Setup/Execution.

HIGH sigue requiriendo evidencia adicional. Un indicador aislado sigue sin poder producir LIVE.

### 2. Los comités pueden mejorar realmente la geometría

Se eliminan únicamente restricciones de *sameness* con el baseline. No se baja ningún control de calidad.

Una geometría refinada debe mantener:

- R/R dentro de la banda técnica vigente;
- Entry shift <= 1.35 ATR;
- riesgo vs baseline entre 0.65x y 1.45x;
- Geometry Quality >= 68;
- Entry Quality >= 65;
- SL Quality >= 60;
- TP Quality >= 60;
- mejora mínima de 1.50 puntos cuando existe baseline comparable, o calidad >=70 sin baseline comparable;
- Entry debe superar el timing gate real existente;
- execution_setup_guard debe seguir pasando.

Para Futures/Multi, entre geometrías ya admisibles el comité prioriza la alternativa con mejor calidad de publicación usando los mismos componentes Entry/SL/TP/RR del Safety actual. Ese proxy **no publica ni cambia umbrales**; sólo elige mejor entre candidatos técnicamente válidos.

### 3. Safety mide la geometría que realmente se ejecutará

Se añadió `score_execution_geometry()` y un rescore final. Entry/SL/TP no se mueven durante este rescore: sólo se vuelven a medir sus cualidades sobre los precios finales.

Esto corrige el caso donde el frontend mostraba una geometría razonable pero Safety seguía consumiendo scores de una geometría anterior.

### 4. Multi-Activo

Multi-Activo hereda la misma recuperación de calidad y además puede formar una tesis LIVE por patrón concreto aun cuando no existan las antiguas etiquetas de familias cripto. El macro-event gate, Safety, R/R y demás controles siguen intactos.

El frontend diagnóstico de Multi ahora muestra el **motivo Premium exacto** cuando una tesis todavía es rechazada.

### 5. Greeks

El proveedor y su autoridad no cambian.

- BTC/ETH observados: confluencia acotada.
- Resto: Black-Scholes teórico, cero autoridad LIVE.
- Si falta un precio en el payload de análisis, el frontend reutiliza el último precio válido ya dibujado en el gráfico de velas antes de intentar un fallback de red.
- En modo teórico, Zero-Gamma, Delta-Neutral y Walls derivados de Open Interest ahora muestran `N/A` en lugar de `--`, porque no existe OI observado y no se debe inventar ese dato.

## Umbrales Premium — SIN CAMBIOS

- Execution Safety >= 75
- TP Quality >= 55
- SL avoidance quality >= 60
- R/R >= 1.8
- R/R máximo técnico vigente = 3.5
- pérdida estimada en SL <= 8% del margen
- ATR stress <= 25% del margen

Leverage V6, liquidation buffer, Guardian y Alpha Decay 8+8 permanecen sin reducción.

## Recursos — SIN AUMENTO

Render:

- 1 worker
- 2 threads
- MEMORY_SOFT_LIMIT_MB=220
- MEMORY_HARD_LIMIT_MB=300
- MEMORY_JOB_START_LIMIT_MB=200
- MULTIASSET_DEEP_LIMIT=2

Greeks:

- mismo budget 19.1: 12 MiB/día máximo para el proveedor observado;
- mismo TTL 7200 s;
- proveedor directo sólo BTC/ETH;
- sin polling;
- sin nuevos threads;
- sin nuevas llamadas LLM;
- Commit 19.2 no añade ninguna nueva descarga de mercado.

## QA

- Commit 19.2: **28/28 PASS**
- Commit 19.1 regression: **13/13 PASS**
- 17.5.11R.1 regression: **18/18 PASS**
- Champion backtest release: **PASS**
- Python compileall: **PASS**
- JavaScript `node --check`: **PASS**

## Backtest Champion preservado

La corrección no modifica los Champion históricos. El replay 30m sigue en:

- IS: N=11 · +1.702R · PF 1.254
- OOS: N=4 · +3.928R · PF 4.513
- Total: +5.630R · PF 1.719

No se declara un backtest histórico del nuevo Quant Synthesis/Greeks si no existen snapshots point-in-time suficientes para reconstruirlo sin look-ahead.

## Resultado esperado

Commit 19.2 elimina falsos negativos técnicos y permite que el sistema convierta una oportunidad real en señal oficial **cuando la geometría final supera los mismos filtros Premium de siempre**. No establece una cuota de señales y no garantiza que todo cierre produzca una operación.
