# PROMPT MACRO — CONTINUIDAD SMARTRADINGREVIEW DESDE COMMIT 17.5.1

Trabaja sobre SmarTradingReview desde **Commit 17.5.1 Stable Recovery · Multi-Asset + Leverage Preservation**.

## Estado de referencia
- Base: ZIP del usuario `smartradingreview-main commit 17.5.zip`.
- NO volver a la rama 17.4/17.4.1 ni introducir estados Signal/Execution nuevos.
- Spot y Crypto Futures conservan el motor estable del 17.5 del usuario.
- Entry/SL/TP conservan el endurecimiento quirúrgico de 17.5.
- Leverage conserva EXACTAMENTE `RC9_7_14_STANDARD_TECHNICAL_MAX_LEVERAGE_V6`, idéntico al Commit 13 pre-heatmap.
- Multi-Activo fue reparado de forma AISLADA: celdas propias 1h/4h/1D, router de velas cerradas, caché por TF, scheduler close-aware y retries bounded.

## Reglas no negociables
1. No buscar lluvia de señales. Calidad primero.
2. No reducir Safety/MTF/familias para aumentar frecuencia.
3. No forzar leverage alto ni regresar a leverage 1x/2x por tamaño de posición. El leverage se calcula por geometría, volatilidad, liquidación, maintenance margin, límites del contrato y calidad; la posición se reduce por separado.
4. CORE/MEDIUM/HIGH permanecen diferenciados.
5. Multi-Activo NO debe modificar Crypto Futures. Toda modificación Multi-Activo debe estar scopeada por sus siete símbolos.
6. Multi-Activo usa sólo 1h/4h/1D.
7. Comités Entry/SL/TP mejoran geometría después de la señal; no deben crear la dirección.
8. No romper login ni Liquidation Map.
9. Frontend nunca expone terminología interna del sistema.
10. Mantener Render/Supabase/Groq dentro de tiers gratuitos: evitar requests, polling, DB writes, workers y llamadas IA adicionales.
11. Cada ZIP debe incluir este Prompt Macro actualizado.

## Historial clave GitHub
- Commit 13 `718f4af2...`: comités SL/TP/apalancamiento; leverage V6.
- Commit 14 `b7892f4b...`: inicio del nuevo Liquidation Map.
- Commit 17.2 `46783417...`: runtime reliability Multi-Activo; 17.5.1 recupera sólo su parte segura, sin persistencia Supabase extra.

## Autenticación
- Flask Session firmada con `SMARTRADING_SESSION_SECRET`.
- Usuarios/password desde `SMARTRADING_PASSWORD_*` env.
- `/api/auth/login`, `/api/auth/me`, `/api/auth/logout`.
- Supabase service/secret key server-side.
- IMPORTANTE: repo público; verificar/rotar `SCHEDULED_AUTH_KEY`, porque el código histórico conserva un fallback público conocido.

## Qué evaluar después del deploy
- Futures: frecuencia, WR, expectancy/R, MAE, MFE, reacción alrededor de SL, TP touch rate, leverage técnico recomendado.
- Multi-Activo: cobertura efectiva por 1h/4h/1D, runtime failures vs NO_OPERAR técnico, señales completas Entry/SL/TP/leverage.
- No modificar el motor por un solo trade o un solo día sin señales. Exigir regresión reproducible o evidencia estadística.
