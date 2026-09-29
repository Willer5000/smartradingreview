-- Commit 17.5.10 — consultas READ ONLY de aceptación rentable.

-- 1) Coste histórico 30m usado como stress por entrada.
select lower(s.timeframe) tf,
       percentile_cont(0.5) within group(order by r.modeled_fee_slippage_cost_r::float8) median_cost_r,
       percentile_cont(0.75) within group(order by r.modeled_fee_slippage_cost_r::float8) p75_cost_r,
       avg(r.modeled_fee_slippage_cost_r::float8) avg_cost_r,
       count(*) n
from public.signals s join public.signal_results r on r.signal_id=s.id
where s.system_type='futures' and lower(s.timeframe)='30m'
  and r.modeled_fee_slippage_cost_r is not null
group by 1;

-- 2) Cohorte congelada y filas reproducibles.
with base as (
  select s.id::text signal_id,s.created_at,s.symbol,s.action_normalized,
         nullif(s.indicators_snapshot->>'adx','')::float8 adx,
         nullif(s.indicators_snapshot->>'volume_ratio','')::float8 volume_ratio,
         nullif(s.indicators_snapshot->>'rsi','')::float8 rsi,
         lower(coalesce(s.indicators_snapshot->>'trend_direction','')) trend_dir,
         r.execution_forensics
  from public.signals s join public.signal_results r on r.signal_id=s.id
  where s.system_type='futures' and lower(s.timeframe)='30m'
    and jsonb_typeof(r.execution_forensics->'execution_challenger_results'->'results')='array'
), c as (
 select b.*,
        x->>'status' status,
        nullif(x->>'realized_r','')::float8 realized_r,
        coalesce((x->>'entry_reached')::boolean,false) entry_reached,
        nullif(x->>'risk_reward','')::float8 rr,
        nullif(x->>'candles_to_entry','')::int candles_to_entry,
        nullif(x->>'candles_after_entry','')::int candles_after_entry,
        nullif(x->>'mfe_r','')::float8 mfe_r,
        nullif(x->>'mae_r','')::float8 mae_r
 from base b cross join lateral jsonb_array_elements(
      b.execution_forensics->'execution_challenger_results'->'results') x
 where x->>'name'='LIQUIDITY_SWEEP_MSS_POI'
)
select *,
       case when created_at < '2026-09-14' then 'DEV' else 'HOLDOUT' end period,
       coalesce(realized_r,-1.0)-0.118 as stress_net_r
from c
where entry_reached
  and adx>=20
  and volume_ratio>=1.20
  and ((action_normalized='LONG' and trend_dir='bullish' and rsi<=80)
    or (action_normalized='SHORT' and trend_dir='bearish' and rsi>=20))
order by created_at,symbol;

-- 3) Métricas DEV/HOLDOUT con unresolved=-1R y coste 0.118R/entrada.
with base as (
  select s.created_at,s.symbol,s.action_normalized,
         nullif(s.indicators_snapshot->>'adx','')::float8 adx,
         nullif(s.indicators_snapshot->>'volume_ratio','')::float8 volume_ratio,
         nullif(s.indicators_snapshot->>'rsi','')::float8 rsi,
         lower(coalesce(s.indicators_snapshot->>'trend_direction','')) trend_dir,
         r.execution_forensics
  from public.signals s join public.signal_results r on r.signal_id=s.id
  where s.system_type='futures' and lower(s.timeframe)='30m'
    and jsonb_typeof(r.execution_forensics->'execution_challenger_results'->'results')='array'
), c as (
 select b.*, x->>'status' status,
        nullif(x->>'realized_r','')::float8 realized_r,
        coalesce((x->>'entry_reached')::boolean,false) entry_reached
 from base b cross join lateral jsonb_array_elements(
      b.execution_forensics->'execution_challenger_results'->'results') x
 where x->>'name'='LIQUIDITY_SWEEP_MSS_POI'
), f as (
 select *,case when created_at<'2026-09-14' then 'DEV' else 'HOLDOUT' end period,
        coalesce(realized_r,-1.0)-0.118 as stress_r
 from c
 where entry_reached and adx>=20 and volume_ratio>=1.20
   and ((action_normalized='LONG' and trend_dir='bullish' and rsi<=80)
     or (action_normalized='SHORT' and trend_dir='bearish' and rsi>=20))
), curve as (
 select *,sum(stress_r) over(partition by period order by created_at,symbol) cum_r
 from f
), dd as (
 select *,max(cum_r) over(partition by period order by created_at,symbol) peak_r
 from curve
)
select period,count(*) n,
       count(*) filter(where status='tp_hit') tp,
       count(*) filter(where status='sl_hit') sl,
       count(*) filter(where status='expired_after_entry') expired_after_entry,
       count(*) filter(where status not in ('tp_hit','sl_hit','expired_after_entry')) other_unresolved,
       sum(stress_r) net_stress_r,
       sum(greatest(stress_r,0))/nullif(abs(sum(least(stress_r,0))),0) pf_stress,
       max(peak_r-cum_r) max_drawdown_r
from dd group by period order by period;

-- 4) Pequeña vecindad de estabilidad. No usar para elegir el máximo; sirve
--    para comprobar que el punto 20/1.2/80 no es una aguja aislada.
with params(adx_min,vol_min,rsi_cap) as (values
 (20.0,1.0,80.0),(20.0,1.2,80.0),(25.0,1.0,75.0),
 (25.0,1.2,75.0),(25.0,1.4,75.0),(30.0,1.0,70.0),(30.0,1.2,70.0)
)
select * from params;
-- Ejecutar los params sobre el CTE c anterior aplicando el mismo stress.
