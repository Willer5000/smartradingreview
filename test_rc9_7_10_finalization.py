import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


class RC9710FinalizationTests(unittest.TestCase):
    def test_spot_three_lanes_have_distinct_semantics(self):
        js = read('static/script.js')
        app = read('app.py')
        self.assertIn("document.getElementById('current-active-signals-list')", js)
        self.assertIn("/api/spot/signals/vigent", js)
        self.assertIn("@app.route('/api/spot/signals/vigent')", app)
        self.assertIn("'ui_context': 'CONFIRMED'", app)
        self.assertIn("item['ui_context'] = 'VIGENT'", app)
        self.assertIn('Snapshot original: Entry, SL, TP', js)

    def test_spot_vigent_preserves_original_validity(self):
        app = read('app.py')
        self.assertIn('valid_until_raw = item.get', app)
        self.assertIn("item['valid_until'] = valid_until.isoformat()", app)
        self.assertNotIn("item['entry'] =", app[app.index('def _build_spot_vigent_cache'):app.index('def _compute_previous_signals')])
        self.assertNotIn("item['stop_loss'] =", app[app.index('def _build_spot_vigent_cache'):app.index('def _compute_previous_signals')])
        self.assertNotIn("item['take_profit'] =", app[app.index('def _build_spot_vigent_cache'):app.index('def _compute_previous_signals')])

    def test_live_price_race_is_guarded_and_autoscales(self):
        js = read('static/script.js')
        html = read('templates/index.html')
        self.assertIn('__LIVE_PRICE_ABORT_CONTROLLER__', html)
        self.assertIn('__LIVE_PRICE_REQUEST_SEQ__', html)
        self.assertIn('responseSymbol !== requestedSymbol', html)
        self.assertIn('responseTf !== requestedTf', html)
        self.assertIn('window.resetLiveVisualContext', js)
        self.assertIn("'yaxis.autorange': true", js)
        self.assertIn("trace?.meta === 'LIVE_OPEN_CANDLE'", js)
        self.assertNotIn('payload.symbol || window.currentSymbol', js)
        self.assertNotIn('payload.timeframe || window.currentInterval', js)

    def test_futures_context_uses_selected_symbol_and_no_paxg_copy(self):
        js = read('static/futures.js')
        html = read('templates/index.html')
        self.assertIn('symbol=${encodeURIComponent(symbol)}', js)
        self.assertIn('payload.intermarket_context', js)
        self.assertIn('Amplitud Futures', html)
        self.assertNotIn('No representa una rotación BTC/PAXG', html)
        self.assertNotIn('Seleccione un par para ver el análisis', js)

    def test_leverage_policy_grows_only_with_tight_geometry(self):
        spec = importlib.util.spec_from_file_location('lev_policy_rc9710', ROOT / 'leverage_policy.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tight = mod.select_risk_budget_leverage(
            minimum_required=2.0,
            sl_distance_pct=0.5,
            max_by_risk=20.0,
            max_by_atr_stress=20.0,
            safety_score=92.0,
            timeframe_static_max=20.0,
            fallback_exchange_max=50.0,
            verified_exchange_max=50.0,
            max_by_liquidation_buffer=30.0,
            adaptive_enabled=False,
            target_loss_budget_pct_margin=5.0,
        )
        wide = mod.select_risk_budget_leverage(
            minimum_required=2.0,
            sl_distance_pct=2.0,
            max_by_risk=5.0,
            max_by_atr_stress=5.0,
            safety_score=92.0,
            timeframe_static_max=20.0,
            fallback_exchange_max=50.0,
            verified_exchange_max=50.0,
            max_by_liquidation_buffer=30.0,
            adaptive_enabled=False,
            target_loss_budget_pct_margin=5.0,
        )
        self.assertIsNotNone(tight)
        self.assertIsNotNone(wide)
        self.assertGreater(tight['leverage'], 2)
        self.assertLess(wide['leverage'], tight['leverage'])
        self.assertEqual(tight['selection_policy'], 'POSITION_AWARE_TECHNICAL_MAX')
        self.assertEqual(tight['version'], 'RC9_7_11_POSITION_AWARE_TECHNICAL_LEVERAGE_V5')

    def test_liquidation_and_contract_caps_are_wired(self):
        fs = read('futures_system.py')
        self.assertIn("api/v1/contracts/{symbol}", fs)
        self.assertIn("'max_leverage': max_leverage", fs)
        self.assertIn("'maintenance_margin_rate': mmr", fs)
        self.assertIn('max_by_liquidation_buffer', fs)
        self.assertIn('estimated_liquidation_distance_pct', fs)
        self.assertIn('symbol=symbol', fs)
        self.assertIn("'technical_target_loss_pct_margin': 5.0", fs)
        # Fresh/unvalidated contingency cells remain canary-sized: the new
        # technical policy must not jump to 20x/30x merely because a stop is tight.
        self.assertIn("((contingency_playbook.get('risk') or {}).get('leverage_cap')) or 10", fs)


if __name__ == '__main__':
    unittest.main()
