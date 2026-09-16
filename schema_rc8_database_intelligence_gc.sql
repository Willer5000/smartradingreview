-- RC8 POST-AUDIT — DB intelligence / IO hygiene / signal identity
-- Idempotent. Preserves useful evidence; suppresses recreatable/no-op writes.

create schema if not exists maintenance;
revoke all on schema maintenance from public, anon, authenticated;
create extension if not exists pg_cron with schema extensions;

create table if not exists maintenance.research_evidence_compact_v1 (
  source_kind text not null, research_version text not null,
  engine text not null default '*', experiment text not null default '*', stage text not null default '*',
  market_family text not null default '*', symbol text not null default '*', timeframe text not null default '*',
  direction text not null default '*', regime text not null default '*', archived_rows bigint not null default 0,
  first_seen_at timestamptz, last_seen_at timestamptz, summary jsonb not null default '{}'::jsonb,
  last_compacted_at timestamptz not null default now(),
  primary key(source_kind,research_version,engine,experiment,stage,market_family,symbol,timeframe,direction,regime)
);
create table if not exists maintenance.gc_runs_v1 (
  id bigint generated always as identity primary key, ran_at timestamptz not null default now(),
  active_research_version text, research_findings_deleted int not null default 0,
  research_promotions_deleted int not null default 0, runtime_snapshots_deleted int not null default 0,
  macro_events_deleted int not null default 0, research_runs_deleted int not null default 0,
  ai_usage_deleted int not null default 0, cron_logs_deleted int not null default 0,
  notes jsonb not null default '{}'::jsonb
);

create index if not exists idx_signal_results_signal_created_desc on public.signal_results(signal_id,created_at desc);
create index if not exists idx_research_findings_version_engine_updated on public.research_findings_v1(research_version,engine,updated_at desc);
create index if not exists idx_research_promotions_version_engine_updated on public.research_promotions_v1(research_version,source_engine,updated_at desc);
create index if not exists idx_research_promotions_version_stage_updated on public.research_promotions_v1(research_version,stage,updated_at desc);
create index if not exists idx_ai_advisor_saved_signal_fk on public.ai_advisor_observations(related_saved_signal_id);
create index if not exists idx_ai_control_observation_fk on public.ai_control_events(ai_observation_id);

alter table public.research_findings_v1 set (autovacuum_vacuum_scale_factor=.02,autovacuum_vacuum_threshold=50,autovacuum_analyze_scale_factor=.05,autovacuum_analyze_threshold=50);
alter table public.research_promotions_v1 set (autovacuum_vacuum_scale_factor=.02,autovacuum_vacuum_threshold=50,autovacuum_analyze_scale_factor=.05,autovacuum_analyze_threshold=50);
alter table public.runtime_snapshots_v1 set (autovacuum_vacuum_scale_factor=.05,autovacuum_vacuum_threshold=20);

-- SAME DATASET + SAME EVIDENCE = NO WRITE. New dataset fingerprint is still persisted.
create or replace function maintenance.skip_research_noop_v1() returns trigger
language plpgsql security invoker set search_path=public,maintenance,pg_temp as $$
declare old_fp text; new_fp text; old_meta jsonb; new_meta jsonb;
begin
  old_fp:=coalesce(old.meta->>'causal_dataset_signature',old.meta->>'dataset_fingerprint','');
  new_fp:=coalesce(new.meta->>'causal_dataset_signature',new.meta->>'dataset_fingerprint','');
  if old_fp='' or new_fp='' or old_fp<>new_fp then return new; end if;
  old_meta:=old.meta-'research_run_id'-'validation_run_id';
  new_meta:=new.meta-'research_run_id'-'validation_run_id';
  if tg_table_name='research_findings_v1' and
     new.engine is not distinct from old.engine and new.experiment is not distinct from old.experiment and
     new.scope is not distinct from old.scope and new.stage is not distinct from old.stage and
     new.authority is not distinct from old.authority and new.metrics is not distinct from old.metrics and
     new.research_version is not distinct from old.research_version and new_meta is not distinct from old_meta then
       return null;
  end if;
  if tg_table_name='research_promotions_v1' and
     new.source_engine is not distinct from old.source_engine and new.experiment is not distinct from old.experiment and
     new.stage is not distinct from old.stage and new.authority is not distinct from old.authority and
     new.reason is not distinct from old.reason and new.scope is not distinct from old.scope and
     new.metrics is not distinct from old.metrics and new.research_version is not distinct from old.research_version and
     new_meta is not distinct from old_meta then return null;
  end if;
  return new;
end $$;
revoke all on function maintenance.skip_research_noop_v1() from public,anon,authenticated;
drop trigger if exists trg_rc8_skip_noop_findings on public.research_findings_v1;
create trigger trg_rc8_skip_noop_findings before update on public.research_findings_v1 for each row execute function maintenance.skip_research_noop_v1();
drop trigger if exists trg_rc8_skip_noop_promotions on public.research_promotions_v1;
create trigger trg_rc8_skip_noop_promotions before update on public.research_promotions_v1 for each row execute function maintenance.skip_research_noop_v1();

create or replace function maintenance.skip_runtime_snapshot_noop_v1() returns trigger
language plpgsql security invoker set search_path=public,maintenance,pg_temp as $$
begin
  if new.payload is not distinct from old.payload and old.expires_at>now()+interval '1 hour' then return null; end if;
  return new;
end $$;
revoke all on function maintenance.skip_runtime_snapshot_noop_v1() from public,anon,authenticated;
drop trigger if exists trg_rc8_skip_runtime_snapshot_noop on public.runtime_snapshots_v1;
create trigger trg_rc8_skip_runtime_snapshot_noop before update on public.runtime_snapshots_v1 for each row execute function maintenance.skip_runtime_snapshot_noop_v1();

-- Consolidate historical exact duplicates, preserving all references/outcomes.
do $$
begin
  create temporary table rc8_signal_merge on commit drop as
  with ranked as (
    select s.id old_id,
      first_value(s.id) over(partition by s.symbol,s.timeframe,s.candle_timestamp,s.action_normalized,s.system_type order by
        exists(select 1 from public.signal_results r where r.signal_id=s.id) desc,
        exists(select 1 from public.research_shadow_live_v1 h where h.signal_id=s.id) desc,
        (s.status in ('tp_hit','sl_hit')) desc,s.created_at,s.id) keep_id,
      row_number() over(partition by s.symbol,s.timeframe,s.candle_timestamp,s.action_normalized,s.system_type order by
        exists(select 1 from public.signal_results r where r.signal_id=s.id) desc,
        exists(select 1 from public.research_shadow_live_v1 h where h.signal_id=s.id) desc,
        (s.status in ('tp_hit','sl_hit')) desc,s.created_at,s.id) rn
    from public.signals s where s.candle_timestamp is not null)
  select old_id,keep_id from ranked where rn>1;

  update public.saved_signals t set source_signal_id=m.keep_id::text from rc8_signal_merge m where t.source_signal_id=m.old_id::text;
  update public.ai_advisor_observations t set source_signal_id=m.keep_id::text from rc8_signal_merge m where t.source_signal_id=m.old_id::text;
  update public.ai_control_events t set source_signal_id=m.keep_id::text from rc8_signal_merge m where t.source_signal_id=m.old_id::text;
  update public.signal_results t set signal_id=m.keep_id from rc8_signal_merge m where t.signal_id=m.old_id;
  delete from public.signal_indicators i using rc8_signal_merge m where i.signal_id=m.old_id and exists(select 1 from public.signal_indicators k where k.signal_id=m.keep_id and k.strategy_name=i.strategy_name);
  update public.signal_indicators t set signal_id=m.keep_id from rc8_signal_merge m where t.signal_id=m.old_id;
  delete from public.research_shadow_live_v1 h using rc8_signal_merge m where h.signal_id=m.old_id and exists(select 1 from public.research_shadow_live_v1 k where k.signal_id=m.keep_id and k.candidate_key=h.candidate_key);
  update public.research_shadow_live_v1 t set signal_id=m.keep_id from rc8_signal_merge m where t.signal_id=m.old_id;
  delete from public.signals s using rc8_signal_merge m where s.id=m.old_id;
end $$;
create unique index if not exists uq_signals_market_candle_action_v1 on public.signals(symbol,timeframe,candle_timestamp,action_normalized,system_type) where candle_timestamp is not null;

-- The GC function was installed during the IO incident. Keep its schedule enforced here.
do $$ declare j bigint; begin
  if to_regprocedure('maintenance.gc_smartradingreview_v1()') is not null then
    for j in select jobid from cron.job where jobname='smartradingreview-db-gc-v1' loop perform cron.unschedule(j); end loop;
    perform cron.schedule('smartradingreview-db-gc-v1','*/15 * * * *','select maintenance.gc_smartradingreview_v1();');
  end if;
end $$;
