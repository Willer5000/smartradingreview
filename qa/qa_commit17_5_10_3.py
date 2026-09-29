from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT/'app.py').read_text(encoding='utf-8')
pipe = (ROOT/'pipeline_integrity_175102.py').read_text(encoding='utf-8')
tpl = (ROOT/'templates/index.html').read_text(encoding='utf-8')
js = (ROOT/'static/runtime_resilience_175103.js').read_text(encoding='utf-8')

checks=[]
def check(name, cond):
    checks.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), name)

ast.parse(app)
ast.parse(pipe)
check('futures ABI bridge key installed', "_execution_observations_175103" in app)
# The dangerous unconditional call shape must no longer exist in the levels block.
segment=app[app.index('# ============ NIVELES ============'):app.index('# COMMIT 17.5.10.2 — EXECUTION COMPLETENESS CONTRACT')]
check('Futures path does not pass legacy-incompatible kwarg', "if analysis_system_type == 'futures'" in segment and "symbol, timeframe, liquidation=liquidation_data," in segment)
check('Spot still passes execution observations', 'execution_observations=capas' in segment)
check('runtime failure is explicit', 'EXECUTION_RUNTIME_FAILED' in app and 'execution_runtime_failed' in app)
check('pipeline generation 17.5.10.3', 'PIPELINE_GENERATION = "17.5.10.3"' in pipe)
check('public pipeline health present', '_public_pipeline_health_175103' in app and "'pipeline_health'" in app)
check('frontend helper loaded', 'runtime_resilience_175103.js' in tpl)
check('frontend has no auto retry', 'setInterval' not in js and 'fetch(url' in js and 'for (' not in js[js.find('window._futFetchBounded'):js.find('// Avoid duplicated risk-profile')])
check('frontend timeout bounded at 25s', 'timeoutMs = 25000' in js)
check('BLS 403 fail-open wrapper exists', 'bls_http_403_seen' in (ROOT/'runtime_resilience_175103.py').read_text())

failed=[n for n,ok in checks if not ok]
print(f"{len(checks)-len(failed)}/{len(checks)} PASS")
if failed:
    raise SystemExit('Failed: '+', '.join(failed))
