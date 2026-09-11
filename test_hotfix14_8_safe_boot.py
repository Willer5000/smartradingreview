import ast
import unittest
from pathlib import Path


class Hotfix148SafeBootTests(unittest.TestCase):
    def test_python_is_pinned_away_from_render_314_default(self):
        self.assertEqual(Path('.python-version').read_text().strip(), '3.11')
        render = Path('render.yaml').read_text()
        self.assertIn('value: 3.11.9', render)

    def test_heavy_scientific_modules_are_lazy(self):
        src = Path('app.py').read_text()
        tree = ast.parse(src)
        top_imports = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                top_imports.append(ast.unparse(node))
        self.assertNotIn('import numpy as np', top_imports)
        self.assertNotIn('import pandas as pd', top_imports)
        self.assertNotIn('import plotly.graph_objects as go', top_imports)
        self.assertIn("np = _LazyModule('numpy')", src)
        self.assertIn("pd = _LazyModule('pandas')", src)
        self.assertIn("go = _LazyModule('plotly.graph_objects')", src)

    def test_runtime_side_effects_are_deferred(self):
        tree = ast.parse(Path('app.py').read_text())
        direct_calls = []

        def scan_stmt(node):
            # Scan module-level control flow but never descend into a def/class.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                return
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    direct_calls.append(fn.id)
                elif isinstance(fn, ast.Attribute):
                    direct_calls.append(fn.attr)
            for child in ast.iter_child_nodes(node):
                scan_stmt(child)

        for stmt in tree.body:
            scan_stmt(stmt)

        for forbidden in (
            '_load_futures_cache_from_disk',
            '_load_entry_alerts_from_disk',
            '_load_guardian_telegram_events',
            '_load_spot_signals_cache_from_disk',
            '_start_futures_warmup',
            '_start_background_threads',
        ):
            self.assertNotIn(forbidden, direct_calls)
        self.assertIn('_schedule_deferred_runtime_bootstrap', direct_calls)

    def test_supabase_import_does_not_run_deep_health_check(self):
        src = Path('supabase_client.py').read_text()
        tail = src[src.index('# INSTANCIA GLOBAL (SINGLETON)'):]
        self.assertNotIn('health = supabase_db.health_check()', tail)

    def test_requirements_are_bounded_and_mplfinance_removed(self):
        req = Path('requirements.txt').read_text()
        self.assertIn('numpy==1.26.4', req)
        self.assertIn('pandas==2.2.3', req)
        self.assertIn('plotly==5.24.1', req)
        self.assertIn('supabase==2.18.1', req)
        self.assertNotIn('mplfinance', req.lower())


    def test_build_precompiles_large_app_source(self):
        render = Path('render.yaml').read_text()
        build = Path('build.sh').read_text()
        self.assertIn('buildCommand: bash build.sh', render)
        self.assertIn('compileall -q -j 1 .', build)
        self.assertIn('--no-cache-dir', build)

    def test_thread_stack_and_unbuffered_logs(self):
        src = Path('app.py').read_text()
        render = Path('render.yaml').read_text()
        self.assertIn('threading.stack_size(1024 * 1024)', src)
        self.assertIn('PYTHONUNBUFFERED', render)
        self.assertIn('RUNTIME_BOOTSTRAP_DELAY_SECONDS', render)


if __name__ == '__main__':
    unittest.main()
