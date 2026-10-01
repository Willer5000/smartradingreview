# Commit 18.1 — Multi-Asset UI / Heavy Slot Repair

Base requerida: **Commit 18 Main (`0617268f64ca7cf8ae9040ba00ab509bec57d52e`)**.

## Diagnóstico confirmado por logs del deploy

La UI Multi sí marcaba prioridad interactiva, pero el worker heavy se construía como:

`multiasset-ui:CL-USDT:4h`

mientras `_acquire_heavy_analysis()` sólo reconocía como interactivos:

`futures-ui:` / `spot-ui:` / `multi-ui:`

Resultado: el propio job Multi era clasificado como background y cedía ante la prioridad que él mismo acababa de marcar:

`[PRIORITY] multiasset-ui:CL-USDT:4h: cede turno a la interfaz activa`

Por eso el POST `/api/multiasset/analyze` quedaba en 202 y nunca producía recomendación rica.

Además, el Display Lane usaba `FuturesAnalysis.get_kucoin_data()`, que exige al menos 100 velas reales. Algunos contratos Multi pueden no entregar ese mínimo en esa consulta aunque el router Multi sí disponga de suficientes velas cerradas. El endpoint devolvía HTTP 200 pero un payload mínimo `available:false`, dejando el panel sin gráfico.

## Cambios 18.1

1. `multiasset-ui:` queda reconocido como owner interactivo por compatibilidad.
2. El scheduler Multi genera canónicamente `multi-ui:<symbol>:<tf>`.
3. Display Lane mantiene como primera fuente el loader normal de velas reales.
4. Si esa fuente no llega al mínimo heavy, **sólo la UI** reutiliza `_router_fetch()` del propio Multi como fallback de velas REALES CERRADAS (mínimo 30). No crea señales ni autoridad de trading.
5. El Display Lane nunca usa datos sintéticos, no llama IA, no escribe Supabase y no ejecuta comités.
6. El frontend cachea hasta 4 celdas durante 45 s para que los retries del POST heavy no vuelvan a descargar/renderizar el gráfico cada 5 s.
7. Si una fuente de mercado falla, se muestra un mensaje explícito en vez de una zona negra silenciosa.
8. Cache-bust actualizado a `20261001-COMMIT18-1-MULTI-UI`.

## Archivos a reemplazar

- `app.py`
- `static/script.js`
- `templates/index.html`

Son archivos completos, listos para arrastrar en VSCode Web.

## Qué NO modifica

Commit 18.1 es un hotfix de runtime/UI. No cambia:

- Strategy Bank;
- Operational Intelligence;
- Entry/SL/TP committees;
- Safety;
- leverage;
- Guardian;
- Research/OOS;
- clasificación Premium/Manual;
- lógica de Telegram.

## QA post-deploy

1. Ctrl+F5.
2. Abrir `/multiasset`.
3. Seleccionar `CL-USDT · 4h` y pulsar Analizar.
4. El gráfico de velas debe aparecer aunque el POST heavy todavía esté 202.
5. En logs ya **no** debe aparecer `multiasset-ui:... cede turno a la interfaz activa`.
6. Debe aparecer un owner `multi-ui:CL-USDT:4h` entrando al slot o, si el slot está realmente ocupado por otro job ya iniciado, diferirse sin auto-bloquearse.
7. Cuando finalice el heavy job deben aparecer recomendación y capas completas de Multi.
8. Cambiar a XAG/QQQ/etc.: ningún panel puede conservar identidad de CL o BTC.

Los errores `contentScript.js ... selectors_instance_found` y `Tracking Prevention` pertenecen al navegador/extensiones; no son la causa del auto-bloqueo del backend Multi.
