# Prompt Maestro de Continuidad — Commit 20

Proyecto: `Willer5000/smartradingreview`

Versión: `COMMIT20_PREMIUM_PATH_EXPANSION_V1`

## Objetivo

Aumentar la frecuencia de señales Premium sin convertir el sistema en una lluvia de señales y sin relajar ningún hard gate.

## Contrato inmutable

1. No bajar Safety Premium.
2. No bajar TP Quality.
3. No bajar SL Quality.
4. No bajar R/R mínimo 1.8.
5. No permitir R/R > 3.5 para publicación Premium.
6. No relajar pérdida estimada en SL.
7. No relajar estrés ATR.
8. No crear dirección desde PPE.
9. No modificar Alpha Decay.
10. No promocionar fallback a Premium.
11. No agregar workers, threads, polling ni APIs pagas.
12. Mantener Candle Close Authority.
13. No convertir Safety/CPQE en probabilidad.

## Qué hace PPE

PPE aumenta la superficie de acceso a Premium mediante:

- Context Router;
- hasta 2 rutas alternativas de geometría;
- competencia entre Entry/SL/TP ya calculados;
- Premium Funnel y blocker codes;
- route diagnostics;
- mercado especializado para Multi-Activo;
- evidencia/champion como diagnóstico, no como permiso inventado.

## Regla de autoridad

Una ruta alternativa solamente representa otra forma de ejecutar la **misma dirección ya existente**.

No es un nuevo voto.

No genera LONG/SHORT.

No sustituye CPQE.

No sustituye Publication Gate.

## Rutas de expansión

Priorizar sólo si los datos ya calculados lo justifican:

- LIQUIDITY_SWEEP_MSS_POI
- TREND_PULLBACK
- BREAKOUT_RETEST
- STRUCTURE_RETEST
- COMPRESSION_EXPANSION
- VWAP_SESSION_PULLBACK
- MEAN_REVERSION_SELECTIVE
- VOLATILITY_RETEST
- POST_EVENT_CONFIRMATION
- ASIA_SESSION_RETEST

## Multi-Activo

No heredar edge entre clases de activo.

QQQ/SPY, Energy, Metals y KSTR deben investigarse por su propia celda/asset class/sesión.

## Saved Signals

`market_type` determina el proveedor de velas:

- `futures` → Futures perpetual
- `multiasset` → MultiAsset provider
- `spot` → Spot provider

## Estadística

Nunca afirmar:

`Safety 80 = 80% de ganar`

La probabilidad sólo se incorpora después mediante outcomes calibrados por celda.

## Próxima evolución

El siguiente paso estadístico después de PPE es persistir Q1-Q9 por señal y conectar:

IS → Selection → OOS → Walk-Forward → Shadow → Live Champion → Alpha Decay.

No crear una cuota diaria de señales.
