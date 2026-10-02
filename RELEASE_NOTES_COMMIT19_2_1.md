# Release Notes — Commit 19.2.1

**Nombre:** Root Cause Quality Recovery

### Resuelto
- Multi-Activo ya recibe semántica por clase antes de Operational Intelligence y los 9 especialistas.
- Scheduler Multi basado en última vela cerrada con catch-up, no en ventanas exactas de reloj.
- Snapshot compacto local para no perder señales/análisis por recycle del worker.
- Router score pasa a prioridad, no gate de existencia de análisis profundo.
- Structural recovery nativo se gobierna por calidad real y reaction re-check, no por whitelist histórica.
- Scores Entry/SL/TP se sincronizan con los niveles finalmente seleccionados.
- Delta/Gamma/Vega/Theta teóricos numéricos para todos los activos con datos de mercado suficientes.
- La UI distingue métricas modelables de levels que requieren Open Interest real.

### No modificado
- Safety Premium
- R/R mínimo
- Leverage V6
- Guardian
- Champion backtests/geometría
- Alpha Decay 8+8
- workers/threads
- límites de RAM
- techo de deep jobs Multi
- proveedor directo de Options sólo BTC/ETH
