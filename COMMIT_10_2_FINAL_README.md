# Commit 10.2 FINAL · Outbound Bandwidth + Telegram texto

Base: Commit 10 ya desplegado. Este entregable absorbe los cambios aprobados de 10.1 y añade el cierre final de bandwidth.

## Qué cambia

- Telegram queda **text-only**. `sendPhoto` y `sendDocument` dejan de existir en el backend operativo.
- Las alertas de señal incluyen un **deep-link a la señal concreta** (`/signal/<signal_id>`), no un enlace genérico a la página.
- Se elimina el endpoint del **PDF de análisis** (`/api/generate_report`) y su transporte Telegram.
- El frontend elimina el control operativo del PDF de análisis al cargar `script.js`.
- El **PDF de aprendizaje** se conserva íntegro (`/api/review/learning_pdf` + `pdf_learning_report.py`).
- Spot Guardian Telegram conserva privacidad por porcentajes; los montos nominales quedan en la web autenticada.
- Futures Guardian conserva formato compacto.
- Consejo IA Futures: generación gobernada cada 30 min cuando hay oportunidad; espera/idle conserva frecuencia más baja.
- Asistente IA Futures: 1 pregunta cada 20 min, máximo 3/h.
- Supabase: dedupe temporal **sólo de materiales derivados** (`review_recommendations` y estadísticas de estrategia idénticas). Una escritura se marca como deduplicable únicamente después de que Supabase confirmó persistencia.
- Se mide localmente el tamaño JSON enviado a Supabase para futuras auditorías.

## Lo que NO cambia

No modifica ni sustituye:

- `futures_system.py`
- `review_trader.py`
- `execution_challenger_lab.py`
- `governed_self_calibration.py`
- `execution_intelligence_v2.py`
- `portfolio_guardian.py`
- `pdf_learning_report.py`
- Entry / SL / TP / R:R / Execution Safety / leverage
- comité de traders / comité de Entry
- MFE / MAE / reachability / wick diagnostics
- Shadow → Canary → Active
- Alpha Decay / rollback
- evidencia primaria: `signals`, `signal_results`, contextos y resultados de aprendizaje.

## Sobre `pdf_report.py`

El archivo puede seguir físicamente en el repositorio para no obligar a un segundo commit de borrado. Queda **huérfano y no invocable**: `app.py` ya no importa `pdf_report`, no existe `/api/generate_report` y Telegram no envía documentos. Puede borrarse más adelante como limpieza de código sin efecto funcional ni de bandwidth.

## Archivos de producción a reemplazar

1. `app.py`
2. `ai_advisor.py`
3. `render.yaml`
4. `supabase_client.py`
5. `static/script.js`
6. `static/futures.js`
7. `static/ai_assistant.js`

No ejecutar SQL nuevo.
