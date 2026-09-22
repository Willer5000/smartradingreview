from pathlib import Path

ROOT = Path(__file__).resolve().parent

def text(name):
    return (ROOT / name).read_text(encoding='utf-8')

def test_trading_safety_contract_unchanged():
    s = text('futures_system.py')
    assert "'minimum_execution_safety': 65.0" in s
    assert "'minimum_publication_execution_safety': 75.0" in s
    assert "'minimum_publication_tp_quality': 55.0" in s
    assert "'minimum_publication_sl_avoidance_quality': 60.0" in s
    assert "'minimum_publication_rr': 1.8" in s

def test_render_bandwidth_and_quota_guards():
    s = text('render.yaml')
    assert 'key: FUTURES_DATA_CACHE_MAX_ENTRIES\n        value: "8"' in s
    assert 'key: FUTURES_MICROSTRUCTURE_CACHE_MAX_ENTRIES\n        value: "20"' in s
    assert 'key: FREE_PLAN_LOCKDOWN\n        value: "1"' in s
    assert 'key: MAIN_SUPABASE_DAILY_BUDGET_MB\n        value: "12"' in s
    assert 'key: AI_GROQ_DAILY_TOKEN_BUDGET\n        value: "160000"' in s

def test_groq_model_and_single_quota_read_hardening():
    s = text('ai_advisor.py')
    assert 'openai/gpt-oss-20b' in s
    assert '_GROQ_DEPRECATED_MODEL_MAP' in s
    assert '"groq/compound": "openai/gpt-oss-20b"' in s
    assert '"llama-3.1-8b-instant": "openai/gpt-oss-20b"' in s
    assert 'qwen/qwen3.8-27b' in s
    assert 'def _read_usage_window_once' in s
    block = s[s.index('def get_ai_quota_status'):s.index('def _quota_allowed')]
    assert '_count_usage(' not in block
    assert 'groq_tokens_daily' in block
    assert 'GROQ_DAILY_TOKEN_RESERVE' in s

def test_security_lockdown_covers_server_tables():
    s = text('schema_commit10_final_security_lockdown.sql').lower()
    for table in ['signals','signal_results','saved_signals','user_preferences','ai_usage_events','runtime_snapshots_v1']:
        assert f'alter table public.{table} enable row level security;' in s
    assert 'revoke execute on function public.cleanup_research_federation_v1()' in s
    assert 'security_invoker = true' in s

def test_reachability_learning_stays_governed():
    challenger = text('execution_challenger_lab.py')
    governance = text('governed_self_calibration.py')
    assert 'REACHABILITY_BALANCED' in challenger
    assert 'initial_gap * 0.35' in challenger
    assert 'atr * 0.35' in challenger
    assert 'baseline_risk * 0.05' in challenger
    assert 'new_risk > base_risk * 1.05' in challenger
    assert 'CANARY_FRACTION = 0.25' in governance
    assert 'ALPHA_DECAY' in governance.upper() or 'DECAY' in governance.upper()
