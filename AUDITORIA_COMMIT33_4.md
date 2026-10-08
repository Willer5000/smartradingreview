# Auditoría Commit 33.4 — Canonical Core

## Veredicto
La ausencia de señales no era explicable por un único umbral. Después de la limpieza de 33.3, `app.py` conservaba referencias directas a módulos eliminados (`commit28_core`, `commit29_core`, `commit30_core`, `premium_path_expansion_20`) y la ruta de niveles tenía un `execution_market_type` no inicializado en una rama válida. El resultado era pérdida de contexto, fallo de los nueve especialistas, fallo de correlación y degradación a fallback/ANALYSIS_ONLY.

## Causas raíz corregidas
1. Dependencias históricas vivas después de borrar sus archivos.
2. Varias generaciones de pipeline/calidad/safety coexistiendo conceptualmente.
3. OOS/ruta validada actuando demasiado pronto como veto de generación de candidato.
4. Safety interpretando métricas ausentes como valores cero reales (por ejemplo ATR stress), generando falsos bloqueos.
5. `ENTRY_MISSING` podía aparecer por plumbing del score aunque hubiera Entry real.
6. Multi-Activo display intentaba una descarga pesada de hasta 15 s antes del fallback, mientras el navegador abortaba a los 10 s.
7. `execution_market_type` se inicializaba sólo en una rama y podía producir `UnboundLocalError`.

## Arquitectura 33.4
`Market Data -> market_context -> Operational Intelligence -> pipeline_integrity -> Strategy/Setup -> Entry Committee -> SL Committee -> TP Committee -> safety_profiles -> publication_quality -> Guardian`

No existe un `install_commit33_4`, monkeypatch, wrapper ABI ni main entrypoint por commit. El único arranque es `app:app`.

## Frecuencia sin bajar calidad
La frecuencia se amplía en el núcleo permitiendo que un setup técnico fuerte, cerrado y reproducible llegue a geometría y Safety aunque no posea una ruta histórica exacta para esa celda. La publicación puede usar `CORE_TECHNICAL_ROUTE` sólo cuando:
- el candidato procede del pipeline canónico;
- el setup no es ambiguo;
- existe soporte independiente suficiente;
- Entry/SL/TP son geometría primaria, no fallback;
- Safety especializado está listo;
- RR y hard risk guards pasan;
- la vela está cerrada y es real.

Una ruta histórica validada sigue teniendo prioridad. `CORE_TECHNICAL_ROUTE` NO se presenta como OOS validado y debe medirse con ReviewTrader/forward data.

## Multi-Activo
`/api/multiasset/display` es una ruta visual ligera. Reutiliza OHLCV cacheado y, si falta, usa el fetch corto del router. Nunca inicia el análisis pesado. El navegador calcula los indicadores desde OHLCV, por lo que los gráficos dejan de depender de que termine el comité pesado.

## Eliminaciones
Se retiraron entrypoints/runtimes históricos sin autoridad y tests que verificaban exclusivamente módulos ya eliminados. Los backtests/documentos históricos restantes no participan del runtime.
