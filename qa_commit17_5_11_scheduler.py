"""Offline production scheduler tests with fake I/O; resource ceilings retained."""
from qa_commit17_5_11_runtime import functions
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch
import unittest,threading,sys,os,time

class SchedulerQA(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,29,12,1,tzinfo=timezone.utc)
        self.calls=[];self.failed=set();self.busy=False;self.sent=[];self.score=90
        owner=self
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return owner.now
        fake_time=SimpleNamespace(time=lambda:self.now.timestamp(),monotonic=time.monotonic)
        env={'datetime':Clock,'timezone':timezone,'time':fake_time,'os':os,
            '_MULTI_AUTO_LOCK':threading.Lock(),'_MULTI_AUTO_DONE':set(),'_MULTI_AUTO_DAILY':{},
            '_MULTI_PENDING_QUEUE':[],'_MULTI_PENDING_KEYS':set(),'_MULTI_PENDING_EXPIRED':0,
            '_MULTI_PENDING_RESOURCE_DEFERRALS':0,'_MULTI_DEEP_RETRY':{},'_MULTI_CLOSE_REFRESHED':set(),
            '_MULTI_FAST_LANE_MIN_SCORE':82,'_MULTI_DAILY_CONTEXT_EXTRA_MAX':2,
            '_MULTI_ROUTER_STATE_LOCK':threading.Lock(),'_MULTI_ROUTER_STATE':{},
            '_multiasset_is_executable':lambda r:False,'_multiasset_compact_telegram':lambda r:self.sent.append(r)}
        names={'_multiasset_close_plan','_multiasset_close_refresh_done','_multiasset_mark_close_refresh',
            '_multiasset_bucket','_multiasset_queue_ttl_seconds','_multiasset_enqueue_due','_multiasset_prune_pending',
            '_multiasset_pop_completed_pending','_multiasset_retry_ready','_multiasset_record_retry','_multiasset_background_tick'}
        self.ns=functions(names,env)
        self.ns['_multiasset_scan']=lambda tf,force=False:[{'symbol':f'A{i}','router_score':self.score-i,'deep_candidate':i<2} for i in range(7)]
        def run(sym,tf,owner):
            self.calls.append((sym,tf))
            if self.busy:return {'busy':True}
            if sym in self.failed:return {'success':False,'error':'timeout'}
            return {'success':True,'symbol':sym,'timeframe':tf}
        self.ns['_multiasset_run_analysis']=run
    def tick(self,n=1):
        with patch.dict(sys.modules,{'multiasset_system':SimpleNamespace(MULTIASSET_DEEP_LIMIT=2,MULTIASSET_AUTO_DEEP_DAILY_MAX=12)}),patch.dict(os.environ,{'MULTIASSET_ENABLED':'1'}):
            for _ in range(n):self.ns['_multiasset_background_tick']()
    def test_all_seven_qualified_fast_candidates_reachable(self):
        self.tick(7)
        self.assertEqual(len(set(self.calls)),7)
        self.assertTrue(all(tf=='1h' for _,tf in self.calls))
    def test_resource_cap_preserved_and_not_marked_complete(self):
        self.tick(20)
        self.assertEqual(len(self.calls),12)
        self.assertGreater(self.ns['_MULTI_PENDING_RESOURCE_DEFERRALS'],0)
        self.assertGreater(len(self.ns['_MULTI_PENDING_QUEUE']),0)
    def test_blocked_fast_budget_does_not_block_daily_lane(self):
        self.now=self.now.replace(hour=0)
        self.ns['_MULTI_AUTO_DAILY']={'day':'2026-09-29','count':12,'context_count':0}
        self.tick(3)
        self.assertEqual(len(self.calls),2)
        self.assertTrue(all(tf=='1D' for _,tf in self.calls))
    def test_4h_candidates_rotate_past_top_two(self):
        self.score=70
        self.tick(7)
        self.assertEqual(len(set(self.calls)),7)
        self.assertTrue(all(tf=='4h' for _,tf in self.calls))
    def test_failures_not_completed_and_next_candidate_can_run(self):
        self.failed={'A0'};self.tick(2)
        self.assertEqual(self.calls,[('A0','1h'),('A1','1h')])
        self.assertFalse(any(key.startswith('A0|') for key in self.ns['_MULTI_AUTO_DONE']))
    def test_busy_retains_queue_then_resumes(self):
        self.busy=True;self.tick();self.assertFalse(self.ns['_MULTI_AUTO_DONE'])
        self.busy=False;self.now=self.now.replace(minute=25);self.tick()
        self.assertEqual(self.calls[0],self.calls[1])
    def test_expired_queue_not_analyzed(self):
        self.busy=True;self.tick();self.busy=False;self.calls=[]
        self.now=self.now.replace(hour=14,minute=50);self.tick()
        self.assertEqual(self.calls,[]);self.assertGreater(self.ns['_MULTI_PENDING_EXPIRED'],0)
    def test_fast_lane_quality_floor_unchanged(self):
        self.score=81;self.tick()
        self.assertFalse(any(tf=='1h' for _,tf in self.calls))

if __name__=='__main__':unittest.main(verbosity=2)
