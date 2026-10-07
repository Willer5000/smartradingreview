# Rollback Commit32 FINAL -> Commit31

El rollback sólo necesita devolver la autoridad WSGI/configuración a Commit31. Los módulos `commit32_*` pueden permanecer dormidos en el repositorio: si `Procfile`, `render.yaml` y el Start Command apuntan a `commit31_main_entrypoint:app`, no se instalan sus monkeypatches.

Usa el ZIP de rollback entregado junto al paquete principal.
