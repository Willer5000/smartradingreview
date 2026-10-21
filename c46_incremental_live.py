"""C46 incremental candidates, only on an otherwise neutral existing router.

No I/O, timers, model inference, background processes, new historical input,
or changes to the canonical Entry/SL/TP/Safety/publication/leverage gates.
Candidates are NOT statistically certified: original OOS sample small.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Mapping

VERSION = 'C46-INCREMENTAL-LIVE-20261021'

# Nine precise symbol x timeframe x side x family observations from the user's
# independent *proxy* backtest. This is a LIMITED proposal, NOT an OOS guarantee.
ROUTES = (
    ('XRP-USDT','1H','SHORT','VWAP_RECLAIM_REVERSAL','VWMA',19),
    ('ETH-USDT','30M','LONG','FLOOR_CEILING_SWEEP_MSS','FVG',18),
    ('SOL-USDT','30M','SHORT','OB_STRUCTURAL_RECLAIM','OB',12),
    ('ETH-USDT','1H','LONG','OB_STRUCTURAL_RECLAIM','FVG',11),
    ('ETH-USDT','30M','LONG','DOUBLE_DIVERGENCE_REVERSAL','VWMA',11),
    ('ETH-USDT','30M','LONG','VWAP_RECLAIM_REVERSAL','OB',11),
    ('SOL-USDT','30M','LONG','ICHIMOKU_CLOUD_REVERSAL','VWMA',10),
    ('XRP-USDT','1H','LONG','FLOOR_CEILING_SWEEP_MSS','VWMA',9),
    ('ADA-USDT','30M','LONG','TREND_PULLBACK','FIB',7),
)


def _num(v, default=0.0):
    try:
        x = float(v)
        return x if x == x and abs(x) < float('inf') else default
    except (ValueError, TypeError):
        return default


def _upper(s):
    return str(s or '').strip().upper().replace('/','-')


def _direction_text(v):
    # Fail closed: empty or ambiguous values never count as evidence.
    value = _upper(v)
    if any(x in value for x in ('BULLISH','ALCIST','LONG','COMPRA')):
        return 'LONG'
    if any(x in value for x in ('BEARISH','BAJIST','SHORT','VENTA')):
        return 'SHORT'
    return ''


def _direction_rows(rows, side):
    if isinstance(rows, Mapping):
        rows = list(rows.values())
    if not isinstance(rows, (list,tuple)):
        return False
    for row in rows:
        if isinstance(row, Mapping):
            txt = (row.get('direction') or row.get('type') or row.get('side') or row.get('bias') or '')
        else:
            txt = str(row)
        if _direction_text(txt) == side:
            return True
    return False


def _divergence_types(momentum, side):
    # The original live app uses BOTH string tags in `divergences` and dictionaries
    # in `divergence_details`. Do not accidentally count hidden divergences.
    out = set()
    raw = list(momentum.get('divergences') or [])
    raw.extend(list(momentum.get('divergence_details') or []))
    target = 'BULL' if side=='LONG' else 'BEAR'
    for row in raw:
        if isinstance(row, Mapping):
            typ = _upper(row.get('direction') or row.get('type') or row.get('side'))
            if 'HIDDEN' in typ or _direction_text(typ) != side:
                continue
            name = _upper(row.get('oscillator') or row.get('indicator') or row.get('name') or row.get('source'))
        else:
            typ = _upper(row)
            if 'HIDDEN' in typ or target not in typ:
                continue
            name = typ
        if 'RSI' in name:
            out.add('RSI')
        if 'MACD' in name:
            out.add('MACD')
    return out


def _checks(layers: Mapping[str,Any], op: Mapping[str,Any], ev: Mapping[str,Any], route):
    symbol, tf, side, family, entry, n = route
    s = layers.get('structure') or {}
    t = layers.get('trend') or {}
    m = layers.get('momentum') or {}
    v = layers.get('volume') or {}
    vi = layers.get('volatility') or {}
    mtf = op.get('multi_timeframe') or {}
    groups = op.get('indicator_groups') or {}
    gtrend = groups.get('trend') or {}
    gstruct = groups.get('structure_liquidity') or {}
    gvol = groups.get('volume_flow') or {}
    price = _num(s.get('current_price') or gstruct.get('current_price'))
    indicators = t.get('indicators') or {}
    adx = _num(t.get('adx'))
    if not adx:
        adx = _num(gtrend.get('adx'))
    side_dir = 'BULLISH' if side == 'LONG' else 'BEARISH'
    opposite_dir = 'BEARISH' if side == 'LONG' else 'BULLISH'
    # Independently signed price zones only; don't count bullish and bearish
    # entries simply because a structure dictionary exists.
    obs = s.get('order_blocks') or []
    fvgs = s.get('fair_value_gaps') or s.get('fvgs') or []
    zone_ob = _direction_rows(obs,side)
    zone_fvg = _direction_rows(fvgs,side)
    has_fib = bool(s.get('fib_levels') or gstruct.get('fib_levels'))
    vwap = _num(v.get('vwap') or gvol.get('vwap'))
    has_vwap = price > 0 and vwap > 0 and ((price > vwap) if side=='LONG' else (price < vwap))
    psar = _direction_text(indicators.get('parabolic_sar_trend') or gtrend.get('psar')) == side
    ichi = _direction_text(indicators.get('ichimoku_cloud') or gtrend.get('ichimoku_cloud')) == side
    bb_position = (vi.get('bb_position') if vi.get('bb_position') is not None else (groups.get('volatility') or {}).get('bb_position'))
    bb_ok = bb_position is not None and ((0.1 <= _num(bb_position) <= 0.65) if side=='LONG' else (0.35 <= _num(bb_position) <= 0.9))
    strong_vol = _num(v.get('volume_ratio'),1) >= 1.1
    mom_dir = _direction_text(m.get('direction')) == side
    aligned_structure = bool(ev.get('structure'))
    aligned_momentum = bool(ev.get('momentum')) or mom_dir
    res = {
        'market_price_known': price > 0,
        'structure': aligned_structure,
        'momentum': aligned_momentum,
        'rejection_zone': (zone_fvg if entry=='FVG' else zone_ob if entry=='OB' else has_fib if entry=='FIB' else has_vwap),
        'structure_signed': zone_ob or zone_fvg,
    }
    if family=='FLOOR_CEILING_SWEEP_MSS':
        res.update({'sweep': bool(ev.get('sweep')), 'mss': bool(ev.get('mss')),
                    'momentum_confirmation':aligned_momentum})
    elif family=='OB_STRUCTURAL_RECLAIM':
        res.update({'order_block_confirmed':zone_ob, 'momentum_confirmation':aligned_momentum,
                    'adx':adx >= 18 if side=='LONG' else strong_vol and has_fib})
    elif family=='DOUBLE_DIVERGENCE_REVERSAL':
        res.update({'two_independent_divergences':len(_divergence_types(m,side)) >=2,
                    'psar':psar})
    elif family=='VWAP_RECLAIM_REVERSAL':
        res.update({'vwap_side':has_vwap,'structure_reclaim':bool(ev.get('pullback') or ev.get('mss')),
                    'extra_confirmation': (True if side=='SHORT' else bool(bb_ok and 'MACD' in _divergence_types(m,side)))})
    elif family=='ICHIMOKU_CLOUD_REVERSAL':
        res.update({'ichimoku':ichi,'psar':psar,'adx':adx>=18})
    elif family=='TREND_PULLBACK':
        res.update({'trend_aligned':bool(ev.get('trend')),'pullback':bool(ev.get('pullback')),
                    'fvg_present':zone_fvg,'vwap_value':vwap > 0})
    return res


def augment_candidate(op, *, layers, symbol, timeframe, system_type,
                      evidence_builder, select_strategy, official_cell):
    """Return same op unless an exact incremental LIVE technical setup exists.

    Admission is downstream: no premium inference, no SL/TP/leverage creation.
    """
    if os.getenv('C46_INCREMENTAL_LIVE_ENABLED','1').lower() in ('0','false','off','no'):
        return op
    if str(system_type).upper() != 'FUTURES' or op.get('candidate_ready'):
        return op
    if _upper(op.get('candidate_action')) not in ('','NO_OPERAR'):
        return op
    if _upper(op.get('candidate_source')) == 'MACRO_CRITICAL_HOLD':
        return op
    if _upper((op.get('thesis') or {}).get('macro_risk') or (layers.get('macro_context') or {}).get('risk_level')) == 'CRITICAL':
        return op
    if bool((op.get('multi_timeframe') or {}).get('conflict')):
        return op
    sym, tf = _upper(symbol), _upper(timeframe)
    # Never fill unspecified instruments or untested 2h/4h/multi-asset cells.
    matched = [r for r in ROUTES if (r[0],r[1]) == (sym,tf)]
    if not matched:
        return op
    candidates = []
    for route in matched:
        side = route[2]
        if not official_cell('FUTURES',sym,tf,side):
            continue
        # Existing adversarial research veto, when present, takes precedence.
        prior = ((op.get('research_candidates') or {}).get(side) or {})
        if _upper(prior.get('state')) in {'ALPHA_DECAY','REJECTED_OOS','NEGATIVE_OOS','REVOKED','DEGRADED'}:
            continue
        ev = evidence_builder(layers,op, 'BULLISH' if side=='LONG' else 'BEARISH')
        checks = _checks(layers,op,ev,route)
        if not all(checks.values()):
            continue
        # Require three DISTINCT evidence roles, without treating RSI and MACD
        # as separate independent families for thesis authorisation.
        support = ['structure','momentum','entry_zone']
        if ev.get('volume'):
            support.append('volume')
        if ev.get('mss'):
            support.append('structure_shift')
        if ev.get('mtf'):
            support.append('multi_timeframe')
        if len(support) < 4:
            continue
        candidates.append((route, checks, support))
    # Competing LONG and SHORT contracts in the same candle => abstain.
    if len(set(r[2] for r,_,_ in candidates)) != 1:
        return op
    # Multiple configs of same side: deterministic, highest OOS sample count
    # (not maximum historical winrate/expected profit).
    route, checks, support = sorted(candidates,key=lambda item:(-item[0][5], item[0][3]))[0]
    side, family = route[2],route[3]
    if side=='LONG' and _upper((op.get('thesis') or {}).get('direction')) == 'BEARISH':
        # Contrary to trend is allowed only if actual MSS and sweep or explicit
        # counter-direction confirmation are present in the current live layers.
        ev = evidence_builder(layers,op,'BULLISH')
        if not (ev.get('mss') and ev.get('sweep')):
            return op
    if side=='SHORT' and _upper((op.get('thesis') or {}).get('direction')) == 'BULLISH':
        ev = evidence_builder(layers,op,'BEARISH')
        if not (ev.get('mss') and ev.get('sweep')):
            return op
    preferred = ('SWEEP_REVERSAL' if 'SWEEP' in family or 'DIVERGENCE' in family or 'ICHIMOKU' in family
                 else 'TREND_PULLBACK' if family=='TREND_PULLBACK' else 'MEAN_REVERSION')
    strategy = select_strategy(op,layers=layers,symbol=sym,timeframe=tf,market='FUTURES',action=side,
                               preferred_family=preferred,is_multi=False)
    if not isinstance(strategy,dict) or strategy.get('id')=='NO_PLAYBOOK':
        return op
    # This is a deterministic technical SETUP score; it is not a win probability
    # and never sets Premium. Original quality, geometry, and publication remain.
    quality = 82.0 + min(6.0,2.0 * (len(support)-3))
    patched = dict(op)
    thesis = dict(patched.get('thesis') or {})
    thesis.update({'action':side, 'direction':'BULLISH' if side=='LONG' else 'BEARISH',
                   'quality':quality,'independent_support_families':list(support),
                   'c46_base_action':(patched.get('thesis') or {}).get('action')})
    patched['thesis'] = thesis
    patched['candidate_action']=side
    patched['candidate_ready']=True
    patched['candidate_source']='C46_INCREMENTAL_LIVE'
    patched['candidate_quality']=quality
    patched['core_setup_family']=('SWEEP_REVERSAL' if 'SWEEP' in family else preferred)
    patched['default_strategy']=strategy
    patched['official_cell']=True
    patched['never_bypass_safety']=True
    patched['candidate_contract']={
        'version': VERSION,'passed':True,'action':side,'source':'C46_INCREMENTAL_LIVE',
        'setup_family':preferred,'quality':quality,'quality_floor':82,
        'support':list(support),'support_count':len(support),'support_floor':4,
        'primary_geometry_is_downstream':True,'safety_is_downstream':True,
        'quality_is_rechecked_at_publication':False,
    }
    patched['c46_live_audit']={'route_id':f'{sym}:{tf}:{side}:{family}',
                                'historical_oos_proxy_trades':route[5],
                                'oos_statistically_validated':False,
                                'checks':dict(checks),'authority':'CANDIDATE_ONLY'}
    logging.getLogger('C46_INCREMENTAL').info(
        '[C46 LIVE] candidato adicional %s %s %s familia=%s (antes de Safety)',
        sym, tf, side, family,
    )
    return patched
