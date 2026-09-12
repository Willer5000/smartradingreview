from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _text(path):
    return (ROOT / path).read_text(encoding='utf-8', errors='ignore')


def test_research_bridge_uses_backend_service_key_and_promotions():
    text = _text('research_bridge.py')
    assert 'CENTRAL_SUPABASE_SERVICE_KEY' in text
    assert 'research_promotions_v1' in text
    assert 'RESEARCH_BRIDGE_CACHE_SECONDS' in text


def test_shadow_bridge_uses_backend_service_key():
    assert 'CENTRAL_SUPABASE_SERVICE_KEY' in _text('research_shadow_bridge.py')


def test_futures_busy_is_202_not_503():
    text = _text('app.py')
    anchor = text.index("@app.route('/api/futures/analyze', methods=['POST'])")
    end = text.index("@app.route('/api/futures/analyze_all/<timeframe>')", anchor)
    block = text[anchor:end]
    assert "}), 202" in block
    assert "'partial': bool(partial_data)" in block
    assert "retry_after_ms': 3000" in block


def test_spot_fast_restore_and_closed_candle_setup():
    text = _text('app.py')
    assert 'def _trigger_spot_fast_restore()' in text
    assert 'time.sleep(90)' in text
    assert 'SPOT · SEÑAL VIGENTE (VELA CERRADA)' in text
    warm = text[text.index('def _start_previous_signals_warmup'):]
    assert 'time.sleep(20 * 60)' not in warm[:5000]


def test_frontend_busy_and_cache_buster():
    js = _text('static/script.js')
    html = _text('templates/index.html')
    assert 'HOTFIX 16.2 — FUTURES BUSY ES ESTADO NORMAL' in js
    assert 'data?.busy' in js
    assert '20260912-H16-2-OPERABILITY' in html
