# Auditoría Commit 19.2 — Quality Signal Recovery

Fecha: 2026-10-01

## Evidencia que motivó la auditoría

Producción mostraba 0 señales vigentes, 0 confirmadas y 0 activas, pero alrededor de 20 hipótesis direccionales con Entry/SL/TP y R/R coherentes. Varias filas indicaban explícitamente que Safety operativo mínimo se había superado, pero no la publicación Premium.

Esto demuestra que el sistema sí estaba produciendo análisis direccional. El cuello de botella estaba entre **síntesis/optimización de geometría** y **publicación Premium**.

## Hallazgo 1 — cuota genérica de familias

La vía Quant Synthesis exigía un número genérico de familias de estrategia además de la evidencia concreta del patrón. La regla era redundante y especialmente perjudicial para Multi-Activo, donde la semántica de estrategia no siempre coincide con las etiquetas cripto.

### Corrección

Se sustituye la cuota por contratos de evidencia propios del patrón. La calidad global >=0.66, la coherencia Setup/Execution, los conflictos MTF, macro crítico y todos los filtros Premium siguen vigentes.

## Hallazgo 2 — refinamiento encadenado al baseline

El comité podía encontrar una alternativa mejor, pero `_refinement_admissible()` obligaba a conservar características del baseline que no son criterios absolutos de calidad:

- mismo bucket R/R;
- misma clase de timing;
- mismo lado del umbral 0.60 ATR;
- timing baseline y refinado debían dar el mismo resultado;
- desplazamiento/riesgo muy estrechos.

El efecto era paradójico: si el baseline era mediocre, el comité no podía alejarse suficiente para corregirlo.

### Corrección

Se eliminan esas restricciones de paridad y se reemplazan por requisitos absolutos más relevantes: Geometry>=68, Entry>=65, SL>=60, TP>=60, mejora real, R/R válido, Entry timing real y setup guard.

## Hallazgo 3 — score/geometry mismatch

Cuando una alternativa refinada resultaba elegida, Entry/SL/TP podían cambiar sin actualizar simultáneamente `entry_score`, `sl_score` y `tp_score`. Futures Safety podía evaluar los precios nuevos con las puntuaciones de la geometría anterior.

### Corrección

Al seleccionar una geometría refinada se actualizan los scores del candidato seleccionado. Además se añadió `score_execution_geometry()` para medir explícitamente la geometría final sin mover precios.

## Hallazgo 4 — geometría final Champion/Quant

Champion/Quant pueden aplicar una geometría después de etapas previas de scoring. Faltaba una medición final explícita del objeto que realmente llega a la ruta Futures/Multi.

### Corrección

El runtime 19.2 vuelve a puntuar la geometría final cuando detecta una de estas fuentes:

- committee refinement;
- structural recovery;
- Champion geometry parity;
- native Quant Synthesis.

El rescore sólo actualiza métricas; no cambia Entry, SL o TP y no hace I/O.

## Hallazgo 5 — el 68% visible no es la causa

El 68% repetido en filas ANALYSIS_ONLY proviene de caps diagnósticos aplicados **después** de un downgrade. El gate Premium real se basa en Safety, TP Quality, SL Quality, R/R, pérdida al SL y ATR stress. Cambiar el 68% no resolvería la causa y podría maquillar la salida; no se tocó.

## Hallazgo 6 — Multi-Activo

Multi usa el motor Futures y conserva macro gates/resource guards propios. La antigua cuota genérica de familias afectaba más a Multi porque sus contextos no siempre traen las mismas etiquetas de estrategia cripto. El contrato por patrón permite que estructura, tendencia, volumen, MTF y desks formen una tesis nativa sin copiar un Champion cripto.

## Hallazgo 7 — gráficos Greeks incompletos

Para activos sin cadena observada, la curva Black-Scholes necesita un precio. El frontend no siempre encontraba el precio aunque el candlestick ya estuviera dibujado. Además, `--` en Zero-Gamma/Delta-Neutral/Walls podía interpretarse como error cuando en realidad esos niveles no existen sin Open Interest observado.

### Corrección

- Reutilizar último precio válido del Plotly candlestick antes del fallback de red.
- Mostrar `N/A` para métricas OI-only en modo teórico.
- No inventar Zero-Gamma, Delta-Neutral o Walls para activos sin OI real.

## Umbrales verificados como invariantes

`futures_system.py` conserva:

- minimum_publication_execution_safety = 75.0
- minimum_publication_tp_quality = 55.0
- minimum_publication_sl_avoidance_quality = 60.0
- minimum_publication_rr = 1.8
- maximum_publication_rr = 3.5
- maximum_publication_loss_pct_margin = 8.0
- maximum_publication_atr_stress_loss_pct_margin = 25.0

## QA

`qa_commit19_2.py` verifica 28 invariantes, entre ellas:

- contrato por patrón;
- indicador aislado todavía bloqueado;
- Multi native pattern lane;
- scoring exacto de geometría final;
- eliminación de parity shackles;
- mínimos locales de calidad intactos;
- timing gate real obligatorio;
- Safety75/RR1.8/TP55/SL60 intactos;
- Alpha Decay 8+8;
- Greeks reutiliza precio del candle chart;
- sin polling;
- 1 worker / 2 threads;
- hard guard 300 MB;
- options provider 12 MB/día;
- Multi deep limit 2;
- motivos exactos Premium en Futures y Multi.

Resultado: **28/28 PASS**.

## Conclusión

Commit 19.2 no convierte análisis mediocres en señales por decreto. Corrige dos clases de falso negativo: impedir que una tesis concreta obtenga autoridad por una regla genérica, y puntuar una geometría diferente de la que realmente va a ejecutarse. Tras el cambio, una señal sólo se publica si la geometría mejorada supera los mismos límites Premium de producción.
