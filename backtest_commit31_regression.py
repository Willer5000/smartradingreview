from pathlib import Path
import csv, json
from safety_profiles_commit31 import audit

ROOT=Path(__file__).resolve().parent
csv_path=ROOT/'BACKTEST_ROWS_17_5_10_PROFITABILITY.csv'
rows=[]
if csv_path.exists():
    with csv_path.open(encoding='utf-8') as f:
        rows=list(csv.DictReader(f))

def stats(period=None):
    rr=[float(r['stress_net_r']) for r in rows if (period is None or r.get('period')==period)]
    return {'n':len(rr),'net_stress_r':round(sum(rr),3),'expectancy_r':round(sum(rr)/len(rr),5) if rr else None}

out={
    'commit':'COMMIT31_MULTI_SAFETY_AUTHORITY_V1',
    'f30_route_regression':{'DEV':stats('DEV'),'HOLDOUT':stats('HOLDOUT'),'ALL':stats()},
    'safety_architecture':audit(),
    'claim_limits':{
        'route_alpha_reoptimized':False,
        'safety_weights_backtested_on_outcomes':False,
        'reason':'Historical rows do not contain the complete component vector for the 8 specialised Safety profiles.',
    },
}
print(json.dumps(out,indent=2))
