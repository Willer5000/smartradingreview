-- COMMIT 3 — Strategy Lab registry + bounded historical research metadata
CREATE TABLE IF NOT EXISTS public.strategy_registry (
    strategy_key TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '*',
    timeframe TEXT NOT NULL DEFAULT '*',
    market_regime TEXT NOT NULL DEFAULT '*',
    state TEXT NOT NULL DEFAULT 'SHADOW' CHECK (state IN ('SHADOW','CHALLENGER','CANARY','ACTIVE','DEGRADED','DISABLED')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    version TEXT NOT NULL DEFAULT 'C3_STRATEGY_REGISTRY_V1',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (strategy_key, symbol, timeframe, market_regime)
);

CREATE TABLE IF NOT EXISTS public.strategy_research_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    cohort TEXT NOT NULL DEFAULT 'HISTORICAL_RESEARCH',
    engine_version TEXT NOT NULL,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_research_symbol_tf
ON public.strategy_research_runs(symbol, timeframe, created_at DESC);

INSERT INTO public.strategy_registry(strategy_key)
VALUES
 ('Q7_RSI_PROFILE_V1'),
 ('Q7_ROLLING_VWAP_REVERSION_V1'),
 ('Q7_BREAKOUT_RETEST_V1'),
 ('TRENDLINE_SUPPORT_REACTION_V1'),
 ('TRENDLINE_RESISTANCE_REACTION_V1'),
 ('TRENDLINE_BREAK_RETEST_LONG_V1'),
 ('TRENDLINE_BREAK_RETEST_SHORT_V1'),
 ('TRENDLINE_FIB_CONFLUENCE_V1')
ON CONFLICT DO NOTHING;
