# BACKTEST 17.5.11R.1 — Cobertura + Geometría de ejecución

Fecha de auditoría: **30/09/2026**  
Base productiva: **17.5.10.9**  
Paquete sustituido: **17.5.11R no desplegado**

## 1. Objetivo

No aumentar señales por bajar Safety/RR ni por añadir estrategias arbitrarias. La pregunta de R.1 fue:

1. ¿Qué estrategias tienen evidencia rentable en **train/IS + selection holdout + OOS final + walk-forward**?
2. ¿Qué rutas de Entry/SL/TP tienen evidencia cronológica suficiente para recibir autoridad adicional?
3. ¿Cómo hacer que Main use el **mismo tipo de setup** que Research validó, sin copiar un SL fijo que pueda volver a quedar dentro de una zona de reacción?

La evidencia proviene de las tablas gobernadas de Research y `signal_results.execution_forensics` ya persistidas por el sistema. No se usó información futura para crear una señal live y no se trató un Telegram ajeno como ground truth.

---

## 2. Resultado de estrategias exactas de Futures

Research tenía 6 rutas actuales en `SHADOW_READY/SHADOW_READY_FAST`. Al exigir además **rentabilidad positiva en train/IS, selection y OOS final**, sólo 3 conservan autoridad nueva de *routing* en R.1.

| Celda | Familia | Train/IS | Selection | OOS final | WF+ | R.1 |
|---|---|---:|---:|---:|---:|---|
| ETH-USDT 2H LONG · TREND_UP | RSI_TREND | N40 · +0.0866R · PF1.185 | N14 · +0.1646R · PF1.482 | N14 · **+0.3331R · PF1.968** | 1.00 | **Routing validado** |
| SOL-USDT 2H SHORT · TREND_DOWN | SUPERTREND_PULLBACK | N23 · +0.1015R · PF1.138 | N8 · +0.5033R · PF1.873 | N8 · **+0.3130R · PF1.416** | 1.00 | **Routing validado** |
| XRP-USDT 2H SHORT · TREND_DOWN | TREND_CONTINUATION | N52 · +0.1113R · PF1.212 | N17 · +0.3306R · PF1.826 | N18 · **+0.2785R · PF1.519** | 1.00 | **Routing validado** |
| ADA-USDT 2H SHORT | SWEEP_REVERSAL | N34 · **-0.0375R · PF0.949** | N12 · +1.2846R · PF5.610 | N12 · +0.5596R · PF2.142 | 1.00 | **SHADOW**: IS no rentable |
| LINK-USDT 2H SHORT · BALANCE | RSI_MAVERICK_REVERSAL | N26 · **-0.1100R · PF0.837** | N9 · +0.8671R · PF4.458 | N9 · +0.2642R · PF1.509 | 1.00 | **SHADOW**: IS no rentable |
| ADA-USDT 4H SHORT | BOLLINGER_SQUEEZE | N16 · **-0.1202R · PF0.804** | N6 · +0.5567R · PF3.014 | N6 · +0.9649R · PF6.618 | 1.00 | **SHADOW**: IS negativo + OOS pequeño |

### Interpretación

R.1 **no promociona automáticamente todo lo que tiene OOS positivo**. ADA 2H, LINK 2H y ADA 4H parecen atractivos mirando sólo el tramo final, pero fallan la exigencia del usuario de demostrar rentabilidad también en la muestra de desarrollo/train. Se conservan como investigación, no como autoridad de producción.

Las tres rutas aceptadas tampoco crean dirección. Sólo pueden alinear el tipo de setup cuando el runtime ya tiene el mismo activo×TF×dirección, régimen compatible, prior Research sano, evidencia live independiente, MTF utilizable y luego supera Entry/SL/TP/RR/Safety/publicación.

---

## 3. Combinaciones históricas Entry / SL / TP de las 3 rutas aceptadas

Estos parámetros son la geometría del replay de Research. R.1 **no copia el SL ATR como stop live**, porque eso podría reintroducir el problema crítico "SL dentro de zona de reacción". Se usan de forma limitada:

- el `entry_style` decide qué semántica de setup recibe el comité;
- el RR histórico puede orientar suavemente el *preferred RR* del ranking conjunto;
- el piso/techo técnico de RR **no cambia**;
- Entry, SL y TP finales deben seguir viniendo de estructura/liquidez/POI/invalidation/targets observados;
- `SL_REACTION_CONFLICT` conserva veto duro.

| Celda | Entry replay | SL replay | RR replay | Semántica live R.1 |
|---|---|---:|---:|---|
| ETH 2H LONG | NEXT_OPEN | 2.00 ATR | 2.0 | **MOMENTUM_CONTINUATION**; objetivo estructural priorizado cerca del RR validado |
| SOL 2H SHORT | PULLBACK 0.18 ATR | 0.90 ATR | 3.0 | **TREND_PULLBACK**; Entry debe ser POI/pullback real, SL detrás de invalidación |
| XRP 2H SHORT | NEXT_OPEN | 1.40 ATR | 3.0 | **MOMENTUM_CONTINUATION**; no chase, target estructural y RR histórico como preferencia suave |

Esto crea **paridad semántica**, no paridad perfecta de ejecución. La paridad completa sólo podrá declararse después de Shadow/live con los niveles reales del comité.

---

## 4. Backtest de rutas de Entry/SL/TP ya persistidas

Se reanalizaron los challengers de `execution_forensics` con orden temporal. El hallazgo que sigue siendo más sólido para geometría es:

### LIQUIDITY_SWEEP_MSS_POI · Futures 30m

- IS cronológico: **N=11 · 7 TP / 4 SL · +0.8592R · PF 3.363**
- OOS cronológico: **N=5 · 5 TP / 0 SL · +1.8000R**

Por eso R.1 conserva la autoridad acotada de 17.5.11R: sólo en Futures 30m y sólo si existen sweep + MSS/BOS o displacement + POI estructural.

### No promocionados

- 1h LIQUIDITY route: OOS N9, 2TP/7SL, +0.0906R, PF1.116 → **SHADOW**.
- 2h LIQUIDITY route: OOS N6, 0TP/6SL, -1.000R → **rechazada**.
- 4h LIQUIDITY route: OOS N2 → **muestra insuficiente**.
- MICROSTRUCTURE_CONFIRMED_ENTRY: muestra demasiado pequeña/inestable → **sin autoridad**.
- TRENDLINE_RETEST: IS/OOS inestable → **sin autoridad**.
- SPECIALIST_COMMITTEE genérico: muestras pequeñas y no estables por TF → **sin autoridad adicional**.

Un segundo split 60/20/20 por clases de contexto tampoco encontró otra combinación con estabilidad suficiente en IS+selection+OOS como para promoverla. Algunos subgrupos mejoraron al final, pero tenían IS/selection negativo o N demasiado pequeño.

---

## 5. Screening de familias genéricas nuevas

Antes de R.1 ya se probaron familias construidas con indicadores persistidos. Se mantienen rechazadas porque aumentarían frecuencia sin demostrar edge estable:

- `TREND_PULLBACK` genérico: IS -0.7786R, OOS -1.0992R.
- `VOLUME_PROFILE_REACTION`: IS -0.8613R, OOS -0.5908R.
- `FVG_RECLAIM`: IS -1.1231R, OOS -1.1180R.
- `TREND_BAND_CONTINUATION`: IS -0.7404R; OOS +0.0584R/PF1.08, insuficiente e inestable.

Conclusión: **más familias por cantidad no era la solución**.

---

## 6. Matriz real de cobertura

`COVERAGE_MATRIX_17_5_11R1.csv` contiene **4,200 combinaciones** de:

- activo;
- TF;
- LONG/SHORT;
- régimen (TREND_UP, TREND_DOWN, BALANCE, TRANSITION, VOLATILITY_SHOCK);
- volatilidad (LOW, NORMAL, COMPRESSION, EXPANSION, SHOCK);
- Futures cripto + Multi-Activo.

Cada fila distingue:

- `VALIDATED_EXACT_ROUTE`: exacto y rentable train/selection/OOS;
- `SHADOW_EXACT_ROUTE`: Research interesante pero sin autoridad R.1;
- `RESEARCH_GAP_FALLBACK_ONLY`: existe cobertura contextual del Strategy Bank, pero **no se afirma alpha validado exacto**.

El sistema, por tanto, **no veta automáticamente baja/alta volatilidad**. El banco contextual sigue ofreciendo familias de rango/mean-reversion, pullback, breakout/retest, sweep, compresión/expansión según el contexto. R.1 añade observabilidad para saber cuándo esa cobertura es sólo contextual y cuándo además existe edge exacto validado.

---

## 7. Qué cambia en producción y qué NO

### Cambia

1. Un exact Research prior rentable ya no puede llegar al runtime con una familia geométrica genérica distinta: `validated_strategy_routes_175111r1.py` alinea Research → Strategy Bank → Entry/SL/TP.
2. Las tres rutas con train+selection+OOS positivo reciben routing exacto.
3. El RR histórico de esas rutas sólo ajusta el **preferred RR de ranking** (±0.35), nunca el piso/techo técnico ni crea targets sintéticos.
4. El funnel conserva `coverage_route_state`, familia validada y motivo de gap para auditar `NO_STRATEGY_FOR_CONTEXT` sin bajar thresholds.
5. Se conserva la ruta Entry 30m `LIQUIDITY_SWEEP_MSS_POI` ya validada.
6. Se conserva el veto de SL dentro de zona de reacción y la recuperación estructural acotada.

### NO cambia

- Safety.
- mínimo R/R técnico.
- leverage como gate de publicación.
- requisitos MTF.
- Alpha Decay / OOS negativo.
- cantidad mínima de familias de evidencia.
- OrderBook/OrderFlow no recibe autoridad histórica nueva sin L2 point-in-time.
- Greeks/0DTE/GEX siguen SHADOW_CONTEXT_ONLY.
- Multi-Activo no recibe un alpha genérico copiado desde cripto.

---

## 8. Limitación estadística importante

Ningún backtest garantiza resultados futuros. Las muestras OOS de SOL (8) y ETH (14) siguen siendo moderadas; por eso R.1 les da **autoridad de routing contextual**, no permiso para saltarse la ejecución real. Después del deploy se debe medir prospectivamente:

- señal/celda/TF;
- Entry activado;
- MAE/MFE;
- TP vs SL;
- `SL_REACTION_CONFLICT`;
- route state;
- cobertura de volatilidad/régimen;
- frecuencia recuperada vs 17.5.10.9.

La meta es recuperar oportunidades **demostrablemente defendibles**, no garantizar una señal diaria.
