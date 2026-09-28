# PROMPT MACRO DE CONTINUIDAD — POST COMMIT 17.4 FINAL R3

Proyecto: **SmartradingReview / Crypto Trader Analyst Pro**
Estado de referencia: **Commit 17.4 FINAL R3 — Trading Audit Closure**.

## Misión
Sistema técnico de análisis y ejecución para tres mercados diferenciados:
- **SPOT:** snowball/rotación para aumentar BTC (satoshis), PAXG (oro) y USDT con el tiempo.
- **FUTURES CRYPTO:** operaciones rápidas de alta calidad, diferenciadas por CORE / MEDIUM / HIGH.
- **MULTI-ACTIVO:** objetivo rápido similar a Futures, pero con lógica por clase de activo, sesión, macro, volatilidad y comportamiento propios.

Política: **“Asertivo pero cauto, precavido pero no tímido y sobre todo rentable.”**
No fabricar señales por frecuencia. No bajar Safety/R:R/calidad. No perseguir precio. No prometer rentabilidad.

## Arquitectura obligatoria
1. Datos + indicadores.
2. Contexto de mercado/clase/sesión/macro.
3. Régimen + volatilidad relativa.
4. Multitemporalidad (Context / Structure / Setup / Timing).
5. Tesis independiente por familias no correlacionadas.
6. Selección de estrategia contextual.
7. 9 especialistas internos como evidencia/challenge, no mayoría ciega.
8. **Confirmación de señal direccional.**
9. Entry Committee busca mejor zona de reacción/alcanzabilidad.
10. SL Committee busca invalidación real, difícil de tocar y fuera de zonas de reacción, con economía de leverage como ranking.
11. TP Committee busca touch probability + estructura + R/R + economía sobre margen, capturando antes de reacción relevante.
12. R/R/Safety/leverage deciden `execution_ready`, no borran la señal confirmada.
13. Guardian protege MFE y puede extender TP sólo con estructura/momentum/economía favorables.
14. ReviewTrader/Research/OOS gobiernan evidencia estadística; small-N no crea hard veto.

## Estados
- `EXECUTABLE_SIGNAL`: dirección confirmada + ejecución lista.
- `CONFIRMED_PENDING_EXECUTION`: dirección confirmada, esperando geometría válida; tamaño 0 hasta ejecutar.
- `ANALYSIS_ONLY`: todavía no existe señal confirmada.
- `NO_TRADE`: no existe tesis suficiente.

## Cambios clave de R3
- Spot anti-FOMO ya NO cambia COMPRA/VENTA a ESPERAR; conserva señal y aplaza ejecución.
- Contingency Playbook reutiliza `operational_intelligence.context.macro_reasoning/research_reasoning`; no reintroduce CRITICAL==veto ni small-N negative==veto.
- Multi-Activo inyecta macro/sesión/clase antes de Operational Intelligence usando caché (`fetch_if_stale=False`).
- Router Multi-Activo usa el mismo OHLCV y cuatro carriles: Trend/Momentum, Expansion/Breakout, Reversal/Mean-Reversion y Compression/Release. Es high-recall, NO genera señal.
- R2 de Execution Quality sigue vigente: leverage sólo ayuda a rankear geometría; motor de riesgo fija leverage final.

## Recursos
No añadir requests externos, polling, llamadas Groq/LLM, escrituras Supabase, workers o threads salvo necesidad demostrada. Render/RAM, ancho de banda, Supabase y tokens deben mantenerse en cuota gratuita/limitada.

## Validación de referencia
- 54/54 Commit 17.3
- 29/29 Adaptive Reasoning
- 10/10 Signal/Execution Decoupling
- 6/6 Execution Quality
- 15/15 R3 Trading Audit Closure
- Python/JS PASS

## Etapa actual
Después de desplegar R3: **congelar arquitectura y entrar en segunda etapa de evaluación**. No modificar por “pocas señales”. Evaluar expectancy neta, PF, WR, MAE/MFE, MFE giveback, DD, losing streaks, Entry/SL/TP, pending->execution y resultados por mercado/símbolo-clase/TF/dirección/familia. Sólo autorizar nuevos cambios con regresión reproducible o evidencia estadística/OOS suficiente.

Baseline de etapa 1 informado por el usuario: aproximadamente **50% WR y +5% rentabilidad** antes del ciclo de correcciones iniciado por tres reacciones consecutivas alrededor del SL.
