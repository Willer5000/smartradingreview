# Implementación — Commit 32.1 Recovery

## Instalación en un único commit
1. Descomprime `SMARTRADINGREVIEW_COMMIT32_1_RECOVERY_DRAG_REPLACE.zip`.
2. Arrastra el contenido directamente a la raíz de `smartradingreview` y elige Replace/Overwrite.
3. Verifica que existan:
   - `commit32_1_main_entrypoint.py`
   - `commit32_1_runtime_patch.py`
   - `commit32_1_candidate_recovery.py`
   - `commit32_1_research_registry.py`
4. `Procfile` y `render.yaml` deben contener `commit32_1_main_entrypoint:app`.
5. Haz **un único commit**: `Commit 32.1 - ABI visual RAM and candidate recovery`.
6. Si Render tiene un Start Command manual, reemplázalo por:

`gunicorn commit32_1_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 60 --max-requests-jitter 15`

## Verificación después del deploy
`/api/runtime/version` debe mostrar:
- `COMMIT32_1_RECOVERY_V1`
- `commit32_1_main_entrypoint:app`
- `multi_execution_abi = SELF_HEALED_AND_BOOT_GUARDED`
- `visual_lane = OHLC_ONLY_HEAVY_LOCK_INDEPENDENT`

En logs deben aparecer líneas `[COMMIT32.1]`.

En `/api/commit32-1/status` (autenticado) revisa:
- `futures_abi` y `multi_abi` contienen `execution_observations`;
- `visual_lane=true`;
- RSS y límites de memoria;
- contadores de `candidate_second_chance_*`;
- registry CRT/Triple RSI con `production_authority=false`.

## Criterios de éxito
- desaparece el TypeError `execution_observations` de Multi;
- el gráfico obtiene `df` aunque exista un heavy job normal;
- deja de existir backoff permanente sólo porque RSS normal supera 190/210 MB;
- aparecen candidatos primarios recuperados sin publicar fallback;
- toda señal LIVE sigue mostrando Safety/OOS/ruta válida.

## Rollback
Usa el ZIP `SMARTRADINGREVIEW_COMMIT32_1_RECOVERY_TO_COMMIT32.zip` para volver al Commit32 FINAL.
