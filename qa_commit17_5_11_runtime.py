"""Offline behavioral QA, not a profitability backtest. No external writes.

Run from the full 17.5.10 FINAL project after applying 17.5.11:
    python qa_commit17_5_9_1_quality_delivery.py
Production functions are AST-loaded to avoid starting Flask, exchange, DB or
Telegram. Only transport/storage/time/market-provider boundaries are faked.
"""
import ast
import contextlib
import copy
from datetime import datetime, timezone, timedelta
import io
import math
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
import execution_specialist_committees as committees
import preliminary_backtest_prior as prior


ROOT = Path(__file__).resolve().parent
APP = (ROOT/'app.py').read_text(encoding='utf-8')
TREE = ast.parse(APP)


def functions(names, env=None):
    nodes = [copy.deepcopy(n) for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names), names
    for n in nodes:
        n.decorator_list = []
    ns = dict(env or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT/'app.py'), 'exec'), ns)
    return ns


def extract(name, tree=TREE):
    n, = [copy.deepcopy(n) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    n.decorator_list = []
    return n


def structure_fixture(side='long'):
    st = {'supports': [98., 97.5], 'resistances': [104., 106.],
          'pivot_lows': [{'price': 98.2, 'strength': 3}], 'pivot_highs': [{'price': 104.2, 'strength': 3}],
          'order_blocks': [{'type': 'bullish', 'price_range': [97.8, 98.4], 'strength': 'strong'},
                           {'type': 'bearish', 'price_range': [104., 104.5], 'strength': 'strong'}],
          'volume_profile': {'poc': 100., 'val': 98., 'vah': 104., 'hvn_nodes': [{'price': 98.3}, {'price': 104.1}]},
          'indicators': {'ema20': 99., 'ema50': 98.5, 'vwap': 99.2},
          'smc': {'liquidity_sweep': True, 'mss': True, 'displacement': True},
          'liquidity_sweep': True, 'mss': True, 'displacement': True}
    if side == 'short':
        st['supports'], st['resistances'] = [200-x for x in st['resistances']], [200-x for x in st['supports']]
        st['pivot_lows'], st['pivot_highs'] = ([{**x, 'price': 200-x['price']} for x in st['pivot_highs']],
                                            [{**x, 'price': 200-x['price']} for x in st['pivot_lows']])
        for ob in st['order_blocks']:
            ob['type'] = 'bearish' if ob['type'] == 'bullish' else 'bullish'
            ob['price_range'] = sorted(200-x for x in ob['price_range'])
        v = st['volume_profile']
        v['val'], v['vah'] = 200-v['vah'], 200-v['val']
        v['hvn_nodes'] = [{'price': 200-x['price']} for x in v['hvn_nodes']]
        st['indicators'] = {k: 200-v for k, v in st['indicators'].items()}
    return st


def recover(side='long', **changes):
    args = dict(direction=side, current_price=100., atr=1., structure=structure_fixture(side),
                trend={'direction': 'bullish' if side == 'long' else 'bearish'}, momentum={'rsi': 55 if side=='long' else 45},
                setup_family='SWEEP_REVERSAL', market_type='futures', symbol='BTC-USDT', timeframe='1h',
                execution_context={'activity_score': 50, 'shock_score': 0},
                rr_floor=1.8, rr_ceiling=4.5, leverage_hint=5)
    return committees.recover_execution_geometry_from_structure(**{**args, **changes})


class GeometryQA(unittest.TestCase):
    def test_long_and_short_far_level_is_not_collision(self):
        for side, stop, key, level in [('long',98,'pivot_lows',50), ('short',102,'pivot_highs',150)]:
            self.assertFalse(committees.evaluate_sl_reaction_conflict(structure={key:[{'price':level,'strength':3}]},
                direction=side, entry=100, stop_loss=stop, atr=1)['conflict'])

    def test_local_zone_remains_protected_and_beyond_is_clear(self):
        for side, stop, clear, key in [('long',98,97.5,'pivot_lows'),('short',102,102.5,'pivot_highs')]:
            st={key:[{'price':stop,'strength':3}]}
            self.assertTrue(committees.evaluate_sl_reaction_conflict(structure=st,direction=side,entry=100,stop_loss=stop,atr=1)['conflict'])
            self.assertFalse(committees.evaluate_sl_reaction_conflict(structure=st,direction=side,entry=100,stop_loss=clear,atr=1)['conflict'])

    def test_full_order_block_width_not_just_edge(self):
        for side, typ, band, stop, beyond in [('long','bullish',[95,99],96,94),('short','bearish',[101,105],104,106)]:
            st={'order_blocks':[{'type':typ,'price_range':band,'strength':'strong'}]}
            self.assertTrue(committees.evaluate_sl_reaction_conflict(structure=st,direction=side,entry=100,stop_loss=stop,atr=1)['conflict'])
            self.assertFalse(committees.evaluate_sl_reaction_conflict(structure=st,direction=side,entry=100,stop_loss=beyond,atr=1)['conflict'])

    def test_invalidated_ob_does_not_veto(self):
        st={'order_blocks':[{'type':'bullish','price_range':[95,99],'strength':'strong','invalidated':True}]}
        self.assertFalse(committees.evaluate_sl_reaction_conflict(structure=st,direction='long',entry=100,stop_loss=98,atr=1)['conflict'])

    def test_guard_invalid_data_fail_closed(self):
        for field in ('entry','stop_loss','atr'):
            for value in (0,-1,float('nan'),float('inf')):
                args=dict(structure={},direction='long',entry=100,stop_loss=98,atr=1)
                args[field]=value
                self.assertTrue(committees.evaluate_sl_reaction_conflict(**args)['conflict'])

    def test_recovery_both_directions_real_structure(self):
        for side in ('long','short'):
            got=recover(side)
            self.assertTrue(got['success'],got)
            e,s,t=got['entry'],got['stop_loss'],got['take_profit']
            self.assertTrue(s<e<t if side=='long' else t<e<s)
            self.assertGreaterEqual(got['sl_quality'],60)
            self.assertGreaterEqual(got['tp_quality'],60)
            self.assertGreaterEqual(got['geometry_quality'],62)
            self.assertFalse(committees.evaluate_sl_reaction_conflict(structure=structure_fixture(side),direction=side,entry=e,stop_loss=s,atr=1)['conflict'])

    def test_recovery_never_fabricates_atr(self):
        for val in (0,-1,float('nan'),float('inf')):
            self.assertEqual(recover(atr=val)['reason'],'INVALID_RECOVERY_INPUT')

    def test_close_median_and_hint_alone_cannot_create_entry(self):
        st={'df':{'high':[101,102,103], 'low':[97,98,99], 'close':[100,100,100]}}
        self.assertFalse(recover(structure=st,entry_hint=99)['success'])

    def test_no_structure_no_recovery(self):
        self.assertFalse(recover(structure={})['success'])

    def test_admissibility_veto_and_error_cannot_be_bypassed(self):
        self.assertFalse(recover(candidate_filter=lambda _:False)['success'])
        def broken(_): raise ValueError('fixture')
        self.assertEqual(recover(candidate_filter=broken)['reason'],'RECOVERY_GUARD_ERROR')

    def test_identical_geometry_zero_improvement_and_same_risk(self):
        for market in ('spot','futures','multiasset'):
            for side in ('long','short'):
                got=committees.coordinate_execution_committees(baseline_entry=100,baseline_sl=98 if side=='long' else 102,
                    baseline_tp=104 if side=='long' else 96,direction=side,current_price=101 if side=='long' else 99,
                    atr=2,market_type=market)
                self.assertTrue(got['success'])
                self.assertEqual(got['geometry_improvement'],0)


def approved_signal(side='LONG'):
    close=pd.Timestamp.now(tz='UTC')-pd.Timedelta(minutes=2)
    return {'success':True,'symbol':'BTC-USDT','timeframe':'1h','source_candle_closed':True,
            'source_candle_close_timestamp':close.isoformat(),
            'source_candle_timestamp':(close-pd.Timedelta(hours=1)).isoformat(),
            'analysis_mode':'CLOSED_CANDLE','decision':{'action':side,'confidence':80},
            'levels':{'entry':100,'stop_loss':98 if side=='LONG' else 102,'take_profit':104 if side=='LONG' else 96,
                      'leverage':2,'publication_status':'EXECUTABLE_SIGNAL','is_executable':True},
            'valid_until':(close+pd.Timedelta(hours=1)).isoformat()}



import market_maker_math as mm
import options_market_context as opt

class RuntimeQA(unittest.TestCase):
    def test_zero_weight_prior_cannot_change_consensus(self):
        for role in ('entry','sl','tp'):
            weights=committees._weights_for(role,'futures')
            scores={k:70 for k,v in weights.items() if v>0}
            base=committees._score_candidate(scores,weights,role)
            for value in (0,50,100):
                self.assertEqual(base,committees._score_candidate({**scores,'backtest_prior':value},weights,role))

    def test_cache_readers_never_fetch_options_or_build_curves(self):
        ns=functions({'_apply_17_5_10_profitability_market_maker_context'}, {'_PROFITABILITY_QUALIFIER_VERSION':'QA'})
        with patch.object(opt,'get_crypto_option_chain',side_effect=AssertionError('unexpected network')), patch.object(mm,'build_market_maker_context',side_effect=AssertionError('unexpected math')):
            for market in ('futures','multiasset'):
                raw=approved_signal()
                out=ns['_apply_17_5_10_profitability_market_maker_context'](raw,market)
                self.assertEqual(raw['decision'],out['decision'])
                self.assertEqual(out['levels']['entry'],100)
                self.assertFalse(out['levels']['profitability_qualification_is_publication_gate'])

    def test_ui_math_does_not_mutate_signal(self):
        ns=functions({'_attach_mm_ui_context'})
        raw={**approved_signal(),'current_price':100};before=copy.deepcopy(raw)
        with patch.object(opt,'get_crypto_option_chain',return_value={'rows':[]}):
            out=ns['_attach_mm_ui_context'](raw,'futures')
        self.assertEqual(raw,before)
        self.assertEqual(out['levels']['market_maker_context']['authority'],'UI_CONTEXT_ONLY')
        self.assertEqual(len(out['levels']['market_maker_context']['theta_curve']),41)

    def test_runtime_compaction_preserves_gates_and_drops_chart(self):
        ns=functions({'_compact_futures_runtime_result'})
        raw={**approved_signal(),'publication_eligible':False,'asset_class':'metal','is_executable':False}
        raw['levels']['market_maker_context']={'gex_curve':[[1,2]]*10000}
        got=ns['_compact_futures_runtime_result'](raw)
        self.assertFalse(got['publication_eligible']);self.assertFalse(got['is_executable'])
        self.assertEqual(got['asset_class'],'metal')
        self.assertNotIn('market_maker_context',got['levels'])
        self.assertEqual(got['source_candle_close_timestamp'],raw['source_candle_close_timestamp'])

    def test_single_interactive_job_across_markets(self):
        jobs=[]
        class Thread:
            def __init__(self,**kwargs): jobs.append(kwargs)
            def start(self): pass
        ns=functions({'_start_futures_ui_analysis_async'}, {'threading':SimpleNamespace(Thread=Thread),
            '_FUTURES_UI_CACHE':{'lock':threading.Lock(),'running':set(),'errors':{}},
            '_futures_ui_key':lambda s,t:(s,t), '_mark_futures_interactive_priority':lambda **kw:None})
        start=ns['_start_futures_ui_analysis_async']
        self.assertEqual(start('BTC-USDT','1h'),'SCHEDULED')
        self.assertEqual(start('BTC-USDT','1h'),'RUNNING')
        self.assertEqual(start('CL-USDT','4h','multiasset'),'DEFERRED_BUSY')
        self.assertEqual(len(jobs),1)

    def test_multi_http_returns_202_without_running_engine(self):
        fake=SimpleNamespace(MULTIASSET_SYMBOLS=['CL-USDT'],MULTIASSET_TIMEFRAMES=['4h'])
        calls=[]
        ns=functions({'api_multiasset_analyze'}, {'request':SimpleNamespace(get_json=lambda **kw:{}),
            'jsonify':lambda v:v,'_get_futures_ui_cached':lambda *a:None,
            '_MULTI_ASSET_CACHE':{'lock':threading.Lock(),'analysis':{}},
            '_get_futures_ui_recent_error':lambda *a:None,
            '_start_futures_ui_analysis_async':lambda *a,**kw:calls.append((a,kw)) or 'SCHEDULED'})
        with patch.dict(sys.modules,{'multiasset_system':fake}):
            out,status=ns['api_multiasset_analyze']()
        self.assertEqual(status,202);self.assertTrue(out['busy']);self.assertEqual(len(calls),1)

    def test_retry_failure_is_not_completed_analysis(self):
        ns=functions({'_multiasset_record_retry'}, {'_MULTI_AUTO_LOCK':threading.Lock(),
            '_MULTI_DEEP_RETRY':{},'_MULTI_AUTO_DONE':set(),'time':time})
        for _ in range(5):ns['_multiasset_record_retry']('CL|1h','timeout')
        self.assertNotIn('CL|1h',ns['_MULTI_AUTO_DONE'])
        self.assertEqual(ns['_MULTI_DEEP_RETRY']['CL|1h']['attempts'],5)

    def test_queue_expiry_anchored_to_close_not_enqueue(self):
        ns=functions({'_multiasset_bucket','_multiasset_queue_ttl_seconds','_multiasset_enqueue_due'},
            {'_MULTI_AUTO_LOCK':threading.Lock(),'_MULTI_AUTO_DONE':set(),'_MULTI_PENDING_KEYS':set(),
             '_MULTI_PENDING_QUEUE':[],'time':time})
        now=datetime(2026,9,29,12,9,tzinfo=timezone.utc)
        ns['_multiasset_enqueue_due']([('CL-USDT','1h')],now)
        self.assertEqual(ns['_MULTI_PENDING_QUEUE'][0]['expires_at'],datetime(2026,9,29,12,45,tzinfo=timezone.utc).timestamp())

class OptionsQA(unittest.TestCase):
    def test_put_delta_remains_negative_and_theta_is_present(self):
        now=datetime.now(timezone.utc)
        out=mm.aggregate_gamma_exposure([{'strike':100,'iv':.5,'open_interest':10,'option_type':'PUT','expiry':now+timedelta(hours=6)}],spot=100,as_of=now)
        self.assertLess(out['heuristic_signed_delta_dollars'],0)
        self.assertIsNone(out['delta_neutral_level']);self.assertIsNone(out['zero_gamma_level'])
        self.assertEqual(len(out['theta_curve']),41)
        self.assertTrue(all(r[1]<=0 for r in out['theta_curve']))
        self.assertTrue(any(r[1]<0 for r in out['theta_curve']))

    def test_expired_chain_is_not_revived(self):
        now=datetime.now(timezone.utc)
        out=mm.aggregate_gamma_exposure([{'strike':100,'iv':.5,'open_interest':10,'option_type':'PUT','expiry':now-timedelta(hours=1)}],spot=100,as_of=now)
        self.assertFalse(out['available'])

    def test_no_crossing_does_not_invent_zero(self):
        self.assertIsNone(mm._nearest_zero([(90,1),(100,2)],100))
        self.assertIsNone(mm._nearest_zero([(90,0),(100,0)],100))
        self.assertEqual(mm._nearest_zero([(90,-1),(100,1)],100),95)

    def test_theoretical_shape_label_and_authority(self):
        out=mm.theoretical_gamma_shape(spot=100,volatility=.6)
        self.assertFalse(out['observed_option_chain']);self.assertFalse(out['can_create_direction'])
        self.assertTrue(any(r[1]>0 for r in out['gex_curve']))
        self.assertIsNone(out['gamma_wall']);self.assertIsNone(out['zero_gamma_level'])

    def test_contracts_bounded_even_for_generator(self):
        now=datetime.now(timezone.utc)
        rows=({'strike':100,'iv':.5,'open_interest':10,'option_type':'PUT','expiry':now+timedelta(hours=6)} for _ in range(10000))
        out=mm.aggregate_gamma_exposure(rows,spot=100,as_of=now)
        self.assertEqual(out['contracts_used'],128)

    def test_free_mode_zero_external_calls(self):
        request=SimpleNamespace(get=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network')))
        with patch.object(opt,'ENABLED',False),patch.object(opt,'requests',request):
            self.assertFalse(opt.get_crypto_option_chain('BTC-USDT')['available'])

    def test_oversize_response_fail_cached_and_closed(self):
        class Response:
            headers={'Content-Length':str(opt.MAX_RESPONSE_BYTES+1)}
            def __enter__(self):return self
            def __exit__(self,*a):self.closed=True
            def raise_for_status(self):pass
        r=Response();calls=[]
        req=SimpleNamespace(get=lambda *a,**k:calls.append(1) or r)
        with patch.object(opt,'ENABLED',True),patch.object(opt,'requests',req),patch.object(opt,'_CACHE',{}):
            self.assertFalse(opt.get_crypto_option_chain('BTC-USDT')['available'])
            self.assertFalse(opt.get_crypto_option_chain('BTC-USDT')['available'])
        self.assertEqual(len(calls),1);self.assertTrue(r.closed)

    def test_inflight_fetch_is_not_duplicated(self):
        req=SimpleNamespace(get=lambda *a,**k:(_ for _ in ()).throw(AssertionError('duplicate')))
        with patch.object(opt,'ENABLED',True),patch.object(opt,'requests',req),patch.object(opt,'_CACHE',{}),patch.object(opt,'_INFLIGHT',{'BTC'}):
            self.assertEqual(opt.get_crypto_option_chain('BTC-USDT')['reason'],'FETCH_IN_PROGRESS')

class DeliveryQA(unittest.TestCase):
    def setUp(self):
        self.sent=[];self.ack=False;self.saved=[]
        env={'time':time,'pd':pd,'_confirmed_signal_outbox_lock':threading.Lock(),
            '_confirmed_signal_send_lock':threading.Lock(),'_confirmed_signal_alerts_lock':threading.Lock(),
            '_confirmed_signal_outbox':{},'_confirmed_signal_alerts_sent':{},
            '_save_confirmed_signal_outbox_to_disk':lambda:self.saved.append(1),
            '_save_confirmed_signal_alerts_to_disk':lambda:None,
            '_confirmed_signal_preferences_allow':lambda *a:True,
            '_build_confirmed_signal_telegram_message':lambda m,s:'test',
            'expert_system':SimpleNamespace(send_telegram_alert=lambda *a,**k:self.sent.append(1) or self.ack)}
        self.ns=functions({'_confirmed_signal_rr','_confirmed_signal_tf_seconds','_confirmed_signal_close_timestamp',
            '_confirmed_signal_recent_enough','_confirmed_delivery_valid_17_5_11','_compact_confirmed_outbox_signal',
            '_confirmed_outbox_enqueue','_attempt_confirmed_outbox_event','_attempt_confirmed_outbox_event_inner'},env)

    def test_long_short_and_low_leverage_valid(self):
        for market in ('futures','multiasset'):
            for side in ('LONG','SHORT'):
                self.assertTrue(self.ns['_confirmed_delivery_valid_17_5_11'](market,approved_signal(side)))

    def test_reject_invalid_geometry_expiry_preview_synthetic(self):
        cases=[]
        for k,v in [('source_candle_closed',False),('market_data_is_synthetic',True),('analysis_mode','INTRABAR_PREVIEW'),('publication_eligible',False),('valid_until','2020-01-01T00:00:00Z')]:
            cases.append({**approved_signal(),k:v})
        for value in (0,float('nan'),103):
            s=approved_signal();s['levels']['stop_loss']=value;cases.append(s)
        for s in cases:self.assertFalse(self.ns['_confirmed_delivery_valid_17_5_11']('futures',s),s)

    def test_spot_flat_levels_survive_compaction(self):
        s=approved_signal();s.update(s.pop('levels'));s['decision']['action']='COMPRA_SPOT'
        compact=self.ns['_compact_confirmed_outbox_signal']('spot',s)
        self.assertEqual(compact['levels']['entry'],100)
        self.assertTrue(self.ns['_confirmed_delivery_valid_17_5_11']('spot',compact))

    def test_retry_ack_and_duplicate_no_extra_persistence(self):
        enqueue=self.ns['_confirmed_outbox_enqueue'];attempt=self.ns['_attempt_confirmed_outbox_event']
        enqueue('futures',approved_signal(),'k');self.assertFalse(attempt('k'))
        row=self.ns['_confirmed_signal_outbox']['k'];deadline=row['next_retry_at'];writes=len(self.saved)
        enqueue('futures',approved_signal(),'k')
        self.assertEqual(len(self.saved),writes);self.assertEqual(row['next_retry_at'],deadline)
        self.assertFalse(attempt('k'));self.assertEqual(len(self.sent),1)
        row['next_retry_at']=0;self.ack=True;self.assertTrue(attempt('k'))
        self.assertTrue(attempt('k'));self.assertEqual(len(self.sent),2)

    def test_terminal_event_not_resurrected(self):
        self.ns['_confirmed_outbox_enqueue']('futures',approved_signal(),'k')
        self.ns['_confirmed_signal_outbox']['k']['state']='EXPIRED_OR_SUPERSEDED'
        self.ns['_confirmed_outbox_enqueue']('futures',approved_signal(),'k')
        self.assertFalse(self.ns['_attempt_confirmed_outbox_event']('k'));self.assertEqual(self.sent,[])

    def test_concurrent_send_lock_deduplicates(self):
        self.ns['_confirmed_outbox_enqueue']('futures',approved_signal(),'k')
        lock=self.ns['_confirmed_signal_send_lock'];lock.acquire()
        try:self.assertFalse(self.ns['_attempt_confirmed_outbox_event']('k'))
        finally:lock.release()
        self.assertEqual(self.sent,[])

    def test_full_outbox_never_evicts_pending(self):
        self.ns['_confirmed_signal_outbox'].update({str(i):{'state':'PENDING'} for i in range(300)})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(self.ns['_confirmed_outbox_enqueue']('futures',approved_signal(),'new'))
        self.assertEqual(len(self.ns['_confirmed_signal_outbox']),300)
        self.assertIn('0',self.ns['_confirmed_signal_outbox'])

if __name__=='__main__':unittest.main(verbosity=2)
