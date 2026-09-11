-- HOTFIX 14.9 — Restore Analytics learning without reintroducing Render OOM
-- Safe to run more than once.
-- Does NOT delete signals, signal_results, saved_signals, learning history or q6_job_runs.

-- 1) Index the exact JSON discriminator used by the current V2 cohort.
CREATE INDEX IF NOT EXISTS idx_signals_q5_quality_created_v1
ON public.signals (
    (context #>> '{execution,quality_score_version}'),
    created_at DESC
);

-- 2) Compact server-side projection.
--    PostgreSQL extracts only the learning/execution branches Analytics needs.
--    Render never receives the full analysis context JSON for thousands of rows.
CREATE OR REPLACE VIEW public.analytics_quality_v2_compact_v1
WITH (security_invoker = true)
AS
SELECT
    s.id,
    s.symbol,
    s.timeframe,
    s.system_type,
    s.action_normalized,
    s.status,
    s.created_at,
    s.entry_price,
    s.stop_loss,
    s.take_profit,
    s.risk_reward,

    jsonb_build_object(
        'learning', jsonb_build_object(
            'cohort', s.context #> '{learning,cohort}',
            'market_data_source', s.context #> '{learning,market_data_source}',
            'market_data_is_synthetic', s.context #> '{learning,market_data_is_synthetic}',
            'source_candle_closed', s.context #> '{learning,source_candle_closed}',
            'statistically_eligible', s.context #> '{learning,statistically_eligible}',
            'evaluation_role', s.context #> '{learning,evaluation_role}',
            'analysis_version', s.context #> '{learning,analysis_version}',
            'contract_version', s.context #> '{learning,contract_version}',
            'source_candle_timestamp', s.context #> '{learning,source_candle_timestamp}',
            'source_candle_close_timestamp', s.context #> '{learning,source_candle_close_timestamp}',
            'microstructure_shadow', COALESCE(s.context #> '{learning,microstructure_shadow}', '{}'::jsonb),
            'quantitative_shadow', COALESCE(s.context #> '{learning,quantitative_shadow}', '{}'::jsonb),
            'cautious_shadow', COALESCE(s.context #> '{learning,cautious_shadow}', '{}'::jsonb),
            'q7_strategy_lab_shadow', COALESCE(s.context #> '{learning,q7_strategy_lab_shadow}', '{}'::jsonb),
            'strategy_attribution_v2', COALESCE(s.context #> '{learning,strategy_attribution_v2}', '{}'::jsonb),
            'trader_intelligence_v2', COALESCE(s.context #> '{learning,trader_intelligence_v2}', '{}'::jsonb),
            'execution_challenger_lab', COALESCE(s.context #> '{learning,execution_challenger_lab}', '{}'::jsonb),
            'trendline_strategy_lab_shadow', COALESCE(s.context #> '{learning,trendline_strategy_lab_shadow}', '{}'::jsonb)
        ),
        'execution', jsonb_build_object(
            'quality_score_version', s.context #> '{execution,quality_score_version}',
            'execution_safety', s.context #> '{execution,execution_safety}',
            'entry_score', s.context #> '{execution,entry_score}',
            'sl_reliability', s.context #> '{execution,sl_reliability}',
            'tp_quality_score', s.context #> '{execution,tp_quality_score}',
            'futures_execution_refined', s.context #> '{execution,futures_execution_refined}',
            'entry_defensibility_score', s.context #> '{execution,entry_defensibility_score}',
            'entry_reachability_score', s.context #> '{execution,entry_reachability_score}',
            'entry_source', s.context #> '{execution,entry_source}'
        )
    ) AS context,

    COALESCE((
        SELECT jsonb_agg(latest_result.result_json)
        FROM (
            SELECT jsonb_build_object(
                'status', sr.status,
                'pnl_pct', sr.pnl_pct,
                'exit_price', sr.exit_price,
                'exit_timestamp', sr.exit_timestamp,
                'notes', sr.notes,
                'created_at', sr.created_at,
                'mfe_r', sr.mfe_r,
                'mae_r', sr.mae_r,
                'mfe_pct', sr.mfe_pct,
                'mae_pct', sr.mae_pct,
                'candles_to_result', sr.candles_to_result,
                'execution_forensics', COALESCE(sr.execution_forensics, '{}'::jsonb),
                -- These economics fields are read through to_jsonb so this view
                -- remains tolerant if a migration is temporarily behind.
                'gross_r', to_jsonb(sr) -> 'gross_r',
                'modeled_net_r', to_jsonb(sr) -> 'modeled_net_r',
                'modeled_total_cost_r', to_jsonb(sr) -> 'modeled_total_cost_r',
                'economics_cost_components_complete', to_jsonb(sr) -> 'economics_cost_components_complete'
            ) AS result_json
            FROM public.signal_results sr
            WHERE sr.signal_id = s.id
            ORDER BY sr.created_at DESC
            LIMIT 1
        ) AS latest_result
    ), '[]'::jsonb) AS signal_results

FROM public.signals s
WHERE
    s.context #>> '{execution,quality_score_version}' = '36W_V2_NORMALIZED'
    AND s.action_normalized IN ('LONG', 'SHORT', 'COMPRA_SPOT', 'VENTA_SPOT');

-- 3) Remove only the bad/recreatable Analytics snapshots produced while the
--    compact JSON alias query was failing. Durable learning remains untouched.
DELETE FROM public.runtime_snapshots_v1
WHERE namespace = 'analytics';

-- Optional sanity check after running this migration:
-- SELECT system_type, COUNT(*)
-- FROM public.analytics_quality_v2_compact_v1
-- WHERE created_at >= NOW() - INTERVAL '90 days'
-- GROUP BY system_type;
