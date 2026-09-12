from pathlib import Path

ROOT = Path(__file__).resolve().parent
FUTURES = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def test_futures_asset_is_cache_busted_for_f3():
    assert "futures.js') }}?v=20260912-F3-SIGNAL-CONTEXT" in INDEX


def test_active_cards_open_canonical_signal_context():
    assert 'onclick="window.openFuturesActiveSignal(' in FUTURES
    assert 'window.__FUTURES_SIGNAL_CONTEXT_VERSION__ = \'F3\'' in FUTURES


def test_bridge_is_reinstalled_on_click():
    assert 'function _futuresInstallSignalRecommendationBridge()' in FUTURES
    open_block = FUTURES.split('window.openFuturesActiveSignal = function', 1)[1]
    assert '_futuresInstallSignalRecommendationBridge();' in open_block


def test_origin_and_current_market_are_separate():
    assert 'RECOMENDACIÓN QUE ORIGINÓ ESTA SEÑAL' in FUTURES
    assert 'Estado actual del mercado · no reemplaza la señal' in FUTURES


def test_no_f1_auto_invalidation_frontend_logic():
    assert 'invalidated_before_entry' not in FUTURES
