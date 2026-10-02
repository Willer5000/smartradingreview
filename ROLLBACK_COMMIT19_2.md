# Rollback Commit 19.2

Si el deploy 19.2 presenta una regresión operativa:

1. Restaurar los archivos del ZIP `COMMIT19_1_FINAL_GREEKS_ALL_MARKETS_FULL.zip` o del commit Git inmediatamente anterior.
2. Restaurar `Procfile` y `render.yaml` para apuntar nuevamente a `commit19_1_main_entrypoint:app`.
3. Hacer deploy limpio.
4. No borrar tablas, señales, ReviewTrader ni Alpha Decay: Commit 19.2 no crea schema nuevo.

No se requiere rollback SQL.
