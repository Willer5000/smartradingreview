# Implementación Commit 32.2

1. Descomprime el ZIP en la raíz de `smartradingreview` y usa Replace/Overwrite.
2. Un solo commit recomendado: `Commit 32.2 - quality signal recovery ABI policy truth and strategy governance`.
3. En Render, si existe Start Command manual, usar:
   `gunicorn commit32_2_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 60 --max-requests-jitter 15`
4. Tras desplegar, abrir `/api/runtime/version`. Debe indicar `COMMIT32_2_RECOVERY_V1`, entrypoint C32.2 y ABI Futures/Multi OK.
5. Abrir `/health`. Si ABI no está correcto responde 503 en vez de dejar un runtime parcialmente roto.
6. No modificar manualmente Safety/RR/ATR/ADX después del despliegue.

## Criterio de rollback
Usar rollback a C32.1 si C32.2 no arranca, si `/health` retorna 503 de forma persistente tras verificar el Start Command, o si aparece una regresión ajena al bloqueo diagnosticado.
