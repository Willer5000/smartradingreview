# Implementación Commit 31 — un solo commit

1. Descomprime `SMARTRADINGREVIEW_COMMIT31_MULTI_SAFETY_DRAG_REPLACE.zip`.
2. Copia todos los archivos directamente a la raíz del repositorio y acepta Replace/Overwrite.
3. Comprueba que `Procfile` y `render.yaml` apunten a `commit31_main_entrypoint:app`.
4. Haz UN único commit a `main`, por ejemplo: `Commit 31 - Multi Safety authority`.
5. Si Render tiene Start Command manual, configúralo (esto no requiere otro commit Git):
   `gunicorn commit31_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 60 --max-requests-jitter 15`
6. Tras deploy, abre `/api/runtime/version`.
7. Debe mostrar:
   - `COMMIT31_MULTI_SAFETY_AUTHORITY_V1`
   - `commit31_main_entrypoint:app`
   - `profile_count: 8`
   - `legacy_safety_75_publication_gate: false`
   - `q1_q10_publication_authority: false`
   - `single_specialised_safety_per_signal: true`
8. No modifiques thresholds manualmente después del deploy. Observa los nuevos blockers por varios cierres.

## Qué buscar en logs

- `Safety perfil=<PROFILE> ... ready=True/False`
- ausencia de rechazo universal por `Safety legacy < 75`;
- un candidato sin ruta LIVE seguirá mostrando `NO_VALIDATED_LIVE_ROUTE`;
- fallback seguirá bloqueado;
- hard risk seguirá bloqueando pérdida/ATR/geometry inválida.
