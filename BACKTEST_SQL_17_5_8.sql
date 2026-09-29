-- Commit 17.5.8 — reproducible evidence queries (Supabase/PostgreSQL)

-- A) Positive family cells eligible for preliminary prior
select system_type,cell_key,strategy_family,direction,oos_n,
       round(oos_expectancy_r::numeric,4) exp_r,
       round(oos_profit_factor::numeric,3) pf,
       round(oos_max_drawdown_r::numeric,3) maxdd
from public.research_candidate_memory_v1
where system_type in ('FUTURES','SPOT')
  and oos_n>=10
  and oos_expectancy_r>=0.12
  and oos_profit_factor>=1.25
  and oos_max_drawdown_r<=6
order by system_type, oos_expectancy_r desc, oos_n desc;

-- B) Entry challenger study
with base as (
  select lower(s.timeframe) tf,s.symbol,s.system_type,r.execution_forensics
  from public.signals s join public.signal_results r on r.signal_id=s.id
  where s.system_type='futures'
    and lower(s.timeframe) in ('30m','1h','2h','4h')
    and jsonb_typeof(r.execution_forensics->'execution_challenger_results'->'results')='array'
), c as (
 select b.tf,b.symbol,x->>'name' challenger,x->>'status' status,
        nullif(x->>'realized_r','')::float8 realized_r,
        coalesce((x->>'entry_reached')::boolean,false) entry_reached
 from base b cross join lateral jsonb_array_elements(b.execution_forensics->'execution_challenger_results'->'results') x
 where x->>'name' in ('BASELINE','LIQUIDITY_SWEEP_MSS_POI','SPECIALIST_COMMITTEE','MICROSTRUCTURE_CONFIRMED_ENTRY','DEFENSIBILITY')
)
select tf,challenger,count(*) obs,count(*) filter(where entry_reached) entries,
       count(*) filter(where status='tp_hit') tp,
       count(*) filter(where status='sl_hit') sl,
       round(100.0*count(*) filter(where status='tp_hit')/nullif(count(*) filter(where status in ('tp_hit','sl_hit')),0),2) wr,
       round(avg(realized_r) filter(where realized_r is not null)::numeric,3) exp_r,
       round((sum(greatest(realized_r,0)) filter(where realized_r is not null)/
             nullif(abs(sum(least(realized_r,0)) filter(where realized_r is not null)),0))::numeric,3) pf
from c group by 1,2 having count(*)>=8 order by tf,challenger;

-- C) TP compression sweep, same historical Entry/SL
with x as (
 select lower(s.timeframe) tf,s.risk_reward::float8 rr,r.status,
        coalesce(nullif(r.execution_forensics->>'target_progress_ratio','')::float8,
                 r.mfe_r::float8/nullif(s.risk_reward::float8,0)) progress
 from public.signals s join public.signal_results r on r.signal_id=s.id
 where s.system_type='futures'
   and lower(s.timeframe) in ('30m','1h','2h','4h')
   and r.status in ('tp_hit','sl_hit')
   and s.risk_reward between 1.8 and 3.5
), levels(mult) as (values (0.50::float8),(0.60),(0.70),(0.80),(0.90),(1.00))
select tf,mult,count(*) n,
       count(*) filter(where progress>=mult or status='tp_hit') wins,
       round(100.0*count(*) filter(where progress>=mult or status='tp_hit')/count(*),2) hit_pct,
       round(avg(case when progress>=mult or status='tp_hit' then rr*mult else -1 end)::numeric,3) exp_r,
       round((sum(case when progress>=mult or status='tp_hit' then rr*mult else 0 end)/
              nullif(count(*) filter(where not(progress>=mult or status='tp_hit')),0))::numeric,3) pf_proxy
from x cross join levels group by tf,mult order by tf,mult;

-- D) SL false-invalidation / recovery forensics
select lower(s.timeframe) tf,
       count(*) filter(where r.status='sl_hit') sl_hits,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->>'wick_out')::boolean,false)) wick_out,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->'post_stop_recovery'->>'reclaimed_entry')::boolean,false)) reclaimed,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->'post_stop_recovery'->>'tp_reached_after_stop')::boolean,false)) tp_after_stop,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->>'stop_was_possibly_tight')::boolean,false)) possibly_tight,
       round(avg(r.mfe_r::float8) filter(where r.status='sl_hit')::numeric,3) avg_mfe_before_sl
from public.signals s join public.signal_results r on r.signal_id=s.id
where s.system_type='futures' and lower(s.timeframe) in ('30m','1h','2h','4h')
group by 1 order by 1;
