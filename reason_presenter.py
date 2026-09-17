"""Presentación pública de motivos de trading.

Los identificadores internos de Research, gobernanza, contingencia y versiones
se conservan para auditoría, pero NO forman parte de la justificación visible
de una recomendación. La justificación pública debe hablar de mercado:
tendencia, momentum, volatilidad, volumen, estructura, liquidez y ejecución.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

# Identificadores de arquitectura/estado. Nunca se convierten en una frase
# pública de recomendación: se omiten y permanecen sólo en auditoría/Analytics.
_INTERNAL_ONLY_CODES = {
    "ACTION_CELL_NOT_YET_VALIDATED",
    "RESEARCH_UNAVAILABLE",
    "VALIDATED_CHAMPION_AVAILABLE",
    "KNOWN_NEGATIVE_OR_DECAY",
    "CONTINGENCY_PLAYBOOK_NOT_VALIDATED_ALPHA",
    "CONTINGENCY_ENGINE_ERROR",
    "NOT_EVALUATED",
    "EDGE_BLOCKED",
    "NEGATIVE_OOS",
    "SHADOW_DIVERGED",
    "ALPHA_DECAY",
    "DEGRADED_LOSS_STREAK",
    "DEGRADED_ROLLING",
    "DEGRADED_RETEST",
}

# Nombres internos del playbook. El setup queda registrado en context/Research,
# pero no se usa como una supuesta "razón" frente al usuario.
_INTERNAL_SETUP_CODES = {
    "STRUCTURE_RETEST",
    "TREND_PULLBACK",
    "BREAKOUT_RETEST",
    "LIQUIDITY_SWEEP_REVERSAL",
    "RANGE_MEAN_REVERSION",
    "SPOT_ROTATION",
    "DEFAULT_STRUCTURE_RETEST",
    "DEFAULT_TREND_PULLBACK",
    "DEFAULT_BREAKOUT_RETEST",
    "DEFAULT_LIQUIDITY_SWEEP_REVERSAL",
    "DEFAULT_RANGE_MEAN_REVERSION",
    "DEFAULT_SPOT_ROTATION",
}

_CODE_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b")
_VERSION_PREFIX = re.compile(r"\bRC\d+(?:\.\d+)?\s*(?:contingencia|contingency)?\s*:\s*", re.I)


def _is_internal(code: str) -> bool:
    value = str(code or "").strip().upper()
    return value in _INTERNAL_ONLY_CODES or value in _INTERNAL_SETUP_CODES


def humanize_code(value: object) -> str:
    """No inventa prosa para códigos internos: los excluye de la UI pública."""
    code = str(value or "").strip().upper()
    if not code or _is_internal(code):
        return ""
    # Si un identificador desconocido llega a esta capa, es más seguro ocultarlo
    # que transformar PROGRAMMER_CODE en una justificación artificial.
    if _CODE_TOKEN.fullmatch(code):
        return ""
    return str(value or "").strip()


def public_reason(value: object, *, fallback: str = "") -> str:
    """Conserva sólo prosa natural de mercado y elimina metadatos internos."""
    text = str(value or "").strip()
    if not text:
        return str(fallback or "").strip()

    exact = text.upper()
    if _is_internal(exact):
        return ""

    text = _VERSION_PREFIX.sub("", text).strip()

    # Elimina códigos incrustados en frases heredadas. Si tras retirarlos sólo
    # quedan separadores, no muestra nada. La UI debe usar las razones reales
    # de los traders/indicadores en lugar de explicar la arquitectura.
    def repl(match: re.Match) -> str:
        token = match.group(0)
        return "" if _is_internal(token) or _CODE_TOKEN.fullmatch(token) else token

    cleaned = _CODE_TOKEN.sub(repl, text)
    cleaned = re.sub(r"\s*·\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -·:.;")

    if not cleaned:
        return ""

    if cleaned[-1] not in ".!?":
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
    """La contingencia no se explica en la recomendación pública.

    reason_code/setup_code quedan disponibles en ``contingency_playbook`` para
    auditoría y aprendizaje. La recomendación usa las razones de mercado que ya
    emitieron los especialistas.
    """
    del reason_code, setup_code
    return ""
