# Resource Budget — Commit 19.2.2

## RAM
- Render target: 512 MB.
- 1 Gunicorn worker / 2 gthread.
- soft guard: 220 MB.
- hard guard: 300 MB.
- heavy job start guard: 200 MB.
- un único `_HEAVY_ANALYSIS_LOCK`.

19.2.2 no aumenta heavy concurrency. Corrige un guard de `active_count()` que confundía daemons permanentes con jobs pesados. El conteo de threads permanece como alerta de presión transitoria combinada con RSS.

## Bandwidth
No se añaden fuentes ni polling.

Mejora neta: `/api/multiasset/opportunities`, `/api/multiasset/correlation` y el router de contexto AI ya no llaman `scan_opportunities()` desde requests HTTP. El provider scan queda exclusivamente en background, dentro de las cuotas existentes.

Se preservan:
- MULTIASSET_AUTO_DEEP_DAILY_MAX existente.
- MULTIASSET_DEEP_LIMIT=2.
- opciones provider budget 12 MB/día.
- Main Supabase budget existente.

Esto reduce el riesgo de exceder 5 GB/mes respecto de 19.2.1; no puede garantizar por sí solo el consumo total de Render porque éste también depende de tráfico HTTP y otros endpoints existentes.
