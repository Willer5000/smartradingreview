# Commit 21 — Premium Strategy Route Engine

## Archivos de producción
- premium_path_expansion_20.py (compatibility overlay + Commit 21 engine)
- commit21_main_entrypoint.py
- static/futures.js
- Procfile
- render.yaml

## Qué resuelve
- Convierte PPE en un verdadero Strategy Route Engine, no en un comparador de geometría solamente.
- Prueba hasta 2 familias alternativas ya elegibles en el Strategy Bank para la misma celda exacta.
- Re-ejecuta la geometría completa con la familia alternativa.
- Sólo acepta la alternativa si el pipeline existente retorna `publication_eligible=true`.
- Mantiene el baseline si ninguna alternativa alcanza Premium.
- Mantiene el contrato Multi-Activo Saved Signals de Commit 20.2.

## Contratos preservados
- Safety Premium = 75
- TP Quality = 55
- SL Quality = 60
- R/R = 1.8–3.5
- Loss at SL y ATR stress sin relajación
- CPQE sin cambio de thresholds
- Alpha Decay sin cambios
- 1 worker / 2 threads
- sin nuevas APIs, workers, threads o polling
- fallback geometry no tiene autoridad Premium

## Control de overfitting
- No hay calibración online de parámetros.
- No hay optimización por PnL live.
- No hay selección por resultado del último cierre.
- Sólo se reutilizan playbooks ya declarados por `default_strategy_bank`.
- Se exige coincidencia de régimen/volatilidad y familias funcionales.
- El máximo de dos alternativas es fijo.

## Diagnóstico
`premium_route_engine_21` queda dentro del payload con:
- ruta baseline
- rutas intentadas
- blockers de cada ruta
- ruta Premium seleccionada, si existe
- indicador de si se promovió una alternativa
