# Auditoría Commit 33.3 — reparación del núcleo actual

## Alcance corregido

Commit 33.3 NO restaura el `main` antiguo. Ese snapshot se usó únicamente como control histórico para responder una pregunta: **¿qué cambió entre una versión que sí producía dirección y el runtime actual que termina casi todo como fallback?**

Se preservan expresamente:

- temporalidad operativa mínima Futures = **30m**;
- los comités **Entry / SL / TP** del código actual;
- SL estructural y el veto de reacción/conflicto del SL;
- TP único, realista y probable, construido con estructura/liquidez/Fibonacci/imbalances y la evidencia ya disponible;
- los 8 Safeties especializados de Commit31;
- hard-risk, RR/economics, OOS/Champion/Publicación;
- Guardian independiente por usuario.

## Evidencia de producción que explica por qué 32.2 no resolvió el problema

1. Producción seguía mostrando 0 señales y 14 hipótesis dominadas por `FALLBACK_GEOMETRY_NOT_PUBLISHABLE`.
2. Seguía apareciendo `PREMIUM_SAFETY_BELOW_75`, aunque la arquitectura moderna declara que el umbral universal Safety>=75 ya no es autoridad final.
3. Seguía ocurriendo `FuturesAnalysis.calculate_entry_levels() got an unexpected keyword argument 'execution_observations'`.
4. `/api/futures/visuals` seguía devolviendo respuestas de ~180 bytes cuando RSS/heavy pressure activaba `deferred`, de modo que el navegador no recibía `df` y no podía dibujar.
5. Los logs seguían imprimiendo `COMMIT21.1 overlay activo` con memory policy ~215/235/300 MB.
6. El RSS operativo real se movía repetidamente por ~220–306 MB. Un start limit ~215 MB convertía la protección de RAM en un bloqueo recurrente.

## Comparación con el main antiguo

El main antiguo sí generaba señales direccionales, pero:

- no contenía los comités modernos Entry/SL/TP;
- no tenía el ABI `execution_observations`;
- su debilidad principal conocida era la geometría del SL;
- por tanto NO es una base segura para producción actual.

Su utilidad para esta auditoría es otra: arrancaba directamente con `gunicorn app:app` y no tenía la cadena de entrypoints 32.x.

## Causas raíz encontradas en el código actual

### 1. El ABI nativo actual está bien; la cadena de wrappers lo vuelve inconsistente

El `app.py` actual y `futures_system.py` actuales ya admiten `execution_observations`. `MultiAssetAnalysis` hereda ese contrato. Sin embargo, 32.0, 32.1 y 32.2 vuelven a envolver esas funciones secuencialmente desde el entrypoint WSGI.

Conclusión: el TypeError de producción no exige volver al método antiguo. Exige **dejar de envolver el ABI nativo correcto**.

### 2. `premium_path_expansion_20` reinstala una política de memoria obsoleta

`app.py` auto-instala ese módulo al final del import. El módulo vigente vuelve a escribir los límites de memoria de app/runtime a aproximadamente 210–225 MB para inicio, 235 MB soft y 280–300 MB hard.

Eso coincide con los logs y pisa los valores configurados en Render.

### 3. El carril de gráficos no es realmente independiente

El endpoint liviano `/api/futures/visuals` devuelve `deferred=True` si LOW_MEMORY_MODE está activo y existe heavy owner o RSS>=210 MB. El frontend necesita `df.time` para dibujar. Por eso el backend responde HTTP 200 pero la pantalla queda vacía.

### 4. Existe over-selection ANTES de los comités Entry/SL/TP

El router particular actual puede exigir simultáneamente todos los `core`, MTF sin conflicto, Strategy Bank, official cell y pisos de calidad diferentes por risk class (CORE~82, MEDIUM~85, HIGH~88) antes de dejar existir al candidato.

Eso es conceptualmente incorrecto para la finalidad de HIGH/MEDIUM: **risk class debe cambiar rapidez/exposición/Safety, no la cantidad de indicadores correlacionados necesarios para que una hipótesis llegue a Geometry**.

## Solución 33.3

### A. Autoridad de arranque única

`Procfile` y `render.yaml` vuelven a `gunicorn app:app`.

Los entrypoints 31/32/32.1/32.2 se conservan sólo como shims inertes para proteger contra un Start Command manual antiguo. Ninguno instala runtime patches.

### B. Commit21.1 neutralizado

`premium_path_expansion_20.py` se reemplaza por una compatibilidad estrecha que:

- NO modifica dirección;
- NO modifica candidatos;
- NO modifica Entry/SL/TP;
- NO modifica Safety;
- NO modifica publicación;
- NO modifica memoria;
- sólo conserva runtime truth y el carril visual OHLC-only.

### C. Visual lane realmente liviano

Los gráficos pueden descargar 120 velas OHLC sin pedir el heavy lock. Sólo se difieren cerca de 430 MB RSS, no a 210 MB.

### D. Router de candidatos 33.3

`pipeline_integrity_175101.py` conserva el import histórico pero apunta a `pipeline_integrity_175103.py`.

El router base actual se ejecuta PRIMERO. Sólo si no produce candidato, 33.3 aplica un segundo contrato setup-aware:

- Trend Pullback: MTF estricto.
- Breakout Retest: MTF estricto.
- Directional Impulse: MTF contextual; conflicto/oposición exige confirmación adicional.
- Sweep Reversal: MTF contextual; sweep obligatorio + MSS o structure + confirmaciones independientes.
- Compression Expansion: MTF contextual con confirmación adicional.
- Range Mean Reversion: range + extreme + location; momentum pasa a confirmación, no doble gate.

La calidad pre-candidato Futures deja de depender de CORE/MEDIUM/HIGH. El piso técnico es común; la diferencia entre clases permanece downstream.

### E. Tempo Futures migrado a núcleo

El comportamiento rápido que Commit32 instalaba por monkeypatch se conserva, pero ahora vive en `futures_universe.py`:

- CORE1: zona 0.12%, 3 velas.
- CORE2: zona 0.11%, 3 velas.
- MEDIUM: zona 0.08%, 2 velas.
- HIGH: zona 0.05%, 1 vela.

Esto cambia sólo reacción/vigencia de una oportunidad ya válida. No toca Entry/SL/TP calculados, Safety, RR ni OOS.

### F. SPOT Market Signal Authority preservada sin WSGI patch

La lógica global SPOT introducida en Commit32 no se pierde. `pipeline_integrity_175103.py` la invoca de forma explícita para BTC-USDT, PAXG-USDT y PAXG-BTC. No lee tenencias ni modifica Guardian.

### G. Nada salta los filtros finales

Un candidato recuperado todavía debe pasar:

`Entry committee -> SL committee -> TP committee -> Safety especializado -> hard risk/RR -> OOS/Publicación`.

No se publica fallback. No se introduce Safety>=75 universal. No se fabrican Champions.

## Qué NO hace este commit

- No añade 15m.
- No activa CRT/Triple RSI/Failed Auction/Opening Range/Efficiency Ratio/Compression Release en LIVE.
- No vuelve al SL antiguo.
- No reemplaza los comités Entry/SL/TP.
- No modifica Guardian.
- No baja RR ni Safety.

Las seis estrategias nuevas deben estudiarse después con histórico 30m real IS/OOS; mezclarlas con esta reparación impediría saber si la recuperación provino del núcleo o de una estrategia nueva.
