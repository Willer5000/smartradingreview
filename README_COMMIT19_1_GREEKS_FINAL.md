# Commit 19.1 FINAL — Champion + Live Quant Synthesis + Greeks Execution Context

Fecha: 2026-10-01

## Objetivo

Este release sustituye al Commit 19.1 anterior. Si todavía no se implementó 19/19.1, desplegar **sólo este release final**.

Combina dos vías LIVE:

1. **Champion Lane**: conserva los Champions IS/OOS rentables de Commit 19 y su geometría auditada.
2. **Native Quant Synthesis Lane**: los 9 especialistas + ReviewTrader forman una tesis contextual y los comités Entry/SL/TP construyen una geometría ejecutable sin volver a una votación por mayoría.

Añade una tercera capa de contexto de ejecución:

3. **Greeks / Options Reaction Map**: sirve como confluencia acotada para Entry/SL/TP. Nunca crea dirección, Entry/SL/TP standalone, leverage ni bypass de Safety/R/R.

## Greeks en todos los mercados

El frontend muestra el gráfico de Greeks en **Spot, Futures y Multi-Activo**.

- BTC/ETH Spot/Futures: cuando la cadena pública directa está disponible, usa cadena observada y puede aportar confluencia productiva acotada.
- Resto de activos Spot/Futures/Multi: muestra superficie Black-Scholes teórica con Delta/Gamma/Theta/curvas para contexto visual. Esos datos teóricos tienen **cero autoridad para modificar Entry/SL/TP**.

Esto evita inventar dealer positioning donde no existe Open Interest de opciones directo y confiable.

## Reglas anti-overfitting

- Un nivel de opciones nunca crea una señal LONG/SHORT.
- Un nivel de opciones no puede crear una zona de Entry desde cero.
- Entry: sólo desempata/refuerza candidatos técnicos ya válidos.
- SL: sólo penaliza un stop que colisiona con una zona observada de reacción; no crea un stop nuevo por sí solo.
- TP: sólo ayuda a rankear un target técnico existente y favorece quedar antes de una barrera observada cuando el R/R sigue siendo válido.
- Peso Entry options = 0.40; SL = 0.45; TP = 0.45, por debajo de las familias técnicas principales.
- Greeks no entran en el núcleo armónico de calidad.
- Champions conservan su geometría auditada; la capa Champion se aplica después de la selección base de comités.

## Recursos

Render permanece con:

- 1 worker
- 2 threads
- MEMORY_SOFT_LIMIT_MB=220
- MEMORY_HARD_LIMIT_MB=300
- MEMORY_JOB_START_LIMIT_MB=200

Greeks añade:

- cero threads de background;
- cero llamadas LLM;
- cero polling del navegador;
- proveedor observado sólo BTC/ETH;
- TTL del proveedor: 7200 s;
- máximo por respuesta: 1.5 MiB;
- presupuesto proveedor: 12 MiB/día, máximo contable aproximado 360 MiB/30 días;
- máximo 220 filas normalizadas del proveedor;
- contexto compacto en el hot path: curvas completas eliminadas antes de ejecución.

El límite de 12 MiB/día controla el **incremento atribuible al proveedor de Greeks**. El total mensual de Render también depende de respuestas HTTP, resto de feeds, tráfico real y reinicios, por lo que debe seguir observándose en el dashboard de Render; este release no eleva los presupuestos existentes del sistema.

## QA de release

- Greeks final: 34/34 PASS
- Quant Synthesis 19.1: 13/13 PASS
- Commit 19 heredado: PASS
- 17.5.11R.1 heredado: 18/18 PASS
- Python compileall: PASS
- JS node --check: PASS
- Backtest Champion Commit 19: PASS

## Backtest

El backtest de los Champions no cambia por introducir Greeks. El release conserva los resultados auditados de Commit 19. En particular, el replay 30m físicamente incluido mantiene:

- IS: N=11, +1.702R, expectancy +0.1547R, PF 1.254
- OOS: N=4, +3.928R, expectancy +0.9820R, PF 4.513
- Total: +5.630R, PF 1.719

No se declara un “backtest de Greeks” histórico porque el ZIP no contiene snapshots point-in-time completos de cadenas de opciones para reconstruir sin look-ahead la nueva confluencia. Inventar ese resultado sería overfitting. La capa Greeks es deliberadamente un refinador de baja autoridad y su desempeño deberá registrarse por ReviewTrader para futura validación causal.
