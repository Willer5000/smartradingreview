-- ============================================================================
-- OPCIONAL: UNIQUE CONSTRAINT en la tabla signals para prevenir duplicados
-- ============================================================================
--
-- CUÁNDO EJECUTAR:
-- - DESPUÉS de haber ejecutado POST /api/admin/dedup_signals con éxito
--   (para no violar el constraint con duplicados existentes).
-- - Cuando quieras que la base de datos GARANTICE que no puede haber dos
--   señales idénticas para el mismo (symbol, timeframe, vela, acción, sistema).
--
-- QUÉ HACE:
-- - Crea un UNIQUE INDEX sobre (symbol, timeframe, candle_timestamp,
--   action_normalized, system_type).
-- - Después de esto, cualquier INSERT que intente duplicar una señal existente
--   fallará con error de la base de datos (impide silenciosamente el
--   duplicado). El código Python en supabase_client.py ya maneja este caso
--   con el dedup check previo, pero este constraint es un doble seguro.
--
-- CÓMO EJECUTAR:
-- 1. Ir a Supabase → SQL Editor → New Query
-- 2. Copiar y pegar TODO este archivo
-- 3. Click "Run"
-- 4. Verificar que apareció el mensaje "Success. No rows returned"
--
-- SI FALLA:
-- - Error "could not create unique index": significa que aún hay duplicados
--   en la tabla. Primero ejecuta:
--       POST https://smartradingreview.onrender.com/api/admin/dedup_signals
--       con header X-Auth-Key: crypto_trader_analyst_2025
--   y después vuelve a intentar este SQL.
-- ============================================================================

-- Índice UNIQUE parcial: solo aplica a filas con candle_timestamp NOT NULL.
-- Las filas sin candle_timestamp (fallbacks antiguos) no se cuentan como duplicados.
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_dedup
    ON public.signals (symbol, timeframe, candle_timestamp, action_normalized, system_type)
    WHERE candle_timestamp IS NOT NULL;

-- Verificación:
--   SELECT indexname, indexdef FROM pg_indexes 
--   WHERE tablename = 'signals' AND indexname = 'idx_signals_dedup';
--
-- Esperado: 1 fila con la definición del índice.
