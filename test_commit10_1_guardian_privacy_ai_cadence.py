from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
AI = (ROOT / "ai_advisor.py").read_text(encoding="utf-8")
JS = (ROOT / "static" / "ai_assistant.js").read_text(encoding="utf-8")
RENDER = (ROOT / "render.yaml").read_text(encoding="utf-8")


def _function_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(lines[node.lineno - 1 : end])
    raise AssertionError(f"Function not found: {name}")


def _allocation_helper():
    tree = ast.parse(APP)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_tgp_public_allocation_lines":
            ns = {}
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(module, "<allocation-helper>", "exec"), ns)
            return ns[node.name]
    raise AssertionError("_tgp_public_allocation_lines missing")


def test_spot_telegram_buy_uses_percentage_only():
    helper = _allocation_helper()
    out = " ".join(
        helper(
            {
                "action": "BUY_BTC",
                "source_asset": "USDT",
                "target_asset": "BTC",
                "trade_size_pct": 0.10,
                "amount_usd": 22.0,
                "amount_crypto": 0.00028,
                "portfolio_before": {"pct_btc": 0.30},
                "portfolio_after": {"pct_btc": 0.35},
            }
        )
    )
    assert "10.0% de USDT" in out
    assert "22" not in out
    assert "0.00028" not in out
    assert "$" not in out


def test_spot_telegram_sale_uses_source_portfolio_percentage_only():
    helper = _allocation_helper()
    out = " ".join(
        helper(
            {
                "action": "SELL_BTC",
                "source_asset": "BTC",
                "target_asset": "USDT",
                "trade_size_pct": 0.10,
                "amount_usd": 999.99,
                "amount_crypto": 0.012345,
                "portfolio_before": {"pct_usdt": 0.10},
                "portfolio_after": {"pct_usdt": 0.20},
            }
        )
    )
    assert "10.0% del portafolio BTC" in out
    assert "999.99" not in out
    assert "0.012345" not in out


def test_spot_telegram_builders_do_not_render_nominal_amounts():
    proactive = _function_source(APP, "_build_proactive_spot_guardian_message")
    legacy = _function_source(APP, "send_tgp_telegram_alert")
    for source in (proactive, legacy):
        assert "amount_usd" not in source
        assert "amount_crypto" not in source
        assert "_tgp_public_allocation_lines" in source
        assert "montos exactos" in source.lower()


def test_futures_guardian_message_is_compact_but_actionable():
    source = _function_source(APP, "_build_futures_guardian_telegram_message")
    assert "PROTEGER + AUMENTAR" in source
    assert "PROTEGER + EXTENDER" in source
    assert "REDUCIR / PROTEGER" in source
    assert "SALIR DE LA OPERACIÓN" in source
    assert "SL:" in source
    assert "TP:" in source
    assert "➕ Entrada:" in source
    assert "RR incremental:" in source
    assert "no promediar pérdida" in source
    assert "Deterioro" in source
    assert "Protección de riesgo" not in source
    assert "Aumento de posición · sólo confirmación" not in source
    assert "Margen orientativo:" not in source


def test_futures_ai_advice_no_longer_uses_15_minute_actionable_bucket():
    source = _function_source(AI, "_fingerprint")
    assert "interval_minutes = (" in source
    assert "30" in source
    assert "if futures_actionable" in source
    assert "else 60" in source
    assert "15" not in source


def test_futures_manual_assistant_is_spaced_every_20_minutes():
    assert '"AI_MANUAL_MIN_INTERVAL_MINUTES",' in AI
    assert '"20"' in AI
    assert "MANUAL_FUTURES_MIN_INTERVAL_MINUTES" in AI
    assert "manual_futures_cooldown" in AI
    assert "1 pregunta cada" in AI
    assert "AI_MANUAL_MIN_INTERVAL_MINUTES" in RENDER
    assert 'value: "20"' in RENDER
    assert "Futures: 1 pregunta cada 20 min" in JS
    assert "Futures: próxima pregunta en" in JS



def test_futures_manual_cooldown_cannot_be_bypassed_by_cache():
    source = _function_source(AI, "run_ai_advisor")
    assert 'manual_futures_request = (' in source
    assert 'usage_type == "MANUAL"' in source
    assert 'market == "FUTURES"' in source
    assert 'if cached and not manual_futures_request' in source

def test_groq_token_fuse_has_zero_token_local_fallback_for_advice_and_chat():
    source = _function_source(AI, "run_ai_advisor")
    assert "token_budget_limited" in source
    assert "_local_operational_fallback" in source
    assert 'context_type in {"HOURLY_MARKET_ADVICE", "MANUAL_CHAT"}' in source
    fallback = _function_source(AI, "_local_operational_fallback")
    assert "LOCAL_RULES" in fallback
    assert "No se altera LONG/SHORT, Entry, SL, TP ni leverage" in fallback


def test_ui_no_longer_labels_30_minute_advice_as_hourly_unavailable():
    assert "Consejo horario no disponible" not in JS
    assert "Consejo IA no disponible" in JS
    assert "Evaluación 30 min" in JS
