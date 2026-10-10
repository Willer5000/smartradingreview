"""Commit 34.4: deterministic, offline contracts (no Flask startup/network)."""
import ast
import hashlib
import pathlib
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text()
TREE = ast.parse(APP)


def namespace(*names):
    nodes = []
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            nodes.append(node)
    assert len(nodes) == len(names), (len(nodes), names)
    code = compile(ast.Module(body=nodes, type_ignores=[]), 'isolated-app.py', 'exec')
    space = {'datetime':datetime, 'timedelta':timedelta, 'timezone':timezone, 'pd':pd}
    exec(code,space)
    return space


class TelegramWebParity(unittest.TestCase):
    def setUp(self):
        from candle_close_authority_19_2_3 import signal_close_utc
        funcs=['_confirmed_web_registry_rows_34_4',
               '_merge_official_telegram_rows_34_4',
               '_find_official_telegram_row_34_4']
        self.g = namespace(*funcs)
        self.g.update({
            '_confirmed_signal_outbox_lock':threading.Lock(),
            '_confirmed_signal_alerts_lock':threading.Lock(),
            '_confirmed_signal_alerts_sent':{},
            '_confirmed_signal_outbox':{},
            '_confirmed_signal_tf_seconds': lambda tf: {'30m':1800,'1h':3600,'2h':7200,'4h':14400,'12h':43200,'1D':86400}[tf],
            '_confirmed_signal_close_timestamp': lambda sig,tf:pd.Timestamp(signal_close_utc(sig,tf)),
            '_parse_utc_iso': lambda raw: pd.Timestamp(raw).to_pydatetime().astimezone(timezone.utc) if raw is not None else None,
            '_futures_analysis_cache':{'data':{'lifecycle':{}}},
        })
        self.now = datetime(2026,10,10,14,30,tzinfo=timezone.utc)

    def add(self,market='multiasset', symbol='KSTR-USDT', tf='1h', minutes_old=20,
            valid_for_minutes=180, state='SENT', signal_id='kstr-34-test'):
        close = self.now - timedelta(minutes=minutes_old)
        # Use an explicit candle CLOSE aligned to the hour, to reflect real exchange data
        close = close.replace(minute=0,second=0,microsecond=0)
        key = f'{market}|{symbol}|{tf}|LONG|{close.isoformat()}'
        expiry = (close + timedelta(minutes=valid_for_minutes)).isoformat() if valid_for_minutes is not None else None
        self.g['_confirmed_signal_outbox'][key] = {
            'market':market,'state':state,'key':key,
            'signal':{'symbol':symbol,'timeframe':tf,'signal_id':signal_id,
                'source_candle_close_timestamp':close.isoformat(),
                'valid_until':expiry,
                'decision':{'action':'LONG','confidence':87},
                'levels':{'entry':90,'stop_loss':88,'take_profit':94,'leverage':7,
                          'publication_status':'EXECUTABLE_SIGNAL'},
            }
        }
        return key, close

    def rows(self,market='multiasset',lane='previous'):
        return self.g['_confirmed_web_registry_rows_34_4'](market,lane,55,self.now)

    def test_kstr_sent_does_not_disappear_when_cache_empty(self):
        self.add()
        rows=self.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['symbol'],'KSTR-USDT')
        self.assertEqual(rows[0]['source_authority'],'OFFICIAL_CONFIRMED_OUTBOX')
        self.assertEqual(rows[0]['source_context'],'PREVIOUS_CONFIRMED')
        self.assertEqual(rows[0]['activa'],1)
        self.assertEqual(rows[0]['signal_id'],'kstr-34-test')
        self.assertEqual(rows[0]['entry'],90)

    def test_one_candle_confirmed_then_technical_active(self):
        self.add(minutes_old=95,valid_for_minutes=180)
        self.assertEqual(len(self.rows(lane='previous')),0)
        self.assertEqual(len(self.rows(lane='active')),1)
        self.assertEqual(self.rows(lane='active')[0]['source_context'],'ACTIVE_CONFIRMED')

    def test_expired_does_not_resurrect(self):
        self.add(minutes_old=95,valid_for_minutes=40)
        self.assertEqual(self.rows(lane='active'),[])

    def test_terminal_futures_lifecycle_blocks_delivery_fallback(self):
        self.add(market='futures',symbol='BTC-USDT',tf='1h',minutes_old=95,signal_id='f-1')
        self.g['_futures_analysis_cache']['data']['lifecycle']['f-1']={'lifecycle_status':'sl_hit'}
        self.assertEqual(self.rows(market='futures',lane='active'),[])

    def test_futures_without_technical_until_does_not_extend_life(self):
        self.add(market='futures',symbol='BTC-USDT',tf='1h',minutes_old=95,
                 valid_for_minutes=None,signal_id='f-2')
        self.assertEqual(self.rows(market='futures',lane='active'),[])

    def test_pending_remains_accessible_even_if_telegram_down(self):
        key,_=self.add(state='FAILED_RETRYABLE')
        self.assertEqual(len(self.rows()),1)
        self.assertFalse(self.rows()[0]['telegram_delivery_confirmed'])
        self.assertEqual(self.rows()[0]['telegram_delivery_status'],'FAILED_RETRYABLE')
        self.g['_confirmed_signal_alerts_sent'][key]=self.now.timestamp()
        self.assertTrue(self.rows()[0]['telegram_delivery_confirmed'])

    def test_terminal_transport_candle_does_not_extend_technical_expiry(self):
        key,_=self.add(state='EXPIRED_OR_SUPERSEDED', minutes_old=95, valid_for_minutes=180)
        self.assertEqual(self.rows(lane='active'),[])
        # ACKed by Telegram but local transport ended as terminal after crash.
        self.g['_confirmed_signal_alerts_sent'][key]=self.now.timestamp()
        self.assertEqual(len(self.rows(lane='active')),1)
        self.g['_confirmed_signal_outbox'].clear()
        self.add(state='INVALID')
        self.assertEqual(self.rows(),[])

    def test_no_synthetic_intrabar_or_publication_ineligible_in_web_registry(self):
        key,_=self.add(state='PENDING')
        obj=self.g['_confirmed_signal_outbox'][key]['signal']
        for invalid_field in ('publication_eligible','source_candle_closed','market_data_is_synthetic'):
            obj[invalid_field] = True if invalid_field=='market_data_is_synthetic' else False
            self.assertEqual(self.rows(),[],invalid_field)
            obj.pop(invalid_field)

    def test_cannot_promote_non_execution_or_bad_geometry(self):
        key,_=self.add()
        obj=self.g['_confirmed_signal_outbox'][key]['signal']
        obj['levels']['publication_status']='ANALYSIS_ONLY'
        self.assertEqual(self.rows(),[])
        obj['levels']['publication_status']='EXECUTABLE_SIGNAL'
        obj['levels']['stop_loss']=93
        self.assertEqual(self.rows(),[])

    def test_market_isolation_and_merge_without_duplicate(self):
        self.add()
        self.assertEqual(self.rows(market='futures'),[])
        fn=self.g['_merge_official_telegram_rows_34_4']
        existing=[{'signal_id':'kstr-34-test','native':True}]
        # merge uses current UTC rather than fixture; test absence of duplicates via mocked rows
        self.g['_confirmed_web_registry_rows_34_4']=Mock(return_value=self.rows())
        self.assertEqual(fn(existing,'multiasset','previous')[0]['native'],True)
        self.assertEqual(len(fn(existing,'multiasset','previous')),1)

    def test_terminal_outbox_pruning_preserves_pending_and_active(self):
        from candle_close_authority_19_2_3 import signal_close_utc, tf_seconds, parse_utc
        g=namespace('_confirmed_outbox_terminal_technical_expired_34_4')
        g.update({'timedelta':timedelta,'time':__import__('time')})
        fn=g['_confirmed_outbox_terminal_technical_expired_34_4']
        close=self.now-timedelta(hours=2)
        close=close.replace(minute=0,second=0,microsecond=0)
        item={'market':'multiasset','state':'SENT','signal':{
            'timeframe':'1h','source_candle_close_timestamp':close.isoformat(),
            'valid_until':(close+timedelta(hours=4)).isoformat()}}
        self.assertFalse(fn(item, self.now.timestamp()))
        item['signal']['valid_until']=(close+timedelta(minutes=30)).isoformat()
        self.assertTrue(fn(item, self.now.timestamp()))
        item['state']='FAILED_RETRYABLE'
        self.assertFalse(fn(item, self.now.timestamp()))

    def test_multi_official_cache_has_save_button_authority(self):
        g=namespace('_multiasset_signal_row')
        row=g['_multiasset_signal_row']({
            'signal_id':'KSTR-1h','symbol':'KSTR-USDT','timeframe':'1h',
            'decision':{'action':'LONG','confidence':88},
            'levels':{'entry':91,'stop_loss':89,'take_profit':94,'leverage':7,
                      'publication_status':'EXECUTABLE_SIGNAL'}}, 'PREVIOUS_CONFIRMED')
        self.assertEqual(row['activa'],1)
        self.assertEqual(row['lifecycle_status'],'waiting_entry')

    def test_source_unchanged_and_no_new_external_fetches(self):
        helper_src=ast.get_source_segment(APP,next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_confirmed_web_registry_rows_34_4'))
        for prohibited in ('requests.get','requests.post','fetch_ohlcv','analyze_full_market','save_runtime_snapshot','threading.Thread'):
            self.assertNotIn(prohibited,helper_src)

    def test_endpoints_serve_both_markets_from_ledger(self):
        for endpoint in ('api_multiasset_signals_previous','api_multiasset_signals_active','api_futures_signals_previous','api_futures_signals_active'):
            node = next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name==endpoint)
            self.assertIn('_merge_official_telegram_rows_34_4',ast.get_source_segment(APP,node))
        for word in ("if is_multiasset_save:", "_find_official_telegram_row_34_4('multiasset'", "data['source_valid_until']"):
            self.assertIn(word,APP)

    def test_technical_until_is_not_extended(self):
        self.add(minutes_old=95,valid_for_minutes=180)
        expected=self.now.replace(hour=14,minute=0,second=0,microsecond=0) + timedelta(minutes=180) # from close 14:00? minutes_old=95 -> 12:00
        expected=self.now-timedelta(minutes=95); expected=expected.replace(minute=0,second=0,microsecond=0)+timedelta(minutes=180)
        self.assertEqual(self.rows(lane='active')[0]['valid_until'],expected.isoformat())


if __name__=='__main__':
    unittest.main()
