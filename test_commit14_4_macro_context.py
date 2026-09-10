import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import macro_context


class MacroContextClassificationTests(unittest.TestCase):
    def test_high_impact_macro_is_context_not_trade_signal(self):
        result = macro_context.classify_macro_headline(
            "La Reserva Federal enfrenta un dato de inflación CPI inesperado",
            "prueba"
        )
        self.assertIn(result["risk_level"], {"HIGH", "CRITICAL"})
        self.assertEqual(result["opportunity_level"], "WATCH")
        self.assertEqual(result["method"], "RULE_BASED_CONTEXT_ONLY")
        self.assertNotIn("LONG", result.values())
        self.assertNotIn("SHORT", result.values())

    def test_bls_calendar_keeps_exact_time_and_converts_timezone(self):
        ics = """BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=America/New_York:20260911T083000\nSUMMARY:Consumer Price Index\nEND:VEVENT\nEND:VCALENDAR\n"""
        response = Mock()
        response.text = ics
        response.raise_for_status = Mock()
        now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
        with patch.object(macro_context.requests, "get", return_value=response):
            events = macro_context._fetch_bls_calendar(now=now)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["time_precision"], "EXACT")
        self.assertEqual(events[0]["source"], "BLS")
        self.assertTrue(events[0]["scheduled_at"].endswith("Z"))
        # 08:30 New York = 12:30 UTC = 09:30 Argentina in September.
        dt = macro_context._safe_dt(events[0]["scheduled_at"])
        self.assertEqual(dt.astimezone(macro_context.DISPLAY_TZ).strftime("%H:%M"), "09:30")

    def test_fomc_date_only_does_not_invent_intraday_freeze(self):
        html = """
        <html><body>
        <h2>2026 FOMC Meetings</h2>
        <div>September 15-16</div>
        <div>October 27-28</div>
        <h2>2027 FOMC Meetings</h2>
        </body></html>
        """
        response = Mock()
        response.text = html
        response.raise_for_status = Mock()
        now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
        with patch.object(macro_context.requests, "get", return_value=response):
            events = macro_context._fetch_fomc_calendar(now=now)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["time_precision"], "DATE_ONLY")
        self.assertEqual(events[0]["futures_posture"], "CAUTION")
        # A date-only event must never emit a fake 3h/30m alert.
        e = dict(events[0])
        e["scheduled_at"] = macro_context._iso_utc(now.replace(hour=15) + __import__('datetime').timedelta(minutes=30))
        alerts = macro_context._build_alert_candidates([e], [], now)
        self.assertFalse(any(a["key"].endswith(":30M") for a in alerts))


class MacroContextIntegrationContractTests(unittest.TestCase):
    def test_backend_is_fail_open_and_tradermacro_futures_is_context_only(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("@app.route('/api/macro/context'", app_source)
        self.assertIn("macro_context_alert_loop", app_source)
        self.assertIn("'macro_context': macro_context_snapshot", app_source)
        self.assertIn("MACRO_EVENT_RISK", app_source)
        self.assertIn("MACRO_NEWS_RISK", app_source)
        self.assertIn("return accion, 0, estrategias, razones", app_source)
        self.assertIn("noticias no pueden bloquear trading", app_source)

    def test_frontend_has_lightweight_ticker_and_action_panel_macro_context(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "script.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        self.assertIn('id="macro-news-ticker"', html)
        self.assertIn('id="macro-risk-badge"', html)
        self.assertIn("/api/macro/context", js)
        self.assertIn("300000", js)  # UI polls at most every 5 min.
        self.assertIn("NO_NEW_TRADES", js)
        self.assertIn(".macro-news-ticker", css)
        self.assertIn("max-height: 30px", css)

    def test_pdf_attribution_knows_new_macro_context_strategies(self):
        source = (ROOT / "pdf_learning_report.py").read_text(encoding="utf-8")
        self.assertIn("'MACRO_EVENT_RISK': 'TraderMacro'", source)
        self.assertIn("'MACRO_NEWS_RISK': 'TraderMacro'", source)


if __name__ == "__main__":
    unittest.main()
