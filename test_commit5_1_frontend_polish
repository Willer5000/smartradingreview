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


class Commit51FrontendPolish(unittest.TestCase):
    def test_serious_brand_and_signal_header_policy(self):
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        visible = visible_html_text(ROOT / 'templates/index.html')
        self.assertNotIn('🚀 FUTUROS', visible)
        self.assertNotIn('fa-robot', html)
        self.assertEqual(html.count('signal-header-active'), 1)
        self.assertEqual(html.count('signal-header-previous'), 1)
        self.assertIn('Alertas de scalping Futures', visible)

    def test_full_width_workspace_and_black_theme(self):
        css = (ROOT / 'static/style.css').read_text(encoding='utf-8')
        self.assertIn('--app-bg: #050505;', css)
        self.assertIn('grid-template-columns: minmax(0, 1fr) !important;', css)
        self.assertIn('.signal-header-active', css)
        self.assertIn('.signal-header-previous', css)

    def test_mobile_recommendation_contract(self):
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        js = (ROOT / 'static/script.js').read_text(encoding='utf-8')
        for element_id in (
            'mobile-rec-action', 'mobile-rec-entry', 'mobile-rec-sl',
            'mobile-rec-tp', 'mobile-rec-rr', 'mobile-rec-leverage'
        ):
            self.assertIn(element_id, html)
            self.assertIn(element_id, js)
        self.assertIn('applyMobileRecommendationDefault', html)

    def test_rsi_vwap_and_pattern_contract(self):
        js = (ROOT / 'static/script.js').read_text(encoding='utf-8')
        workspace = (ROOT / 'static/chart_workspace.js').read_text(encoding='utf-8')
        rsi = js[js.index('function updateRSIChart(data) {'):js.index('// ============ Estocástico ============')]
        self.assertIn("xaxis: systemType === 'futures' ? 'x' : 'x2'", rsi)
        self.assertIn("xaxis: 'x2', yaxis: 'y2'", rsi)
        vwap = js[js.index('function updateVWAPChart(data) {'):js.index('// ============ UPDATE ALL CHARTS ============')]
        self.assertIn("type: 'candlestick'", vwap)
        self.assertIn("rangeslider: {visible: false}", vwap)
        self.assertIn("new Set(['trading-zones', 'pattern4'])", workspace)
        self.assertIn("'pattern4': { label: 'Patrón reciente de velas', category: 'Estructura', permanent: true }", workspace)

    def test_report_can_be_sent_to_telegram(self):
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn("delivery == 'telegram'", app)
        self.assertIn('/sendDocument', app)
        self.assertIn("session.get('authenticated_user')", app)
        self.assertIn("downloadAnalysisReport('telegram')", html)
        self.assertIn('Enviar a Telegram', html)


if __name__ == '__main__':
    unittest.main()
