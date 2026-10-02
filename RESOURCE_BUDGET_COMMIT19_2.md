# Resource Budget — Commit 19.2

Commit 19.2 no amplía el presupuesto de recursos respecto de 19.1 FINAL Greeks.

## Render RAM

- workers: 1
- threads: 2
- MEMORY_SOFT_LIMIT_MB: 220
- MEMORY_HARD_LIMIT_MB: 300
- MEMORY_JOB_START_LIMIT_MB: 200
- MEMORY_ANALYSIS_CACHE_KEEP: 1
- FUTURES_DATA_CACHE_MAX_ENTRIES: 8
- LOW_MEMORY_MODE: 1

El hard guard interno de 300 MB se mantiene 212 MB por debajo de la instancia de 512 MB. El nuevo scoring es cálculo local sobre estructuras ya existentes y no conserva datasets nuevos.

## Bandwidth / egress

Commit 19.2 añade **0 nuevas fuentes de red**.

Se preserva:

- MAIN_SUPABASE_DAILY_BUDGET_MB=12
- OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB=12
- OPTIONS_MM_CACHE_TTL_SECONDS=7200
- OPTIONS_MM_MAX_RESPONSE_BYTES=1572864
- OPTIONS_MM_MAX_CHAIN_ROWS=220
- proveedor observado de opciones sólo BTC/ETH
- sin polling de Greeks en navegador
- MULTIASSET_DEEP_LIMIT=2
- MULTIASSET_AUTO_DEEP_DAILY_MAX=12
- MULTIASSET_AI_AUTOMATIC_ENABLED=0

El nuevo fallback de Greeks reutiliza el precio que ya está en el gráfico antes de recurrir al endpoint existente, por lo que reduce la probabilidad de una consulta redundante; no crea otra frecuencia de actualización.

## Groq

- 0 llamadas nuevas automáticas por Commit 19.2.
- El Quant Synthesis y el rescore final son locales/determinísticos.

## Nota sobre el límite 5 GB mensual

El release no aumenta los presupuestos configurados y no añade fan-out de red. El consumo total real de Render también depende de tráfico del usuario, respuestas HTTP existentes, proveedores ya activos y reinicios; por eso el dashboard de Render sigue siendo la fuente final de consumo mensual. Commit 19.2 está diseñado para no aumentar materialmente ese consumo respecto de 19.1.
