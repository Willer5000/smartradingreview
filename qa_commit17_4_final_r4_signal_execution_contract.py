from pathlib import Path
import ast
from execution_specialist_committees import coordinate_execution_committees, VERSION

checks=[]
def ck(label, cond):
    checks.append((label,bool(cond))); print(('OK   ' if cond else 'FAIL ')+label)

ck('execution committee version is R4 contract', 'R4_SIGNAL_EXECUTION_CONTRACT' in VERSION)

cases=[
 ('long','futures','BTC-USDT','1h'),('short','futures','LINK-USDT','1h'),
 ('long','multiasset','CL-USDT','4h'),('short','multiasset','QQQ-USDT','1D'),
 ('long','spot','BTC-USDT','4h'),('short','spot','PAXG-USDT','4h'),
]
for direction,market,symbol,tf in cases:
    c=coordinate_execution_committees(
        baseline_entry=0,baseline_sl=0,baseline_tp=0,direction=direction,
        current_price=100,atr=2.0,structure={},trend={'direction':direction},momentum={'direction':direction},volatility={},
        setup_family='MOMENTUM_CONTINUATION',market_type=market,symbol=symbol,timeframe=tf,
        execution_context={'activity_score':60,'shock_score':20,'timeframe':tf},
        rr_floor=1.5,rr_ceiling=4.5,preferred_rr_min=2.0,preferred_rr_max=3.2,leverage_hint=10,
    )
    geo=(c.get('stop_loss',0)<c.get('entry',0)<c.get('take_profit',0)) if direction=='long' else (c.get('take_profit',0)<c.get('entry',0)<c.get('stop_loss',0))
    ck(f'{market} {direction} zero-baseline recovers geometry', c.get('success') is True and geo)
    ck(f'{market} {direction} RR stays technical', 1.5 <= float(c.get('risk_reward') or 0) <= 4.5)

app=Path('app.py').read_text()
ck('confirmed calculation emits no normal pending state', "'execution_ready': True" in app and "'publication_status': 'EXECUTABLE_SIGNAL'" in app)
ck('anti-FOMO remains advisory', "levels['anti_fomo_advisory']" in app)
ck('legacy setup guard remains advisory', "levels['execution_advisories']" in app)
ck('committee score only backfills missing legacy score', 'if float(entry_score or 0) <= 0' in app and 'if float(sl_score or 0) <= 0' in app and 'if float(tp_score or 0) <= 0' in app)

exec_text=Path('execution_specialist_committees.py').read_text()
for token in ('requests.','httpx','supabase','groq','openai'):
    ck(f'no added I/O dependency {token}', token not in exec_text.lower())

bad=[x for x,v in checks if not v]
print(f'PASS {len(checks)-len(bad)}/{len(checks)}')
if bad:
    print('FAILED',bad); raise SystemExit(1)
