import ast
from pathlib import Path
import unittest

import pandas as pd

APP_PATH = Path(__file__).with_name('app.py')


def _load_functions(*names):
    source = APP_PATH.read_text(encoding='utf-8')
    tree = ast.parse(source)
    wanted = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            wanted.append(node)
    found = {n.name for n in wanted}
    missing = set(names) - found
    if missing:
        raise AssertionError(f'Funciones faltantes: {sorted(missing)}')

    module = ast.Module(body=wanted, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        'pd': pd,
        '_FUTURES_TF_SECONDS': {'2h': 7200},
    }
    exec(compile(module, str(APP_PATH), 'exec'), ns)
    return [ns[name] for name in names]


class SignalRevalidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authority, reason, refresh = _load_functions(
            '_futures_current_entry_authority',
            '_futures_waiting_record_invalidation_reason',
            '_refresh_futures_signal_lifecycle',
        )
        cls.authority = staticmethod(authority)
        cls.reason = staticmethod(reason)
        cls.refresh = staticmethod(refresh)
        # _refresh only needs this helper when it creates a new record.
        refresh.__globals__['_futures_entry_wait_bars'] = lambda result, timeframe: 6

    def _waiting(self, action='LONG', close='2026-09-12T14:00:00+00:00'):
        return {
            'signal_id': 'old',
            'symbol': 'XRP-USDT',
            'timeframe': '2h',
            'action': action,
            'confidence': 86,
            'entry': 1.36,
            'stop_loss': 1.28,
            'take_profit': 1.56,
            'leverage': 3,
            'risk_reward': 2.5,
            'source_candle_timestamp': '2026-09-12T12:00:00+00:00',
            'source_candle_close_timestamp': close,
            'valid_until': '2099-01-01T00:00:00+00:00',
            'lifecycle_status': 'waiting_entry',
        }

    def _result(self, action='NO_OPERAR', close='2026-09-12T16:00:00+00:00', executable=False):
        levels = {
            'publication_status': 'EXECUTABLE_SIGNAL' if executable else 'ANALYSIS_ONLY',
        }
        if executable:
            levels.update({
                'entry': 1.37,
                'stop_loss': 1.30,
                'take_profit': 1.545,
                'leverage': 3,
                'risk_reward': 2.5,
            })
        return {
            'success': True,
            'decision': {'action': action, 'confidence': 88},
            'levels': levels,
            'signal_id': 'new' if executable else '',
            'source_candle_timestamp': '2026-09-12T14:00:00+00:00',
            'source_candle_close_timestamp': close,
            'live_price': 1.40,
            'analysis_price': 1.40,
            'analysis_mode': 'CLOSED_CANDLE',
        }

    def test_no_operar_invalidates_waiting_entry(self):
        record = self._waiting()
        result = self._result('NO_OPERAR', executable=False)
        self.assertEqual(
            self.reason(record, result),
            'CURRENT_RECOMMENDATION_NOT_EXECUTABLE',
        )

        lifecycle = self.refresh(
            {'old': record},
            'XRP-USDT',
            '2h',
            result,
        )
        self.assertEqual(
            lifecycle['old']['lifecycle_status'],
            'invalidated_before_entry',
        )
        self.assertEqual(
            lifecycle['old']['current_recommendation_action'],
            'NO_OPERAR',
        )

    def test_direction_change_invalidates_waiting_entry(self):
        record = self._waiting('LONG')
        result = self._result('SHORT', executable=True)
        self.assertEqual(
            self.reason(record, result),
            'CURRENT_RECOMMENDATION_DIRECTION_CHANGED',
        )

    def test_newer_closed_candle_supersedes_old_waiting_signal(self):
        record = self._waiting('LONG', '2026-09-12T14:00:00+00:00')
        result = self._result('LONG', '2026-09-12T16:00:00+00:00', executable=True)
        self.assertEqual(
            self.reason(record, result),
            'SUPERSEDED_BY_NEW_CLOSED_CANDLE',
        )
        lifecycle = self.refresh(
            {'old': record},
            'XRP-USDT',
            '2h',
            result,
        )
        self.assertEqual(lifecycle['old']['lifecycle_status'], 'invalidated_before_entry')
        self.assertEqual(lifecycle['new']['lifecycle_status'], 'waiting_entry')
        self.assertEqual(lifecycle['new']['entry'], 1.37)

    def test_same_closed_candle_same_action_is_preserved(self):
        record = self._waiting('LONG', '2026-09-12T16:00:00+00:00')
        result = self._result('LONG', '2026-09-12T16:00:00+00:00', executable=True)
        result['signal_id'] = 'old'
        self.assertIsNone(self.reason(record, result))

    def test_entry_touched_is_not_cancelled_retroactively(self):
        record = self._waiting('LONG')
        record['lifecycle_status'] = 'entry_touched'
        result = self._result('NO_OPERAR', executable=False)
        self.assertIsNone(self.reason(record, result))
        lifecycle = self.refresh(
            {'old': record},
            'XRP-USDT',
            '2h',
            result,
        )
        self.assertEqual(lifecycle['old']['lifecycle_status'], 'entry_touched')

    def test_data_error_does_not_cancel_waiting_signal(self):
        record = self._waiting('LONG')
        result = {'success': False, 'error': 'temporary'}
        self.assertIsNone(self.reason(record, result))

    def test_active_endpoint_has_defensive_mismatch_filter(self):
        source = APP_PATH.read_text(encoding='utf-8')
        self.assertIn("'recommendation_mismatch': 0", source)
        self.assertIn("if lifecycle_status == 'waiting_entry':", source)
        self.assertIn("filter_stats['recommendation_mismatch'] += 1", source)


if __name__ == '__main__':
    unittest.main()
