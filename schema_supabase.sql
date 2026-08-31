-- ============================================================================
-- SCHEMA SUPABASE PARA EL SISTEMA REVIEWTRADER + FUTUROS
-- Versión 1.0 - FASE 1
-- ============================================================================
-- INSTRUCCIONES:
-- 1. Entrar a tu proyecto Supabase → SQL Editor → New Query
-- 2. Copiar y pegar TODO este archivo
-- 3. Presionar "Run"
-- 4. Verificar que las 7 tablas se crearon en Table Editor
-- ============================================================================

-- Extensión para UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- TABLA 1: signals (todas las señales generadas)
-- ============================================================================
CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    system_type TEXT NOT NULL CHECK (system_type IN ('spot', 'futures', 'both')),
    action_original TEXT NOT NULL,          -- COMPRA_SPOT, LONG, VENTA_SPOT, SHORT, NO_OPERAR
    action_normalized TEXT NOT NULL,        -- LONG, SHORT, NO_OPERAR (equivalencia)
    confidence NUMERIC(5, 2) NOT NULL DEFAULT 0,
    entry_price NUMERIC(20, 8) DEFAULT 0,
    stop_loss NUMERIC(20, 8) DEFAULT 0,
    take_profit NUMERIC(20, 8) DEFAULT 0,
    leverage INTEGER DEFAULT 1,
    risk_reward NUMERIC(5, 2) DEFAULT 0,
    current_price NUMERIC(20, 8) DEFAULT 0,
    candle_timestamp TIMESTAMPTZ,           -- Timestamp de la vela ANTERIOR cerrada
    indicators_snapshot JSONB DEFAULT '{}'::jsonb,
    context JSONB DEFAULT '{}'::jsonb,
    was_executed BOOLEAN DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, tp_hit, sl_hit, expired, missed_opportunity
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_tf ON signals(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_signals_action_norm ON signals(action_normalized);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_candle_ts ON signals(candle_timestamp DESC);


-- ============================================================================
-- TABLA 2: signal_indicators (estrategias detectadas por señal - relación N:M)
-- ============================================================================
CREATE TABLE IF NOT EXISTS signal_indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    strategy_name TEXT NOT NULL,
    indicator_values JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_si_signal ON signal_indicators(signal_id);
CREATE INDEX IF NOT EXISTS idx_si_strategy ON signal_indicators(strategy_name);


-- ============================================================================
-- TABLA 3: signal_results (resultado final de cada señal)
-- ============================================================================
CREATE TABLE IF NOT EXISTS signal_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    status TEXT NOT NULL, -- tp_hit, sl_hit, expired, missed_opportunity
    exit_price NUMERIC(20, 8) DEFAULT 0,
    exit_timestamp TIMESTAMPTZ,
    pnl_pct NUMERIC(10, 4) DEFAULT 0,
    candles_to_result INTEGER DEFAULT 0,

    -- ========================================================================
    -- FASE 7D — MFE / MAE HISTÓRICO
    -- ========================================================================
    -- Maximum Favorable Excursion:
    -- máximo movimiento favorable alcanzado antes de cerrar la operación.
    --
    -- Maximum Adverse Excursion:
    -- máximo movimiento adverso soportado antes de cerrar la operación.
    --
    -- Se almacenan en precio, porcentaje y unidades R.
    -- ========================================================================

    mfe_price NUMERIC(20, 8) DEFAULT 0,
    mae_price NUMERIC(20, 8) DEFAULT 0,

    mfe_pct NUMERIC(10, 4) DEFAULT 0,
    mae_pct NUMERIC(10, 4) DEFAULT 0,

    mfe_r NUMERIC(10, 4) DEFAULT 0,
    mae_r NUMERIC(10, 4) DEFAULT 0,

    candles_to_mfe INTEGER DEFAULT 0,
    candles_to_mae INTEGER DEFAULT 0,

    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sr_signal ON signal_results(signal_id);
CREATE INDEX IF NOT EXISTS idx_sr_status ON signal_results(status);

-- ============================================================================
-- FASE 7D — MIGRACIÓN MFE / MAE
-- ============================================================================
-- CREATE TABLE IF NOT EXISTS no modifica tablas que ya existían.
-- Por eso mantenemos también esta migración idempotente.
-- ============================================================================

ALTER TABLE IF EXISTS public.signal_results
    ADD COLUMN IF NOT EXISTS mfe_price NUMERIC(20, 8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mae_price NUMERIC(20, 8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(10, 4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(10, 4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mfe_r NUMERIC(10, 4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mae_r NUMERIC(10, 4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS candles_to_mfe INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS candles_to_mae INTEGER DEFAULT 0;

-- ============================================================================
-- TABLA 4: strategy_stats_specific (estadísticas por par + TF + acción + estrategia)
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategy_stats_specific (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    action TEXT NOT NULL,                   -- Normalizado: LONG, SHORT
    strategy TEXT NOT NULL,
    total_signals INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    expired INTEGER DEFAULT 0,
    win_rate NUMERIC(5, 2) DEFAULT 0,       -- 0-100
    avg_win_pct NUMERIC(10, 4) DEFAULT 0,
    avg_loss_pct NUMERIC(10, 4) DEFAULT 0,
    avg_rr NUMERIC(5, 2) DEFAULT 0,
    expectancy NUMERIC(10, 4) DEFAULT 0,    -- (win_rate * avg_win) - (loss_rate * avg_loss)
    last_20_win_rate NUMERIC(5, 2) DEFAULT 0,  -- Para detectar degradación
    is_degrading BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sss_unique 
    ON strategy_stats_specific(symbol, timeframe, action, strategy);
CREATE INDEX IF NOT EXISTS idx_sss_win_rate ON strategy_stats_specific(win_rate DESC);
CREATE INDEX IF NOT EXISTS idx_sss_expectancy ON strategy_stats_specific(expectancy DESC);


-- ============================================================================
-- TABLA 5: strategy_stats_general (estadísticas globales por estrategia)
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategy_stats_general (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy TEXT NOT NULL UNIQUE,
    total_signals INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate NUMERIC(5, 2) DEFAULT 0,
    avg_rr NUMERIC(5, 2) DEFAULT 0,
    expectancy NUMERIC(10, 4) DEFAULT 0,
    best_symbols JSONB DEFAULT '[]'::jsonb,       -- ["BTC-USDT", "ETH-USDT"]
    worst_symbols JSONB DEFAULT '[]'::jsonb,      -- ["XRP-USDT"]
    best_timeframes JSONB DEFAULT '[]'::jsonb,    -- ["4h", "1h"]
    worst_timeframes JSONB DEFAULT '[]'::jsonb,   -- ["5m"]
    is_degrading BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ssg_expectancy ON strategy_stats_general(expectancy DESC);


-- ============================================================================
-- TABLA 6: missed_opportunities (señales NO_OPERAR/ESPERAR que resultaron rentables)
-- ============================================================================
CREATE TABLE IF NOT EXISTS missed_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    action_that_should_have_been TEXT NOT NULL,  -- LONG o SHORT (normalizado)
    confidence_at_moment NUMERIC(5, 2) DEFAULT 0,
    strategies_detected JSONB DEFAULT '[]'::jsonb,
    indicators_snapshot JSONB DEFAULT '{}'::jsonb,
    price_at_signal NUMERIC(20, 8) DEFAULT 0,
    max_favorable_price NUMERIC(20, 8) DEFAULT 0,
    max_favorable_pct NUMERIC(10, 4) DEFAULT 0,
    candles_to_max INTEGER DEFAULT 0,
    candle_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mo_symbol_tf ON missed_opportunities(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_mo_action ON missed_opportunities(action_that_should_have_been);
CREATE INDEX IF NOT EXISTS idx_mo_created ON missed_opportunities(created_at DESC);


-- ============================================================================
-- TABLA 7: review_recommendations (cache de recomendaciones pre-calculadas)
-- ============================================================================
CREATE TABLE IF NOT EXISTS review_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    action TEXT NOT NULL,                          -- LONG, SHORT (normalizado)
    winning_strategies JSONB DEFAULT '[]'::jsonb,  -- Top estrategias ganadoras
    losing_strategies JSONB DEFAULT '[]'::jsonb,   -- Top estrategias perdedoras
    best_combinations JSONB DEFAULT '[]'::jsonb,   -- Combinaciones óptimas
    win_rate NUMERIC(5, 2) DEFAULT 0,
    expectancy NUMERIC(10, 4) DEFAULT 0,
    sample_size INTEGER DEFAULT 0,
    recommended_confidence_multiplier NUMERIC(3, 2) DEFAULT 1.0,  -- 0.5x - 1.5x
    recommended_leverage INTEGER DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rr_unique 
    ON review_recommendations(symbol, timeframe, action);


-- ============================================================================
-- FUNCIONES ÚTILES (opcional pero recomendado)
-- ============================================================================

-- Función para obtener estadísticas rápidas (uso opcional)
CREATE OR REPLACE FUNCTION get_symbol_summary(p_symbol TEXT)
RETURNS TABLE (
    total_signals BIGINT,
    tp_count BIGINT,
    sl_count BIGINT,
    win_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as total_signals,
        COUNT(*) FILTER (WHERE status = 'tp_hit')::BIGINT as tp_count,
        COUNT(*) FILTER (WHERE status = 'sl_hit')::BIGINT as sl_count,
        CASE 
            WHEN COUNT(*) FILTER (WHERE status IN ('tp_hit', 'sl_hit')) > 0 THEN
                (COUNT(*) FILTER (WHERE status = 'tp_hit')::NUMERIC / 
                 COUNT(*) FILTER (WHERE status IN ('tp_hit', 'sl_hit'))::NUMERIC) * 100
            ELSE 0
        END as win_rate
    FROM signals
    WHERE symbol = p_symbol AND status != 'pending';
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- ROW LEVEL SECURITY (RLS) - Opcional pero recomendado
-- ============================================================================
-- Si tu proyecto Supabase requiere RLS, descomentar y ajustar según tus políticas:

-- ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE signal_indicators ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE signal_results ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE strategy_stats_specific ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE strategy_stats_general ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE missed_opportunities ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE review_recommendations ENABLE ROW LEVEL SECURITY;

-- Política permisiva por defecto (ajustar según necesidad):
-- CREATE POLICY "Enable all for service_role" ON signals FOR ALL 
--     USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');


-- ============================================================================
-- VERIFICACIÓN FINAL
-- ============================================================================
-- Ejecutar esta query después del CREATE para verificar que todo está OK:

SELECT 
    schemaname,
    tablename,
    'created' as status
FROM pg_tables
WHERE tablename IN (
    'signals', 
    'signal_indicators', 
    'signal_results',
    'strategy_stats_specific', 
    'strategy_stats_general',
    'missed_opportunities', 
    'review_recommendations'
)
ORDER BY tablename;

-- Debe retornar 7 filas.
