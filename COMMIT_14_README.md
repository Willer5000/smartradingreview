# COMMIT 14 — LIQUIDATION HEATMAP REALITY CALIBRATION

Base exacta: Commit 13 `718f4af2ae713596c4eec4cbcb1dacff5d8683e0`.

## Objetivo
Mantener la lógica base del mapa existente, recalibrar la intensidad de sus zonas con datos públicos gratuitos y rediseñar su representación visual como heatmap tiempo×precio, sin exponer arquitectura interna al usuario.

## Cambios funcionales
- Mantiene `active_bins`, `frozen_bins`, geometría, lados, precios y leverage del mapa existente.
- Recalibra sólo los pesos relativos con Binance USD-M público (OI, long/short y taker buy/sell).
- Si Binance no responde, intenta Bybit público (OI + long/short).
- Caché RAM: 15 min cuando hay datos, 3 min en fallback.
- Máximo 2 calibraciones de red simultáneas; sin Supabase, Groq, API keys ni planes pagos.
- Fallo de APIs externas => factores 1.0 => comportamiento anterior.
- `data_type` sigue siendo `MODEL_ESTIMATE_NOT_OBSERVED`: no se venden estimaciones como liquidaciones futuras exactas.

## Visual
- Sustituye las franjas horizontales de ancho completo por un heatmap tiempo×precio.
- Cada zona nace en `created_at`; si fue alcanzada termina en `frozen_at`; si sigue activa llega a la vela actual.
- Intensidad: verde → amarillo → naranja → rojo.
- Mantiene las velas visibles encima del calor.
- Elimina el sufijo “M” de los pesos, porque la unidad es relativa y no millones reales.
- El frontend sólo muestra información técnica; no expone comités, especialistas ni traders internos.

## Rollback
Antes de modificar, el aplicador crea `.commit14_backup/`. Si todavía no hiciste commit, restaura esos tres archivos. Si ya hiciste Commit 14, `git revert <sha_commit14>` devuelve el sistema a Commit 13 en un único commit de reversión.
