"""
pdf_report.py
==============
Generador de reporte PDF profesional de análisis para el botón
"Descargar Análisis" del dashboard.

Estructura del PDF:
  - Cabecera con símbolo, timeframe, acción, confianza, fecha
  - Tabla resumen de niveles (Entry, SL, TP, R/R, Leverage)
  - 3 párrafos generados usando el BANCO DE JUSTIFICACIONES:
      1. ACCIÓN A TOMAR EN CUENTA
      2. INDICADORES QUE RESPALDAN
      3. CONCLUSIÓN
  - ANEXO: 
      - Gráfico principal de velas con EMAs / S-R
      - Gráfico de indicadores que sustentan la señal

Requiere: reportlab, kaleido (para el gráfico), plotly.
"""

import io
import re
import logging
from typing import Optional, Dict, List

logger = logging.getLogger('PDF_REPORT')


# ============================================================================
# Helpers de texto
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


def _clean_message_for_pdf(msg: str) -> str:
    """
    Limpia el mensaje del banco de justificaciones para renderizar en PDF.
    - Elimina emojis conflictivos
    - Convierte saltos de línea en <br/>
    - Escapa caracteres XML problemáticos
    """
    if not msg:
        return ''
    
    # Escape básico
    msg = msg.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # ReportLab acepta un subconjunto de HTML: <b>, <i>, <br/>
    msg = msg.replace('\n\n', '<br/><br/>').replace('\n', '<br/>')
    # Truncar si es excesivamente largo (para no romper paginación)
    if len(msg) > 10000:
        msg = msg[:9500] + '...<br/><i>[justificación truncada]</i>'
    return msg


def _split_message_by_categories(msg: str) -> Dict[str, str]:
    """
    Divide el mensaje del banco de justificaciones en secciones lógicas
    para poblar los 3 párrafos. Las plantillas del banco están ordenadas
    por 'order': 1=acción, 2=tendencia, 3=momentum, ..., 98=recomendación,
    99=cierre. Aproximamos dividiendo por líneas.
    """
    if not msg:
        return {'accion': '', 'indicadores': '', 'conclusion': ''}
    
    lines = [l.strip() for l in msg.split('\n') if l.strip()]
    n = len(lines)
    if n == 0:
        return {'accion': '', 'indicadores': '', 'conclusion': ''}
    
    # Heurística: primer bloque = acción (1-2 líneas), medio = indicadores,
    # último 20% = recomendación/cierre/conclusión
    if n <= 3:
        return {'accion': '\n'.join(lines), 'indicadores': '', 'conclusion': ''}
    
    accion_end = min(2, n // 4)
    conclusion_start = max(accion_end + 1, int(n * 0.75))
    
    return {
        'accion': '\n'.join(lines[:accion_end]),
        'indicadores': '\n'.join(lines[accion_end:conclusion_start]),
        'conclusion': '\n'.join(lines[conclusion_start:])
    }


# ============================================================================
# Construcción de los 3 párrafos (usando banco de justificaciones + resúmenes)
# ============================================================================
def _build_paragraph_action(analysis: Dict, msg_sections: Dict[str, str]) -> str:
    """
    Párrafo 1: Acción a tomar en cuenta.
    Combina: título del banco + niveles + resumen humano.
    """
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
    tp_source = levels.get('tp_source', '')
    sl_source = levels.get('sl_source', '')
    
    action_desc = _describe_action(action)
    parts = []
    
    # Frase del banco (si existe)
    banco_accion = _clean_message_for_pdf(msg_sections.get('accion', ''))
    if banco_accion:
        parts.append(banco_accion)
        parts.append('<br/><br/>')
    
    parts.append(
        f"El sistema experto recomienda <b>{action_desc.upper()}</b> para "
        f"<b>{symbol}</b> en temporalidad <b>{tf}</b> con un nivel de confianza del "
        f"<b>{conf:.0f}%</b>. "
    )
    
    if action in ('COMPRA_SPOT', 'VENTA_SPOT', 'LONG', 'SHORT') and entry > 0:
        parts.append(
            f"El nivel óptimo de entrada se sitúa en <b>{entry:.4f}</b> "
            f"(retroceso técnico respecto al cierre de la vela anterior). "
            f"El stop-loss de protección se coloca en <b>{sl:.4f}</b>"
        )
        if sl_source:
            parts.append(f" (fuente: {sl_source})")
        parts.append(
            f" y el objetivo de take-profit en <b>{tp:.4f}</b>"
        )
        if tp_source:
            parts.append(f" (fuente: {tp_source})")
        parts.append('. ')
        if rr:
            parts.append(
                f"La relación riesgo/recompensa es de <b>1:{rr:.2f}</b>, "
                f"considerada {'favorable' if rr >= 1.5 else 'ajustada'} para esta operación. "
            )
        if lev and lev > 1:
            parts.append(f"El apalancamiento sugerido es <b>x{lev}</b>. ")
    else:
        parts.append(
            "En este momento no se cumplen las condiciones necesarias para tomar una posición "
            "direccional. Se recomienda mantener disciplina y esperar una configuración más clara."
        )
    
    return ''.join(parts)


def _build_paragraph_indicators(analysis: Dict, msg_sections: Dict[str, str]) -> str:
    """
    Párrafo 2: Indicadores que respaldan la señal.
    Prioriza el contenido del banco de justificaciones (que ya incorpora
    los indicadores relevantes) + resumen numérico compacto.
    """
    parts = []
    
    # Contenido del banco (indicadores/estructura/volatilidad/etc.)
    banco_ind = _clean_message_for_pdf(msg_sections.get('indicadores', ''))
    if banco_ind:
        parts.append(banco_ind)
        parts.append('<br/><br/>')
    
    # Resumen numérico compacto (complementa el banco)
    trend = analysis.get('trend', {}) or {}
    momentum = analysis.get('momentum', {}) or {}
    volatility = analysis.get('volatility', {}) or {}
    volume = analysis.get('volume', {}) or {}
    
    indicators = momentum.get('indicators', {}) or {}
    resumen = (
        "<b>Resumen técnico numérico:</b> "
        f"Tendencia {trend.get('direction', 'neutral').upper()} "
        f"(ADX={trend.get('adx', 0) or 0:.1f}), "
        f"RSI={indicators.get('rsi', 0) or 0:.1f}, "
        f"RSI-Maverick={indicators.get('rsi_maverick', 0) or 0:.2f}, "
        f"ATR={volatility.get('atr_pct', 0) or 0:.2f}%, "
        f"volumen ratio={volume.get('volume_ratio', 1) or 1:.2f}x."
    )
    parts.append(resumen)
    
    # Divergencias si existen
    divs = momentum.get('divergences', []) or []
    if divs:
        parts.append(f" Divergencias detectadas: <i>{', '.join(divs[:3])}</i>.")
    
    # Ballenas
    if volume.get('whale_buy'):
        parts.append(" Se observa <b>presencia compradora institucional</b>.")
    elif volume.get('whale_sell'):
        parts.append(" Se observa <b>presencia vendedora institucional</b>.")
    
    return ''.join(parts)


def _build_paragraph_conclusion(analysis: Dict, msg_sections: Dict[str, str]) -> str:
    """Párrafo 3: Conclusión (usando cierre del banco + evaluación de convicción)."""
    decision = analysis.get('decision', {}) or {}
    action = decision.get('action', 'NO_OPERAR')
    conf = _cap_conf(decision.get('confidence'))
    estrategias = decision.get('estrategias', []) or []
    
    parts = []
    
    # Frase del banco (cierre/recomendación)
    banco_conc = _clean_message_for_pdf(msg_sections.get('conclusion', ''))
    if banco_conc:
        parts.append(banco_conc)
        parts.append('<br/><br/>')
    
    # Evaluación de convicción
    if conf >= 80:
        parts.append(
            f"<b>Convicción ALTA</b> ({conf:.0f}%): múltiples factores técnicos alineados "
            f"a favor de la acción propuesta. "
        )
    elif conf >= 65:
        parts.append(
            f"<b>Convicción MODERADA-ALTA</b> ({conf:.0f}%): el escenario es favorable "
            f"pero requiere confirmación de precio en el nivel de entrada. "
        )
    elif conf >= 50:
        parts.append(
            f"<b>Convicción MEDIA</b> ({conf:.0f}%): existe una configuración interesante "
            f"pero conviene manejar tamaños de posición conservadores. "
        )
    else:
        parts.append(
            f"<b>Convicción BAJA</b> ({conf:.0f}%): no se recomienda tomar acción hasta "
            f"que las condiciones técnicas mejoren. "
        )
    
    if estrategias:
        parts.append(
            f"Estrategias clave detectadas por los traders: "
            f"<i>{', '.join(estrategias[:5])}</i>. "
        )
    
    # Traders del comité
    registro = decision.get('registro_votacion', {}) or {}
    ganadores = []
    if isinstance(registro, dict):
        for v in registro.get('todos_los_votos', []) or []:
            if isinstance(v, dict) and v.get('accion') == action:
                nombre = v.get('trader', '')
                if nombre:
                    ganadores.append(nombre)
    if ganadores:
        parts.append(
            f"<br/><br/>El comité de {len(ganadores)} traders que respaldan esta decisión: "
            f"<i>{', '.join(ganadores[:6])}</i>."
        )
    
    parts.append(
        "<br/><br/><i>Aviso: este análisis es informativo y no constituye asesoría "
        "financiera. Toda operación implica riesgo; use únicamente capital que pueda permitirse "
        "perder y respete los niveles de stop-loss.</i>"
    )
    
    return ''.join(parts)


# ============================================================================
# Función principal — genera el PDF completo
# ============================================================================
def generate_analysis_pdf(analysis: Dict,
                          chart_image_bytes: Optional[bytes] = None,
                          indicators_image_bytes: Optional[bytes] = None,
                          supporting_indicator_charts: Optional[List[Dict]] = None) -> bytes:
    """
    Genera el PDF de análisis.
    
    Estructura:
      - Cabecera
      - Tabla resumen niveles
      - 3 párrafos (usando banco de justificaciones)
      - ANEXO A: gráfico principal (velas + EMAs + estructura)
      - ANEXO B: gráficos individuales de cada indicador que respalda la señal
    
    analysis: dict retornado por analyze_full_market
    chart_image_bytes: PNG del gráfico completo (velas + indicadores + patrón)
    indicators_image_bytes: PNG opcional específico de indicadores (LEGACY, se mantiene)
    supporting_indicator_charts: lista [{'name': str, 'image': bytes}] con
        gráficos individuales de indicadores que respaldan la señal.
        Cada elemento genera una entrada en la sección anexa.
    
    Retorna: bytes del PDF listo para servir con Content-Type: application/pdf
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak
    )
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title='Análisis Crypto Trader'
    )
    
    styles = getSampleStyleSheet()
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
        spaceBefore=14, spaceAfter=8
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
    
    story.append(Paragraph("Análisis Técnico Profesional", style_title))
    story.append(Paragraph(
        f"<b>{symbol}</b> · Temporalidad <b>{timeframe}</b> · Emitido {now_str}",
        style_subtitle
    ))
    
    # ============ TABLA RESUMEN ============
    levels = analysis.get('levels', {}) or {}
    current_price = analysis.get('current_price', 0) or 0
    
    action_color = HexColor('#666666')
    if action in ('COMPRA_SPOT', 'LONG'):
        action_color = HexColor('#0a8f4c')
    elif action in ('VENTA_SPOT', 'SHORT'):
        action_color = HexColor('#c92a2a')
    
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
        ('TEXTCOLOR', (1, 0), (1, 0), action_color),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
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
    story.append(Spacer(1, 0.5 * cm))
    
    # ============ 3 PÁRRAFOS (con banco de justificaciones) ============
    msg = analysis.get('message', '') or ''
    msg_sections = _split_message_by_categories(msg)
    
    story.append(Paragraph("1. Acción a tomar en cuenta", style_h2))
    story.append(Paragraph(_build_paragraph_action(analysis, msg_sections), style_body))
    
    story.append(Paragraph("2. Indicadores que respaldan la señal", style_h2))
    story.append(Paragraph(_build_paragraph_indicators(analysis, msg_sections), style_body))
    
    story.append(Paragraph("3. Conclusión", style_h2))
    story.append(Paragraph(_build_paragraph_conclusion(analysis, msg_sections), style_body))
    
    # ============ ANEXO A: GRÁFICO PRINCIPAL (velas + EMAs + estructura) ============
    if chart_image_bytes:
        story.append(PageBreak())
        story.append(Paragraph("Anexo A — Gráfico principal", style_title))
        story.append(Paragraph(
            f"Velas, EMAs, soportes/resistencias e indicadores clave · <b>{symbol}</b> · <b>{timeframe}</b>",
            style_subtitle
        ))
        try:
            img_buf = io.BytesIO(chart_image_bytes)
            img = Image(img_buf, width=17 * cm, height=18 * cm, kind='proportional')
            story.append(img)
        except Exception as e:
            logger.warning(f"No se pudo embeber gráfico principal: {e}")
    
    # ============ ANEXO B: GRÁFICOS INDIVIDUALES DE INDICADORES DE RESPALDO ============
    # Un gráfico por indicador que sustenta la señal (RSI, MACD, EMAs, Bollinger, etc.)
    # cada uno con su propio subplot dedicado y nombre visible.
    if supporting_indicator_charts:
        story.append(PageBreak())
        story.append(Paragraph("Anexo B — Indicadores que respaldan la señal", style_title))
        action = decision.get('action', '?')
        story.append(Paragraph(
            f"Cada gráfico muestra un indicador del sistema que votó a favor de <b>{action}</b> · "
            f"<b>{symbol}</b> · <b>{timeframe}</b>",
            style_subtitle
        ))
        
        for idx, chart in enumerate(supporting_indicator_charts):
            try:
                if not chart or not chart.get('image'):
                    continue
                story.append(Paragraph(
                    f"{idx + 1}. {chart.get('name', 'Indicador')}",
                    style_h2
                ))
                img_buf = io.BytesIO(chart['image'])
                img = Image(img_buf, width=17 * cm, height=5.5 * cm, kind='proportional')
                story.append(img)
                story.append(Spacer(1, 0.2 * cm))
            except Exception as e:
                logger.warning(f"No se pudo embeber gráfico de {chart.get('name')}: {e}")
    
    # LEGACY: gráfico único de indicadores (por compatibilidad si aún se pasa)
    elif indicators_image_bytes:
        try:
            story.append(PageBreak())
            story.append(Paragraph("Anexo B — Indicadores que respaldan la señal", style_title))
            img_buf2 = io.BytesIO(indicators_image_bytes)
            img2 = Image(img_buf2, width=17 * cm, height=17 * cm, kind='proportional')
            story.append(img2)
        except Exception as e:
            logger.warning(f"No se pudo embeber gráfico de indicadores: {e}")
    
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
