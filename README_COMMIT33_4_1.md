# Commit 33.4.1 — Canonical Flow Recovery

## Objetivo
Eliminar cuellos de botella estructurales que sobrevivieron a la limpieza 33.4 sin bajar Safety ni fabricar señales.

## Causas raíz corregidas
1. **Segundo gate de dirección**: `contingency_strategy_engine` podía degradar un candidato canónico después de Pipeline Integrity y antes de Entry/SL/TP. Se retira del camino LIVE.
2. **Doble scoring direccional**: Pipeline Integrity aprobaba una tesis y Publication volvía a exigir un score direccional más alto sobre la misma evidencia. Ahora la madurez direccional se evalúa una sola vez; Publication conserva Primary Geometry + Safety + hard-risk + economía.
3. **Snapshots 33.4/pre-33.4 reutilizables**: se incrementa el schema Futures y la identidad de autoridad. Análisis viejos se descartan; lifecycle Saved/Guardian se preserva.
4. **Compactación incompleta**: se conservan `candidate_source`, `candidate_contract`, setup/core support y `pipeline_generation`, de modo que una vela reutilizada mantiene la misma autoridad causal.
5. **Multi local snapshot antiguo**: el snapshot efímero Multi ahora exige schema 33.4.1.
6. **Dependencia activa de Contingency para normalizar indicadores**: Operational Intelligence usa `technical_evidence.py`, un módulo puro del núcleo.

## Lo que NO cambia
- No se baja ningún Safety crítico.
- Fallback/manual geometry sigue sin poder publicarse.
- No se fuerza una cuota de señales.
- No se crea dirección desde IA/LLM.
- No se añade un overlay, monkeypatch ni nuevo entrypoint.
- `app:app` sigue siendo la única autoridad de arranque.

## Pipeline 33.4.1
Market Data → Technical Evidence/Context → Operational Intelligence → Pipeline Integrity (candidate contract) → Specialist work products → Entry Committee → SL Committee → TP Committee → Safety → Publication → Guardian.

`contingency_strategy_engine.py` queda fuera del grafo LIVE. Puede conservarse como artefacto histórico, pero ninguna ruta de producción lo importa.

## Verificación post-deploy
- `/api/runtime/version` debe mostrar `COMMIT33_4_1_CANONICAL_FLOW_V1`.
- Boot: `✅ [33.4.1] núcleo canónico activo`.
- No deben aparecer nuevas importaciones de `commit28_core`, `commit29_core`, `commit30_core` ni `premium_path_expansion_20` desde el proceso 33.4.1.
- Tras el primer arranque, los análisis Futures de schema anterior deben ser descartados y sólo se preserva lifecycle.
- Un candidato `THESIS_CORE`/`CORE_SETUP` que supera el contrato canónico debe llegar a Entry/SL/TP sin ser degradado por Contingency.
- `FALLBACK_GEOMETRY_NOT_PUBLISHABLE` sigue siendo correcto sólo para geometría realmente manual/fallback.
