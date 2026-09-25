# QA / Tester · Commit 12.1 FINAL

## Hallazgos corregidos
1. `market=multiasset` podía caer en la rama Spot → corregido.
2. Multi heredaba `/api/futures/microstructure` → endpoint separado/proxy protegido.
3. `/multiasset` no tenía prioridad de interacción → corregido.
4. Reintentos heredados daban sensación de carga infinita → polling acotado.
5. Analytics no tenía navegación/filtro Multi → corregido.
6. Analytics podía contaminar Futures con símbolos Multi → separación por universo.
7. KPI Multi consultaba como Futures → cache-only Multi.
8. Guía/Información desactualizada → actualizada.
9. Etiquetas BTC/Futures heredadas → nombre de mercado dinámico.
10. Símbolos técnicos en UX → nombres humanos.
11. Listas Python crudas en justificaciones → español natural.
12. Paneles insinuaban order book/OI/funding no descargados → proxy/mode protegido explícito.
13. Consejo IA tenía bucket homogéneo/incorrecto → 4h/30m/1h.
14. Asistente Futures tenía 20m y Multi heredaba ese cooldown → 30m/60m, Spot 3/4h.
15. Comparaciones manuales repetían contexto por símbolo → una ficha compacta por activo.
16. Consejo de cada mercado no veía panorama global → snapshot cache-only de los tres mercados.
17. Multi no tenía Research causal/OOS → paquete Research coordinado y acotado.
18. Aislamiento por usuario verificado en Guardian Multi → `user_name=user`.

## Guardas de recursos
- Main: mismo worker/threading y mismos budgets de DB/Groq.
- Scanner Multi: 0 LLM, 0 escrituras DB.
- Consejo: 450 tokens máximo de salida y caché por bucket.
- Research Multi: 10 celdas/run, Strategy service existente, 0 LLM, 0 tablas.
- Ningún SQL/migración.

## Validación local
- QA 12.1 original: PASS.
- Contrato IA nuevo: 16/16 PASS.
- Python compile Main: PASS.
- JS syntax Main: PASS.
- Research module audit: PASS.
- Research synthetic causal batch: 10/10 cells PASS.
- Python compile Research: PASS.
