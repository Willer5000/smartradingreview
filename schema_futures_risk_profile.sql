-- ============================================================================
-- SMARTRADINGREVIEW
-- COMMIT 36P — PERFIL PERSONAL DE RIESGO FUTURES
-- ============================================================================

ALTER TABLE public.user_preferences

    ADD COLUMN IF NOT EXISTS
        futures_risk_mode TEXT DEFAULT 'MANUAL',

    ADD COLUMN IF NOT EXISTS
        futures_margin_policy TEXT DEFAULT 'FIXED_USDT',

    ADD COLUMN IF NOT EXISTS
        futures_equity_usdt NUMERIC(20, 4),

    ADD COLUMN IF NOT EXISTS
        futures_max_allocation_pct NUMERIC(8, 4),

    ADD COLUMN IF NOT EXISTS
        futures_max_loss_pct_equity_per_trade NUMERIC(8, 4),

    ADD COLUMN IF NOT EXISTS
        futures_preferred_margin_usdt NUMERIC(20, 4),

    ADD COLUMN IF NOT EXISTS
        futures_personal_max_leverage INTEGER,

    ADD COLUMN IF NOT EXISTS
        futures_risk_updated_at TIMESTAMPTZ;
