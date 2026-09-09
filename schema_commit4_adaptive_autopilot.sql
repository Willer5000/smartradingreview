-- ==========================================================================
-- COMMIT 4 — REVIEWTRADER ADAPTIVE AUTOPILOT
-- Versioned execution profiles + audit trail + unique research windows
-- ==========================================================================

ALTER TABLE IF EXISTS public.strategy_research_runs
    ADD COLUMN IF NOT EXISTS data_fingerprint TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_research_fingerprint
ON public.strategy_research_runs(data_fingerprint)
WHERE data_fingerprint IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.adaptive_execution_profiles (
    system_type TEXT NOT NULL DEFAULT 'futures',
    symbol TEXT NOT NULL DEFAULT '*',
    timeframe TEXT NOT NULL DEFAULT '*',
    market_regime TEXT NOT NULL DEFAULT '*',
    state TEXT NOT NULL DEFAULT 'OBSERVE'
        CHECK (state IN ('OBSERVE','PROTECT','ACTIVE','DEGRADED')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    version TEXT NOT NULL DEFAULT 'C4_ADAPTIVE_EXECUTION_PROFILE_V1',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (system_type, symbol, timeframe, market_regime)
);

CREATE INDEX IF NOT EXISTS idx_adaptive_execution_lookup
ON public.adaptive_execution_profiles(system_type, symbol, timeframe, market_regime, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.adaptive_execution_profile_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_type TEXT NOT NULL DEFAULT 'futures',
    symbol TEXT NOT NULL DEFAULT '*',
    timeframe TEXT NOT NULL DEFAULT '*',
    market_regime TEXT NOT NULL DEFAULT '*',
    state TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    version TEXT NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_adaptive_profile_history_lookup
ON public.adaptive_execution_profile_history(system_type, symbol, timeframe, archived_at DESC);

CREATE TABLE IF NOT EXISTS public.adaptive_autopilot_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    component TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    reason TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    version TEXT NOT NULL DEFAULT 'C4_REVIEWTRADER_AUTOPILOT_V1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_adaptive_autopilot_events_created
ON public.adaptive_autopilot_events(created_at DESC);

-- Baseline profile is OBSERVE and therefore has zero production authority.
INSERT INTO public.adaptive_execution_profiles(
    system_type, symbol, timeframe, market_regime, state, config, evidence
)
VALUES (
    'futures', '*', '*', '*', 'OBSERVE',
    '{
      "entry_min_defensibility": 0.0,
      "q2_weights": {"sl": 0.40, "tp": 0.30, "rr": 0.30},
      "q2_min_pair_improvement": 4.0,
      "leverage_target_factor": 1.0,
      "leverage_cap_factor": 1.0,
      "allow_leverage_growth": false,
      "minimum_safety_delta": 0.0
    }'::jsonb,
    '{"reason":"STATIC_BASELINE_NO_AUTHORITY"}'::jsonb
)
ON CONFLICT (system_type, symbol, timeframe, market_regime) DO NOTHING;

SELECT
    (SELECT COUNT(*) FROM public.adaptive_execution_profiles) AS adaptive_profiles,
    (SELECT COUNT(*) FROM public.strategy_registry) AS strategy_registry_rows,
    (SELECT COUNT(*) FROM public.adaptive_autopilot_events) AS autopilot_events;
