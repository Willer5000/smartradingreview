from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def test_incremental_refresh_is_not_blocking_warmup():
    assert "d['refreshing'] = bool(cache.get('running', False))" in APP
    assert "d['warming_up'] = bool(d['refreshing'] and not has_snapshot)" in APP
    assert "'background_refresh':" in APP
    assert "'cache_ready':" in APP


def test_cached_signals_render_during_background_refresh():
    assert FUTURES.count('const backgroundRefreshHtml = backgroundRefresh') >= 2
    assert 'Las señales actuales siguen visibles.' in FUTURES
    assert 'La última vela cerrada disponible sigue siendo válida para visualización.' in FUTURES


def test_link_bnb_are_visible_but_stay_research_shadow():
    assert "'LINK-USDT': 'LINK/USDT · Research/Shadow'" in INDEX
    assert "'BNB-USDT': 'BNB/USDT · Research/Shadow'" in INDEX
    assert "'LINK-USDT': ['15m', '30m', '1h']" in INDEX
    assert "engine_status == 'RESEARCH_ONLY_SHADOW'" in APP
    assert 'autoridad productiva' in APP and 'guardado manual' in APP
    assert 'RESEARCH / SHADOW' in FUTURES


def test_cache_bust_for_futures_js():
    assert '20260912-H1-NONBLOCKING-SHADOW' in INDEX
