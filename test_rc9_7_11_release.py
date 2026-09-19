import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class RC9711ReleaseTests(unittest.TestCase):
    def _policy(self):
        spec = importlib.util.spec_from_file_location(
            'lev_policy_rc9711', ROOT / 'leverage_policy.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_position_aware_leverage_uses_size_without_weakening_target_risk(self):
        mod = self._policy()
        entry, sl = 12.40, 12.26
        sl_pct = abs(entry - sl) / entry * 100.0
        size = 0.35
        result = mod.select_risk_budget_leverage(
            minimum_required=2.0,
            sl_distance_pct=sl_pct,
            max_by_risk=10.0 / (sl_pct * size),
            max_by_atr_stress=30.0,
            safety_score=80.0,
            timeframe_static_max=30.0,
            fallback_exchange_max=50.0,
            verified_exchange_max=50.0,
            max_by_liquidation_buffer=30.0,
            target_loss_budget_pct_margin=5.0,
            risk_allocation_fraction=size,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['leverage'], 12)
        self.assertEqual(
            result['selection_policy'],
            'POSITION_AWARE_TECHNICAL_MAX',
        )
        self.assertLessEqual(sl_pct * result['leverage'] * size, 5.0)

    def test_same_geometry_full_size_stays_lower(self):
        mod = self._policy()
        entry, sl = 12.40, 12.26
        sl_pct = abs(entry - sl) / entry * 100.0
        full = mod.select_risk_budget_leverage(
            minimum_required=2.0,
            sl_distance_pct=sl_pct,
            max_by_risk=10.0 / sl_pct,
            max_by_atr_stress=30.0,
            safety_score=80.0,
            timeframe_static_max=30.0,
            fallback_exchange_max=50.0,
            verified_exchange_max=50.0,
            max_by_liquidation_buffer=30.0,
            target_loss_budget_pct_margin=5.0,
            risk_allocation_fraction=1.0,
        )
        reduced = mod.select_risk_budget_leverage(
            minimum_required=2.0,
            sl_distance_pct=sl_pct,
            max_by_risk=10.0 / (sl_pct * 0.35),
            max_by_atr_stress=30.0,
            safety_score=80.0,
            timeframe_static_max=30.0,
            fallback_exchange_max=50.0,
            verified_exchange_max=50.0,
            max_by_liquidation_buffer=30.0,
            target_loss_budget_pct_margin=5.0,
            risk_allocation_fraction=0.35,
        )
        self.assertEqual(full['leverage'], 4)
        self.assertGreater(reduced['leverage'], full['leverage'])

    def test_contingency_cap_is_preserved(self):
        text = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
        self.assertIn("or 10", text)
        self.assertIn(
            'optimal_leverage = min(optimal_leverage, contingency_leverage_cap)',
            text,
        )

    def test_frontend_does_not_recalculate_backend_leverage(self):
        text = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
        self.assertNotIn('modifiedLeverage', text)
        self.assertIn('canonicalLeverage', text)
        block = text[text.index('window.updateConvictionInfo'):]
        block = block[:block.index('function updateSystemStatus')]
        self.assertNotIn('suggested_leverage_modifier', block)

    def test_frontend_visible_language_is_apalancamiento(self):
        futures = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        forbidden = (
            '>Leverage<',
            'Leverage:</strong>',
            'Máx. leverage',
            '<small>Lev.</small>',
            'margen/leverage',
            'margen y leverage',
        )
        for token in forbidden:
            self.assertNotIn(token, futures)
            self.assertNotIn(token, html)
        self.assertIn('Máx. apalancamiento', html)
        self.assertIn('Apalancamiento:</strong>', futures)

    def test_guardian_preferences_cache_is_replaced_after_upsert(self):
        text = (ROOT / 'supabase_client.py').read_text(encoding='utf-8')
        start = text.index('def upsert_user_preferences')
        block = text[start:text.index('# COMMIT 36P', start)]
        response_at = block.index('response = self._with_retry')
        cache_at = block.index('self._preferences_cache[user_name] =')
        self.assertGreater(cache_at, response_at)
        self.assertIn("'spot_telegram_timeframes': list(clean_spot)", block)

    def test_spot_partial_save_preserves_previous_and_vigent(self):
        text = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = text.index('def _save_spot_signals_cache_to_disk')
        block = text[start:text.index('def _load_spot_signals_cache_from_disk', start)]
        self.assertIn('load_runtime_snapshot(', block)
        self.assertIn("'spot', 'signals_cache'", block.replace('\n', ' '))
        self.assertIn("persisted.get('previous')", block)
        self.assertIn("persisted.get('vigent')", block)
        self.assertIn("persisted.get('vigent_ts')", block)

    def test_futures_restores_before_cold_refresh_and_merges_partial_snapshot(self):
        text = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('def _trigger_futures_fast_restore', text)
        start = text.index('def _get_or_refresh_futures_analysis')
        block = text[start:text.index('def _trigger_futures_refresh_async', start)]
        restore_at = block.index('_trigger_futures_fast_restore()')
        combo_at = block.index('_trigger_futures_combo_refresh_async()', restore_at)
        self.assertLess(restore_at, combo_at)
        save_start = text.index('def _save_futures_cache_to_disk')
        save_block = text[save_start:text.index('# Hotfix 14.8', save_start)]
        self.assertIn('merged_lifecycle.update(new_lifecycle)', save_block)
        self.assertIn("len(old_analysis) > len(new_analysis)", save_block)

    def test_lifecycle_clock_is_not_reset_by_restore_fix(self):
        text = (ROOT / 'app.py').read_text(encoding='utf-8')
        save_start = text.index('def _save_futures_cache_to_disk')
        save_block = text[save_start:text.index('# Hotfix 14.8', save_start)]
        self.assertNotIn("['valid_until'] = time.time()", save_block)
        spot_start = text.index('def _save_spot_signals_cache_to_disk')
        spot_block = text[spot_start:text.index('def _load_spot_signals_cache_from_disk', spot_start)]
        self.assertNotIn("['valid_until'] =", spot_block)


if __name__ == '__main__':
    unittest.main()
