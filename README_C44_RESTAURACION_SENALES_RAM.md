# C44 — RESTAURACIÓN COMPLETA DESDE BASE FUNCIONAL + VISTA C43.1 + WATCHDOG

**Base exacta:** ZIP entregado por el usuario titulado `smartradingreview-main ULTIMO FUNCIONAL CON RESULTADOS POSITIVOS PERO CON PROBLEMAS DE RAM.zip`, previo a la implantación C43. El repositorio aquí es COMPLETO, no un parche.

**Problema observado el 17-10-2026:** Tras C43/C43.1, ausencia o baja frecuencia de nuevas confirmaciones Spot/Futures/Multi y de Telegram/Discord, con picos de uso cgroup de 400–428 MB y RSS Python de ~154–181 MB. La captura/log no prueba que todos los mercados debieran haber emitido una señal: contiene una tesis BTC 1h con R/R 0.01 y rechazo `ANALYSIS_ONLY`. Sí prueba que un watchdog renovaba pausas globales de 90 s en esos estados de memoria.

## Decisión de seguridad

NO reutilizar el app.py de C43: la implementación C43 comprimía/descomprimía el caché de análisis en seis puntos de lectura/escritura. No está probado que sea el único causante de la pérdida de señales; como es una transformación transversal al análisis, no se conserva en la recuperación conservadora.

NO alterar funciones de análisis de trading, comités Entry/SL/TP, filtros Safety, parámetros de publicación, generación o distribución de Telegram/Discord, ni API de guardado, expiraciones o Guardian personal.

## Cambios limitados a C44

1. **`app.py`**: únicamente una función pura `_c44_watchdog_cgroup_pressure()` y su llamada en el watchdog existente. La política global de espera usa el descuento CONSERVADOR del archivo inactivo (`inactive_file` × 50%, máximo 120MB), que YA reconocía el autorizador físico C34.6 para iniciar trabajos. Se mantiene el margen físico bruto de 80MB. Nunca se altera la reserva por temporalidad, el control de un único trabajo pesado ni la protección intra-análisis de 34.6. Si la RAM real es insuficiente, SIGUE protegiendo el contenedor y puede diferir análisis. No se puede garantizar 0 OOM con 512MB.
2. **`app.py`**: campo adicional (pasivo) `c44_watchdog_cgroup_backoff` en `/api/commit35/resource-health` para distinguir presión real del cgroup de caché de archivos.
3. **`static/script.js`**: únicamente el orden Spot previsto en C43 (por menor temporalidad y mayor vigencia). Se basa en el JS de C43; no se copia el backend C43.
4. **`static/futures.js`, `static/signal_presentation_order_c43.js`, `templates/index.html`**: únicamente orden visual C43.1 (temporalidad ascendente × vigencia descendente × riesgo ascendente) y deduplicación VISUAL por símbolo × timeframe dentro de Futures y Multi-Activo. Confirmadas/vigentes compartidas aparecen en un solo carril según vigencia y calidad, sin tocar backend, Supabase o notificaciones. Activas se manejan de manera independiente. Spot conserva orden C43 sin desempate por riesgo.
5. **`tests/`**: pruebas del comportamiento del watchdog y del orden visual.

## Por qué la RAM puede parecer alta y las señales bajas al mismo tiempo

`memory.current` incluye memoria del proceso + caché de páginas Linux + otros componentes del contenedor. El watchdog previo generaba `background backoff 90s` cuando `limit-memory.current <135MB`, sin discriminar caché recuperable. A diferencia de ese watchdog, el autorizador C34.6 de trabajos ya utilizaba el descuento conservador de `inactive_file`. Con `memory.current≈402MB` y Python `RSS≈157MB`, había una posibilidad importante de aplazamiento por caché y no por agotamiento real del heap. Si `inactive_file` está vacío, C44 NO ignora el problema; sigue aplicando backoff.

## Importante: no se garantiza la frecuencia anterior sin verificación en producción

No se alteran estándares de calidad ni se generan señales artificiales. El histórico registra también `ANALYSIS_ONLY: RR 0.01` para BTC-USDT 1h, una razón independiente y válida para no confirmar. El resultado debe verificarse durante cierres reales, junto con logs de la autoridad de publicación y de los webhooks. La coincidencia temporal con C43 no demuestra por sí sola que la compresión haya provocado todos los silencios.

## Instalación sin perder repositorio, históricos ni usuarios

1. **NO BORRAR el repositorio GitHub ni el proyecto Render.** Antes, descarga un backup del commit actual C43.1 y exporta la configuración NO secreta de Render. Los datos de Supabase son independientes del ZIP y no se deben borrar.
2. Descomprime este ZIP. Contiene carpeta raíz `smartradingreview-main/`. Dentro hay código completo, pruebas, assets y configuración. Copia SU CONTENIDO a la raíz del repo EXISTENTE, reemplazando los archivos. Evita anidar `smartradingreview-main/smartradingreview-main`.
3. Haz UN solo commit y deploy en Render. Mantén exactamente las variables privadas de Supabase, Groq/Gemini, Telegram, Discord y usuarios Guardian. Este ZIP NO contiene claves privadas.
4. Confirma que Render siga ejecutando Gunicorn con 1 worker, 2 threads, `app:app` y que las variables de memoria configuradas previamente no hayan sido sobreescritas.
5. Recarga las tres páginas con Ctrl+F5 para descargar JS nuevo.

## Cómo comprobar la recuperación

- **Spot:** cierre de vela y confirmada en la WEB + Telegram y Discord; registrar los tres estados por `signal_id` y cierre, sin exigir nuevas señales cuando Safety las rechace.
- **Futures y Multi:** confirmar que el escáner incremental cubra cierres previstos; el contador `commit36_scheduler.reasons.GLOBAL_BACKOFF` no debe crecer sin parar solo por cgroup con caché inactiva; confirmar una alerta de calidad real si se publica.
- **Guardian:** acceso con Willer, Danilo y Damir (sesiones separadas) y comprobar que sus señales guardadas, SL/TP, expiraciones y avisos sean individuales.
- **Guardado no Premium:** la API debe devolver éxito si los criterios *anteriores* lo permitían. Un HTTP 429 se investiga por endpoint y respuesta; no es sinónimo de OOM.
- **RAM:** abrir autenticado `/api/commit35/resource-health`: mirar `rss_mb`, `cgroup_used_mb`, `inactive_file_mb`, `raw_headroom_mb`, `effective_headroom_mb`, `c44_watchdog_cgroup_backoff`, y `commit36_scheduler`.

## Pruebas locales realizadas

- `python -m py_compile app.py`
- `node --check static/script.js` / `node --check static/futures.js` / `node --check static/signal_presentation_order_c43.js`
- `node tests/test_c43_1_visual_only.js` — OK
- `node tests/test_c43_visual_order.js` — OK
- `python -m pytest -q tests/test_c44_restore_and_watchdog.py` — 3 superadas
- Intento de suite de integración adicional: no finalizó dentro del tiempo disponible. No se atribuyen éxitos a esas pruebas ni se afirman pruebas de Telegram/Render reales.

## Rollback

Si el deploy falla, hacer rollback a un commit completo previamente respaldado desde Render/GitHub; preservar las bases de datos. No volver a mezclar `app.py` de C43 con el código de esta restauración sin pruebas específicas. Si hay retrocesos visibles, comparar por activo/temporalidad/cierre, `signal_id`, estado `ANALYSIS_ONLY` / oficial y respuesta del webhook antes de decidir.
