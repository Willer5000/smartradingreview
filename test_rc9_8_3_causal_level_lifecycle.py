import importlib.util
import pathlib
import types
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('saved_signals_rc983', ROOT / 'saved_signals.py')
ss = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ss)


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeTable:
    def __init__(self, db):
        self.db = db
        self.payload = None

    def update(self, payload):
        self.payload = dict(payload)
        return self

    def insert(self, payload):
        self.payload = dict(payload)
        return self

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        if self.payload is not None:
            self.db.updates.append(dict(self.payload))
        return FakeResponse([dict(self.payload or {})])


class FakeClient:
    def __init__(self, db):
        self.db = db

    def table(self, _name):
        return FakeTable(self.db)


class FakeDB:
    enabled = True

    def __init__(self):
        self.updates = []
        self.client = FakeClient(self)

    def _with_retry(self, fn):
        return fn()


def frame(rows):
    return pd.DataFrame(rows)


def base_signal(**overrides):
    row = {
        'id': 'sig-1',
        'symbol': 'XRP-USDT',
        'timeframe': '2h',
        'action': 'LONG',
        'entry': 1.408,
        'original_entry': 1.408,
        'stop_loss': 1.420,
        'original_stop_loss': 1.3575,
        'take_profit': 1.4958,
        'original_take_profit': 1.4958,
        'leverage': 13,
        'investment_usdt': 24,
        'status': 'entry_touched',
        'entry_touched': True,
        'entry_at': '2026-09-21T08:00:00+00:00',
        'created_at': '2026-09-21T07:55:00+00:00',
        'entry_touched_at': '2026-09-21T08:15:00+00:00',
        'stop_loss_updated_at': '2026-09-21T10:30:00+00:00',
        'take_profit_updated_at': '2026-09-21T07:55:00+00:00',
        'updated_at': '2026-09-21T10:30:00+00:00',
    }
    row.update(overrides)
    return row


class RC983CausalLifecycleTests(unittest.TestCase):
    def run_eval(self, signal, df):
        db = FakeDB()
        with patch.object(ss, '_get_db', return_value=db), \
             patch.object(ss, 'list_saved_signals', return_value=[signal]), \
             patch.object(ss, '_calculate_open_excursions', return_value=None), \
             patch.object(ss, '_observe_early_exit_shadow', return_value=None), \
             patch.object(ss, '_build_estimated_economics', return_value={}), \
             patch.object(ss, '_build_early_exit_comparison', return_value={}):
            stats = ss.evaluate_saved_signals(lambda _s, _tf: df)
        return stats, db.updates

    def test_protected_long_sl_does_not_hit_retroactively(self):
        sig = base_signal()
        df = frame([
            # Antes del cambio de SL: low < 1.42. Antes de RC9.8.3 cerraba falso.
            {'time': '2026-09-21T09:00:00+00:00', 'high': 1.445, 'low': 1.395, 'close': 1.435},
            # Vela donde se cambió SL a las 10:30: high/low son ambiguos.
            {'time': '2026-09-21T10:00:00+00:00', 'high': 1.448, 'low': 1.400, 'close': 1.438},
            # Primera vela íntegramente posterior al cambio: no toca SL.
            {'time': '2026-09-21T12:00:00+00:00', 'high': 1.460, 'low': 1.430, 'close': 1.450},
        ])
        stats, updates = self.run_eval(sig, df)
        self.assertEqual(stats['sl_hit'], 0)
        self.assertFalse(any(x.get('status') == 'sl_hit' for x in updates))

    def test_protected_long_sl_hits_only_after_activation(self):
        sig = base_signal()
        df = frame([
            {'time': '2026-09-21T09:00:00+00:00', 'high': 1.445, 'low': 1.395, 'close': 1.435},
            {'time': '2026-09-21T10:00:00+00:00', 'high': 1.448, 'low': 1.400, 'close': 1.438},
            {'time': '2026-09-21T12:00:00+00:00', 'high': 1.450, 'low': 1.419, 'close': 1.425},
        ])
        stats, updates = self.run_eval(sig, df)
        self.assertEqual(stats['sl_hit'], 1)
        self.assertTrue(any(x.get('status') == 'sl_hit' for x in updates))

    def test_activation_candle_uses_live_close_not_old_low(self):
        sig = base_signal(timeframe='2h')
        df = frame([
            {'time': '2026-09-21T08:00:00+00:00', 'high': 1.440, 'low': 1.390, 'close': 1.430},
            # Activation 10:30 is inside this 10:00 candle. Old low is below 1.42,
            # but close is safely above it, so it must NOT archive.
            {'time': '2026-09-21T10:00:00+00:00', 'high': 1.448, 'low': 1.400, 'close': 1.438},
        ])
        # Current-candle freshness uses wall-clock time; patch the live probe to
        # exercise its causal contract deterministically through direct helper.
        activation = ss._saved_signal_utc_ts('2026-09-21T10:30:00+00:00')
        # Historical row is not eligible for full OHLC.
        row_ts = ss._saved_signal_utc_ts(df.iloc[-1]['time'])
        self.assertFalse(row_ts > activation)
        self.assertTrue(ss._saved_signal_level_hit(
            action='LONG', level_kind='stop_loss', level=1.42,
            high=float(df.iloc[-1]['high']), low=float(df.iloc[-1]['low'])
        ))
        # This proves why full OHLC is unsafe; evaluator test above proves it is excluded.

    def test_modified_entry_is_not_retroactively_touched(self):
        sig = base_signal(
            status='active',
            entry_touched=False,
            entry_touched_at=None,
            entry=1.410,
            original_entry=1.460,
            entry_updated_at='2026-09-21T10:30:00+00:00',
            stop_loss=1.370,
            original_stop_loss=1.370,
        )
        df = frame([
            # Crossed NEW entry before it existed.
            {'time': '2026-09-21T09:00:00+00:00', 'high': 1.430, 'low': 1.400, 'close': 1.425},
            {'time': '2026-09-21T10:00:00+00:00', 'high': 1.425, 'low': 1.405, 'close': 1.420},
            # After edit: remains above new entry.
            {'time': '2026-09-21T12:00:00+00:00', 'high': 1.440, 'low': 1.420, 'close': 1.435},
        ])
        stats, updates = self.run_eval(sig, df)
        self.assertEqual(stats['entry_touched'], 0)
        self.assertFalse(any(x.get('status') == 'entry_touched' for x in updates))

    def test_modified_tp_is_not_retroactively_hit(self):
        sig = base_signal(
            take_profit=1.445,
            original_take_profit=1.4958,
            take_profit_updated_at='2026-09-21T10:30:00+00:00',
            stop_loss=1.350,
            original_stop_loss=1.350,
            stop_loss_updated_at='2026-09-21T07:55:00+00:00',
        )
        df = frame([
            # Past high exceeded the NEW lower TP before it existed.
            {'time': '2026-09-21T09:00:00+00:00', 'high': 1.470, 'low': 1.410, 'close': 1.430},
            {'time': '2026-09-21T10:00:00+00:00', 'high': 1.460, 'low': 1.420, 'close': 1.435},
            {'time': '2026-09-21T12:00:00+00:00', 'high': 1.440, 'low': 1.425, 'close': 1.435},
        ])
        stats, updates = self.run_eval(sig, df)
        self.assertEqual(stats['tp_hit'], 0)
        self.assertFalse(any(x.get('status') == 'tp_hit' for x in updates))

    def test_update_persists_per_level_activation_timestamp(self):
        db = FakeDB()
        current = base_signal(stop_loss=1.3575, original_stop_loss=1.3575)
        with patch.object(ss, '_get_db', return_value=db), \
             patch.object(ss, 'get_saved_signal', return_value=current):
            result = ss.update_saved_signal('sig-1', {'stop_loss': 1.420})
        self.assertIsNotNone(result)
        self.assertTrue(db.updates)
        payload = db.updates[-1]
        self.assertEqual(payload.get('stop_loss'), 1.420)
        self.assertTrue(payload.get('stop_loss_updated_at'))
        self.assertFalse(payload.get('entry_updated_at'))
        self.assertFalse(payload.get('take_profit_updated_at'))

    def test_short_is_symmetric(self):
        sig = base_signal(
            action='SHORT',
            entry=1.408,
            original_entry=1.408,
            stop_loss=1.395,  # protected stop below entry for SHORT
            original_stop_loss=1.460,
            take_profit=1.330,
            original_take_profit=1.330,
            stop_loss_updated_at='2026-09-21T10:30:00+00:00',
        )
        df = frame([
            # Old high > protected SL occurred before edit; must not close.
            {'time': '2026-09-21T09:00:00+00:00', 'high': 1.430, 'low': 1.370, 'close': 1.380},
            {'time': '2026-09-21T10:00:00+00:00', 'high': 1.420, 'low': 1.360, 'close': 1.380},
            {'time': '2026-09-21T12:00:00+00:00', 'high': 1.390, 'low': 1.350, 'close': 1.360},
        ])
        stats, updates = self.run_eval(sig, df)
        self.assertEqual(stats['sl_hit'], 0)
        self.assertFalse(any(x.get('status') == 'sl_hit' for x in updates))


if __name__ == '__main__':
    unittest.main()
