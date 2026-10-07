# Implementación Commit 30.1

## Un único commit Git

1. Descarga y descomprime `SMARTRADINGREVIEW_COMMIT30_1_PROPUESTA3_ADJUSTMENT_DRAG_REPLACE.zip`.
2. En la rama `main`, arrastra **todos los archivos del ZIP directamente a la raíz** del repositorio.
3. Selecciona **Replace / Overwrite** para todos los duplicados. No crees una carpeta `Commit30.1` dentro del repo.
4. Comprueba antes de commitear:
   - `Procfile` contiene `commit30_1_main_entrypoint:app`.
   - `render.yaml` contiene `commit30_1_main_entrypoint:app`.
   - existen `commit30_1_core.py` y `commit30_1_main_entrypoint.py`.
5. Haz **un solo commit**, por ejemplo: `Commit 30.1 - Proposal 3 fast lane bridge repair`.
6. Si Render tiene un **Start Command manual**, cámbialo en Settings (no requiere otro commit Git) a:

   `gunicorn commit30_1_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 60 --max-requests-jitter 15`

7. Tras el deploy abre `/api/runtime/version`. Debe mostrar:
   - `COMMIT30_1_PROPOSAL3_FAST_LANE_BRIDGE_V1`
   - `commit30_1_main_entrypoint:app`
   - `f30_frozen_volume_min: 1.0`
   - `ui_cooldown_can_starve_impulse_lane: false`
8. En logs de arranque busca:
   - `Commit30.1 entrypoint is authoritative`
   - `Impulse queue persists until successful 30m ACK`
   - `F30 uses frozen broader stability contract ADX>=20 / Vol>=1.00 / RSI anti-chase`
9. Durante un impulso busca:
   - `[C30.1 IMPULSE]`
   - `[C30.1 BRIDGE]`
   - y, si una señal no publica, un `ROUTE_CONTEXT:<causa exacta>`.

## No modificar después del deploy

No bajes manualmente Safety, RR, ADX, ATR stress ni memoria. Primero observa varios cierres 30m/1h con Commit30.1 confirmado por `/api/runtime/version`.
