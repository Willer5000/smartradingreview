from pathlib import Path
from execution_specialist_committees import coordinate_execution_committees

checks=[]
def ck(label, cond):
    checks.append((label,bool(cond))); print(('OK   ' if cond else 'FAIL ')+label)

# The same specialist committees must recover geometry for the two affected lanes.
for direction, market, symbol, tf, px, atr in [
    ('long','multiasset','CL-USDT','4h',94.32,2.0),
    ('short','futures','BTC-USDT','1h',65000.0,1200.0),
]:
    c=coordinate_execution_committees(
        baseline_entry=0, baseline_sl=0, baseline_tp=0,
        direction=direction, current_price=px, atr=atr,
        structure={}, trend={'direction':direction}, momentum={'direction':direction},
        volatility={}, setup_family='MOMENTUM_CONTINUATION', liquidation=None,
        market_type=market, symbol=symbol, timeframe=tf,
        execution_context={'activity_score':60,'shock_score':15,'timeframe':tf},
        rr_floor=1.8, rr_ceiling=4.5, preferred_rr_min=2.0, preferred_rr_max=3.2,
        leverage_hint=10,
    )
    geo = (c.get('stop_loss',0) < c.get('entry',0) < c.get('take_profit',0)) if direction=='long' else (c.get('take_profit',0) < c.get('entry',0) < c.get('stop_loss',0))
    ck(f'{market} {symbol} committee recovers zero-baseline geometry', c.get('success') is True and geo)
    ck(f'{market} {symbol} committee RR is usable', 1.8 <= float(c.get('risk_reward') or 0) <= 4.5)

app=Path('app.py').read_text()
js=Path('static/futures.js').read_text()

ck('runtime recovery helper exists', 'def _recover_confirmed_execution_levels' in app)
ck('geometry validator exists', 'def _execution_geometry_valid' in app)
ck('calculate_entry_levels exception recovers instead of returning zero defaults', "Recuperando geometría obligatoria tras excepción de runtime" in app)
ck('caller validates geometry before publication', 'POST_CALC_INVALID_GEOMETRY' in app)
ck('legacy setup guard cannot promote invalid geometry', 'LEGACY_SETUP_GUARD_INVALID_GEOMETRY' in app)
ck('anti-FOMO cannot promote invalid geometry', 'ANTI_FOMO_INVALID_GEOMETRY' in app)
ck('invalid legacy Multi-Asset rows are not called confirmed executable', 'LEGACY_INVALID_GEOMETRY' in app)
ck('invalid legacy Futures rows are classified as analysis error', "classification = 'ANALYSIS_ERROR'" in app and 'Registro legacy con geometría incompleta' in app)
ck('expired previous signal UI uses clock state', 'expiredByClock' in js and 'VIGENCIA FINALIZADA' in js)
ck('Multi-Asset official signals can be saved', "'manual_save_allowed': bool(executable)" in app)
ck('Multi-Asset save contexts are server-validated', 'MULTIASSET_PREVIOUS_CONFIRMED' in app and 'MULTIASSET_ACTIVE_CONFIRMED' in app)
ck('frontend preserves Multi-Asset save context', 'MULTIASSET_PREVIOUS_CONFIRMED' in js and 'MULTIASSET_ACTIVE_CONFIRMED' in js)

# Resource policy: new helper must remain local-only.
start=app.index('    def _recover_confirmed_execution_levels')
end=app.index('    def calculate_entry_levels', start)
helper=app[start:end].lower()
for token in ('requests.','httpx','supabase','groq','openai'):
    ck(f'17.4.1 runtime recovery adds no {token} dependency', token not in helper)

bad=[label for label,ok in checks if not ok]
print(f'PASS {len(checks)-len(bad)}/{len(checks)}')
if bad:
    print('FAILED',bad); raise SystemExit(1)
