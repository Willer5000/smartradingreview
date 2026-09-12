from pathlib import Path
import pandas as pd


def test_historical_research_is_importable():
    from historical_research import run_historical_strategy_research
    assert callable(run_historical_strategy_research)


def test_historical_replay_has_embargo_split():
    from historical_research import run_historical_strategy_research
    n=180
    close=[100 + i*0.15 + ((i%7)-3)*0.05 for i in range(n)]
    df=pd.DataFrame({
        'open':close,
        'high':[x+0.7 for x in close],
        'low':[x-0.7 for x in close],
        'close':close,
        'volume':[1000]*n,
    })
    out=run_historical_strategy_research(df,'BTC-USDT','30m',120)
    assert out['production_authority'] is False
    if out.get('resolved'):
        assert (out.get('split') or {}).get('methodology') == 'BOUNDED_CLOSED_CANDLE_REPLAY_WITH_EMBARGO'


def test_hvn_resistance_branch_is_not_duplicate_elif():
    text=(Path(__file__).resolve().parent/'app.py').read_text(encoding='utf-8')
    assert "hvn_neutral_band = 0.0025" in text
    assert "elif current_price >= poc_price * (1 + hvn_neutral_band)" in text


def test_shadow_contract_rejects_non_strategy_components():
    import research_shadow_bridge as rs
    feat={'strategies':['PULLBACK BAJISTA']}
    assert rs._matches({'component':'STRATEGY:PULLBACK BAJISTA'},feat) is True
    assert rs._matches({'component':'RSI_ALIGNMENT:ALIGNED'},feat) is False


def test_modern_secret_is_not_forced_into_bearer(monkeypatch):
    import research_shadow_bridge as rs
    monkeypatch.setenv('CENTRAL_SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setenv('CENTRAL_SUPABASE_SERVICE_KEY','sb_secret_example')
    _,headers=rs._headers()
    assert headers['apikey']=='sb_secret_example'
    assert 'Authorization' not in headers
