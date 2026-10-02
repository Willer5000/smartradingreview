# AUDITORÍA COMMIT 19.2.2 — Runtime Scheduler & Multi Read Recovery
Fecha: 2026-10-02
Base: Commit 19.2.1

## Hallazgo principal
El problema observado después de 19.2.1 no era únicamente de filtros de trading. Los logs productivos muestran que los trabajos que debían refrescar Futures y Multi eran diferidos por un guard de threads absoluto:

- `multi-background:XAG-USDT:1D: threads=11 >= 10; job de fondo diferido`
- `futures-incremental:NEAR-USDT:30m: threads=12 >= 10; job de fondo diferido`

El proceso posee varios threads daemon permanentes. Por tanto `threading.active_count() >= 10` no medía concurrencia pesada real y podía bloquear para siempre el scheduler aun con el heavy lock libre y RSS seguro.

## Corrección estructural
1. La concurrencia pesada continúa siendo exactamente UNA mediante `_HEAVY_ANALYSIS_LOCK`.
2. El inicio de trabajos continúa bloqueado por RSS >= 200 MB y hard guard 300 MB.
3. El número total de threads pasa a ser señal de presión transitoria, no veto absoluto. Se captura un baseline de daemons permanentes y sólo se difiere por combinación de exceso transitorio + presión RSS.
4. No se agregan workers ni threads de servicio.

## Multi /opportunities 502
19.2.1 hacía que el GET del navegador `/api/multiasset/opportunities` ejecutara `scan_opportunities()`. Cuando la caché vencía, una consulta visual podía recorrer el universo Multi y abrir I/O de proveedor. El log productivo mostró HTTP 502.

19.2.2 convierte `/api/multiasset/opportunities`, `/api/multiasset/correlation` y el router usado por AI en lectores de caché. Sólo el scheduler background tiene autoridad para refrescar el router.

Resultado esperado:
- el navegador deja de competir con el scheduler;
- menos fan-out de red;
- un 502/lectura degradada no destruye el último estado visual;
- el endpoint de activas responde fail-soft 200 sin iniciar análisis pesado.

## CL 4H · `DIRECTION CONFIRMATION`
El diagnóstico era ambiguo. Una tesis podía tener dirección y geometría completa, y posteriormente `execution_setup_guard` degradarla a ESPERAR/PRECAUCION. El funnel la etiquetaba genéricamente como `DIRECTION_CONFIRMATION` porque la acción final ya no era LONG/SHORT.

19.2.2 distingue:
- `EXECUTION_SETUP_GUARD` + razones exactas;
- `ENTRY_FRESHNESS`;
- `DIRECTION_CONFIRMATION` sólo cuando realmente faltó confirmación direccional.

No se baja ningún gate para CL. Un análisis Quality 92 puede seguir siendo ANALYSIS_ONLY si su setup de ejecución no está confirmado. Geometry Quality y Direction/Execution Quality no son la misma variable.

## Greeks
Las griegas NO son sólo frontend.

Con cadena observada válida (actualmente el proveedor directo está acotado a BTC/ETH), Zero-Gamma/Delta-Neutral/Walls entran en los comités como rankers acotados:
- Entry: confluencia de un candidato técnico ya existente;
- SL: penalización por colisión con reacción observada;
- TP: ranking/front-run de barrera observada.

No crean dirección ni pueden saltar Safety.

Para AVAX/PAXG/CL/etc. existen Delta/Gamma/Vega/Theta y niveles teóricos Black-Scholes, pero NO reciben autoridad productiva de Entry/SL/TP porque no contienen Open Interest observado. Usarlos como si fueran dealer positioning duplicaría volatilidad/modelo y produciría pseudo-evidencia.

## Calidad preservada
No se modifican:
- Entry >= 65 para Quant Synthesis;
- SL >= 60;
- TP >= 60;
- Safety Premium;
- R/R por contexto;
- reaction guard;
- Leverage V6;
- Guardian;
- Alpha Decay 8 LIVE -> Shadow -> 8 Shadow -> Retired.

## Recursos
- Gunicorn: 1 worker, 2 threads.
- MEMORY_SOFT_LIMIT_MB: 220.
- MEMORY_HARD_LIMIT_MB: 300.
- MEMORY_JOB_START_LIMIT_MB: 200.
- MULTIASSET_DEEP_LIMIT: 2.
- No proveedor nuevo.
- No polling nuevo.
- No llamadas LLM nuevas.
- Multi HTTP ahora usa MENOS red porque sus lecturas son cache-only.

## Validación
- QA 19.2.2: 33/33 PASS.
- Regression 19.2.1: 49/49 PASS.
- Regression 19.2: 28/28 PASS.
- Regression 19.1: 13/13 PASS.
- Regression 17.5.11R1: 18/18 PASS.
- Python compileall: PASS.
- Node syntax futures.js: PASS.
- Champion backtest: sin regresión.
