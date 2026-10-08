# Commit 32.2 — Quality Signal Recovery

C32.2 corrige la persistencia de cero señales de calidad sin rebajar Geometry, Safety, hard-risk u OOS.

## Cambios productivos
- Autoridad WSGI explícita: `commit32_2_main_entrypoint:app`.
- ABI endurecido en Base/Futures/Multi para `execution_observations`.
- Snapshot policy `COMMIT32_2_PUBLICATION_AUDIT_V1`; bloqueadores legacy Safety>=75 son invalidados.
- `/health` y `/api/runtime/version` muestran verdad de runtime y ABI.
- Hereda C32.1: visual OHLC-only lane, RAM authority y candidate recovery contextual.
- Guardian no se modifica.

## Nuevas técnicas
CRT y Triple RSI quedan registradas con evidencia `PENDING_BACKTEST_DATA`. No se afirma rentabilidad sin ejecutar un IS/OOS reproducible. El harness `commit32_2_backtest.py` usa split cronológico 70/30, costes, reglas congeladas y evita leakage de warm-up hacia OOS.

Una estrategia con evidencia PASS obtiene `production_authority=true` directamente. Ocho pérdidas LIVE consecutivas la degradan a SHADOW; un TP/WIN reinicia la racha.

## Verificación después del deploy
- `/api/runtime/version`: `COMMIT32_2_RECOVERY_V1`
- `entrypoint`: `commit32_2_main_entrypoint:app`
- `geometry_abi.ok`: true
- `/health`: `runtime_authority=COMMIT32_2_RECOVERY_V1`

Si Render tiene un Start Command manual, cámbialo también a C32.2; Git no puede sobrescribir un comando manual del dashboard.
