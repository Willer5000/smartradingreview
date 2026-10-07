# SmartTradingReview — Auditoría Propuesta 3 / Commit 30.1

## Diagnóstico

Commit 30 corrigió el **reconocimiento** del movimiento temprano: `DIRECTIONAL_IMPULSE` ya aparece como familia causal en tesis reales. El log de producción posterior demuestra, por ejemplo, una tesis QQQ 4h LONG de calidad 92 con `dmi_impulse`, estructura, momentum, volumen, MTF, displacement y breakout.

Sin embargo, Propuesta 3 quedó incompleta en el puente 1h→30m. Se identificaron cinco causas:

1. **El evento 1h sólo priorizaba scheduling, pero no era un contexto persistente.** La cola anterior guardaba principalmente símbolo/TF/tiempo y podía desaparecer antes de que el 30m se procesara.
2. **La misma vela 30m podía reutilizarse sin recalcular.** Si 30m había sido analizado minutos antes del cierre 1h, el nuevo contexto no provocaba una reevaluación inmediata del mismo símbolo.
3. **La prioridad podía seguir bloqueada por UI/background cooldown dentro del heavy-lock gate.** El log mostró explícitamente `futures-incremental:ETH-USDT:30m: cooldown operativo; cede CPU/red a la UI`.
4. **La prioridad podía perderse si no obtenía el heavy lock.** El evento era consumido demasiado pronto. En 30.1 sólo se elimina después de un análisis pesado exitoso (ACK).
5. **Se perdía el blocker exacto del Champion al compactar snapshots.** La UI terminaba mostrando sólo `NO_VALIDATED_LIVE_ROUTE`, ocultando si la causa real era ADX, volumen, RSI, dirección, MTF o falta de Champion.

Además, la ruta F30 LIVE conservaba `volume_ratio >= 1.20`. El archivo de estabilidad congelado antes del incidente contiene un punto vecino más amplio `ADX20 / Vol1.00 / RSI80` con más muestras y net R stressed positivo tanto en Development como en holdout cronológico. Commit 30.1 adopta ese punto únicamente como **contrato pre-Entry de elegibilidad**, no como publicación automática.

## Qué cambia Commit 30.1

- Mantiene `DIRECTIONAL_IMPULSE` como **CONTEXTO**, nunca alpha 1h LIVE por sí solo.
- Convierte la cola impulso→30m en una cola persistente con TTL de 90 minutos.
- El evento se selecciona sin eliminarse; se elimina sólo tras un heavy pass exitoso.
- Si el impulso 1h llega justo después de haber analizado la misma vela 30m del mismo símbolo, esa vela puede reanalizarse **una sola vez** con el contexto fresco.
- La navegación/UI puede seguir teniendo prioridad normal, pero ya no puede bloquear indefinidamente un evento de impulso seleccionado. El bridge NO salta RSS preflight, memory backoff, in-job memory guard ni el único heavy lock.
- Se conserva el evento padre en el resultado/snapshot para trazabilidad.
- `commit19_champion.reason` se conserva en snapshots compactos.
- La UI prioriza `ROUTE_CONTEXT:<causa exacta>` antes del genérico `NO_VALIDATED_LIVE_ROUTE`.
- La ruta F30 usa `ADX>=20`, `Vol>=1.00`, RSI anti-chase. ADX, RSI, RR, Safety, SL/TP y fallback policy no se relajan.
- `detect_market_regime()` recibe volumen real también desde la ruta principal de análisis.
- `/api/runtime/version` informa Commit30.1 y los contratos activos.

## Qué NO cambia

- No existe nueva autoridad LIVE 1h.
- No se crea nueva autoridad rápida Multi-Activo.
- No se baja Safety 75.
- No se baja RR mínimo 1.8 ni se sube el máximo 3.5.
- No se permite publicar fallback.
- No se convierte Q1..Q10 en autoridad de publicación.
- No se añade una cuota de señales.
- No se crean nuevas requests, queries Supabase, llamadas LLM o threads.

## Riesgo de overfitting del ajuste Vol1.00

El punto Vol1.00 es anterior al incidente actual y tiene más observaciones que Vol1.20, pero también muestra mayor net R en la rejilla congelada. Por ello **no puede presentarse como un nuevo OOS limpio ni como prueba de superioridad futura**. Se usa sólo para ensanchar la puerta de routing pre-Entry; la señal todavía debe superar geometría causal, Entry/SL/TP, Safety, RR, ATR stress y demás hard guards. La validación prospectiva posterior al deploy sigue siendo necesaria.

## Lectura correcta de la frecuencia

Commit 30.1 debería reducir falsos negativos de integración y hacer que las seis celdas F30 gobernadas sean realmente evaluadas durante un impulso. No garantiza cuatro señales diarias. Si, una vez desplegado íntegramente, predominan motivos como `F30_ADX_BELOW...`, `F30_RSI...`, `RR_OUTSIDE...` o `SAFETY...`, eso será evidencia técnica real. Si Multi sigue mostrando `*_FAST_ROUTE_REQUIRES_OOS`, será una limitación estadística deliberada y no un bug.
