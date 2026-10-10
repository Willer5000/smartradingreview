"""Commit 34 consolidation smoke tests (no web/network/Flask dependency)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from commit34_lifecycle_contract import in_confirmation_window

UTC = timezone.utc
T0 = datetime(2026, 10, 10, 0, tzinfo=UTC)
HERE = Path(__file__).resolve().parent


class LifecycleContractTests(unittest.TestCase):
    def test_confirmed_twelve_hours_then_vigent(self):
        self.assertTrue(in_confirmation_window(T0, None, '12h', T0 + timedelta(hours=11, minutes=59)))
        self.assertFalse(in_confirmation_window(T0, None, '12h', T0 + timedelta(hours=12)))
        # Original valid_until is never manipulated by this classifier.

    def test_30m_boundary(self):
        self.assertTrue(in_confirmation_window(T0, None, '30m', T0 + timedelta(minutes=29)))
        self.assertFalse(in_confirmation_window(T0, None, '30m', T0 + timedelta(minutes=30)))

    def test_open_fallback(self):
        self.assertTrue(in_confirmation_window(None, T0, '1h', T0 + timedelta(hours=1, minutes=10)))
        self.assertFalse(in_confirmation_window(None, T0, '1h', T0 + timedelta(hours=2)))

    def test_future_close_rejected(self):
        self.assertFalse(in_confirmation_window(T0 + timedelta(hours=4), None, '4h', T0))

    def test_missing_timestamp_rejected(self):
        self.assertFalse(in_confirmation_window(None, None, '4h', T0))

    def test_all_futures_tfs(self):
        for tf, seconds in [('30m',1800),('1h',3600),('2h',7200),('4h',14400),('12h',43200),('1D',86400)]:
            self.assertTrue(in_confirmation_window(T0, None, tf, T0 + timedelta(seconds=seconds-1)))
            self.assertFalse(in_confirmation_window(T0, None, tf, T0 + timedelta(seconds=seconds)))

    def test_timezone_awareness(self):
        self.assertTrue(in_confirmation_window('2026-10-10T00:00:00Z', None, '1h', '2026-10-10T00:30:00+00:00'))


class ConsolidationStaticTests(unittest.TestCase):
    def test_memory_fetch_is_read_only_without_heavy(self):
        core=(HERE/'app.py').read_text()
        section=core.split('def api_futures_visuals():',1)[1].split("@app.route('/api/price')",1)[0]
        self.assertIn('_COMMIT34_VISUAL_FETCH_LOCK',section)
        self.assertIn('df_obj.tail(120)',section)
        self.assertIn('_vis_cgroup_limit',section)
        self.assertNotIn('analyze_full_market(',section)

    def test_new_confirmation_moves_by_clock(self):
        core=(HERE/'app.py').read_text()
        active=core.split('def api_futures_signals_active():',1)[1].split("@app.route('/api/futures/signals/previous')",1)[0]
        previous=core.split('def api_futures_signals_previous():',1)[1]
        self.assertIn('_commit34_confirmation_window_is_current(record, tf)',active)
        self.assertIn('_commit34_confirmation_window_is_current(result, tf)',previous)

    def test_bounded_browser_post_retry(self):
        js=(HERE/'static/script.js').read_text()
        self.assertIn('retryCount < 2',js)
        self.assertIn('loadSpotReadOnlyCharts',js)
        self.assertIn('Último cierre conocido',js)

    def test_only_empty_authority_not_live(self):
        import json
        m=json.loads((HERE/'commit34_live_authority.json').read_text())
        self.assertEqual(m.get('authorized_routes'),{})


if __name__=='__main__': unittest.main()
