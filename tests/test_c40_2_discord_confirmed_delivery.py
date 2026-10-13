"""C40.2: independent official Discord delivery tests without Flask/network.

Real production functions are AST-loaded from the replacement app.py, with
stubbed outbox persistence and a fake Discord transport. No trading logic is
altered and no actual webhook is contacted.
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
FUNCTIONS = ('_discord_confirmed_delivery_optional',
             '_retry_discord_confirmed_only', '_confirmed_outbox_enqueue')


def load_functions():
    source = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    nodes = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name in FUNCTIONS]
    if len(nodes) != len(FUNCTIONS):
        raise AssertionError('Missing expected official Discord function')
    code = compile(ast.Module(body=nodes, type_ignores=[]), '<app.py AST>', 'exec')
    return code


class DiscordC402Test(unittest.TestCase):
    def setUp(self):
        self.module = types.ModuleType('discord_confirmed')
        self.module.enabled = lambda: True
        self.module.deliver = Mock(return_value=(True, 0, ''))
        self.modules_patch = patch.dict(sys.modules, {'discord_confirmed': self.module})
        self.modules_patch.start()
        self.env_patch = patch.dict(os.environ, {
            'DISCORD_CONFIRMED_WEBHOOK_URL': 'https://discord.com/api/webhooks/1234/testToken',
        })
        self.env_patch.start()
        self.box = {}
        self.saves = Mock(return_value=True)
        self.valid = Mock(return_value=False)
        self.namespace = {
            'os': os,
            'time': time,
            'threading': threading,
            '_confirmed_signal_outbox': self.box,
            '_confirmed_signal_outbox_lock': threading.Lock(),
            '_confirmed_discord_delivery_lock': threading.Lock(),
            '_save_confirmed_signal_outbox_to_disk': self.saves,
            '_confirmed_delivery_valid_17_5_11': self.valid,
            '_build_confirmed_signal_telegram_message':
                lambda market, signal: f"✅ NUEVA SEÑAL CONFIRMADA {market} {signal['symbol']}",
            '_CONFIRMED_OUTBOX_LAST_RESTORE_MONO_35': time.monotonic(),
            '_load_confirmed_signal_outbox_from_disk': Mock(),
        }
        exec(load_functions(), self.namespace)

    def tearDown(self):
        self.modules_patch.stop()
        self.env_patch.stop()

    def event(self, symbol='BTC-USDT', telegram_state='SENT', discord_state='PENDING',
              age=60):
        return {
            'created_at': time.time() - age,
            'state': telegram_state,
            'discord_state': discord_state,
            'discord_retry_at': 0,
            '_c35_remote_persisted': True,
            'market': 'futures',
            'signal': {'symbol': symbol, 'timeframe': '30m',
                       'decision': {'action': 'SHORT', 'confidence': 88},
                       'levels': {'entry': 80000, 'stop_loss': 82000, 'take_profit': 77000,
                                  'publication_status': 'EXECUTABLE_SIGNAL'}},
        }

    def test_futures_confirmations_arrive_without_futures_lifecycle_thread(self):
        self.box['btc'] = self.event('BTC-USDT')
        self.box['bnb'] = self.event('BNB-USDT')
        count = self.namespace['_retry_discord_confirmed_only'](limit=2)
        self.assertEqual(count, 2)
        self.assertEqual(self.module.deliver.call_count, 2)
        self.assertEqual(self.box['btc']['discord_state'], 'SENT')
        self.assertEqual(self.box['bnb']['discord_state'], 'SENT')
        self.valid.assert_not_called()  # production Telegram ACK already validated

    def test_never_duplicate_confirmed_when_guardian_runs_again(self):
        self.box['btc'] = self.event()
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 1)
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)
        self.assertEqual(self.module.deliver.call_count, 1)

    def test_no_old_telegram_confirmations_replayed_on_deploy(self):
        self.box['old_without_discord_marker'] = self.event(discord_state=None)
        self.box['old_with_marker'] = self.event(age=1800)
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)
        self.module.deliver.assert_not_called()

    def test_telegram_failure_does_not_block_discord_when_signal_valid(self):
        self.box['btc'] = self.event(telegram_state='FAILED_RETRYABLE')
        self.valid.return_value = True
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 1)
        self.module.deliver.assert_called_once()

    def test_no_discord_if_telegram_failed_and_signal_invalid(self):
        self.box['btc'] = self.event(telegram_state='FAILED_RETRYABLE')
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)
        self.module.deliver.assert_not_called()

    def test_new_event_marks_discord_pending_but_does_not_send_unconfirmed(self):
        self.namespace.update({
            '_compact_confirmed_outbox_signal':
                lambda m, s: {'signal_id': 'sig123', 'symbol': 'BTC-USDT', 'timeframe': '30m'},
            '_confirmed_signal_outbox_lock': threading.Lock(),
        })
        store = types.ModuleType('official_signal_store')
        store.persist_official = Mock(return_value=True)
        with patch.dict(sys.modules, {'official_signal_store': store}):
            result = self.namespace['_confirmed_outbox_enqueue'](
                'futures', {'symbol': 'BTC-USDT'}, 'new-key')
        self.assertIsNotNone(result)
        self.assertEqual(self.box['new-key']['discord_state'], 'PENDING')
        self.module.deliver.assert_not_called()

    def test_discord_failure_remains_retryable_without_telegram_status_change(self):
        self.box['btc'] = self.event()
        self.module.deliver.return_value = (False, 10, 'HTTP_429')
        self.assertEqual(self.namespace['_retry_discord_confirmed_only'](), 0)
        self.assertEqual(self.box['btc']['state'], 'SENT')
        self.assertEqual(self.box['btc']['discord_state'], 'FAILED_RETRYABLE')
        self.assertEqual(self.box['btc']['discord_last_error'], 'HTTP_429')
        self.assertGreater(self.box['btc']['discord_retry_at'], time.time())


if __name__ == '__main__':
    unittest.main()
