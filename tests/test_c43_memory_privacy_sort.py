"""C43: isolated checks; no real network, Supabase, Telegram or trading engine."""
from __future__ import annotations
import ast
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis_cache_compact_c43 import pack_cache_entry, read_cache_entry, compact_cache_statistics


def test_cache_is_lossless_and_isolated_across_three_concurrent_clients():
    payload = {
        'symbol': 'BTC-USDT', 'timeframe': '1h',
        'decision': {'action': 'SHORT', 'confidence': 88.0},
        'levels': {'entry': 58000.25, 'stop_loss': 59000.75, 'take_profit': 56000.0},
        'chart': [1.33333] * 50000,
        'confirmation': {'signal_id': 'id-1', 'source_valid_until': '2026-12-15T00:00:00Z'},
    }
    saved = pack_cache_entry(payload)
    assert 'packed' in saved  # large, repetitive input can be compacted
    assert len(saved['packed']) < saved['raw_bytes'] * 0.75
    assert read_cache_entry(saved, isolated=True) == payload

    def client(i):
        view = read_cache_entry(saved, isolated=True)
        view['decision']['confidence'] = i
        view['chart'][0] = i
        return view

    with ThreadPoolExecutor(max_workers=3) as pool:
        views = list(pool.map(client, (10, 20, 30)))
    assert [view['decision']['confidence'] for view in views] == [10, 20, 30]
    assert read_cache_entry(saved, isolated=True) == payload
    assert compact_cache_statistics({('BTC-USDT', '1h'): saved})['packed_entries'] == 1


def test_cache_fallback_legacy_and_unpickleable_objects():
    class CannotSerialize:
        def __deepcopy__(self, memo):
            return CannotSerialize()
    item = {'custom': CannotSerialize(), 'decision': {'action': 'LONG'}}
    packed = pack_cache_entry(item)
    assert 'data' in packed and packed['data'] is not item
    second = read_cache_entry(packed, isolated=True)
    second['decision']['action'] = 'SHORT'
    assert packed['data']['decision']['action'] == 'LONG'
    assert read_cache_entry({'data': {'saved': 1}}, isolated=True) == {'saved': 1}


def test_pandas_payload_keeps_exact_rows_and_types():
    try:
        import pandas as pd
    except ImportError:
        return
    df = pd.DataFrame({'close': [100.11] * 3000, 'volume': [4500] * 3000})
    payload = {'df': df, 'decision': {'action': 'NO_OPERAR'}}
    entry = pack_cache_entry(payload)
    decoded = read_cache_entry(entry, isolated=True)
    assert decoded['df'].equals(df)
    assert decoded['decision'] == payload['decision']
    decoded['df'].iloc[0, 0] = 22
    assert read_cache_entry(entry)['df'].iloc[0, 0] == 100.11


def test_private_guardian_and_save_routes_not_modified():
    # Only cache, monitoring and UI-order code may change. Checking AST of
    # user-specific writes prevents accidentally changing privacy or lifecycle.
    import zipfile
    zips = list(ROOT.parent.parent.glob('smartradingreview-main ULTIMO FUNCIONAL*.zip'))
    if not zips:
        return
    with zipfile.ZipFile(zips[0]) as archive:
        original = archive.read('smartradingreview-main/app.py').decode('utf-8')
    old_ast = ast.parse(original)
    new_ast = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    names = ('api_saved_signals_list', 'api_saved_signals_create',
             'api_saved_signals_update', 'api_saved_signals_close',
             'api_saved_signals_delete')
    for name in names:
        old = next((n for n in old_ast.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        new = next((n for n in new_ast.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        assert (old is None) == (new is None), name
        if old is not None:
            assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False), name


def test_no_trading_routes_modified():
    s = (ROOT/'app.py').read_text(encoding='utf-8')
    assert '_HEAVY_ANALYSIS_LOCK.acquire(timeout=timeout)' in s
    assert '_commit346_cgroup_budget(_reserved_mb)' in s
    assert "'c43_memory_jobs':_c43_memory_snapshot()" in s
    assert "'c43_compact': _c43_cache_stats(_ANALYSIS_CACHE)" in s
