COMMIT 23 CORE — NUCLEO REAL DE CALIDAD

REEMPLAZAR:
1. app.py
2. futures_system.py
3. multiasset_system.py
4. premium_path_expansion_20.py
5. premium_path_expansion_21.py
6. quality_9q_engine_21.py
7. commit23_core_main_entrypoint.py
8. Procfile
9. quality_filters_frontend.js

IMPORTANTE:
- El cambio crítico es el entrypoint: antes el despliegue arrancaba commit21_1_main_entrypoint y sólo instalaba premium_path_expansion_20.
- Este entrypoint instala primero la base 20.2.1 y después el núcleo 21/22/23.
- app.py se conserva como núcleo estable; no se reemplaza por una versión experimental.
- Q1..Q10 se evalúan en paralelo; una sola calidad >=75 puede confirmar si los guardas universales pasan.
- Q10 queda como diagnóstico; sus umbrales históricos no se borran.
- No se añaden llamadas de red ni workers.
- Si el worker se atasca, Gunicorn lo recicla por max-requests/timeout en vez de dejar un proceso colgado indefinidamente.

NO BORRAR premium_path_expansion_20.py: es la base estable sobre la que se monta 23.
