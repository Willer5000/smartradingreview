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

_INTERNAL_DELIBERATION_WORDS = re.compile(
    r"\b(?:comit[eé]|veto(?: [uú]nico)?|r[eé]plica(?: del comit[eé])?|voto(?:s)?|consenso|trader(?: de revisi[oó]n)?)\b",
    re.I,
)
_ROLE_PREFIX = re.compile(
    r"^\s*(?:Esc[eé]ptico|Smart Money|Chartista|Multiframe|Pullback|El Liquidador)\s*(?:\([^)]*%[^)]*\))?\s*[:\-–]\s*",
    re.I,
)
_ROLE_WITH_PERCENT = re.compile(
    r"\b(?:Esc[eé]ptico|Smart Money|Chartista|Multiframe|El Liquidador)\s*\(\s*\d+(?:[.,]\d+)?%\s*\)",
    re.I,
)


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
    # Deliberación interna nunca es una justificación técnica pública.
    if _INTERNAL_DELIBERATION_WORDS.search(text):
        return ""

    # Si un motivo heredado sólo prefija el nombre de un rol interno, retiramos
    # la etiqueta y preservamos la explicación técnica posterior. Términos de
    # trading legítimos como "pullback" siguen siendo visibles.
    text = _ROLE_PREFIX.sub("", text).strip()
    text = _ROLE_WITH_PERCENT.sub("", text).strip(" -–:;")
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

    # RC9: architecture-level filler is never shown as a market reason.
    if contains_generic_public_phrase(cleaned):
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


# ===================== RC9 PUBLIC DECISION EVIDENCE =====================
_GENERIC_PHRASES = (
    "uno o más filtros",
    "filtros activos",
    "calidad suficiente",
    "evidencia disponible no supera",
    "mínimos de estructura, ejecución y riesgo",
    "confirmación suficiente",
)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _u(value: Any) -> str:
    return str(value or "").strip().upper()


def _pick(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(d, dict) and d.get(key) is not None:
            return d.get(key)
    return default


def _append_unique(out: List[str], text: str) -> None:
    text = " ".join(str(text or "").split()).strip()
    if not text:
        return
    if text[-1] not in ".!?":
        text += "."
    if text not in out:
        out.append(text)


def contains_generic_public_phrase(text: object) -> bool:
    low = str(text or "").lower()
    return any(token in low for token in _GENERIC_PHRASES)


def build_public_decision_evidence(
    action: str,
    *,
    trend: Dict[str, Any] | None = None,
    momentum: Dict[str, Any] | None = None,
    volatility: Dict[str, Any] | None = None,
    volume: Dict[str, Any] | None = None,
    structure: Dict[str, Any] | None = None,
    correlation: Dict[str, Any] | None = None,
    market_hours: Dict[str, Any] | None = None,
    confirmation: Dict[str, Any] | None = None,
    sentiment: Dict[str, Any] | None = None,
    liquidation: Dict[str, Any] | None = None,
    limit: int = 4,
) -> List[str]:
    """Return concise, numerical, trader-readable reasons for ``action``.

    This function is deliberately defensive because old analyses do not all use
    the same key names.  It only states a number when that number is present.
    """
    action = _u(action) or "NO_OPERAR"
    if action in {"PRECAUCION", "PRECAUCIÓN"}:
        action = "CAUTION"

    trend = trend or {}
    momentum = momentum or {}
    volatility = volatility or {}
    volume = volume or {}
    structure = structure or {}
    correlation = correlation or {}
    market_hours = market_hours or {}
    confirmation = confirmation or {}
    sentiment = sentiment or {}
    liquidation = liquidation or {}

    out: List[str] = []
    adx = _f(_pick(trend, "adx", "adx_value"), 0.0)
    plus_di = _f(_pick(trend, "plus_di", "di_plus"), 0.0)
    minus_di = _f(_pick(trend, "minus_di", "di_minus"), 0.0)
    trend_dir = _u(_pick(trend, "direction", "trend_direction"))
    mom_dir = _u(_pick(momentum, "direction", "momentum_direction"))
    rsi = _f(_pick(momentum, "rsi", "rsi_14"), 50.0)
    atr_pct = _f(_pick(volatility, "atr_pct", "atr_percent"), 0.0)
    bb_width = _f(_pick(volatility, "bb_width", "bollinger_width"), 0.0)
    volume_ratio = _f(_pick(volume, "volume_ratio", "relative_volume"), 1.0)
    struct_dir = _u(_pick(structure, "direction", "structure_direction"))

    # 1) Market direction / lack of direction.
    if adx > 0:
        if adx < 20:
            _append_unique(out, f"ADX en {adx:.1f} está por debajo de 20; la fuerza direccional es baja y aumenta el riesgo de falsas rupturas")
        elif adx >= 25:
            dmi_text = ""
            if plus_di > 0 or minus_di > 0:
                dmi_text = f" (+DI {plus_di:.1f} / -DI {minus_di:.1f})"
            _append_unique(out, f"ADX en {adx:.1f}{dmi_text} confirma una tendencia con fuerza suficiente para evaluar continuidad")
        else:
            _append_unique(out, f"ADX en {adx:.1f} muestra una tendencia todavía moderada; la entrada necesita confirmación adicional de estructura o volumen")

    # 2) Direction agreement / conflict.
    directional_action = "BULLISH" if action in {"COMPRA_SPOT", "LONG"} else "BEARISH" if action in {"VENTA_SPOT", "SHORT"} else ""
    dirs = [d for d in (trend_dir, mom_dir, struct_dir) if d and d not in {"NEUTRAL", "NONE", "UNKNOWN"}]
    if directional_action and dirs:
        agree = sum(1 for d in dirs if directional_action in d or (directional_action == "BULLISH" and d in {"UP", "LONG"}) or (directional_action == "BEARISH" and d in {"DOWN", "SHORT"}))
        if agree >= 2:
            _append_unique(out, f"Tendencia, momentum y estructura muestran una lectura mayormente coherente con el movimiento {('alcista' if directional_action == 'BULLISH' else 'bajista')}")
    elif action in {"NO_OPERAR", "ESPERAR", "CAUTION"} and len(set(dirs)) > 1:
        _append_unique(out, "Tendencia, momentum y estructura no apuntan en la misma dirección; entrar ahora expone la operación a un giro antes de confirmar")

    # 3) Momentum.
    if rsi <= 35:
        _append_unique(out, f"RSI en {rsi:.1f} refleja presión vendedora intensa y zona de sobreventa; una compra necesita señal de recuperación antes de entrar")
    elif rsi >= 65:
        _append_unique(out, f"RSI en {rsi:.1f} refleja presión compradora elevada y cercanía a sobrecompra; perseguir el precio aumenta el riesgo de retroceso")
    elif action in {"NO_OPERAR", "ESPERAR", "CAUTION"} and 45 <= rsi <= 55:
        _append_unique(out, f"RSI en {rsi:.1f} permanece en zona neutral y no aporta una ventaja direccional clara")

    # 4) Volume / participation.
    if volume_ratio > 0:
        if volume_ratio < 0.75:
            _append_unique(out, f"El volumen actual es {volume_ratio:.2f}× del promedio; la participación es baja y una ruptura tendría menos respaldo")
        elif volume_ratio >= 1.30:
            _append_unique(out, f"El volumen alcanza {volume_ratio:.2f}× el promedio, señal de participación suficiente para respaldar el movimiento observado")

    # 5) Volatility.
    if atr_pct > 0:
        if atr_pct >= 5:
            _append_unique(out, f"ATR equivale a {atr_pct:.2f}% del precio; la volatilidad es extrema y amplía el recorrido necesario del Stop Loss")
        elif atr_pct >= 2.5:
            _append_unique(out, f"ATR equivale a {atr_pct:.2f}% del precio; la volatilidad es alta y exige mayor margen frente al ruido")
    squeeze_on = bool(_pick(volatility, "squeeze_on", "squeeze", default=False))
    if squeeze_on:
        extra = f" (ancho de bandas {bb_width:.2f}%)" if bb_width > 0 else ""
        _append_unique(out, f"Las Bandas de Bollinger están comprimidas{extra}; el precio necesita romper y confirmar el rango antes de asumir dirección")

    # 6) Concrete structure / confirmation fields when present.
    range_break = _pick(confirmation, "range_break_confirmed", "breakout_confirmed", "confirmed")
    required_closes = int(max(1, _f(_pick(confirmation, "required_closed_candles", "required_closes", "confirm_bars"), 0)))
    current_closes = int(max(0, _f(_pick(confirmation, "closed_candles", "confirmed_closes"), 0)))
    if range_break is False:
        if required_closes:
            _append_unique(out, f"La ruptura todavía no está confirmada: hay {current_closes} de {required_closes} cierres requeridos fuera del rango")
        else:
            _append_unique(out, "El precio continúa sin un cierre confirmado fuera del rango reciente; conviene esperar una ruptura cerrada o un retest defendido")

    support = _f(_pick(structure, "support", "nearest_support", "support_level"), 0.0)
    resistance = _f(_pick(structure, "resistance", "nearest_resistance", "resistance_level"), 0.0)
    current_price = _f(_pick(structure, "current_price", "price"), 0.0)
    if current_price > 0 and support > 0 and resistance > 0 and action in {"NO_OPERAR", "ESPERAR", "CAUTION"}:
        if support < current_price < resistance:
            _append_unique(out, f"El precio ({current_price:.2f}) sigue entre soporte {support:.2f} y resistencia {resistance:.2f}; falta salida confirmada del rango")

    # 7) Liquidation / market-time risk when supplied.
    liq_risk = _u(_pick(liquidation, "risk", "risk_level", "state"))
    if liq_risk in {"HIGH", "EXTREME", "CRITICAL"}:
        _append_unique(out, "Hay concentración elevada de liquidaciones cerca del precio; aumenta la probabilidad de barridas antes del movimiento principal")
    session_liq = _u(_pick(market_hours, "liquidity", "liquidity_level"))
    if session_liq in {"LOW", "VERY_LOW", "BAJA", "MUY_BAJA"}:
        _append_unique(out, "La sesión actual tiene liquidez reducida; las rupturas tienen mayor riesgo de ser falsas y requieren confirmación adicional")

    # 8) If still empty, state exactly what readings are missing rather than a
    # vague filter message.
    if not out:
        missing = []
        if not trend: missing.append("tendencia/ADX")
        if not momentum: missing.append("momentum/RSI")
        if not volume: missing.append("volumen")
        if not volatility: missing.append("volatilidad/ATR")
        if not structure: missing.append("estructura")
        if missing:
            _append_unique(out, "No se publica una entrada porque faltan lecturas actuales de " + ", ".join(missing[:4]) + "; sin esos datos no puede definirse una invalidación responsable")
        else:
            _append_unique(out, "El precio no presenta todavía una combinación clara de dirección, estructura y participación que permita definir una entrada y una invalidación defendibles")

    # Decision-specific closing condition, concrete and understandable.
    if action == "ESPERAR":
        _append_unique(out, "La decisión cambia cuando aparezca un cierre confirmado, un retest defendido o una alineación clara entre dirección y volumen")
    elif action == "CAUTION":
        _append_unique(out, "La operación sólo mejora si disminuye el riesgo actual o aparece una confirmación adicional que permita mantener el Stop Loss fuera del ruido")
    elif action == "NO_OPERAR":
        _append_unique(out, "Se vuelve a evaluar cuando el mercado muestre dirección suficiente y permita definir Entry, Stop Loss y Take Profit sin perseguir el precio")

    return out[: max(1, int(limit or 4))]


def join_public_decision_evidence(*args: Any, **kwargs: Any) -> str:
    return " ".join(build_public_decision_evidence(*args, **kwargs))

