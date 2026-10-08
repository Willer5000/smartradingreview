# Auditoría Commit 32.2

## Causas confirmadas
- Strong thesis -> ABI failure -> no primary geometry.
- Runtime observado contiene autoridad/telemetría legacy y no prueba C32.1 activo.
- Razones `PREMIUM_SAFETY_BELOW_75` son incompatibles con la política moderna y deben tratarse como stale.
- Fallback geometry domina diagnósticos, por lo que no corresponde bajar Safety para aumentar frecuencia.
- Multi comparte la falla ABI.

## Causas no confirmadas
- No se atribuye la ausencia de señales a falta de RSI/MACD/traders.
- El Escéptico registra objeciones pero el flujo moderno las etiqueta no vinculantes; no se considera causa terminal por sí sola.

## Riesgo estadístico
Agregar nuevas técnicas sin OOS puede aumentar overfitting. Por eso CRT/Triple RSI sólo obtienen autoridad cuando el backtest reproducible pasa el contrato predefinido.
