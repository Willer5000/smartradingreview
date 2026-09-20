# RC9.7.15 — Structural Entry Location & Lower-TF Confirmation

**Proyecto:** SmartradingReview / CRYPTO TRADER ANALYST PRO  
**Repositorio:** MAIN  
**Baseline:** RC9.7.14 FINAL FINAL  
**SQL:** No requerido  
**Research:** Sin cambios  
**Frontend:** Sin cambios  

## Objetivo

RC9.7.15 corrige una debilidad identificada durante las primeras pruebas reales de Futures: una tesis direccional correcta y una zona estructural razonable no garantizan que el momento de ejecución sea bueno.

La versión separa explícitamente:

**zona candidata de reacción → confirmación/timing → Entry ejecutable**

El precio de Entry deja de depender de una distancia mecánica respecto del cierre. El ATR se conserva como normalizador de distancia y volatilidad, pero no como generador principal del Entry.

## Problema observado

En operaciones reales como LINK/USDT 4h se observó que una tesis LONG podía tener argumentos técnicos válidos, pero el Entry podía producirse después de una expansión fuerte y cerca de una zona alta de la estructura. Aunque el precio posteriormente pudiera recuperar, un Entry con MAE inmediato elevado sigue siendo una ejecución deficiente.

Este caso no se toma como prueba estadística suficiente para recalibrar el sistema por sí solo. Se usa como evidencia práctica de una debilidad arquitectónica: el sistema debía distinguir mejor entre **dirección correcta** y **momento correcto para ejecutar**.

## Nueva lógica del Entry

La secuencia de decisión pasa a ser:

1. **Tesis/dirección** — LONG o SHORT viene del motor principal.
2. **Ubicación estructural** — piso/demanda, mitad de rango o techo/oferta.
3. **Zona de reacción** — Order Block, FVG, soporte/resistencia, POC y otras zonas válidas.
4. **Confluencia** — Fibonacci y EMAs pueden reforzar una zona existente, pero no crean una operación por sí solas.
5. **Timing/confirmación** — en Futures, un Entry cercano al mercado puede requerir reacción confirmada en un timeframe inferior.
6. **Entry ejecutable** — sólo después de superar los filtros anteriores.
7. **SL/TP/R:R** — se mantienen las reglas existentes de invalidación y geometría.

## Lógica simétrica LONG / SHORT

| Ubicación | LONG | SHORT |
|---|---|---|
| Piso / demanda | Puede aceptar Entry cercano si existe reacción estructural válida | Evita perseguir la caída; espera rebote/reacción |
| Mitad de rango | Penaliza Entries cercanos sin POI claro | Penaliza Entries cercanos sin POI claro |
| Techo / oferta | Evita perseguir la subida; espera pullback/reacción | Puede aceptar Entry cercano si existe rechazo/reacción |

La intención es evitar reglas asimétricas o sesgos direccionales: lo que se exige para LONG se refleja de forma equivalente para SHORT.

## Jerarquía de zonas

Las zonas principales de reacción continúan siendo estructurales:

- **Order Blocks** — POI estructural principal.
- **FVG** — zona de desequilibrio/retest.
- **Soporte / resistencia** — estructura horizontal real.
- **POC** — contexto de volumen y posible equilibrio/reacción.
- **Fibonacci** — confluencia secundaria.
- **EMA 9/21/50/200** — confluencia dinámica cuando ya existe un POI válido.
- **ATR fallback** — recurso de respaldo, con menor autoridad que las zonas estructurales.

Las EMAs y Fibonacci no generan por sí solos una operación.

## Papel del ATR

ATR se utiliza para:

- normalizar distancias entre activos con volatilidades distintas;
- medir extensión;
- estimar si una zona es razonablemente alcanzable;
- definir tolerancias de proximidad;
- ayudar a evaluar volatilidad y timing.

ATR **no debe interpretarse como el origen del precio de Entry**.

## Confirmación lower-TF en Futures

Para Entries cercanos al mercado, RC9.7.15 amplía la confirmación inferior:

| Timeframe de señal | Confirmación inferior |
|---|---|
| 1h | 30m |
| 2h | 30m |
| 4h | 1h |
| 12h | 2h |
| 1D | 4h |

Una orden estructural más profunda puede permanecer como limit order sin exigir una reacción antes de que el precio llegue a la zona. La confirmación inferior se exige especialmente cuando el Entry está cerca del mercado y existe riesgo de perseguir el movimiento.

## Anti-chase estructural

Nuevos estados de timing permiten evitar entradas tardías:

- `WAIT_PULLBACK_LONG_EXTENDED`
- `WAIT_REBOUND_SHORT_EXTENDED`

Ejemplos:

**LONG en techo/extensión:** la tesis puede seguir siendo alcista, pero la ejecución espera un retroceso hacia una zona defendible.

**SHORT en piso/extensión bajista:** la tesis puede seguir siendo bajista, pero la ejecución espera un rebote hacia oferta/resistencia.

## Order Flow

El Order Flow público/microestructura existente permanece como:

`SHADOW_CONFLUENCE_NOT_AUTHORITY`

No se promueve todavía a veto ni a gatillo autónomo de producción porque no existe evidencia OOS suficiente que demuestre que mejora de forma robusta las decisiones. Puede aportar contexto y acumular evidencia para ReviewTrader, pero no debe fabricar ni bloquear por sí solo una operación.

## Diagnósticos nuevos en `levels`

RC9.7.15 conserva información adicional para auditoría y aprendizaje, incluyendo:

- `entry_market_location`
- `entry_location_context`
- `entry_location_basis`
- posición dentro del rango
- extensión direccional
- confluencia EMA
- papel del ATR en la selección

Esto permite a ReviewTrader estudiar después si una pérdida estuvo asociada a dirección, estrategia, ubicación, timing o calidad de Entry.

## Qué NO cambia

RC9.7.15 no modifica:

- motor de dirección/tesis;
- Strategy Bank;
- ReviewTrader y sus reglas de aprendizaje;
- Guardian;
- apalancamiento;
- vigencia/lifecycle de señales;
- Telegram;
- esquema Supabase;
- hardening de Render Free;
- interfaz frontend.

El propósito del release es deliberadamente limitado: **mejorar la calidad estructural y temporal del Entry sin alterar el resto del sistema**.

## Archivos modificados

Producción:

- `app.py`
- `futures_system.py`
- `entry_reaction_engine.py`

Pruebas/documentación:

- `test_rc9_7_15_entry_location_engine.py`
- `test_rc9_7_14_final_final_entry_precision.py`
- `RC9_7_15_VALIDATION.txt`
- `RC9_7_15_NOTES.txt`
- `README_RC9_7_15.md`

## Validación

Resultado del paquete:

- **pytest:** 71 passed
- **Python compile:** PASS

Cobertura incluida:

- clasificación piso / rango / techo;
- simetría LONG/SHORT;
- LONG en piso permite reacción estructural cercana;
- SHORT en piso evita perseguir caída;
- LONG en techo penaliza Entry near-market;
- EMA sólo como confluencia;
- OB/FVG/S/R con mayor prioridad que ATR fallback;
- confirmación lower-TF para 2h y 4h;
- limits estructurales profundos siguen siendo elegibles;
- mapping lower-TF completo;
- Order Flow permanece en shadow hasta demostrar edge OOS.

## Interpretación correcta

RC9.7.15 **no garantiza que una operación gane** ni que un Entry nunca tenga MAE. El objetivo es exigir que el Entry sea más defendible técnicamente y evitar que una buena tesis direccional se convierta automáticamente en una mala ejecución.

La política esperada es:

> **Futures:** tesis válida + ubicación estructural + POI + confluencia + timing/reacción lower-TF + geometría válida = Entry ejecutable.

> **Spot:** tesis válida + POI estructural + confluencia + alcanzabilidad razonable; confirmación adicional cuando el precio esté extendido o la zona sea conflictiva.

## Criterio de evolución futura

Los parámetros numéricos de proximidad, score y confirmación deben tratarse como **parámetros iniciales gobernados**, no como verdades universales. ReviewTrader debe acumular evidencia por mercado, símbolo, timeframe, dirección y contexto antes de proponer ajustes de autoridad.

Una pérdida aislada no debe modificar el sistema. Una secuencia consistente de Entries con poco MFE, MAE temprano y expectancy negativa sí puede justificar recalibración posterior.
