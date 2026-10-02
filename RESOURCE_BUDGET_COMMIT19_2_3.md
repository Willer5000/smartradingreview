# Resource Budget — Commit 19.2.3

## Render
Sin cambios de capacidad:
- 1 Gunicorn worker
- 2 gthread
- MEMORY_JOB_START_LIMIT_MB = 200
- MEMORY_SOFT_LIMIT_MB = 220
- MEMORY_HARD_LIMIT_MB = 300

## Delta del release
`candle_close_authority_19_2_3.py`:
- 0 HTTP
- 0 Supabase adicional
- 0 LLM
- 0 threads
- estructuras de pocos bytes/timestamps.

Watermarks Spot:
- 4 claves (`4h`, `12h`, `1D`, `1W`) dentro del snapshot existente.

## Reducción de trabajo
Antes, cada refresh 4h podía recorrer 4h/12h/1D/1W en análisis actual + replay cerrado: hasta 24 análisis completos.
Con watermarks, un cierre 4h que no coincide con 12h/1D/1W procesa sólo 4h: hasta 6 análisis completos.

No se promete un ahorro mensual exacto porque depende de cachés, tráfico, proveedores y reinicios, pero el delta sólo reduce fan-out; no agrega tráfico.
