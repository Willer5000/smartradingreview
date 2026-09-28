# Commit 17.5 — Stable Baseline Recovery + Execution Geometry Hardening

## Base de trabajo

Este release está construido **directamente sobre `smartradingreview-main(4).zip`**, entregado por Willer como el último `main` útil antes de la regresión de lluvia de señales / señales incompletas de la rama 17.4.

No es un parche acumulativo sobre 17.4/17.4.1. El objetivo es recuperar el comportamiento operativo conocido del baseline y mejorar solamente Entry / SL / TP.

## Alcance funcional

Archivos funcionales modificados frente al baseline:

- `app.py`
- `execution_geometry_committee.py`

No se modifican los motores que deciden la existencia de una señal ni el leverage:

- `futures_system.py` — sin cambios
- `leverage_policy.py` — sin cambios
- `operational_intelligence.py` — sin cambios
- `default_strategy_bank.py` — sin cambios
- `multiasset_system.py` — sin cambios
- `portfolio_guardian.py` — sin cambios
- `saved_signals.py` — sin cambios
- `static/futures.js` — sin cambios
- `static/script.js` — sin cambios
- `templates/index.html` — sin cambios

El login y el Liquidation Map del baseline se conservan. La clase que genera/recalibra el mapa no fue reescrita.

## Qué se corrige

### Entry

La lógica original de selección de Entry se conserva. Se mejora únicamente el contexto de liquidez ya cargado:

- el mapa actual usa `relative_participation`;
- entre pools de distancia similar, Entry puede preferir el cluster relativamente más fuerte;
- no se añade ninguna API, indicador o voto nuevo;
- no cambia LONG / SHORT / COMPRA_SPOT / VENTA_SPOT.

### Stop Loss

El baseline ya calculaba `sl_buffer_atr` por mercado, símbolo/grupo, TF, régimen y volatilidad, pero la recolección real de candidatos seguía usando offsets fijos de 0.2/0.3 ATR.

17.5 conecta ambos componentes:

- swing/sweep/S-R quedan detrás de la zona de reacción;
- OB/FVG/Value Area usan clearance contextual;
- existe un piso moderado por tipo de estructura;
- el score penaliza stops demasiado pegados a la reacción;
- el score también penaliza stops excesivamente amplios mediante las reglas existentes;
- ATR fallback se conserva.

Esto busca reducir el patrón observado de `Entry -> MFE casi nulo -> reacción exactamente en SL` sin convertir el SL en una pérdida desproporcionada.

### Take Profit

El target analítico continúa siendo estructural. El TP ejecutable se coloca ligeramente **antes** de la zona donde puede aparecer reacción contraria:

- resistencia / soporte;
- swing;
- OB / FVG;
- HVN / Value Area;
- Fibonacci;
- pool de liquidación.

El buffer depende del contexto y volatilidad (`tp_capture_buffer_atr`) y se reduce automáticamente si fuera necesario para conservar el piso técnico de R/R. Nunca se aleja artificialmente el TP para fabricar R/R.

Además, el ranking de pools del Liquidation Map deja de comparar pesos relativos contra umbrales legacy de millones de USD. Se normaliza contra la intensidad relativa de los bins activos ya cargados.

## Lo que NO hace

- no baja Safety;
- no cambia umbrales de publicación;
- no cambia familias de estrategia;
- no crea estrategias nuevas;
- no modifica MTF;
- no modifica macro;
- no modifica Research / ReviewTrader;
- no modifica leverage;
- no cambia frecuencia por política;
- no introduce `CONFIRMED_PENDING_EXECUTION`;
- no permite señales con SL/TP=0;
- no añade llamadas Groq;
- no añade requests externos;
- no añade escrituras Supabase;
- no añade workers/polling.

## QA

Validación directa:

- `python -m compileall -q .` — PASS
- `node --check static/script.js` — PASS
- `node --check static/futures.js` — PASS
- `test_rc9_8_execution_geometry.py` + `test_commit17_5_execution_hardening.py` — **25/25 PASS**
- QA nuevo 17.5 — **7/7 PASS**

Se ejecutó también una batería amplia del baseline. Los 8 fallos observados son exactamente los mismos 8 fallos preexistentes al ejecutar la misma batería sobre el ZIP original (tests históricos desactualizados respecto de archivos SQL/versiones posteriores). No apareció ningún fallo nuevo provocado por 17.5.

## Despliegue

1. Usar este árbol completo como reemplazo del repo desplegado actual.
2. Hacer **un solo commit físico**.
3. Deploy en Render.
4. No aplicar después los ZIP 17.4 / 17.4.1 sobre este árbol.
5. Observar las primeras señales y medir:
   - Entry reachability;
   - MAE antes de MFE;
   - reacción alrededor de SL;
   - TP touch rate;
   - R realizado;
   - leverage recomendado por el motor baseline.

## Rollback

El rollback limpio es el `smartradingreview-main(4).zip` original. Como 17.5 sólo cambia dos archivos funcionales respecto de ese baseline, el rollback también puede hacerse restaurando:

- `app.py`
- `execution_geometry_committee.py`

## Política para la siguiente etapa

Después de este commit no ajustar el motor por una sola pérdida, una sola sesión sin señales o un movimiento retrospectivo no capturado. Cambios adicionales requieren una regresión reproducible o evidencia estadística por mercado × símbolo/grupo × TF × dirección.
