# Commit 31 — QA Report

## Suite específica Commit31

- `test_commit31_multi_safety.py`: **13/13 PASS**.
- Verifica 8 perfiles, selección previa al score, no threshold universal, impulso con ADX rezagado, sweep/MSS/POI, pullback, breakout, Multi-Asset como modificador, event/session explícito, evidencia opcional reponderada, hard SL no compensatorio, legacy Safety<75 no bloqueante, route/hard-risk/fallback obligatorios y deploy target Commit31.

## Regresión Proposal3 / Quality actual

- Commit31 + Commit30.1 + Commit30 + Commit23 diagnostic + Commit22 context, excluyendo únicamente asserts de deploy de versiones anteriores: **34 passed / 3 deselected**.

## Suite histórica adicional

Se ejecutó una suite adicional de geometry/lifecycle:
- **61 passed / 6 failed**.
- 2 fallos son `test_commit24_3_repair.py`, que exige que Q directo/cluster vuelva a promover una señal. Eso contradice deliberadamente Commit25+ y Commit31: Q es diagnóstico, no autoridad.
- 4 fallos pertenecen a `test_rc9_8_1_technical_signal_lifecycle.py` de Spot/Telegram y ya reflejan contratos históricos distintos del código actual. Commit31 no modifica ese flujo Spot.

También existen tests aún más antiguos que fijan literalmente entrypoints Commit20/28/29/30.1; no son criterio válido para un release Commit31.

## Compilación / sintaxis

- Python: **275 módulos**, **0 errores** de compilación en simulación full repo + 30.1 + 31.
- JavaScript: PASS con `node --check` en:
  - `static/futures.js`
  - `static/script.js`
  - `static/chart_workspace.js`
  - `static/market_maker_frontend.js`

## Boot

El import Flask/Gunicorn completo no pudo ejecutarse en el sandbox porque el entorno no trae `flask` instalado (`ModuleNotFoundError: flask`). El paquete sí compila y los tests puros/integración de autoridad pasan. Render instalará las dependencias declaradas por el repositorio durante build.

## Contratos verificados

1. Exactamente un Safety por señal.
2. Nunca se prueban 8 Safety para elegir el score mayor.
3. `Safety legacy >=75` deja de ser publication gate.
4. Q1..Q10 dejan de ser publication gate.
5. Hard risk permanece no compensatorio.
6. Route LIVE sigue siendo obligatorio.
7. Fallback nunca publica.
8. Missing optional evidence no se convierte en 0/50; se repondera.
9. Safety score sirve para ranking/leverage, no como magic threshold.
10. Proposal3 impulse/bridge y protecciones de memoria/ABI de 29–30.1 se preservan.
