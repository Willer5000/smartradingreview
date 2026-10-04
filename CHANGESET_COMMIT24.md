# COMMIT 24 — Change Set

Base exacta auditada: GitHub `Willer5000/smartradingreview` HEAD `1bba17bf51c693d75ef08e96bea6ddfe2452142d` (Commit 23.1 Fix).

## Archivos nuevos
- `commit24_repair_runtime.py`
- `commit24_main_entrypoint.py`
- `test_commit24_repair.py`

## Archivos reemplazados
- `Procfile`
- `render.yaml`

## No se reemplazan
- `app.py`
- `futures_system.py`
- `multiasset_system.py`
- `quality_9q_engine_21.py`

## Objetivo
1. Evaluar Q1..Q10 sobre la hipótesis que realmente llega a `_classify_futures_analysis_result()` en `app.py`.
2. Permitir autoridad One-of-Ten con Q >= 75 y guardas universales válidas.
3. Mantener Q10 no obligatorio.
4. Mantener Safety >= 65, SL loss <= 8%, ATR stress >0 y <=25%, stage explícito PUBLICATION_GATE y datos no sintéticos.
5. No crear dirección ni Entry/SL/TP nuevos; sólo reusar la geometría que `app.py` ya calculó.
6. Evitar threads de espera detrás del heavy lock; la UI queda coalescida en una sola solicitud pendiente.
7. Reciclar Gunicorn/Render con `os._exit(75)` sólo si existe UI pendiente y un background holder anómalo supera el timeout configurado.

## Validación local
`python -m py_compile commit24_repair_runtime.py commit24_main_entrypoint.py`

`python test_commit24_repair.py`

Resultado esperado: `ALL PASS`.
