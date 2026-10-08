# Research posterior a Commit 33.3 — temporalidad mínima 30m

Este documento NO activa ninguna estrategia en producción.

Familias a estudiar:

1. CRT / Candle Range Theory — parent range, sweep, reclaim y liquidez opuesta.
2. Failed Auction / Failed Breakout — ruptura fallida, regreso a rango y displacement contrario.
3. Opening Range + VWAP — contexto de sesión y aceptación/rechazo de valor.
4. Triple RSI — feature de timing/momentum, no autoridad independiente.
5. Efficiency Ratio / Noise filter — tendencia eficiente vs chop.
6. Volatility Compression / Release — squeeze/compresión seguida de expansión.

## Protocolo mínimo

- Timeframe mínimo: 30m.
- Split cronológico IS/OOS; nunca random shuffle.
- Parámetros congelados antes de OOS.
- Costes y slippage incluidos.
- Entrada sólo después de la información disponible al cierre que genera el setup.
- Reportar N, expectancy R, PF, MaxDD, win rate, MAE/MFE y estabilidad por régimen.
- Comparar cada nueva técnica contra las familias actuales para demostrar **valor incremental**, no sólo rentabilidad aislada.

La promoción LIVE debe utilizar el gobierno acordado por el proyecto, pero no se declarará PASS sin datos históricos reales ejecutados.


## Herramientas incluidas

El ZIP incluye `strategies_commit33_3.py` y `backtest_commit33_3.py`. El runner espera CSV 30m con `timestamp,open,high,low,close,volume`, usa split 70/30 cronológico, entrada en la apertura de la vela siguiente y regla conservadora SL-first cuando TP y SL aparecen en una misma vela.

`BACKTEST_COMMIT33_3_STATUS.json` queda explícitamente en `real_market_backtest_executed=false` porque no se adjuntó histórico profundo 30m y este runtime no tiene salida de red al proveedor. No se declara rentabilidad ni se concede autoridad LIVE sin ejecutar datos reales.
