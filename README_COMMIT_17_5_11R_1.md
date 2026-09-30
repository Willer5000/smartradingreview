# COMMIT 17.5.11R.1 — Coverage Matrix + Validated Context Routing + Execution Geometry

**Base real a reemplazar:** Commit 17.5.10.9 desplegado.  
**IMPORTANTE:** el usuario NO desplegó 17.5.11 ni 17.5.11R. Este ZIP **sustituye ambos**. Aplicar **solamente 17.5.11R.1** en un único commit/deploy.

## Objetivo

Resolver conjuntamente, sin fabricar trades:

1. oportunidades perdidas por frontend/caché/orquestación/gates invisibles;
2. cobertura insuficientemente gobernada por contexto;
3. mismatch entre la familia que Research validó y la familia geométrica que recibía Entry/SL/TP;
4. Entry/SL incorrectos, en especial SL dentro de una zona válida de reacción;
5. duplicados Telegram;
6. Multi-Activo sin gráficos/diagnósticos fiables.

La política sigue siendo:

> **Asertivo pero cauto, precavido pero no tímido y sobre todo rentable.**

No existe cuota de señales/día y no se baja Safety ni R/R para producir frecuencia.

---

## Qué agrega R.1 respecto a 17.5.11R

### 1. Matriz de cobertura real

Se generó `COVERAGE_MATRIX_17_5_11R1.csv` con **4,200 filas** de activo × TF × dirección × régimen × volatilidad para Futures cripto y Multi-Activo.

Distingue:

- exact route validada;
- exact route SHADOW;
- contexto cubierto sólo por Strategy Bank sin alpha exacto validado;
- ruta Entry 30m condicionada a Liquidity Sweep + MSS/BOS/Displacement + POI.

Esto permite auditar `NO_STRATEGY_FOR_CONTEXT` sin confundirlo con “mercado sin oportunidad”.

### 2. Sólo 3 estrategias reciben nuevo routing exacto

Se exigió **train/IS rentable + selection rentable + OOS final rentable + walk-forward positivo**.

Aprobadas para *routing contextual*:

- **ETH-USDT 2H LONG · TREND_UP · RSI_TREND**
  - Train N40, +0.0866R, PF1.185
  - Selection N14, +0.1646R, PF1.482
  - OOS N14, +0.3331R, PF1.968
  - WF+ 1.00

- **SOL-USDT 2H SHORT · TREND_DOWN · SUPERTREND_PULLBACK**
  - Train N23, +0.1015R, PF1.138
  - Selection N8, +0.5033R, PF1.873
  - OOS N8, +0.3130R, PF1.416
  - WF+ 1.00

- **XRP-USDT 2H SHORT · TREND_DOWN · TREND_CONTINUATION**
  - Train N52, +0.1113R, PF1.212
  - Selection N17, +0.3306R, PF1.826
  - OOS N18, +0.2785R, PF1.519
  - WF+ 1.00

NO reciben routing LIVE nuevo:

- ADA 2H SWEEP_REVERSAL: OOS bueno, pero Train/IS -0.0375R / PF0.949.
- LINK 2H RSI_MAVERICK_REVERSAL: OOS bueno, pero Train/IS -0.1100R / PF0.837.
- ADA 4H BOLLINGER_SQUEEZE: Train/IS -0.1202R y OOS sólo N6.

Esas tres permanecen SHADOW. Esto evita “escoger sólo el tramo bonito” del backtest.

### 3. Nuevo bridge `validated_strategy_routes_175111r1.py`

Antes Main podía saber que un exact prior Research era positivo pero enviar a Entry/SL/TP una familia genérica distinta.

R.1 alinea:

`Research exacto -> Strategy Bank compatible -> semántica Entry/SL/TP`

sin crear dirección ni saltarse ninguna puerta.

Ejemplos:

- RSI_TREND -> MOMENTUM_CONTINUATION
- SUPERTREND_PULLBACK -> TREND_PULLBACK
- TREND_CONTINUATION -> MOMENTUM_CONTINUATION
- RSI_MAVERICK_REVERSAL -> MEAN_REVERSION (SHADOW)
- BOLLINGER_SQUEEZE -> COMPRESSION_EXPANSION (SHADOW)

### 4. Entry/SL/TP: paridad económica sin copiar stops ATR

Las rutas aprobadas tenían geometría histórica rentable, pero R.1 **NO copia el SL ATR** al trade live. Eso sería peligroso por el problema observado de SL dentro de zona de reacción.

R.1 utiliza:

- semántica de Entry del setup validado;
- Entry final sólo desde niveles observados/estructurales;
- SL final detrás de invalidación y con `SL_REACTION_CONFLICT` fail-closed;
- TP desde estructura/liquidez/targets observados;
- RR histórico sólo como **preferencia suave ±0.35** dentro del ranking conjunto;
- el piso y techo técnicos de R/R no cambian;
- nunca se inventa TP desde RR/ATR.

### 5. Se conserva la única ruta Entry con evidencia IS/OOS suficiente

`LIQUIDITY_SWEEP_MSS_POI` en Futures 30m:

- IS N11 · 7TP/4SL · +0.8592R · PF3.363
- OOS N5 · 5TP/0SL · +1.8000R

Sólo actúa si hay sweep + MSS/BOS o displacement + POI estructural. No se generaliza a 1h/2h/4h.

### 6. Funnel ahora conserva estado de cobertura

El snapshot compacto y el funnel técnico guardan:

- `coverage_route_state`;
- `validated_route_matched`;
- `validated_route_execution_eligible`;
- familia y razón.

Así, después del deploy se puede medir si la baja frecuencia viene de:

- falta de tesis;
- falta de dirección;
- falta de edge exacto validado;
- Entry;
- SL;
- TP;
- RR;
- Safety;
- publicación.

### 7. Todo lo de 17.5.11R se conserva

- reparación Multi-Activo de caché/jobs/response shape/gráficos;
- caché compacta suficiente para universo Multi;
- análisis pesado fuera del request HTTP;
- bounded retry, no polling infinito;
- separación Futures/Multi;
- dedup KSTR por cierre canónico de vela;
- `gunicorn app:app`, 1 worker / 2 threads;
- Greeks/GEX siguen SHADOW_CONTEXT_ONLY;
- OrderBook/OrderFlow conserva su autoridad actual, no se inventa backtest L2 histórico.

---

## Archivos que debes reemplazar/agregar

Arrastra exactamente estos **14 archivos de código/configuración** respetando carpetas:

1. `app.py`
2. `operational_intelligence.py`
3. `contingency_strategy_engine.py`
4. `validated_strategy_routes_175111r1.py` **(nuevo)**
5. `execution_specialist_committees.py`
6. `strategy_quality_extension_175105.py`
7. `market_maker_math.py`
8. `options_market_context.py`
9. `static/futures.js`
10. `static/script.js`
11. `static/market_maker_frontend.js`
12. `templates/index.html`
13. `Procfile`
14. `render.yaml`

Los demás `.md/.json/.csv/.txt/qa_...` son documentación/QA; no son necesarios para runtime.

**No apliques primero 17.5.11R.** Este paquete ya contiene todo lo necesario y lo reemplaza.

---

## Implementación

1. Haz backup/tag del HEAD 17.5.10.9.
2. Abre este ZIP.
3. Arrastra/reemplaza los 14 archivos anteriores en VSCode Web.
4. Haz **un único commit**: `Commit 17.5.11R.1`.
5. Un solo deploy en Render.
6. Espera estado `Live`.
7. `Ctrl+F5`.
8. Verifica `/futures` y `/multiasset`.

No ejecutes scripts de aplicación ni pegues fragmentos a mano.

---

## QA

PASS:

- Python syntax de todos los Python cambiados.
- Node parse de JS cambiado.
- Runtime/Geometry/Options/Delivery: **34/34**.
- Multi Scheduler: **8/8**.
- Structure regression: **23/23**.
- Frontend: **11/11**.
- R.1 exact-route QA: **18/18**.

**Total principal: 94 checks PASS.**

R.1 QA verifica expresamente:

- sólo 3 rutas con train+selection+OOS rentable reciben routing;
- las otras 3 quedan SHADOW;
- un régimen incorrecto no activa la ruta;
- Alpha Decay/recycle la bloquea;
- LOW volatility no se veta si el StrategySpec validado era `ANY`;
- un activo sin ruta exacta no recibe una estrategia fabricada;
- mapping Research -> geometría correcto;
- ruta Entry 30m validada preservada;
- RR histórico sólo modifica preferencia, no floor/ceiling;
- backtest prior de ejecución sigue con peso 0.

---

## Qué medir después del deploy

Durante 24–48 h mínimas y varios cierres de 30m/1h/2h/4h:

- celdas analizadas / universo esperado;
- contexto y volatilidad de cada celda;
- `coverage_route_state`;
- thesis/direction/candidate/setup;
- Entry propuesto y Entry activado;
- MAE/MFE;
- TP/SL;
- `SL_REACTION_CONFLICT`;
- recovery applied/shadow;
- señales por TF sin duplicados;
- Multi gráfico/recomendación/diagnóstico;
- RSS/RAM y Service-Initiated bandwidth.

El objetivo de éxito no es “X señales por día”. Es demostrar que los días con movimientos aprovechables ya no se pierden por bug, por familia geométrica equivocada o por Entry/SL técnicamente defectuoso.

---

## Rollback

Si aparece regresión crítica de runtime:

- volver al tag/commit 17.5.10.9;
- no intentar mezclar parcialmente R, R.1 y 17.5.10.9;
- conservar logs y ejemplos de señal para reproducir el fallo.

Si el problema es sólo una ruta validada concreta, **no bajar Safety**: deshabilitar/volver SHADOW esa ruta en `validated_strategy_routes_175111r1.py` en el siguiente commit gobernado.
