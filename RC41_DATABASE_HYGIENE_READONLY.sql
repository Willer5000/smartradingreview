-- FINAL V1 RC4.1 · DATABASE HYGIENE AUDIT (READ ONLY)
-- Ejecutar en Supabase SQL Editor SOLO para diagnóstico.
-- No contiene DELETE, UPDATE, TRUNCATE ni ALTER.

-- 1) Inventario general por mercado / TF / estado.
select
  coalesce(system_type, 'SIN_MERCADO') as system_type,
  coalesce(timeframe, 'SIN_TF') as timeframe,
  coalesce(status, 'SIN_ESTADO') as status,
  count(*) as filas,
  min(created_at) as primera,
  max(created_at) as ultima
from signals
group by 1,2,3
order by 1,2,3;

-- 2) Temporalidades retiradas 5m/15m. Deben quedar como histórico/Research,
-- nunca como cohorte operativa RC4.1.
select system_type, timeframe, status, count(*) as filas
from signals
where lower(coalesce(timeframe,'')) in ('5m','15m')
group by 1,2,3
order by filas desc;

-- 3) Celdas Spot activas RC4.1.
select symbol, timeframe, status, count(*) as filas
from signals
where lower(coalesce(system_type,''))='spot'
  and upper(replace(symbol,'/','-')) in ('BTC-USDT','PAXG-USDT','PAXG-BTC')
  and timeframe in ('4h','12h','1D','1W')
group by 1,2,3
order by 1,2,3;

-- 4) Celdas Futures activas RC4.1. 12H/1D sólo BTC/ETH/SOL.
select symbol, timeframe, status, count(*) as filas
from signals
where lower(coalesce(system_type,''))='futures'
  and (
    (upper(replace(symbol,'/','-')) in ('BTC-USDT','ETH-USDT','SOL-USDT','XRP-USDT','ADA-USDT','LINK-USDT','BNB-USDT')
     and timeframe in ('30m','1h','2h','4h'))
    or
    (upper(replace(symbol,'/','-')) in ('BTC-USDT','ETH-USDT','SOL-USDT')
     and timeframe in ('12h','1D'))
  )
group by 1,2,3
order by 1,2,3;

-- 5) Procedencia de aprendizaje. Sirve para detectar filas pre-auditoría.
select
  lower(coalesce(system_type,'')) as market,
  coalesce(context->'learning'->>'cohort','SIN_COHORT') as learning_cohort,
  coalesce(context->'learning'->>'market_data_source','SIN_SOURCE') as market_data_source,
  coalesce(context->'learning'->>'evaluation_role','SIN_ROLE') as evaluation_role,
  count(*) as filas
from signals
group by 1,2,3,4
order by filas desc;

-- 6) Filas con procedencia incompleta: NO borrar; revisar/cuarentenar.
select id, symbol, timeframe, system_type, status, created_at
from signals
where context is null
   or context->'learning' is null
   or coalesce(context->'learning'->>'market_data_source','')=''
order by created_at desc
limit 500;

-- 7) Posibles duplicados lógicos. Es sólo una lista de candidatos para revisión.
-- No eliminar sin comprobar señal fuente/candle timestamp/usuario.
select
  symbol,
  timeframe,
  coalesce(action_normalized,'SIN_ACCION') as action_normalized,
  coalesce(context->'learning'->>'source_candle_timestamp','SIN_CANDLE') as source_candle,
  count(*) as repeticiones,
  min(created_at) as primera,
  max(created_at) as ultima
from signals
group by 1,2,3,4
having count(*) > 1
order by repeticiones desc
limit 500;

-- 8) Resultados resueltos históricos. Deben preservarse: son evidencia de TP/SL.
select system_type, timeframe, status, count(*) as filas
from signals
where lower(coalesce(status,'')) in ('tp_hit','sl_hit','expired')
group by 1,2,3
order by 1,2,3;

-- 9) ReviewTrader / AI Control: sólo inventario de telemetría, si existen tablas.
select context_type, market, count(*) as eventos, max(updated_at) as ultimo
from ai_control_events
group by 1,2
order by ultimo desc;

-- DECISIÓN RC4.1:
-- NO EJECUTAR BORRADOS AUTOMÁTICOS. El runtime ahora sólo audita candidatos TTL.
-- Cualquier limpieza física futura debe partir de este inventario + backup,
-- y nunca eliminar TP/SL/expired necesarios para evaluar rentabilidad.
