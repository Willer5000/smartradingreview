-- RC8.2 · Contingency + storage compaction
-- 1) signal_indicators keeps only the N:M signal↔strategy relation.
--    The indicator snapshot already exists once on signals.indicators_snapshot.
-- 2) missed_opportunities is physically rewritten without changing its rows,
--    reclaiming dead pages left by earlier churn.

begin;

create temporary table rc82_signal_indicators_keep on commit drop as
select distinct on (signal_id, strategy_name)
       id, signal_id, strategy_name, null::jsonb as indicator_values, created_at
from public.signal_indicators
order by signal_id, strategy_name, created_at desc, id;

truncate table public.signal_indicators;
insert into public.signal_indicators(id,signal_id,strategy_name,indicator_values,created_at)
select id,signal_id,strategy_name,indicator_values,created_at
from rc82_signal_indicators_keep;

create unique index if not exists uq_signal_indicators_signal_strategy_v1
  on public.signal_indicators(signal_id,strategy_name);

-- Reclaim physical bloat while preserving every current missed-opportunity row.
create temporary table rc82_missed_opportunities_keep on commit drop as
select * from public.missed_opportunities;
truncate table public.missed_opportunities;
insert into public.missed_opportunities select * from rc82_missed_opportunities_keep;

commit;
