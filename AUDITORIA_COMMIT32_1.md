# Auditoría Commit 32.1 — causas raíz y reparación

## Evidencia que motivó 32.1
1. Futures mostraba 0 confirmadas y múltiples hipótesis construidas con `FALLBACK_GEOMETRY_NOT_PUBLISHABLE`.
2. Multi fallaba repetidamente con `unexpected keyword argument 'execution_observations'`.
3. Los gráficos recibían respuestas visuales diferidas mientras RSS permanecía habitualmente por encima de 210 MB.
4. Heavy jobs terminaron alrededor de 270–309 MB; el job-start de 190 MB generaba backoff crónico.
5. El router particular exigía todos los core + MTF limpio, creando over-selection antes de Geometry.

## Causa A — Commit32 vigilaba el ABI equivocado de forma incompleta
El boot guard comprobaba Futures, pero no la clase Multi ni el singleton efectivo. Además el checkpoint RAM de Geometry envolvía el método base de `app.py`, mientras Futures tiene un override propio.

**Reparación:** ABI explícito + boot guard triple + wrapper sobre el override real.

## Causa B — la UI visual dependía de un umbral inferior al RSS normal
El visual lane devolvía `deferred` si existía heavy owner o RSS >=210 MB. El proceso operaba frecuentemente en 215–300 MB, por lo que la UI podía quedar indefinidamente sin OHLC.

**Reparación:** fallback display-only de 120 OHLC que no ejecuta traders ni pide heavy lock.

## Causa C — memoria protegida mediante starvation
C32 configuró job-start 190 MB, pero los logs muestran un baseline operativo mayor. La consecuencia no fue sólo protección: background y UI pesada quedaban sin turno repetidamente.

**Reparación:** un solo heavy job, pero límites coherentes con el working set real + cache shed + abort + post-job malloc_trim.

## Causa D — over-selection pre-Geometry
Los contratos existentes exigen todos los core y MTF limpio. Esto es correcto para algunos trend setups, pero excesivo para early impulse y reversal.

**Reparación:** segundo chance por roles, únicamente después de que la ruta normal falle. MTF continúa estricto donde conceptualmente corresponde y contextual donde el setup puede liderar al HTF.

## Lo que NO cambia
- 8 Safeties especializados de Commit31.
- hard risk.
- ruta estadística OOS/LIVE.
- prohibición de publicar fallback.
- Guardian por usuario/timeframe.
- Entry tempo CORE/MEDIUM/HIGH de Commit32.
- número de traders/comités.

## Nuevas estrategias
CRT/Triple RSI no corrigen un ABI ni un OOM. Incorporarlas directamente LIVE antes de resolver estos defectos confundiría una mejora de alpha con una reparación de ingeniería. Por eso 32.1 sólo crea su protocolo Research/Shadow.
