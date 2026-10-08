# Propuesta general — Commit 32.1 Recovery

## Objetivo
Corregir los defectos observados después de Commit32 sin convertir la frecuencia de señales en una cuota. La prioridad es recuperar el flujo real:

**datos → tesis → candidato → Geometry → Safety especializado → hard risk → ruta OOS/LIVE → publicación**.

Commit32.1 no reduce Safety final, no permite publicar fallback, no elimina RR/hard risk y no convierte Research en LIVE.

## 1. Multi-Activo: ABI autoritativo
Los logs mostraron repetidamente `calculate_entry_levels(... execution_observations=...)` incompatible en Multi. Commit32 sólo comprobaba Futures. Commit32.1:

- comprueba la firma de `FuturesAnalysis`;
- instala una firma explícita en `MultiAssetAnalysis`;
- comprueba también el singleton Multi real;
- instala checkpoints RAM sobre el override real Futures/Multi;
- el boot falla si cualquiera pierde `execution_observations`.

## 2. Gráficos: carril OHLC independiente
El endpoint visual legacy se difería cuando había heavy owner o RSS >=210 MB. Con el RSS real observado (~215–300 MB), esto dejaba a la UI sin `df` aunque respondiera HTTP 200.

Commit32.1 conserva el endpoint existente, pero si devuelve `deferred` intenta un segundo carril **OHLC-only**:

- máximo 120 velas;
- sin 9 traders;
- sin Operational Intelligence;
- sin Safety/ReviewTrader;
- sin adquirir el heavy lock;
- sólo se conserva el defer por presión extrema (default 360 MB).

## 3. Memoria: evitar OOM sin matar el servicio por inanición
Los límites de C32 eran demasiado bajos respecto del working set observado y, además, el checkpoint de geometría estaba en la clase base, no en el override Futures.

Política C32.1 propuesta para Render ~512 MB:

- un único heavy slot: se mantiene;
- job start: 240 MB;
- soft: 280 MB;
- cache/heap shed: 285 MB;
- abort preventivo: 335 MB;
- hard lógico: 350 MB;
- visual hard defer: 360 MB;
- heap trim después de Futures/Multi si RSS >=250 MB.

Estos valores son ingeniería de runtime basada en los RSS observados; no son parámetros de trading.

## 4. Frecuencia: segundo chance por setup, no relajación final
El router anterior exigía todos los `core` simultáneamente y MTF sin conflicto para casi todas las familias. Esto penaliza especialmente impulsos y reversals tempranos.

Commit32.1 sólo actúa si la ruta vigente terminó con `candidate_ready=False`.

### Contratos graduales
- **Directional Impulse**: DMI impulse obligatorio + dirección/momentum + soporte independiente. MTF es contexto; un conflicto exige evidencia extra.
- **Sweep Reversal**: sweep obligatorio + MSS/estructura + al menos dos soportes. MTF es contexto; conflicto exige evidencia extra.
- **Trend Pullback**: trend + pullback + MTF siguen siendo estrictos.
- **Breakout Retest**: breakout/retest + estructura/dirección; MTF contrario bloquea.
- **Compression Expansion**: squeeze + expansión + dirección/momentum + soportes. MTF contextual.
- **Range Mean Reversion**: rango + extremo + localización de reversión + momentum/estructura. MTF contextual.

No existen constantes por símbolo ni optimización por timeframe.

### HIGH / MEDIUM / CORE
Para permitir que una hipótesis técnica llegue a Geometry, el segundo chance usa un piso común de 82 para Futures crypto. `HIGH` no debe significar “necesita más indicadores correlacionados para existir”; significa ejecución más rápida, menor vigencia y gestión de riesgo distinta downstream.

Multi mantiene 84 por la heterogeneidad entre clases de activo.

Después del candidato siguen siendo obligatorios Strategy Bank, official cell, macro no crítico, Geometry, Safety especializado, hard risk y ruta OOS/LIVE.

## 5. CRT, Triple RSI y nuevas técnicas
Sí pueden ampliar cobertura de temporalidades menores, pero no tienen autoridad LIVE en 32.1.

Se crea un registry `SHADOW_ONLY` para:

1. `CRT_LIQUIDITY_RANGE_RECLAIM`: rango HTF → sweep → reclaim → MSS/displacement/retest LTF. Debe demostrar valor incremental frente a Sweep/MSS/POI existente.
2. `TRIPLE_RSI_MOMENTUM_TIMING`: tres horizontes/longitudes RSI como feature de timing, nunca como dirección autónoma. Debe demostrar valor incremental frente al momentum actual.
3. `EFFICIENCY_RATIO_NOISE_FILTER`: research de régimen/ruido.
4. `SESSION_OPENING_RANGE_VWAP`: research de ejecución por sesión.

No se agregan traders nuevos ni threads. El registry no descarga datos ni consume LLM.

## 6. Protocolo de promoción Research → LIVE
Una técnica nueva sólo puede ganar autoridad después de:

- reglas congeladas antes del test;
- división cronológica IS/validation/OOS;
- walk-forward;
- fees y slippage;
- expectancy OOS positiva;
- PF >1 después de costes como criterio mínimo de inspección, no garantía;
- drawdown aceptable;
- estabilidad ante parámetros vecinos;
- análisis por régimen;
- evidencia de valor incremental frente a la familia ya existente;
- forward Shadow prospectivo.

Guía de muestra: 30 trades OOS es apenas inspeccionable; 50+ es preferible antes de promover una ruta. No se usa una cuota de señales diarias.
