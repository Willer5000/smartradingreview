-- COMMIT 10 · FINAL PHASE 1 SECURITY LOCKDOWN
-- IMPORTANT: execute only after confirming Render uses a Supabase service-role key
-- (CENTRAL_SUPABASE_SERVICE_KEY or SUPABASE_SERVICE_ROLE_KEY, or equivalent
-- legacy SUPABASE_KEY whose JWT role is service_role). The backend is server-side.
-- Service-role bypasses RLS. anon/authenticated are intentionally denied direct access.

begin;

-- Main/runtime tables are server-owned. RLS + revoke prevents accidental direct
-- PostgREST exposure if a publishable/anon key is ever exposed client-side.
alter table public.signals enable row level security;
alter table public.signal_indicators enable row level security;
alter table public.signal_results enable row level security;
alter table public.strategy_stats_specific enable row level security;
alter table public.strategy_stats_general enable row level security;
alter table public.missed_opportunities enable row level security;
alter table public.review_recommendations enable row level security;
alter table public.review_logs enable row level security;
alter table public.saved_signals enable row level security;
alter table public.user_portfolios enable row level security;
alter table public.user_trades enable row level security;
alter table public.user_preferences enable row level security;
alter table public.guardian_learning_events enable row level security;
alter table public.ai_usage_events enable row level security;
alter table public.ai_advisor_observations enable row level security;
alter table public.ai_control_events enable row level security;
alter table public.strategy_registry enable row level security;
alter table public.strategy_research_runs enable row level security;
alter table public.adaptive_execution_profiles enable row level security;
alter table public.adaptive_execution_profile_history enable row level security;
alter table public.adaptive_autopilot_events enable row level security;
alter table public.edge_discovery_runs enable row level security;
alter table public.edge_hypotheses enable row level security;
alter table public.autopilot_governance_state enable row level security;
alter table public.runtime_snapshots_v1 enable row level security;
alter table public.macro_context_events_v1 enable row level security;

revoke all on table
  public.signals,
  public.signal_indicators,
  public.signal_results,
  public.strategy_stats_specific,
  public.strategy_stats_general,
  public.missed_opportunities,
  public.review_recommendations,
  public.review_logs,
  public.saved_signals,
  public.user_portfolios,
  public.user_trades,
  public.user_preferences,
  public.guardian_learning_events,
  public.ai_usage_events,
  public.ai_advisor_observations,
  public.ai_control_events,
  public.strategy_registry,
  public.strategy_research_runs,
  public.adaptive_execution_profiles,
  public.adaptive_execution_profile_history,
  public.adaptive_autopilot_events,
  public.edge_discovery_runs,
  public.edge_hypotheses,
  public.autopilot_governance_state,
  public.runtime_snapshots_v1,
  public.macro_context_events_v1
from anon, authenticated;

-- Research is server-only too. Existing RLS is preserved; explicit grants are removed.
revoke all on table
  public.q6_job_runs,
  public.research_candidate_memory_v1,
  public.research_champions_v1,
  public.research_engine_state_v1,
  public.research_findings_v1,
  public.research_governance_snapshot_v1,
  public.research_promotions_v1,
  public.research_runs_v1,
  public.research_shadow_live_v1,
  public.research_validated_history_v1
from anon, authenticated;

-- SECURITY DEFINER cleanup RPCs must not be callable by public API roles.
revoke execute on function public.cleanup_research_federation_v1() from public, anon, authenticated;
revoke execute on function public.cleanup_research_shadow_v1() from public, anon, authenticated;

-- Pin search_path on the remaining cleanup function.
alter function public.cleanup_ephemeral_v1() set search_path = public, pg_temp;
revoke execute on function public.cleanup_ephemeral_v1() from public, anon, authenticated;

-- Make the metrics view obey invoker permissions/RLS and remove direct API grants.
alter view public.research_shadow_live_metrics_v1 set (security_invoker = true);
revoke all on public.research_shadow_live_metrics_v1 from anon, authenticated;

commit;
