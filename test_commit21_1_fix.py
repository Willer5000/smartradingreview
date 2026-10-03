from __future__ import annotations

import pathlib
import py_compile
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
passed = 0

def check(name, condition):
    global passed
    if not condition:
        raise AssertionError(name)
    passed += 1
    print(f"PASS: {name}")

for fn in ("app.py", "premium_path_expansion_21.py", "quality_9q_engine_21.py"):
    py_compile.compile(str(ROOT / fn), doraise=True)
check("python compile", True)

for js in ("static/script.js", "static/futures.js"):
    cp = subprocess.run(["node", "--check", str(ROOT / js)], capture_output=True, text=True)
    check(f"node check {js}", cp.returncode == 0)

app = (ROOT / "app.py").read_text()
ppe = (ROOT / "premium_path_expansion_21.py").read_text()
script = (ROOT / "static/script.js").read_text()
template = (ROOT / "templates/index.html").read_text()

check("transport sanitizer exists", "def _json_safe_transport(value):" in app)
check("cache read sanitized", "cached_ui = _json_safe_transport(_get_futures_ui_cached(symbol, timeframe))" in app)
check("runtime partial sanitized", "partial_data = _json_safe_transport(_get_futures_runtime_cached(symbol, timeframe))" in app)
check("cache store sanitized", "safe_payload = _json_safe_transport(payload)" in app)
check("numpy bool explicitly handled", "_np.bool_" in app)
check("Q10 precheck exists", "def _q10_hard_violation_codes" in ppe)
check("Q10 precheck precedes Q9 selection", "q10_preeligible" in ppe and "ranking_pool = q10_viable or candidates" in ppe)
check("final Q10 remains downstream", "q10_safety_contract" in ppe)
check("no lowered Safety", "Q10_MIN_SAFETY" in (ROOT / "quality_9q_engine_21.py").read_text() and "Q10_MIN_SAFETY = 75.0" in (ROOT / "quality_9q_engine_21.py").read_text())
check("script version marker fixed", "COMMIT21-9Q-FIX1" in script)
check("template cache bust fixed", "20261003-COMMIT21-9Q-FIX1" in template)
check("multiasset identity preserved", "CRYPTO TRADER ANALYST PRO · MULTIACTIVOS" in template)
check("no extra workers in Fix module", not re.search(r"workers\s*[=:]\s*[2-9]|--workers\s+[2-9]", ppe, re.I))

# Synthetic contract check for the route pre-screen logic without importing the full Flask runtime.
def q10_codes(levels):
    safety = float(levels.get("execution_safety", 0))
    tp = float(levels.get("tp_quality_score", 0))
    sl = float(levels.get("sl_reliability", 0))
    if sl <= 1: sl *= 100
    rr = float(levels.get("risk_reward", 0))
    rc = levels.get("risk_control") or {}
    planned = float(rc.get("estimated_sl_loss_pct_margin", abs(float(levels.get("roi_sl", 0)))))
    atr = float(rc.get("estimated_atr_stress_loss_pct_margin", 0))
    codes=[]
    if safety < 75: codes.append("SAFETY")
    if tp < 55: codes.append("TP_QUALITY")
    if sl < 60: codes.append("SL_QUALITY")
    if not 1.8 <= rr <= 3.5: codes.append("RR")
    if planned > 8: codes.append("LOSS_AT_SL")
    if not 0 < atr <= 25: codes.append("ATR_STRESS")
    return codes

valid = {
    "execution_safety": 80, "tp_quality_score": 70, "sl_reliability": .75,
    "risk_reward": 2.2, "risk_control": {"estimated_sl_loss_pct_margin": 4, "estimated_atr_stress_loss_pct_margin": 12},
}
invalid_rr = dict(valid, risk_reward=4.1)
check("synthetic valid package passes Q10 precheck", q10_codes(valid) == [])
check("synthetic RR-invalid package blocked", "RR" in q10_codes(invalid_rr))

print(f"COMMIT 21.1 FIX QA: {passed} PASS")
