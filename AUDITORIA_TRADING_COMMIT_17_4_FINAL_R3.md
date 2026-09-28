# AUDITORÍA TÉCNICA DE TRADING — COMMIT 17.4 FINAL R3

## Veredicto
R2 no debía implementarse sin cierre. La auditoría encontró tres contradicciones de arquitectura capaces de producir timidez artificial o sesgo de selección:

1. **Spot anti-FOMO podía borrar una señal confirmada** convirtiendo COMPRA/VENTA en ESPERAR por calidad de ejecución. Se corrige separando `signal_confirmed` de `execution_ready`: la dirección se conserva y queda `CONFIRMED_PENDING_EXECUTION` con tamaño 0 hasta hallar zona fresca.
2. **Contingency Playbook podía reintroducir vetos legacy** (`CRITICAL` macro o cualquier Research negativo) después de que Operational Intelligence ya los había tratado de forma adaptativa. Ahora reutiliza la autoridad de `macro_reasoning.hard_block_new_entry` y `research_reasoning.hard_block`; CRITICAL genérico eleva exigencia, evento inminente/no modelable sí puede bloquear, y Research negativo small-N es advisory.
3. **Multi-Activo recibía macro/sesión específica demasiado tarde y el router favorecía tendencia/momentum.** Ahora el contexto por clase de activo entra antes de la tesis y el router de alto recall usa cuatro carriles con el MISMO OHLCV: Trend/Momentum, Expansion/Breakout, Reversal/Mean Reversion y Compression/Release. El router no genera señal; sólo decide qué celdas merecen el análisis profundo acotado.

## Criterios del desk simulado
- **Desk Spot:** el objetivo es snowball/rotación de unidades; una mala zona de entrada no debe borrar la tesis, sólo aplazar ejecución.
- **Desk Futures crypto:** CORE/MEDIUM/HIGH conservan exigencias distintas. No se bajan Safety, R/R, familias ni calidad para aumentar frecuencia.
- **Desk Multi-Activo:** índices, energía y metales deben recibir macro, sesión y volatilidad acordes a su clase antes de seleccionar estrategia.
- **Desk Ejecución:** Entry busca reacción/alcanzabilidad; SL invalidación real fuera de ruido y zonas de reacción; TP touch probability + estructura + R/R + economía sobre margen; ninguno decide dirección.
- **Desk Risk/Guardian:** protege MFE y sólo extiende TP con momentum/estructura/economía incremental favorables; nunca promedia perdedores ni promete rentabilidad.
- **Desk Sistemático:** indicadores correlacionados cuentan por familia, no como votos independientes; Research necesita evidencia robusta/OOS para hard-block; no se ajustan parámetros por small-N.

## Qué NO cambia en R3
- No se agregan nuevas familias estratégicas.
- No se bajan Safety, R/R, quality thresholds ni requisitos HIGH.
- No se toca la lógica de Liquidation Map.
- No se altera la independencia Signal -> Entry/SL/TP introducida en R2.
- No se añaden requests, polling, LLM/Groq, escrituras Supabase, workers o threads.

## Recursos
Los cambios de R3 trabajan sobre datos ya cargados/cachés existentes. El router Multi-Activo calcula más rasgos con las mismas 72 velas ya descargadas; el macro específico reutiliza `fetch_if_stale=False`.

## Validación
- QA Commit 17.3: **54/54 PASS**
- QA Adaptive Reasoning 17.4: **29/29 PASS**
- QA Signal/Execution Decoupling: **10/10 PASS**
- QA Execution Quality: **6/6 PASS**
- QA R3 Trading Audit Closure: **15/15 PASS**
- Python compile: **PASS**
- JS `node --check`: **PASS**

## Recomendación operativa
Implementar R3 como el único **Commit 17.4**, congelar arquitectura de trading y comenzar la segunda etapa de evaluación. No volver a ajustar estrategia/gates por frecuencia de señales. La siguiente intervención sólo debe ocurrir ante una regresión demostrada o evidencia estadística suficiente.

### Métricas para la etapa 2
Medir por mercado × símbolo/clase × TF × dirección × familia:
- Expectancy neta en R y dinero
- Profit Factor
- Win rate (secundario a expectancy)
- MAE/MFE y MFE giveback
- % de señales `CONFIRMED_PENDING_EXECUTION` que logran ejecución
- causas de no ejecución/rechazo
- precisión de Entry, distancia/colisión de SL, touch probability de TP
- drawdown, losing streaks, costes/slippage
- OOS/Shadow y tamaño de muestra antes de otorgar autoridad adaptativa

El baseline de ~50% WR y +5% se usa como referencia de etapa 1, no como objetivo a optimizar de forma directa. Mejorar WR sacrificando payoff o sobreajustando sería una regresión.
