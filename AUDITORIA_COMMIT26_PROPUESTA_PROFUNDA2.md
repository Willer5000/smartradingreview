# AUDITORÍA COMMIT 25 → COMMIT 26 — PROPUESTA PROFUNDA 2

Fecha de auditoría: 2026-10-06

## 1. Veredicto ejecutivo

Commit 25 corrigió dos problemas reales: recuperó rutas Champion con evidencia histórica y retiró `max(Q1..Q10)` como autoridad optimista de publicación. Sin embargo, no resolvió el problema de frecuencia porque introdujo una incompatibilidad temporal en la ruta Champion 30m: exige MSS/displacement en el router **antes** de que el sistema construya esos campos durante la selección de Entry.

El resultado práctico es un falso negativo de plumbing: una oportunidad 30m puede tener tendencia, volumen, ADX, RSI, estructura cerrada y zona de reacción reales, pero no alcanza la etapa donde Entry/SL/TP y Safety pueden evaluarla.

**Commit 26 / Propuesta Profunda 2 repara exclusivamente ese desfase.** No baja Safety, RR, SL Quality, TP Quality, ATR stress, pérdida máxima, closed-candle authority ni leverage policy. Tampoco agrega workers, requests, Supabase, Groq, polling ni cachés.

La expansión LIVE deliberada es sólo la ruta 30m que ya tiene replay IS/OOS positivo. No se promueven nuevas rutas 1h ni Multi sin evidencia OOS limpia.

---

## 2. Hallazgo crítico #1 — Commit 25 pide evidencia que todavía no existe

### Commit 25

Para `F30_SHARED_LIQ_SWEEP_MSS_POI_V1`, el router exigía:

- Sweep + MSS, o
- Displacement + POI.

Pero `analyze_price_structure_layer()` en el flujo real pre-Entry expone:

- `direction` / `structure_direction`;
- `structure_reasons`;
- supports/resistances;
- pivots;
- order blocks;
- fair value gaps;
- liquidity sweeps;
- stop hunts;
- volume profile.

Los campos de ejecución:

- `entry_mss_bos_confirmed`;
- `entry_displacement_confirmed`;

se calculan posteriormente durante la construcción de Entry/levels.

Por lo tanto, Commit 25 estaba solicitando una confirmación **post-Entry** en una etapa **pre-Entry**.

### Evidencia reproducible

Con un payload que replica el esquema real pre-Entry:

- trigger Commit 25: **False**;
- trigger Commit 26: **True** cuando hay evento estructural estricto de vela cerrada y existe inventario real de reacción;
- Commit 26 sin evento estructural estricto: **False**.

Esto recupera coverage sin fabricar evidencia.

---

## 3. Solución causal de Commit 26

El router 30m se divide conceptualmente en dos fases.

### Fase A — elegibilidad pre-Entry

Se conserva exactamente el contrato histórico del cohort rentable:

- tendencia alineada;
- ADX >= 20;
- volume ratio >= 1.20;
- RSI LONG <= 80;
- RSI SHORT >= 20;
- activo/celda dentro del Champion exacto;
- MTF sin conflicto LIVE no validado;
- macro no CRITICAL.

La estructura ahora debe usar evidencia que existe en ese momento:

1. dirección estricta de Structure igual a la tesis;
2. evento primario reciente de vela cerrada:
   - `SWEEP_REJECTION`,
   - `STOP_HUNT_RECOVERY`, o
   - `BOS_CLOSE`;
3. inventario real para que el motor de reacción pueda construir Entry:
   - liquidity sweep / stop hunt,
   - OB/FVG,
   - soporte/resistencia/pivote real.

**Fase A no elige Entry, SL o TP.** Sólo permite que una hipótesis estadísticamente gobernada llegue a ejecución.

### Fase B — ejecución y publicación

Se mantiene intacta la autoridad downstream:

- Entry en zona de reacción;
- reachability;
- confirmación SMC durante Entry;
- geometría válida;
- SL detrás de invalidación/reacción;
- SL Quality;
- TP antes de una reacción probable;
- TP Quality;
- RR contractual;
- Safety;
- pérdida al SL;
- ATR stress;
- liquidation buffer;
- leverage calculado después de Entry/SL/TP;
- vela cerrada;
- datos reales;
- publication gate;
- Telegram sólo después de publicación.

Así se aumenta la frecuencia **antes** de los hard guards, no rebajando los hard guards.

---

## 4. Backtest ejecutado por esta auditoría

### 4.1 Ruta 30m — replay físico del CSV incluido

Se reejecutó `BACKTEST_ROWS_17_5_10_PROFITABILITY.csv` usando el split cronológico congelado y el stress de coste histórico de 0.118R por entrada.

| Split | N | Net R | Expectancy | PF | MaxDD |
|---|---:|---:|---:|---:|---:|
| IS | 11 | +1.702R | +0.1547R/trade | 1.254 | 2.236R |
| OOS | 4 | +3.928R | +0.9820R/trade | 4.513 | 1.118R |
| Combined | 15 | +5.630R | +0.3753R/trade | 1.719 | 2.236R |

Bootstrap 100,000 remuestreos:

- P(media > 0): ~90.3%;
- CI95 de la media incluye cero.

Conclusión: resultado positivo y consistente con la promoción histórica, pero todavía de muestra pequeña. Debe conservar Alpha Decay y vigilancia LIVE.

### 4.2 Stress adicional de costes

Sobre el coste histórico ya descontado:

- +0.05R/trade adicional: IS +0.1047R, PF 1.164; OOS +0.932R, PF 4.192.
- +0.10R/trade adicional: IS +0.0547R, PF 1.082; OOS +0.882R, PF 3.897.
- +0.15R/trade adicional: IS apenas +0.0047R, PF 1.007; OOS +0.832R.
- +0.20R/trade adicional: IS pasa a negativo.

Esto indica que el edge 30m no debe cargarse con capas adicionales costosas ni LLM por trade.

### 4.3 Evidencia conjunta de todas las rutas gobernadas

Agregación de evidencia de rutas, **no** simulación de portfolio sincronizado:

- IS: N=388, expectancy ponderada +0.0467R, PF proxy 1.093.
- OOS: N=133, expectancy ponderada +0.4300R, PF proxy 2.239.

Todas las particiones disponibles de las rutas actualmente gobernadas mantienen expectativa >0 y PF>1.

---

## 5. Por qué NO activo 1h LIVE todavía

La evidencia disponible contradice una promoción directa:

### Histórico general 1h

- resolved: 120;
- TP: 11;
- SL: 109;
- WR: 9.17%;
- gross expectancy proxy: -0.642R;
- modeled net R: -0.907R.

### Challenger `LIQUIDITY_SWEEP_MSS_POI` 1h

- observations: 50;
- TP: 9;
- SL: 18;
- expired: 23;
- expectancy: +0.089R;
- PF: 1.134.

El challenger es marginalmente positivo, pero no existe en los archivos suministrados un split cronológico limpio IS/Selection/OOS equivalente al de 30m. Promoverlo hoy sería precisamente el overfitting que se quiere evitar.

**Uso de 1h en Commit 26:** contexto/setup MTF para 30m y Research/Shadow para recolectar evidencia. No nueva autoridad de Telegram.

---

## 6. Alta volatilidad 4h: interpretación correcta

Alta volatilidad 4h incrementa rango y número potencial de desplazamientos, pero **no implica automáticamente leverage alto**.

La cadena correcta es:

`4h volatility/context -> 1h setup/context -> 30m timing -> reaction Entry -> structural SL -> reachable TP -> economics -> leverage`

El leverage sólo puede subir cuando la distancia Entry-SL y el liquidation buffer lo permiten manteniendo:

- pérdida al SL contractual;
- ATR stress contractual;
- Safety;
- RR.

Forzar leverage por volatilidad sería un error de riesgo.

Commit 26 permite que la volatilidad alta sea contexto, pero no una fuente de dirección ni una excepción de Safety.

---

## 7. Hallazgo crítico #2 — transiciones MTF

Commit 18.2 distingue:

- `HARD_CONFLICT`;
- `REVERSAL_TRANSITION`;
- `COUNTERTREND_VALID`.

Commit 25 vuelve a bloquear los dos últimos porque conserva `original_conflict=True`.

Esto puede ocultar oportunidades 30m frente a un 4h opuesto. Sin embargo, el dataset suministrado no conserva la relación 4h→30m sincronizada para rebacktestear este subconjunto IS/OOS.

**Decisión Commit 26:** esas transiciones quedan explícitamente `SHADOW_ONLY`; no se les otorga LIVE hasta reunir evidencia temporal limpia. Se evita transformar una intuición razonable de mercado en una regla sobreajustada.

---

## 8. Futures — arquitectura recomendada

### Datos / indicadores

Rol: observables. No son votos independientes.

- Trend family: ADX/DMI/EMA como una familia correlacionada.
- Structure/Liquidity: sweep/BOS/OB/FVG como otra familia.
- Momentum: RSI/MACD/divergencias como una familia.
- Volume/flow: volumen/OBV/MFI/whales como familia.
- Volatility: ATR/BB/squeeze como contexto y geometry normalizer.

### Traders / especialistas

Rol: producir hipótesis y evidencia especializada. No deben sumar nueve votos como si fueran nueve edges.

### Comité / moderador

Rol: resolver contradicciones y seleccionar una tesis candidata. No debe aumentar probabilidad por cantidad de miembros.

### Champion registry

Rol: única autoridad estadística de ruta LIVE antes de ejecución. Exact cell only: asset × TF × direction × context demostrado.

### Q1..Q10

Rol: diagnóstico y trazabilidad de calidad. No usar `max(Q1..Q10)` para publicar. Sus scores sirven para explicar bloqueos, Research y aprendizaje.

### Execution engine

Rol: transformar la tesis en un trade defendible. Aquí se validan reacción, reachability, MSS/displacement, SL/TP y economía.

### ReviewTrader / Alpha Decay

Rol: outcomes reales y retirada de edges degradados. No crear señales ni elevar scores.

Esta separación hace que todos los componentes sean útiles sin multiplicar artificialmente grados de libertad.

---

## 9. Multi-Activo

No se copia la ruta crypto a:

- ENERGY;
- INDUSTRIAL_METAL;
- PRECIOUS_METAL;
- CHINA_INDEX.

El proxy histórico genérico Multi incluido fue negativo:

- signals 74;
- resolved 59;
- expectancy -0.3714R;
- PF 0.553;
- MaxDD 24.761R.

Por tanto, Commit 26 conserva LIVE sólo donde ya hay evidencia gobernada (US_INDEX 1D) y deja las otras clases en Strategy Bank + Shadow/Research. Cada clase debe construir su propio OOS antes de Telegram.

También se inspeccionó el ZIP `smartradingresearch-main (1)`: contiene el laboratorio causal 60/20/20 y el motor Multi, pero no incluye una exportación nueva de resultados OOS que justifique promover ENERGY/METALS/CHINA o 1h a LIVE. El propio diseño de Research mantiene esas promociones condicionadas a OOS final y walk-forward.

---

## 10. Spot

No se cambia la lógica de Spot.

Histórico disponible:

- resolved 16;
- TP 9;
- SL 7;
- WR 56.25%;
- expectancy proxy +1.3656R;
- PF proxy 4.121.

La muestra es pequeña y no contiene una contabilidad completa de rotación/costes, pero no hay evidencia para justificar intervenir un módulo que el usuario reporta funcional.

---

## 11. Recursos

Commit 26 agrega:

- 0 threads;
- 0 loops;
- 0 requests de mercado;
- 0 lecturas Supabase;
- 0 escrituras Supabase;
- 0 llamadas Groq/LLM;
- 0 cachés persistentes.

Microbenchmark del router reparado: 100,000 resoluciones en ~6.1 s en el entorno de auditoría; pico `tracemalloc` ~0.07 MB. No representa el RSS del proceso Flask completo, pero demuestra que la lógica añadida es computacionalmente trivial.

Se conservan:

- 1 worker;
- 2 gthreads;
- MEMORY_SOFT_LIMIT_MB=220;
- MEMORY_HARD_LIMIT_MB=300;
- MEMORY_JOB_START_LIMIT_MB=200;
- MAIN_SUPABASE_DAILY_BUDGET_MB=12;
- AI_GROQ_DAILY_TOKEN_BUDGET=140000.

---

## 12. QA

Ejecutado sobre el árbol Commit 25 + Commit 26:

- compilación de todos los `.py` de raíz: PASS;
- nuevo `test_commit26_causal_preentry.py`: PASS;
- `test_commit25_contextual_authority.py`: PASS;
- `test_commit23_parallel_quality.py`: PASS;
- `test_commit22_context_quality.py`: PASS;
- `qa_commit19_1.py`: PASS;
- `test_rc9_8_execution_geometry.py`: PASS.

Existe un fallo **preexistente** en `test_rc9_7_15_entry_location_engine.py` sobre el signo de `location_adjustment` para un LONG en techo cuando la selección final es un soporte profundo a 1.6 ATR. Commit 26 no modifica `app.py` ni ese algoritmo. No se ha usado ese test como justificación para relajar Entry.

---

## 13. Base de datos LIVE y límite de esta auditoría

El código reconoce el project ref actual `frganummqwzzsukdefqd`, pero los ZIP suministrados no contienen una credencial Supabase utilizable para consultar directamente el funnel de los últimos cuatro días. La URL por sí sola no permite auditar tablas privadas. Por ello esta auditoría no inventa estadísticas del período LIVE reciente: usa código real, artefactos históricos reproducibles y tests locales.

Esto hace todavía más importante que el funnel posterior al deploy registre por qué muere cada candidato.

## 14. Riesgo de despliegue detectado

El ZIP `smartradingreview-main (10)` suministrado ya contiene Commit 25. Sin embargo, la captura de Render incluida en la solicitud muestra como LIVE el SHA abreviado `bdd6866`, que en el dossier corresponde a Commit 24.5.

Si esa captura es actual, **Commit 25 no está corriendo en producción aunque esté en GitHub/main**.

Después de subir Commit 26, verificar en Render que:

1. el deploy LIVE muestra el nuevo SHA;
2. el Start Command usa `commit26_main_entrypoint:app`;
3. los logs imprimen `COMMIT26_CAUSAL_PREENTRY_RECOVERY_PROPOSAL2_V1`;
4. no se mantiene un deploy anterior como LIVE.

---

## 15. Criterio de éxito LIVE

Durante la primera ventana de observación, no medir sólo “cantidad de Telegram”. Medir:

- F30 candidates que llegan al Champion router;
- bloqueos por ADX/volume/RSI;
- bloqueos por strict Structure;
- candidatos que llegan a Entry;
- Entry reaction pass/fail;
- geometry valid;
- Safety;
- RR;
- ATR stress;
- publication gate;
- Premium publicados;
- outcomes y Alpha Decay.

La mejora esperada es **más candidatos 30m válidos alcanzando Entry**, no una tasa artificial de publicación.

---

## 16. Conclusión

Commit 26 es una intervención pequeña sobre una causa raíz grande:

**Commit 25 tenía una ruta rentable habilitada en el registry, pero el contrato live pedía pruebas de ejecución antes de que la ejecución existiera.**

La reparación aumenta la probabilidad de producir señales 30m de calidad en contextos activos sin modificar el estándar económico ni el riesgo. 1h y Multi no reciben autoridad nueva porque los datos suministrados todavía no justifican hacerlo sin overfitting.
