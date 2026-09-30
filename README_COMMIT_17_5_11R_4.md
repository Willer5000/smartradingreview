# COMMIT 17.5.11R.4 — Manual Lane Accionable + Geometry Invariant + Greeks Fallback

**Base requerida:** `17.5.11R.3` ya desplegado.  
**Objetivo:** cerrar la regresión que dejaba hipótesis visibles sin Entry/SL/TP o sin botón de guardado, sin tocar los thresholds de señal Premium ni fabricar una lluvia de señales.

## Diagnóstico exacto de R.3

Se encontraron dos bugs concretos, no un simple problema de Safety:

1. Los dos bloques de geometría manual de R.3 intentaban leer `decision_audit` **antes de que `decision_audit` fuese construido**. El error quedaba atrapado por `try/except`, por lo que muchas tesis LONG/SHORT sobrevivían al frontend pero quedaban con `SL=0/TP=0`.
2. `_futures_directional_hidden_candidates()` podía volver a poner `manual_save_allowed=False` si el `signal_id` no coincidía con el representante elegido por el arbitraje visual. Eso explica casos con Entry/SL/TP completos pero sin botón de guardado.

## Contrato final R.4

- Una tesis LONG/SHORT ya gobernada **no puede aparecer en “Por qué no aparecen otras señales” sin geometría coherente**.
- Primero se conserva la geometría original del comité si es válida.
- Si falta, se intenta la ruta normal/estructural de R.3.
- Como último recurso manual se completa con estructura disponible (soportes/resistencias, OB, FVG, perfil de volumen) y ATR sólo como normalizador/clearance.
- Esa geometría fallback queda `ANALYSIS_ONLY`, `USER_MANUAL_ANALYSIS_ONLY`, riesgo alto y **jamás se autopromueve a Premium**.
- Una hipótesis visible y confirmada con geometría válida se puede guardar bajo riesgo del usuario aunque Safety/Premium no la autorice oficialmente.
- El arbitraje de “representante” ya no puede quitar el botón de guardado.
- El endpoint de guardado reconstruye/verifica la geometría canónica antes de validar el guardado, para evitar desacuerdo UI↔backend.
- Las filas incompletas/stale no se muestran como ruido; esperan al siguiente refresh.

## Delta / Gamma / Theta

R.3 todavía podía quedar vacío cuando el endpoint de opciones no encontraba cadena ni spot en caché. R.4 añade un último fallback UI:

1. pide el contexto de opciones una sola vez;
2. si no hay curvas utilizables, obtiene **sólo el precio** con `/api/price?...&market=futures`;
3. dibuja localmente la superficie Black‑Scholes teórica de Delta/Gamma/Theta.

No inventa Call Wall, Put Wall, Gamma Wall, Zero-Gamma ni inventario real de dealers. Es contexto teórico SHADOW.

## Archivos a reemplazar

Sólo cuatro archivos sobre tu `17.5.11R.3` actual:

1. `app.py`
2. `static/futures.js`
3. `static/market_maker_frontend.js`
4. `templates/index.html`

No reemplaces otros archivos de R.3.

## Implementación

1. Haz backup/branch de tu R.3 actual.
2. Descomprime este ZIP.
3. Arrastra los cuatro archivos respetando `static/` y `templates/`.
4. Un único commit sugerido: `Commit 17.5.11R.4 - actionable manual lane final geometry`.
5. Push y espera `Live` en Render.
6. Haz `Ctrl+F5`.
7. Abre `/futures` y verifica “Por qué no aparecen otras señales”. Las filas visibles deben tener Entry + SL + TP + R/R y botones de guardado.
8. Guarda una hipótesis de riesgo alto y verifica que aparezca en Guardadas y que Guardian pueda seguirla.
9. Abre Delta/Gamma/Theta. Si no hay cadena compatible, debe aparecer la curva teórica en lugar del panel vacío.

## Qué NO cambia

- Safety Premium.
- Pisol/techo R/R oficiales.
- Estrategias validadas de R.1/R.2.
- Política de Telegram oficial.
- Reglas de publicación Premium.
- Multi-Activo ya reparado en R.3.

R.4 no aumenta frecuencia bajando calidad. Convierte en **accionables** las hipótesis que el sistema ya detectó y evita que un bug de geometría/representación las haga inútiles.
