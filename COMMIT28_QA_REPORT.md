# Commit 28 — QA Report

## Resultado

- Tests Commit 28 + regresión Commit 22–27: **49/49 PASS**.
- Tests específicos Commit 28: **7/7 PASS**.
- Compilación: **271 módulos Python / 0 errores**.
- `node --check`: `static/futures.js`, `static/script.js`, `static/chart_workspace.js` PASS.
- QA execution ABI 17.5.10.6: **13/13 PASS**.
- QA legacy 17.5.10.4: 14/15; el único fallo es una aserción obsoleta que espera que `templates/index.html` cargue `runtime_resilience_175104.js`. No está relacionado con Commit 28 y el template actual usa la cadena frontend posterior.

## Contratos probados

1. `execution_observations` existe en la firma Futures.
2. Futures lo reenvía al motor padre.
3. Multi pre-execution routing se preserva.
4. `NO_OPERAR` con confianza 0 -> `ABSTAIN`.
5. un `NO_OPERAR` real con confianza positiva no cambia.
6. contexto BTC same-TF usa cache actual primero y cache previo después.
7. fallback no puede publicar ni generar falsos blockers Safety/ATR.
8. geometría primaria sigue exigiendo Safety y ATR stress.
9. Procfile/render apuntan a Commit 28.

## Restricciones de recursos

Commit 28 añade:

- 0 requests de market data;
- 0 lecturas/escrituras Supabase;
- 0 llamadas Groq/LLM;
- 0 threads;
- 0 timers/polling;
- 0 caches nuevos.

El contexto BTC se reutiliza desde estructuras que ya existen en RAM.

## Límite del entorno de auditoría

No se pudo ejecutar un boot Flask/Gunicorn completo dentro del sandbox de esta conversación porque el entorno no trae Flask instalado y no tiene acceso de red a PyPI. Sí se hizo una simulación exacta `Commit27 base -> unzip Commit28 -> tests/compile`, que terminó 49/49 PASS y 271/271 módulos compilados. Render instalará las dependencias declaradas por el repositorio durante su build normal.
