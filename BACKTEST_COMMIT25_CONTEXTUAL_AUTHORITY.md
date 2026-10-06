# BACKTEST COMMIT 25 — Contextual Champion Recovery / Anti-Overfit

## Resultado de release
- PASS: **True**
- 30m raw replay IS: N=11 · E=+0.1547R · PF=1.2537
- 30m raw replay OOS: N=4 · E=+0.9820R · PF=4.5134
- Cobertura gobernada symbol×TF: 3 -> 12 (4.0x)

## Rutas con autoridad exacta
| Ruta | Mercado / celda | IS | Selection | OOS | Release |
|---|---|---:|---:|---:|---|
| F30_SHARED_LIQ_SWEEP_MSS_POI_V1 | BTC-USDT,ETH-USDT,SOL-USDT,XRP-USDT,ADA-USDT,LINK-USDT 30M | N11 E +0.1547R PF 1.254 | — | N4 E +0.9820R PF 4.513 | PASS |
| ETH_2H_LONG_RSI_TREND_V1 | ETH-USDT 2H | N40 E +0.0866R PF 1.185 | N14 E +0.1646R PF 1.482 | N14 E +0.3331R PF 1.968 | PASS |
| SOL_2H_SHORT_SUPERTREND_PULLBACK_V1 | SOL-USDT 2H | N23 E +0.1015R PF 1.138 | N8 E +0.5033R PF 1.873 | N8 E +0.3130R PF 1.416 | PASS |
| XRP_2H_SHORT_TREND_CONTINUATION_V1 | XRP-USDT 2H | N52 E +0.1113R PF 1.212 | N17 E +0.3306R PF 1.826 | N18 E +0.2785R PF 1.519 | PASS |
| LINK_4H_SHORT_RSI_TREND_V1 | LINK-USDT 4H | N49 E +0.0071R PF 1.016 | N16 E +0.5422R PF 3.633 | N17 E +0.2754R PF 1.853 | PASS |
| US_INDEX_1D_TREND_PULLBACK_RR18_V1 | SPY-USDT,QQQ-USDT 1D | N213 E +0.0211R PF 1.043 | N71 E +0.0130R PF 1.030 | N72 E +0.5055R PF 2.912 | PASS |

## Interpretación
La evidencia positiva es una condición de release, no una garantía de rentabilidad futura. Commit 25 no hace búsqueda de parámetros ni copia una ruta ganadora a otra clase de activo. Los Q paralelos quedan diagnósticos y no pueden rescatar un paquete que incumple el gate económico nativo.

## Limitaciones
- 30m is the only route whose row-level cohort is physically present in the attached Main ZIP and is re-executed here.
- ETH/SOL/XRP/LINK use governed causal IS/Selection/OOS metrics audited from Research/Supabase; their raw candle datasets are not in the attached Main ZIP.
- US_INDEX 1D uses the independent public-history IS/Selection/OOS result recorded by the Commit-19 audit; the external raw price dataset is not bundled here.
- Positive historical IS/OOS evidence is a release criterion, not a guarantee of future profitability.
- Commit25 does not have the raw candle datasets for ETH/SOL/XRP/LINK/US_INDEX in the supplied ZIP, so those frozen governed IS/Selection/OOS metrics are audited/reused rather than recomputed from candles.
- The 30m OOS has N=4; it is positive but statistically small and must continue under Alpha Decay/ReviewTrader.
- Increasing governed route coverage does not guarantee a non-zero signal on every market day; a cell still needs live direction, MTF compatibility, geometry, Safety, RR and publication quality.
