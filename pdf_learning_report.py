"""
pdf_learning_report.py
=======================
Genera un PDF que explica qué está aprendiendo el ReviewTrader:

  1. Métricas globales (cuántas señales registradas, evaluadas, pendientes)
  2. Aprendizaje INDIVIDUAL: top estrategias por (par, TF, acción)
  3. Aprendizaje GENERAL: top estrategias agregadas de todas las condiciones
  4. Recomendaciones activas cacheadas
  5. Última ejecución del ciclo run_full_review
  6. Notas sobre qué está aplicándose vs qué queda pendiente

Requiere: reportlab. Usa la conexión Supabase del ReviewTrader.
"""

import io
import logging
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger('LEARNING_REPORT')


def _fetch_learning_data() -> Dict:
    """
    Recupera todo el conocimiento actual del ReviewTrader desde Supabase.
    Retorna un dict con las secciones necesarias.
    """
    data = {
        'supabase_connected': False,
        'total_signals': 0,
        'evaluated_signals': 0,
        'pending_signals': 0,
        'tp_hit': 0,
        'sl_hit': 0,
        'expired': 0,
        'missed_opportunities': 0,
        'stats_specific': [],   # top por (par, tf, acción, estrategia)
        'stats_general': [],    # top por estrategia agregada
        'recommendations': [],  # recomendaciones activas
        'last_review_log': None,
        'error': None,
    }
    
    try:
        from review_trader import review_trader
        db = review_trader.db
    except Exception as e:
        data['error'] = f'ReviewTrader no disponible: {e}'
        return data
    
    if not db.enabled:
        data['error'] = 'Supabase no conectado (revisar SUPABASE_URL / SUPABASE_KEY)'
        return data
    
    data['supabase_connected'] = True
    
    # 1. Signals: totales por status
    try:
        r = db.client.table('signals').select('status', count='exact').execute()
        data['total_signals'] = len(r.data or [])
        for row in (r.data or []):
            st = (row.get('status') or 'pending').lower()
            if st == 'tp_hit':
                data['tp_hit'] += 1
            elif st == 'sl_hit':
                data['sl_hit'] += 1
            elif st == 'expired':
                data['expired'] += 1
            elif st == 'pending':
                data['pending_signals'] += 1
        data['evaluated_signals'] = data['tp_hit'] + data['sl_hit'] + data['expired']
    except Exception as e:
        logger.warning(f'Error contando signals: {e}')
    
    # 2. Missed opportunities
    try:
        r = db.client.table('missed_opportunities').select('id', count='exact').limit(1).execute()
        data['missed_opportunities'] = getattr(r, 'count', None) or len(r.data or [])
    except Exception:
        pass
    
    # 3. Stats específicas — top 20 por expectancy
    try:
        r = (db.client.table('strategy_stats_specific')
             .select('*')
             .order('expectancy', desc=True)
             .limit(20)
             .execute())
        data['stats_specific'] = r.data or []
    except Exception as e:
        logger.warning(f'Error leyendo stats_specific: {e}')
    
    # 4. Stats generales — top 20
    try:
        r = (db.client.table('strategy_stats_general')
             .select('*')
             .order('expectancy', desc=True)
             .limit(20)
             .execute())
        data['stats_general'] = r.data or []
    except Exception as e:
        logger.warning(f'Error leyendo stats_general: {e}')
    
    # 5. Recomendaciones activas — top 15 por sample_size
    try:
        r = (db.client.table('review_recommendations')
             .select('*')
             .order('sample_size', desc=True)
             .limit(15)
             .execute())
        data['recommendations'] = r.data or []
    except Exception as e:
        logger.warning(f'Error leyendo recommendations: {e}')
    
    # 6. Último ciclo de review
    try:
        r = (db.client.table('review_logs')
             .select('*')
             .order('created_at', desc=True)
             .limit(1)
             .execute())
        if r.data:
            data['last_review_log'] = r.data[0]
    except Exception:
        pass
    
    return data


def generate_learning_pdf() -> bytes:
    """
    Genera el PDF de aprendizaje del ReviewTrader.
    Retorna bytes PDF listos para servir con Content-Type: application/pdf.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    )
    
    data = _fetch_learning_data()
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title='Aprendizaje del Sistema'
    )
    
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'LTitle', parent=styles['Title'],
        fontSize=20, textColor=HexColor('#1a1a2e'),
        alignment=TA_CENTER, spaceAfter=10
    )
    style_subtitle = ParagraphStyle(
        'LSub', parent=styles['Normal'],
        fontSize=11, textColor=HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=18
    )
    style_h2 = ParagraphStyle(
        'LH2', parent=styles['Heading2'],
        fontSize=14, textColor=HexColor('#0a3d62'),
        spaceBefore=14, spaceAfter=8
    )
    style_body = ParagraphStyle(
        'LBody', parent=styles['Normal'],
        fontSize=10.5, leading=15,
        alignment=TA_JUSTIFY, spaceAfter=8,
        textColor=HexColor('#222222')
    )
    style_small = ParagraphStyle(
        'LSmall', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#555555')
    )
    style_meta = ParagraphStyle(
        'LMeta', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#888888'),
        alignment=TA_CENTER, spaceAfter=6
    )
    
    story = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # ============ CABECERA ============
    story.append(Paragraph("Aprendizaje del Sistema", style_title))
    story.append(Paragraph(
        f"Informe del ReviewTrader · generado {now_str}",
        style_subtitle
    ))
    
    # ============ ESTADO DE CONEXIÓN ============
    if not data['supabase_connected']:
        story.append(Paragraph("Estado del sistema", style_h2))
        story.append(Paragraph(
            f"<b>Supabase no está conectado.</b> El ReviewTrader no puede acumular "
            f"aprendizaje sin la base de datos. Detalle: <i>{data.get('error', 'desconocido')}</i>",
            style_body
        ))
        doc.build(story)
        result = buf.getvalue()
        buf.close()
        return result
    
    # ============ QUÉ APRENDE EL SISTEMA ============
    story.append(Paragraph("¿Qué está aprendiendo el sistema?", style_h2))
    story.append(Paragraph(
        "El ReviewTrader observa cada señal generada por los 9 traders y registra el "
        "resultado real cuando el precio alcanza el take-profit, el stop-loss o expira "
        "sin llegar a ninguno. A partir de estos resultados aprende:"
        "<br/><br/>"
        "<b>1. Aprendizaje INDIVIDUAL (por par, temporalidad, acción y estrategia).</b> "
        "Ejemplo: '¿La estrategia ORDER_BLOCK_ALCISTA funciona en BTC-USDT 1h para LONG?'. "
        "Se calcula win rate específico, expectancy, y si la estrategia está degradándose "
        "(últimas 20 señales vs histórico). Requiere mínimo <b>20 muestras</b> para publicar."
        "<br/><br/>"
        "<b>2. Aprendizaje GENERAL (por estrategia agregando todos los pares y TFs).</b> "
        "Ejemplo: '¿RSI-Maverick funciona bien globalmente?'. Además guarda los mejores "
        "pares y timeframes en los que dicha estrategia rinde. Requiere mínimo <b>50 muestras</b>."
        "<br/><br/>"
        "<b>3. Recomendaciones cacheadas.</b> Combinación de lo aprendido en un formato "
        "listo para consulta: top estrategias ganadoras/perdedoras por (par, TF, acción), "
        "multiplicador de confianza sugerido (0.5x–1.5x) y leverage recomendado.",
        style_body
    ))
    
    # ============ CÓMO INFLUYE EN DECISIONES ============
    story.append(Paragraph("¿Cómo influye el aprendizaje en las decisiones?", style_h2))
    story.append(Paragraph(
        "El ReviewTrader es el <b>10º trader del comité</b> del Moderador. En cada análisis, "
        "consulta las recomendaciones específicas para el (par, TF, acción) y emite un voto: "
        "COMPRA/VENTA/NO_OPERAR con una confianza entre 40% y 95% basada en cuántas "
        "estrategias activas actuales coinciden con las históricamente ganadoras. Este voto "
        "se pondera con peso 1.0 en el consenso final."
        "<br/><br/>"
        "<b>Aplicación PENDIENTE:</b> el <i>multiplicador de confianza</i> calculado por "
        "estrategia (0.5x–1.5x) actualmente <b>se guarda y expone al frontend</b>, pero "
        "aún no ajusta directamente la confianza del consenso final. Ese ajuste requiere "
        "más muestras estables antes de introducirlo sin distorsionar decisiones.",
        style_body
    ))
    
    # ============ MÉTRICAS GLOBALES ============
    story.append(Paragraph("Métricas globales", style_h2))
    metrics_data = [
        ['Métrica', 'Valor'],
        ['Señales registradas totales', str(data['total_signals'])],
        ['Señales pendientes (aún abiertas)', str(data['pending_signals'])],
        ['Señales evaluadas (TP/SL/Expired)', str(data['evaluated_signals'])],
        ['   — Toques de Take Profit', str(data['tp_hit'])],
        ['   — Toques de Stop Loss', str(data['sl_hit'])],
        ['   — Expiradas sin toque', str(data['expired'])],
        ['Oportunidades perdidas detectadas', str(data['missed_opportunities'])],
    ]
    
    total_eval = max(1, data['evaluated_signals'])
    win_rate_global = data['tp_hit'] / total_eval * 100 if total_eval > 0 else 0
    metrics_data.append(['Win rate global (TP / evaluadas)', f'{win_rate_global:.1f}%'])
    
    if data.get('last_review_log'):
        try:
            log = data['last_review_log']
            last_run = log.get('created_at', 'desconocido')
            metrics_data.append(['Último ciclo run_full_review', str(last_run)[:19]])
        except Exception:
            pass
    
    tmetrics = Table(metrics_data, colWidths=[10 * cm, 5 * cm])
    tmetrics.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#0a3d62')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f4f6fa'), white]),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(tmetrics)
    
    # ============ APRENDIZAJE INDIVIDUAL ============
    story.append(Paragraph("Aprendizaje individual · top estrategias por par-TF-acción", style_h2))
    story.append(Paragraph(
        "Estas son las combinaciones específicas donde el ReviewTrader ha aprendido "
        "que ciertas estrategias funcionan mejor:",
        style_body
    ))
    
    if data['stats_specific']:
        stat_rows = [['Par', 'TF', 'Acción', 'Estrategia', 'Muestras', 'Win %', 'Expec.']]
        for row in data['stats_specific'][:15]:
            wr = row.get('win_rate', 0) or 0
            ex = row.get('expectancy', 0) or 0
            stat_rows.append([
                str(row.get('symbol', '')),
                str(row.get('timeframe', '')),
                str(row.get('action', '')),
                str(row.get('strategy', ''))[:22],
                str(row.get('total_signals', 0)),
                f'{wr:.1f}',
                f'{ex:.2f}',
            ])
        tstat = Table(stat_rows, colWidths=[2.5*cm, 1.5*cm, 2*cm, 4.5*cm, 2*cm, 1.5*cm, 1.8*cm])
        tstat.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ]))
        story.append(tstat)
    else:
        story.append(Paragraph(
            "<i>Aún no hay estadísticas específicas publicadas. Se requieren al menos "
            "20 muestras por combinación (par, TF, acción, estrategia) antes de aparecer aquí. "
            "El sistema empezará a mostrar datos conforme se acumulen resultados de operaciones.</i>",
            style_body
        ))
    
    story.append(PageBreak())
    
    # ============ APRENDIZAJE GENERAL ============
    story.append(Paragraph("Aprendizaje general · top estrategias agregadas", style_h2))
    story.append(Paragraph(
        "Estas son las estrategias con mejor rendimiento agregando todos los pares y "
        "temporalidades. Requieren al menos 50 muestras totales.",
        style_body
    ))
    
    if data['stats_general']:
        gen_rows = [['Estrategia', 'Muestras', 'Wins', 'Losses', 'Win %', 'Expectancy']]
        for row in data['stats_general'][:20]:
            wr = row.get('win_rate', 0) or 0
            ex = row.get('expectancy', 0) or 0
            gen_rows.append([
                str(row.get('strategy', ''))[:35],
                str(row.get('total_signals', 0)),
                str(row.get('wins', 0)),
                str(row.get('losses', 0)),
                f'{wr:.1f}%',
                f'{ex:.2f}',
            ])
        tgen = Table(gen_rows, colWidths=[6*cm, 2*cm, 1.8*cm, 2*cm, 1.8*cm, 2.4*cm])
        tgen.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]))
        story.append(tgen)
    else:
        story.append(Paragraph(
            "<i>Sin datos aún. Requiere ≥50 muestras por estrategia.</i>",
            style_body
        ))
    
    # ============ RECOMENDACIONES ACTIVAS ============
    story.append(Paragraph("Recomendaciones activas del sistema", style_h2))
    story.append(Paragraph(
        "Estas son las recomendaciones cacheadas que el ReviewTrader consulta al votar. "
        "Se actualizan diariamente por el ciclo <i>run_full_review</i> (20:00 hora Bolivia).",
        style_body
    ))
    
    if data['recommendations']:
        rec_rows = [['Par', 'TF', 'Acción', 'Muestras', 'Win %', 'Mult.', 'Leverage']]
        for row in data['recommendations'][:15]:
            wr = row.get('win_rate', 0) or 0
            mult = row.get('recommended_confidence_multiplier', 1.0) or 1.0
            lev = row.get('recommended_leverage', 1) or 1
            rec_rows.append([
                str(row.get('symbol', '')),
                str(row.get('timeframe', '')),
                str(row.get('action', '')),
                str(row.get('sample_size', 0)),
                f'{wr:.1f}%',
                f'{mult:.2f}x',
                f'x{lev}',
            ])
        trec = Table(rec_rows, colWidths=[2.5*cm, 1.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm])
        trec.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1a5490')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
        ]))
        story.append(trec)
    else:
        story.append(Paragraph(
            "<i>No hay recomendaciones activas. El ciclo diario aún no las ha generado.</i>",
            style_body
        ))
    
    # ============ NOTAS FINALES ============
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("Notas técnicas", style_h2))
    story.append(Paragraph(
        "<b>Umbrales estadísticos configurados:</b>"
        "<br/>• Muestras mínimas para publicar stats específicas: <b>20</b>"
        "<br/>• Muestras mínimas para stats generales: <b>50</b>"
        "<br/>• Umbral de estrategia ganadora: <b>win rate ≥ 60%</b>"
        "<br/>• Umbral de estrategia perdedora: <b>win rate ≤ 40%</b>"
        "<br/>• Degradación: se marca si el win rate de las últimas 20 señales cae ≥20% "
        "vs el histórico"
        "<br/><br/>"
        "<b>Frecuencia de aprendizaje:</b>"
        "<br/>• Registro de señales: cada análisis (inmediato)"
        "<br/>• Evaluación TP/SL/Expired: cada 5 minutos (worker background)"
        "<br/>• Recalculo de estadísticas y recomendaciones: 20:00 Bolivia (diario)"
        "<br/>• Detección de oportunidades perdidas: durante el ciclo diario",
        style_body
    ))
    
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(
        "© Crypto Trader Analyst Pro — Sistema Experto de Trading. "
        "El aprendizaje se acumula con cada operación evaluada; a más muestras, más precisión.",
        style_meta
    ))
    
    doc.build(story)
    result = buf.getvalue()
    buf.close()
    return result
