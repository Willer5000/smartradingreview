# Auditoría técnica — Commit 17.5.10.1

## Alcance

Base verificada: `68f90f313fa961693c7cebb09251bdc3e4265f31` (`Commit 17.5.10`).

Objetivo de 17.5.10.1: corregir pérdida de oportunidades y regresiones de observabilidad sin bajar Safety, Entry/SL/TP, R/R ni modificar Leverage V6; mantener el runtime compatible con un servicio Render de memoria restringida y minimizar tráfico saliente.

## Hallazgos reproducidos

### 1. Multi-Activo tenía el Strategy Bank correcto, pero llegaba tarde

`operational_intelligence.py` asignaba a Multi-Activo `MULTIASSET_DELEGATED_PLAYBOOK` con `quality=0`. El Strategy Bank específico por clase de activo se aplicaba después del análisis base, en `_post_market_analysis_hook()`. Resultado: normalmente Multi sólo podía sobrevivir por la ruta `THESIS_AUTONOMOUS` de calidad alta, en vez de permitir que la estrategia específica participara en la construcción del candidato.

17.5.10.1 no agrega familias indiscriminadamente. Reutiliza las familias que ya existen para índices, energía, metales y China, las evalúa antes de `candidate_ready`, y exige la misma calidad de estrategia (78) y el mismo contrato de tesis/MTF. La estrategia no puede crear dirección desde una tesis neutral.

### 2. Multi-Activo estaba subanalizado por shortlist y cuotas

El router barato marcaba sólo `top-2` como `deep_candidate`; 1h además dependía de `router_score>=82`, y el scheduler usaba `MULTIASSET_AUTO_DEEP_DAILY_MAX`. Esto convertía una capa barata de priorización en derecho a ser analizado.

17.5.10.1 convierte `router_score` en prioridad, no elegibilidad. Los siete activos pueden entrar a una cola justa. Se conserva un solo análisis profundo por tick, sin nuevos threads. El límite diario deja de descartar celdas y se reemplaza por backpressure: RAM + intervalo + presupuesto observado de respuestas KuCoin. Una celda diferida sigue pendiente hasta su vencimiento.

Tres errores ya no significan `DONE`; quedan `RUNTIME_FAILED`/diferidos con backoff. `DONE` vuelve a significar procesado.

### 3. Futures podía ser vetado por OOS antiguo de otra generación

El Profitability Router podía convertir una oportunidad ya ejecutable en `EDGE_BLOCKED` a partir de `REJECTED_OOS` histórico, aun cuando Entry/SL/TP y orquestación cambiaron en 17.5.x.

17.5.10.1 conserva esa evidencia como `COUNTER_EVIDENCE`. No borra Research. El veto duro queda reservado a deterioro/alpha-decay con evidencia forward suficientemente reciente/compatible; el histórico viejo puede reducir exposición sugerida, pero no borrar por sí solo una nueva señal técnicamente válida.

### 4. HIGH confundía falta de microestructura con mala microestructura

Antes:
- microestructura disponible y mala -> bloquea;
- microestructura no disponible -> también bloquea HIGH.

Ahora:
- disponible y objetivamente mala -> sigue bloqueando por riesgo de ejecución;
- no disponible -> `MICROSTRUCTURE_UNAVAILABLE`, no inventa evidencia negativa y reduce exposición sugerida. No cambia leverage ni Safety.

### 5. El aprendizaje existe en código, pero la durabilidad no estaba verificable

En el proyecto Supabase conectado durante la auditoría:
- `signals` termina el 18/09/2026;
- `runtime_snapshots_v1` tiene 0 filas;
- `research_shadow_live_metrics_v1` y `research_promotions_v1` tampoco muestran actualización posterior al 18/09.

Eso contradice los logs actuales que dicen “Señal registrada” y “Snapshot Supabase guardado”. Puede existir una diferencia de proyecto/variables de entorno o una escritura que no está llegando al destino auditado.

17.5.10.1 agrega readback periódico de snapshot y `/api/diagnostics/pipeline-integrity`, incluyendo el project-ref sanitizado del destino Supabase. Esto permite comprobar después del deploy si ReviewTrader está aprendiendo sobre la base esperada. No se afirma que el aprendizaje durable esté verificado hasta observar ese readback.

Alpha decay continúa siendo la idea correcta: evidencia histórica -> Shadow/forward -> monitor de deterioro -> degradar/retiro cuando la cohorte actual lo demuestra. Lo que se evita es usar una cohorte vieja como veto duro de una generación distinta.

### 6. Los logs estaban generando ruido extremo

La traza mostrada sí alcanzaba `ANÁLISIS COMPLETADO`; el proceso no estaba necesariamente atascado en esos mensajes. Sin embargo, imprimir decenas de líneas `Excluida condición...` y ejecutar `traceback.extract_stack()` por análisis agrega I/O/CPU y hace parecer colgado el worker.

17.5.10.1 deja ese detalle detrás de `TRADING_VERBOSE_TEMPLATE_DIAGNOSTICS=1`. Por defecto queda sólo el resumen compacto.

### 7. Greeks existían, pero la UI no era robusta

17.5.10 ya contenía Black-Scholes/Gamma/Delta/0DTE. El frontend dependía de interceptar `updateAllCharts`, por lo que podía no dibujar si el orden de carga/hook no coincidía.

17.5.10.1 añade un endpoint ligero cacheado y una carga UI explícita sin polling. La tarjeta muestra Delta, Gamma/GEX, Vega, Theta/día, Gamma <=24h, Zero Gamma, Delta-Neutral y Greeks ATM. No lanza un análisis completo y no crea dirección.

## Gratuidad / recursos

17.5.10.1 mantiene:
- un solo heavy-slot;
- un solo deep Multi por tick;
- cero threads nuevos;
- cero polling adicional para Greeks;
- opciones observadas sólo bajo demanda o para un candidato direccional BTC/ETH, con cache de 1 hora;
- Profitability Router con cache mínimo de 30 minutos;
- router Multi barato con su cache existente;
- backpressure por RAM antes del trabajo profundo;
- presupuesto soft observado de respuestas KuCoin para el auto-scan Multi, por defecto 48 MB/día dentro del proceso.

El presupuesto de 48 MB es un guardrail de respuestas observadas por la aplicación; no equivale exactamente a la facturación de Render y no permite garantizar matemáticamente el total mensual de ancho de banda. Su función es impedir que el auto-scan escale sin control.

## Qué NO cambia

No se cambian los thresholds centrales de:
- Entry/SL/TP committees;
- hard guard de reacción del SL;
- R/R;
- Safety;
- Publication;
- Leverage V6;
- Liquidation Map;
- worker orchestration.

No se agregan familias sólo para producir señales.

## Backtest heredado

Se volvió a ejecutar el backtest de aceptación congelado de 17.5.10. Sigue positivo:

| Split | N | Net stress R | Expectancy/trade | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| IS 10–13/09 | 11 | +1.702R | +0.1547R | 1.254 | 2.236R |
| OOS cronológico 14–16/09 | 4 | +3.928R | +0.9820R | 4.513 | 1.118R |
| Combinado | 15 | +5.630R | +0.3753R | 1.719 | 2.236R |

Tratamiento: no resuelto tras Entry = -1R y coste stress 0.118R por entrada.

Esto NO es un replay exacto de 17.5.10.1. Los cambios de 17.5.10.1 son principalmente de cobertura/autoridad/observabilidad y necesitan validación forward después del deploy. El bootstrap de la cohorte histórica da P(media>0)≈0.9026, pero el IC95% incluye cero; N es pequeño.

## Conclusión

La causa principal de falta de señales no justifica todavía bajar Safety. Multi-Activo tenía inteligencia específica disponible pero colocada después de candidate-ready y además un scheduler que no permitía analizar todo el universo. Futures tenía una asimetría de veto histórico y HIGH confundía NO DATA con BAD DATA. 17.5.10.1 corrige esas rutas conservando los filtros de calidad y el control de recursos.
