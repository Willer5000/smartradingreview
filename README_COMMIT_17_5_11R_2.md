# COMMIT 17.5.11R.2 — Frecuencia defendible + Entry/SL/TP + guardado manual + Multi UI + Delta/Gamma/Theta

**Base real para aplicar:** 17.5.10.9 actualmente desplegado.  
**IMPORTANTE:** el usuario NO desplegó 17.5.11, 17.5.11R ni 17.5.11R.1. Este paquete **sustituye a los tres**. Aplicar solamente **17.5.11R.2** en un único commit/deploy.

## Por qué existe R.2

La evidencia visual del 30/09/2026 mostró dos regresiones/defectos que debían resolverse antes del único deploy:

1. En `Por qué no aparecen otras señales (N)`, las hipótesis ANALYSIS_ONLY seguían visibles pero habían perdido el flujo antiguo de guardado manual. Ese cambio no había sido solicitado por el usuario.
2. Multi-Activo seguía pudiendo producir señales en Telegram (por ejemplo XAG-USDT 4h), pero la interfaz podía quedar con `motor compartido ocupado`, gráfico vacío y hasta identidad stale de BTC en una selección CL.
3. El panel Delta/Gamma/Theta podía quedar totalmente vacío si no había una cadena pública compatible **y** el análisis rico de Futures no estaba en caché.
4. Muchas hipótesis direccionales terminaban en `NO_EXECUTABLE_LEVELS` no porque la dirección fuese necesariamente mala, sino porque al terminar la decisión oficial en ESPERAR/PRECAUCION el pipeline ya no llamaba al mismo desk de Entry/SL/TP que usa una señal publicable.

R.2 corrige estos puntos **sin convertir ANALYSIS_ONLY en señal Premium y sin bajar Safety/RR para producir frecuencia**.

---

## 1. Se restaura el guardado manual anterior

Una hipótesis LONG/SHORT mostrada en `Por qué no aparecen otras señales` puede volver a guardarse **si y sólo si** el servidor consigue construir una geometría completa y válida:

- Entry > 0;
- SL > 0;
- TP > 0;
- orden geométrico correcto para LONG/SHORT;
- R/R dentro de la banda manual existente;
- vela cerrada y datos reales;
- no es Research-only ni AI_BLOCKED;
- el servidor autoriza `manual_save_allowed`.

El frontend vuelve a ofrecer:

- `Guardar seguimiento` cuando corresponde a riesgo MEDIUM;
- `Guardar bajo mi riesgo` cuando corresponde a riesgo HIGH;
- `Guardar en operación` cuando el usuario ya está dentro.

**No se vuelve señal oficial.** El registro conserva `ANALYSIS_ONLY`, `system_executable=False` y requiere confirmación explícita del usuario.

Una hipótesis sin Entry/SL/TP defendibles sigue visible, pero no puede activar Guardian porque no existe todavía una operación técnicamente definida.

---

## 2. Las hipótesis no publicadas vuelven a pasar por el MISMO comité Entry/SL/TP

Éste es el cambio más importante para los múltiples `NO_EXECUTABLE_LEVELS`.

Antes, si la decisión final quedaba en PRECAUCION/ESPERAR aunque `operational_intelligence` conservara una dirección LONG/SHORT, el código entregaba niveles por defecto con SL/TP en cero. Por eso una tesis direccional podía aparecer como:

`LONG/SHORT válido para diagnóstico -> NO_EXECUTABLE_LEVELS`

sin que el comité de ejecución hubiera intentado construir la geometría completa.

R.2 hace:

`tesis LONG/SHORT gobernada -> calculate_entry_levels(...) -> Entry/SL/TP -> validación completa -> ANALYSIS_ONLY manual`

usa exactamente el mismo desk de ejecución que una señal de calidad. Después fuerza:

- `publication_status = ANALYSIS_ONLY`;
- `is_executable = False`;
- `manual_observation_geometry = True` sólo si la geometría es válida.

Por lo tanto el cambio **mejora la capacidad de seguimiento manual sin abrir una puerta paralela de publicación**.

Se conservan las protecciones de R/R, `SL_REACTION_CONFLICT`, invalidación estructural y gates posteriores. Si el desk no puede encontrar una geometría defendible, no se fabrican niveles.

---

## 3. Guardian protege también un Multi-Activo guardado manualmente

El endpoint de guardado ahora conserva `market=multiasset` y valida la hipótesis contra `_MULTI_ASSET_CACHE`, no contra el snapshot de Futures.

El lifecycle de Saved/Guardian ya existente selecciona `multiasset_system` cuando el símbolo pertenece a `MULTIASSET_SYMBOLS`; R.2 preserva esa ruta. Por ello una hipótesis Multi manual con Entry/SL/TP válidos puede ser guardada y luego gestionada por Guardian bajo el riesgo asumido por el usuario.

No se crea un segundo Guardian ni un worker adicional.

---

## 4. Multi-Activo deja de depender del análisis pesado para dibujar el gráfico básico

Cuando el motor compartido está ocupado, R.2 primero agenda el job gobernado normal y, en paralelo de interfaz, obtiene **sólo la celda seleccionada** para mostrar hasta 180 velas.

Características del fallback visual:

- sólo símbolo/TF seleccionado;
- TTL 60 s;
- máximo 4 celdas en RAM;
- sin LLM;
- sin DB write;
- sin escanear todo el universo;
- no crea señal;
- no altera el resultado del motor pesado.

Así, seleccionar `CL-USDT · 4h` debe mostrar CL 4h mientras el análisis completo continúa, en lugar de una zona vacía o una identidad stale `BTC/USDT 1D`.

Cuando el job pesado termina, la recomendación/gráficos completos reemplazan el snapshot visual ligero.

---

## 5. Delta / Gamma / Theta vuelve a dibujar contexto teórico cuando no hay cadena pública

`market_maker_math.py` ya distinguía correctamente entre una cadena observada y una forma Black-Scholes teórica. El problema visual era otro: si el análisis rico había sido evictado, el endpoint podía quedarse también sin `spot`, por lo que ni siquiera podía generar la curva teórica.

R.2 añade un fallback **UI-only**:

1. usa el spot del resultado/cache cuando existe;
2. para BTC/ETH intenta cadena pública compatible;
3. si no hay spot en el cache, obtiene sólo el último precio de la celda Futures seleccionada;
4. si no hay cadena compatible, genera Delta/Gamma/Theta Black-Scholes teórico.

No inventa Call Wall, Put Wall, Gamma Wall, Zero-Gamma o Delta-Neutral. Esos niveles permanecen `--` si no existen datos observados suficientes.

Las curvas teóricas no tienen autoridad de señal ni modifican Entry/SL/TP/Safety.

---

## 6. Frecuencia y estrategias de R.1 se conservan intactas

R.2 **no elimina** la solución de cobertura/backtest de R.1.

Se conservan las 3 rutas exactas que superaron Train/IS + Selection + OOS final + walk-forward:

- ETH-USDT 2H LONG · TREND_UP · RSI_TREND;
- SOL-USDT 2H SHORT · TREND_DOWN · SUPERTREND_PULLBACK;
- XRP-USDT 2H SHORT · TREND_DOWN · TREND_CONTINUATION.

Se conservan SHADOW, sin autoridad nueva, ADA 2H SWEEP_REVERSAL, LINK 2H RSI_MAVERICK_REVERSAL y ADA 4H BOLLINGER_SQUEEZE porque su Train/IS no justificó promoción.

Se conserva además `LIQUIDITY_SWEEP_MSS_POI` Futures 30m con la evidencia ya auditada:

- IS N=11 · 7 TP / 4 SL · +0.8592R · PF 3.363;
- OOS N=5 · 5 TP / 0 SL · +1.8000R.

No se generaliza a 1h/2h/4h.

---

## 7. Archivos runtime que debes reemplazar/agregar

Arrastra exactamente estos **14 archivos** respetando carpetas:

1. `app.py`
2. `operational_intelligence.py`
3. `contingency_strategy_engine.py`
4. `validated_strategy_routes_175111r1.py` *(archivo nuevo heredado de R.1; el nombre se conserva para no romper imports)*
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

Los `.md/.json/.csv/.txt` del ZIP son documentación y QA; no son necesarios para runtime.

**No apliques R, R.1 ni el 17.5.11 anterior antes de éste.**

---

## 8. Implementación

1. Backup/tag del HEAD actual 17.5.10.9.
2. Extraer este ZIP.
3. Arrastrar los 14 archivos runtime a VSCode Web y aceptar reemplazo.
4. Un único commit: `Commit 17.5.11R.2 - frequency entry guardian multi ui repair`.
5. Un solo deploy Render.
6. Esperar `Live`.
7. `Ctrl+F5`.
8. Verificar primero Futures y Multi-Activo.

### Checklist visual post-deploy

- Futures → `Por qué no aparecen otras señales`: una hipótesis con niveles válidos vuelve a mostrar botón de guardado manual.
- Guardarla no la convierte en Premium; aparece en Guardadas y Guardian puede seguirla.
- Multi → seleccionar CL/XAG/QQQ/KSTR: el gráfico debe corresponder al símbolo/TF seleccionado incluso durante `motor compartido ocupado`.
- Una señal Multi guardada debe conservar `market=multiasset`.
- Delta/Gamma/Theta: si no existe cadena compatible, debe aparecer el gráfico teórico cuando existe precio; walls observados pueden seguir en `--`.
- Telegram: no duplicados para la misma vela canónica.

---

## 9. QA ejecutado sobre repositorio completo

R.2 se superpuso sobre el snapshot completo 17.5.10.9 antes de ejecutar QA.

PASS:

- Python `py_compile` de 8 Python cambiados.
- Node parse de los 3 JS modificados.
- Geometry/Runtime 17.5.11: **19/19**.
- Multi Scheduler: **8/8**.
- Structure regression: **23/23**.
- Frontend: **11/11**.
- R.1 validated-route QA: **18/18**.
- R.2 manual-save/Multi/DGT QA: **11/11**.

**Total funcional principal: 90/90 PASS**, más syntax PASS.

El contenedor de QA no tiene Flask instalado, por lo que no se levantó un servidor Flask/Gunicorn real. La validación fue offline mediante AST/unit tests y parse/syntax sobre el repositorio completo. El deploy real en Render sigue siendo la prueba de integración final de infraestructura.

---

## 10. Qué NO cambia

- no se baja Safety;
- no se baja el piso técnico de R/R;
- no se impone una cuota de señales por día;
- no se convierten diagnósticos en Telegram Premium;
- no se inventan Entry/SL/TP si el comité no puede defenderlos;
- no se da autoridad LIVE nueva a Greeks/GEX;
- no se inventa OrderFlow histórico para Multi;
- no se añaden workers permanentes;
- no se reintroducen imágenes/PDF pesados en Telegram.

---

## Rollback

Si aparece una regresión crítica inesperada tras el deploy, volver al commit/tag 17.5.10.9 completo. No mezclar archivos de R.2 con archivos parciales de R/R.1 durante rollback.
