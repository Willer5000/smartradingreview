# Backtest / Validación — Commit 30 Propuesta 3

## Objetivo estadístico
Commit 30 corrige un falso negativo de **detección contextual**. No declara una estrategia 1h nueva como rentable. El impulso 1h es contexto; la publicación LIVE continúa en las rutas que ya tienen autoridad estadística y hard guards.

## 1. Guardrail histórico 1h
El histórico agregado Futures 1h disponible es negativo:
- resolved: 120
- TP / SL: 11 / 109
- WR: 9.17%
- gross expectancy proxy: -0.642R
- avg modeled net R: -0.907R

El challenger histórico `LIQUIDITY_SWEEP_MSS_POI` 1h fue sólo marginalmente positivo (N=50, E=+0.089R, PF=1.134), pero no existe un split limpio IS/Selection/OOS del nuevo patrón de impulso. Por eso **no se promueve 1h directamente a Premium**.

## 2. Ruta LIVE que recibe el puente 1h→30m
No se modifica ningún threshold del Champion 30m. Reejecución de `BACKTEST_ROWS_17_5_10_PROFITABILITY.csv`:

| Split | N | Net R | Expectancy | PF | MaxDD |
|---|---:|---:|---:|---:|---:|
| IS/DEV | 11 | +1.702 | +0.1547R | 1.254 | 2.236R |
| OOS/Holdout | 4 | +3.928 | +0.9820R | 4.513 | 1.118R |
| Combined | 15 | +5.630 | +0.3753R | 1.719 | 2.236R |

El OOS es pequeño (N=4); es evidencia positiva observada, no garantía futura.

## 3. Replay causal del incidente BTC 1h
Fixture tomado de producción: dirección bearish, ADX 17.7, +DI 9.5, -DI 42.2, RSI 23.9, volumen relativo 2.82x, estructura bajista con OB/FVG/sweeps. En el momento de la tesis, el contexto MTF operacional no estaba disponible como familia independiente.

**Commit 29:** `NO_OPERAR`, calidad 56.0, familias ['structure', 'momentum', 'volume'].

**Commit 30:** `SHORT`, calidad 98.5, familias ['trend', 'structure', 'momentum', 'volume'], régimen `DIRECTIONAL_IMPULSE_BEAR`.

La mejora no agrega `directional_impulse` como una quinta familia. Recupera la familia `trend` existente cuando DI dominante + momentum + volumen/estructura muestran desplazamiento y ADX todavía rezaga.

## 4. Contrato anti-overfitting
El detector usa la misma regla para LONG/SHORT, cualquier símbolo y cualquier TF:
- DI dominante >=25;
- dominancia relativa clara: spread >=15 o ratio >=2.0;
- momentum alineado;
- al menos una corroboración independiente: volumen o estructura.

No existe excepción para BTC, el día del evento, una hora específica ni un activo. El detector **no puede publicar**. Un evento 1h sólo pone al frente de la cola las celdas 30m que ya pertenecen al Champion validado. Si la celda 30m no pasa su contrato, geometría, Safety, RR o ATR, no hay señal.

## 5. Cola causal y recursos
El evento 1h se conserva hasta 90 minutos para cubrir el caso donde el 30m se había analizado segundos antes del cierre 1h. La cola está limitada a 12 entradas y consume un solo heavy job por ciclo. No crea threads, polling, requests, Supabase ni Groq adicionales.
