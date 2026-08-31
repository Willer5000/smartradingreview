-- ============================================================================
-- SCHEMA: saved_signals (señales guardadas manualmente por el usuario)
-- ============================================================================
-- v22.9: Solo aplica a señales de FUTUROS (spot no lo usa).
-- El usuario guarda una señal desde el modal de "Justificación de Señal Anterior"
-- ingresando su monto, apalancamiento personalizado y confirmando entry/TP/SL.
--
-- Estados posibles (status):
--   'active'        : señal activa, esperando que el precio toque entry
--   'entry_touched' : el precio tocó el entry (marca importante para winrate)
--   'tp_hit'        : el precio alcanzó take profit → cerrada como ganadora
--   'sl_hit'        : el precio alcanzó stop loss → cerrada como perdedora
--   'closed_manual' : usuario cerró manualmente (rentabilidad segun current_price)
--   'deleted'       : usuario eliminó la señal (soft delete)
--
-- Reglas de winrate:
--   - Solo cuentan para winrate las señales cuyo status ∈ (tp_hit, sl_hit, closed_manual)
--   - Adicionalmente entry_touched=true para que cuente
--     (si el precio nunca tocó el entry, NO se computa como win/loss)
-- ============================================================================

CREATE TABLE IF NOT EXISTS saved_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Datos de la señal original (copia snapshot al guardar)
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('LONG', 'SHORT')),
    confidence NUMERIC(5, 2) DEFAULT 0,
    
    -- Niveles (el usuario puede modificarlos al guardar)
    entry NUMERIC(20, 8) NOT NULL,
    stop_loss NUMERIC(20, 8) NOT NULL,
    take_profit NUMERIC(20, 8) NOT NULL,
    leverage INTEGER NOT NULL DEFAULT 1,
    
    -- Configuración del usuario
    investment_usdt NUMERIC(20, 4) NOT NULL DEFAULT 10,
    
    -- Metadatos de la señal original (para trazabilidad)
    original_confidence NUMERIC(5, 2),
    original_entry NUMERIC(20, 8),
    original_stop_loss NUMERIC(20, 8),
    original_take_profit NUMERIC(20, 8),
    original_leverage INTEGER,
    candle_timestamp TIMESTAMPTZ,
    
    -- Estado y evaluación
    status TEXT NOT NULL DEFAULT 'active',
    entry_touched BOOLEAN NOT NULL DEFAULT FALSE,
    entry_touched_at TIMESTAMPTZ,
    entry_touched_price NUMERIC(20, 8),
    
    -- Cierre (cualquier tipo)
    closed_at TIMESTAMPTZ,
    closed_price NUMERIC(20, 8),
    pnl_pct NUMERIC(10, 4),           -- ROI apalancado real (incluye leverage)
    pnl_usdt NUMERIC(20, 4),          -- Ganancia/pérdida en USDT
    close_reason TEXT, -- 'tp_hit' | 'sl_hit' | 'manual' | 'expired'
    
    -- ============================================================================
    -- FASE 7D.2 — MFE / MAE DE POSICIONES GUARDADAS
    -- ============================================================================
    
    mfe_price NUMERIC(20, 8) DEFAULT 0,
    mae_price NUMERIC(20, 8) DEFAULT 0,
    
    mfe_pct NUMERIC(10, 4) DEFAULT 0,
    mae_pct NUMERIC(10, 4) DEFAULT 0,
    
    mfe_r NUMERIC(10, 4) DEFAULT 0,
    mae_r NUMERIC(10, 4) DEFAULT 0,
    
    candles_to_mfe INTEGER DEFAULT 0,
    candles_to_mae INTEGER DEFAULT 0,
    
    last_excursion_at TIMESTAMPTZ,

    -- ============================================================================
    -- FASE 7D.3 — EARLY EXIT SHADOW MODE
    -- ============================================================================
    -- Guarda la primera ocasión en que el Futures Position Guardian
    -- habría recomendado EXIT.
    --
    -- IMPORTANTE:
    -- esto NO cierra la posición.
    -- Sólo permite comparar posteriormente esa salida hipotética
    -- contra el resultado real de TP / SL / cierre manual.
    -- ============================================================================

    early_exit_candidate_at TIMESTAMPTZ,
    early_exit_candidate_price NUMERIC(20, 8),
    early_exit_candidate_r NUMERIC(10, 4),

    early_exit_score NUMERIC(6, 2),
    early_exit_reason TEXT,

    early_exit_mfe_r NUMERIC(10, 4),
    early_exit_mae_r NUMERIC(10, 4),

    early_exit_evaluated BOOLEAN DEFAULT FALSE,

    actual_close_r NUMERIC(10, 4),
    early_exit_delta_r NUMERIC(10, 4),
    early_exit_would_help BOOLEAN,

    -- Timestamps
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- v22.9.4: fecha/hora que el USUARIO ingresa la señal (editable)
    -- Puede ser distinta de created_at si el usuario guarda una señal con
    -- retraso o si quiere backtestear una entrada teórica de una vela pasada.
    entry_at TIMESTAMPTZ,
    
    -- Notas del usuario (opcional)
    notes TEXT
);

-- Migración: añadir columna entry_at si la tabla ya existe (idempotente)
ALTER TABLE saved_signals
ADD COLUMN IF NOT EXISTS entry_at TIMESTAMPTZ;

-- ============================================================================
-- FASE 7D.2 — MIGRACIÓN MFE / MAE
-- ============================================================================

ALTER TABLE saved_signals
    ADD COLUMN IF NOT EXISTS mfe_price NUMERIC(20, 8) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mae_price NUMERIC(20, 8) DEFAULT 0,

    ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC(10, 4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mae_pct NUMERIC(10, 4) DEFAULT 0,

    ADD COLUMN IF NOT EXISTS mfe_r NUMERIC(10, 4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mae_r NUMERIC(10, 4) DEFAULT 0,

    ADD COLUMN IF NOT EXISTS candles_to_mfe INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS candles_to_mae INTEGER DEFAULT 0,

        ADD COLUMN IF NOT EXISTS last_excursion_at TIMESTAMPTZ;

-- ============================================================================
-- FASE 7D.3 — EARLY EXIT SHADOW MODE
-- ============================================================================

ALTER TABLE saved_signals
    ADD COLUMN IF NOT EXISTS early_exit_candidate_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS early_exit_candidate_price NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS early_exit_candidate_r NUMERIC(10, 4),

    ADD COLUMN IF NOT EXISTS early_exit_score NUMERIC(6, 2),
    ADD COLUMN IF NOT EXISTS early_exit_reason TEXT,

    ADD COLUMN IF NOT EXISTS early_exit_mfe_r NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS early_exit_mae_r NUMERIC(10, 4),

    ADD COLUMN IF NOT EXISTS early_exit_evaluated BOOLEAN DEFAULT FALSE,

    ADD COLUMN IF NOT EXISTS actual_close_r NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS early_exit_delta_r NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS early_exit_would_help BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_saved_signals_status ON saved_signals(status);
CREATE INDEX IF NOT EXISTS idx_saved_signals_symbol_tf ON saved_signals(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_saved_signals_created ON saved_signals(created_at DESC);

-- ============================================================================
-- Verificación de la tabla creada
-- ============================================================================
SELECT
    'saved_signals' as tablename,
    COUNT(*) as filas,
    'creada' as estado
FROM saved_signals;
