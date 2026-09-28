from pathlib import Path
import hashlib, importlib, sys

ROOT=Path(__file__).resolve().parent

def txt(name): return (ROOT/name).read_text(encoding='utf-8')
def git_blob(path):
    data=(ROOT/path).read_bytes()
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def strong_layers(side='BEARISH'):
    bull=side=='BULLISH'
    return {
        'trend':{'direction':side.lower(),'adx':35,'plus_di':35 if bull else 10,'minus_di':10 if bull else 35},
        'momentum':{'direction':side.lower(),'rsi':60 if bull else 40,'macd_histogram':1 if bull else -1,'divergences':[]},
        'volume':{'volume_ratio':1.4,'obv_trend':side.lower(),'whale_buy_confirmed':bull,'whale_sell_confirmed':not bull},
        'structure':{'direction':side.lower(),'order_blocks':[1],'fair_value_gaps':[1],'liquidity_sweeps':[1]},
        'volatility':{'atr_pct':2.0,'bb_width':3.0},
        'market_regime':{'regime':'TRENDING_BULL' if bull else 'TRENDING_BEAR'},
        'macro_context':{'risk_level':'NORMAL'},'liquidation':{},
    }

def weak_layers():
    return {
        'trend':{'direction':'neutral','adx':14,'plus_di':20,'minus_di':20},
        'momentum':{'direction':'neutral','rsi':50,'macd_histogram':0,'divergences':[]},
        'volume':{'volume_ratio':0.7,'obv_trend':'neutral'},
        'structure':{'direction':'neutral','order_blocks':[],'fair_value_gaps':[],'liquidity_sweeps':[]},
        'volatility':{'atr_pct':1.0,'bb_width':2.0},'market_regime':{'regime':'RANGING'},
        'macro_context':{'risk_level':'NORMAL'},'liquidation':{},
    }

def main():
    sys.path.insert(0,str(ROOT))
    import operational_intelligence as oi
    from leverage_policy import select_risk_budget_leverage

    # 1. Pre-heatmap Commit 13 leverage policy is byte-identical.
    assert git_blob('leverage_policy.py') == '9e85a7fc8628799e9590a8a1d0be990c8ef30486'

    # 2. The original audited 150 Spot/Crypto-Futures cells remain unchanged.
    audit=oi.official_universe_audit(); assert audit['ok'] and audit['cells']==150
    assert oi.is_official_cell('FUTURES','BTC-USDT','1H','LONG')
    assert oi.is_official_cell('FUTURES','SUI-USDT','30M','SHORT')

    # 3. Multi-Asset is isolated to its real production universe/TFs.
    for tf in ('1H','4H','1D'):
        assert oi.is_official_cell('FUTURES','CL-USDT',tf,'LONG')
    assert not oi.is_official_cell('FUTURES','CL-USDT','30M','LONG')
    assert not oi.is_official_cell('FUTURES','CL-USDT','2H','LONG')
    assert not oi.is_official_cell('FUTURES','UNKNOWN-USDT','1H','LONG')

    # 4. Crypto MTF profiles are preserved; Multi-Asset uses only real TFs.
    assert oi.mtf_required_timeframes('FUTURES','1H','BTC-USDT') == ['4H','2H','1H','30M']
    assert oi.mtf_required_timeframes('FUTURES','30M','SUI-USDT') == ['2H','1H','30M']
    assert oi.mtf_required_timeframes('FUTURES','1H','CL-USDT') == ['4H','1H']
    assert oi.mtf_required_timeframes('FUTURES','4H','CL-USDT') == ['1D','4H']

    # 5. A strong aligned Multi-Asset thesis can reach the stable execution lane.
    mtf={'conflict':False,'complete':True,'dominant_direction':'BEARISH','alignment':'ALIGNED','public_summary':'aligned'}
    r=oi.prepare_operational_intelligence(layers=strong_layers(),symbol='CL-USDT',timeframe='4H',system_type='futures',mtf_context=mtf,research_candidates={})
    assert r['candidate_ready'] is True and r['candidate_action']=='SHORT'
    assert r['risk_class']=='MULTIASSET' and r['official_cell'] is True
    assert (r['default_strategy'] or {}).get('family') == 'MULTIASSET_DELEGATED'
    assert float((r['thesis'] or {}).get('quality') or 0) >= 82

    # 6. Weak evidence still cannot create a Multi-Asset signal.
    rw=oi.prepare_operational_intelligence(layers=weak_layers(),symbol='CL-USDT',timeframe='4H',system_type='futures',mtf_context={'conflict':False,'complete':False,'dominant_direction':'NEUTRAL','alignment':'INCOMPLETE'},research_candidates={})
    assert rw['candidate_ready'] is False

    # 7. Leverage V6 does not collapse to 1x/2x for ordinary technically viable cases.
    scenarios=[(1.0,1.0,28.1),(2.0,2.0,16.5),(3.0,3.0,11.7)]
    for sl,atr,cap in scenarios:
        out=select_risk_budget_leverage(minimum_required=1,sl_distance_pct=sl,max_by_risk=cap,max_by_atr_stress=cap,safety_score=80,timeframe_static_max=20,fallback_exchange_max=50,max_by_liquidation_buffer=cap,emergency_max_leverage=50,quality_score=80)
        assert out and int(out['leverage']) >= 5 and int(out['leverage']) <= int(cap)

    # 8. Runtime reliability comes from closed candles/per-TF caches without DB/AI.
    multi=txt('multiasset_system.py'); app=txt('app.py')
    assert "closed_cutoff" in multi and "_router_cache[timeframe]" in multi
    assert "router_cache_status" in multi
    block=app[app.index('def _multiasset_background_tick'):app.index('def _get_review_trader',app.index('def _multiasset_background_tick'))]
    assert "_multiasset_scan('1D'" in block and "_multiasset_scan('1h'" in block
    assert 'save_runtime_snapshot' not in block and 'supabase' not in block.lower() and 'groq' not in block.lower()
    assert 'threading.Thread' not in block

    # 9. Login/auth flow remains present and untouched conceptually.
    assert "SMARTRADING_SESSION_SECRET" in app and "SMARTRADING_PASSWORD_WILLER" in app
    assert "@app.route('/api/auth/login'" in app and "hmac.compare_digest" in app
    assert "SESSION_COOKIE_HTTPONLY" in app and "SESSION_COOKIE_SECURE" in app and "SESSION_COOKIE_SAMESITE" in app

    print('COMMIT 17.5.1 QA: 9/9 groups PASS')

if __name__=='__main__': main()
