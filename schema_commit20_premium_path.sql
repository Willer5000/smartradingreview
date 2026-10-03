-- Commit 20 — Premium Path Expansion
-- Adds market-aware metadata to Saved Signals so Futures and Multi-Asset use
-- the same lifecycle/detail API without sharing candle providers.

ALTER TABLE public.saved_signals
    ADD COLUMN IF NOT EXISTS market_type TEXT,
    ADD COLUMN IF NOT EXISTS asset_class TEXT,
    ADD COLUMN IF NOT EXISTS data_provider TEXT,
    ADD COLUMN IF NOT EXISTS premium_route TEXT,
    ADD COLUMN IF NOT EXISTS premium_blocker_stage TEXT,
    ADD COLUMN IF NOT EXISTS premium_blocker_codes JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS premium_path_version TEXT;

CREATE INDEX IF NOT EXISTS idx_saved_signals_market_type
ON public.saved_signals(market_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_saved_signals_premium_route
ON public.saved_signals(premium_route, created_at DESC);

COMMENT ON COLUMN public.saved_signals.market_type IS
'Commit 20: futures | multiasset | spot; selects lifecycle/chart data provider.';
COMMENT ON COLUMN public.saved_signals.data_provider IS
'Commit 20: source used by the saved-signal chart/lifecycle.';
COMMENT ON COLUMN public.saved_signals.premium_route IS
'Commit 20: diagnostic execution route; does not confer Premium authority.';
COMMENT ON COLUMN public.saved_signals.premium_blocker_stage IS
'Commit 20: exact Premium funnel stage captured when the signal was saved.';
