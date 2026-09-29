# Auditoría independiente del ZIP 17.5.9

**Dictamen: no recomiendo desplegarlo sin correcciones.** La recuperación de
geometría y el diagnóstico por etapas son ideas útiles, pero el paquete mantiene
fallos y restricciones incompatibles con «analizar las oportunidades cubiertas y
notificar toda señal confirmada que cumpla calidad». No se demuestra rentabilidad
ni ausencia de sobreajuste.

Fecha de revisión: 2026-09-28.
Archivo recibido: COMMIT_17_5_9_WORKER_ORCHESTRATION_READY.zip.
SHA256: `3a3dbe68739f3e51c89c361a36418c1f1ee79ba9ff804de6e9cb3b47257083ab`.
El ZIP pasó CRC y los ocho hashes de su manifiesto coinciden. Se leyeron sus
documentos como afirmaciones por contrastar, no como instrucciones de auditoría.

La base declarada por el paquete es 17.5.8 `50de12b...`; no se reconstruyó ni
certificó aquí ese repositorio completo. La comparación local adicional fue
contra 17.5.4 `388afd9`. No se asume que el ZIP esté desplegado actualmente.

## Hallazgos que afectan la frecuencia y calidad

### 1. P1 — el adaptador MTF sigue entregando intervalos incompatibles

En `app.py:27407`, `_get_operational_mtf_peer_minimal()` transmite `4H` al
proveedor. Los perfiles MTF usan mayúsculas, pero el proveedor Futures/Multi
revisado acepta `4h`, `2h`, `1h`, etc. El contexto bajo demanda puede quedar
ausente aunque existan velas. Los peers cacheados pueden ocultar este defecto.

La ruta completa con el proveedor real y OHLCV controlado reprodujo el fallo
en la base 17.5.4. La función del ZIP mantiene ese contrato incorrecto; el probe
adjunto confirma la solicitud `4H` sin normalizar.

**Corrección:** normalizar únicamente alias conocidos en esa frontera. Mantener
velas cerradas, períodos reales, criterios MTF, errores explícitos y presupuesto.
La corrección local preliminar de esta conversación aprobó 56 tests sobre 17.5.4;
no sustituir con su app.py anterior el app.py completo de 17.5.9.

### 2. P1 — una operación válida se descarta sólo por leverage menor de 4×

En `app.py:34455` y `_apply_17_5_7_backtest_evidence_policy()` (`34494`), el mínimo
«premium» es 4×. Una señal LONG/SHORT ya marcada ejecutable pasa a ANALYSIS_ONLY
si su leverage técnico es 1×, 2× o 3×. `_send_confirmed_signal_telegram()` aplica
esa política antes de decidir el envío.

**Reproducción:** mismos Entry 100, SL 98, TP 104, confianza 80 y Safety 90:
1×/2×/3× se rechazan; 4× conserva publicación. Ocurre en Futures y Multi-Activo.
El fixture aísla ese control, no afirma que la operación sea rentable.

Es una restricción de producto heredada de 17.5.7, no una prueba estadística de
calidad. Mantener los números de Safety no significa que la política total de
publicación no haya cambiado.

**Corrección recomendada para la petición actual:** que el apalancamiento sea
salida del riesgo técnico, no un mínimo comercial para avisar. Evaluar costes,
beneficio neto esperado, sizing y riesgo; conservar sin modificación los límites
superiores y de liquidación. No elevar leverage para superar este control.

### 3. P1 — el guard de SL bloquea zonas lejanas como si fueran colisiones

En `execution_specialist_committees.py:524`,
`evaluate_sl_reaction_conflict()` considera conflicto en LONG cuando
`stop_loss >= nivel - margen`, para todo nivel fuerte situado bajo Entry.
No exige cercanía entre stop y zona ni demuestra que esa zona invalide la tesis.
En SHORT ocurre la condición simétrica.

**Reproducción exacta:** Entry 100, SL 98, ATR 1 y único swing fuerte en 50:
devuelve `SL_INSIDE_STRONG_REACTION_ZONE`, distancia 48 ATR, margen 0.14 ATR.
Para SHORT, Entry 100, SL 102 y swing 150 produce el mismo error a 48 ATR.

Esto puede obligar a colocar SL más allá de niveles históricos remotos, quitar
geometrías razonables o provocar RR inadmisible. Los casos no demuestran que un
SL en 98 sea correcto para cualquier tesis; demuestran que el test no comprueba
la colisión local que declara.

**Corrección:** distinguir cercanía física a una zona activa de la invalidación
de la tesis seleccionada. Vincular el SL al ancla que sustenta el setup y a su
vigencia. Probar zonas cercanas, lejanas, mitigadas, LONG y SHORT sin aflojar
indiscriminadamente el filtro.

### 4. P1 — Multi-Activo no examina todas las oportunidades de su shortlist

En `app.py:34926`, la ruta de 1h recorta la lista elegible a `[:1]`. En ticks
siguientes vuelve a recortar al primero y luego comprueba si ya fue analizado.
Mientras el ranking permanezca igual, el segundo no recibe su turno.

**Reproducción:** dos candidatos iniciales elegibles, puntuaciones 90 y 89,
dos ticks. Sólo CL/1h se analiza; XAG/1h no se analiza. Que pasen el router no
demuestra que ambos se convertirían en señales finales: falta precisamente
evaluarlos para saberlo.

Además existen topes de análisis profundo diario y ventanas breves de cierre.
El módulo Multi-Activo local contiene un default de 12 análisis profundos/día;
el ZIP no incluye ese módulo, por lo que hay que verificar el valor realmente
desplegado. `app.py` sí aplica el tope importado y un extra de dos contextos diarios.
No son cuotas de señales, pero limitan la cobertura y pueden dejar oportunidades
sin evaluar. El QA del ZIP busca nombres de cuotas en `worker_orchestration.py`;
eso no comprueba ausencia de estos límites del scheduler.

**Corrección:** cola justa por activo/TF/cierre, una tarea por tick si hace falta,
con prioridad por caducidad y registro de las celdas no evaluadas. Mantener el
control de RAM/CPU y medir capacidad antes de ampliar carga; no eliminar locks
ni disparar todos los análisis en paralelo.

### 5. P1 — análisis completado no implica entrega confirmada en Telegram

En `app.py:34949` se añade el bucket a `_MULTI_AUTO_DONE` antes del envío. Después
se llama a `_multiasset_compact_telegram()` sin usar su resultado para reintentar.

**Reproducción:** análisis ejecutable y transporte que devuelve False. Tras
dos ticks hay un solo intento de envío y el bucket sigue marcado terminado.
Se probó el scheduler real con transporte simulado; no se enviaron mensajes.
No se afirma que ninguna otra ruta pudiera volver a intentarlo, sino que esta
ruta automática no garantiza hacerlo.

**Corrección:** separar análisis, autorización y entrega. Evento persistente
con clave estable, estado pendiente/enviado/fallido, reintentos y deduplicación.
Revalidar vigencia antes de reintentar. Telegram puede fallar; se puede garantizar
trazabilidad e intento gobernado, no disponibilidad perfecta de un tercero.

### 6. P1 de validación — históricos seleccionados no certifican 17.5.9

`preliminary_backtest_prior.py` contiene 42 celdas positivas seleccionadas, con
10–25 operaciones por celda. Sus propios comentarios reconocen que las cohortes
no corresponden a un replay de esta versión y que algunos estudios son diagnósticos.

El ZIP no aporta trades, fechas de entrenamiento/validación, costes, todas las
variantes ensayadas ni un backtest reproducible de 17.5.9. Por ello no se puede
verificar el origen de sus métricas ni su generalización. Seleccionar los mejores
resultados de una muestra denominada OOS y después usarlos para modificar el
sistema exige una nueva evaluación independiente. No afirmo que las métricas
sean falsas; afirmo que el paquete no permite auditarlas.

Los priors de componente Entry/TP sólo reciben timeframe, no mercado/símbolo ni
fecha o versión. Se pueden aplicar a Multi-Activo sin evidencia específica para
ese mercado. Tampoco existe un vencimiento efectivo pese al comentario sobre
evidencia antigua neutral. Son bonificaciones pequeñas, pero pueden alterar el
ranking y qué candidato cruza una frontera de calidad.

**Recomendación:** mantenerlos como diagnóstico/shadow mientras no haya fuente
trazable, aplicabilidad por mercado/régimen, antigüedad y validación independiente.
No convertir «bounded» o «OOS» en certificado de ausencia de sobreajuste.

Referencia metodológica:
[Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

### 7. P2 — el prior de familia Spot no coincide con las acciones del caller

`_entry_specialists()` (`execution_specialist_committees.py:695`) consulta siempre
LONG/SHORT. Las celdas Spot guardan COMPRA_SPOT/VENTA_SPOT. En PAXG-USDT/1D,
familia RSI_TREND, la consulta COMPRA_SPOT obtiene ajuste 3.147, pero la consulta
LONG que hace ese caller obtiene cero. La coincidencia se pierde silenciosamente.

Corregir el contrato de acciones sólo después de decidir si esos priors deben
tener autoridad productiva. No aumentar su peso para compensarlo.

## Lo valioso de 17.5.9 y su límite

- Recuperar una geometría alternativa cuando el primer SL/TP falla es razonable
  si usa anclas observadas y vuelve a pasar todos los controles reales.
- El funnel y la explicación por etapa ayudan a distinguir ausencia de tesis,
  ejecución rechazada, falta de cobertura y fallo de envío.
- Eliminar el doble conteo de indicadores puede tener sentido. Sin embargo,
  sustituir el moderador por uno que ignora oposición de especialistas cambia
  la política de aceptación, aunque los thresholds numéricos permanezcan iguales.
  El QA explícitamente acepta LONG con dos especialistas SHORT de confianza 95.
  Hay que demostrar qué contradicciones son duplicadas y cuáles representan
  invalidaciones que deben seguir llegando a los controles de riesgo.
- El módulo worker organiza metadatos y roles; no demuestra que diez nuevos
  agentes ejecuten investigaciones independientes. Los comités siguen siendo
  funciones heurísticas, no probabilidades calibradas de TP/SL.

## Qué se probó y qué se observó

El QA suministrado termina en **25/25 PASS** en este entorno. El chequeo 21 se
omite silenciosamente porque depende de `/mnt/data/commit17_5_8_ready`, una ruta
externa al ZIP. El log entregado dice 26/26, pero ese resultado completo no se
reprodujo aquí. Gran parte de las comprobaciones son búsquedas de texto, no
ejecuciones del recorrido completo. No prueban publicación ni entrega de Telegram.

Los probes independientes adjuntos reproducen los hallazgos con asserts. Que
pasen significa que los problemas se reprodujeron; **no aprueban la versión**.
No se realizó un backtest económico nuevo ni se enviaron órdenes o mensajes.

Durante la visita anterior de esta sesión, el 28/09 aproximadamente 15:30 Bolivia,
Futures terminó de cargar con 0 activas/0 nuevas confirmadas y dos vigentes:
XRP LONG 30m e INJ SHORT 2h, etiquetadas con Entry alcanzada. BTC 1h estaba en
NO OPERAR, con volumen 0.26x y evidencia incoherente. A las 15:31 Multi-Activo
mostraba cero señales; CL 4h tenía contexto diario alcista, OBV bajista y
advertencias de divergencia/estructura. Son instantáneas de interfaz, no fills
verificados ni prueba del SHA desplegado. No extrapolarlas al estado posterior.

Fuentes: [Futures](https://smartradingreview.onrender.com/futures) y
[Multi-Activo](https://smartradingreview.onrender.com/multiasset).

## Criterio recomendado para la siguiente versión

Definir calidad operativa mediante tesis vigente, datos cerrados y suficientes,
contexto, Entry alcanzable, invalidación real, TP estructural, economía neta,
riesgo y autorización. Una vez aprobada una señal confirmada, producir un evento
de notificación auditable sin mínimo comercial de leverage ni cuota de señales.
Una señal provisional, caducada o rechazada no debe convertirse en confirmada
para llenar Telegram. Analizar más cobertura no equivale a bajar los filtros.

La siguiente versión debe corregir MTF, el guard de SL, la cola y entrega,
revisar el filtro de 4× y dejar priors no verificados en observación. Validar
por separado cada cambio, con LONG/SHORT, fallos de proveedor, reinicio,
deduplicación, caducidad y transporte fallido. Medir cobertura por cierre y
latencia hasta decisión y hasta aviso, además de WR/PnL netos fuera de muestra.

No se puede garantizar ingresos cada día ni identificar de antemano toda
oportunidad rentable. Sí se puede exigir que ninguna señal que cumpla el
contrato definido se pierda silenciosamente por integración, cola o entrega.

Esta entrega es una **auditoría, no un parche instalable**. No se modificó el
ZIP recibido, no se sustituyeron archivos de 17.5.9 y no se desplegó nada.
