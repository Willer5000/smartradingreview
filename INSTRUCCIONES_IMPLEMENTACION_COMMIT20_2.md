# Implementación Commit 20.2

Reemplaza/arrastra estos archivos: `app.py`, `premium_path_expansion_20.py`, `commit20_2_main_entrypoint.py`, `static/futures.js`, `templates/index.html`, `Procfile`, `render.yaml`.

Ejecuta una vez `schema_commit20_2_runtime_saved_signals.sql` en Supabase.

### Render Start Command
`gunicorn commit20_2_main_entrypoint:app --timeout 180 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 30 --max-requests 120 --max-requests-jitter 20`

Aun si el Dashboard de Render mantiene `gunicorn app:app`, el `app.py` incluido instala el overlay 20.2 de forma idempotente.

### Verificación
`/health` debe mostrar `COMMIT20_2_PREMIUM_PATH_EXPANSION_RUNTIME_FIX_V1`.
Memoria aproximada: start 215 MB / soft 235 MB / hard 300 MB.

En Multi-Activo, abrir una Saved Signal debe mostrar velas, Entry, SL, TP, precio actual, ficha técnica y revisión. No debe aparecer `Sin datos de velas Futures perpetuos`.
