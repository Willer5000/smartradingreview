# Auditoría final — SmartradingReview Commit 17.5.10

Base auditada: Commit 17.5.9 `e8d5cd0c148cde9d8c9dfeed1ec2bdee3030148a`.

## Dictamen técnico

17.5.10 es un ajuste de integridad del pipeline y de contexto cuantitativo; no reemplaza la arquitectura construida durante el último mes. Conserva la separación entre trabajadores, Strategy Bank, Operational Intelligence, Entry/SL/TP, Safety, Publication, Leverage V6, Guardian y ReviewTrader. No reinstaura votaciones y no añade una cuota de señales.

## Hallazgos de la auditoría 17.5.9 y corrección

1. **MTF `4H` vs `4h`:** corregido en la frontera del proveedor. La semántica interna sigue siendo 4H; el proveedor recibe el alias que espera.
2. **Leverage 1x-3x usado como veto adicional:** corregido. El leverage ya no determina calidad por sí solo. Safety/TP/SL/RR permanecen independientes. 17.5.10 no fuerza leverage al alza para publicar.
3. **SL vetado por estructuras remotas:** corregido. El hard guard sólo considera una reacción relevante al corredor de invalidación del setup. El caso Entry100/SL98/support50 no veta; una reacción realmente próxima sí.
4. **Multi-Activo 1h `[:1]`:** reemplazado por cola justa secuencial. Sigue existiendo sólo un deep analysis por tick para proteger recursos, pero el segundo candidato conserva turno.
5. **Telegram marcado terminado antes de confirmar entrega:** corregido mediante outbox PENDING/FAILED_RETRYABLE/SENT, reintento, expiración y deduplicación.
6. **Priors positivos 17.5.8:** pasan a SHADOW. Producción recibe ajuste 0; ReviewTrader conserva la evidencia para comparación prospectiva.
7. **Spot action mismatch:** LONG/SHORT se normaliza a COMPRA_SPOT/VENTA_SPOT cuando corresponde consultar evidencia Spot.

## Black-Scholes / Gamma / Delta / 0DTE

Se incorpora un módulo matemático de opciones con Black-Scholes y Greeks (Delta, Gamma, Vega, Theta), agregación de Open Interest y lecturas de Gamma Exposure, gamma <=24h, Zero-Gamma aproximado, Delta-Neutral aproximado y Call/Put/Gamma walls.

Reglas anti-sobreajuste:

- no crea LONG/SHORT;
- no modifica Safety;
- no cambia Entry/SL/TP;
- no cambia leverage;
- no tiene peso directo en comité en 17.5.10;
- signed GEX CALL+/PUT- está etiquetado como heurístico porque Open Interest no revela el inventario real del market maker;
- BTC/ETH pueden consumir una cadena pública directamente compatible; un altcoin NO hereda falsamente la cadena de BTC;
- sin cadena observada, el fallback Black-Scholes es `SHADOW_THEORETICAL_ONLY`.

## Frontend

Se añade un indicador convencional en Futures:

**Opciones · Gamma / Delta / 0DTE**

Muestra:
- curva GEX;
- curva Delta $;
- régimen Gamma;
- proporción de Gamma <=24h;
- Zero-Gamma;
- Delta-Neutral aproximado;
- Call Wall, Gamma Wall y Put Wall.

La UI consume el payload de análisis existente. No inicia un segundo análisis de mercado ni un polling adicional.

## Calidad vs cantidad

17.5.10 no establece mínimo ni máximo de señales. La cantidad no es criterio de publicación. Las oportunidades que superan el pipeline técnico siguen siendo publicables; las que no, se rechazan por causas técnicas. Los límites de CPU/RAM son backpressure de scheduler, no una cuota de trading.

El sistema sigue diferenciado por mercado, activo, TF, régimen y volatilidad. No se aplica el backtest 30m de cripto como estrategia universal a Multi-Activo.

## Leverage

`leverage_policy.py` no se modifica. Se congela como dependencia la política `RC9_7_14_STANDARD_TECHNICAL_MAX_LEVERAGE_V6`, que selecciona el **máximo entero técnicamente admisible** bajo sus techos de seguridad/contrato/liquidación/riesgo/ATR y calidad. Position sizing controla después el presupuesto monetario.

Un 2x/3x NO es objetivo. Sólo es aceptable cuando, para esa geometría, el techo admisible de V6 queda realmente en ese nivel. 17.5.10 tampoco fuerza x4 para que una señal parezca premium.

## Backtest de aceptación

In-sample: N=11, +1.702R stressed.  
OOS cronológico: N=4, +3.928R stressed.  
Combinado: N=15, +5.630R, PF 1.719, MaxDD 2.236R.

Todas las entradas no resueltas se penalizan -1R y se descuenta 0.118R de stress de costes por entrada.

Limitación central: N es pequeño y el OOS es cronológico, no prospectivo limpio de 17.5.10. El bootstrap combinado tiene IC95 de la media [-0.3713,+1.122]R; incluye cero. Esto impide afirmar garantía estadística o ausencia demostrada de overfitting.

## Falta de señales

17.5.10 corrige las rutas mecánicas reproducidas que podían perder oportunidades: MTF, falso conflicto SL, starvation Multi 1h, veto autónomo de low leverage y entrega Telegram. Esto mejora la cobertura y elimina pérdidas silenciosas comprobadas.

No puede garantizar que al desplegar haya una señal activa inmediatamente. Si tras desplegar hay cobertura completa y todos los candidatos fallan gates técnicos reales, cero señales puede ser correcto. El funnel post-deploy es el criterio para distinguirlo.

## QA final

**53/53 PASS** en el QA específico de 17.5.10 FINAL, más:

- `python -m py_compile`: PASS;
- `node --check static/market_maker_frontend.js`: PASS;
- parse Jinja de `templates/index.html`: PASS;
- backtest offline reproducido: PASS.

Las pruebas reducen el riesgo de regresión; no sustituyen un deploy real y observación prospectiva.
