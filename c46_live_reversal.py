"""C46: optional additive *LIVE* reversal lane, fail-closed.

Never touches accepted original signals. Operates only on verified CLOSED real candles
already loaded by the established scanner. New geometry and leverage must originate
from the deployed native Futures/Multi-Asset calculation, not from this module.
Official publication_quality still owns final authority. This code does NOT certify
historical profitability; see release notes and IS/OOS report.
"""
from __future__ import annotations
import os
from copy import deepcopy
from collections.abc import Mapping
from typing import Callable, Any

from countertrend_reversal_c46 import detect

VERSION = 'C46_LIVE_COUNTERTREND_V2_UNVALIDATED_OOS'


def _enabled():
    return str(os.environ.get('C46_LIVE_ENABLED', '1')).strip().lower() not in ('0','false','no','off')


def _f(value, default=0.):
    try:
        n=float(value)
        return n if __import__('math').isfinite(n) else default
    except (TypeError,ValueError,OverflowError):
        return default


def _rows(candles):
    """Construct only the small OHLCV slice required, without copying the dataframe."""
    if candles is None:return []
    if hasattr(candles,'iloc') and hasattr(candles,'columns'):
        cols=['open','high','low','close','volume']
        if not all(c in candles.columns for c in cols):return []
        return candles.iloc[-130:][cols].to_dict('records')
    if isinstance(candles,Mapping):
        fields=['open','high','low','close','volume']
        if not all(isinstance(candles.get(k),list) for k in fields):return []
        n=min(len(candles[k]) for k in fields)
        return [{k:candles[k][i] for k in fields} for i in range(max(0,n-130),n)]
    if isinstance(candles,(list,tuple)):
        return list(candles[-130:])
    return []


def _score_pct(value):
    v=_f(value)
    return v*100. if 0<v<=1. else v


def _strong_poi(levels):
    raw=' '.join(str(levels.get(k) or '') for k in ('entry_source','entry_location_basis','entry_location_context')).lower()
    positives=('order block','fvg','fair value gap','fibonacci','fib ', 'poc','vwap','liquidity','liquidación','liquidation','support','resistance','soporte','resistencia','retest','zona técnica','recuperación estructural')
    negatives=('fallback','market entry','market order','cierre anterior','close price','atr fallback','precio actual')
    return any(s in raw for s in positives) and not any(s in raw for s in negatives)


def maybe_promote_reversal(original: dict, candles: Any, *, symbol: str,
                           timeframe: str, market: str, engine: Any,
                           final_authority: Callable) -> dict:
    """Additive to LIVE only when the ORIGINAL canonical signal was rejected.

    On ANY incomplete evidence/exception returns original object unchanged.
    No extra fetch of OHLC, no workers, no cache, no per-user state.
    A candidate is published only if actual native Entry/SL/TP/Leverage and
    the ORIGINAL specialised Safety and publication_quality all approve.
    """
    if not _enabled() or not isinstance(original,dict):return original
    if original.get('success') is False or original.get('publication_eligible') or original.get('is_executable'):
        return original
    if original.get('source_candle_closed') is not True or original.get('market_data_is_synthetic') is not False:
        return original
    if original.get('analysis_mode') != 'CLOSED_CANDLE':return original
    if not str(original.get('source_candle_timestamp') or '').strip():return original
    # Never replace a valid incumbent, or reactivate an external risk veto.
    status=str(original.get('publication_status') or '').upper()
    if status in {'WAIT_EVENT','MACRO_VETO','RISK_HALT','SYSTEM_PAUSED'}:
        return original
    reason=' '.join((str(original.get('rejected_reason') or ''),
                     str((original.get('levels') or {}).get('rejected_reason') or ''))).upper()
    if any(term in reason for term in ('MACRO_EVENT_RISK','MARKET_DATA_FAILURE',
                'INSUFFICIENT_REAL_DATA','EXECUTION_RUNTIME_FAILED','CONTRACT_NOT_MAPPED')):
        return original
    if original.get('c46_reversal_live'):return original
    if market not in ('futures','multiasset'):return original
    if market == 'multiasset' and timeframe not in ('1h','4h'):return original
    if market == 'futures' and timeframe not in ('30m','1h','2h','4h'):return original
    try:
        candidates=detect(_rows(candles),symbol=symbol,timeframe=timeframe,market=market)
        if len(candidates)!=1:return original # do not arbitrate opposing hypotheses
        h=candidates[0]
        direction=h.get('action')
        if direction not in ('LONG','SHORT'):return original
        context=dict(original.get('quality_context') or {})
        trend=original.get('trend') or context.get('trend') or {}
        momentum=original.get('momentum') or context.get('momentum') or {}
        volatility=original.get('volatility') or context.get('volatility') or {}
        structure=original.get('structure') or context.get('structure') or {}
        if not all(isinstance(q,dict) and q for q in (trend,momentum,volatility,structure)):
            return original
        # A negative exact-route state is never rescued by a new strategy.
        prior=dict(original.get('operational_intelligence') or {})
        governance=prior.get('alpha_decay') or original.get('alpha_decay') or {}
        if isinstance(governance,Mapping):
            state=str(governance.get('state') or '').upper()
            if state in {'SHADOW','SHADOW_DIVERGED','ALPHA_DECAY','REVOKED','RETIRED'} or _f(governance.get('consecutive_losses'))>=8:
                return original
        known=prior.get('research_candidates') or {}
        if isinstance(known,Mapping):
            cell=known.get(direction) or known.get('COMPRA_SPOT' if direction=='LONG' else 'VENTA_SPOT') or {}
            if isinstance(cell,Mapping) and str(cell.get('state') or '').upper() in {
                'ALPHA_DECAY','SHADOW_DIVERGED','DEGRADED','REVOKED','NEGATIVE_OOS','REJECTED_OOS'}:
                return original
        # Protect original against mutations: parent calculates on copies.
        native = engine.calculate_entry_levels(
            direction, deepcopy(trend),deepcopy(momentum),deepcopy(volatility),
            deepcopy(structure),symbol,timeframe
        )
        if not isinstance(native,dict):return original
        if native.get('is_executable') is not True or native.get('is_rejected') is True:
            return original
        if not _strong_poi(native):return original
        e,s,t=(_f(native.get(k)) for k in ('entry','stop_loss','take_profit'))
        close=_f(h.get('reference_price'))
        if not all(z>0 for z in (e,s,t,close)):return original
        if not (s<e<=close<t if direction=='LONG' else t<e and e>=close and s>e):
            return original
        # A reversal SL must remain beyond the swept liquidity extreme.
        invalidation=_f(h.get('invalidating_price_reference'))
        if invalidation<=0 or (direction=='LONG' and s>invalidation) or (direction=='SHORT' and s<invalidation):
            return original
        # Never lower native guard thresholds. Strictly stronger entry and quality.
        if (_score_pct(native.get('entry_quality_score') or native.get('entry_score')) < 75 or
            _score_pct(native.get('sl_quality_score') or native.get('sl_reliability')) < 60 or
            _score_pct(native.get('tp_quality_score')) < 60):return original
        # New countertrend route requires premium-grade native execution safety.
        # It never converts an illustrative confluence score into a win probability.
        if _score_pct(native.get('execution_safety')) < 75.:return original
        lev=_f(native.get('leverage'))
        native_risk=native.get('risk_control') or {}
        if not (lev>=1 and isinstance(native_risk,Mapping) and
                str(native_risk.get('leverage_policy_version') or native.get('leverage_policy_version') or '').strip()):
            return original
        risk=abs(e-s); reward=abs(t-e)
        rr=reward/max(risk,1e-12)
        if rr<1.8 or rr>3.5:return original
        # Explicit economic scenario. Costs are in notional %; no profit assertion.
        target_pct=100*reward/e
        costs_pct=_f(os.getenv('C46_FEE_SLIPPAGE_FUNDING_PCT','0.16'),-1)
        if costs_pct<0 or not target_pct>costs_pct:return original
        if native.get('manual_geometry_fallback') or native.get('execution_runtime_failed'):
            return original
        entry_gate=native.get('entry_timing_gate') or {}
        reaction=native.get('entry_reaction_rc4') or {}
        lower=native.get('entry_lower_tf_confirmation') or {}
        if (isinstance(entry_gate,Mapping) and entry_gate.get('passed') is False) or (
            isinstance(reaction,Mapping) and reaction.get('hard_block') is True) or (
            isinstance(lower,Mapping) and lower.get('required') is True and lower.get('passed') is not True):
            return original
        if native.get('sl_reaction_conflict') is True or (
            isinstance(native_risk,Mapping) and native_risk.get('sl_reaction_conflict') is True):
            return original

        # Preserve source-candle identity and every field required by original
        # Safety/Quality. Candidate contract is separately traceable as C46.
        alt=dict(original)
        alt['levels']=dict(native)
        alt['levels'].update({
            'manual_observation_action':direction,
            'strategy_family':'SWEEP_REVERSAL',
            'setup_family':'SWEEP_REVERSAL',
            'entry_sweep_confirmed':True,
            'entry_mss_bos_confirmed':True,
            'c46_reversal_family':h['family'],
            'c46_reversal_version':VERSION,
        })
        alt['decision']={**dict(original.get('decision') or {}),'action':direction,
                         'original_action':'COMPRA_SPOT' if direction=='LONG' else 'VENTA_SPOT',
                         'confidence':_score_pct(native.get('execution_safety'))}
        family=h.get('family')
        evidence=h.get('evidence') or {}
        # Every support comes from actual measured fields of the closed OHLCV detector.
        # This is a technical hypothesis, NOT statistical OOS validation.
        rsi_gap=abs(_f(evidence.get('rsi_sweep'))-_f(evidence.get('rsi_anchor')))
        volume_ratio=_f(evidence.get('volume_ratio_proxy'))
        if not (rsi_gap>=3.0 and volume_ratio>=0.8 and
                evidence.get('confirmed_structure') is True and
                evidence.get('opposite_ema_context') is True and
                evidence.get('rejection') in ('floor','ceiling')):
            return original
        score=round(min(88.,75.+min(8.,max(0.,rsi_gap-3.))*0.9+
                        min(5.,max(0.,volume_ratio-0.8)*4.)),2)
        support=['LIQUIDITY_SWEEP','RSI_DIVERGENCE','STRUCTURAL_MSS',
                 'VOLUME_CONFIRMATION']
        contract={
            'passed':True,'action':direction,'source':'CORE_SETUP',
            'quality':score,'quality_floor':75.,
            'support':support,'support_count':len(support),'support_floor':4,
            'setup_family':'SWEEP_REVERSAL','ambiguous':False,
            'c46_detector':family,'historical_oos_validated':False,
            'c46_technical_evidence':dict(evidence),
        }
        alt['operational_intelligence']={**prior,'candidate_action':direction,
            'candidate_ready':True,'candidate_source':'CORE_SETUP',
            'core_setup_family':'SWEEP_REVERSAL',
            'candidate_contract':contract,'c46_additive_live':True,
        }
        alt['message']=(f'Posible reversión {direction} {symbol} {timeframe}, confirmada tras barrido de liquidez, '
                       f'divergencia y cambio de estructura. Entry {e:.8g} en zona de reacción; '
                       f'SL {s:.8g}, TP {t:.8g}, R/R {rr:.2f}, apalancamiento técnico {lev:g}x. '
                       'Sujeto a validación final de Safety y publicación.')
        alt['c46_reversal_live']=True
        alt['c46_detector_evidence']=dict(h.get('evidence') or {})
        alt['c46_previous_diagnostic_action']=str((original.get('decision') or {}).get('action') or '')
        # The same native publication authority as original Futures/Multi.
        vetted=final_authority(alt,symbol,timeframe)
        if not isinstance(vetted,dict):return original
        if not (vetted.get('publication_eligible') is True and vetted.get('is_executable') is True):
            return original
        if str((vetted.get('levels') or {}).get('publication_status') or '').upper()!='EXECUTABLE_SIGNAL':
            return original
        import hashlib
        seed=f"C46|{market}|{symbol}|{timeframe}|{direction}|{original.get('source_candle_timestamp') or ''}"
        vetted['signal_id']=hashlib.sha256(seed.encode()).hexdigest()[:24]
        vetted['c46_additive_not_a_historical_proof']=True
        vetted['c46_validation_status']='OOS_NOT_VALIDATED'
        vetted['c46_safety_gate']='ORIGINAL_PUBLICATION_AUTHORITY'
        # Remains the only representative for this asset*TF when replacing a
        # rejected original. Standard dispatcher/outbox manages the delivery.
        return vetted
    except Exception:
        return original
