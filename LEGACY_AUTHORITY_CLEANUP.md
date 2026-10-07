# Commit32 — consolidación de autoridad legacy

## Se conserva porque sigue siendo dependencia funcional
- Operational Intelligence.
- `worker_orchestration` y 9 especialistas.
- Strategy Bank.
- Champion Registry / OOS.
- ReviewTrader / Research.
- Commit30 directional impulse.
- Commit30.1 fast-lane bridge.
- Commit31 8 Safety profiles.
- Portfolio Guardian.
- Supabase/Guardian lifecycle.

## Ya NO es autoridad SPOT de Commit32
- `expert_system.vote_on_actions()` como selector final de COMPRA/VENTA.

Commit32 no lo borra porque puede tener callers legacy; simplemente no lo parchea ni lo usa como nueva autoridad. La señal SPOT se reconcilia en `pipeline_integrity`.

## Regla de limpieza futura
Sólo eliminar un archivo cuando:
1. no exista import/caller productivo;
2. tests confirmen equivalencia;
3. no sea requerido para rollback/schema;
4. su telemetría sea cero durante una ventana razonable.

Esto evita que una "limpieza" rompa dependencias históricas mientras sí reduce autoridad duplicada y over-gating real.
