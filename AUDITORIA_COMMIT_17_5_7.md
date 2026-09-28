# Auditoría — Commit 17.5.7

## Dictamen

17.5.7 es un parche de **evidencia + publicación**, no una recalibración del motor de trading.

La evidencia disponible no justifica modificar globalmente Entry, SL o TP. Sí justifica preservar 17.5.6, mejorar la trazabilidad por versión y evitar publicar como oportunidad premium un derivado cuyo leverage técnico final queda en x1–x3.

## Evidencia revisada

### Historial SmartradingReview

Se consultaron `signals`, `signal_results`, `research_champions_v1` y `execution_forensics` en el proyecto Supabase conectado.

El historial de señales termina el 18/09/2026; por lo tanto, antecede a 17.5.6. Se filtraron geometrías inválidas y RR extremos antes de calcular la cohorte principal.

Hallazgos centrales:

- Futures histórico agregado: negativo.
- Spot: positivo con N pequeño.
- SL que rebota después del stop: fenómeno real, pero minoritario.
- expiraciones: la mayoría nunca se acercó al TP.
- challenger histórico liquidity/sweep/MSS/POI: mejor comportamiento que baseline en 30m/1h/2h.
- x1–x3: cohorte histórica débil; x11+ no comparable y sin economía neta modelada.

### Multi-Activo

No existe una cohorte productiva histórica suficiente. Se ejecutó un proxy point-in-time con datos OHLC públicos. El proxy genérico fue negativo, por lo que no se usa para ajustar thresholds; sólo respalda mantener la diferenciación por activo/contexto que ya posee el sistema.

## Cambios auditados

### app.py

Añade `_apply_17_5_7_backtest_evidence_policy()`.

Propiedades verificadas:

- sólo puede **preservar o degradar** publicación;
- no cambia dirección;
- no cambia Entry;
- no cambia SL;
- no cambia TP;
- no cambia RR;
- no cambia Safety;
- no cambia leverage;
- Spot sale intacto;
- x1/x2/x3 derivados quedan ANALYSIS_ONLY;
- x4+ no son afectados por la regla;
- Telegram vuelve a comprobar la política antes de enviar;
- Multi-Activo aplica la política antes de guardar el análisis en caché.

También incorpora stamps de evidencia para poder crear cohortes versionadas futuras.

### execution_specialist_committees.py

Sin cambio funcional respecto de 17.5.6. SHA256 idéntico. Conserva el hard guard SL/reacción.

## QA

- `python -m py_compile app.py execution_specialist_committees.py`: OK.
- `qa_commit17_5_6_execution_quality_visibility.py`: 20/20 OK.
- `qa_commit17_5_7_backtest_evidence.py`: 14/14 OK.

El QA prueba explícitamente que x2/x3 no se transforman en x4 y que Entry/SL/TP permanecen iguales al degradar a ANALYSIS_ONLY.

## Riesgos restantes

1. No existe replay completo point-in-time de 17.5.6 porque el histórico no conserva todos los snapshots de Structure/MTF/Strategy Bank.
2. Spot todavía no tiene N suficiente ni contabilidad completa BTC/PAXG/USDT para afirmar objetivo de acumulación.
3. Multi-Activo necesita acumular resultados reales versionados.
4. `modeled_net_r` histórico no equivale a PnL de cuenta realizado.
5. El nuevo floor de **publicación** x4 es un requisito de producto/economía, no una afirmación causal de que x4 sea más rentable que x3.

## Seguridad Supabase — fuera del alcance del commit

La inspección del proyecto conectado reportó un advisory crítico: múltiples tablas del esquema `public` tienen **RLS deshabilitado**. 17.5.7 no modifica seguridad ni políticas de base de datos porque el objetivo actual es trading/ejecución y una corrección de RLS requiere revisar el acceso real de frontend/backend antes de aplicar políticas. Debe tratarse en un commit de seguridad separado para no bloquear accidentalmente la aplicación.

## Criterio de aceptación

Aceptar 17.5.7 si:

- ambos QA pasan;
- el sistema vuelve a producir análisis Futures/Multi-Activo sin errores;
- ninguna confirmación oficial x1–x3 aparece como EXECUTABLE_SIGNAL;
- las configuraciones x1–x3 siguen visibles como análisis y conservan su leverage técnico original;
- no aparecen regresiones en Entry/SL/TP;
- el Funnel permite distinguir ausencia real de candidatos de bloqueo de publicación.
