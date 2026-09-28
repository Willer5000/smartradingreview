# Diagnóstico Commit 17.3.1

## Hallazgo 1 — Futures
Commit 17.3 sí detecta una caída fuerte y puede construir SHORT; una prueba sintética dio candidato SHORT en CORE, MEDIUM y HIGH. El problema era posterior: `mtf_usable = not conflict` funcionaba como veto absoluto. En una transición, 30m/1h/2h pueden girar antes de 4h; el sistema descartaba precisamente el movimiento que `STRUCTURE_REVERSAL`/`MOMENTUM_CONTINUATION` debían cubrir.

La corrección no elimina MTF. Sólo admite en CORE/MEDIUM (30m/1h/2h) un retraso del marco de contexto cuando estructura, setup y timing ya están alineados, el tipo de estrategia es apto para transición, existen suficientes familias independientes locales y el margen direccional supera el normal en +0.60. HIGH continúa estricto.

## Hallazgo 2 — Multi-Activo
Multi-Activo reutiliza `system_type=futures`, pero `official_cell` sólo reconocía símbolos cripto. SPY/QQQ/CL/NATGAS/COPPER/XAG/KSTR podían tener tesis técnica pero quedar fuera de celda gobernada antes de llegar al router Multi-Activo. Ahora esas 7×4 TF×LONG/SHORT son reconocidas como celdas operacionales Multi-Activo y delegan la familia específica a `multiasset_system.py`.

## No modificado
Safety, Economics, R/R, Entry/SL/TP, Publication Gate, Liquidation Map, frontend, thresholds HIGH y aprendizaje no se relajan.
