# Propuesta general — Commit 32 FINAL

## Objetivo
Corregir causas raíz sin bajar calidad ni mezclar responsabilidades entre señales globales y Guardian.

## Contratos por sistema

### SPOT — señal global de mercado
Objetivo: detectar oportunamente **COMPRA_SPOT, VENTA_SPOT y rotación BTC↔PAXG** con evidencia cuantitativa/técnica/algorítmica/contextual para favorecer, cuando corresponda, la acumulación de USDT, satoshis y PAXG/oro.

La señal es **global** y NO depende de las tenencias de ningún usuario. El `Portfolio Guardian` sigue siendo independiente por usuario/temporalidad y recibe la señal global después. Commit32 no incluye ni modifica `portfolio_guardian.py`.

Commit32 integra la nueva autoridad en el flujo moderno:
`Operational Intelligence -> pipeline_integrity.reconcile_operational_candidate -> 9 especialistas -> Strategy Bank -> geometry -> Safety -> Publication/OOS -> Guardian por usuario`.

No se parchea el legacy `vote_on_actions()`.

La autoridad SPOT:
- normaliza divergencias RSI/MACD y corrige aliases históricos;
- trata doble/triple techo/suelo como evidencia individual fuerte;
- detecta clusters de pivotes para rechazo repetido/soporte repetido;
- considera resistencia/soporte próximos;
- incorpora acumulación/distribución, OBV y proxies de ballenas;
- usa contexto macro sin fabricar dirección por sí solo;
- usa BTC, PAXG y PAXG/BTC como contexto relativo;
- expresa PAXG-BTC como `ROTACION_BTC_A_PAXG` o `ROTACION_PAXG_A_BTC`;
- nunca lee holdings del usuario;
- nunca salta Strategy Bank, geometry, Safety ni ruta OOS.

Si la nueva evidencia fuerte contradice una candidata legacy/generic y la dirección nueva no logra superar los gates existentes, se prefiere ESPERAR/NO_OPERAR antes que publicar la dirección contradictoria.

### FUTURES
Objetivo: entradas precisas y rápidas sin hacerlas más permisivas.

- CORE1: zona 0.12%, máximo 3 velas.
- CORE2: zona 0.11%, máximo 3 velas.
- MEDIUM: zona 0.08%, máximo 2 velas.
- HIGH: zona 0.05%, máximo 1 vela.

No cambia Entry/SL/TP calculado, RR, Safety, risk budget, leverage, Guardian, scale-in ni Champions/OOS. La rapidez viene de tolerancia más estrecha y menor vigencia, no de bajar filtros.

### MULTI-ACTIVO
No se inventan CORE/MEDIUM/HIGH. Se conserva la autoridad por clase de activo y evidencia OOS.

- 1h: FAST_LANE, zona <=0.08%, 1 vela.
- 4h: PRECISE_EXECUTION, zona <=0.10%, 2 velas.
- 1D: VALIDATED_SWING_CONTEXT, zona <=0.12%, 2 velas.

No convierte Research/Shadow en LIVE sin evidencia.

## Autoridad y snapshots
Commit31 seguía reutilizando una identidad de publicación `COMMIT30_1_PUBLICATION_AUDIT_V1`. Commit32 fuerza `COMMIT32_PUBLICATION_AUDIT_V2`, invalidando snapshots viejos como autoridad actual.

## RAM / Render
Se mantiene 1 worker / 2 gthreads y BLAS a 1 hilo. Se añaden:
- serialización de endpoints pesados legacy mediante el coordinador global;
- scheduler fail-closed si falta `SCHEDULED_AUTH_KEY`;
- auth para generación pesada de PDF;
- checkpoints RSS antes de heatmap, Operational Intelligence, 9 especialistas, geometry y publication;
- `shed` agresivo a 245 MB y abort limpio a 285 MB;
- `MEMORY_IN_JOB_ABORT_MB=285`;
- heatmaps residentes máximos = 4;
- compaction de `structure['df']`: evita copiar OHLCV a seis listas Python cuando downstream sólo consume la longitud temporal.

El objetivo es reemplazar reinicios OOM por backpressure/abort controlado de la celda pesada.

## Traders y comités
No se agregan traders ni comités. Se mantienen los 9 especialistas como **work products**, no como mayoría que controla la dirección. Operational Intelligence sigue siendo dueño de tesis, Strategy Bank del playbook, Geometry de Entry/SL/TP, Safety/Publicación de ejecutabilidad y ReviewTrader de evidencia estadística.

## Limpieza de commits anteriores
No se borran módulos antiguos a ciegas. Un archivo dormido no crea RAM/overfitting por existir. Commit32 consolida la autoridad activa y deja explícitamente fuera de la nueva autoridad SPOT el legacy `vote_on_actions`. Los módulos históricos que todavía son dependencias siguen disponibles.

La limpieza futura debe basarse en trazado de imports/call graph y telemetría, no en número de archivos.
