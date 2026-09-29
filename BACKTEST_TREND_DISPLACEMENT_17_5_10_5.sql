-- Backtest reproducible de la hipótesis TREND_DISPLACEMENT_CONTINUATION
-- No escribe ni modifica datos.
with sig as (
 select s.id,s.created_at,s.symbol,lower(s.timeframe) tf,upper(s.action_normalized) action,
        s.risk_reward,r.status,r.entry_timestamp,r.gross_r,r.mfe_r,r.mae_r,
        s.context->'learning'->'trader_intelligence_v2'->'theses' as theses
 from public.signals s
 join public.signal_results r on r.signal_id=s.id
 where s.system_type='futures'
   and upper(s.action_normalized) in ('LONG','SHORT')
   and s.entry_price>0 and s.stop_loss>0 and s.take_profit>0
), setup as (
 select *,
   case
     when status='tp_hit' then greatest(coalesce(gross_r,risk_reward,0),0)-0.118
     when status='sl_hit' then -1.118
     when entry_timestamp is not null
      and status in ('expired','ambiguous','invalid_setup','expired_after_entry')
       then -1.118
     else null
   end stress_r
 from sig
 where tf='30m'
   and exists (
     select 1
     from jsonb_array_elements(coalesce(theses,'[]'::jsonb)) t,
          jsonb_array_elements_text(coalesce(t->'setups','[]'::jsonb)) x
     where t->>'direction'=action and x ilike 'BAND_WALK_%'
   )
   and exists (
     select 1
     from jsonb_array_elements(coalesce(theses,'[]'::jsonb)) t,
          jsonb_array_elements_text(coalesce(t->'setups','[]'::jsonb)) x
     where t->>'direction'=action and x ilike 'ALINEACION_%_COMPLETA'
   )
), res as (
 select * from setup where stress_r is not null
), cutoff as (
 select percentile_disc(0.7) within group(order by created_at) cut from res
)
select
 case when created_at < (select cut from cutoff) then 'IS' else 'OOS' end split,
 count(*) n,
 count(*) filter(where status='tp_hit') tp,
 avg(stress_r) expectancy_r,
 sum(stress_r) net_r,
 sum(greatest(stress_r,0))/nullif(abs(sum(least(stress_r,0))),0) profit_factor,
 avg(mfe_r) avg_mfe_r,
 avg(mae_r) avg_mae_r
from res
group by 1
order by 1;
