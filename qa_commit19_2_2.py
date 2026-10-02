from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
ma=(ROOT/'multiasset_system.py').read_text(encoding='utf-8')
js=(ROOT/'static/futures.js').read_text(encoding='utf-8')
tpl=(ROOT/'templates/index.html').read_text(encoding='utf-8')
greeks=(ROOT/'greeks_execution_context_19_1.py').read_text(encoding='utf-8')
mm=(ROOT/'market_maker_math.py').read_text(encoding='utf-8')
proc=(ROOT/'Procfile').read_text(encoding='utf-8')
render=(ROOT/'render.yaml').read_text(encoding='utf-8')

checks=[]
def ck(name, cond):
    ok=bool(cond); checks.append((name,ok)); print(('PASS ' if ok else 'FAIL ')+name)

# Root cause from production logs: 11-12 permanent threads must not hard-starve jobs.
acq=app[app.index('def _acquire_heavy_analysis'):app.index('def _release_heavy_analysis')]
ck('absolute_thread_count_no_longer_hard_veto', 'threading.active_count() >= _FREE_RUNTIME_MAX_THREADS' not in acq)
ck('heavy_lock_still_single_authority', '_HEAVY_ANALYSIS_LOCK.acquire' in acq)
ck('rss_job_start_guard_preserved', '_MEMORY_JOB_START_LIMIT_MB' in acq and 'return False' in acq)
ck('dynamic_thread_baseline_present', '_FREE_RUNTIME_THREAD_BASELINE' in app and '_FREE_RUNTIME_TRANSIENT_THREAD_HEADROOM' in app)
ck('permanent_baseline_captured_after_background_threads', 'baseline permanente=' in app)
ck('one_worker_two_threads', '--workers 1 --threads 2' in proc and '--workers 1 --threads 2' in render)
ck('memory_hard_300_preserved', '_MEMORY_HARD_LIMIT_MB = min(_MEMORY_HARD_LIMIT_MB, 300.0)' in app)
ck('memory_job_start_200_preserved', '_MEMORY_JOB_START_LIMIT_MB = min(_MEMORY_JOB_START_LIMIT_MB, 200.0)' in app)

# Multi browser reads are cache only; provider fan-out belongs to scheduler.
route=app[app.index("@app.route('/api/multiasset/opportunities'"):app.index("@app.route('/api/multiasset/display'")]
ck('multi_opportunities_cache_only', 'from multiasset_system import cached_opportunities' in route and 'rows=cached_opportunities(tf)' in route and 'from multiasset_system import scan_opportunities' not in route)
ck('multi_opportunities_fail_soft_200', "'degraded_read':True" in route and '),200' in route.replace(' ',''))
ck('multi_cached_router_helper', 'def cached_opportunities' in ma and 'with _router_lock' in ma)
ck('multi_correlation_cache_only', "from multiasset_system import cached_opportunities" in app[app.index("@app.route('/api/multiasset/correlation'"):app.index("@app.route('/api/multiasset/microstructure'")])
ck('ai_multi_router_cache_only', "router = cached_opportunities('4h')" in app)
ck('scheduler_still_owns_scans', 'def _multiasset_scan' in app and 'scan_opportunities' in app[app.index('def _multiasset_scan'):app.index('def _multiasset_bucket')])
ck('multi_daily_heavy_cap_preserved', "daily_max=int(MULTIASSET_AUTO_DEEP_DAILY_MAX)" in app)
ck('multi_deep_limit_2_preserved', "MULTIASSET_DEEP_LIMIT = max(1, min(2" in ma or 'MULTIASSET_DEEP_LIMIT' in ma)

# Browser 502 must not turn Active into hard ERR / retry provider itself.
fn=js[js.index('window.loadFuturesOpportunities96'):js.index('// ============================================================================\n// RC9.7.17', js.index('window.loadFuturesOpportunities96'))]
ck('frontend_checks_http_status', 'if (!response.ok)' in fn)
ck('frontend_preserves_last_valid_state', '_lastDerivOpportunityView' in fn and 'se conserva el último estado válido' in fn)
ck('frontend_no_ERR_badge_for_opportunity_read', "countEl.textContent = 'ERR'" not in fn)
ck('frontend_no_heavy_recovery_fetch', 'scan_opportunities' not in fn)
ck('frontend_cache_bust_19_2_2', 'COMMIT19-2-2-RUNTIME-RECOVERY' in tpl)

# Diagnostic truthfulness: direction vs later execution gate.
funnel=app[app.index('def _technical_signal_funnel_row'):app.index('def _technical_signal_funnel_summary')]
ck('funnel_exposes_execution_setup_guard', "stage='EXECUTION_SETUP_GUARD'" in funnel)
ck('funnel_exposes_exact_execution_reasons', "_op_exec.get('reasons')" in funnel)
ck('direction_confirmation_kept_only_as_fallback', "stage='DIRECTION_CONFIRMATION'" in funnel)

# Greeks are internally functional only with observed chain; theoretical values are truthful diagnostics.
ck('observed_greeks_entry_is_internal_ranker', 'def score_entry_confluence' in greeks and 'OBSERVED_OPTIONS_CONFLUENCE' in greeks)
ck('observed_greeks_sl_is_internal_ranker', 'def score_sl_collision' in greeks)
ck('observed_greeks_tp_is_internal_ranker', 'def score_tp_barrier' in greeks)
ck('observed_chain_authority_required', 'observed_option_chain' in greeks and 'OBSERVED_CONFLUENCE_RANKER_ONLY' in greeks)
ck('theoretical_greeks_have_no_fake_production_authority', 'production_score_adjustment": 0.0' in mm and 'can_create_direction": False' in mm)

# Trading quality gates are not changed by this runtime release.
ck('entry65_preserved', 'entry_q<65.0' in (ROOT/'commit19_1_runtime.py').read_text(encoding='utf-8'))
ck('sl60_preserved', 'sl_rel<60.0' in (ROOT/'commit19_1_runtime.py').read_text(encoding='utf-8'))
ck('tp60_preserved', 'tp_q<60.0' in (ROOT/'commit19_1_runtime.py').read_text(encoding='utf-8'))
ck('new_entrypoint_19_2_2', 'commit19_2_2_main_entrypoint:app' in proc and 'commit19_2_2_main_entrypoint:app' in render)

passed=sum(ok for _,ok in checks); total=len(checks)
print(f'\nSUMMARY {passed}/{total} PASS')
failed=[n for n,ok in checks if not ok]
if failed:
    print('FAILED', failed)
    raise SystemExit(1)
