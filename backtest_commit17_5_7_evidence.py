"""Commit 17.5.7 research-only backtest helper.

This script never changes production state. It can:
  1) validate/print the frozen aggregate snapshot shipped with the commit; and
  2) replay the Multi-Asset proxy when a local prices_ohlc.csv from
     vivek-v-rao/OHLC-Vol is supplied.

The Multi-Asset mode is deliberately a proxy, not the production engine.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / 'BACKTEST_DATA_SNAPSHOT_20260928.json'


def print_snapshot():
    data = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    print(json.dumps({
        'clean_logged_backtest': data['clean_logged_backtest'],
        'stop_forensics': data['stop_forensics'],
        'expiry_forensics': data['expiry_forensics'],
        'multiasset_proxy': data['multiasset_proxy'],
    }, indent=2, ensure_ascii=False))


def load_multiasset_csv(path: Path):
    with path.open(newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.reader(fh))
    symbols, fields = rows[0], rows[1]
    columns = {}
    for i in range(1, len(symbols)):
        columns.setdefault(symbols[i].strip(), {})[fields[i].strip()] = i
    out = {s: [] for s in ('SPY','QQQ','USO','GLD') if s in columns}
    for row in rows[3:]:
        if not row:
            continue
        date = row[0]
        if not ('2022-01-01' <= date <= '2026-04-15'):
            continue
        for sym in out:
            m = columns[sym]
            try:
                o,h,l,c = (float(row[m[k]]) for k in ('Open','High','Low','Close'))
            except (ValueError, IndexError, KeyError):
                continue
            if o>0 and h>=max(o,c) and l<=min(o,c):
                out[sym].append({'date':date,'o':o,'h':h,'l':l,'c':c})
    return out


def atr14(a, i):
    if i < 14:
        return None
    trs=[]
    for k in range(i-13, i+1):
        prev=a[k-1]['c']
        trs.append(max(a[k]['h']-a[k]['l'], abs(a[k]['h']-prev), abs(a[k]['l']-prev)))
    return mean(trs)


def pivots(a):
    hi=[]; lo=[]
    for i in range(5, len(a)-5):
        if all(a[k]['h'] < a[i]['h'] for k in range(i-5,i+6) if k != i): hi.append(i)
        if all(a[k]['l'] > a[i]['l'] for k in range(i-5,i+6) if k != i): lo.append(i)
    return hi,lo


def replay_symbol(a):
    highs,lows=pivots(a); trades=[]; last_signal=-99
    for i in range(65, len(a)-13):
        if i-last_signal < 2: continue
        hp=[p for p in highs if i-60 <= p <= i-5]
        lp=[p for p in lows if i-60 <= p <= i-5]
        if not hp or not lp: continue
        ph,pl=hp[-1],lp[-1]; b=a[i]; prev=a[i-1]
        bull=(b['l']<a[pl]['l'] and b['c']>a[pl]['l']) or (b['c']>a[ph]['h'] and prev['c']<=a[ph]['h'])
        bear=(b['h']>a[ph]['h'] and b['c']<a[ph]['h']) or (b['c']<a[pl]['l'] and prev['c']>=a[pl]['l'])
        if bull == bear: continue
        direction='LONG' if bull else 'SHORT'; entry=a[i+1]['o']; atr=atr14(a,i)
        if not atr: continue
        if direction=='LONG':
            anchors=[a[p]['l'] for p in lp if a[p]['l']<entry]
            targets=sorted(a[p]['h'] for p in hp if a[p]['h']>entry)
            if not anchors or not targets: continue
            sl=max(anchors)-0.20*atr; tp=targets[0]
        else:
            anchors=[a[p]['h'] for p in hp if a[p]['h']>entry]
            targets=sorted((a[p]['l'] for p in lp if a[p]['l']<entry), reverse=True)
            if not anchors or not targets: continue
            sl=min(anchors)+0.20*atr; tp=targets[0]
        risk=abs(entry-sl); rr=abs(tp-entry)/risk if risk>0 else 0
        if not 1.8 <= rr <= 4.5: continue
        outcome='EXPIRED'; r=0.0
        for j in range(i+1, min(len(a), i+13)):
            q=a[j]
            hit_tp=q['h']>=tp if direction=='LONG' else q['l']<=tp
            hit_sl=q['l']<=sl if direction=='LONG' else q['h']>=sl
            if hit_tp and hit_sl: outcome='AMBIGUOUS'; break
            if hit_tp: outcome='TP'; r=rr; break
            if hit_sl: outcome='SL'; r=-1.0; break
        trades.append({'date':a[i+1]['date'],'outcome':outcome,'r':r,'rr':rr})
        last_signal=i
    return trades


def summarize(trades):
    res=[t for t in trades if t['outcome'] in ('TP','SL')]
    tp=sum(t['outcome']=='TP' for t in res); sl=sum(t['outcome']=='SL' for t in res)
    gains=sum(max(0,t['r']) for t in res); losses=-sum(min(0,t['r']) for t in res)
    return {
        'signals': len(trades), 'resolved': len(res), 'tp': tp, 'sl': sl,
        'expired': sum(t['outcome']=='EXPIRED' for t in trades),
        'ambiguous': sum(t['outcome']=='AMBIGUOUS' for t in trades),
        'wr_pct': round(100*tp/len(res),2) if res else None,
        'expectancy_r': round(mean([t['r'] for t in res]),4) if res else None,
        'profit_factor': round(gains/losses,3) if losses else None,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--multiasset-csv', type=Path, help='local prices_ohlc.csv')
    args=ap.parse_args()
    if not args.multiasset_csv:
        print_snapshot(); return
    data=load_multiasset_csv(args.multiasset_csv)
    result={s:summarize(replay_symbol(a)) for s,a in data.items()}
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__ == '__main__':
    main()
