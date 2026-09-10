-- ==========================================================================
-- COMMIT 9 — NET EDGE ECONOMICS + RISK-BUDGET LEVERAGE
-- Adds only diagnostic/economic fields to immutable signal outcomes.
-- It does NOT delete or rewrite TP/SL/Entry/SL/TP/leverage history.
-- ==========================================================================

ALTER TABLE IF EXISTS public.signal_results
    ADD COLUMN IF NOT EXISTS entry_timestamp TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS economics_model_version TEXT,
    ADD COLUMN IF NOT EXISTS economics_status TEXT,
    ADD COLUMN IF NOT EXISTS economics_cost_model_source TEXT,
    ADD COLUMN IF NOT EXISTS economics_round_trip_cost_rate NUMERIC(18, 10),
    ADD COLUMN IF NOT EXISTS economics_cost_components_complete BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gross_r NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS gross_pnl_pct_margin NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS modeled_fee_slippage_cost_r NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS funding_data_source TEXT,
    ADD COLUMN IF NOT EXISTS funding_calculation_status TEXT,
    ADD COLUMN IF NOT EXISTS funding_contract_symbol TEXT,
    ADD COLUMN IF NOT EXISTS funding_settlements_count INTEGER,
    ADD COLUMN IF NOT EXISTS funding_rate_sum NUMERIC(24, 12),
    ADD COLUMN IF NOT EXISTS funding_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS modeled_funding_cost_r NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS modeled_total_cost_r NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS modeled_net_r NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS modeled_net_pnl_pct_margin NUMERIC(18, 8),
    -- Reserved for future exchange-confirmed fills/costs. This project does not populate it.
    ADD COLUMN IF NOT EXISTS net_pnl_pct NUMERIC(18, 8),
    ADD COLUMN IF NOT EXISTS economics_quality TEXT,
    ADD COLUMN IF NOT EXISTS funding_attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS economics_last_error TEXT,
    ADD COLUMN IF NOT EXISTS economics_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_signal_results_economics_pending
ON public.signal_results (economics_status, economics_updated_at)
WHERE status IN ('tp_hit', 'sl_hit');

CREATE INDEX IF NOT EXISTS idx_signal_results_economics_complete
ON public.signal_results (economics_cost_components_complete, economics_status)
WHERE status IN ('tp_hit', 'sl_hit');

-- Explicitly keep risk-growth authority closed until the next ReviewTrader
-- governance refresh evaluates the new Commit-9 economic evidence.
UPDATE public.autopilot_governance_state
SET risk_growth_allowed = FALSE,
    version = 'C9_NET_EDGE_GOVERNANCE_V2',
    updated_at = NOW()
WHERE scope = 'FUTURES_GLOBAL';

SELECT
    COUNT(*) FILTER (WHERE economics_cost_components_complete IS TRUE) AS model_complete_results,
    COUNT(*) FILTER (WHERE status IN ('tp_hit', 'sl_hit')) AS resolved_results
FROM public.signal_results;
