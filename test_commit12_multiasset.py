from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parent

def read(p): return (ROOT/p).read_text(encoding='utf-8')

def test_multiasset_module_has_bounded_universe_router_and_no_llm_db_scanner():
    s=read('multiasset_system.py')
    for sym in ('SPY-USDT','QQQ-USDT','CL-USDT','NATGAS-USDT','COPPER-USDT','XAG-USDT','KSTR-USDT'):
        assert sym in s
    assert "MULTIASSET_DEEP_LIMIT = max(1, min(2" in s
    assert "'router':'SEQUENTIAL_NO_DB_NO_LLM'" in s
    assert "'auto_ai_calls':0" in s
    assert "'scanner_supabase_writes':0" in s
    assert 'scan_opportunities' in s

def test_human_frontend_names_and_third_tab_exist():
    t=read('templates/index.html')
    assert 'MULTI-ACTIVO' in t and 'href="/multiasset"' in t
    assert "'CL-USDT': 'CL (Petróleo WTI)'" in t
    assert "'SPY-USDT': 'SPY (S&P 500)'" in t
    assert "window.IS_MULTI_ASSET_PAGE" in t
    assert "window.DERIV_API_BASE" in t

def test_multiasset_reuses_one_heavy_slot_and_no_new_background_thread():
    a=read('app.py')
    assert "owner.startswith(('futures-ui:', 'spot-ui:', 'multi-ui:'))" in a
    assert 'def _multiasset_background_tick' in a
    assert '_multiasset_background_tick()' in a
    assert "name='multiasset" not in a and 'name="multiasset' not in a
    assert 'One deep cell per 20s loop max' in a

def test_market_specific_strategy_bank_specialists_and_macro_gate():
    s=read('multiasset_system.py')
    for key in ('US_INDEX','ENERGY','INDUSTRIAL_METAL','PRECIOUS_METAL','CHINA_INDEX'):
        assert key in s
    assert 'MULTIASSET_STRATEGY_BANK' in s
    assert 'SPECIALIST_BY_CLASS' in s
    assert "gate='WAIT_EVENT'" in s
    assert 'Liquidity>Sweep>MSS>Displacement>POI>Entry' in s
    assert "preferred_for_context" in s

def test_reviewtrader_can_evaluate_multiasset_without_new_tables():
    r=read('review_trader.py')
    assert 'def _is_multiasset_signal' in r
    assert 'MULTI::' in r
    assert 'from multiasset_system import multiasset_system as futures_engine' in r
    assert "('1h','4h','1D')" in r
    # Commit 12 adds no schema/migration artifact.
    assert not any(p.name.endswith('.sql') for p in ROOT.iterdir())

def test_telegram_is_compact_confirmed_and_guardian_has_separate_route():
    a=read('app.py')
    assert "_send_confirmed_signal_telegram('multiasset', result)" in a
    assert "@app.route('/api/multiasset/position-guardian'" in a
    assert "@app.route('/api/multiasset/analyze'" in a
    assert 'sendPhoto' not in a and 'sendDocument' not in a

def test_ai_shares_global_budget_and_prompt_is_bounded():
    a=read('app.py'); ai=read('ai_advisor.py'); ui=read('static/ai_assistant.js')
    assert "elif market == 'MULTIASSET':" in a
    assert "context['signals'] = candidates[:4]" in a
    assert "'automatic_multiasset_llm_calls': 0" in a
    assert 'shares_global_budget' in a
    assert 'MULTIASSET' in ai and 'MULTIASSET' in ui

def test_render_guards_do_not_raise_worker_threads_or_supabase_budget():
    y=read('render.yaml')
    assert 'MULTIASSET_ROUTER_TTL_SECONDS' in y
    assert 'MULTIASSET_DEEP_LIMIT' in y
    assert 'MULTIASSET_AI_AUTOMATIC_ENABLED' in y
    assert 'MAIN_SUPABASE_DAILY_BUDGET_MB\n        value: "12"' in y
    assert 'workers 1 --threads 2' in y

def test_python_sources_parse():
    for name in ('app.py','futures_system.py','multiasset_system.py','review_trader.py','saved_signals.py','ai_advisor.py'):
        ast.parse(read(name), filename=name)
