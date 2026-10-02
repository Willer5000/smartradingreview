# Auditoría Commit 19.2.3 — Candle Close Authority & Telegram Timing

## Resultado
Commit 19.2.2 consiguió que Multi-Activo vuelva a producir candidatos y eliminó el starvation principal del scheduler. La evidencia posterior al deploy mostró dos hechos distintos:

1. **Multi ya está analizando de verdad**: KSTR 1h produjo una tesis SHORT de calidad 100/100 con R/R 1:2.33, pero quedó ANALYSIS_ONLY en la etapa SL. No corresponde convertirla en Premium: el problema ya no es falta de dirección sino que el stop no superó su control técnico.
2. **Telegram Spot tenía una autoridad temporal incorrecta**: una confirmación 1D podía enviarse varias horas después del cierre y 1W podía anclarse al día equivocado de la semana.

## Causa raíz Telegram
### A. Semana anclada al Unix epoch
`_confirmed_signal_close_timestamp()` y `_normalize_candle_start()` podían usar divisiones de segundos desde epoch para 1W. El epoch Unix comenzó un jueves; por ello un grid de `604800` segundos no representa el calendario de vela semanal deseado.

19.2.3 define explícitamente:

- 1W abre lunes 00:00 UTC;
- 1W cierra el lunes siguiente 00:00 UTC;
- en Argentina ese cierre corresponde al domingo 21:00 (UTC-3);
- en Bolivia corresponde al domingo 20:00 (UTC-4).

### B. Ventana anti-cold-start demasiado amplia
La lógica anterior permitía que un resultado 1D siguiera considerándose "nuevo" hasta 6 horas después del cierre y 1W hasta 12 horas después. Eso protegía frente a Render cold-start, pero mezclaba dos conceptos:

- señal todavía técnicamente vigente;
- notificación **NUEVA SEÑAL CONFIRMADA**.

Una señal puede seguir vigente en frontend/Guardian sin que Telegram la anuncie horas después como nueva.

19.2.3 limita el descubrimiento Telegram posterior al cierre:

- 30m: 20 min
- 1h: 45 min
- 2h: 45 min
- 4h: 60 min
- 12h: 60 min
- 1D: 60 min
- 1W: 90 min

El caso observado de BTC 4h enviado ~36 min después del cierre continúa permitido. El PAXG-BTC 1D descubierto ~4.5 h tarde queda bloqueado.

## Causa de carga Spot innecesaria
El scheduler Spot se despertaba por el TF operativo más rápido (4h), pero `_compute_previous_signals()` recorría **4h + 12h + 1D + 1W** en cada ciclo. Además realizaba análisis actuales y replay cerrado, por lo que un cierre 4h ordinario podía provocar hasta 24 análisis completos (3 pares × 4 TF × 2 fases).

19.2.3 agrega **watermarks por timeframe** persistidos en el snapshot compacto:

- cierre ordinario 4h: sólo 4h se recalcula;
- cierre 12h: 4h + 12h;
- cierre diario 00:00 UTC: 4h + 12h + 1D;
- cierre semanal lunes 00:00 UTC: añade 1W.

Esto reduce carga de CPU/RAM/red y libera antes el heavy-analysis lock para Futures y Multi-Activo sin bajar filtros de calidad.

## Impacto esperado sobre frecuencia Futures/Multi
No se modifica Safety, Entry, SL, TP, R/R ni Leverage. La mejora de frecuencia es operativa: menos trabajo Spot innecesario compitiendo por el único turno pesado.

El caso KSTR demuestra que Multi ahora llega hasta una tesis direccional completa. El rechazo `SL` se conserva porque calidad 100/100 de tesis no equivale a stop defendible.

En Futures, la lista de 22 ANALYSIS_ONLY no justifica bajar umbrales. Los cierres posteriores a 19.2.2/19.2.3 deben observarse con los nuevos diagnósticos exactos antes de tocar el motor Premium.

## NEAR guardada
La señal NEAR 30m previa a 19.2.1 mostró recuperación posterior por encima del Entry 4.936 en la captura posterior. Esto es consistente con una entrada de retest razonable. No constituye validación estadística de una sola operación; debe seguir alimentando ReviewTrader/Alpha Decay hasta TP/SL/cierre.

## Recursos
No se agrega ningún proveedor, polling, worker, thread de background ni llamada LLM.

Se conserva:

- Gunicorn 1 worker / 2 threads;
- memory job-start guard 200 MB;
- hard guard 300 MB;
- Multi heavy cap existente;
- options provider budget existente.

La nueva autoridad temporal es cálculo local puro y los watermarks son cuatro timestamps pequeños dentro del snapshot Spot ya existente.

## Cambios de archivos
- `app.py`
- `candle_close_authority_19_2_3.py` (nuevo)
- `commit19_2_3_main_entrypoint.py` (nuevo)
- `Procfile`
- `render.yaml`
- QA/documentación de release.

## SQL
No requiere SQL nuevo.
