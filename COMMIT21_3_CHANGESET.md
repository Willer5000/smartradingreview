# Commit 21.3 Fix

## Objetivo
Corregir el cuello de botella real observado en la UI: frontend 21.1 cacheado + tormenta de lecturas repetidas.

## Cambios
- Cache-bust y `no-store` para HTML operativo.
- Visuales single-flight/TTL 45 s.
- Cooldown de Futures para Activas/Vigentes/Confirmadas/Oportunidades/Perfil.
- Carriles escalonados.
- Mantiene intacto el núcleo 21.2 de CPQE context-complete, route engine y macro timeout 3 s.

## No cambia
- Safety 75.
- TP 55.
- SL 60.
- R/R 1.8–3.5.
- Número de workers/threads.
- Reglas de pérdida al SL/ATR.
