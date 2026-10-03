from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent

def test_entrypoint_is_20_2_boot_chain():
    s = (ROOT / 'commit20_2_main_entrypoint.py').read_text(encoding='utf-8')
    assert 'install_pre_app' in s
    assert 'install_post_app' in s
    assert 'cpqe_19_2_4' in s
    assert 'premium_path_expansion_20' in s


def test_no_21x_start_command():
    for name in ('Procfile', 'render.yaml'):
        s = (ROOT / name).read_text(encoding='utf-8')
        assert 'commit20_2_main_entrypoint:app' in s
        assert 'commit21_1_main_entrypoint:app' not in s
        assert 'commit21_2_main_entrypoint:app' not in s


def test_script_returns_to_20_2_navigation():
    s = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
    assert 'loadLightVisualsForSignal' not in s
    assert 'window.runCompleteAnalysis();' in s


def test_futures_governor_and_previous_fix():
    s = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
    assert 'COMMIT 20.2.1 — REQUEST GOVERNOR / SINGLE-FLIGHT' in s
    assert '__COMMIT2021_REQUEST_GOVERNOR__' in s
    assert 'single-flight' in s
    assert 'se reutiliza el estado actual' in s
    assert 'Evitar bloqueo permanente.' not in s
    assert 'se reutiliza el estado actual' in s


def test_template_cache_bust():
    s = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert '20261003-COMMIT20-2-STABILITY-1' in s
    assert 'COMMIT21-1-FIX' not in s


def test_html_no_store_present():
    s = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert "Cache-Control'] = 'no-store, no-cache, max-age=0, must-revalidate'" in s


def test_python_compile():
    for name in ('app.py', 'premium_path_expansion_20.py', 'commit20_2_main_entrypoint.py'):
        subprocess.run(['python', '-m', 'py_compile', str(ROOT / name)], check=True)


def test_js_syntax():
    for name in ('static/script.js', 'static/futures.js'):
        subprocess.run(['node', '--check', str(ROOT / name)], check=True)
