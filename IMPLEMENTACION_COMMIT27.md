# IMPLEMENTACIÓN COMMIT 27 — DRAG & REPLACE

## Archivos de producción completos incluidos

- `app.py` — núcleo completo; autoridad final unificada Futures + Multi.
- `champion_registry_commit19.py` — router Champion con paridad del cohort 30m y celdas exactas.
- `quality_9q_engine_21.py` — Q paralelos diagnósticos; Q1..Q8 calidad, Q9 governance diagnóstico para Commit 27.
- `contextual_quality_commit27.py` — núcleo contextual y hard publication contract.
- `commit27_main_entrypoint.py` — entrypoint de producción.
- `render.yaml` y `Procfile` — arrancan Commit 27 sin cambiar worker/thread budget.

También se incluyen tests, backtest reproducible, resultados y documentación.

## Instalación

1. Descargar y descomprimir `SMARTRADINGREVIEW_COMMIT27_DEEP_CORE_DRAG_REPLACE.zip`.
2. Arrastrar **todo el contenido de la carpeta descomprimida a la raíz** del repositorio `smartradingreview` en VS Code Web/GitHub y aceptar Replace.
3. Commit/push a `main`.
4. Render debe desplegar con `commit27_main_entrypoint:app`.
5. Confirmar en logs: `COMMIT27_UNIFIED_CONTEXTUAL_SIGNAL_CORE_V1`.

No es necesario editar líneas ni copiar fragmentos manualmente.

## Validación LIVE recomendada

En el primer ciclo completo de velas cerradas revisar:

- que `signal_engineering_funnel` informe blocker exacto;
- que un fallback tenga siempre `ANALYSIS_ONLY`;
- que un Champion 30m llegue a post-geometría antes de ser juzgado por MSS/Displacement;
- que `max(Q1..Q10)` nunca aparezca como source de publicación;
- que Multi 1h/4h sin OOS aparezca como Shadow, no como Premium;
- que Telegram reciba sólo `EXECUTABLE_SIGNAL`.

KPI de 7–14 días (no cuota):

- celdas evaluadas;
- hipótesis direccionales;
- geometrías primarias vs fallback;
- candidatos con route authority;
- quality-ready;
- hard blockers;
- Premium/día;
- outcomes y expectancy por route × asset class × TF × direction × regime × volatility.

## Rollback

Usar `SMARTRADINGREVIEW_COMMIT27_RECOVERY_COMMIT25.zip`, reemplazar sus archivos en raíz y desplegar. Los archivos nuevos Commit 27 pueden permanecer inertes porque el `render.yaml`/`Procfile` restaurado vuelve a arrancar Commit 25; para rollback limpio pueden eliminarse después.
