"""
pdf_learning_report.py
=======================
Genera un PDF que explica QUÉ está aprendiendo el ReviewTrader.

Estructura del informe:
  1. Métricas globales (registradas, evaluadas, TP/SL/expired, win rate)
  2. QUÉ HA APRENDIDO EL SISTEMA (resumen humano automático)
  3. Top 20 mejores estrategias generales (agregado por estrategia)
  4. Top 20 peores estrategias generales
  5. Top 15 mejores combinaciones específicas (par + TF + acción + estrategia)
  6. Top 15 peores combinaciones específicas
  7. Aprendizaje por PAR (win rate por símbolo)
  8. Aprendizaje por TIMEFRAME
  9. Oportunidades perdidas: indicadores que estaban activos
  10. Notas técnicas

CAMBIO IMPORTANTE: en lugar de leer solo las tablas strategy_stats_* (que
requieren ejecutar run_full_review y a veces fallan por timeout), este PDF
CALCULA las estadísticas EN EL MOMENTO desde la tabla `signals` de Supabase.
Así el aprendizaje siempre se ve, aunque las tablas cache estén vacías.

Requiere: reportlab, supabase-py.
"""

import io
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger('LEARNING_REPORT')

# ============================================================================
# Umbrales de confianza estadística (informativos, no bloquean visualización)
# ============================================================================
SPECIFIC_SAMPLES_RIGOROUS = 10   # con >=10 muestras el resultado es "válido"
SPECIFIC_SAMPLES_MIN = 3         # con <3 no lo mostramos (ruido puro)
GENERAL_SAMPLES_RIGOROUS = 25    # con >=25 muestras el resultado es "válido"
GENERAL_SAMPLES_MIN = 5


# ============================================================================
# HELPERS DE CÁLCULO DE STATS (funcionan directamente sobre signals de la BD)
# ============================================================================

def _fetch_all_signals_with_indicators(db, days_back: int = 90) -> List[Dict]:
    """Trae todas las señales resueltas con sus estrategias (paginación manual)."""
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
    all_data = []
    offset = 0
    page_size = 1000
    for _ in range(50):  # cap 50k
        try:
            r = (db.client.table('signals')
                 .select('id, symbol, timeframe, action_normalized, status, '
                         'confidence, entry_price, stop_loss, take_profit, leverage, '
                         'created_at, candle_timestamp, system_type, '
                         'signal_indicators(strategy_name)')
                 .neq('status', 'pending')
                 .gte('created_at', cutoff)
                 .order('created_at', desc=True)
                 .range(offset, offset + page_size - 1)
                 .execute())
            batch = r.data or []
            if not batch:
                break
            all_data.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as e:
            logger.warning(f'paginación falló offset={offset}: {e}')
            break
    return all_data


def _calc_stats_general(signals: List[Dict]) -> List[Dict]:
    """
    Calcula stats por ESTRATEGIA (agregado global).
    Devuelve lista ordenada por expectancy desc.
    Solo cuenta wins/losses (tp_hit/sl_hit) para win_rate estadístico.
    """
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0, 'missed_opps': 0,
        'by_symbol': defaultdict(lambda: {'wins': 0, 'losses': 0}),
        'by_timeframe': defaultdict(lambda: {'wins': 0, 'losses': 0}),
        'by_action': defaultdict(lambda: {'wins': 0, 'losses': 0}),
    })
    
    for sig in signals:
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        status = sig.get('status')
        symbol = sig.get('symbol')
        tf = sig.get('timeframe')
        action = sig.get('action_normalized')
        
        for strat in strategies:
            b = buckets[strat]
            if status == 'tp_hit':
                b['wins'] += 1
                b['by_symbol'][symbol]['wins'] += 1
                b['by_timeframe'][tf]['wins'] += 1
                if action:
                    b['by_action'][action]['wins'] += 1
            elif status == 'sl_hit':
                b['losses'] += 1
                b['by_symbol'][symbol]['losses'] += 1
                b['by_timeframe'][tf]['losses'] += 1
                if action:
                    b['by_action'][action]['losses'] += 1
            elif status == 'expired':
                b['expired'] += 1
            elif status == 'missed_opportunity':
                b['missed_opps'] += 1
    
    rows = []
    for strat, b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins'] / resolved * 100) if resolved > 0 else 0
        expectancy = (win_rate/100)*2 - (1 - win_rate/100)*1  # asume RR 2:1
        
        # Best/worst pairs & timeframes (min 3 muestras)
        def _rank(subs: Dict, top: bool):
            scored = []
            for k, v in subs.items():
                s = v['wins'] + v['losses']
                if s >= 3:
                    scored.append((k, v['wins']/s*100, s))
            return sorted(scored, key=lambda x: -x[1] if top else x[1])[:3]
        
        rows.append({
            'strategy': strat,
            'total': resolved + b['expired'],
            'wins': b['wins'],
            'losses': b['losses'],
            'expired': b['expired'],
            'missed': b['missed_opps'],
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 3),
            'sample_size': resolved,
            'best_symbols': _rank(b['by_symbol'], top=True),
            'worst_symbols': _rank(b['by_symbol'], top=False),
            'best_tfs': _rank(b['by_timeframe'], top=True),
            'worst_tfs': _rank(b['by_timeframe'], top=False),
        })
    return sorted(rows, key=lambda r: (-r['expectancy'], -r['sample_size']))


def _calc_stats_specific(signals: List[Dict]) -> List[Dict]:
    """
    Calcula stats por (symbol, timeframe, action, strategy).
    Ordenado por expectancy desc.
    """
    buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0})
    
    for sig in signals:
        symbol = sig.get('symbol')
        tf = sig.get('timeframe')
        action = sig.get('action_normalized')
        status = sig.get('status')
        if not (symbol and tf and action):
            continue
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        
        for strat in strategies:
            key = (symbol, tf, action, strat)
            if status == 'tp_hit':
                buckets[key]['wins'] += 1
            elif status == 'sl_hit':
                buckets[key]['losses'] += 1
            elif status == 'expired':
                buckets[key]['expired'] += 1
    
    rows = []
    for (sym, tf, action, strat), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0:
            continue
        win_rate = (b['wins'] / resolved) * 100
        expectancy = (win_rate/100)*2 - (1 - win_rate/100)*1
        rows.append({
            'symbol': sym, 'timeframe': tf, 'action': action, 'strategy': strat,
            'total': resolved + b['expired'], 'wins': b['wins'],
            'losses': b['losses'], 'expired': b['expired'],
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 3),
            'sample_size': resolved,
        })
    return sorted(rows, key=lambda r: (-r['expectancy'], -r['sample_size']))


def _calc_stats_by_symbol(signals: List[Dict]) -> List[Dict]:
    """Win rate agregado por par."""
    buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0, 'missed': 0})
    for sig in signals:
        sym = sig.get('symbol')
        if not sym:
            continue
        st = sig.get('status')
        b = buckets[sym]
        if st == 'tp_hit':
            b['wins'] += 1
        elif st == 'sl_hit':
            b['losses'] += 1
        elif st == 'expired':
            b['expired'] += 1
        elif st == 'missed_opportunity':
            b['missed'] += 1
    rows = []
    for sym, b in buckets.items():
        resolved = b['wins'] + b['losses']
        win_rate = (b['wins']/resolved*100) if resolved > 0 else 0
        rows.append({
            'symbol': sym, 'wins': b['wins'], 'losses': b['losses'],
            'expired': b['expired'], 'missed': b['missed'],
            'sample_size': resolved,
            'win_rate': round(win_rate, 1),
        })
    return sorted(rows, key=lambda r: -r['win_rate'])


def _calc_stats_by_timeframe(signals: List[Dict]) -> List[Dict]:
    """Win rate agregado por timeframe."""
    buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0})
    for sig in signals:
        tf = sig.get('timeframe')
        if not tf:
            continue
        st = sig.get('status')
        b = buckets[tf]
        if st == 'tp_hit':
            b['wins'] += 1
        elif st == 'sl_hit':
            b['losses'] += 1
        elif st == 'expired':
            b['expired'] += 1
    rows = []
    for tf, b in buckets.items():
        resolved = b['wins'] + b['losses']
        win_rate = (b['wins']/resolved*100) if resolved > 0 else 0
        rows.append({
            'timeframe': tf, 'wins': b['wins'], 'losses': b['losses'],
            'expired': b['expired'], 'sample_size': resolved,
            'win_rate': round(win_rate, 1),
        })
    # Ordenar por TF de menor a mayor (5m, 15m, 30m, 1h, 2h, 4h, 12h, 1D, 1W)
    tf_order = {'5m': 0, '15m': 1, '30m': 2, '1h': 3, '2h': 4, '4h': 5,
                '12h': 6, '1D': 7, '1W': 8}
    return sorted(rows, key=lambda r: tf_order.get(r['timeframe'], 99))


def _fetch_missed_opp_indicators(db, limit: int = 200) -> List[Dict]:
    """
    Trae oportunidades perdidas junto con los indicadores que estaban activos
    cuando el sistema NO tomó la operación. Ayuda a identificar patrones de
    'cuándo el sistema es demasiado conservador'.
    """
    try:
        r = (db.client.table('missed_opportunities')
             .select('symbol, timeframe, action_that_should_have_been, '
                     'pct_missed, active_strategies, created_at')
             .order('created_at', desc=True)
             .limit(limit)
             .execute())
        return r.data or []
    except Exception:
        return []


def _analyze_missed_opps(missed: List[Dict]) -> Dict:
    """
    De las oportunidades perdidas, agrupa por indicadores/estrategias activas
    para ver qué combinaciones aparecen con más frecuencia (candidatas a
    'próximas veces con este set, sí tomar la operación').
    """
    indicator_freq = defaultdict(lambda: {'count': 0, 'total_pct': 0.0})
    combination_freq = defaultdict(lambda: {'count': 0, 'total_pct': 0.0})
    by_pair = defaultdict(int)
    by_direction = defaultdict(int)
    
    for opp in missed:
        strats = opp.get('active_strategies') or []
        if not isinstance(strats, list):
            continue
        pct = float(opp.get('pct_missed', 0) or 0)
        
        # Frecuencia individual
        for s in strats:
            if not s:
                continue
            indicator_freq[s]['count'] += 1
            indicator_freq[s]['total_pct'] += pct
        
        # Combinaciones (pares de indicadores)
        if len(strats) >= 2:
            sorted_strats = sorted([s for s in strats if s])
            for i in range(len(sorted_strats)):
                for j in range(i+1, len(sorted_strats)):
                    combo = f"{sorted_strats[i]} + {sorted_strats[j]}"
                    combination_freq[combo]['count'] += 1
                    combination_freq[combo]['total_pct'] += pct
        
        pair = f"{opp.get('symbol','?')} {opp.get('timeframe','?')}"
        by_pair[pair] += 1
        by_direction[opp.get('action_that_should_have_been', '?')] += 1
    
    # Ordenar top
    top_indicators = sorted(
        [(k, v['count'], v['total_pct']/max(v['count'], 1)) for k, v in indicator_freq.items()],
        key=lambda x: -x[1]
    )[:15]
    top_combos = sorted(
        [(k, v['count'], v['total_pct']/max(v['count'], 1)) for k, v in combination_freq.items()],
        key=lambda x: -x[1]
    )[:10]
    top_pairs = sorted(by_pair.items(), key=lambda x: -x[1])[:8]
    
    return {
        'total': len(missed),
        'top_indicators': top_indicators,
        'top_combinations': top_combos,
        'top_pairs': top_pairs,
        'by_direction': dict(by_direction),
    }


def _build_human_summary(metrics: Dict, top_general: List[Dict],
                         worst_general: List[Dict],
                         by_symbol: List[Dict],
                         by_timeframe: List[Dict]) -> str:
    """Genera un resumen en lenguaje natural de lo que ha aprendido el sistema."""
    lines = []
    total_resolved = metrics['tp_hit'] + metrics['sl_hit']
    win_rate = (metrics['tp_hit'] / total_resolved * 100) if total_resolved > 0 else 0
    
    lines.append(
        f"El sistema ha registrado <b>{metrics['total_signals']}</b> señales en total. "
        f"De estas, <b>{total_resolved}</b> operaciones han sido resueltas (tocaron TP o SL), "
        f"con un win rate REAL de <b>{win_rate:.1f}%</b>. "
        f"Otras {metrics['expired']} señales expiraron sin toque, y "
        f"{metrics['missed_opp_from_signals']} fueron NO_OPERAR que se equivocaron "
        f"(el precio se movió >2% en la dirección esperada)."
    )
    
    if win_rate < 40:
        lines.append(
            f"<br/><br/>⚠️ El win rate actual ({win_rate:.1f}%) está por debajo del umbral "
            f"de rentabilidad (~40% con RR 1:1.5). Esto indica que los stops se están "
            f"tocando más de lo que se alcanzan los TP. Posibles causas: entries tardíos, "
            f"stops demasiado apretados para la volatilidad actual, o el mercado en modo "
            f"'choppy' (sin dirección clara)."
        )
    elif win_rate < 55:
        lines.append(
            f"<br/><br/>📊 El win rate ({win_rate:.1f}%) está en zona de subsistencia. "
            f"Con RR 1:2 este ratio permite ganancias moderadas, pero requiere disciplina "
            f"en el sizing."
        )
    else:
        lines.append(
            f"<br/><br/>✅ El win rate ({win_rate:.1f}%) es sólido. El sistema está "
            f"identificando setups con edge estadístico."
        )
    
    # Top estrategia con muestras suficientes
    top_valid = [s for s in top_general if s['sample_size'] >= GENERAL_SAMPLES_RIGOROUS]
    if top_valid:
        top = top_valid[0]
        lines.append(
            f"<br/><br/><b>Mejor estrategia aprendida hasta ahora</b>: "
            f"<i>{top['strategy']}</i> con {top['win_rate']}% de win rate "
            f"en {top['sample_size']} muestras evaluadas. "
        )
        if top['best_symbols']:
            best_sym = top['best_symbols'][0]
            lines.append(
                f"Rinde especialmente bien en <b>{best_sym[0]}</b> "
                f"({best_sym[1]:.0f}% win rate)."
            )
    else:
        lines.append(
            f"<br/><br/>Ninguna estrategia ha acumulado aún las {GENERAL_SAMPLES_RIGOROUS} "
            f"muestras necesarias para considerarla estadísticamente probada. "
            f"Se muestran igual las estrategias con >={GENERAL_SAMPLES_MIN} muestras como "
            f"referencia preliminar."
        )
    
    # Peor estrategia
    worst_valid = [s for s in worst_general if s['sample_size'] >= GENERAL_SAMPLES_RIGOROUS]
    if worst_valid:
        w = worst_valid[-1]  # último es el peor (menor expectancy)
        lines.append(
            f"<br/><br/><b>Estrategia con peor desempeño</b>: "
            f"<i>{w['strategy']}</i> con solo {w['win_rate']}% de win rate. "
            f"Con {w['sample_size']} muestras evaluadas, esta señal está debilitando "
            f"al comité y sería candidata a bajarle peso."
        )
    
    # Mejor par
    valid_symbols = [s for s in by_symbol if s['sample_size'] >= 5]
    if valid_symbols:
        best_pair = valid_symbols[0]
        worst_pair = valid_symbols[-1]
        lines.append(
            f"<br/><br/><b>Par con mejor rendimiento</b>: {best_pair['symbol']} "
            f"({best_pair['win_rate']}% win rate en {best_pair['sample_size']} operaciones). "
            f"<b>Par con peor rendimiento</b>: {worst_pair['symbol']} "
            f"({worst_pair['win_rate']}% win rate)."
        )
    
    # Mejor timeframe
    valid_tfs = [t for t in by_timeframe if t['sample_size'] >= 5]
    if valid_tfs:
        best_tf = max(valid_tfs, key=lambda t: t['win_rate'])
        worst_tf = min(valid_tfs, key=lambda t: t['win_rate'])
        lines.append(
            f"<br/><br/><b>Timeframe más efectivo</b>: {best_tf['timeframe']} "
            f"({best_tf['win_rate']}% win rate). "
            f"<b>Timeframe con más pérdidas</b>: {worst_tf['timeframe']} "
            f"({worst_tf['win_rate']}%)."
        )
    
    return ''.join(lines)


# ============================================================================
# FETCH DE MÉTRICAS GLOBALES (usando .count real)
# ============================================================================

def _fetch_learning_data() -> Dict:
    """Recupera todo el conocimiento actual del ReviewTrader desde Supabase."""
    data = {
        'supabase_connected': False,
        'total_signals': 0,
        'evaluated_signals': 0,
        'pending_signals': 0,
        'tp_hit': 0,
        'sl_hit': 0,
        'expired': 0,
        'missed_opp_from_signals': 0,
        'missed_opportunities': 0,
        'signals_with_indicators': [],
        'missed_details': [],
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
        data['error'] = 'Supabase no conectado'
        return data
    
    data['supabase_connected'] = True
    
    # Conteo global por status usando .count
    try:
        r_total = (db.client.table('signals').select('id', count='exact').limit(1).execute())
        data['total_signals'] = int(getattr(r_total, 'count', 0) or 0)
        
        for status_name, key in [
            ('tp_hit', 'tp_hit'),
            ('sl_hit', 'sl_hit'),
            ('expired', 'expired'),
            ('pending', 'pending_signals'),
            ('missed_opportunity', 'missed_opp_from_signals'),
        ]:
            try:
                r_s = (db.client.table('signals')
                       .select('id', count='exact')
                       .eq('status', status_name)
                       .limit(1)
                       .execute())
                data[key] = int(getattr(r_s, 'count', 0) or 0)
            except Exception:
                data[key] = 0
        
        data['evaluated_signals'] = data['tp_hit'] + data['sl_hit'] + data['expired']
    except Exception as e:
        logger.warning(f'Error contando signals: {e}')
    
    # Missed opportunities dedicated table
    try:
        r = db.client.table('missed_opportunities').select('id', count='exact').limit(1).execute()
        data['missed_opportunities'] = int(getattr(r, 'count', None) or 0)
    except Exception:
        pass
    
    # Traer TODAS las signals resueltas con indicadores (paginación manual)
    try:
        data['signals_with_indicators'] = _fetch_all_signals_with_indicators(db, days_back=90)
    except Exception as e:
        logger.warning(f'Error trayendo signals con indicadores: {e}')
    
    # Missed opps detalladas para análisis
    try:
        data['missed_details'] = _fetch_missed_opp_indicators(db, limit=500)
    except Exception:
        pass
    
    # Último ciclo review_log
    try:
        r = (db.client.table('review_logs').select('*').order('created_at', desc=True)
             .limit(1).execute())
        if r.data:
            data['last_review_log'] = r.data[0]
    except Exception:
        pass
    
    return data


# ============================================================================
# GENERACIÓN DEL PDF
# ============================================================================

def _confidence_badge(sample_size: int, min_rigorous: int) -> str:
    """Devuelve texto y color según si la muestra es estadísticamente válida."""
    if sample_size >= min_rigorous:
        return '✅ Válida', '#0a8f4c'
    elif sample_size >= 5:
        return '⚠️ Preliminar', '#e8a500'
    else:
        return '❓ Insuficiente', '#c92a2a'


def generate_learning_pdf() -> bytes:
    """Genera el PDF completo de aprendizaje."""
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    )
    
    data = _fetch_learning_data()
    signals_with_ind = data.get('signals_with_indicators', [])
    
    # Calcular stats en el momento
    stats_general = _calc_stats_general(signals_with_ind) if signals_with_ind else []
    stats_specific = _calc_stats_specific(signals_with_ind) if signals_with_ind else []
    stats_by_symbol = _calc_stats_by_symbol(signals_with_ind) if signals_with_ind else []
    stats_by_tf = _calc_stats_by_timeframe(signals_with_ind) if signals_with_ind else []
    missed_analysis = _analyze_missed_opps(data.get('missed_details', []))
    
    # ============ SETUP DEL PDF ============
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=1.2*cm, leftMargin=1.2*cm,
        topMargin=1.2*cm, bottomMargin=1.2*cm,
        title='Aprendizaje del Sistema'
    )
    
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('LT', parent=styles['Title'],
        fontSize=20, textColor=HexColor('#1a1a2e'),
        alignment=TA_CENTER, spaceAfter=8)
    style_sub = ParagraphStyle('LS', parent=styles['Normal'],
        fontSize=11, textColor=HexColor('#555'),
        alignment=TA_CENTER, spaceAfter=14)
    style_h2 = ParagraphStyle('LH2', parent=styles['Heading2'],
        fontSize=14, textColor=HexColor('#0a3d62'),
        spaceBefore=12, spaceAfter=8)
    style_h3 = ParagraphStyle('LH3', parent=styles['Heading3'],
        fontSize=11, textColor=HexColor('#333'),
        spaceBefore=8, spaceAfter=6)
    style_body = ParagraphStyle('LB', parent=styles['Normal'],
        fontSize=10.5, leading=14.5,
        alignment=TA_JUSTIFY, spaceAfter=8,
        textColor=HexColor('#222'))
    style_meta = ParagraphStyle('LM', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#888'),
        alignment=TA_CENTER, spaceAfter=6)
    style_note = ParagraphStyle('LN', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#666'), leftIndent=10)
    
    story = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # ============ 1. CABECERA ============
    story.append(Paragraph("Aprendizaje del Sistema", style_title))
    story.append(Paragraph(
        f"Informe del ReviewTrader · generado {now_str}",
        style_sub
    ))
    
    if not data['supabase_connected']:
        story.append(Paragraph(
            f"<b>Supabase no está conectado.</b> Detalle: {data.get('error', 'desconocido')}",
            style_body
        ))
        doc.build(story)
        result = buf.getvalue()
        buf.close()
        return result
    
    # ============ 2. QUÉ HA APRENDIDO EL SISTEMA (resumen humano) ============
    story.append(Paragraph("¿Qué ha aprendido el sistema hasta ahora?", style_h2))
    human_summary = _build_human_summary(data, stats_general, stats_general,
                                          stats_by_symbol, stats_by_tf)
    story.append(Paragraph(human_summary, style_body))
    
    # ============ 3. MÉTRICAS GLOBALES ============
    story.append(Paragraph("Métricas globales", style_h2))
    resolved = data['tp_hit'] + data['sl_hit']
    win_rate_global = (data['tp_hit'] / resolved * 100) if resolved > 0 else 0
    
    metrics_data = [
        ['Métrica', 'Valor'],
        ['Señales registradas totales', str(data['total_signals'])],
        ['Señales pendientes', str(data['pending_signals'])],
        ['Operaciones resueltas (TP + SL)', str(resolved)],
        ['   — Take Profit tocado', str(data['tp_hit'])],
        ['   — Stop Loss tocado', str(data['sl_hit'])],
        ['Señales expiradas sin toque', str(data['expired'])],
        ['NO_OPERAR marcadas como oportunidad perdida', str(data['missed_opp_from_signals'])],
        ['Win rate real (TP / (TP+SL))', f'{win_rate_global:.1f}%'],
        ['Oportunidades perdidas registradas', str(data['missed_opportunities'])],
    ]
    tmet = Table(metrics_data, colWidths=[11*cm, 5*cm])
    tmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#0a3d62')),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.4, HexColor('#c8ccd6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(tmet)
    
    story.append(PageBreak())
    
    # ============ 4. TOP 20 MEJORES ESTRATEGIAS GENERALES ============
    story.append(Paragraph("Top 20 mejores estrategias (todas las combinaciones)", style_h2))
    story.append(Paragraph(
        "Agregado por estrategia, sumando todos los pares y timeframes. "
        "Ordenadas por <b>expectancy</b> (rentabilidad esperada por operación). "
        "La columna 'Confianza estadística' indica si la muestra es suficiente para "
        f"tomar la métrica como válida (≥{GENERAL_SAMPLES_RIGOROUS} muestras).",
        style_note
    ))
    
    top_general = [s for s in stats_general if s['sample_size'] >= GENERAL_SAMPLES_MIN][:20]
    if top_general:
        rows = [['#', 'Estrategia', 'Muestras', 'Wins', 'Losses', 'Win %', 'Expec.', 'Confianza']]
        for i, s in enumerate(top_general, 1):
            badge_txt, _ = _confidence_badge(s['sample_size'], GENERAL_SAMPLES_RIGOROUS)
            rows.append([
                str(i), s['strategy'][:32], str(s['sample_size']),
                str(s['wins']), str(s['losses']),
                f"{s['win_rate']}%", f"{s['expectancy']}", badge_txt
            ])
        t = Table(rows, colWidths=[0.8*cm, 5.5*cm, 1.6*cm, 1.4*cm, 1.6*cm, 1.5*cm, 1.6*cm, 3.0*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (2,1), (6,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Aún no hay estrategias con al menos {GENERAL_SAMPLES_MIN} muestras evaluadas.</i>",
            style_body
        ))
    
    # ============ 5. TOP 20 PEORES ESTRATEGIAS GENERALES ============
    story.append(Paragraph("Top 20 peores estrategias (todas las combinaciones)", style_h2))
    story.append(Paragraph(
        "Estrategias que están perjudicando al sistema. Candidatas a revisión o "
        "reducción de peso en el comité. Ordenadas por expectancy ascendente.",
        style_note
    ))
    
    worst_general = [s for s in stats_general if s['sample_size'] >= GENERAL_SAMPLES_MIN]
    worst_general = sorted(worst_general, key=lambda r: (r['expectancy'], -r['sample_size']))[:20]
    if worst_general:
        rows = [['#', 'Estrategia', 'Muestras', 'Wins', 'Losses', 'Win %', 'Expec.', 'Confianza']]
        for i, s in enumerate(worst_general, 1):
            badge_txt, _ = _confidence_badge(s['sample_size'], GENERAL_SAMPLES_RIGOROUS)
            rows.append([
                str(i), s['strategy'][:32], str(s['sample_size']),
                str(s['wins']), str(s['losses']),
                f"{s['win_rate']}%", f"{s['expectancy']}", badge_txt
            ])
        t = Table(rows, colWidths=[0.8*cm, 5.5*cm, 1.6*cm, 1.4*cm, 1.6*cm, 1.5*cm, 1.6*cm, 3.0*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#c92a2a')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (2,1), (6,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Sin datos suficientes aún.</i>", style_body
        ))
    
    story.append(PageBreak())
    
    # ============ 6. APRENDIZAJE ESPECÍFICO ============
    story.append(Paragraph("Top 15 combinaciones específicas (par + TF + acción + estrategia)", style_h2))
    story.append(Paragraph(
        "Aprendizaje más granular: dónde exactamente rinde cada estrategia. "
        f"Requiere ≥{SPECIFIC_SAMPLES_MIN} muestras para aparecer, ≥{SPECIFIC_SAMPLES_RIGOROUS} para ser 'válida'.",
        style_note
    ))
    
    top_specific = [s for s in stats_specific if s['sample_size'] >= SPECIFIC_SAMPLES_MIN][:15]
    if top_specific:
        rows = [['Par', 'TF', 'Acción', 'Estrategia', 'Muestras', 'Win %', 'Expec.']]
        for s in top_specific:
            rows.append([
                s['symbol'], s['timeframe'], s['action'],
                s['strategy'][:22], str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']}"
            ])
        t = Table(rows, colWidths=[2.2*cm, 1.3*cm, 1.9*cm, 4.5*cm, 1.8*cm, 1.6*cm, 2.0*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (4,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Aún no hay combinaciones específicas con ≥{SPECIFIC_SAMPLES_MIN} muestras.</i>",
            style_body
        ))
    
    # Peores específicas
    story.append(Paragraph("Top 15 peores combinaciones específicas", style_h2))
    worst_specific = sorted(
        [s for s in stats_specific if s['sample_size'] >= SPECIFIC_SAMPLES_MIN],
        key=lambda r: (r['expectancy'], -r['sample_size'])
    )[:15]
    if worst_specific:
        rows = [['Par', 'TF', 'Acción', 'Estrategia', 'Muestras', 'Win %', 'Expec.']]
        for s in worst_specific:
            rows.append([
                s['symbol'], s['timeframe'], s['action'],
                s['strategy'][:22], str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']}"
            ])
        t = Table(rows, colWidths=[2.2*cm, 1.3*cm, 1.9*cm, 4.5*cm, 1.8*cm, 1.6*cm, 2.0*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#c92a2a')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(f"<i>Sin datos suficientes.</i>", style_body))
    
    story.append(PageBreak())
    
    # ============ 7. APRENDIZAJE POR PAR ============
    story.append(Paragraph("Aprendizaje por par (todos los TFs y acciones)", style_h2))
    if stats_by_symbol:
        rows = [['Par', 'Wins (TP)', 'Losses (SL)', 'Expired', 'Missed', 'Muestras', 'Win %']]
        for s in stats_by_symbol:
            rows.append([
                s['symbol'], str(s['wins']), str(s['losses']),
                str(s['expired']), str(s['missed']),
                str(s['sample_size']), f"{s['win_rate']}%"
            ])
        t = Table(rows, colWidths=[2.5*cm, 2*cm, 2*cm, 1.8*cm, 1.8*cm, 2*cm, 2*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#1a5490')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>Sin datos.</i>", style_body))
    
    # ============ 8. APRENDIZAJE POR TIMEFRAME ============
    story.append(Paragraph("Aprendizaje por timeframe (todos los pares y acciones)", style_h2))
    if stats_by_tf:
        rows = [['Timeframe', 'Wins (TP)', 'Losses (SL)', 'Expired', 'Muestras', 'Win %']]
        for s in stats_by_tf:
            rows.append([
                s['timeframe'], str(s['wins']), str(s['losses']),
                str(s['expired']), str(s['sample_size']),
                f"{s['win_rate']}%"
            ])
        t = Table(rows, colWidths=[3*cm, 2.5*cm, 2.5*cm, 2*cm, 2.5*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#1a5490')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>Sin datos.</i>", style_body))
    
    story.append(PageBreak())
    
    # ============ 9. OPORTUNIDADES PERDIDAS - ANÁLISIS DE INDICADORES ============
    story.append(Paragraph("Análisis de oportunidades perdidas", style_h2))
    story.append(Paragraph(
        f"Se han detectado <b>{missed_analysis['total']}</b> oportunidades perdidas — "
        f"casos donde el sistema decidió NO_OPERAR pero el precio se movió >2% en una "
        f"dirección clara. El análisis de qué indicadores estaban activos revela dónde "
        f"el sistema está siendo demasiado conservador.",
        style_body
    ))
    
    if missed_analysis['top_indicators']:
        story.append(Paragraph("Top 15 indicadores/estrategias más frecuentes en oportunidades perdidas", style_h3))
        story.append(Paragraph(
            "Cuando estos indicadores estaban activos, el sistema no operó pero el mercado sí se movió. "
            "Si aparecen muchas veces, sugieren que el sistema debería <b>ponderar más</b> "
            "su señal para no dejarlas pasar.",
            style_note
        ))
        rows = [['#', 'Indicador / Estrategia', 'Veces aparece', 'Movimiento medio']]
        for i, (ind, count, avg_pct) in enumerate(missed_analysis['top_indicators'], 1):
            rows.append([str(i), ind[:35], str(count), f"{avg_pct:.2f}%"])
        t = Table(rows, colWidths=[0.8*cm, 8*cm, 3*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#e8a500')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ]))
        story.append(t)
    
    if missed_analysis['top_combinations']:
        story.append(Paragraph("Top 10 COMBINACIONES de indicadores en oportunidades perdidas", style_h3))
        story.append(Paragraph(
            "Estas combinaciones de 2 indicadores/estrategias aparecen juntas frecuentemente "
            "cuando el sistema no toma la operación pero el precio sí se mueve. Son <b>señales "
            "confluentes que el sistema aprendió a identificar pero que aún no traduce en trade</b>.",
            style_note
        ))
        rows = [['#', 'Combinación', 'Veces aparece', 'Movimiento medio']]
        for i, (combo, count, avg_pct) in enumerate(missed_analysis['top_combinations'], 1):
            rows.append([str(i), combo[:50], str(count), f"{avg_pct:.2f}%"])
        t = Table(rows, colWidths=[0.8*cm, 9*cm, 2.5*cm, 3.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#8a3ffc')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
        ]))
        story.append(t)
    
    if missed_analysis['top_pairs']:
        story.append(Paragraph("Pares con más oportunidades perdidas", style_h3))
        rows = [['Par + TF', 'Oportunidades perdidas']]
        for pair, count in missed_analysis['top_pairs']:
            rows.append([pair, str(count)])
        t = Table(rows, colWidths=[8*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#333')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
        ]))
        story.append(t)
    
    if not missed_analysis['top_indicators'] and not missed_analysis['top_combinations']:
        story.append(Paragraph(
            "<i>No hay oportunidades perdidas registradas con detalles de indicadores todavía.</i>",
            style_body
        ))
    
    # ============ 10. NOTAS TÉCNICAS ============
    story.append(PageBreak())
    story.append(Paragraph("Notas técnicas sobre el aprendizaje", style_h2))
    story.append(Paragraph(
        f"<b>Umbrales estadísticos:</b>"
        f"<br/>• Muestras mínimas para publicar estrategia como VÁLIDA (nivel específico): "
        f"<b>{SPECIFIC_SAMPLES_RIGOROUS}</b>"
        f"<br/>• Muestras mínimas para publicar estrategia como VÁLIDA (nivel general): "
        f"<b>{GENERAL_SAMPLES_RIGOROUS}</b>"
        f"<br/>• Muestras mínimas para mostrar en el PDF (preliminares): "
        f"<b>{SPECIFIC_SAMPLES_MIN}/{GENERAL_SAMPLES_MIN}</b>"
        f"<br/>• Win rate objetivo para 'estrategia ganadora': ≥ 60%"
        f"<br/>• Win rate objetivo para 'estrategia perdedora': ≤ 40%"
        f"<br/><br/>"
        f"<b>Cómo se aprende:</b>"
        f"<br/>• El learning worker corre cada 15 minutos: evalúa señales pendientes y "
        f"marca si tocaron TP, SL o expiraron."
        f"<br/>• Cada 4 horas se recalculan las estadísticas cachedas y las recomendaciones."
        f"<br/>• A las 20:00 hora Bolivia corre el ciclo diario completo (evaluación + "
        f"detección de oportunidades perdidas + recalculo + optimización)."
        f"<br/><br/>"
        f"<b>Cómo se aplica el aprendizaje:</b>"
        f"<br/>• El ReviewTrader (10º trader del comité) consulta las estrategias "
        f"históricamente ganadoras para el (par, TF, acción) y emite voto con confianza "
        f"proporcional a cuántas coinciden con las estrategias activas actuales."
        f"<br/>• El voto se pondera con peso 1.0 en el consenso final junto a los otros 9 traders."
        f"<br/>• Las 'oportunidades perdidas' se registran para futura calibración pero "
        f"aún no ajustan automáticamente las decisiones — es información para el operador humano.",
        style_body
    ))
    
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(
        "© Crypto Trader Analyst Pro — Sistema Experto de Trading. "
        "El aprendizaje se acumula con cada operación evaluada; a más muestras, más precisión.",
        style_meta
    ))
    
    doc.build(story)
    result = buf.getvalue()
    buf.close()
    return result
