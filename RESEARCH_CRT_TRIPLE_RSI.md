# Research plan — CRT, Triple RSI y técnicas adicionales

## Respuesta de diseño
No se afirma que SmartTradingReview ya tenga todas las estrategias necesarias. Para aumentar cobertura en 5m/15m/30m pueden investigarse técnicas adicionales, pero deben demostrar **edge incremental**, no sólo producir más operaciones.

### CRT
Se modelará como setup, no como trader adicional. Hipótesis de investigación:
- definir parent range en HTF;
- raid/sweep de un extremo;
- reclaim/close dentro del rango;
- confirmación LTF mediante MSS/displacement/retest;
- target de liquidez opuesta.

Riesgo de duplicación: el sistema ya tiene Sweep/MSS/POI. CRT sólo merece promoción si la formalización del parent range mejora expectancy, timing o drawdown OOS.

### Triple RSI
No existe una única especificación universal. Deben testearse por separado:
- multi-length (p.ej. fast/mid/slow);
- multi-timeframe (execution + parent contexts).

Debe actuar como feature de momentum/timing. No puede crear una dirección por sí solo porque ya existe una familia RSI/momentum/divergencias y añadir votos correlacionados favorecería overfitting.

### Otras técnicas con posible información ortogonal
- Efficiency Ratio / trend-noise regime filter.
- Opening Range + VWAP por sesión.
- Failed Auction / Failed Breakout como subfamilia de reversal, si OOS demuestra que no es equivalente a Sweep Reversal.

## Backtest mínimo
- sin lookahead;
- datos de cierre disponibles en cada instante;
- costes/slippage;
- IS y OOS cronológicos;
- walk-forward;
- estabilidad de parámetros vecinos;
- resultados por activo, timeframe y régimen;
- comparación contra la familia existente;
- Shadow prospectivo antes de LIVE.

El objetivo no es garantizar señales cada día. El objetivo es aumentar la **oportunidad estadísticamente rentable** sin aumentar falsos positivos.
