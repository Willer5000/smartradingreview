# QA Commit 32 FINAL

## Resultado local determinista
- `20 PASS / 0 FAIL`
- `py_compile`: PASS para todos los módulos Commit32 y QA.

## Contratos probados
1. aliases de divergencia RSI bajista normalizados;
2. BTC 4h con divergencia bajista + distribución + doble techo/rechazo + riesgo macro no termina en COMPRA;
3. escenario alcista de acumulación sí puede producir COMPRA;
4. señal SPOT no usa holdings y declara Guardian downstream intacto;
5. semántica PAXG-BTC para ambas rotaciones;
6. score interno no se presenta como probabilidad calibrada;
7. cambio de dirección SPOT sólo se promueve si Strategy Bank existente pasa >=70, regime/volatility y official cell;
8. si la estrategia no pasa, no se fuerza la nueva dirección;
9. Futures no es alterado por el wrapper SPOT;
10. `structure['df']` conserva longitud temporal pero elimina cinco listas OHLCV duplicadas;
11. HIGH < MEDIUM < CORE en vigencia y tolerancia;
12. Multi no mueve Entry/SL/TP;
13. política de snapshots es `COMMIT32_PUBLICATION_AUDIT_V2`;
14. runtime usa pipeline moderno, no instala parche legacy `vote_on_actions`;
15. `portfolio_guardian.py` no forma parte del paquete;
16. Render contiene límites RAM/heatmap C32;
17. checkpoint RAM libera caches antes de abortar;
18. checkpoint RAM aborta presión persistente;
19. Procfile usa Commit32;
20. render.yaml usa Commit32.

## Limitación honesta
Estas pruebas validan contratos e integración estática/pura. No demuestran rentabilidad futura ni pueden demostrar ausencia total de OOM en Render. La confirmación final requiere producción: boot, cierres reales y observación de RSS/logs.
