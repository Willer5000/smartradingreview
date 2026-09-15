import pathlib, unittest

ROOT=pathlib.Path(__file__).resolve().parent

class RC5FinalStabilityTests(unittest.TestCase):
    def test_research_generation_and_contract(self):
        txt=(ROOT/'research_evidence_fusion.py').read_text()
        self.assertIn('RFV1_12_RC5_ITERATIVE_EDGE_46CELL',txt)
        self.assertIn('_COVERAGE_TARGET = 46',txt)

    def test_analytics_is_snapshot_first_background(self):
        txt=(ROOT/'app.py').read_text()
        self.assertIn('_schedule_analytics_quality_refresh',txt)
        block=txt[txt.index("@app.route('/api/analytics/quality-v2')"):txt.index("@app.route('/api/analytics/strategies')")]
        self.assertNotIn('svc.get_quality_v2_summary(**filters)',block)
        self.assertIn("'deferred':True",block)

    def test_no_retired_tf_in_autopilot(self):
        txt=(ROOT/'adaptive_autopilot.py').read_text()
        part=txt[txt.index('AUTO_RESEARCH_UNIVERSE'):txt.index('_cache_lock')]
        self.assertNotIn('"5m"',part); self.assertNotIn('"15m"',part)
        self.assertIn('"30m"',part); self.assertIn('"12h"',part); self.assertIn('"1D"',part)

    def test_pdf_human_labels(self):
        txt=(ROOT/'pdf_learning_report.py').read_text()
        self.assertNotIn('Spot fuera de la cohorte operativa RC4.1:',txt)
        self.assertNotIn('Validación Commit 36',txt)
        self.assertIn('Spot fuera de la cohorte operativa actual:',txt)

    def test_macro_separates_current_from_next(self):
        txt=(ROOT/'macro_context.py').read_text()
        self.assertIn('immediate_events=',txt)
        self.assertIn('next_high_event',txt)
        self.assertIn('CURRENT risk is not the same as NEXT',txt)

if __name__=='__main__': unittest.main()
