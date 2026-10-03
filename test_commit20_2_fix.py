from pathlib import Path

ROOT = Path(__file__).resolve().parent

def test_render_uses_commit20_2_entrypoint():
    assert 'commit20_2_main_entrypoint:app' in (ROOT / 'Procfile').read_text(encoding='utf-8')
    assert 'commit20_2_main_entrypoint:app' in (ROOT / 'render.yaml').read_text(encoding='utf-8')

def test_app_has_guarded_auto_install():
    s=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'COMMIT 20.2 — GUARDED AUTO-INSTALL' in s
    assert 'premium_path_expansion_20 import install' in s

def test_memory_policy_is_20_2():
    s=(ROOT/'premium_path_expansion_20.py').read_text(encoding='utf-8')
    assert 'start = min(215.0' in s
    assert 'soft = min(235.0' in s
    assert 'memory_hard_limit_mb' in s

def test_multi_saved_chart_is_direct_and_market_aware():
    s=(ROOT/'premium_path_expansion_20.py').read_text(encoding='utf-8')
    assert 'MULTIASSET_KUCOIN_REST' in s
    assert "if market=='multiasset':" in s

def test_multi_saved_ui_is_enabled():
    s=(ROOT/'static'/'futures.js').read_text(encoding='utf-8')
    assert 'window.IS_FUTURES_PAGE && !window.IS_MULTI_ASSET_PAGE' in s
    assert 'window.IS_FUTURES_PAGE || window.IS_MULTI_ASSET_PAGE' in s

def test_cache_bust():
    s=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
    assert '20261003-COMMIT20-2-FIX' in s
