# BACKTEST COMMIT 26 — PROPUESTA PROFUNDA 2

## Resultado release

**PASS = True**

El cambio no optimiza parámetros. Repara una incompatibilidad temporal entre el router Champion 30m y el esquema real pre-Entry.

## 30m — replay físico IS/OOS

| Split | N | Net R | Expectancy | PF | MaxDD R |
|---|---:|---:|---:|---:|---:|
| IS | 11 | 1.702 | 0.1547R | 1.254 | 2.236 |
| OOS | 4 | 3.928 | 0.9820R | 4.513 | 1.118 |

El OOS es positivo pero pequeño (N=4). No es una garantía de rentabilidad futura.

## Evidencia conjunta de rutas gobernadas

| Conjunto | N | Net R proxy | Expectancy ponderada | PF agregado proxy |
|---|---:|---:|---:|---:|
| IS gobernado | 388 | 18.129 | 0.0467R | 1.093 |
| OOS gobernado | 133 | 57.186 | 0.4300R | 2.239 |

Esto agrega evidencia de rutas; no es una curva de portfolio sincronizada.

## Hallazgo causal

- Commit 25 con esquema real pre-Entry: trigger estructural = **False**.
- Commit 26 con el mismo esquema: trigger estructural = **True**.
- Sin evento estructural estricto: Commit 26 = **False**.

Commit 26 consume `structure_direction`, `structure_reasons` y el inventario real de zonas; no fabrica MSS/displacement antes de Entry.

## Decisiones anti-overfit

- 1h: **Shadow**, no nueva autoridad LIVE.
- Multi ENERGY/METALS/CHINA: **Shadow**, no copia de reglas crypto.
- Spot: sin cambio de lógica.
- Q1..Q10: diagnóstico/evidencia; no `max(Q)` como atajo de publicación.
- RR/Safety/SL/TP/ATR/closed candle: sin rebaja.

## Recursos incrementales

0 threads, 0 requests de mercado, 0 lecturas/escrituras Supabase, 0 llamadas LLM.
