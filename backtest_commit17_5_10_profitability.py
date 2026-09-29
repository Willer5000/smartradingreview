from __future__ import annotations
import csv, json, random
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
COST_R=0.118
SEED=17510
BOOTSTRAP_ITERATIONS=100000


def load_rows():
    with open(ROOT/'BACKTEST_ROWS_17_5_10_PROFITABILITY.csv',encoding='utf-8') as f:
        return list(csv.DictReader(f))


def metrics(rows):
    vals=[float(r['stress_net_r']) for r in rows]
    wins=sum(max(v,0) for v in vals)
    losses=abs(sum(min(v,0) for v in vals))
    cum=0.0; peak=0.0; maxdd=0.0
    for v in vals:
        cum+=v; peak=max(peak,cum); maxdd=max(maxdd,peak-cum)
    return {
        'n':len(rows),
        'tp':sum(r['status']=='tp_hit' for r in rows),
        'sl':sum(r['status']=='sl_hit' for r in rows),
        'expired_after_entry':sum(r['status']=='expired_after_entry' for r in rows),
        'other_unresolved':sum(r['status'] not in {'tp_hit','sl_hit','expired_after_entry'} for r in rows),
        'net_stress_r':round(sum(vals),3),
        'expectancy_stress_r':round(sum(vals)/len(vals),4) if vals else 0.0,
        'profit_factor_stress':round(wins/losses,3) if losses else None,
        'max_drawdown_r':round(maxdd,3),
        'conservative_tp_rate_pct':round(100*sum(r['status']=='tp_hit' for r in rows)/len(rows),2) if rows else 0.0,
    }


def bootstrap_mean(vals, iterations=BOOTSTRAP_ITERATIONS, seed=SEED):
    rnd=random.Random(seed)
    n=len(vals)
    means=[]
    if not vals:
        return {'iterations':0,'probability_mean_gt_zero':0.0,'ci95':[0.0,0.0]}
    for _ in range(iterations):
        means.append(sum(vals[rnd.randrange(n)] for __ in range(n))/n)
    means.sort()
    lo=means[int(0.025*(iterations-1))]
    hi=means[int(0.975*(iterations-1))]
    p=sum(m>0 for m in means)/iterations
    return {
        'iterations':iterations,
        'seed':seed,
        'probability_mean_gt_zero':round(p,4),
        'ci95_mean_r':[round(lo,4),round(hi,4)],
        'interpretation':'CI95_INCLUDES_ZERO_SMALL_SAMPLE' if lo <= 0 <= hi else 'CI95_EXCLUDES_ZERO',
    }


def daily_folds(rows):
    groups=defaultdict(list)
    for r in rows:
        groups[r['created_at'][:10]].append(r)
    return {d:metrics(rs) for d,rs in sorted(groups.items())}


def main():
    rows=load_rows()
    insample=[r for r in rows if r['period']=='DEV']
    oos=[r for r in rows if r['period']=='HOLDOUT']
    out={
        'IN_SAMPLE_DEVELOPMENT':metrics(insample),
        'OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT':metrics(oos),
        'COMBINED':metrics(rows),
        'DAILY_FOLDS':daily_folds(rows),
        'BOOTSTRAP_COMBINED':bootstrap_mean([float(r['stress_net_r']) for r in rows]),
        'method':{
            'route':'LIQUIDITY_SWEEP_MSS_POI','timeframe':'30m','market':'FUTURES',
            'trend_aligned':True,'adx_min':20,'volume_ratio_min':1.2,
            'rsi_long_max':80,'rsi_short_min':20,
            'unresolved_treatment':'-1R','cost_stress_r_per_entry':COST_R,
            'development_period':'2026-09-10..2026-09-13',
            'holdout_period':'2026-09-14..2026-09-16',
            'oos_type':'CHRONOLOGICAL_HOLDOUT_NOT_PROSPECTIVE_LIVE',
            'limitations':["small N", "historical challenger cohort predates 17.5.10", "not a full version-matched replay"],
        },
        'release_acceptance':{
            'in_sample_profitable':metrics(insample)['net_stress_r']>0 and (metrics(insample)['profit_factor_stress'] or 0)>1,
            'oos_profitable':metrics(oos)['net_stress_r']>0 and (metrics(oos)['profit_factor_stress'] or 0)>1,
            'backtest_acceptance_pass':False,
            'profitability_guarantee':False,
        }
    }
    out['release_acceptance']['backtest_acceptance_pass']=bool(
        out['release_acceptance']['in_sample_profitable'] and out['release_acceptance']['oos_profitable']
    )
    print(json.dumps(out,indent=2))
    assert out['release_acceptance']['backtest_acceptance_pass']
    assert out['IN_SAMPLE_DEVELOPMENT']['net_stress_r'] > 0
    assert out['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['net_stress_r'] > 0
    assert out['OUT_OF_SAMPLE_CHRONOLOGICAL_HOLDOUT']['profit_factor_stress'] > 1

if __name__=='__main__': main()
