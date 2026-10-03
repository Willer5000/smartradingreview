# Commit 21.3 Fix — auditoría de causa raíz

## Evidencia nueva de la ejecución del usuario

1. El navegador sigue cargando `script.js` y `futures.js` con `v=20261003-COMMIT21-1-FIX`. Por lo tanto, la página observada no estaba ejecutando realmente el frontend de Commit 21.2. Esta es la causa más directa de que no se viera el cambio visual de 21.2.
2. Se observan múltiples lecturas de `/signals/active`, riesgo y carril de oportunidades que permanecen 15 s esperando y vuelven a intentarse. Eso compite con el único slot pesado de Render y degrada la respuesta de la página.
3. `updatePreviousSignals` tenía una defensa que podía limpiar `previousLoading` y permitir otra solicitud aunque la anterior todavía estuviera en vuelo.
4. El carril visual podía recibir más de una descarga para la misma celda durante navegación/cambio de selector.
5. El HTML de `/futures` y `/multiasset` no tenía un contrato explícito `no-store`; un navegador podía conservar la plantilla antigua con los query-bust de 21.1.

## Correcciones 21.3

- `index.html` pasa a `COMMIT21-3-FIX` para `script.js` y `futures.js`.
- Las páginas `/`, `/futures` y `/multiasset` responden con `Cache-Control: no-store, no-cache`.
- Se incorpora single-flight + TTL de 45 s para visuales ligeros.
- Los carriles Futures reciben cooldowns después de timeout/error y ya no fuerzan una nueva lectura inmediatamente.
- `updatePreviousSignals` conserva la petición en vuelo en vez de resetear el flag.
- `loadFuturesOpportunities96` tiene guard de concurrencia y cooldown.
- El perfil de riesgo deja de golpear el backend cada vez que un request lento falla.
- Arranque de carriles escalonado para no lanzar Vigentes + Confirmadas + Activas + Correlación juntas.

## Calidad de señales

Este commit **no afirma** que cada hipótesis pase a Premium. Su objetivo es que el motor 21.2 pueda ejecutarse realmente y que sus resultados sean visibles sin que el navegador/Render los oculte detrás de una tormenta de lecturas. Safety, TP, SL y R/R permanecen sin cambios.

## Qué evidencia debe aparecer después del despliegue

- DevTools/HTML debe mostrar `COMMIT21-3-FIX`, no `COMMIT21-1-FIX`.
- Debe aparecer al menos una solicitud `/api/futures/visuals?...` al abrir Futuros y su respuesta debe ser `200` con `df`.
- Después de un timeout de un carril debe verse `[21.3] ... cooldown` y no una repetición inmediata del mismo request.
- El endpoint de salud debe reportar versión `21.3`.
