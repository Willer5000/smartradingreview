"""C40.3: integration of Telegram ACK -> Discord with no extra thread/network.

Loads the actual app.py function AST; tests using fake transport and persistence.
No external API, strategy engine or Flask imported.
"""
import ast
import os
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    '_attempt_confirmed_outbox_event_inner',
    '_discord_confirmed_delivery_optional',
    '_deliver_discord_confirmed_for_key',
    '_retry_discord_confirmed_only',
)


def production_code():
    src = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    nodes = [n for n in src.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    assert len(nodes) == len(NAMES), 'Production code changed unexpectedly'
    return compile(ast.Module(body=nodes, type_ignores=[]), '<app.py>', 'exec')


class TestPostTelegramAck(unittest.TestCase):
    def setUp(self):
        self.discord_module = types.ModuleType('discord_confirmed')
        self.discord_module.enabled = lambda: True
        self.discord_module.deliver = Mock(return_value=(True, 0, ''))
        self.store_module = types.ModuleType('official_signal_store')
        self.store_module.persist_official = Mock(return_value=True)
        self.patch_modules = patch.dict(sys.modules, {
            'discord_confirmed': self.discord_module,
            'official_signal_store': self.store_module,
        })
        self.patch_modules.start()
        self.patch_env = patch.dict(os.environ, {
            'DISCORD_CONFIRMED_WEBHOOK_URL': 'https://discord.com/api/webhooks/1234/fakeTOKEN',
        })
        self.patch_env.start()
        self.box = {}
        self.telegram = Mock(return_value=True)
        self.save = Mock(return_value=True)
        self.namespace = {
            'time': time, 'threading': threading, 'os': os,
            '_confirmed_signal_outbox': self.box,
            '_confirmed_signal_outbox_lock': threading.Lock(),
            '_confirmed_discord_delivery_lock': threading.Lock(),
            '_confirmed_signal_alerts_lock': threading.Lock(),
            '_confirmed_signal_alerts_sent': {},
            '_confirmed_delivery_valid_17_5_11': Mock(return_value=True),
            '_save_confirmed_signal_outbox_to_disk': self.save,
            '_save_confirmed_signal_alerts_to_disk': self.save,
            '_build_confirmed_signal_telegram_message':
                lambda market, sig: f'✅ NUEVA SEÑAL CONFIRMADA {market} {sig["symbol"]}',
            '_CONFIRMED_OUTBOX_LAST_RESTORE_MONO_35': time.monotonic(),
            '_load_confirmed_signal_outbox_from_disk': Mock(),
            'expert_system': types.SimpleNamespace(send_telegram_alert=self.telegram),
        }
        exec(production_code(), self.namespace)

    def tearDown(self):
        self.patch_env.stop()
        self.patch_modules.stop()

    def add_signal(self, key='BTC', market='futures', age=0):
        self.box[key] = {
            'key': key, 'market': market,
            'signal': {'symbol': key+'-USDT', 'timeframe': '30m',
                       'decision': {'action': 'SHORT', 'confidence': 88},
                       'levels': {'entry': 80, 'stop_loss': 82, 'take_profit': 74,
                                  'publication_status': 'EXECUTABLE_SIGNAL'}},
            'state': 'PENDING', 'created_at': time.time()-age,
            'next_retry_at': 0.0, '_c35_remote_persisted': True,
            'discord_state': 'PENDING', 'discord_retry_at': 0.0,
        }

    def test_telegram_positive_ack_posts_same_event_immediately(self):
        for market, key in [('futures', 'BTC'), ('spot', 'PAXG'), ('multiasset', 'CL')]:
            self.add_signal(key, market)
            self.assertTrue(self.namespace['_attempt_confirmed_outbox_event_inner'](key))
            self.assertEqual(self.box[key]['state'], 'SENT')
            self.assertEqual(self.box[key]['discord_state'], 'SENT')
        self.assertEqual(self.discord_module.deliver.call_count, 3)
        self.assertEqual(self.telegram.call_count, 3)
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)

    def test_telegram_failure_cannot_post_to_discord(self):
        self.add_signal()
        self.telegram.return_value = False
        self.assertFalse(self.namespace['_attempt_confirmed_outbox_event_inner']('BTC'))
        self.discord_module.deliver.assert_not_called()
        self.assertEqual(self.box['BTC']['discord_state'], 'PENDING')
        self.assertEqual(self.box['BTC']['state'], 'FAILED_RETRYABLE')
        self.telegram.return_value = True
        self.box['BTC']['next_retry_at'] = 0
        self.assertTrue(self.namespace['_attempt_confirmed_outbox_event_inner']('BTC'))
        self.discord_module.deliver.assert_called_once()

    def test_discord_http_429_keeps_telegram_sent_and_retries(self):
        self.add_signal()
        self.discord_module.deliver.side_effect = [
            (False, 25, 'HTTP_429'), (True, 0, '')]
        self.assertTrue(self.namespace['_attempt_confirmed_outbox_event_inner']('BTC'))
        self.assertEqual(self.box['BTC']['state'], 'SENT')
        self.assertEqual(self.box['BTC']['discord_state'], 'FAILED_RETRYABLE')
        self.assertGreater(self.box['BTC']['discord_retry_at'], time.time())
        self.box['BTC']['discord_retry_at'] = 0
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 1)
        self.assertEqual(self.box['BTC']['discord_state'], 'SENT')
        self.assertEqual(self.telegram.call_count, 1)

    def test_delayed_telegram_acked_event_is_explicitly_marked(self):
        self.add_signal(age=40 * 60)
        self.box['BTC']['state'] = 'SENT'
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 1)
        sent_text = self.discord_module.deliver.call_args.args[0]
        self.assertIn('ENTREGA DIFERIDA', sent_text)
        self.assertIn('NUEVA SEÑAL CONFIRMADA', sent_text)

    def test_no_legacy_replay_and_no_three_hour_old_signals(self):
        self.add_signal('OLD', age=60)
        self.box['OLD'].pop('discord_state')
        self.add_signal('STALE', age=3 * 3600)
        self.box['STALE']['state'] = 'SENT'
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)
        self.discord_module.deliver.assert_not_called()

    def test_lock_prevents_overlapping_discord_sender(self):
        self.add_signal()
        self.box['BTC']['state'] = 'SENT'
        lock = self.namespace['_confirmed_discord_delivery_lock']
        lock.acquire()
        try:
            self.assertFalse(self.namespace['_deliver_discord_confirmed_for_key']('BTC'))
        finally:
            lock.release()
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 1)
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)
        self.discord_module.deliver.assert_called_once()

    def test_guardian_drains_before_early_future_none(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        block = source[source.index('def monitor_guardian_telegram_loop():'):
                       source.index('\n# COMMIT 31 — SPOT GUARDIAN', source.index('def monitor_guardian_telegram_loop():'))]
        self.assertLess(block.index('_retry_discord_confirmed_only(limit=2)'),
                        block.index('if futures_market is None:'))
        self.assertLess(block.index('drain_telegram_mirror(max_items=2)'),
                        block.index('if futures_market is None:'))
        self.assertEqual(block.count('_retry_discord_confirmed_only(limit=2)'), 1)


if __name__ == '__main__':
    unittest.main()
