"""Commit 17.5.6 offline QA — execution quality + signal visibility.

Run from the complete SmartradingReview project after replacing app.py and
execution_specialist_committees.py:
    python qa_commit17_5_6_execution_quality_visibility.py

No exchange, DB, LLM or Telegram request is executed by this suite.
"""
from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / 'app.py'
COMMITTEE_PATH = ROOT / 'execution_specialist_committees.py'
APP = APP_PATH.read_text(encoding='utf-8')
COMMITTEE = COMMITTEE_PATH.read_text(encoding='utf-8')
APP_TREE = ast.parse(APP)


def app_source(name: str) -> str:
    hits = [n for n in ast.walk(APP_TREE) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(hits) != 1:
        raise AssertionError(f'{name}: expected exactly one function, got {len(hits)}')
    return ast.get_source_segment(APP, hits[0]) or ''


def load_committee():
    spec = importlib.util.spec_from_file_location('exec_committee_1756', COMMITTEE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class Commit1756QA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = load_committee()

    def test_01_files_compile(self):
        compile(APP, str(APP_PATH), 'exec')
        compile(COMMITTEE, str(COMMITTEE_PATH), 'exec')

    def test_02_version_and_hard_guard_exported(self):
        self.assertEqual(self.c.VERSION, 'COMMIT17_5_6_EXECUTION_QUALITY_VISIBILITY_V1')
        self.assertTrue(callable(self.c.evaluate_sl_reaction_conflict))

    def test_03_long_sl_on_strong_support_is_conflict(self):
        st = {'supports':[98.0, 98.02], 'pivot_lows':[{'price':98.01,'strength':3}]}
        got = self.c.evaluate_sl_reaction_conflict(structure=st, direction='long', entry=100, stop_loss=98.0, atr=1.0)
        self.assertTrue(got['conflict'])
        self.assertEqual(got['reason'], 'SL_INSIDE_STRONG_REACTION_ZONE')

    def test_04_long_sl_beyond_support_is_clear(self):
        st = {'supports':[98.0, 98.02], 'pivot_lows':[{'price':98.01,'strength':3}]}
        got = self.c.evaluate_sl_reaction_conflict(structure=st, direction='long', entry=100, stop_loss=97.5, atr=1.0)
        self.assertFalse(got['conflict'])

    def test_05_short_sl_on_strong_resistance_is_conflict(self):
        st = {'resistances':[102.0, 102.02], 'pivot_highs':[{'price':102.01,'strength':3}]}
        got = self.c.evaluate_sl_reaction_conflict(structure=st, direction='short', entry=100, stop_loss=102.0, atr=1.0)
        self.assertTrue(got['conflict'])

    def test_06_short_sl_beyond_resistance_is_clear(self):
        st = {'resistances':[102.0, 102.02], 'pivot_highs':[{'price':102.01,'strength':3}]}
        got = self.c.evaluate_sl_reaction_conflict(structure=st, direction='short', entry=100, stop_loss=102.5, atr=1.0)
        self.assertFalse(got['conflict'])

    def test_07_committee_filters_conflicting_stops_before_selection(self):
        src = COMMITTEE
        self.assertIn('filtered_sl_candidates = []', src)
        self.assertIn('sl_reaction_rejections += 1', src)
        self.assertIn('sl_candidates = filtered_sl_candidates', src)

    def test_08_final_derivatives_geometry_has_same_hard_guard(self):
        src = app_source('calculate_entry_levels')
        self.assertIn('evaluate_sl_reaction_conflict', src)
        self.assertIn("if is_futures and sl_reaction_guard.get('conflict')", src)
        self.assertIn('SL no defendible', src)

    def test_09_guard_error_is_fail_safe_not_fail_open(self):
        src = app_source('calculate_entry_levels')
        anchor = src.index('SL_REACTION_GUARD_ERROR')
        self.assertIn("'conflict': True", src[max(0, anchor-400):anchor+200])

    def test_10_original_refinement_quality_bounds_remain(self):
        src = app_source('calculate_entry_levels')
        for token in (
            'values[4] >= 1.50', 'values[3] >= 62.0', 'values[5] >= 55.0',
            'values[6] >= 60.0', 'values[7] >= 60.0',
            '0.82 <= risk / max(baseline_risk, 1e-12) <= 1.18',
            '_rr_safety_bucket(rr_candidate) == _rr_safety_bucket(baseline_rr)',
        ):
            self.assertIn(token, src)

    def test_11_downstream_execution_setup_guard_still_participates(self):
        src = app_source('calculate_entry_levels')
        self.assertIn('execution_setup_guard as _execution_setup_guard', src)
        self.assertIn('candidate_guard = _execution_setup_guard', src)
        self.assertIn("if candidate_guard.get('applied')", src)

    def test_12_fast_lane_1h_uses_own_closed_router(self):
        src = app_source('_multiasset_background_tick')
        self.assertIn("rows_1h=_multiasset_scan('1h'", src)
        self.assertIn("float(r.get('router_score') or 0) >= _MULTI_FAST_LANE_MIN_SCORE", src)
        self.assertNotIn("plan['1h']['due'] and top_score >= 82", src)

    def test_13_no_new_separate_daily_fast_lane_quota(self):
        self.assertIn('_MULTI_FAST_LANE_MIN_SCORE = 82.0', APP)
        self.assertNotIn('_MULTI_FAST_LANE_DAILY_MAX', APP)
        src = app_source('_multiasset_background_tick')
        self.assertNotIn("fast_count') or 0) >=", src)

    def test_14_existing_global_resource_guard_is_preserved(self):
        src = app_source('_multiasset_background_tick')
        self.assertIn('MULTIASSET_AUTO_DEEP_DAILY_MAX', src)
        self.assertIn('One deep cell per 20s loop max', src)
        self.assertIn('_acquire_heavy_analysis', APP)

    def test_15_multiasset_active_is_not_hardcoded_empty(self):
        src = app_source('api_multiasset_signals_active')
        compact = src.replace(' ', '')
        self.assertIn('_multiasset_is_executable', src)
        self.assertIn('_multiasset_signal_temporal_state', src)
        self.assertIn("'total':len(signals)", compact)
        self.assertNotIn("'total':0,'signals':[]", compact)

    def test_16_funnel_is_authenticated_and_cache_only(self):
        src = app_source('api_signal_funnel')
        self.assertIn('_require_auth()', src)
        self.assertIn('cache_only', src)
        for forbidden in ('_multiasset_scan(', '_multiasset_run_analysis(', 'requests.'):
            self.assertNotIn(forbidden, src)

    def test_17_multiasset_vigency_respects_explicit_expiry(self):
        names = {'_parse_utc_iso', '_multiasset_signal_temporal_state'}
        body = [n for n in APP_TREE.body if isinstance(n, ast.FunctionDef) and n.name in names]
        ns = {'datetime': datetime, 'timezone': timezone}
        from datetime import timedelta
        ns['timedelta'] = timedelta
        exec(compile(ast.Module(body=body, type_ignores=[]), str(APP_PATH), 'exec'), ns)
        now = datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc)
        state = ns['_multiasset_signal_temporal_state']({
            'timeframe':'1h',
            'source_candle_close_timestamp':'2026-09-28T17:00:00+00:00',
            'valid_until':'2026-09-28T17:30:00+00:00',
        }, now)
        self.assertFalse(state['valid'])
        self.assertEqual(state['remaining_seconds'], 0)

    def test_18_leverage_formulas_are_not_replaced_by_a_low_fixed_cap(self):
        src = app_source('calculate_entry_levels')
        # Existing dynamic leverage paths remain. 17.5.6 adds no x2/x3 cap.
        self.assertIn("leverage = max(5, min(50, base_leverage))", src)
        self.assertIn("leverage = max(3, min(20, base_leverage))", src)
        self.assertIn("leverage = max(1, int(leverage * 0.6))", src)
        self.assertIn("leverage = max(1, int(leverage * 0.8))", src)
        self.assertNotIn('leverage = min(leverage, 2)', src)
        self.assertNotIn('leverage = min(leverage, 3)', src)

    def test_19_telegram_has_no_1756_quantity_cap_marker(self):
        markers = '\n'.join(line for line in APP.splitlines() if '17.5.6' in line).lower()
        self.assertNotIn('telegram_max', markers)
        self.assertNotIn('max_telegram', markers)

    def test_20_public_telemetry_contains_sl_conflict_without_internal_votes(self):
        src = app_source('calculate_entry_levels')
        self.assertIn("'sl_reaction_conflict'", src)
        self.assertIn("'sl_reaction_conflict_source'", src)
        self.assertNotIn("'specialist_scores'", src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
