-- ============================================================================
-- ACTIVAR ROW LEVEL SECURITY (RLS) EN TODAS LAS TABLAS
-- ============================================================================
-- Propósito: eliminar la advertencia de seguridad de Supabase que dice
-- "Table public.X is public, but RLS has not been enabled".
--
-- Cómo funciona:
-- - RLS activado + SIN políticas = tabla completamente bloqueada al público
-- - El backend usa la SERVICE_ROLE_KEY (sb_secret_...) que BYPASSA RLS
--   automáticamente, así que la app sigue funcionando igual.
-- - Un atacante con la anon_key NO podrá leer/escribir estas tablas.
--
-- INSTRUCCIONES:
-- 1. Supabase → SQL Editor → New Query
-- 2. Copiar TODO este archivo
-- 3. Presionar "Run"
-- 4. Verificar en Table Editor que las tablas muestran el candado (RLS enabled)
-- ============================================================================

-- Activar RLS en todas las tablas del ReviewTrader
ALTER TABLE IF EXISTS public.signals              ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signal_indicators    ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.signal_results       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.strategy_stats_specific ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.strategy_stats_general  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.missed_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.review_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.review_logs          ENABLE ROW LEVEL SECURITY;

-- IMPORTANTE: NO creamos políticas.
-- Sin políticas + RLS activado = bloqueo total para roles anon y authenticated.
-- Solo el service_role (que el backend usa) puede operar sobre las tablas.

-- ============================================================================
-- VERIFICACIÓN
-- ============================================================================
-- Ejecuta esto para confirmar que RLS está activo en todas las tablas:
--
-- SELECT tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public'
--   AND tablename IN (
--     'signals', 'signal_indicators', 'signal_results',
--     'strategy_stats_specific', 'strategy_stats_general',
--     'missed_opportunities', 'review_recommendations', 'review_logs'
--   );
--
-- Todas deben mostrar rowsecurity = true
-- ============================================================================
