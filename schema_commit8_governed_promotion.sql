-- ==========================================================================
-- COMMIT 8 — GOVERNED PROMOTION
-- Evidence-driven authority gate. No risk/leverage growth in this commit.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.autopilot_governance_state (
    scope TEXT PRIMARY KEY,
    quality_optimization_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    strategy_veto_authority_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    risk_growth_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    version TEXT NOT NULL DEFAULT 'C8_PROMOTION_GOVERNANCE_V1',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_autopilot_governance_updated
ON public.autopilot_governance_state(updated_at DESC);

-- Any ACTIVE state created under the old manual/env authority must be
-- revalidated under Commit 8 before it can affect runtime. CANARY has no
-- production authority.
UPDATE public.strategy_registry
SET state = 'CANARY',
    evidence = COALESCE(evidence, '{}'::jsonb) || '{"commit8_revalidation":"required"}'::jsonb,
    updated_at = NOW()
WHERE state = 'ACTIVE';

-- Fail-closed initial state. The ReviewTrader refresh will replace the evidence
-- only after it can verify the current 90-day window.
INSERT INTO public.autopilot_governance_state(
    scope,
    quality_optimization_allowed,
    strategy_veto_authority_allowed,
    risk_growth_allowed,
    evidence,
    version
)
VALUES (
    'FUTURES_GLOBAL',
    FALSE,
    FALSE,
    FALSE,
    '{"block_reasons":["WAITING_FIRST_GOVERNANCE_REFRESH"],"risk_growth_allowed":false}'::jsonb,
    'C8_PROMOTION_GOVERNANCE_V1'
)
ON CONFLICT (scope) DO NOTHING;

SELECT
    scope,
    quality_optimization_allowed,
    strategy_veto_authority_allowed,
    risk_growth_allowed,
    version,
    updated_at
FROM public.autopilot_governance_state
ORDER BY scope;
