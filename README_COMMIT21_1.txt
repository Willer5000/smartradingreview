COMMIT 21.1 — FIX
==================

Objetivo: recuperar oportunidades Premium genuinas sin relajar Premium y hacer
que la UI sea visualmente inmediata.

Cambios principales:
- memoria real: 225/235/300 MB bajo LOW_MEMORY_MODE;
- Strategy Bank exact-cell routing corregido;
- recuperación de una tesis PRECAUCION sólo si el pipeline real ya devuelve PREMIUM;
- una ruta alternativa como máximo para fallback; dos como máximo para near-Premium;
- endpoint `/api/futures/visuals` y render de indicadores antes del análisis pesado;
- se conserva el arreglo Multi-Activo de Commit 20.2.

El paquete NO garantiza una frecuencia fija de señales. La condición de Premium
sigue siendo la misma.
