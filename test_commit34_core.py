"""Offline deterministic contract tests; not a substitute for market-data OOS."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtest_commit34 import replay, universe, resolve_trade
from commit34_family_engine import discover_families, FAMILIES
from commit34_promotion import resolve


def frame(n=100):
    timestamps=pd.date_range('2026-04-01',periods=n,freq='30min',tz='UTC')
    closes=[100.0+i*.018 for i in range(n)]
    opens=[c-0.04 for c in closes]
    return pd.DataFrame({'timestamp':timestamps,'time':timestamps,'open':opens,
            'high':[c+0.22 for c in closes],
            'low':[c-0.22 for c in closes],
            'close':closes,'volume':[100.0]*n})


class Commit34CausalTests(unittest.TestCase):
    def test_coverage_is_exactly_336(self):
        rows=list(universe())
        self.assertEqual(len(rows),336)
        self.assertEqual(len(set(rows)),336)
        self.assertEqual(len(FAMILIES),4)

    def test_no_market_data_no_fake_oos(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=replay(out_dir=tmp)
            self.assertEqual(report['status'],'RESEARCH_INCOMPLETE')
            self.assertEqual(sum(r['live_eligible'] for r in report['rows']),0)
            self.assertTrue(all(r['oos']['n']==0 for r in report['rows']))
            self.assertTrue((Path(tmp)/'COMMIT34_MATRIX.csv').exists())

    def test_families_need_closed_history(self):
        result=discover_families(frame(40),timeframe='30m')
        self.assertEqual(result['candidates'],[])

    def test_macro_requires_causal_timestamp(self):
        df=frame()
        # A clear high-volume bullish release breakout.
        df.loc[df.index[-1],'high']=107.0
        df.loc[df.index[-1],'open']=101.0
        df.loc[df.index[-1],'close']=106.0
        df.loc[df.index[-1],'low']=100.8
        df.loc[df.index[-1],'volume']=500.0
        now=df['timestamp'].iloc[-1]
        later={'last_high_impact_event':{'timestamp':(now+timedelta(minutes=60)).isoformat(),
                  'published_at':(now+timedelta(minutes=60)).isoformat()}}
        result=discover_families(df,timeframe='30m',macro=later)
        self.assertFalse(any(c['family']=='POST_MACRO_CONFIRMATION' for c in result['candidates']))
        earlier={'last_high_impact_event':{'timestamp':(now-timedelta(hours=1)).isoformat(),
                  'published_at':(now-timedelta(hours=1)).isoformat()}}
        result=discover_families(df,timeframe='30m',macro=earlier)
        self.assertTrue(any(c['family']=='POST_MACRO_CONFIRMATION' and c['action']=='LONG'
                            for c in result['candidates']),result)

    def test_no_intrabar_lookahead_and_pessimistic_double_touch(self):
        df=frame(90)
        idx=60; entry=101.1
        df.loc[idx+1,'high']=103
        df.loc[idx+1,'low']=99
        row={'action':'LONG','entry':entry,'stop_loss':100.1,'take_profit':103}
        out,status=resolve_trade(df,idx,row,cost_bps=10)
        self.assertTrue(out<-1.0)
        self.assertEqual(status,'SL_OR_DOUBLE_TOUCH')

    def test_cgroup_pressure_checkpoint_aborts_instead_of_allocating(self):
        # Extract only the native governor from app.py: no Flask imports,
        # no background daemons, and no artificial test deployment.
        import ast, os
        src=(Path(__file__).parent/'app.py').read_text(encoding='utf-8')
        tree=ast.parse(src)
        target=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                    and n.name=='_commit34_guard_stage')
        namespace={'os':os,
            '_commit34_cgroup_mb':lambda:(475.0,512.0),
            '_process_rss_mb':lambda:320.0,
            '_shed_recreatable_memory':lambda *a,**k:{}}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[target],type_ignores=[])),
                     '<resource_governor>','exec'),namespace)
        with self.assertRaisesRegex(RuntimeError,'RESOURCE_PRESSURE_ABORT'):
            namespace['_commit34_guard_stage']('unit-test')
        self.assertFalse(namespace['_commit34_guard_stage']('research',optional=True))
        namespace['_commit34_cgroup_mb']=lambda:(180.0,512.0)
        namespace['_process_rss_mb']=lambda:155.0
        self.assertTrue(namespace['_commit34_guard_stage']('normal'))

    def test_strategy_authority_no_unverified_promotion(self):
        import commit34_promotion
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/'bad_authority.json'
            bad.write_text(json.dumps({'version':'COMMIT34_LIVE_AUTHORITY_V1','authorized_routes':{
                'BTC-USDT|30M|LONG|FAILED_AUCTION_RANGE_ACCEPTANCE':{
                    'status':'VALIDATED_IS_SELECTION_OOS','is':{'n':50,'expectancy_r':.3},
                    'selection':{'n':13,'expectancy_r':.2},
                    'oos':{'n':13,'expectancy_r':.2,'pf':1.5},
                    'geometry_source':'GENERIC_ATR_SL_TP',
                    'walk_forward_pass':True,'data_sha256':'data','code_sha256':'code'}
            }}),encoding='utf-8')
            with patch.object(commit34_promotion,'MANIFEST',bad):
                self.assertFalse(resolve('BTC-USDT','30m','LONG',
                      'FAILED_AUCTION_RANGE_ACCEPTANCE')['eligible'])

    def test_manifest_empty_cannot_promote(self):
        outcome=resolve('BTC-USDT','30m','LONG','FAILED_AUCTION_RANGE_ACCEPTANCE')
        self.assertFalse(outcome['eligible'])
        outcome=resolve('BTC-USDT','30m','SHORT','POST_MACRO_CONFIRMATION',existing_validated_family='BREAKOUT_RETEST')
        self.assertFalse(outcome['eligible'])
        self.assertEqual(outcome['reason'],'EXISTING_VALIDATED_ROUTE_PRIORITY')

    def test_repo_core_integrated_before_oi_without_new_safety_override(self):
        root=Path(__file__).parent
        app=(root/'app.py').read_text(encoding='utf-8')
        oi=(root/'operational_intelligence.py').read_text(encoding='utf-8')
        self.assertLess(app.index("capas['commit34_families'] = discover_families"),app.index('operational_intelligence = prepare_operational_intelligence('))
        self.assertIn('from commit34_promotion import resolve',oi)
        self.assertIn('from commit34_family_engine import discover_families',app)
        self.assertIn('def _commit34_guard_stage(',app)
        self.assertIn('def _commit34_cgroup_mb(',app)
        self.assertIn("structure['df'] = df_dict",app)
        self.assertIn("'high': [float(x) for x in df['high'].tolist()]",app)

if __name__=='__main__':unittest.main()
