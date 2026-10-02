# Rollback Commit 19.2.2

Si el release introduce una regresión:
1. revertir los archivos del patch a Commit 19.2.1;
2. restaurar Procfile/render.yaml a `commit19_2_1_main_entrypoint:app`;
3. redeploy.

No hay migración SQL que revertir.
