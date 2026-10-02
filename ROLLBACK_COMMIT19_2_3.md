# Rollback 19.2.3

1. Restaurar los archivos del Commit 19.2.2.
2. `Procfile` y `render.yaml` deben volver a `commit19_2_2_main_entrypoint:app`.
3. No hay migración SQL que revertir.
4. Los watermarks adicionales del snapshot son claves JSON compatibles e inocuas para 19.2.2.
