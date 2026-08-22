"""
pdf_report.py
==============
Generador de reporte PDF profesional de análisis para el botón
"Descargar Análisis" del dashboard.

Estructura del PDF:
  - Cabecera con símbolo, timeframe, acción, confianza, fecha
  - Tabla resumen de niveles (Entry, SL, TP, R/R, Leverage)
  - 3 párrafos generados automáticamente:
      1. ACCIÓN A TOMAR EN CUENTA
      2. INDICADORES QUE RESPALDAN
      3. CONCLUSIÓN
  - Gráfico del análisis con velas + indicadores top

Requiere: reportlab, kaleido (para el gráfico), plotly.
"""

import io
import logging
from typing import Optional, Dict, List

logger = logging.getLogger('PDF_REPORT')


# ============================================================================
# Helpers de texto — construcción de los 3 párrafos
# ============================================================================
def _cap_conf(v):
    try:
        return max(0.0, min(100.0, float(v or 0)))
    except Exception:
        return 0.0


def _describe_action(action: str) -> str:
    """Traduce la acción a lenguaje humano."""
    return {
        'COMPRA_SPOT': 'compra en spot',
        'VENTA_SPOT': 'venta en spot',
        'LONG': 'apertura de posición LONG (futuros)',
        'SHORT': 'apertura de posición SHORT (futuros)',
        'NO_OPERAR': 'no operar en este momento',
        'ESPERAR': 'esperar mejor confirmación',
        'PRECAUCION': 'operar con precaución',
        'CAUTION': 'operar con precaución',
    }.get(action, action.lower() if action else 'sin decisión')


def _build_paragraph_action(analysis: Dict) -> str:
    """Párrafo 1: Acción a tomar en cuenta."""
    decision = analysis.get('decision', {}) or {}
    levels = analysis.get('levels', {}) or {}
    symbol = analysis.get('symbol', '?')
    tf = analysis.get('timeframe', '?')
    action = decision.get('action', 'NO_OPERAR')
    conf = _cap_conf(decision.get('confidence'))
    entry = levels.get('entry', 0) or 0
    sl = levels.get('stop_loss', 0) or 0
    tp = levels.get('take_profit', 0) or 0
    rr = levels.get('risk_reward', 0) or 0
    lev = levels.get('leverage', 1) or 1
    
    action_desc = _describe_action(action)
    
    parts = [
        f"El sistema experto recomienda <b>{action_desc.upper()}</b> para {symbol} en temporalidad {tf} "
        f"con un nivel de confianza del <b>{conf:.0f}%</b>."
    ]
    
    if action in ('COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT') and entry > 0:
        parts.append(
            f"El nivel óptimo de entrada se sitúa en <b>{entry:.4f}</b>, "
            f"con stop-loss de protección en <b>{sl:.4f}</b> y objetivo de take-profit en <b>{tp:.4f}</b>."
        )
        if rr:
            parts.append(f"La relación riesgo/recompensa es de <b>1:{rr:.2f}</b>, "
                        f"considerada {'favorable' if rr >= 1.5 else 'ajustada'} para esta operación.")
        if lev and lev > 1:
            parts.append(f"El apalancamiento sugerido es <b>x{lev}</b>, calibrado para el perfil de volatilidad actual.")
    else:
        parts.append(
            "En este momento no se cumplen las condiciones necesarias para tomar una posición direccional. "
            "Se recomienda mantener disciplina y esperar una configuración más clara antes de exponer capital."
        )
    
    # Contexto de mercado
    session = (analysis.get('market_hours', {}) or {}).get('session', '')
    if session:
        parts.append(f"El análisis se ejecuta durante la sesión de mercado <i>{session}</i>.")
    
    return ' '.join(parts)


def _build_paragraph_indicators(analysis: Dict) -> str:
    """Párrafo 2: Indicadores que respaldan la señal."""
    trend = analysis.get('trend', {}) or {}
    momentum = analysis.get('momentum', {}) or {}
    volatility = analysis.get('volatility', {}) or {}
    volume = analysis.get('volume', {}) or {}
    structure = analysis.get('structure', {}) or {}
    
    parts = ["El análisis técnico se sustenta en múltiples indicadores convergentes."]
    
    # Tendencia
    direction = trend.get('direction', 'neutral')
    strength = trend.get('strength', '')
    adx = trend.get('adx', 0) or 0
    parts.append(
        f"En cuanto a la <b>tendencia</b>, la dirección es <b>{direction.upper()}</b> "
        f"con fuerza {strength} (ADX={adx:.1f})."
    )
    
    # Momentum
    indicators = momentum.get('indicators', {}) or {}
    rsi = indicators.get('rsi', 0) or 0
    rsi_maverick = indicators.get('rsi_maverick', 0) or 0
    momentum_dir = momentum.get('direction', 'neutral')
    parts.append(
        f"El <b>momentum</b> se orienta {momentum_dir.upper()}, con RSI en {rsi:.1f} "
        f"y RSI-Maverick en {rsi_maverick:.2f}."
    )
    divergences = momentum.get('divergences', []) or []
    if divergences:
        parts.append(f"Se han detectado divergencias en: {', '.join(divergences[:3])}.")
    
    # Volatilidad
    atr_pct = volatility.get('atr_pct', 0) or 0
    vol_level = volatility.get('volatility_level', '')
    ftm_zone = volatility.get('ftm_zone', '')
    parts.append(
        f"La <b>volatilidad</b> se ubica en nivel {vol_level} (ATR={atr_pct:.2f}%), "
        f"con FTMaverick indicando zona <b>{ftm_zone}</b>."
    )
    
    # Volumen
    vol_ratio = volume.get('volume_ratio', 1) or 1
    if volume.get('whale_buy'):
        parts.append(f"Se observa <b>presencia compradora institucional</b> "
                     f"(ratio volumen {vol_ratio:.2f}x).")
    elif volume.get('whale_sell'):
        parts.append(f"Se observa <b>presencia vendedora institucional</b> "
                     f"(ratio volumen {vol_ratio:.2f}x).")
    else:
        parts.append(f"El volumen se mantiene {'elevado' if vol_ratio > 1.5 else 'normal'} "
                     f"(ratio {vol_ratio:.2f}x).")
    
    # Estructura
    patterns = (structure.get('patterns') or {}).get('count', 0) or 0
    if patterns > 0:
        parts.append(f"Se identifican <b>{patterns} patrones</b> de precio relevantes en la estructura actual.")
    
    return ' '.join(parts)


def _build_paragraph_conclusion(analysis: Dict) -> str:
    """Párrafo 3: Conclusión."""
    decision = analysis.get('decision', {}) or {}
    action = decision.get('action', 'NO_OPERAR')
    conf = _cap_conf(decision.get('confidence'))
    
    # Estrategias
    estrategias = decision.get('estrategias', []) or []
    
    # Traders que votaron por la acción ganadora
    registro = decision.get('registro_votacion', {}) or {}
    ganadores = []
    if isinstance(registro, dict):
        votos = registro.get('todos_los_votos', []) or []
        for v in votos:
            if isinstance(v, dict) and v.get('accion') == action:
                nombre = v.get('trader', '')
                if nombre:
                    ganadores.append(nombre)
    
    parts = []
    
    if conf >= 80:
        parts.append(
            f"En conclusión, la señal presenta una <b>alta convicción</b> ({conf:.0f}%) "
            f"con múltiples factores técnicos alineados a favor de la acción propuesta."
        )
    elif conf >= 65:
        parts.append(
            f"En conclusión, la señal muestra una <b>convicción moderada-alta</b> ({conf:.0f}%). "
            f"El escenario es favorable pero requiere confirmación de precio en el nivel de entrada."
        )
    elif conf >= 50:
        parts.append(
            f"En conclusión, la señal tiene <b>convicción media</b> ({conf:.0f}%). "
            f"Existe una configuración interesante pero conviene manejar tamaños de posición conservadores."
        )
    else:
        parts.append(
            f"En conclusión, la <b>convicción es baja</b> ({conf:.0f}%). "
            f"No se recomienda tomar acción hasta que las condiciones técnicas mejoren."
        )
    
    if estrategias:
        parts.append(
            f"Las estrategias clave detectadas son: <i>{', '.join(estrategias[:5])}</i>."
        )
    
    if ganadores:
        parts.append(
            f"Los {len(ganadores)} traders del comité que respaldan esta decisión son: "
            f"<i>{', '.join(ganadores[:5])}</i>."
        )
    
    # Advertencia de riesgo
    parts.append(
        "<i>Recordatorio: toda operación implica riesgo. Use únicamente capital que pueda permitirse "
        "perder y respete siempre los niveles de stop-loss establecidos.</i>"
    )
    
    return ' '.join(parts)


# ============================================================================
# Función principal — genera el PDF completo
# ============================================================================
def generate_analysis_pdf(analysis: Dict, chart_image_bytes: Optional[bytes] = None) -> bytes:
    """
    Genera el PDF de análisis con 3 párrafos + gráfico.
    
    analysis: dict retornado por analyze_full_market
    chart_image_bytes: PNG del gráfico (opcional, se puede pasar externamente)
    
    Retorna: bytes del PDF listo para servir con Content-Type: application/pdf
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, KeepTogether
    )
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title='Análisis Crypto Trader'
    )
    
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    style_title = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=18, textColor=HexColor('#1a1a2e'),
        alignment=TA_CENTER, spaceAfter=12
    )
    style_subtitle = ParagraphStyle(
        'CustomSubtitle', parent=styles['Normal'],
        fontSize=11, textColor=HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=18
    )
    style_h2 = ParagraphStyle(
        'CustomH2', parent=styles['Heading2'],
        fontSize=13, textColor=HexColor('#1a1a2e'),
        spaceBefore=14, spaceAfter=8,
        leftIndent=0, borderPadding=0
    )
    style_body = ParagraphStyle(
        'CustomBody', parent=styles['Normal'],
        fontSize=10.5, leading=15,
        alignment=TA_JUSTIFY, spaceAfter=10,
        textColor=HexColor('#222222')
    )
    style_meta = ParagraphStyle(
        'Meta', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#888888'),
        alignment=TA_CENTER, spaceAfter=6
    )
    
    story = []
    
    # ============ CABECERA ============
    symbol = analysis.get('symbol', '?')
    timeframe = analysis.get('timeframe', '?')
    decision = analysis.get('decision', {}) or {}
    action = decision.get('action', 'NO_OPERAR')
    conf = _cap_conf(decision.get('confidence'))
    
    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    story.append(Paragraph(f"Análisis Técnico Profesional", style_title))
    story.append(Paragraph(
        f"<b>{symbol}</b> · Temporalidad <b>{timeframe}</b> · Emitido {now_str}",
        style_subtitle
    ))
    
    # ============ TABLA RESUMEN ============
    levels = analysis.get('levels', {}) or {}
    current_price = analysis.get('current_price', 0) or 0
    
    # Color de la acción
    action_color = HexColor('#666666')
    if action in ('COMPRA_SPOT', 'LONG'):
        action_color = HexColor('#0a8f4c')  # verde
    elif action in ('VENTA_SPOT', 'SHORT'):
        action_color = HexColor('#c92a2a')  # rojo
    
    table_data = [
        ['Recomendación', action, 'Confianza', f'{conf:.0f}%'],
        ['Precio Actual', f'{current_price:.4f}', 'Entry', f"{levels.get('entry', 0) or 0:.4f}"],
        ['Stop Loss', f"{levels.get('stop_loss', 0) or 0:.4f}", 'Take Profit', f"{levels.get('take_profit', 0) or 0:.4f}"],
        ['Risk/Reward', f"1:{levels.get('risk_reward', 0) or 0:.2f}", 'Apalancamiento', f"x{levels.get('leverage', 1) or 1}"],
    ]
    
    table = Table(table_data, colWidths=[3.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f4f6fa')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#e0e4ec')),
        ('BACKGROUND', (2, 0), (2, -1), HexColor('#e0e4ec')),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('TEXTCOLOR', (1, 0), (1, 0), action_color),   # acción en color
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),  # acción en bold
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#c8ccd6')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.6 * cm))
    
    # ============ 3 PÁRRAFOS ============
    story.append(Paragraph("1. Acción a tomar en cuenta", style_h2))
    story.append(Paragraph(_build_paragraph_action(analysis), style_body))
    
    story.append(Paragraph("2. Indicadores que respaldan la señal", style_h2))
    story.append(Paragraph(_build_paragraph_indicators(analysis), style_body))
    
    story.append(Paragraph("3. Conclusión", style_h2))
    story.append(Paragraph(_build_paragraph_conclusion(analysis), style_body))
    
    # ============ GRÁFICO ============
    if chart_image_bytes:
        try:
            story.append(Spacer(1, 0.4 * cm))
            story.append(Paragraph("Gráfico técnico de indicadores", style_h2))
            img_buf = io.BytesIO(chart_image_bytes)
            img = Image(img_buf, width=17 * cm, height=13 * cm, kind='proportional')
            story.append(img)
        except Exception as e:
            logger.warning(f"No se pudo embeber gráfico: {e}")
    
    # ============ FOOTER ============
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(
        "© Crypto Trader Analyst Pro — Sistema Experto de Trading. "
        "Este documento es informativo y no constituye asesoría financiera.",
        style_meta
    ))
    
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
