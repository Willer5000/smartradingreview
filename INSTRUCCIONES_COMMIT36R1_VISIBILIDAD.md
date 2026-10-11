# SmartTradingReview — Commit 36R.1 · Visibilidad oficial sin ocultamientos

**Base:** paquete 36R `SmartTradingReview_COMMIT36R_REPOSITORIO_COMPLETO_ESTABILIDAD.zip` (derivado del Restore all 111026). **No se ha desplegado en Render ni alterado Supabase.** Verificar la base exacta antes de reemplazar `app.py` completo.

## Diagnóstico comprobable

Los logs del 11/10/2026 12:46–12:49 UTC registran `GET /api/futures/signals/previous` HTTP 200 de ~70.5 KB, `GET /api/futures/signals/active` HTTP 200 ~71.8 KB y `GET /api/multiasset/signals/previous` HTTP 200 ~1.35 KB. Esto **no prueba** si el JSON contenía una señal particular: se necesita consultar el campo `signals` / su `signal_id`. Tampoco demuestra que la señal siga técnicamente válida.

El código de la base 36R tiene dos mecanismos capaces de **ocultar tarjetas** aunque el endpoint devuelva señales: `const signals = allSignals.filter(sig => !_isSignalSavedByCurrentUser(sig))` en Confirmadas y Vigentes, y la limpieza con spinner al comenzar cada petición. Hay además retraso de hasta ~120 s antes de la primera reconstrucción del índice oficial tras reinicio; `persist_official()` escribía a Supabase sin actualizar la copia leída por las tarjetas.

## Archivos completos incluidos para reemplazar

- `app.py`: recuperar el índice oficial en el worker de Telegram **existente** al arrancar; leer historial de confirmaciones realmente enviadas desde el índice acotado, incluso después de perder la memoria local; incluir historial en Futures. **No** ejecutar estrategias en endpoints de lectura ni anunciar vigentes como nuevas confirmadas.
- `official_signal_store.py`: después de confirmar el guardado remoto de una señal aprobada, actualizar el índice en memoria sin peticiones extra; fusionar índices remotos con escrituras concurrentes en lugar de reemplazarlas. Mantiene 120 registros como máximo, TTL remoto original y falla cerrada si Supabase no confirma la persistencia.
- `static/futures.js`: en Futures **y** Multi-Activo dejar visibles las señales globales aunque el usuario las tenga en Guardadas; sustituir botones por `Ya guardada` para no duplicar. No bloquear tarjetas esperando una consulta de Guardadas ni borrarlas mientras una actualización está en curso. Mostrar historial no operativo de alertas vencidas también en Futures.
- `templates/index.html`: versión nueva del JS para evitar caché antigua en navegador.
- `tests/test_commit36r1_official_visibility.py`: regresiones de persistencia, índice, carrera de refresco, no ocultamiento de tarjetas, historial no operativo y Telegram solo Confirmadas.

No se modifica `futures_system.py`, `multiasset_system.py`, `local_resilience.py`, `render.yaml`, `static/script.js`, las estrategias, ocho Safety, comités Entry/SL/TP, temporalidades o lógica de autorizar señales.

## Instalación: UN solo commit

1. Guardar el SHA **actual** de `main` y, si es posible, crear rama de respaldo. No borrar archivos del repositorio.
2. Comprobar que el código presente corresponde a 36R. **Si hubo cambios posteriores, fusionar**: no sobrescribir a ciegas un `app.py` modificado después de 36R.
3. Copiar exactamente los cinco archivos completos anteriores a sus respectivas rutas.
4. Antes de desplegar, ejecutar:

   ```bash
   python -m py_compile app.py official_signal_store.py
   node --check static/futures.js
   python -m pytest -q tests/test_commit36r1_official_visibility.py tests/test_commit37_official_delivery_recovery.py
   ```

5. Realizar un solo commit, por ejemplo: `Commit 36R.1 - conservar visibilidad de confirmadas y vigentes`.

## Verificación funcional después del despliegue

- En el momento de una nueva confirmación oficial, comparar el `signal_id` del mensaje Telegram con `/api/signals/official/<id>?market=futures` o `market=multiasset` y comprobar presencia en `GET /api/<market>/signals/previous` durante la **vela confirmada**.
- Después de esa vela, comprobar `GET /api/<market>/signals/active` **solo si** el `valid_until` técnico todavía está abierto y no hay cierre por SL/TP/cancelación. No alargar la validez original.
- Si se ha guardado, la tarjeta global **permanece visible** con el distintivo «Ya guardada»; la operación personal continúa en Guardadas. No se vuelve a enviar Telegram por pasar a Vigentes.
- Una señal técnicamente vencida debe desaparecer de Confirmadas/Vigentes, pero puede aparecer durante 24 horas después del vencimiento en «Historial de alertas Telegram finalizadas», **sin** habilitar Guardar.
- Revisar gráficos y recomendaciones de Spot/Futures/Multi-Activo y RAM cgroup. Este commit no corrige todos los motivos de OOM/502 ni certifica 24/7 en Render Free; se centra en visibilidad sin nuevos trabajos pesados.

## Resultado de pruebas locales

- `pytest` del módulo nuevo + regresiones `test_commit37_official_delivery_recovery.py` y `test_commit36r_oom_safe_preservation.py`: **17 passed**.
- `pytest` de pruebas de paridad y guardado (`34.4` + `37` + `36R.1`): **30 passed** (la herramienta terminó después de imprimir el resultado y el wrapper marcó timeout; no se atribuye a una prueba fallida).
- Compilación Python y `node --check` correctos.
- **No** se ejecutó una prueba de carga real de Render ni una consulta autenticada a la Supabase del usuario.

**Rollback:** revertir los cinco archivos al SHA previo (sin borrar snapshots, operaciones guardadas ni deduplicación de Telegram).
