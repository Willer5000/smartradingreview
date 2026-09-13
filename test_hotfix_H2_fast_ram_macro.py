from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUT = (ROOT / 'futures_system.py').read_text(encoding='utf-8')
SCRIPT = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


def test_fast_timeframes_keep_full_analysis_but_trim_only_ui_copy():
    assert "'5m': 96" in APP
    assert "'15m': 112" in APP
    assert "'30m': 128" in APP
    assert "runtime_memory_profile'] = 'FAST_LIGHT'" in APP
    assert "runtime_full_analysis'] = True" in APP
    assert "df_for_ui = df.tail(fast_ui_points)" in APP
    assert "build_execution_challenger_lab(resultado_final, df)" in APP


def test_background_skips_same_closed_candle_instead_of_recomputing_it():
    assert 'def _futures_combo_due_for_closed_candle' in APP
    assert "source_candle_close_timestamp" in APP
    assert 'next_due = close_ts.timestamp() + float(tf_seconds) + 8.0' in APP
    assert '_futures_combo_due_for_closed_candle(' in APP


def test_microstructure_cache_is_bounded_and_visual_is_compact():
    assert 'FUTURES_MICROSTRUCTURE_CACHE_MAX_ENTRIES' in FUT
    assert 'fast-futures-memory-badge' in INDEX
    assert "const depthRows = fastTradeUi ? 6 : 10" in SCRIPT
    assert 'height: fastTradeUi ? 270 : 360' in SCRIPT
    assert '20260913-H3-NO-INFINITE-LOADING' in INDEX


def test_macro_hides_undated_and_over_24h_headlines():
    spec = importlib.util.spec_from_file_location('macro_context_h2', ROOT / 'macro_context.py')
    macro = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(macro)
    macro._DB_HYDRATED = True
    now = datetime.now(timezone.utc)
    with macro._LOCK:
        macro._CACHE['news'] = [
            {'id':'fresh','kind':'HEADLINE','title_es':'Fresh','source':'Test','url':'https://example.com/fresh',
             'published_at': (now - timedelta(hours=2)).isoformat().replace('+00:00','Z'),
             'risk_level':'LOW','risk_score':10,'categories':[{'label_es':'Macro'}]},
            {'id':'old','kind':'HEADLINE','title_es':'Old','source':'Test','url':'https://example.com/old',
             'published_at': (now - timedelta(hours=30)).isoformat().replace('+00:00','Z'),
             'risk_level':'HIGH','risk_score':70,'categories':[{'label_es':'Macro'}]},
            {'id':'undated','kind':'HEADLINE','title_es':'Undated','source':'Test','url':'https://example.com/undated',
             'published_at': None,'risk_level':'HIGH','risk_score':70,'categories':[{'label_es':'Macro'}]},
        ]
        macro._CACHE['calendar'] = []
        macro._CACHE['news_fetched_at'] = 0.0
        macro._CACHE['calendar_fetched_at'] = 0.0
        macro._CACHE['errors'] = []
    snap = macro.get_macro_context_snapshot(fetch_if_stale=False)
    ids = [row.get('id') for row in snap['headlines']]
    assert ids == ['fresh']
    assert snap['fresh_headlines'] == 1
    assert snap['headline_max_age_hours'] == 24
    assert snap['news_refresh_seconds'] == 900


def test_macro_frontend_displays_news_age():
    assert 'item?.age_hours' in SCRIPT
    assert 'hace ${Math.round(ageHours)} h' in SCRIPT
