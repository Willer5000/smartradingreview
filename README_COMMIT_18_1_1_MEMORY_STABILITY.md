# Commit 18.1.1 — Memory Stability / Multi-Asset Free-Tier

Base: Commit 18 + 18.1 Multi UI.

## Problema observado
Render reinicia `smartradingreview` por superar el límite de memoria. La ruta Multi tenía un pico evitable: el GET liviano de display calculaba Trend/Momentum/Volatility/Volume/Structure/LiquidationHeatmap en el servidor y, casi al mismo tiempo, el POST `/api/multiasset/analyze` iniciaba el análisis pesado completo. Además, el POST volvía a pedir el mismo snapshot de display. En un proceso de 512 MB esto podía duplicar temporalmente el working set.

## Reparación
- Display Multi queda **OHLCV-only en servidor** (máx. 120 velas reales) + proxy de sentimiento barato.
- Los gráficos estándar siguen renderizándose en el navegador desde OHLCV.
- Structure/liquidation y capas ricas llegan sólo cuando termina el análisis pesado; el display no las recalcula en paralelo.
- `/api/multiasset/analyze` ya no vuelve a construir el snapshot gráfico después de iniciar el heavy job.
- Cache Multi Display del servidor: 1 celda actual, TTL 45 s.
- Cache UI Futures/Multi rica: 1 payload.
- El memory shed elimina también payloads UI recreables.
- En LOW_MEMORY_MODE: soft 220 MB, hard 300 MB, inicio de heavy <=200 MB, cache análisis 1.
- `FREE_RUNTIME_MAX_THREADS=10` en `render.yaml`.
- No se modifica Strategy Bank, Entry, SL, TP, leverage, Safety, Guardian, Research ni autoridad de señal.

## Archivos a reemplazar
1. `app.py`
2. `static/script.js` (mismo runtime 18.1, incluido para reemplazo consistente)
3. `templates/index.html`
4. `render.yaml`

## Implementación
Arrastrar los 4 archivos respetando `static/` y `templates/`, sobrescribir y hacer un único deploy.

Commit sugerido:
`Commit 18.1.1 - memory stability multiasset free tier`

Después del deploy:
1. Ctrl+F5.
2. Abrir Multi-Activo CL 4h.
3. El gráfico central debe aparecer sin esperar el heavy analysis.
4. Esperar el análisis rico. Si el RSS ya está cerca del límite, el sistema debe diferir el trabajo en vez de reiniciar el proceso.
5. En Render > Metrics verificar Memory Usage/RSS durante 20–30 min de uso. Objetivo operativo: mantener margen amplio frente a 512 MB; un pico aislado por encima de 300–350 MB debe investigarse antes de ampliar trabajo pesado.

## Importante
Este hotfix prioriza estabilidad. El mapa de liquidaciones/estructura del display inicial puede aparecer después, con el payload pesado, en vez de calcularse simultáneamente con el gráfico. Es intencional para evitar OOM. No elimina esas capas del análisis completo.
