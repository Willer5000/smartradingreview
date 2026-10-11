"""Commit36R regression gates: durability and UI-only optimizations.

No application import/network is needed; never mutate the trading engine.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import local_resilience as lr


class LocalSQLiteLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path, self.old_init = lr._DB_PATH, lr._INIT
        lr._DB_PATH = os.path.join(self.tmp.name, 'resilience.sqlite3')
        lr._INIT = False

    def tearDown(self):
        lr._DB_PATH, lr._INIT = self.old_path, self.old_init
        self.tmp.cleanup()

    def test_repeated_snapshot_writes_leave_no_open_sqlite_fds(self):
        """Previously `with sqlite3.Connection` didn't explicitly close it."""
        def count():
            try:
                return sum(1 for f in os.listdir('/proc/self/fd')
                           if 'resilience.sqlite3' in os.readlink('/proc/self/fd/' + f))
            except OSError:
                return None
        before = count()
        for i in range(80):
            data = {'id': 'official-example', 'immutable_levels': {'entry': 1.2, 'tp': 1.4, 'sl': 1.1},
                    'n': i, 'evidence': 'x' * 12288}
            self.assertTrue(lr.save_snapshot('official', 'id1', data, ttl_seconds=7200))
        row = lr.load_snapshot('official', 'id1')
        self.assertEqual(row['payload']['n'], 79)
        self.assertEqual(row['payload']['immutable_levels'], {'entry': 1.2, 'tp': 1.4, 'sl': 1.1})
        if before is not None:
            self.assertEqual(count(), before)

    def test_outbox_survives_reopen_and_is_idempotent(self):
        key = lr.enqueue_rest('POST', 'official_events', payload={'id': 'signal-X', 'market': 'futures'})
        self.assertEqual(key, lr.enqueue_rest('POST', 'official_events', payload={'id': 'signal-X', 'market': 'futures'}))
        rows = lr.pending_outbox(5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['payload']['id'], 'signal-X')
        lr.mark_outbox_error(key, 'temporary_error')
        self.assertEqual(lr.pending_outbox(5)[0]['attempts'], 1)
        lr.mark_outbox_done(key)
        self.assertEqual(lr.pending_outbox(5), [])

    def test_wal_is_bounded_under_repeated_overwrites(self):
        for i in range(120):
            self.assertTrue(lr.save_snapshot('analysis', 'snapshot', {'n':i, 'blob':'x'*6000}))
        wal = lr._DB_PATH + '-wal'
        if os.path.exists(wal):
            self.assertLess(os.stat(wal).st_size, 6 * 1024 * 1024)


class NoTradingAuthorityChanges(unittest.TestCase):
    def test_dashboard_only_spot_preview_poll_is_less_frequent(self):
        script = (ROOT / 'static' / 'script.js').read_text(encoding='utf8')
        self.assertIn("function updateActiveSignals()", script)
        self.assertIn("                    20000\n                );", script)
        self.assertIn("updateActiveSignals(), 25000", script)

    def test_all_official_signal_paths_remain_present(self):
        app = (ROOT / 'app.py').read_text(encoding='utf8')
        for path in ('_confirmed_outbox_enqueue', '_confirmed_web_registry_rows_34_4',
                     '_merge_official_telegram_rows_34_4', '_confirmed_outbox_terminal_technical_expired_34_4'):
            self.assertIn('def ' + path + '(', app)
        self.assertIn("'cgroup_breakdown':_commit36r_memory_breakdown()", app)


if __name__ == '__main__':
    unittest.main()
