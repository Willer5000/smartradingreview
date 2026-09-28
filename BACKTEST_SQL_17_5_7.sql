-- Commit 17.5.7 — consultas READ-ONLY usadas para la auditoría económica.
-- No ejecutar INSERT/UPDATE/DELETE. Reemplazar únicamente el proyecto/entorno,
-- nunca los filtros de la cohorte si se quiere comparar con este informe.

-- 1) Estados históricos
select status, count(*) n
from public.signal_results
group by status
order by n desc;

-- 2) Cohorte limpia por mercado, usando sólo geometría válida y TF activos.
with x as (
  select s.system_type, lower(s.timeframe) tf, s.symbol,
         s.risk_reward::float8 rr, s.leverage,
         r.status, r.modeled_net_r::float8 netr,
         r.mfe_r::float8 mfe_r, r.mae_r::float8 mae_r
  from public.signals s
  join public.signal_results r on r.signal_id=s.id
  where s.entry_price>0 and s.stop_loss>0 and s.take_profit>0
    and s.risk_reward between 1 and 6
    and (
      (s.system_type='futures' and lower(s.timeframe) in ('30m','1h','2h','4h','12h','1d'))
      or
      (s.system_type='spot' and lower(s.timeframe) in ('4h','12h','1d','1w'))
    )
)
select system_type,
       count(*) filter(where status in ('tp_hit','sl_hit')) resolved,
       count(*) filter(where status='tp_hit') tp,
       count(*) filter(where status='sl_hit') sl,
       100.0*count(*) filter(where status='tp_hit')/
         nullif(count(*) filter(where status in ('tp_hit','sl_hit')),0) wr_pct,
       avg(case when status='tp_hit' then rr when status='sl_hit' then -1 end)
         filter(where status in ('tp_hit','sl_hit')) expectancy_r_proxy,
       sum(case when status='tp_hit' then rr else 0 end)/
         nullif(count(*) filter(where status='sl_hit'),0) profit_factor_proxy,
       avg(netr) filter(where status in ('tp_hit','sl_hit') and netr is not null) avg_modeled_net_r,
       count(*) filter(where status='expired') expired,
       avg(mfe_r) filter(where status in ('tp_hit','sl_hit')) avg_mfe_r,
       avg(mae_r) filter(where status in ('tp_hit','sl_hit')) avg_mae_r
from x
group by system_type;

-- 3) Forensics post-SL
select s.system_type,
       count(*) filter(where r.status='sl_hit') sl_hits,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->'post_stop_recovery'->>'reclaimed_entry')::boolean,false)) reclaimed_entry_after_stop,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->'post_stop_recovery'->>'tp_reached_after_stop')::boolean,false)) tp_after_stop,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->>'stop_was_possibly_tight')::boolean,false)) possibly_tight,
       count(*) filter(where r.status='sl_hit' and coalesce((r.execution_forensics->>'false_invalidation_to_target')::boolean,false)) false_invalidation_to_target
from public.signals s
join public.signal_results r on r.signal_id=s.id
where jsonb_typeof(r.execution_forensics)='object'
group by s.system_type;

-- 4) Contrafactuales de ejecución guardados históricamente
with base as (
  select lower(s.timeframe) tf,s.symbol,s.system_type,r.execution_forensics
  from public.signals s
  join public.signal_results r on r.signal_id=s.id
  where s.system_type='futures'
    and jsonb_typeof(r.execution_forensics->'execution_challenger_results'->'results')='array'
), c as (
  select b.tf,b.symbol,x->>'name' challenger,x->>'status' status,
         nullif(x->>'realized_r','')::float8 realized_r,
         coalesce((x->>'entry_reached')::boolean,false) entry_reached
  from base b
  cross join lateral jsonb_array_elements(b.execution_forensics->'execution_challenger_results'->'results') x
)
select tf,challenger,count(*) observations,
       count(*) filter(where entry_reached) entries,
       count(*) filter(where status='tp_hit') tp,
       count(*) filter(where status='sl_hit') sl,
       count(*) filter(where status like 'expired%') expired,
       100.0*count(*) filter(where status='tp_hit')/
         nullif(count(*) filter(where status in ('tp_hit','sl_hit')),0) wr_resolved_pct,
       avg(realized_r) filter(where realized_r is not null) avg_realized_r
from c
group by tf,challenger
order by tf,challenger;
