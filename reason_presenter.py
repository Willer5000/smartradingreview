"""Public-facing trading reason presenter.

Internal engine identifiers are useful for auditing and tests, but they must
never be shown verbatim as the explanation of a trading decision.  This module
keeps the machine code and the human explanation deliberately separate.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

_CODE_TEXT = {
    "ACTION_CELL_NOT_YET_VALIDATED": (
        "Esta combinación de mercado, par, temporalidad y acción todavía no tiene "
        "una estrategia validada; se aplica el plan de contingencia con riesgo reducido."
    ),
    "RESEARCH_UNAVAILABLE": (
        "La evidencia validada no está disponible temporalmente; se conserva el último "
        "estado conocido y sólo se permite la lógica de contingencia protegida."
    ),
    "STRUCTURE_RETEST": (
        "El movimiento necesita confirmar la nueva estructura con un retesteo antes de ejecutar la entrada."
    ),
    "TREND_PULLBACK": (
        "La tendencia es favorable, pero la entrada debe esperar un retroceso hacia una zona técnica defendible."
    ),
    "BREAKOUT_RETEST": (
        "Hay una ruptura potencial; se exige un retesteo y aceptación del nivel antes de entrar."
    ),
    "LIQUIDITY_SWEEP_REVERSAL": (
        "Se detecta un posible barrido de liquidez; la reversión sólo es válida si estructura y momentum confirman el giro."
    ),
    "RANGE_MEAN_REVERSION": (
        "El mercado está en balance; la operación busca retorno hacia valor desde un extremo del rango, con invalidación clara."
    ),
    "SPOT_ROTATION": (
        "La señal corresponde a una rotación de cartera Spot entre BTC, PAXG y liquidez según fuerza relativa y protección del capital."
    ),
    "NEGATIVE_OOS": (
        "La validación fuera de muestra no confirma una ventaja estadística suficiente para autorizar esta operación."
    ),
    "SHADOW_DIVERGED": (
        "El comportamiento observado en seguimiento real se apartó de la validación y la estrategia queda suspendida."
    ),
    "ALPHA_DECAY": (
        "La estrategia validada muestra deterioro reciente de su ventaja y queda suspendida hasta una nueva validación."
    ),
    "DEGRADED_LOSS_STREAK": (
        "La estrategia acumula una racha de pérdidas incompatible con su comportamiento validado y queda suspendida."
    ),
    "DEGRADED_ROLLING": (
        "Las métricas recientes de la estrategia se deterioraron frente a su referencia y se requiere una nueva validación."
    ),
    "DEGRADED_RETEST": (
        "El retest del mismo linaje no confirmó la ventaja previa; la celda vuelve a búsqueda de una estrategia mejor."
    ),
    "EDGE_BLOCKED": (
        "La evidencia estadística no autoriza una nueva señal ejecutable en esta celda."
    ),
    "CONTINGENCY_PLAYBOOK_NOT_VALIDATED_ALPHA": (
        "Se está usando una estrategia provisional de contingencia; todavía no posee ventaja estadística validada."
    ),
    "CONTINGENCY_ENGINE_ERROR": (
        "El módulo de contingencia no pudo completar su evaluación; se mantiene una postura conservadora."
    ),
    "NOT_EVALUATED": "La contingencia todavía no fue necesaria para esta decisión.",
}

_DEFAULT_SETUP_TEXT = {
    "DEFAULT_STRUCTURE_RETEST": _CODE_TEXT["STRUCTURE_RETEST"],
    "DEFAULT_TREND_PULLBACK": _CODE_TEXT["TREND_PULLBACK"],
    "DEFAULT_BREAKOUT_RETEST": _CODE_TEXT["BREAKOUT_RETEST"],
    "DEFAULT_LIQUIDITY_SWEEP_REVERSAL": _CODE_TEXT["LIQUIDITY_SWEEP_REVERSAL"],
    "DEFAULT_RANGE_MEAN_REVERSION": _CODE_TEXT["RANGE_MEAN_REVERSION"],
    "DEFAULT_SPOT_ROTATION": _CODE_TEXT["SPOT_ROTATION"],
}

# Tokens that are diagnostic identifiers rather than prose.  We do not destroy
# unknown text; we only rewrite code-looking fragments.
_CODE_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b")
_VERSION_PREFIX = re.compile(r"\bRC\d+(?:\.\d+)?\s*(?:contingencia|contingency)?\s*:\s*", re.I)


def humanize_code(value: object) -> str:
    code = str(value or "").strip().upper()
    if not code:
        return ""
    if code in _CODE_TEXT:
        return _CODE_TEXT[code]
    if code in _DEFAULT_SETUP_TEXT:
        return _DEFAULT_SETUP_TEXT[code]
    # Safe generic fallback for an unknown machine identifier.
    return code.replace("_", " ").lower().capitalize() + "."


def public_reason(value: object, *, fallback: str = "") -> str:
    """Return a user-facing Spanish reason while preserving natural prose."""
    text = str(value or "").strip()
    if not text:
        return str(fallback or "").strip()

    exact = text.upper()
    if exact in _CODE_TEXT or exact in _DEFAULT_SETUP_TEXT:
        return humanize_code(exact)

    text = _VERSION_PREFIX.sub("", text).strip()

    # Common legacy compound format: CODE · CODE.  Translate every machine token
    # but leave genuine trading prose untouched.
    def repl(match: re.Match) -> str:
        return humanize_code(match.group(0)).rstrip(".")

    cleaned = _CODE_TOKEN.sub(repl, text)
    cleaned = re.sub(r"\s*·\s*", ". ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -·:")

    if not cleaned:
        cleaned = str(fallback or "").strip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def public_reasons(values: Optional[Iterable[object]], *, limit: int = 4) -> List[str]:
    out: List[str] = []
    for value in values or []:
        reason = public_reason(value)
        if not reason or reason in out:
            continue
        out.append(reason)
        if len(out) >= max(1, int(limit or 4)):
            break
    return out


def contingency_public_reason(reason_code: object, setup_code: object) -> str:
    pieces = []
    for raw in (reason_code, setup_code):
        piece = public_reason(raw)
        if piece and piece not in pieces:
            pieces.append(piece)
    return " ".join(pieces).strip()
