# Commit 31 — Regression / Evidence Note

Commit31 modifica autoridad de calidad/ejecución, no el alpha histórico de las rutas Champion.

La cohorte congelada F30 disponible conserva:

| Split | N | Net stress R | Expectancy R/trade |
|---|---:|---:|---:|
| DEV/IS | 11 | +1.702 | +0.1547 |
| HOLDOUT/OOS | 4 | +3.928 | +0.9820 |
| Total | 15 | +5.630 | +0.3753 |

Esto demuestra paridad de la evidencia de ruta, NO valida estadísticamente los pesos de los ocho Safety.

No existe todavía un dataset histórico con Entry-score, SL reliability, TP quality, estructura, momentum, MTF, flow, timing y outcome para toda la población. Por tanto sería incorrecto optimizar los pesos contra el resultado conocido.

Commit31 adopta la política anti-overfit siguiente:
- perfiles definidos por arquetipo, no por símbolo;
- LONG/SHORT simétricos;
- exactamente un perfil antes de calcular score;
- score no es hard gate;
- hard risk y route/OOS siguen separados;
- pesos no se optimizan con el incidente observado;
- futuros ajustes requieren cohorte prospectiva por perfil.
