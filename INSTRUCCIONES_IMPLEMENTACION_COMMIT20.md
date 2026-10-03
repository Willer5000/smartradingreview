# Commit 20 — Premium Path Expansion (PPE)

## Objetivo

Implementar la propuesta de **Premium Path Expansion** para aumentar la frecuencia de oportunidades de calidad sin bajar ningún contrato Premium.

El commit NO cambia:

- Safety mínimo Premium: 75
- TP Quality mínimo: 55
- SL Quality mínimo: 60
- R/R mínimo: 1.8
- R/R máximo: 3.5
- pérdida estimada en SL
- estrés ATR
- Alpha Decay
- número de workers/threads
- APIs de mercado adicionales
- polling adicional

## Archivos para reemplazar/agregar

Arrastrar estos archivos al repositorio en VS Code/GitHub Web:

```text
commit20_main_entrypoint.py
premium_path_expansion_20.py
static/futures.js
static/script.js
templates/index.html
Procfile
render.yaml
schema_commit20_premium_path.sql
```

No borrar otros archivos del proyecto.

## Paso obligatorio de Supabase

Abrir el SQL Editor del mismo proyecto Supabase que usa SmarTradingReview y ejecutar:

```text
schema_commit20_premium_path.sql
```

Es idempotente y solamente agrega columnas/índices.

### Muy importante

El SQL es necesario para que las señales Multi-Activo guardadas puedan almacenar `market_type`, `asset_class` y `data_provider`. Sin esta migración, el nuevo backend puede rechazar el insert por columna inexistente.

## Qué cambia PPE

### 1. Candidate Route Expansion

Después de la geometría nativa, PPE puede evaluar como máximo **2 rutas alternativas** cuando la geometría inicial está lejos de ser Premium o usa recuperación/fallback.

Las rutas se seleccionan usando únicamente datos ya calculados:

- régimen;
- volatilidad;
- liquidez/sweep/MSS;
- compresión;
- estructura;
- asset class;
- sesión/contexto Multi-Activo.

No se descargan datos nuevos.

### 2. Las rutas no votan

Las rutas son candidatos de **Entry/SL/TP** para una dirección que ya existe.

Nunca:

- crean LONG/SHORT;
- cambian la dirección;
- suman votos de especialistas;
- convierten fallback en Premium.

El paquete geométrico con mayor calidad interna gana y recién después vuelve a pasar por Safety, CPQE y Publication Gate.

### 3. Premium Funnel

Cada resultado mantiene un diagnóstico con:

```text
premium_blocker_stage
premium_blocker_codes
premium_route
premium_path_expansion_20
```

Esto permite saber si una oportunidad murió por:

```text
ECONOMIC_RISK
RR
SL_QUALITY
TP_QUALITY
SAFETY
CPQE_FAIL
PUBLICATION_GATE
```

### 4. Multi-Activo Saved Signals

Saved Signals deja de consultar siempre Futures perpetual.

Si una señal guardada tiene:

```text
market_type = multiasset
```

el detalle obtiene las velas mediante `MultiAssetAnalysis`.

La card de Saved Signals también queda visible en Multi-Activo.

## Runtime

El entrypoint nuevo conserva Commit 19.x cuando está disponible y agrega PPE después de CPQE. Si el overlay legacy no puede importarse, el sistema arranca en modo fail-open y `/health` informa el problema; PPE nunca debe impedir el boot.

## Validación mínima antes de desplegar

1. `python -m py_compile commit20_main_entrypoint.py premium_path_expansion_20.py`
2. `node --check static/futures.js`
3. `node --check static/script.js`
4. Ejecutar tests/QA existentes del repositorio.
5. Después del deploy abrir:

```text
/health
/futures
/multiasset
```

En `/health` debe aparecer:

```text
runtime_contract.commit = 20
runtime_contract.ppe_installed = true
runtime_contract.premium_thresholds_unchanged = true
```

## Criterio de éxito

NO existe una cuota diaria de señales.

El éxito se mide por:

- más rutas primarias válidas;
- menor dependencia del fallback;
- menor cantidad de `NO_PRIMARY_GEOMETRY`;
- mayor cobertura de celdas que llegan a Research/Champion;
- más oportunidades Premium **sin** cambiar los umbrales.

## Rollback

Para volver a Commit 19.2.4:

- restaurar el entrypoint anterior;
- restaurar `static/futures.js`, `static/script.js` y `templates/index.html` anteriores;
- no ejecutar el SQL de rollback destructivo.

Las nuevas columnas de Supabase son aditivas y pueden permanecer durante el rollback.
