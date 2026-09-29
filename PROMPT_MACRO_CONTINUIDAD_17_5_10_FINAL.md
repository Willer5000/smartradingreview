# PROMPT MACRO — CONTINUIDAD SMARTRADINGREVIEW DESDE COMMIT 17.5.10 FINAL

Continuar exclusivamente desde el paquete 17.5.10 FINAL construido sobre GitHub Commit 17.5.9 `e8d5cd0c148cde9d8c9dfeed1ec2bdee3030148a`. Antes de cualquier cambio, verificar el HEAD realmente desplegado. No asumir que recibir este ZIP significa que el usuario lo desplegó.

## Política inmutable

“Asertivo pero cauto, precavido pero no tímido y, sobre todo, orientado a rentabilidad.”

Calidad por encima de cantidad. La cantidad de señales nunca es un veto ni una meta. No imponer mínimos/máximos de señales. Una ausencia de señales sólo es aceptable si el funnel demuestra cobertura y rechazos técnicos reales.

Los traders y comités son TRABAJADORES: producen work products especializados para el objetivo común. No son votantes. Una objeción cuenta por la evidencia técnica que contiene, no por quién la emitió.

## Objetivos

Futures: Entries precisos, SL detrás de invalidación relevante y fuera del ruido/reacción, TP estructural alcanzable, expectancy positiva y leverage técnico máximo permisible con riesgo controlado.

Spot: acumulación/rotación BTC/PAXG/USDT, evaluada por satoshis, oro y valor tras costes.

Multi-Activo: perfiles propios por clase, activo, TF, sesión, volatilidad, liquidez y macro; nunca copiar mecánicamente cripto.

## Estado 17.5.10 FINAL

Correcciones de integridad:
- MTF canonicaliza aliases en la frontera del proveedor (4H interno -> 4h provider).
- SL reaction guard sólo veta estructura relevante/local; estructuras remotas no generan falso conflicto.
- Multi 1h usa fair queue y un único deep analysis por tick; recursos generan DEFER, no desaparición silenciosa.
- Telegram confirmado tiene outbox con PENDING/FAILED_RETRYABLE/SENT, retry, dedup y expiración.
- Leverage 1x-3x no es un veto autónomo. Safety/TP/SL/RR permanecen independientes.
- Priors históricos 17.5.8 son SHADOW y no suman puntos LIVE ni reordenan el scanner.
- Spot action mapping corrige COMPRA_SPOT/VENTA_SPOT.

## Leverage

NO modificar `leverage_policy.py` sin una auditoría independiente. La dependencia esperada es `RC9_7_14_STANDARD_TECHNICAL_MAX_LEVERAGE_V6` / `STANDARD_TECHNICAL_MAX_V6`. Debe recomendar el mayor entero técnicamente admisible bajo sus techos reales. x2/x3 no es objetivo: sólo se acepta si ése es realmente el máximo permisible. El presupuesto monetario se controla con posición/allocation, no rebajando arbitrariamente leverage.

## Black-Scholes / Gamma / 0DTE / Delta

17.5.10 agrega `market_maker_math.py`, `options_market_context.py` y `static/market_maker_frontend.js`.

Black-Scholes/Greeks y GEX son herramientas de CONTEXTO. No crean dirección, no cambian Entry/SL/TP, no suben leverage y no bypass Safety. Signed GEX basado en CALL+/PUT- es heurístico. Open Interest no revela la posición neta real de market makers.

Cadena pública directamente compatible sólo cuando el underlying coincide. No proyectar opciones BTC sobre altcoins. Sin cadena compatible usar `SHADOW_THEORETICAL_ONLY`.

## Backtest de aceptación

Ruta congelada: FUTURES 30m `LIQUIDITY_SWEEP_MSS_POI`, tendencia alineada, ADX>=20, volume_ratio>=1.20, RSI LONG<=80 / SHORT>=20.

Stress: toda entrada no resuelta=-1R; coste 0.118R por entrada.

Development 2026-09-10..13: N=11, +1.702R, PF1.254, DD2.236R.
Holdout cronológico 2026-09-14..16: N=4, +3.928R, PF4.513, DD1.118R.
Combinado: N=15, +5.630R, expectancy +0.3753R, PF1.719.

Limitación obligatoria: el holdout NO es OOS prospectivo limpio de 17.5.10 y N es pequeño. Bootstrap IC95 de media incluye cero. Nunca describir esto como garantía. La validación prospectiva posterior al deploy es necesaria.

El backtest y `profitability_qualification.py` son DIAGNÓSTICO/SHADOW. NO convertirlos en un nuevo publication gate: eso volvería tímido al sistema y sería circular. Tampoco aplicar esta cohorte como filtro universal a Multi-Activo.

## Archivos modificados/agregados por 17.5.10

Raíz:
- app.py
- execution_specialist_committees.py
- worker_orchestration.py
- preliminary_backtest_prior.py
- market_maker_math.py [nuevo]
- options_market_context.py [nuevo]
- profitability_qualification.py [nuevo]

Frontend:
- templates/index.html
- static/market_maker_frontend.js [nuevo]

No tocar por este commit:
- futures_system.py
- leverage_policy.py
- static/script.js
- static/futures.js

## QA

QA específico final: 53/53 PASS. También py_compile, node --check, Jinja parse y replay offline pasan.

## Regla de trabajo futuro

Si tras deploy no hay señales, NO bajar Safety. Revisar el funnel: cobertura -> thesis -> strategy -> Entry -> SL -> TP -> RR -> Safety -> Publication -> Delivery. Separar NO_SCAN, NO_THESIS, BAD_GEOMETRY, SAFETY_REJECT, PUBLICATION_REJECT y DELIVERY_FAIL. Corregir bugs concretos antes de tocar umbrales.

Para promover Gamma/0DTE a autoridad productiva, acumular una cohorte point-in-time con option chain/OI/IV/Greeks de cada timestamp y validar walk-forward/OOS. No usar cadena actual sobre fechas pasadas.
