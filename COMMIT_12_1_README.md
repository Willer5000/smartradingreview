# Commit 12.1 FINAL · Multi-Activo QA + IA gobernada + Research

Base requerida: **Commit 12 ya desplegado**. Esta versión reemplaza cualquier ZIP 12.1 anterior.

## MAIN — cambios

### Consejo IA: un mismo cerebro, cadencia por mercado
- Spot: refresco máximo **cada 4 h**.
- Futures: refresco máximo **cada 30 min**.
- Multi-Activo: refresco máximo **cada 1 h**.
- Cada Consejo recibe un `cross_market_snapshot` de los tres mercados **sólo desde caché local**: no refresca motores, no consulta Supabase y no dispara otra llamada IA.
- Presupuesto Groq global sin aumento: `AI_GROQ_DAILY_TOKEN_BUDGET=160000`, reserva 8000.
- Salida máxima del Consejo recurrente: **450 tokens**. Chat manual: 700. Learning conserva 900.

### Asistente IA: cuotas por pestaña
- Spot: **3 preguntas / 4 h**.
- Futures: **1 pregunta / 30 min**.
- Multi-Activo: **1 pregunta / 1 h**.
- El límite diario global manual sigue existiendo; cambiar de pestaña no crea un presupuesto global nuevo.
- La cuota se carga a la pestaña desde la que el usuario pregunta (`quota_market`), pero el resolver puede analizar otro mercado si el prompt menciona claramente el activo. Esto permite usar otra pestaña cuando su cuota propia siga disponible.
- Hasta **7 activos mencionados** en una sola pregunta, con una sola ficha compacta por activo.
- Prompts simples también funcionan.
- Frontend lo explica discretamente en texto pequeño.

### QA Commit 12 conservado
- `/api/price?...market=multiasset` usa Multi-Activo, no Spot.
- Microestructura Multi no llama `/api/futures/microstructure`.
- `/multiasset` tiene prioridad interactiva y comparte el único slot pesado.
- Polling Multi acotado (sin carga infinita por reintentos).
- Analytics separa Multi-Activo de Futures y permite volver a Multi.
- Guía/Información actualizada.
- Nombres humanos: `CL (Petróleo WTI)`, `SPY (S&P 500)`, etc.
- Listas técnicas tipo `Volumen: ['rechazo_intrabarra', ...]` se humanizan antes de mostrarse.
- Microestructura/liquidaciones se etiquetan como proxy cuando no existe evidencia real.
- PDF de análisis eliminado; PDF de aprendizaje preservado.

### Operaciones guardadas por usuario
No se cambia el contrato existente. El Guardian Multi sigue consultando señales con `user_name=user`; las señales guardadas permanecen aisladas por usuario.

## RESEARCH — paquete coordinado
El segundo ready-tree va en el repositorio `Willerman5000/smartradingresearch`.

- No amplía el contrato cripto pesado de 60 celdas.
- Reutiliza **sólo el servicio Strategy Research existente**.
- 5 representantes por clase: SPY, CL, COPPER, XAG, KSTR.
- Backtest causal/OOS en **4H y 1D**, alternados cada 6 h.
- Máximo **10 celdas por corrida** (5 representantes × LONG/SHORT).
- QQQ y NATGAS reciben sólo prior de clase; no Champion prestado.
- Split causal: Discovery 60% / Selection 20% / Final OOS 20%.
- Final OOS no participa en ranking de candidatos.
- 0 LLM, 0 servicio nuevo, 0 thread nuevo, 0 tabla nueva, 0 SQL.
- Findings en `research_findings_v1` con `authority=RESEARCH_ONLY` y `class_prior_only=true`.
- La 1H permanece Fast Lane/live hasta tener evidencia suficiente; no se añade al backtest pesado inicial.

## Deploy
Se requieren dos commits físicos porque son dos repositorios:
1. Main: `Commit 12.1 - QA Multi-Activo, IA gobernada y separación por mercado`
2. Research: `Commit 12.1 Research - Backtest OOS Multi-Activo acotado`

No ejecutar SQL. No cambiar Render env para usar los valores seguros por defecto.
