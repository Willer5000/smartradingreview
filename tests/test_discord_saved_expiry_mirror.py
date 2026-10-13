"""C40.1: paridad de eventos a Discord (sin HTTP real, sin imports de app).

La expiración privada sólo se origina en eventos NUEVOS del lifecycle de una
señal guardada por usuario. Las señales confirmadas usan el outbox previo.
"""
import ast
import os
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import discord_guardian as dg
import discord_telegram_mirror as tm

PRIVATE_URL = 'https://discord.com/api/webhooks/12345/PrivateTOKEN'
PUBLIC_URL = 'https://discord.com/api/webhooks/67890/PublicTOKEN'

class Storage(types.ModuleType):
    def __init__(self):
        super().__init__('runtime_persistence')
        self.db = {}
    def save_runtime_snapshot(self, ns, key, payload, **kw):
        self.db[(ns, key)] = {'payload':payload};return True
    def load_runtime_snapshot(self, ns, key, **kw):
        return self.db.get((ns,key))

class DiscordExpiry(unittest.TestCase):
    def setUp(self):
        self.storage = Storage()
        self.stub = patch.dict(sys.modules, {'runtime_persistence':self.storage})
        self.stub.start()
        self.env = patch.dict(os.environ, {
            'DISCORD_GUARDIAN_USERS':'Willer, Danilo, Damir',
            'DISCORD_CONFIRMED_WEBHOOK_URL': PUBLIC_URL,
            'DISCORD_GUARDIAN_WEBHOOK_URL': PRIVATE_URL,
        }, clear=True)
        self.env.start()
        for mod in (dg,tm):
            mod._EVENTS.clear();mod._INFLIGHT.clear()
            mod._LOADED=False;mod._LAST_LOAD=0
    def tearDown(self):
        self.stub.stop();self.env.stop()

    def test_three_authorized_users_and_unapproved_owner(self):
        with patch.object(dg,'deliver',return_value=(True,0,'')) as send:
            for user in ['Willer','danilo','DAMIR']:
                self.assertTrue(dg.queue(user,'futures',f'saved-{user}', 'EXPIRED',f'saved-{user}', f'Expirada: {user}', ttl_seconds=86400))
            self.assertFalse(dg.queue('Ajeno','futures','saved-other','EXPIRED','saved-other','Expirada'))
        self.assertEqual(send.call_count,3)
        self.assertTrue(all(c.kwargs['webhook_env']=='DISCORD_GUARDIAN_WEBHOOK_URL' for c in send.call_args_list))
        self.assertEqual(len(self.storage.db[('discord','discord_guardian_v1')]['payload']['events']),3)

    def test_expired_not_sent_twice_even_across_restore(self):
        with patch.object(dg,'deliver',return_value=(True,0,'')) as send:
            self.assertTrue(dg.queue('Willer','multiasset','saved-id','EXPIRED','saved-id','⌛ Operación expirada',ttl_seconds=86400))
            self.assertFalse(dg.queue('Willer','multiasset','saved-id','EXPIRED','saved-id','⌛ Operación expirada',ttl_seconds=86400))
            dg._EVENTS.clear();dg._LOADED=False;dg._LAST_LOAD=0
            self.assertFalse(dg.queue('Willer','multiasset','saved-id','EXPIRED','saved-id','⌛ Operación expirada',ttl_seconds=86400))
            self.assertEqual(send.call_count,1)

    def test_pending_expiry_24h_but_normal_guardian_short(self):
        with patch.object(dg,'deliver',return_value=(False,5,'FAIL')):
            dg.queue('Willer','futures','saved-1','EXPIRED','saved-1','expired',ttl_seconds=86400)
            dg.queue('Willer','futures','saved-2','PROTECT','bucket','protect',ttl_seconds=900)
        events=list(dg._EVENTS.values())
        durations=sorted(e['expires_at']-e['created_at'] for e in events)
        self.assertGreater(durations[-1],86000)
        self.assertLess(durations[0],1000)

    def test_misc_mirror_is_private_never_public_and_no_new_threads(self):
        with patch('discord_confirmed.deliver',return_value=(True,0,'')) as send:
            self.assertTrue(tm.enqueue_from_telegram('🧭 ALERTA MACRO de interés',category='SPOT_OR_SYSTEM'))
            self.assertTrue(tm.enqueue_from_telegram('📌 Entry alcanzado BTC', category='FUTURES_ENTRY_ZONE'))
            self.assertEqual(tm.drain(2),2)
        self.assertEqual(send.call_count,2)
        self.assertTrue(all(c.kwargs['webhook_env']=='DISCORD_GUARDIAN_WEBHOOK_URL' for c in send.call_args_list))
        self.assertTrue(all('fallback_env' not in c.kwargs for c in send.call_args_list))

    def test_confirmations_saved_expiry_and_guardian_are_not_mirrored_twice(self):
        for category,message in [
            ('CONFIRMED_SIGNAL','✅ NUEVA SEÑAL CONFIRMADA FUTURES'),
            ('SPOT_OR_SYSTEM','✅ NUEVA SEÑAL CONFIRMADA SPOT'),
            ('SAVED_SIGNAL_EXPIRED','⌛ SEÑAL EXPIRADA Willer'),
            ('FUTURES_GUARDIAN','Guardian BTC'),
            ('SPOT_OR_SYSTEM','🛡️ GUARDIAN COMPRA'),
        ]:
            self.assertFalse(tm.enqueue_from_telegram(message,category=category))
        self.assertEqual(len(tm._EVENTS),0)

    def test_no_private_webhook_no_mirror_into_shared_channel(self):
        os.environ.pop('DISCORD_GUARDIAN_WEBHOOK_URL')
        self.assertFalse(tm.enqueue_from_telegram('Entry usuario privado'))
        self.assertEqual(tm.drain(),0)

    def test_mirror_retried_without_affecting_telegram_ack(self):
        with patch('discord_confirmed.deliver',side_effect=[(False,1,'HTTP_429'),(True,0,'')]) as send:
            self.assertTrue(tm.enqueue_from_telegram('⚠️ Aviso de vigilancia'))
            self.assertEqual(tm.drain(),0)
            event=next(iter(tm._EVENTS.values()))
            self.assertEqual(event['state'],'PENDING')
            event['retry_at']=time.time()-1
            self.assertEqual(tm.drain(),1)
            self.assertEqual(event['state'],'SENT')
        self.assertEqual(send.call_count,2)
        self.assertEqual(tm.drain(),0)

    def test_no_persistence_means_no_mirror_delivery(self):
        with patch.object(self.storage,'save_runtime_snapshot',return_value=False),patch('discord_confirmed.deliver') as send:
            self.assertFalse(tm.enqueue_from_telegram('Macro aviso'))
            self.assertEqual(send.call_count,0)

class AppWire(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=(ROOT/'app.py').read_text(encoding='utf-8')
        cls.tree=ast.parse(cls.s)
    def _func(self,name):
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name:
                return ast.get_source_segment(self.s,n)
        raise AssertionError('function not found: '+name)
    def test_expiry_only_current_saved_lifecycle(self):
        s=self._func('_send_saved_futures_lifecycle_notifications')
        self.assertIn('list(expired_events or [])',s)
        self.assertIn("str(sig.get('status') or '').lower() != 'expired'",s)
        self.assertIn('telegram_lifecycle_armed_at',s)
        self.assertIn('telegram_expired_notified_at',s)
        self.assertIn("if bool(sig.get('entry_touched'))",s)
        self.assertIn("'EXPIRED', signal_id",s)
        self.assertIn('if not _telegram_user_has_market_permission',s)
        self.assertLess(s.find('discord_private_queue('),s.find('if not _telegram_user_has_market_permission'))
    def test_generic_telegram_alerts_mirrored_without_affecting_transport(self):
        s=self._func('send_telegram_alert')
        self.assertIn('enqueue_from_telegram(message, category=category)',s)
        self.assertIn('requests.post(url, json=payload, timeout=15)',s)
        self.assertIn("category='CONFIRMED_SIGNAL'",self.s)
    def test_expiry_dispatch_uses_private_queue_only_for_new_saved_state(self):
        import datetime
        node=next(n for n in ast.walk(self.tree) if isinstance(n,ast.FunctionDef)
                  and n.name=='_send_saved_futures_lifecycle_notifications')
        expiry_globals={
            '_auth_users':lambda: {'Willer':{},'Danilo':{},'Damir':{}},
            '_saved_expiry_short_message':lambda user,record: ('futures',f'⌛ SEÑAL EXPIRADA: {user}'),
            '_telegram_user_has_market_permission':lambda user,market: True,
            'expert_system':types.SimpleNamespace(send_telegram_alert=lambda *a,**k: True),
            'datetime':datetime.datetime,
        }
        sent_updates=[]
        mock_saved=types.ModuleType('saved_signals')
        mock_saved.update_saved_signal_telegram_state=lambda sid,data:sent_updates.append((sid,data))
        with patch.dict(sys.modules,{'saved_signals':mock_saved}), patch.object(dg,'queue',return_value=True) as q:
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<expired>', 'exec'),expiry_globals)
            f=expiry_globals['_send_saved_futures_lifecycle_notifications']
            good={'id':'saved-123','status':'expired','user_name':'Willer','symbol':'SOL-USDT',
                  'timeframe':'2h','telegram_lifecycle_armed_at':'2026-10-13T10:00:00',
                  'close_reason':'expired_no_entry','entry_touched':False}
            stale={**good,'id':'saved-456','status':'active'}
            touched={**good,'id':'saved-789','entry_touched':True}
            nonarmed={**good,'id':'saved-012','telegram_lifecycle_armed_at':None}
            unknown={**good,'id':'saved-000','close_reason':'manual_close'}
            already={**good,'id':'saved-333','telegram_expired_notified_at':'now'}
            sent=f([good,stale,touched,nonarmed,unknown,already,good])
            self.assertEqual(sent,1)
            self.assertEqual(q.call_count,1)
            self.assertEqual(q.call_args.args[:5],('Willer','futures','saved-123','EXPIRED','saved-123'))
            self.assertEqual(len(sent_updates),1)

    def test_expiry_discord_not_depends_on_telegram_opt_in(self):
        import datetime
        node=next(n for n in ast.walk(self.tree) if isinstance(n,ast.FunctionDef)
                  and n.name=='_send_saved_futures_lifecycle_notifications')
        tg=Mock(return_value=True)
        expiry_globals={
            '_auth_users':lambda: {'Danilo':{}},
            '_saved_expiry_short_message':lambda user,record: ('multiasset','Expirada Danilo'),
            '_telegram_user_has_market_permission':lambda user,market: False,
            'expert_system':types.SimpleNamespace(send_telegram_alert=tg),
            'datetime':datetime.datetime,
        }
        mock_saved=types.ModuleType('saved_signals')
        mock_saved.update_saved_signal_telegram_state=Mock()
        with patch.dict(sys.modules,{'saved_signals':mock_saved}),patch.object(dg,'queue',return_value=True) as q:
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<expired>', 'exec'),expiry_globals)
            f=expiry_globals['_send_saved_futures_lifecycle_notifications']
            good={'id':'saved-id','status':'expired','user_name':'Danilo',
                  'telegram_lifecycle_armed_at':'now','close_reason':'expired_no_entry'}
            self.assertEqual(f([good]),0)
        q.assert_called_once()
        tg.assert_not_called()
        mock_saved.update_saved_signal_telegram_state.assert_not_called()

    def test_mirror_reuses_guardian_worker_and_no_trading_changes(self):
        s=self._func('monitor_guardian_telegram_loop')
        self.assertIn('drain_telegram_mirror(max_items=2)',s)
        self.assertIn('from discord_guardian import drain',s)
        self.assertEqual(self.s.count('def _discord_confirmed_delivery_optional('),1)
        self.assertIn("'SAVED_SIGNAL_EXPIRED'",self.s)

if __name__=='__main__':
    unittest.main()
