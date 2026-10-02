# Commit 19.2.2 — Runtime Scheduler & Multi Read Recovery

Este release corrige el starvation real de análisis background observado en producción y separa las lecturas visuales Multi de los scans de proveedor.

Cambios principales:
1. El conteo absoluto de threads deja de bloquear jobs; heavy lock + RSS siguen limitando concurrencia/memoria.
2. `/api/multiasset/opportunities` pasa a cache-only.
3. Active Multi fail-soft: conserva último estado válido ante lectura temporalmente degradada.
4. Diagnóstico `DIRECTION_CONFIRMATION` se descompone en el gate real cuando existió downgrade de ejecución.
5. Cache-bust frontend 19.2.2.

No cambia parámetros Premium ni geometría Champion.
