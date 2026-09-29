# Commit 17.5.10.1 — Opportunity Pipeline Integrity

## Base

Construido sobre HEAD verificado:
`68f90f313fa961693c7cebb09251bdc3e4265f31` — `Commit 17.5.10`.

## Archivos a reemplazar / agregar

Arrastrar conservando rutas:

- `app.py` — REEMPLAZAR.
- `pipeline_integrity_175101.py` — NUEVO en raíz.
- `market_maker_math.py` — REEMPLAZAR.
- `options_market_context.py` — REEMPLAZAR.
- `templates/index.html` — REEMPLAZAR.
- `static/market_maker_frontend.js` — REEMPLAZAR.

No reemplazar por este commit:
- `futures_system.py`;
- `leverage_policy.py`;
- `review_trader.py`;
- `execution_specialist_committees.py`;
- `worker_orchestration.py`;
- `static/script.js`;
- `static/futures.js`.

## Qué corrige

1. Multi usa su Strategy Bank por clase de activo antes de `candidate_ready`.
2. Todos los activos Multi pueden entrar a una cola; router-score sólo prioriza.
3. Un deep analysis por tick; backpressure por RAM/tráfico en vez de descarte por cuota.
4. Tres errores -> `RUNTIME_FAILED`, nunca `DONE` falso.
5. OOS viejo -> counter-evidence; no veto duro de una generación nueva.
6. HIGH: NO DATA de microestructura != mala microestructura.
7. Funnel/cache diagnostics y readback de persistencia para detectar Supabase equivocado/caído.
8. Logs de plantillas compactos por defecto.
9. Greeks/Black-Scholes/GEX visibles mediante endpoint ligero sin polling.

## Variables opcionales

No son obligatorias; los defaults son conservadores.

- `TRADING_VERBOSE_TEMPLATE_DIAGNOSTICS=0` (default): evita spam de condiciones.
- `PROFITABILITY_ROUTER_MIN_CACHE_SECONDS=1800`.
- `MULTIASSET_AUTO_KUCOIN_SOFT_MB_PER_DAY=48`.
- `MULTIASSET_AUTO_DEEP_MIN_INTERVAL_SECONDS=120`.
- `OPTIONS_CONTEXT_CACHE_SECONDS=3600`.

No aumentes estos límites para “forzar” señales sin revisar primero RAM/bandwidth y el funnel.

## Despliegue

1. Arrastra los seis archivos indicados a sus rutas.
2. Un solo commit: `Commit 17.5.10.1 — Opportunity Pipeline Integrity · Free Runtime · Greeks UI`.
3. Espera el deploy de Render.
4. Ctrl+F5.
5. Ejecuta el checklist de `VALIDACION_COMMIT_17_5_10_1.md`.

Este ZIP no ejecuta ni afirma un deploy a Render.
