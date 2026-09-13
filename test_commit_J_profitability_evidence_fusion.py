from pathlib import Path
import research_evidence_fusion as ref
ROOT = Path(__file__).resolve().parent

FUTURES_SYMBOLS=['BTC-USDT','ETH-USDT','SOL-USDT','XRP-USDT','ADA-USDT','LINK-USDT','BNB-USDT']
FUTURES_TFS=['5M','15M','30M','1H','2H','4H']
SPOT=[('CRYPTO_SPOT','BTC-USDT'),('PAXG_USDT','PAXG-USDT'),('PAXG_BTC','PAXG-BTC')]
SPOT_TFS=['4H','12H','1D','1W']

def _promotion(*, key, family, symbol, tf, stage='OBSERVE', exp=0.2, pf=1.3, n=20, vn=6, experiment='CAUSAL_COVERAGE_STRATEGY', meta_extra=None, scope_extra=None, updated='2026-09-13T04:00:00Z'):
    scope={'market_family':family,'timeframe':tf,'direction':'LONG','symbol':symbol}
    if scope_extra: scope.update(scope_extra)
    meta={'is_current':True,'coverage_cell':{'system_type':'futures' if family=='CRYPTO_FUTURES' else 'spot','market_family':family,'symbol':symbol,'timeframe':tf},'coverage_cell_id':f"{'futures' if family=='CRYPTO_FUTURES' else 'spot'}|{family}|{symbol}|{tf}".upper(),'recommended_shadow_target':6,'causal_strategy_family':'TREND_PULLBACK'}
    if meta_extra: meta.update(meta_extra)
    return {'candidate_key':key,'source_engine':'strategy','experiment':experiment,'stage':stage,'scope':scope,'metrics':{'all':{'resolved':n,'expectancy_r':exp,'profit_factor':pf},'validation':{'resolved':vn,'expectancy_r':exp,'profit_factor':pf,'win_rate_pct':55.0}},'meta':meta,'updated_at':updated}

def test_commit_j1_counts_54_exact_symbol_timeframe_cells(monkeypatch):
    rows=[]
    for symbol in FUTURES_SYMBOLS:
        for tf in FUTURES_TFS:
            rows.append(_promotion(key=f'f-{symbol}-{tf}',family='CRYPTO_FUTURES',symbol=symbol,tf=tf))
    for family,symbol in SPOT:
        for tf in SPOT_TFS:
            rows.append(_promotion(key=f's-{symbol}-{tf}',family=family,symbol=symbol,tf=tf))
    assert len(rows)==54
    monkeypatch.setattr(ref,'_load',lambda force=False:(rows,[]))
    snap=ref.profitability_snapshot(force=True)
    assert snap['coverage_cells']==54
    assert snap['coverage_target']==54
    assert snap['coverage_complete'] is True
    assert len(snap['coverage_matrix'])==54

def test_commit_j1_runtime_predicate_prevents_wrong_prior(monkeypatch):
    row=_promotion(key='ready',family='PAXG_USDT',symbol='PAXG-USDT',tf='1D',stage='SHADOW_READY_FAST',exp=0.45,pf=1.8,n=60,vn=12,scope_extra={'has_pullback':'YES'})
    monkeypatch.setattr(ref,'_load',lambda force=False:([row],[]))
    wrong=ref.edge_prior('PAXG-USDT','1D','LONG','spot',runtime_features={'has_pullback':'NO'})
    right=ref.edge_prior('PAXG-USDT','1D','LONG','spot',runtime_features={'has_pullback':'YES'})
    assert wrong['support_score']==0
    assert right['state'] in {'OOS_VALIDATED','OOS_PLUS_SHADOW'}
    assert right['support_score']>0

def test_commit_j1_retest_does_not_double_count(monkeypatch):
    base=_promotion(key='base',family='PAXG_USDT',symbol='PAXG-USDT',tf='1D',stage='SHADOW_READY',exp=0.2,n=30,vn=6,updated='2026-09-13T03:00:00Z')
    retest=_promotion(key='retest',family='PAXG_USDT',symbol='PAXG-USDT',tf='1D',stage='SHADOW_READY_FAST',exp=0.5,n=44,vn=9,experiment='CAUSAL_REGISTRY_RETEST',meta_extra={'registry_retest':True,'original_candidate_key':'base'},updated='2026-09-13T04:00:00Z')
    monkeypatch.setattr(ref,'_load',lambda force=False:([base,retest],[]))
    snap=ref.profitability_snapshot(force=True)
    assert snap['spot']['validated_strategies']==1
    assert snap['spot']['oos_n']==9
    assert abs(snap['spot']['oos_exp_r_weighted']-0.5)<1e-9

def test_commit_j1_contracts_visible_and_bounded():
    app=(ROOT/'app.py').read_text(); review=(ROOT/'review_trader.py').read_text(); router=(ROOT/'profitability_router.py').read_text(); analytics=(ROOT/'templates/analytics.html').read_text(); analytics_js=(ROOT/'static/analytics.js').read_text(); macro=(ROOT/'macro_context.py').read_text(); scientist=(ROOT/'ai_advisor.py').read_text(); fusion=(ROOT/'research_evidence_fusion.py').read_text()
    assert '0.65*float(existing) + 0.35*support' in review
    assert 'SHADOW_DIVERGED' in review
    assert 'SHADOW_DIVERGED_RETEST' in router
    assert 'q5-spot-backtest' in analytics and 'q5-futures-backtest' in analytics
    assert '_COVERAGE_TARGET = 54' in fusion
    assert 'RENTABILIDAD OOS VALIDADA' in analytics_js
    assert 'exchange_flow' in macro and 'fundamental_signal_context' in macro
    assert 'Flujo CEX 24h' in macro
    assert 'startswith("AI_LEARNING_V2:")' in scientist
    assert '_ensure_ai_learning_scientist_thread' in app
