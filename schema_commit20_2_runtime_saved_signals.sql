-- Commit 20.2 — idempotent Saved Signals market contract / diagnostics
ALTER TABLE public.saved_signals
    ADD COLUMN IF NOT EXISTS market_type TEXT,
    ADD COLUMN IF NOT EXISTS asset_class TEXT,
    ADD COLUMN IF NOT EXISTS data_provider TEXT,
    ADD COLUMN IF NOT EXISTS premium_route TEXT,
    ADD COLUMN IF NOT EXISTS premium_blocker_stage TEXT,
    ADD COLUMN IF NOT EXISTS premium_blocker_codes JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS premium_path_version TEXT;

CREATE INDEX IF NOT EXISTS idx_saved_signals_20_2_market
    ON public.saved_signals(market_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_saved_signals_20_2_provider
    ON public.saved_signals(data_provider, created_at DESC);
