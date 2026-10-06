# Deploy simple — Commit 25

1. Descarga y descomprime `SMARTRADINGREVIEW_COMMIT25_DRAG_REPLACE.zip`.
2. Abre el repositorio `smartradingreview` en VS Code Web.
3. Arrastra **todos los archivos del ZIP a la raíz del repositorio** y acepta Replace/Overwrite.
4. No cambies `.env`, `SUPABASE_URL`, `SUPABASE_KEY`, Telegram ni ninguna key.
5. Commit/push a `main`.
6. Render debe construir con `requirements.txt` y arrancar con `commit25_main_entrypoint:app`.
7. En logs de boot busca:
   - `COMMIT25_CONTEXTUAL_CHAMPION_RECOVERY_ANTI_OVERFIT_V1`
   - `Contextual Champions restored`
   - `Q1..Q10 parallel scores diagnostic-only`
8. No ejecutar SQL: Commit 25 no crea tablas ni cambia schema.

## Verificación funcional mínima

- Spot/Futures/Multi deben abrir igual que antes.
- Gráficos no dependen del Champion registry.
- En una celda no validada (ej. SUI 30m, CL 1D, XAG 1D, KSTR 1D) no debe aparecer autoridad Commit25 por similitud.
- En celdas Champion, una coincidencia sólo crea candidato; publicación todavía debe exigir Safety/RR/SL/TP y demás gates.
- Revisar RSS de Render; Commit25 no añade threads/loops/requests.

## Feature flag

`COMMIT25_CONTEXTUAL_AUTHORITY_ENABLED=1` está en `render.yaml`. Si se cambia a `0`, el registry deja de otorgar Champion routing sin necesidad de borrar archivos.
