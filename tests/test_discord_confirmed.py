import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('discord_confirmed', ROOT / 'discord_confirmed.py')
discord = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discord)


class TestDiscordWebhook(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(discord.enabled())
            self.assertEqual(discord.deliver('x')[2], 'DISABLED')

    def test_reject_non_discord_url(self):
        with patch.dict(os.environ, {'DISCORD_CONFIRMED_WEBHOOK_URL': 'https://example.com/steal'}):
            self.assertEqual(discord.deliver('x')[2], 'INVALID_WEBHOOK_URL')

    def test_message_schema_and_wait_ack(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch.dict(os.environ, {'DISCORD_CONFIRMED_WEBHOOK_URL': 'https://discord.com/api/webhooks/12345/abcDEF-token', 'DISCORD_CONFIRMED_NAME': 'Captain Hook'}):
            with patch.object(discord.urllib.request, 'urlopen', return_value=Response()) as mocked:
                self.assertTrue(discord.deliver('SOL-USDT LONG')[0])
                request = mocked.call_args.args[0]
                self.assertTrue(request.full_url.endswith('?wait=true'))
                self.assertIn(b'SOL-USDT LONG', request.data)
                self.assertIn(b'allowed_mentions', request.data)

    def test_no_direct_delivery_from_vigent(self):
        # Delivery originates only at the existing confirmation outbox, never
        # in the functions exposing /signals/active.
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertEqual(source.count('def _discord_confirmed_delivery_optional('), 1)
        self.assertIn('_confirmed_delivery_valid_17_5_11(market, signal)', source)
        self.assertIn('discord_state', source)
        self.assertIn('_retry_confirmed_signal_outbox', source)


if __name__ == '__main__':
    unittest.main()
