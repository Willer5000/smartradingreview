import hashlib
import os
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import c46_live_reversal as c46

CAND=[dict(open=90.,high=92.,low=88.,close=91.,volume=100.) for _ in range(130)]
EVIDENCE={'rejection':'floor','sweep_bar_offset':-3,'anchor_bar_offset':-12,
          'rsi_sweep':39.,'rsi_anchor':34.,'confirmed_structure':True,
          'volume_ratio_proxy':1.35,'opposite_ema_context':True}
EVENT={'family':'FLOOR_SWEEP_DIVERGENCE_MSS','action':'LONG','evidence':EVIDENCE,
       'reference_price':110.,'invalidating_price_reference':96.}
BASE={'success':True,'publication_eligible':False,'is_executable':False,
      'source_candle_closed':True,'market_data_is_synthetic':False,
      'analysis_mode':'CLOSED_CANDLE','source_candle_timestamp':'2026-10-20T19:00:00Z',
      'decision':{'action':'NO_OPERAR'},
      'quality_context':{'trend':{'adx':28.,'direction':'bearish'},
      'momentum':{'rsi':44.,'direction':'bullish'},
      'volatility':{'atr':2.},
      'structure':{'current_price':110.,'order_blocks':[{'price':103.}]}}}
NATIVE={'entry':104.,'stop_loss':95.,'take_profit':123.,'leverage':15.,
        'entry_source':'Order Block alcista','entry_quality_score':89.,
        'sl_quality_score':87.,'tp_quality_score':84.,'execution_safety':86.,
        'is_executable':True,'is_rejected':False,
        'risk_control':{'leverage_policy_version':'native-V8'}}
class Engine:
    def __init__(self,native=None):self.calls=0;self.native=native or NATIVE
    def calculate_entry_levels(self,*args,**kwargs):
        self.calls+=1
        return dict(self.native)

def native_pass(result,symbol,timeframe):
    assert result['operational_intelligence']['candidate_contract']['historical_oos_validated'] is False
    assert result['operational_intelligence']['candidate_contract']['quality'] < 89
    assert result['operational_intelligence']['candidate_contract']['support_count']==4
    result['publication_eligible']=True;result['is_executable']=True
    result['levels']['publication_status']='EXECUTABLE_SIGNAL'
    return result

class Unit(unittest.TestCase):
    def setUp(self):self.flag=patch.dict(os.environ,{'C46_LIVE_ENABLED':'1'});self.flag.start();self.addCleanup(self.flag.stop)
    def run_candidate(self,source=BASE,engine=None,final=native_pass,events=None):
        engine=engine or Engine()
        with patch.object(c46,'detect',return_value=[EVENT] if events is None else events):
            result=c46.maybe_promote_reversal(source,CAND,symbol='BTC-USDT',timeframe='30m',market='futures',engine=engine,final_authority=final)
        return result,engine
    def test_additive_live_only_on_rejected_original(self):
        original={**BASE,'publication_eligible':True}
        result,engine=self.run_candidate(source=original)
        self.assertIs(result,original);self.assertEqual(engine.calls,0)
    def test_native_approval_required(self):
        o=dict(BASE);res,e=self.run_candidate(o,final=lambda a,s,t:a)
        self.assertIs(res,o);self.assertEqual(e.calls,1)
    def test_never_fabricates_backtest_evidence(self):
        o=dict(BASE);res,e=self.run_candidate(o)
        self.assertIsNot(res,o)
        self.assertFalse(res['operational_intelligence']['candidate_contract']['historical_oos_validated'])
        self.assertEqual(res['c46_validation_status'],'OOS_NOT_VALIDATED')
        self.assertEqual(res['levels']['leverage'],15.)
        self.assertEqual(res['decision']['action'],'LONG')
        self.assertEqual(o['decision']['action'],'NO_OPERAR')
    def test_stop_outside_swept_extreme(self):
        o=dict(BASE);res,_=self.run_candidate(o,Engine({**NATIVE,'stop_loss':99.}))
        self.assertIs(res,o)
    def test_no_market_pursuit(self):
        o=dict(BASE);res,_=self.run_candidate(o,Engine({**NATIVE,'entry':115.}))
        self.assertIs(res,o)
    def test_no_atr_fallback(self):
        o=dict(BASE);res,_=self.run_candidate(o,Engine({**NATIVE,'entry_source':'ATR fallback'}))
        self.assertIs(res,o)
    def test_no_macro_veto_bypass(self):
        o={**BASE,'publication_status':'WAIT_EVENT'}
        res,e=self.run_candidate(o)
        self.assertIs(res,o);self.assertEqual(e.calls,0)
    def test_no_source_candle_ambiguity(self):
        for key,val in [('source_candle_closed',False),('market_data_is_synthetic',True),('analysis_mode','INTRABAR_PREVIEW')]:
            o={**BASE,key:val};res,e=self.run_candidate(o)
            self.assertIs(res,o);self.assertEqual(e.calls,0)
    def test_no_oos_route_blocked(self):
        o={**BASE,'operational_intelligence':{'research_candidates':{'LONG':{'state':'NEGATIVE_OOS'}}}}
        res,e=self.run_candidate(o)
        self.assertIs(res,o);self.assertEqual(e.calls,0)
    def test_no_shadow_or_eight_losses(self):
        for gov in ({'state':'SHADOW'},{'consecutive_losses':8}):
            o={**BASE,'operational_intelligence':{'alpha_decay':gov}}
            res,e=self.run_candidate(o)
            self.assertIs(res,o);self.assertEqual(e.calls,0)
    def test_economics(self):
        with patch.dict(os.environ,{'C46_FEE_SLIPPAGE_FUNDING_PCT':'100'}):
            o=dict(BASE);res,_=self.run_candidate(o)
            self.assertIs(res,o)
    def test_unsupported_market_and_tf(self):
        e=Engine()
        with patch.object(c46,'detect',return_value=[EVENT]):
            for market,tf in [('spot','30m'),('multiasset','30m'),('futures','5m')]:
                o=dict(BASE)
                res=c46.maybe_promote_reversal(o,CAND,symbol='BTC-USDT',timeframe=tf,market=market,engine=e,final_authority=native_pass)
                self.assertIs(res,o)
        self.assertEqual(e.calls,0)
    def test_disabled_is_noop(self):
        with patch.dict(os.environ,{'C46_LIVE_ENABLED':'0'}):
            o=dict(BASE);res,e=self.run_candidate(o)
            self.assertIs(res,o);self.assertEqual(e.calls,0)
    def test_no_opposing_candidates(self):
        o=dict(BASE);res,e=self.run_candidate(o,events=[EVENT,{**EVENT,'action':'SHORT'}])
        self.assertIs(res,o);self.assertEqual(e.calls,0)
    def test_no_entry_policy_metadata_is_rejected(self):
        o=dict(BASE);native={**NATIVE,'risk_control':{}}
        res,e=self.run_candidate(o,Engine(native))
        self.assertIs(res,o)
    def test_no_lost_error_or_changed_original(self):
        o=dict(BASE);fingerprint=repr(o)
        res,e=self.run_candidate(o,final=lambda a,s,t: (_ for _ in ()).throw(RuntimeError('gate error')))
        self.assertIs(res,o);self.assertEqual(repr(o),fingerprint)

class Cache(unittest.TestCase):
    def test_read_cached_matching_closed_bar_only(self):
        import pandas as pd
        from c46_market_cache import closed_candles_from_native_cache
        try:import futures_system as fut
        except (ImportError,Exception):
            # Use a native-module stub: verifies read-only correctness.
            import threading
            fut=types.SimpleNamespace(_futures_data_cache={},_futures_data_cache_lock=threading.Lock())
            with patch.dict(sys.modules,{'futures_system':fut}):
                self._check_cache(pd,fut,closed_candles_from_native_cache)
        else:self._check_cache(pd,fut,closed_candles_from_native_cache)
    def _check_cache(self,pd,fut,read):
        times=pd.date_range('2026-10-01',periods=151,freq='h')
        df=pd.DataFrame([dict(time=x,open=100,high=110,low=90,close=105,volume=10) for x in times])
        key=('BTC-USDT','1h')
        old=fut._futures_data_cache.get(key)
        fut._futures_data_cache[key]={'df':df,'stored_at':0}
        try:
            expected=times[-2].isoformat()+'Z'
            rows=read(*key,expected)
            self.assertEqual(len(rows),130)
            self.assertEqual(rows[0]['open'],100)
            self.assertEqual(read(*key,'2020-01-01T00:00:00Z'),[])
            self.assertEqual(read('ETH-USDT','1h',expected),[])
            self.assertEqual(len(df),151)
        finally:
            if old is None:fut._futures_data_cache.pop(key,None)
            else:fut._futures_data_cache[key]=old

if __name__=='__main__':unittest.main()
