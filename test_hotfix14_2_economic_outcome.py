import unittest

from saved_signals import _with_saved_signal_economic_outcome


class SavedSignalEconomicOutcomeTests(unittest.TestCase):
    def test_long_protected_sl_is_win_when_pnl_positive(self):
        row = _with_saved_signal_economic_outcome({
            'status': 'sl_hit',
            'entry_touched': True,
            'pnl_pct': 1.25,
        })
        self.assertEqual(row['gross_outcome'], 'WIN')
        self.assertEqual(row['economic_outcome'], 'WIN')
        self.assertTrue(row['protected_stop_exit'])

    def test_short_protected_sl_is_win_when_pnl_positive(self):
        row = _with_saved_signal_economic_outcome({
            'status': 'sl_hit',
            'entry_touched': True,
            'pnl_pct': 0.72,
        })
        self.assertEqual(row['gross_outcome'], 'WIN')
        self.assertTrue(row['protected_stop_exit'])

    def test_net_modeled_outcome_is_exposed_separately(self):
        row = _with_saved_signal_economic_outcome({
            'status': 'sl_hit',
            'entry_touched': True,
            'pnl_pct': 0.03,
            'estimated_net_pnl_pct': -0.01,
        })
        self.assertEqual(row['gross_outcome'], 'WIN')
        self.assertEqual(row['net_modeled_outcome'], 'LOSS')
        self.assertEqual(row['economic_outcome'], 'LOSS')
        self.assertEqual(row['economic_outcome_basis'], 'MODELED_NET')
        self.assertTrue(row['protected_stop_exit'])

    def test_signal_closed_without_entry_is_no_trade(self):
        row = _with_saved_signal_economic_outcome({
            'status': 'closed_manual',
            'entry_touched': False,
            'pnl_pct': 0,
        })
        self.assertEqual(row['economic_outcome'], 'NO_TRADE')
        self.assertFalse(row['protected_stop_exit'])


if __name__ == '__main__':
    unittest.main()
