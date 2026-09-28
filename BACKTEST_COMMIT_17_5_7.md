# Backtest y evidencia económica — SmartradingReview Commit 17.5.7

Fecha de corte: **2026-09-28**  
Base funcional evaluada para la propuesta: **Commit 17.5.6 preparado localmente, aún no desplegado**.

## 1. Qué se pudo y qué NO se pudo backtestear

Se utilizaron tres fuentes distintas y se mantienen separadas para no mezclar evidencia:

1. **Historial real registrado por SmartradingReview en Supabase** (señales/resultados entre 2026-08-21 y 2026-09-18). Sirve para medir fallos históricos, SL/TP, expiraciones, leverage y contrafactuales guardados por ReviewTrader.
2. **Research OOS/Shadow existente** (`research_champions_v1`). Sirve como evidencia por celda mercado×símbolo×TF, pero las muestras son todavía pequeñas.
3. **Proxy Multi-Activo point-in-time**, porque Multi-Activo se incorporó después del período con historial de `signals` y no existe una cohorte productiva histórica suficiente. Se utilizó OHLC diario público 2022-01-01→2026-04-15 para SPY, QQQ, USO y GLD con pivotes confirmados, sweep/BOS, Entry en apertura siguiente, SL estructural y TP estructural.

**No existe un replay exacto de 17.5.6 sobre el pasado**, porque la base histórica no conserva todos los snapshots point-in-time de Structure/MTF/Strategy Bank necesarios para reconstruir cada decisión con el código actual. Por tanto, este documento **no afirma que 17.5.6 habría producido los mismos trades históricos**. El backtest se usa para identificar fallos robustos y decidir qué sí/no conviene modificar en 17.5.7.

Las métricas `gross_expectancy_r_proxy` asignan `+RR` a TP y `-1R` a SL, excluyendo expiradas y ambiguas. `modeled_net_r` es un dato modelado histórico, no PnL realizado de cuenta. Los resultados Spot tampoco incluyen todavía una contabilidad completa de rotación BTC↔PAXG, satoshis, oro, USDT y costes.

---

## 2. Resultado resumido de los tres mercados

| Mercado | Evidencia | Resueltas | WR | Expectancy R | PF | Lectura |
|---|---:|---:|---:|---:|---:|---|
| **Futuros** | Historial limpio, TF activos, RR 1–6 | 346 | 22.25% | **-0.132R** | 0.830 | Historial agregado antiguo no rentable; 1h/2h concentran el problema. |
| **Spot** | Historial limpio, TF 4h/12h/1D/1W | 16 | 56.25% | **+1.366R** | 4.121 | Señal positiva, pero **N demasiado pequeño** para declarar rentabilidad robusta. |
| **Multi-Activo** | Proxy técnico 2022–2026 | 59 | 16.95% | **-0.371R** | 0.553 | Un modelo genérico de Structure+geometría no funciona de forma transversal; confirma que debe conservarse la diferenciación por activo/contexto. |

### Conclusión económica

- **No se puede afirmar todavía que el sistema completo sea rentable en los tres mercados.**
- Spot tiene evidencia inicial favorable, pero insuficiente.
- El historial antiguo de Futuros es negativo agregado, aunque Research OOS contiene varias celdas con expectativa/PF positivos y muestras pequeñas.
- Multi-Activo no dispone todavía de backtest productivo. El proxy genérico fue negativo y, por ello, **no autoriza copiar lógica crypto de manera uniforme**.

---

## 3. Futuros — qué muestran los datos

### 3.1 Historial limpio por timeframe

| TF | N resuelto | TP | SL | WR | Exp. R proxy | Modeled net-R medio | Expiradas |
|---|---:|---:|---:|---:|---:|---:|---:|
| 30m | 125 | 44 | 81 | 35.20% | **+0.320** | +0.760 | 232 |
| 1h | 120 | 11 | 109 | 9.17% | **-0.642** | -0.907 | 113 |
| 2h | 78 | 16 | 62 | 20.51% | **-0.184** | -1.061 | 79 |
| 4h | 23 | 6 | 17 | 26.09% | **+0.244** | -0.044 | 23 |

Estos resultados corresponden a versiones históricas anteriores al 17.5.6. No deben utilizarse para bloquear 1h/2h de forma permanente, porque el motor actual cambió. Sí muestran que **el problema no era “falta de cantidad”, sino calidad de selección/ejecución**.

### 3.2 Contrafactual de Entry/ejecución guardado históricamente

El historial de `execution_challenger_results` permite comparar cómo habría evolucionado el mismo episodio bajo variantes de ejecución antiguas. No es 17.5.6, pero es útil para detectar qué familia merece seguimiento.

| TF | Variante | TP | SL | WR resuelto | Exp. R | PF |
|---|---|---:|---:|---:|---:|---:|
| 30m | BASELINE | 14 | 21 | 40.00% | +0.220 | 1.366 |
| 30m | **LIQUIDITY_SWEEP_MSS_POI** | 12 | 4 | **75.00%** | **+1.153** | **5.613** |
| 30m | SPECIALIST_COMMITTEE antiguo | 5 | 4 | 55.56% | +0.756 | 2.701 |
| 1h | BASELINE | 3 | 28 | 9.68% | -0.740 | 0.180 |
| 1h | **LIQUIDITY_SWEEP_MSS_POI** | 9 | 18 | **33.33%** | **+0.089** | **1.134** |
| 1h | SPECIALIST_COMMITTEE antiguo | 1 | 10 | 9.09% | -0.645 | 0.290 |
| 2h | BASELINE | 2 | 19 | 9.52% | -0.596 | 0.342 |
| 2h | **LIQUIDITY_SWEEP_MSS_POI** | 8 | 9 | **47.06%** | **+0.318** | **1.600** |
| 2h | SPECIALIST_COMMITTEE antiguo | 2 | 9 | 18.18% | +0.001 | 1.001 |

La lectura correcta es **“priorizar y medir estructura/liquidez real”**, no “hacer obligatorio un único setup”. Las cohortes son de versiones anteriores y contienen muchas expiraciones. Por eso 17.5.7 **no cambia pesos ni umbrales de Entry/SL/TP para copiar estos números**. En cambio, registra una clase de evidencia `LIQUIDITY_SWEEP_STRUCTURE_POI` para construir una cohorte limpia con el motor nuevo.

### 3.3 El problema del SL no justifica ensanchar todos los stops

Sobre **521 SL de Futuros con forensics**:

- 37 recuperaron el Entry después del SL: **7.10%**.
- Sólo 3 llegaron posteriormente al TP: **0.58%**.
- 13 fueron marcados como posiblemente estrechos.
- `best_favorable_r_after_stop` medio: **0.151R**.

Esto confirma que el fenómeno “tocó SL y rebotó” existe, pero es minoritario. Por ello:

- se **mantiene** el hard guard de 17.5.6 que prohíbe colocar SL dentro de una zona fuerte de reacción todavía válida;
- **no** se aumenta el buffer global del SL;
- **no** se aleja el stop por ATR únicamente;
- si la invalidación correcta queda demasiado lejos para una operación rentable, el setup debe quedar ANALYSIS_ONLY.

### 3.4 El TP tampoco parece ser el problema principal

Entre **1,146 expiradas de Futuros**:

- MFE medio: 0.410R;
- progreso medio hacia el target: 16.8%;
- llegaron a 1R: 169 (14.7%);
- llegaron al 70% del TP: 63 (5.5%);
- llegaron al 90% del TP: 19 (1.7%).

Si la mayoría ni siquiera se acerca al objetivo, reducir todos los TP sólo maquillaría la estadística. 17.5.7 mantiene TP estructural y no introduce un TP artificial por RR/ATR.

### 3.5 Apalancamiento

Cohorte histórica de señales resueltas:

| Leverage | N | WR | Exp. R válida | Net-R modelado |
|---|---:|---:|---:|---:|
| x1–x3 | 118 | 29.66% | **-0.623** | -0.812 |
| x4–x5 | 227 | 22.47% | -0.344 | -0.118 |
| x6–x10 | 367 | 28.61% | -0.146 | -0.295 |
| x11–x20 | 20 | 100% | +3.183 | N/D |
| x21+ | 28 | 100% | +3.623 | N/D |

**No debe concluirse que más leverage causa más rentabilidad.** Las 48 observaciones x11+ pertenecen sólo al período 21–27/08 y no tienen economía neta modelada; no son comparables con las otras cohortes.

Sí hay dos hechos suficientes para una decisión de producto prudente:

1. x1–x3 fue una cohorte históricamente débil;
2. el objetivo operativo del sistema es no publicar como señal premium una operación de Futuros que sólo resulta atractiva con x2/x3.

Por eso 17.5.7 añade **un gate de publicación, no un floor artificial de leverage**: si V6 determina x1–x3, se conservan Entry/SL/TP/leverage, pero queda `ANALYSIS_ONLY`. Nunca se fuerza x4 ni se mueve el SL para obtener más leverage.

---

## 4. Spot — acumulación y rotación

Historial limpio en los TF actualmente relevantes:

- 16 resueltas, 9 TP, 7 SL.
- WR 56.25%.
- expectativa bruta proxy +1.366R.
- PF proxy 4.121.

La celda con más evidencia fue **PAXG-BTC 4h**: 7 resueltas, 5 TP / 2 SL, WR 71.43%, +2.167R proxy. Es una señal interesante para la lógica de rotación BTC↔oro, pero sigue siendo una muestra pequeña.

Research OOS existente también contiene:

- PAXG-BTC 12h: N=5, exp. +1.144R, PF 6.19.
- PAXG-USDT 12h: N=24, exp. +0.196R, PF 1.50.
- BTC-USDT 12h: N=5, exp. +0.305R, PF 1.66.

**Decisión 17.5.7:** no tocar Spot con el ajuste de leverage ni recalibrar Strategy Bank por estos N pequeños. La próxima medición Spot debe reportar por separado:

- Δ satoshis;
- Δ PAXG/oro;
- Δ USDT;
- valor total en USDT después de costes;
- resultado de rotación frente a buy-and-hold de BTC/PAXG/USDT.

---

## 5. Multi-Activo — proxy histórico

No existen registros productivos suficientes de Multi-Activo en la tabla histórica `signals`: la cohorte disponible termina el 18/09 y Multi-Activo llegó después. Tampoco se encontró memoria histórica para SPY/QQQ/CL/NATGAS/COPPER/XAG/KSTR en la cohorte inspeccionada.

Para no inventar resultados se hizo un **proxy point-in-time** con OHLC diario público para SPY, QQQ, USO y GLD (2022-01-01→2026-04-15):

- pivote confirmado con 5 velas a cada lado;
- sweep con recuperación o BOS por cierre;
- Entry en la apertura siguiente;
- SL detrás de invalidación estructural + 0.20 ATR;
- TP en el objetivo estructural confirmado más cercano;
- RR 1.8–4.5;
- horizonte 12 velas;
- sin look-ahead de pivotes.

Resultado agregado: 74 setups, 59 resueltos, 10 TP / 49 SL, WR 16.95%, **-0.371R**, PF 0.553, DD 24.76R.

Esto **NO es el backtest del motor Multi-Activo real**: faltan volumen, macro, sesión, Strategy Bank, contexto por clase, adapters y microestructura; USO/GLD son proxies y no los contratos CL/XAG exactos. Precisamente por eso el resultado es útil: demuestra que una receta genérica de Structure+geometría **no debe convertirse en el motor Multi-Activo**.

**Decisión 17.5.7:** conservar la diferenciación ya existente por clase de activo, macro, sesión, volatilidad y Strategy Bank. No introducir un fallback “crypto genérico” para conseguir más señales.

---

## 6. Cambios que SÍ autoriza la evidencia en 17.5.7

1. **Preservar 17.5.6**: Structure estricta, MTF cerrado, Entry/SL/TP independientes, hard guard SL↔zona de reacción, Multi-Activo visible, Telegram sin cupo diario.
2. **Futuros/Multi-Activo x1–x3 → ANALYSIS_ONLY**. El leverage calculado por V6 permanece intacto; no se fuerza un mínimo técnico ni se altera Entry/SL/TP.
3. **Crear una cohorte versionada** con `backtest_evidence_policy_version` y `entry_evidence_class`. Esto permitirá comparar, con el motor actual, `LIQUIDITY_SWEEP_STRUCTURE_POI` vs `STRUCTURAL_CONFLUENCE` vs `BASIC_TECHNICAL_EVIDENCE` sin ajustar a ciegas.
4. **Mantener SL y TP sin recalibración global**. Los datos no justifican ensanchar SL ni acortar TP de forma universal.
5. **Mantener Spot intacto** hasta reunir N y contabilidad de rotación suficientes.
6. **Mantener Multi-Activo diferenciado**, sin copiar parámetros crypto por el resultado del proxy.

## 7. Cambios que la evidencia NO autoriza

- bajar Safety, familias o Publication para aumentar frecuencia;
- deshabilitar 1h/2h por el historial viejo;
- fabricar un WR de 55%;
- subir leverage porque una señal “parece buena”;
- mover SL para obtener un leverage mayor;
- imponer LIQUIDITY_SWEEP_MSS_POI como única estrategia;
- llamar “rentable” al sistema completo antes de una cohorte versionada OOS.

## 8. Criterio de validación posterior a 17.5.7

La siguiente cohorte debe medirse **por versión + mercado + símbolo + TF + clase de Entry**. Un mínimo razonable para tomar decisiones automáticas no se fija aquí por conveniencia; se aplicarán las reglas de gobernanza existentes. Reportar: N, fills/no-fills, WR, expectancy R neta, PF neto, DD, MAE/MFE, expiradas, costes/funding y `STOP_THEN_REACTION`.

El commit no promete rentabilidad. Su objetivo es que la siguiente evidencia sea comparable y que ninguna señal premium de derivados se publique con x1–x3 sólo porque el resto del setup obtuvo buen score.
