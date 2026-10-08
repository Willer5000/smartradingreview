# SmartTradingReview — Commit 33.4.2
## Execution + Display Core Recovery

### Objetivo
Commit 33.4.2 corrige causas de núcleo observadas después de desplegar 33.4.1. No instala overlays, monkeypatches ni un nuevo entrypoint. `app:app` sigue siendo la única autoridad de arranque.

El commit NO baja Safety ni convierte fallbacks en señales. La frecuencia adicional sólo puede aparecer porque candidatos técnicamente válidos dejan de morir por errores de runtime o por gates duplicados sobre la misma evidencia.

### Causas raíz corregidas
1. `futures_system.py` conservaba una referencia huérfana a `_commit28_preexec_route` después de calcular un Entry válido. La variable fue retirada del núcleo y el flujo usa únicamente `_multi_preexec_route` cuando corresponde.
2. `review_trader.py` usaba `uuid.uuid5` sin importar `uuid`.
3. Entry Reaction volvía a actuar como segundo gate de calidad después del Entry Committee. Ahora sólo `hard_block=True` es veto; una reacción débil no-hard queda como diagnóstico.
4. R/R podía evaluarse antes de una reparación estructural de SL y quedar asociado a una geometría ya reemplazada. Ahora R/R se calcula y valida sobre la geometría FINAL.
5. La reparación de SL ya no depende de una whitelist histórica de alpha: si la tesis canónica ya está gobernada y la geometría reparada cumple los mismos floors técnicos, puede mover el stop fuera de una zona de reacción válida. El SL reaction guard continúa siendo duro si el conflicto no se resuelve.
6. Futures invalida snapshots 33.4.1 mediante schema 6 y autoridad de publicación 33.4.2; lifecycle/Guardian se preserva.
7. Multi-Activo recibe un carril de display ligero e independiente: OHLCV real + estructura visual derivada del mismo OHLCV + indicadores en un bundle JS pequeño. No inicia traders, Strategy Bank, AI ni publicación.
8. Cada job pesado incremental y Multi libera/trimmea memoria al terminar; `/futures` y `/multiasset` marcan prioridad interactiva antes de que el background pueda iniciar un nuevo heavy job.
9. Un `q6_job_runs` REST 409/23505 se trata como coordinación normal (slot ya tomado), no como error de runtime.

### Arquitectura LIVE
`Market Data -> Context/Features -> Operational Intelligence -> Pipeline Integrity -> Entry Committee -> SL Committee -> TP Committee -> Safety -> Publication -> Guardian`

Los 9 traders son work-products de evidencia; no se agregan más traders en 33.4.2. Agregar votantes correlacionados aumentaría CPU, RAM y ruido de veto sin solucionar la falla demostrada.

### Multi-Activo
`/api/multiasset/display` es presentation-only y devuelve:
- OHLCV real de una sola celda seleccionada;
- estructura visual ligera (FVG, OB heurístico, pivotes, sweeps, soportes/resistencias);
- identidad de celda y generación 33.4.2.

`static/multiasset_display_core.js` renderiza de forma independiente:
- velas y volumen;
- RSI;
- MACD;
- ADX/DMI;
- ATR;
- Bollinger/volatility bands;
- Ichimoku;
- Estocástico;
- RSI Maverick;
- compresión/expansión;
- SuperTrend proxy visual;
- Williams %R / CCI;
- MFI / Force Index;
- Fibonacci dinámico;
- perfil de volumen;
- FVG / Order Blocks visuales.

Nada de este carril visual crea una señal ni tiene autoridad de trading.

### Verificación de deploy
1. Reemplazar el working tree por este repositorio completo.
2. Commit sugerido: `Commit 33.4.2 - execution and multiasset display core recovery`.
3. Render debe arrancar con `gunicorn app:app ...`.
4. Abrir `/api/runtime/version` y verificar:
   - `COMMIT33_4_2_EXECUTION_AND_DISPLAY_CORE_V1`
   - `entrypoint = app:app`
   - `runtime_overlay_chain = false`
5. En logs posteriores al boot NO debe aparecer `_commit28_preexec_route`.
6. El primer ciclo puede descartar análisis del snapshot 33.4.1 por cambio de schema; lifecycle de señales guardadas se conserva.

### Qué NO hace este commit
- no promete una cuota de señales;
- no baja thresholds para fabricar frecuencia;
- no publica fallback geometry;
- no agrega traders;
- no promueve las estrategias research 30m sin IS/OOS;
- no altera una operación guardada por el usuario.
