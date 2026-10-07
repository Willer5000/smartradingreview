"""Offline deterministic validation for Commit30 Proposal 3.
No network, Supabase, Groq, Flask, or market-data provider calls.
"""
from __future__ import annotations
import json
import commit30_core as c30
from operational_intelligence import build_independent_thesis

layers = {
    'trend': {'direction':'bearish','adx':17.7,'plus_di':9.5,'minus_di':42.2},
    'momentum': {'direction':'bearish','score':-4.0,'indicators':{'rsi':23.9,'macd_histogram':-1.0}},
    'volume': {'volume_ratio':2.82,'obv_direction':'bearish'},
    'structure': {'structure_direction':'bearish','order_blocks':[{}], 'fair_value_gaps':[{}], 'liquidity_sweeps':[{}]},
    'volatility': {'bb_width':2.81,'atr_pct':1.0},
    'macro_context': {'risk_level':'NORMAL'},
    'liquidation': {'direction':'bearish'},
}
impulse = c30.detect_directional_impulse(layers['trend'], layers['momentum'], layers['volume'], layers['structure'])
regime = c30.classify_market_regime(layers['trend'], layers['volatility'], layers['momentum'], layers['volume'], layers['structure'])
thesis = build_independent_thesis(layers=layers, mtf_context={}, market='FUTURES', symbol='BTC-USDT', timeframe='1h')
result = {
    'version': c30.VERSION,
    'impulse': impulse,
    'regime': regime,
    'thesis': {k: thesis.get(k) for k in ('action','quality','short_score','short_families','required_independent_families','directional_impulse')},
    'pass': bool(impulse.get('active') and regime.get('regime') == 'DIRECTIONAL_IMPULSE_BEAR' and thesis.get('action') == 'SHORT'),
}
print(json.dumps(result, indent=2, ensure_ascii=False))
raise SystemExit(0 if result['pass'] else 1)
