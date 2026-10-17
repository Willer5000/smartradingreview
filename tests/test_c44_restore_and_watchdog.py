"""C44 non-invasive resource governor and signal restoration contract."""
from pathlib import Path
import ast
import hashlib
import zipfile

HERE = Path(__file__).resolve().parents[1]
BASE_ZIP_NAME = 'smartradingreview-main ULTIMO FUNCIONAL CON RESULTADOS POSITIVOS PERO CON PROBLEMAS DE RAM.zip'


def _watchdog_fn():
    src = ast.parse((HERE / 'app.py').read_text(encoding='utf-8'))
    fn = next(n for n in src.body if isinstance(n, ast.FunctionDef) and n.name == '_c44_watchdog_cgroup_pressure')
    mod = ast.Module(body=[fn], type_ignores=[])
    scope = {}
    exec(compile(ast.fix_missing_locations(mod), '<c44-watchdog>', 'exec'), scope)
    return scope['_c44_watchdog_cgroup_pressure']


def test_watchdog_does_not_starve_on_reclaimable_file_cache():
    decide = _watchdog_fn()
    # 402/512 MB in logs + 100MB cold page cache should not trigger global 90s blackout.
    assert decide(402.3, 512, 100) is False
    # 428MB with 120MB cold page cache: heavy work still needs its own reserve.
    assert decide(428, 512, 120) is False
    # Truly exhausted physical headroom or no reclaimable cache: defer.
    assert decide(449, 512, 500) is True
    assert decide(402.3, 512, 0) is True
    assert decide(390, 512, 0) is True
    assert decide(340, 512, 0) is False
    assert decide(None, None, 0) is False


def test_original_trading_functions_unchanged():
    path = HERE.parents[2] / BASE_ZIP_NAME
    if not path.exists():
        return  # A portable deployed repository does not need the user's original zip.
    original = zipfile.ZipFile(path).read('smartradingreview-main/app.py').decode()
    before = ast.parse(original)
    after = ast.parse((HERE/'app.py').read_text())
    old_defs = {n.name: ast.dump(n, include_attributes=False) for n in before.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    new_defs = {n.name: ast.dump(n, include_attributes=False) for n in after.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    changed = {k for k in old_defs if old_defs[k] != new_defs.get(k)}
    assert changed == {'resource_watchdog_loop', 'api_commit35_resource_health'}, changed
    assert set(new_defs)-set(old_defs) == {'_c44_watchdog_cgroup_pressure'}
    assert 'analysis_cache_compact_c43' not in (HERE/'app.py').read_text()


def test_original_source_files_preserved():
    path = HERE.parents[2] / BASE_ZIP_NAME
    if not path.exists():
        return
    old = zipfile.ZipFile(path)
    exceptions = {'app.py', 'templates/index.html','static/script.js','static/futures.js'}
    for file in old.namelist():
        prefix = 'smartradingreview-main/'
        if not file.startswith(prefix) or file.endswith('/'):
            continue
        rel = file[len(prefix):]
        if rel in exceptions or rel.startswith('tests/'):
            continue
        newer = HERE / rel
        assert newer.is_file(), rel
        assert hashlib.sha256(old.read(file)).digest() == hashlib.sha256(newer.read_bytes()).digest(), rel
