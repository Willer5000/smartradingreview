"""Commit 13 — Entry / SL / TP Challenger Lab.

All candidates are SHADOW.  They reuse the same closed OHLCV already loaded by
the analysis/evaluation workers and never alter the published Entry, SL, TP,
Safety, leverage or direction.  Their purpose is to compare defensibility and
net-execution geometry before any later governed promotion.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional
import math

import pandas as pd

from learning_integrity import learning_context, latest_result, normalize_action, normalize_market, safe_float

CHALLENGER_LAB_VERSION = "C13_EXECUTION_CHALLENGER_LAB_V1"


def _positive(value: Any) -> Optional[float]:
    number = safe_float(value)
    return number if number is not None and number > 0 else None


def _atr(df: pd.DataFrame, fallback: Optional[float] = None) -> Optional[float]:
    try:
        if df is None or len(df) < 3:
            return fallback
        high = pd.to_numeric(df['high'], errors='coerce')
        low = pd.to_numeric(df['low'], errors='coerce')
        close = pd.to_numeric(df['close'], errors='coerce')
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        value = float(tr.tail(14).mean())
        return value if math.isfinite(value) and value > 0 else fallback
    except Exception:
        return fallback


def _candidate(name: str, entry: Any, sl: Any, tp: Any, action: str, source: str, *, available=True, reason=None) -> Dict[str, Any]:
    entry = _positive(entry)
    sl = _positive(sl)
    tp = _positive(tp)
    action = normalize_action(action)
    valid = bool(available and action in {'LONG', 'SHORT'} and entry and sl and tp)
    rr = None
    if valid:
        if action == 'LONG':
            valid = sl < entry < tp
        else:
            valid = tp < entry < sl
        if valid:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else None
            valid = bool(rr and math.isfinite(rr) and rr > 0)
    return {
        'name': name,
        'mode': 'SHADOW_ONLY',
        'available': bool(available),
        'geometry_valid': bool(valid),
        'action': action,
        'entry': round(entry, 10) if entry is not None else None,
        'stop_loss': round(sl, 10) if sl is not None else None,
        'take_profit': round(tp, 10) if tp is not None else None,
        'risk_reward': round(rr, 4) if rr is not None else None,
        'source': source,
        'reason': str(reason or '')[:220],
        'affects_production': False,
    }


def _strategy_text(analysis: Dict[str, Any]) -> str:
    decision = analysis.get('decision') or {}
    audit = decision.get('audit') or {}
    chunks = []
    chunks.extend(str(v) for v in (decision.get('estrategias') or []))
    chunks.extend(str(v) for v in (decision.get('razones') or []))
    if isinstance(audit, dict):
        for vote in audit.get('votes') or []:
            if not isinstance(vote, dict):
                continue
            chunks.extend(str(v) for v in (vote.get('strategies') or []))
            chunks.extend(str(v) for v in (vote.get('reasons') or []))
    return ' '.join(chunks).upper()


def _retest_level(strategy_lab: Dict[str, Any]) -> Optional[float]:
    strategies = strategy_lab.get('strategies') or {}
    retest = strategies.get('breakout_retest') if isinstance(strategies, dict) else {}
    if not isinstance(retest, dict):
        return None
    for key in ('retest_price', 'breakout_level', 'level', 'price', 'zone_price'):
        value = _positive(retest.get(key))
        if value is not None:
            return value
    return None


def build_execution_challenger_lab(analysis: Dict[str, Any], df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    analysis = analysis if isinstance(analysis, dict) else {}
    action = normalize_action((analysis.get('decision') or {}).get('action'))
    levels = analysis.get('levels') or {}
    baseline_entry = _positive(levels.get('entry'))
    baseline_sl = _positive(levels.get('stop_loss'))
    baseline_tp = _positive(levels.get('take_profit'))
    current = _positive(analysis.get('analysis_price') or analysis.get('current_price'))
    market = str(analysis.get('system_type') or 'spot').upper()

    baseline = _candidate('BASELINE', baseline_entry, baseline_sl, baseline_tp, action, 'PRODUCTION_BASELINE')
    candidates = [baseline]
    if action not in {'LONG', 'SHORT'} or not baseline['geometry_valid'] or df is None or len(df) < 8:
        return {
            'version': CHALLENGER_LAB_VERSION,
            'authority': 'SHADOW_ONLY', 'production_change': False,
            'market': market, 'action': action, 'candidates': candidates,
            'status': 'INSUFFICIENT_GEOMETRY_OR_DATA',
        }

    work = df.tail(min(30, len(df))).copy()
    high = pd.to_numeric(work['high'], errors='coerce')
    low = pd.to_numeric(work['low'], errors='coerce')
    close = pd.to_numeric(work['close'], errors='coerce')
    work = work.assign(high=high, low=low, close=close).dropna(subset=['high', 'low', 'close'])
    if len(work) < 8:
        return {
            'version': CHALLENGER_LAB_VERSION,
            'authority': 'SHADOW_ONLY', 'production_change': False,
            'market': market, 'action': action, 'candidates': candidates,
            'status': 'INSUFFICIENT_CLEAN_OHLCV',
        }

    atr = _atr(work, fallback=abs(baseline_entry - baseline_sl)) or abs(baseline_entry - baseline_sl)
    recent8 = work.tail(8)
    recent20 = work.tail(min(20, len(work)))
    swing_low = float(recent8['low'].min())
    swing_high = float(recent8['high'].max())
    range_low = float(recent20['low'].min())
    range_high = float(recent20['high'].max())
    current = current or float(work['close'].iloc[-1])

    # A — maximum defensibility: wait closer to a recent structural extreme and
    # put invalidation beyond it. This may reduce activation; that trade-off is
    # exactly what the lab must measure.
    if action == 'LONG':
        a_entry = min(current, max(swing_low + 0.20 * atr, baseline_entry - 0.35 * atr))
        a_sl = min(baseline_sl, swing_low - 0.20 * atr)
        a_tp = max(baseline_tp, swing_high) if swing_high > a_entry else baseline_tp
    else:
        a_entry = max(current, min(swing_high - 0.20 * atr, baseline_entry + 0.35 * atr))
        a_sl = max(baseline_sl, swing_high + 0.20 * atr)
        a_tp = min(baseline_tp, swing_low) if swing_low < a_entry else baseline_tp
    candidates.append(_candidate('DEFENSIBILITY', a_entry, a_sl, a_tp, action, 'RECENT_SWING_PLUS_ATR'))

    # B — liquidity/sweep/MSS/POI is only emitted when the existing committee
    # actually observed institutional evidence. No SMC signal is fabricated.
    evidence = _strategy_text(analysis)
    smc_present = any(token in evidence for token in ('SWEEP', 'MSS', 'ORDER BLOCK', 'ORDER_BLOCK', 'FVG', 'DISPLACEMENT', 'LIQUIDITY'))
    if smc_present and range_high > range_low:
        if action == 'LONG':
            b_entry = min(current, range_low + (range_high - range_low) * 0.35)
            b_sl = range_low - 0.20 * atr
            b_tp = max(b_entry + abs(b_entry - b_sl) * 1.8, range_high)
        else:
            b_entry = max(current, range_low + (range_high - range_low) * 0.65)
            b_sl = range_high + 0.20 * atr
            b_tp = min(b_entry - abs(b_entry - b_sl) * 1.8, range_low)
        candidates.append(_candidate('LIQUIDITY_SWEEP_MSS_POI', b_entry, b_sl, b_tp, action, 'OBSERVED_SMC_EVIDENCE_PLUS_RANGE', reason='Only emitted because current analysis contains SMC/liquidity evidence'))

    # C — breakout/retest/trendline candidate, only when Strategy Lab supplied a
    # usable retest level. A missing level remains missing; it is not guessed.
    strategy_lab = analysis.get('strategy_lab') or {}
    retest = _retest_level(strategy_lab if isinstance(strategy_lab, dict) else {})
    if retest is not None:
        if action == 'LONG':
            c_entry = min(current, retest)
            c_sl = min(baseline_sl, c_entry - max(0.75 * atr, abs(c_entry - baseline_sl)))
            c_tp = max(baseline_tp, c_entry + abs(c_entry - c_sl) * 1.8)
        else:
            c_entry = max(current, retest)
            c_sl = max(baseline_sl, c_entry + max(0.75 * atr, abs(c_entry - baseline_sl)))
            c_tp = min(baseline_tp, c_entry - abs(c_entry - c_sl) * 1.8)
        candidates.append(_candidate('TRENDLINE_RETEST', c_entry, c_sl, c_tp, action, 'STRATEGY_LAB_RETEST_LEVEL'))

    # D — use the specialist committee only when its SHADOW simulation agrees
    # with the baseline direction. It changes geometry, never direction.
    register = (analysis.get('decision') or {}).get('registro_votacion') or {}
    committee = register.get('dynamic_expert_committee_shadow') if isinstance(register, dict) else {}
    if isinstance(committee, dict) and str(committee.get('shadow_action') or '').upper() == str((analysis.get('decision') or {}).get('action') or '').upper():
        if action == 'LONG':
            d_entry = min(current, baseline_entry - 0.20 * atr)
            d_sl = min(baseline_sl, swing_low - 0.15 * atr)
            d_tp = max(baseline_tp, d_entry + abs(d_entry - d_sl) * 1.8)
        else:
            d_entry = max(current, baseline_entry + 0.20 * atr)
            d_sl = max(baseline_sl, swing_high + 0.15 * atr)
            d_tp = min(baseline_tp, d_entry - abs(d_entry - d_sl) * 1.8)
        candidates.append(_candidate('SPECIALIST_COMMITTEE', d_entry, d_sl, d_tp, action, 'C12_SHADOW_AGREEMENT'))

    # Maximum four total candidates (Baseline + up to three challengers) to
    # limit multiple-testing and memory. Prefer structural candidates first.
    candidates = candidates[:4]
    return {
        'version': CHALLENGER_LAB_VERSION,
        'authority': 'SHADOW_ONLY',
        'production_change': False,
        'market': market,
        'action': action,
        'atr_reference': round(float(atr), 10),
        'candidates': candidates,
        'status': 'OBSERVING',
        'policy': {
            'max_candidates_per_signal': 4,
            'no_stop_widening_in_production': True,
            'no_direction_change': True,
            'compare_activation_mfe_mae_tp_sl_expectancy': True,
            'promotion_path': 'HISTORICAL_WALK_FORWARD_SHADOW_CHALLENGER_CANARY_ACTIVE',
        },
    }


def evaluate_execution_challengers(signal: Dict[str, Any], df: pd.DataFrame, evaluation_start, evaluation_end) -> Dict[str, Any]:
    """Evaluate C13 candidates on the same candles already fetched by learning."""
    learning = learning_context(signal)
    lab = learning.get('execution_challenger_lab') or {}
    candidates = lab.get('candidates') if isinstance(lab, dict) else []
    if not isinstance(candidates, list) or not candidates:
        return {}

    frame = df
    try:
        if 'time' in df.columns:
            times = pd.to_datetime(df['time'], utc=True, errors='coerce')
            start = pd.Timestamp(evaluation_start)
            end = pd.Timestamp(evaluation_end)
            start = start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
            end = end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
            frame = df[(times >= start) & (times < end)]
    except Exception:
        frame = df

    results = []
    for candidate in candidates[:4]:
        if not isinstance(candidate, dict) or not candidate.get('geometry_valid'):
            continue
        action = normalize_action(candidate.get('action'))
        entry = _positive(candidate.get('entry'))
        sl = _positive(candidate.get('stop_loss'))
        tp = _positive(candidate.get('take_profit'))
        if action not in {'LONG', 'SHORT'} or not entry or not sl or not tp:
            continue
        risk = abs(entry - sl)
        if risk <= 0:
            continue

        entered = False
        candles_to_entry = 0
        candles_after_entry = 0
        mfe = 0.0
        mae = 0.0
        status = 'expired_no_entry'
        realized = None

        for idx, (_, candle) in enumerate(frame.iterrows(), start=1):
            high = safe_float(candle.get('high'))
            low = safe_float(candle.get('low'))
            if high is None or low is None:
                continue
            if not entered:
                touched = low <= entry if action == 'LONG' else high >= entry
                if not touched:
                    continue
                entered = True
                candles_to_entry = idx
            candles_after_entry += 1

            if action == 'LONG':
                mfe = max(mfe, max(0.0, (high - entry) / risk))
                mae = max(mae, max(0.0, (entry - low) / risk))
                tp_hit = high >= tp
                sl_hit = low <= sl
            else:
                mfe = max(mfe, max(0.0, (entry - low) / risk))
                mae = max(mae, max(0.0, (high - entry) / risk))
                tp_hit = low <= tp
                sl_hit = high >= sl

            if tp_hit and sl_hit:
                status = 'ambiguous'
                realized = None
                break
            if sl_hit:
                status = 'sl_hit'
                realized = -1.0
                break
            if tp_hit:
                status = 'tp_hit'
                realized = abs(tp - entry) / risk
                break

        if entered and status == 'expired_no_entry':
            status = 'expired_after_entry'

        results.append({
            'name': str(candidate.get('name') or 'UNKNOWN'),
            'status': status,
            'entry_reached': entered,
            'candles_to_entry': candles_to_entry,
            'candles_after_entry': candles_after_entry,
            'mfe_r': round(mfe, 4),
            'mae_r': round(mae, 4),
            'realized_r': round(realized, 4) if realized is not None else None,
            'risk_reward': candidate.get('risk_reward'),
        })

    return {
        'version': CHALLENGER_LAB_VERSION,
        'authority': 'SHADOW_ONLY',
        'production_change': False,
        'results': results,
    }


def summarize_execution_challenger_evidence(scoped_rows: Dict[str, Iterable[Dict[str, Any]]]) -> Dict[str, Any]:
    groups = defaultdict(lambda: {'n': 0, 'entry': 0, 'tp': 0, 'sl': 0, 'ambiguous': 0, 'r_sum': 0.0, 'r_n': 0, 'mfe_sum': 0.0, 'mae_sum': 0.0})
    for rows in (scoped_rows or {}).values():
        for row in rows or []:
            market = normalize_market(row).upper() or 'UNKNOWN'
            result = latest_result(row)
            evaluation = result.get('execution_challenger_results') or {}
            items = evaluation.get('results') if isinstance(evaluation, dict) else []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or 'UNKNOWN')
                g = groups[(market, name)]
                g['n'] += 1
                g['entry'] += int(bool(item.get('entry_reached')))
                status = str(item.get('status') or '')
                if status == 'tp_hit': g['tp'] += 1
                elif status == 'sl_hit': g['sl'] += 1
                elif status == 'ambiguous': g['ambiguous'] += 1
                r = safe_float(item.get('realized_r'))
                if r is not None:
                    g['r_sum'] += r; g['r_n'] += 1
                mfe = safe_float(item.get('mfe_r'))
                mae = safe_float(item.get('mae_r'))
                if mfe is not None: g['mfe_sum'] += mfe
                if mae is not None: g['mae_sum'] += mae

    rows_out = []
    for (market, name), g in groups.items():
        resolved = g['tp'] + g['sl']
        rows_out.append({
            'market': market, 'candidate': name, 'n_evaluated': g['n'],
            'entry_reached_pct': round(g['entry'] / g['n'] * 100.0, 2) if g['n'] else None,
            'resolved': resolved, 'tp': g['tp'], 'sl': g['sl'], 'ambiguous': g['ambiguous'],
            'win_rate_pct': round(g['tp'] / resolved * 100.0, 2) if resolved else None,
            'expectancy_r': round(g['r_sum'] / g['r_n'], 4) if g['r_n'] else None,
            'avg_mfe_r': round(g['mfe_sum'] / g['n'], 4) if g['n'] else None,
            'avg_mae_r': round(g['mae_sum'] / g['n'], 4) if g['n'] else None,
            'evidence_state': 'REVIEWABLE' if resolved >= 25 else 'INSUFFICIENT',
        })
    rows_out.sort(key=lambda r: (r['market'], -(r['resolved'] or 0), -(r['expectancy_r'] or -999), r['candidate']))
    return {
        'version': CHALLENGER_LAB_VERSION,
        'authority': 'SHADOW_ONLY', 'production_change': False,
        'rows': rows_out,
        'policy': {
            'spot_futures_separate': True,
            'min_resolved_before_review': 25,
            'oos_required_before_promotion': True,
            'costs_required_before_promotion': True,
        },
    }
