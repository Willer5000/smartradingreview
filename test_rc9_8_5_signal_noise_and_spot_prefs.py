from pathlib import Path
import ast
from datetime import datetime, timezone

import pandas as pd

ROOT = Path(__file__).parent
APP_PATH = ROOT / 'app.py'
SCRIPT_PATH = ROOT / 'static' / 'script.js'
SUPA_PATH = ROOT / 'supabase_client.py'

APP = APP_PATH.read_text(encoding='utf-8')
SCRIPT = SCRIPT_PATH.read_text(encoding='utf-8')
SUPA = SUPA_PATH.read_text(encoding='utf-8')
TREE = ast.parse(APP)


def _load_functions(*names):
    wanted = set(names)
    nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    found = {n.name for n in nodes}
    assert wanted == found, f'missing functions: {wanted - found}'
    mod = ast.Module(body=nodes, type_ignores=[])
    ns = {
        'pd': pd,
        'datetime': datetime,
        'timezone': timezone,
    }
    exec(compile(mod, str(APP_PATH), 'exec'), ns)
    return ns


def test_one_representative_signal_per_symbol_timeframe_prefers_quality():
    ns = _load_functions(
        '_signal_numeric_metric',
        '_representative_signal_score',
        '_signal_source_epoch',
        '_dedupe_representative_signals',
    )
    dedupe = ns['_dedupe_representative_signals']
    rows = [
        {
            'symbol': 'BTC-USDT', 'timeframe': '4h', 'entry': 80000,
            'confidence': 74, 'entry_quality_score': 62,
            'entry_reachability_score': 70, 'execution_safety': 75,
            'risk_reward': 2.1,
            'source_candle_timestamp': '2026-09-20T12:00:00+00:00',
        },
        {
            'symbol': 'BTC-USDT', 'timeframe': '4h', 'entry': 79000,
            'confidence': 74, 'entry_quality_score': 91,
            'entry_reachability_score': 88, 'execution_safety': 82,
            'risk_reward': 2.5,
            'source_candle_timestamp': '2026-09-20T08:00:00+00:00',
        },
        {
            'symbol': 'BTC-USDT', 'timeframe': '12h', 'entry': 78000,
            'confidence': 72, 'entry_quality_score': 80,
            'entry_reachability_score': 80, 'execution_safety': 80,
            'risk_reward': 2.2,
            'source_candle_timestamp': '2026-09-20T00:00:00+00:00',
        },
    ]
    out = dedupe(rows)
    assert len(out) == 2
    btc4 = next(x for x in out if x['timeframe'] == '4h')
    assert btc4['entry'] == 79000


def test_spot_vigent_hides_expired_and_hides_touched_after_touch_candle_close():
    ns = _load_functions(
        '_signal_numeric_metric',
        '_representative_signal_score',
        '_signal_source_epoch',
        '_dedupe_representative_signals',
        '_confirmed_signal_tf_seconds',
        '_spot_entry_touch_display_until',
        '_spot_vigent_visible_cache',
    )
    visible = ns['_spot_vigent_visible_cache']
    now = pd.Timestamp.now(tz='UTC')

    cache = {
        'a': {
            'symbol': 'BTC-USDT', 'timeframe': '4h', 'decision': 'COMPRA_SPOT',
            'entry': 79000, 'confidence': 75, 'entry_quality_score': 90,
            'valid_until': (now + pd.Timedelta(hours=10)).isoformat(),
            'entry_touched': True,
            'entry_touched_at': (now - pd.Timedelta(minutes=5)).isoformat(),
            'entry_display_until': (now + pd.Timedelta(minutes=20)).isoformat(),
        },
        'b': {
            'symbol': 'BTC-USDT', 'timeframe': '4h', 'decision': 'COMPRA_SPOT',
            'entry': 80000, 'confidence': 70, 'entry_quality_score': 60,
            'valid_until': (now + pd.Timedelta(hours=8)).isoformat(),
        },
        'expired': {
            'symbol': 'PAXG-BTC', 'timeframe': '4h', 'decision': 'VENTA_SPOT',
            'entry': 0.055, 'confidence': 80,
            'valid_until': (now - pd.Timedelta(minutes=1)).isoformat(),
        },
    }
    out = visible(cache)
    rows = list(out.values())
    assert len(rows) == 1
    assert rows[0]['entry'] == 79000

    cache['a']['entry_display_until'] = (now - pd.Timedelta(seconds=1)).isoformat()
    out2 = visible(cache)
    rows2 = list(out2.values())
    assert len(rows2) == 1
    assert rows2[0]['entry'] == 80000


def test_futures_vigent_contract_is_waiting_entry_only_and_deduplicated():
    segment = APP[APP.index('def api_futures_signals_active():'):]
    segment = segment[:segment.index("@app.route('/api/futures/signals/previous')")]
    assert "if lifecycle_status != 'waiting_entry':" in segment
    assert 'active_signals = _dedupe_representative_signals(active_signals)' in segment
    assert 'if tiempo_restante <= 0:' in segment

    manual = APP[APP.index('def _futures_vigent_manual_candidates'):APP.index("@app.route('/api/futures/signals/active')")]
    assert "if lifecycle_status != 'waiting_entry':" in manual
    assert 'visible = _dedupe_representative_signals(visible)' in manual


def test_spot_entry_touch_is_persisted_before_telegram_gate_and_monitor_is_deduped():
    monitor = APP[APP.index('def monitor_entries_loop():'):APP.index('# ============================================================================\n# COMMIT 36N')]
    assert '_mark_spot_entry_touched_in_caches(sig, current, shadow)' in monitor
    assert monitor.index('_mark_spot_entry_touched_in_caches') < monitor.index('_spot_entry_alert_allowed(tf)')

    collector = APP[APP.index('def _get_signals_for_entry_monitor():'):APP.index('def _spot_live_market_price')]
    assert 'return _dedupe_representative_signals(signals)' in collector


def test_spot_preferences_fail_closed_and_frontend_keeps_exact_user_selection():
    # Backend no longer re-enables every TF when there is no durable value/read.
    assert "'spot_telegram_timeframes': []" in SUPA
    pref_segment = APP[APP.index('def _normalize_spot_telegram_preferences'):APP.index("@app.route(\n    '/api/user/telegram-preferences'")]
    assert "'spot_telegram_timeframes': []" in pref_segment
    assert '_spot_telegram_session_preferences' in pref_segment

    # Frontend starts empty rather than all checked and freezes the exact click snapshot.
    assert 'spot_telegram_timeframes: []' in SCRIPT
    assert 'spotTelegramPreferencesOwner' in SCRIPT
    assert 'spotTelegramPreferencesRevision' in SCRIPT
    assert 'spotTelegramPreferencesDirty' in SCRIPT
    assert 'const requestedPreferences = {' in SCRIPT
    assert 'spot_telegram_timeframes: [...selectedTimeframes]' in SCRIPT
    assert 'The exact click snapshot is authoritative after a successful write.' in SCRIPT
    assert 'no se activaron temporalidades por defecto' in SCRIPT
