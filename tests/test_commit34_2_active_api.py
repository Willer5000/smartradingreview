"""Isolated production-route regressions without starting Gunicorn or background jobs.

Executes the *actual* api_futures_signals_active function from app.py, with
network/DB dependencies replaced by in-memory test doubles. No strategy changes.
"""
import ast
import sys
import threading
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from commit34_lifecycle_contract import in_confirmation_window  # noqa: E402

TF_SECONDS = {'30m':1800,'1h':3600,'2h':7200,'4h':14400,'12h':43200,'1D':86400}


class AppStub:
    @staticmethod
    def route(*args, **kwargs):
        return lambda fn: fn


class ActiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT/'app.py').read_text(encoding='utf-8')
        module = ast.parse(source)
        route = next(n for n in module.body
                     if isinstance(n, ast.FunctionDef)
                     and n.name == 'api_futures_signals_active')
        route.decorator_list = []
        cls.route_source = ast.get_source_segment(source, route)
        cls.route_code = compile(ast.Module(body=[route],type_ignores=[]),
                                 filename=str(ROOT/'app.py'),mode='exec')

    def make_server(self, *, tf='1h', minutes_after_close=90,
                    valid_for_minutes=150, status='waiting_entry',
                    official=True, representative=True, confidence=87):
        now = datetime.now(timezone.utc)
        duration = TF_SECONDS[tf]
        candle_close = now - timedelta(minutes=minutes_after_close)
        record = {
            'signal_id':'s1', 'symbol':'BTC-USDT', 'timeframe':tf,
            'lifecycle_status':status, 'publication_status':
                'EXECUTABLE_SIGNAL' if official else 'ANALYSIS_ONLY',
            'system_executable':official, 'action':'SHORT',
            'confidence':confidence, 'entry':100., 'stop_loss':104.,
            'take_profit':92., 'leverage':5, 'risk_reward':2.,
            'source_candle_close_timestamp':candle_close.isoformat(),
            'source_candle_timestamp':(candle_close-timedelta(seconds=duration)).isoformat(),
            'valid_until':(now+timedelta(minutes=valid_for_minutes)).isoformat(),
        }
        analysis = {
            ('BTC-USDT', tf): {
                'success':True, 'signal_id':'s1', 'symbol':'BTC-USDT',
                'timeframe':tf, 'decision':{'action':'SHORT'},
                'levels':{'publication_status':'EXECUTABLE_SIGNAL'},
                'source_candle_close_timestamp':candle_close.isoformat(),
                'source_candle_timestamp':record['source_candle_timestamp'],
            }
        }
        cache = {'analysis':analysis,'lifecycle':{'s1':record},
                 'warming_up':False, 'refreshing':False}
        futures=types.ModuleType('futures_system')
        futures.futures_timeframe_allowed=lambda s, t: bool(s and t in TF_SECONDS)
        futures._leverage_in_valid_range=lambda leverage,tf: leverage>0
        sys.modules['futures_system']=futures
        ns={
            'app':AppStub(), 'request':types.SimpleNamespace(args={'min_confidence':'55'}),
            'jsonify':lambda payload:payload,
            'pd':pd, 'datetime':datetime, 'bolivia_tz':timezone.utc,
            '_get_or_refresh_futures_analysis':lambda:cache,
            '_build_futures_analysis_visibility':lambda *a,**kw:{'summary':{},'candidates':[]},
            '_futures_manual_risk_profile':lambda row:{'allowed':False},
            '_futures_frontend_representative_ids':lambda cache:{'s1'} if representative else set(),
            '_futures_decision_audit_for_api':lambda rec:{},
            '_configured_futures_module':lambda:None,
            '_derivative_premium_leverage_ok':lambda lev:True,
            '_futures_vigent_manual_candidates':lambda *a,**kw:[],
            '_futures_directional_hidden_candidates':lambda *a,**kw:[],
            '_public_pipeline_health_175103':lambda x:{},
            '_dedupe_representative_signals':lambda x:x,
            '_representative_signal_score':lambda x:10.,
            '_signal_source_epoch':lambda x:1.,
            '_futures_analysis_cache':{'lock':threading.RLock(),'progress':{}},
            '_commit34_confirmation_window_is_current':lambda row,tf:in_confirmation_window(
                row.get('source_candle_close_timestamp'),
                row.get('source_candle_timestamp'),tf),
        }
        exec(self.route_code,ns)
        return ns['api_futures_signals_active'],cache

    def test_all_futures_timeframes_can_become_vigent(self):
        for tf,seconds in TF_SECONDS.items():
            with self.subTest(tf=tf):
                call,_ = self.make_server(tf=tf,minutes_after_close=seconds/60+2)
                result=call()
                self.assertIsInstance(result,dict,repr(result))
                self.assertTrue(result['success'])
                self.assertEqual(result['total'],1)
                self.assertEqual(result['signals'][0]['timeframe'],tf)
                self.assertEqual(result['signals'][0]['source_context'],'ACTIVE_CONFIRMED')

    def test_fresh_confirmation_does_not_duplicate_in_active(self):
        call,_ = self.make_server(tf='1h',minutes_after_close=20)
        result=call()
        self.assertTrue(result['success'])
        self.assertEqual(result['total'],0)
        self.assertEqual(result['filter_stats']['new_confirmation'],1)

    def test_expired_technical_validity_does_not_reappear(self):
        call,_ = self.make_server(minutes_after_close=125,valid_for_minutes=-1)
        result=call()
        self.assertTrue(result['success'])
        self.assertEqual(result['total'],0)

    def test_analysis_only_has_no_official_live_authority(self):
        call,_ = self.make_server(minutes_after_close=125,official=False)
        result=call()
        self.assertTrue(result['success'])
        self.assertEqual(result['total'],0)

    def test_closed_signal_never_returns_to_active(self):
        call,_ = self.make_server(minutes_after_close=125,status='tp')
        result=call()
        self.assertTrue(result['success'])
        self.assertEqual(result['total'],0)

    def test_nonrepresentative_not_shown_as_duplicate(self):
        call,_ = self.make_server(minutes_after_close=125,representative=False)
        result=call()
        self.assertTrue(result['success'])
        self.assertEqual(result['total'],0)

    def test_old_active_does_not_mutate_original_expiration(self):
        call,cache = self.make_server(minutes_after_close=125,valid_for_minutes=120)
        original=cache['lifecycle']['s1']['valid_until']
        result=call()
        self.assertTrue(result['success'])
        self.assertEqual(cache['lifecycle']['s1']['valid_until'],original)
        self.assertEqual(result['signals'][0]['valid_until'],original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
