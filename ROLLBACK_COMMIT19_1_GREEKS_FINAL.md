# Rollback Commit 19.1 Greeks Final

Este release no agrega tablas ni modifica schema.

Rollback seguro:
- Git revert del commit del release, o
- reemplazo por el árbol anterior.

Al volver atrás desaparecen:
- frontend Greeks universal;
- endpoint genérico `/api/market-maker-context` (queda la versión previa según baseline);
- autoridad observada de confluencia Entry/SL/TP;
- budget guard específico del proveedor.

Los históricos, señales guardadas, Champions y Alpha Decay no requieren migración inversa.
