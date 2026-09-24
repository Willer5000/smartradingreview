# Commit 12 · Auditoría interna Multi‑Activo

Fecha: 24/09/2026  
Base: `main` posterior a Hotfix 10.2.2, verificado directamente contra GitHub antes del empaquetado.

## Dictamen

**APTO PARA INCORPORACIÓN CONTROLADA DE MULTI‑ACTIVO.**

El diseño evita crear un segundo sistema paralelo. Multi‑Activo reutiliza el núcleo de ejecución Futures ya probado —geometría, Entry/SL/TP, Safety, Publication Gate, lifecycle y ReviewTrader— y agrega únicamente semántica específica de mercado: universo, sesiones, Macro Gate, banco de estrategias, especialistas y Router de oportunidades.

El objetivo no es forzar una operación diaria. Es ampliar la cobertura a motores de mercado menos correlacionados que Crypto para que existan más días con opciones técnicas reales.

## 1. Universo V1

- `SPY-USDT` → **SPY (S&P 500)**
- `QQQ-USDT` → **QQQ (Nasdaq 100)**
- `CL-USDT` → **CL (Petróleo WTI)**
- `NATGAS-USDT` → **NATGAS (Gas Natural)**
- `COPPER-USDT` → **COPPER (Cobre)**
- `XAG-USDT` → **XAG (Plata)**
- `KSTR-USDT` → **KSTR (China STAR 50)**

Los identificadores de transporte KuCoin se mantienen ocultos al usuario. La disponibilidad de contratos puede cambiar; el sistema falla abierto en scanner si un contrato no responde en vez de bloquear Spot/Futures.

## 2. Arquitectura de oportunidad

### Nivel 1 · Opportunity Router

Scanner determinístico y barato:
- secuencial, no paralelo;
- 72 velas;
- TTL 15 minutos;
- 7 activos máximo;
- 0 llamadas LLM;
- 0 escrituras Supabase;
- sólo métricas escalares de tendencia/momentum/ATR/volumen/sesión/macro;
- shortlist máximo 2.

### Nivel 2 · Análisis profundo

Sólo los candidatos del shortlist pasan al motor completo. El automático tiene límite duro de 12 análisis profundos por día y procesa como máximo una celda por iteración del loop existente.

No se crea un thread nuevo: Multi‑Activo comparte el loop Futures y el único `HEAVY_ANALYSIS_LOCK` existente.

## 3. Banco de estrategias diferenciado

No se copia ciegamente el banco Crypto. Hay familias por clase:

- **US_INDEX**: Sweep/MSS/POI, VWAP Session Pullback, Breakout Retest, Compression Expansion, Trend Pullback, Post‑Macro Confirmation, Mean Reversion selectiva.
- **ENERGY**: Sweep/MSS/POI, Trend Pullback, Breakout Retest, Compression Expansion, Post‑Event Confirmation, Volatility Retest.
- **INDUSTRIAL_METAL**: Sweep/MSS/POI, Trend Pullback, Breakout Retest, Compression Expansion, Macro Trend Confirmation.
- **PRECIOUS_METAL**: Sweep/MSS/POI, Trend Pullback, Mean Reversion selectiva, Breakout Retest, Rates/USD Confirmation.
- **CHINA_INDEX**: Sweep/MSS/POI, Trend Pullback, Breakout Retest, Compression Expansion, Asia Session Retest, Macro Trend Confirmation.

La selección inicial del banco es **routing contextual**, no autoridad estadística. ReviewTrader sigue siendo quien debe acumular evidencia por celda y Alpha Decay conserva la gobernanza.

Celda conceptual:
`MULTI::<clase>::<activo>::<TF>::<régimen>::<volatilidad>`.

## 4. Especialistas

Multi‑Activo añade especialistas determinísticos/contextuales, no LLM permanentes:

- Equity Index Specialist
- Energy Specialist
- Metals / Industrial Cycle Specialist
- Precious Metals Specialist
- Asia / China Specialist
- Macro / Intermarket Specialist

Sólo participa el especialista de la clase correspondiente. No se ejecutan todos simultáneamente.

Su autoridad inicial es **contexto/veto**, no creación de LONG/SHORT ni modificación libre de Entry/SL/TP.

## 5. Macro Gate

Reutiliza el snapshot de `macro_context.py` ya existente con `fetch_if_stale=False`; Commit 12 no añade otra descarga macro automática.

- `NORMAL`: sin penalización especial.
- `CAUTION`: riesgo macro elevado, exigir confirmación completa.
- `WAIT_EVENT`: si un evento exacto y relevante está dentro de 45 minutos, una nueva señal no se publica todavía.

Macro nunca crea dirección y no reescribe Entry/SL/TP.

## 6. Entry y ejecución

Se conserva la filosofía central:

`Liquidity → Sweep → MSS → Displacement → POI → Entry`

seguida de:

`SL técnico → TP estructural → R:R → Reachability → Safety → Publication Gate`.

El activo/contexto puede terminar aprendiendo parámetros distintos, pero no se transplanta arbitrariamente el perfil BTC a petróleo/índices/metales.

## 7. ReviewTrader / aprendizaje / Alpha Decay

No hay nuevas tablas.

Multi‑Activo se identifica mediante:
- símbolos exclusivos;
- `context.market_segment=MULTIASSET`;
- `asset_class`;
- celdas de estrategia propias;
- prefijos `MULTI::<ASSET_CLASS>::...`.

ReviewTrader obtiene las velas desde el motor Multi‑Activo para poder evaluar TP/SL/MFE/MAE. El campo de transporte `system_type` conserva la familia derivativa Futures por compatibilidad con el esquema actual; la diferenciación de aprendizaje ocurre por símbolo/contexto/estrategia.

Alpha Decay no se elimina ni se relaja.

## 8. Recursos

### Render

No se aumenta Gunicorn: **1 worker / 2 threads**. No hay segundo scheduler/thread. El scanner es secuencial y comparte el mismo lock pesado.

Render contabiliza como outbound el tráfico iniciado por el servicio hacia Internet; inbound no se factura como outbound. Por eso el diseño usa requests públicos pequeños y cacheados, y evita Order Book/trades automáticos en Multi‑Activo V1.

### Supabase

Estado pre-deploy observado directamente:
- DB: **156 MB**.
- `signals`: ~107 MB.
- `signal_indicators`: ~12 MB.
- `signal_results`: ~2.8 MB.

Commit 12:
- no crea tablas;
- no incluye SQL;
- no almacena velas del scanner;
- no almacena cada ranking del Router;
- no modifica `MAIN_SUPABASE_DAILY_BUDGET_MB=12`;
- sólo el análisis profundo entra al ciclo normal de evidencia.

### IA / Groq

No hay Científico, Consejo ni Asistente nuevos.

- scanner: 0 LLM calls;
- contexto IA: máximo 4 señales compactas + top 4 del Router;
- Multi‑Activo comparte el presupuesto global existente;
- `AI_GROQ_DAILY_TOKEN_BUDGET=160000` no aumenta;
- cadencias 10.1 se conservan.

### Telegram

Reutiliza el canal compacto confirmado:
- texto;
- Entry/SL/TP/R:R/leverage cuando corresponda;
- deep link a señal;
- sin imagen/PDF.

## 9. Temporalidades

V1 deliberadamente pequeña:
- **4h** principal;
- **1D** swing/contexto;
- **1h** Fast Lane dinámica sólo para el candidato de actividad excepcional.

No se habilitan 12h/1W en la primera versión para evitar multiplicar celdas antes de validar edge.

## 10. Riesgos y límites conocidos

- Un contrato sintético puede cambiar o retirarse en KuCoin; el código debe fallar abierto para no afectar Crypto.
- El Router no es una señal; sólo prioriza dónde gastar análisis completo.
- La microestructura Multi‑Activo V1 no descarga Order Book/trades adicionales automáticamente; se conserva como proxy no autoritativo para proteger recursos.
- No puede prometerse costo literalmente cero: toda request consume unos bytes/CPU. La arquitectura impone límites para mantener el incremento acotado y no ampliar los presupuestos configurados.
- La validación de rentabilidad requiere tiempo/muestra; Commit 12 incorpora capacidad y gobernanza, no una garantía de ganancias.

## 11. QA

- 30/30 pruebas de regresión PASS.
- Python compile PASS.
- JavaScript syntax PASS.
- Jinja template parse PASS.
- Commit 10.1/10.2/10.2.2 cubiertos por regresión.
- No SQL / no thread nuevo / no incremento de presupuesto IA o Supabase.

## Conclusión

Commit 12 añade un universo Multi‑Activo razonador y market‑aware manteniendo la misma filosofía del sistema. La ampliación se hace mediante **selección inteligente de dónde analizar**, no mediante análisis pesado permanente de todos los activos.
