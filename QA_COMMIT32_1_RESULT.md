# QA — Commit 32.1 Recovery

## Resultado
**30 PASS / 0 FAIL**

- 20 contratos/regresiones heredados de Commit32 (adaptado únicamente al nuevo entrypoint 32.1).
- 10 pruebas específicas de Commit32.1.
- `py_compile` PASS para todos los módulos C32/C32.1 incluidos.

## Pruebas nuevas cubiertas
1. CRT/Triple RSI y research registry son `SHADOW_ONLY` y `production_authority=false`.
2. Directional Impulse permite MTF contextual con evidencia extra.
3. Trend Pullback conserva MTF estricto.
4. Graded candidate recovery puede crear candidato pero siempre deja `never_bypass_safety=true`.
5. `requires_validated_live_route=true` permanece obligatorio.
6. HIGH/MEDIUM/CORE comparten piso pre-candidate 82 en el recovery; no se toca gestión downstream.
7. Multi conserva piso 84.
8. Procfile/render apuntan al entrypoint 32.1 y a límites de memoria nuevos.
9. Boot guard contiene verificaciones ABI de Futures, Multi class y Multi singleton.
10. Runtime patch contiene carril visual OHLC independiente y wrappers sobre geometría Futures/Multi real.

## Lo que estas pruebas NO demuestran
No demuestran rentabilidad de CRT, Triple RSI ni del recovery. Tampoco calibran probabilidad de éxito. La rentabilidad sólo puede establecerse mediante IS/OOS/walk-forward/forward Shadow.
