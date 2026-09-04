"""
pdf_learning_report.py
=======================
Genera un PDF que explica QUÉ está aprendiendo el ReviewTrader.

Estructura del informe:
  1. Métricas coherentes por mercado y cohorte
  2. QUÉ HA APRENDIDO EL SISTEMA (resumen humano automático)
  3. Métricas separadas Spot/Futuros
  4. Futures Shadow: Safety, resultados y contexto cuantitativo
  5. Mejores/peores estrategias operables y combinaciones por mercado
  7. ESTRATEGIAS POR TRADER (cobertura del comité) — v22
  8. Aprendizaje por PAR (win rate por símbolo)
  9. Aprendizaje por TIMEFRAME
  10. Oportunidades perdidas: indicadores que estaban activos
  11. Notas técnicas

CAMBIO IMPORTANTE: en lugar de leer solo las tablas strategy_stats_* (que
requieren ejecutar run_full_review y a veces fallan por timeout), este PDF
CALCULA las estadísticas EN EL MOMENTO desde `signals` + `signal_results`.
Así el aprendizaje siempre se ve, aunque las tablas cache estén vacías.

Requiere: reportlab, supabase-py.
"""

import io
import json
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
REPORT_DAYS_BACK = 90

LEARNING_CONTRACT_VERSION = 'market_separated_v1'
FUTURES_REAL_DATA_SOURCE = 'KUCOIN_FUTURES_PERPETUAL_REST'
FUTURES_REAL_COHORT = 'FUTURES_PERPETUAL_REAL_CLOSED_V1'

# ============================================================================
# v26: BANDAS DE DIAGNÓSTICO SHADOW FUTURES
# ============================================================================
# Referencias exclusivas del informe: NO cambian el motor operativo.
SHADOW_EXECUTION_FLOOR = 65.0
SHADOW_PUBLICATION_SAFETY = 75.0
SHADOW_TP_QUALITY_REFERENCE = 55.0
SHADOW_SL_QUALITY_REFERENCE = 60.0
SHADOW_RR_MIN_REFERENCE = 1.8
SHADOW_RR_MAX_REFERENCE = 3.5


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'si', 'sí')
    return bool(value)


def _normalize_market(signal: Dict) -> str:
    value = str(signal.get('system_type') or '').strip().lower()
    if value == 'spot':
        return 'spot'
    if value == 'futures':
        return 'futures'
    return 'unscoped'


def _get_learning_context(signal: Dict) -> Dict:
    context = signal.get('context') or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            return {}
    if not isinstance(context, dict):
        return {}
    learning = context.get('learning') or {}
    return learning if isinstance(learning, dict) else {}


def _is_clean_futures_observation(signal: Dict) -> bool:
    if _normalize_market(signal) != 'futures':
        return False
    learning = _get_learning_context(signal)
    return bool(
        learning.get('contract_version') == LEARNING_CONTRACT_VERSION
        and learning.get('cohort') == FUTURES_REAL_COHORT
        and str(learning.get('market_data_source') or '').upper()
        == FUTURES_REAL_DATA_SOURCE
        and not _as_bool(learning.get('market_data_is_synthetic', True))
        and _as_bool(learning.get('source_candle_closed', False))
    )


def _is_verified_futures_trade(signal: Dict) -> bool:
    if not _is_clean_futures_observation(signal):
        return False
    learning = _get_learning_context(signal)
    return bool(
        _as_bool(learning.get('statistically_eligible', False))
        and learning.get('evaluation_role') == 'EXECUTABLE_SIGNAL'
    )


def _latest_signal_result(signal: Dict) -> Dict:
    results = signal.get('signal_results') or []
    if isinstance(results, dict):
        return results
    if not isinstance(results, list) or not results:
        return {}
    return max(
        (item for item in results if isinstance(item, dict)),
        key=lambda item: str(item.get('created_at') or ''),
        default={}
    )


def _outcome_values(signal: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Retorna (PnL bruto %, resultado R) usando los niveles de ESA señal."""
    status = str(signal.get('status') or '')
    if status not in ('tp_hit', 'sl_hit'):
        return None, None

    try:
        entry = float(signal.get('entry_price') or 0)
        sl = float(signal.get('stop_loss') or 0)
        tp = float(signal.get('take_profit') or 0)
    except (TypeError, ValueError):
        return None, None
    if entry <= 0 or sl <= 0 or tp <= 0:
        return None, None

    result = _latest_signal_result(signal)
    raw_pnl = result.get('pnl_pct')
    try:
        pnl_pct = float(raw_pnl) if raw_pnl is not None else None
    except (TypeError, ValueError):
        pnl_pct = None

    action = str(signal.get('action_normalized') or '').upper()
    if pnl_pct is None:
        exit_price = tp if status == 'tp_hit' else sl
        if action == 'LONG':
            pnl_pct = (exit_price - entry) / entry * 100
        elif action == 'SHORT':
            pnl_pct = (entry - exit_price) / entry * 100
        else:
            return None, None

    risk_pct = abs(entry - sl) / entry * 100
    r_multiple = pnl_pct / risk_pct if risk_pct > 0 else None
    return pnl_pct, r_multiple


def _signal_notes(signal: Dict) -> str:
    return str(_latest_signal_result(signal).get('notes') or '')


def _market_metrics(signals: List[Dict]) -> Dict:
    counts = defaultdict(int)
    pnl_values = []
    r_values = []
    for signal in signals:
        status = str(signal.get('status') or 'unknown')
        counts[status] += 1
        if status == 'expired':
            notes = _signal_notes(signal)
            if 'outcome_reason=expired_no_entry' in notes:
                counts['expired_no_entry'] += 1
            elif 'outcome_reason=expired_after_entry' in notes:
                counts['expired_after_entry'] += 1
        pnl_pct, r_multiple = _outcome_values(signal)
        if pnl_pct is not None:
            pnl_values.append(pnl_pct)
        if r_multiple is not None:
            r_values.append(r_multiple)

    resolved = counts['tp_hit'] + counts['sl_hit']
    return {
        'total': len(signals),
        'pending': counts['pending'],
        'tp_hit': counts['tp_hit'],
        'sl_hit': counts['sl_hit'],
        'resolved': resolved,
        'expired': counts['expired'],
        'expired_no_entry': counts['expired_no_entry'],
        'expired_after_entry': counts['expired_after_entry'],
        'ambiguous': counts['ambiguous'],
        'invalid_setup': counts['invalid_setup'],
        'win_rate': round(counts['tp_hit'] / resolved * 100, 1)
        if resolved else None,
        'avg_pnl_pct': round(sum(pnl_values) / len(pnl_values), 4)
        if pnl_values else None,
        'expectancy_r': round(sum(r_values) / len(r_values), 4)
        if r_values else None,
        'outcome_samples': len(pnl_values)
    }


def _split_learning_cohorts(signals: List[Dict]) -> Dict[str, List[Dict]]:
    cohorts = {
        'spot': [],
        'futures_verified': [],
        'futures_shadow': [],
        'futures_legacy': [],
        'unscoped': []
    }
    for signal in signals:
        market = _normalize_market(signal)
        if market == 'spot':
            cohorts['spot'].append(signal)
        elif market == 'futures':
            if _is_verified_futures_trade(signal):
                cohorts['futures_verified'].append(signal)
            elif _is_clean_futures_observation(signal):
                cohorts['futures_shadow'].append(signal)
            else:
                cohorts['futures_legacy'].append(signal)
        else:
            cohorts['unscoped'].append(signal)
    return cohorts


# ============================================================================
# v26: ANALÍTICA SHADOW FUTURES
# ============================================================================
# SHADOW nunca entra en métricas operativas ni modifica decisiones.
# Sólo permite estudiar si algún filtro podría ser demasiado estricto.
# ============================================================================

def _get_signal_context(signal: Dict) -> Dict:
    """Devuelve context como dict, tolerando JSON serializado."""
    context = signal.get('context') or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            return {}
    return context if isinstance(context, dict) else {}


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_execution_context(signal: Dict) -> Dict:
    context = _get_signal_context(signal)
    execution = context.get('execution') or {}
    return execution if isinstance(execution, dict) else {}


def _normalize_shadow_action(signal: Dict) -> str:
    raw = str(
        signal.get('action_normalized')
        or signal.get('action')
        or ''
    ).strip().upper()
    if raw.endswith('LONG'):
        return 'LONG'
    if raw.endswith('SHORT'):
        return 'SHORT'
    return raw


def _shadow_has_trade_geometry(signal: Dict) -> bool:
    """True sólo si hay LONG/SHORT con Entry, SL y TP numéricos válidos."""
    action = _normalize_shadow_action(signal)
    if action not in ('LONG', 'SHORT'):
        return False

    entry = _safe_float(signal.get('entry_price'), 0.0) or 0.0
    sl = _safe_float(signal.get('stop_loss'), 0.0) or 0.0
    tp = _safe_float(signal.get('take_profit'), 0.0) or 0.0

    if entry <= 0 or sl <= 0 or tp <= 0:
        return False
    if action == 'LONG':
        return sl < entry < tp
    return tp < entry < sl


def _shadow_entry_state(signal: Dict) -> str:
    """Infiere sólo estados de Entry demostrables por status/notas."""
    status = str(signal.get('status') or '').strip().lower()
    notes = _signal_notes(signal).lower()

    if status in ('tp_hit', 'sl_hit', 'ambiguous', 'expired_after_entry'):
        return 'entry_touched'
    if status == 'expired_no_entry':
        return 'no_entry'
    if status == 'expired':
        if 'outcome_reason=expired_after_entry' in notes:
            return 'entry_touched'
        if 'outcome_reason=expired_no_entry' in notes:
            return 'no_entry'
    return 'unknown'


def _normalized_sl_quality(execution: Dict) -> Optional[float]:
    """Normaliza sl_reliability histórico 0-1 o 0-100 a escala 0-100."""
    raw = _safe_float(execution.get('sl_reliability'))
    if raw is None:
        return None
    if 0 <= raw <= 1:
        return raw * 100.0
    return raw


def _shadow_safety_bucket(safety: Optional[float]) -> str:
    if safety is None or safety <= 0:
        return 'Sin dato'
    if safety < SHADOW_EXECUTION_FLOOR:
        return '<65'
    if safety < 70:
        return '65-69'
    if safety < SHADOW_PUBLICATION_SAFETY:
        return '70-74'
    return '>=75'


def _shadow_bucket_metrics(signals: List[Dict]) -> Dict:
    counts = defaultdict(int)
    pnl_values = []
    r_values = []

    for signal in signals:
        status = str(signal.get('status') or 'unknown').strip().lower()
        counts[status] += 1
        counts[_shadow_entry_state(signal)] += 1

        pnl_pct, r_multiple = _outcome_values(signal)
        if pnl_pct is not None:
            pnl_values.append(pnl_pct)
        if r_multiple is not None:
            r_values.append(r_multiple)

    resolved = counts['tp_hit'] + counts['sl_hit']
    return {
        'total': len(signals),
        'pending': counts['pending'],
        'tp_hit': counts['tp_hit'],
        'sl_hit': counts['sl_hit'],
        'resolved': resolved,
        'expired': (
            counts['expired']
            + counts['expired_no_entry']
            + counts['expired_after_entry']
        ),
        'ambiguous': counts['ambiguous'],
        'invalid_setup': counts['invalid_setup'],
        'entry_touched': counts['entry_touched'],
        'no_entry': counts['no_entry'],
        'entry_unknown': counts['unknown'],
        'win_rate': round(counts['tp_hit'] / resolved * 100, 1)
        if resolved else None,
        'expectancy_r': round(sum(r_values) / len(r_values), 4)
        if r_values else None,
        'avg_pnl_pct': round(sum(pnl_values) / len(pnl_values), 4)
        if pnl_values else None,
        'outcome_samples': len(r_values),
    }


def _calc_shadow_futures_analysis(signals: List[Dict]) -> Dict:
    """
    Resume la cohorte SHADOW sin concederle autoridad operativa.

    Las banderas de referencia NO son el motivo histórico exacto de rechazo:
    ReviewTrader no persiste hoy toda la lista del publication gate.
    """
    signals = list(signals or [])
    directional = [
        s for s in signals
        if _normalize_shadow_action(s) in ('LONG', 'SHORT')
    ]
    geometry = [s for s in directional if _shadow_has_trade_geometry(s)]

    summary = _shadow_bucket_metrics(signals)
    summary['directional'] = len(directional)
    summary['valid_geometry'] = len(geometry)

    by_safety_raw = defaultdict(list)
    reference_flags = defaultdict(int)
    quant_regime_raw = defaultdict(list)
    quant_alignment_raw = defaultdict(list)
    quant_verdict_raw = defaultdict(list)
    quant_available = 0

    for signal in geometry:
        execution = _get_execution_context(signal)
        safety = _safe_float(execution.get('execution_safety'))
        tp_quality = _safe_float(execution.get('tp_quality_score'))
        sl_quality = _normalized_sl_quality(execution)
        rr = _safe_float(
            execution.get('risk_reward'),
            _safe_float(signal.get('risk_reward'))
        )

        by_safety_raw[_shadow_safety_bucket(safety)].append(signal)

        if safety is not None and safety > 0 and safety < SHADOW_PUBLICATION_SAFETY:
            reference_flags['Safety < 75'] += 1
        if tp_quality is not None and tp_quality > 0 and tp_quality < SHADOW_TP_QUALITY_REFERENCE:
            reference_flags['Calidad TP < 55'] += 1
        if sl_quality is not None and sl_quality > 0 and sl_quality < SHADOW_SL_QUALITY_REFERENCE:
            reference_flags['Protección SL < 60'] += 1
        if rr is not None and rr > 0:
            if rr < SHADOW_RR_MIN_REFERENCE:
                reference_flags['RR < 1.8'] += 1
            elif rr > SHADOW_RR_MAX_REFERENCE:
                reference_flags['RR > 3.5'] += 1

        learning = _get_learning_context(signal)
        quant = learning.get('quantitative_shadow') or {}
        if isinstance(quant, dict) and quant:
            quant_available += 1
            regime = str(quant.get('regime') or 'UNAVAILABLE').strip().upper()
            alignment = str(
                quant.get('direction_alignment') or 'NOT_APPLICABLE'
            ).strip().upper()
            verdict = str(
                quant.get('shadow_verdict') or 'UNAVAILABLE'
            ).strip().upper()
            quant_regime_raw[regime].append(signal)
            quant_alignment_raw[alignment].append(signal)
            quant_verdict_raw[verdict].append(signal)

    by_safety = []
    for bucket in ['<65', '65-69', '70-74', '>=75', 'Sin dato']:
        items = by_safety_raw.get(bucket) or []
        if items:
            row = _shadow_bucket_metrics(items)
            row['bucket'] = bucket
            by_safety.append(row)

    def _group_rows(raw_groups, key_name):
        rows = []
        for key, items in raw_groups.items():
            row = _shadow_bucket_metrics(items)
            row[key_name] = key
            rows.append(row)
        return sorted(rows, key=lambda r: (-r.get('total', 0), str(r.get(key_name, ''))))

    return {
        'summary': summary,
        'by_safety': by_safety,
        'reference_flags': sorted(
            reference_flags.items(),
            key=lambda item: (-item[1], item[0])
        ),
        'quant_available': quant_available,
        'by_quant_regime': _group_rows(quant_regime_raw, 'regime'),
        'by_quant_alignment': _group_rows(quant_alignment_raw, 'alignment'),
        'by_quant_verdict': _group_rows(quant_verdict_raw, 'verdict'),
    }


# ============================================================================
# v22: MAPEO ESTRATEGIA → TRADER (para auditar cobertura del comité)
# ============================================================================
# Cada trader emite un conjunto conocido de estrategias. Este mapa permite
# saber a qué trader corresponde cada strategy_name guardada en Supabase, y
# generar la sección "estrategias por trader" del PDF de Aprendizaje.
STRATEGY_TO_TRADER = {
    # TraderTecnico (RSI, MACD, ADX, BB, Squeeze)
    'BAND_WALK_ALCISTA': 'TraderTecnico',
    'BAND_WALK_BAJISTA': 'TraderTecnico',
    'EXPANSION_VOLATILIDAD': 'TraderTecnico',
    'PULLBACK_TENDENCIA': 'TraderTecnico',
    'SOBRECOMPRA': 'TraderTecnico',
    'SOBREVENTA': 'TraderTecnico',
    'SQUEEZE_ALCISTA': 'TraderTecnico',
    'SQUEEZE_BAJISTA': 'TraderTecnico',
    'TENDENCIA_FUERTE': 'TraderTecnico',
    # TraderChartista (patrones gráficos)
    'ACUMULACION_PATRONES': 'TraderChartista',
    'ACUMULACION_PATRONES_BAJISTAS': 'TraderChartista',
    'BANDERA_ALCISTA': 'TraderChartista',
    'DOBLE_SUELO': 'TraderChartista',
    'DOBLE_TECHO': 'TraderChartista',
    'HCH_INVERTIDO': 'TraderChartista',
    # TraderBallenas (volumen anómalo, whale)
    'ACUMULACION_ICEBERG': 'TraderBallenas',
    'DISTRIBUCION_ICEBERG': 'TraderBallenas',
    'MAVERICK': 'TraderBallenas',
    'MAVERICK_BAJISTA': 'TraderBallenas',
    'VOLUMEN_ANOMALO_ALCISTA': 'TraderBallenas',
    'VOLUMEN_ANOMALO_BAJISTA': 'TraderBallenas',
    # TraderMacro (correlaciones BTC/PAXG, régimen macro)
    'BTC_ALCISTA_UNILATERAL': 'TraderMacro',
    'BTC_BAJISTA_UNILATERAL': 'TraderMacro',
    'BTC_MAS_FUERTE': 'TraderMacro',
    'BTC_MAS_FUERTE_RATIO': 'TraderMacro',
    'CORRELACION_NEGATIVA': 'TraderMacro',
    'CORRELACION_POSITIVA': 'TraderMacro',
    'EVITAR_BTC_POR_ROTACION': 'TraderMacro',
    'EVITAR_PAXG_POR_ROTACION': 'TraderMacro',
    'PAXG_MAS_FUERTE': 'TraderMacro',
    'PAXG_MAS_FUERTE_RATIO': 'TraderMacro',
    'RATIO_ALCISTA': 'TraderMacro',
    'RATIO_BAJISTA': 'TraderMacro',
    'ROTACION_REFUGIO': 'TraderMacro',
    'ROTACION_REFUGIO_RATIO': 'TraderMacro',
    'ROTACION_RIESGO': 'TraderMacro',
    'ROTACION_RIESGO_RATIO': 'TraderMacro',
    # TraderPullback
    'PULLBACK_ALCISTA': 'TraderPullback',
    'PULLBACK_BAJISTA': 'TraderPullback',
    # TraderSmartMoney (SMC: OB, FVG, VP, liquidity)
    'CONFLUENCIA_MULTIPLE': 'TraderSmartMoney',
    'FVG_ALCISTA': 'TraderSmartMoney',
    'FVG_BAJISTA': 'TraderSmartMoney',
    'HVN_RESISTENCIA': 'TraderSmartMoney',
    'HVN_SOPORTE': 'TraderSmartMoney',
    'LIQUIDITY_SWEEP_ALCISTA': 'TraderSmartMoney',
    'LIQUIDITY_SWEEP_BAJISTA': 'TraderSmartMoney',
    'LVN_ROTURA': 'TraderSmartMoney',
    'ORDER_BLOCK_ALCISTA': 'TraderSmartMoney',
    'ORDER_BLOCK_BAJISTA': 'TraderSmartMoney',
    'POC_CONFLUENCIA': 'TraderSmartMoney',
    'POC_REBOTE': 'TraderSmartMoney',
    'POC_RESISTENCIA': 'TraderSmartMoney',
    'POC_VWAP_CONFLUENCIA': 'TraderSmartMoney',
    'STOP_HUNT_ALCISTA': 'TraderSmartMoney',
    'STOP_HUNT_BAJISTA': 'TraderSmartMoney',
    'STOP_HUNT_OB': 'TraderSmartMoney',
    'VALUE_AREA_BREAKDOWN': 'TraderSmartMoney',
    'VALUE_AREA_BREAKOUT': 'TraderSmartMoney',
    'VALUE_AREA_CONFIRMACION': 'TraderSmartMoney',
    'VALUE_AREA_CONFIRMACION_BAJISTA': 'TraderSmartMoney',
    'VALUE_AREA_EXTREMO_ALTO': 'TraderSmartMoney',
    'VALUE_AREA_EXTREMO_BAJO': 'TraderSmartMoney',
    'VOLUMEN_ANOMALO': 'TraderSmartMoney',
    # TraderEspectico (cauteloso)
    'CONFIRMACION_RECHAZADA': 'TraderEspectico',
    # TraderMultiframe (multi-timeframe)
    'ACUMULACION_EN_ZONA_BAJISTA': 'TraderMultiframe',
    'ALINEACION_BEARISH_COMPLETA': 'TraderMultiframe',
    'ALINEACION_BULLISH_COMPLETA': 'TraderMultiframe',
    'CONFLICTO_MAYOR_ADVIERTE_CAMBIO': 'TraderMultiframe',
    'DISTRIBUCION_EN_ZONA_ALCISTA': 'TraderMultiframe',
    'PULLBACK_OPORTUNIDAD': 'TraderMultiframe',
    'RUPTURA_CONFIRMADA': 'TraderMultiframe',
    # TraderLiquidation (mapa de liquidaciones futuros)
    'HEAVY_LONG_CONCENTRATION': 'TraderLiquidation',
    'HEAVY_SHORT_CONCENTRATION': 'TraderLiquidation',
    'LIQUIDITY_BALANCE': 'TraderLiquidation',
    'LIQUIDITY_PRESENT': 'TraderLiquidation',
    'LONG_DOMINANCE_SUPPORT': 'TraderLiquidation',
    'LONG_EXTREME_REVERSAL': 'TraderLiquidation',
    'RECENT_LONG_LIQUIDATIONS': 'TraderLiquidation',
    'RECENT_SHORT_LIQUIDATIONS': 'TraderLiquidation',
    'SHORT_DOMINANCE_RESISTANCE': 'TraderLiquidation',
    'SHORT_EXTREME_REVERSAL': 'TraderLiquidation',
    'SPIKE_ACCUMULATION_LONG': 'TraderLiquidation',
    'SPIKE_ACCUMULATION_SHORT': 'TraderLiquidation',
    # ReviewTrader (juez del comité)
    'REVIEW_HISTORICO_GANADOR_LONG': 'ReviewTrader',
    'REVIEW_HISTORICO_GANADOR_SHORT': 'ReviewTrader',
    'REVIEW_PATRON_PERDEDOR': 'ReviewTrader',
    # Ambiguas / compartidas
    'ESPERAR_CONFIRMACION': 'TraderPullback+TraderEspectico',
}
# Lista canónica de traders para orden estable en el PDF
CANONICAL_TRADERS = [
    'TraderTecnico', 'TraderChartista', 'TraderBallenas',
    'TraderMacro', 'TraderPullback', 'TraderSmartMoney',
    'TraderEspectico', 'TraderMultiframe', 'TraderLiquidation',
    'ReviewTrader',
]


def _calc_stats_by_trader(signals: List[Dict]) -> List[Dict]:
    """
    v22: agrupa las señales resueltas por trader (usando STRATEGY_TO_TRADER)
    y calcula: nº estrategias distintas, señales totales, wins, losses, WR.
    
    Retorna lista ordenada por WR desc, con métricas por trader.
    """
    by_trader = defaultdict(lambda: {
        'strategies_seen': set(),
        'wins': 0, 'losses': 0, 'expired': 0,
    })
    
    for sig in signals:
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        status = sig.get('status')
        market = _normalize_market(sig)
        
        traders_de_esta_signal = set()
        for strat in strategies:
            trader = STRATEGY_TO_TRADER.get(strat)
            if not trader:
                continue
            # Estrategia ambigua: contarla para cada trader que la emite
            for t in trader.split('+'):
                traders_de_esta_signal.add(t)
                by_trader[(market, t)]['strategies_seen'].add(strat)
        
        # Cada trader que contribuyó recibe crédito/débito
        for t in traders_de_esta_signal:
            b = by_trader[(market, t)]
            if status == 'tp_hit':
                b['wins'] += 1
            elif status == 'sl_hit':
                b['losses'] += 1
            elif status == 'expired':
                b['expired'] += 1
    
    rows = []
    markets_present = [
        market for market in ('spot', 'futures')
        if any(key[0] == market for key in by_trader)
    ]
    for market in markets_present:
        for t in CANONICAL_TRADERS:
            b = by_trader.get((market, t))
            if not b:
                rows.append({
                    'market': market,
                    'trader': t, 'signals': 0, 'wins': 0, 'losses': 0,
                    'win_rate': 0.0, 'expired': 0,
                    'unique_strategies': 0, 'strategies': [],
                })
                continue
            resolved = b['wins'] + b['losses']
            wr = (b['wins'] / resolved * 100) if resolved > 0 else 0.0
            rows.append({
                'market': market,
                'trader': t,
                'signals': resolved + b['expired'],
                'wins': b['wins'],
                'losses': b['losses'],
                'expired': b['expired'],
                'win_rate': round(wr, 1),
                'unique_strategies': len(b['strategies_seen']),
                'strategies': sorted(b['strategies_seen']),
            })
    # Ordenar: primero por si aportó, luego por WR
    rows.sort(key=lambda x: (
        0 if x['market'] == 'spot' else 1,
        -x['signals'],
        -x['win_rate']
    ))
    return rows


# ============================================================================
# HELPERS DE CÁLCULO DE STATS (funcionan directamente sobre signals de la BD)
# ============================================================================

def _fetch_all_signals_with_indicators(db, days_back: int = 90) -> List[Dict]:
    """Trae una cohorte temporal coherente, incluyendo pendientes y resultados."""
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
                          'created_at, candle_timestamp, system_type, context, '
                          'signal_indicators(strategy_name), '
                          'signal_results(status, pnl_pct, notes, exit_price, '
                          'exit_timestamp, created_at)')
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
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0,
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
        market = _normalize_market(sig)
        pnl_pct, r_multiple = _outcome_values(sig)
        
        for strat in strategies:
            b = buckets[(market, strat)]
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
            if pnl_pct is not None and r_multiple is not None:
                b['pnl_total'] += pnl_pct
                b['r_total'] += r_multiple
                b['outcome_samples'] += 1
    
    rows = []
    for (market, strat), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins'] / resolved * 100) if resolved > 0 else 0
        outcome_samples = b['outcome_samples']
        expectancy = (
            b['r_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        avg_pnl_pct = (
            b['pnl_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        
        # Best/worst pairs & timeframes (min 3 muestras)
        def _rank(subs: Dict, top: bool):
            scored = []
            for k, v in subs.items():
                s = v['wins'] + v['losses']
                if s >= 3:
                    scored.append((k, v['wins']/s*100, s))
            return sorted(scored, key=lambda x: -x[1] if top else x[1])[:3]
        
        rows.append({
            'market': market,
            'strategy': strat,
            'total': resolved + b['expired'],
            'wins': b['wins'],
            'losses': b['losses'],
            'expired': b['expired'],
            'missed': b['missed_opps'],
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 3),
            'avg_pnl_pct': round(avg_pnl_pct, 4),
            'sample_size': resolved,
            'best_symbols': _rank(b['by_symbol'], top=True),
            'worst_symbols': _rank(b['by_symbol'], top=False),
            'best_tfs': _rank(b['by_timeframe'], top=True),
            'worst_tfs': _rank(b['by_timeframe'], top=False),
        })
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        -r['expectancy'],
        -r['sample_size']
    ))


def _calc_stats_specific(signals: List[Dict]) -> List[Dict]:
    """
    Calcula stats por (symbol, timeframe, action, strategy).
    Ordenado por expectancy desc.
    """
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0
    })
    
    for sig in signals:
        symbol = sig.get('symbol')
        tf = sig.get('timeframe')
        action = sig.get('action_normalized')
        status = sig.get('status')
        market = _normalize_market(sig)
        pnl_pct, r_multiple = _outcome_values(sig)
        if not (symbol and tf and action):
            continue
        strategies = [
            si.get('strategy_name') for si in (sig.get('signal_indicators') or [])
            if si.get('strategy_name')
        ]
        if not strategies:
            continue
        
        for strat in strategies:
            key = (market, symbol, tf, action, strat)
            if status == 'tp_hit':
                buckets[key]['wins'] += 1
            elif status == 'sl_hit':
                buckets[key]['losses'] += 1
            elif status == 'expired':
                buckets[key]['expired'] += 1
            if pnl_pct is not None and r_multiple is not None:
                buckets[key]['pnl_total'] += pnl_pct
                buckets[key]['r_total'] += r_multiple
                buckets[key]['outcome_samples'] += 1
    
    rows = []
    for (market, sym, tf, action, strat), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0:
            continue
        win_rate = (b['wins'] / resolved) * 100
        outcome_samples = b['outcome_samples']
        expectancy = (
            b['r_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        avg_pnl_pct = (
            b['pnl_total'] / outcome_samples
            if outcome_samples else 0.0
        )
        rows.append({
            'market': market,
            'symbol': sym, 'timeframe': tf, 'action': action, 'strategy': strat,
            'total': resolved + b['expired'], 'wins': b['wins'],
            'losses': b['losses'], 'expired': b['expired'],
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 3),
            'avg_pnl_pct': round(avg_pnl_pct, 4),
            'sample_size': resolved,
        })
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        -r['expectancy'],
        -r['sample_size']
    ))


def _calc_stats_by_symbol(signals: List[Dict]) -> List[Dict]:
    """Win rate agregado por par."""
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0, 'missed': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0
    })
    for sig in signals:
        sym = sig.get('symbol')
        if not sym:
            continue
        st = sig.get('status')
        market = _normalize_market(sig)
        b = buckets[(market, sym)]
        if st == 'tp_hit':
            b['wins'] += 1
        elif st == 'sl_hit':
            b['losses'] += 1
        elif st == 'expired':
            b['expired'] += 1
        elif st == 'missed_opportunity':
            b['missed'] += 1
        pnl_pct, r_multiple = _outcome_values(sig)
        if pnl_pct is not None and r_multiple is not None:
            b['pnl_total'] += pnl_pct
            b['r_total'] += r_multiple
            b['outcome_samples'] += 1
    rows = []
    for (market, sym), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins']/resolved*100) if resolved > 0 else 0
        outcome_samples = b['outcome_samples']
        rows.append({
            'market': market, 'symbol': sym,
            'wins': b['wins'], 'losses': b['losses'],
            'expired': b['expired'], 'missed': b['missed'],
            'sample_size': resolved,
            'win_rate': round(win_rate, 1),
            'expectancy': round(b['r_total']/outcome_samples, 3)
            if outcome_samples else 0.0,
            'avg_pnl_pct': round(b['pnl_total']/outcome_samples, 4)
            if outcome_samples else 0.0,
        })
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        -r['expectancy'],
        -r['sample_size']
    ))


def _calc_stats_by_timeframe(signals: List[Dict]) -> List[Dict]:
    """Win rate agregado por timeframe."""
    buckets = defaultdict(lambda: {
        'wins': 0, 'losses': 0, 'expired': 0,
        'pnl_total': 0.0, 'r_total': 0.0, 'outcome_samples': 0
    })
    for sig in signals:
        tf = sig.get('timeframe')
        if not tf:
            continue
        st = sig.get('status')
        market = _normalize_market(sig)
        b = buckets[(market, tf)]
        if st == 'tp_hit':
            b['wins'] += 1
        elif st == 'sl_hit':
            b['losses'] += 1
        elif st == 'expired':
            b['expired'] += 1
        pnl_pct, r_multiple = _outcome_values(sig)
        if pnl_pct is not None and r_multiple is not None:
            b['pnl_total'] += pnl_pct
            b['r_total'] += r_multiple
            b['outcome_samples'] += 1
    rows = []
    for (market, tf), b in buckets.items():
        resolved = b['wins'] + b['losses']
        if resolved == 0 and b['expired'] == 0:
            continue
        win_rate = (b['wins']/resolved*100) if resolved > 0 else 0
        outcome_samples = b['outcome_samples']
        rows.append({
            'market': market, 'timeframe': tf,
            'wins': b['wins'], 'losses': b['losses'],
            'expired': b['expired'], 'sample_size': resolved,
            'win_rate': round(win_rate, 1),
            'expectancy': round(b['r_total']/outcome_samples, 3)
            if outcome_samples else 0.0,
            'avg_pnl_pct': round(b['pnl_total']/outcome_samples, 4)
            if outcome_samples else 0.0,
        })
    # Ordenar por TF de menor a mayor (5m, 15m, 30m, 1h, 2h, 4h, 12h, 1D, 1W)
    tf_order = {'5m': 0, '15m': 1, '30m': 2, '1h': 3, '2h': 4, '4h': 5,
                '12h': 6, '1D': 7, '1W': 8}
    return sorted(rows, key=lambda r: (
        0 if r['market'] == 'spot' else 1,
        tf_order.get(r['timeframe'], 99)
    ))


def _fetch_missed_opp_indicators(db, limit: int = 200) -> List[Dict]:
    """
    Trae oportunidades perdidas junto con los indicadores que estaban activos
    cuando el sistema NO tomó la operación. Ayuda a identificar patrones de
    'cuándo el sistema es demasiado conservador'.
    
    v22.8 FIX: los nombres de columnas eran INCORRECTOS. La tabla
    missed_opportunities usa 'max_favorable_pct' y 'strategies_detected'
    (ver schema_supabase.sql:137-151), no 'pct_missed' ni 'active_strategies'.
    Este bug hacía que el fetch fallara silenciosamente (try/except return [])
    y el PDF siempre mostraba 0 oportunidades perdidas, aunque en Supabase
    hubiera cientos (log del ReviewTrader reportaba 1061).
    """
    try:
        r = (db.client.table('missed_opportunities')
             .select('symbol, timeframe, action_that_should_have_been, '
                     'max_favorable_pct, strategies_detected, created_at')
             .order('created_at', desc=True)
             .limit(limit)
             .execute())
        return r.data or []
    except Exception as e:
        logger.warning(f"_fetch_missed_opp_indicators falló: {e}")
        return []


def _analyze_missed_opps(missed: List[Dict]) -> Dict:
    """
    De las oportunidades perdidas, agrupa por indicadores/estrategias activas
    para ver qué combinaciones aparecen con más frecuencia (candidatas a
    'próximas veces con este set, sí tomar la operación').
    
    v22.8: nombres de campos corregidos (strategies_detected, max_favorable_pct).
    """
    indicator_freq = defaultdict(lambda: {'count': 0, 'total_pct': 0.0})
    combination_freq = defaultdict(lambda: {'count': 0, 'total_pct': 0.0})
    by_pair = defaultdict(int)
    by_direction = defaultdict(int)
    
    for opp in missed:
        # v22.8: el schema usa 'strategies_detected', no 'active_strategies'
        strats = opp.get('strategies_detected') or []
        if not isinstance(strats, list):
            continue
        # v22.8: el schema usa 'max_favorable_pct', no 'pct_missed'
        pct = float(opp.get('max_favorable_pct', 0) or 0)
        
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
    """Resumen por mercado, sin presentar win rate aislado como rentabilidad."""
    del worst_general, by_symbol, by_timeframe  # Las tablas contienen el detalle.
    lines = [
        f"Este informe usa una sola ventana coherente de <b>{REPORT_DAYS_BACK} días</b>. "
        "Spot y Futuros se evalúan por separado. Los Futuros sin procedencia "
        "verificable no pueden mejorar ni empeorar las estadísticas operables."
    ]
    metrics_by_market = metrics.get('metrics_by_market') or {}

    for market, label in (
        ('spot', 'SPOT — acumulación'),
        ('futures', 'FUTUROS — perpetuos verificados')
    ):
        values = metrics_by_market.get(market) or {}
        resolved = int(values.get('resolved') or 0)
        if resolved:
            wr = values.get('win_rate')
            expectancy_r = values.get('expectancy_r')
            avg_pnl = values.get('avg_pnl_pct')
            expectancy_text = (
                f'{expectancy_r:+.3f}R'
                if expectancy_r is not None else '—'
            )
            pnl_text = (
                f'{avg_pnl:+.3f}%'
                if avg_pnl is not None else '—'
            )
            lines.append(
                f"<br/><br/><b>{label}</b>: {resolved} salidas demostrables, "
                f"win rate {wr:.1f}%, expectancy observada "
                f"{expectancy_text} y movimiento bruto medio {pnl_text}."
            )
        else:
            lines.append(
                f"<br/><br/><b>{label}</b>: todavía no hay salidas "
                "demostrables suficientes para afirmar que existe rentabilidad."
            )
        lines.append(
            f" Pendientes: {int(values.get('pending') or 0)}; "
            f"expiradas: {int(values.get('expired') or 0)}; "
            f"ambiguas: {int(values.get('ambiguous') or 0)}; "
            f"setups inválidos: {int(values.get('invalid_setup') or 0)}."
        )

    quarantine = metrics.get('quarantine_counts') or {}
    lines.append(
        f"<br/><br/>Cuarentena informativa: "
        f"{int(quarantine.get('futures_legacy') or 0)} Futuros antiguos/no "
        f"verificables, {int(quarantine.get('futures_shadow') or 0)} análisis "
        f"shadow y {int(quarantine.get('unscoped') or 0)} registros sin mercado."
    )

    for market, label in (('spot', 'Spot'), ('futures', 'Futuros')):
        candidates = [
            item for item in top_general
            if item.get('market') == market
            and item.get('sample_size', 0) >= GENERAL_SAMPLES_RIGOROUS
        ]
        if candidates:
            best = max(candidates, key=lambda item: item['expectancy'])
            lines.append(
                f"<br/><br/><b>Mejor evidencia válida en {label}</b>: "
                f"{best['strategy']} con {best['expectancy']:+.3f}R por señal, "
                f"PnL bruto medio {best['avg_pnl_pct']:+.3f}% y "
                f"{best['sample_size']} resultados."
            )
        else:
            lines.append(
                f"<br/><br/>{label} aún no tiene una estrategia con "
                f"{GENERAL_SAMPLES_RIGOROUS} resultados demostrables."
            )

    lines.append(
        "<br/><br/><i>El PnL mostrado todavía es bruto: no descuenta comisión, "
        "slippage ni funding. Por eso este informe no lo llama beneficio neto.</i>"
    )
    return ''.join(lines)


# ============================================================================
# FETCH DE MÉTRICAS GLOBALES (usando .count real)
# ============================================================================

def _fetch_learning_data() -> Dict:
    """Recupera todo el conocimiento actual del ReviewTrader desde Supabase."""
    data = {
        'supabase_connected': False,
        'report_window_days': REPORT_DAYS_BACK,
        'all_time_signals': 0,
        'total_signals': 0,
        'evaluated_signals': 0,
        'pending_signals': 0,
        'tp_hit': 0,
        'sl_hit': 0,
        'expired': 0,
        'missed_opp_from_signals': 0,
        'missed_opportunities': 0,
        'signals_with_indicators': [],
        'metrics_by_market': {},
        'quarantine_counts': {},
        'futures_shadow_analysis': {},
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
    
    # El total histórico se muestra sólo como inventario; no se mezcla con la
    # ventana estadística del informe.
    try:
        r_total = (db.client.table('signals').select('id', count='exact').limit(1).execute())
        data['all_time_signals'] = int(getattr(r_total, 'count', 0) or 0)
    except Exception as e:
        logger.warning(f'Error contando signals: {e}')
    
    # Missed opportunities dedicated table
    try:
        r = db.client.table('missed_opportunities').select('id', count='exact').limit(1).execute()
        data['missed_opportunities'] = int(getattr(r, 'count', None) or 0)
    except Exception:
        pass
    
    # Traer una sola ventana y separar las cohortes antes de calcular cualquier
    # win rate. Así el encabezado y las tablas hablan del mismo conjunto.
    try:
        report_signals = _fetch_all_signals_with_indicators(
            db,
            days_back=REPORT_DAYS_BACK
        )
        cohorts = _split_learning_cohorts(report_signals)
        eligible_signals = (
            cohorts['spot']
            + cohorts['futures_verified']
        )
        spot_metrics = _market_metrics(cohorts['spot'])
        futures_metrics = _market_metrics(cohorts['futures_verified'])
        data['signals_with_indicators'] = eligible_signals
        data['metrics_by_market'] = {
            'spot': spot_metrics,
            'futures': futures_metrics
        }
        data['quarantine_counts'] = {
            'futures_legacy': len(cohorts['futures_legacy']),
            'futures_shadow': len(cohorts['futures_shadow']),
            'unscoped': len(cohorts['unscoped'])
        }
        data['futures_shadow_analysis'] = _calc_shadow_futures_analysis(
            cohorts['futures_shadow']
        )
        data['total_signals'] = len(eligible_signals)
        data['pending_signals'] = (
            spot_metrics['pending'] + futures_metrics['pending']
        )
        data['tp_hit'] = spot_metrics['tp_hit'] + futures_metrics['tp_hit']
        data['sl_hit'] = spot_metrics['sl_hit'] + futures_metrics['sl_hit']
        data['expired'] = spot_metrics['expired'] + futures_metrics['expired']
        data['evaluated_signals'] = (
            data['tp_hit'] + data['sl_hit'] + data['expired']
        )
        data['missed_opp_from_signals'] = sum(
            1 for signal in eligible_signals
            if signal.get('status') == 'missed_opportunity'
        )
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
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        KeepTogether
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
    
    # ============ 3. MÉTRICAS COHERENTES POR MERCADO ============
    story.append(Paragraph("Métricas por mercado", style_h2))
    spot_metrics = data.get('metrics_by_market', {}).get('spot', {})
    futures_metrics = data.get('metrics_by_market', {}).get('futures', {})
    quarantine = data.get('quarantine_counts', {})

    def _metric_text(value, suffix=''):
        return '—' if value is None else f'{value}{suffix}'

    metrics_data = [
        ['Métrica', 'Valor'],
        ['Inventario histórico total (no usado como cohorte)', str(data['all_time_signals'])],
        [f'Cohorte estadística verificable ({REPORT_DAYS_BACK} días)', str(data['total_signals'])],
        ['SPOT — señales en cohorte', str(spot_metrics.get('total', 0))],
        ['   — TP / SL / Expired', (
            f"{spot_metrics.get('tp_hit', 0)} / "
            f"{spot_metrics.get('sl_hit', 0)} / "
            f"{spot_metrics.get('expired', 0)}"
        )],
        ['   — Win rate / Expectancy observada', (
            f"{_metric_text(spot_metrics.get('win_rate'), '%')} / "
            f"{_metric_text(spot_metrics.get('expectancy_r'), 'R')}"
        )],
        ['FUTUROS — ejecutables y verificables', str(futures_metrics.get('total', 0))],
        ['   — TP / SL / Expired', (
            f"{futures_metrics.get('tp_hit', 0)} / "
            f"{futures_metrics.get('sl_hit', 0)} / "
            f"{futures_metrics.get('expired', 0)}"
        )],
        ['   — Win rate / Expectancy observada', (
            f"{_metric_text(futures_metrics.get('win_rate'), '%')} / "
            f"{_metric_text(futures_metrics.get('expectancy_r'), 'R')}"
        )],
        ['Resultados ambiguos (Spot / Futuros)', (
            f"{spot_metrics.get('ambiguous', 0)} / "
            f"{futures_metrics.get('ambiguous', 0)}"
        )],
        ['Futuros antiguos/no verificables en cuarentena', str(quarantine.get('futures_legacy', 0))],
        ['Análisis Futures shadow (no publicados)', str(quarantine.get('futures_shadow', 0))],
        ['Registros sin mercado en cuarentena', str(quarantine.get('unscoped', 0))],
        ['Oportunidades perdidas (diagnóstico no separado)', str(data['missed_opportunities'])],
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
    
    # ============ 4. FUTURES SHADOW — DIAGNÓSTICO DE TIMIDEZ ============
    shadow = data.get('futures_shadow_analysis') or {}
    shadow_summary = shadow.get('summary') or {}

    story.append(Paragraph(
        "FUTURES — aprendizaje Shadow (diagnóstico de timidez)",
        style_h2
    ))
    story.append(Paragraph(
        "Esta sección estudia análisis de Futuros <b>reales, de perpetuos y vela "
        "cerrada</b> que NO superaron la publicación. Son observaciones hipotéticas: "
        "<b>no son operaciones autorizadas</b>, no entran al win rate oficial y no "
        "pueden modificar pesos, Safety, Entry, SL, TP ni leverage. Su función es "
        "descubrir si alguna puerta de publicación podría estar descartando edge.",
        style_body
    ))

    if shadow_summary.get('total'):
        def _shadow_metric_text(value, suffix=''):
            return '—' if value is None else f'{value}{suffix}'

        shadow_metrics_rows = [
            ['Métrica Shadow', 'Valor'],
            ['Observaciones limpias no publicadas',
             str(shadow_summary.get('total', 0))],
            ['Candidatos LONG/SHORT',
             str(shadow_summary.get('directional', 0))],
            ['Con Entry + SL + TP geométricamente válidos',
             str(shadow_summary.get('valid_geometry', 0))],
            ['Entry demostrado / No Entry / Indeterminado', (
                f"{shadow_summary.get('entry_touched', 0)} / "
                f"{shadow_summary.get('no_entry', 0)} / "
                f"{shadow_summary.get('entry_unknown', 0)}"
            )],
            ['TP / SL / Expired / Ambiguous', (
                f"{shadow_summary.get('tp_hit', 0)} / "
                f"{shadow_summary.get('sl_hit', 0)} / "
                f"{shadow_summary.get('expired', 0)} / "
                f"{shadow_summary.get('ambiguous', 0)}"
            )],
            ['Win rate hipotético / Expectancy R', (
                f"{_shadow_metric_text(shadow_summary.get('win_rate'), '%')} / "
                f"{_shadow_metric_text(shadow_summary.get('expectancy_r'), 'R')}"
            )],
            ['PnL bruto medio de resultados TP/SL',
             _shadow_metric_text(shadow_summary.get('avg_pnl_pct'), '%')],
        ]

        tshadow = Table(shadow_metrics_rows, colWidths=[11*cm, 5*cm])
        tshadow.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#6c4ab6')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9.3),
            ('GRID', (0,0), (-1,-1), 0.35, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f6f2ff'), white]),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(tshadow)

        if shadow.get('by_safety'):
            story.append(Paragraph("Shadow por banda de Execution Safety", style_h3))
            story.append(Paragraph(
                "Las bandas 65-69 y 70-74 son diagnósticas. El motor operativo "
                "permanece sin cambios. Una banda sólo debería promoverse si acumula "
                "muestra suficiente, expectancy positiva neta y valida después en "
                "walk-forward.",
                style_note
            ))
            rows = [['Safety', 'N', 'Entry', 'TP', 'SL', 'WR %', 'Exp. R']]
            for row in shadow.get('by_safety') or []:
                rows.append([
                    row.get('bucket', '—'),
                    str(row.get('total', 0)),
                    str(row.get('entry_touched', 0)),
                    str(row.get('tp_hit', 0)),
                    str(row.get('sl_hit', 0)),
                    '—' if row.get('win_rate') is None else f"{row.get('win_rate'):.1f}",
                    '—' if row.get('expectancy_r') is None else f"{row.get('expectancy_r'):+.3f}",
                ])
            tsafety = Table(
                rows,
                colWidths=[2.2*cm, 1.5*cm, 1.7*cm, 1.4*cm, 1.4*cm, 1.7*cm, 2.0*cm]
            )
            tsafety.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), HexColor('#3f51b5')),
                ('TEXTCOLOR', (0,0), (-1,0), white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 8.5),
                ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f3f5ff'), white]),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ]))
            story.append(tsafety)

        if shadow.get('reference_flags'):
            story.append(Paragraph(
                "Métricas por debajo de bandas de referencia",
                style_h3
            ))
            story.append(Paragraph(
                "Estas banderas se reconstruyen con los valores que ReviewTrader "
                "sí guardó. <b>No equivalen al motivo exacto histórico de rechazo</b>, "
                "porque la lista completa del publication gate no se persiste todavía. "
                "Sirven para localizar qué métrica merece una auditoría posterior.",
                style_note
            ))
            rows = [['Banda observada', 'Casos']]
            for label, count in shadow.get('reference_flags') or []:
                rows.append([label, str(count)])
            tflags = Table(rows, colWidths=[11*cm, 3*cm])
            tflags.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), HexColor('#e8a500')),
                ('TEXTCOLOR', (0,0), (-1,0), white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#fff9e6'), white]),
            ]))
            story.append(tflags)

        if shadow.get('quant_available'):
            story.append(Paragraph("Contexto cuantitativo Shadow", style_h3))
            story.append(Paragraph(
                f"{int(shadow.get('quant_available') or 0)} candidatos ya contienen "
                "el snapshot cuantitativo del Commit 22. Sigue en modo observación: "
                "ninguna fila de esta tabla puede aprobar o rechazar una operación.",
                style_note
            ))
            quant_rows = shadow.get('by_quant_regime') or []
            if quant_rows:
                rows = [['Régimen', 'N', 'TP', 'SL', 'WR %', 'Exp. R']]
                for row in quant_rows[:10]:
                    rows.append([
                        str(row.get('regime') or 'UNAVAILABLE')[:24],
                        str(row.get('total', 0)),
                        str(row.get('tp_hit', 0)),
                        str(row.get('sl_hit', 0)),
                        '—' if row.get('win_rate') is None else f"{row.get('win_rate'):.1f}",
                        '—' if row.get('expectancy_r') is None else f"{row.get('expectancy_r'):+.3f}",
                    ])
                tq = Table(
                    rows,
                    colWidths=[5.2*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.7*cm, 2.0*cm]
                )
                tq.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), HexColor('#00838f')),
                    ('TEXTCOLOR', (0,0), (-1,0), white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8.5),
                    ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#edfafa'), white]),
                    ('ALIGN', (1,0), (-1,-1), 'CENTER'),
                ]))
                story.append(tq)
    else:
        story.append(Paragraph(
            "<i>Todavía no hay observaciones Shadow Futures limpias dentro de la "
            "ventana del informe. Esto no es un error del PDF: significa que la "
            "cohorte nueva aún no tiene registros disponibles.</i>",
            style_body
        ))

    story.append(Paragraph(
        "<b>Regla de interpretación:</b> un Shadow que habría tocado TP no prueba "
        "por sí solo que debió publicarse. Para relajar Futuros necesitaremos una "
        "cohorte suficiente, expectancy positiva después de costos y validación "
        "walk-forward. Hasta entonces la política operativa permanece intacta.",
        style_note
    ))
    story.append(PageBreak())

    # ============ 4. TOP 20 MEJORES ESTRATEGIAS GENERALES ============
    story.append(Paragraph("Mejores estrategias por mercado", style_h2))
    story.append(Paragraph(
        "Spot y Futuros permanecen separados. La <b>Expectancy R</b> es el "
        "promedio de los resultados R propios de cada señal; ya no supone que "
        "todas las ganadoras valen +2R. El PnL es bruto, antes de costos. "
        "La columna 'Confianza estadística' indica si la muestra es suficiente para "
        f"tomar la métrica como válida (≥{GENERAL_SAMPLES_RIGOROUS} muestras).",
        style_note
    ))
    
    top_general = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_general
            if s['market'] == market
            and s['sample_size'] >= GENERAL_SAMPLES_MIN
        ]
        top_general.extend(
            sorted(market_rows, key=lambda r: (-r['expectancy'], -r['sample_size']))[:10]
        )
    if top_general:
        rows = [['#', 'Mercado', 'Estrategia', 'N', 'TP', 'SL', 'Win %', 'Exp. R', 'PnL %', 'Confianza']]
        for i, s in enumerate(top_general, 1):
            badge_txt, _ = _confidence_badge(s['sample_size'], GENERAL_SAMPLES_RIGOROUS)
            rows.append([
                str(i), s['market'].upper(), s['strategy'][:27], str(s['sample_size']),
                str(s['wins']), str(s['losses']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%", badge_txt
            ])
        t = Table(rows, colWidths=[0.6*cm, 1.6*cm, 4.2*cm, 0.9*cm, 0.8*cm,
                                  0.8*cm, 1.2*cm, 1.2*cm, 1.4*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#0a8f4c')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-2,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Aún no hay estrategias con al menos {GENERAL_SAMPLES_MIN} muestras evaluadas.</i>",
            style_body
        ))
    
    # ============ 5. TOP 20 PEORES ESTRATEGIAS GENERALES ============
    story.append(Paragraph("Estrategias con peor evidencia por mercado", style_h2))
    story.append(Paragraph(
        "Se muestran por separado y se ordenan por Expectancy R observada. Una "
        "muestra preliminar sirve para investigar, no para cambiar pesos automáticamente.",
        style_note
    ))
    
    worst_general = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_general
            if s['market'] == market
            and s['sample_size'] >= GENERAL_SAMPLES_MIN
        ]
        worst_general.extend(
            sorted(market_rows, key=lambda r: (r['expectancy'], -r['sample_size']))[:10]
        )
    if worst_general:
        rows = [['#', 'Mercado', 'Estrategia', 'N', 'TP', 'SL', 'Win %', 'Exp. R', 'PnL %', 'Confianza']]
        for i, s in enumerate(worst_general, 1):
            badge_txt, _ = _confidence_badge(s['sample_size'], GENERAL_SAMPLES_RIGOROUS)
            rows.append([
                str(i), s['market'].upper(), s['strategy'][:27], str(s['sample_size']),
                str(s['wins']), str(s['losses']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%", badge_txt
            ])
        t = Table(rows, colWidths=[0.6*cm, 1.6*cm, 4.2*cm, 0.9*cm, 0.8*cm,
                                  0.8*cm, 1.2*cm, 1.2*cm, 1.4*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#c92a2a')),
            ('TEXTCOLOR', (0,0), (-1,0), white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#c8ccd6')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#f4f6fa'), white]),
            ('ALIGN', (1,1), (-2,-1), 'CENTER'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(
            f"<i>Sin datos suficientes aún.</i>", style_body
        ))
    
    story.append(PageBreak())
    
    # ============ 6. APRENDIZAJE ESPECÍFICO ============
    story.append(Paragraph("Combinaciones específicas por mercado", style_h2))
    story.append(Paragraph(
        "Aprendizaje más granular: dónde exactamente rinde cada estrategia. "
        f"Requiere ≥{SPECIFIC_SAMPLES_MIN} muestras para aparecer, ≥{SPECIFIC_SAMPLES_RIGOROUS} para ser 'válida'.",
        style_note
    ))
    
    top_specific = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_specific
            if s['market'] == market
            and s['sample_size'] >= SPECIFIC_SAMPLES_MIN
        ]
        top_specific.extend(
            sorted(market_rows, key=lambda r: (-r['expectancy'], -r['sample_size']))[:8]
        )
    if top_specific:
        rows = [['Mercado', 'Par', 'TF', 'Acción', 'Estrategia', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in top_specific:
            rows.append([
                s['market'].upper(), s['symbol'], s['timeframe'], s['action'],
                s['strategy'][:20], str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.6*cm, 2.0*cm, 1.0*cm, 1.5*cm, 3.6*cm,
                                  0.8*cm, 1.2*cm, 1.3*cm, 1.5*cm])
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
    story.append(Paragraph("Peores combinaciones específicas por mercado", style_h2))
    worst_specific = []
    for market in ('spot', 'futures'):
        market_rows = [
            s for s in stats_specific
            if s['market'] == market
            and s['sample_size'] >= SPECIFIC_SAMPLES_MIN
        ]
        worst_specific.extend(
            sorted(market_rows, key=lambda r: (r['expectancy'], -r['sample_size']))[:8]
        )
    if worst_specific:
        rows = [['Mercado', 'Par', 'TF', 'Acción', 'Estrategia', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in worst_specific:
            rows.append([
                s['market'].upper(), s['symbol'], s['timeframe'], s['action'],
                s['strategy'][:20], str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.6*cm, 2.0*cm, 1.0*cm, 1.5*cm, 3.6*cm,
                                  0.8*cm, 1.2*cm, 1.3*cm, 1.5*cm])
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
    
    # ============ v22: 7. ESTRATEGIAS POR TRADER (auditoría del comité) ============
    # Permite al usuario verificar que cada uno de los 10 traders está
    # aportando estrategias distintas y qué performance tiene cada uno.
    story.append(Paragraph("Estrategias por trader (cobertura del comité)", style_h2))
    story.append(Paragraph(
        "Cada uno de los 10 traders del sistema emite un conjunto de estrategias distintas. "
        "La contribución se separa por mercado. Esta tabla muestra <b>qué está aportando cada trader</b>: cuántas estrategias diferentes "
        "ha emitido, cuántas señales resueltas tiene y su win rate. Si un trader tiene 0 señales, "
        "significa que no ha aportado en el período — puede indicar que no encuentra setups o que "
        "sus estrategias están silenciadas por el régimen de mercado actual.",
        style_body
    ))
    
    stats_by_trader = _calc_stats_by_trader(signals_with_ind) if signals_with_ind else []
    if stats_by_trader:
        rows = [['Mercado', 'Trader', '# Estr.', 'Señales', 'TP', 'SL', 'Expired', 'Win %']]
        for s in stats_by_trader:
            active_mark = '' if s['signals'] > 0 else ' (inactivo)'
            rows.append([
                s['market'].upper(),
                s['trader'] + active_mark,
                str(s['unique_strategies']),
                str(s['signals']),
                str(s['wins']),
                str(s['losses']),
                str(s['expired']),
                f"{s['win_rate']}%" if s['signals'] > 0 else '—'
            ])
        t = Table(rows, colWidths=[1.7*cm, 3.8*cm, 1.4*cm, 1.5*cm, 1.0*cm,
                                  1.0*cm, 1.5*cm, 1.4*cm])
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
        story.append(Spacer(1, 8))
        
        # Detalle: estrategias emitidas por cada trader activo
        trader_details = [
            Paragraph("Estrategias emitidas por cada trader (detalle)", style_h3)
        ]
        for s in stats_by_trader:
            if s['unique_strategies'] == 0:
                continue
            strategies_str = ', '.join(s['strategies'])
            trader_details.append(Paragraph(
                f"<b>[{s['market'].upper()}] {s['trader']}</b> "
                f"({s['unique_strategies']} estrategias): "
                f"<font color='#555'>{strategies_str}</font>",
                style_note
            ))
        story.append(KeepTogether(trader_details))
    else:
        story.append(Paragraph("<i>Sin datos suficientes — el sistema aún no ha resuelto señales.</i>", style_body))
    
    # ============ 8. APRENDIZAJE POR PAR ============
    story.append(Paragraph("Aprendizaje por par y mercado", style_h2))
    if stats_by_symbol:
        rows = [['Mercado', 'Par', 'TP', 'SL', 'Expired', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in stats_by_symbol:
            rows.append([
                s['market'].upper(), s['symbol'], str(s['wins']), str(s['losses']),
                str(s['expired']), str(s['sample_size']), f"{s['win_rate']}%",
                f"{s['expectancy']:+.3f}", f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.8*cm, 2.3*cm, 1.0*cm, 1.0*cm, 1.4*cm,
                                  1.0*cm, 1.3*cm, 1.3*cm, 1.5*cm])
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
    story.append(Paragraph("Aprendizaje por timeframe y mercado", style_h2))
    if stats_by_tf:
        rows = [['Mercado', 'Timeframe', 'TP', 'SL', 'Expired', 'N', 'Win %', 'Exp. R', 'PnL %']]
        for s in stats_by_tf:
            rows.append([
                s['market'].upper(), s['timeframe'], str(s['wins']),
                str(s['losses']), str(s['expired']), str(s['sample_size']),
                f"{s['win_rate']}%", f"{s['expectancy']:+.3f}",
                f"{s['avg_pnl_pct']:+.3f}%"
            ])
        t = Table(rows, colWidths=[1.8*cm, 2.0*cm, 1.0*cm, 1.0*cm, 1.4*cm,
                                  1.0*cm, 1.3*cm, 1.3*cm, 1.5*cm])
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
        f"dirección clara. La tabla histórica no identifica de forma fiable Spot/Futuros "
        f"ni demuestra que la entrada hubiese sido ejecutable. Por eso se usa sólo para "
        f"formular hipótesis y no para subir pesos automáticamente.",
        style_body
    ))
    
    if missed_analysis['top_indicators']:
        story.append(Paragraph("Top 15 indicadores/estrategias más frecuentes en oportunidades perdidas", style_h3))
        story.append(Paragraph(
            "Cuando estos indicadores estaban activos, el sistema no operó pero el mercado sí se movió. "
            "La frecuencia por sí sola <b>no prueba rentabilidad</b>: falta confirmar Entry, "
            "SL, TP, costos y mercado de procedencia.",
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
            "cuando el sistema no toma la operación pero el precio sí se mueve. Son candidatos "
            "para pruebas posteriores, <b>no señales autorizadas de trade</b>.",
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
        f"<br/>• El win rate es descriptivo: no demuestra rentabilidad sin tamaño de "
        f"ganancias, pérdidas y costos."
        f"<br/>• Expectancy R = promedio de cada resultado dividido por el riesgo "
        f"Entry–SL de esa misma señal; no se supone RR fijo 2:1."
        f"<br/><br/>"
        f"<b>Cómo se aprende:</b>"
        f"<br/>• El learning worker corre cada 15 minutos: evalúa señales pendientes y "
        f"marca TP, SL, expiración, ambigüedad o setup inválido."
        f"<br/>• TP y SL en la misma vela no cuentan como win ni loss hasta resolver "
        f"su orden con datos más finos."
        f"<br/>• Las estadísticas OPERABLES de Futuros sólo usan contratos perpetuos "
        f"reales, vela fuente cerrada y señales que superaron el filtro de publicación. "
        f"El legado queda en cuarentena."
        f"<br/>• Los análisis Futures limpios que no superaron publicación se conservan "
        f"como SHADOW para estudiar timidez/filtros, pero no cambian pesos ni win rate oficial."
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
        f"aún no ajustan automáticamente las decisiones — es información para el operador humano."
        f"<br/>• El PnL de este informe es bruto. Comisión, slippage y funding se "
        f"incorporarán en la siguiente fase económica.",
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
