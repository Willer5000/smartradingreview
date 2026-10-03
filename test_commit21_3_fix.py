from pathlib import Path
import py_compile
import re

ROOT = Path(__file__).resolve().parent

def test_python_compile():
    for name in ["app.py", "premium_path_expansion_20.py", "cpqe_19_2_4.py", "macro_context.py", "commit21_3_main_entrypoint.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

def test_contract_thresholds_unchanged():
    p = (ROOT / "premium_path_expansion_20.py").read_text()
    assert "PREMIUM_MIN_SAFETY = 75.0" in p
    assert "PREMIUM_MIN_TP = 55.0" in p
    assert "PREMIUM_MIN_SL = 60.0" in p
    assert "PREMIUM_MIN_RR = 1.8" in p
    assert "PREMIUM_MAX_RR = 3.5" in p
    assert "ROUTE_RSS_HARD_MB = 235.0" in p
    assert "ROUTE_MAX_RSS_AFTER_SHED_MB = 222.0" in p

def test_cpqe_context_plumbing():
    cpqe = (ROOT / "cpqe_19_2_4.py").read_text()
    ppe = (ROOT / "premium_path_expansion_20.py").read_text()
    assert "_cpqe_context" in cpqe
    assert "ctx.get(\"trend\")" in cpqe
    assert "ctx.get(\"structure\")" in cpqe
    assert "_revalidate_with_full_context" in ppe

def test_promoted_route_uses_route_family_guard():
    app = (ROOT / "app.py").read_text()
    assert "_promoted_family" in app
    assert "strategy_route_family" in app

def test_cache_bust_and_html_nostore():
    html = (ROOT / 'templates' / 'index.html').read_text()
    app = (ROOT / 'app.py').read_text()
    assert 'COMMIT21-3-FIX' in html
    assert "'cache-control'".lower() in app.lower()

def test_frontend_request_governor():
    fut = (ROOT / 'static' / 'futures.js').read_text()
    assert '_futLaneCooldown' in fut
    assert 'opportunityLoading' in fut
    assert 'previousLoading' in fut
    assert '8000' in fut or '6000' in fut

def test_visuals_are_independent():
    js = (ROOT / "static" / "script.js").read_text()
    assert "Promise.resolve(window.loadLightVisualsForSignal?.(symbol, timeframe))" in js
    fut = (ROOT / "static" / "futures.js").read_text()
    assert "/api/futures/visuals" in js
    assert "loadLightVisualsForSignal" in fut

def test_light_visual_singleflight():
    js = (ROOT / 'static' / 'script.js').read_text()
    assert '__SMARTTRADING_LIGHT_VISUAL_STATE__' in js
    assert 'state.inflightKey' in js
    assert '45000' in js

def test_macro_timeout_and_runtime():
    macro = (ROOT / "macro_context.py").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert 'os.getenv("MACRO_HTTP_TIMEOUT", "3")' in macro
    assert 'key: MACRO_HTTP_TIMEOUT' in render
    assert 'value: "225"' in render
    assert 'value: "235"' in render
    assert 'value: "300"' in render

if __name__ == '__main__':
    for fn in [test_python_compile, test_contract_thresholds_unchanged, test_cpqe_context_plumbing, test_promoted_route_uses_route_family_guard, test_cache_bust_and_html_nostore, test_frontend_request_governor, test_visuals_are_independent, test_light_visual_singleflight, test_macro_timeout_and_runtime]:
        fn()
    print('COMMIT 21.3 QA: 9 PASS')
