"""Commit 13 — Entry / SL / TP Challenger Lab.

All candidates are SHADOW.  They reuse the same closed OHLCV already loaded by
the analysis/evaluation workers and never alter the published Entry, SL, TP,
Safety, leverage or direction.  Their purpose is to compare defensibility and
net-execution geometry before any later governed promotion.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional
import hashlib
import math
import threading

import pandas as pd

from learning_integrity import learning_context, latest_result, normalize_action, normalize_market, safe_float

CHALLENGER_LAB_VERSION = "RC9_8_8_EXECUTION_CHALLENGER_LAB_V3"


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

    # RC9.8.8 — reachability challenger.
    #
    # The baseline Entry can be technically defensible yet so deep that price
    # repeatedly runs in the correct direction without ever filling.  This
    # challenger moves Entry only a bounded fraction toward the signal price,
    # keeps absolute risk no wider than baseline and preserves >=1.8R.  It is
    # SHADOW until enough chronological evidence proves both better activation
    # and acceptable post-entry expectancy.  It never changes direction.
    candidates = candidates[:4]
    baseline_risk = abs(baseline_entry - baseline_sl)
    initial_gap = (current - baseline_entry) if action == 'LONG' else (baseline_entry - current)
    if baseline_risk > 0 and initial_gap > max(0.10 * atr, 0.0):
        # Production safety remains stricter than the learning objective. We
        # never move the structural SL just to manufacture fills. Entry may
        # approach the signal price by at most 5% of baseline price-risk, while
        # SHADOW forensics still record the full missed-gap/retracement data.
        shift = min(initial_gap * 0.35, atr * 0.35, baseline_risk * 0.05)
        if action == 'LONG':
            e_entry = min(current - 0.10 * atr, baseline_entry + shift)
            e_entry = max(baseline_entry, e_entry)
            e_sl = baseline_sl
            new_risk = abs(e_entry - e_sl)
            e_tp = max(baseline_tp, e_entry + new_risk * 1.8)
        else:
            e_entry = max(current + 0.10 * atr, baseline_entry - shift)
            e_entry = min(baseline_entry, e_entry)
            e_sl = baseline_sl
            new_risk = abs(e_entry - e_sl)
            e_tp = min(baseline_tp, e_entry - new_risk * 1.8)
        reachability = _candidate(
            'REACHABILITY_BALANCED',
            e_entry, e_sl, e_tp, action,
            'BOUNDED_ENTRY_REACHABILITY',
            reason=(
                'Shadow alternative for missed fills: bounded by 35% of Entry gap, '
                '0.35 ATR and 5% of baseline risk; structural SL is preserved'
            ),
        )
        reachability['entry_shift_from_baseline_pct'] = round(
            abs((e_entry or baseline_entry) - baseline_entry) / baseline_entry * 100.0, 6
        ) if baseline_entry else 0.0
        reachability['baseline_gap_to_signal_price_pct'] = round(
            initial_gap / current * 100.0, 6
        ) if current else 0.0
    else:
        reachability = None

    # Preserve the original Commit 13 contract: the base lab still exposes at
    # most four core candidates. RC9.8.8 keeps its reachability experiment in
    # a dedicated SHADOW field, so no earlier specialist candidate is displaced
    # and Commit 15 can still use its fifth microstructure slot.
    candidates = candidates[:4]
    return {
        'version': CHALLENGER_LAB_VERSION,
        'authority': 'SHADOW_ONLY',
        'production_change': False,
        'market': market,
        'action': action,
        'atr_reference': round(float(atr), 10),
        'candidates': candidates,
        'reachability_candidate': reachability,
        'status': 'OBSERVING',
        'policy': {
            'max_candidates_per_signal': 5,
            'reachability_candidate_out_of_band': True,
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
    if not isinstance(candidates, list):
        candidates = []
    reachability = lab.get('reachability_candidate') if isinstance(lab, dict) else None
    evaluation_candidates = list(candidates[:5])
    if isinstance(reachability, dict) and not any(
        isinstance(item, dict) and str(item.get('name') or '').upper() == 'REACHABILITY_BALANCED'
        for item in evaluation_candidates
    ):
        evaluation_candidates.append(reachability)
    if not evaluation_candidates:
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
    for candidate in evaluation_candidates[:6]:
        if not isinstance(candidate, dict) or not candidate.get('geometry_valid'):
            continue
        # Commit 15: conditional challengers form a subset cohort.  If the
        # predeclared condition was not met at signal time, there is nothing to
        # evaluate for this candidate; production remains unchanged.
        if candidate.get('activation_condition') and not candidate.get('condition_met_at_signal'):
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


def _profit_factor(values: List[float]) -> Optional[float]:
    gains = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    if losses <= 0:
        return 99.0 if gains > 0 else None
    return gains / losses


def _candidate_evaluation_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    direct = result.get('execution_challenger_results') or {}
    if isinstance(direct, dict) and direct:
        return direct
    forensics = result.get('execution_forensics') or {}
    if isinstance(forensics, dict):
        nested = forensics.get('execution_challenger_results') or {}
        return nested if isinstance(nested, dict) else {}
    return {}


def _signal_cost_r(result: Dict[str, Any]) -> Optional[float]:
    direct = safe_float(result.get('modeled_total_cost_r'))
    if direct is not None and direct >= 0:
        return direct
    gross = safe_float(result.get('gross_r'))
    net = safe_float(result.get('modeled_net_r'))
    if gross is not None and net is not None:
        return max(0.0, gross - net)
    return None


def _evidence_metrics(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Chronological profitability evidence plus an eight-trade decay watch.

    `expired_no_entry` observations remain in the activation sample but never
    enter WR/expectancy.  This preserves the contract: no fill == no trade.
    """
    resolved = [
        o for o in observations
        if o.get('status') in {'tp_hit', 'sl_hit'}
        and o.get('realized_r') is not None
    ]
    resolved.sort(key=lambda o: str(o.get('created_at') or ''))
    cut = (
        max(1, min(len(resolved) - 1, int(math.floor(len(resolved) * 0.70))))
        if len(resolved) >= 2 else len(resolved)
    )
    discovery = resolved[:cut]
    validation = resolved[cut:]

    def vals(rows, key):
        out = []
        for row in rows:
            value = safe_float(row.get(key))
            if value is not None:
                out.append(value)
        return out

    def effective_r(row):
        value = safe_float(row.get('net_r'))
        if value is None:
            value = safe_float(row.get('realized_r'))
        return value

    gross = vals(resolved, 'realized_r')
    net = vals(resolved, 'net_r')
    disc_net = vals(discovery, 'net_r')
    val_net = vals(validation, 'net_r')
    val_gross = vals(validation, 'realized_r')
    gross_pf = _profit_factor(gross)
    val_gross_pf = _profit_factor(val_gross)
    pf = _profit_factor(net)
    val_pf = _profit_factor(val_net)
    coverage = len(net) / len(resolved) * 100.0 if resolved else 0.0

    # RC9.8.8 Alpha Decay: a promoted execution geometry must be able to lose
    # authority faster than it gained it. Eight consecutive losses revoke it;
    # an eight-trade expectancy collapse versus its previous history also
    # forces revalidation. No no-entry observation is treated as a loss.
    recent8 = resolved[-8:]
    prior = resolved[:-8]
    recent_values = [v for v in (effective_r(row) for row in recent8) if v is not None]
    prior_values = [v for v in (effective_r(row) for row in prior) if v is not None]
    recent8_expectancy = (
        sum(recent_values) / len(recent_values)
        if len(recent_values) == 8 else None
    )
    prior_expectancy = (
        sum(prior_values) / len(prior_values)
        if prior_values else None
    )

    def sharpe_proxy(values):
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(max(0.0, variance))
        if std <= 1e-12:
            return 99.0 if mean > 0 else (-99.0 if mean < 0 else 0.0)
        return mean / std

    recent8_sharpe = sharpe_proxy(recent_values) if len(recent_values) == 8 else None
    prior_sharpe = sharpe_proxy(prior_values)
    consecutive_losses = 0
    for row in reversed(resolved):
        if str(row.get('status') or '').lower() == 'sl_hit':
            consecutive_losses += 1
        else:
            break

    alpha_decay_reason = None
    if consecutive_losses >= 8:
        alpha_decay_reason = 'EIGHT_CONSECUTIVE_LOSSES'
    elif (
        len(recent_values) == 8
        and prior_sharpe is not None
        and recent8_sharpe is not None
        and prior_sharpe >= 0.50
        and recent8_sharpe <= 0.0
        and (prior_sharpe - recent8_sharpe) >= 0.75
    ):
        alpha_decay_reason = 'EIGHT_TRADE_SHARPE_DECAY'
    elif (
        len(recent_values) == 8
        and prior_expectancy is not None
        and recent8_expectancy is not None
        and recent8_expectancy <= 0.0
        and (prior_expectancy - recent8_expectancy) >= 0.15
    ):
        alpha_decay_reason = 'EIGHT_TRADE_EXPECTANCY_DECAY'

    return {
        'resolved': len(resolved),
        'discovery_resolved': len(discovery),
        'validation_resolved': len(validation),
        'expectancy_r': round(sum(gross) / len(gross), 4) if gross else None,
        'validation_expectancy_r': round(sum(val_gross) / len(val_gross), 4) if val_gross else None,
        'profit_factor': round(gross_pf, 3) if gross_pf is not None else None,
        'validation_profit_factor': round(val_gross_pf, 3) if val_gross_pf is not None else None,
        'net_rows': len(net),
        'net_coverage_pct': round(coverage, 2),
        'net_expectancy_r': round(sum(net) / len(net), 4) if net else None,
        'discovery_net_expectancy_r': round(sum(disc_net) / len(disc_net), 4) if disc_net else None,
        'validation_net_expectancy_r': round(sum(val_net) / len(val_net), 4) if val_net else None,
        'net_profit_factor': round(pf, 3) if pf is not None else None,
        'validation_net_profit_factor': round(val_pf, 3) if val_pf is not None else None,
        'recent8_resolved': len(recent8),
        'recent8_expectancy_r': round(recent8_expectancy, 4) if recent8_expectancy is not None else None,
        'prior_expectancy_r': round(prior_expectancy, 4) if prior_expectancy is not None else None,
        'recent8_sharpe_proxy': round(recent8_sharpe, 4) if recent8_sharpe is not None else None,
        'prior_sharpe_proxy': round(prior_sharpe, 4) if prior_sharpe is not None else None,
        'consecutive_losses': int(consecutive_losses),
        'alpha_decay': bool(alpha_decay_reason),
        'alpha_decay_reason': alpha_decay_reason,
    }


def summarize_execution_challenger_evidence(scoped_rows: Dict[str, Iterable[Dict[str, Any]]]) -> Dict[str, Any]:
    """Compare C13 candidates chronologically and with conservative cost-R.

    Commit 14 reads the challenger snapshot persisted inside execution_forensics,
    so no new database column is required.  Net-R is a conservative proxy using
    the cost-R already modeled for the source signal; it is never called an
    exchange-realized result.
    """
    groups = defaultdict(list)
    counters = defaultdict(lambda: {'n': 0, 'entry': 0, 'tp': 0, 'sl': 0, 'ambiguous': 0, 'expired_no_entry': 0, 'expired_after_entry': 0, 'mfe_sum': 0.0, 'mfe_n': 0, 'mae_sum': 0.0, 'mae_n': 0})

    for rows in (scoped_rows or {}).values():
        for row in rows or []:
            market = normalize_market(row).upper() or 'UNKNOWN'
            symbol = str(row.get('symbol') or 'ALL').upper().replace('/', '-')
            timeframe = str(row.get('timeframe') or 'ALL').upper()
            action = normalize_action(row.get('action_normalized'))
            action = action if action in {'LONG', 'SHORT'} else 'ALL'
            result = latest_result(row)
            evaluation = _candidate_evaluation_from_result(result)
            items = evaluation.get('results') if isinstance(evaluation, dict) else []
            cost_r = _signal_cost_r(result)
            created_at = row.get('created_at') or result.get('created_at')
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or 'UNKNOWN').upper()
                key = (market, symbol, timeframe, action, name)
                c = counters[key]
                c['n'] += 1
                c['entry'] += int(bool(item.get('entry_reached')))
                status = str(item.get('status') or '').lower()
                if status == 'tp_hit': c['tp'] += 1
                elif status == 'sl_hit': c['sl'] += 1
                elif status == 'ambiguous': c['ambiguous'] += 1
                elif status == 'expired_no_entry': c['expired_no_entry'] += 1
                elif status == 'expired_after_entry': c['expired_after_entry'] += 1
                realized = safe_float(item.get('realized_r'))
                net_r = None
                if realized is not None and cost_r is not None:
                    net_r = realized - max(0.0, cost_r)
                mfe = safe_float(item.get('mfe_r'))
                mae = safe_float(item.get('mae_r'))
                if mfe is not None:
                    c['mfe_sum'] += mfe; c['mfe_n'] += 1
                if mae is not None:
                    c['mae_sum'] += mae; c['mae_n'] += 1
                groups[key].append({
                    'created_at': created_at,
                    'status': status,
                    'realized_r': realized,
                    'net_r': net_r,
                })

    metrics_by_key = {key: _evidence_metrics(obs) for key, obs in groups.items()}
    baseline_by_cell = {
        (market, symbol, timeframe, action): metrics
        for (market, symbol, timeframe, action, candidate), metrics in metrics_by_key.items()
        if candidate == 'BASELINE'
    }

    rows_out = []
    for key, observations in groups.items():
        market, symbol, timeframe, action, name = key
        c = counters[key]
        m = metrics_by_key[key]
        baseline = baseline_by_cell.get((market, symbol, timeframe, action)) or {}
        baseline_counter = counters.get((market, symbol, timeframe, action, 'BASELINE')) or {}
        baseline_n = int(baseline_counter.get('n') or 0)
        baseline_entry_pct = (
            float(baseline_counter.get('entry') or 0) / baseline_n * 100.0
            if baseline_n else None
        )
        candidate_entry_pct = (float(c.get('entry') or 0) / c['n'] * 100.0) if c['n'] else None
        entry_reach_improvement_pp = (
            candidate_entry_pct - baseline_entry_pct
            if candidate_entry_pct is not None and baseline_entry_pct is not None
            else None
        )
        val_net = safe_float(m.get('validation_net_expectancy_r'))
        base_val_net = safe_float(baseline.get('validation_net_expectancy_r'))
        improvement = None
        if val_net is not None and base_val_net is not None:
            improvement = val_net - base_val_net

        resolved = int(m.get('resolved') or 0)
        val_n = int(m.get('validation_resolved') or 0)
        net_cov = safe_float(m.get('net_coverage_pct'), 0.0) or 0.0
        net_exp = safe_float(m.get('net_expectancy_r'))
        pf = safe_float(m.get('net_profit_factor'))
        if (
            name != 'BASELINE' and resolved >= 50 and val_n >= 15 and net_cov >= 95.0
            and net_exp is not None and net_exp >= 0.10 and val_net is not None and val_net >= 0.10
            and pf is not None and pf >= 1.25 and improvement is not None and improvement >= 0.10
        ):
            evidence_state = 'ACTIVE_READY'
        elif (
            name != 'BASELINE' and resolved >= 25 and val_n >= 10 and net_cov >= 95.0
            and net_exp is not None and net_exp >= 0.05 and val_net is not None and val_net >= 0.05
            and pf is not None and pf >= 1.15 and improvement is not None and improvement >= 0.05
        ):
            evidence_state = 'CANARY_READY'
        elif resolved >= 25:
            evidence_state = 'REVIEWABLE'
        else:
            evidence_state = 'INSUFFICIENT'

        rows_out.append({
            'market': market,
            'symbol': symbol,
            'timeframe': timeframe,
            'action': action,
            'candidate': name,
            'n_evaluated': c['n'],
            'entry_reached_pct': round(candidate_entry_pct, 2) if candidate_entry_pct is not None else None,
            'baseline_entry_reached_pct': round(baseline_entry_pct, 2) if baseline_entry_pct is not None else None,
            'entry_reach_improvement_pp': round(entry_reach_improvement_pp, 2) if entry_reach_improvement_pp is not None else None,
            'no_entry_count': int(c.get('expired_no_entry') or 0),
            'expired_after_entry_count': int(c.get('expired_after_entry') or 0),
            'tp': c['tp'], 'sl': c['sl'], 'ambiguous': c['ambiguous'],
            'win_rate_pct': round(c['tp'] / resolved * 100.0, 2) if resolved else None,
            'avg_mfe_r': round(c['mfe_sum'] / c['mfe_n'], 4) if c['mfe_n'] else None,
            'avg_mae_r': round(c['mae_sum'] / c['mae_n'], 4) if c['mae_n'] else None,
            **m,
            'validation_net_improvement_vs_baseline_r': round(improvement, 4) if improvement is not None else None,
            'evidence_state': evidence_state,
            'economics_basis': 'MODELED_SIGNAL_COST_R_PROXY',
        })

    rows_out.sort(key=lambda r: (r['market'], r.get('symbol') or '', r.get('timeframe') or '', r.get('action') or 'ALL', -(r['resolved'] or 0), -(safe_float(r.get('validation_net_expectancy_r'), -999) or -999), r['candidate']))
    return {
        'version': CHALLENGER_LAB_VERSION,
        'authority': 'SHADOW_ONLY', 'production_change': False,
        'rows': rows_out,
        'policy': {
            'spot_futures_separate': True,
            'symbol_timeframe_action_specific': True,
            'min_resolved_before_review': 25,
            'oos_required_before_promotion': True,
            'costs_required_before_promotion': True,
            'cost_basis': 'CONSERVATIVE_MODELED_COST_R_FROM_SOURCE_SIGNAL',
            'no_entry_counts_as_trade': False,
            'no_entry_counts_in_win_rate': False,
            'entry_reachability_is_learning_evidence': True,
            'alpha_decay_window_resolved_trades': 8,
        },
    }


# ============================================================================
# COMMIT 14 — GOVERNED EXECUTION CHAMPION
# ============================================================================
_GOVERNED_EXECUTION_LOCK = threading.Lock()
_GOVERNED_EXECUTION_PROFILE: Dict[str, Any] = {'rows': [], 'selected': []}


def install_governed_execution_profile(profile: Dict[str, Any]) -> None:
    global _GOVERNED_EXECUTION_PROFILE
    safe_profile = deepcopy(profile if isinstance(profile, dict) else {})
    with _GOVERNED_EXECUTION_LOCK:
        _GOVERNED_EXECUTION_PROFILE = safe_profile


def get_governed_execution_profile() -> Dict[str, Any]:
    with _GOVERNED_EXECUTION_LOCK:
        return deepcopy(_GOVERNED_EXECUTION_PROFILE)


def _canary_selected(analysis: Dict[str, Any], fraction: float) -> bool:
    timestamp = str(
        analysis.get('source_candle_timestamp')
        or (analysis.get('levels') or {}).get('source_candle_timestamp')
        or ''
    )
    if not timestamp:
        return False
    key = f"{analysis.get('symbol')}|{analysis.get('timeframe')}|{timestamp}"
    bucket = int(hashlib.sha256(key.encode('utf-8')).hexdigest()[:8], 16) % 10000
    return bucket < int(max(0.0, min(1.0, fraction)) * 10000)


def apply_governed_execution_calibration(analysis: Dict[str, Any], lab: Dict[str, Any]) -> Dict[str, Any]:
    """Apply one already-governed Entry geometry champion without changing direction.

    RC9.8.8 supports Spot and Futures separately. CANARY affects a deterministic
    25% of eligible source candles; ACTIVE affects all eligible signals. A
    candidate is rejected if it widens baseline risk by more than 5%. Safety is
    never lowered and a missed Entry is never converted into a trade result.
    """
    audit = {
        'version': 'RC9_8_8_GOVERNED_ENTRY_CALIBRATION_V1',
        'applied': False,
        'state': 'OBSERVE',
        'candidate': None,
        'reason': 'NO_GOVERNED_CHAMPION',
    }
    if not isinstance(analysis, dict) or not isinstance(lab, dict):
        return audit
    market = str(analysis.get('system_type') or '').upper()
    if market not in {'FUTURES', 'SPOT'}:
        audit['reason'] = 'UNSUPPORTED_MARKET'
        return audit

    profile = get_governed_execution_profile()
    selected_rows = profile.get('selected') or []
    if isinstance(selected_rows, dict):
        selected_rows = [selected_rows]
    symbol = str(analysis.get('symbol') or '').upper().replace('/', '-')
    timeframe = str(analysis.get('timeframe') or '').upper()
    current_action = normalize_action((analysis.get('decision') or {}).get('action'))
    selected = next((r for r in selected_rows if isinstance(r, dict)
                     and str(r.get('market') or '').upper() == market
                     and str(r.get('symbol') or 'ALL').upper().replace('/', '-') in {'ALL', symbol}
                     and str(r.get('timeframe') or 'ALL').upper() in {'ALL', timeframe}
                     and str(r.get('action') or 'ALL').upper() in {'ALL', current_action}), None)
    if not selected:
        audit['reason'] = 'NO_GOVERNED_CHAMPION_FOR_CELL'
        return audit
    state = str(selected.get('state') or 'OBSERVE').upper()
    if state not in {'CANARY', 'ACTIVE'}:
        audit['reason'] = 'CHAMPION_NOT_PROMOTED'
        return audit
    if state == 'CANARY' and not _canary_selected(analysis, safe_float(profile.get('canary_fraction'), 0.25) or 0.25):
        audit.update({'state': 'CANARY', 'candidate': selected.get('candidate'), 'reason': 'CANARY_CONTROL_BUCKET'})
        return audit

    name = str(selected.get('candidate') or '').upper()
    candidates = list(lab.get('candidates') or [])
    reachability = lab.get('reachability_candidate')
    if isinstance(reachability, dict):
        candidates.append(reachability)
    candidate = next((c for c in candidates if isinstance(c, dict) and str(c.get('name') or '').upper() == name), None)
    if not candidate or not candidate.get('geometry_valid'):
        audit.update({'state': state, 'candidate': name, 'reason': 'CANDIDATE_NOT_AVAILABLE_THIS_SIGNAL'})
        return audit

    action = current_action
    if normalize_action(candidate.get('action')) != action or action not in {'LONG', 'SHORT'}:
        audit.update({'state': state, 'candidate': name, 'reason': 'DIRECTION_GUARD'})
        return audit

    levels = analysis.get('levels') or {}
    base_entry = _positive(levels.get('entry'))
    base_sl = _positive(levels.get('stop_loss'))
    new_entry = _positive(candidate.get('entry'))
    new_sl = _positive(candidate.get('stop_loss'))
    new_tp = _positive(candidate.get('take_profit'))
    if not all((base_entry, base_sl, new_entry, new_sl, new_tp)):
        audit.update({'state': state, 'candidate': name, 'reason': 'MISSING_GEOMETRY'})
        return audit
    base_risk = abs(base_entry - base_sl)
    new_risk = abs(new_entry - new_sl)
    if base_risk <= 0 or new_risk > base_risk * 1.05:
        audit.update({'state': state, 'candidate': name, 'reason': 'NO_STOP_WIDENING_GUARD'})
        return audit

    old = {'entry': base_entry, 'stop_loss': base_sl, 'take_profit': _positive(levels.get('take_profit'))}
    levels['entry'] = float(new_entry)
    levels['stop_loss'] = float(new_sl)
    levels['take_profit'] = float(new_tp)
    levels['risk_reward'] = float(candidate.get('risk_reward') or 0.0)
    analysis['levels'] = levels
    audit.update({
        'applied': True,
        'state': state,
        'candidate': name,
        'reason': 'GOVERNED_EXECUTION_CHAMPION',
        'baseline': old,
        'calibrated': {'entry': new_entry, 'stop_loss': new_sl, 'take_profit': new_tp},
    })
    return audit
