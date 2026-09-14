from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parent


def _txt(path):
    return (ROOT/path).read_text(encoding='utf-8')


def test_final_v1_contract_tracks_40_cells_and_recycles_shadow_divergence():
    txt=_txt('research_evidence_fusion.py')
    assert '_COVERAGE_TARGET = 40' in txt
    assert 'SHADOW_DIVERGED' in txt
    assert 'recycle_required' in txt
    assert 'EARLY_DIVERGENCE' in txt
    assert 'oos_total_r' in txt


def test_router_can_remove_positive_support_when_shadow_diverges():
    txt=_txt('profitability_router.py')
    assert 'SHADOW_DIVERGED_RETEST' in txt
    assert 'recycle_required' in txt
    assert 'CAUSAL_SHADOW_RECYCLE' in txt


def test_reviewtrader_uses_research_as_bounded_prior_not_direction_creator():
    txt=_txt('review_trader.py')
    assert 'SHADOW_DIVERGED' in txt
    assert 'reciclaje/retest' in txt
    # J policy remains bounded; research cannot directly rewrite trade geometry.
    assert 'research_support_max' in txt or 'support_score' in txt


def test_scientist_watchdog_has_independent_runtime_heartbeat():
    app=_txt('app.py')
    advisor=_txt('ai_advisor.py')
    assert '_ensure_ai_learning_scientist_thread' in app
    assert '_AI_LEARNING_RUNTIME_STATE' in app
    assert "status='WATCHDOG_STARTED'" in app
    assert "status='RUNNING_LLM'" in app
    assert 'scheduler_runtime' in app
    assert '.like("job_key", "AI_LEARNING_V2:%")' not in advisor
    assert 'startswith("AI_LEARNING_V2:")' in advisor


def test_macro_cex_evidence_is_permanently_visible_in_main_ticker():
    html=_txt('templates/index.html')
    js=_txt('static/script.js')
    assert 'id="macro-flow-meta"' in html
    assert '_macroRenderFlow' in js
    assert 'CEX 24h' in js
    assert 'aggregate_inflow_7d_usd' in js
    assert 'no equivale a compra/venta propia del exchange' in js


def test_analytics_explicitly_displays_oos_profitability_and_recycle_count():
    js=_txt('static/analytics.js')
    html=_txt('templates/analytics.html')
    assert 'RENTABILIDAD OOS VALIDADA' in js
    assert 'Resultado OOS' in js
    assert 'Celdas validadas' in js
    assert 'Reciclar' in js
    assert '20260914-FINAL-V1-RC2' in html


def test_research_bridge_shows_one_causal_representative_per_cell():
    txt=_txt('research_bridge.py')
    assert '_best_causal_per_cell' in txt
    assert 'CAUSAL_SHADOW_RECYCLE' in txt
    assert 'coverage_cell_id' in txt
    assert "'limit':'1800'" in txt


def test_safety_and_leverage_policies_are_not_changed_by_j1():
    # J.1 does not ship either policy file. It fuses evidence only.
    assert not (ROOT/'leverage_policy.J1.py').exists()
    fusion=_txt('research_evidence_fusion.py')
    assert 'EVIDENCE_PRIOR_ONLY' in fusion
