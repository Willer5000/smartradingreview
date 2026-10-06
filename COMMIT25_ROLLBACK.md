# Rollback Commit 25

Usa `SMARTRADINGREVIEW_COMMIT25_RECOVERY.zip` y reemplaza sus archivos en la raíz del repositorio.

El recovery:
- vuelve el start command a `commit24_main_entrypoint:app`;
- restaura los archivos existentes modificados a las versiones del ZIP original entregado;
- fija `COMMIT25_CONTEXTUAL_AUTHORITY_ENABLED=0` en el `render.yaml` de recuperación, de modo que los módulos nuevos que puedan quedar en GitHub no obtengan autoridad;
- no toca Supabase ni requiere SQL.

Después del rollback, commit/push y verificar que Render arranca con Commit 24.
