from pathlib import Path
from market_maker_math import theoretical_gamma_shape

ROOT=Path(__file__).resolve().parent
checks={}
def ck(name, cond):
    checks[name]=bool(cond)
    print(('PASS' if cond else 'FAIL'), name)

app=(ROOT/'app.py').read_text(encoding='utf-8')
ma=(ROOT/'multiasset_system.py').read_text(encoding='utf-8')
qs=(ROOT/'live_quant_synthesis_commit19_1.py').read_text(encoding='utf-8')
mm=(ROOT/'market_maker_math.py').read_text(encoding='utf-8')
js=(ROOT/'static/market_maker_frontend.js').read_text(encoding='utf-8')
fy=(ROOT/'futures_system.py').read_text(encoding='utf-8')
render=(ROOT/'render.yaml').read_text(encoding='utf-8')
proc=(ROOT/'Procfile').read_text(encoding='utf-8')

# Greeks coverage: numerical BS sensitivities for arbitrary prices/assets.
for label,spot,vol in [('AVAX',14.5,.80),('PAXG_USDT',3900,.22),('PAXG_BTC',.045,.35),('CL',96,.35),('SPY',710,.20)]:
    x=theoretical_gamma_shape(spot=spot, volatility=vol)
    ck(f'greeks_{label}_available', x.get('available') is True and x.get('theoretical_greeks_available') is True)
    ck(f'greeks_{label}_numeric', all(x.get(k) is not None for k in (
        'theoretical_atm_delta_net','theoretical_atm_gamma','theoretical_atm_vega_per_iv_point',
        'theoretical_atm_theta_per_day','theoretical_gamma_peak_level','theoretical_delta_neutral_level')))
    ck(f'greeks_{label}_does_not_fake_oi', x.get('gamma_wall') is None and x.get('call_wall') is None and x.get('put_wall') is None and x.get('oi_dependent_levels_available') is False)
ck('frontend_local_vega', 'const vega = px * normalPdf(d1) * sqrtT / 100.0' in js)
ck('frontend_theoretical_peak_and_delta_neutral', 'theoretical_gamma_peak_level' in js and 'theoretical_delta_neutral_level' in js)
ck('frontend_labels_oi_truthfully', "Call Wall (por OI)" in js and "Pico Gamma teórico" in js)
ck('provider_fanout_still_btc_eth_only', "market !== 'multiasset' && (sym.startsWith('BTC-') || sym.startsWith('ETH-'))" in js)

# Multi semantics happen before Operational Intelligence/Moderador.
pre_idx=app.find("_pre_market_hook = getattr(self, '_market_pre_analysis_context'")
oi_idx=app.find('from operational_intelligence import prepare_operational_intelligence')
mod_idx=app.find('moderador = Moderador()', oi_idx)
ck('multi_pre_context_before_operational_intelligence', 0 <= pre_idx < oi_idx)
ck('multi_pre_context_before_nine_specialists', 0 <= pre_idx < mod_idx)
ck('multi_hook_asset_semantics', "'market_segment':'MULTIASSET'" in ma and "'multiasset_strategy_bank':strategy" in ma and "'multiasset_macro':macro" in ma)
ck('quant_synthesis_consumes_multi_context', 'multiasset_macro' in qs and 'preferred_patterns' in qs and 'MULTIASSET_IMMINENT_EVENT_WAIT' in qs)
ck('multi_strategy_context_is_bonus_not_direction', 'multi_context_bonus = 0.025' in qs and 'pattern in set(f.get("preferred_patterns")' in qs)

# Multi scheduler root fix: source candle + catch-up + cache survival.
ck('multi_source_candle_queue', 'def _multiasset_source_bucket' in app and 'def _multiasset_enqueue_router_rows' in app)
ck('multi_4h_catchup_without_close_window', "_multiasset_enqueue_router_rows(rows_4h,'4h',now,limit=1)" in app)
ck('multi_1h_cadence_without_82_gate', "_multiasset_enqueue_router_rows(rows_1h,'1h',now,limit=1)" in app and "router_score') or 0) >= _MULTI_FAST_LANE_MIN_SCORE" not in app[app.find('def _multiasset_background_tick'):app.find('def _get_review_trader')])
ck('multi_daily_heavy_limit_preserved', 'MULTIASSET_AUTO_DEEP_DAILY_MAX' in render and 'value: "12"' in render)
ck('multi_one_heavy_per_tick', 'if _multiasset_is_executable(result): _multiasset_compact_telegram(result)\n            return' in app)
ck('multi_local_snapshot_no_db', '_MULTI_LOCAL_SNAPSHOT_PATH' in app and '/tmp/smartradingreview_multi_cache_19_2_1.json' in app)
ck('multi_snapshot_bounded_2mb', '2 * 1024 * 1024' in app or '2*1024*1024' in app)
ck('multi_signal_routes_restore_snapshot', app.count('_multiasset_restore_local_snapshot_once()') >= 4)

# Structural recovery: native LIVE/Multi may repair under unchanged quality;
# Champions keep audited parity authority.
_ri=app.find('# Commit 19.2.1 — reaction recovery')
recovery=app[_ri:_ri+9000]
ck('native_recovery_quality_authority', "LIVE_NATIVE_QUALITY_CONTRACT" in recovery and '_gq>=68.0' in recovery and '_eq>=65.0' in recovery and '_sq>=60.0' in recovery and '_tq>=60.0' in recovery)
ck('champion_recovery_parity_preserved', 'validated_liquidity_route' in recovery and 'CHAMPION_PARITY' in recovery)
ck('reaction_guard_still_required', "if sl_reaction_guard.get('conflict'):\n                        _recovery_authorized=False" in recovery)
ck('recovered_scores_follow_prices', "quality_source']='REACTION_RECOVERY_COMMIT19_2_1'" in recovery and "sl_score=float(_reaction_recovery.get('sl_quality')" in recovery)
ck('derivative_recovery_floor_entry65', "_qualities[1] >= (65.0 if is_futures else 55.0)" in app)
ck('derivative_recovery_floor_geometry68', "_qualities[0] >= (68.0 if is_futures else 62.0)" in app)

# Existing quality / resource contract unchanged.
ck('publication_safety_75', "'minimum_publication_execution_safety': 75.0" in fy)
ck('publication_tp_55', "'minimum_publication_tp_quality': 55.0" in fy)
ck('publication_sl_60', "'minimum_publication_sl_avoidance_quality': 60.0" in fy)
ck('rr_default_reference_1_8_preserved', 'minimum_viable_rr, maximum_technical_rr = 1.8, 4.5' in app)
ck('one_worker_two_threads', '--workers 1 --threads 2' in proc and '--workers 1 --threads 2' in render)
ck('memory_hard_guard_300', 'MEMORY_HARD_LIMIT_MB' in render and 'value: "300"' in render)
ck('memory_job_guard_200', 'MEMORY_JOB_START_LIMIT_MB' in render and 'value: "200"' in render)
ck('options_budget_12mb_day', 'OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB' in render and 'value: "12"' in render)
ck('multi_deep_limit_2', 'MULTIASSET_DEEP_LIMIT' in render and 'value: "2"' in render)
ck('entrypoint_19_2_1', (('commit19_2_1_main_entrypoint:app' in proc and 'commit19_2_1_main_entrypoint:app' in render) or ('commit19_2_2_main_entrypoint:app' in proc and 'commit19_2_2_main_entrypoint:app' in render)))
ck('no_new_llm_for_greeks', 'Groq' not in mm and 'groq' not in js.lower())

passed=sum(checks.values()); total=len(checks)
print(f'\nSUMMARY {passed}/{total} PASS')
failed=[k for k,v in checks.items() if not v]
if failed:
    print('FAILED', failed)
    raise SystemExit(1)
