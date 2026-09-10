import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class CompactUiTests(unittest.TestCase):
    def test_action_now_replaces_visible_system_status_card(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="action-now-card"', html)
        self.assertIn('Qué debo hacer ahora', html)
        self.assertNotIn('Estado del Sistema\n', html)
        self.assertIn('id="api-status"', html)  # compatibility ID retained

    def test_analysis_controls_are_compact(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('analysis-actions-compact', html)
        self.assertIn('>Analizar', html)
        self.assertIn('>Aprendizaje', html)

    def test_correlation_details_are_collapsible(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('correlation-chip-row', html)
        self.assertIn('Ver explicación', html)
        self.assertIn('id="correlation-explanation"', html)

    def test_footer_is_compact_and_links_remain(self):
        html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('app-footer-compact', html)
        self.assertIn('github.com/Willer5000', html)
        self.assertIn('linkedin.com/in/willer-gianni-torrico-arispe', html)


if __name__ == '__main__':
    unittest.main()
