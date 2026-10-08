# QA — Commit 33.4.1 Canonical Flow Recovery

## Veredicto
Commit 33.4 eliminó gran parte de la arquitectura de overlays, pero conservó tres cuellos de botella funcionales dentro del propio camino LIVE: una segunda autoridad de dirección (`contingency_strategy_engine`) posterior al router canónico, un segundo veto de setup dentro/después de Geometry y un segundo scoring direccional en Publication. Además, los snapshots podían sobrevivir al deploy con contratos de autoridad anteriores y perder campos del candidato canónico durante la compactación.

Commit 33.4.1 corrige esas causas en el núcleo. No introduce `install_*`, monkeypatch, nuevo entrypoint ni runtime overlay. `app:app` continúa siendo la única autoridad de arranque.

## Cambios de arquitectura
1. `technical_evidence.py` absorbe la normalización pura de familias técnicas que antes obligaba a Operational Intelligence a importar Contingency.
2. Pipeline Integrity emite un `candidate_contract` explícito. La madurez direccional se decide una sola vez.
3. Publication deja de imponer un segundo score direccional superior sobre la misma evidencia. Conserva gates independientes: vela cerrada, datos reales, geometría primaria, RR/economía, Safety especializado y hard risk.
4. `contingency_strategy_engine` sale completamente del grafo LIVE. No puede cambiar dirección, capar confianza ni degradar un candidato antes de Entry/SL/TP.
5. `execution_setup_guard` queda diagnóstico-only después de Geometry. Ya no puede convertir una geometría primaria aprobada por los comités en fallback/ANALYSIS_ONLY antes del Safety final.
6. Se elimina la segunda reconstrucción manual post-Geometry. La geometría manual existe sólo para visibilidad de una tesis no publicable y nunca puede promoverse.
7. Futures incrementa schema de snapshot a 5, exige `pipeline_generation=33.4.1` y autoridad de publicación 33.4.1; análisis antiguos se descartan conservando lifecycle.
8. El snapshot compacto conserva `candidate_source`, `candidate_contract`, setup/support y `pipeline_generation`.
9. Multi local snapshot usa schema 33.4.1 y ruta `/tmp` nueva, evitando restaurar estado efímero de generaciones previas.
10. Los nombres activos de Funnel/Publicación/Safety dejan de declarar autoridad Commit28/31 y pasan a identidad neutral 33.4.1.

## Gates que NO se relajaron
- fallback/manual geometry sigue sin poder publicar;
- Safety especializado debe quedar `ready`;
- hard risk por SL/ATR permanece no compensatorio cuando existe una medición real;
- RR debe permanecer dentro del rango del perfil;
- datos sintéticos/no verificados no publican;
- una vela no cerrada no publica;
- IA/LLM no crea ni publica dirección;
- no existe cuota mínima artificial de señales.

## Tests de 33.4.1
Comando:

```text
python -m pytest -q test_commit33_4_core.py test_commit33_4_1_core.py test_rc9_8_execution_geometry.py test_execution_learning.py
```

Resultado:

```text
44 passed
```

Cobertura específica añadida:
- no hay autoridad LIVE de Contingency;
- Operational Intelligence no importa Contingency;
- schema/cache viejo se invalida;
- compact snapshot conserva contrato canónico;
- dirección no se scorea dos veces;
- Multi local snapshot exige 33.4.1;
- `execution_setup_guard` es diagnóstico-only;
- geometría manual no puede promoverse;
- runtime usa una sola identidad 33.4.1;
- archivos activos no importan cores borrados 28/29/30 ni ABI/overlays históricos.

## Regresión histórica comparativa
Se ejecutó además:

```text
python -m pytest -q \
  test_commit25_contextual_authority.py \
  test_commit26_causal_preentry.py \
  test_commit27_contextual_core.py \
  test_commit17_5_execution_hardening.py \
  test_commit15_execution_intelligence.py \
  test_commit13_execution_geometry_v2.py \
  test_commit9_net_edge_leverage.py
```

Baseline Commit 33.4 recibido:

```text
44 passed, 10 failed
```

Commit 33.4.1:

```text
44 passed, 10 failed
```

Los 10 fallos son idénticos al baseline y corresponden a contratos históricos incompatibles con decisiones posteriores del repositorio (Commit26, texto UI Commit15 y política de leverage Commit9). Commit 33.4.1 no añade fallos a ese conjunto.

## Compilación y dependencias activas
`py_compile` validado para:
- `app.py`
- `futures_system.py`
- `multiasset_system.py`
- `operational_intelligence.py`
- `technical_evidence.py`
- `market_context.py`
- `pipeline_integrity.py`
- `publication_quality.py`
- `safety_profiles.py`
- `worker_orchestration.py`

El grafo core anterior no contiene referencias a:
- `commit28_core`
- `commit29_core`
- `commit30_core`
- `premium_path_expansion_20`
- `pipeline_integrity_175*`
- `execution_abi_175*`
- `contingency_strategy_engine`

`contingency_strategy_engine.py` puede permanecer como artefacto histórico porque no está en el grafo LIVE; eliminarlo no cambia memoria ni frecuencia. La limpieza se basa en call graph, no en el nombre/edad del archivo.

## Verificación obligatoria en Render
1. `/api/runtime/version` → `COMMIT33_4_1_CANONICAL_FLOW_V1`.
2. Boot → `✅ [33.4.1] núcleo canónico activo`.
3. Debe aparecer la invalidación del schema anterior Futures en el primer arranque con cache vieja.
4. A partir del boot 33.4.1 no deben aparecer nuevos `ModuleNotFoundError` de `commit28_core`, `commit29_core`, `commit30_core` o `premium_path_expansion_20`.
5. Un candidato canónico debe conservar `candidate_contract` hasta Publication.
6. Si Entry/SL/TP son primarios y Safety está READY, un candidato no debe transformarse a `FALLBACK_GEOMETRY_NOT_PUBLISHABLE` por un segundo setup gate.

No se considera validación productiva hasta observar un ciclo real de cierre de vela posterior al deploy.
