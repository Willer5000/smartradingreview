import unittest

from execution_learning import (
    build_execution_forensics,
    build_strategy_attribution_v2,
)


class ExecutionLearningTests(unittest.TestCase):
    def test_strategy_attribution_keeps_vote_direction(self):
        analysis = {
            'decision': {
                'action': 'LONG',
                'registro_votacion': {
                    'todos_los_votos': [
                        {
                            'trader': 'SmartMoney',
                            'accion': 'LONG',
                            'confianza_original': 88,
                            'estrategias': ['ORDER_BLOCK_ALCISTA']
                        },
                        {
                            'trader': 'Tecnico',
                            'accion': 'SHORT',
                            'confianza_original': 77,
                            'estrategias': ['DOBLE_TECHO']
                        }
                    ]
                }
            }
        }
        snapshot = build_strategy_attribution_v2(analysis, 'futures')
        by_strategy = {item['strategy']: item for item in snapshot['items']}
        self.assertEqual(by_strategy['ORDER_BLOCK_ALCISTA']['relation_to_final'], 'SUPPORT')
        self.assertEqual(by_strategy['DOBLE_TECHO']['relation_to_final'], 'OPPOSE')
        self.assertEqual(snapshot['item_count'], 2)

    def test_stop_without_progress_is_identified(self):
        signal = {
            'action_normalized': 'LONG',
            'entry_price': 100,
            'stop_loss': 99,
            'take_profit': 102.5,
        }
        result = {
            'status': 'sl_hit',
            'mfe_r': 0.10,
            'mae_r': 1.0,
            'mfe_pct': 0.10,
            'mae_pct': 1.0,
            'candles_to_result': 2,
        }
        forensics = build_execution_forensics(signal, result, entry_touched=True)
        self.assertEqual(forensics['diagnosis'], 'STOPPED_WITHOUT_PROGRESS')
        self.assertFalse(forensics['stop_was_possibly_tight'])

    def test_post_stop_recovery_flags_possible_tight_stop(self):
        signal = {
            'action_normalized': 'SHORT',
            'entry_price': 100,
            'stop_loss': 101,
            'take_profit': 97,
        }
        result = {
            'status': 'sl_hit',
            'mfe_r': 0.60,
            'mae_r': 1.0,
            'mfe_pct': 0.60,
            'mae_pct': 1.0,
            'candles_to_result': 3,
        }
        forensics = build_execution_forensics(
            signal,
            result,
            entry_touched=True,
            post_stop_recovery={
                'observed': True,
                'reclaimed_entry': True,
                'tp_reached_after_stop': True,
                'best_favorable_r_after_stop': 3.0,
            }
        )
        self.assertTrue(forensics['stop_was_possibly_tight'])
        self.assertEqual(
            forensics['diagnosis'],
            'STOPPED_AFTER_WEAK_PROGRESS'
        )

    def test_spot_alias_is_normalized(self):
        analysis = {
            'decision': {
                'action': 'COMPRA_SPOT',
                'registro_votacion': {
                    'todos_los_votos': [{
                        'trader': 'Pullback',
                        'accion': 'COMPRA_SPOT',
                        'confianza': 70,
                        'estrategias': ['PULLBACK_TENDENCIA']
                    }]
                }
            }
        }
        snapshot = build_strategy_attribution_v2(analysis, 'spot')
        self.assertEqual(snapshot['final_action'], 'LONG')
        self.assertEqual(snapshot['items'][0]['vote_action'], 'LONG')
        self.assertEqual(snapshot['items'][0]['relation_to_final'], 'SUPPORT')


if __name__ == '__main__':
    unittest.main()
