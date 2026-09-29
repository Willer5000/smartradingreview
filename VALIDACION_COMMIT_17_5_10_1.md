# Validación — Commit 17.5.10.1

## Suites ejecutadas sobre la base exacta 17.5.10 + patch 17.5.10.1

- `qa_commit17_5_10_1.py`: **53/53 PASS**.
- `qa_commit17_5_10_1_inherited.py`: **53/53 PASS** (regresión 17.5.10 adaptada sólo a los cambios intencionales del scheduler/UI).
- `python -m py_compile`: PASS para app, pipeline-integrity, MM/options y módulos de ejecución heredados.
- `node --check static/market_maker_frontend.js`: PASS.
- parse Jinja `templates/index.html`: PASS.
- conteo de `threading.Thread(`: **igual a baseline** (28 -> 28); 17.5.10.1 no añade threads.
- backtest congelado de 17.5.10 re-ejecutado: IS y OOS cronológico continúan positivos.

Las 106 comprobaciones contienen solapamiento y no deben interpretarse como 106 pruebas estadísticamente independientes.

## Pruebas específicas de pipeline

PASS para:
- Strategy Bank Multi participa antes de candidate-ready.
- quality mínima de strategy permanece 78.
- una tesis neutral no obtiene LONG/SHORT por la estrategia.
- OOS antiguo pasa a counter-evidence.
- candidato Crypto válido ya no es borrado sólo por prior antiguo.
- alpha-decay conserva ruta de autoridad forward.
- siete activos Multi pueden entrar a cola; top-2 es prioridad visual, no gate.
- desaparece `router_score>=82` como derecho a deep analysis.
- desaparece el hard cap 12/día como descarte; queda backpressure.
- tres fallos no marcan DONE.
- HIGH sin microestructura no se trata como mala liquidez.
- microestructura disponible y mala continúa bloqueando.
- Profitability Router usa cache >=1800 s.
- opciones automáticas sólo se solicitan para contexto direccional BTC/ETH.
- endpoint Greeks no ejecuta full analysis.
- UI Greeks no contiene `setInterval`.
- Delta call/put, Gamma, Vega y Theta matemáticamente disponibles.
- GEX permanece no-direccional.
- `futures_system.py` y `leverage_policy.py` no forman parte de los archivos a reemplazar.

## Verificación post-deploy necesaria

1. Abrir `/api/diagnostics/pipeline-integrity` autenticado.
2. Comprobar `supabase_target_project_ref` y `runtime_persistence_verification`.
3. Confirmar que el funnel de Futures recorre celdas y muestra razones exactas.
4. Confirmar que Multi tiene `pending/deferred/failed/processed` y que no todos los no analizados aparecen como “sin oportunidad”.
5. Abrir Futures BTC/ETH y verificar la tarjeta `Opciones · Greeks / Gamma / 0DTE`.
6. Confirmar que cambiar símbolo/TF no dispara polling continuo.
7. Vigilar RAM/RSS y bytes observados antes de aumentar cualquier frecuencia.
8. No tocar Safety por pocas horas sin señales: primero leer el funnel.
