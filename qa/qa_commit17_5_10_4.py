from pathlib import Path
import ast, importlib.util, types

ROOT=Path(__file__).resolve().parents[1]
app=(ROOT/'app.py').read_text(encoding='utf-8')
pipe=(ROOT/'pipeline_integrity_175102.py').read_text(encoding='utf-8')
tpl=(ROOT/'templates/index.html').read_text(encoding='utf-8')
js=(ROOT/'static/runtime_resilience_175104.js').read_text(encoding='utf-8')
abi=(ROOT/'execution_abi_175104.py').read_text(encoding='utf-8')

checks=[]
def check(name, cond):
    checks.append((name,bool(cond)))
    print(('PASS' if cond else 'FAIL'), name)

ast.parse(app); ast.parse(pipe); ast.parse(abi)
check('stable market identity helper', '_stable_analysis_system_type_175104' in app)
check('app no longer uses shared skip flag for market identity/persistence', '_skip_supabase_register' not in app)
check('class ABI installer wired to Futures', 'install_futures_execution_abi_175104(futures_module)' in app)
check('MultiAsset installs inherited ABI before use', 'MultiAssetAnalysis inherits FuturesAnalysis' in app and 'install_futures_execution_abi_175104(futures_module)' in app[app.index('def _get_multiasset_system'):app.index('def _multiasset_cache_result')])
check('uniform execution_observations call', 'execution_observations=capas' in app and '_execution_bridge_key_175103' not in app)
check('pipeline generation 17.5.10.4', 'PIPELINE_GENERATION = "17.5.10.4"' in pipe)
check('Futures runtime failure becomes scheduler error', "raise RuntimeError(\n                    'EXECUTION_RUNTIME_FAILED:" in app)
check('MultiAsset runtime failure is not cached as success', "'runtime_failed':True" in app and app.index("'runtime_failed':True") < app.index("_multiasset_cache_result(symbol,timeframe,result)", app.index("'runtime_failed':True")))
check('frontend status noise removed', 'Estado del análisis' not in js and 'pipeline_health' not in js)
check('frontend resilience preserved', 'timeoutMs = 25000' in js and 'setInterval' not in js and 'loadFuturesRiskProfile' in js)
check('template loads 17.5.10.4 JS', 'runtime_resilience_175104.js' in tpl and 'runtime_resilience_175103.js' not in tpl)
check('no signal-count quota in new ABI/UI', all(tok not in (abi+js).lower() for tok in ('max_signals','min_signals','signal_quota','quota_signals')))

# Behavioral ABI simulation with a legacy FuturesAnalysis signature.
spec=importlib.util.spec_from_file_location('abi175104', ROOT/'execution_abi_175104.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
class FakeFutures:
    def calculate_entry_levels(self, decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation=None):
        obs=structure.get('_execution_observations_175103')
        return {'seen': bool(obs and obs.get('marker') == 175104)}
fake=types.SimpleNamespace(FuturesAnalysis=FakeFutures)
state=mod.install_futures_execution_abi_175104(fake)
s={}
out=FakeFutures().calculate_entry_levels('LONG',{}, {}, {}, s,'BTC-USDT','1h',execution_observations={'marker':175104})
check('legacy Futures ABI accepts observations', out.get('seen') is True)
check('ABI bridge leaves no mutable residue', '_execution_observations_175103' not in s)
check('ABI installer reports installed', state.get('installed') is True)

failed=[n for n,ok in checks if not ok]
print(f"{len(checks)-len(failed)}/{len(checks)} PASS")
if failed: raise SystemExit('Failed: '+', '.join(failed))
