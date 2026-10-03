# Commit 22 — changeset

## Reemplazar
- `quality_9q_engine_21.py`
- `premium_path_expansion_21.py`
- `Procfile`
- `render.yaml`

## No tocar
- `app.py`
- `static/script.js`
- `static/futures.js`
- `templates/index.html`

## Añadido funcional
- grupos de calidad contextual embebidos en `quality_9q_engine_21.py`
- matriz contextual de pesos Q1–Q9
- group score basado en evidencia
- bounded context composite (+5 máximo)
- multiasset session quality group

## Estabilidad
- request timeout 120s
- graceful timeout 15s
- worker recycle 80 requests + jitter 20
- un solo worker
- sin nuevos threads/network calls
