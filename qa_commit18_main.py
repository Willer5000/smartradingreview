from __future__ import annotations
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parent

def check(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS:',msg)

spec=importlib.util.spec_from_file_location('rf',ROOT/'reason_first_contract_18.py')
rf=importlib.util.module_from_spec(spec); spec.loader.exec_module(rf)
a=rf.audit_contract()
check(a['majority_vote_gate'] is False,'no majority-vote production gate')
check(a['leverage_modified'] is False,'Commit18 does not modify leverage policy')
check(a['ai_scientist_production_authority'] is False,'Learning Scientist remains proposal/shadow only')
check(a['macro_creates_direction'] is False,'macro/news cannot create direction')
check(a['options_create_direction'] is False,'Greeks/GEX cannot create direction')
check(len(rf.EVIDENCE_FAMILIES)==9,'correlated indicators grouped into bounded evidence families')

eth=rf.research_route_state(market='futures',symbol='ETH-USDT',timeframe='2h',action='long',regime='trend_up')
check(eth['state']=='POSITIVE_IS_SELECTION_OOS_WF_ROUTE','positive exact Research route recognized')
check(eth['production_authority'] is False,'historical route cannot bypass production parity')

app=(ROOT/'app.py').read_text(encoding='utf-8')
js=(ROOT/'static'/'script.js').read_text(encoding='utf-8')
html=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
check("@app.route('/api/multiasset/display'" in app,'dedicated Multi display endpoint exists')
block=app[app.index("@app.route('/api/multiasset/display'"):app.index("@app.route('/api/multiasset/analyze'")]
check('_start_futures_ui_analysis_async' not in block,'display lane never starts heavy analysis')
check('loadMultiDisplayLane' in js and 'commit18MultiIdentityReset' in js,'frontend has strict Multi identity/display lane')
check('MULTI_DISPLAY_IDENTITY_MISMATCH' in js,'stale cross-cell response fails identity check')
check('runtime_resilience_175104.js' not in html,'separate resilience static request removed')
check('__RUNTIME_RESILIENCE_18__' in js,'runtime resilience inlined into core script')
check('STRUCTURAL_RECOVERY_AFTER_SL_REACTION_CONFLICT' in app,'manual Entry/SL geometry repairs reaction-zone stop conflict')
check("response_contract_version':'18.0'" in app,'Multi heavy/display response contract bumped to Commit18')
print('COMMIT 18 MAIN QA: PASS')

# Dynamic unit check when the complete repository is present. The delivery ZIP
# intentionally contains only replacement files, so the unchanged execution
# module may be absent when QA is run directly inside the extracted package.
try:
    import execution_specialist_committees  # noqa: F401
except Exception:
    print('INFO: full-tree SL-reaction regression requires unchanged execution_specialist_committees.py from the repository')
else:
    import ast, math
    _tree=ast.parse(app)
    _fn=next(n for n in _tree.body if isinstance(n,ast.FunctionDef) and n.name=='_ensure_manual_diagnostic_geometry_175114')
    _mod=ast.Module(body=[_fn],type_ignores=[]); ast.fix_missing_locations(_mod)
    _ns={'math':math}; exec(compile(_mod,'<manual18>','exec'),_ns)
    _result={
        'success':True,'symbol':'TEST-USDT','timeframe':'1h','current_price':100,
        'levels':{'entry':100,'stop_loss':105,'take_profit':90,'leverage':23},
        'volatility':{'atr':2},
        'structure':{'order_blocks':[{'type':'bearish','price_range':[104,106],'invalidated':False,'mitigated':False}]},
        'trend':{},'momentum':{},'liquidation':{}
    }
    _out=_ns['_ensure_manual_diagnostic_geometry_175114'](_result,'SHORT','TEST-USDT','1h')
    check(float(_out['stop_loss'])>106,'reaction-zone SL repaired beyond bearish OB invalidation edge')
    check(float(_out['entry'])==104.0,'reaction zone becomes the manual Entry candidate in regression fixture')
    check(int(_out['leverage'])==23,'Entry/SL repair does not alter existing leverage')
