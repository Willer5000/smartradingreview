# SmartTradingReview — recuperación integral de confirmaciones (candidato post-36)

## ADVERTENCIA ANTES DE REEMPLAZAR EL REPOSITORIO

**NO borres el repositorio remoto a ciegas.** Este ZIP contiene el árbol completo de los archivos recuperables a partir de los **dos respaldos proporcionados**; se utilizó el más reciente (`smartradingreview-main (15).zip`, fecha interna 10/10/2026), integrando los módulos completos posteriores 34.2, 34.3, 34.4, 34.5, 34.6, 35 y 36 que ya habías recibido y los cambios de recuperación presentes en este paquete. **No es una descarga verificada del HEAD actual de GitHub.** Si alguien añadió archivos al remoto posteriormente, reemplazar todo sin comparar los perdería.

**No hemos accedido a Supabase ni a Render con credenciales**, ni se ha probado el comportamiento real de 512 MB/24 h. Este paquete es candidato de validación, **NO hay garantía absoluta de eliminación de OOM/502 o entrega instantánea de Telegram**. No requiere nueva tabla ni migraciones SQL: reutiliza `runtime_snapshots_v1` existente.

## Qué se corrigió

1. **Outbox oficial independiente por señal.** Además del snapshot agregado histórico, cada nueva señal con `signal_id` se guarda en Supabase, como fila independiente `official_confirmed_v37 / <signal_id>`, **antes de intentar enviarla a Telegram**. Si no se comprueba la persistencia remota, la alerta queda pendiente, sin fingir éxito. La señal no se genera de nuevo por consultar el registro.
2. **Paridad web/Telegram.** Los paneles de `Confirmadas` y `Vigentes` de Futures y Multi-Activo consultan las señales oficiales persistidas, incluso si un OOM o un despliegue perdió el caché del proceso. El índice remoto es acotado a 120 elementos y se refresca cada 120 s en **un worker ya existente**, no en cada solicitud web. En Spot las confirmaciones oficiales también se proyectan dentro de `/api/previous_signals` y `/api/spot/signals/vigent`.
3. **Sin alertas por estado Vigente.** Telegram anuncia únicamente **nuevas señales confirmadas**. Tras una vela de confirmación, la misma señal sólo puede figurar en Vigentes mientras conserve `valid_until` técnico y validez; no genera una segunda alerta de confirmación ni modifica TP/SL.
4. **Enlace individual fiable.** `/signal/<signal_id>?market=futures|multiasset|spot` presenta una página independiente del motor pesado: mercado, símbolo, tiempo, Entry, SL, TP, confianza, vigencia y, para Futures/Multi-Activo técnicamente válidas y con sesión autenticada, botón de guardado al backend original. El backend valida de nuevo el registro antes de guardar, sin confiar en niveles suministrados por el navegador. Señal expirada: historial informativo sin guardar ni operar.
5. **Separación ligera UI/motor.** Se conservan los gráficos y recomendaciones de commits 34–36; la consulta del índice de confirmaciones se ejecuta únicamente en el bucle ya existente `futures_standard_alert_loop`, cada ~120 s y cacheada. No se crea un nuevo hilo permanente. El frontend no necesita recalcular especialistas para visualizar una tarjeta.
6. **No se modifican los Safety ni los comités de Entry, SL y TP.** Tampoco se promueven las cuatro familias del Commit 34 sin backtest IS/OOS. No se reduce el umbral de publicación para producir señales artificialmente.

## Archivos críticos

- `app.py`: motor/servidor completo (Commit 36 + integración de recuperación).
- `official_signal_store.py`: nuevo almacenamiento por-ID, índice remoto acotado y lecturas.
- `runtime_persistence.py`: persistidor existente de Commit 36.
- `templates/official_signal.html`: página ligera para el enlace real de cada señal.
- `templates/index.html`, `static/script.js`, `static/futures.js`, `static/multiasset_display_core.js`: pantallas consolidadas de commits 34–35.
- `tests/test_commit37_official_delivery_recovery.py`: pruebas nuevas del contrato oficial.
- Todos los demás archivos del respaldo más reciente del usuario, salvo basura generada de caché/pytest.

## Pruebas ejecutadas EN ENTORNO LOCAL

```
PYTHONPATH=. pytest -q tests/*.py
# 71 passed, 6 subtests passed; 1 warning de deprecación en supabase_client.py
python -m py_compile app.py runtime_persistence.py official_signal_store.py
node --check static/script.js
node --check static/futures.js
node --check static/multiasset_display_core.js
```

Estas pruebas usan dobles de BD y eventos sintéticos; no prueban Render/Supabase/Telegram reales, latencia ni presión de memoria total a 512 MB. El presupuesto contractual sigue siendo RAM Render <=512 MB, transferencia Render <=5 GB/mes, egress Supabase <=5 GB/mes, base Supabase <=500 MB; vigilar métricas reales.

## INSTALACIÓN EN UN SOLO COMMIT (sin perder trabajo)

1. En GitHub, **crea una rama de respaldo** apuntando al SHA desplegado (por ejemplo `respaldo-antes-recuperacion`) y apunta su SHA. No borres los archivos remotos hasta comparar. GitHub conserva el historial, pero un borrado masivo es innecesario y riesgoso.
2. **Descomprime** el ZIP. Copia el contenido interno de `smartradingreview-main/`, no el ZIP, a una carpeta local nueva. Conserva `render.yaml`, `Procfile`, `build.sh`, `static/`, `templates/`, `.gitignore` y módulos auxiliares. **No sobrescribas `.git`** de tu clon.
3. Opción segura: `git clone https://github.com/Willer5000/smartradingreview.git`, crea rama, compara archivos del ZIP con el árbol remoto y aplica las diferencias compatibles. Para trabajar en GitHub Web VS Code, arrastrar cientos de archivos o carpetas puede no funcionar en todos los navegadores; si falla, usa VS Code local o el editor web de GitHub por lotes. No borres el contenido completo del remoto antes de comprobar que todos los archivos se cargaron.
4. Ejecuta pruebas (comandos anteriores) en local. Comprueba que las credenciales siguen configuradas en **Render Environment**, porque `.env` real no está ni debe estar en este ZIP.
5. Consolida la intervención en **un único commit**, prueba en rama o entorno de staging si está disponible y despliega.
6. **No habilites de nuevo Scientist pesado en una instancia gratuita de 512 MB.** Mantén el worker de aprendizaje liviano y la lógica de trading existente.

## Pruebas imprescindibles TRAS desplegar

- Render: 24 h y varios cierres de vela (30m, 1h, 2h y 1D), registrar picos RSS/cgroup y reinicios 502; si falla, detener la liberación y revertir a SHA anterior mediante Render.
- Cada señal NUEVA confirmada en Telegram debe tener `signal_id` y la misma geometría en `GET /api/signals/official/<id>?market=...`; la web debe mostrarla en `Confirmadas` mientras corresponda a su vela. Después debe pasar a `Vigentes` únicamente si existe validez técnica original.
- Abrir desde Telegram `https://smartradingreview.onrender.com/signal/<id>?market=futures`: se debe ver un registro concreto, NO redireccionar ciegamente a un panel genérico. Probar Guardar mientras es válida y estar autenticado; esperar rechazo si ha vencido.
- Repetir en Multi-Activo y Spot (Spot mantiene su flujo específico de guardado/portafolio). Consultas del índice NO deben crear nuevas señales ni incrementar el número de llamadas a especialistas.
- Revisión especial de los cuatro IDs proporcionados por el usuario: SOL 2h `1fc0f37196da79089a6a2d23`; XRP 2h `fb48ae6c11e89a5c6f1a6faf`; SEI 30m `5aae16955aa75933a2cf531d`; SOL 1h `250f0204cdd88ed908673c20`. **Si ya expiraron o su anterior outbox quedó destruido, NO reaparecerán como trades nuevos.** La nueva persistencia por ID aplica a señales emitidas tras instalar este código.
- Comparar número de ciclos de análisis programados y ejecutados contra el commit previo para constatar ausencia de regresión de frecuencia. Si hay OOM, no bajar Safety ni «forzar» señales: el cuello de botella requiere liberar trabajo no crítico o ampliar recursos.

## Condiciones de reversión

Cualquier nuevo OOM/502, envío duplicado de Telegram, confirmación web no recuperable, señal expirada guardable o regresión comprobada de frecuencia exige rollback al SHA de respaldo (Render Deploys, sin borrar base de datos). **No cambies el `valid_until` de una señal ni promociones una estrategia para esconder un problema de observabilidad.**
