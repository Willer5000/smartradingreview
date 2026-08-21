-- ============================================================================
-- SCHEMA ADICIONAL: Tabla de logs del ReviewTrader
-- ============================================================================
-- INSTRUCCIONES:
-- 1. Ir a Supabase → SQL Editor → New query
-- 2. Copiar y pegar este archivo completo
-- 3. Presionar Run (elegir "Run without RLS" si aparece el diálogo)
-- 4. Verificar que la tabla review_logs aparece en Table Editor
-- ============================================================================

CREATE TABLE IF NOT EXISTS review_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Timing de la ejecución
    run_started_at TIMESTAMPTZ NOT NULL,
    run_finished_at TIMESTAMPTZ,
    duration_seconds NUMERIC(10, 2),
    
    -- Trigger (manual desde endpoint o automático desde scheduler)
    trigger_source TEXT DEFAULT 'scheduler', -- scheduler | manual | test
    
    -- Resultados de evaluación de señales pendientes
    signals_evaluated INTEGER DEFAULT 0,
    tp_hits INTEGER DEFAULT 0,
    sl_hits INTEGER DEFAULT 0,
    expired INTEGER DEFAULT 0,
    still_pending INTEGER DEFAULT 0,
    
    -- Oportunidades perdidas detectadas
    missed_opportunities_found INTEGER DEFAULT 0,
    
    -- Actualización de estadísticas
    stats_specific_updated INTEGER DEFAULT 0,
    stats_general_updated INTEGER DEFAULT 0,
    recommendations_updated INTEGER DEFAULT 0,
    
    -- Optimizaciones de almacenamiento
    ttl_deleted INTEGER DEFAULT 0,
    low_sample_deleted INTEGER DEFAULT 0,
    
    -- Snapshot del uso de almacenamiento (JSONB)
    storage_stats JSONB DEFAULT '{}'::jsonb,
    
    -- Diagnóstico
    errors JSONB DEFAULT '[]'::jsonb,      -- lista de errores encontrados
    warnings JSONB DEFAULT '[]'::jsonb,    -- lista de advertencias
    notes TEXT,
    
    -- Estado final
    status TEXT DEFAULT 'success',         -- success | partial | failed
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_review_logs_started_at ON review_logs(run_started_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_logs_status ON review_logs(status);
CREATE INDEX IF NOT EXISTS idx_review_logs_trigger ON review_logs(trigger_source);


-- ============================================================================
-- Verificación
-- ============================================================================

SELECT 
    'review_logs' as tablename, 
    'created' as status;
