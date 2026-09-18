# RC9.7 · nueva Supabase desde cero

## Orden obligatorio

1. En la **nueva** Supabase abre `SQL Editor > New query`.
2. Copia y ejecuta completo `schema_rc9_7_fresh_supabase.sql` **una sola vez**.
3. El SELECT final debe mostrar aproximadamente:
   - `champions = 0`
   - `findings = 0`
   - `promotions = 0`
   - `research_target = 60`
   - `research_pending = 60`
4. Verifica en Render Main y Research que `CENTRAL_SUPABASE_URL` y la service key apuntan al mismo proyecto nuevo. No dejes un `SUPABASE_URL`, `RESEARCH_SUPABASE_URL` o key de fallback apuntando a la cuenta anterior.
5. Despliega **Research RC9.7** y luego **Main RC9.7**.
6. Inicia sesión y vuelve a cargar tu estado personal actual: cartera BTC/PAXG/USDT, preferencias Telegram y perfil de riesgo Futures si corresponde.

## Qué comienza en cero

No se importan señales históricas, outcomes, ReviewTrader, Shadow, Champions, Candidate Memory, AI Learning, Research findings/promotions, missed opportunities ni eventos macro históricos. `N=0` significa **SIN MUESTRA**, no WR 0%.

## Qué funciona inmediatamente sin aprendizaje previo

- Login (variables `SMARTRADING_PASSWORD_*` + sesión Flask).
- KuCoin, indicadores y análisis de mercado.
- Strategy Bank de contingencia RC9.7 (local en código).
- Tesis técnica autónoma.
- 9 especialistas técnicos.
- Smart-Money Entry, SL, TP, Safety y Guardian.
- Research: empieza nuevamente sus 60 celdas y puede reconstruir Backtest/OOS con históricos de mercado aunque la BD esté vacía.
- Científico IA: puede proponer hipótesis, pero no puede convertirlas directamente en operaciones.

## Free plan / egress

RC9.7 limita lecturas de aplicación de forma deliberadamente conservadora:

- Main: máximo interno 12 MB/día por proceso.
- Research: máximo interno 2 MB/día por servicio/proceso.
- Los bridges Research pasan por el mismo gobernador de egress.
- Las definiciones de las estrategias de contingencia permanecen en código; Supabase guarda referencias y resultados, no copias completas del banco.
- GC diario conserva evidencia compacta y limita telemetría raw recreable.

Estos límites son de la aplicación; el Dashboard de Supabase, accesos manuales y cualquier cliente externo también consumen cuota y deben vigilarse en Usage.

## Caída/HTTP 402 de Supabase

El trading técnico no debe detenerse. Main conserva Strategy Bank + tesis + KuCoin + Entry/SL/TP/Safety. Las escrituras críticas se ponen temporalmente en un outbox SQLite local aislado por fingerprint del proyecto y se reintentan cuando vuelve Supabase. El filesystem de Render Free es efímero: esto es continuidad, no una segunda base durable.

## Seguridad

El bootstrap prioriza compatibilidad con el backend actual. Después de comprobar que Main y Research usan una **service-role/service secret**, puedes revisar `schema_rc9_7_security_optional.sql`. No lo ejecutes antes de verificar el deploy porque RLS sin una credencial backend correcta bloquearía el sistema.
