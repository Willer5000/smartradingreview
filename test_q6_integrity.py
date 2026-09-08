"""Offline regression tests: python -m unittest -v test_q6_integrity.

Uses synthetic fixtures ONLY in tests; never writes production data.
Requires the project's requirements. Network is blocked during the tests.
"""
import ast
import contextlib
import io
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

os.environ['DISABLE_WARMUP'] = '1'
os.environ['DISABLE_SCHEDULER'] = '1'
for key in list(os.environ):
    if key.startswith(('SUPABASE_', 'GROQ_', 'GEMINI_', 'GOOGLE_', 'TELEGRAM_')):
        os.environ.pop(key, None)

import pandas as pd
from q6_integrity import (prepare_spot_frame, verified_spot, SPOT_SOURCE,
    SPOT_COHORT, SPOT_VERSION, read_pages, daily_slot, claim_daily_job, finish_daily_job)

ROOT = Path(__file__).resolve().parent


def frame():
    data = pd.DataFrame({'time': pd.date_range('2026-09-01', periods=181, freq='h'),
                         'open': 100., 'high': 102., 'low': 98., 'close': 101., 'volume': 10.})
    data.attrs = {'market_data_source': SPOT_SOURCE, 'market_data_is_synthetic': False}
    return data


class Query:
    def __init__(self, data, cap=200, error_offset=None):
        self.data, self.cap, self.error_offset = data, cap, error_offset
        self.start, self.end = 0, len(data)
    def range(self, start, end):
        self.start, self.end = start, end
        return self
    def execute(self):
        if self.start == self.error_offset:
            raise RuntimeError('test database outage')
        return SimpleNamespace(data=self.data[self.start:min(self.end+1, self.start+self.cap)])


class DataContracts(unittest.TestCase):
    def test_active_previous_have_distinct_closed_sources(self):
        raw = frame()
        active = prepare_spot_frame(raw, '1h', now='2026-09-08T12:30:00Z')
        previous = prepare_spot_frame(raw, '1h', previous=True, now='2026-09-08T12:30:00Z')
        self.assertEqual(active.attrs['source_candle_timestamp'], '2026-09-08T11:00:00+00:00')
        self.assertEqual(previous.attrs['source_candle_timestamp'], '2026-09-08T10:00:00+00:00')
        previous.iloc[-1, previous.columns.get_loc('close')] = 99
        self.assertEqual(active['close'].iloc[-2], 101)
        self.assertEqual(len(raw), 181)

    def test_no_open_row_is_not_dropped_blindly(self):
        raw = frame().iloc[:-1].copy()
        active = prepare_spot_frame(raw, '1h', now='2026-09-08T12:30:00Z')
        self.assertEqual(len(raw), len(active))

    def test_previous_override_is_idempotent(self):
        previous = prepare_spot_frame(frame(), '1h', True, '2026-09-08T12:30:00Z')
        again = prepare_spot_frame(previous, '1h', now='2026-09-08T12:30:00Z')
        self.assertEqual(previous.attrs, again.attrs)
        self.assertTrue(previous.equals(again))

    def test_invalid_data_rejected(self):
        for kind in ('synthetic', 'unknown', 'nan', 'negative', 'duplicate', 'geometry', 'stale'):
            with self.subTest(kind=kind):
                raw = frame()
                if kind == 'synthetic': raw.attrs['market_data_is_synthetic'] = True
                if kind == 'unknown': raw.attrs.clear()
                if kind == 'nan': raw.loc[0, 'close'] = float('nan')
                if kind == 'negative': raw.loc[0, 'volume'] = -1
                if kind == 'duplicate': raw.loc[1, 'time'] = raw.loc[0, 'time']
                if kind == 'geometry': raw.loc[0, 'high'] = 90
                if kind == 'stale': raw = raw.iloc[:-4].copy()
                with self.assertRaises(ValueError):
                    prepare_spot_frame(raw, '1h', now='2026-09-08T12:30:00Z')

    def test_pagination_respects_server_cap(self):
        rows = [{'id': str(i)} for i in range(21)]
        result = read_pages(lambda: Query(rows, cap=3), page_size=10, max_rows=30)
        self.assertEqual(len(result), 21)
        self.assertTrue(result.coverage['complete'])

    def test_pagination_exact_limit_and_truncation(self):
        for count, complete in ((20, True), (21, False)):
            rows = [{'id': str(i)} for i in range(count)]
            result = read_pages(lambda: Query(rows), page_size=10, max_rows=20)
            self.assertEqual(result.coverage['complete'], complete)
            self.assertEqual(len(result), 20)

    def test_partial_error_does_not_claim_complete(self):
        rows = [{'id': str(i)} for i in range(25)]
        result = read_pages(lambda: Query(rows, error_offset=10), page_size=10)
        self.assertFalse(result.coverage['complete'])
        self.assertEqual(len(result), 10)

    def test_daily_slot_recovers_after_midnight(self):
        now = datetime(2026, 9, 9, 5, tzinfo=timezone.utc)
        self.assertEqual(daily_slot(now), '2026-09-08')
        self.assertEqual(daily_slot(now.replace(hour=0)), '2026-09-08')

    def test_daily_claim_is_persistent_and_fails_closed(self):
        db = SimpleNamespace(enabled=True, client=MagicMock())
        self.assertTrue(claim_daily_job(db, 'AI_LEARNING', '2026-09-08'))
        db.client.table.return_value.insert.return_value.execute.side_effect = RuntimeError('duplicate key')
        self.assertFalse(claim_daily_job(db, 'AI_LEARNING', '2026-09-08'))
        self.assertFalse(claim_daily_job(SimpleNamespace(enabled=False), 'REVIEW', '2026-09-08'))
        db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {'status': 'DONE', 'updated_at': datetime.now(timezone.utc).isoformat()}]
        self.assertFalse(claim_daily_job(db, 'REVIEW', '2026-09-08', retry=True))


class ProductionIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import requests
        cls.network = patch.object(requests.Session, 'request', side_effect=RuntimeError('offline test'))
        cls.network.start()
        with contextlib.redirect_stdout(io.StringIO()):
            import app
            import review_trader
            import analytics_service
            import pdf_learning_report
            import futures_system
        cls.app, cls.review = app, review_trader
        cls.analytics, cls.pdf, cls.futures = analytics_service, pdf_learning_report, futures_system

    @classmethod
    def tearDownClass(cls):
        cls.network.stop()

    def review_instance(self):
        return self.review.ReviewTrader.__new__(self.review.ReviewTrader)

    def test_full_app_import_and_health(self):
        response = self.app.app.test_client().get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.futures.futures_system)

    def test_market_templates_render(self):
        for route in ('/', '/futures'):
            response = self.app.app.test_client().get(route)
            self.assertEqual(response.status_code, 200)

    def test_real_spot_pipeline_keeps_closed_provenance(self):
        raw = frame()
        current_open = pd.Timestamp.now(tz='UTC').floor('h').tz_localize(None)
        raw['time'] = pd.date_range(end=current_open, periods=len(raw), freq='h')
        expected = pd.Timestamp(raw['time'].iloc[-2], tz='UTC').isoformat()
        system = self.app.TradingExpertSystem()
        with patch.object(system, 'get_kucoin_data', return_value=raw), \
             contextlib.redirect_stdout(io.StringIO()):
            result = system.analyze_full_market('BTC-USDT', '1h', btc_analysis={'test':True})
        self.assertTrue(result.get('success'), result.get('error'))
        self.assertEqual(result['source_candle_timestamp'], expected)
        self.assertTrue(result['source_candle_closed'])
        self.assertFalse(result['market_data_is_synthetic'])

    def test_raw_fetch_failure_cannot_invoke_synthetic_fallback(self):
        system = self.app.TradingExpertSystem()
        with patch('kucoin_cache.fetch_kucoin_candles', return_value=None), patch.object(system, '_generate_fallback_data') as fake:
            self.assertIsNone(system.get_kucoin_data('BTC-USDT', '1h'))
            fake.assert_not_called()

    def test_spot_data_failure_returns_structured_error(self):
        system = self.app.TradingExpertSystem()
        with patch.object(system, 'get_kucoin_data', return_value=None), contextlib.redirect_stdout(io.StringIO()):
            result = system.analyze_full_market('BTC-USDT', '1h', btc_analysis={'test': True})
        self.assertFalse(result['success'])
        self.assertEqual(result['data_status'], 'UNAVAILABLE')

    def test_spot_legacy_and_replay_cannot_vote_from_history(self):
        review = self.review_instance()
        source = prepare_spot_frame(frame(), '1h', now='2026-09-08T12:30:00Z')
        analysis = dict(source.attrs)
        learning = review._build_learning_provenance(analysis, 'spot')
        row = {'system_type': 'spot', 'context': {'learning': learning}}
        self.assertTrue(verified_spot(row))
        self.assertTrue(review._is_signal_eligible_for_profit_stats(row))
        self.assertFalse(review._is_signal_eligible_for_profit_stats({'system_type': 'spot'}))
        analysis['analysis_mode'] = 'PREVIOUS_CLOSED_CANDLE'
        replay = review._build_learning_provenance(analysis, 'spot')
        self.assertFalse(replay['statistically_eligible'])
        self.assertEqual(replay['evaluation_role'], 'SPOT_PREVIOUS_REPLAY')

    def test_pdf_quarantines_unverified_spot_and_uses_observed_pnl(self):
        cohorts = self.pdf._split_learning_cohorts([{'system_type': 'spot'}])
        self.assertEqual(len(cohorts['spot']), 0)
        self.assertEqual(len(cohorts['spot_legacy']), 1)
        row = {'status':'tp_hit','entry_price':100,'stop_loss':95,'take_profit':110,
               'action_normalized':'LONG'}
        self.assertEqual(self.pdf._outcome_values(row), (None, None))
        row['signal_results'] = [{'pnl_pct': 7}]
        self.assertEqual(self.pdf._outcome_values(row), (7, 1.4))

    def test_analytics_no_results_is_not_zero_winrate(self):
        metrics = self.analytics.AnalyticsService._q5_aggregate([])
        self.assertIsNone(metrics['win_rate'])
        self.assertIsNone(metrics['expectancy_r'])
        self.assertIsNone(metrics['profit_factor'])

    def test_cache_payloads_are_independent(self):
        original = {'levels': {'entry': 100}, 'system_type': 'futures'}
        key = ('Q6_TEST', '1h')
        self.app._analysis_cache_put(key, original)
        original['levels']['entry'] = 200
        first = self.app._analysis_cache_get(key)
        first['levels']['entry'] = 300
        self.assertEqual(self.app._analysis_cache_get(key)['levels']['entry'], 100)

    def test_analysis_only_preserves_levels(self):
        levels = {'entry':100, 'stop_loss':95, 'take_profit':110}
        result = self.futures.futures_system._mark_levels_non_executable(levels, 'test')
        for key in levels:
            self.assertEqual(result[key], levels[key])
        self.assertFalse(result['is_executable'])

    def test_no_tp_before_entry_and_intrabar_ambiguity(self):
        review = self.review_instance()
        signal = {'action_normalized':'LONG', 'entry_price':100, 'stop_loss':95, 'take_profit':110}
        start = datetime(2026, 9, 8)
        df = pd.DataFrame([{'time':start,'open':105,'high':112,'low':103,'close':108}])
        result = review._check_tp_sl_hit(signal, df, start, start+timedelta(hours=2), True)
        self.assertEqual(result['status'], 'pending_no_entry')
        df.loc[0, 'low'] = 94
        result = review._check_tp_sl_hit(signal, df, start, start+timedelta(hours=2), True)
        self.assertEqual(result['status'], 'ambiguous')

    def test_duplicate_shadow_function_removed(self):
        tree = ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
        names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        self.assertEqual(names.count('_evaluate_36s_spot_tgp_shadow'), 1)

    def test_same_candle_entry_then_tp_is_not_assumed(self):
        review = self.review_instance()
        start = datetime(2026, 9, 8)
        for action, candle in (
            ('LONG', {'open':105, 'high':112, 'low':99, 'close':101}),
            ('SHORT', {'open':95, 'high':101, 'low':88, 'close':99}),
        ):
            signal = {'action_normalized':action, 'entry_price':100,
                      'stop_loss':95 if action == 'LONG' else 105,
                      'take_profit':110 if action == 'LONG' else 90}
            data = pd.DataFrame([{'time':start, **candle}])
            result = review._check_tp_sl_hit(signal, data, start, start+timedelta(hours=2), True)
            self.assertEqual(result['status'], 'ambiguous')

    def test_result_write_failure_leaves_signal_pending(self):
        from supabase_client import SupabaseClient
        db = SupabaseClient.__new__(SupabaseClient)
        db.enabled, db.client = True, MagicMock()
        db._check_rotation = MagicMock()
        db.client.table.return_value.upsert.return_value.execute.side_effect = RuntimeError('offline write failure')
        with self.assertLogs('SUPABASE', level='ERROR'):
            self.assertFalse(db.update_signal_result('test', {'status':'tp_hit', 'exit_timestamp':'2026-09-08T01:00:00Z'}))
        db.client.table.return_value.update.assert_not_called()

    def test_result_retry_has_stable_identity(self):
        from supabase_client import SupabaseClient
        db = SupabaseClient.__new__(SupabaseClient)
        db.enabled, db.client = True, MagicMock()
        db._check_rotation = MagicMock()
        result = {'status':'tp_hit', 'exit_timestamp':'2026-09-08T01:00:00Z'}
        self.assertTrue(db.update_signal_result('test', result))
        self.assertTrue(db.update_signal_result('test', result))
        calls = db.client.table.return_value.upsert.call_args_list
        self.assertEqual(calls[0].args[0]['id'], calls[1].args[0]['id'])

    def test_header_filters_market_candle_and_direction(self):
        import supabase_client
        class HeaderQuery:
            def __init__(self): self.filters = []
            def table(self, name): return self
            def select(self, fields): return self
            def eq(self, field, value): self.filters.append((field, value)); return self
            def in_(self, *args): return self
            def order(self, *args, **kwargs): return self
            def limit(self, n): return self
            def execute(self): return SimpleNamespace(data=[])
        query = HeaderQuery()
        db = SimpleNamespace(client=query, normalize_action=lambda value:value)
        signals = [dict(symbol='BTC-USDT', timeframe='1h', action='LONG',
                        candle_timestamp='2026-09-08T01:00:00Z', activa=1, system=market)
                   for market in ('spot', 'futures')]
        with patch.object(self.app, '_collect_frontend_signals', return_value=signals), \
             patch.object(supabase_client, 'supabase_db', db):
            response = self.app.app.test_client().get('/api/kpis/frontend_signals?system_type=futures')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        self.assertEqual(data['total_spot'], 0)
        self.assertEqual(data['total_futures'], 1)
        self.assertIn(('candle_timestamp', '2026-09-08T01:00:00+00:00'), query.filters)
        self.assertIn(('action_normalized', 'LONG'), query.filters)


if __name__ == '__main__':
    unittest.main(verbosity=2)
