# Rollback Commit 28

El ZIP de recovery restaura los archivos modificados a la versión base de Commit 27 y vuelve a arrancar `commit27_main_entrypoint:app`.

Los archivos nuevos `commit28_main_entrypoint.py`, `commit28_core.py`, `contextual_quality_commit28.py` y `test_commit28_core_recovery.py` pueden permanecer en el repositorio: al restaurar Procfile/render quedan inactivos.
