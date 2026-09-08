import unittest

import numpy as np
import pandas as pd

from q7_strategy_lab import (
    Q7_STRATEGY_LAB_VERSION,
    analyze_q7_strategy_lab,
)


class TestQ7StrategyLab(unittest.TestCase):

    def setUp(self):
        size = 320
        close = np.linspace(100.0, 102.0, size)

        self.df = pd.DataFrame({
            'open': close - 0.05,
            'high': close + 0.15,
            'low': close - 0.15,
            'close': close,
            'volume': np.linspace(1000.0, 1200.0, size),
        })

        self.market_regime = {
            'regime': 'RANGING'
        }

        self.momentum = {
            'divergences': [],
            'hidden_divergences': [],
        }

        self.volatility = {
            'atr_pct': 1.0
        }

        self.volume = {
            'volume_ratio': 1.0
        }

        self.structure = {
            'nearest_support': 101.8,
            'nearest_resistance': 102.2,
            'volume_profile': {
                'val': 101.8,
                'vah': 102.2,
            },
        }

        self.confirmation = {}

    @staticmethod
    def fake_rsi(close, period):
        values = np.full(
            len(close),
            50.0,
            dtype=float
        )

        if period == 3:
            values[-4:] = [
                25.0,
                28.0,
                35.0,
                45.0,
            ]

        elif period == 7:
            values[-5:] = [
                35.0,
                37.0,
                39.0,
                42.0,
                50.0,
            ]

        elif period == 14:
            values[-2:] = [
                46.0,
                52.0,
            ]

        elif period == 21:
            values[-2:] = [
                49.0,
                50.0,
            ]

        return values

    def run_lab(
        self,
        timeframe='15m',
        system_type='futures',
        final_action='LONG',
    ):
        return analyze_q7_strategy_lab(
            df=self.df,
            symbol='BTC-USDT',
            timeframe=timeframe,
            system_type=system_type,
            market_regime=self.market_regime,
            momentum=self.momentum,
            volatility=self.volatility,
            volume=self.volume,
            structure=self.structure,
            confirmation=self.confirmation,
            final_action=final_action,
            rsi_calculator=self.fake_rsi,
        )

    def assert_no_authority(self, result):
        self.assertTrue(
            result.get('shadow_only')
        )

        for key in (
            'affects_vote',
            'affects_safety',
            'affects_entry',
            'affects_levels',
            'affects_publication',
            'affects_leverage',
        ):
            self.assertIs(
                result.get(key),
                False,
                key
            )

        for strategy in (
            result.get('strategies', {})
            or {}
        ).values():
            if isinstance(strategy, dict):
                self.assertTrue(
                    strategy.get('shadow_only')
                )

    def test_version_and_guardrails(self):
        result = self.run_lab()

        self.assertEqual(
            result.get('version'),
            Q7_STRATEGY_LAB_VERSION
        )

        self.assert_no_authority(
            result
        )

    def test_spot_is_out_of_scope(self):
        result = self.run_lab(
            system_type='spot'
        )

        self.assertFalse(
            result.get('eligible')
        )

        self.assertEqual(
            result.get('reason'),
            'SPOT_OUT_OF_SCOPE_Q7_V1'
        )

        self.assert_no_authority(
            result
        )

    def test_unsupported_timeframe_is_out_of_scope(self):
        result = self.run_lab(
            timeframe='12h'
        )

        self.assertFalse(
            result.get('eligible')
        )

        self.assertEqual(
            result.get('reason'),
            'TIMEFRAME_OUT_OF_SCOPE_Q7_V1'
        )

        self.assert_no_authority(
            result
        )

    def test_profiles_by_timeframe(self):
        expected = {
            '5m': 'FAST',
            '15m': 'FAST',
            '30m': 'BALANCED',
            '1h': 'BALANCED',
            '2h': 'STRUCTURAL',
            '4h': 'STRUCTURAL',
        }

        for timeframe, profile in expected.items():
            with self.subTest(
                timeframe=timeframe
            ):
                result = self.run_lab(
                    timeframe=timeframe
                )

                self.assertTrue(
                    result.get('eligible')
                )

                self.assertEqual(
                    result.get('active_profile'),
                    profile
                )

                self.assert_no_authority(
                    result
                )

    def test_futures_internal_spot_action_is_normalized(self):
        result = self.run_lab(
            timeframe='15m',
            final_action='COMPRA_SPOT'
        )

        self.assertEqual(
            result.get('final_action_observed'),
            'COMPRA_SPOT'
        )

        self.assertEqual(
            result.get('final_action_normalized'),
            'LONG'
        )

        rsi = (
            result.get('strategies', {})
            .get('rsi_profile', {})
        )

        self.assertEqual(
            rsi.get('direction'),
            'LONG'
        )

        self.assertEqual(
            rsi.get('alignment_with_system'),
            'ALIGNED'
        )

    def test_vwap_is_real_rolling_ohlcv_observation(self):
        result = self.run_lab(
            timeframe='15m'
        )

        vwap = (
            result.get('strategies', {})
            .get('vwap_reversion', {})
        )

        self.assertEqual(
            vwap.get('method'),
            'ROLLING_24H_TYPICAL_PRICE_VOLUME'
        )

        self.assertGreater(
            float(vwap.get('coverage_pct') or 0),
            0.0
        )

        self.assertTrue(
            vwap.get('shadow_only')
        )

    def test_breakout_retest_stays_shadow(self):
        result = self.run_lab(
            timeframe='1h'
        )

        retest = (
            result.get('strategies', {})
            .get('breakout_retest', {})
        )

        self.assertTrue(
            retest
        )

        self.assertTrue(
            retest.get('shadow_only')
        )

        self.assertIn(
            retest.get('state'),
            {
                'NO_RETEST',
                'ACCEPTED_LONG_RETEST',
                'ACCEPTED_SHORT_RETEST',
                'BREAKOUT_PENDING_RETEST',
                'BREAKDOWN_PENDING_RETEST',
            }
        )


if __name__ == '__main__':
    unittest.main()
