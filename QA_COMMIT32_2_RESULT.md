# QA Commit 32.2

- Regression Commit32 + Commit32.1 + Commit32.2: 36 PASS / 0 FAIL.
- Python compile: PASS.
- Se prueba limpieza de blocker legacy Safety>=75.
- Evidencia PENDING no puede adquirir LIVE.
- Evidencia rentable IS/OOS con reglas congeladas puede adquirir LIVE.
- Ocho pérdidas consecutivas degradan a SHADOW; un win resetea la racha.
- OOS backtest bloquea señales durante el warm-up para evitar leakage IS->OOS.
- Procfile/render apuntan a C32.2.
