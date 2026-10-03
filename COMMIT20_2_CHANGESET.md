# Commit 20.2 — Production Fix

### Causas raíz resueltas
1. El despliegue visible estaba en `gunicorn app:app` / 19.2.3; por eso Commit 20/20.1 no era una autoridad activa garantizada.
2. El wrapper 20.1 de Multi-Activo podía caer al endpoint Futures y producir `Sin datos de velas Futures perpetuos`.
3. `futures.js` todavía trataba Saved Signals como exclusivas de Futures.
4. 20.1 elevaba el start limit, pero el soft guard seguía por debajo; el trabajo podía rechazarse inmediatamente.

### Contrato preservado
- Safety/RR/SL/TP/ATR/Alpha Decay sin relajaciones.
- PPE no crea dirección ni votos y fallback nunca obtiene Premium.
- 1 worker / 2 threads.
- Hard memory guard 300 MB.
