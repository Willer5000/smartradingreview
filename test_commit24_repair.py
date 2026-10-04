import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('commit24_repair_runtime', ROOT / 'commit24_repair_runtime.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_result(**overrides):
    result = {
        'success': True,
        'symbol': 'BTC-USDT',
        'timeframe': '1h',
        'is_multiasset': False,
        'decision': {'action': 'LONG', 'confidence': 68},
        'levels': {
            'entry': 100.0,
            'stop_loss': 98.0,
            'take_profit': 104.0,
            'risk_reward': 2.0,
            'leverage': 5,
            'risk_allocation_fraction': 0.50,
            'execution_safety': 80.0,
            'execution_safety_operational_min': 65.0,
            'futures_filter_stage': 'PUBLICATION_GATE',
            'futures_publication_gate': {
                'stage': 'PUBLICATION_GATE',
                'reason_codes': ['SAFETY'],
                'reasons': ['Safety insuficiente en legacy Q10'],
            },
            'risk_control': {
                'estimated_sl_loss_pct_margin': 5.0,
                'estimated_atr_stress_loss_pct_margin': 10.0,
            },
            'entry_score': 80.0,
            'entry_reachability': 80.0,
            'tp_quality_score': 85.0,
            'sl_reliability': 0.85,
        },
        'trend': {'direction': 'bullish', 'adx': 30},
        'momentum': {'direction': 'bullish'},
        'volatility': {'atr_pct': 2.0, 'state': 'NORMAL'},
        'structure': {'direction': 'bullish'},
        'market_data_is_synthetic': False,
    }
    for k, v in overrides.items():
        result[k] = v
    return result


class FakeFutures:
    def _calculate_execution_safety(self, levels, trend, momentum, structure, timeframe):
        return {'score': float(levels.get('execution_safety', 80.0)), 'label': 'ALTA', 'components': {}}


class FakeApp:
    def _get_futures_system(self):
        return FakeFutures()

    def _ensure_manual_diagnostic_geometry_175114(self, result, action, symbol, timeframe):
        # In production this is app.py's exact helper. The test keeps existing geometry.
        return result['levels']


class FakeQModule:
    @staticmethod
    def evaluate(**kwargs):
        levels = kwargs['levels']
        stage = kwargs.get('native_stage') or levels.get('futures_filter_stage') or 'PUBLICATION_GATE'
        return {
            'parallel_quality_filters': {
                'selected_filter': 'Q7',
                'selected_filter_name': 'SALIDA / GEOMETRÍA',
                'selected_filter_score': 84.0,
                'selected_filter_passed': True,
                'passed_filters': ['Q7'],
                'summary': 'Q1 40 · Q2 50 · Q3 55 · Q4 50 · Q5 60 · Q6 70 · Q7 84✓ · Q8 64 · Q9 55 · Q10 62',
                'legacy_publication_blockers': ['SAFETY'],
                'universal_guards': {'passed': stage == 'PUBLICATION_GATE', 'codes': []},
            }
        }


def install_fake_q(stage='PUBLICATION_GATE', score=84.0, passed=True, blockers=('SAFETY',)):
    class Q:
        @staticmethod
        def evaluate(**kwargs):
            return {
                'parallel_quality_filters': {
                    'selected_filter': 'Q7',
                    'selected_filter_name': 'SALIDA / GEOMETRÍA',
                    'selected_filter_score': score,
                    'selected_filter_passed': passed,
                    'passed_filters': ['Q7'] if passed else [],
                    'summary': 'Q7 %.1f' % score,
                    'legacy_publication_blockers': list(blockers),
                    'universal_guards': {'passed': stage == 'PUBLICATION_GATE', 'codes': []},
                }
            }
    sys.modules['quality_9q_engine_21'] = Q


def test_promotes_one_of_ten():
    install_fake_q()
    out, auth = mod._normalize_quality_candidate(FakeApp(), make_result(), 'BTC-USDT', '1h')
    assert auth['confirmed'] is True
    assert auth['authority'] == 'Q7'
    assert out['levels']['publication_status'] == 'EXECUTABLE_SIGNAL'
    assert out['premium_confirmation_mode'] == 'ONE_OF_TEN_QUALITY_FILTERS'
    assert out['levels']['risk_control']['estimated_sl_loss_pct_margin'] == 5.0


def test_rejects_below_75():
    install_fake_q(score=74.9, passed=False)
    out, auth = mod._normalize_quality_candidate(FakeApp(), make_result(), 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert out.get('publication_status') != 'EXECUTABLE_SIGNAL'


def test_rejects_pre_gate():
    install_fake_q(stage='CANDIDATE')
    r = make_result()
    r['levels']['futures_filter_stage'] = 'CANDIDATE'
    r['levels']['futures_publication_gate']['stage'] = 'CANDIDATE'
    out, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert 'PRE_GATE_REJECTION' in auth['universal_guard_codes']


def test_rejects_safety_floor():
    install_fake_q()
    r = make_result()
    r['levels']['execution_safety'] = 64.9
    out, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert 'OPERATIONAL_SAFETY_BELOW_65' in auth['universal_guard_codes']


def test_rejects_sl_loss():
    install_fake_q()
    r = make_result()
    r['levels']['risk_allocation_fraction'] = 1.0
    out, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert 'LOSS_AT_SL' in auth['universal_guard_codes']


def test_rejects_atr_stress():
    install_fake_q()
    r = make_result()
    r['levels']['risk_control']['estimated_atr_stress_loss_pct_margin'] = 25.1
    out, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert 'ATR_STRESS' in auth['universal_guard_codes']


def test_rejects_non_q10_blocker():
    install_fake_q(blockers=('LOSS_AT_SL',))
    r = make_result()
    r['levels']['futures_publication_gate']['reason_codes'] = ['LOSS_AT_SL']
    out, auth = mod._normalize_quality_candidate(FakeApp(), r, 'BTC-USDT', '1h')
    assert auth['confirmed'] is False
    assert 'NON_Q10_LEGACY_BLOCKER' in auth['universal_guard_codes']


if __name__ == '__main__':
    for fn in [
        test_promotes_one_of_ten,
        test_rejects_below_75,
        test_rejects_pre_gate,
        test_rejects_safety_floor,
        test_rejects_sl_loss,
        test_rejects_atr_stress,
        test_rejects_non_q10_blocker,
    ]:
        fn()
        print('PASS', fn.__name__)
    print('ALL PASS')
