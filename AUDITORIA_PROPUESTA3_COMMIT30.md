# Auditoría Propuesta 3 — Commit 30

## Veredicto
Commit 29 sí reparó infraestructura importante: `ABSTAIN` ya aparece correctamente, el contexto ausente deja de actuar como neutral y no se repite el crash ABI de Entry. El incidente BTC-USDT 1h reveló el cuello de botella decisivo que permanecía: **ADX bajo seguía borrando una impulsión direccional temprana antes de que pudiera convertirse en una tesis ejecutable**.

## Evidencia del incidente
El episodio de producción mostró simultáneamente:
- +DI=9.5, -DI=42.2, ADX=17.7;
- dirección y Parabolic SAR bearish;
- RSI 23.9;
- participación relativa 2.82x;
- 33 OB, 33 FVG y 5 liquidity sweeps;
- liquidations proxy más cargado del lado SHORT;
- Smart Money SHORT 100% con OB bajista + LVN + Value Area + confluencia;
- 1h y 2h bearish, pero el especialista Multiframe se abstuvo porque ADX era 17.7;
- RC9.2 terminó PRECAUCION/NEUTRAL calidad 56.

La caída no fue invisible para los sensores. Fue descartada por el **mecanismo de agregación**.

## Causa raíz
`build_independent_thesis()` atenuaba la familia Trend cuando ADX<18. Al mismo tiempo Multiframe exigía ADX>=18. En una caída rápida ADX puede rezagar varias barras respecto a DI, volumen, estructura y precio. Esto generaba una doble penalización sobre la misma variable y dejaba sólo tres familias activas, por debajo del mínimo Futures.

## Propuesta 3
Commit 30 introduce `DIRECTIONAL_IMPULSE_BEAR/BULL` como **evento contextual**, no como alpha independiente. El evento exige DI dominante, dominancia relativa, momentum y volumen/estructura. ADX sigue siendo útil para una tendencia sostenida, pero deja de ser veto durante la primera fase del desplazamiento.

### Cambios de núcleo
1. `commit30_core.py`: detector puro de impulso + régimen explícito.
2. `operational_intelligence.py`: el impulso refuerza la familia Trend existente; no suma una familia adicional.
3. `app.py`: Técnico y Multiframe reconocen impulso; runtime endpoint Commit30; bridge 1h→30m; auditoría compacta del evento.
4. `pipeline_integrity_175102.py`: `DIRECTIONAL_IMPULSE_CONTINUATION` permite geometría/telemetría Shadow 1h sin otorgar autoridad LIVE.
5. Scheduler: una señal contextual 1h reprioriza sólo celdas 30m ya validadas. El evento se conserva hasta 90 minutos y no se pierde si el 30m todavía no está due.
6. `commit30_main_entrypoint.py`: boot guards deterministas del ABI, deploy y replay del incidente.
7. `Procfile` y `render.yaml`: autoridad única Commit30.

## Lo que NO hace Commit 30
- no baja Safety 75;
- no baja RR 1.8;
- no sube RR máximo 3.5;
- no relaja ATR stress 25%;
- no permite fallback Premium;
- no crea un Champion BTC 1h;
- no fuerza cuatro señales por día;
- no añade Q11, traders ni comités;
- no añade I/O, threads, Supabase o Groq.

## Futures
El cambio está diseñado para que un shock 1h no muera antes de activar los carriles rápidos 30m. La dirección final del trade la vuelve a calcular cada 30m; el 1h no la impone.

## Multi-Activo
El mismo clasificador reconoce impulsos direccionales y mejora Shadow/Research, pero Energy, US Index fast, China y Metals siguen sin autoridad LIVE rápida porque no existe OOS limpio. Los actuales `*_FAST_ROUTE_REQUIRES_OOS` son blockers estadísticos reales, no bugs.

## Spot
No se modifica la autoridad Spot ni su objetivo de snowball USDT/BTC. Sólo comparte el clasificador puro si lo consume; no cambia reglas de compra/venta/rotación.

## Recursos
Se heredan las defensas Commit29: 1 worker/2 gthreads, memory soft 205 MB, hard 285 MB, prestart 190 MB, in-job abort 315 MB, caches reducidos. Commit30 añade sólo una cola Python acotada de hasta 12 entradas.
