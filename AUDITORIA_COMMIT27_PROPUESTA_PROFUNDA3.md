# AUDITORÍA COMMIT 27 — PROPUESTA PROFUNDA 3

## 1. Objetivo

Commit 27 reorganiza el núcleo de autoridad de SmartTradingReview para que la “oficina de traders” completa sea útil sin convertir múltiples observaciones correlacionadas en votos independientes. El objetivo de producto se mantiene en tres carriles:

1. **Spot**: acumulación/rotación BTC–PAXG–USDT (“bola de nieve”).
2. **Futures**: entradas precisas, rápidas o muy rápidas en cripto, con leverage posterior a la geometría y hard risk guards intactos.
3. **Multi-Activo**: el mismo principio de ejecución rápida, pero con razonamiento específico por clase (US Index, Energy, Industrial Metal, Precious Metal, China) y sin copiar reglas cripto.

La frecuencia aproximada de cuatro señales de calidad por día se trata como **KPI de cobertura**, nunca como cuota. Si el mercado no presenta setups válidos, el resultado correcto puede seguir siendo cero.

## 2. Diagnóstico de Commit 25/26

### 2.1 La oficina sí genera información, pero tenía autoridades superpuestas

El sistema ya contiene tendencia, momentum, volumen, estructura/liquidez, MTF, traders especializados, comités de Entry/SL/TP, zonas dinámicas, orderbook/orderflow, macro/fundamentales, sentimiento, griegas/opciones, sesión/día, IA contextual, ReviewTrader y Alpha Decay. El problema no era falta de herramientas sino que varias capas podían volver a juzgar el mismo hecho y existían rutas de publicación parcialmente contradictorias.

Se observaron simultáneamente CPQE/repairs históricos, Champion routing, quality engine Q1..Q10, autoridad nativa en `app.py` y overlays de entrypoint. Esa topología aumenta falsos negativos y riesgo de rule-fitting.

### 2.2 El 68% de Futures y 92/100 de Multi no equivalen a Premium

La UI podía mostrar Entry/SL/TP después de que la oportunidad hubiera perdido autoridad. `app.py` generaba geometría de visibilidad/fallback y la marcaba `ANALYSIS_ONLY`. Por eso RR repetidos y scores altos no demuestran una ruta primaria publicable.

### 2.3 Commit 26 introdujo un gate pre-Entry no respaldado por el cohort raw

El router 30m exigía evidencia de Sweep/MSS/BOS/Displacement antes de que el pipeline hubiera terminado el Entry. El cohort raw de 15 filas usado para IS/OOS sólo conserva trend, ADX, volume ratio, RSI y outcome. Por tanto esa nueva condición no estaba validada por el backtest citado y podía destruir frecuencia. Commit 27 la elimina del routing pre-Entry y la vuelve a exigir **después de la geometría**, donde sí existe evidencia histórica separada de la ruta `LIQUIDITY_SWEEP_MSS_POI`.

### 2.4 Multi no cerraba con la misma autoridad final que Futures

Commit 27 hace pasar análisis Multi background e interactivo por la misma función final de autoridad, pero el `contextual_quality_commit27.py` determina clase de activo y perfil de movimiento. La paridad es de **gobernanza**, no de estrategia.

## 3. Arquitectura Commit 27

### 3.1 Única autoridad final

El flujo final queda:

```text
REAL DATA + CLOSED CANDLE
        ↓
CONTEXT / ASSET CLASS / REGIME / VOLATILITY / MTF
        ↓
DIRECTIONAL THESIS
        ↓
STATISTICAL ROUTE ELIGIBILITY
        ↓
PRIMARY ENTRY / SL / TP GEOMETRY
        ↓
CONTEXTUAL QUALITY (Q1..Q8)
        ↓
POST-GEOMETRY ESSENTIAL EVIDENCE
        ↓
HARD ECONOMIC / SAFETY GUARDS
        ↓
EXECUTABLE_SIGNAL / SHADOW / ANALYSIS_ONLY
        ↓
TELEGRAM only if executable
```

`app.py` es ahora el cierre único. Puede **promover o despromover** estados previos, eliminando el problema de que un overlay antiguo deje una señal ejecutable por una autoridad distinta.

### 3.2 Roles de la oficina, sin doble voto

La evidencia queda agrupada por función:

- **Direction / Structure**: trend, momentum indicators, structure/liquidity, MTF, specialist traders.
- **Timing / Execution**: dynamic zones, orderbook/orderflow, Entry committee, reaction zone.
- **Risk / Exit**: SL committee, TP committee, Guardian inputs.
- **Context / Risk**: fundamentals/macro, sentiment, Greeks/options, session/day, AI context.
- **Statistical Governance**: validated route, ReviewTrader, Alpha Decay.

La presencia de un componente se registra en `office_evidence`, pero **no añade automáticamente puntos**. Esto impide que la misma tendencia sea contada en indicador, trader, comité y Q como cuatro edges independientes.

### 3.3 Q1..Q10

- Q1..Q8 forman el quality gate de tesis/estructura/contexto/ejecución.
- Se conservan los pisos históricos: composite 76, structural floor 64, execution floor 70.
- Q9 queda como **diagnóstico de evidencia estadística**, no se vuelve a contar en el composite que decide calidad, porque la autoridad Champion/OOS se exige aparte.
- Q1..Q10 paralelos se conservan como diagnósticos/telemetría.
- `max(Q1..Q10)` **no puede publicar**.
- Los context groups pueden seguir explicando el contexto, pero el cierre Commit 27 usa el contrato no-estadístico + route authority para evitar double counting.

### 3.4 Hard guards no reducidos

Commit 27 mantiene:

- Safety Premium >= 75.
- RR 1.8 .. 3.5.
- pérdida estimada al SL <= 8% del margen.
- ATR stress >0 y <=25%.
- Entry quality >=65.
- SL quality >=60.
- TP quality >=55.
- datos reales.
- vela cerrada.
- Entry/SL/TP válidos.
- fallback geometry nunca publicable.
- leverage no se cambia en esta capa; se calcula después de geometría mediante la política existente.

## 4. Filtros por movimiento/contexto

Commit 27 clasifica el paquete existente en perfiles, sin añadir indicadores ni requests:

### Futures

- `FUTURES_FAST_SWEEP_MSS_REACTION`
- `FUTURES_FAST_DISPLACEMENT_POI_RETEST`
- `FUTURES_TREND_PULLBACK_REACTION`
- `FUTURES_TREND_CONTINUATION`
- `FUTURES_BREAKOUT_EXPANSION_RETEST`
- `FUTURES_CONTEXTUAL_GENERIC`

La ruta 30m compartida se preselecciona únicamente con variables realmente contenidas en su cohort raw: trend alineado, ADX>=20, volume ratio>=1.20 y RSI anti-chase. La evidencia Sweep/MSS/POI se exige posteriormente sobre la geometría final.

### Multi-Activo

Perfiles diferenciados:

- US_INDEX: sesión/tendencia/retest.
- ENERGY: volatilidad/evento/retest.
- INDUSTRIAL_METAL: macro trend / reaction.
- PRECIOUS_METAL: rates/USD / reaction.
- CHINA_INDEX: Asia session / macro / retest.

Estos perfiles hacen que las herramientas de cada clase sean relevantes, pero **no conceden por sí solos autoridad LIVE**. Una clase necesita evidencia IS/Selection/OOS de su ruta exacta.

## 5. Backtest y decisión LIVE

### 5.1 Futures 30m raw — coste stress 0.118R/trade

| Split | N | Net R | Expectancy | PF | MaxDD |
|---|---:|---:|---:|---:|---:|
| IS | 11 | +1.702 | +0.1547R | 1.2537 | 2.236R |
| OOS | 4 | +3.928 | +0.9820R | 4.5134 | 1.118R |
| Combined | 15 | +5.630 | +0.3753R | 1.7194 | 2.236R |

Bootstrap (50k): IS P(E>0) ~61.5%, OOS P(E>0) ~94.9%; ambos IC95% incluyen cero. La muestra es pequeña: evidencia favorable, no garantía.

### 5.2 Trigger estructural 30m post-geometría

`LIQUIDITY_SWEEP_MSS_POI`:

- IS N=11, E=+0.8592R, PF=3.363.
- OOS N=5, E=+1.8000R.
- condición: sweep+MSS/BOS o displacement+structural POI.

Se usa como prueba de ejecución **después** de Entry, no como filtro anticipado.

### 5.3 Champions exactos

Se mantienen LIVE sólo rutas con evidencia positiva disponible en sus splits gobernados:

- F30 shared BTC/ETH/SOL/XRP/ADA/LINK.
- ETH 2h LONG RSI_TREND.
- SOL 2h SHORT SUPERTREND_PULLBACK.
- XRP 2h SHORT TREND_CONTINUATION.
- LINK 4h SHORT RSI_TREND.
- US_INDEX 1D TREND_PULLBACK_RR18.

No se crean excepciones por símbolo/dirección a partir de los minúsculos subgrupos 30m.

### 5.4 Multi rápido 1h/4h

No se promueve todavía una nueva ruta Energy/Metals/China 1h/4h a LIVE porque los materiales suministrados no contienen un cohort class-specific IS/Selection/OOS limpio. El proxy genérico disponible es negativo: expectancy -0.3714R, PF 0.553, MaxDD 24.761R.

Commit 27 convierte esos casos en **Shadow Quality Candidates** con blocker explícito. Eso permite acumular resultados reales para Research/ReviewTrader sin arriesgar capital ni afirmar rentabilidad no demostrada.

## 6. Spot

Commit 27 no cambia la lógica de señal Spot. El snapshot histórico entregado tiene 16 operaciones resueltas, 9 TP / 7 SL, WR 56.25% y expectancy bruta proxy positiva; la muestra es pequeña y no contiene una contabilidad completa de costes/rotaciones, por lo que no se declara rentabilidad robusta. Se evita una regresión sobre un carril que el usuario observa operativo.

## 7. Frecuencia: qué puede y qué no puede prometer Commit 27

**Sí mejora la capacidad de producir señales Futures** porque elimina un falso negativo causal 30m, unifica la autoridad y evita que Q9/Champion se cuenten dos veces.

**No codifica 4 señales/día.** Cuatro señales diarias se usa como KPI de cobertura esperado cuando el mercado ofrece oportunidades, no como obligación. Codificar una cuota obligaría a relajar filtros cuando no haya edge.

**Multi rápido puede seguir sin Premium al inicio** si sus rutas no poseen OOS. Commit 27 prepara la instrumentación correcta para promoverlas únicamente después de demostrar edge. Inventar una promoción hoy sería incompatible con el requisito de backtest previo.

## 8. Recursos

Cambios Commit 27 en la capa de autoridad:

- nuevas requests: 0.
- nuevas lecturas/escrituras Supabase: 0.
- nuevas llamadas Groq/LLM: 0.
- nuevos threads/loops: 0.
- no almacena OHLCV.
- reusa objetos ya calculados.

Microbenchmark de `evaluate_publication`: 100,000 evaluaciones ~19.7 s bajo `tracemalloc` (~197 µs/call), pico de asignación Python ~0.026 MB. No representa el RSS total del servidor, pero muestra que la nueva capa no es un consumidor relevante.

Se mantienen 1 worker/2 gthreads y límites internos 220/300 MB, `MAIN_SUPABASE_DAILY_BUDGET_MB=12` y `AI_GROQ_DAILY_TOKEN_BUDGET=140000`.

## 9. QA

- 42/42 tests actuales de Commit 22/23/24.3/25/27: PASS.
- 261 módulos Python: compile PASS.
- `static/futures.js`, `static/script.js`, `static/chart_workspace.js`: `node --check` PASS.
- Bloque legacy lifecycle: 38 PASS / 14 FAIL tanto en Commit 25 original como en Commit 27. Es deuda de tests preexistente, no una regresión Commit 27.
- El entorno de auditoría no tiene Flask instalado; no se pudo hacer un import runtime completo del entrypoint, aunque todos los módulos compilan y `requirements.txt` del proyecto declara Flask.

## 10. Conclusión

Commit 27 sí realiza una modificación profunda del núcleo: deja una sola autoridad final en `app.py`, recupera paridad entre backtest y routing 30m, separa calidad de evidencia estadística, lleva Multi al mismo cierre de gobernanza sin copiar estrategias cripto, mantiene todos los hard guards y hace auditable la función de cada componente de la oficina.

No afirma que una arquitectura produzca automáticamente cuatro señales diarias ni que la rentabilidad histórica garantice el futuro. El criterio de éxito LIVE debe ser: más candidatos con **geometría primaria** llegan al publication gate, disminuye el porcentaje de fallback, las rutas LIVE preservan expectancy/PF OOS y las rutas Shadow nuevas sólo se promueven después de una muestra suficiente.
