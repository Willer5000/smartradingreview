# PROMPT MACRO — SmartradingReview continuidad desde Commit 17.5.10.1

Continúa el proyecto `Willer5000/smartradingreview` a partir de **Commit 17.5.10.1 — Opportunity Pipeline Integrity**. Antes de modificar código, verificar el HEAD real de GitHub y el estado del despliegue; nunca asumir que un ZIP entregado fue desplegado.

## Política del sistema

**Asertivo pero cauto, precavido pero no tímido y, sobre todo, orientado a rentabilidad.**

La cantidad de señales NO es objetivo ni veto. Debe publicarse toda oportunidad independiente que supere el proceso técnico. Cero señales puede ser correcto cuando el mercado no ofrece setups ejecutables, pero `NO ANALIZADO POR RECURSOS`, `ERROR DE DATOS`, `EDGE HISTÓRICO`, `SAFETY`, `ENTRY`, `SL`, `TP` y `NO HAY TESIS` deben ser estados distintos y observables.

## Arquitectura obligatoria

Los traders son trabajadores/especialistas, no votantes. Producen evidencia técnica. La dirección la sintetiza la tesis; Strategy Router elige procedimientos compatibles; Entry/SL/TP resuelven la geometría; Leverage V6 se calcula después y debe buscar el máximo técnicamente permisible; Safety/Publication gobiernan admisibilidad; Guardian gestiona post-Entry; ReviewTrader/Research aprenden de resultados.

No reintroducir democracia/votación como autoridad final.

## Reglas de calidad que NO deben bajarse para producir señales

No bajar sin nueva evidencia OOS/forward:
- familias independientes / margen de tesis;
- Entry/SL/TP quality;
- hard guard SL vs reacción local;
- R/R;
- Safety;
- Publication;
- Leverage V6;
- estructura/MTF.

No forzar leverage. x2/x3 sólo cuando sea realmente el máximo seguro; si V6 permite 20x/30x con geometría y riesgo defendibles, no degradarlo arbitrariamente a x2/x3.

## Commit 17.5.10.1 — contratos nuevos

### Multi-Activo
- El Strategy Bank específico entra **antes** de `candidate_ready`.
- Reusar los bancos ya existentes por US_INDEX, ENERGY, INDUSTRIAL_METAL, PRECIOUS_METAL y CHINA_INDEX.
- No agregar familias simplemente por falta de señales.
- `router_score` ordena prioridad; no decide quién tiene derecho a análisis profundo.
- Los siete activos pueden entrar a cola.
- Un deep analysis por tick, sin paralelismo adicional.
- Recursos generan `DEFERRED_RESOURCE`, no “sin oportunidad”.
- Tres fallos generan `RUNTIME_FAILED`, nunca `DONE`.

### Futures / Research
- REJECTED_OOS de una generación anterior = `COUNTER_EVIDENCE`, no veto absoluto.
- Alpha decay duro sólo puede recuperar autoridad cuando exista evidencia forward suficientemente actual/compatible.
- Una evidencia histórica negativa puede justificar reducción de exposición, no borrar automáticamente una señal nueva con Entry/SL/TP distintos.

### Microestructura HIGH
- BAD DATA / mala liquidez observada puede bloquear.
- NO DATA no debe convertirse en conclusión de mala calidad; marcar indisponibilidad y ser conservador con exposición.

### Learning
ReviewTrader debe registrar, resolver y atribuir señales. Alpha decay es obligatorio como monitor de persistencia de edge, pero debe actuar sobre cohortes comparables. Verificar persistencia real con `/api/diagnostics/pipeline-integrity`; no confiar sólo en un log “guardado”. Si `supabase_target_project_ref` no coincide con el proyecto esperado o el readback falla, reparar configuración/persistencia antes de tunear trading.

### Greeks / Market Maker
Black-Scholes/Delta/Gamma/Vega/Theta/GEX/0DTE son herramientas de contexto. No crean LONG/SHORT, no bypass Safety y no reciben autoridad LIVE hasta tener cohorte point-in-time suficiente. Sólo BTC/ETH pueden usar cadena directamente compatible; no proyectar GEX BTC a altcoins. UI mediante endpoint ligero cacheado, sin polling.

## Gratuidad / recursos

Objetivo operativo: mantenerse dentro de la RAM y ancho de banda disponibles en el tier gratuito/configurado de Render.

Preservar:
- single heavy slot;
- cero threads adicionales salvo evidencia de necesidad;
- un deep Multi por tick;
- caches largos para Research/opciones;
- sin polling de Greeks;
- no descargar orderbook/option chain para todos los NO_OPERAR;
- backpressure antes de iniciar trabajo pesado;
- telemetría compacta, no blobs de velas/orderbook en Supabase;
- logging compacto por defecto.

Nunca aumentar cobertura mediante paralelismo masivo o fanout de red.

## Backtest heredado

El backtest congelado 17.5.10 continúa positivo bajo stress:
- IS: N=11, +1.702R, PF 1.254.
- OOS cronológico: N=4, +3.928R, PF 4.513.
- combinado: N=15, +5.630R, PF 1.719.
- no resuelto tras Entry = -1R; coste 0.118R/entrada.

Limitaciones: muestra pequeña, OOS no prospectivo y no es replay exacto de 17.5.10.1. No declarar rentabilidad garantizada. La cohorte posterior al deploy debe considerarse la verdadera validación forward.

## Siguiente diagnóstico si siguen faltando señales

Primero consultar el funnel, por mercado × símbolo × TF:
`SCANNED -> THESIS -> STRATEGY -> ENTRY -> SL -> TP -> SAFETY -> PUBLICATION -> EDGE -> RISK_CLASS -> EXECUTABLE`.

Sólo después de demostrar una etapa excesivamente restrictiva con forward data se propone tuning. No modificar Strategy Bank, thresholds o Safety basándose en la mera ausencia de señales durante unas horas.
