# IMPLEMENTACIÓN COMMIT 26 — DRAG & REPLACE

## Archivos que reemplaza/agrega

Reemplazar en la raíz:
- `champion_registry_commit19.py`
- `render.yaml`
- `Procfile`

Agregar en la raíz:
- `commit26_main_entrypoint.py`
- `test_commit26_causal_preentry.py`
- `backtest_commit26_proposal2.py`
- `BACKTEST_COMMIT26_PROPOSAL2.json`
- `BACKTEST_COMMIT26_PROPOSAL2.md`
- `AUDITORIA_COMMIT26_PROPUESTA_PROFUNDA2.md`

## Despliegue

1. Descomprimir el ZIP.
2. Arrastrar todos los archivos a la raíz del repositorio en VS Code Web y aceptar Replace.
3. Commit a `main`.
4. Render debe desplegar automáticamente.
5. Confirmar en Render que el deploy LIVE corresponde al nuevo commit y no a `bdd6866`.
6. En logs debe aparecer `COMMIT26_CAUSAL_PREENTRY_RECOVERY_PROPOSAL2_V1`.

## Rollback inmediato

- Restaurar `champion_registry_commit19.py`, `render.yaml` y `Procfile` de Commit 25; o
- como kill-switch de la reparación causal, poner `COMMIT26_CAUSAL_PREENTRY_ENABLED=0` y redeploy. Esta opción vuelve al trigger legacy y probablemente reduce otra vez la frecuencia 30m.

## Qué NO cambia

- `app.py`
- Safety
- RR
- Entry/SL/TP engine
- leverage policy
- closed-candle authority
- Telegram publication gate
- Spot logic
- Supabase schema
- Q thresholds
- workers/threads
- polling
- Groq calls
