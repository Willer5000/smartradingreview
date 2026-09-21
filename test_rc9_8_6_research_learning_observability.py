import importlib.util
from pathlib import Path
import sys
import types

class _FakeBlueprint:
    def __init__(self, *args, **kwargs): pass
    def get(self, *args, **kwargs):
        return lambda fn: fn

fake_flask = types.ModuleType('flask')
fake_flask.Blueprint = _FakeBlueprint
fake_flask.jsonify = lambda *a, **k: a[0] if len(a) == 1 else a
fake_flask.render_template = lambda *a, **k: ''
fake_flask.Response = object
sys.modules.setdefault('flask', fake_flask)


ROOT = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location('research_bridge_rc986', ROOT / 'research_bridge.py')
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)


def _row(i, *, selection=True, oos_positive=False, stage='VALIDATION_REQUIRED'):
    action = 'LONG' if i % 2 == 0 else 'SHORT'
    return {
        'candidate_key': f'cand-{i}',
        'source_engine': 'strategy',
        'experiment': 'CAUSAL_COVERAGE_STRATEGY',
        'stage': stage,
        'reason': 'test',
        'scope': {
            'market_family': 'CRYPTO_FUTURES',
            'symbol': 'BTC-USDT',
            'timeframe': '1H',
            'direction': action,
            'action': action,
        },
        'metrics': {
            'all': {'resolved': 20, 'win_rate_pct': 55, 'expectancy_r': 0.1, 'profit_factor': 1.2},
            'selection': {'resolved': 4, 'win_rate_pct': 50, 'expectancy_r': 0.05, 'profit_factor': 1.1},
            'validation': {
                'resolved': 4,
                'win_rate_pct': 50,
                'expectancy_r': 0.2 if oos_positive else -0.2,
                'profit_factor': 1.4 if oos_positive else 0.8,
            },
        },
        'meta': {
            'is_current': True,
            'coverage_cell_id': f'CELL-{i}',
            'coverage_status': 'SELECTION_PROFITABLE' if selection else 'SELECTION_REJECTED',
            'causal_strategy': True,
            'causal_strategy_family': 'TEST_STRATEGY',
        },
        'research_version': 'TEST',
        'updated_at': '2026-09-21T12:43:00+00:00',
    }


def test_learning_summary_distinguishes_learning_from_champions():
    rows = [rb._compact_promotion(_row(i, selection=i < 39, oos_positive=i < 16)) for i in range(44)]
    summary = rb._research_learning_summary(rows, 60)
    assert summary['investigated_cells'] == 44
    assert summary['selection_positive_cells'] == 39
    assert summary['oos_positive_cells'] == 16
    assert summary['champion_cells'] == 0
    assert summary['pending_investigation_cells'] == 16
    assert summary['pending_champion_cells'] == 60


def test_compact_promotion_preserves_selection_evidence():
    row = rb._compact_promotion(_row(1, selection=True, oos_positive=True))
    assert row['coverage_status'] == 'SELECTION_PROFITABLE'
    assert row['selection_n'] == 4
    assert row['selection_exp_r'] == 0.05
    assert row['oos_exp_r'] == 0.2


def test_champion_remains_authoritative_for_same_cell():
    champion = {
        'candidate_key': 'champ', 'stage': 'SHADOW_READY', 'coverage_cell_id': 'CELL-1',
        'market_family': 'CRYPTO_FUTURES', 'symbol': 'BTC-USDT', 'timeframe': '1H',
        'action': 'SHORT', 'scope': {'market_family': 'CRYPTO_FUTURES', 'symbol': 'BTC-USDT', 'timeframe': '1H', 'action': 'SHORT'},
        'coverage_status': 'SELECTION_PROFITABLE', 'oos_exp_r': 0.3, 'oos_pf': 1.5,
    }
    merged = rb._merge_champions_with_learning([champion], [_row(1, selection=True, oos_positive=True)])
    assert len(merged) == 1
    assert merged[0]['candidate_key'] == 'champ'


def test_snapshot_path_supplements_zero_champion_snapshot_with_learning(monkeypatch):
    evidence = [_row(i, selection=i < 39, oos_positive=i < 16) for i in range(44)]

    def fake_get(table, params):
        if table == 'research_governance_snapshot_v1':
            return [{
                'id': 1, 'updated_at': '2026-09-21T12:43:00+00:00', 'target_cells': 60,
                'champion_count': 0, 'pending_count': 60, 'champions': [], 'shadow': [],
            }]
        if table == 'research_promotions_v1':
            return evidence
        if table == 'research_engine_state_v1':
            return []
        raise AssertionError(table)

    monkeypatch.setattr(rb, '_get', fake_get)
    rb._CACHE.update(ts=0.0, payload=None, error=None, watermark=None)
    candidates, states, shadow, coverage = rb._compact(force=True)
    assert len(candidates) == 44
    assert coverage['champion_count'] == 0
    assert coverage['learning_summary']['investigated_cells'] == 44
    assert coverage['learning_summary']['selection_positive_cells'] == 39
    assert coverage['learning_summary']['oos_positive_cells'] == 16


def test_frontend_copy_and_labels_do_not_equate_zero_champions_with_zero_learning():
    js = (ROOT / 'static' / 'analytics.js').read_text(encoding='utf-8')
    assert 'rf96LearningStats' in js
    assert 'Selection+' in js
    assert 'OOS+' in js
    assert 'esto no significa aprendizaje cero' in js
    assert 'Investigadas · OOS+ · Champion' in js
