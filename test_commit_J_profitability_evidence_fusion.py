from pathlib import Path

import research_evidence_fusion as ref

ROOT = Path(__file__).resolve().parent


def _promotion(*, key, family, symbol, tf, stage='OBSERVE', exp=0.2, pf=1.3, n=20, vn=6, experiment='CAUSAL_COVERAGE_STRATEGY', meta_extra=None, scope_extra=None, updated='2026-09-13T04:00:00Z'):
    scope = {'market_family': family, 'timeframe': tf, 'direction': 'LONG'}
    if symbol != 'ALL':
        scope['symbol'] = symbol
    if scope_extra:
        scope.update(scope_extra)
    meta = {
        'is_current': True,
        'coverage_cell': {'system_type': 'futures' if family == 'CRYPTO_FUTURES' else 'spot', 'market_family': family, 'symbol': symbol, 'timeframe': tf},
        'coverage_cell_id': f"{'futures' if family == 'CRYPTO_FUTURES' else 'spot'}|{family}|{symbol}|{tf}".upper(),
        'recommended_shadow_target': 6,
        'causal_strategy_family': 'TREND_PULLBACK',
    }
    if meta_extra:
        meta.update(meta_extra)
    return {
        'candidate_key': key,
        'source_engine': 'strategy',
        'experiment': experiment,
        'stage': stage,
        'scope': scope,
        'metrics': {
            'all': {'resolved': n, 'expectancy_r': exp, 'profit_factor': pf},
            'validation': {'resolved': vn, 'expectancy_r': exp, 'profit_factor': pf, 'win_rate_pct': 55.0},
        },
        'meta': meta,
        'updated_at': updated,
    }


def test_commit_j_counts_all_18_cells_even_when_observe(monkeypatch):
    rows = []
    futures_tfs = ['5M','15M','30M','1H','2H','4H']
    for i, tf in enumerate(futures_tfs):
        rows.append(_promotion(key=f'f{i}', family='CRYPTO_FUTURES', symbol='ALL', tf=tf))
    for family, symbol in [('CRYPTO_SPOT','BTC-USDT'),('PAXG_USDT','PAXG-USDT'),('PAXG_BTC','PAXG-BTC')]:
        for tf in ['4H','12H','1D','1W']:
            rows.append(_promotion(key=f'{family}-{tf}', family=family, symbol=symbol, tf=tf))
    assert len(rows) == 18
    monkeypatch.setattr(ref, '_load', lambda force=False: (rows, []))
    snap = ref.profitability_snapshot(force=True)
    assert snap['coverage_cells'] == 18
    assert snap['coverage_complete'] is True


def test_commit_j_runtime_predicate_prevents_wrong_prior(monkeypatch):
    row = _promotion(
        key='ready', family='PAXG_USDT', symbol='PAXG-USDT', tf='1D',
        stage='SHADOW_READY_FAST', exp=0.45, pf=1.8, n=60, vn=12,
        scope_extra={'has_pullback': 'YES'},
    )
    monkeypatch.setattr(ref, '_load', lambda force=False: ([row], []))
    wrong = ref.edge_prior('PAXG-USDT','1D','LONG','spot', runtime_features={'has_pullback':'NO'})
    right = ref.edge_prior('PAXG-USDT','1D','LONG','spot', runtime_features={'has_pullback':'YES'})
    assert wrong['support_score'] == 0
    assert right['state'] == 'OOS_VALIDATED'
    assert right['support_score'] > 0


def test_commit_j_retest_does_not_double_count(monkeypatch):
    base = _promotion(key='base', family='PAXG_USDT', symbol='PAXG-USDT', tf='1D', stage='SHADOW_READY', exp=0.2, n=30, vn=6, updated='2026-09-13T03:00:00Z')
    retest = _promotion(
        key='retest', family='PAXG_USDT', symbol='PAXG-USDT', tf='1D', stage='SHADOW_READY_FAST', exp=0.5, n=44, vn=9,
        experiment='CAUSAL_REGISTRY_RETEST',
        meta_extra={'registry_retest': True, 'original_candidate_key': 'base'},
        updated='2026-09-13T04:00:00Z',
    )
    monkeypatch.setattr(ref, '_load', lambda force=False: ([base, retest], []))
    snap = ref.profitability_snapshot(force=True)
    # Only the latest lineage contributes to profitability KPIs.
    assert snap['spot']['validated_strategies'] == 1
    assert snap['spot']['oos_n'] == 9
    assert abs(snap['spot']['oos_exp_r_weighted'] - 0.5) < 1e-9


def test_commit_j_contracts_are_visible_and_bounded():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    review = (ROOT / 'review_trader.py').read_text(encoding='utf-8')
    router = (ROOT / 'profitability_router.py').read_text(encoding='utf-8')
    analytics = (ROOT / 'templates' / 'analytics.html').read_text(encoding='utf-8')
    analytics_js = (ROOT / 'static' / 'analytics.js').read_text(encoding='utf-8')
    macro = (ROOT / 'macro_context.py').read_text(encoding='utf-8')
    scientist = (ROOT / 'ai_advisor.py').read_text(encoding='utf-8')

    assert "0.65*float(existing) + 0.35*support" in review
    assert "else (0.35*support)" in review
    assert 'HISTORICAL_EDGE_VALIDATED' in router
    assert 'NEGATIVE_EDGE_VETO' in router
    assert 'q5-spot-backtest' in analytics
    assert 'q5-futures-backtest' in analytics
    assert 'q5-shadow-backtest' in analytics
    assert 'Backtest/OOS y live se muestran separados' in (ROOT / 'research_evidence_fusion.py').read_text(encoding='utf-8')
    assert 'const causal=`Causal ${Number(causalInfo.coverage_cells||0)}/${Number(causalInfo.coverage_target||18)}`' in analytics_js
    assert 'exchange_flow' in macro and 'fundamental_signal_context' in macro
    assert 'Flujo CEX 24h' in macro
    assert 'AI_LEARNING_V2:%' in scientist
    assert 'profitability_evidence' in app
    assert 'return accion, 0, estrategias, razones' in app  # legacy contract documented, J keeps Futures non-directional
