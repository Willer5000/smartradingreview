# Commit 23 — Parallel Quality Authority

Base: Commit 22 Context Quality Groups.

## Cambio central

Una hipótesis puede convertirse en señal confirmada cuando **al menos uno de Q1..Q10 alcanza 75/100** y los guardas universales de ejecución pasan.

## Q10

Q10 ya no actúa como veto secuencial obligatorio.
Su contrato legado permanece visible y sin modificar.

## R/R

En rutas rápidas 30m/1h, R/R se convierte en factor blando, no en veto universal del nuevo camino paralelo.

## Frontend

Se añade `static/quality_filters_frontend.js` para mostrar el filtro de autoridad, score y resumen Q1..Q10 también dentro de “Por qué no aparecen otras señales”.

## No app.py

`app.py`, `static/script.js`, `static/futures.js` y `templates/index.html` no se reemplazan.

## Estabilidad

Se conservan timeout 120s y reciclado del worker de Commit 22.
