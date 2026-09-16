from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_bridge_preserves_champion_contract():
    src = _src("research_bridge.py")
    start = src.index("def _compact_promotion")
    block = src[start:src.index("def _compact(force", start)]
    for token in ("strategy_card", "strategy_spec", "strategy_id", "runtime_trackable", "scope"):
        assert token in block


def test_fusion_exposes_card_and_shadow_diagnostic():
    src = _src("research_evidence_fusion.py")
    assert "STRATEGY_SPEC_MISSING" in src
    assert "WAITING_MARKET_SETUP" in src
    assert '"strategy_card"' in src
    assert '"strategy_spec"' in src
    assert '"shadow_wait_reason_es"' in src
    assert '"shadow_tracking_errors"' in src


def test_runtime_skips_identical_writes_before_postgrest():
    src = _src("runtime_persistence.py")
    assert "_stable_digest" in src
    assert "_RC8_IDENTICAL_WRITE_SECONDS" in src
    assert "macro_digest" in src


def test_signal_insert_recovers_unique_race():
    src = _src("supabase_client.py")
    assert "duplicate key" in src
    assert "23505" in src
    assert "candle_timestamp" in src


def test_rc8_sql_contract():
    sql = _src("schema_rc8_database_intelligence_gc.sql")
    for token in ("uq_signals_market_candle_action_v1","skip_research_noop_v1","skip_runtime_snapshot_noop_v1","research_evidence_compact_v1","*/15 * * * *","idx_signal_results_signal_created_desc"):
        assert token in sql


def test_analytics_is_user_first_not_id_first():
    js = _src("static/analytics.js")
    start = js.index("const strategyCardHtml=row=>{")
    segment = js[start:js.index("const renderBt=", start)]
    assert "Qué busca" in segment
    assert "Detalles técnicos / auditoría" in segment
    assert segment.index("Qué busca") < segment.index("ID técnico inmutable")
    assert "Ficha enriquecida pendiente" not in segment
