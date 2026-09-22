from pathlib import Path
import importlib.util
import sys
import time

ROOT = Path(__file__).resolve().parent


def _load_kucoin_cache():
    spec = importlib.util.spec_from_file_location('kucoin_cache_rc987', ROOT / 'kucoin_cache.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeResponse:
    status_code = 200
    headers = {'content-type': 'application/json'}
    text = ''

    def __init__(self, payload):
        self._payload = payload
        self.content = repr(payload).encode('utf-8')

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({'url': url, 'params': dict(params or {}), 'timeout': timeout})
        return _FakeResponse(self.payload)


def _spot_rows(n=400):
    now = int(time.time())
    # KuCoin Spot: newest first, columns time/open/close/high/low/volume/turnover
    rows = []
    for i in range(n):
        ts = now - i * 3600
        base = 100.0 + i * 0.01
        rows.append([
            str(ts), str(base), str(base + 0.1), str(base + 0.2),
            str(base - 0.2), '12.5', '1250.0'
        ])
    return rows


def test_spot_ohlcv_preserves_full_history_and_reuses_cache(monkeypatch):
    kc = _load_kucoin_cache()
    kc.clear_cache()
    rows = _spot_rows(400)
    session = _FakeSession({'code': '200000', 'data': rows})
    monkeypatch.setattr(kc, '_get_session', lambda: session)

    first = kc.fetch_kucoin_candles('BTC-USDT', '1h', timeout=3)
    second = kc.fetch_kucoin_candles('BTC-USDT', '1h', timeout=3)
    assert first is not None and second is not None
    assert len(first) == 400
    assert len(second) == 400
    assert len(session.calls) == 1  # segunda lectura sale de caché
    params = session.calls[0]['params']
    assert params == {'symbol': 'BTC-USDT', 'type': '1hour'}

    stats = kc.get_cache_stats()
    assert stats['fetches'] == 1
    assert stats['hits'] >= 1
    assert stats['bytes_received'] > 0
    assert stats['candles_received'] == 400
    assert 'request_candle_limit' not in stats


def test_futures_bandwidth_policy_preserves_shadow_authority_boundaries():
    src = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
    assert "FUTURES_MICROSTRUCTURE_TTL_SECONDS = max(120" in src
    assert "'600'" in src
    assert "FUTURES_MICROSTRUCTURE_CACHE_MAX_ENTRIES = max(8, min(24" in src
    assert "FUTURES_DATA_CACHE_MAX_ENTRIES = max(1" in src
    assert "'8'" in src
    # Q3 remains observational; optimization must not grant or remove authority.
    for invariant in (
        "'mode':\n            'SHADOW_OBSERVATION'",
        "'affects_entry':\n            False",
        "'affects_safety':\n            False",
        "'affects_publication':\n            False",
        "'affects_leverage':\n            False",
    ):
        assert invariant in src
    for category in (
        'micro_orderbook', 'micro_trades', 'micro_funding',
        'micro_mark_index', 'micro_open_interest', 'ohlcv', 'contract_spec'
    ):
        assert category in src


def test_app_compresses_only_transfer_representation_and_exposes_local_stats():
    src = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'def _rc987_compress_text_response(response):' in src
    assert "gzip.compress(raw, compresslevel=4)" in src
    assert "response.headers['Content-Encoding'] = 'gzip'" in src
    assert "@app.route('/api/system/bandwidth-stats'" in src
    assert "scope': 'PROCESS_SINCE_LAST_RESTART'" in src
    # Price cache is presentation/alert plumbing only; no trading recalculation.
    assert '_SPOT_LEVEL1_CACHE_TTL_SECONDS = 20' in src


def test_frontend_does_not_poll_hidden_spot_or_duplicate_futures_lane_polling():
    js = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
    assert 'document.hidden || window.IS_FUTURES_PAGE || !isAuthenticated()' in js
    assert 'RC9.8.7: sólo Spot visible; Futures no duplica polling' in js
