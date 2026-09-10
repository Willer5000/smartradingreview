-- ==========================================================================
-- COMMIT 7 — EDGE DISCOVERY ENGINE
-- Research-only hypotheses. No production authority is stored here.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.edge_discovery_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version TEXT NOT NULL DEFAULT 'C7_EDGE_DISCOVERY_V1',
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edge_discovery_runs_created
ON public.edge_discovery_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS public.edge_hypotheses (
    hypothesis_key TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'OBSERVE'
        CHECK (state IN ('OBSERVE','PROMISING_NEEDS_VALIDATION','RESEARCH_PRIORITY','LOW_PRIORITY_RESEARCH')),
    factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    label TEXT NOT NULL DEFAULT '',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    version TEXT NOT NULL DEFAULT 'C7_EDGE_DISCOVERY_V1',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edge_hypotheses_state
ON public.edge_hypotheses(market, state, last_seen_at DESC);

SELECT
    (SELECT COUNT(*) FROM public.edge_discovery_runs) AS discovery_runs,
    (SELECT COUNT(*) FROM public.edge_hypotheses) AS hypotheses;
