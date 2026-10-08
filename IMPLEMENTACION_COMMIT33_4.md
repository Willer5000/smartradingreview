# Implementación Commit 33.4

## Forma recomendada
Este paquete es un repositorio limpio, no un parche. Para evitar que sobrevivan archivos borrados:
1. Guarda una copia de tu repo actual como rollback.
2. Extrae `SMARTRADINGREVIEW_COMMIT33_4_CANONICAL_CORE.zip` en una carpeta nueva.
3. Conserva tu `.git`/credenciales locales si trabajas desde un clon y sustituye el contenido versionado del working tree por el contenido extraído.
4. Verifica que `Procfile` y `render.yaml` arranquen `app:app`.
5. Commit sugerido: `Commit 33.4 - canonical core signal recovery and multiasset charts`.
6. Despliega una sola vez.

## Verificación post-deploy
- `/api/runtime/version` debe identificar `COMMIT33_4_CANONICAL_CORE_V1` y `app:app`.
- Los logs no deben contener `No module named 'commit28_core'`, `commit29_core`, `commit30_core` o `premium_path_expansion_20`.
- No debe reaparecer `execution_market_type ... not associated with a value`.
- Multi-Activo debe devolver OHLCV por `/api/multiasset/display` sin lanzar el análisis pesado.
- Los candidatos fuertes deben poder alcanzar Entry/SL/TP/Safety incluso sin una Champion exacta; la clasificación final sigue bloqueando fallback, Safety incompleto y hard-risk failures.

## No hacer
- no restaurar módulos `commit28/29/30_core`;
- no bajar Safety manualmente;
- no quitar ATR stress como riesgo cuando sí está medido;
- no convertir geometría fallback en Premium;
- no añadir un nuevo overlay/runtime patch.
