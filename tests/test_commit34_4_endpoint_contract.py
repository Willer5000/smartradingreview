"""No-network HTTP contract regression for official Multi-Asset sent signals."""
import ast
import pathlib
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
code = (ROOT/'app.py').read_text()
TREE = ast.parse(code)

class DummyApp:
    def route(self, *_args, **_kwargs):
        return lambda fn: fn

class EndpointContractTest(unittest.TestCase):
    def setUp(self):
        names={'api_multiasset_signals_previous','api_multiasset_signals_active'}
        funcs=[]
        for n in TREE.body:
            if isinstance(n,ast.FunctionDef) and n.name in names:
                n.decorator_list=[]
                funcs.append(n)
        self.assertEqual(len(funcs),2)
        self.g={'app': DummyApp(), 'bolivia_tz':timezone.utc,
            'datetime':datetime, 'jsonify':lambda x:x,
            'request':type('Request',(),{'args':{}})(),
            '_multiasset_restore_local_snapshot_once':lambda:None,
            '_MULTI_ASSET_CACHE':{'lock':__import__('threading').Lock(),'analysis':{}},
            '_multiasset_directional_diagnostics_17511':lambda analyses:[],
            '_public_pipeline_health_175103':lambda analyses:{},
            '_multiasset_is_executable':lambda result:bool(result.get('official')),
            '_multiasset_signal_temporal_state':lambda result:result.get('temporal',{}),
            '_multiasset_signal_row':lambda result,src:{'signal_id':result['signal_id'],'confidence':87,'source_context':src},
            '_merge_official_telegram_rows_34_4':Mock(side_effect=lambda cur,market,lane,conf:cur+[{
                'symbol':'KSTR-USDT','timeframe':'1h','signal_id':'kstr-ack',
                'action':'LONG','confidence':87,'entry':90,'stop_loss':88,'take_profit':94,
                'source_context':'PREVIOUS_CONFIRMED' if lane=='previous' else 'ACTIVE_CONFIRMED',
            }] if lane=='previous' else cur),
        }
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'endpoint.py','exec'),self.g)

    def test_multi_previous_shows_telegram_confirmed_when_analysis_cache_empty(self):
        response=self.g['api_multiasset_signals_previous']()
        self.assertTrue(response['success'])
        self.assertEqual(response['total'],1)
        self.assertTrue(response['cache_ready'])
        self.assertEqual(response['signals'][0]['symbol'],'KSTR-USDT')
        self.assertTrue(self.g['_merge_official_telegram_rows_34_4'].called)

    def test_multi_active_no_invention(self):
        response=self.g['api_multiasset_signals_active']()
        self.assertTrue(response['success'])
        self.assertEqual(response['total'],0)
        self.assertFalse(response['cache_ready'])

if __name__=='__main__': unittest.main()
