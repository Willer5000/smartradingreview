"""Commit34 deterministic route authority: no simulated or implied profitability.

Authority is granted only to exact rows imported from an independently run,
chronologically split, committee-level replay.  Never activates from mere
candidate detections, selected OOS-only winners, or broad risk-class labels.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

MANIFEST = Path(__file__).with_name('commit34_live_authority.json')


def resolve(symbol, timeframe, action, family, existing_validated_family=''):
    result={'eligible':False,'reason':'NO_VERIFIED_COMMIT34_IS_OOS','family':str(family or '')}
    # Do not displace already validated 17.5.x routes.
    if existing_validated_family:
        result['reason']='EXISTING_VALIDATED_ROUTE_PRIORITY'; return result
    if str(os.getenv('COMMIT34_FAMILIES_ENABLED','1')).lower() in ('0','false','no'):
        result['reason']='FAMILIES_DISABLED'; return result
    try:
        payload=json.loads(MANIFEST.read_text(encoding='utf-8'))
        if payload.get('version')!='COMMIT34_LIVE_AUTHORITY_V1':return result
        key='|'.join(str(v or '').upper() for v in (symbol,timeframe,action,family))
        row=(payload.get('authorized_routes') or {}).get(key) or {}
        if not row or row.get('status')!='VALIDATED_IS_SELECTION_OOS':return result
        iss=row.get('is') or {};sel=row.get('selection') or {};oos=row.get('oos') or {}
        for metrics,minimum in ((iss,35),(sel,12),(oos,12)):
            if int(metrics.get('n') or 0)<minimum or float(metrics.get('expectancy_r') or 0)<=0:
                return result
        if float(oos.get('pf') or 0)<1.10:return result
        if not (row.get('geometry_source')=='EXACT_CANONICAL_COMMITTEE_REPLAY'
                and row.get('data_sha256') and row.get('code_sha256')
                and row.get('walk_forward_pass') is True):
            return result
        from commit34_family_engine import BANK_FAMILY
        result.update(eligible=True,reason='EXACT_VERIFIED_COMMIT34_ROUTE',
                      strategy_bank_family=BANK_FAMILY.get(str(family).upper()),
                      evidence_id=str(row.get('data_sha256'))[:16])
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return result
