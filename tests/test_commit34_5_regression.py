"""Isolated regression suite without importing the 60,000-line production app."""
import ast
import inspect
import json
import os
import threading
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'app.py').read_text()
TREE=ast.parse(SOURCE)


def load_function(name, scope):
    original=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name==name)
    original=ast.FunctionDef(name=original.name, args=original.args, body=original.body,
                             decorator_list=[],returns=original.returns,type_comment=original.type_comment)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original],type_ignores=[])),
                 str(ROOT/'app.py'),'exec'),scope)
    return scope[name]


class OfficialHistoryTest(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,18,0,0,tzinfo=timezone.utc)
        close=self.now-timedelta(hours=4)
        until=self.now-timedelta(hours=1)
        self.signal={
            'symbol':'KSTR-USDT','timeframe':'4h',
            'decision':{'action':'LONG','confidence':80},
            'levels':{'entry':21,'stop_loss':20,'take_profit':23,'leverage':3,'publication_status':'EXECUTABLE_SIGNAL'},
            'source_candle_close_timestamp':close.isoformat(),
            'valid_until':until.isoformat(),
        }
        self.scope={'datetime':datetime,'timezone':timezone,'timedelta':timedelta,
            'threading':threading,'_confirmed_signal_outbox_lock':threading.Lock(),
            '_confirmed_signal_alerts_lock':threading.Lock(),
            '_confirmed_signal_outbox':{'t|1':{'market':'multiasset','state':'SENT','signal':self.signal}},
            '_confirmed_signal_alerts_sent':{},
            '_parse_utc_iso':lambda value: datetime.fromisoformat(str(value).replace('Z','+00:00')) if value else None,
            '_confirmed_signal_tf_seconds':lambda tf: {'4h':14400,'1h':3600,'1D':86400}.get(tf,0),
            '_confirmed_signal_close_timestamp':lambda signal,tf:signal.get('source_candle_close_timestamp'),
        }
    def test_terminal_retention_24h_beyond_expiry(self):
        fn=load_function('_confirmed_outbox_terminal_technical_expired_34_4',self.scope)
        # This function imports candle_close_authority, which needs a stub for one test.
        import sys
        module=SimpleNamespace(signal_close_utc=lambda sig,tf:datetime.fromisoformat(sig['source_candle_close_timestamp']),
                tf_seconds=lambda tf:14400,parse_utc=lambda value:datetime.fromisoformat(str(value)))
        with patch.dict(sys.modules,{'candle_close_authority_19_2_3':module}):
            event=self.scope['_confirmed_signal_outbox']['t|1']
            self.assertFalse(fn(event, self.now.timestamp()))
            self.assertTrue(fn(event,(self.now+timedelta(hours=24)).timestamp()))
    def test_recent_history_never_tradable(self):
        fn=load_function('_confirmed_web_recent_history_34_5',self.scope)
        rows=fn('multiasset',self.now)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['symbol'],'KSTR-USDT')
        self.assertIs(rows[0]['tradable'],False)
        self.assertIs(rows[0]['manual_save_allowed'],False)
        self.assertEqual(fn('spot',self.now),[])
        self.assertEqual(fn('multiasset',self.now+timedelta(days=2)),[])
    def test_unsent_delivery_not_claimed_as_telegram_history(self):
        fn=load_function('_confirmed_web_recent_history_34_5',self.scope)
        self.scope['_confirmed_signal_outbox']['t|1']['state']='PENDING'
        self.assertEqual(fn('multiasset',self.now),[])


class EndpointTest(unittest.TestCase):
    def test_cache_only_no_analyze_calls(self):
        import sys
        app=SimpleNamespace(route=lambda *args,**kwargs:lambda fn:fn)
        cell={'success':True,'symbol':'CL-USDT','timeframe':'4h',
              'decision':{'action':'ESPERAR','confidence':63},'message':'ADX 17.9, bajo: esperar confirmación',
              'source_candle_close_timestamp':'2026-10-10T12:00:00+00:00'}
        req=SimpleNamespace(args={'symbol':'CL-USDT','timeframe':'4h'})
        scope={'app':app,'request':req,'jsonify':lambda obj:obj,
               'threading':threading,'_MULTI_ASSET_CACHE':{'lock':threading.Lock(),'analysis':{('CL-USDT','4h'):cell}},
               '_get_futures_ui_cached':lambda sym,tf:None,
               '_compact_futures_ui_result':lambda d:d}
        with patch.dict(sys.modules,{'multiasset_system':SimpleNamespace(MULTIASSET_SYMBOLS={'CL-USDT':{}},MULTIASSET_TIMEFRAMES=('1h','4h','1D'))}):
            fn=load_function('api_multiasset_recommendation_ready_34_5',scope)
            result,status=fn()
            self.assertEqual(status,200)
            self.assertTrue(result['ready'])
            self.assertEqual(result['data']['message'],cell['message'])
            self.assertTrue(result['historical_reference'])
            req.args['symbol']='BTC-USDT'
            result,status=fn()
            self.assertEqual(status,400)
            req.args['symbol']='CL-USDT'
            scope['_MULTI_ASSET_CACHE']['analysis'].clear()
            result,status=fn()
            self.assertEqual(status,200)
            self.assertFalse(result['ready'])


class JavascriptTest(unittest.TestCase):
    def test_javascript_contract(self):
        js=(ROOT/'static'/'script.js').read_text()
        fj=(ROOT/'static'/'futures.js').read_text()
        self.assertIn('window.watchMultiRecommendationReady345',js)
        self.assertIn('window.stopMultiRecommendationWatch345',js)
        self.assertIn('/api/multiasset/recommendation-ready?',js)
        self.assertIn('window.renderMultiCachedRecommendation343',js)
        self.assertIn('futRenderRecentOfficialHistory345',fj)
        self.assertIn('Historial de alertas Telegram finalizadas',fj)
        self.assertNotIn('window.openManualAnalysisSave',fj.split('function futRenderRecentOfficialHistory345',1)[1].split('function futRenderAnalysisDiagnostics',1)[0])

if __name__=='__main__':unittest.main()
