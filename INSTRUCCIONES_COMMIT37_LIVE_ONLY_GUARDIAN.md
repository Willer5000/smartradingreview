# SmartTradingReview — paquete de repositorio completo C37 LIVE ONLY + Guardian

## Base y alcance exactos

Este paquete está construido **sobre la reconstrucción completa de señales oficiales que anteriormente sí mostró Confirmadas y Telegram**, obtenida de los respaldos `smartradingreview-main (15)` y `(14)` y del paquete de recuperación individual `SmartTradingReview_REPOSITORIO_COMPLETO_RECUPERACION_CONFIRMADAS.zip` (equivalente a la línea `Restore all 111026`). Los ZIP `(15)(2)` y `(14)(2)` recibidos en este turno fueron examinados y conservados como referencias de origen. No se parte del Commit 36R.1, cuyo comportamiento de visibilidad no fue validado en producción.

No se redujo **ningún símbolo ni temporalidad**. No se modificaron estrategias, comités Entry/SL/TP, ocho Safety, cierre canónico, política de publicación, persistencia individual `official_signal_store.py`, JSON de Confirmadas/Vigentes, enlaces `/signal/<id>`, Telegram oficial, página de señales oficiales, guardado personal ni gráficos de velas/indicadores. Los archivos `futures_system.py`, `multiasset_system.py`, `official_signal_store.py`, `static/futures.js`, `templates/official_signal.html`, `portfolio_guardian.py`, `saved_signals.py`, `runtime_persistence.py` y `static/chart_workspace.js` son **idénticos byte a byte** a la base restaurada.

## Cambios de operación

1. **LIVE_ONLY_RUNTIME=1** por defecto. Desactiva el arranque de `learning_worker_loop` (que recalculaba statistics, economics, governance y autopilot) y del AI Learning Scientist; elimina el disparo diario Q6 de investigación. Los registros esenciales de Entry/TP/SL permanecen gestionados por `saved_futures_lifecycle_loop`, los monitores LIVE, las señales oficiales y Guardian. **La recalibración automática LIVE/SHADOW deja de ejecutarse** en este servidor. Para reactivarla se necesita investigar una arquitectura externa en SmartTradingResearch; NO poner LIVE_ONLY_RUNTIME=0 en este Render pequeño por costumbre.
2. **Consejo IA y Asistente IA permanecen**. No se alteran las APIs de asesoramiento. Solo se detiene el entrenamiento/investigación automática; los proveedores externos podrían igualmente fallar.
3. **Vela abierta conservada**: análisis profundo provisional en caché por TF (Futures: 30m→3min, 1h→5min, 2h→8min, 4h→12min, 12h→20min, 1D→30min; Spot: 4h→12min, 12h→20min, 1D→30min, 1W→60min). Gráfico, precio visual y señales confirmadas siguen sus carriles previos; estos TTL **no retrasan los análisis oficiales de cierre**. La combinación activa es compartida por los usuarios de la instancia; pestañas ocultas no desencadenan análisis profundos, tampoco en Spot.
4. **Guardian sigue activo aun con el navegador cerrado**. Reutiliza hasta 4min las 32 velas cerradas para análisis de estructura, mientras actualiza el mark price de Futures/Multi mediante una llamada ligera hasta cada 25s por símbolo (caché compartida). La vigilancia de posiciones `entry_touched` funciona cada 45s y se acelera a ~15s cuando el precio reciente se aproxima al SL o TP en <35% de la distancia Entry-SL. Es un intervalo objetivo best-effort: no es una garantía de segundos de latencia; depende de Render, proveedor y red. Si el precio live no se obtiene, `price_is_live=false` diferencia el snapshot no actualizado.
5. **Sin OHLCV Guardian paralelo al motor**. Si ya se está ejecutando un trabajo pesado, Guardian reutiliza las velas compactas aún válidas y actualiza sólo el precio, evitando crear otro DataFrame concurrente. Si no existen velas válidas, informa que no hay snapshot y no fabrica una recomendación.
6. **Menos bloqueos por navegación/bots**. Solo navegación humana provoca 6s de preferencia UI; agentes `crawler`, `bot`, `read-aloud` etc. no pausan el scheduler. Los análisis oficiales al cierre siguen teniendo prioridad en sus controles anteriores.
7. **Telegram**: la alerta titulada `NUEVA SEÑAL CONFIRMADA` sigue dependiendo exclusivamente de una **nueva confirmación**, no de pasar a Vigentes. Alertas de gestión de Guardian, si están habilitadas para el usuario, son una categoría distinta, no duplicados de nueva señal.

## Archivos cambiados respecto de la base verificada

- `app.py` (secciones solo LIVE, caché exploratoria, Guardian, prioridades de navegación).
- `static/script.js` (evita iniciar análisis pesado con la pestaña oculta, también en Spot).
- `render.yaml` (variables LIVE/Guardian; los secretos siguen en Render, fuera del ZIP).
- `tests/test_commit37_live_only_guardian.py` (regresiones nuevas).
- Este documento.

**Nunca reemplazar `app.py` de este ZIP en un HEAD distinto sin comparar antes.** Esta entrega es un árbol completo y conserva exactamente los sistemas oficiales de su base, no adapta automáticamente modificaciones posteriores que hayas desplegado.

## Instalación segura desde VS Code Web de GitHub

1. **Guardar un backup antes de borrar nada.** Crear una rama `backup-pre-live-only` a partir del commit de producción, o guardar ZIP y SHA de `HEAD`. Eliminar archivos sin backup puede destruir configuraciones o cambios nuevos.
2. Descargar ZIP de este paquete y **descomprimirlo localmente**. Arrastrar el **contenido de su raíz**, NO una carpeta contenedora `smartradingreview-main`, a la raíz de GitHub. Comprobar que queda `app.py` directamente en la raíz. No subir el ZIP como un archivo dentro del repo.
3. No eliminar la carpeta `.git` ni credenciales/secretos de Render y Supabase. El paquete no incluye tokens. Si estás reemplazando todos los archivos, comparar `.github` y metadatos antes de borrarlos.
4. Verificar los cambios con `git diff --stat`, `git status`, y revisar que **no** se hayan eliminado módulos `official_signal_store.py`, `futures_universe.py`, `multiasset_system.py`, plantillas ni assets de gráficos.
5. Ejecutar `python -m py_compile app.py` y `python -m pytest -q tests/test_commit37_live_only_guardian.py tests/test_commit37_official_delivery_recovery.py tests/test_commit35_core.py tests/test_commit36_resource_signal_parity.py tests/test_commit34_5_regression.py` (dependiendo de dependencias locales). Desplegar en **un solo commit**. No se hizo un commit remoto ni un deploy desde esta conversación.

## Validación OBLIGATORIA después del deploy

- En Render, revisar `/api/commit35/resource-health`, `/health` y los gráficos de memoria del contenedor durante **varias ventanas de cierre 30m, 1h, 2h, 4h y al menos un cierre Spot 1D**. Objetivo: proceso y cgroup sin superar 512MiB. Los controles de memoria existentes continúan protegiendo, pero si un único análisis completo requiere más de 512MiB, **este cambio no puede garantizar evitar otro OOM**.
- Cotejar **cada** Telegram `NUEVA SEÑAL CONFIRMADA` con el **mismo `signal_id`** en el registro oficial y el panel Confirmadas (durante 1 vela), posteriormente en Vigentes mientras sea válida. Usar `/api/signals/official/<signal_id>?market=futures` o `market=multiasset` para inspección (no genera nuevos análisis). No etiquetar vencidas como nuevas ni enviarlas otra vez.
- Probar Guardar en Futures y Multi-Activo; verificar seguimiento Guardian desde `saved_signals` con `entry_touched`, también cerrando la pestaña web. Las alertas de manejo/EXIT de Guardian no son mensajes de nueva confirmación.
- Revisar consumo mensual del Dashboard: **Render 5GB/mes, Supabase egress 5GB/mes, Supabase database 500MB**; estos presupuestos no pueden acreditarse sin métricas reales de esos proveedores.
- Si Render vuelve a reiniciar por OOM, recuperar métricas 2–3 min antes del reinicio (RSS, `memory.current`, `memory.stat inactive_file`, `memory.events oom_kill`), analizar qué tarea estaba admitida y revertir el commit si falla el núcleo.

## Rollback

Revertir a la rama de backup o al SHA que funcionaba para señales. Un cambio de archivos de la aplicación no debe borrar registros persistentes de Supabase; mantener la persistencia anterior. **No usar un rollback a Commit 35/36 si en esas versiones Confirmadas y Telegram estaban desincronizados.**

## Resultados de laboratorio (alcance)

Pruebas locales seleccionadas: **43/43 satisfactorias** (sin claves ni llamadas reales), sintaxis Python y JavaScript correcta. Se compararon los AST de funciones oficiales y los módulos operativos: no se cambiaron. **No se efectuó una prueba de carga 512 MB en Render ni se verificó entrega real del bot o paridad Supabase en producción**. El paquete es instalable para una validación controlada; no una garantía de disponibilidad constante de Render Free.
