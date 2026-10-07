# Implementación — Commit 32 FINAL

## Instalación en un único commit
1. Descomprime `SMARTRADINGREVIEW_COMMIT32_FINAL_ROOT_CAUSE_RECOVERY_DRAG_REPLACE.zip`.
2. Abre la raíz del repositorio `smartradingreview`, rama `main`.
3. Arrastra **el contenido** del ZIP a la raíz y elige Replace/Overwrite. No crees una carpeta Commit32.
4. Confirma que existan:
   - `commit32_main_entrypoint.py`
   - `commit32_runtime_patch.py`
   - `commit32_spot_market_authority.py`
   - `commit32_execution_policy.py`
5. Confirma que `Procfile` y `render.yaml` apunten a `commit32_main_entrypoint:app`.
6. Haz un único commit recomendado:
   `Commit 32 - final root cause recovery spot market authority fast execution and RAM`
7. Si Render tiene Start Command manual, usa:
   `gunicorn commit32_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 60 --max-requests-jitter 15`
8. No modifiques manualmente Safety, RR, ADX, ATR, workers ni memoria después del deploy.

## Verificación
- `/api/runtime/version` debe reportar `COMMIT32_ROOT_CAUSE_RECOVERY_V2` y `commit32_main_entrypoint:app`.
- `/api/commit32/status` (autenticado) debe mostrar RSS, funnel, Guardian untouched y `COMMIT32_PUBLICATION_AUDIT_V2`.
- Logs de boot deben indicar SPOT global market signal authority y RAM checkpoints activos.
- No debe aparecer Commit32 como "Portfolio Authority".
- Guardian debe seguir funcionando por usuario/temporalidad sin cambios.

## OOM
Si una celda pesada supera el margen configurado, debe preferirse un `RESOURCE_PRESSURE_ABORT_COMMIT32:<stage>` a un reinicio completo del worker.

## Rollback
Usa el ZIP `SMARTRADINGREVIEW_COMMIT32_FINAL_RECOVERY_TO_COMMIT31_DRAG_REPLACE.zip` y restaura Start Command a `commit31_main_entrypoint:app`.
