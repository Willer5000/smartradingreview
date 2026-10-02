from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FAILS = []
PASSES = []

def ok(name, cond, detail=''):
    if cond:
        PASSES.append(name)
        print(f'PASS {name}')
    else:
        FAILS.append((name, detail))
        print(f'FAIL {name}: {detail}')

# 1) math + observed/theoretical authority
from market_maker_math import build_market_maker_context
from greeks_execution_context_19_1 import (
    observed_reaction_map, score_entry_confluence, score_sl_collision,
    score_tp_barrier, compact_execution_market_maker_context,
)

asof = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
expiry = asof + timedelta(hours=18)
rows = []
for strike in (94, 96, 98, 100, 102, 104, 106, 108, 110, 112):
    # Make call OI strongest above spot, put OI strongest below spot.
    call_oi = 800 if strike == 106 else 180 + max(0, strike-100)*12
    put_oi = 900 if strike == 96 else 190 + max(0, 100-strike)*12
    rows.append({'strike': strike, 'open_interest': call_oi, 'iv': 0.62, 'option_type': 'CALL', 'expiry': expiry, 'contract_multiplier': 1})
    rows.append({'strike': strike, 'open_interest': put_oi, 'iv': 0.66, 'option_type': 'PUT', 'expiry': expiry, 'contract_multiplier': 1})

observed = build_market_maker_context(spot=100, option_chain=rows, realized_or_implied_volatility=.6, as_of=asof)
theo = build_market_maker_context(spot=100, option_chain=[], realized_or_implied_volatility=.6, as_of=asof)

ok('01_observed_chain_live_execution_ranker_only', observed.get('observed_option_chain') is True and observed.get('execution_reaction_map_authority') == 'OBSERVED_CONFLUENCE_RANKER_ONLY')
ok('02_observed_never_direction_or_safety_bypass', observed.get('can_create_direction') is False and observed.get('can_bypass_safety') is False and observed.get('can_create_standalone_execution_level') is False)
ok('03_theoretical_zero_execution_authority', theo.get('observed_option_chain') is False and theo.get('can_refine_entry') is False and theo.get('can_refine_sl') is False and theo.get('can_refine_tp') is False)
ok('04_theoretical_has_atm_greeks_for_every_asset_ui', isinstance(theo.get('representative_atm_greeks'), dict) and 'call' in theo['representative_atm_greeks'] and 'put' in theo['representative_atm_greeks'])

rx = observed_reaction_map(observed, spot=100, atr=2)
ok('05_observed_reaction_map_eligible', rx.get('eligible') is True and len(rx.get('levels') or []) >= 2, str(rx))

put_wall = float(observed.get('put_wall') or 96)
call_wall = float(observed.get('call_wall') or 106)
ctx = {'market_maker_context': compact_execution_market_maker_context(observed)}
entry_score = score_entry_confluence(candidate={'price': put_wall, 'family':'smc_poi'}, context=ctx, current_price=100, atr=2)
base_score = score_entry_confluence(candidate={'price': put_wall, 'family':'baseline'}, context=ctx, current_price=100, atr=2)
sl_score = score_sl_collision(candidate={'price': put_wall, 'family':'structural_invalidation'}, context=ctx, entry=100, direction='long', atr=2)
first_barrier = min(float(r['price']) for r in rx['levels'] if float(r['price']) > 100)
tp_score = score_tp_barrier(candidate={'price': first_barrier-0.05, 'family':'structure_target'}, context=ctx, entry=100, direction='long', atr=2)

theo_ctx = {'market_maker_context': compact_execution_market_maker_context(theo)}
theo_entry = score_entry_confluence(candidate={'price':99,'family':'smc_poi'}, context=theo_ctx, current_price=100, atr=2)

ok('06_entry_existing_zone_can_receive_observed_options_confluence', entry_score.get('score') is not None and entry_score.get('score',0) >= 50, str(entry_score))
ok('07_options_cannot_create_baseline_entry', base_score.get('score') is None, str(base_score))
ok('08_sl_near_observed_reaction_is_penalized_only', sl_score.get('score') is not None and sl_score.get('score',100) < 60, str(sl_score))
ok('09_tp_before_observed_barrier_is_preferred', tp_score.get('score') is not None and tp_score.get('score',0) >= 75, str(tp_score))
ok('10_theoretical_surface_abstains_from_execution', theo_entry.get('score') is None, str(theo_entry))

compact = compact_execution_market_maker_context(observed)
ok('11_hot_execution_context_drops_curves', all(k not in compact for k in ('gex_curve','delta_curve','theta_curve')))

# 2) committee wiring remains bounded, no hard authority
committee = (ROOT/'execution_specialist_committees.py').read_text(encoding='utf-8')
ok('12_committee_has_low_weight_entry_greeks', '"options_reaction":0.40' in committee)
ok('13_committee_has_low_weight_sl_greeks', '"options_collision":0.45' in committee)
ok('14_committee_has_low_weight_tp_greeks', '"options_barrier":0.45' in committee)
ok('15_greeks_not_in_harmonic_core', 'scores.get("options_reaction")' not in committee.split('def _harmonic',1)[1].split('def _rank_candidates',1)[0])

# 3) frontend Spot/Futures/Multi support and no polling
html = (ROOT/'templates'/'index.html').read_text(encoding='utf-8')
front = (ROOT/'static'/'market_maker_frontend.js').read_text(encoding='utf-8')
workspace = (ROOT/'static'/'chart_workspace.js').read_text(encoding='utf-8')
card_idx = html.find('data-indicator="market-maker-options"')
near = html[max(0,card_idx-250):card_idx]
ok('16_spot_frontend_contains_greeks_card', card_idx >= 0 and '{% if is_futures' not in near and 'is_multiasset' not in near)
ok('17_greeks_script_loaded_on_all_pages', "filename='market_maker_frontend.js'" in html and html.find("filename='market_maker_frontend.js'") > html.find('{% endif %}', html.find("filename='futures.js'")))
ok('18_workspace_keeps_greeks_visible_all_pages', "if (id === 'market-maker-options') return true;" in workspace)
ok('19_frontend_supports_spot_futures_multi', "return 'multiasset'" in front and "return 'futures'" in front and "return 'spot'" in front)
ok('20_no_options_polling', 'setInterval(' not in front)
ok('21_non_direct_assets_use_local_theoretical', 'if (!supportsObservedServer(symbol, market))' in front and 'buildLocalTheoreticalContext' in front)
ok('22_direct_provider_endpoint_is_generic', '/api/market-maker-context?market=' in front)

# 4) provider + Render resource guard
opt = (ROOT/'options_market_context.py').read_text(encoding='utf-8')
render = (ROOT/'render.yaml').read_text(encoding='utf-8')
app = (ROOT/'app.py').read_text(encoding='utf-8')
ok('23_provider_direct_underlyings_bounded_btc_eth', 'if sym.startswith("BTC-")' in opt and 'if sym.startswith("ETH-")' in opt and 'return None' in opt)
ok('24_provider_daily_budget_12mb', 'OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB", "12"' in opt and 'DAILY_PROVIDER_BUDGET_BYTES' in opt)
ok('25_provider_response_stream_byte_cap', 'stream=True' in opt and 'MAX_RESPONSE_BYTES' in opt and 'iter_content(chunk_size=65536)' in opt)
ok('26_provider_cache_ttl_2h_default', 'OPTIONS_MM_CACHE_TTL_SECONDS", "7200"' in opt)
ok('27_render_single_worker_two_threads', '--workers 1 --threads 2' in render)
ok('28_render_memory_hard_cap_300mb_below_512', 'MEMORY_HARD_LIMIT_MB' in render and 'value: "300"' in render)
ok('29_render_greeks_provider_budget_present', 'OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB' in render and 'value: "12"' in render)
ok('30_main_runtime_compacts_greeks_context', 'compact_execution_market_maker_context' in app)
ok('31_generic_endpoint_no_full_analysis', "@app.route('/api/market-maker-context'" in app and 'NO full analysis is launched' in app)
ok('32_spot_execution_may_use_direct_observed_chain', "execution_market_type in {'futures', 'spot'}" in app)

# 5) Commit 19/19.1 safety invariants still stated
runtime = (ROOT/'commit19_1_runtime.py').read_text(encoding='utf-8')
ok('33_no_new_llm_or_background_threads', '"adds_llm_calls":False' in runtime and '"adds_background_threads":False' in runtime)
ok('34_safety_rr_leverage_unchanged', '"changes_safety_thresholds":False' in runtime and '"changes_rr_floor":False' in runtime and '"changes_leverage_v6":False' in runtime)

summary = {'passes': len(PASSES), 'fails': len(FAILS), 'failed': FAILS}
(ROOT/'QA_COMMIT19_1_GREEKS_FINAL_RESULT.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
if FAILS:
    raise SystemExit(1)
