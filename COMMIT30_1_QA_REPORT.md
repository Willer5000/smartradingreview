# Commit 30.1 — QA Report corregido

## Suite actual de aceptación

- **71 passed** en la suite actual de comportamiento/routing/Safety seleccionada.
- Top-level Python: **276 módulos compilados, 0 errores**.
- JavaScript syntax: PASS en `static/futures.js`, `static/script.js`, `static/chart_workspace.js`, `static/market_maker_frontend.js`.

## Suite histórica ampliada

Se ejecutó además una suite más amplia para detectar regresiones heredadas:

- **89 passed / 7 failed**.
- 6 fallos pertenecen a `test_commit24_repair.py`, que exige la antigua política Commit24 donde un Q paralelo podía promover por sí solo (`one-of-ten`). Esa autoridad fue eliminada deliberadamente en Commit25+ y esos tests ya no representan el contrato actual.
- 1 fallo pertenece a `test_rc9_7_15_entry_location_engine.py::test_long_at_ceiling_near_market_zone_is_penalized_before_timing_gate`, preexistente antes de Commit30.1: espera `location_adjustment < 0` pero el motor actual selecciona una zona primaria de reacción con ajuste positivo. Commit30.1 no modifica esa lógica.
- Los tests de deploy de Commit28/29 que exigen literalmente sus entrypoints también son incompatibles por diseño con un deploy Commit30.1 y no se usan como criterio funcional de aceptación.

## Contratos verificados en 30.1

1. F30 Vol1.05 pasa routing; Vol0.99 falla; ADX19.9 sigue fallando.
2. Safety, RR y ATR hard guards no cambian.
3. `DIRECTIONAL_IMPULSE` sigue siendo contexto, no publicación 1h.
4. Evento 1h→30m persiste hasta ACK exitoso.
5. Same-symbol 30m puede recalcular la misma vela cerrada una sola vez tras nuevo contexto 1h.
6. UI/background cooldown no puede descartar el bridge ya seleccionado; RSS/memory y heavy lock siguen mandatorios.
7. El motivo exacto del Champion se conserva y precede al genérico `NO_VALIDATED_LIVE_ROUTE`.
8. El detector de régimen recibe volumen real.
9. Deploy files apuntan a `commit30_1_main_entrypoint:app`.
10. No se crea autoridad LIVE 1h ni Multi fast.

## Interpretación

El criterio de aceptación de Commit30.1 es la suite actual de comportamiento + seguridad/routing. Los fallos históricos se conservan visibles como deuda técnica/contratos superados; no se modificaron para hacerlos pasar artificialmente.
