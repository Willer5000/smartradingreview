# RESOURCE BUDGET — COMMIT 18

## Main / Multi Display Lane
- 1 símbolo × 1 TF por solicitud.
- Máximo 180 velas.
- TTL servidor: 60 s.
- LRU: máximo 4 celdas.
- 0 llamadas IA.
- 0 escrituras Supabase.
- 0 escaneo de las 21 celdas Multi.
- Reutiliza el mismo cache ligero cuando el POST heavy llega inmediatamente después.
- Se elimina la petición HTTP separada a `static/runtime_resilience_175104.js`; su lógica se integra en `script.js`.

## Research
Commit 18-R no aumenta el presupuesto normal de Supabase:
- Execution: 4 MB/día.
- Risk: 4 MB/día.
- Strategy: 4 MB/día.
- Traders: 4 MB/día.
- Validation: 16 MB/día.
- Total normal: 32 MB/día ≈ 0.94 GiB/30 días.
- Reserva crítica existente: máx. 2 MB por proceso para recovery/governance, sólo tras agotar presupuesto normal.
- A partir de 80% se pausan nuevas lecturas bulk de source; governance pequeña puede continuar.
- `RESEARCH_MAX_SOURCE_ROWS`: 900 (antes 1200).
- `RESEARCH_PAGE_SIZE`: 150 (antes 200).
- caches causales reducidas en render.yaml.

Esto reduce la probabilidad de exceder 5 GB de outbound, pero ningún ZIP puede garantizar el consumo mensual real: depende también de market-data externos, cantidad de reinicios y tráfico de usuarios. Debe verificarse en Render después del deploy.
