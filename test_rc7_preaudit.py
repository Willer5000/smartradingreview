from pathlib import Path

from research_strategy_card import build_strategy_card

ROOT = Path(__file__).resolve().parent


def test_spot_busy_is_deferred_202_and_cache_only_exists():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    block = src[src.index("@app.route('/api/analyze')"):src.index("@app.route('/api/telegram/test") if "@app.route('/api/telegram/test" in src else src.index("@app.route('/api/analyze-with-portfolio")]
    assert "cache_only" in block
    assert "'deferred': True" in block
    assert "'retry_after_ms': 1800" in block
    assert "}), 202" in block


def test_quality_v2_request_is_ram_first_not_supabase_first():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    start = src.index("def api_analytics_quality_v2")
    end = src.index("@app.route('/api/analytics/strategies')", start)
    block = src[start:end]
    assert "_analytics_quality_ram_get(filters)" in block
    assert "_schedule_analytics_quality_refresh(filters)" in block
    assert "stored=_load_analytics_quality_snapshot" not in block
    assert "}),202" in block.replace(" ", "")


def test_hidden_90s_timer_does_not_launch_heavy_analysis():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    start = html.index("CONTEXTO / CORRELACIÓN - Cada 90 segundos, SIN análisis pesado")
    end = html.index("// 3.", start)
    block = html[start:end]
    assert "fetch(" not in block
    assert "globalCorrelationData" in block


def test_secondary_spot_correlation_reads_cache_only():
    js = (ROOT / "static" / "script.js").read_text(encoding="utf-8")
    assert "&cache_only=1" in js
    assert "retry_after_ms" in js
    assert "if (!window.IS_FUTURES_PAGE && data?.busy)" in js
    assert "if (window.IS_FUTURES_PAGE && data?.busy)" in js


def test_futures_async_error_has_backoff_instead_of_relaunch_storm():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _get_futures_ui_recent_error" in src
    assert "'job_state': 'BACKOFF'" in src
    assert "'retry_after_ms': 5000" in src


def test_strategy_card_fallback_is_exact_deterministic_and_visible():
    fusion = (ROOT / "research_evidence_fusion.py").read_text(encoding="utf-8")
    analytics = (ROOT / "static" / "analytics.js").read_text(encoding="utf-8")
    assert "_build_strategy_card" in fusion
    assert 'meta.get("causal_strategy_spec")' in fusion
    assert "Ficha de estrategia" in analytics
    assert "Parámetros exactos validados" in analytics

    spec = {
        "family": "MOMENTUM_BREAKOUT", "direction_mode": "LONG",
        "fast": 9, "slow": 21, "rsi_len": 14,
        "rsi_low": 42, "rsi_high": 58, "lookback": 20,
        "volume_mult": 0.9, "entry_style": "NEXT_OPEN", "entry_atr": 0.0,
        "sl_atr": 1.5, "rr": 2.25, "max_wait": 3, "max_hold": 8,
        "volatility_mode": "EXPANSION", "trend_strength_min": 0.25,
        "indicator": "RSI", "aux_period": 14, "signal_period": 9,
        "band_mult": 2.0, "divergence_mode": "NONE",
    }
    card = build_strategy_card(
        strategy_id="CI_TEST", scope={"market_family":"CRYPTO_SPOT","symbol":"BTC-USDT","timeframe":"12H","direction":"LONG","regime":"TREND_UP"},
        spec=spec, metrics={"all":{"resolved":24},"validation":{"resolved":5,"expectancy_r":0.30488,"profit_factor":1.6636}},
        stage="SHADOW_READY", updated_at=None,
    )
    assert card["raw_spec"] == spec
    assert card["uses_llm"] is False
    assert card["immutable"] is True
    assert card["entry"]["style"] == "NEXT_OPEN"
    assert card["risk"]["rr"] == 2.25
