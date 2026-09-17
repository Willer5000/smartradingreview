"""Presentación pública de motivos de trading.

Los identificadores internos de Research, gobernanza, contingencia y versiones
se conservan para auditoría, pero NO forman parte de la justificación visible
de una recomendación. La justificación pública debe hablar de mercado:
tendencia, momentum, volatilidad, volumen, estructura, liquidez y ejecución.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


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

    # Primero retirar etiquetas de roles internos. La explicación técnica que
    # viene después sí es valiosa para el usuario; sólo ocultamos quién la emitió.
    text = _ROLE_PREFIX.sub("", text).strip()
    text = _ROLE_WITH_PERCENT.sub("", text).strip(" -–:;")
    text = _VERSION_PREFIX.sub("", text).strip()
    # Formulaciones heredadas que revelaban el nombre/especialidad del rol.
    text = re.sub(r"\bVentaja chartista\s+(?:bearish|bajista)\s*:\s*", "Lectura de patrones bajista: ", text, flags=re.I)
    text = re.sub(r"\bVentaja chartista\s+(?:bullish|alcista)\s*:\s*", "Lectura de patrones alcista: ", text, flags=re.I)
    text = re.sub(r"^\s*Multiframe\s*[:\-–]\s*", "Lectura multitemporal: ", text, flags=re.I)
    # El score interno de patrones no tiene una escala útil para un trader final.
    text = re.sub(r"\s*;?\s*score\s+[-+]?\d+(?:[.,]\d+)?\s*(?:vs|contra)\s*[-+]?\d+(?:[.,]\d+)?\s*;?", "; ", text, flags=re.I)

    # Si después de quitar el rol la frase sigue hablando de votos/vetos/comité,
    # es arquitectura interna y no una razón de mercado.
    if _INTERNAL_DELIBERATION_WORDS.search(text):
        return ""

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
# ===================== RC9.1 PROFESSIONAL DECISION COMPOSER =====================
_GENERIC_PHRASES = (
    "uno o más filtros", "filtros activos", "calidad suficiente",
    "evidencia disponible no supera", "mínimos de estructura, ejecución y riesgo",
    "confirmación suficiente", "el volumen y el cierre de vela todavía deben confirmar",
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


def _nested(d: Dict[str, Any], *paths: Tuple[str, ...], default=None):
    for path in paths:
        cur: Any = d
        ok=True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok=False; break
            cur=cur.get(key)
        if ok and cur is not None:
            return cur
    return default


def _append_unique(out: List[str], text: str) -> None:
    text = " ".join(str(text or "").split()).strip()
    if not text:
        return
    if text[-1] not in ".!?":
        text += "."
    low=text.lower()
    if any(low == x.lower() for x in out):
        return
    if text not in out:
        out.append(text)


def contains_generic_public_phrase(text: object) -> bool:
    low = str(text or "").lower()
    return any(token in low for token in _GENERIC_PHRASES)


def exact_spot_instruction(action: str, symbol: str) -> str:
    action=_u(action); symbol=_u(symbol).replace('/', '-')
    base, quote = (symbol.split('-',1)+[''])[:2] if '-' in symbol else (symbol,'')
    if action == 'COMPRA_SPOT':
        if symbol == 'PAXG-BTC':
            return 'ROTAR BTC A PAXG'
        if base and quote:
            return f'COMPRAR {base} CON {quote}'
        return 'COMPRAR SPOT'
    if action == 'VENTA_SPOT':
        if symbol == 'PAXG-BTC':
            return 'ROTAR PAXG A BTC'
        if base and quote:
            return f'VENDER {base} A {quote}'
        return 'VENDER SPOT'
    return action


def _divergence_sentence(momentum: Dict[str, Any]) -> str:
    details = momentum.get('divergence_details') or []
    regular = momentum.get('divergences') or []
    hidden = momentum.get('hidden_divergences') or []
    all_items=[]
    for item in list(details)+list(regular)+list(hidden):
        if isinstance(item, dict):
            typ=str(item.get('type') or item.get('kind') or item.get('direction') or '').lower()
            osc=str(item.get('oscillator') or item.get('indicator') or '').strip()
            if typ:
                all_items.append((typ,osc))
        elif item:
            all_items.append((str(item).lower(),''))
    if not all_items:
        return ''
    typ,osc=all_items[0]
    direction='alcista' if ('bull' in typ or 'alcist' in typ) else 'bajista' if ('bear' in typ or 'bajist' in typ) else ''
    hidden_flag=('hidden' in typ or 'ocult' in typ)
    if direction:
        role='continuación' if hidden_flag else 'posible giro'
        osc_txt=f' en {osc}' if osc else ''
        return f"Se detecta divergencia {'oculta ' if hidden_flag else ''}{direction}{osc_txt}; aporta una señal de {role}, pero debe confirmarse con estructura y volumen"
    return ''


def _structure_evidence(structure: Dict[str, Any], action: str) -> List[str]:
    out=[]
    current=_f(_pick(structure,'current_price','price'),0)
    support=_f(_pick(structure,'support','nearest_support','support_level'),0)
    resistance=_f(_pick(structure,'resistance','nearest_resistance','resistance_level'),0)
    if current>0 and support>0 and resistance>0:
        _append_unique(out,f"El precio está en {current:.2f}, entre soporte {support:.2f} y resistencia {resistance:.2f}; esas zonas delimitan la reacción que debe respetar la operación")
    elif support>0:
        _append_unique(out,f"El soporte técnico más próximo se ubica en {support:.2f}; perderlo o defenderlo cambia la lectura de entrada")
    elif resistance>0:
        _append_unique(out,f"La resistencia técnica más próxima está en {resistance:.2f}; su rechazo o ruptura define la siguiente confirmación")

    obs=structure.get('order_blocks') or structure.get('order_blocks_detected') or []
    fvg=structure.get('fvg') or structure.get('fair_value_gaps') or []
    sweeps=structure.get('stop_hunts') or structure.get('liquidity_sweeps') or []
    if obs:
        last=obs[-1] if isinstance(obs,list) else obs
        if isinstance(last,dict):
            direction=str(last.get('direction') or last.get('type') or '').lower()
            level=_f(last.get('level') or last.get('price'),0)
            suffix=f" cerca de {level:.2f}" if level>0 else ''
            _append_unique(out,f"Hay un Order Block {'alcista' if 'bull' in direction or 'alcist' in direction else 'bajista' if 'bear' in direction or 'bajist' in direction else 'relevante'}{suffix}, zona donde puede concentrarse reacción de precio")
    if fvg:
        _append_unique(out,"Existe un desequilibrio/FVG cercano que puede actuar como zona de reacción antes de continuar el movimiento")
    if sweeps:
        _append_unique(out,"La estructura registra un barrido reciente de liquidez/stop hunt; se exige confirmación después del barrido para no entrar dentro de una trampa")

    vp=structure.get('volume_profile') or {}
    poc=_f(_pick(vp,'poc','poc_price','point_of_control'),0)
    hvn=_pick(vp,'closest_hvn','hvn')
    lvn=_pick(vp,'closest_lvn','lvn')
    if poc>0:
        _append_unique(out,f"El POC del perfil de volumen está en {poc:.2f}; operar demasiado cerca de esa zona implica mayor probabilidad de congestión")
    elif isinstance(hvn,dict) and _f(hvn.get('price'),0)>0:
        _append_unique(out,f"El HVN más cercano está en {_f(hvn.get('price')):.2f}, zona de aceptación que puede frenar el recorrido")
    elif isinstance(lvn,dict) and _f(lvn.get('price'),0)>0:
        _append_unique(out,f"El LVN más cercano está en {_f(lvn.get('price')):.2f}; una ruptura limpia puede acelerar el desplazamiento")
    return out


def _technical_evidence(action: str, trend: Dict[str,Any], momentum: Dict[str,Any], volatility: Dict[str,Any], volume: Dict[str,Any], structure: Dict[str,Any], confirmation: Dict[str,Any], market_hours: Dict[str,Any], liquidation: Dict[str,Any], specialist_reasons: Iterable[Any] | None) -> List[str]:
    out=[]
    action=_u(action)
    t_ind=trend.get('indicators') or {}
    m_ind=momentum.get('indicators') or {}
    v_ind=volume.get('indicators') or {}

    adx=_f(_pick(trend,'adx','adx_value'),0); pdi=_f(_pick(trend,'plus_di','di_plus'),0); mdi=_f(_pick(trend,'minus_di','di_minus'),0)
    tdir=str(_pick(trend,'direction','trend_direction',default='neutral')).lower()
    if adx>0:
        if pdi>0 or mdi>0:
            dom='compradora' if pdi>mdi else 'vendedora' if mdi>pdi else 'equilibrada'
            if adx<20:
                _append_unique(out,f"ADX {adx:.1f} indica poca fuerza direccional; DMI (+DI {pdi:.1f} / -DI {mdi:.1f}) muestra presión {dom}, pero todavía sin una tendencia sólida")
            else:
                _append_unique(out,f"ADX {adx:.1f} mide una tendencia {'fuerte' if adx>=25 else 'en desarrollo'} y DMI (+DI {pdi:.1f} / -DI {mdi:.1f}) confirma dominio de presión {dom}")
        else:
            _append_unique(out,f"ADX {adx:.1f} muestra una tendencia {'fuerte' if adx>=25 else 'moderada' if adx>=20 else 'débil'}")

    ema9=_f(_pick(t_ind,'ema9','ema_9'),0); ema21=_f(_pick(t_ind,'ema21','ema_21'),0); ema50=_f(_pick(t_ind,'ema50','ema_50'),0); ema200=_f(_pick(t_ind,'ema200','ema_200'),0)
    if ema9>0 and ema21>0:
        side='alcista' if ema9>ema21 else 'bajista'
        txt=f"Las EMA 9/21 mantienen alineación {side} ({ema9:.2f} / {ema21:.2f})"
        if ema50>0 and ema200>0:
            txt += f"; EMA 50/200 están en {ema50:.2f} / {ema200:.2f}"
        _append_unique(out,txt)

    rsi=_f(_pick(m_ind,'rsi','rsi_14',default=_pick(momentum,'rsi')),50)
    macd=_f(_pick(m_ind,'macd_histogram','macd_hist','histogram'),0)
    stoch=_f(_pick(m_ind,'stoch_k','stochastic_k'),50)
    mom_bits=[f"RSI {rsi:.1f}"]
    if abs(macd)>1e-12: mom_bits.append(f"histograma MACD {macd:.3f}")
    if stoch!=50: mom_bits.append(f"Estocástico %K {stoch:.1f}")
    _append_unique(out,"El momentum se lee con " + ', '.join(mom_bits) + ("; el impulso es neutral/mixto" if 45<=rsi<=55 and abs(macd)<0.05 else "; confirma presión compradora" if rsi>55 and macd>=0 else "; confirma presión vendedora" if rsi<45 and macd<=0 else "; aún no está completamente alineado"))
    div=_divergence_sentence(momentum)
    if div: _append_unique(out,div)

    vol_ratio=_f(_pick(volume,'volume_ratio','relative_volume','ratio'),0)
    mfi=_f(_pick(v_ind,'mfi',default=_pick(volume,'mfi')),0)
    obv_dir=str(_pick(volume,'obv_direction','direction',default='')).lower()
    if vol_ratio>0:
        if vol_ratio<0.8: _append_unique(out,f"El volumen es {vol_ratio:.2f}× su promedio; la participación es baja y reduce la fiabilidad de una ruptura")
        elif vol_ratio>=1.2: _append_unique(out,f"El volumen alcanza {vol_ratio:.2f}× su promedio y aporta participación real al movimiento")
    elif mfi>0:
        _append_unique(out,f"MFI se encuentra en {mfi:.1f}, útil para valorar presión de entrada/salida de capital")
    if obv_dir and obv_dir not in {'neutral','none'}:
        _append_unique(out,f"OBV mantiene dirección {('alcista' if 'bull' in obv_dir or 'up' in obv_dir else 'bajista' if 'bear' in obv_dir or 'down' in obv_dir else obv_dir)}, confirmando si el volumen acompaña al precio")

    atr_pct=_f(_pick(volatility,'atr_pct','atr_percent','atr_percentage'),0)
    bb_width=_f(_pick(volatility,'bb_width','bollinger_width'),0)
    squeeze=bool(_pick(volatility,'squeeze_on','squeeze',default=False)) or int(_f(_pick(volatility,'squeeze_length'),0))>0
    if atr_pct>0:
        _append_unique(out,f"ATR representa {atr_pct:.2f}% del precio; la volatilidad es {'alta' if atr_pct>=2.5 else 'normal/moderada'} y condiciona la distancia del Stop Loss")
    if squeeze:
        extra=f" (ancho de Bollinger {bb_width:.2f}%)" if bb_width>0 else ''
        _append_unique(out,f"Hay compresión de Bandas de Bollinger{extra}; una salida del rango necesita cierre y participación para evitar una falsa ruptura")

    for txt in _structure_evidence(structure,action): _append_unique(out,txt)

    status=str(_pick(confirmation,'status','confirmation_status',default='')).lower()
    reason=str(_pick(confirmation,'reason','confirmation_reason',default='')).strip()
    wait=int(max(0,_f(_pick(confirmation,'wait_bars','required_closed_candles','required_closes'),0)))
    level=_f(_pick(confirmation,'breakout_level','level'),0)
    if reason and not contains_generic_public_phrase(reason):
        _append_unique(out,reason)
    elif wait>0:
        suffix=f" sobre/bajo {level:.2f}" if level>0 else ''
        _append_unique(out,f"La confirmación todavía requiere {wait} vela(s) cerrada(s){suffix} antes de validar la ruptura")
    elif status in {'pending','waiting','wait','unconfirmed'}:
        _append_unique(out,"La estructura todavía no confirmó la ruptura/retest; entrar antes de un cierre válido aumenta el riesgo de quedar atrapado dentro del rango")

    liq_risk=str(_pick(liquidation,'risk','risk_level','state',default='')).upper()
    if liq_risk in {'HIGH','EXTREME','CRITICAL','ALTO','EXTREMO'}:
        _append_unique(out,"El mapa de liquidaciones muestra concentración cercana al precio; existe riesgo de barrido antes del desplazamiento principal")
    session_liq=str(_pick(market_hours,'liquidity','liquidity_level',default='')).upper()
    if session_liq in {'LOW','VERY_LOW','BAJA','MUY_BAJA'}:
        _append_unique(out,"La liquidez de la sesión es reducida; se exige una confirmación más limpia porque las mechas y falsas rupturas son más probables")

    # Reutilizar la inteligencia de los especialistas, pero sin nombres, votos ni códigos.
    for raw in specialist_reasons or []:
        clean=public_reason(raw)
        if not clean or contains_generic_public_phrase(clean):
            continue
        # Sólo prosa técnica: descartar explicación de arquitectura residual.
        low=clean.lower()
        if any(x in low for x in ('bloqueo principal','voto','veto','comité','trader','réplica')):
            continue
        _append_unique(out,clean)

    return out


def compose_professional_recommendation(
    action: str, *, symbol: str, symbol_name: str, timeframe_name: str,
    confidence: float = 0.0, levels: Dict[str,Any] | None = None,
    trend: Dict[str,Any] | None = None, momentum: Dict[str,Any] | None = None,
    volatility: Dict[str,Any] | None = None, volume: Dict[str,Any] | None = None,
    structure: Dict[str,Any] | None = None, correlation: Dict[str,Any] | None = None,
    market_hours: Dict[str,Any] | None = None, confirmation: Dict[str,Any] | None = None,
    sentiment: Dict[str,Any] | None = None, liquidation: Dict[str,Any] | None = None,
    specialist_reasons: Iterable[Any] | None = None, timestamp_text: str = '', max_evidence: int = 6,
) -> str:
    """Professional public narrative: rich technical thesis, no internal roles/codes."""
    action=_u(action) or 'NO_OPERAR'
    if action in {'PRECAUCION','PRECAUCIÓN'}: action='CAUTION'
    levels=levels or {}; trend=trend or {}; momentum=momentum or {}; volatility=volatility or {}; volume=volume or {}; structure=structure or {}; correlation=correlation or {}; market_hours=market_hours or {}; confirmation=confirmation or {}; sentiment=sentiment or {}; liquidation=liquidation or {}

    label_map={'LONG':'📈 LONG','SHORT':'📉 SHORT','ESPERAR':'⏳ ESPERAR','NO_OPERAR':'⏸️ NO OPERAR','CAUTION':'⚠️ PRECAUCIÓN'}
    if action in {'COMPRA_SPOT','VENTA_SPOT'}:
        label=('🟢 ' if action=='COMPRA_SPOT' else '🔴 ') + exact_spot_instruction(action,symbol)
    else:
        label=label_map.get(action,action)
    header=f"{label} · {symbol_name} en {timeframe_name}."

    evidence=_technical_evidence(action,trend,momentum,volatility,volume,structure,confirmation,market_hours,liquidation,specialist_reasons)
    # Prioridad según la decisión. En ESPERAR/NO OPERAR/PRECAUCIÓN la causa
    # concreta de espera/bloqueo debe sobrevivir al límite de longitud; nunca
    # puede ser desplazada por una lista de indicadores menos decisivos.
    def _score(sentence: str) -> int:
        low=sentence.lower()
        score=50
        if action in {'ESPERAR','NO_OPERAR','CAUTION'}:
            if any(x in low for x in ('confirm', 'requiere', 'todavía', 'ruptura', 'retest')): score += 45
            if any(x in low for x in ('soporte', 'resistencia', 'order block', 'fvg', 'barrido', 'liquidez')): score += 35
            if 'adx' in low or 'dmi' in low: score += 32
            if 'volumen' in low: score += 28
            if any(x in low for x in ('rsi', 'macd', 'momentum', 'divergencia')): score += 26
            if 'atr' in low or 'bollinger' in low: score += 22
        else:
            if any(x in low for x in ('order block', 'fvg', 'barrido', 'liquidez', 'soporte', 'resistencia', 'retest')): score += 45
            if 'adx' in low or 'dmi' in low: score += 36
            if any(x in low for x in ('divergencia', 'rsi', 'macd', 'momentum')): score += 34
            if 'volumen' in low: score += 32
            if 'ema' in low or 'supertrend' in low or 'ichimoku' in low: score += 28
            if 'atr' in low or 'bollinger' in low: score += 20
        # Motivos con números concretos son especialmente auditables.
        if re.search(r'\d', sentence): score += 6
        return score

    evidence=sorted(enumerate(evidence), key=lambda pair: (-_score(pair[1]), pair[0]))
    selected=[]
    for _,e in evidence:
        if len(selected)>=max(5,int(max_evidence or 7)): break
        low=e.lower()
        if any(len(set(low.split()) & set(x.lower().split())) > max(8,int(len(low.split())*.78)) for x in selected):
            continue
        selected.append(e)

    # Decision-specific conclusion. Never ambiguous for Spot.
    lvl_entry=_f(_pick(levels,'entry','entry_price'),0); sl=_f(_pick(levels,'stop_loss','sl'),0); tp=_f(_pick(levels,'take_profit','tp'),0); rr=_f(_pick(levels,'risk_reward','rr'),0)
    conclusion=''
    if action in {'LONG','SHORT'}:
        if lvl_entry>0 and sl>0 and tp>0:
            conclusion=f"Plan propuesto: {action} con entrada {lvl_entry:.4f}, Stop Loss {sl:.4f} y Take Profit {tp:.4f}" + (f", relación riesgo/beneficio aproximada 1:{rr:.2f}" if rr>0 else '') + "."
        else:
            conclusion=f"La decisión es {action}, pero sólo es ejecutable cuando Entry, Stop Loss y Take Profit queden definidos sobre la estructura observada."
    elif action in {'COMPRA_SPOT','VENTA_SPOT'}:
        instruction=exact_spot_instruction(action,symbol)
        conclusion=f"Acción propuesta: {instruction}. Esta es una operación Spot; no abre una posición Futures."
    elif action=='ESPERAR':
        conclusion="Decisión: ESPERAR. Existe una tesis potencial, pero el momento de entrada aún no está confirmado; se reevalúa tras cierre válido, retest defendido o alineación clara de estructura, momentum y volumen."
    elif action=='CAUTION':
        conclusion="Decisión: PRECAUCIÓN. La tesis existe, pero el riesgo actual deteriora la ubicación de entrada; sólo mejora si baja la volatilidad/ruido o aparece una confirmación que permita invalidar la operación con un Stop Loss técnico."
    else:
        conclusion="Decisión: NO OPERAR. En este momento no existe una combinación suficientemente coherente de dirección, estructura, participación y ubicación para justificar una entrada; se reevalúa cuando cambien esas condiciones técnicas."

    body=' '.join(selected+[conclusion]).strip()
    if not selected:
        body=conclusion
    ts=(f" {timestamp_text}" if timestamp_text else '')
    return " ".join((header+' '+body+ts).split())


def append_futures_microstructure_context(message: str, micro: Dict[str,Any] | None, action: str) -> str:
    """Append observed Futures order-flow context without giving it unvalidated authority."""
    if not isinstance(micro,dict) or not micro.get('available'):
        return str(message or '')
    metrics=micro.get('metrics') or {}
    if not isinstance(metrics,dict): return str(message or '')
    bits=[]
    imb=_f(metrics.get('orderbook_imbalance'),0)
    buy=_f(metrics.get('recent_buy_share'),0)
    oi=_f(metrics.get('oi_change_pct'),0)
    funding=_f(metrics.get('funding_rate'),0)
    spread=_f(metrics.get('spread_pct'),0)
    liq=str(metrics.get('liquidity_band') or '').strip()
    if abs(imb)>0.02:
        val=imb*100 if abs(imb)<=1.5 else imb
        bits.append(f"libro de órdenes {'inclinado a demanda' if val>0 else 'inclinado a oferta'} ({abs(val):.1f}%)")
    if buy>0:
        pct=buy*100 if buy<=1.5 else buy
        bits.append(f"compras en operaciones recientes {pct:.1f}%")
    if abs(oi)>0.05: bits.append(f"interés abierto Δ {oi:+.2f}%")
    if abs(funding)>1e-9:
        pct=funding*100 if abs(funding)<0.1 else funding
        bits.append(f"funding {pct:+.4f}%")
    if spread>0: bits.append(f"spread {spread:.4f}%")
    if liq: bits.append(f"liquidez {liq.lower()}")
    if not bits: return str(message or '')
    sentence=" Microestructura Futures observada: " + "; ".join(bits[:5]) + "."
    return (str(message or '').rstrip()+sentence).strip()


def build_public_decision_evidence(action: str, **kwargs: Any) -> List[str]:
    """Compatibility API used by legacy fallbacks; now uses the same rich evidence engine."""
    return _technical_evidence(
        _u(action), kwargs.get('trend') or {}, kwargs.get('momentum') or {},
        kwargs.get('volatility') or {}, kwargs.get('volume') or {},
        kwargs.get('structure') or {}, kwargs.get('confirmation') or {},
        kwargs.get('market_hours') or {}, kwargs.get('liquidation') or {},
        kwargs.get('specialist_reasons') or [],
    )[:max(1,int(kwargs.get('limit',6) or 6))]


def join_public_decision_evidence(*args: Any, **kwargs: Any) -> str:
    return " ".join(build_public_decision_evidence(*args, **kwargs))
