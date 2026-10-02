# Rollback Commit 19.2.1

Si el deploy 19.2.1 presenta un fallo operativo:

1. Revertir el commit 19.2.1 en GitHub, o restaurar el ZIP FULL/PATCH del Commit 19.2 anterior.
2. Confirmar que Procfile/render.yaml vuelven a `commit19_2_main_entrypoint:app`.
3. No borrar tablas ni datos: 19.2.1 no requiere migración SQL.
4. El archivo `/tmp/smartradingreview_multi_cache_19_2_1.json` es efímero y puede ignorarse; un restart lo recreará cuando haya análisis.

El rollback no requiere revertir Supabase ni cambiar secretos.
