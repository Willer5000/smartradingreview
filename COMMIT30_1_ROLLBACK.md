# Rollback Commit 30.1 → Commit 30

Usa `SMARTRADINGREVIEW_COMMIT30_1_RECOVERY_TO_COMMIT30.zip`, arrastra los archivos a la raíz y reemplaza. Si Render usa Start Command manual, restáuralo a `commit30_main_entrypoint:app`.

Los archivos nuevos `commit30_1_core.py` y `commit30_1_main_entrypoint.py` pueden permanecer sin uso si el entrypoint vuelve a Commit30; no son importados por el proceso de rollback.
