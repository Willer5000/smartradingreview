# Rollback Commit 32.1 → Commit32 FINAL

Usa el ZIP de rollback y arrástralo sobre la raíz del repositorio con Replace/Overwrite.

Si Render tiene Start Command manual, restaura:

`gunicorn commit32_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 60 --max-requests-jitter 15`

Después confirma `/api/runtime/version` con versión Commit32.
