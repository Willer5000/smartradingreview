# COMMIT 17.5.11R.3 — Geometría manual garantizada + guardado inmediato + Multi progresivo + D/G/T restaurado

**Base para aplicar:** 17.5.11R.2 ya desplegado por el usuario.  
**Aplicación:** reemplazar directamente R.2 por R.3 en un único commit/deploy. No volver a aplicar R ni R.1.

## Por qué existe R.3

La evidencia real después de desplegar R.2 mostró tres regresiones/limitaciones todavía abiertas:

1. `Por qué no aparecen otras señales` aumentó en frecuencia, pero muchas hipótesis LONG/SHORT seguían sin Entry/SL/TP, y las que sí tenían niveles no mostraban guardado manual. El motivo principal era doble: R.2 todavía permitía que algunos setups llegaran al diagnóstico después de haber perdido la geometría, y el helper de visibilidad quitaba `manual_save_allowed` a las hipótesis del cierre ACTUAL aunque el servidor ya las considerara guardables.
2. Multi-Activo ya renderiza el gráfico principal, pero durante `motor compartido ocupado` podían faltar Estructura institucional, mapa de liquidaciones y sentimiento hasta que terminara el análisis pesado.
3. Delta/Gamma/Theta seguía pudiendo quedar en `Contexto de opciones no disponible` porque una respuesta/API fallida todavía podía reemplazar el fallback teórico visual.

R.3 corrige estos tres puntos sin rebajar la publicación Premium y sin convertir las hipótesis manuales en señales oficiales.

---

## 1. TODA tesis direccional real de cierre recibe Entry + SL + TP

Nuevo contrato runtime para Futures y Multi-Activo:

`tesis LONG/SHORT gobernada -> comité Entry/SL/TP -> recuperación estructural -> fallback técnico manual si aún faltan niveles`

Orden de decisión:

1. conservar la geometría normal del comité si es válida y el SL no está en conflicto con una zona de reacción;
2. si falla, volver a intentar con el especialista estructural utilizando POI, soportes/resistencias, OB, FVG, volumen y pools de liquidación;
3. si la estructura observada todavía no permite completar los tres niveles, crear una geometría **MANUAL/ANALYSIS_ONLY de último recurso**:
   - Entry en la zona de reacción más cercana disponible;
   - si no existe POI usable, Entry pendiente mediante retroceso normalizado por ATR;
   - SL detrás de invalidación/estructura; ATR sólo completa la distancia cuando falta un ancla;
   - el guard `SL_REACTION_CONFLICT` vuelve a comprobar que el stop no quede dentro de una zona activa;
   - TP en estructura/liquidez opuesta; sólo si no existe objetivo estructural suficiente se usa un múltiplo R técnico.

Este fallback **no crea dirección**, no hace Premium a la hipótesis, no baja Safety, no manda Telegram oficial y no se presenta como alpha backtesteado. Existe porque el usuario requiere poder seguir manualmente toda tesis direccional real.

Para proteger activos de precio bajo, `_round_price` ahora usa los decimales reales de `futures_universe` / `MULTIASSET_SYMBOLS`; evita colapsar SEI/SUI/DOT/etc. a 2 decimales y destruir la geometría.

---

## 2. TODA hipótesis del cierre actual con geometría puede guardarse inmediatamente

Se eliminó la regresión concreta que impedía el botón aunque el servidor devolviera Entry/SL/TP.

Antes:

`manual_save_allowed = server_allowed AND previous_cycle`

Por eso una hipótesis del cierre actual aparecía con niveles pero seguía mostrando `No cumple las condiciones mínimas para guardado manual`.

Ahora:

`manual_save_allowed = server_allowed`

Si es una tesis LONG/SHORT de vela cerrada, datos reales y geometría válida, puede guardarse **en el mismo cierre**. No tiene que esperar una vela adicional.

El perfil manual ya no usa Safety/Premium como permiso de usuario:

- Safety/publicación siguen determinando si es oficial;
- Safety bajo -> `RIESGO ALTO`;
- Safety suficiente pero no Premium -> `RIESGO MEDIO`;
- ambas clases pueden guardarse bajo decisión del usuario;
- sólo se bloquea si no hay dirección real, datos sintéticos, vela explícitamente abierta o geometría inválida.

El flujo sigue ofreciendo:

- `Guardar seguimiento`;
- `Guardar bajo mi riesgo`;
- `Guardar en operación`.

Guardian puede proteger la operación guardada. Guardar **no** cambia `ANALYSIS_ONLY` a `EXECUTABLE_SIGNAL` y no la incorpora al Telegram Premium.

El endpoint de guardado también puede resolver la fuente por `símbolo × TF × dirección`, además del `signal_id`, evitando que una key sintética del frontend impida el guardado del cierre actual.

---

## 3. Entry/SL/TP: qué significa “garantizado”

R.3 garantiza **existencia de una geometría técnica coherente para seguimiento manual**, no rentabilidad futura.

La jerarquía de autoridad queda:

- **Premium:** geometría normal + Safety/publicación completa.
- **ANALYSIS_ONLY estructural:** geometría recuperada por POI/estructura; usuario puede guardarla.
- **ANALYSIS_ONLY fallback:** geometría técnica de último recurso; usuario puede guardarla, marcada como riesgo alto.

Así se evita el extremo anterior de mostrar una tesis LONG/SHORT sin operación definida, pero tampoco se falsifica evidencia estadística para elevarla a Premium.

Se mantienen las rutas backtesteadas de R.1/R.2 y el `SL_REACTION_CONFLICT` de R.

---

## 4. Multi-Activo: gráficos técnicos progresivos durante BUSY

R.2 ya solucionó la identidad CL/XAG/QQQ/KSTR y el gráfico principal. R.3 amplía el snapshot ligero de **la celda seleccionada solamente** con capas CPU-only derivadas de las mismas velas:

- tendencia;
- momentum;
- volatilidad;
- volumen;
- estructura de mercado;
- modelo local de liquidaciones;
- sentimiento técnico local.

Restricciones de recursos se conservan:

- una sola celda seleccionada;
- hasta 180 velas;
- TTL 60 s;
- máximo 4 snapshots ligeros;
- sin LLM;
- sin escritura DB;
- sin escaneo adicional del universo;
- sin worker nuevo;
- sin polling agresivo.

El sentimiento se etiqueta como **`Sentimiento técnico`** y `MULTI_TECHNICAL_PROXY`. No se presenta como Fear & Greed cripto ni como encuesta real.

El mapa de liquidaciones de este estado parcial se etiqueta `SELECTED_CELL_LOCAL_MODEL`. Cuando finaliza el análisis pesado, los datos ricos sustituyen estas capas progresivas.

---

## 5. Delta / Gamma / Theta vuelve a dibujarse aunque falle la cadena/API

R.2 tenía Black-Scholes teórico, pero todavía existía una ruta visual que llamaba `unavailable()` ante un error del endpoint y borraba la curva.

R.3 añade un fallback local del navegador:

1. obtiene el spot del análisis que ya se está mostrando;
2. estima una superficie Black-Scholes teórica de 41 puntos;
3. dibuja Gamma, Delta y Theta;
4. si luego llega una cadena compatible observada, ésta sustituye al modo teórico.

El modo local está etiquetado:

`SHADOW_THEORETICAL_UI_LOCAL`

No inventa inventario real de dealers, Call Wall, Put Wall, Gamma Wall, Zero-Gamma ni Delta-Neutral. Esos valores siguen `--` si no existen datos observados.

Un error HTTP/provider ahora intenta `render()` con fallback local en vez de borrar el gráfico.

---

## 6. ¿Por qué puede existir un SHORT corto cuando el TF mayor es alcista?

R.3 no elimina automáticamente esas hipótesis porque pueden representar:

- pullback intratendencia;
- mean reversion/rango;
- sweep/reversal táctico;
- corrección de corto plazo dentro de una tendencia superior alcista.

La alineación multitemporal sigue afectando la autoridad Premium. Una hipótesis contra el marco mayor puede permanecer `ANALYSIS_ONLY`/riesgo alto y aun así ser guardada manualmente por el usuario. No se convierte en señal Premium sólo por tener Entry/SL/TP.

---

## 7. Frecuencia / alpha: NO se reoptimiza en R.3

R.3 no añade nuevas familias ni modifica los tres routes validados de R.1/R.2. Se conserva:

- ETH-USDT 2H LONG · RSI_TREND;
- SOL-USDT 2H SHORT · SUPERTREND_PULLBACK;
- XRP-USDT 2H SHORT · TREND_CONTINUATION;
- LIQUIDITY_SWEEP_MSS_POI con autoridad acotada Futures 30m.

Por ello el backtest estadístico es el mismo de R.2. La geometría fallback manual no recibe autoridad estadística nueva.

Ver `BACKTEST_17_5_11R_3_EVIDENCE.md`.

---

## 8. Archivos runtime a reemplazar

El ZIP contiene los 14 archivos completos para mantener un overlay coherente con R.2. Arrástralos respetando carpetas:

1. `app.py`
2. `operational_intelligence.py`
3. `contingency_strategy_engine.py`
4. `validated_strategy_routes_175111r1.py`
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

En R.3 sólo cambian materialmente `app.py`, los tres JS anteriores y `templates/index.html`; los demás se incluyen completos para evitar mezclas de versiones.

---

## 9. Implementación desde tu estado actual R.2

1. Haz backup/tag del commit actualmente desplegado R.2.
2. Extrae el ZIP R.3.
3. Arrastra los 14 archivos runtime en VSCode Web.
4. Acepta reemplazo conservando `static/` y `templates/`.
5. Un solo commit sugerido:
   `Commit 17.5.11R.3 - manual geometry guardian multi greeks final repair`
6. Un único deploy Render.
7. Espera `Live`.
8. Haz `Ctrl+F5` para cargar el cache-bust R.3.

### Verificación post-deploy prioritaria

- Abrir `Por qué no aparecen otras señales` después del nuevo análisis: **cada tesis LONG/SHORT real debe mostrar Entry, SL, TP y R/R**.
- Una tesis HIGH del cierre actual debe mostrar botón `Guardar bajo mi riesgo` sin esperar otra vela.
- Guardarla debe aparecer en Guardadas/operación según elección y Guardian debe poder seguirla.
- Premium/Telegram debe seguir separado.
- Futures D/G/T: con precio disponible debe verse una curva teórica aunque diga `Sin cadena compatible`.
- Multi durante BUSY: gráfico central + estructura + liquidaciones + sentimiento técnico deben empezar a poblarse con la celda seleccionada; la capa pesada puede completar después.

---

## 10. QA

Ejecutado sobre repositorio completo R.2 + R.3:

- Geometry/Runtime: 19/19 PASS
- Scheduler: 8/8 PASS
- Structure regression: 23/23 PASS
- Frontend: 11/11 PASS
- Validated routes R.1: 18/18 PASS
- R.2 regression contracts: 11/11 PASS
- R.3 manual geometry / current-save / Multi / DGT: 17/17 PASS

**Total funcional principal: 107/107 PASS**, más `py_compile` y parse JavaScript PASS.

El contenedor de QA no tiene Flask instalado; no se levantó Gunicorn real. La validación final de infraestructura sigue siendo el deploy de Render.

---

## 11. Qué NO se promete

- No se garantiza beneficio ni una operación Premium diaria.
- La geometría manual fallback no es un nuevo alpha backtesteado.
- No se debilita Safety para convertir diagnósticos en Premium.
- No se fuerza alineación MTF artificial.
- No se inventa OrderBook histórico ni dealer positioning.

El objetivo de R.3 es que una oportunidad direccional detectada deje de ser inútil por falta de niveles/guardado, mientras el sistema conserva una separación estricta entre **seguimiento manual** y **autoridad oficial Premium**.

## Rollback

Si aparece una regresión crítica de infraestructura, vuelve al commit R.2 completo. No mezcles parcialmente R.2/R.3 en rollback.
