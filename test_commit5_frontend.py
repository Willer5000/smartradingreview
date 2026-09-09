import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def visible_html_text(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    text = re.sub(r'<script\b.*?</script>', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<style\b.*?</style>', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text)


class Commit5FrontendContract(unittest.TestCase):
    def test_no_internal_commit_codes_in_visible_templates(self):
        forbidden = re.compile(
            r'\b(?:36[A-Z][A-Z0-9._-]*|Q[1-9][A-Z0-9._-]*|SHADOW_ONLY|HARD_SAFETY|CAUTIOUS_SHADOW|PRE_GATE_REJECTION)\b',
            re.I,
        )
        for rel in ('templates/index.html', 'templates/analytics.html'):
            visible = visible_html_text(ROOT / rel)
            self.assertIsNone(forbidden.search(visible), rel)

    def test_workspace_and_theme_are_loaded(self):
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn("trading_theme.js", html)
        self.assertIn("chart_workspace.js", html)
        workspace = (ROOT / 'static/chart_workspace.js').read_text(encoding='utf-8')
        self.assertIn("const MAX_AUTO = 4", workspace)
        self.assertIn("'trading-zones'", workspace)
        self.assertIn("+ Agregar gráfico", workspace)
        self.assertIn("Relacionado con la señal", workspace)

    def test_key_chart_contracts(self):
        js = (ROOT / 'static/script.js').read_text(encoding='utf-8')
        fib_start = js.index('function updateFibonacciChart(data) {')
        fib_end = js.index('// ============ COMMIT 3: RSI ADAPTATIVO', fib_start)
        fib = js[fib_start:fib_end]
        self.assertNotIn('trendGeometry', fib)

        zones_start = js.index('function updateTradingZones(data) {')
        zones_end = js.index('function getZoneAnnotations', zones_start)
        zones = js[zones_start:zones_end]
        self.assertIn('trendGeometry', zones)
        self.assertIn('Soporte dinámico', zones)
        self.assertIn('Resistencia dinámica', zones)

        rsi_start = js.index('function updateRSIChart(data) {')
        rsi_end = js.index('// ============ Estocástico ============', rsi_start)
        rsi = js[rsi_start:rsi_end]
        self.assertIn('Sobrecompra', rsi)
        self.assertIn('Sobreventa', rsi)
        self.assertIn('price_points', rsi)
        self.assertIn('oscillator_points', rsi)

        self.assertIn('function updateVWAPChart(data) {', js)
        self.assertIn("'vwap': updateVWAPChart", js)
        self.assertIn('workspace.shouldRender', js)

    def test_backend_visual_metadata_is_presentation_only(self):
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn("'visual_evidence': self._make_serializable(visual_evidence)", app)
        self.assertIn("'price_points': _pair_points", app)
        self.assertIn("'oscillator_points': _pair_points", app)
        self.assertIn('Metadatos exclusivos de presentación', app)

    def test_responsive_design_contract(self):
        css = (ROOT / 'static/style.css').read_text(encoding='utf-8')
        for breakpoint in ('1199.98px', '991.98px', '767.98px', '420px'):
            self.assertIn(breakpoint, css)
        self.assertIn('#indicators-container', css)
        self.assertIn('--app-text:', css)
        self.assertIn('--app-bg:', css)


if __name__ == '__main__':
    unittest.main()
