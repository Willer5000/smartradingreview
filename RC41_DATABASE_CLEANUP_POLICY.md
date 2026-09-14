# FINAL V1 RC4.1 · Política de higiene de Supabase

## Decisión

RC4.1 **no borra datos automáticamente**. El antiguo TTL podía eliminar pérdidas/expiraciones antiguas mientras preservaba TP, introduciendo *survivorship bias*. Desde RC4.1 `apply_ttl_cleanup()` es una auditoría read-only y reporta candidatos, con **0 filas borradas**.

## Qué calibra producción

Sólo `OFFICIAL_CURRENT`:
- Spot: BTC-USDT, PAXG-USDT y PAXG-BTC en 4h/12h/1D/1W, Q6 real/cerrado/verificado.
- Futures: siete símbolos en 30m/1h/2h/4h y BTC/ETH/SOL en 12h/1D, perpetuo KuCoin real, vela cerrada y `EXECUTABLE_SIGNAL` elegible.

## Qué se conserva sin calibrar

- `SHADOW_CURRENT / RESEARCH_ONLY`: sirve para investigación y continuidad, no altera KPIs oficiales.
- `LEGACY_ARCHIVE`: versiones pre-auditoría, 5m/15m retirados y geometrías antiguas.
- `INVALID/UNVERIFIED`: queda en cuarentena hasta aclarar procedencia.

## Qué NO borrar

TP, SL, expiraciones, señales con source candle verificable, resultados usados por OOS/ReviewTrader, evidencia de Guardian, Scientist/Trader IA, ni hallazgos Research.

## Candidatos a limpieza física futura

Sólo después de backup y auditoría manual: duplicados exactos demostrados, cachés/snapshots redundantes que tengan una fuente canónica equivalente, o telemetría técnica repetida sin valor estadístico. No hacer DELETE por timeframe o por “ser viejo”.

## Procedimiento

1. Ejecutar `RC41_DATABASE_HYGIENE_READONLY.sql`.
2. Guardar los conteos/resultados.
3. No tocar la BD si hay discrepancias entre Analytics, PDF y ReviewTrader.
4. Una eventual limpieza física debe ser una migración separada y revisada, nunca un job automático del runtime.
