COMMIT 23 — AUTORIDAD PARALELA DE CALIDAD Q1-Q10

Reemplazar:
- quality_9q_engine_21.py
- premium_path_expansion_21.py
- Procfile
- render.yaml

Agregar:
- static/quality_filters_frontend.js

NO reemplazar:
- app.py
- static/script.js
- static/futures.js
- templates/index.html

Regla:
1 de 10 filtros >=75 + guards universales = confirmación.
Q10 no es un segundo veto obligatorio.
R/R es factor blando en operaciones rápidas.

QA:
python test_commit23_parallel_quality.py
Debe mostrar:
COMMIT 23 PARALLEL QUALITY QA: PASS
