from pathlib import Path
import ast
import math
import pandas as pd

ROOT = Path(__file__).parent
APP_PATH = ROOT / 'app.py'
FUT_JS_PATH = ROOT / 'static' / 'futures.js'
APP = APP_PATH.read_text(encoding='utf-8')
FUT_JS = FUT_JS_PATH.read_text(encoding='utf-8')
TREE = ast.parse(APP)


def _load_functions(*names):
    wanted = set(names)
    nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    found = {n.name for n in nodes}
    assert wanted == found, f'missing functions: {wanted - found}'
    mod = ast.Module(body=nodes, type_ignores=[])
    ns = {'math': math, 'pd': pd}
    exec(compile(mod, str(APP_PATH), 'exec'), ns)
    return ns


def test_spot_validity_is_geometry_driven_and_can_be_one_or_many_candles():
    ns = _load_functions('_signal_geometry_context', '_spot_entry_wait_bars')
    f = ns['_spot_entry_wait_bars']
    near = {
        'levels': {
            'entry_timing_mode': 'NEAR_REACTION',
            'setup_family': 'BREAKOUT_RETEST',
            'entry_distance_atr': 0.20,
            'entry_reachability_score': 95,
        },
        'market_regime': {'regime': 'TRENDING_BULL', 'confidence': 80},
    }
    deep = {
        'levels': {
            'entry_timing_mode': 'DEEP_PULLBACK_LIMIT',
            'setup_family': 'PULLBACK',
            'entry_distance_atr': 2.0,
            'entry_reachability_score': 35,
        },
        'market_regime': {'regime': 'TRENDING_BULL', 'confidence': 80},
    }
    assert f(near, '4h') == 1
    assert 6 <= f(deep, '4h') <= 12
    # Same geometry = same candle count; TF only converts candles to clock time.
    assert f(deep, '4h') == f(deep, '1D')


def test_futures_validity_can_be_one_candle_and_deep_setup_can_wait_longer():
    ns = _load_functions('_signal_geometry_context', '_futures_entry_wait_bars')
    f = ns['_futures_entry_wait_bars']
    near = {
        'symbol': 'BTC-USDT',
        'levels': {
            'entry_timing_mode': 'NEAR_REACTION',
            'setup_family': 'BREAKOUT_RETEST',
            'entry_distance_atr': 0.15,
            'entry_reachability_score': 92,
        },
        'market_regime': {'regime': 'TRENDING_BULL', 'confidence': 80},
        'indicators': {'adx': 35},
    }
    deep = {
        'symbol': 'BTC-USDT',
        'levels': {
            'entry_timing_mode': 'DEEP_PULLBACK_LIMIT',
            'setup_family': 'PULLBACK',
            'entry_distance_atr': 2.2,
            'entry_reachability_score': 40,
        },
        'market_regime': {'regime': 'TRENDING_BULL', 'confidence': 80},
        'indicators': {'adx': 35},
        'multi_timeframe_alignment': 'aligned bullish',
    }
    assert f(near, '1h') == 1
    assert 6 <= f(deep, '1h') <= 10


def test_policy_versions_and_persistence_follow_technical_validity():
    assert "RC9_8_1_SPOT_TECHNICAL_VALIDITY_V4" in APP
    assert "RC9_8_1_TECHNICAL_VALIDITY_V4" in APP
    assert '_spot_signals_snapshot_ttl_seconds(previous, vigent)' in APP
    assert '_futures_snapshot_ttl_seconds(serial_data)' in APP
    assert "data['analysis'] = {}" in APP
    assert 'if not (data.get(\'analysis\') or data.get(\'lifecycle\'))' in APP


def test_telegram_spot_is_one_confirmation_per_timeframe_but_entry_stays_enabled():
    assert 'return f"spot|{timeframe}|{close_key}"' in APP
    assert '_send_spot_confirmed_timeframe_alerts(resultados)' in APP
    # Spot entry monitor still exists and is independent.
    assert "# 1. Spot: monitorizar TODA señal oficial que siga esperando Entry" in APP
    assert '_entry_alert_mark_sent(symbol, tf, candle_ts)' in APP


def test_telegram_futures_is_confirmed_only():
    # Confirmed path is still called from the closed-candle engine.
    assert "_send_confirmed_signal_telegram(\n                    'futures'," in APP
    # Futures confirmed sender requires engine publication validation.
    assert "if publication_status != 'EXECUTABLE_SIGNAL':\n            return False" in APP
    # Official Entry shadow monitor remains for lifecycle learning but recipients are disabled.
    assert "users = []" in APP
    # Personal/saved Futures lifecycle notifier is intentionally silent.
    segment = APP[APP.index('def _send_saved_futures_lifecycle_notifications():'):]
    segment = segment[:segment.index('\ndef saved_futures_lifecycle_loop')]
    assert 'return 0' in segment


def test_confirmed_cold_start_window_no_longer_depends_on_process_started_at():
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == '_confirmed_signal_recent_enough')
    source = ast.get_source_segment(APP, node) or ''
    assert '_CONFIRMED_SIGNAL_PROCESS_STARTED_AT' not in source
    assert 'recent_window' in source



def test_spot_confirmed_event_key_deduplicates_symbols_with_same_tf_close():
    ns = _load_functions(
        '_confirmed_signal_tf_seconds',
        '_confirmed_signal_close_timestamp',
        '_confirmed_signal_event_key',
    )
    key = ns['_confirmed_signal_event_key']
    a = {
        'symbol': 'BTC-USDT', 'timeframe': '4h', 'decision': 'COMPRA_SPOT',
        'source_candle_timestamp': '2026-09-20T12:00:00+00:00',
    }
    b = {
        'symbol': 'PAXG-BTC', 'timeframe': '4h', 'decision': 'VENTA_SPOT',
        'source_candle_timestamp': '2026-09-20T12:00:00+00:00',
    }
    assert key('spot', a) == key('spot', b)
    assert key('futures', a) != key('futures', b)


def test_snapshot_ttl_extends_beyond_signal_valid_until():
    ns = _load_functions('_spot_signals_snapshot_ttl_seconds', '_futures_snapshot_ttl_seconds')
    ns['_SPOT_SIGNALS_CACHE_MIN_TTL'] = 48 * 3600
    ns['_SPOT_SIGNALS_CACHE_MAX_AGE'] = 90 * 24 * 3600
    ns['_FUTURES_SNAPSHOT_MIN_TTL'] = 3 * 24 * 3600
    ns['_FUTURES_SNAPSHOT_MAX_AGE'] = 45 * 24 * 3600
    future = (pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=10)).isoformat()
    spot_ttl = ns['_spot_signals_snapshot_ttl_seconds'](
        {'x': {'valid_until': future}}, {}
    )
    assert spot_ttl >= 10 * 24 * 3600
    fut_ttl = ns['_futures_snapshot_ttl_seconds']({
        'lifecycle': {'s': {'lifecycle_status': 'waiting_entry', 'valid_until': future}}
    })
    assert fut_ttl >= 10 * 24 * 3600

def test_futures_active_lane_has_bounded_watchlist_and_no_63_cell_scan():
    assert 'def _futures_intrabar_watchlist_cells' in APP
    assert 'def _schedule_one_futures_watchlist_preview' in APP
    assert 'most ONE technically relevant extra cell' in APP
    assert '}, 90000);' in FUT_JS
