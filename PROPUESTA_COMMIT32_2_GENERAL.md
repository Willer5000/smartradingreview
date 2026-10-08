# Propuesta general — Commit 32.2

## Diagnóstico
1. El runtime observado no demuestra autoridad C32.1: no aparecen sus marcadores y reaparece el overlay C21.1 con límites antiguos.
2. Existen tesis de alta calidad que no llegan a geometría primaria. NATGAS 1D alcanzó tesis 98.5 y LONG 88%, pero `calculate_entry_levels` falló por ABI y la ejecución cayó a ESPERAR.
3. La UI aún expone `PREMIUM_SAFETY_BELOW_75`, aunque la política moderna ya no lo usa como veto. Son razones/snapshots legacy.
4. Los análisis fallback dominan la lista de diagnósticos. Fallback no debe publicarse; el objetivo es recuperar primary geometry, no autorizar fallback.
5. Multi sigue afectado por el mismo ABI y PAXG-BTC muestra staleness repetido; el contexto no disponible debe abstenerse y nunca fabricarse como neutral.

## Solución C32.2
- Runtime truth contractual en health/version.
- ABI hardening en Base, Futures, Multi y singleton vivo.
- Invalidación de policy snapshot y saneamiento de blockers legacy.
- Conserva visual lane/RAM/candidate recovery de 32.1.
- No cambia Guardian ni la independencia de señales SPOT.
- No rebaja Safety, hard-risk, RR ni autoriza fallback.

## Estrategias nuevas
CRT y Triple RSI son candidatos legítimos de investigación en 15m/30m/1h, pero no se les atribuye rentabilidad sin datos. C32.2 incorpora un harness IS/OOS cronológico y un contrato de promoción:
- expectancy IS > 0 y PF IS >= 1.05;
- expectancy OOS > 0 y PF OOS >= 1.05;
- mínimo 30 trades OOS;
- costes incluidos;
- reglas congeladas antes de OOS.
Si PASS -> LIVE directo. Si acumula 8 pérdidas LIVE consecutivas -> SHADOW. Un resultado ganador reinicia la racha.

La frecuencia no es una cuota; se amplía cobertura sólo mediante familias con edge demostrado.
