# SmartTradingReview — Commit 28 Core Execution Recovery

## Objetivo

Resolver en un único deploy los cuellos de botella demostrados por los logs de producción sin bajar Safety, RR, calidad de Entry/SL/TP, ATR stress, leverage policy ni closed-candle authority.

Commit 28 **no añade una cuota de señales** y no promueve rutas sin OOS. Su objetivo es que una oportunidad válida llegue completa al motor de geometría y sea rechazada/publicada por razones técnicas reales, no por incompatibilidades internas.

## Causas raíz demostradas

### 1. ABI roto antes de Entry/SL/TP

`app.py` llama:

`calculate_entry_levels(..., execution_observations=capas)`

El override de `FuturesAnalysis.calculate_entry_levels()` no aceptaba ese argumento. Los logs mostraron:

`TypeError: FuturesAnalysis.calculate_entry_levels() got an unexpected keyword argument 'execution_observations'`

Consecuencia: Futures/Multi podían caer en `EXECUTION_RUNTIME_FAILED` o terminar usando geometría de visibilidad/fallback en vez de geometría primaria.

### 2. Context starvation en Futures

Los análisis de alts podían entrar a `analyze_full_market()` con `btc_analysis=None`, que luego se convertía en un contexto neutral artificial con ADX=0. Commit 28 reutiliza el snapshot BTC ya calculado para el mismo timeframe, desde el refresh actual o el cache anterior. No abre nuevas requests.

### 3. NO_APLICA contado como NO_OPERAR

Especialistas fuera de su TF o sin cobertura devolvían `NO_OPERAR` con confianza 0. Eso no es evidencia contra una operación. Commit 28 lo normaliza a `ABSTAIN`. Un `NO_OPERAR` real con confianza/evidencia positiva sigue intacto.

### 4. Diagnóstico falso después del fallback

Un fallback ya es no-publicable. Sin embargo, Safety/ATR/quality vacíos del fallback podían producir simultáneamente:

`FALLBACK_GEOMETRY_NOT_PUBLISHABLE; PREMIUM_SAFETY_BELOW_75; ATR_STRESS`

Commit 28 deja de tratar Safety/ATR del fallback como causa adicional. Conserva esos valores como diagnóstico, pero muestra la causa primaria y el motivo de route/coverage.

### 5. Riesgo de deploy parcial

Commit 28 tiene entrypoint propio y tanto `Procfile` como `render.yaml` apuntan a:

`commit28_main_entrypoint:app`

Además, al arrancar verifica que la ABI de Futures contiene `execution_observations`. Si vuelve a existir una incompatibilidad, el deploy falla de forma visible en vez de quedar días funcionando con cero señales.

## Cambios implementados

### `futures_system.py`

- `calculate_entry_levels()` acepta nativamente `execution_observations=None`.
- reenvía el contexto completo al motor padre.
- preserva el pre-routing Multi-Activo antes de Entry/SL/TP.
- no modifica dirección, thresholds, Safety, RR ni leverage.

### `app.py`

- usa semántica `ABSTAIN` para `NO_OPERAR` con confianza 0.
- excluye `ABSTAIN/NO_APLICA` del conteo de votos.
- reutiliza contexto BTC same-TF ya existente para alts Futures.
- usa autoridad final Commit 28.
- mantiene fallback como `ANALYSIS_ONLY`.

### `worker_orchestration.py`

- un trabajador `ABSTAIN` queda como `NOT_APPLICABLE`, no como contradicción.

### `contextual_quality_commit28.py`

- unifica publicación Futures/Multi bajo los mismos hard guards históricos.
- `max(Q1..Q10)` sigue sin poder publicar.
- fallback sigue sin poder publicar.
- Safety/ATR/quality sólo se evalúan como causal blockers cuando existe geometría primaria.
- expone `route_reason` y `ROUTE_CONTEXT:<reason>` para distinguir falta de edge/cobertura de un bug de ejecución.

### `commit28_core.py`

Helpers puros sin I/O para:

- normalización de abstención;
- selección de contexto BTC same-TF desde cache.

### Deploy

`Procfile` y `render.yaml` arrancan `commit28_main_entrypoint:app` con:

- 1 worker;
- 2 gthreads;
- mismo timeout/max-request policy.

## Lo que NO cambia

- Spot signal logic.
- Safety Premium >= 75.
- RR 1.8..3.5.
- pérdida máxima al SL <= 8% del margen.
- ATR stress <= 25%.
- Entry Quality >= 65.
- SL Quality >= 60.
- TP Quality >= 55.
- closed candle.
- real-data requirement.
- Guardian.
- leverage policy.
- Alpha Decay.
- cantidad de workers.
- Supabase budgets.
- Groq budgets.
- universo LIVE de Champions.

## Por qué este commit tiene más probabilidad de resolver el síntoma

Commit 26/27 intentaban mejorar autoridad/calidad mientras todavía podía romperse la transición entre tesis y geometría. Commit 28 corrige primero el contrato de ejecución que los logs demostraron roto.

Antes:

`tesis -> calculate_entry_levels(TypeError) -> fallback -> Safety/ATR vacíos -> ANALYSIS_ONLY`

Ahora:

`tesis/ruta -> geometría primaria Entry/SL/TP -> execution safety -> contextual quality -> hard guards -> publicación`

Si la señal es mala, seguirá sin publicar. Si es buena y pertenece a una ruta LIVE validada, ya no debería morir por el `TypeError` ni por contexto BTC neutral artificial.

## Limitación honesta

Commit 28 no puede garantizar cuatro señales diarias. La cobertura LIVE validada sigue siendo escasa. Lo que sí debe garantizar es que la ausencia de señales no provenga de los dos bugs demostrados aquí. Si después del deploy el funnel muestra `NO_VALIDATED_LIVE_ROUTE` / `ROUTE_CONTEXT:*`, el siguiente trabajo es Research/OOS de nuevas rutas, no otra reparación de plumbing.
