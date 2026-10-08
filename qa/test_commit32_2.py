import json, tempfile
from pathlib import Path
import pandas as pd

import commit32_2_strategy_governance as gov
from commit32_2_runtime_patch import _sanitize_reason_list
from commit32_2_backtest import trades


def test_legacy_reason_cleanup():
    out=_sanitize_reason_list(['FALLBACK_GEOMETRY_NOT_PUBLISHABLE','PREMIUM_SAFETY_BELOW_75'])
    assert 'PREMIUM_SAFETY_BELOW_75' not in out
    assert 'STALE_LEGACY_POLICY_REASON_REEVALUATED' in out


def test_pending_never_live():
    snap=gov.snapshot()
    assert snap['strategies']['CRT_LIQUIDITY_RANGE_RECLAIM_V1']['production_authority'] is False
    assert snap['strategies']['TRIPLE_RSI_MOMENTUM_TIMING_V1']['production_authority'] is False


def test_evidence_pass_rules():
    row={'verdict':'PASS','costs_included':True,'chronological_split':True,'rules_frozen_before_oos':True,
         'in_sample':{'expectancy_r':0.1,'profit_factor':1.2},
         'out_of_sample':{'expectancy_r':0.08,'profit_factor':1.15,'trades':35}}
    assert gov.evidence_passes(row)
    row['out_of_sample']['trades']=29
    assert not gov.evidence_passes(row)


def test_eight_losses_demote_and_win_resets():
    state={'production_authority':True,'state':'ACTIVE','live_consecutive_losses':0}
    for _ in range(7): state=gov.apply_live_outcome(state,outcome='SL')
    assert state['production_authority'] is True
    state=gov.apply_live_outcome(state,outcome='TP')
    assert state['live_consecutive_losses']==0
    for _ in range(8): state=gov.apply_live_outcome(state,outcome='SL')
    assert state['state']=='SHADOW' and state['production_authority'] is False


def test_oos_start_index_prevents_warmup_signal_leakage():
    n=120
    df=pd.DataFrame({'open':[100.0]*n,'high':[102.0]*n,'low':[99.0]*n,'close':[101.0]*n,'atr':[1.0]*n})
    l=pd.Series([False]*n); s=pd.Series([False]*n)
    l.iloc[60]=True; l.iloc[90]=True
    rs=trades(df,l,s,start_index=80)
    assert len(rs)==1


def test_entrypoint_wiring_files():
    root=Path(__file__).resolve().parents[1]
    assert 'commit32_2_main_entrypoint:app' in (root/'Procfile').read_text()
    assert 'commit32_2_main_entrypoint:app' in (root/'render.yaml').read_text()
