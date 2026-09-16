from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_main_fusion_recognizes_exact_champion_alpha_decay():
    src = _read("research_evidence_fusion.py")
    assert "current_loss_streak" in src
    assert "loss_streak >= 8" in src
    assert 'return "ALPHA_DECAY"' in src
    assert "recent8_expectancy_r" in src
    assert "previous8_trade_sharpe" in src


def test_profitability_router_hard_blocks_decayed_champion():
    src = _read("profitability_router.py")
    assert "ALPHA_DECAY_VETO" in src
    assert 'block_new_signal=bool(hard)' in src
    assert '"DIVERGED","ALPHA_DECAY"' in src or '"DIVERGED", "ALPHA_DECAY"' in src
    assert "vuelve a Research/Shadow" in src


def test_supabase_522_is_treated_as_transient_and_optional_reads_fail_fast():
    sb = _read("supabase_client.py")
    saved = _read("saved_signals.py")
    ai = _read("ai_advisor.py")
    assert "522" in sb
    assert "cloudflare" in sb.lower()
    assert "json could not be generated" in sb.lower()
    assert "read_circuit" in sb.lower()
    assert "read_circuit" in saved.lower()
    assert "read_circuit" in ai.lower()


def test_futures_frontend_uses_wider_timeout_and_bounded_backoff():
    futures = _read("static/futures.js")
    script = _read("static/script.js")
    assert "16000" in futures
    assert "AbortError" in futures
    assert "25000" in script
    assert "retryCount < 8" in script
    assert "retryCount < 24" not in script
    assert "Math.max(4000, Number(data.retry_after_ms || 6000))" in script


def test_alpha_decay_is_not_confused_with_spot_futures_action_semantics():
    # RC8 recommendation coherence must remain present while adding decay safety.
    src = _read("app.py")
    assert "COMPRA_SPOT" in src
    assert "VENTA_SPOT" in src
    assert "LONG" in src
    assert "SHORT" in src
