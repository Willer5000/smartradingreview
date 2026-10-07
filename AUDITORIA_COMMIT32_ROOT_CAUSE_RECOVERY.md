# Auditoría Commit 32 FINAL — causas raíz

## Hallazgos corregidos
1. **SPOT:** divergencia RSI histórica tenía aliases productor/consumidor incompatibles.
2. **SPOT:** patrones fuertes podían diluirse en conteos genéricos y el rechazo multi-pivote no tenía autoridad propia.
3. **SPOT:** el primer C32 propuesto parcheaba `vote_on_actions()`, pero la arquitectura moderna usa Operational Intelligence + `pipeline_integrity.reconcile_operational_candidate`. C32 FINAL se mueve al pipeline moderno.
4. **SPOT/Guardian:** señales globales y portafolio personal quedan separados. Guardian no se modifica.
5. **Publicación:** Commit31 todavía identificaba snapshots con versión Commit30.1; C32 FINAL invalida esa reutilización.
6. **Futures/Multi:** se acelera sólo el tempo de ejecución; no se relajan gates.
7. **RAM:** endpoints legacy pesados podían quedar fuera del coordinador global.
8. **RAM:** el único guard intra-job estaba antes de una duplicación completa OHLCV en `structure['df']` y antes de heatmap/especialistas/geometry.
9. **RAM:** C32 FINAL compacta esa copia y añade checkpoints por etapa.
10. **Deuda legacy:** no se elimina código histórico sin call-graph; se desactiva semánticamente como autoridad donde corresponde.

## Lo que NO hace Commit32
- no lee portafolios de usuarios para decidir la señal SPOT;
- no modifica `portfolio_guardian.py`;
- no baja Safety;
- no elimina hard-risk;
- no baja RR;
- no inventa Champions;
- no promueve Energy/Metals/China a LIVE sin OOS;
- no agrega traders, LLMs, Supabase queries ni threads;
- no convierte scores internos en probabilidades matemáticas;
- no borra indiscriminadamente commits históricos.

## Riesgo residual
La mitigación RAM es sustancial, pero la ausencia de OOM sólo puede confirmarse observando producción. `/api/commit32/status` expone RSS y funnel con autenticación. Si Render reinicia otra vez, los logs deben buscar `RESOURCE_PRESSURE_ABORT_COMMIT32` y el último checkpoint alcanzado.
