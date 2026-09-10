import unittest
from pathlib import Path

import pandas as pd

from saved_signals import _current_candle_live_entry_probe


class Hotfix141SavedEntryLifecycleTests(unittest.TestCase):
    def test_same_open_2h_candle_can_detect_live_entry_after_save(self):
        # La vela abrió antes del guardado. Su high/low histórico no debe decidir;
        # el close vivo sí puede confirmar que el monitor está en Entry.
        now = pd.Timestamp.now(tz='UTC')
        candle_open = now.floor('2h')
        start_ts = candle_open + pd.Timedelta(minutes=30)
        df = pd.DataFrame([{
            'time': candle_open.tz_convert(None),
            'open': 1.3800,
            'high': 1.3900,
            'low': 1.3300,   # podría haber ocurrido antes del guardado
            'close': 1.35958,
        }])
        probe = _current_candle_live_entry_probe(
            entry=1.36,
            df=df,
            start_ts=start_ts,
            action='LONG',
            timeframe='2h',
        )
        self.assertIsNotNone(probe)
        self.assertAlmostEqual(probe['price'], 1.35958, places=5)

    def test_same_candle_does_not_reuse_pre_save_wick(self):
        now = pd.Timestamp.now(tz='UTC')
        candle_open = now.floor('2h')
        start_ts = candle_open + pd.Timedelta(minutes=30)
        df = pd.DataFrame([{
            'time': candle_open.tz_convert(None),
            'open': 1.3800,
            'high': 1.3900,
            'low': 1.3500,   # tocó antes, pero no sabemos si fue post-guardado
            'close': 1.3750, # precio vivo lejos del Entry
        }])
        probe = _current_candle_live_entry_probe(
            entry=1.36,
            df=df,
            start_ts=start_ts,
            action='LONG',
            timeframe='2h',
        )
        self.assertIsNone(probe)

    def test_saved_chart_uses_futures_not_spot(self):
        source = Path('app.py').read_text(encoding='utf-8')
        start = source.index('def api_saved_signals_chart_data')
        end = source.index("@app.route('/api/kpis/frontend_signals')", start)
        block = source[start:end]
        self.assertIn('futures_market = _get_futures_system()', block)
        self.assertIn('futures_market.get_kucoin_data(symbol, tf)', block)
        self.assertNotIn('expert_system.get_kucoin_data(symbol, tf)', block)
        self.assertIn("'market_data_source': 'KUCOIN_FUTURES_PERPETUAL_REST'", block)

    def test_frontend_distinguishes_operational_and_original_entry(self):
        source = Path('static/futures.js').read_text(encoding='utf-8')
        self.assertIn('Entry operativo guardado:', source)
        self.assertIn('Entry original del análisis:', source)
        self.assertIn('Precio actual Futures:', source)


if __name__ == '__main__':
    unittest.main()
