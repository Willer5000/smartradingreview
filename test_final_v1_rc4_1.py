import unittest
from unittest.mock import MagicMock

from q6_integrity import spot_cell_active, verified_spot_current
from cohort_integrity import futures_cell_active, classify_quality_signal
from supabase_client import SupabaseClient


def spot_row(tf='4h'):
    return {
        'system_type': 'spot', 'symbol': 'BTC-USDT', 'timeframe': tf,
        'context': {'learning': {
            'cohort': 'SPOT_REAL_CLOSED_Q6',
            'market_data_source': 'KUCOIN_SPOT_REST',
            'market_data_is_synthetic': False,
            'source_candle_closed': True,
            'analysis_version': 'spot_closed_q6_v1',
            'source_candle_timestamp': '2026-09-14T00:00:00+00:00',
            'source_candle_close_timestamp': '2026-09-14T04:00:00+00:00',
            'statistically_eligible': True,
        }}
    }


class RC41IntegrityTests(unittest.TestCase):
    def test_spot_active_contract(self):
        self.assertTrue(spot_cell_active('BTC-USDT','4h'))
        self.assertTrue(spot_cell_active('PAXG-BTC','1W'))
        self.assertFalse(spot_cell_active('BTC-USDT','15m'))
        self.assertFalse(verified_spot_current(spot_row('15m')))
        self.assertTrue(verified_spot_current(spot_row('4h')))

    def test_futures_active_contract(self):
        self.assertTrue(futures_cell_active('XRP-USDT','4h'))
        self.assertFalse(futures_cell_active('XRP-USDT','1D'))
        self.assertTrue(futures_cell_active('BTC-USDT','1D'))
        self.assertFalse(futures_cell_active('BTC-USDT','15m'))

    def test_retired_spot_classifies_legacy(self):
        info = classify_quality_signal(spot_row('15m'), spot_verified=True)
        self.assertEqual(info['cohort'], 'LEGACY_ARCHIVE')
        self.assertFalse(info['official'])

    def test_ttl_cleanup_is_non_destructive(self):
        db = SupabaseClient.__new__(SupabaseClient)
        db.enabled = True
        db.preview_old_signals_by_tf = MagicMock(return_value=3)
        result = db.apply_ttl_cleanup()
        self.assertEqual(result['deleted'], 0)
        self.assertEqual(result['policy'], 'NON_DESTRUCTIVE_AUDIT_ONLY')
        self.assertGreater(result['candidate_total'], 0)


if __name__ == '__main__':
    unittest.main()
