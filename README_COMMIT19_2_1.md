# Commit 19.2.1 — Root Cause Quality Recovery

Release incremental sobre 19.2.

## Objetivos

1. Multi-Activo debe razonar como Multi antes de formar la tesis.
2. El análisis profundo debe cubrir la última vela cerrada aunque Render reinicie fuera de una ventana exacta.
3. Las rutas Multi no deben quedar vacías únicamente por pérdida de caché en un recycle de Gunicorn.
4. Una geometría nativa correctamente reparada no debe depender de una whitelist histórica ajena a su calidad real.
5. Todos los activos deben mostrar Greeks Black-Scholes numéricos cuando exista precio/volatilidad, sin inventar Open Interest/dealer walls.
6. Mantener los umbrales Premium y los límites de RAM/bandwidth.

## Cambios de producción

- `app.py`: pre-market hook, source-candle scheduler Multi, snapshot local compacto, recovery authority 19.2.1 y rescore de geometría reparada.
- `multiasset_system.py`: contexto por clase de activo antes de los nueve especialistas.
- `live_quant_synthesis_commit19_1.py`: consume contexto Multi antes de la tesis; preferencia de familia sólo como bonus contextual.
- `market_maker_math.py`: Delta/Gamma/Vega/Theta y niveles de modelo numéricos para modo teórico.
- `static/market_maker_frontend.js`: Vega local + resumen teórico universal + labels honestos para métricas que requieren OI.
- `templates/index.html`: resumen ATM incluye Vega.
- `commit19_2_1_main_entrypoint.py`, `Procfile`, `render.yaml`: identidad de release.

## Calidad preservada

No se rebajaron Safety, R/R, Entry, SL, TP ni Leverage V6. Champions mantienen paridad. Alpha Decay 8+8 continúa.

## QA

- 19.2.1: 49/49 PASS
- 19.2 regression: 28/28 PASS
- 19.1 regression: 13/13 PASS
- 17.5.11R.1: 18/18 PASS
- compileall: PASS
- JS syntax: PASS
- Champion backtest: PASS
