"""Regression checks: all three confirmation lanes and all three Guardian lanes.

Network is always mocked. These checks do not assert live delivery.
"""
import ast
import importlib
import os
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import discord_confirmed as dc
import discord_guardian as dg

TEST_URL = 'https://discord.com/api/webhooks/1234/fakeTOKEN'


class InMemoryPersistence(types.ModuleType):
    def __init__(self):
        super().__init__('runtime_persistence')
        self.saved = {}
    def save_runtime_snapshot(self, namespace, key, payload, **kwargs):
        self.saved[(namespace, key)] = {'payload': payload}
        return True
    def load_runtime_snapshot(self, namespace, key, **kwargs):
        return self.saved.get((namespace, key))


class DiscordTransports(unittest.TestCase):
    def setUp(self):
        self.persist = InMemoryPersistence()
        self.patcher = patch.dict(sys.modules, {'runtime_persistence': self.persist})
        self.patcher.start()
        dg._EVENTS.clear(); dg._INFLIGHT.clear(); dg._LOADED = False; dg._LAST_LOAD = 0
        self.env_patch = patch.dict(os.environ, {
            'DISCORD_CONFIRMED_WEBHOOK_URL': TEST_URL,
            'DISCORD_GUARDIAN_USERS': 'Willer',
        }, clear=True)
        self.env_patch.start()

    def tearDown(self):
        self.patcher.stop(); self.env_patch.stop()

    def test_confirmations_use_one_lightweight_transport(self):
        with patch.object(dc.urllib.request, 'urlopen') as call:
            response = call.return_value.__enter__.return_value
            response.status = 200
            ok, _, _ = dc.deliver('✅ SPOT BTC-USDT CONFIRMADA')
            self.assertTrue(ok)
            self.assertEqual(call.call_count, 1)
            self.assertIn(b'allowed_mentions', call.call_args.args[0].data)
            self.assertIn(b'?wait=true', call.call_args.args[0].full_url.encode())

    def test_guardian_opt_in_and_no_hold(self):
        with patch.object(dg, 'deliver', return_value=(True, 0, '')) as deliver:
            self.assertFalse(dg.queue('Danilo','spot','BTC','BUY_BTC','1','x'))
            self.assertFalse(dg.queue('Willer','spot','BTC','HOLD','1','x'))
            self.assertEqual(deliver.call_count, 0)

    def test_all_guardian_markets_and_durable_dedup(self):
        with patch.object(dg, 'deliver', return_value=(True, 0, '')) as deliver:
            self.assertTrue(dg.queue('Willer','spot','portfolio','SELL_BTC','window','a'))
            self.assertTrue(dg.queue('Willer','futures','signal-1','PROTECT','bucket','b'))
            self.assertTrue(dg.queue('Willer','multiasset','signal-2','EXIT','bucket','c'))
            self.assertEqual(deliver.call_count, 3)
            self.assertFalse(dg.queue('Willer','futures','signal-1','PROTECT','bucket','b'))
            self.assertEqual(deliver.call_count, 3)
            self.assertIn(('discord', 'discord_guardian_v1'), self.persist.saved)
            self.assertEqual(len(self.persist.saved[('discord', 'discord_guardian_v1')]['payload']['events']),3)
            dg._EVENTS.clear(); dg._LOADED = False; dg._LAST_LOAD = 0
            # Restart: SENT from Supabase still blocks another notification.
            self.assertFalse(dg.queue('Willer','futures','signal-1','PROTECT','bucket','b'))
            self.assertEqual(deliver.call_count, 3)

    def test_guardian_retries_without_telegram(self):
        with patch.object(dg, 'deliver', side_effect=[(False, 1, 'HTTP_429'), (True, 0, '')]) as deliver:
            self.assertFalse(dg.queue('Willer','spot','portfolio','BUY_BTC','42','buy'))
            self.assertEqual(deliver.call_count, 1)
            record = next(iter(dg._EVENTS.values()))
            self.assertEqual(record['status'],'PENDING')
            record['retry_after'] = time.time() - 1
            self.assertEqual(dg.drain(),1)
            self.assertEqual(record['status'],'SENT')

    def test_guardian_fail_closed_if_remote_store_down(self):
        with patch.object(self.persist, 'save_runtime_snapshot', return_value=False), \
                patch.object(dg, 'deliver', return_value=(True,0,'')) as sender:
            self.assertFalse(dg.queue('Willer','multiasset','CL-4H','EXIT','1','Exit'))
            self.assertEqual(sender.call_count,0)

    def test_html_telegram_to_discord_link(self):
        msg = '<b>Guardian</b> <a href="https://smartradingreview.onrender.com/signal/abc">Abrir señal</a> &amp; riesgo'
        out = dc._discord_text(msg)
        self.assertIn('https://smartradingreview.onrender.com/signal/abc',out)
        self.assertNotIn('<b>',out)
        self.assertIn('& riesgo',out)

    def test_proactive_spot_material_risk_is_sent(self):
        with patch.object(dg, 'deliver', return_value=(True,0,'')):
            payload={'action':'HOLD', 'market_risk_watch':{'alert':True,'reason':'Volatilidad extrema'}}
            self.assertTrue(dg.queue('Willer','spot','SPOT_RISK','RISK_WATCH','2',dg.format_spot_guardian('Willer',payload,'4h')))


class AppWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'app.py').read_text(encoding='utf8')
        cls.tree = ast.parse(cls.source)

    def test_lanes_wired_without_new_background_worker(self):
        s=self.source
        self.assertIn("_send_confirmed_signal_telegram('spot'", s)
        self.assertIn("_send_confirmed_signal_telegram('multiasset'", s)
        self.assertIn("_send_confirmed_signal_telegram(\n                        'futures'", s)
        self.assertIn('def _discord_confirmed_delivery_optional(key)',s)
        self.assertIn('def _retry_confirmed_signal_outbox',s)
        self.assertEqual(s.count('def _discord_guardian_notify('),1)
        self.assertIn("market='multiasset' if _is_multi_guardian else 'futures'",s)
        self.assertIn('tgp_result=tgp_result, timeframe=timeframe,',s)
        self.assertIn('drain(max_items=2)',s)
        self.assertNotIn('name=\'discord-worker\'',s)

    def test_no_trading_rules_touched(self):
        s=self.source
        self.assertIn("if not _confirmed_delivery_valid_17_5_11(market, signal):",s)
        self.assertIn("if event_action not in (",s)
        self.assertIn("if str(item.get('state') or '').upper() in ('INVALID', 'EXPIRED_OR_SUPERSEDED')",s)


if __name__=='__main__':
    unittest.main()
