# Commit 12 · Multi‑Activo Resource‑Governed

Este ZIP es **ready-tree**: contiene únicamente los archivos que deben agregarse o reemplazarse sobre el `main` actual posterior a Hotfix 10.2.2, más documentación y tests.

## Resultado visible

Aparece una tercera pestaña:

**SPOT | FUTUROS | MULTI‑ACTIVO**

Los códigos se muestran con nombre humano, por ejemplo:

- `CL (Petróleo WTI)`
- `SPY (S&P 500)`
- `QQQ (Nasdaq 100)`
- `NATGAS (Gas Natural)`
- `COPPER (Cobre)`
- `XAG (Plata)`
- `KSTR (China STAR 50)`

## Diseño operativo

`Opportunity Router barato → Macro Gate → shortlist ≤2 → motor técnico completo → Entry/Safety/Publication → Telegram → Guardian → ReviewTrader/Alpha Decay`

Multi‑Activo reutiliza el motor Futures probado pero tiene:
- banco de estrategias por clase/contexto;
- especialista por clase de activo;
- Macro/Intermarket Specialist;
- sesión y volatilidad propias;
- celdas de aprendizaje Multi‑Activo.

## Restricción central de recursos

No se aumentan:
- worker/threads Render;
- presupuesto Supabase de la app;
- presupuesto Groq;
- número de schedulers.

El scanner no escribe DB ni llama LLM.

## Instalación

Ver `COMMIT_12_DEPLOY_ORDER.txt`.

## Importante

No ejecutar ningún SQL: Commit 12 no lo necesita.
