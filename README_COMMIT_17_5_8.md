# Commit 17.5.8 — Backtest Prior + Quality Opportunity Recovery

## Archivos a reemplazar/agregar

Arrastrar juntos a VSCode:

- `app.py` — reemplazar.
- `execution_specialist_committees.py` — reemplazar.
- `preliminary_backtest_prior.py` — archivo nuevo.

Los demás archivos del ZIP son QA/documentación.

## Qué hace

- Incorpora evidencia preliminar por familia/celda.
- Incorpora prior suave de Entry basado en Liquidity/Sweep/MSS/POI.
- Mantiene SL estructural y hard guard de zona de reacción.
- No comprime TP globalmente.
- Entrega los priors al Learning Scientist/ReviewTrader context.
- Prioriza en Futures el orden de análisis de celdas con evidencia, sin excluir otras.
- Conserva correcciones 17.5.6/17.5.7 de Multi-Activo, leverage y visibilidad.
- No añade cupo de Telegram.

## Instalación

1. Crear backup de los tres archivos si ya existe el nuevo módulo.
2. Arrastrar `app.py`, `execution_specialist_committees.py` y `preliminary_backtest_prior.py`.
3. Ejecutar:

```bash
python -m py_compile app.py execution_specialist_committees.py preliminary_backtest_prior.py
python qa_commit17_5_8_backtest_prior.py
python qa_commit17_5_8_inherited_execution.py
```

Resultados esperados: 17/17 y 20/20.

## Verificación post-deploy

1. Abrir Futures y Multi-Activo.
2. Consultar el funnel autenticado `/api/diagnostics/signal-funnel?market=futures` y `market=multiasset`.
3. Consultar, por ejemplo:
   `/api/diagnostics/backtest-prior?market=futures&symbol=SOL-USDT&timeframe=2h&action=LONG&family=RSI_TREND`
4. Confirmar que no aparecen señales x1-x3 como premium.
5. Confirmar que Telegram sólo envía señales realmente `EXECUTABLE_SIGNAL` y no tiene límite diario de cantidad.

## Nota

17.5.8 no garantiza que aparezca una señal si el mercado no cumple calidad. Su objetivo es que el sistema analice antes las celdas con evidencia y que Entry/estrategia utilicen el backtest como prior acotado, sin relajar los filtros que controlan la calidad.
