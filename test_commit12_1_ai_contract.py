from pathlib import Path
ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
ai=(ROOT/'ai_advisor.py').read_text(encoding='utf-8')
js=(ROOT/'static'/'ai_assistant.js').read_text(encoding='utf-8')
checks={
 'advice_spot_240': "'SPOT': 240" in app and 'interval_minutes = 240' in ai,
 'advice_futures_30': "'FUTURES': 30" in app and 'interval_minutes = 30' in ai,
 'advice_multi_60': "'MULTIASSET': 60" in app and 'interval_minutes = 60' in ai,
 'manual_spot_3x4h': 'MANUAL_SPOT_WINDOW_MINUTES' in ai and 'MANUAL_SPOT_WINDOW_LIMIT' in ai,
 'manual_futures_30m': 'MANUAL_FUTURES_MIN_INTERVAL_MINUTES' in ai and '"30"' in ai,
 'manual_multi_60m': 'MANUAL_MULTI_MIN_INTERVAL_MINUTES' in ai and '"60"' in ai,
 'cross_tab_quota': 'quota_market=('
                     in app and 'cross_tab_question' in app,
 'multi_symbol_prompt': 'mentioned_symbols' in app and 'requested_symbols[:7]' in app,
 'compact_comparison': "'comparison_compact':True" in app and "'alternatives':rows[1:3]" not in app,
 'cross_market_cache_only': '_ai_cross_market_cached_snapshot' in app and 'CACHE_ONLY_ZERO_EXTRA_IO' in app,
 'advice_output_guard_450': '450' in ai and 'HOURLY_MARKET_ADVICE' in ai,
 'same_global_token_budget': 'AI_GROQ_DAILY_TOKEN_BUDGET", "160000"' in ai,
 'frontend_quota_copy': '3 preguntas cada 4 h' in js and '1 pregunta cada 30 min' in js and '1 pregunta cada hora' in js,
 'frontend_cross_tab_hint': 'otra pestaña' in js.lower() and 'varios activos' in js.lower(),
 'question_1200': 'maxlength="1200"' in js and ").strip()[:1200]" in app,
 'multi_guardian_user_filter': "user_name=user" in app and '/api/multiasset/position-guardian' in app,
}
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items(): print(('PASS' if v else 'FAIL'),k)
if failed: raise SystemExit('FAILED: '+', '.join(failed))
print(f'{len(checks)}/{len(checks)} PASS')
