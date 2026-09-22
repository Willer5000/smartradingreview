# COMMIT 10 · Auditoría final de Fase 1

Fecha de auditoría: 2026-09-22
Base auditada: RC9.8.8 sobre la cadena RC9.7.14 → RC9.8.8.
Objetivo: congelar una Fase 1 estable antes de transformar el producto en aplicación de escritorio.

## Dictamen de release

**APTO PARA CIERRE DE FASE 1 CON HARDENING DE COMMIT 10.**

No se encontró motivo técnico para reescribir el motor de trading antes de Fase 2. Los cambios de Commit 10 son de endurecimiento de infraestructura/seguridad/IA y no alteran dirección, Entry, SL, TP, Safety, R:R ni gobernanza de aprendizaje.

Hay un requisito obligatorio antes de declarar el release cerrado: ejecutar `schema_commit10_final_security_lockdown.sql` después de confirmar que Render usa una key Supabase `service_role`. La auditoría del proyecto Supabase detectó tablas públicas sin RLS.

---

## 1. Infraestructura y cuotas

### Render

Estado: **PASS CON MONITOREO**.

- El workspace está ahora en Pro; el plan de workspace da margen de bandwidth, pero no cambia por sí mismo el plan de compute del servicio.
- RC9.8.7 eliminó tráfico redundante sin reducir análisis.
- Se encontró una inconsistencia en `render.yaml`: `FUTURES_DATA_CACHE_MAX_ENTRIES=2` estaba anulando el nuevo default 8 de RC9.8.7. Commit 10 lo corrige a 8 y fija microstructure cache 20.
- Se mantienen LOW_MEMORY_MODE, un worker y dos threads; no se aumenta agresivamente memoria/threads.
- Recomendación de operación: medir `Service-Initiated` y `HTTP Responses` a 24h/72h/7d tras Commit 10.

### Supabase

Estado: **PASS DE CAPACIDAD / FIX OBLIGATORIO DE SEGURIDAD**.

Auditoría directa del proyecto conectado:

- Plan: Free.
- Estado: ACTIVE_HEALTHY.
- Tamaño DB observado: **155 MB** de 500 MB incluidos (~31%).
- Filas vivas aproximadas: **71.250**.
- Conexiones observadas durante la auditoría: 6.
- Tabla principal `signals`: ~19.388 filas / ~112 MB.
- `signal_indicators`: ~39.590 filas / ~12,6 MB.
- `signal_results`: ~2.655 filas / ~2,9 MB.
- `research_candidate_memory_v1`: ~2.003 filas / ~1,6 MB.

El almacenamiento está actualmente muy por debajo del límite Free. El código ya tiene FIFO/cleanup y guardas de egress. La configuración de aplicación queda protegida con `FREE_PLAN_LOCKDOWN=1` y `MAIN_SUPABASE_DAILY_BUDGET_MB=12`; Research conserva su investigación lenta y sus propios presupuestos. Estos presupuestos son guardas de aplicación, no el contador oficial de facturación de Supabase.

**Hallazgo crítico de seguridad:** 26 tablas públicas tenían RLS desactivado. También se detectaron RPCs SECURITY DEFINER ejecutables por roles públicos y una vista SECURITY DEFINER. Commit 10 entrega una migración de lockdown; no se ejecuta automáticamente para evitar bloquear la aplicación si el despliegue no usa service-role.

### Groq

Estado: **PASS CON FUSIBLE LOCAL**.

- Modelo por defecto actual: `openai/gpt-oss-20b`.
- El sistema ya tiene backoff ante 429 y cuotas por tipo de uso.
- Se detectó que una comprobación de cuota podía hacer múltiples lecturas Supabase. Commit 10 las consolida en **una sola lectura acotada por ventana de 24 h**.
- Commit 10 añade presupuesto protector de **160.000 tokens/día**, con reserva de 8.000, por debajo del TPD publicado para `gpt-oss-20b` en la tabla pública actual.
- IDs Groq retirados en 2026 son normalizados automáticamente a modelos actuales para evitar que una variable vieja de Render rompa el Asistente.

No se realiza ninguna llamada Groq real durante QA para no consumir cuota; se valida contrato, modelo, fusibles y fallback.

---

## 2. Auditoría técnica de trading

Estado: **PASS**.

Se verificó que permanecen los guardrails principales:

- `minimum_execution_safety = 65`.
- `minimum_publication_execution_safety = 75`.
- `minimum_publication_tp_quality = 55`.
- `minimum_publication_sl_avoidance_quality = 60`.
- `minimum_publication_rr = 1.8`.

No se rebaja Safety en Commit 10.

### Separación de responsabilidades

- Comité de estrategia: dirección/tesis.
- Execution Geometry Committee: Entry/SL/TP.
- ReviewTrader: evidencia y calibración, no segundo veto direccional.
- Guardian: protección posterior de señales guardadas/operaciones supervisadas.

### Spot

La arquitectura sigue orientada a acumulación/rotación BTC–PAXG–USDT y mantiene Spot separado de Futures. No se mezclan muestras para otorgar autoridad.

### Futures

Se conserva clasificación CORE1/CORE2/MEDIUM/HIGH, Entry más exigente que Spot, SL estructural y TP técnico con validación económica. El apalancamiento no se aumenta simplemente porque el activo sea más volátil.

### Lifecycle

Se mantienen las correcciones causales RC9.8.3: un Entry/SL/TP editado sólo puede ser tocado por precio posterior a su activación. La visualización de señales, guardados por usuario y deduplicación símbolo×TF permanecen separadas del motor global.

---

## 3. Aprendizaje y mejora continua

Estado: **PASS DE MECANISMO / NO ES GARANTÍA DE BENEFICIO FUTURO**.

El aprendizaje sí termina en una modificación gobernada del sistema; no es solamente telemetría.

### Señal que no toca Entry

- No cuenta como win.
- No cuenta como loss.
- No entra al WR operacional.
- Puede aportar MFE/MAE/reachability para diagnosticar Entry demasiado profundo.

`REACHABILITY_BALANCED` sólo puede acercar Entry dentro de límites conservadores: 35% del gap, 0,35 ATR y 5% del riesgo base; preserva SL estructural y R:R.

### Promoción

La ruta es Shadow/Observe → Canary → Active. Canary usa una fracción de 25%, y la evidencia está separada por mercado × símbolo × temporalidad × acción/dirección.

### Alpha Decay

Las promociones pueden retroceder cuando la evidencia resuelta se deteriora. Los no-fill no se cuentan como pérdidas para fabricar un decay falso. El rollback se basa en operaciones con Entry tocado y resultados reales/modelados.

### Límite conceptual

El software puede garantizar que **evalúa, propone, promueve de forma gradual y revierte configuraciones deterioradas**. Ningún sistema puede garantizar que cada ajuste mejore la rentabilidad futura; por eso la gobernanza Shadow/Canary/Active y el rollback son obligatorios.

---

## 4. Software, bugs y rendimiento

Estado: **PASS CON DEUDA TÉCNICA CONTROLADA**.

- Python compile: PASS.
- JavaScript syntax en la cadena auditada: PASS.
- Regresión RC9.8→RC9.8.8 + Commit 10: 78/78 PASS.
- Se intentó ejecutar toda la colección histórica; contiene numerosos tests obsoletos de contratos anteriores (46/92 celdas, APIs/UI previas) y no es un release gate válido. Deben archivarse en Fase 2 o etiquetarse por versión, no modificar producción para hacerlos pasar.
- Persisten warnings de `datetime.utcnow()` deprecado. No afectan el release en Python 3.11, pero deben migrarse a timezone-aware durante la refactorización desktop/backend de Fase 2.

### Riesgos de arquitectura conocidos

`app.py`, `review_trader.py` y `ai_advisor.py` son archivos muy grandes. Funcionan, pero aumentan el coste de mantenimiento y riesgo de regresión. **No deben fragmentarse antes del cierre de Fase 1**; la modularización es trabajo natural de Fase 2.

---

## 5. QA por perfil de usuario

### Usuario básico

**Resultado: usable, pero denso.**

Fortalezas:
- Acción principal visible.
- Entry/SL/TP/R:R y confianza accesibles.
- Confirmadas/Vigentes/Guardadas reducen ambigüedad.
- Recomendaciones fueron reestructuradas para evitar repeticiones.

Riesgo UX:
- Hay muchos indicadores y conceptos. Un usuario básico puede confundir “señal confirmada” con “orden ejecutada”. Mantener siempre la diferencia entre `PRICE_TOUCHED` y `EXCHANGE_FILLED` en Fase 2.

### Usuario intermedio

**Resultado: bueno.**

Puede usar la señal, esperar Entry, seguir Guardian, interpretar contexto multitemporal y consultar Analytics sin necesitar ver detalles internos del comité.

### Usuario profesional

**Resultado: bueno para sistema de decisión/seguimiento; no es OMS/exchange executor.**

Tiene estructura, liquidity/sweeps, SMC/POI, volumen/profile, VWAP/Fib, MTF, ejecución gobernada, evidencia OOS y aprendizaje live. La limitación explícita es que SmartradingReview no confirma fills reales del exchange salvo integración futura: un toque de mercado no equivale por sí solo a fill.

### Rendimiento UX

RC9.8.7 evita polling oculto/duplicado y comprime respuestas. Commit 10 corrige el cache configurado a 8. No se añade más polling ni dashboard pesado en el cierre.

---

## 6. Seguridad — release blocker corregido por Commit 10

El linter de Supabase encontró:

- 26 tablas `public` sin RLS.
- 10 tablas Research con RLS pero sin políticas (válido si son server-only con service-role).
- 1 vista Research con SECURITY DEFINER.
- 2 funciones cleanup SECURITY DEFINER invocables por `anon`/`authenticated`.
- 1 función con `search_path` mutable.

`schema_commit10_final_security_lockdown.sql` cierra el acceso directo a roles públicos y mantiene el backend como autoridad mediante service-role.

**Precondición obligatoria:** confirmar service-role en Render antes de ejecutar SQL.

---

## 7. Alcance de Commit 10

Commit 10 no añade estrategias, no cambia señales ni busca más operaciones. Su función es congelar Fase 1:

1. corregir el override de cache que reducía la eficiencia de RC9.8.7;
2. reducir lecturas Supabase del control IA;
3. proteger cuota diaria Groq por tokens;
4. sobrevivir a IDs Groq retirados;
5. cerrar exposición Supabase server-only;
6. dejar un test de contrato final que impida rebajar Safety accidentalmente.

Tras desplegar y ejecutar la migración de seguridad con la precondición indicada, la recomendación es **congelar funcionalidades de Fase 1**. Cualquier cambio posterior debería ser bug crítico o pertenecer a Fase 2.
