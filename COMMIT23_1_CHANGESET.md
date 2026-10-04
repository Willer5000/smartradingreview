# COMMIT 23.1 FIX — Integración Final de Autoridad Q1–Q10

## Objetivo

Reparar el tramo que convierte una tesis direccional de calidad en una señal ejecutable, sin bajar Safety, sin quitar los guardas de pérdida/ATR, sin agregar workers y sin agregar nuevas llamadas de red.

## Fallos que corrige

1. **Arranque inconsistente de Render/Blueprint**
   - `render.yaml` y `Procfile` usan ahora exactamente el mismo entrypoint: `commit23_1_main_entrypoint:app`.

2. **Boot chain incompleta del Core 23 anterior**
   - Conserva explícitamente:
     `19.1 PRE → app.py → CPQE 19.2.4 → 19.1 POST → PPE 20.2.1 → Q23 → 23.1`.

3. **Snapshots de vela cerrada antiguos**
   - Cuando un resultado almacenado no tiene la versión actual de autoridad Q23, se reprocesa la autoridad sobre el Entry/SL/TP y contexto ya guardados.
   - No se vuelve a pedir mercado por este mecanismo.

4. **Autoridad fragmentada**
   - `commit23_1_authority_runtime.py` crea un único contrato `FINAL_QUALITY_AUTHORITY` y lo reconcilia antes de clasificación y lifecycle.
   - Una Q válida >=75 puede confirmar únicamente si pasan los guardas universales.

5. **Dedupe de candidatas Futures**
   - Para el mismo `symbol × timeframe`, la prioridad pasa a ser: Q confirmada → `quality_filter_score` → confidence → R/R.

6. **Multi-Asset**
   - El overlay intenta integrar el mismo contrato de autoridad en los puntos existentes del runtime. Cuando una función opcional de una revisión anterior no existe, no rompe el servicio: queda registrada como no disponible en el diagnóstico de instalación.

## Riesgo y límites preservados

- Q mínimo: **75**.
- Safety operacional mínimo: **65**.
- Pérdida máxima estimada al SL: **8%**.
- ATR stress: **0 < stress <= 25%**.
- Q10 no es obligatorio para confirmar una Q distinta.
- Los umbrales históricos de Q10 no se eliminan.
- No se agregan workers.
- No se agregan llamadas de red.
- No se fabrican direcciones.

## Por qué no reemplazamos `app.py`

El `app.py` actual del repositorio es un archivo muy grande y el snapshot histórico usado para el Core 23 no coincide byte a byte con el `app.py` actual. En lugar de entregar una copia potencialmente antigua de todo `app.py`, 23.1 carga un **overlay de integración después de importar el `app` real** y parchea en memoria sus contratos de clasificación/lifecycle/refresh/dedupe.

Esto sí modifica el comportamiento real de `app.py`, pero evita sustituir accidentalmente otras correcciones existentes.

## Verificación post-deploy

Endpoint de diagnóstico:

`/api/commit23-1/health`

Debe devolver `version = COMMIT23_1_AUTHORITY_INTEGRATION_FIX_V1` y una boot chain que termine en `Q23 -> 23.1`.

## Resultado esperado

Una tesis que ya tenga:
- LONG/SHORT,
- Entry/SL/TP válidos,
- Safety >=65,
- SL loss <=8%,
- ATR stress válido,
- stage `PUBLICATION_GATE`,
- datos no sintéticos,
- Q1..Q10 actualizados y una Q >=75,

puede convertirse en `EXECUTABLE_SIGNAL` sin depender de que una capa intermedia deje correctamente copiado el `publication_status` antiguo.
