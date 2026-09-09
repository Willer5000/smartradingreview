"""
COMMIT 2 — Execution Learning V2

Capa puramente diagnóstica para ReviewTrader.

Objetivos:
- atribuir cada estrategia al trader y a la dirección que realmente votó;
- separar soporte/oposición respecto del consenso final;
- clasificar retrospectivamente por qué un Entry terminó en TP/SL/expired;
- resumir MFE/MAE y recuperación posterior al SL sin modificar producción.

Guardrails:
- NO modifica votos;
- NO modifica Safety;
- NO modifica Entry, SL o TP;
- NO modifica leverage;
- NO modifica Publication Gate;
- NO promociona estrategias.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
import math


EXECUTION_LEARNING_VERSION = "COMMIT2_EXECUTION_LEARNING_V2"
STRATEGY_ATTRIBUTION_VERSION = "COMMIT2_STRATEGY_ATTRIBUTION_V2"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def normalize_direction(action: Any) -> str:
    """Normaliza acciones Spot/Futures al espacio LONG/SHORT/NO_OPERAR."""
    text = str(action or "").strip().upper()
    aliases = {
        "COMPRA_SPOT": "LONG",
        "BUY": "LONG",
        "COMPRAR": "LONG",
        "VENTA_SPOT": "SHORT",
        "SELL": "SHORT",
        "VENDER": "SHORT",
        "ESPERAR": "NO_OPERAR",
        "HOLD": "NO_OPERAR",
        "MANTENER": "NO_OPERAR",
    }
    text = aliases.get(text, text)
    return text if text in {"LONG", "SHORT"} else "NO_OPERAR"


def build_strategy_attribution_v2(
    analysis_result: Dict[str, Any],
    system_type: str,
) -> Dict[str, Any]:
    """
    Construye un snapshot compacto de atribución por trader/estrategia.

    Importante: no interpreta si una estrategia es "buena". Sólo preserva
    quién la emitió, en qué dirección votó y si apoyó/contradijo la decisión
    final. Así un TP de LONG no se acredita accidentalmente a una estrategia
    que en realidad votó SHORT.
    """
    analysis_result = analysis_result or {}
    decision = analysis_result.get("decision") or {}
    if not isinstance(decision, dict):
        decision = {}

    final_action_raw = decision.get("action", "NO_OPERAR")
    final_action = normalize_direction(final_action_raw)

    registro = decision.get("registro_votacion") or {}
    votes: Iterable[Any]
    if isinstance(registro, dict):
        votes = registro.get("todos_los_votos") or []
    elif isinstance(registro, list):
        votes = registro
    else:
        votes = []

    items: List[Dict[str, Any]] = []
    seen = set()

    for vote in votes:
        if not isinstance(vote, dict):
            continue

        trader = str(vote.get("trader") or "").strip()
        vote_action_raw = vote.get("accion", vote.get("action", "NO_OPERAR"))
        vote_action = normalize_direction(vote_action_raw)
        confidence = _safe_float(
            vote.get("confianza_original", vote.get("confianza", 0.0)),
            0.0,
        )

        if final_action in {"LONG", "SHORT"}:
            if vote_action == final_action:
                relation = "SUPPORT"
            elif vote_action in {"LONG", "SHORT"}:
                relation = "OPPOSE"
            else:
                relation = "NEUTRAL"
        else:
            relation = "NEUTRAL_FINAL"

        strategies = vote.get("estrategias") or []
        if not isinstance(strategies, (list, tuple, set)):
            strategies = []

        for strategy in strategies:
            strategy_name = str(strategy or "").strip().upper()
            if not strategy_name:
                continue

            dedupe_key = (trader.upper(), strategy_name, vote_action)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            items.append(
                {
                    "trader": trader or "UNKNOWN",
                    "strategy": strategy_name,
                    "vote_action": vote_action,
                    "vote_action_raw": str(vote_action_raw or ""),
                    "confidence": round(confidence, 2),
                    "relation_to_final": relation,
                }
            )

    return {
        "version": STRATEGY_ATTRIBUTION_VERSION,
        "diagnostic_only": True,
        "system_type": str(system_type or "").strip().lower(),
        "final_action": final_action,
        "final_action_raw": str(final_action_raw or ""),
        "items": items,
        "item_count": len(items),
        "trader_count": len({item["trader"] for item in items}),
    }


def build_execution_forensics(
    signal: Dict[str, Any],
    result: Dict[str, Any],
    *,
    entry_touched: Optional[bool] = None,
    entry_timestamp: Optional[str] = None,
    candles_to_entry: int = 0,
    post_stop_recovery: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construye diagnóstico retrospectivo a partir de un outcome ya observado."""
    signal = signal or {}
    result = result or {}

    status = str(result.get("status") or "").strip().lower()
    entry = _safe_float(signal.get("entry_price"), 0.0)
    sl = _safe_float(signal.get("stop_loss"), 0.0)
    tp = _safe_float(signal.get("take_profit"), 0.0)
    action = normalize_direction(signal.get("action_normalized"))

    risk_abs = abs(entry - sl) if entry > 0 and sl > 0 else 0.0
    reward_abs = abs(tp - entry) if entry > 0 and tp > 0 else 0.0
    planned_rr = reward_abs / risk_abs if risk_abs > 0 else 0.0

    mfe_r = max(0.0, _safe_float(result.get("mfe_r"), 0.0))
    mae_r = max(0.0, _safe_float(result.get("mae_r"), 0.0))
    mfe_pct = max(0.0, _safe_float(result.get("mfe_pct"), 0.0))
    mae_pct = max(0.0, _safe_float(result.get("mae_pct"), 0.0))

    if entry_touched is None:
        if status in {"tp_hit", "sl_hit", "ambiguous"}:
            entry_touched = True
        else:
            entry_touched = bool(result.get("entry_touched", False))

    target_progress = (
        min(2.0, mfe_r / planned_rr)
        if planned_rr > 0
        else 0.0
    )
    mfe_mae_ratio = (
        mfe_r / mae_r
        if mae_r > 1e-9
        else (mfe_r if mfe_r > 0 else 0.0)
    )

    if not entry_touched:
        diagnosis = "ENTRY_NOT_REACHED"
    elif status == "tp_hit":
        diagnosis = "ENTRY_DEFENDED_TO_TARGET"
    elif status == "sl_hit":
        if mfe_r < 0.25:
            diagnosis = "STOPPED_WITHOUT_PROGRESS"
        elif mfe_r < 0.75:
            diagnosis = "STOPPED_AFTER_WEAK_PROGRESS"
        else:
            diagnosis = "STOPPED_AFTER_MEANINGFUL_PROGRESS"
    elif status == "expired":
        diagnosis = "EXPIRED_AFTER_ENTRY"
    elif status == "ambiguous":
        diagnosis = "AMBIGUOUS_OHLC_SEQUENCE"
    elif status == "invalid_setup":
        diagnosis = "INVALID_SETUP"
    else:
        diagnosis = "UNRESOLVED_DIAGNOSTIC"

    recovery = dict(post_stop_recovery or {})
    stop_was_possibly_tight = bool(
        status == "sl_hit"
        and (
            recovery.get("tp_reached_after_stop")
            or (
                recovery.get("reclaimed_entry")
                and _safe_float(recovery.get("best_favorable_r_after_stop"), 0.0)
                >= 0.75
            )
        )
    )

    return {
        "version": EXECUTION_LEARNING_VERSION,
        "diagnostic_only": True,
        "action": action,
        "status": status,
        "entry_reached": bool(entry_touched),
        "entry_timestamp": entry_timestamp,
        "candles_to_entry": int(candles_to_entry or 0),
        "candles_to_result": int(result.get("candles_to_result", 0) or 0),
        "planned_rr": round(planned_rr, 4),
        "mfe_r": round(mfe_r, 4),
        "mae_r": round(mae_r, 4),
        "mfe_pct": round(mfe_pct, 4),
        "mae_pct": round(mae_pct, 4),
        "mfe_mae_ratio": round(mfe_mae_ratio, 4),
        "target_progress_ratio": round(target_progress, 4),
        "diagnosis": diagnosis,
        "stop_was_possibly_tight": stop_was_possibly_tight,
        "post_stop_recovery": recovery,
    }
