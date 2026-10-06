# COMMIT 27 — QA REPORT

## Tests de autoridad/calidad actuales

Suite:

- `test_commit27_contextual_core.py`
- `test_commit25_contextual_authority.py` (actualizado al contrato Commit 27)
- `test_commit23_parallel_quality.py`
- `test_commit22_context_quality.py`
- `test_commit24_3_repair.py` (asserts de autoridad actualizados: direct/cluster son diagnóstico)

Resultado: **42 passed**.

Cobertura específica Commit 27:

- ruta F30 validada + geometría primaria puede publicar;
- fallback nunca publica incluso con Q=100;
- max-Q no rescata un candidato sin quality gate;
- evidencia estructural F30 se exige post-geometría;
- Multi Energy 4h sin OOS queda Shadow;
- US Index 1D Champion puede publicar;
- Safety 74.99 bloquea;
- router F30 pre-Entry no exige campos post-Entry;
- Q9 bajo no bloquea dos veces cuando la ruta estadística LIVE ya aporta esa autoridad y Q1..Q8 conservan el quality contract.

## Compilación

- 261 módulos Python top-level: **0 errores**.
- `node --check static/futures.js`: PASS.
- `node --check static/script.js`: PASS.
- `node --check static/chart_workspace.js`: PASS.

## Tests legacy lifecycle

Suite histórica de 8 archivos: **38 passed / 14 failed**.

Se ejecutó el mismo bloque sobre el Commit 25 original y produjo **exactamente 38 passed / 14 failed**, con los mismos tipos de asserts legacy (firmas/textos antiguos de Telegram, frontend, event keys y funciones trasladadas). Por tanto no se clasifican como regresión Commit 27.

No se modifica producción para satisfacer tests que prueban strings/implementaciones obsoletas.

## Runtime / recursos

La nueva capa `contextual_quality_commit27.evaluate_publication` no ejecuta I/O.

Microbenchmark local bajo `tracemalloc`:

- 100,000 calls: ~19.7 s.
- ~197 µs/call.
- peak Python allocation: ~0.026 MB.

Nuevos recursos externos: 0 requests, 0 Supabase, 0 Groq, 0 threads, 0 loops.

## Limitación de entorno

El contenedor de auditoría no tiene Flask instalado, por lo que no se realizó import runtime completo de `commit27_main_entrypoint.py`. `py_compile` sí valida sintaxis de todos los módulos y producción instala Flask mediante `requirements.txt`.
