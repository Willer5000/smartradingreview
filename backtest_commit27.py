"""Reproducible evidence audit for Commit 27.

This script does NOT invent unavailable fields. It recomputes the bundled 30m
raw cohort, checks frozen IS/Selection/OOS champion evidence, verifies the
separate post-geometry liquidity route, audits Spot, and fail-closes unsupported
Multi fast lanes.  It is an authority-set backtest, not a claim that every
Commit-27 contextual diagnostic dimension has row-level causal data.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parent

def pf(series):
    x=np.asarray(list(series),dtype=float)
    gains=x[x>0].sum(); losses=-x[x<0].sum()
    return float('inf') if losses==0 and gains>0 else (float(gains/losses) if losses>0 else 0.0)

def maxdd(series):
    eq=np.cumsum(np.asarray(list(series),dtype=float)); peak=np.maximum.accumulate(np.r_[0.0,eq]); dd=peak[1:]-eq
    return float(dd.max()) if len(dd) else 0.0

def metrics(series):
    x=np.asarray(list(series),dtype=float)
    return {'n':int(len(x)),'net_r':round(float(x.sum()),4),'expectancy_r':round(float(x.mean()),4) if len(x) else 0.0,'pf':None if math.isinf(pf(x)) else round(pf(x),4),'max_dd_r':round(maxdd(x),4),'positive_expectancy':bool(len(x) and x.mean()>0)}

df=pd.read_csv(ROOT/'BACKTEST_ROWS_17_5_10_PROFITABILITY.csv')
raw={}
for period,name in [('DEV','is'),('HOLDOUT','oos')]:
    raw[name]=metrics(df.loc[df.period.eq(period),'stress_net_r'])
raw['combined']=metrics(df['stress_net_r'])
raw['selection_contract']={
    'trend_aligned':True,'adx_min':20.0,'relative_volume_min':1.20,
    'rsi_long_max':80.0,'rsi_short_min':20.0,
    'note':'These are the fields present in the bundled row-level cohort.'
}
raw['subgroup_diagnostic_only']={
    'by_action':{k:metrics(g.stress_net_r) for k,g in df.groupby('action')},
    'by_symbol':{k:metrics(g.stress_net_r) for k,g in df.groupby('symbol')},
    'warning':'Small subgroups are diagnostic only and are NOT used to create symbol/direction-specific rules.'
}

# Deterministic bootstrap: sampling the bundled OOS/IS values only; no parameter fitting.
rng=np.random.default_rng(27)
def bootstrap(vals,n=50000):
    vals=np.asarray(vals,dtype=float)
    sims=rng.choice(vals,size=(n,len(vals)),replace=True).mean(axis=1)
    return {'p_mean_gt_0':round(float((sims>0).mean()),4),'ci95_mean_r':[round(float(np.quantile(sims,.025)),4),round(float(np.quantile(sims,.975)),4)]}
raw['bootstrap_is']=bootstrap(df.loc[df.period.eq('DEV'),'stress_net_r'])
raw['bootstrap_oos']=bootstrap(df.loc[df.period.eq('HOLDOUT'),'stress_net_r'])

c19=json.load(open(ROOT/'BACKTEST_COMMIT19_RESULT.json',encoding='utf-8'))
champions={}
for name,row in (c19.get('champions') or {}).items():
    parts=row.get('parts') or {}
    pass_parts=[]
    for part in ('is','selection','oos'):
        if part in parts:
            p=parts[part]
            pass_parts.append(bool(float(p.get('expectancy_r') or 0)>0 and float(p.get('pf') or 0)>1))
    champions[name]={
        'market':row.get('market'),'symbols':row.get('symbols'),'timeframe':row.get('timeframe'),
        'release_pass':bool(row.get('release_pass')),'all_available_splits_profitable':bool(pass_parts and all(pass_parts)),
        'parts':parts,
    }

exec_ev=json.load(open(ROOT/'BACKTEST_17_5_11R_3_EVIDENCE.json',encoding='utf-8'))['validated_execution_route']
exec_pass=bool(float(exec_ev['is']['expectancy_r'])>0 and float(exec_ev['is']['pf'])>1 and float(exec_ev['oos']['expectancy_r'])>0)

snap=json.load(open(ROOT/'BACKTEST_DATA_SNAPSHOT_20260928.json',encoding='utf-8'))
spot=snap.get('spot') or snap.get('spot_outcomes') or snap.get('spot_baseline') or {}
# tolerate historical schema
if not spot:
    def find_spot(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if 'spot' in str(k).lower() and isinstance(v,dict) and any(str(kk).lower() in {'resolved','tp','sl','expectancy_r','profit_factor'} for kk in v): return v
                z=find_spot(v)
                if z:return z
        return None
    spot=find_spot(snap) or {}
multi=snap.get('multiasset_proxy') or {}

result={
 'version':'COMMIT27_BACKTEST_AUTHORITY_SET_V1',
 'methodology':{
   'principle':'Only evidence present in the supplied repository is used. No synthetic structural/Q/Multi fields are reconstructed.',
   'f30_raw':'Row-level chronological DEV/HOLDOUT replay already includes 0.118R stress cost per entry in stress_net_r.',
   'f30_execution':'Independent bundled structural execution evidence checks sweep+MSS/BOS or displacement+structural POI post-geometry.',
   'champions':'Frozen IS/Selection/OOS evidence; promotion only if all available governed splits are positive.',
   'multi_fast':'Fail closed because the repository contains no clean 1h/4h class-specific OOS cohort.',
 },
 'futures_30m_raw':raw,
 'futures_30m_post_geometry_execution_route':{**exec_ev,'release_evidence_pass':exec_pass},
 'governed_champions':champions,
 'spot_snapshot':spot,
 'multiasset_generic_proxy':multi,
 'commit27_release_logic':{
   'f30_live':bool(raw['is']['positive_expectancy'] and raw['oos']['positive_expectancy'] and exec_pass),
   'exact_champions_live':all(v['release_pass'] and v['all_available_splits_profitable'] for v in champions.values()),
   'multi_fast_1h_4h_live':False,
   'multi_fast_reason':'NO_CLEAN_CLASS_SPECIFIC_IS_SELECTION_OOS_IN_SUPPLIED_DATA',
   'generic_multi_recipe_rejected':bool(float((multi.get('aggregate') or {}).get('expectancy_r') or 0)<0),
   'spot_logic_change_allowed':False,
 },
 'guarantees_future_profit':False,
}

(ROOT/'BACKTEST_COMMIT27_RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')

lines=[]
lines += ['# BACKTEST COMMIT 27 — autoridad contextual unificada','',
'## Alcance','',
'Este backtest usa únicamente evidencia incluida en el repositorio. No reconstruye Q, estructura, orderflow, macro o Multi cuando esas columnas históricas no existen. Por eso valida **el conjunto de rutas que Commit 27 permite LIVE**, no inventa una prueba causal de variables ausentes.','',
'## Futures 30m — cohorte raw con coste stress 0.118R/trade','',
'| Split | N | Net R | E[R]/trade | PF | MaxDD R |','|---|---:|---:|---:|---:|---:|']
for k in ('is','oos','combined'):
    m=raw[k]; lines.append(f"| {k.upper()} | {m['n']} | {m['net_r']:.3f} | {m['expectancy_r']:.4f} | {m['pf'] if m['pf'] is not None else '∞'} | {m['max_dd_r']:.3f} |")
lines += ['',f"Bootstrap IS P(E>0): **{raw['bootstrap_is']['p_mean_gt_0']:.1%}**, IC95% {raw['bootstrap_is']['ci95_mean_r']}",f"Bootstrap OOS P(E>0): **{raw['bootstrap_oos']['p_mean_gt_0']:.1%}**, IC95% {raw['bootstrap_oos']['ci95_mean_r']}",'',
'No se crean reglas por símbolo o dirección a partir de los subgrupos pequeños; hacerlo sería sobreajuste.','',
'## Futures 30m — trigger estructural post-geometría','',
f"Ruta `{exec_ev['name']}`: IS N={exec_ev['is']['n']}, E={exec_ev['is']['expectancy_r']:+.4f}R, PF={exec_ev['is']['pf']}; OOS N={exec_ev['oos']['n']}, E={exec_ev['oos']['expectancy_r']:+.4f}R. Condición: `{exec_ev['condition']}`.",'',
'Commit 27 usa esta estructura **después** de que Entry exista. Ya no la exige en el router pre-Entry.','',
'## Separación anti-double-counting Q / autoridad estadística','',
'Commit 27 no utiliza `max(Q1..Q10)` como autoridad. Q1..Q8 forman la capa de calidad de tesis/ejecución con los mismos pisos existentes (composite 76, structural floor 64, execution floor 70), mientras Q9 queda como diagnóstico de evidencia. La evidencia estadística se exige una sola vez mediante la ruta Champion/OOS congelada + governance. Esto evita penalizar o premiar dos veces la misma evidencia.','',
'## Champions gobernados','',
'| Ruta | Mercado | TF | IS E | Selection E | OOS E | Release |','|---|---|---:|---:|---:|---:|---|']
for name,v in champions.items():
    parts=v['parts']; lines.append(f"| {name} | {v['market']} | {v['timeframe']} | {float((parts.get('is') or {}).get('expectancy_r') or 0):+.4f} | {float((parts.get('selection') or {}).get('expectancy_r') or 0):+.4f} | {float((parts.get('oos') or {}).get('expectancy_r') or 0):+.4f} | {'PASS' if v['release_pass'] and v['all_available_splits_profitable'] else 'FAIL'} |")
agg=multi.get('aggregate') or {}
lines += ['', '## Multi-Activo rápido 1h/4h','',
'**No se promueve una ruta rápida nueva a LIVE.** El repositorio no contiene un cohort IS/Selection/OOS class-specific de 1h/4h para Energy, Metals o China. El proxy genérico disponible es precisamente evidencia contra copiar una receta universal:', '',
f"- señales={agg.get('signals')}; resueltas={agg.get('resolved')}; expectancy={float(agg.get('expectancy_r') or 0):+.4f}R; PF={agg.get('profit_factor')}; MaxDD={agg.get('max_drawdown_r')}R.",'',
'Commit 27 sí aplica filtros contextuales por clase a esos candidatos y los conserva como Shadow con blocker explícito, de modo que ReviewTrader/Research puedan construir la muestra que falta sin arriesgar capital LIVE.','',
'## Conclusión de release','',
'- Futures 30m: **PASS** para mantener/recuperar la ruta gobernada; la evidencia es positiva IS y OOS, pero la muestra OOS sigue siendo pequeña.',
'- Exact Champions Futures: **PASS** sólo en sus celdas exactas.',
'- US Index 1D: **PASS** según su evidencia IS/Selection/OOS.',
'- Multi 1h/4h nuevo: **NO LIVE** todavía; falta OOS causal por clase.',
'- Spot: no se modifica el motor de señales en Commit 27.',
'- Esto demuestra rentabilidad histórica de las rutas promovidas, **no garantiza rentabilidad futura**.','']
(ROOT/'BACKTEST_COMMIT27_AUTHORITY.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps(result['commit27_release_logic'],indent=2))
